#pragma once
#include "nex_host.h"
#include <coroutine>
#include <exception>
#include <optional>
#include <utility>

// Compiler-private development substrate, enabled only by NEX_ASYNC_TASKS.
// NEX source types/lowering and asynchronous I/O are not implemented here.
namespace nexrt {
namespace task_detail {
struct Cancellation {
  std::atomic<bool> cancelled{false};
  std::shared_ptr<const Cancellation> parent;
  size_t depth=1;
  bool stopped()const noexcept {
    for(auto *p=this;p;p=p->parent.get())if(p->cancelled.load())return true;
    return false;
  }
};
}
class TaskGroup;
struct TaskBody {
  struct promise_type {
    Value value;std::exception_ptr failure;
    TaskBody get_return_object(){return TaskBody(std::coroutine_handle<promise_type>::from_promise(*this));}
    std::suspend_always initial_suspend()noexcept{return {};}
    std::suspend_always final_suspend()noexcept{return {};}
    void return_value(Value result)noexcept{value=std::move(result);}
    void unhandled_exception()noexcept{failure=std::current_exception();}
  };
  using Handle=std::coroutine_handle<promise_type>;
  Handle handle;
  explicit TaskBody(Handle handle):handle(handle){}
  TaskBody(TaskBody &&other)noexcept:handle(std::exchange(other.handle,{})){}
  TaskBody(const TaskBody&)=delete;
  ~TaskBody(){if(handle)handle.destroy();}
};
struct TaskEvent {bool present=false;Value value;};
class TaskGroup {
  struct Impl;std::shared_ptr<Impl> impl;
  static constexpr size_t none=static_cast<size_t>(-1);
public:
  class Ticket {
    friend class TaskGroup;
    std::weak_ptr<Impl> owner;size_t index=none;
    Ticket(const std::shared_ptr<Impl> &owner,size_t index):owner(owner),index(index){}
  public:Ticket()=default;
  };
  class Channel {
    friend class TaskGroup;
    std::weak_ptr<Impl> owner;size_t index=none;
    Channel(const std::shared_ptr<Impl> &owner,size_t index):owner(owner),index(index){}
  public:Channel()=default;
  };
  class Awaiter {
    friend class TaskGroup;
    enum Kind { Yield, Future, Send, Receive } kind;
    TaskGroup *group;size_t target;Value value;
    Awaiter(Kind kind,TaskGroup *group,size_t target=none,Value value={}):kind(kind),group(group),target(target),value(std::move(value)){}
  public:
    bool await_ready()const noexcept{return false;}
    bool await_suspend(TaskBody::Handle handle);
    TaskEvent await_resume();
  };
  // Factories take snapshots by value, never borrowed Handle pointers. Bodies
  // may retain Value objects across suspension; raw runtime handles may not.
  using Factory=TaskBody (*)(TaskGroup&,Value,Value);
  explicit TaskGroup(size_t workers=4,size_t maximumTasks=4096);
  ~TaskGroup();
  TaskGroup(const TaskGroup&)=delete;
  TaskGroup &operator=(const TaskGroup&)=delete;
  Ticket spawn(Factory factory,Value input={},Value captures={});
  Value join(const Ticket &ticket);
  Awaiter await(const Ticket &ticket);
  Awaiter yield();
  Channel channel(size_t capacity);
  Awaiter send(const Channel &channel,Value value);
  Awaiter receive(const Channel &channel);
  bool close(const Channel &channel);
  bool cancel(const Ticket &ticket);
  void cancel();
  // Drain, join OS workers, destroy coroutine frames and surface unobserved
  // failures. Immutable results remain joinable while this group exists.
  void finish();
private:
  size_t taskIndex(const Ticket&)const;
  size_t channelIndex(const Channel&)const;
};
}
