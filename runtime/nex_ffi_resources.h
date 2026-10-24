#pragma once
#include "nex_ffi_host.h"
#include "nex_external_resource.h"

namespace nexrt::foreign_detail {
struct ForeignResourceObject {
  void *pointer=nullptr;
  nex_ffi_resource_destroy_v1 destroy;
  explicit ForeignResourceObject(nex_ffi_resource_destroy_v1 destroy):destroy(destroy){}
  ~ForeignResourceObject()noexcept;
};
class ResourceRegistry {
  struct Impl;std::shared_ptr<Impl> impl;
public:
  ResourceRegistry();
  ExternalResourceType<ForeignResourceObject> type(const std::string&,const std::string&)const;
  ResourceByteBudget budget()const;
};
class ResourceContext {
  std::shared_ptr<ResourceRegistry> registry;
  ResourceAccess access;
  std::vector<ResourceByteBudget> budgets;
  std::shared_ptr<void> codePin;
  std::function<bool(const void*)> ownsCode;
public:
  ResourceContext(std::shared_ptr<ResourceRegistry>,ResourceAccess,ResourceByteBudget,
      std::shared_ptr<void>,std::function<bool(const void*)>);
  void check()const;
  void callbacks(nex_ffi_resource_factory_v1,nex_ffi_resource_destroy_v1)const;
  ExternalResource create(const std::string&,const std::string&,uint64_t,nex_ffi_resource_destroy_v1,
      const std::function<void(void**,const ResourcePermit&)> &)const;
  ExternalResourceBorrow borrow(const ExternalResource&,const std::string&,const std::string&)const;
  void *pointer(const ExternalResourceBorrow&,const std::string&,const std::string&)const;
};
Value invokeForeignTypedResources(nex_ffi_callback_v1,std::span<const Value>,const ForeignSignature&,
    void*,std::function<void()>,ForeignCallLimits,std::shared_ptr<ResourceContext>);
}
