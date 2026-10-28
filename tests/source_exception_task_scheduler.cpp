#include "nex_tasks.h"
#include "nex_task_protocol.h"
#include <barrier>
#include <chrono>
#include <cstdio>
#include <thread>
#include <mutex>
#include <map>
using namespace nexrt;
namespace {std::mutex allocationsMutex;std::map<const void*,int> allocations;}
extern "C" void nex_profile_unwind(){}
extern "C" void nex_profile_allocation(const void *p,size_t,int pool){std::lock_guard lock(allocationsMutex);if(!allocations.emplace(p,pool).second)std::abort();}
extern "C" void nex_profile_free(const void *p){std::lock_guard lock(allocationsMutex);if(allocations.erase(p)!=1)std::abort();}
namespace {
unsigned cases=0;
struct Context {std::barrier<> together{2};std::atomic<unsigned> ended{0};RequestScope *request=nullptr;};
struct Guard {Context &context;Value retained{string("owned")};~Guard(){++context.ended;}};
void require(bool yes,const char *message){if(!yes)throw std::runtime_error(message);}
NativeSourceException error(const char *code){return {code,std::string("λ\0message",10),"{\"site\":\"original\"}",47};}
TaskBody source(TaskGroup &group,Value,Value,const void *opaque){auto &ctx=*const_cast<Context*>(static_cast<const Context*>(opaque));Guard guard{ctx};co_await group.yield();throw error("SOURCE");co_return Value();}
TaskBody parked(TaskGroup &group,Value,Value,const void *opaque){auto &ctx=*const_cast<Context*>(static_cast<const Context*>(opaque));Guard guard{ctx};for(;;)co_await group.yield();}
TaskBody synchronizedFailure(TaskGroup &,Value kind,Value,const void *opaque){auto &ctx=*const_cast<Context*>(static_cast<const Context*>(opaque));Guard guard{ctx};ctx.together.arrive_and_wait();if(kind.scalar)throw Trap("E_ASSERT","produced before cleanup",12);throw error("SOURCE");co_return Value();}
TaskBody waits(TaskGroup &group,Value,Value,const void *opaque){
  auto scope=group.openScope(2);auto child=group.spawnWithContext(scope,source,opaque,{},{});unsigned caught=0;
  try{co_await group.await(child);}catch(const NativeSourceException &e){require(e.code=="SOURCE"&&e.line==47&&e.message.size()==10,"wait payload changed");++caught;}
  try{co_await group.await(child);}catch(const NativeSourceException &e){require(e.code=="SOURCE","repeated wait payload changed");++caught;}
  co_await group.leaveScope(scope);require(caught==2,"observed future was lost/redelivered at close");co_return Value(42);
}
TaskBody closeSource(TaskGroup &group,Value body,Value,const void *opaque){
  auto scope=group.openScope(2);group.spawnWithContext(scope,source,opaque,{},{});group.spawnWithContext(scope,parked,opaque,{},{});
  bool caught=false;
  try{if(body.scalar)co_await group.leaveSourceExceptionScope(scope,std::make_exception_ptr(error("BODY")));else co_await group.leaveScope(scope);}
  catch(const NativeSourceException &e){require(e.code==(body.scalar?"BODY":"SOURCE"),"body/child source priority changed");caught=true;}
  require(caught,"group swallowed its source error");co_return Value(42);
}
TaskBody runtimePriority(TaskGroup &group,Value,Value,const void *opaque){
  auto scope=group.openScope(2);group.spawnWithContext(scope,synchronizedFailure,opaque,Value(0),{});group.spawnWithContext(scope,synchronizedFailure,opaque,Value(1),{});
  co_await group.leaveScope(scope);co_return Value(0);
}
TaskBody controlPriority(TaskGroup &,Value deadline,Value,const void *opaque){
  auto &ctx=*const_cast<Context*>(static_cast<const Context*>(opaque));Guard guard{ctx};
  if(deadline.scalar)std::this_thread::sleep_for(std::chrono::milliseconds(600));else ctx.request->cancel();
  throw error("SOURCE");co_return Value();
}
TaskBody childFatal(TaskGroup &,Value kind,Value,const void *opaque){
  auto &ctx=*const_cast<Context*>(static_cast<const Context*>(opaque));Guard guard{ctx};
  const char *code=kind.scalar==0?"E_MEMORY":kind.scalar==1?"E_LIMIT":"E_TIMEOUT";
  throw Trap(code,"canonical child resource failure",47);co_return Value();
}
TaskBody blockedOwner(TaskGroup &group,Value kind,Value,const void *opaque){
  auto &ctx=*const_cast<Context*>(static_cast<const Context*>(opaque));Guard guard{ctx};
  auto scope=group.openScope(2);auto pipe=group.channel(scope,0);
  group.spawnWithContext(scope,childFatal,opaque,kind,{});
  (void)co_await group.receive(pipe);co_return Value(0);
}
TaskBody implicitBody(TaskGroup &group,Value,Value,const void *opaque){
  auto &ctx=*const_cast<Context*>(static_cast<const Context*>(opaque));Guard guard{ctx};
  auto scope=group.openScope(2);group.spawnWithContext(scope,synchronizedFailure,opaque,Value(1),{});
  ctx.together.arrive_and_wait();throw error("IMPLICIT_BODY");co_return Value();
}
TaskBody labeledSource(TaskGroup &,Value,Value,const void *opaque){auto &ctx=*const_cast<Context*>(static_cast<const Context*>(opaque));Guard guard{ctx};throw error("E_MEMORY");co_return Value();}
TaskBody recoverLabel(TaskGroup &group,Value,Value,const void *opaque){
  auto scope=group.openScope(1);auto child=group.spawnWithContext(scope,labeledSource,opaque,{},{});bool caught=false;
  try{co_await group.await(child);}catch(const NativeSourceException &e){caught=e.code=="E_MEMORY";}
  require(caught,"source code was classified as fatal runtime control");co_await group.leaveScope(scope);co_return Value(42);
}
}
int main(int argc,char **argv){try{
  bool implicitOnly=argc==2&&std::string(argv[1])=="implicit";
  auto baseline=liveObjects.load();
  require(validTaskCodeRequirements(taskCodeExceptionPrototypeABI,taskCodeDeclaredTask|taskCodeDeclaredThrow),"private task ABI rejected");
  require(validTaskCodeRequirements(taskCodeExceptionHostPrototypeABI,taskCodeStreamRequirementsMask|taskCodeDeclaredThrow)&&
          !validTaskCodeRequirements(taskCodeExceptionHostPrototypeABI,8192)&&
          !validTaskCodeRequirements(taskCodeExceptionHostPrototypeABI,-1),"private host ABI requirements changed");
  require(sourceExceptionTaskABI(taskCodeExceptionPrototypeABI)&&sourceExceptionTaskABI(taskCodeExceptionHostPrototypeABI)&&
          !sourceExceptionTaskABI(taskCodeStreamABI)&&fileStreamTaskABI(taskCodeExceptionHostPrototypeABI)&&
          !fileStreamTaskABI(taskCodeExceptionPrototypeABI),"private host/source execution modes overlap");
  require(!validTaskCodeRequirements(taskCodeStreamABI,taskCodeDeclaredThrow)&&!validTaskCodeRequirements(taskCodeExceptionPrototypeABI,taskCodeDeclaredFs),"retained/private descriptor requirements overlap");++cases;
  for(auto fn:{waits,closeSource})for(int body=0;body<(fn==closeSource?2:1);++body){
    Context ctx;{RequestScope request(1000000,10000);TaskGroup group(4,4096,{},false,true);auto root=group.spawnWithContext(fn,&ctx,Value(body),{});auto result=group.join(root);group.finish();require(result.scalar==42,"source recovery result changed");}
    require(liveObjects.load()==baseline&&(ctx.ended>0||body),"source recovery did not physically retire values");++cases;
  }
  for(unsigned repetition=0;repetition<32;++repetition){Context ctx;bool trapped=false;
    {RequestScope request(1000000,10000);TaskGroup group(4,4096,{},false,true);auto root=group.spawnWithContext(runtimePriority,&ctx,{},{});try{group.join(root);}catch(const Trap &e){require(e.code=="E_ASSERT","runtime failure lost to source/cleanup cancellation");trapped=true;}}
    require(trapped&&ctx.ended==2&&liveObjects.load()==baseline,"produced-failure drain/retirement was incomplete");
  }++cases;
  for(int deadline=0;deadline<2;++deadline){Context ctx;bool trapped=false;
    {RequestScope request(1000000,deadline?500:10000);ctx.request=&request;TaskGroup group(2,4096,{},false,true);auto root=group.spawnWithContext(controlPriority,&ctx,Value(deadline),{});try{group.join(root);}catch(const Trap &e){require(e.code==(deadline?"E_TIMEOUT":"E_CANCELLED"),"parent control lost to source payload");trapped=true;}}
    require(trapped&&ctx.ended==1&&liveObjects.load()==baseline,"control outcome published before retirement");++cases;
  }
  if(!implicitOnly)for(int kind=0;kind<3;++kind){Context ctx;bool trapped=false;
    {RequestScope request(1000000,500);TaskGroup group(4,4096,{},false,true);auto root=group.spawnWithContext(blockedOwner,&ctx,Value(kind),{});
      try{group.join(root);}catch(const Trap &e){require(e.code==(kind==0?"E_MEMORY":kind==1?"E_LIMIT":"E_TIMEOUT")&&e.line==47&&std::string(e.what())=="canonical child resource failure","unobserved fatal child did not interrupt blocked owner with its original error");trapped=true;}}
    require(trapped&&ctx.ended==2&&liveObjects.load()==baseline,"fatal child/blocked owner were not physically retired");++cases;
  }
  for(unsigned repetition=0;repetition<32;++repetition){Context ctx;bool trapped=false;
    {RequestScope request(1000000,10000);TaskGroup group(4,4096,{},false,true);auto root=group.spawnWithContext(implicitBody,&ctx,{},{});
      try{group.join(root);}catch(const Trap &e){require(e.code=="E_ASSERT","implicit body cleanup lost child runtime priority");trapped=true;}}
    require(trapped&&ctx.ended==2&&liveObjects.load()==baseline,"implicit source exit did not join owned scopes");
  }++cases;
  {Context ctx;{RequestScope request(1000000,10000);TaskGroup group(2,4096,{},false,true);auto root=group.spawnWithContext(recoverLabel,&ctx,{},{});require(group.join(root).scalar==42,"source data label interrupted root");group.finish();}require(liveObjects.load()==baseline&&ctx.ended==1,"source label recovery retained values");++cases;}
  {std::lock_guard lock(allocationsMutex);require(allocations.empty(),"scheduler retained tracked allocations");}
  std::printf("{\"ok\":true,\"cases\":%u,\"runtime_priority_repetitions\":32,\"implicit_priority_repetitions\":32,\"global_fatal_cases\":3,\"physical_workers\":true}\n",cases);return 0;
}catch(const NativeSourceException &e){std::fprintf(stderr,"native source scheduler: unexpected source outcome %s\n",e.code.c_str());return 1;}
catch(const std::exception &e){std::fprintf(stderr,"native source scheduler: %s\n",e.what());return 1;}}
