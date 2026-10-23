#pragma once
#include <cstddef>
#include <cstdint>
#include <type_traits>
namespace nexrt {
inline constexpr uint64_t taskDebugCatalogABI=1;
inline constexpr uint64_t taskDebugCatalogMagic=UINT64_C(0x4e45584442473031);
inline constexpr uint64_t noTaskDebugIndex=UINT64_MAX;
inline constexpr size_t maximumTaskDebugCodes=16384,maximumTaskDebugPoints=262144,
  maximumTaskDebugBindings=65536,maximumTaskDebugVisibleBindings=1048576,
  maximumTaskDebugTextBytes=16*1024*1024,maximumTaskDebugMetadataBytes=64*1024*1024;
enum class TaskDebugPointKind:int64_t {Entry=0,Statement=1,Loop=2,Call=3,Resume=4,Return=5};
struct TaskDebugBinding {int64_t id;const char *name,*type;int64_t slot,scope;};
struct TaskDebugPoint {
  const char *site;
  int64_t pc,line,column,begin,end,kind,visibleBegin,visibleCount;
};
struct TaskDebugCodeSite {
  const void *code;
  const char *name,*file,*content,*functionHash;
  const TaskDebugPoint *points;
  const TaskDebugBinding *bindings;
  const int64_t *visibleBindings;
  int64_t pointCount,bindingCount,visibleCount,slotCount;
};
static_assert(sizeof(void*)==8&&sizeof(TaskDebugBinding)==40&&offsetof(TaskDebugBinding,name)==8);
static_assert(sizeof(TaskDebugPoint)==72&&offsetof(TaskDebugPoint,pc)==8);
static_assert(sizeof(TaskDebugCodeSite)==96&&offsetof(TaskDebugCodeSite,pointCount)==64);
static_assert(std::is_trivial_v<TaskDebugBinding>&&std::is_standard_layout_v<TaskDebugBinding>);
static_assert(std::is_trivial_v<TaskDebugPoint>&&std::is_standard_layout_v<TaskDebugPoint>);
static_assert(std::is_trivial_v<TaskDebugCodeSite>&&std::is_standard_layout_v<TaskDebugCodeSite>);
}
extern "C" {
void nex_task_debug_prepare(const nexrt::TaskDebugCodeSite*,int64_t count);
void nex_task_debug_checkpoint(void *frame,int64_t pointIndex)noexcept;
}
