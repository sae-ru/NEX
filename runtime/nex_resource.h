#pragma once
#include "nex_error.h"
#include "nex_resource_executor.h"
#include <algorithm>
#include <atomic>
#include <cstdint>
#include <functional>
#include <limits>
#include <memory>
#include <mutex>
#include <type_traits>
#include <utility>
#include <vector>

namespace nexrt {
namespace resource_detail {
struct ControlBase {
  std::shared_ptr<std::atomic<bool>> closed=std::make_shared<std::atomic<bool>>(false);
  virtual bool close() noexcept = 0;
  virtual ~ControlBase() = default;
};
struct Registration {
  std::weak_ptr<ControlBase> resource;
  std::shared_ptr<std::atomic<bool>> closed;
};
struct DomainState {
  std::mutex mutex;
  std::atomic<bool> active{true};
  std::atomic<size_t> used{0};
  const size_t limit;
  std::vector<Registration> resources;
  explicit DomainState(size_t limit):limit(limit){}
};
using Bindings = std::vector<std::shared_ptr<DomainState>>;
inline auto lock(const Bindings &bindings) {
  std::vector<std::unique_lock<std::mutex>> locks;
  locks.reserve(bindings.size());
  for(const auto &state:bindings)locks.emplace_back(state->mutex);
  return locks;
}
inline void check(const Bindings &bindings) {
  if(bindings.empty())throw DataError("E_RESOURCE_SCOPE","resource domain is unavailable");
  for(const auto &state:bindings)
    if(!state->active.load())throw DataError("E_RESOURCE_SCOPE","resource domain has ended");
}
struct Ticket {
  Bindings bindings;
  bool reserved=false;
  explicit Ticket(Bindings bindings):bindings(std::move(bindings)){}
  ~Ticket(){if(reserved)for(const auto &state:bindings)state->used.fetch_sub(1);}
};
template<class T> struct Payload {
  // Destroy the external object before returning its physical quota slot.
  std::shared_ptr<Ticket> ticket;
  std::unique_ptr<T> value;
  Payload(std::shared_ptr<Ticket> ticket,std::unique_ptr<T> value)
      :ticket(std::move(ticket)),value(std::move(value)){}
};
template<class T> struct Control final:ControlBase {
  const uint64_t identity;
  const Bindings bindings;
  std::mutex mutex;
  std::shared_ptr<Payload<T>> payload;
  Control(uint64_t identity,Bindings bindings,std::shared_ptr<Payload<T>> payload)
      :identity(identity),bindings(std::move(bindings)),payload(std::move(payload)){}
  bool close() noexcept override {
    std::shared_ptr<Payload<T>> released;
    {
      std::lock_guard guard(mutex);
      if(closed->exchange(true))return false;
      released=std::move(payload);
    }
    // Destructors may re-enter the host. Never run them under our mutexes.
    return true;
  }
  ~Control() override {close();}
};
inline uint64_t nextIdentity() {
  static std::atomic<uint64_t> next{1};
  auto value=next.load();
  for(;;){
    if(value==std::numeric_limits<uint64_t>::max())
      throw DataError("E_LIMIT","resource identities exhausted");
    if(next.compare_exchange_weak(value,value+1))return value;
  }
}
}

template<class T> class ResourceOwner;
template<class T> class ResourceLease;
class ResourceDomain;
class ResourceAccess;

// A factory can check revocation between host operations without keeping a
// domain wrapper alive. No lock is held while the factory itself runs.
class ResourcePermit {
  friend class ResourceDomain;
  friend class ResourceAccess;
  resource_detail::Bindings bindings;
  explicit ResourcePermit(resource_detail::Bindings bindings):bindings(std::move(bindings)){}
public:
  void check() const {auto locks=resource_detail::lock(bindings);resource_detail::check(bindings);}
};

template<class T> class ResourceLease {
  friend class ResourceOwner<T>;
  std::shared_ptr<resource_detail::Control<T>> control;
  std::shared_ptr<resource_detail::Payload<T>> payload;
  ResourceLease(std::shared_ptr<resource_detail::Control<T>> control,
                std::shared_ptr<resource_detail::Payload<T>> payload)
      :control(std::move(control)),payload(std::move(payload)){}
public:
  ResourceLease()=default;
  void check() const {
    auto retained=control;
    if(!retained)throw DataError("E_RESOURCE_CLOSED","resource is closed");
    auto locks=resource_detail::lock(retained->bindings);
    resource_detail::check(retained->bindings);
    std::lock_guard guard(retained->mutex);
    if(retained->closed->load())throw DataError("E_RESOURCE_CLOSED","resource is closed");
  }
  const T &value() const {check();return *payload->value;}
};

// Copies alias one identity and one logical close state. Only trusted runtime
// code sees a typed payload, and only while a lease retains its physical owner.
template<class T> class ResourceOwner {
  friend class ResourceDomain;
  friend class ResourceAccess;
  std::shared_ptr<resource_detail::Control<T>> control;
  explicit ResourceOwner(std::shared_ptr<resource_detail::Control<T>> control):control(std::move(control)){}
public:
  ResourceOwner()=default;
  uint64_t identity() const noexcept {return control?control->identity:0;}
  bool isOpen() const noexcept {
    auto retained=control;if(!retained||retained->closed->load())return false;
    for(const auto &state:retained->bindings)if(!state->active.load())return false;
    return true;
  }
  bool close() const noexcept {auto retained=control;return retained&&retained->close();}
  ResourceLease<T> acquire() const {
    auto retained=control;
    if(!retained)throw DataError("E_RESOURCE_CLOSED","resource is closed");
    auto locks=resource_detail::lock(retained->bindings);
    resource_detail::check(retained->bindings);
    std::lock_guard guard(retained->mutex);
    if(retained->closed->load())throw DataError("E_RESOURCE_CLOSED","resource is closed");
    return ResourceLease<T>(retained,retained->payload);
  }
};

// A retained authority snapshot owns no revocation responsibility. It may
// outlive the unique domain wrapper, but every use still checks its activity.
class ResourceAccess {
  friend class ResourceDomain;
  resource_detail::Bindings bindings;
  std::shared_ptr<resource_detail::DomainState> own;
  ResourceAccess(resource_detail::Bindings bindings,std::shared_ptr<resource_detail::DomainState> own)
      :bindings(std::move(bindings)),own(std::move(own)){}
public:
  ResourceAccess()=default;
  const void *scopeKey()const noexcept{return own.get();}
  void check()const{auto retained=bindings;auto locks=resource_detail::lock(retained);resource_detail::check(retained);}
  // Join retained authorities without creating a temporary lexical revoker.
  // scopeKey remains the left creation-domain key; it is not a joined cache key.
  ResourceAccess combine(const ResourceAccess &other)const{
    auto retained=bindings;retained.insert(retained.end(),other.bindings.begin(),other.bindings.end());
    std::sort(retained.begin(),retained.end(),[](const auto &a,const auto &b){return std::less<>{}(a.get(),b.get());});
    retained.erase(std::unique(retained.begin(),retained.end()),retained.end());
    if(retained.size()>8)throw DataError("E_RESOURCE_LIMIT","joined resource access exceeds eight domains");
    auto locks=resource_detail::lock(retained);resource_detail::check(bindings);resource_detail::check(other.bindings);
    return ResourceAccess(std::move(retained),own);
  }
  template<class T,class Factory> ResourceOwner<T> make(Factory &&factory) const {
    static_assert(std::is_nothrow_destructible_v<T>);
    auto retained=bindings;
    auto create=std::forward<Factory>(factory);
    auto ticket=std::make_shared<resource_detail::Ticket>(retained);
    {
      auto locks=resource_detail::lock(retained);resource_detail::check(retained);
      for(const auto &state:retained)
        if(state->used.load()>=state->limit)throw DataError("E_RESOURCE_LIMIT","resource domain quota exceeded");
      for(const auto &state:retained)state->used.fetch_add(1);
      ticket->reserved=true;
    }
    auto identity=resource_detail::nextIdentity();
    auto value=create(ResourcePermit(retained));
    if(!value)throw DataError("E_RESOURCE_CLOSED","resource factory returned no value");
    auto payload=std::make_shared<resource_detail::Payload<T>>(std::move(ticket),std::move(value));
    auto control=std::make_shared<resource_detail::Control<T>>(identity,retained,std::move(payload));
    {
      auto locks=resource_detail::lock(retained);resource_detail::check(retained);
      for(const auto &state:retained){
        auto &resources=state->resources;
        // Never acquire the last strong control reference under domain locks:
        // its destructor could re-enter the domain. Status has no callbacks.
        std::erase_if(resources,[](const auto &entry){return entry.resource.expired()||entry.closed->load();});
        resources.push_back({control,control->closed});
      }
    }
    return ResourceOwner<T>(std::move(control));
  }
  template<class T,class Factory> ResourceOwner<T> makeOnExecutor(
      const std::shared_ptr<ResourceExecutor> &executor,Factory &&factory)const{
    static_assert(std::is_nothrow_destructible_v<T>);
    if(!executor)throw DataError("E_RESOURCE_EXECUTOR","resource executor is unavailable");
    auto retained=bindings;
    auto ticket=std::make_shared<resource_detail::Ticket>(retained);
    auto cleanup=std::make_shared<ResourceCleanupTicket>(executor->reserveCleanup());
    {
      auto locks=resource_detail::lock(retained);resource_detail::check(retained);
      for(const auto &state:retained)
        if(state->used.load()>=state->limit)throw DataError("E_RESOURCE_LIMIT","resource domain quota exceeded");
      for(const auto &state:retained)state->used.fetch_add(1);
      ticket->reserved=true;
    }
    auto identity=resource_detail::nextIdentity();
    auto create=std::forward<Factory>(factory);
    using Payload=resource_detail::Payload<T>;
    std::shared_ptr<Payload> payload;
    executor->invoke([&]{
      ResourcePermit permit(retained);permit.check();
      auto value=create(permit);
      if(!value)throw DataError("E_RESOURCE_CLOSED","resource factory returned no value");
      // Unpublished factory objects also die on this executor if allocation or
      // publication fails. The deleter moves the complete physical ticket,
      // including object quota, to its reserved cleanup slot.
      payload=std::shared_ptr<Payload>(new Payload(ticket,std::move(value)),
        [cleanup](Payload *p)noexcept{cleanup->retire(p,[](void *raw)noexcept{delete static_cast<Payload*>(raw);});});
    });
    auto control=std::make_shared<resource_detail::Control<T>>(identity,retained,std::move(payload));
    {
      auto locks=resource_detail::lock(retained);resource_detail::check(retained);
      for(const auto &state:retained){
        auto &resources=state->resources;
        std::erase_if(resources,[](const auto &entry){return entry.resource.expired()||entry.closed->load();});
        resources.push_back({control,control->closed});
      }
    }
    return ResourceOwner<T>(std::move(control));
  }
};

// A domain wrapper has unique lexical ownership; resource handles retain only
// state. Destroying/moving over the wrapper revokes every resource bound to it.
class ResourceDomain {
  resource_detail::Bindings bindings;
  std::shared_ptr<resource_detail::DomainState> own;
  static auto state(size_t limit) {
    if(!limit||limit>4096)throw DataError("E_RESOURCE_LIMIT","resource domain limit must be 1..4096");
    return std::make_shared<resource_detail::DomainState>(limit);
  }
  ResourceDomain(resource_detail::Bindings parents,size_t limit):bindings(std::move(parents)),own(state(limit)) {
    bindings.push_back(own);
    std::sort(bindings.begin(),bindings.end(),[](const auto &a,const auto &b){return std::less<>{}(a.get(),b.get());});
  }
public:
  explicit ResourceDomain(size_t limit=64):ResourceDomain({},limit){}
  ResourceDomain(const ResourceDomain&)=delete;
  ResourceDomain &operator=(const ResourceDomain&)=delete;
  ResourceDomain(ResourceDomain &&other) noexcept:bindings(std::move(other.bindings)),own(std::move(other.own)){}
  ResourceDomain &operator=(ResourceDomain &&other) noexcept {
    if(this!=&other){revoke();bindings=std::move(other.bindings);own=std::move(other.own);}return *this;
  }
  ~ResourceDomain(){revoke();}
  ResourceDomain child(size_t limit=64) const {
    auto retained=bindings;
    if(retained.size()>=8)throw DataError("E_RESOURCE_LIMIT","resource domain nesting exceeds eight");
    {auto locks=resource_detail::lock(retained);resource_detail::check(retained);}
    return ResourceDomain(std::move(retained),limit);
  }
  bool descendsFrom(const ResourceDomain &parent) const noexcept {
    if(parent.bindings.empty())return false;
    for(const auto &required:parent.bindings)
      if(std::find(bindings.begin(),bindings.end(),required)==bindings.end())return false;
    return true;
  }
  // Trusted host key; states retained by a joined domain cannot reuse it.
  const void *scopeKey() const noexcept {return own.get();}
  ResourceDomain combine(const ResourceDomain &other,size_t limit=64) const {
    auto retained=bindings;retained.insert(retained.end(),other.bindings.begin(),other.bindings.end());
    std::sort(retained.begin(),retained.end(),[](const auto &a,const auto &b){return std::less<>{}(a.get(),b.get());});
    retained.erase(std::unique(retained.begin(),retained.end()),retained.end());
    if(retained.size()>=8)throw DataError("E_RESOURCE_LIMIT","combined resource domain exceeds eight");
    {auto locks=resource_detail::lock(retained);resource_detail::check(bindings);resource_detail::check(other.bindings);}
    return ResourceDomain(std::move(retained),limit);
  }
  size_t used() const noexcept {return own?own->used.load():0;}
  void revoke() noexcept {
    auto retained=own;if(!retained)return;
    std::vector<resource_detail::Registration> resources;
    {
      std::lock_guard guard(retained->mutex);
      if(!retained->active.exchange(false))return;
      resources.swap(retained->resources);
    }
    for(const auto &entry:resources)if(auto resource=entry.resource.lock())resource->close();
  }
  ResourceAccess access()const{return ResourceAccess(bindings,own);}
  template<class T,class Factory> ResourceOwner<T> make(Factory &&factory) const {
    return access().make<T>(std::forward<Factory>(factory));
  }
  template<class T,class Factory> ResourceOwner<T> makeOnExecutor(
      const std::shared_ptr<ResourceExecutor> &executor,Factory &&factory)const{
    return access().makeOnExecutor<T>(executor,std::forward<Factory>(factory));
  }
};
namespace resource_detail {
using RequestBinder = ResourceDomain *(*)(const ResourceDomain &);
// The reference interpreter leaves this empty. A native request installs its
// thread-local binder, avoiding a filesystem dependency in ordinary programs.
inline thread_local RequestBinder requestBinder=nullptr;
}
}
