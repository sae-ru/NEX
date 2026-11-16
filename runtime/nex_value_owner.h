#pragma once
#include <atomic>
#include <cstddef>
#include <cstdint>
#include <exception>
#include <functional>
#include <limits>
#include <memory>
#include <type_traits>
#include <utility>

namespace nexrt {
namespace value_owner_detail {
struct Retirement;
struct Control {
  // Live counts are odd: (strong owners * 2) + 1. After the last decrement
  // reaches 1, this word can hold an aligned queue/context pointer (even).
  // Weak acquisition rejects both 1 and every even state, including queued
  // objects whose genuine destructor has not run yet.
  std::atomic<uintptr_t> state{3};
  std::atomic<size_t> weak{1}; // The implicit weak owner survives actual destruction.
  void (*const action)(Control*,bool)noexcept;
  explicit Control(void (*action)(Control*,bool)noexcept):action(action){}
  size_t useCount()const noexcept{auto value=state.load(std::memory_order_relaxed);return value&1?value>>1:0;}
  void retain()noexcept{
    auto before=state.fetch_add(2,std::memory_order_relaxed);
    if(before<3||!(before&1)||before>std::numeric_limits<uintptr_t>::max()-2)std::terminate();
  }
  bool tryRetain()noexcept{
    auto value=state.load(std::memory_order_relaxed);
    while(value>=3&&(value&1)&&value<=std::numeric_limits<uintptr_t>::max()-2){
      if(state.compare_exchange_weak(value,value+2,std::memory_order_acquire,std::memory_order_relaxed))return true;
    }
    return false;
  }
  void retainWeak()noexcept{
    auto before=weak.fetch_add(1,std::memory_order_relaxed);
    if(!before||before==std::numeric_limits<size_t>::max())std::terminate();
  }
  void releaseWeak()noexcept{if(weak.fetch_sub(1,std::memory_order_acq_rel)==1)action(this,false);}
  void release(Retirement&)noexcept;
  void release()noexcept;
  Retirement &retirement()const noexcept;
};
static_assert(alignof(Control)>=2);

// Stack-owned and explicitly carried across images. No TLS queue or module
// local recursion flag is needed. Nested host API root releases use their own
// context and finish synchronously; Data payload edges use release(context).
struct Retirement {
  Control *pending=nullptr;
  Retirement()=default;
  Retirement(const Retirement&)=delete;
  Retirement &operator=(const Retirement&)=delete;
  ~Retirement(){drain();}
  void enqueue(Control *value)noexcept{
    value->state.store(reinterpret_cast<uintptr_t>(pending),std::memory_order_relaxed);pending=value;
  }
  void drain()noexcept{
    while(pending){
      auto *value=pending;pending=reinterpret_cast<Control*>(value->state.load(std::memory_order_relaxed));
      value->state.store(reinterpret_cast<uintptr_t>(this),std::memory_order_relaxed);
      value->action(value,true);
    }
  }
};
static_assert(alignof(Retirement)>=2);
inline Retirement &Control::retirement()const noexcept{return *reinterpret_cast<Retirement*>(state.load(std::memory_order_relaxed));}
inline void Control::release(Retirement &context)noexcept{
  if(state.fetch_sub(2,std::memory_order_acq_rel)==3)context.enqueue(this);
}
inline void Control::release()noexcept{Retirement context;release(context);}

template<class T>struct Allocation final:Control {
  alignas(T) std::byte storage[sizeof(T)];
  Allocation():Control(dispose){}
  T *address()noexcept{return reinterpret_cast<T*>(storage);}
  T *object()noexcept{return std::launder(address());}
  static void dispose(Control *value,bool destroy)noexcept{
    auto *allocation=static_cast<Allocation*>(value);
    if(destroy){std::destroy_at(allocation->object());allocation->releaseWeak();}
    else delete allocation;
  }
};
template<class T,class Deleter>struct ExternalAllocation final:Control {
  T *const pointer;
  Deleter deleter;
  ExternalAllocation(T *pointer,Deleter &&deleter)noexcept:Control(dispose),pointer(pointer),deleter(std::move(deleter)){}
  static void dispose(Control *value,bool destroy)noexcept{
    auto *allocation=static_cast<ExternalAllocation*>(value);
    if(destroy){allocation->deleter(allocation->pointer);allocation->releaseWeak();}
    else delete allocation;
  }
};
}

template<class T>class WeakValueOwner;
class ValueOwnerFactory;

// Deliberately two pointer words, matching the previous private Value layout.
// It is not binary-interchangeable with std::shared_ptr; all C++ runtime images
// must use the matching compiler/runtime cohort. Public C handles stay opaque.
template<class T>class ValueOwner {
  template<class U>friend class ValueOwner;
  template<class U>friend class WeakValueOwner;
  friend class ValueOwnerFactory;
  struct Adopt {};
  T *pointer_=nullptr;
  value_owner_detail::Control *owner_=nullptr;
  ValueOwner(T *pointer,value_owner_detail::Control *owner,Adopt)noexcept:pointer_(pointer),owner_(owner){}
public:
  ValueOwner()noexcept=default;
  ValueOwner(std::nullptr_t)noexcept{}
  template<class U>requires std::is_convertible_v<U*,T*>
  explicit ValueOwner(U *pointer);
  template<class U,class Deleter>requires std::is_convertible_v<U*,T*>
  ValueOwner(U *pointer,Deleter deleter);
  ValueOwner(const ValueOwner &other)noexcept:pointer_(other.pointer_),owner_(other.owner_){if(owner_)owner_->retain();}
  template<class U>requires std::is_convertible_v<U*,T*>
  ValueOwner(const ValueOwner<U> &other)noexcept:pointer_(other.pointer_),owner_(other.owner_){if(owner_)owner_->retain();}
  ValueOwner(ValueOwner &&other)noexcept:pointer_(std::exchange(other.pointer_,nullptr)),owner_(std::exchange(other.owner_,nullptr)){}
  template<class U>requires std::is_convertible_v<U*,T*>
  ValueOwner(ValueOwner<U> &&other)noexcept:pointer_(std::exchange(other.pointer_,nullptr)),owner_(std::exchange(other.owner_,nullptr)){}
  ~ValueOwner(){if(owner_)owner_->release();}
  ValueOwner &operator=(const ValueOwner &other)noexcept{ValueOwner(other).swap(*this);return *this;}
  ValueOwner &operator=(ValueOwner &&other)noexcept{ValueOwner(std::move(other)).swap(*this);return *this;}
  template<class U>requires std::is_convertible_v<U*,T*>
  ValueOwner &operator=(const ValueOwner<U> &other)noexcept{ValueOwner(other).swap(*this);return *this;}
  template<class U>requires std::is_convertible_v<U*,T*>
  ValueOwner &operator=(ValueOwner<U> &&other)noexcept{ValueOwner(std::move(other)).swap(*this);return *this;}
  T *get()const noexcept{return pointer_;}
  T *operator->()const noexcept{return pointer_;}
  T &operator*()const noexcept{return *pointer_;}
  explicit operator bool()const noexcept{return pointer_!=nullptr;}
  size_t use_count()const noexcept{return owner_?owner_->useCount():0;}
  bool unique()const noexcept{return use_count()==1;}
  void swap(ValueOwner &other)noexcept{std::swap(pointer_,other.pointer_);std::swap(owner_,other.owner_);}
  void reset()noexcept{ValueOwner().swap(*this);}
  void resetDeferred(value_owner_detail::Retirement &context)noexcept{
    pointer_=nullptr;auto *owner=std::exchange(owner_,nullptr);if(owner)owner->release(context);
  }
  template<class U>bool owner_before(const ValueOwner<U> &other)const noexcept{return std::less<value_owner_detail::Control*>{}(owner_,other.owner_);}
};
template<class T,class U>bool operator==(const ValueOwner<T> &a,const ValueOwner<U> &b)noexcept{return a.get()==b.get();}
template<class T>bool operator==(const ValueOwner<T> &a,std::nullptr_t)noexcept{return !a;}
template<class T>void swap(ValueOwner<T> &a,ValueOwner<T> &b)noexcept{a.swap(b);}

template<class T>class WeakValueOwner {
  template<class U>friend class WeakValueOwner;
  T *pointer_=nullptr;
  value_owner_detail::Control *owner_=nullptr;
public:
  WeakValueOwner()noexcept=default;
  WeakValueOwner(const WeakValueOwner &other)noexcept:pointer_(other.pointer_),owner_(other.owner_){if(owner_)owner_->retainWeak();}
  template<class U>requires std::is_convertible_v<U*,T*>
  WeakValueOwner(const WeakValueOwner<U> &other)noexcept:pointer_(other.pointer_),owner_(other.owner_){if(owner_)owner_->retainWeak();}
  template<class U>requires std::is_convertible_v<U*,T*>
  WeakValueOwner(const ValueOwner<U> &other)noexcept:pointer_(other.pointer_),owner_(other.owner_){if(owner_)owner_->retainWeak();}
  WeakValueOwner(WeakValueOwner &&other)noexcept:pointer_(std::exchange(other.pointer_,nullptr)),owner_(std::exchange(other.owner_,nullptr)){}
  ~WeakValueOwner(){if(owner_)owner_->releaseWeak();}
  WeakValueOwner &operator=(const WeakValueOwner &other)noexcept{WeakValueOwner(other).swap(*this);return *this;}
  WeakValueOwner &operator=(WeakValueOwner &&other)noexcept{WeakValueOwner(std::move(other)).swap(*this);return *this;}
  template<class U>requires std::is_convertible_v<U*,T*>
  WeakValueOwner &operator=(const ValueOwner<U> &other)noexcept{WeakValueOwner(other).swap(*this);return *this;}
  ValueOwner<T> lock()const noexcept{
    if(owner_&&owner_->tryRetain())return ValueOwner<T>(pointer_,owner_,typename ValueOwner<T>::Adopt{});
    return {};
  }
  size_t use_count()const noexcept{return owner_?owner_->useCount():0;}
  bool expired()const noexcept{return !use_count();}
  void swap(WeakValueOwner &other)noexcept{std::swap(pointer_,other.pointer_);std::swap(owner_,other.owner_);}
  void reset()noexcept{WeakValueOwner().swap(*this);}
  template<class U>bool owner_before(const WeakValueOwner<U> &other)const noexcept{return std::less<value_owner_detail::Control*>{}(owner_,other.owner_);}
};

class ValueOwnerFactory {
public:
  template<class T,class U,class Deleter>static ValueOwner<T> take(U *pointer,Deleter deleter){
    static_assert(std::is_nothrow_move_constructible_v<Deleter>,"value deleters must move without throwing");
    value_owner_detail::ExternalAllocation<U,Deleter> *allocation=nullptr;
    try{allocation=new value_owner_detail::ExternalAllocation<U,Deleter>(pointer,std::move(deleter));}
    catch(...){deleter(pointer);throw;}
    if(pointer)pointer->attachValueOwner(allocation);
    return ValueOwner<T>(pointer,allocation,typename ValueOwner<T>::Adopt{});
  }
  // The builder form keeps private owned constructors at their existing friend
  // call sites, while still coallocating the control and complete object.
  template<class T,class Builder>static ValueOwner<T> build(Builder &&builder){
    auto *allocation=new value_owner_detail::Allocation<T>;
    try{
      auto *pointer=builder(allocation->address());
      if(pointer!=allocation->address())std::terminate();
      pointer->attachValueOwner(allocation);
      return ValueOwner<T>(pointer,allocation,typename ValueOwner<T>::Adopt{});
    }catch(...){delete allocation;throw;}
  }
  template<class T,class...Args>static ValueOwner<T> make(Args&&...args){
    return build<T>([&](T *address){return std::construct_at(address,std::forward<Args>(args)...);});
  }
};
template<class T>template<class U>requires std::is_convertible_v<U*,T*>
ValueOwner<T>::ValueOwner(U *pointer):ValueOwner(ValueOwnerFactory::take<T>(pointer,std::default_delete<U>{})){}
template<class T>template<class U,class Deleter>requires std::is_convertible_v<U*,T*>
ValueOwner<T>::ValueOwner(U *pointer,Deleter deleter):ValueOwner(ValueOwnerFactory::take<T>(pointer,std::move(deleter))){}
template<class T,class...Args>ValueOwner<T> makeValueOwner(Args&&...args){return ValueOwnerFactory::make<T>(std::forward<Args>(args)...);}
}
