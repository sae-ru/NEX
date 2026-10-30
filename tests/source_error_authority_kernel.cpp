#include "nex_task_values.h"
#include <atomic>
#include <barrier>
#include <cstdio>
#include <map>
#include <mutex>
using namespace nexrt;
namespace {std::mutex allocationsMutex;std::map<const void*,int> allocations;const char *active="start";unsigned cases=0;}
extern "C" void nex_profile_unwind(){}
extern "C" void nex_profile_allocation(const void *p,size_t,int pool){std::lock_guard lock(allocationsMutex);if(!allocations.emplace(p,pool).second)std::abort();}
extern "C" void nex_profile_free(const void *p){std::lock_guard lock(allocationsMutex);if(allocations.erase(p)!=1)std::abort();}
namespace {
void require(bool value,const char *message){if(!value)throw Trap("E_TEST",std::string(active)+": "+message,0);}
const std::string key(64,'a');
NativeSourceException error(Value value){return {"TYPED","generic","{\"origin\":\"unchanged\"}",53,std::make_shared<const SourceErrorPayload>(key,std::move(value))};}
Value caught(const NativeSourceException &e){require(e.code=="TYPED"&&e.line==53&&e.source=="{\"origin\":\"unchanged\"}"&&bool(e.payload),"source metadata changed");return e.payload->get(key);}
struct Host;
struct Box {Host *host;explicit Box(Host *host):host(host){}~Box()noexcept;};
struct Host {
 ResourceDomain domain{16};ResourceByteBudget bytes{1024};ExternalResourceType<Box> type{"test::Source",key};
 std::shared_ptr<void> pin=std::make_shared<int>(0);std::atomic<unsigned> destroyed{0};TaskGroup *group=nullptr;std::barrier<> together{2};
 ExternalResource make(TaskGroup &g){group=&g;return ExternalResource::makeInRegion(domain.access(),g.resourceAuthority(),type,std::span(&bytes,1),8,pin,{},[&](const ResourcePermit &p){p.check();return std::make_unique<Box>(this);});}
};
Box::~Box()noexcept{if(host){if(host->group)(void)host->group->allowsSourceFiles();++host->destroyed;}}
TaskBody child(TaskGroup &group,Value mode,Value captures,const void *opaque){
 auto &host=*const_cast<Host*>(static_cast<const Host*>(opaque));
 if(mode.scalar==2)throw error(Value(externalValue(host.make(group))));
 if(mode.scalar==3){host.together.arrive_and_wait();throw Trap("E_ASSERT","produced child fatal",77);}
 auto value=captures;
 if(value.tag!=Value::Object||!value.object)value=taskChannelValue(group,group.channel(group.currentScope(),1),0);
 if(mode.scalar==4)host.together.arrive_and_wait();
 throw error(std::move(value));co_return Value();
}
TaskBody observed(TaskGroup &group,Value,Value,const void *opaque){
 auto scope=group.openScope(2);auto future=group.spawnWithContext(scope,child,opaque,{},{});Value first;
 for(int i=0;i<2;++i){Value value;try{(void)co_await group.await(future);}catch(const NativeSourceException &e){value=caught(e);}
  require(value.tag==Value::Object&&value.object&&value.object->kind==Data::Channel,"future lost its channel");
  if(i)require(value.object==first.object,"future error cloned its payload");else first=value;
 }
 auto channel=taskData(first,Data::Channel).channel;
 require((co_await group.send(channel,Value(42))).present,"source channel cannot send");
 require((co_await group.receive(channel)).value.scalar==42,"source channel changed contents");
 co_await group.leaveScope(scope);co_return Value(42);
}
TaskBody direct(TaskGroup &group,Value mode,Value,const void *opaque){
 auto &host=*const_cast<Host*>(static_cast<const Host*>(opaque));auto outer=group.openScope(2);
 auto shared=taskChannelValue(group,group.channel(outer,1),0);auto inner=group.openScope(2);
 bool expectedTrap=mode.scalar==1||mode.scalar==3;Value payload;ExternalResource resource;
 if(mode.scalar>=2){resource=host.make(group);payload=Value(externalValue(resource));
  if(mode.scalar==3){auto record=std::make_shared<Data>(Data::Record);record->values={taskScopeValue(group,inner),payload};payload=Value(record);}}
 else payload=mode.scalar==1?taskScopeValue(group,inner):shared;
 Value result;bool trapped=false;
 try{co_await group.leaveSourceExceptionScope(inner,std::make_exception_ptr(error(payload)));}
 catch(const NativeSourceException &e){result=caught(e);}
 catch(const Trap &e){require(e.code=="E_TASK_SCOPE","wrong source-transfer trap");trapped=true;}
 require(trapped==expectedTrap,"scope transfer accepted/lost an invalid payload");
 if(mode.scalar==2){auto value=externalResource(result.object);require(value.isOpen(),"source resource closed before handler");
  (void)value.borrowInRegion(group.resourceAuthority(),host.type);require(value.close(),"source resource failed to close");}
 if(mode.scalar==3)require(!resource.isOpen(),"mixed failed snapshot partially promoted a resource");
 if(mode.scalar==0)require(result.object==shared.object,"ancestor source payload changed identity");
 co_await group.leaveScope(outer);co_return Value(42);
}
TaskBody unobserved(TaskGroup &group,Value mode,Value,const void *opaque){
 auto &host=*const_cast<Host*>(static_cast<const Host*>(opaque));auto outer=group.openScope(2);
 auto shared=taskChannelValue(group,group.channel(outer,1),0);auto inner=group.openScope(2);
 group.spawnWithContext(inner,child,opaque,Value(mode.scalar==2?2:0),mode.scalar==0?shared:Value{});
 Value result;bool trapped=false;
 try{co_await group.leaveScope(inner);}catch(const NativeSourceException &e){result=caught(e);}
 catch(const Trap &e){require(e.code=="E_TASK_SCOPE","wrong unobserved source trap");trapped=true;}
 require(trapped==(mode.scalar==1),"implicit close lost source ownership validation");
 if(mode.scalar==0)require(result.object==shared.object,"implicit close lost ancestor payload");
 if(mode.scalar==2){auto value=externalResource(result.object);require(value.isOpen(),"unobserved source resource was retired early");
  (void)value.borrowInRegion(group.resourceAuthority(),host.type);require(value.close(),"unobserved resource close failed");}
 co_await group.leaveScope(outer);co_return Value(42);
}
TaskBody rootEscape(TaskGroup &group,Value,Value,const void*){auto scope=group.openScope(1);throw error(taskScopeValue(group,scope));co_return Value();}
TaskBody priority(TaskGroup &group,Value,Value,const void *opaque){
 auto scope=group.openScope(2);group.spawnWithContext(scope,child,opaque,Value(3),{});group.spawnWithContext(scope,child,opaque,Value(4),{});
 co_await group.leaveScope(scope);co_return Value();
}
TaskBody nested(TaskGroup &group,Value,Value,const void*){
 std::vector<TaskGroup::Scope> scopes;for(int i=0;i<100;++i)scopes.push_back(group.openScope(1));
 auto pending=std::make_exception_ptr(error(Value(42)));
 for(auto it=scopes.rbegin();it!=scopes.rend();++it){try{co_await group.leaveSourceExceptionScope(*it,pending);}catch(const NativeSourceException &e){require(caught(e).scalar==42,"nested source packet changed");pending=std::current_exception();}}
 co_return Value(42);
}
void empty(){require(liveObjects.load()==0,"managed source value survived teardown");std::lock_guard lock(allocationsMutex);require(allocations.empty(),"source allocations survived teardown");}
void run(const char *name,TaskGroup::ContextFactory factory,int mode,unsigned workers,bool resources=false,const char *trap=nullptr){
 active=name;Host host;bool raised=false;
 {RequestScope request(1000000,15000);TaskGroup group(workers,4096,{},false,true);if(resources)group.enableResourceRegions({},true,true);
  auto task=group.spawnWithContext(factory,&host,Value(mode),{});
  try{auto result=group.join(task);require(!trap&&result.scalar==42,"unexpected source-kernel result");group.finish();}
  catch(const Trap &e){if(!trap||e.code!=trap)throw std::runtime_error(std::string("unexpected ")+e.code+": "+e.what());if(e.code=="E_ASSERT")require(e.line==77,"fatal location changed");raised=true;}
 }
 host.group=nullptr;require(raised==bool(trap),"expected trap absent");
 require(host.domain.used()==0&&host.bytes.used()==0,"resource capacity survived source teardown");
 if(resources)require(host.destroyed==1,"source resource destroyed an incorrect number of times");empty();++cases;
}
}
int main(){try{
 for(unsigned workers:{1u,4u}){
  run("observed",observed,0,workers);run("ancestor",direct,0,workers);run("direct-invalid",direct,1,workers);
  run("direct-resource",direct,2,workers,true);run("atomic-mixed",direct,3,workers,true);
  run("implicit-ancestor",unobserved,0,workers);run("implicit-invalid",unobserved,1,workers);
  run("implicit-resource",unobserved,2,workers,true);run("root-escape",rootEscape,0,workers,false,"E_TASK_SCOPE");run("nested",nested,0,workers);
 }
 for(unsigned i=0;i<32;++i)run("fatal-priority",priority,0,4,false,"E_ASSERT");
 std::printf("{\"ok\":true,\"cases\":%u,\"source_prepare_outside_lock\":true,\"physical_retirement\":true}\n",cases);return 0;
}catch(const std::exception &e){std::fprintf(stderr,"%s: %s\n",active,e.what());return 1;}}
