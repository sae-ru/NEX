#pragma once
#include "nex_resource.h"
#include <span>
#include <string>

namespace nexrt {
namespace external_detail {struct ByteState;struct ClassState;struct State;struct BorrowState;struct Charge;}

// Host accounting for declared external capacity, not total process/vendor RAM.
class ResourceByteBudget {
  std::shared_ptr<external_detail::ByteState> state;
  friend class ExternalResource;
public:
  explicit ResourceByteBudget(uint64_t limit);
  uint64_t used()const noexcept;
  uint64_t limit()const noexcept;
};

class ExternalResourceClass {
  std::shared_ptr<const external_detail::ClassState> state;
  friend class ExternalResource;
  friend class ExternalResourceBorrow;
public:
  ExternalResourceClass(std::string name,std::string semanticHash);
};
template<class T> class ExternalResourceType {
  ExternalResourceClass key;
  friend class ExternalResource;
  friend class ExternalResourceBorrow;
public:
  ExternalResourceType(std::string name,std::string semanticHash):key(std::move(name),std::move(semanticHash)){}
};

// Destruction and its control blocks are implemented in the host runtime.
// Never allocate a payload/control block in a provider that its own pin unloads.
class ExternalResourceObject {
  using Destroy=void(*)(void*)noexcept;
  void *pointer=nullptr;
  Destroy destroy=nullptr;
  std::shared_ptr<void> codePin;
  friend class ExternalResource;
  friend class ExternalResourceBorrow;
  friend struct external_detail::State;
  ExternalResourceObject(void*,Destroy,std::shared_ptr<void>)noexcept;
public:
  ExternalResourceObject(ExternalResourceObject&&)noexcept;
  ExternalResourceObject(const ExternalResourceObject&)=delete;
  ExternalResourceObject &operator=(const ExternalResourceObject&)=delete;
  ~ExternalResourceObject();
};

class ExternalResourceBorrow {
  std::shared_ptr<external_detail::BorrowState> impl;
  friend class ExternalResource;
  explicit ExternalResourceBorrow(std::shared_ptr<external_detail::BorrowState>);
  void *data(const ExternalResourceClass&)const;
public:
  ExternalResourceBorrow()=default;
  void check()const;
  template<class T> T &value(const ExternalResourceType<T> &type)const{return *static_cast<T*>(data(type.key));}
};

class ExternalResource {
  ResourceOwner<external_detail::State> owner;
  std::shared_ptr<const external_detail::ClassState> type;
  uint64_t capacity=0;
  ExternalResource(ResourceOwner<external_detail::State>,std::shared_ptr<const external_detail::ClassState>,uint64_t);
  static ExternalResource makeErased(const ResourceDomain&,const ExternalResourceClass&,
      std::span<const ResourceByteBudget>,uint64_t,std::function<ExternalResourceObject(const ResourcePermit&)>);
  static ExternalResource makeInAccessErased(ResourceAccess,const ExternalResourceClass&,
      std::span<const ResourceByteBudget>,uint64_t,std::function<ExternalResourceObject(const ResourcePermit&)>,
      std::shared_ptr<ResourceExecutor> executor={});
public:
  ExternalResource()=default;
  uint64_t identity()const noexcept{return owner.identity();}
  bool isOpen()const noexcept;
  bool close()const noexcept;
  uint64_t capacityBytes()const noexcept{return capacity;}
  const std::string &typeName()const noexcept;
  const std::string &typeHash()const noexcept;
  template<class T> ExternalResourceBorrow borrow(const ExternalResourceType<T> &key)const{return borrowErased(key.key);}
  ExternalResourceBorrow borrowErased(const ExternalResourceClass&)const;
  template<class T,class Factory> static ExternalResource make(const ResourceDomain &domain,
      const ExternalResourceType<T> &key,std::span<const ResourceByteBudget> budgets,uint64_t bytes,
      std::shared_ptr<void> codePin,Factory factory){
    static_assert(std::is_nothrow_destructible_v<T>);
    if(!codePin)throw DataError("E_RESOURCE_MODULE","external resource requires an explicit code owner");
    auto snapshot=key.key;
    return makeErased(domain,snapshot,budgets,bytes,
      [pin=std::move(codePin),create=std::move(factory)](const ResourcePermit &permit)mutable{
        std::unique_ptr<T> object=create(permit);
        return ExternalResourceObject(object.release(),[](void *p)noexcept{delete static_cast<T*>(p);},pin);
      });
  }
  // Host-only prepared authority. The C table never accepts an access object.
  template<class T,class Factory> static ExternalResource makeInAccess(ResourceAccess access,
      const ExternalResourceType<T> &key,std::span<const ResourceByteBudget> budgets,uint64_t bytes,
      std::shared_ptr<void> codePin,Factory factory){
    static_assert(std::is_nothrow_destructible_v<T>);
    if(!codePin)throw DataError("E_RESOURCE_MODULE","external resource requires an explicit code owner");
    auto snapshot=key.key;
    return makeInAccessErased(std::move(access),snapshot,budgets,bytes,
      [pin=std::move(codePin),create=std::move(factory)](const ResourcePermit &permit)mutable{
        std::unique_ptr<T> object=create(permit);
        return ExternalResourceObject(object.release(),[](void *p)noexcept{delete static_cast<T*>(p);},pin);
      });
  }
  template<class T,class Factory> static ExternalResource makeOnExecutor(const ResourceDomain &domain,
      const ExternalResourceType<T> &key,std::span<const ResourceByteBudget> budgets,uint64_t bytes,
      std::shared_ptr<void> codePin,std::shared_ptr<ResourceExecutor> executor,Factory factory){
    static_assert(std::is_nothrow_destructible_v<T>);
    if(!codePin)throw DataError("E_RESOURCE_MODULE","external resource requires an explicit code owner");
    if(!executor)throw DataError("E_RESOURCE_EXECUTOR","external resource requires an explicit executor");
    auto access=domain.access();
    if(auto bind=resource_detail::requestBinder)if(auto *request=bind(domain))access=request->access();
    return makeInAccessErased(std::move(access),key.key,budgets,bytes,
      [pin=std::move(codePin),create=std::move(factory)](const ResourcePermit &permit)mutable{
        std::unique_ptr<T> object=create(permit);
        return ExternalResourceObject(object.release(),[](void *p)noexcept{delete static_cast<T*>(p);},pin);
      },std::move(executor));
  }
};
}
