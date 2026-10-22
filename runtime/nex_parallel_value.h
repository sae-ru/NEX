#pragma once
#include "nex_value.h"
#include <unordered_set>

namespace nexrt {
inline constexpr int64_t parallelMaximumWorkers=16;
inline constexpr size_t parallelMaximumItems=65536;
inline constexpr size_t parallelMaximumNodes=262144;
// Representation validation is shared by the native and reference evaluators.
// It traverses immutable captures as well as visible aggregate members; an
// opaque function signature alone cannot establish absence of file resources.
template<class Poll> void validateParallelValue(const Value &value,Poll poll){
  std::vector<Value> pending{value};std::unordered_set<const Data*> seen;size_t members=1;
  while(!pending.empty()){
    auto next=std::move(pending.back());pending.pop_back();
    if(next.tag!=Value::Object)continue;
    if(!next.object)throw DataError("E_PARALLEL_VALUE","parallel value has a null object");
    if(!seen.insert(next.object.get()).second)continue;
    if(seen.size()>parallelMaximumNodes)throw DataError("E_LIMIT","parallel value graph exceeds its object limit");
    if((seen.size()%64)==0)poll();
    if(next.object->kind==Data::File||next.object->kind==Data::TaskScope||next.object->kind==Data::Task||next.object->kind==Data::Channel)throw DataError("E_PARALLEL_VALUE","parallel values cannot contain file or task authority");
    if(next.object->values.size()>parallelMaximumNodes-members)throw DataError("E_LIMIT","parallel value graph exceeds its member limit");
    members+=next.object->values.size();pending.insert(pending.end(),next.object->values.begin(),next.object->values.end());
  }
}
}
