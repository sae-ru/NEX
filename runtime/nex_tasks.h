#pragma once
#include "nex_host.h"
#include "nex_task_external.h"
#include "nex_profile.h"
#include <coroutine>
#include <exception>
#include <optional>
#include <utility>

// Compiler-private development substrate, enabled only by NEX_ASYNC_TASKS.
// Used by the private compiled source bridge. Public task source support and
// asynchronous I/O remain pending.
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
  friend struct TaskValueAccess;
  struct Impl;std::shared_ptr<Impl> impl;
  static constexpr size_t none=static_cast<size_t>(-1);
public:
  class Scope {
    friend class TaskGroup;friend struct TaskValueAccess;friend struct Impl;
    std::weak_ptr<Impl> owner;size_t index=none;
    Scope(const std::shared_ptr<Impl> &owner,size_t index):owner(owner),index(index){}
  public:Scope()=default;bool empty()const noexcept{return index==none;}
  };
  class Ticket {
    friend class TaskGroup;friend struct TaskValueAccess;friend struct Impl;
    std::weak_ptr<Impl> owner;size_t index=none;
    Ticket(const std::shared_ptr<Impl> &owner,size_t index):owner(owner),index(index){}
  public:Ticket()=default;
  };
  class Channel {
    friend class TaskGroup;friend struct TaskValueAccess;friend struct Impl;
    std::weak_ptr<Impl> owner;size_t index=none;
    Channel(const std::shared_ptr<Impl> &owner,size_t index):owner(owner),index(index){}
  public:Channel()=default;
  };
  class Awaiter {
    friend class TaskGroup;friend struct TaskValueAccess;friend struct Impl;
    enum Kind { Yield, Future, Send, Receive, DrainScope } kind;
    TaskGroup *group;size_t target;Value value;
    SourceLocation location;
    Awaiter(Kind kind,TaskGroup *group,size_t target=none,Value value={}):kind(kind),group(group),target(target),value(std::move(value)){}
  public:
    Awaiter at(SourceLocation where)&&{location=where;return std::move(*this);}
    bool await_ready()const noexcept{return false;}
    bool await_suspend(TaskBody::Handle handle);
    TaskEvent await_resume();
  };
  class ExternalAwaiter {
    TaskGroup *group;TaskExternalTicket ticket;SourceLocation location;
    friend class TaskGroup;
    ExternalAwaiter(TaskGroup *group,TaskExternalTicket ticket):group(group),ticket(std::move(ticket)){}
  public:
    ExternalAwaiter at(SourceLocation where)&&{location=where;return std::move(*this);}
    bool await_ready()const noexcept{return false;}
    bool await_suspend(TaskBody::Handle);
    TaskExternalResult await_resume();
  };
  // Factories take snapshots by value, never borrowed Handle pointers. Bodies
  // may retain Value objects across suspension; raw runtime handles may not.
  using Factory=TaskBody (*)(TaskGroup&,Value,Value);
  // Invoked synchronously outside scheduler locks, before enqueue. The caller
  // context is borrowed only for this invocation; a coroutine must copy its
  // typed host state into parameters. No raw context is saved in a Job.
  using ContextFactory=TaskBody (*)(TaskGroup&,Value,Value,const void*);
  explicit TaskGroup(size_t workers=4,size_t maximumTasks=4096,TaskExternalLimits externalLimits={},bool sourceFileReadFailures=false);
  ~TaskGroup();
  TaskGroup(const TaskGroup&)=delete;
  TaskGroup &operator=(const TaskGroup&)=delete;
  Ticket spawn(Factory factory,Value input={},Value captures={});
  Ticket spawn(const Scope &,Factory,Value input={},Value captures={});
  Ticket spawnWithContext(ContextFactory,const void*,Value input={},Value captures={});
  Ticket spawnWithContext(const Scope &,ContextFactory,const void*,Value input={},Value captures={});
  Scope openScope(size_t workers);
  Scope currentScope()const;
  Scope currentScopeOrEmpty()const;
  Awaiter leaveScope(const Scope &,bool cancelChildren=false);
  bool scopeContains(const Scope &ancestor,const Scope &descendant)const;
  void requireScope(const Scope &)const;
  Value join(const Ticket &ticket);
  Awaiter await(const Ticket &ticket);
  Awaiter yield();
  Channel channel(size_t capacity);
  Channel channel(const Scope &,size_t capacity);
  Awaiter send(const Channel &channel,Value value);
  Awaiter receive(const Channel &channel);
  bool close(const Channel &channel);
  bool cancel(const Ticket &ticket);
  void cancel();
  // Private fixed host adapters only. Payload conversion to source Values must
  // occur after await_resume, on the owning task's scheduler worker.
  TaskExternalTicket submitExternal(std::shared_ptr<TaskExternalOperation>,size_t reservedBytes);
  ExternalAwaiter awaitExternal(const TaskExternalTicket &);
  TaskExternalStats externalStats()const;
  // Public020 fixed read bridge only: select a resource fatal before physical
  // drain and suppress further source execution. Private/019 groups keep their
  // existing policy unless explicitly constructed for this bridge.
  void failFileRead(std::exception_ptr);
  // Drain, join OS workers, destroy coroutine frames and surface unobserved
  // failures. Immutable results remain joinable while this group exists.
  void finish();
private:
  size_t taskIndex(const Ticket&)const;
  size_t channelIndex(const Channel&)const;
  size_t scopeIndex(const Scope&)const;
  Ticket spawnIn(size_t,Factory,Value,Value,ContextFactory=nullptr,const void*context=nullptr);
  Channel channelIn(size_t,size_t);
};
}
