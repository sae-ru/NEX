#pragma once
#include "nex_error.h"
#include <atomic>
#include <cstddef>
#include <memory>
#include <mutex>
#include <span>

namespace nexrt {
template<class> class ResourceOwner;
class ExternalResource;
class ResourceAccess;
namespace resource_detail {
struct ControlBase;struct SettlementGuard;
struct SettlementState {std::mutex mutex;size_t guards=0;bool ready=false;};
}
namespace resource_region_detail {struct Forest;struct Graph;struct Owner;}

class ResourceSettlement {
  std::shared_ptr<resource_detail::SettlementState> state;
  friend class ResourceAccess;
  friend class ExternalResource;
  friend struct resource_detail::SettlementGuard;
  static ResourceSettlement pending(){ResourceSettlement result;result.state=std::make_shared<resource_detail::SettlementState>();return result;}
public:
  ResourceSettlement()=default;
  bool ready()const noexcept{if(!state)return true;std::lock_guard lock(state->mutex);return state->ready;}
};

// A weak, destruction-only host capability. It retains no physical payload and
// gives no access to native data. Numeric region IDs never construct authority.
class ResourceRevocation {
  std::weak_ptr<resource_detail::ControlBase> control;
  ResourceSettlement settlement;
  template<class> friend class ResourceOwner;
  ResourceRevocation(std::weak_ptr<resource_detail::ControlBase>,ResourceSettlement);
public:
  ResourceRevocation()=default;
  bool close()const noexcept;
  bool expired()const noexcept;
  bool settled()const noexcept{return settlement.ready();}
};
// Request authority is the common caller ancestry. Attached scheduler graphs
// retain distinct Native/Reference identities until explicit ancestor transfer.
// Logical ancestry never creates a physical grant or drains source execution.
enum class ResourceRegionFamily {Native,Reference,Request};
struct ResourceRegionLimits {size_t regions=1025,depth=256,owners=4096,tasks=0,groups=1024;};
class ResourceRegionAuthority;
class ResourceRegionOwner {
  std::shared_ptr<resource_region_detail::Owner> owner;
  friend class ResourceRegionAuthority;
  friend class ExternalResource;
  explicit ResourceRegionOwner(std::shared_ptr<resource_region_detail::Owner>);
  void attach(ResourceSettlement)const;
  void publish(ResourceRevocation)const;
public:
  ResourceRegionOwner()=default;
  explicit operator bool()const noexcept{return bool(owner);}
  bool active()const noexcept;
  void checkCreation()const;
  void check(const ResourceRegionAuthority&)const;
  void checkPromotion(const ResourceRegionAuthority &actor,const ResourceRegionAuthority &target)const;
  void promote(const ResourceRegionAuthority &actor,const ResourceRegionAuthority &target)const;
  // Validate the entire bounded batch before changing any owner. Ancestor
  // borrowing is unchanged; promotion reserves every destination slot first.
  static void transfer(std::span<const ResourceRegionOwner>,const ResourceRegionAuthority &actor,
      const ResourceRegionAuthority &target,bool commit=true);
};
class ResourceRegionAuthority {
  std::shared_ptr<resource_region_detail::Graph> graph;
  size_t node=0;
  friend class ResourceRegion;
  friend class ResourceRegionOwner;
  ResourceRegionAuthority(std::shared_ptr<resource_region_detail::Graph>,size_t);
public:
  ResourceRegionAuthority()=default;
  explicit operator bool()const noexcept{return bool(graph);}
  void check()const;
  ResourceRegionOwner reserve()const;
  bool contains(const ResourceRegionAuthority&)const;
  size_t depth()const;
  ResourceRegionFamily family()const;
};
class ResourceRegionRetirement {
  std::shared_ptr<resource_region_detail::Graph> graph;
  size_t node=0;
  friend class ResourceRegion;
  ResourceRegionRetirement(std::shared_ptr<resource_region_detail::Graph>,size_t);
public:
  ResourceRegionRetirement()=default;
  ResourceRegionRetirement(ResourceRegionRetirement&&)noexcept;
  ResourceRegionRetirement &operator=(ResourceRegionRetirement&&)noexcept;
  ResourceRegionRetirement(const ResourceRegionRetirement&)=delete;
  ~ResourceRegionRetirement();
  // Call outside scheduler and graph locks. Logical revocation is already
  // visible; physical borrows and executor finalizers keep their own quotas.
  void requestClose()noexcept;
  bool ready()const noexcept;
};
class ResourceRegion {
  std::shared_ptr<resource_region_detail::Graph> graph;
  size_t node=0;
  std::atomic<bool> responsible{true};
  ResourceRegion(std::shared_ptr<resource_region_detail::Graph>,size_t);
public:
  explicit ResourceRegion(ResourceRegionFamily=ResourceRegionFamily::Native,ResourceRegionLimits={});
  static ResourceRegion inRequest(ResourceRegionFamily,const ResourceRegionAuthority &,ResourceRegionLimits={});
  ResourceRegion(ResourceRegion&&)noexcept;
  ResourceRegion &operator=(ResourceRegion&&)noexcept;
  ResourceRegion(const ResourceRegion&)=delete;
  ~ResourceRegion();
  ResourceRegion child()const;
  ResourceRegion taskChild()const;
  ResourceRegionAuthority authority()const;
  ResourceRegionRetirement beginClose()noexcept;
  void close()noexcept;
};
}
