#include "nex_resource_region.h"
#include "nex_resource.h"
#include <mutex>
#include <utility>
#include <vector>
#include <unordered_set>

namespace nexrt {
namespace resource_region_detail {
constexpr size_t none=size_t(-1);
struct Forest {std::mutex mutex;};
struct Node {
  size_t parent=0,depth=0,taskDepth=0,firstChild=none,nextSibling=none,subtreeSlots=0;
  bool active=true;
};
struct Owner {
  const std::shared_ptr<Forest> forest;
  std::shared_ptr<Graph> graph;
  size_t node,slot;
  bool published=false;
  ResourceRevocation revocation;
  Owner(std::shared_ptr<Forest> forest,std::shared_ptr<Graph> graph,size_t node,size_t slot)
      :forest(std::move(forest)),graph(std::move(graph)),node(node),slot(slot){}
};
struct Slot {
  std::weak_ptr<Owner> owner;size_t node=0;bool occupied=false,attached=false;
  ResourceSettlement settlement;ResourceRevocation revocation;
};
struct Graph {
  const ResourceRegionFamily family;
  const ResourceRegionLimits limits;
  const std::shared_ptr<Forest> forest;
  const std::shared_ptr<Graph> parent;
  const size_t parentNode;
  std::vector<Node> nodes;
  std::vector<Slot> owners;
  std::vector<std::weak_ptr<Graph>> groups;
  size_t scopeNodes=1,taskNodes=0;
  Graph(ResourceRegionFamily family,ResourceRegionLimits limits,std::shared_ptr<Forest> forest=std::make_shared<Forest>(),
        std::shared_ptr<Graph> parent={},size_t parentNode=0)
      :family(family),limits(limits),forest(std::move(forest)),parent(std::move(parent)),parentNode(parentNode),owners(limits.owners){
    nodes.reserve(limits.regions+limits.tasks);nodes.push_back({});
    if(family==ResourceRegionFamily::Request)groups.resize(limits.groups);
  }
  bool live(size_t node)const noexcept{
    return node<nodes.size()&&nodes[node].active&&(!parent||parent->live(parentNode));
  }
  void check(size_t node)const{if(!live(node))throw DataError("E_RESOURCE_SCOPE","logical resource region or request has ended");}
  bool within(size_t ancestor,size_t node)const noexcept{
    if(node>=nodes.size()||ancestor>=nodes.size())return false;
    for(;;){if(node==ancestor)return true;if(!node)return false;node=nodes[node].parent;}
  }
  void count(size_t node,bool add)noexcept{
    for(;;){if(add)++nodes[node].subtreeSlots;else{if(!nodes[node].subtreeSlots)std::terminate();--nodes[node].subtreeSlots;}
      if(!node)return;node=nodes[node].parent;}
  }
  void clearSlot(size_t index)noexcept{
    if(owners[index].occupied)count(owners[index].node,false);owners[index]={};
  }
  size_t freeSlot(){
    for(size_t i=0;i<owners.size();++i){const auto &slot=owners[i];
      if(!slot.occupied||(slot.owner.expired()&&(!slot.attached||slot.settlement.ready()))){clearSlot(i);return i;}
    }
    throw DataError("E_RESOURCE_REGION_LIMIT","logical resource owner capacity exhausted");
  }
  bool settled(size_t root)const noexcept{
    if(!nodes[root].subtreeSlots)return true;
    for(const auto &slot:owners)if(slot.occupied&&within(root,slot.node)){
      if(!slot.attached&&!slot.owner.expired())return false;
      if(slot.attached&&!slot.settlement.ready())return false;
    }
    return true;
  }
  void deactivate(size_t root)noexcept{
    size_t current=root;
    for(;;){
      auto &entry=nodes[current];const bool descend=entry.active;entry.active=false;
      if(descend&&entry.firstChild!=none){current=entry.firstChild;continue;}
      while(current!=root&&nodes[current].nextSibling==none)current=nodes[current].parent;
      if(current==root)return;current=nodes[current].nextSibling;
    }
  }
  size_t child(size_t parentNode,bool task){
    check(parentNode);const auto &p=nodes[parentNode];
    if((task&&(taskNodes>=limits.tasks||p.taskDepth>=256))||
       (!task&&(scopeNodes>=limits.regions||p.depth>=limits.depth)))
      throw DataError("E_RESOURCE_REGION_LIMIT","logical resource scope/task count or depth exhausted");
    Node value;value.parent=parentNode;value.depth=p.depth+(task?0:1);value.taskDepth=p.taskDepth+(task?1:0);value.nextSibling=p.firstChild;
    const auto index=nodes.size();nodes.push_back(value);nodes[parentNode].firstChild=index;
    if(task)++taskNodes;else ++scopeNodes;return index;
  }
};
bool ancestor(const std::shared_ptr<Graph> &outer,size_t outerNode,const std::shared_ptr<Graph> &inner,size_t innerNode)noexcept{
  if(outer==inner)return outer->within(outerNode,innerNode);
  return inner->parent==outer&&outer->within(outerNode,inner->parentNode);
}
void limitsChecked(ResourceRegionFamily family,ResourceRegionLimits limits){
  if(!limits.regions||limits.regions>1025||!limits.depth||limits.depth>256||!limits.owners||limits.owners>4096||limits.tasks>65536||limits.groups>1024)
    throw DataError("E_RESOURCE_REGION_LIMIT","logical resource bounds exceed1025 scopes,256 depth,4096 owners,65536 tasks or1024 groups");
  if(family!=ResourceRegionFamily::Native&&family!=ResourceRegionFamily::Reference&&family!=ResourceRegionFamily::Request)
    throw DataError("E_RESOURCE_SCOPE","invalid resource scheduler family");
}
}
ResourceRevocation::ResourceRevocation(std::weak_ptr<resource_detail::ControlBase> control,ResourceSettlement settlement):control(std::move(control)),settlement(std::move(settlement)){}
bool ResourceRevocation::close()const noexcept{auto retained=control.lock();return retained&&retained->close();}
bool ResourceRevocation::expired()const noexcept{return control.expired();}
ResourceRegionOwner::ResourceRegionOwner(std::shared_ptr<resource_region_detail::Owner> owner):owner(std::move(owner)){}
void ResourceRegionOwner::attach(ResourceSettlement settlement)const{
  if(!owner)throw DataError("E_RESOURCE_SCOPE","logical resource owner is unavailable");
  std::lock_guard lock(owner->forest->mutex);auto &g=*owner->graph;auto &slot=g.owners[owner->slot];
  if(slot.attached)throw DataError("E_RESOURCE_SCOPE","logical creation fence is already attached");
  slot.settlement=std::move(settlement);slot.attached=true;g.check(owner->node);
}
void ResourceRegionOwner::checkCreation()const{
  if(!owner)throw DataError("E_RESOURCE_SCOPE","logical resource owner is unavailable");
  std::lock_guard lock(owner->forest->mutex);owner->graph->check(owner->node);
}
bool ResourceRegionOwner::active()const noexcept{
  if(!owner)return false;std::lock_guard lock(owner->forest->mutex);return owner->graph->live(owner->node);
}
void ResourceRegionOwner::publish(ResourceRevocation revocation)const{
  if(!owner||revocation.expired())throw DataError("E_RESOURCE_SCOPE","logical resource publication is unavailable");
  std::lock_guard lock(owner->forest->mutex);auto &g=*owner->graph;
  if(owner->published)throw DataError("E_RESOURCE_SCOPE","logical resource owner is already published");
  if(!g.owners[owner->slot].attached)throw DataError("E_RESOURCE_SCOPE","logical resource has no creation fence");
  g.owners[owner->slot].revocation=revocation;owner->revocation=std::move(revocation);g.check(owner->node);owner->published=true;
}
void ResourceRegionOwner::check(const ResourceRegionAuthority &access)const{
  if(!owner||!access.graph||access.graph->forest!=owner->forest)throw DataError("E_RESOURCE_SCOPE","resource authority belongs to another request or group");
  std::lock_guard lock(owner->forest->mutex);auto &g=*owner->graph;g.check(owner->node);access.graph->check(access.node);
  if(!owner->published||!resource_region_detail::ancestor(owner->graph,owner->node,access.graph,access.node))
    throw DataError("E_RESOURCE_SCOPE","resource is outside the current logical ancestry");
}
void ResourceRegionOwner::checkPromotion(const ResourceRegionAuthority &actor,const ResourceRegionAuthority &target)const{
  if(!owner||!actor.graph||!target.graph||actor.graph->forest!=owner->forest||target.graph->forest!=owner->forest)
    throw DataError("E_RESOURCE_SCOPE","resource transfer belongs to another request or group");
  std::lock_guard lock(owner->forest->mutex);auto previous=owner->graph;
  previous->check(owner->node);actor.graph->check(actor.node);target.graph->check(target.node);
  if(!owner->published||!resource_region_detail::ancestor(previous,owner->node,actor.graph,actor.node)||
     !resource_region_detail::ancestor(target.graph,target.node,previous,owner->node))
    throw DataError("E_RESOURCE_SCOPE","resource transfer requires an admitted borrower and an ancestor target");
}
void ResourceRegionOwner::promote(const ResourceRegionAuthority &actor,const ResourceRegionAuthority &target)const{
  if(!owner||!actor.graph||!target.graph||actor.graph->forest!=owner->forest||target.graph->forest!=owner->forest)
    throw DataError("E_RESOURCE_SCOPE","resource transfer belongs to another request or group");
  std::lock_guard lock(owner->forest->mutex);auto previous=owner->graph;
  previous->check(owner->node);actor.graph->check(actor.node);target.graph->check(target.node);
  if(!owner->published||!resource_region_detail::ancestor(previous,owner->node,actor.graph,actor.node)||
     !resource_region_detail::ancestor(target.graph,target.node,previous,owner->node))
    throw DataError("E_RESOURCE_SCOPE","resource transfer requires an admitted borrower and an ancestor target");
  if(previous==target.graph){
    previous->count(owner->node,false);owner->node=target.node;previous->owners[owner->slot].node=target.node;previous->count(owner->node,true);return;
  }
  const auto next=target.graph->freeSlot();auto &destination=target.graph->owners[next];destination=previous->owners[owner->slot];destination.node=target.node;
  target.graph->count(target.node,true);previous->clearSlot(owner->slot);owner->graph=target.graph;owner->node=target.node;owner->slot=next;
}
void ResourceRegionOwner::transfer(std::span<const ResourceRegionOwner> values,const ResourceRegionAuthority &actor,const ResourceRegionAuthority &target,bool commit){
  if(values.empty())return;
  if(values.size()>4096)throw DataError("E_RESOURCE_REGION_LIMIT","resource transfer batch exceeds4096 owners");
  using namespace resource_region_detail;
  std::vector<std::shared_ptr<Owner>> owners;owners.reserve(values.size());std::unordered_set<const Owner*> unique;
  for(const auto &value:values){
    if(!value.owner)throw DataError("E_RESOURCE_SCOPE","resource transfer requires a genuine logical owner");
    if(unique.insert(value.owner.get()).second)owners.push_back(value.owner);
  }
  if(!actor.graph||!target.graph||actor.graph->forest!=target.graph->forest)
    throw DataError("E_RESOURCE_SCOPE","resource transfer belongs to another request or group");
  struct Move {std::shared_ptr<Owner> owner;std::shared_ptr<Graph> previous;size_t destination;};
  std::vector<Move> moves;moves.reserve(owners.size());
  std::lock_guard lock(actor.graph->forest->mutex);actor.graph->check(actor.node);target.graph->check(target.node);
  size_t cursor=0;
  for(const auto &owner:owners){
    if(owner->forest!=actor.graph->forest||!owner->published)
      throw DataError("E_RESOURCE_SCOPE","resource transfer requires a published owner in this request");
    auto previous=owner->graph;previous->check(owner->node);
    if(!ancestor(previous,owner->node,actor.graph,actor.node))
      throw DataError("E_RESOURCE_SCOPE","resource transfer requires an admitted borrower");
    if(ancestor(previous,owner->node,target.graph,target.node))continue;
    if(!ancestor(target.graph,target.node,previous,owner->node))
      throw DataError("E_RESOURCE_SCOPE","resource transfer target must be an ancestor owner");
    if(!commit)continue;
    size_t destination=owner->slot;
    if(previous!=target.graph){
      for(;cursor<target.graph->owners.size();++cursor){const auto &slot=target.graph->owners[cursor];
        if(!slot.occupied||(slot.owner.expired()&&(!slot.attached||slot.settlement.ready())))break;
      }
      if(cursor==target.graph->owners.size())throw DataError("E_RESOURCE_REGION_LIMIT","resource transfer destination capacity exhausted");
      destination=cursor++;
    }
    moves.push_back({owner,std::move(previous),destination});
  }
  if(!commit)return;
  // No allocation, callbacks or failing admission beyond this point. Preserve
  // all physical objects, aliases, grants and their actual settlement fences.
  for(auto &move:moves){auto &owner=*move.owner;
    if(move.previous==target.graph){
      move.previous->count(owner.node,false);owner.node=target.node;
      move.previous->owners[owner.slot].node=target.node;move.previous->count(owner.node,true);
    }else{
      target.graph->clearSlot(move.destination);
      auto &slot=target.graph->owners[move.destination];slot=move.previous->owners[owner.slot];slot.node=target.node;
      target.graph->count(target.node,true);move.previous->clearSlot(owner.slot);
      owner.graph=target.graph;owner.node=target.node;owner.slot=move.destination;
    }
  }
}
ResourceRegionAuthority::ResourceRegionAuthority(std::shared_ptr<resource_region_detail::Graph> graph,size_t node):graph(std::move(graph)),node(node){}
void ResourceRegionAuthority::check()const{
  if(!graph)throw DataError("E_RESOURCE_SCOPE","logical resource authority is unavailable");
  std::lock_guard lock(graph->forest->mutex);graph->check(node);
}
ResourceRegionOwner ResourceRegionAuthority::reserve()const{
  if(!graph)throw DataError("E_RESOURCE_SCOPE","logical resource authority is unavailable");
  std::lock_guard lock(graph->forest->mutex);graph->check(node);const auto index=graph->freeSlot();
  auto owner=std::make_shared<resource_region_detail::Owner>(graph->forest,graph,node,index);auto &slot=graph->owners[index];
  slot.node=node;slot.occupied=true;slot.owner=owner;graph->count(node,true);return ResourceRegionOwner(std::move(owner));
}
bool ResourceRegionAuthority::contains(const ResourceRegionAuthority &other)const{
  if(!graph||!other.graph||graph->forest!=other.graph->forest)return false;
  std::lock_guard lock(graph->forest->mutex);graph->check(node);other.graph->check(other.node);
  return resource_region_detail::ancestor(graph,node,other.graph,other.node);
}
size_t ResourceRegionAuthority::depth()const{if(!graph)check();std::lock_guard lock(graph->forest->mutex);graph->check(node);return graph->nodes[node].depth;}
ResourceRegionFamily ResourceRegionAuthority::family()const{check();return graph->family;}
ResourceRegion::ResourceRegion(ResourceRegionFamily family,ResourceRegionLimits limits){
  resource_region_detail::limitsChecked(family,limits);graph=std::make_shared<resource_region_detail::Graph>(family,limits);
}
ResourceRegion ResourceRegion::inRequest(ResourceRegionFamily family,const ResourceRegionAuthority &parent,ResourceRegionLimits limits){
  resource_region_detail::limitsChecked(family,limits);
  if(!parent.graph||parent.graph->family!=ResourceRegionFamily::Request||family==ResourceRegionFamily::Request)
    throw DataError("E_RESOURCE_SCOPE","group resource regions require a genuine request parent");
  auto next=std::make_shared<resource_region_detail::Graph>(family,limits,parent.graph->forest,parent.graph,parent.node);
  std::lock_guard lock(parent.graph->forest->mutex);parent.graph->check(parent.node);
  for(auto &slot:parent.graph->groups){auto previous=slot.lock();
    if(!previous||(!previous->nodes[0].active&&previous->settled(0))){slot=next;return ResourceRegion(std::move(next),0);}
  }
  throw DataError("E_RESOURCE_REGION_LIMIT","request resource group capacity exhausted");
}
ResourceRegion::ResourceRegion(std::shared_ptr<resource_region_detail::Graph> graph,size_t node):graph(std::move(graph)),node(node){}
ResourceRegion::ResourceRegion(ResourceRegion &&other)noexcept:graph(std::move(other.graph)),node(other.node),responsible(other.responsible.exchange(false)){}
ResourceRegion &ResourceRegion::operator=(ResourceRegion &&other)noexcept{
  if(this!=&other){close();graph=std::move(other.graph);node=other.node;responsible=other.responsible.exchange(false);}return *this;
}
ResourceRegion::~ResourceRegion(){close();}
ResourceRegion ResourceRegion::child()const{
  if(!graph||!responsible.load())throw DataError("E_RESOURCE_SCOPE","logical resource region has ended");
  std::lock_guard lock(graph->forest->mutex);return ResourceRegion(graph,graph->child(node,false));
}
ResourceRegion ResourceRegion::taskChild()const{
  if(!graph||!responsible.load())throw DataError("E_RESOURCE_SCOPE","logical resource region has ended");
  std::lock_guard lock(graph->forest->mutex);return ResourceRegion(graph,graph->child(node,true));
}
ResourceRegionAuthority ResourceRegion::authority()const{
  if(!graph||!responsible.load())throw DataError("E_RESOURCE_SCOPE","logical resource region has ended");
  std::lock_guard lock(graph->forest->mutex);graph->check(node);return ResourceRegionAuthority(graph,node);
}
ResourceRegionRetirement ResourceRegion::beginClose()noexcept{
  if(!graph||!responsible.exchange(false))return {};
  {std::lock_guard lock(graph->forest->mutex);graph->deactivate(node);
    for(auto &link:graph->groups)if(auto child=link.lock())if(graph->within(node,child->parentNode))child->deactivate(0);
  }
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
  auto closeGraph=[](const auto &g,size_t root){
    {std::lock_guard lock(g->forest->mutex);if(!g->nodes[root].subtreeSlots)return;}
    for(size_t i=0;i<g->owners.size();++i){std::shared_ptr<resource_region_detail::Owner> retained;ResourceRevocation close;
      {std::lock_guard lock(g->forest->mutex);const auto &slot=g->owners[i];
        if(slot.occupied&&g->within(root,slot.node)){retained=slot.owner.lock();close=slot.revocation;}}
      close.close();
    }
  };
  if(!graph)return;closeGraph(graph,node);
  for(size_t i=0;i<graph->groups.size();++i){std::shared_ptr<resource_region_detail::Graph> child;
    {std::lock_guard lock(graph->forest->mutex);child=graph->groups[i].lock();if(child&&!graph->within(node,child->parentNode))child.reset();}
    if(child)closeGraph(child,0);
  }
}
bool ResourceRegionRetirement::ready()const noexcept{
  if(!graph)return true;std::lock_guard lock(graph->forest->mutex);if(!graph->settled(node))return false;
  for(const auto &link:graph->groups)if(auto child=link.lock())if(graph->within(node,child->parentNode)&&!child->settled(0))return false;
  return true;
}
}
