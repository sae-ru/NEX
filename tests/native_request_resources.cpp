#include "nex_external_resource.h"
#include "nex_host.h"
#include "nex_tasks.h"
#include <array>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <iostream>
#include <optional>
#include <thread>
using namespace nexrt;
namespace {
void require(bool value,const char *message){if(!value)throw std::runtime_error(message);}
template<class F> void dataError(const char *code,F body){try{body();}catch(const DataError &e){require(e.code==code,"wrong resource error");return;}throw std::runtime_error(std::string("missing ")+code);}
template<class F> void trap(const char *code,F body){try{body();}catch(const Trap &e){require(e.code==code,"wrong task trap");return;}throw std::runtime_error(std::string("missing ")+code);}
struct Gate {
 std::mutex mutex;std::condition_variable changed;bool arrived=false,released=false;
 void enter(){std::unique_lock lock(mutex);arrived=true;changed.notify_all();changed.wait(lock,[&]{return released;});}
 void wait(){std::unique_lock lock(mutex);require(changed.wait_for(lock,std::chrono::seconds(5),[&]{return arrived;}),"native cleanup barrier missing");}
 bool reached(){std::lock_guard lock(mutex);return arrived;}
 void open(){{std::lock_guard lock(mutex);released=true;}changed.notify_all();}
};
struct Release {std::shared_ptr<Gate> gate;~Release(){if(gate)gate->open();}};
struct Box {
 std::shared_ptr<std::atomic<int>> destroyed;std::shared_ptr<Gate> cleanup;const int value=42;
 Box(std::shared_ptr<std::atomic<int>> destroyed,std::shared_ptr<Gate> cleanup):destroyed(std::move(destroyed)),cleanup(std::move(cleanup)){}
 ~Box()noexcept{if(cleanup)cleanup->enter();++*destroyed;}
};
enum Mode {Basic,Returned,Holding,Failing};
struct State {
 ResourceDomain physical{8};ResourceAccess access;
 std::array<ResourceByteBudget,1> budgets{ResourceByteBudget(32)};
 ExternalResourceType<Box> key{"task::RequestBuffer",std::string(64,'d')};
 std::shared_ptr<std::atomic<int>> destroyed=std::make_shared<std::atomic<int>>(0),pins=std::make_shared<std::atomic<int>>(0);
 std::shared_ptr<ResourceExecutor> executor=std::make_shared<ResourceExecutor>();std::shared_ptr<Gate> cleanup;
 ResourceRegionAuthority parent,groupRoot,actor;
 ExternalResource caller;std::optional<ExternalResource> output;TaskGroup::Ticket target;
 std::atomic<bool> created=false,allowComplete=false,awaiting=false,observed=false,helperRan=false,childEnded=false;
 Mode mode=Basic;
 explicit State(RequestScope &request):access(request.bindResources(physical).access()){}
 ExternalResource make(const ResourceRegionAuthority &authority,bool blocked=false){
  auto pin=std::shared_ptr<void>(new int(1),[pins=pins](void *p){delete static_cast<int*>(p);++*pins;});
  return ExternalResource::makeInRegion(access,authority,key,budgets,4,std::move(pin),executor,
    [destroyed=destroyed,gate=blocked?cleanup:nullptr](const auto&){return std::make_unique<Box>(destroyed,gate);});
 }
 void borrow(const ExternalResource &value,const ResourceRegionAuthority &authority){require(value.borrowInRegion(authority,key).value(key).value==42,"native resource data changed");}
 void settled(int count){require(*destroyed==count&&*pins==count&&physical.used()==0&&budgets[0].used()==0&&executor->stats().resources==0,"task published before payload/pin/quotas/cleanup slot settled");}
};
using Shared=std::shared_ptr<State>;
TaskBody producer(TaskGroup &group,Shared state){
 auto authority=group.resourceAuthority();state->actor=authority;
 if(state->groupRoot){require(state->groupRoot.contains(authority)&&!authority.contains(state->groupRoot),"task reused coordinator root authority");}
 if(state->caller.isOpen())state->borrow(state->caller,authority);
 auto owner=state->make(authority,bool(state->cleanup));state->output=owner;state->created=true;
 for(size_t i=0;i<64;++i){state->borrow(owner,group.resourceAuthority());if(state->caller.isOpen())state->borrow(state->caller,group.resourceAuthority());co_await group.yield();}
 if(state->mode==Holding)while(!state->allowComplete)co_await group.yield();
 if(state->mode==Returned)owner.promoteRegion(authority,state->parent);
 if(state->mode==Failing)throw Trap("E_DEVICE_TEST","native body failure",0);
 co_return Value(int64_t(42));
}
TaskBody producerFactory(TaskGroup &group,Value,Value,const void *context){return producer(group,*static_cast<const Shared*>(context));}
TaskBody observer(TaskGroup &group,Shared state){
 state->awaiting=true;auto result=co_await group.await(state->target);
 require(result.present&&result.value.scalar==42,"future lost native result");state->settled(1);state->observed=true;co_return Value(int64_t(42));
}
TaskBody observerFactory(TaskGroup &group,Value,Value,const void *context){return observer(group,*static_cast<const Shared*>(context));}
TaskBody releaser(TaskGroup &group,Shared state,bool cancel){
 while(!state->created)co_await group.yield();
 if(cancel)group.cancel(state->target);
 while(!state->cleanup->reached()||(!cancel&&!state->awaiting))co_await group.yield();
 require(!state->observed&&*state->destroyed==0&&*state->pins==0&&state->physical.used()==1&&state->budgets[0].used()==4&&state->executor->stats().resources==1,"physical cleanup was published early");
 // Exercise ordinary source-worker APIs while the owner's executor is blocked.
 auto scope=group.openScope(1);auto pipe=group.channel(0);group.close(pipe);co_await group.leaveScope(scope);
 state->helperRan=true;state->cleanup->open();co_return Value(int64_t(1));
}
TaskBody releaseFactory(TaskGroup &group,Value cancel,Value,const void *context){return releaser(group,*static_cast<const Shared*>(context),bool(cancel.scalar));}
TaskBody sibling(TaskGroup &group,Shared state){
 while(!state->created)co_await group.yield();auto authority=group.resourceAuthority();
 dataError("E_RESOURCE_SCOPE",[&]{state->borrow(state->output.value(),authority);});
 dataError("E_RESOURCE_SCOPE",[&]{state->output->promoteRegion(authority,state->parent);});
 state->allowComplete=true;co_return Value(int64_t(1));
}
TaskBody siblingFactory(TaskGroup &group,Value,Value,const void *context){return sibling(group,*static_cast<const Shared*>(context));}
TaskBody pure(TaskGroup &,Value,Value){co_return Value(int64_t(1));}
TaskBody heldPure(TaskGroup &group,Shared state){state->created=true;while(!state->allowComplete)co_await group.yield();co_return Value(int64_t(1));}
TaskBody heldPureFactory(TaskGroup &group,Value,Value,const void *context){return heldPure(group,*static_cast<const Shared*>(context));}
struct Chain {Shared state;size_t depth=1;};
TaskBody chainFactory(TaskGroup &,Value,Value,const void*);
TaskBody chain(TaskGroup &group,Chain context){
 auto scope=group.openScope(1);
 if(context.depth<256){Chain next{context.state,context.depth+1};auto child=group.spawnWithContext(chainFactory,&next);auto result=co_await group.await(child);require(result.value.scalar==42,"deep child result changed");}
 else{
  require(group.resourceAuthority().depth()==256,"task roots consumed source scope depth");trap("E_LIMIT",[&]{group.openScope(1);});
  Chain extra{context.state,257};trap("E_LIMIT",[&]{group.spawnWithContext(chainFactory,&extra);});
  auto owner=context.state->make(group.resourceAuthority());context.state->output=owner;
 }
 co_await group.leaveScope(scope);co_return Value(int64_t(42));
}
TaskBody chainFactory(TaskGroup &group,Value,Value,const void *context){return chain(group,*static_cast<const Chain*>(context));}
struct Ancestor {Shared state;TaskGroup::Scope outer;ResourceRegionAuthority caller;std::shared_ptr<std::optional<TaskGroup::Ticket>> late;};
TaskBody late(TaskGroup &group,Ancestor context){
 auto authority=group.resourceAuthority();require(!context.caller.contains(authority),"explicit ancestor spawn inherited caller job lifetime");
 auto owner=context.state->make(authority);context.state->output=owner;context.state->created=true;
 while(!context.state->childEnded)co_await group.yield();context.state->borrow(owner,group.resourceAuthority());co_return Value(int64_t(42));
}
TaskBody lateFactory(TaskGroup &group,Value,Value,const void *context){return late(group,*static_cast<const Ancestor*>(context));}
TaskBody descendant(TaskGroup &group,Ancestor context){
 context.caller=group.resourceAuthority();auto inner=group.openScope(1);
 *context.late=group.spawnWithContext(context.outer,lateFactory,&context);
 while(!context.state->created)co_await group.yield();co_await group.leaveScope(inner);co_return Value(int64_t(1));
}
TaskBody descendantFactory(TaskGroup &group,Value,Value,const void *context){return descendant(group,*static_cast<const Ancestor*>(context));}
TaskBody ancestor(TaskGroup &group,Shared state){
 auto outer=group.openScope(1);Ancestor context{state,outer,{},std::make_shared<std::optional<TaskGroup::Ticket>>()};
 auto child=group.spawnWithContext(descendantFactory,&context);auto first=co_await group.await(child);require(first.value.scalar==1,"ancestor child failed");state->childEnded=true;
 auto result=co_await group.await(context.late->value());require(result.value.scalar==42,"ancestor-spawned task failed");state->settled(1);
 co_await group.leaveScope(outer);co_return Value(int64_t(42));
}
TaskBody ancestorFactory(TaskGroup &group,Value,Value,const void *context){return ancestor(group,*static_cast<const Shared*>(context));}
void created(const Shared &state){auto deadline=std::chrono::steady_clock::now()+std::chrono::seconds(5);while(!state->created){require(std::chrono::steady_clock::now()<deadline,"native task never created resource");std::this_thread::yield();}}
}
int main(){try{
 size_t cases=0;auto run=[&](const char *name,auto body){body();++cases;std::cout<<"PASS "<<name<<std::endl;};
 run("unparented task join retires its own resources before group finish",[]{
  RequestScope request;auto state=std::make_shared<State>(request);TaskGroup group(4);group.enableResourceRegions();state->groupRoot=group.resourceAuthority();
  auto ticket=group.spawnWithContext(producerFactory,&state);require(group.join(ticket).scalar==42,"native result changed");require(!state->output->isOpen(),"task join left task owner open");state->settled(1);group.finish();state->executor->finish();
 });
 run("caller resource survives task completion and repeated attached groups",[]{
  RequestScope request;ResourceRegion parent(ResourceRegionFamily::Request);auto state=std::make_shared<State>(request);state->parent=parent.authority();state->caller=state->make(state->parent);
  for(size_t i=0;i<2;++i){TaskGroup group(2);group.enableResourceRegions(state->parent);state->groupRoot=group.resourceAuthority();require(group.join(group.spawnWithContext(producerFactory,&state)).scalar==42,"borrowed caller task failed");group.finish();state->borrow(state->caller,state->parent);require(*state->destroyed==int(i+1),"group retired caller ownership");}
  parent.close();state->executor->finish();state->settled(3);
 });
 run("explicit native return preserves identity beyond task and group",[]{
  RequestScope request;ResourceRegion parent(ResourceRegionFamily::Request);auto state=std::make_shared<State>(request);state->parent=parent.authority();state->mode=Returned;
  {TaskGroup group(2);group.enableResourceRegions(state->parent);state->groupRoot=group.resourceAuthority();require(group.join(group.spawnWithContext(producerFactory,&state)).scalar==42,"returned task failed");group.finish();}
  auto identity=state->output->identity();require(state->output->isOpen()&&*state->destroyed==0,"returned owner died with group");state->borrow(*state->output,state->parent);auto alias=*state->output;require(alias.identity()==identity,"return copied physical resource");
  parent.close();state->executor->finish();state->settled(1);
 });
 run("sibling tasks cannot borrow or return each other's local owners",[]{
  RequestScope request;ResourceRegion parent(ResourceRegionFamily::Request);auto state=std::make_shared<State>(request);state->parent=parent.authority();state->mode=Holding;
  TaskGroup group(1);group.enableResourceRegions(state->parent);auto ticket=group.spawnWithContext(producerFactory,&state);auto probe=group.spawnWithContext(siblingFactory,&state);require(group.join(probe).scalar==1&&group.join(ticket).scalar==42,"sibling authority test failed");state->settled(1);group.finish();parent.close();state->executor->finish();
 });
 run("future publication waits physical settlement while the only source worker runs",[]{
  RequestScope request;auto state=std::make_shared<State>(request);state->cleanup=std::make_shared<Gate>();TaskGroup group(1);Release release{state->cleanup};group.enableResourceRegions();
  state->target=group.spawnWithContext(producerFactory,&state);auto waiter=group.spawnWithContext(observerFactory,&state);auto helper=group.spawnWithContext(releaseFactory,&state);
  require(group.join(waiter).scalar==42&&group.join(helper).scalar==1&&state->observed&&state->helperRan,"task fence starved source worker or published early");state->settled(1);group.finish();state->executor->finish();
 });
 run("failed body reports only after its physical owner retirement",[]{
  RequestScope request;auto state=std::make_shared<State>(request);state->mode=Failing;TaskGroup group(2);group.enableResourceRegions();
  auto task=group.spawnWithContext(producerFactory,&state);trap("E_DEVICE_TEST",[&]{group.join(task);});state->settled(1);require(!state->output->isOpen(),"failure left local resource usable");group.finish();state->executor->finish();
 });
 run("individual cancellation parks cleanup without occupying the only source worker",[]{
  RequestScope request;auto state=std::make_shared<State>(request);state->mode=Holding;state->cleanup=std::make_shared<Gate>();TaskGroup group(1);Release release{state->cleanup};group.enableResourceRegions();
  state->target=group.spawnWithContext(producerFactory,&state);auto helper=group.spawnWithContext(releaseFactory,&state,Value(int64_t(1)));
  trap("E_CANCELLED",[&]{group.join(state->target);});require(group.join(helper).scalar==1&&state->helperRan,"cancelled task starved helper");state->settled(1);group.finish();state->executor->finish();
 });
 for(bool cancel:{true,false})run(cancel?"request cancellation preserves physical cleanup fence":"request deadline preserves physical cleanup fence",[&]{
  RequestScope request(1000000000,cancel?5000:200);auto state=std::make_shared<State>(request);state->mode=Holding;state->cleanup=std::make_shared<Gate>();TaskGroup group(1);Release release{state->cleanup};group.enableResourceRegions();
  auto task=group.spawnWithContext(producerFactory,&state);created(state);std::atomic<bool> returned=false,checked=false;
  std::jthread physical([&]{state->cleanup->wait();checked=!returned&&*state->destroyed==0&&state->physical.used()==1&&state->budgets[0].used()==4;state->cleanup->open();});
  if(cancel)request.cancel();trap(cancel?"E_CANCELLED":"E_TIMEOUT",[&]{group.join(task);});returned=true;physical.join();require(checked,"request error escaped physical fence");state->settled(1);state->executor->finish();
 });
 run("256 native task and scope nesting remain available together",[]{
  RequestScope request(1000000000,30000);auto state=std::make_shared<State>(request);TaskGroup group(4,300);group.enableResourceRegions();Chain context{state,1};
  require(group.join(group.spawnWithContext(chainFactory,&context)).scalar==42,"combined native ownership depth changed");state->settled(1);group.finish();state->executor->finish();
 });
 run("explicit ancestor scope spawn survives its caller task root",[]{
  RequestScope request;auto state=std::make_shared<State>(request);TaskGroup group(1);group.enableResourceRegions();require(group.join(group.spawnWithContext(ancestorFactory,&state)).scalar==42,"ancestor lifetime was shortened");state->settled(1);group.finish();state->executor->finish();
 });
 run("logical request closure preserves existing pure work and rejects new admission",[]{
  RequestScope request;ResourceRegion parent(ResourceRegionFamily::Request);auto state=std::make_shared<State>(request);TaskGroup group(1);group.enableResourceRegions(parent.authority());
  auto task=group.spawnWithContext(heldPureFactory,&state);created(state);parent.close();state->allowComplete=true;
  require(group.join(task).scalar==1,"logical resource closure cancelled existing pure source execution");
  trap("E_RESOURCE_SCOPE",[&]{group.spawn(pure);});group.finish();state->executor->finish();
 });
 run("resource free task roots keep large group admission independent of owner quota",[]{
  RequestScope request(1000000000,60000);ResourceRegion parent(ResourceRegionFamily::Request);TaskGroup group(4,65536);group.enableResourceRegions(parent.authority());
  TaskGroup::Ticket last;for(size_t i=0;i<2048;++i)last=group.spawn(pure);require(group.join(last).scalar==1,"empty task resources consumed owner slots");group.finish();parent.close();
 });
 std::cout<<"NATIVE REQUEST RESOURCE CASES "<<cases<<std::endl;return 0;
}catch(const std::exception &e){std::cerr<<e.what()<<std::endl;return 1;}}
