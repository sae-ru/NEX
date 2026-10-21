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

// Compiler-private bridge ABI. Scalar bits and an optional job-local heap
// handle avoid allocating a list/record for each argument or result. The bridge
// invokes a checked pure closure and writes exactly one result through the
// helpers below. Environment/input handles borrow retained immutable values;
// no coordinator Handle ever crosses a thread. Not a source operation yet.
enum class ParallelValueKind : int64_t { I64=0, Bool=1, F64=2, Heap=3 };
using CompiledParallelBridge=void (*)(Handle *environment,int64_t scalar,
                                    Handle *heap,void *result);
Value parallelCompiledValues(const Value &items,const Value &environment,
                             int64_t workers,CompiledParallelBridge bridge,
                             ParallelValueKind input,ParallelValueKind output,
                             SourceLocation location={});
}

#ifdef NEX_STRUCTURED_WORKERS
extern "C" {
void nex_parallel_return_i64(void *result,int64_t value,int64_t tag);
void nex_parallel_return_i64_at(void *result,int64_t value,int64_t tag,const nexrt::NativeSite *site);
void nex_parallel_return_heap(void *result,nexrt::Handle *value);
void nex_parallel_return_heap_at(void *result,nexrt::Handle *value,const nexrt::NativeSite *site);
}
#endif
