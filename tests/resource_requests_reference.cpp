#include "resource_regions_reference_helpers.h"
namespace {
const std::string waited=R"(fn main()->i64 !{task}{return with_tasks(1,fn(scope:task_scope)->i64 !{task}{
 let child:task<i64>=task_spawn(scope,fn()->i64 !{task}{task_yield();return 42;});
 let value:i64=task_wait(child);task_yield();return value;});})";
const std::string helped=R"(fn main()->i64 !{task}{return with_tasks(1,fn(scope:task_scope)->i64 !{task}{
 let child:task<i64>=task_spawn(scope,fn()->i64 !{task}{task_yield();return 40;});
 let helper:task<i64>=task_spawn(scope,fn()->i64 !{task}{var i:i64=0;while i<128{task_yield();i=i+1;}return 2;});
 let value:i64=task_wait(child);task_yield();return value+task_wait(helper);});})";
void settled(Host &host,int count){host.empty();require(*host.destroyed==count&&*host.pins==count&&(!host.executor||host.executor->stats().resources==0),"AST completion preceded payload/pin/executor slot settlement");}
}
int main(){try{
 size_t cases=0;auto run=[&](const char *name,auto action){auto before=liveObjects.load();action();require(liveObjects.load()==before,"reference request test leaked source values");++cases;std::cout<<"PASS "<<name<<std::endl;};
 run("legacy hosts ignore request ancestry when resource opt-in is disabled",[]{
  Host host;ResourceRegion foreign;host.resourceRegions=false;host.resourceRequestParent=foreign.authority();
  require(evaluate(source(once),host).value.scalar==42&&host.legacy==1&&host.prepared==0,"legacy host admitted resource authority");host.empty();
 });
 run("reference task groups require genuine live request ancestry",[]{
  Host host;ResourceRegion foreign;host.resourceRequestParent=foreign.authority();auto caller=host.make(foreign.authority());
  sourceRejected("E_RESOURCE_SCOPE",[&]{evaluate(source(once),host);});require(caller.isOpen()&&host.prepared==0,"wrong parent revoked caller resource");foreign.close();settled(host,1);
  ResourceRegion request(ResourceRegionFamily::Request);host.resourceRequestParent=request.authority();request.close();
  sourceRejected("E_RESOURCE_SCOPE",[&]{evaluate(source(once),host);});require(host.taskRetirements==0,"invalid parent published a task");
 });
 run("root task authority is a genuine captured request descendant",[]{
  Host host;ResourceRegion request(ResourceRegionFamily::Request);auto parent=request.authority();host.resourceRequestParent=parent;
  host.action=[&](size_t owner,const auto &authority)->std::optional<TaskReferenceExternalRequest>{
   require(owner==0&&parent.contains(authority)&&!authority.contains(parent),"reference task reused caller authority");
   host.resourceRegions=false;host.resourceRequestParent={};host.aliases.push_back(host.make(authority));return {};
  };
  require(evaluate(source(once),host).value.scalar==42&&host.taskRetirements==1,"captured opt-in changed during evaluation");settled(host,1);request.close();
 });
 run("caller resources survive repeated AST evaluations with recycled group links",[]{
  Host host;ResourceRegion request(ResourceRegionFamily::Request,{1,1,4,0,1});auto parent=request.authority();host.resourceRequestParent=parent;auto caller=host.make(parent);
  host.action=[&](size_t,const auto &authority)->std::optional<TaskReferenceExternalRequest>{
   require(caller.borrowInRegion(authority,host.key).value(host.key).value==42,"caller borrow failed");host.aliases.push_back(host.make(authority));return {};
  };
  auto program=source(once);
  for(size_t i=0;i<3;++i){require(evaluate(program,host).value.scalar==42,"repeated evaluation failed");require(caller.isOpen()&&*host.destroyed==int(i+1)&&!host.aliases.back().isOpen(),"group closure revoked caller or retained local owner");}
  request.close();settled(host,4);
 });
 run("root-owned return retains alias identity after reference group destruction",[]{
  Host host;ResourceRegion request(ResourceRegionFamily::Request);auto parent=request.authority();host.resourceRequestParent=parent;
  host.action=[&](size_t,const auto &authority)->std::optional<TaskReferenceExternalRequest>{auto owner=host.make(authority);auto id=owner.identity();host.aliases.push_back(owner);owner.promoteRegion(authority,parent);require(host.aliases[0].identity()==id,"return replaced physical identity");return {};};
  require(evaluate(source(once),host).value.scalar==42&&host.aliases[0].isOpen()&&*host.destroyed==0,"returned resource died with evaluator");
  auto native=ResourceRegion::inRequest(ResourceRegionFamily::Native,parent);require(host.aliases[0].borrowInRegion(native.authority(),host.key).value(host.key).value==42,"returned request resource cannot reach another scheduler family");native.close();request.close();settled(host,1);
 });
 run("child future can explicitly return request ownership to its caller",[]{
  Host host;ResourceRegion request(ResourceRegionFamily::Request);auto parent=request.authority();host.resourceRequestParent=parent;bool observed=false;
  host.action=[&](size_t owner,const auto &authority)->std::optional<TaskReferenceExternalRequest>{
   if(owner==1){host.aliases.push_back(host.make(authority));host.aliases.back().promoteRegion(authority,parent);}
   else{observed=host.aliases[0].isOpen()&&*host.destroyed==0;require(host.aliases[0].borrowInRegion(authority,host.key).value(host.key).value==42,"caller could not borrow explicit return");}return {};
  };
  require(evaluate(source(waited),host).value.scalar==42&&observed&&host.aliases[0].isOpen(),"future return retired caller ownership");request.close();settled(host,1);
 });
 run("unpromoted child owner is physically retired before parent task_wait resumes",[]{
  Host host;host.executor=std::make_shared<ResourceExecutor>();bool observed=false,retired=false;
  host.action=[&](size_t owner,const auto &authority)->std::optional<TaskReferenceExternalRequest>{
   if(owner==1)host.aliases.push_back(host.make(authority));else{settled(host,1);observed=!host.aliases[0].isOpen()&&retired;}return {};
  };
  host.taskRetirement=[&](size_t owner){if(owner==1)retired=*host.destroyed==1&&*host.pins==1&&host.physical.used()==0&&host.executor->stats().resources==0;};
  require(evaluate(source(waited),host).value.scalar==42&&observed&&host.taskRetirements==2,"future was published before task resource settlement");host.executor->finish();settled(host,1);
 });
 run("sibling tasks in the same scope have distinct resource ownership",[]{
  Host host;ResourceRegion request(ResourceRegionFamily::Request);auto parent=request.authority();host.resourceRequestParent=parent;bool refused=false;
  host.action=[&](size_t owner,const auto &authority)->std::optional<TaskReferenceExternalRequest>{
   if(owner==1)host.aliases.push_back(host.make(authority));
   if(owner==2){require(host.aliases[0].isOpen(),"first sibling ended before refusal probe");rejected("E_RESOURCE_SCOPE",[&]{host.aliases[0].borrowInRegion(authority,host.key);});rejected("E_RESOURCE_SCOPE",[&]{host.aliases[0].promoteRegion(authority,parent);});refused=true;}return {};
  };
  auto p=source(R"(fn main()->i64 !{task}{return with_tasks(1,fn(scope:task_scope)->i64 !{task}{
   let gate:channel<i64>=channel_new<i64>(scope,0);
   let first:task<i64>=task_spawn(scope,fn()->i64 !{task}{task_yield();task_recv(gate);return 40;});
   let second:task<i64>=task_spawn(scope,fn()->i64 !{task}{task_yield();task_send(gate,1);return 2;});return task_wait(first)+task_wait(second);});})");
  require(evaluate(p,host).value.scalar==42&&refused,"sibling job ancestry collapsed");request.close();settled(host,1);
 });
 run("explicit promotion to a source scope outlives child task completion",[]{
  Host host;ResourceRegionAuthority outer;size_t parentCalls=0;bool observed=false;
  host.action=[&](size_t owner,const auto &authority)->std::optional<TaskReferenceExternalRequest>{
   if(owner==0){if(parentCalls++==0)outer=authority;else observed=host.aliases[0].isOpen()&&*host.destroyed==0;}
   else{host.aliases.push_back(host.make(authority));host.aliases.back().promoteRegion(authority,outer);}return {};
  };
  auto p=source(R"(fn main()->i64 !{task}{return with_tasks(1,fn(scope:task_scope)->i64 !{task}{task_yield();let child:task<i64>=task_spawn(scope,fn()->i64 !{task}{task_yield();return 42;});let value:i64=task_wait(child);task_yield();return value;});})");
  require(evaluate(p,host).value.scalar==42&&observed&&!host.aliases[0].isOpen(),"scope return died with child or escaped scope");settled(host,1);
 });
 run("another AST job runs while child resource cleanup is physically blocked",[]{
  Host host;host.executor=std::make_shared<ResourceExecutor>();auto gate=std::make_shared<Gate>();bool progressed=false,observed=false,retired=false;
  host.action=[&](size_t owner,const auto &authority)->std::optional<TaskReferenceExternalRequest>{if(owner==1)host.aliases.push_back(host.make(authority,gate));if(owner==0){observed=retired&&!host.aliases[0].isOpen();settled(host,1);}return {};};
  host.taskRetirement=[&](size_t owner){if(owner==1)retired=*host.destroyed==1&&*host.pins==1&&host.executor->stats().resources==0;};
  auto result=evaluate(source(helped),host,[&](size_t owner,const TaskTransition &t){if(owner==2&&!progressed&&((t.operation=="task_yield"&&gate->reached())||t.kind==TaskTransition::Done)){
   bool entered=gate->wait();bool pending=*host.destroyed==0&&*host.pins==0&&host.physical.used()==1&&host.budgets[0].used()==4&&!retired;gate->open();require(entered&&pending,"AST future escaped or coordinator blocked all ready jobs");progressed=true;
  }});
  gate->open();host.executor->finish();require(result.value.scalar==42&&progressed&&observed,"physical task fence blocked unrelated AST progress");settled(host,1);
 });
 for(bool deadline:{false,true})run(deadline?"root task deadline retains its resource cleanup fence":"root task cancellation retains its resource cleanup fence",[&]{
  Host host;host.executor=std::make_shared<ResourceExecutor>();auto gate=std::make_shared<Gate>();std::stop_source stop;host.cancellation=stop.get_token();std::atomic<bool> returned=false,premature=false,arrived=false;
  host.action=[&](size_t,const auto &authority)->std::optional<TaskReferenceExternalRequest>{host.aliases.push_back(host.make(authority,gate));return {};};
  std::jthread release([&]{arrived=gate->wait();if(!deadline)stop.request_stop();std::this_thread::sleep_for(deadline?150ms:25ms);premature=returned.load()||host.taskRetirements!=0||*host.destroyed!=0;gate->open();});
  TaskExecutionLimits limits{1000000,100,1};sourceRejected(deadline?"E_TIMEOUT":"E_CANCELLED",[&]{evaluate(source(once),host,{},deadline?&limits:nullptr);});returned=true;release.join();host.executor->finish();require(arrived&&!premature&&host.taskRetirements==1,"root control failure lost the job resource fence");settled(host,1);
 });
 run("failed child body drains its own resources before surfacing error",[]{
  Host host;host.executor=std::make_shared<ResourceExecutor>();host.action=[&](size_t owner,const auto &authority)->std::optional<TaskReferenceExternalRequest>{if(owner==1)host.aliases.push_back(host.make(authority));return {};};
  auto p=source(R"(fn main()->i64 !{task}{return with_tasks(1,fn(scope:task_scope)->i64 !{task}{let child:task<i64>=task_spawn(scope,fn()->i64 !{task}{task_yield();let n:i64=9223372036854775807;return n+1;});return task_wait(child);});})");
  sourceRejected("E_OVERFLOW",[&]{evaluate(p,host);});settled(host,1);host.executor->finish();
 });
 run("physical operation admission keeps its job authority until final task cleanup",[]{
  Host host;host.executor=std::make_shared<ResourceExecutor>();auto work=std::make_shared<Gate>();work->open();ResourceRegionAuthority prepared;bool same=false;
  host.action=[&](size_t owner,const auto &authority)->std::optional<TaskReferenceExternalRequest>{if(owner!=1)return {};prepared=authority;host.aliases.push_back(host.make(authority));return TaskReferenceExternalRequest{std::make_shared<Operation>(work,host.aliases[0].borrowInRegion(authority,host.key)),0};};
  host.admission=[&](size_t,const auto &authority){same=prepared.contains(authority)&&authority.contains(prepared)&&host.aliases[0].isOpen();};
  auto result=evaluate(source(waited),host);require(result.value.scalar==42&&same&&result.external.retired==1&&!result.external.pending,"unit admission lost task resource identity");settled(host,1);host.executor->finish();
 });
 run("logical request closure rejects unpublished creation and waits executor cleanup",[]{
  Host host;host.executor=std::make_shared<ResourceExecutor>();ResourceRegion request(ResourceRegionFamily::Request);host.resourceRequestParent=request.authority();auto gate=std::make_shared<Gate>();std::atomic<bool> returned=false,premature=false,arrived=false;
  host.action=[&](size_t,const auto &authority)->std::optional<TaskReferenceExternalRequest>{
   auto pin=std::shared_ptr<void>(new int(1),[pins=host.pins](void *p){delete static_cast<int*>(p);++*pins;});
   ExternalResource::makeInRegion(host.access,authority,host.key,host.budgets,4,std::move(pin),host.executor,[&](const auto&){auto value=std::unique_ptr<Box>(new Box{host.destroyed,gate});request.close();return value;});return {};
  };
  std::jthread release([&]{arrived=gate->wait();premature=returned.load()||host.taskRetirements!=0||*host.destroyed!=0||host.physical.used()!=1;gate->open();});
  sourceRejected("E_RESOURCE_SCOPE",[&]{evaluate(source(once),host);});returned=true;release.join();host.executor->finish();require(arrived&&!premature&&host.taskRetirements==1,"unpublished creation lost the job cleanup fence");settled(host,1);
 });
 run("unexpected observer failure drains task resources without false publication",[]{
  Host host;host.executor=std::make_shared<ResourceExecutor>();auto gate=std::make_shared<Gate>();std::atomic<bool> returned=false,premature=false,arrived=false;
  host.action=[&](size_t,const auto &authority)->std::optional<TaskReferenceExternalRequest>{host.aliases.push_back(host.make(authority,gate));return {};};
  std::jthread release([&]{arrived=gate->wait();std::this_thread::sleep_for(25ms);premature=returned.load()||host.taskRetirements!=0||*host.destroyed!=0;gate->open();});
  bool failed=false;try{evaluate(source(once),host,[&](size_t,const TaskTransition &t){if(t.kind==TaskTransition::Done)throw std::runtime_error("request observer failure");});}catch(const std::runtime_error &e){failed=std::string(e.what())=="request observer failure";}returned=true;
  release.join();host.executor->finish();require(failed&&arrived&&!premature&&host.taskRetirements==0,"unexpected unwind published an unfinished task or escaped cleanup");settled(host,1);
 });
 run("rejected resource inputs preserve genuine caller request ownership",[]{
  Host host;ResourceRegion request(ResourceRegionFamily::Request);auto parent=request.authority();host.resourceRequestParent=parent;auto caller=host.make(parent);Value input(externalValue(caller));
  auto p=source("fn main(input:i64)->i64 !{task}{return input;}");sourceRejected("E_TASK_VALUE",[&]{evaluateTaskReference(p,"main",{input},1000000,{},nullptr,&host);});
  require(caller.isOpen()&&host.prepared==0&&host.taskRetirements==0,"input rejection granted source authority or revoked caller");request.close();settled(host,1);
 });
 run("explicit ancestor scope spawn outlives the child job that created it",[]{
  Host host;ResourceRegionAuthority child;bool childEnded=false,checked=false;
  host.taskRetirement=[&](size_t owner){if(owner==1)childEnded=true;};
  host.action=[&](size_t owner,const auto &authority)->std::optional<TaskReferenceExternalRequest>{
   if(owner==1&&!child)child=authority;
   if(owner==2){if(host.aliases.empty()){require(!child.contains(authority),"ancestor scope spawn inherited caller job root");host.aliases.push_back(host.make(authority));}else{checked=childEnded&&host.aliases[0].isOpen();require(host.aliases[0].borrowInRegion(authority,host.key).value(host.key).value==42,"ancestor-spawned resource died with caller job");}}return {};
  };
  auto p=source(R"(fn main()->i64 !{task}{return with_tasks(1,fn(outer:task_scope)->i64 !{task}{
   let gate:channel<i64>=channel_new<i64>(outer,0);
   let child:task<i64>=task_spawn(outer,fn()->i64 !{task}{task_yield();return with_tasks(1,fn(inner:task_scope)->i64 !{task}{
    task_spawn(outer,fn()->i64 !{task}{task_yield();task_recv(gate);task_yield();return 42;});task_yield();return 1;});});
   task_wait(child);task_send(gate,1);return 42;});})");
  require(evaluate(p,host).value.scalar==42&&checked,"explicit ancestor resource lifetime was shortened");settled(host,1);
 });
 run("logical resource request closure leaves admitted pure execution independent",[]{
  Host host;ResourceRegion request(ResourceRegionFamily::Request);host.resourceRequestParent=request.authority();bool closed=false;
  auto result=evaluate(source("fn main()->i64 !{task}{return 42;}"),host,[&](size_t,const TaskTransition &t){if(t.kind==TaskTransition::Done){request.close();closed=true;}});
  require(result.value.scalar==42&&closed&&host.taskRetirements==1,"logical request closure substituted execution cancellation");host.empty();
 });
 run("individual cancellation drains a task owner while another AST job progresses",[]{
  Host host;host.executor=std::make_shared<ResourceExecutor>();auto gate=std::make_shared<Gate>();bool progressed=false,retired=false;
  host.action=[&](size_t owner,const auto &authority)->std::optional<TaskReferenceExternalRequest>{if(owner==1&&host.aliases.empty())host.aliases.push_back(host.make(authority,gate));return {};};
  host.taskRetirement=[&](size_t owner){if(owner==1)retired=*host.destroyed==1&&*host.pins==1&&host.physical.used()==0;};
  auto p=source(R"(fn main()->i64 !{task}{return with_tasks(1,fn(scope:task_scope)->i64 !{task}{
   let victim:task<i64>=task_spawn(scope,fn()->i64 !{task}{task_yield();var active:bool=true;while active{task_yield();}return 40;});
   task_yield();task_cancel(victim);
   let helper:task<i64>=task_spawn(scope,fn()->i64 !{task}{var i:i64=0;while i<128{task_yield();i=i+1;}return 2;});return 40+task_wait(helper);});})");
  auto result=evaluate(p,host,[&](size_t owner,const TaskTransition &t){if(owner==2&&!progressed&&((t.operation=="task_yield"&&gate->reached())||t.kind==TaskTransition::Done)){
   bool entered=gate->wait();bool pending=!retired&&*host.destroyed==0&&host.physical.used()==1;gate->open();require(entered&&pending,"individual task cancellation bypassed physical cleanup");progressed=true;
  }});
  gate->open();host.executor->finish();require(result.value.scalar==42&&progressed&&retired,"cancelled job blocked all AST work");settled(host,1);
 });
 run("256 task and scope ancestry levels remain available to actual AST execution",[]{
  Host host;host.action=[&](size_t owner,const auto &authority)->std::optional<TaskReferenceExternalRequest>{require(owner==255&&authority.depth()==256,"AST resource ownership reduced source nesting depth");host.aliases.push_back(host.make(authority));return {};};
  const std::string body=R"(fn descend(n:i64)->i64 !{task}{
   if n==1{return with_tasks(1,fn(inner:task_scope)->i64 !{task}{task_yield();return 42;});}
   return with_tasks(1,fn(scope:task_scope)->i64 !{task}{let child:task<i64>=task_spawn(scope,fn()->i64 !{task}{return descend(n-1);});return task_wait(child);});}
   fn main()->i64 !{task}{return descend(DEPTH);})";
  auto program=body;program.replace(program.find("DEPTH"),5,"256");TaskExecutionLimits limits{1000000000,30000,1};
  auto result=evaluate(source(program),host,{},&limits);require(result.value.scalar==42&&result.tasks==256&&result.scopes==256&&host.taskRetirements==256,"combined AST task/scope nesting changed");settled(host,1);
  host.action={};program=body;program.replace(program.find("DEPTH"),5,"257");sourceRejected("E_LIMIT",[&]{evaluate(source(program),host,{},&limits);});settled(host,1);
 });
 run("bounded AST job roots do not consume resource owner slots",[]{
  Host host;auto p=source(R"(fn main()->i64 !{task}{return with_tasks(1,fn(scope:task_scope)->i64 !{task}{var i:i64=0;while i<512{task_spawn(scope,fn()->i64 !{task}{return 1;});i=i+1;}return 42;});})");
  auto result=evaluate(p,host);require(result.value.scalar==42&&result.tasks==513&&host.taskRetirements==513,"empty AST task roots exhausted owner quota or missed retirement");host.empty();
 });
 std::cout<<"independent reference request resource cases="<<cases<<"\n";return 0;
}catch(const std::exception &e){std::cerr<<e.what()<<"\n";return 1;}}
