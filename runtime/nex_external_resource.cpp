#include "nex_external_resource.h"
#include "nex_value.h"
#include <unordered_set>

namespace nexrt {
namespace external_detail {
struct ByteState {
  const uint64_t maximum;
  std::atomic<uint64_t> used{0};
  std::mutex mutex;
  explicit ByteState(uint64_t maximum):maximum(maximum){}
};
struct ClassState {
  const std::string name,hash;
  ClassState(std::string name,std::string hash):name(std::move(name)),hash(std::move(hash)){}
};
struct Charge {
  const std::vector<std::shared_ptr<ByteState>> states;
  const uint64_t bytes;
  bool reserved=false;
  Charge(std::vector<std::shared_ptr<ByteState>> states,uint64_t bytes):states(std::move(states)),bytes(bytes){}
  ~Charge(){if(reserved)for(const auto &s:states)s->used.fetch_sub(bytes);}
  void reserve(){
    std::vector<std::unique_lock<std::mutex>> locks;locks.reserve(states.size());
    for(const auto &s:states)locks.emplace_back(s->mutex);
    for(const auto &s:states)if(bytes>s->maximum-s->used.load())throw DataError("E_RESOURCE_BYTES","external capacity quota exceeded");
    for(const auto &s:states)s->used.fetch_add(bytes);
    reserved=true;
  }
};
struct Dependencies {
  struct Entry {uint64_t identity;ResourceRegionOwner region;resource_detail::Bindings grants;};
  std::vector<Entry> entries;
  size_t depth=0;
  bool active()const noexcept{
    for(const auto &entry:entries){
      for(const auto &grant:entry.grants)if(!grant->active.load())return false;
      if(entry.region&&!entry.region.active())return false;
    }
    return true;
  }
  void check(const ResourceRegionAuthority &actor)const{
    for(const auto &entry:entries){
      {auto locks=resource_detail::lock(entry.grants);resource_detail::check(entry.grants);}
      if(actor)entry.region.check(actor);
      else if(entry.region)throw DataError("E_RESOURCE_SCOPE","scoped dependency requires explicit logical authority");
    }
  }
};
struct ParentCapture {
  std::vector<ResourceLease<State>> leases;
  std::shared_ptr<const Dependencies> metadata;
};
struct State {
  // Object destructor and code-pin cleanup finish before physical capacity is returned.
  const std::shared_ptr<Charge> charge;
  // Release dependent native data first, then parent payloads/code pins. Parent
  // leases retain their original physical tickets even after logical close.
  const std::vector<ResourceLease<State>> parents;
  ExternalResourceObject object;
  State(std::shared_ptr<Charge> charge,std::vector<ResourceLease<State>> parents,ExternalResourceObject object)
      :charge(std::move(charge)),parents(std::move(parents)),object(std::move(object)){}
};
struct BorrowState {
  ResourceLease<State> lease;
  const std::shared_ptr<const ClassState> type;
  const ResourceRegionOwner region;
  const ResourceRegionAuthority access;
  const std::shared_ptr<const Dependencies> dependencies;
  BorrowState(ResourceLease<State> lease,std::shared_ptr<const ClassState> type,ResourceRegionOwner region={},ResourceRegionAuthority access={},std::shared_ptr<const Dependencies> dependencies={})
    :lease(std::move(lease)),type(std::move(type)),region(std::move(region)),access(std::move(access)),dependencies(std::move(dependencies)){}
};
}
ResourceByteBudget::ResourceByteBudget(uint64_t maximum){
  if(!maximum)throw DataError("E_RESOURCE_BYTES","external capacity quota must be positive");
  state=std::make_shared<external_detail::ByteState>(maximum);
}
uint64_t ResourceByteBudget::used()const noexcept{return state?state->used.load():0;}
uint64_t ResourceByteBudget::limit()const noexcept{return state?state->maximum:0;}
ExternalResourceClass::ExternalResourceClass(std::string name,std::string hash){
  if(name.empty()||name.size()>128||hash.size()!=64)throw DataError("E_RESOURCE_TYPE","invalid external class metadata");
  bool start=true;
  for(size_t i=0;i<name.size();++i){
    auto c=static_cast<unsigned char>(name[i]);bool letter=(c>='a'&&c<='z')||(c>='A'&&c<='Z')||c=='_';
    if(c==':'&&!start&&i+2<name.size()&&name[i+1]==':'){++i;start=true;continue;}
    if(!letter&&(!(!start&&c>='0'&&c<='9')))throw DataError("E_RESOURCE_TYPE","external class name must be qualified ASCII identifiers");
    start=false;
  }
  for(unsigned char c:hash)if(!((c>='0'&&c<='9')||(c>='a'&&c<='f')))throw DataError("E_RESOURCE_TYPE","external class hash must be64 lowercase hexadecimal digits");
  state=std::make_shared<external_detail::ClassState>(std::move(name),std::move(hash));
}
ExternalResourceObject::ExternalResourceObject(void *pointer,Destroy destroy,std::shared_ptr<void> pin)noexcept
    :pointer(pointer),destroy(destroy),codePin(std::move(pin)){}
ExternalResourceObject::ExternalResourceObject(ExternalResourceObject &&other)noexcept
    :pointer(std::exchange(other.pointer,nullptr)),destroy(other.destroy),codePin(std::move(other.codePin)){}
ExternalResourceObject::~ExternalResourceObject(){if(pointer)destroy(pointer);}
ExternalResource::ExternalResource(ResourceOwner<external_detail::State> owner,std::shared_ptr<const external_detail::ClassState> type,uint64_t capacity)
    :owner(std::move(owner)),type(std::move(type)),capacity(capacity){}
bool ExternalResource::isOpen()const noexcept{return owner.isOpen()&&(!region||region.active())&&(!dependencies||dependencies->active());}
bool ExternalResource::close()const noexcept{return owner.close();}
size_t ExternalResource::dependencyCount()const noexcept{return dependencies?dependencies->entries.size():0;}
size_t ExternalResource::dependencyDepth()const noexcept{return dependencies?dependencies->depth:0;}
void ExternalResource::checkRegion(const ResourceRegionAuthority &actor)const{
  region.check(actor);if(dependencies)dependencies->check(actor);
}
void ExternalResource::promoteRegion(const ResourceRegionAuthority &actor,const ResourceRegionAuthority &target)const{
  region.checkPromotion(actor,target);transferRegions(std::span<const ExternalResource>(this,1),actor,target);
}
void ExternalResource::transferRegions(std::span<const ExternalResource> values,const ResourceRegionAuthority &actor,const ResourceRegionAuthority &target,bool commit){
  if(values.size()>4096)throw DataError("E_RESOURCE_REGION_LIMIT","resource transfer batch exceeds4096 owners");
  std::vector<ResourceRegionOwner> owners;owners.reserve(values.size());
  std::unordered_set<uint64_t> unique;
  auto append=[&](uint64_t identity,const ResourceRegionOwner &owner){
    if(!identity)throw DataError("E_RESOURCE_SCOPE","resource transfer requires a genuine physical identity");
    if(!unique.insert(identity).second)return;
    if(owners.size()==4096)throw DataError("E_RESOURCE_REGION_LIMIT","resource dependency transfer exceeds4096 owners");
    owners.push_back(owner);
  };
  for(const auto &value:values){
    append(value.identity(),value.region);
    if(value.dependencies){
      value.dependencies->check(actor);
      for(const auto &entry:value.dependencies->entries)append(entry.identity,entry.region);
    }
  }
  ResourceRegionOwner::transfer(owners,actor,target,commit);
}
const std::string &ExternalResource::typeName()const noexcept{static const std::string empty;return type?type->name:empty;}
const std::string &ExternalResource::typeHash()const noexcept{static const std::string empty;return type?type->hash:empty;}
ExternalResource ExternalResource::makeErased(const ResourceDomain &domain,const ExternalResourceClass &key,
    std::span<const ResourceByteBudget> budgets,uint64_t bytes,std::function<ExternalResourceObject(const ResourcePermit&)> factory,std::span<const ExternalResource> parents){
  auto access=domain.access();
  if(auto bind=resource_detail::requestBinder)if(auto *request=bind(domain))access=request->access();
  return makeInAccessErased(std::move(access),key,budgets,bytes,std::move(factory),{}, {},false,parents);
}
external_detail::ParentCapture ExternalResource::captureParents(std::span<const ExternalResource> parents,const ResourceRegionAuthority &actor){
  external_detail::ParentCapture result;if(parents.empty())return result;
  if(parents.size()>16)throw DataError("E_RESOURCE_DEPENDENCY_LIMIT","external resource accepts at most16 parents");
  auto metadata=std::make_shared<external_detail::Dependencies>();std::unordered_set<uint64_t> captured,unique;
  auto append=[&](external_detail::Dependencies::Entry entry){
    if(!unique.insert(entry.identity).second)return;
    if(metadata->entries.size()==4095)throw DataError("E_RESOURCE_DEPENDENCY_LIMIT","external dependency graph exceeds4096 objects");
    metadata->entries.push_back(std::move(entry));
  };
  for(const auto &parent:parents){
    if(!parent.identity())throw DataError("E_RESOURCE_CLOSED","external parent is unavailable");
    if(!captured.insert(parent.identity()).second)continue;
    if(actor)parent.checkRegion(actor);
    else if(parent.region)throw DataError("E_RESOURCE_SCOPE","scoped parent requires explicit logical authority");
    if(parent.dependencies)parent.dependencies->check(actor);
    result.leases.push_back(parent.owner.acquire());
    const size_t depth=parent.dependencyDepth()+1;
    if(depth>256)throw DataError("E_RESOURCE_DEPENDENCY_LIMIT","external dependency depth exceeds256");
    metadata->depth=std::max(metadata->depth,depth);
    append({parent.identity(),parent.region,parent.owner.control->bindings});
    if(parent.dependencies)for(const auto &entry:parent.dependencies->entries)append(entry);
  }
  metadata->check(actor);result.metadata=std::move(metadata);return result;
}
ExternalResource ExternalResource::makeInAccessErased(ResourceAccess access,const ExternalResourceClass &key,
    std::span<const ResourceByteBudget> budgets,uint64_t bytes,std::function<ExternalResourceObject(const ResourcePermit&)> factory,
    std::shared_ptr<ResourceExecutor> executor,ResourceSettlement settlement,bool localFactory,std::span<const ExternalResource> parents,ResourceRegionAuthority parentActor){
  if(budgets.empty()||budgets.size()>8)throw DataError("E_RESOURCE_BYTES","external resource needs1..8 capacity budgets");
  auto type=key.state;
  if(!type)throw DataError("E_RESOURCE_TYPE","external class is unavailable");
  std::vector<std::shared_ptr<external_detail::ByteState>> states;
  for(const auto &budget:budgets){if(!budget.state)throw DataError("E_RESOURCE_BYTES","external capacity budget is unavailable");states.push_back(budget.state);}
  std::sort(states.begin(),states.end(),[](const auto &a,const auto &b){return std::less<>{}(a.get(),b.get());});
  states.erase(std::unique(states.begin(),states.end()),states.end());
  auto captured=captureParents(parents,parentActor);
  auto create=[&](const ResourcePermit &permit){
    auto charge=std::make_shared<external_detail::Charge>(states,bytes);charge->reserve();permit.check();
    if(captured.metadata)captured.metadata->check(parentActor);
    auto object=factory(permit);
    if(!object.pointer)throw DataError("E_RESOURCE_CLOSED","external resource factory returned no object");
    if(captured.metadata)captured.metadata->check(parentActor);
    return std::make_unique<external_detail::State>(std::move(charge),captured.leases,std::move(object));
  };
  auto resource=executor?access.makeOnExecutor<external_detail::State>(executor,create,settlement,localFactory):access.make<external_detail::State>(create,settlement);
  auto result=ExternalResource(std::move(resource),std::move(type),bytes);result.dependencies=std::move(captured.metadata);return result;
}
ExternalResourceBorrow::ExternalResourceBorrow(std::shared_ptr<external_detail::BorrowState> impl):impl(std::move(impl)){}
ExternalResourceBorrow ExternalResource::borrowErased(const ExternalResourceClass &expected)const{
  if(region)throw DataError("E_RESOURCE_SCOPE","scoped external resource requires explicit logical authority");
  auto lease=owner.acquire();lease.check();
  if(!type||type!=expected.state)throw DataError("E_RESOURCE_TYPE","external class registration differs");
  if(dependencies)dependencies->check({});
  return ExternalResourceBorrow(std::make_shared<external_detail::BorrowState>(std::move(lease),type,ResourceRegionOwner{},ResourceRegionAuthority{},dependencies));
}
ExternalResourceBorrow ExternalResource::borrowInRegionErased(const ResourceRegionAuthority &access,const ExternalResourceClass &expected)const{
  if(!region)throw DataError("E_RESOURCE_SCOPE","external resource has no matching logical owner");
  region.check(access);auto lease=owner.acquire();lease.check();
  if(!type||type!=expected.state)throw DataError("E_RESOURCE_TYPE","external class registration differs");
  if(dependencies)dependencies->check(access);
  return ExternalResourceBorrow(std::make_shared<external_detail::BorrowState>(std::move(lease),type,region,access,dependencies));
}
void ExternalResourceBorrow::check()const{
  if(!impl)throw DataError("E_RESOURCE_CLOSED","external borrow has ended");
  if(impl->region)impl->region.check(impl->access);
  impl->lease.check();
  if(impl->dependencies)impl->dependencies->check(impl->access);
}
void *ExternalResourceBorrow::data(const ExternalResourceClass &expected)const{
  check();if(impl->type!=expected.state)throw DataError("E_RESOURCE_TYPE","external borrow class differs");
  return impl->lease.value().object.pointer;
}
std::shared_ptr<Data> externalValue(ExternalResource resource){
  if(!resource.identity())throw DataError("E_RUNTIME","external value requires a genuine resource identity");
  return std::shared_ptr<Data>(new ExternalData(std::move(resource)));
}
}
