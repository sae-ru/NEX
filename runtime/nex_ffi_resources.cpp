#include "nex_ffi_resources.h"
#include <map>

namespace nexrt::foreign_detail {
ForeignResourceObject::~ForeignResourceObject()noexcept{if(pointer)destroy(pointer);}
struct ResourceRegistry::Impl {
  mutable std::mutex mutex;
  mutable std::map<std::pair<std::string,std::string>,ExternalResourceType<ForeignResourceObject>> types;
  ResourceByteBudget imageBytes{uint64_t(1024)*1024*1024};
};
ResourceRegistry::ResourceRegistry():impl(std::make_shared<Impl>()){}
ExternalResourceType<ForeignResourceObject> ResourceRegistry::type(const std::string &name,const std::string &hash)const{
  std::lock_guard lock(impl->mutex);auto key=std::pair{name,hash};auto found=impl->types.find(key);
  if(found!=impl->types.end())return found->second;
  if(impl->types.size()>=4096)throw DataError("E_FFI_LIMIT","module resource class registry exceeds4096 entries");
  return impl->types.emplace(std::move(key),ExternalResourceType<ForeignResourceObject>(name,hash)).first->second;
}
ResourceByteBudget ResourceRegistry::budget()const{return impl->imageBytes;}
ResourceContext::ResourceContext(std::shared_ptr<ResourceRegistry> registry,ResourceAccess access,
    ResourceByteBudget hostBytes,std::shared_ptr<void> pin,std::function<bool(const void*)> owns)
    :registry(std::move(registry)),access(std::move(access)),budgets{std::move(hostBytes)},codePin(std::move(pin)),ownsCode(std::move(owns)){
  if(!this->registry||!codePin||!ownsCode)throw DataError("E_FFI_GRANT","resource context requires actual module ownership");
  budgets.push_back(this->registry->budget());
}
void ResourceContext::check()const{access.check();}
void ResourceContext::callbacks(nex_ffi_resource_factory_v1 factory,nex_ffi_resource_destroy_v1 destroy)const{
  check();if(!factory||!destroy||!ownsCode(reinterpret_cast<const void*>(factory))||!ownsCode(reinterpret_cast<const void*>(destroy)))
    throw DataError("E_FFI_TYPE","resource callbacks must belong to the current pinned module snapshot");
}
ExternalResource ResourceContext::create(const std::string &name,const std::string &hash,uint64_t bytes,
    nex_ffi_resource_destroy_v1 destroy,const std::function<void(void**,const ResourcePermit&)> &initialize)const{
  check();auto key=registry->type(name,hash);
  return ExternalResource::makeInAccess(access,key,budgets,bytes,codePin,[&](const ResourcePermit &permit){
    auto object=std::make_unique<ForeignResourceObject>(destroy);initialize(&object->pointer,permit);
    if(!object->pointer)throw DataError("E_RESOURCE_CLOSED","resource factory returned no native object");
    return object;
  });
}
ExternalResourceBorrow ResourceContext::borrow(const ExternalResource &value,const std::string &name,const std::string &hash)const{
  check();return value.borrow(registry->type(name,hash));
}
void *ResourceContext::pointer(const ExternalResourceBorrow &lease,const std::string &name,const std::string &hash)const{
  check();return lease.value(registry->type(name,hash)).pointer;
}
}
