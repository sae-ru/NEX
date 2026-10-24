#include "nex_external_resource.h"
#include "nex_value.h"

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
struct State {
  // Object destructor and code-pin cleanup finish before physical capacity is returned.
  const std::shared_ptr<Charge> charge;
  ExternalResourceObject object;
  State(std::shared_ptr<Charge> charge,ExternalResourceObject object):charge(std::move(charge)),object(std::move(object)){}
};
struct BorrowState {
  ResourceLease<State> lease;
  const std::shared_ptr<const ClassState> type;
  const ResourceRegionOwner region;
  const ResourceRegionAuthority access;
  BorrowState(ResourceLease<State> lease,std::shared_ptr<const ClassState> type,ResourceRegionOwner region={},ResourceRegionAuthority access={})
    :lease(std::move(lease)),type(std::move(type)),region(std::move(region)),access(std::move(access)){}
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
bool ExternalResource::isOpen()const noexcept{return owner.isOpen()&&(!region||region.active());}
bool ExternalResource::close()const noexcept{return owner.close();}
const std::string &ExternalResource::typeName()const noexcept{static const std::string empty;return type?type->name:empty;}
const std::string &ExternalResource::typeHash()const noexcept{static const std::string empty;return type?type->hash:empty;}
ExternalResource ExternalResource::makeErased(const ResourceDomain &domain,const ExternalResourceClass &key,
    std::span<const ResourceByteBudget> budgets,uint64_t bytes,std::function<ExternalResourceObject(const ResourcePermit&)> factory){
  auto access=domain.access();
  if(auto bind=resource_detail::requestBinder)if(auto *request=bind(domain))access=request->access();
  return makeInAccessErased(std::move(access),key,budgets,bytes,std::move(factory));
}
ExternalResource ExternalResource::makeInAccessErased(ResourceAccess access,const ExternalResourceClass &key,
    std::span<const ResourceByteBudget> budgets,uint64_t bytes,std::function<ExternalResourceObject(const ResourcePermit&)> factory,
    std::shared_ptr<ResourceExecutor> executor,ResourceSettlement settlement){
  if(budgets.empty()||budgets.size()>8)throw DataError("E_RESOURCE_BYTES","external resource needs1..8 capacity budgets");
  auto type=key.state;
  if(!type)throw DataError("E_RESOURCE_TYPE","external class is unavailable");
  std::vector<std::shared_ptr<external_detail::ByteState>> states;
  for(const auto &budget:budgets){if(!budget.state)throw DataError("E_RESOURCE_BYTES","external capacity budget is unavailable");states.push_back(budget.state);}
  std::sort(states.begin(),states.end(),[](const auto &a,const auto &b){return std::less<>{}(a.get(),b.get());});
  states.erase(std::unique(states.begin(),states.end()),states.end());
  auto create=[&](const ResourcePermit &permit){
    auto charge=std::make_shared<external_detail::Charge>(states,bytes);charge->reserve();permit.check();
    auto object=factory(permit);
    if(!object.pointer)throw DataError("E_RESOURCE_CLOSED","external resource factory returned no object");
    return std::make_unique<external_detail::State>(std::move(charge),std::move(object));
  };
  auto resource=executor?access.makeOnExecutor<external_detail::State>(executor,create,settlement):access.make<external_detail::State>(create,settlement);
  return ExternalResource(std::move(resource),std::move(type),bytes);
}
ExternalResourceBorrow::ExternalResourceBorrow(std::shared_ptr<external_detail::BorrowState> impl):impl(std::move(impl)){}
ExternalResourceBorrow ExternalResource::borrowErased(const ExternalResourceClass &expected)const{
  if(region)throw DataError("E_RESOURCE_SCOPE","scoped external resource requires explicit logical authority");
  auto lease=owner.acquire();lease.check();
  if(!type||type!=expected.state)throw DataError("E_RESOURCE_TYPE","external class registration differs");
  return ExternalResourceBorrow(std::make_shared<external_detail::BorrowState>(std::move(lease),type));
}
ExternalResourceBorrow ExternalResource::borrowInRegionErased(const ResourceRegionAuthority &access,const ExternalResourceClass &expected)const{
  if(!region)throw DataError("E_RESOURCE_SCOPE","external resource has no matching logical owner");
  region.check(access);auto lease=owner.acquire();lease.check();
  if(!type||type!=expected.state)throw DataError("E_RESOURCE_TYPE","external class registration differs");
  return ExternalResourceBorrow(std::make_shared<external_detail::BorrowState>(std::move(lease),type,region,access));
}
void ExternalResourceBorrow::check()const{
  if(!impl)throw DataError("E_RESOURCE_CLOSED","external borrow has ended");
  if(impl->region)impl->region.check(impl->access);
  impl->lease.check();
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
