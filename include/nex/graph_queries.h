#pragma once
#include <string>

namespace nex {
struct GraphQueryOptions {
  std::string query,entity="all",field="any",symbol,direction="dependencies";
  unsigned depth=1,offset=0,limit=100,edgeOffset=0,edgeLimit=100;
};
// Validate before opening/synchronizing any store, also for non-CLI callers.
void validateGraphQuery(const GraphQueryOptions &options,bool subgraph);
}
