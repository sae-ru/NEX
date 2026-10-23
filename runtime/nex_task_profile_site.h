#pragma once
#include <cstddef>
#include <cstdint>
#include <type_traits>

namespace nexrt {
// Immutable compiler-owned source identity, never a graph-local node ID or
// execution authority. This fixed POD is separate from registration string_view.
struct TaskProfileCodeSite {
  const char *name,*file,*content;
  int64_t line;
};
struct TaskProfileCodeRegistry {
  int64_t abi;
  const TaskProfileCodeSite *sites;
  int64_t count;
  const char *component;
};
inline constexpr int64_t taskProfileRegistryABI=1;
inline constexpr size_t maximumTaskProfileRegistries=128;
inline constexpr size_t maximumTaskProfileCodeSites=16384;
inline constexpr size_t maximumTaskProfileCodeTextBytes=16*1024*1024;
static_assert(std::is_standard_layout_v<TaskProfileCodeSite>&&std::is_trivial_v<TaskProfileCodeSite>);
static_assert(sizeof(TaskProfileCodeSite)==32&&offsetof(TaskProfileCodeSite,line)==24);
static_assert(std::is_standard_layout_v<TaskProfileCodeRegistry>&&std::is_trivial_v<TaskProfileCodeRegistry>);
static_assert(sizeof(TaskProfileCodeRegistry)==32&&offsetof(TaskProfileCodeRegistry,sites)==8&&offsetof(TaskProfileCodeRegistry,count)==16&&offsetof(TaskProfileCodeRegistry,component)==24);
}
extern "C" {
// Profile builds call this before workers, source helpers or root Data values.
// Release/debug images keep the ordinary task application entry path.
void nex_task_profile_prepare(const nexrt::TaskProfileCodeSite *,int64_t);
void nex_task_profile_prepare_registries(const nexrt::TaskProfileCodeRegistry *const *,int64_t);
}
