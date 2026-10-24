#include "nex/task_reference.h"
#include "nex_external_resource.h"
#include <array>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <iostream>
#include <mutex>
#include <thread>

using namespace nex;
using namespace nexrt;
using namespace std::chrono_literals;
namespace {
void require(bool value,const char *message){if(!value)throw std::runtime_error(message);}
template<class F>void rejected(const char *code,F action){
  try{action();}catch(const DataError &e){require(e.code==code,"unexpected region error");return;}
  throw std::runtime_error(std::string("missing ")+code);
}
template<class F>void sourceRejected(const char *code,F action){
  try{action();}catch(const Error &e){if(e.code!=code)throw std::runtime_error(std::string("expected ")+code+", got "+e.code+": "+e.what());return;}
  throw std::runtime_error(std::string("missing ")+code);
}
struct Gate {
  std::mutex mutex;std::condition_variable changed;bool entered=false,released=false;
  void enter(){std::unique_lock lock(mutex);entered=true;changed.notify_all();changed.wait(lock,[&]{return released;});}
  bool wait(){std::unique_lock lock(mutex);return changed.wait_for(lock,5s,[&]{return entered;});}
  bool reached(){std::lock_guard lock(mutex);return entered;}
  void open(){{std::lock_guard lock(mutex);released=true;}changed.notify_all();}
};
struct Box {
  std::shared_ptr<std::atomic<int>> destroyed;
  std::shared_ptr<Gate> cleanup;
  int value=42;
  ~Box(){if(cleanup)cleanup->enter();++*destroyed;}
};
struct Host:TaskReferenceExternalHost {
  ResourceDomain physical{16};ResourceAccess access=physical.access();
  std::array<ResourceByteBudget,1> budgets{ResourceByteBudget(64)};
  ExternalResourceType<Box> key{"reference::Buffer",std::string(64,'c')};
  std::shared_ptr<std::atomic<int>> destroyed=std::make_shared<std::atomic<int>>(0);
  std::shared_ptr<ResourceExecutor> executor;
  std::vector<ExternalResource> aliases;
  std::vector<ResourceRegionAuthority> authorities;
  std::function<std::optional<TaskReferenceExternalRequest>(size_t,const ResourceRegionAuthority&)> action;
  std::function<void(size_t,const ResourceRegionAuthority&)> admission;
  std::atomic<size_t> retired{0};size_t legacy=0,prepared=0,admitted=0;
  Host(){resourceRegions=true;}
  std::optional<TaskReferenceExternalRequest> prepare(size_t,Span)override{++legacy;return {};}
  std::optional<TaskReferenceExternalRequest> prepareInRegion(size_t owner,Span,const ResourceRegionAuthority &authority)override{
    require(authority.family()==ResourceRegionFamily::Reference,"native authority reached independent reference scheduler");
    ++prepared;return action?action(owner,authority):std::nullopt;
  }
  void admitInRegion(size_t owner,const TaskExternalResult &,const ResourceRegionAuthority &authority)override{
    authority.check();++admitted;if(admission)admission(owner,authority);
  }
  void scopeRetired(size_t)noexcept override{++retired;}
  ExternalResource make(const ResourceRegionAuthority &authority,std::shared_ptr<Gate> cleanup={}){
    return ExternalResource::makeInRegion(access,authority,key,budgets,4,std::make_shared<int>(1),executor,
      [counter=destroyed,cleanup](const auto&){return std::unique_ptr<Box>(new Box{counter,cleanup});});
  }
  void empty(){require(physical.used()==0&&budgets[0].used()==0,"evaluation returned before physical quota release");}
};
struct Operation:TaskExternalOperation {
  std::shared_ptr<Gate> gate;
  ExternalResourceBorrow borrow;
  Operation(std::shared_ptr<Gate> gate,ExternalResourceBorrow borrow):gate(std::move(gate)),borrow(std::move(borrow)){}
  TaskExternalResult run(const TaskExternalControl &)override{gate->enter();return {};}
};
Program source(const std::string &body){auto p=parse("module reference_regions;\n"+body,"reference_regions.nex");check(p);return p;}
auto evaluate(const Program &p,Host &host,TaskReferenceObserver observer={},const TaskExecutionLimits *limits=nullptr){
  return evaluateTaskReference(p,"main",{},1000000,std::move(observer),limits,&host);
}
const std::string once="fn main()->i64 !{task}{task_yield();return 42;}";
const std::string scoped="fn main()->i64 !{task}{return with_tasks(1,fn(scope:task_scope)->i64 !{task}{task_yield();return 42;});}";
}
int main(){try{
 size_t cases=0;auto run=[&](const char *name,auto action){auto before=liveObjects.load();action();require(liveObjects.load()==before,"reference test leaked source values");++cases;std::cout<<"PASS "<<name<<std::endl;};
 run("ordinary hosts retain legacy yield hooks and allocate no resource graph",[]{
   Host host;host.resourceRegions=false;auto r=evaluate(source(once),host);
   require(r.value.scalar==42&&host.legacy==1&&host.prepared==0,"private opt-in changed ordinary host execution");host.empty();
 });
 run("root owners survive64 independent AST resumes and retire before return",[]{
   Host host;ResourceRegionAuthority root;
   host.action=[&](size_t,const auto &authority)->std::optional<TaskReferenceExternalRequest>{
     require(authority.depth()==0,"root has wrong logical depth");
     if(host.aliases.empty()){root=authority;host.aliases.push_back(host.make(authority));}
     if(host.prepared==1)host.resourceRegions=false; // Opt-in was captured before execution.
     require(host.aliases[0].borrowInRegion(authority,host.key).value(host.key).value==42,"owner expired across reference resume");return {};
   };
   auto r=evaluate(source("fn main()->i64 !{task}{var i:i64=0;while i<64{task_yield();i=i+1;}return 42;}"),host);
   require(r.value.scalar==42&&host.prepared==64&&*host.destroyed==1&&!host.aliases[0].isOpen(),"root resource did not retire");
   rejected("E_RESOURCE_SCOPE",[&]{root.check();});host.empty();
 });
 run("actual nested scopes admit ancestor borrows and fence their own resources",[]{
   Host host;size_t rootCalls=0;ResourceRegion foreign;
   host.action=[&](size_t,const auto &authority)->std::optional<TaskReferenceExternalRequest>{
     if(authority.depth()==0){
       if(rootCalls++==0){host.aliases.push_back(host.make(authority));host.authorities.push_back(authority);}
       else require(*host.destroyed==1&&!host.aliases[1].isOpen()&&host.aliases[0].isOpen()&&host.retired==1,"nested publication preceded cleanup or revoked parent");
     }else{
       require(authority.depth()==1&&host.authorities[0].contains(authority),"logical ancestry differs from AST scopes");
       require(host.aliases[0].borrowInRegion(authority,host.key).value(host.key).value==42,"ancestor borrow refused");
       host.aliases.push_back(host.make(authority));
       rejected("E_RESOURCE_SCOPE",[&]{host.aliases[1].borrowInRegion(host.authorities[0],host.key);});
       rejected("E_RESOURCE_SCOPE",[&]{host.aliases[1].borrowInRegion(foreign.authority(),host.key);});
     }return {};
   };
   auto p=source("fn main()->i64 !{task}{task_yield();let n:i64=with_tasks(1,fn(s:task_scope)->i64 !{task}{task_yield();return 42;});task_yield();return n;}");
   require(evaluate(p,host).value.scalar==42&&rootCalls==2&&*host.destroyed==2,"nested resource result changed");host.empty();
 });
 run("sibling and ended reference scope authority cannot borrow or construct",[]{
   Host host;size_t visits=0;
   host.action=[&](size_t,const auto &authority)->std::optional<TaskReferenceExternalRequest>{
     if(visits++==0){host.authorities.push_back(authority);host.aliases.push_back(host.make(authority));}
     else{
       rejected("E_RESOURCE_SCOPE",[&]{host.authorities[0].check();});
       rejected("E_RESOURCE_SCOPE",[&]{host.make(host.authorities[0]);});
       rejected("E_RESOURCE_SCOPE",[&]{host.aliases[0].borrowInRegion(authority,host.key);});
     }return {};
   };
   auto p=source("fn main()->i64 !{task}{let a:i64=with_tasks(1,fn(s:task_scope)->i64 !{task}{task_yield();return 40;});let b:i64=with_tasks(1,fn(s:task_scope)->i64 !{task}{task_yield();return 2;});return a+b;}");
   require(evaluate(p,host).value.scalar==42&&*host.destroyed==1&&host.retired==2,"sibling closure failed");host.empty();
 });
 run("checked child promotion retains alias identity until reference root closure",[]{
   Host host;ResourceRegionAuthority root;size_t roots=0;
   host.action=[&](size_t,const auto &authority)->std::optional<TaskReferenceExternalRequest>{
     if(authority.depth()==0){
       if(roots++==0)root=authority;
       else require(host.aliases[0].isOpen()&&*host.destroyed==0&&host.aliases[0].borrowInRegion(authority,host.key).value(host.key).value==42,"promoted owner failed parent continuation");
     }else{
       auto value=host.make(authority),alias=value;auto id=value.identity();value.promoteRegion(authority,root);
       require(alias.identity()==id&&value.identity()==id,"promotion replaced physical identity");host.aliases.push_back(alias);
     }return {};
   };
   auto p=source("fn main()->i64 !{task}{task_yield();let n:i64=with_tasks(1,fn(s:task_scope)->i64 !{task}{task_yield();return 42;});task_yield();return n;}");
   require(evaluate(p,host).value.scalar==42&&roots==2&&*host.destroyed==1&&!host.aliases[0].isOpen(),"root did not retire promoted alias");host.empty();
 });
 run("another AST job progresses while an owning executor destructor is blocked",[]{
   Host host;host.executor=std::make_shared<ResourceExecutor>();auto gate=std::make_shared<Gate>();bool progressed=false;
   host.action=[&](size_t owner,const auto &authority)->std::optional<TaskReferenceExternalRequest>{
     if(owner==1&&host.aliases.empty())host.aliases.push_back(host.make(authority,gate));return {};
   };
   auto p=source(R"(fn main()->i64 !{task}{return with_tasks(1,fn(scope:task_scope)->i64 !{task}{
     let slow:task<i64>=task_spawn(scope,fn()->i64 !{task}{return with_tasks(1,fn(inner:task_scope)->i64 !{task}{task_yield();return 40;});});
     let helper:task<i64>=task_spawn(scope,fn()->i64 !{task}{var i:i64=0;while i<128{task_yield();i=i+1;}return 2;});
     return task_wait(slow)+task_wait(helper);});})");
   auto r=evaluate(p,host,[&](size_t owner,const TaskTransition &transition){
     if(owner==2&&!progressed&&((transition.operation=="task_yield"&&gate->reached())||transition.kind==TaskTransition::Done)){
       require(gate->wait(),"executor cleanup did not start");
       progressed=*host.destroyed==0&&host.retired==0&&host.physical.used()==1&&host.budgets[0].used()==4;gate->open();
     }
   });
   gate->open();host.executor->finish();
   require(r.value.scalar==42&&progressed&&*host.destroyed==1&&host.retired==2,"physical cleanup blocked all AST jobs or early scope publication");host.empty();
 });
 for(bool deadline:{false,true})run(deadline?"timeout waits for full resource finalization":"root cancellation waits for full resource finalization",[&]{
   Host host;host.executor=std::make_shared<ResourceExecutor>();auto gate=std::make_shared<Gate>();std::stop_source stop;host.cancellation=stop.get_token();
   std::atomic<bool> returned=false,premature=false,arrived=false;
   host.action=[&](size_t,const auto &authority)->std::optional<TaskReferenceExternalRequest>{host.aliases.push_back(host.make(authority,gate));return {};};
   std::jthread release([&]{arrived=gate->wait();if(!deadline)stop.request_stop();std::this_thread::sleep_for(deadline?150ms:25ms);
     premature=returned.load()||*host.destroyed!=0||host.retired!=0;gate->open();});
   TaskExecutionLimits limits{1000000,100,1};
   sourceRejected(deadline?"E_TIMEOUT":"E_CANCELLED",[&]{evaluate(source(scoped),host,{},deadline?&limits:nullptr);});returned=true;
   release.join();host.executor->finish();require(arrived&&!premature&&host.retired==1&&*host.destroyed==1,"control failure bypassed physical resource fence");host.empty();
 });
 run("failed preparation retires already-created scoped host resources",[]{
   Host host;host.action=[&](size_t,const auto &authority)->std::optional<TaskReferenceExternalRequest>{host.aliases.push_back(host.make(authority));throw std::runtime_error("controlled host failure");};
   sourceRejected("E_TASK_HOST",[&]{evaluate(source(scoped),host);});
   require(*host.destroyed==1&&host.retired==1&&!host.aliases[0].isOpen(),"preparation error leaked scoped resource");host.empty();
 });
 run("unexpected observer failure still drains root resources before unwinding",[]{
   Host host;host.executor=std::make_shared<ResourceExecutor>();auto gate=std::make_shared<Gate>();std::atomic<bool> arrived=false,returned=false,premature=false;
   host.action=[&](size_t,const auto &authority)->std::optional<TaskReferenceExternalRequest>{host.aliases.push_back(host.make(authority,gate));return {};};
   std::jthread release([&]{arrived=gate->wait();std::this_thread::sleep_for(25ms);premature=returned.load()||*host.destroyed!=0;gate->open();});
   bool failed=false;try{evaluate(source(once),host,[&](size_t,const TaskTransition &t){if(t.kind==TaskTransition::Done)throw std::runtime_error("observer failure");});}
   catch(const std::runtime_error &e){failed=std::string(e.what())=="observer failure";}returned=true;
   release.join();host.executor->finish();require(failed&&arrived&&!premature&&*host.destroyed==1,"exception unwinding bypassed physical root fence");host.empty();
 });
 run("physical IO lease and resource executor both settle before cancelled scope exit",[]{
   Host host;host.executor=std::make_shared<ResourceExecutor>();auto work=std::make_shared<Gate>(),cleanup=std::make_shared<Gate>();std::stop_source stop;host.cancellation=stop.get_token();
   std::atomic<bool> returned=false,premature=false,arrived=false;
   host.action=[&](size_t,const auto &authority)->std::optional<TaskReferenceExternalRequest>{
     host.aliases.push_back(host.make(authority,cleanup));
     return TaskReferenceExternalRequest{std::make_shared<Operation>(work,host.aliases[0].borrowInRegion(authority,host.key)),0};
   };
   std::jthread release([&]{bool first=work->wait();stop.request_stop();std::this_thread::sleep_for(25ms);
     premature=returned.load()||host.retired!=0||*host.destroyed!=0;work->open();arrived=first&&cleanup->wait();
     std::this_thread::sleep_for(25ms);premature=premature.load()||returned.load()||host.retired!=0||*host.destroyed!=0;cleanup->open();});
   sourceRejected("E_CANCELLED",[&]{evaluate(source(scoped),host);});returned=true;
   release.join();host.executor->finish();require(arrived&&!premature&&host.admitted==0&&host.retired==1&&*host.destroyed==1,"scope confused IO retirement with resource finalization");host.empty();
 });
 run("successful unit host admission receives the same live reference scope",[]{
   Host host;auto gate=std::make_shared<Gate>();gate->open();ResourceRegionAuthority prepared;
   host.action=[&](size_t,const auto &authority)->std::optional<TaskReferenceExternalRequest>{
     prepared=authority;host.aliases.push_back(host.make(authority));
     return TaskReferenceExternalRequest{std::make_shared<Operation>(gate,host.aliases[0].borrowInRegion(authority,host.key)),0};
   };
   host.admission=[&](size_t,const auto &authority){require(prepared.contains(authority)&&authority.contains(prepared)&&host.aliases[0].isOpen(),"admission lost live owning authority");};
   auto r=evaluate(source(scoped),host);require(r.value.scalar==42&&host.admitted==1&&r.external.retired==1&&!r.external.pending&&*host.destroyed==1,"reference admission changed source unit result");host.empty();
 });
 run("direct and hidden source resource inputs remain rejected without revoking caller ownership",[]{
   for(bool nested:{false,true}){
     Host host;ResourceRegion caller(ResourceRegionFamily::Reference);auto owner=host.make(caller.authority());
     Value input(externalValue(owner));
     if(nested){auto aggregate=std::make_shared<Data>(Data::List);aggregate->values.push_back(input);input=Value(std::move(aggregate));}
     auto p=source("fn main(input:i64)->i64 !{task}{task_yield();return input;}");
     sourceRejected("E_TASK_VALUE",[&]{evaluateTaskReference(p,"main",{input},1000000,{},nullptr,&host);});
     require(owner.isOpen()&&host.prepared==0&&*host.destroyed==0,"rejected input was admitted or caller's region was revoked");
     caller.close();host.empty();require(*host.destroyed==1,"caller resource cleanup failed");
   }
 });
 std::cout<<"independent reference resource region cases="<<cases<<"\n";return 0;
}catch(const std::exception &e){std::cerr<<e.what()<<"\n";return 1;}}
