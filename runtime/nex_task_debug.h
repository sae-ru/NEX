#pragma once
#include "nex_task_debug_site.h"
#include <span>
namespace nexrt {
inline constexpr size_t maximumTaskDebugTasks=4096,maximumTaskDebugFrames=65536,
  maximumTaskDebugStack=256,maximumTaskDebugLocals=256;
enum class TaskDebugState:uint64_t {Queued,Running,Ready,Blocked,Draining,Terminal};
enum class TaskDebugWait:uint64_t {None,Future,Send,Receive,Scope,External};
inline constexpr uint64_t taskDebugUnavailable=1,taskDebugAtCheckpoint=2,taskDebugParked=4,
  taskDebugNotStarted=8,taskDebugTerminal=16,taskDebugOriginOmitted=32;
struct TaskDebugCatalog {
  uint64_t magic,abi,header_size,task_record_size,frame_record_size,code_record_size,point_record_size,binding_record_size;
  uint64_t codes_address,code_count,tasks_address,task_capacity,task_count,frames_address,frame_capacity,live_frames;
  uint64_t dropped_tasks,dropped_frames,invalid_transitions,maximum_stack_depth,maximum_locals;
};
struct TaskDebugTaskRecord {
  uint64_t source_sequence,scheduler_sequence,id,generation,run_epoch,worker_id,state,wait_kind,wait_target;
  uint64_t top_frame_slot,top_frame_id,frame_count,checkpoint_sequence,flags,origin_task_id,origin_frame_id;
};
struct TaskDebugFrameRecord {
  uint64_t sequence,id,task_id,parent_slot,parent_id,code_index,frame_address,point_index,depth,flags;
};
struct TaskDebugStop {
  uint64_t catalog_address,task_slot,task_id,frame_slot,frame_id,point_index,checkpoint_sequence,source_sequence;
};
static_assert(sizeof(TaskDebugCatalog)==168&&sizeof(TaskDebugTaskRecord)==128&&sizeof(TaskDebugFrameRecord)==80&&sizeof(TaskDebugStop)==64);
static_assert(std::is_trivial_v<TaskDebugCatalog>&&std::is_standard_layout_v<TaskDebugCatalog>);
static_assert(std::is_trivial_v<TaskDebugTaskRecord>&&std::is_standard_layout_v<TaskDebugTaskRecord>);
static_assert(std::is_trivial_v<TaskDebugFrameRecord>&&std::is_standard_layout_v<TaskDebugFrameRecord>);
namespace task_debug_detail {struct State;}
struct TaskDebugTask {
  task_debug_detail::State *owner=nullptr;uint64_t slot=noTaskDebugIndex,id=0;
  explicit operator bool()const noexcept{return owner&&id;}
};
class TaskDebugFrame {
  task_debug_detail::State *owner=nullptr;uint64_t slot=noTaskDebugIndex,id=0,taskId=0;
  void retire()noexcept;
  friend struct TaskDebugFrameView;
  friend void taskDebugPublish(std::span<const struct TaskDebugFrameView>,bool)noexcept;
public:
  TaskDebugFrame()noexcept=default;
  explicit TaskDebugFrame(size_t codeIndex)noexcept;
  ~TaskDebugFrame(){retire();}
  TaskDebugFrame(TaskDebugFrame&&)noexcept;
  TaskDebugFrame &operator=(TaskDebugFrame&&)noexcept;
  TaskDebugFrame(const TaskDebugFrame&)=delete;
  TaskDebugFrame &operator=(const TaskDebugFrame&)=delete;
  uint64_t activation()const noexcept{return id;}
  explicit operator bool()const noexcept{return owner&&id;}
};
struct TaskDebugFrameView {const TaskDebugFrame *frame;const void *address;uint64_t point=noTaskDebugIndex,flags=0;};
bool taskDebugEnabled()noexcept;
void taskDebugUnavailableCurrent()noexcept;
TaskDebugTask taskDebugCreateTask()noexcept;
TaskDebugTask taskDebugCurrentTask()noexcept;
void taskDebugInvalidate(const TaskDebugTask&)noexcept;
// Atomic POD-only; safe inside the existing scheduler mutex. No debug lock,
// allocation, clock, callback, marker, Value or frame traversal occurs here.
void taskDebugKernelState(const TaskDebugTask&,TaskDebugState,TaskDebugWait=TaskDebugWait::None,uint64_t target=0)noexcept;
class TaskDebugTurn {
  TaskDebugTask previous;
public:
  explicit TaskDebugTurn(const TaskDebugTask&)noexcept;
  ~TaskDebugTurn();
  TaskDebugTurn(const TaskDebugTurn&)=delete;
};
class TaskDebugStackRegistration {
  TaskDebugTask task;
public:
  explicit TaskDebugStackRegistration(void*)noexcept;
  ~TaskDebugStackRegistration();
  TaskDebugStackRegistration(const TaskDebugStackRegistration&)=delete;
};
void *taskDebugCurrentStack()noexcept;
uint64_t taskDebugCodeIndex(const void *descriptor)noexcept;
void taskDebugPublish(std::span<const TaskDebugFrameView>,bool checkpoint)noexcept;
// Defined by the native frame driver. Called outside kernel locks only, after
// the awaiter has accepted a real park; immediate awaits never publish a park.
void taskDebugPublishPark()noexcept;
}
extern "C" {
extern nexrt::TaskDebugCatalog nex_task_debug_catalog_v1;
void nex_task_debug_stop_marker(const nexrt::TaskDebugStop *stop)noexcept;
}
