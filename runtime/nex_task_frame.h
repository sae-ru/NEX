#pragma once
#include "nex_tasks.h"
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
class NativeTaskFrame {
public:
  TaskFrameDescriptor::Step step;
  std::vector<int64_t> kinds;
  std::vector<std::optional<Value>> slots;
  int64_t pc=0;
  bool completed=false;
  Value result;
  NativeTaskFrame(TaskFrameDescriptor,const std::vector<Value> &arguments);
  Value read(int64_t id,int64_t kind)const;
  void write(int64_t id,Value value,int64_t kind);
  void drop(int64_t id);
};
TaskBody executeTaskFrame(TaskGroup &,NativeTaskFrame);
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
}
