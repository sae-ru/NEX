#pragma once
#include "nex_host.h"

namespace nexrt {
// Internal trusted-host substrate, not a source-language intrinsic or stable ABI.
// Available only in an explicitly NEX_STRUCTURED_WORKERS-enabled runtime build.
// The callback must only compute from its immutable input/environment and poll
// through the native runtime. No mutable callback state or external capability
// may be shared. Each callback's owned handles belong to its worker job.
using ParallelCallback=Value (*)(const Value &item,const Value &environment);
inline constexpr int64_t parallelMaximumWorkers=16;
inline constexpr size_t parallelMaximumItems=65536;
inline constexpr size_t parallelMaximumNodes=262144;
Value parallelValues(const Value &items,const Value &environment,int64_t workers,
                     ParallelCallback callback,SourceLocation location={});
}
