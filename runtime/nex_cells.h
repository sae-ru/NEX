#pragma once
// Compiler-private managed-reference foundation. No public source type/ABI is enabled.
#include "nex_value.h"
#include <cstddef>

namespace nexrt {
struct CellHeapState;
struct CellHeapLimits {
  size_t maximumCells=1048576;
  size_t maximumNodes=4194304;
  size_t maximumEdges=16777216;
};
struct CellHeapStats {size_t cells=0,nodes=0,edges=0,collections=0;};
struct CellCollection {size_t beforeCells=0,afterCells=0,reclaimedCells=0,reclaimedNodes=0;};

// One heap belongs to one execution context. Mutation/collection are thread
// affine. close() tears down the context and invalidates outstanding cells.
// Immutable payload graphs are captured by ownership, not deep copied. Native
// callers must not mutate Data::values of an adopted immutable payload.
// Genuine file/external owners retain their independent resource authority.
// Cleanup callbacks cannot reenter operations; closing an active heap defers
// registry teardown until that operation unwinds. Close on the owner thread.
class CellHeap {
  std::shared_ptr<CellHeapState> state;
public:
  explicit CellHeap(CellHeapLimits limits={});
  ~CellHeap();
  CellHeap(const CellHeap&)=delete;
  CellHeap&operator=(const CellHeap&)=delete;
  Value create(Value initial);
  Value read(const Value &cell)const;
  void write(const Value &cell,Value value);
  CellCollection collect();
  CellHeapStats stats()const;
  void close()noexcept;
};
}
