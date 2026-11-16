#include "nex_value.h"
#include <barrier>
#include <functional>
#include <filesystem>
#include <iostream>
#include <thread>
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#else
#include <dlfcn.h>
#include <pthread.h>
#endif
using namespace nexrt;
namespace {
constexpr size_t depth=65536,stackBytes=256*1024;
void require(bool value,const char *message){if(!value)throw std::runtime_error(message);}
struct Work {std::function<void()> action;std::exception_ptr error;};
#ifdef _WIN32
DWORD WINAPI enter(void *raw){auto &work=*static_cast<Work*>(raw);try{work.action();}catch(...){work.error=std::current_exception();}return 0;}
void bounded(std::function<void()> action){
  Work work{std::move(action),{}};auto handle=CreateThread(nullptr,stackBytes,enter,&work,STACK_SIZE_PARAM_IS_A_RESERVATION,nullptr);
  require(handle,"cannot create bounded worker");auto result=WaitForSingleObject(handle,INFINITE);CloseHandle(handle);
  require(result==WAIT_OBJECT_0,"cannot join bounded worker");if(work.error)std::rethrow_exception(work.error);
}
#else
void *enter(void *raw){auto &work=*static_cast<Work*>(raw);try{work.action();}catch(...){work.error=std::current_exception();}return nullptr;}
void bounded(std::function<void()> action){
  Work work{std::move(action),{}};pthread_attr_t attr;require(pthread_attr_init(&attr)==0,"cannot create worker attributes");
  auto result=pthread_attr_setstacksize(&attr,stackBytes);pthread_t handle{};
  if(!result)result=pthread_create(&handle,&attr,enter,&work);pthread_attr_destroy(&attr);
  require(!result,"cannot create bounded worker");require(!pthread_join(handle,nullptr),"cannot join bounded worker");
  if(work.error)std::rethrow_exception(work.error);
}
#endif
struct Counted:Data {
  std::atomic<unsigned> &destroyed;
  explicit Counted(std::atomic<unsigned> &destroyed):Data(Data::Record),destroyed(destroyed){values.emplace_back(int64_t(42));}
  ~Counted(){if(values.size()!=1||values[0].scalar!=42)std::abort();++destroyed;}
};
struct Prefix {virtual ~Prefix()=default;int prefix=7;};
struct Adjusted final:Prefix,Counted {explicit Adjusted(std::atomic<unsigned> &destroyed):Counted(destroyed){}};
struct TrackedDeleter {
  std::atomic<unsigned> &freed;bool active=true;
  explicit TrackedDeleter(std::atomic<unsigned> &freed):freed(freed){}
  TrackedDeleter(TrackedDeleter &&other)noexcept:freed(other.freed),active(std::exchange(other.active,false)){}
  void operator()(Counted *value)noexcept{delete value;}
  ~TrackedDeleter(){if(active)++freed;}
};
struct ConstructorFailure {};
struct Failing final:Data {
  Failing():Data(Data::List){values.emplace_back(string("partially constructed"));throw ConstructorFailure{};}
};
struct Observer final:Data {
  WeakValueOwner<Data> watched;
  std::atomic<unsigned> &watchedDestroyed;
  Value independent;
  std::atomic<unsigned> &independentDestroyed;
  bool &observed;
  Observer(WeakValueOwner<Data> watched,std::atomic<unsigned> &destroyed,Value independent,std::atomic<unsigned> &nested,bool &observed)
    :Data(Data::Record),watched(std::move(watched)),watchedDestroyed(destroyed),independent(std::move(independent)),independentDestroyed(nested),observed(observed){}
  ~Observer(){
    if(!watched.expired()||watched.use_count()!=0||watched.lock()||watchedDestroyed!=0)std::abort();
    independent=Value();
    if(independentDestroyed!=1||watchedDestroyed!=0)std::abort();observed=true;
  }
};
Value chain(Value value,size_t count=depth){for(size_t i=0;i<count;++i){auto data=Data::make(Data::List);data->values.push_back(std::move(value));value=Value(std::move(data));}return value;}
struct Image {
#ifdef _WIN32
  HMODULE handle;
  explicit Image(const char *path):handle(LoadLibraryW(std::filesystem::u8path(path).c_str())){require(handle,"cannot load value-owner module");}
  void *symbol(const char *name){return reinterpret_cast<void*>(GetProcAddress(handle,name));}
  ~Image(){FreeLibrary(handle);}
#else
  void *handle;
  explicit Image(const char *path):handle(dlopen(path,RTLD_NOW|RTLD_LOCAL)){require(handle,"cannot load value-owner module");}
  void *symbol(const char *name){return dlsym(handle,name);}
  ~Image(){dlclose(handle);}
#endif
};
}
int main(int argc,char **argv){try{
  require(argc==2,"expected value-owner module path");unsigned cases=0;
  auto check=[&](const char *name,auto action){auto live=liveObjects.load();action();require(liveObjects.load()==live,"live value count changed");++cases;std::cout<<"PASS "<<name<<std::endl;};
  check("strong weak conversion and adjusted base",[]{
    std::atomic<unsigned> destroyed=0;auto derived=makeValueOwner<Adjusted>(destroyed);
    ValueOwner<Data> base=derived;WeakValueOwner<Data> weak=derived;
    require(base.get()==static_cast<Data*>(derived.get())&&base.use_count()==2,"converted owner differs");
    auto locked=weak.lock();require(locked==base&&locked.use_count()==3,"weak acquisition differs");
    auto *same=&base;base=*same;base=std::move(*same);require(base.use_count()==3,"self assignment changed ownership");
    derived.reset();locked.reset();require(!weak.expired()&&base.use_count()==1,"live owner lost");
    auto moved=std::move(base);require(!base&&moved.use_count()==1,"move changed ownership");moved.reset();
    require(destroyed==1&&weak.expired()&&!weak.lock(),"weak owner resurrected destroyed data");weak.reset();
  });
  check("constructor unwind",[]{try{(void)makeValueOwner<Failing>();throw std::runtime_error("constructor returned");}catch(const ConstructorFailure&){} });
  check("weak controls pin storage through actual destruction",[]{
    std::atomic<unsigned> destroyed=0,freed=0;
    ValueOwner<Data> value(new Counted(destroyed),TrackedDeleter(freed));WeakValueOwner<Data> weak=value;
    value.reset();require(destroyed==1&&freed==0&&weak.expired()&&!weak.lock(),"weak storage lifetime differs");
    weak.reset();require(freed==1,"last weak owner retained control storage");
  });
  check("queued weak state and synchronous nested retirement",[]{
    std::atomic<unsigned> destroyed=0,nested=0;bool observed=false;
    auto first=makeValueOwner<Counted>(destroyed);WeakValueOwner<Data> weak=first;
    auto nestedRoot=chain(Value(makeValueOwner<Counted>(nested)));
    auto second=makeValueOwner<Observer>(weak,destroyed,std::move(nestedRoot),nested,observed);
    auto parent=Data::make(Data::List);parent->values={Value(first),Value(second)};first.reset();second.reset();
    bounded([&]{parent.reset();});require(observed&&destroyed==1&&nested==1,"retirement completion differs");weak.reset();
  });
  check("weak lock races last strong release",[]{
    std::atomic<unsigned> destroyed=0;auto value=makeValueOwner<Counted>(destroyed);WeakValueOwner<Data> weak=value;
    std::barrier start(3);std::atomic<unsigned> acquired=0;
    auto acquire=[&]{auto initial=weak.lock();require(bool(initial),"initial weak lock failed");start.arrive_and_wait();initial.reset();
      for(size_t i=0;i<50000;++i)if(auto held=weak.lock()){if(held->values.size()!=1||held->values[0].scalar!=42)std::abort();++acquired;}};
    std::jthread a(acquire),b(acquire);start.arrive_and_wait();value.reset();a.join();b.join();
    require(destroyed==1&&weak.expired()&&!weak.lock(),"racing weak ownership differs");
  });
  check("concurrent alias ladder on bounded stacks",[]{
    std::atomic<unsigned> destroyed=0;Value root(makeValueOwner<Counted>(destroyed));std::vector<Value> aliases;aliases.reserve(depth);
    for(size_t i=0;i<depth;++i){root=chain(std::move(root),1);aliases.push_back(root);}
    std::barrier start(2);std::exception_ptr first,second;
    std::thread a([&]{try{bounded([&]{start.arrive_and_wait();root=Value();});}catch(...){first=std::current_exception();}});
    std::thread b([&]{try{bounded([&]{start.arrive_and_wait();for(auto &alias:aliases)alias=Value();});}catch(...){second=std::current_exception();}});
    a.join();b.join();if(first)std::rethrow_exception(first);if(second)std::rethrow_exception(second);
    require(destroyed==1,"concurrent ladder retained its leaf");
  });
  check("hidden-module graph retirement across images",[&]{
    Image module(argv[1]);auto make=reinterpret_cast<void(*)(Value*,const Value*,size_t)>(module.symbol("nex_owner_module_make"));
    auto live=reinterpret_cast<int64_t(*)()>(module.symbol("nex_owner_module_live"));require(make&&live,"module entry missing");
    auto moduleBefore=live();std::atomic<unsigned> destroyed=0;Value leaf(makeValueOwner<Counted>(destroyed)),root;
    make(&root,&leaf,depth);leaf=Value();WeakValueOwner<Data> weak=root.object;
    bounded([&]{root=Value();});require(destroyed==1&&weak.expired()&&live()==moduleBefore,"module graph was not retired");
    weak.reset(); // The image must also outlive its weak control allocations.
  });
  static_assert(sizeof(ValueOwner<Data>)==2*sizeof(void*));
  std::cout<<"{\"ok\":true,\"cases\":"<<cases<<",\"depth\":"<<depth<<",\"stack_bytes\":"<<stackBytes
    <<",\"sizeof_value\":"<<sizeof(Value)<<",\"sizeof_data\":"<<sizeof(Data)<<",\"sizeof_control\":"<<sizeof(value_owner_detail::Control)<<",\"live_value_delta\":0}\n";
  return 0;
}catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 1;}}
