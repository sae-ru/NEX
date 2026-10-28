#include "nex_external_resource.h"
#include "nex_ffi_host.h"
#include "nex_json.h"
#include "nex_parallel_value.h"
#include "nex_host.h"
#include "nex_task_values.h"
#include <array>
#include <condition_variable>
#include <dlfcn.h>
#include <iostream>
#include <map>
#include <thread>

using namespace nexrt;
extern "C" nex_ffi_status old_resource_forward(const nex_ffi_api_v1*,nex_ffi_call,const nex_ffi_ref*,uint64_t,nex_ffi_ref*,void*);
namespace {
std::map<const void*,std::pair<size_t,int>> allocations;
std::mutex allocationMutex;
bool allocationError=false;
void require(bool v,const char *text){if(!v)throw std::runtime_error(text);}
template<class F> void error(const char *code,F f){try{f();}catch(const DataError &e){require(e.code==code,"wrong DataError");return;}throw std::runtime_error(std::string("missing ")+code);}
struct Box {
  std::vector<unsigned char> bytes;
  int *destroyed;
  std::function<void()> onDestroy;
  Box(size_t n,int &destroyed,std::function<void()> f={}):bytes(n,42),destroyed(&destroyed),onDestroy(std::move(f)){}
  ~Box()noexcept{++*destroyed;if(onDestroy)onDestroy();}
};
std::shared_ptr<void> hostCode(){return std::make_shared<int>(1);}
ExternalResourceType<Box> type(){return {"model::Buffer",std::string(64,'a')};}
template<class Budgets> ExternalResource make(const ResourceDomain &domain,const ExternalResourceType<Box> &t,
    const Budgets &budgets,uint64_t bytes,int &destroyed){
  return ExternalResource::make(domain,t,std::span<const ResourceByteBudget>(budgets),bytes,hostCode(),[&](const auto &){return std::make_unique<Box>(bytes,destroyed);});
}
nex_ffi_status forward(const nex_ffi_api_v1 *api,nex_ffi_call call,const nex_ffi_ref *args,uint64_t count,nex_ffi_ref *out,void*){
  if(count!=1)return NEX_FFI_ARGUMENT;uint32_t kind=0;if(api->kind(call,args[0],&kind)!=NEX_FFI_OK||kind!=NEX_FFI_EXTERNAL_RESOURCE)return NEX_FFI_TYPE;
  uint64_t unchanged=123;int64_t integer=456;
  if(api->file_identity(call,args[0],&unchanged)!=NEX_FFI_TYPE||unchanged!=123||api->get_i64(call,args[0],&integer)!=NEX_FFI_TYPE||integer!=456)return NEX_FFI_INTERNAL;
  nex_ffi_ref retained=0;if(auto s=api->retain(call,args[0],&retained))return s;
  return api->make_success(call,retained,out);
}
std::vector<int> moduleEvents;std::function<void(int)> observeModule;
extern "C" void moduleEvent(int event){moduleEvents.push_back(event);if(observeModule)observeModule(event);}
struct PluginBox {
  void *object;void(*destroy)(void*);
  PluginBox(void *object,void(*destroy)(void*)):object(object),destroy(destroy){}
  PluginBox(const PluginBox&)=delete;
  ~PluginBox()noexcept{destroy(object);}
};
}
extern "C" {
void nex_profile_enter(const char*,const char*,int64_t,const char*){}
void nex_profile_leave(){}
void nex_profile_unwind(){}
void nex_profile_allocation(const void *p,size_t size,int pool){std::lock_guard lock(allocationMutex);if(!allocations.emplace(p,std::pair{size,pool}).second)allocationError=true;}
void nex_profile_free(const void *p){std::lock_guard lock(allocationMutex);if(allocations.erase(p)!=1)allocationError=true;}
}
int main(int argc,char **argv){try{
  require(argc==2,"expected plugin path");unsigned cases=0;
  auto run=[&](const char *name,auto f){f();require(liveObjects==0&&!allocationError&&allocations.empty(),"managed ownership imbalance");++cases;std::cout<<"PASS "<<name<<std::endl;};
  run("typed ownership and complete subtype",[]{
    ResourceDomain domain;std::array budgets{ResourceByteBudget(64)};auto t=type();int destroyed=0;
    auto owner=make(domain,t,budgets,64,destroyed);Value a(externalValue(owner)),b(externalValue(owner));
    require(owner.identity()!=0&&owner.isOpen()&&owner.capacityBytes()==64,"missing resource metadata");
    require(equal(a,b)&&a.object!=b.object,"aliases differ");require(printable(a)=="<resource>"&&representation(a)=="\"<resource>\"","resource display leaked data");
    require(allocations.at(a.object.get())==std::pair{sizeof(ExternalData),1},"wrong subtype allocation");
    error("E_RUNTIME",[]{(void)std::make_shared<Data>(Data::External);});error("E_RUNTIME",[&]{(void)std::make_shared<Data>(*a.object);});error("E_RUNTIME",[]{(void)externalValue({});});
    require(owner.close()&&!externalResource(a.object).close()&&!owner.isOpen(),"close not shared");require(destroyed==1&&domain.used()==0&&budgets[0].used()==0,"closed resource retained capacity");require(equal(a,b),"close changed identity");
  });
  run("aggregate and callable capture ownership",[]{
    ResourceDomain domain;std::array budgets{ResourceByteBudget(4)};auto t=type();int destroyed=0;
    auto closure=std::make_shared<Data>(Data::Closure);
    {auto owner=make(domain,t,budgets,4,destroyed);closure->values.push_back(success(Value(externalValue(owner))));}
    require(destroyed==0&&budgets[0].used()==4,"capture lost physical owner");closure.reset();require(destroyed==1&&budgets[0].used()==0,"capture leaked owner");
  });
  run("borrow delays destruction and both quotas",[]{
    ResourceDomain domain(1);std::array budgets{ResourceByteBudget(4)};auto t=type();int destroyed=0;
    auto owner=make(domain,t,budgets,4,destroyed);auto lease=owner.borrow(t);Box *borrow=&lease.value(t);owner.close();
    require(destroyed==0&&domain.used()==1&&budgets[0].used()==4,"logical close returned quota early");require(borrow->bytes[0]==42,"in-flight borrow lost object");
    error("E_RESOURCE_CLOSED",[&]{lease.check();});error("E_RESOURCE_LIMIT",[&]{make(domain,t,budgets,1,destroyed);});lease={};require(destroyed==1&&domain.used()==0&&budgets[0].used()==0,"last borrow did not settle");
  });
  run("registration identity cannot be forged by matching names",[]{
    ResourceDomain domain;std::array budgets{ResourceByteBudget(1)};auto t=type(),other=type();int destroyed=0;auto owner=make(domain,t,budgets,1,destroyed);
    error("E_RESOURCE_TYPE",[&]{owner.borrow(other);});auto lease=owner.borrow(t);error("E_RESOURCE_TYPE",[&]{lease.value(other);});
  });
  run("joined byte budgets and aliases charge once",[]{
    ResourceDomain domain;ResourceByteBudget global(8),request(4);std::array budgets{global,request,global};auto t=type();int destroyed=0;auto owner=make(domain,t,budgets,4,destroyed);
    require(global.used()==4&&request.used()==4,"budget aliases charged twice");error("E_RESOURCE_BYTES",[&]{make(domain,t,budgets,1,destroyed);});require(domain.used()==1&&global.used()==4,"failed reservation leaked quota");
  });
  run("capacity rejection precedes factory",[]{
    ResourceDomain domain;std::array budgets{ResourceByteBudget(1)};auto t=type();int called=0;
    error("E_RESOURCE_BYTES",[&]{ExternalResource::make(domain,t,budgets,2,hostCode(),[&](auto&)->std::unique_ptr<Box>{++called;return {};});});require(called==0&&domain.used()==0&&budgets[0].used()==0,"rejected capacity invoked factory");
  });
  run("throwing and null factories roll back",[]{
    ResourceDomain domain;std::array budgets{ResourceByteBudget(4)};auto t=type();
    error("E_TEST",[&]{ExternalResource::make(domain,t,budgets,4,hostCode(),[](auto&)->std::unique_ptr<Box>{throw DataError("E_TEST","factory");});});
    error("E_RESOURCE_CLOSED",[&]{ExternalResource::make(domain,t,budgets,4,hostCode(),[](auto&)->std::unique_ptr<Box>{return {};});});require(domain.used()==0&&budgets[0].used()==0,"factory failure leaked quota");
  });
  run("revoked publication destroys unpublished object",[]{
    ResourceDomain domain;std::array budgets{ResourceByteBudget(4)};auto t=type();int destroyed=0;
    error("E_RESOURCE_SCOPE",[&]{ExternalResource::make(domain,t,budgets,4,hostCode(),[&](auto&){domain.revoke();return std::make_unique<Box>(4,destroyed);});});require(destroyed==1&&domain.used()==0&&budgets[0].used()==0,"revoked publication leaked object");
  });
  run("zero capacity still needs live authority",[]{
    ResourceDomain domain;std::array budgets{ResourceByteBudget(1)};auto t=type();int destroyed=0;auto owner=make(domain,t,budgets,0,destroyed);require(domain.used()==1&&budgets[0].used()==0,"empty resource missing physical slot");domain.revoke();require(destroyed==1,"empty resource not revoked");error("E_RESOURCE_SCOPE",[&]{owner.borrow(t);});
  });
  run("request exit revokes escaped managed values",[]{
    ResourceDomain grant;std::array budgets{ResourceByteBudget(4)};auto t=type();int destroyed=0;Value escaped;
    {RequestScope request(1000,5000);escaped=Value(externalValue(make(grant,t,budgets,4,destroyed)));}
    require(!externalResource(escaped.object).isOpen()&&destroyed==1&&budgets[0].used()==0,"escaped owner outlived request authority");error("E_RESOURCE_SCOPE",[&]{externalResource(escaped.object).borrow(t);});
  });
  run("cancel retains in-flight physical storage until settlement",[]{
    ResourceDomain grant;std::array budgets{ResourceByteBudget(4)};auto t=type();int destroyed=0;RequestScope request(1000,5000);auto owner=make(grant,t,budgets,4,destroyed);auto lease=owner.borrow(t);request.cancel();
    require(!owner.isOpen()&&destroyed==0&&budgets[0].used()==4,"cancel reclaimed in-flight bytes");error("E_RESOURCE_SCOPE",[&]{lease.check();});lease={};require(destroyed==1&&budgets[0].used()==0,"canceled borrow leaked capacity");
  });
  run("untyped C forwarding preserves opaque subtype",[]{
    ResourceDomain domain;std::array budgets{ResourceByteBudget(4)};auto t=type();int destroyed=0;Value out;
    {Value input(externalValue(make(domain,t,budgets,4,destroyed)));std::array args{input};for(auto callback:{forward,old_resource_forward}){out=invokeForeign(callback,args);require(equal(unwrap(out),input),"C transport changed resource identity");}}
    require(destroyed==0&&budgets[0].used()==4,"C transport sliced owner");out={};require(destroyed==1&&budgets[0].used()==0,"C return lost cleanup");
  });
  run("typed C cannot relabel external authority as a file",[]{
    ResourceDomain domain;std::array budgets{ResourceByteBudget(1)};auto t=type();int destroyed=0;Value resource(externalValue(make(domain,t,budgets,1,destroyed)));std::array args{resource};
    ForeignSignature signature(R"({"schema":"nex.foreign-signature/1","parameters":[0],"result":0,"types":[{"kind":"file"}]})");bool entered=false;
    auto callback=[](const nex_ffi_api_v1*,nex_ffi_call,const nex_ffi_ref *a,uint64_t,nex_ffi_ref *o,void *p)->nex_ffi_status{*static_cast<bool*>(p)=true;*o=a[0];return NEX_FFI_OK;};
    error("E_FFI_TYPE",[&]{invokeForeignTyped(callback,args,signature,&entered);});require(!entered&&externalResource(resource.object).isOpen(),"typed resource mismatch entered producer or consumed owner");
  });
  run("JSON and parallel boundaries traverse hidden owners",[]{
    ResourceDomain domain;std::array budgets{ResourceByteBudget(1)};auto t=type();int destroyed=0;Value resource(externalValue(make(domain,t,budgets,1,destroyed)));auto capture=std::make_shared<Data>(Data::Closure);capture->values={success(resource)};
    error("E_PARALLEL_VALUE",[&]{validateParallelValue(Value(capture),[]{});});error("E_JSON",[&]{encodeJSON(success(resource));});require(externalResource(resource.object).isOpen(),"rejected transfer consumed owner");
  });
  run("native task snapshot rejects hidden external authority",[]{
    ResourceDomain domain;std::array budgets{ResourceByteBudget(1)};auto t=type();int destroyed=0;Value resource(externalValue(make(domain,t,budgets,1,destroyed)));auto capture=std::make_shared<Data>(Data::Closure);capture->values={success(resource)};RequestScope request(1000,5000);TaskGroup group(1);
    error("E_TASK_VALUE",[&]{validateTaskSnapshot(group,Value(capture),{});});require(externalResource(resource.object).isOpen(),"task rejection consumed resource");
  });
  run("factory requires code owner and valid class metadata",[]{
    for(auto name:{"::","x::","x::::y","1x","x y"})error("E_RESOURCE_TYPE",[&]{ExternalResourceType<Box> invalid(name,std::string(64,'a'));});
    error("E_RESOURCE_TYPE",[]{ExternalResourceType<Box> invalid("Type",std::string(64,'A'));});error("E_RESOURCE_BYTES",[]{ResourceByteBudget invalid(0);});
    ResourceDomain domain;std::array budgets{ResourceByteBudget(1)};auto t=type();int called=0;
    error("E_RESOURCE_MODULE",[&]{ExternalResource::make(domain,t,budgets,1,{},[&](auto&)->std::unique_ptr<Box>{++called;return {};});});require(called==0&&domain.used()==0,"missing module owner invoked factory");
  });
  run("capacity arithmetic cannot wrap",[]{
    ResourceDomain domain;std::array budgets{ResourceByteBudget(UINT64_MAX)};auto t=type();int destroyed=0;
    auto owner=ExternalResource::make(domain,t,budgets,UINT64_MAX,hostCode(),[&](auto&){return std::make_unique<Box>(0,destroyed);});
    require(budgets[0].used()==UINT64_MAX,"capacity counter narrowed");error("E_RESOURCE_BYTES",[&]{make(domain,t,budgets,1,destroyed);});owner.close();require(budgets[0].used()==0,"capacity arithmetic leaked charge");
  });
  run("moved accounting handles stay safely empty",[]{
    ResourceByteBudget previous(1);ResourceByteBudget current=std::move(previous);require(previous.used()==0&&previous.limit()==0&&current.limit()==1,"moved budget invalid");
    ResourceDomain domain;std::array budgets{previous};auto t=type();int destroyed=0;error("E_RESOURCE_BYTES",[&]{make(domain,t,budgets,1,destroyed);});
  });
  run("payload destruction reenters without registry locks",[]{
    ResourceDomain domain;std::array budgets{ResourceByteBudget(1)};auto t=type();int destroyed=0,nested=0;
    auto owner=ExternalResource::make(domain,t,budgets,1,hostCode(),[&](auto&){return std::make_unique<Box>(1,destroyed,[&]{auto other=make(domain,t,budgets,0,nested);other.close();});});
    owner.close();require(destroyed==1&&nested==1&&budgets[0].used()==0&&domain.used()==0,"reentrant cleanup failed");
  });
  run("concurrent close preserves admitted borrow",[]{
    ResourceDomain domain;std::array budgets{ResourceByteBudget(4)};auto t=type();int destroyed=0;auto owner=make(domain,t,budgets,4,destroyed);std::mutex mutex;std::condition_variable condition;bool ready=false,finish=false;
    std::thread worker([&]{auto lease=owner.borrow(t);auto *object=&lease.value(t);{std::unique_lock lock(mutex);ready=true;condition.notify_all();condition.wait(lock,[&]{return finish;});}object->bytes[0]=99;});
    {std::unique_lock lock(mutex);condition.wait(lock,[&]{return ready;});}owner.close();require(destroyed==0&&budgets[0].used()==4,"close raced physical storage");{std::lock_guard lock(mutex);finish=true;}condition.notify_all();worker.join();require(destroyed==1&&budgets[0].used()==0,"worker borrow did not settle");
  });
  run("real provider destructor precedes dlclose and quota release",[&]{
    ResourceDomain domain;std::array budgets{ResourceByteBudget(8)};moduleEvents.clear();bool orderOK=true;
    observeModule=[&](int){if(budgets[0].used()!=8||domain.used()!=1)orderOK=false;};
    void *image=dlopen(argv[1],RTLD_NOW|RTLD_LOCAL);require(image,"dlopen failed");auto pin=std::shared_ptr<void>(image,[](void *p){dlclose(p);});
    using Create=void*(*)(void(*)(int));using Destroy=void(*)(void*);auto create=reinterpret_cast<Create>(dlsym(image,"resource_fixture_create"));auto destroy=reinterpret_cast<Destroy>(dlsym(image,"resource_fixture_destroy"));require(create&&destroy,"missing plugin exports");
    ExternalResourceType<PluginBox> t("model::Session",std::string(64,'b'));
    auto owner=ExternalResource::make(domain,t,budgets,8,pin,[&](auto&){std::unique_ptr<void,Destroy> object(create(moduleEvent),destroy);require(bool(object),"plugin allocation failed");auto result=std::make_unique<PluginBox>(object.get(),destroy);object.release();return result;});pin.reset();auto lease=owner.borrow(t);owner.close();require(moduleEvents.empty(),"provider unloaded before borrow settled");lease={};
    require(orderOK&&moduleEvents==std::vector<int>({1,2})&&budgets[0].used()==0&&domain.used()==0,"provider unload/destruction/capacity order wrong");observeModule={};
  });
  std::cout<<"EXTERNAL RESOURCE CASES "<<cases<<std::endl;return 0;
}catch(const std::exception &e){std::cerr<<e.what()<<std::endl;return 1;}}
