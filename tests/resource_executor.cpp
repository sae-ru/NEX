#include "nex_external_resource.h"
#include <array>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <dlfcn.h>
#include <iostream>
#include <mutex>
#include <thread>
#include <vector>

using namespace nexrt;
namespace {
void require(bool value,const char *message){if(!value)throw std::runtime_error(message);}
template<class F> void error(const char *code,F body){
  try{body();}catch(const DataError &e){require(e.code==code,"unexpected error code");return;}
  throw std::runtime_error(std::string("missing ")+code);
}
struct Gate {
  std::mutex mutex;std::condition_variable changed;bool arrived=false,released=false;
  void enter(){std::unique_lock lock(mutex);arrived=true;changed.notify_all();changed.wait(lock,[&]{return released;});}
  void wait(){std::unique_lock lock(mutex);require(changed.wait_for(lock,std::chrono::seconds(5),[&]{return arrived;}),"executor did not reach barrier");}
  void open(){{std::lock_guard lock(mutex);released=true;}changed.notify_all();}
  ~Gate(){open();}
};
struct Observation {
  std::mutex mutex;std::vector<int> events;std::vector<std::thread::id> threads;
  void record(int n){std::lock_guard lock(mutex);events.push_back(n);threads.push_back(std::this_thread::get_id());}
  std::vector<int> values(){std::lock_guard lock(mutex);return events;}
  bool sameThread(std::thread::id t){std::lock_guard lock(mutex);for(auto actual:threads)if(actual!=t)return false;return true;}
};
struct Box {
  std::shared_ptr<Observation> observed;std::shared_ptr<Gate> cleanup;
  explicit Box(std::shared_ptr<Observation> observed,std::shared_ptr<Gate> cleanup={}):observed(std::move(observed)),cleanup(std::move(cleanup)){this->observed->record(1);}
  ~Box()noexcept{observed->record(2);if(cleanup)cleanup->enter();observed->record(3);}
};
struct Operation:ResourceExecutionOperation {
  std::function<void(const ResourceExecutionControl&)> body;std::function<void()> done;
  Operation(std::function<void(const ResourceExecutionControl&)> body,std::function<void()> done={}):body(std::move(body)),done(std::move(done)){}
  void run(const ResourceExecutionControl &control)override{body(control);}
  ~Operation(){if(done)done();}
};
auto operation(std::function<void(const ResourceExecutionControl&)> f,std::function<void()> done={}){return std::make_unique<Operation>(std::move(f),std::move(done));}
auto hostCode(){return std::make_shared<int>(1);}
ExternalResourceType<Box> boxType(){return {"device::Buffer",std::string(64,'d')};}
template<class Budgets> ExternalResource make(const ResourceDomain &domain,const Budgets &budgets,
    const std::shared_ptr<ResourceExecutor> &executor,const ExternalResourceType<Box> &type,
    const std::shared_ptr<Observation> &observed,std::shared_ptr<Gate> cleanup={}){
  return ExternalResource::makeOnExecutor(domain,type,budgets,4,hostCode(),executor,
    [observed,cleanup](const auto&){return std::make_unique<Box>(observed,cleanup);});
}
std::shared_ptr<Observation> moduleObservation;
std::shared_ptr<Gate> moduleDestructor;
extern "C" void moduleEvent(int n){moduleObservation->record(n);if(n==1&&moduleDestructor)moduleDestructor->enter();}
struct PluginBox {
  void *pointer;void(*destroy)(void*);
  PluginBox(void *pointer,void(*destroy)(void*)):pointer(pointer),destroy(destroy){}
  ~PluginBox()noexcept{destroy(pointer);}
};
}
int main(int argc,char **argv){try{
  require(argc==2,"expected module path");size_t cases=0;
  auto run=[&](const char *name,auto body){body();++cases;std::cout<<"PASS "<<name<<std::endl;};
  run("bounded executor and missing operation refusals",[]{
    for(auto limits:std::vector<ResourceExecutorLimits>{{0,1,1},{4097,1,1},{1,0,1},{1,65,1},{1,1,0},{1,1,8388609}})
      error("E_RESOURCE_EXECUTOR_LIMIT",[&]{ResourceExecutor executor(limits);});
    ResourceExecutor executor;error("E_RESOURCE_EXECUTOR",[&]{executor.submit({});});
    error("E_RESOURCE_EXECUTOR",[]{ResourceExecution{}.wait();});executor.finish();
  });
  run("factory and payload destructor share the dedicated thread",[]{
    auto executor=std::make_shared<ResourceExecutor>();auto observed=std::make_shared<Observation>();
    ResourceDomain domain;std::array budgets{ResourceByteBudget(4)};auto type=boxType();
    auto resource=make(domain,budgets,executor,type,observed);std::thread::id worker;
    executor->invoke([&]{worker=std::this_thread::get_id();});require(worker!=std::this_thread::get_id(),"executor ran on caller");
    resource.close();executor->drain();require(observed->values()==std::vector<int>({1,2,3})&&observed->sameThread(worker),"thread-affine lifetime broken");
    require(domain.used()==0&&budgets[0].used()==0&&executor->stats().resources==0,"settled cleanup retained quota");executor->finish();
  });
  run("queued cleanup retains both physical quotas until destructor returns",[]{
    auto executor=std::make_shared<ResourceExecutor>();auto observed=std::make_shared<Observation>();auto cleanup=std::make_shared<Gate>();
    ResourceDomain domain(1);std::array budgets{ResourceByteBudget(4)};auto type=boxType();auto resource=make(domain,budgets,executor,type,observed,cleanup);
    require(resource.close()&&!resource.close()&&!resource.isOpen(),"close was not shared");cleanup->wait();
    require(domain.used()==1&&budgets[0].used()==4&&executor->stats().resources==1,"cleanup scheduling returned physical quota early");
    error("E_RESOURCE_CLOSED",[&]{resource.borrow(type);});cleanup->open();executor->drain();
    require(domain.used()==0&&budgets[0].used()==0,"physical cleanup did not release quotas");executor->finish();
  });
  run("cleanup admission is reserved before entering a factory",[]{
    auto executor=std::make_shared<ResourceExecutor>(ResourceExecutorLimits{1,2,8});ResourceDomain domain(2);
    std::array budgets{ResourceByteBudget(8)};auto type=boxType();auto observed=std::make_shared<Observation>();auto resource=make(domain,budgets,executor,type,observed);
    std::atomic<int> called=0;
    error("E_RESOURCE_EXECUTOR_LIMIT",[&]{ExternalResource::makeOnExecutor(domain,type,budgets,4,hostCode(),executor,[&](const auto&){++called;return std::make_unique<Box>(observed);});});
    require(called==0&&domain.used()==1&&budgets[0].used()==4,"failed executor admission entered factory or leaked quota");resource.close();executor->finish();
  });
  run("failed factory leaves no cleanup reservation",[]{
    auto executor=std::make_shared<ResourceExecutor>(ResourceExecutorLimits{1,1,4});ResourceDomain domain(1);std::array budgets{ResourceByteBudget(4)};auto type=boxType();
    error("E_DEVICE_TEST",[&]{ExternalResource::makeOnExecutor(domain,type,budgets,4,hostCode(),executor,[](const auto&)->std::unique_ptr<Box>{throw DataError("E_DEVICE_TEST","factory failed");});});
    require(domain.used()==0&&budgets[0].used()==0&&executor->stats().resources==0,"failed factory leaked reservation");
    auto observed=std::make_shared<Observation>();auto resource=make(domain,budgets,executor,type,observed);resource.close();executor->finish();
  });
  run("null and closed executor refuse construction before factory",[]{
    ResourceDomain domain;std::array budgets{ResourceByteBudget(4)};auto type=boxType();std::atomic<int> called=0;
    auto factory=[&](const auto&)->std::unique_ptr<Box>{++called;return {};};
    error("E_RESOURCE_EXECUTOR",[&]{ExternalResource::makeOnExecutor(domain,type,budgets,4,hostCode(),{},factory);});
    auto executor=std::make_shared<ResourceExecutor>();executor->close();
    error("E_RESOURCE_EXECUTOR",[&]{ExternalResource::makeOnExecutor(domain,type,budgets,4,hostCode(),executor,factory);});
    require(called==0&&domain.used()==0&&budgets[0].used()==0,"refused executor entered factory");executor->finish();
  });
  run("queued cancellation never starts its operation",[]{
    ResourceExecutor executor({1,2,8});auto gate=std::make_shared<Gate>();std::atomic<int> started=0,destroyed=0;
    auto first=executor.submit(operation([gate](const auto&){gate->enter();}));gate->wait();
    auto cancelled=executor.submit(operation([&](const auto&){++started;},[&]{++destroyed;}),8);cancelled.cancel();
    require(!cancelled.ready()&&executor.stats().reservedBytes==8,"queued cancellation returned quota early");
    gate->open();first.wait();error("E_CANCELLED",[&]{cancelled.wait();});require(started==0&&destroyed==1&&executor.stats().reservedBytes==0,"queued cancel ran or leaked storage");executor.finish();
  });
  run("running cancel waits physical fence and releases borrow on executor",[]{
    auto executor=std::make_shared<ResourceExecutor>();auto observed=std::make_shared<Observation>();auto gate=std::make_shared<Gate>();
    ResourceDomain domain(1);std::array budgets{ResourceByteBudget(4)};auto type=boxType();auto resource=make(domain,budgets,executor,type,observed);auto borrow=resource.borrow(type);
    Box *pointer=nullptr;executor->invoke([&]{pointer=&borrow.value(type);});
    auto ticket=executor->submit(operation([borrow,pointer,gate](const auto &control){borrow.check();gate->enter();pointer->observed->record(4);control.checkpoint();}),4);
    gate->wait();borrow={};resource.close();ticket.cancel();
    require(!ticket.ready()&&budgets[0].used()==4&&domain.used()==1&&executor->stats().reservedBytes==4,"cancel or close released an in-flight resource");
    gate->open();error("E_CANCELLED",[&]{ticket.wait();});executor->drain();
    require(observed->values()==std::vector<int>({1,4,2,3})&&budgets[0].used()==0&&domain.used()==0,"physical fence/borrow/cleanup order broken");executor->finish();
  });
  run("operation exceptions settle destructor before publication",[]{
    ResourceExecutor executor;std::atomic<bool> destroyed=false;
    auto ticket=executor.submit(operation([](const auto&){throw DataError("E_DEVICE_TEST","settled failure");},[&]{destroyed=true;}),32);
    error("E_DEVICE_TEST",[&]{ticket.wait();});require(destroyed&&ticket.ready()&&executor.stats().reservedBytes==0,"failure published before destruction");executor.finish();
  });
  run("completed result cannot be changed by a later cancellation",[]{
    ResourceExecutor executor;auto ticket=executor.submit(operation([](const auto&){}));ticket.wait();ticket.cancel();ticket.wait();executor.finish();
  });
  run("cancelled operation destructor settles before capacity is returned",[]{
    ResourceExecutor executor({1,2,8});auto running=std::make_shared<Gate>();auto destroying=std::make_shared<Gate>();std::atomic<int> started=0;
    auto first=executor.submit(operation([running](const auto&){running->enter();}));running->wait();
    auto second=executor.submit(operation([&](const auto&){++started;},[destroying]{destroying->enter();}),8);second.cancel();running->open();first.wait();destroying->wait();
    require(!second.ready()&&executor.stats().reservedBytes==8,"cancelled operation destructor released storage early");destroying->open();error("E_CANCELLED",[&]{second.wait();});
    require(started==0&&executor.stats().reservedBytes==0,"cancelled destructor did not settle");executor.finish();
  });
  run("bounded operation slots and bytes cannot over-admit",[]{
    ResourceExecutor executor({1,2,4});auto gate=std::make_shared<Gate>();auto first=executor.submit(operation([gate](const auto&){gate->enter();}),4);gate->wait();
    error("E_RESOURCE_EXECUTOR_LIMIT",[&]{executor.submit(operation([](const auto&){}),1);});
    auto second=executor.submit(operation([](const auto&){}));error("E_RESOURCE_EXECUTOR_LIMIT",[&]{executor.submit(operation([](const auto&){}));});
    gate->open();first.wait();second.wait();executor.finish();
  });
  run("domain revoke schedules idle cleanup on the owning executor",[]{
    auto executor=std::make_shared<ResourceExecutor>();ResourceDomain domain;std::array budgets{ResourceByteBudget(4)};auto type=boxType();auto observed=std::make_shared<Observation>();
    auto owner=make(domain,budgets,executor,type,observed);domain.revoke();require(!owner.isOpen(),"domain revoke left owner open");executor->drain();
    require(observed->values()==std::vector<int>({1,2,3})&&budgets[0].used()==0,"domain revoke failed physical cleanup");executor->finish();
  });
  run("revocation during construction retires unpublished payload on executor",[]{
    auto executor=std::make_shared<ResourceExecutor>();ResourceDomain domain;std::array budgets{ResourceByteBudget(4)};auto type=boxType();auto observed=std::make_shared<Observation>();std::thread::id worker;
    executor->invoke([&]{worker=std::this_thread::get_id();});
    error("E_RESOURCE_SCOPE",[&]{ExternalResource::makeOnExecutor(domain,type,budgets,4,hostCode(),executor,[&](const auto&){auto value=std::make_unique<Box>(observed);domain.revoke();return value;});});
    executor->drain();require(observed->values()==std::vector<int>({1,2,3})&&observed->sameThread(worker)&&domain.used()==0&&budgets[0].used()==0,"unpublished owner escaped executor cleanup");executor->finish();
  });
  run("executor close still accepts every pre-reserved finalizer",[]{
    auto executor=std::make_shared<ResourceExecutor>();ResourceDomain domain;std::array budgets{ResourceByteBudget(4)};auto type=boxType();auto observed=std::make_shared<Observation>();
    auto owner=make(domain,budgets,executor,type,observed);auto borrow=owner.borrow(type);executor->close();owner.close();
    error("E_RESOURCE_EXECUTOR",[&]{executor->submit(operation([](const auto&){}));});borrow={};executor->finish();
    require(observed->values()==std::vector<int>({1,2,3})&&domain.used()==0&&budgets[0].used()==0,"executor close lost reserved finalizer");
  });
  run("reentrant operations run inline and own-thread waits are rejected",[]{
    ResourceExecutor executor;std::atomic<int> result=0;
    executor.invoke([&]{executor.invoke([&]{result=42;});error("E_RESOURCE_EXECUTOR",[&]{executor.drain();});error("E_RESOURCE_EXECUTOR",[&]{executor.finish();});});
    require(result==42,"reentrant invoke did not run inline");executor.finish();
  });
  run("closed executor rejects new inline invocation",[]{
    ResourceExecutor executor;std::atomic<int> called=0;
    executor.invoke([&]{executor.close();error("E_RESOURCE_EXECUTOR",[&]{executor.invoke([&]{++called;});});});
    require(called==0,"closed executor admitted inline work");executor.finish();
  });
  run("concurrent closes preserve one physical destructor",[]{
    auto executor=std::make_shared<ResourceExecutor>();ResourceDomain domain;std::array budgets{ResourceByteBudget(4)};auto type=boxType();auto observed=std::make_shared<Observation>();auto owner=make(domain,budgets,executor,type,observed);std::atomic<int> closed=0;
    std::vector<std::thread> threads;for(size_t i=0;i<16;++i)threads.emplace_back([&]{if(owner.close())++closed;});for(auto &thread:threads)thread.join();executor->finish();
    require(closed==1&&observed->values()==std::vector<int>({1,2,3})&&budgets[0].used()==0&&domain.used()==0,"concurrent close duplicated physical cleanup");
  });
  for(int unknown:{0,1})run(unknown?"unknown module exception is destroyed before unload":"typed module exception is copied before unload",[&]{
    ResourceExecutor executor;moduleObservation=std::make_shared<Observation>();
    void *image=dlopen(argv[1],RTLD_NOW|RTLD_LOCAL);require(image,"module exception dlopen failed");auto pin=std::shared_ptr<void>(image,[](void *p){dlclose(p);});
    auto callback=reinterpret_cast<void(*)(void(*)(int))>(dlsym(image,"resource_executor_callback"));auto thrower=reinterpret_cast<void(*)(int)>(dlsym(image,"resource_executor_throw"));require(callback&&thrower,"missing module exception exports");callback(moduleEvent);
    auto gate=std::make_shared<Gate>();auto ticket=executor.submit(operation([pin,thrower,unknown,gate](const auto&){gate->enter();thrower(unknown);}));gate->wait();pin.reset();gate->open();
    error(unknown?"E_RUNTIME":"E_DEVICE_TEST",[&]{ticket.wait();});executor.finish();
    require(moduleObservation->values()==std::vector<int>({3,2}),"module exception outlived its physical code pin");moduleObservation.reset();
  });
  run("real module destructor and unload precede quota return on executor",[&]{
    auto executor=std::make_shared<ResourceExecutor>();ResourceDomain domain;std::array budgets{ResourceByteBudget(8)};
    moduleObservation=std::make_shared<Observation>();moduleDestructor=std::make_shared<Gate>();
    void *image=dlopen(argv[1],RTLD_NOW|RTLD_LOCAL);require(image,"failed loading actual module");
    auto pin=std::shared_ptr<void>(image,[](void *p){dlclose(p);});
    using Create=void*(*)(void(*)(int));using Destroy=void(*)(void*);
    auto create=reinterpret_cast<Create>(dlsym(image,"resource_fixture_create"));auto destroy=reinterpret_cast<Destroy>(dlsym(image,"resource_fixture_destroy"));require(create&&destroy,"missing actual module exports");
    ExternalResourceType<PluginBox> type("device::Session",std::string(64,'e'));
    auto owner=ExternalResource::makeOnExecutor(domain,type,budgets,8,pin,executor,[&](const auto&){return std::make_unique<PluginBox>(create(moduleEvent),destroy);});
    pin.reset();std::thread::id worker;executor->invoke([&]{worker=std::this_thread::get_id();});owner.close();moduleDestructor->wait();
    require(moduleObservation->values()==std::vector<int>({1})&&budgets[0].used()==8&&domain.used()==1,"module code or quota released while destructor was running");
    moduleDestructor->open();executor->finish();require(moduleObservation->values()==std::vector<int>({1,2})&&moduleObservation->sameThread(worker)&&budgets[0].used()==0&&domain.used()==0,"module unload/cleanup quota order broken");
    moduleDestructor.reset();moduleObservation.reset();
  });
  std::cout<<"RESOURCE EXECUTOR CASES "<<cases<<std::endl;return 0;
}catch(const std::exception &e){std::cerr<<e.what()<<std::endl;return 1;}}
