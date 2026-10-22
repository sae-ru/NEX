#pragma once
#include "nex_tasks.h"
#include "nex_task_values.h"
#include "nex_task_protocol.h"
#include <span>
namespace nexrt {
// A compiler-private ABI. Owned Values survive parking; Handles are only leases
// within one resume. The generated step owns a temporary-handle boundary.
struct TaskFrameDescriptor {
  using Step=int64_t (*)(void *);
  Step step=nullptr;
  std::span<const int64_t> kinds;
  std::span<const uint32_t> parameters;
};
// Emitted immutable data, separate from the ordinary closure function pointer.
// Pointer fields precede fixed-width counts to match the private LLVM ABI.
struct TaskCodeDescriptor {
  TaskFrameDescriptor::Step step;
  const int64_t *kinds,*parameters,*captures;
  int64_t abi,slotCount,parameterCount,captureCount,resultKind;
};
static_assert(sizeof(TaskCodeDescriptor)==72&&offsetof(TaskCodeDescriptor,abi)==32);
inline constexpr int64_t taskCodeABI=INT64_C(0x4e45585400000001);
struct NativeTaskRequest {
  TaskRequestKind operation;
  std::vector<Value> arguments;
  int64_t destination=-1,kind=4;
  SourceLocation location;
};
class NativeTaskFrame {
public:
  TaskFrameDescriptor::Step step;
  std::vector<int64_t> kinds;
  std::vector<std::optional<Value>> slots;
  int64_t pc=0;
  bool completed=false;
  Value result;
  int64_t expectedResult=-1,returnDestination=-1;
  size_t depth=1;
  std::unique_ptr<NativeTaskFrame> pendingCall;
  std::optional<NativeTaskRequest> pendingRequest;
  std::optional<TaskGroup::Scope> closingScope;
  TaskGroup::Scope parentScope;
  SourceLocation scopeLocation;
  NativeTaskFrame(TaskFrameDescriptor,const std::vector<Value> &arguments);
  NativeTaskFrame(const TaskCodeDescriptor &,const std::vector<Value> &arguments,const Value &environment);
  Value read(int64_t id,int64_t kind)const;
  void write(int64_t id,Value value,int64_t kind);
  void drop(int64_t id);
};
using TaskStepObserver=void (*)(const NativeTaskFrame &,int64_t);
TaskBody executeTaskFrame(TaskGroup &,NativeTaskFrame,TaskStepObserver=nullptr);
// Resume-local baseline, restored even when compiled code traps. Ordinary pure
// helper calls and retained logical task calls share the same depth budget.
size_t exchangeCompiledTaskDepth(size_t);
}
extern "C" {
int64_t nex_task_frame_pc(void *);
void nex_task_frame_set_pc(void *,int64_t);
int64_t nex_task_frame_get_i64(void *,int64_t,int64_t);
nexrt::Handle *nex_task_frame_get_heap(void *,int64_t);
void nex_task_frame_put_i64(void *,int64_t,int64_t,int64_t);
void nex_task_frame_put_heap(void *,int64_t,nexrt::Handle *);
void nex_task_frame_drop(void *,int64_t);
void nex_task_frame_return_i64(void *,int64_t,int64_t);
void nex_task_frame_return_heap(void *,nexrt::Handle *);
void nex_task_frame_return_unit(void *);
void nex_task_frame_bad_pc(void *);
void nex_task_frame_call_at(void *,void *,nexrt::Handle *,nexrt::Handle *,int64_t,int64_t,const nexrt::NativeSite *);
nexrt::Handle *nex_task_closure_new_at(void *,int64_t,const nexrt::NativeSite *);
void nex_task_closure_bind_at(nexrt::Handle *,void *,const nexrt::NativeSite *);
void nex_task_frame_pause_at(void *,int64_t,nexrt::Handle *,int64_t,int64_t,int64_t,const nexrt::NativeSite *);
}
