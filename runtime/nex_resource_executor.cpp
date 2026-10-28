#include "nex_resource_executor.h"
#include <algorithm>
#include <atomic>
#include <condition_variable>
#include <exception>
#include <mutex>
#include <thread>
#include <utility>
#include <vector>

namespace nexrt {
namespace resource_executor_detail {
struct Completion {
  std::atomic<bool> cancel{false},settled{false};
  std::mutex mutex;
  std::condition_variable changed;
  std::exception_ptr failure;
  std::thread::id executor;
};
// Adapter exceptions can contain destructors/vtables from a retained module.
// Normalize while the operation still pins that module; never put the original
// exception object into the completion mailbox.
std::exception_ptr checkedFailure()noexcept{
  try{throw;}
  catch(const DataError &error){
    try{throw DataError(error.code.size()<=128?error.code:"E_RUNTIME",std::string(std::string_view(error.what()).substr(0,4096)));}
    catch(...){return std::current_exception();}
  }
  catch(const std::bad_alloc &){return std::make_exception_ptr(std::bad_alloc{});}
  catch(...){try{throw DataError("E_RUNTIME","resource host operation failed");}catch(...){return std::current_exception();}}
}
struct Work {
  enum Phase { Free,Reserved,Queued,Running } phase=Free;
  Work *next=nullptr;
  void *payload=nullptr;
  void(*destroy)(void*)noexcept=nullptr;
  std::unique_ptr<ResourceExecutionOperation> operation;
  std::shared_ptr<Completion> completion;
  uint64_t bytes=0;
  std::shared_ptr<void> retirementHold;
};
struct State {
  const ResourceExecutorLimits limits;
  std::vector<Work> cleanups,operations;
  mutable std::mutex mutex;
  std::condition_variable changed;
  std::thread worker;
  std::mutex joinMutex;
  std::thread::id thread;
  Work *head=nullptr,*tail=nullptr;
  bool accepting=true,started=false,stopped=false;
  size_t liveResources=0,liveOperations=0,queued=0,running=0,settlementsPending=0;
  uint64_t reservedBytes=0;
  explicit State(ResourceExecutorLimits limits):limits(limits),cleanups(limits.resources),operations(limits.operations){}
  ~State(){
    // The worker retains its state through its final loop. If the last host
    // handle was released earlier, detach only here, after all physical work.
    if(worker.joinable()){
      if(worker.get_id()==std::this_thread::get_id())worker.detach();
      else worker.join();
    }
  }
  void append(Work &work)noexcept{
    work.phase=Work::Queued;work.next=nullptr;
    if(tail)tail->next=&work;else head=&work;tail=&work;++queued;
  }
  void close()noexcept{{std::lock_guard lock(mutex);accepting=false;}changed.notify_all();}
  void release(size_t index)noexcept{
    std::shared_ptr<void> released;
    {std::lock_guard lock(mutex);auto &work=cleanups[index];
      if(work.phase!=Work::Reserved)std::terminate();
      released=std::move(work.retirementHold);work.phase=Work::Free;--liveResources;if(released)++settlementsPending;
    }
    if(released){released.reset();std::lock_guard lock(mutex);--settlementsPending;}
    changed.notify_all();
  }
  void retain(size_t index,std::shared_ptr<void> hold){
    std::lock_guard lock(mutex);auto &work=cleanups[index];
    if(work.phase!=Work::Reserved||work.retirementHold||!hold)throw DataError("E_RESOURCE_EXECUTOR","cleanup settlement marker is unavailable or already attached");
    work.retirementHold=std::move(hold);
  }
  void retire(size_t index,void *payload,void(*destroy)(void*)noexcept)noexcept{
    {std::lock_guard lock(mutex);auto &work=cleanups[index];
      if(work.phase!=Work::Reserved||!payload||!destroy)std::terminate();
      work.payload=payload;work.destroy=destroy;append(work);
    }changed.notify_all();
  }
  void loop()noexcept{
    {std::lock_guard lock(mutex);thread=std::this_thread::get_id();started=true;}changed.notify_all();
    for(;;){
      Work *work=nullptr;
      {std::unique_lock lock(mutex);changed.wait(lock,[&]{return head||(!accepting&&!liveResources&&!liveOperations&&!settlementsPending);});
        if(!head){stopped=true;lock.unlock();changed.notify_all();return;}
        work=head;head=head->next;if(!head)tail=nullptr;
        work->phase=Work::Running;--queued;++running;
      }
      if(work->destroy){
        work->destroy(work->payload);
        std::shared_ptr<void> released;
        {std::lock_guard lock(mutex);work->payload=nullptr;work->destroy=nullptr;
          released=std::move(work->retirementHold);work->phase=Work::Free;--liveResources;}
        // A physical resource fence includes the executor's reserved slot, not
        // only the payload destructor. Re-entrant marker release is outside locks.
        released.reset();
        {std::lock_guard lock(mutex);--running;}
      }else{
        auto completion=work->completion;
        std::exception_ptr failure;
        try{ResourceExecutionControl control(completion);control.checkpoint();work->operation->run(control);}
        catch(...){failure=checkedFailure();}
        // Destructors can enqueue resource cleanup or re-enter host code. Never
        // execute them under the queue mutex and never signal early completion.
        work->operation.reset();
        {std::lock_guard lock(mutex);reservedBytes-=work->bytes;work->bytes=0;
          work->completion.reset();work->phase=Work::Free;--running;--liveOperations;}
        {std::lock_guard lock(completion->mutex);completion->failure=failure;
          completion->settled.store(true,std::memory_order_release);}
        completion->changed.notify_all();
      }
      changed.notify_all();
    }
  }
};
}
ResourceExecutionControl::ResourceExecutionControl(std::shared_ptr<resource_executor_detail::Completion> c):completion(std::move(c)){}
bool ResourceExecutionControl::cancelled()const noexcept{return completion->cancel.load();}
void ResourceExecutionControl::checkpoint()const{if(cancelled())throw DataError("E_CANCELLED","resource operation cancelled");}
ResourceExecution::ResourceExecution(std::shared_ptr<resource_executor_detail::Completion> c):completion(std::move(c)){}
void ResourceExecution::cancel()const noexcept{
  if(completion){std::lock_guard lock(completion->mutex);if(!completion->settled.load())completion->cancel.store(true);}
}
bool ResourceExecution::ready()const noexcept{return completion&&completion->settled.load(std::memory_order_acquire);}
void ResourceExecution::wait()const{
  auto retained=completion;if(!retained)throw DataError("E_RESOURCE_EXECUTOR","resource execution ticket is unavailable");
  if(retained->executor==std::this_thread::get_id())throw DataError("E_RESOURCE_EXECUTOR","cannot wait on the owning resource executor");
  std::unique_lock lock(retained->mutex);retained->changed.wait(lock,[&]{return retained->settled.load(std::memory_order_acquire);});
  auto failure=retained->failure;bool cancelled=retained->cancel.load();lock.unlock();
  if(failure)std::rethrow_exception(failure);
  if(cancelled)throw DataError("E_CANCELLED","resource operation cancelled after physical settlement");
}
ResourceCleanupTicket::ResourceCleanupTicket(std::shared_ptr<resource_executor_detail::State> s,size_t i):state(std::move(s)),slot(i){}
ResourceCleanupTicket::ResourceCleanupTicket(ResourceCleanupTicket &&other)noexcept:state(std::move(other.state)),slot(other.slot){}
ResourceCleanupTicket &ResourceCleanupTicket::operator=(ResourceCleanupTicket &&other)noexcept{
  if(this!=&other){if(state)state->release(slot);state=std::move(other.state);slot=other.slot;}return *this;
}
ResourceCleanupTicket::~ResourceCleanupTicket(){if(state)state->release(slot);}
void ResourceCleanupTicket::retainUntilSettled(std::shared_ptr<void> hold){
  if(!state)throw DataError("E_RESOURCE_EXECUTOR","cleanup reservation is unavailable");
  state->retain(slot,std::move(hold));
}
void ResourceCleanupTicket::retire(void *payload,void(*destroy)(void*)noexcept)noexcept{
  auto retained=std::move(state);if(!retained)std::terminate();retained->retire(slot,payload,destroy);
}
ResourceExecutor::ResourceExecutor(ResourceExecutorLimits limits){
  if(!limits.resources||limits.resources>4096||!limits.operations||limits.operations>64||!limits.reservedBytes||limits.reservedBytes>8*1024*1024)
    throw DataError("E_RESOURCE_EXECUTOR_LIMIT","resource executor limits exceed supported bounds");
  state=std::make_shared<resource_executor_detail::State>(limits);
  auto retained=state;state->worker=std::thread([retained]{retained->loop();});
  std::unique_lock lock(state->mutex);state->changed.wait(lock,[&]{return state->started;});
}
ResourceExecutor::~ResourceExecutor(){close();}
ResourceCleanupTicket ResourceExecutor::reserveCleanup(){
  std::lock_guard lock(state->mutex);
  if(!state->accepting)throw DataError("E_RESOURCE_EXECUTOR","resource executor is closed");
  for(size_t i=0;i<state->cleanups.size();++i)if(state->cleanups[i].phase==resource_executor_detail::Work::Free){
    state->cleanups[i].phase=resource_executor_detail::Work::Reserved;++state->liveResources;return ResourceCleanupTicket(state,i);
  }
  throw DataError("E_RESOURCE_EXECUTOR_LIMIT","resource executor cleanup capacity exhausted");
}
ResourceExecution ResourceExecutor::submit(std::unique_ptr<ResourceExecutionOperation> operation,uint64_t bytes){
  if(!operation)throw DataError("E_RESOURCE_EXECUTOR","resource operation is unavailable");
  auto completion=std::make_shared<resource_executor_detail::Completion>();completion->executor=state->thread;
  {std::lock_guard lock(state->mutex);
    if(!state->accepting)throw DataError("E_RESOURCE_EXECUTOR","resource executor is closed");
    if(bytes>state->limits.reservedBytes-state->reservedBytes)throw DataError("E_RESOURCE_EXECUTOR_LIMIT","resource executor byte reservation exhausted");
    auto it=std::find_if(state->operations.begin(),state->operations.end(),[](const auto &w){return w.phase==resource_executor_detail::Work::Free;});
    if(it==state->operations.end())throw DataError("E_RESOURCE_EXECUTOR_LIMIT","resource executor operation capacity exhausted");
    it->operation=std::move(operation);it->completion=completion;it->bytes=bytes;
    ++state->liveOperations;state->reservedBytes+=bytes;state->append(*it);
  }state->changed.notify_all();return ResourceExecution(std::move(completion));
}
void ResourceExecutor::invoke(std::function<void()> body){
  if(!body)throw DataError("E_RESOURCE_EXECUTOR","resource invocation is unavailable");
  if(onThread()){
    {std::lock_guard lock(state->mutex);if(!state->accepting)throw DataError("E_RESOURCE_EXECUTOR","resource executor is closed");}
    body();return;
  }
  struct Operation final:ResourceExecutionOperation {
    std::function<void()> body;
    explicit Operation(std::function<void()> body):body(std::move(body)){}
    void run(const ResourceExecutionControl&)override{body();}
  };
  submit(std::make_unique<Operation>(std::move(body))).wait();
}
bool ResourceExecutor::onThread()const noexcept{return state->thread==std::this_thread::get_id();}
void ResourceExecutor::close()noexcept{if(state)state->close();}
void ResourceExecutor::drain(){
  if(onThread())throw DataError("E_RESOURCE_EXECUTOR","cannot drain the owning resource executor");
  std::unique_lock lock(state->mutex);state->changed.wait(lock,[&]{return !state->queued&&!state->running&&!state->settlementsPending;});
}
void ResourceExecutor::finish(){
  if(onThread())throw DataError("E_RESOURCE_EXECUTOR","cannot finish the owning resource executor");
  close();std::lock_guard join(state->joinMutex);
  {std::unique_lock lock(state->mutex);state->changed.wait(lock,[&]{return state->stopped;});}
  if(state->worker.joinable())state->worker.join();
}
ResourceExecutorStats ResourceExecutor::stats()const{
  std::lock_guard lock(state->mutex);return {state->liveResources,state->liveOperations,state->queued,state->running,state->reservedBytes,state->accepting};
}
}
