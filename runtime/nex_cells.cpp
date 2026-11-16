#include "nex_cells.h"
#include <algorithm>
#include <limits>
#include <mutex>
#include <thread>
#include <unordered_map>

namespace nexrt {
struct CellData final : Data {
  const std::weak_ptr<CellHeapState> heap;
  CellData(const std::shared_ptr<CellHeapState> &owner,int64_t identity,Value initial)
      :Data(Cell,sizeof(CellData)),heap(owner){ordinal=identity;values.push_back(std::move(initial));}
};

struct CellHeapState {
  const CellHeapLimits limits;
  const std::thread::id owner=std::this_thread::get_id();
  mutable std::recursive_mutex mutex;
  bool closed=false,busy=false;
  uint64_t nextIdentity=1;
  size_t cells=0,edges=0,collections=0,nextCollection=256;
  // Immutable children precede parents. Mutable cell edges are detached before
  // reclamation; reverse order then releases even long graphs without recursion.
  std::vector<nexrt::ValueOwner<Data>> nodes;
  std::unordered_map<const Data*,size_t> index;
  explicit CellHeapState(CellHeapLimits selected):limits(selected){
    if(!limits.maximumCells||!limits.maximumNodes||!limits.maximumEdges)
      throw DataError("E_CELL_LIMIT","managed heap limits must be positive");
    nextCollection=std::min(nextCollection,limits.maximumNodes);
  }
  void available()const {
    if(closed)throw DataError("E_CELL_CLOSED","managed heap is closed");
    if(owner!=std::this_thread::get_id())throw DataError("E_CELL_THREAD","managed heap belongs to another thread");
  }
  void retire()noexcept {
    busy=true;
    for(const auto &node:nodes)if(node->kind==Data::Cell)node->values.clear();
    while(!nodes.empty()){index.erase(nodes.back().get());nodes.pop_back();}
    cells=0;edges=0;busy=false;
  }
  struct Operation {
    CellHeapState &state;
    explicit Operation(CellHeapState &state):state(state){
      state.available();
      if(state.busy)throw DataError("E_CELL_REENTRY","managed heap operation cannot reenter cleanup or collection");
      state.busy=true;
    }
    ~Operation(){state.busy=false;if(state.closed)state.retire();}
  };
  CellData &cell(const Value &value)const {
    if(value.tag!=Value::Object||!value.object||value.object->kind!=Data::Cell)
      throw DataError("E_CELL_TYPE","expected a managed cell");
    auto &result=static_cast<CellData&>(*value.object);
    if(result.heap.lock().get()!=this)throw DataError("E_CELL_HEAP","cell belongs to another heap");
    if(!index.contains(&result)||result.values.size()!=1)throw DataError("E_CELL_CLOSED","managed cell is no longer live");
    return result;
  }
  void payloadKind(const nexrt::ValueOwner<Data> &value)const {
    if(!value)throw DataError("E_CELL_VALUE","managed payload contains a missing object");
    if(value->kind==Data::Cell){(void)cell(Value(value));return;}
    switch(value->kind){
    case Data::String:case Data::List:case Data::Record:case Data::Success:
    case Data::Failure:case Data::Enum:case Data::Closure:case Data::Bytes:return;
    case Data::File:{
      const auto &file=static_cast<const FileData&>(*value);
      if(file.diagnosticIdentity||!file.resource.identity()||!file.values.empty())
        throw DataError("E_CELL_VALUE","managed payload requires a genuine leaf file owner");
      return;
    }
    case Data::External:
      if(!externalResource(value).identity()||!value->values.empty())
        throw DataError("E_CELL_VALUE","managed payload requires a genuine leaf external owner");
      return;
    default:throw DataError("E_CELL_VALUE","task capabilities cannot enter a managed reference graph");
    }
  }
  std::vector<nexrt::ValueOwner<Data>> pending(const Value &root)const {
    std::vector<nexrt::ValueOwner<Data>> result;
    if(root.tag!=Value::Object)return result;
    struct Frame {nexrt::ValueOwner<Data> value;size_t next=0;};
    std::vector<Frame> stack;std::unordered_map<const Data*,bool> visited;size_t edges=0;
    auto enter=[&](const nexrt::ValueOwner<Data> &value){
      payloadKind(value);if(index.contains(value.get()))return;
      auto [found,inserted]=visited.emplace(value.get(),false);
      if(!inserted){if(!found->second)throw DataError("E_CELL_GRAPH","immutable payload has a cycle outside managed cells");return;}
      if(visited.size()>limits.maximumNodes)throw DataError("E_CELL_LIMIT","managed payload node limit exceeded");
      stack.push_back({value,0});
    };
    enter(root.object);
    while(!stack.empty()){
      auto &frame=stack.back();
      if(frame.next<frame.value->values.size()){
        if(edges++>=limits.maximumEdges)throw DataError("E_CELL_LIMIT","managed payload edge limit exceeded");
        const auto &child=frame.value->values[frame.next++];
        if(child.tag==Value::Object)enter(child.object);
      }else{
        visited.at(frame.value.get())=true;result.push_back(std::move(frame.value));stack.pop_back();
      }
    }
    return result;
  }
  void append(const nexrt::ValueOwner<Data> &value){
    auto [where,inserted]=index.emplace(value.get(),nodes.size());
    if(!inserted)throw DataError("E_CELL_GRAPH","managed node registered twice");
    try{nodes.push_back(value);}catch(...){index.erase(where);throw;}
    edges+=value->values.size();
  }
  void rollback(size_t begin)noexcept {
    while(nodes.size()>begin){edges-=nodes.back()->values.size();index.erase(nodes.back().get());nodes.pop_back();}
  }
  CellCollection collect(){
    const auto count=nodes.size();CellCollection report;report.beforeCells=cells;
    std::vector<size_t> incoming(count,0),ready;std::vector<unsigned char> marked(count,0);ready.reserve(count);
    size_t observedEdges=0;
    for(const auto &node:nodes){
      if(node->values.size()>limits.maximumEdges-observedEdges)throw DataError("E_CELL_GRAPH","managed payload was modified outside its heap");
      observedEdges+=node->values.size();
      for(const auto &value:node->values)if(value.tag==Value::Object){
        auto found=index.find(value.object.get());
        if(found==index.end())throw DataError("E_CELL_GRAPH","managed payload was modified outside its heap");
        ++incoming[found->second];
      }
    }
    if(observedEdges!=edges)throw DataError("E_CELL_GRAPH","managed payload was modified outside its heap");
    // Exactly one owner per node belongs to this registry. Other owners not
    // explained by managed graph edges are actual source/host value roots.
    for(size_t i=0;i<count;++i)if(uint64_t(nodes[i].use_count())>incoming[i]+1){marked[i]=1;ready.push_back(i);}
    while(!ready.empty()){
      auto current=ready.back();ready.pop_back();
      for(const auto &value:nodes[current]->values)if(value.tag==Value::Object){
        auto child=index.at(value.object.get());if(!marked[child]){marked[child]=1;ready.push_back(child);}
      }
    }
    for(size_t i=0;i<count;++i)if(!marked[i]&&nodes[i]->kind==Data::Cell){edges-=nodes[i]->values.size();nodes[i]->values.clear();}
    for(size_t i=count;i>0;){--i;if(!marked[i]){
      if(nodes[i]->kind==Data::Cell){--cells;++report.reclaimedCells;}
      edges-=nodes[i]->values.size();index.erase(nodes[i].get());nodes[i].reset();++report.reclaimedNodes;
    }}
    size_t output=0;
    for(size_t i=0;i<count;++i)if(nodes[i]){
      if(output!=i)nodes[output]=std::move(nodes[i]);
      index.at(nodes[output].get())=output;++output;
    }
    nodes.resize(output);++collections;
    const auto doubled=nodes.size()>limits.maximumNodes/2?limits.maximumNodes:nodes.size()*2;
    nextCollection=std::min(limits.maximumNodes,std::max(size_t(256),doubled));
    report.afterCells=cells;return report;
  }
  std::vector<nexrt::ValueOwner<Data>> prepare(const Value &value,size_t extra){
    if(nodes.size()>=nextCollection){collect();available();}
    auto additions=pending(value);
    auto fits=[&]{
      if(extra>limits.maximumNodes||additions.size()>limits.maximumNodes-extra||nodes.size()>limits.maximumNodes-extra-additions.size())return false;
      if(extra>limits.maximumEdges||edges>limits.maximumEdges-extra)return false;
      auto remaining=limits.maximumEdges-extra-edges;
      for(const auto &node:additions){if(node->values.size()>remaining)return false;remaining-=node->values.size();}
      return true;
    };
    if(!fits()){
      collect();available();additions=pending(value);
      if(!fits())throw DataError("E_CELL_LIMIT","managed heap node or edge limit exceeded");
    }
    return additions;
  }
};

CellHeap::CellHeap(CellHeapLimits limits):state(std::make_shared<CellHeapState>(limits)){}
CellHeap::~CellHeap(){close();}
Value CellHeap::create(Value initial){
  // Resource destruction can synchronously end/delete the owning context.
  // Pin state and never read this after admitting cleanup callbacks.
  auto owner=state;std::lock_guard lock(owner->mutex);CellHeapState::Operation operation(*owner);
  if(owner->cells>=owner->limits.maximumCells){owner->collect();owner->available();}
  if(owner->cells>=owner->limits.maximumCells)throw DataError("E_CELL_LIMIT","managed cell limit exceeded");
  if(owner->nextIdentity>uint64_t(std::numeric_limits<int64_t>::max()))throw DataError("E_CELL_LIMIT","managed cell identities exhausted");
  auto additions=owner->prepare(initial,1);const auto begin=owner->nodes.size();
  try{
    for(const auto &node:additions)owner->append(node);
    auto created=nexrt::makeValueOwner<CellData>(owner,int64_t(owner->nextIdentity),std::move(initial));owner->append(created);
    ++owner->cells;++owner->nextIdentity;return Value(std::move(created));
  }catch(...){owner->rollback(begin);throw;}
}
Value CellHeap::read(const Value &value)const{
  auto owner=state;std::lock_guard lock(owner->mutex);CellHeapState::Operation operation(*owner);return owner->cell(value).values[0];
}
void CellHeap::write(const Value &value,Value next){
  auto owner=state;std::lock_guard lock(owner->mutex);CellHeapState::Operation operation(*owner);auto receiver=value;auto &target=owner->cell(receiver);
  auto additions=owner->prepare(next,0);const auto begin=owner->nodes.size();
  try{for(const auto &node:additions)owner->append(node);}catch(...){owner->rollback(begin);throw;}
  target.values[0]=std::move(next);
}
CellCollection CellHeap::collect(){
  auto owner=state;std::lock_guard lock(owner->mutex);CellHeapState::Operation operation(*owner);
  auto result=owner->collect();owner->available();return result;
}
CellHeapStats CellHeap::stats()const{
  auto owner=state;std::lock_guard lock(owner->mutex);
  if(owner->busy)throw DataError("E_CELL_REENTRY","managed heap statistics are unavailable during cleanup or collection");
  return {owner->cells,owner->nodes.size(),owner->edges,owner->collections};
}
void CellHeap::close()noexcept{
  auto owner=state;std::lock_guard lock(owner->mutex);if(owner->closed)return;owner->closed=true;
  if(!owner->busy)owner->retire();
}
}
