#include "nex_task_external.h"
#include <algorithm>
#include <condition_variable>
#include <exception>
#include <limits>
#include <mutex>
#include <optional>
#include <string_view>
#include <thread>

namespace nexrt {
namespace task_external_detail {
struct State {
  enum Phase {Free,Queued,Running,Ready};
  struct Slot {
    Phase phase=Free;uint64_t generation=0,owner=0;size_t reservation=0;
    std::shared_ptr<std::atomic<bool>> stopped;
    std::shared_ptr<TaskExternalOperation> operation;
    TaskExternalControl control;
    TaskExternalResult result;std::exception_ptr failure;
  };
  TaskExternalLimits limits;TaskExternalPool::Notification notification;
  mutable std::mutex mutex;std::condition_variable changed;
  std::unique_ptr<Slot[]> slots;
  std::vector<size_t> queue;size_t start=0,count=0,physicalPending=0;
  TaskExternalStats ledger;bool sealed=false,stopping=false,joined=false,draining=false;
  std::vector<std::jthread> threads;
  State(TaskExternalLimits limits,TaskExternalPool::Notification notification):limits(limits),notification(std::move(notification)),slots(std::make_unique<Slot[]>(limits.tickets)),queue(limits.tickets){threads.reserve(limits.workers);}
};
// Never retain an adapter-defined exception object in a scheduler mailbox: its
// destructor may call arbitrary host code. Copy only bounded protocol errors;
// destroy the original on the IO worker, outside every runtime lock.
std::exception_ptr checkedFailure()noexcept{
  try{throw;}
  catch(const DataError &error){
    try{throw DataError(error.code.size()<=taskExternalErrorCodeCapacity?error.code:"E_RUNTIME",std::string(std::string_view(error.what()).substr(0,taskExternalErrorMessageCapacity)));}
    catch(...){return std::current_exception();}
  }
  catch(const std::bad_alloc &){return std::make_exception_ptr(std::bad_alloc{});}
  catch(...){try{throw DataError("E_RUNTIME","external host operation failed");}catch(...){return std::current_exception();}}
}
bool fatalFailure(const std::exception_ptr &failure){
  if(!failure)return false;
  try{std::rethrow_exception(failure);}
  catch(const DataError &error){return error.code=="E_MEMORY"||error.code=="E_LIMIT"||error.code=="E_TIMEOUT";}
  catch(const std::bad_alloc &){return true;}
  catch(...){return false;}
}
}
TaskExternalTicket::TaskExternalTicket(const std::shared_ptr<task_external_detail::State> &state,size_t slot,uint64_t generation,uint64_t owner):state(state),slot(slot),generation(generation),task(owner){}
TaskExternalPool::TaskExternalPool(TaskExternalLimits limits,Notification notification){
  if(!validTaskExternalLimits(limits))
    throw DataError("E_RANGE","external kernel requires1..2 workers,1..64 tickets,1..8MiB reservation and1..1MiB result limit");
  state=std::make_shared<task_external_detail::State>(limits,std::move(notification));
  try{
    for(size_t i=0;i<limits.workers;++i)state->threads.emplace_back([owned=state]{
      for(;;){
        size_t index;uint64_t generation,owner;size_t reservation;
        std::shared_ptr<TaskExternalOperation> operation;TaskExternalControl base;
        std::shared_ptr<std::atomic<bool>> stopped;
        {
          std::unique_lock lock(owned->mutex);owned->changed.wait(lock,[&]{return owned->stopping||owned->count;});
          if(!owned->count){if(owned->stopping)return;continue;}
          index=owned->queue[owned->start];owned->start=(owned->start+1)%owned->queue.size();--owned->count;
          auto &slot=owned->slots[index];slot.phase=task_external_detail::State::Running;
          generation=slot.generation;owner=slot.owner;reservation=slot.reservation;stopped=slot.stopped;
          operation=std::move(slot.operation);base=std::move(slot.control);
          --owned->ledger.queued;++owned->ledger.running;owned->ledger.maximumRunning=std::max(owned->ledger.maximumRunning,owned->ledger.running);
        }
        TaskExternalResult result;std::exception_ptr failure;
        try{
          TaskExternalControl control([base=std::move(base),stopped]{
            if(stopped->load())throw DataError("E_CANCELLED","external operation was cancelled");
            base.checkpoint();
          });
          control.checkpoint();result=operation->run(control);
          if(result.bytes.capacity()>owned->limits.maximumResultBytes||result.bytes.capacity()>reservation||result.errorCode.capacity()>taskExternalErrorCodeCapacity||result.errorMessage.capacity()>taskExternalErrorMessageCapacity)
            throw DataError("E_LIMIT","external result exceeds its reserved payload or protocol limit");
          if(result.errorCode=="E_MEMORY"||result.errorCode=="E_LIMIT"||result.errorCode=="E_TIMEOUT")throw DataError(result.errorCode,result.errorMessage);
          control.checkpoint();
        }catch(...){
          failure=task_external_detail::checkedFailure();
          TaskExternalResult rejected;result.bytes.swap(rejected.bytes);result.errorCode.swap(rejected.errorCode);result.errorMessage.swap(rejected.errorMessage);
        }
        // Lease/finally destruction precedes physical publication. No scheduler
        // or kernel lock is held while an adapter or its destructor runs.
        operation.reset();base=TaskExternalControl{};
        {
          std::lock_guard lock(owned->mutex);auto &slot=owned->slots[index];
          slot.result=std::move(result);slot.failure=std::move(failure);slot.phase=task_external_detail::State::Ready;
          --owned->ledger.running;--owned->physicalPending;
        }
        owned->changed.notify_all();
        if(owned->notification)owned->notification(TaskExternalTicket(owned,index,generation,owner));
      }
    });
  }catch(...){
    {std::lock_guard lock(state->mutex);state->stopping=true;}state->changed.notify_all();
    for(auto &thread:state->threads)thread.join();throw;
  }
}
TaskExternalPool::~TaskExternalPool(){drain(true);}
TaskExternalTicket TaskExternalPool::submit(uint64_t owner,std::shared_ptr<TaskExternalOperation> operation,size_t reservation,TaskExternalControl control){
  if(!operation)throw DataError("E_TASK_STATE","external operation is absent");
  if(reservation>state->limits.reservedBytes)throw DataError("E_LIMIT","external payload reservation exceeds the kernel byte limit");
  control.checkpoint();auto stopped=std::make_shared<std::atomic<bool>>(false);
  std::lock_guard lock(state->mutex);
  if(state->sealed)throw DataError("E_TASK_SCOPE","external admission has ended");
  if(state->ledger.tickets>=state->limits.tickets||reservation>state->limits.reservedBytes-state->ledger.reservedBytes)
    throw DataError("E_LIMIT","external ticket or aggregate byte limit exceeded");
  size_t index=state->limits.tickets;
  for(size_t i=0;i<state->limits.tickets;++i)if(state->slots[i].phase==task_external_detail::State::Free&&state->slots[i].generation!=UINT64_MAX){index=i;break;}
  if(index==state->limits.tickets)throw DataError("E_LIMIT","external ticket generations exhausted");
  auto &slot=state->slots[index];++slot.generation;slot.owner=owner;slot.reservation=reservation;slot.stopped=std::move(stopped);slot.operation=std::move(operation);slot.control=std::move(control);slot.phase=task_external_detail::State::Queued;
  ++state->ledger.tickets;state->ledger.reservedBytes+=reservation;++state->ledger.queued;++state->physicalPending;
  state->queue[(state->start+state->count)%state->queue.size()]=index;++state->count;state->changed.notify_one();
  return TaskExternalTicket(state,index,slot.generation,owner);
}
// Validation never resolves a foreign, consumed or previous-generation ticket
// against a newly occupied slot. Only scheduler/host code can consume a result.
#define NEX_EXTERNAL_SLOT(ticket) \
  if((ticket).state.owner_before(state)||state.owner_before((ticket).state)||(ticket).slot>=state->limits.tickets)throw DataError("E_TASK_SCOPE","external ticket belongs to another or ended kernel"); \
  auto &slot=state->slots[(ticket).slot]; \
  if(slot.phase==task_external_detail::State::Free||slot.generation!=(ticket).generation||slot.owner!=(ticket).task)throw DataError("E_TASK_STATE","external ticket is stale or already consumed")
void TaskExternalPool::cancel(const TaskExternalTicket &ticket){std::lock_guard lock(state->mutex);NEX_EXTERNAL_SLOT(ticket);slot.stopped->store(true);state->changed.notify_all();}
bool TaskExternalPool::ready(const TaskExternalTicket &ticket)const{std::lock_guard lock(state->mutex);NEX_EXTERNAL_SLOT(ticket);return slot.phase==task_external_detail::State::Ready;}
TaskExternalResult TaskExternalPool::take(const TaskExternalTicket &ticket){
  TaskExternalResult result;std::exception_ptr failure;bool stopped;
  {
    std::lock_guard lock(state->mutex);NEX_EXTERNAL_SLOT(ticket);
    if(slot.phase!=task_external_detail::State::Ready)throw DataError("E_TASK_STATE","external ticket has not physically retired");
    stopped=slot.stopped->load();result=std::move(slot.result);failure=std::move(slot.failure);
    --state->ledger.tickets;state->ledger.reservedBytes-=slot.reservation;slot.phase=task_external_detail::State::Free;slot.reservation=0;slot.stopped.reset();
  }
  if(task_external_detail::fatalFailure(failure))std::rethrow_exception(failure);
  if(stopped)throw DataError("E_CANCELLED","external operation was cancelled");
  if(failure)std::rethrow_exception(failure);
  return result;
}
void TaskExternalPool::discard(const TaskExternalTicket &ticket){
  TaskExternalResult result;std::exception_ptr failure;
  {
    std::lock_guard lock(state->mutex);NEX_EXTERNAL_SLOT(ticket);
    if(slot.phase!=task_external_detail::State::Ready)throw DataError("E_TASK_STATE","external ticket has not physically retired");
    result=std::move(slot.result);failure=std::move(slot.failure);
    --state->ledger.tickets;state->ledger.reservedBytes-=slot.reservation;slot.phase=task_external_detail::State::Free;slot.reservation=0;slot.stopped.reset();
  }
}
#undef NEX_EXTERNAL_SLOT
TaskExternalStats TaskExternalPool::stats()const{std::lock_guard lock(state->mutex);return state->ledger;}
void TaskExternalPool::drain(bool cancel){
  {
    std::unique_lock lock(state->mutex);if(state->joined)return;state->sealed=true;
    if(cancel)for(size_t i=0;i<state->limits.tickets;++i)if(state->slots[i].phase!=task_external_detail::State::Free)state->slots[i].stopped->store(true);
    if(state->draining){state->changed.wait(lock,[&]{return state->joined;});return;}
    state->draining=true;
    state->changed.wait(lock,[&]{return !state->physicalPending;});state->stopping=true;
  }
  state->changed.notify_all();for(auto &thread:state->threads)thread.join();
  for(size_t i=0;i<state->limits.tickets;++i){
    TaskExternalResult result;std::exception_ptr failure;
    {std::lock_guard lock(state->mutex);auto &slot=state->slots[i];if(slot.phase==task_external_detail::State::Free)continue;
      result=std::move(slot.result);failure=std::move(slot.failure);slot.phase=task_external_detail::State::Free;slot.stopped.reset();slot.reservation=0;}
  }
  {std::lock_guard lock(state->mutex);state->ledger.tickets=state->ledger.reservedBytes=0;state->joined=true;}state->changed.notify_all();
}
}
