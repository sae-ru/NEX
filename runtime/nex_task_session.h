#pragma once
// Compiler-private matching-runtime host API for checked030 provider exports.
#include "nex_cell_host.h"
#include "nex_task_frame.h"
#include "nex_task_limits.h"

namespace nexrt {
struct NativeTaskSessionOptions {
  CellHeapLimits heap;
  ResourceRegionLimits resources;
  size_t maximumTasks=4096;
  TaskExternalLimits external;
};
struct NativeTaskInvocationOptions {
  TaskExecutionLimits limits;
  std::function<bool()> cancelled;
};
struct NativeTaskSessionStats {
  CellHeapStats heap;
  uint64_t invocations=0,sourceErrors=0,fatalExits=0;
  bool closed=false;
};
// Each call joins its source work before returning. Values and cells may survive
// between calls; raw Handles/task capabilities may not. Callers retain every code
// image until the session and its returned values/error packets have retired.
// No ambient file/foreign grant is captured. Any File grants in the explicit
// host must remain live; returned resource owners are promoted into the session.
class NativeTaskSession {
  struct Impl;std::shared_ptr<Impl> impl;
public:
  explicit NativeTaskSession(NativeTaskSessionOptions={},std::shared_ptr<const TaskFrameHostContext> host={});
  ~NativeTaskSession();
  NativeTaskSession(const NativeTaskSession&)=delete;
  NativeTaskSession &operator=(const NativeTaskSession&)=delete;
  Value invoke(const TaskCodeDescriptor &,const std::vector<Value> &arguments={},
               NativeTaskInvocationOptions={},SourceLocation={});
  NativeTaskSessionStats statistics();
  CellCollection collect();
  bool cancel()noexcept;
  bool closed()const noexcept;
  // close revokes immediately and defers destruction during an active call.
  // finish also waits for this session's physical resource retirement; callers
  // must first release outside physical borrows. Neither may run on another
  // thread; finish cannot run from an active invocation callback.
  void close();
  void finish();
};
}
