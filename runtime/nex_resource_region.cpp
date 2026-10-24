#include "nex_resource_region.h"
#include "nex_resource.h"
#include <mutex>
#include <utility>
#include <vector>

namespace nexrt {
namespace resource_region_detail {
struct Node {size_t parent=0,depth=0;bool active=true;};
struct Owner {
  const std::shared_ptr<Graph> graph;
  size_t node;
  const size_t slot;
  bool published=false;
  ResourceRevocation revocation;
  Owner(std::shared_ptr<Graph> graph,size_t node,size_t slot):graph(std::move(graph)),node(node),slot(slot){}
};
struct Slot {std::weak_ptr<Owner> owner;size_t node=0;bool attached=false;ResourceSettlement settlement;ResourceRevocation revocation;};
struct Graph {
  const ResourceRegionFamily family;
  const ResourceRegionLimits limits;
  std::mutex mutex;
  std::vector<Node> nodes;
  std::vector<Slot> owners;
  Graph(ResourceRegionFamily family,ResourceRegionLimits limits):family(family),limits(limits),owners(limits.owners){nodes.reserve(limits.regions);nodes.push_back({});}
  void check(size_t node)const{
    if(node>=nodes.size()||!nodes[node].active)throw DataError("E_RESOURCE_SCOPE","logical resource region has ended");
  }
  bool within(size_t ancestor,size_t node)const noexcept{
    for(;;){if(node==ancestor)return true;if(!node)return false;node=nodes[node].parent;}
  }
};
}
ResourceRevocation::ResourceRevocation(std::weak_ptr<resource_detail::ControlBase> control,ResourceSettlement settlement):control(std::move(control)),settlement(std::move(settlement)){}
bool ResourceRevocation::close()const noexcept{auto retained=control.lock();return retained&&retained->close();}
bool ResourceRevocation::expired()const noexcept{return control.expired();}
ResourceRegionOwner::ResourceRegionOwner(std::shared_ptr<resource_region_detail::Owner> owner):owner(std::move(owner)){}
void ResourceRegionOwner::attach(ResourceSettlement settlement)const{
  if(!owner)throw DataError("E_RESOURCE_SCOPE","logical resource owner is unavailable");
  auto &g=*owner->graph;std::lock_guard lock(g.mutex);auto &slot=g.owners[owner->slot];
  if(slot.attached)throw DataError("E_RESOURCE_SCOPE","logical creation fence is already attached");
  slot.settlement=std::move(settlement);slot.attached=true;g.check(owner->node);
}
void ResourceRegionOwner::checkCreation()const{
  if(!owner)throw DataError("E_RESOURCE_SCOPE","logical resource owner is unavailable");
  auto &g=*owner->graph;std::lock_guard lock(g.mutex);g.check(owner->node);
}
bool ResourceRegionOwner::active()const noexcept{
  if(!owner)return false;auto &g=*owner->graph;std::lock_guard lock(g.mutex);return g.nodes[owner->node].active;
}
void ResourceRegionOwner::publish(ResourceRevocation revocation)const{
  if(!owner||revocation.expired())throw DataError("E_RESOURCE_SCOPE","logical resource publication is unavailable");
  auto &g=*owner->graph;std::lock_guard lock(g.mutex);
  if(owner->published)throw DataError("E_RESOURCE_SCOPE","logical resource owner is already published");
  if(!g.owners[owner->slot].attached)throw DataError("E_RESOURCE_SCOPE","logical resource has no creation fence");
  g.owners[owner->slot].revocation=revocation;owner->revocation=std::move(revocation);g.check(owner->node);owner->published=true;
}
void ResourceRegionOwner::check(const ResourceRegionAuthority &access)const{
  if(!owner||access.graph!=owner->graph)throw DataError("E_RESOURCE_SCOPE","resource authority belongs to another scheduler family or group");
  auto &g=*owner->graph;std::lock_guard lock(g.mutex);g.check(access.node);g.check(owner->node);
  if(!owner->published||!g.within(owner->node,access.node))throw DataError("E_RESOURCE_SCOPE","resource is outside the current logical ancestry");
}
void ResourceRegionOwner::promote(const ResourceRegionAuthority &actor,const ResourceRegionAuthority &target)const{
  if(!owner||actor.graph!=owner->graph||target.graph!=owner->graph)throw DataError("E_RESOURCE_SCOPE","resource transfer belongs to another scheduler family or group");
  auto &g=*owner->graph;std::lock_guard lock(g.mutex);g.check(actor.node);g.check(target.node);g.check(owner->node);
  if(!owner->published||!g.within(owner->node,actor.node)||!g.within(target.node,owner->node))throw DataError("E_RESOURCE_SCOPE","resource transfer requires an admitted borrower and an ancestor target");
  owner->node=target.node;g.owners[owner->slot].node=target.node;
}
ResourceRegionAuthority::ResourceRegionAuthority(std::shared_ptr<resource_region_detail::Graph> graph,size_t node):graph(std::move(graph)),node(node){}
void ResourceRegionAuthority::check()const{
  if(!graph)throw DataError("E_RESOURCE_SCOPE","logical resource authority is unavailable");
  std::lock_guard lock(graph->mutex);graph->check(node);
}
ResourceRegionOwner ResourceRegionAuthority::reserve()const{
  if(!graph)throw DataError("E_RESOURCE_SCOPE","logical resource authority is unavailable");
  std::lock_guard lock(graph->mutex);graph->check(node);
  for(size_t i=0;i<graph->owners.size();++i){auto &slot=graph->owners[i];if(slot.owner.expired()&&(!slot.attached||slot.settlement.ready())){
    auto owner=std::make_shared<resource_region_detail::Owner>(graph,node,i);slot={};slot.node=node;slot.owner=owner;return ResourceRegionOwner(std::move(owner));
  }
  }
  throw DataError("E_RESOURCE_REGION_LIMIT","logical resource owner capacity exhausted");
}
bool ResourceRegionAuthority::contains(const ResourceRegionAuthority &other)const{
  if(!graph||graph!=other.graph)return false;
  std::lock_guard lock(graph->mutex);graph->check(node);graph->check(other.node);return graph->within(node,other.node);
}
size_t ResourceRegionAuthority::depth()const{check();std::lock_guard lock(graph->mutex);return graph->nodes[node].depth;}
ResourceRegionFamily ResourceRegionAuthority::family()const{check();return graph->family;}
ResourceRegion::ResourceRegion(ResourceRegionFamily family,ResourceRegionLimits limits){
  if(!limits.regions||limits.regions>1025||!limits.depth||limits.depth>256||!limits.owners||limits.owners>4096)
    throw DataError("E_RESOURCE_REGION_LIMIT","logical resource bounds exceed1025 nodes,256 depth or4096 owners");
  if(family!=ResourceRegionFamily::Native&&family!=ResourceRegionFamily::Reference)throw DataError("E_RESOURCE_SCOPE","invalid resource scheduler family");
  graph=std::make_shared<resource_region_detail::Graph>(family,limits);
}
ResourceRegion::ResourceRegion(std::shared_ptr<resource_region_detail::Graph> graph,size_t node):graph(std::move(graph)),node(node){}
ResourceRegion::ResourceRegion(ResourceRegion &&other)noexcept:graph(std::move(other.graph)),node(other.node),responsible(other.responsible.exchange(false)){}
ResourceRegion &ResourceRegion::operator=(ResourceRegion &&other)noexcept{
  if(this!=&other){close();graph=std::move(other.graph);node=other.node;responsible=other.responsible.exchange(false);}return *this;
}
ResourceRegion::~ResourceRegion(){close();}
ResourceRegion ResourceRegion::child()const{
  if(!graph||!responsible.load())throw DataError("E_RESOURCE_SCOPE","logical resource region has ended");
  std::lock_guard lock(graph->mutex);graph->check(node);
  if(graph->nodes.size()>=graph->limits.regions||graph->nodes[node].depth>=graph->limits.depth)
    throw DataError("E_RESOURCE_REGION_LIMIT","logical resource scope count or depth exhausted");
  size_t child=graph->nodes.size();graph->nodes.push_back({node,graph->nodes[node].depth+1,true});return ResourceRegion(graph,child);
}
ResourceRegionAuthority ResourceRegion::authority()const{
  if(!graph||!responsible.load())throw DataError("E_RESOURCE_SCOPE","logical resource region has ended");
  std::lock_guard lock(graph->mutex);graph->check(node);return ResourceRegionAuthority(graph,node);
}
ResourceRegionRetirement ResourceRegion::beginClose()noexcept{
  if(!graph||!responsible.exchange(false))return {};
  {std::lock_guard lock(graph->mutex);for(size_t i=0;i<graph->nodes.size();++i)if(graph->within(node,i))graph->nodes[i].active=false;}
  return ResourceRegionRetirement(graph,node);
}
void ResourceRegion::close()noexcept{auto retirement=beginClose();retirement.requestClose();}
ResourceRegionRetirement::ResourceRegionRetirement(std::shared_ptr<resource_region_detail::Graph> graph,size_t node):graph(std::move(graph)),node(node){}
ResourceRegionRetirement::ResourceRegionRetirement(ResourceRegionRetirement &&other)noexcept:graph(std::move(other.graph)),node(other.node){}
ResourceRegionRetirement &ResourceRegionRetirement::operator=(ResourceRegionRetirement &&other)noexcept{
  if(this!=&other){requestClose();graph=std::move(other.graph);node=other.node;}return *this;
}
ResourceRegionRetirement::~ResourceRegionRetirement(){requestClose();}
void ResourceRegionRetirement::requestClose()noexcept{
  auto retained=graph;if(!retained)return;
  for(size_t i=0;i<retained->owners.size();++i){
    std::shared_ptr<resource_region_detail::Owner> owner;ResourceRevocation close;
    {std::lock_guard lock(retained->mutex);const auto &slot=retained->owners[i];owner=slot.owner.lock();
      if(retained->within(node,slot.node))close=slot.revocation;}
    // The retained owner and physical destructor are released without graph or
    // scheduler locks. A destructor may re-enter authority checks or host code.
    close.close();
  }
}
bool ResourceRegionRetirement::ready()const noexcept{
  if(!graph)return true;
  std::lock_guard lock(graph->mutex);
  for(const auto &slot:graph->owners)if(graph->within(node,slot.node)){
    if(!slot.attached&&!slot.owner.expired())return false;
    if(slot.attached&&!slot.settlement.ready())return false;
  }
  return true;
}
}
