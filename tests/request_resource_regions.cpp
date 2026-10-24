#include "nex_external_resource.h"
#include <array>
#include <atomic>
#include <barrier>
#include <chrono>
#include <condition_variable>
#include <iostream>
#include <thread>
#include <vector>
using namespace nexrt;
namespace {
void require(bool value,const char *message){if(!value)throw std::runtime_error(message);}
template<class F> void error(const char *code,F body){try{body();}catch(const DataError &e){require(e.code==code,"unexpected request region error");return;}throw std::runtime_error(std::string("missing ")+code);}
struct Gate {
  std::mutex mutex;std::condition_variable changed;bool arrived=false,released=false;
  void enter(){std::unique_lock lock(mutex);arrived=true;changed.notify_all();changed.wait(lock,[&]{return released;});}
  void wait(){std::unique_lock lock(mutex);require(changed.wait_for(lock,std::chrono::seconds(5),[&]{return arrived;}),"request resource barrier not reached");}
  void open(){{std::lock_guard lock(mutex);released=true;}changed.notify_all();}
};
struct Release {std::shared_ptr<Gate> gate;~Release(){gate->open();}};
struct Box {
  std::shared_ptr<std::atomic<int>> destroyed;std::shared_ptr<Gate> cleanup;
  const int value=42;
  Box(std::shared_ptr<std::atomic<int>> destroyed,std::shared_ptr<Gate> cleanup={}):destroyed(std::move(destroyed)),cleanup(std::move(cleanup)){}
  ~Box()noexcept{if(cleanup)cleanup->enter();++*destroyed;}
};
struct Fixture {
  ResourceDomain physical{4};std::array<ResourceByteBudget,1> budgets{ResourceByteBudget(16)};
  ExternalResourceType<Box> key{"request::Buffer",std::string(64,'a')};
  std::shared_ptr<std::atomic<int>> destroyed=std::make_shared<std::atomic<int>>(0);
  ExternalResource make(const ResourceRegionAuthority &authority,std::shared_ptr<ResourceExecutor> executor={},std::shared_ptr<Gate> cleanup={}){
    return ExternalResource::makeInRegion(physical.access(),authority,key,budgets,4,std::make_shared<int>(1),std::move(executor),
      [destroyed=destroyed,cleanup](const auto&){return std::make_unique<Box>(destroyed,cleanup);});
  }
  void borrow(const ExternalResource &resource,const ResourceRegionAuthority &authority){require(resource.borrowInRegion(authority,key).value(key).value==42,"request borrow changed data");}
  void empty(int expected){require(*destroyed==expected&&physical.used()==0&&budgets[0].used()==0,"physical request resources or quotas remain");}
};
constexpr ResourceRegionLimits small{4,3,4,4,4};
}
int main(){try{
 size_t cases=0;auto run=[&](const char *name,auto body){body();++cases;std::cout<<"PASS "<<name<<std::endl;};
 run("only genuine live request parents admit scheduler graphs",[]{
  ResourceRegion native,reference(ResourceRegionFamily::Reference),request(ResourceRegionFamily::Request);
  for(auto family:{ResourceRegionFamily::Native,ResourceRegionFamily::Reference}){
   error("E_RESOURCE_SCOPE",[&]{ResourceRegion::inRequest(family,{});});
   error("E_RESOURCE_SCOPE",[&]{ResourceRegion::inRequest(family,native.authority());});
   error("E_RESOURCE_SCOPE",[&]{ResourceRegion::inRequest(family,reference.authority());});
  }
  error("E_RESOURCE_SCOPE",[&]{ResourceRegion::inRequest(ResourceRegionFamily::Request,request.authority());});
  for(auto limits:std::vector<ResourceRegionLimits>{{1,1,1,65537,1},{1,1,1,1,1025}})
   error("E_RESOURCE_REGION_LIMIT",[&]{ResourceRegion::inRequest(ResourceRegionFamily::Native,request.authority(),limits);});
  auto parent=request.authority();request.close();error("E_RESOURCE_SCOPE",[&]{ResourceRegion::inRequest(ResourceRegionFamily::Native,parent);});
 });
 run("caller ownership is shared ancestry for both independent scheduler families",[]{
  Fixture f;ResourceRegion request(ResourceRegionFamily::Request);auto parent=request.authority();auto resource=f.make(parent);
  auto native=ResourceRegion::inRequest(ResourceRegionFamily::Native,parent,small),reference=ResourceRegion::inRequest(ResourceRegionFamily::Reference,parent,small);
  require(parent.contains(native.authority())&&parent.contains(reference.authority()),"request ancestry absent");
  require(!native.authority().contains(reference.authority()),"scheduler identities collapsed");
  f.borrow(resource,native.authority());f.borrow(resource,reference.authority());
  native.close();reference.close();f.borrow(resource,parent);require(*f.destroyed==0,"group end revoked caller resource");request.close();f.empty(1);
 });
 for(auto family:{ResourceRegionFamily::Native,ResourceRegionFamily::Reference})
 run(family==ResourceRegionFamily::Native?"native explicit return preserves aliases and identity":"reference explicit return preserves aliases and identity",[&]{
  Fixture f;ResourceRegion request(ResourceRegionFamily::Request);auto parent=request.authority();
  auto group=ResourceRegion::inRequest(family,parent,small);auto actor=group.authority();auto scope=group.child();
  auto resource=f.make(scope.authority());auto alias=resource;auto identity=resource.identity();
  resource.promoteRegion(scope.authority(),parent);group.close();
  require(resource.isOpen()&&alias.identity()==identity&&*f.destroyed==0,"return copied or closed resource");f.borrow(alias,parent);
  auto next=ResourceRegion::inRequest(family==ResourceRegionFamily::Native?ResourceRegionFamily::Reference:ResourceRegionFamily::Native,parent,small);
  f.borrow(alias,next.authority());next.close();f.borrow(resource,parent);request.close();f.empty(1);
 });
 run("group local owners stay inaccessible to sibling groups and caller",[]{
  Fixture f;ResourceRegion request(ResourceRegionFamily::Request),foreign(ResourceRegionFamily::Request);auto parent=request.authority();
  auto left=ResourceRegion::inRequest(ResourceRegionFamily::Native,parent,small),right=ResourceRegion::inRequest(ResourceRegionFamily::Reference,parent,small);
  auto actor=left.authority();auto resource=f.make(actor);
  error("E_RESOURCE_SCOPE",[&]{f.borrow(resource,parent);});error("E_RESOURCE_SCOPE",[&]{f.borrow(resource,right.authority());});
  error("E_RESOURCE_SCOPE",[&]{resource.promoteRegion(actor,right.authority());});error("E_RESOURCE_SCOPE",[&]{resource.promoteRegion(right.authority(),parent);});
  error("E_RESOURCE_SCOPE",[&]{resource.promoteRegion(actor,foreign.authority());});left.close();f.empty(1);
 });
 run("request child ancestry limits borrowing and selective group revocation",[]{
  Fixture f;ResourceRegion request(ResourceRegionFamily::Request);auto left=request.child(),right=request.child();
  auto first=ResourceRegion::inRequest(ResourceRegionFamily::Native,left.authority(),small),second=ResourceRegion::inRequest(ResourceRegionFamily::Reference,right.authority(),small);
  auto caller=f.make(left.authority()),local=f.make(first.authority()),other=f.make(second.authority());
  f.borrow(caller,first.authority());error("E_RESOURCE_SCOPE",[&]{f.borrow(caller,second.authority());});
  auto ended=first.authority();auto retirement=left.beginClose();retirement.requestClose();require(retirement.ready()&&*f.destroyed==2,"child request failed linked retirement");
  error("E_RESOURCE_SCOPE",[&]{ended.check();});f.borrow(other,second.authority());request.close();f.empty(3);
 });
 run("full caller owner quota refuses transfer without changing the origin",[]{
  Fixture f;ResourceRegion request(ResourceRegionFamily::Request,{1,1,1,0,2});auto parent=request.authority();auto existing=f.make(parent);
  auto group=ResourceRegion::inRequest(ResourceRegionFamily::Native,parent,small);auto actor=group.authority();auto local=f.make(actor);auto identity=local.identity();
  error("E_RESOURCE_REGION_LIMIT",[&]{local.promoteRegion(actor,parent);});f.borrow(local,actor);require(local.identity()==identity,"failed transfer changed identity");
  error("E_RESOURCE_SCOPE",[&]{f.borrow(local,parent);});group.close();f.borrow(existing,parent);request.close();f.empty(2);
 });
 run("successful return releases its original group owner slot",[]{
  Fixture f;ResourceRegion request(ResourceRegionFamily::Request,{1,1,1,0,1});auto parent=request.authority();
  auto group=ResourceRegion::inRequest(ResourceRegionFamily::Native,parent,{1,1,1,0,0});auto actor=group.authority();
  auto returned=f.make(actor);returned.promoteRegion(actor,parent);auto next=f.make(actor);
  group.close();require(returned.isOpen()&&!next.isOpen(),"owner slots did not move atomically");f.borrow(returned,parent);request.close();f.empty(2);
 });
 run("settled group links recycle despite retained closed aliases",[]{
  Fixture f;ResourceRegion request(ResourceRegionFamily::Request,{1,1,1,0,1});auto parent=request.authority();
  std::vector<ExternalResource> aliases;aliases.reserve(2048);
  for(size_t i=0;i<2048;++i){auto group=ResourceRegion::inRequest(i%2?ResourceRegionFamily::Native:ResourceRegionFamily::Reference,parent,{1,1,1,0,0});aliases.push_back(f.make(group.authority()));group.close();}
  require(*f.destroyed==2048,"closed group aliases exhausted request group count");request.close();f.empty(2048);
 });
 run("group capacity remains retained through an executor finalizer",[]{
  Fixture f;ResourceRegion request(ResourceRegionFamily::Request,{1,1,1,0,1});auto parent=request.authority();
  auto executor=std::make_shared<ResourceExecutor>();auto gate=std::make_shared<Gate>();Release release{gate};
  auto group=ResourceRegion::inRequest(ResourceRegionFamily::Native,parent,small);auto resource=f.make(group.authority(),executor,gate);
  auto retirement=group.beginClose();retirement.requestClose();gate->wait();resource={};
  error("E_RESOURCE_REGION_LIMIT",[&]{ResourceRegion::inRequest(ResourceRegionFamily::Reference,parent,small);});require(!retirement.ready(),"pending destructor freed group link");
  gate->open();executor->finish();require(retirement.ready(),"physical group cleanup did not settle");
  auto next=ResourceRegion::inRequest(ResourceRegionFamily::Reference,parent,small);next.close();request.close();f.empty(1);
 });
 run("request retirement fences physical borrows and linked cleanup",[]{
  Fixture f;ResourceRegion request(ResourceRegionFamily::Request);auto parent=request.authority();
  auto group=ResourceRegion::inRequest(ResourceRegionFamily::Reference,parent,small);auto actor=group.authority();auto executor=std::make_shared<ResourceExecutor>();
  auto resource=f.make(actor,executor);auto borrow=resource.borrowInRegion(actor,f.key);auto *data=&borrow.value(f.key);
  auto retirement=request.beginClose();retirement.requestClose();require(!resource.isOpen()&&!retirement.ready(),"request published before physical borrow ended");
  require(data->value==42&&f.physical.used()==1,"request reclaimed outstanding physical borrow");error("E_RESOURCE_SCOPE",[&]{borrow.check();});
  borrow={};executor->finish();require(retirement.ready(),"request did not follow linked physical cleanup");f.empty(1);
 });
 run("request closure waits for unpublished factory and its cleanup",[]{
  Fixture f;ResourceRegion request(ResourceRegionFamily::Request);auto group=ResourceRegion::inRequest(ResourceRegionFamily::Native,request.authority(),small);auto actor=group.authority();
  auto executor=std::make_shared<ResourceExecutor>();auto creating=std::make_shared<Gate>(),cleanup=std::make_shared<Gate>();Release releaseCleanup{cleanup};
  std::atomic<bool> rejected=false;
  std::jthread creator([&]{try{ExternalResource::makeInRegion(f.physical.access(),actor,f.key,f.budgets,4,std::make_shared<int>(1),executor,[&](const auto&){auto box=std::make_unique<Box>(f.destroyed,cleanup);creating->enter();return box;});}catch(const DataError &e){rejected=e.code=="E_RESOURCE_SCOPE";}});
  Release releaseCreation{creating};
  creating->wait();auto retirement=request.beginClose();retirement.requestClose();const bool pending=!retirement.ready();creating->open();creator.join();cleanup->wait();
  require(pending&&rejected&&!retirement.ready()&&f.physical.used()==1,"unpublished factory escaped request fence");cleanup->open();executor->finish();require(retirement.ready(),"unpublished cleanup never settled");f.empty(1);
 });
 run("256 scope and256 task levels keep independent logical bounds",[]{
  Fixture f;ResourceRegion request(ResourceRegionFamily::Request);auto group=ResourceRegion::inRequest(ResourceRegionFamily::Native,request.authority(),{257,256,1,256,0});
  std::vector<ResourceRegion> path;path.reserve(512);
  for(size_t i=0;i<256;++i){path.push_back((i?path.back():group).taskChild());path.push_back(path.back().child());}
  require(path.back().authority().depth()==256,"task ownership consumed scope depth");error("E_RESOURCE_REGION_LIMIT",[&]{path.back().child();});error("E_RESOURCE_REGION_LIMIT",[&]{path.back().taskChild();});
  auto resource=f.make(path.back().authority());f.borrow(resource,path.back().authority());auto retirement=request.beginClose();retirement.requestClose();require(retirement.ready(),"iterative request close failed512 combined levels");f.empty(1);
 });
 run("65536 resource free task regions retire without owner scans",[]{
  ResourceRegion request(ResourceRegionFamily::Request);auto group=ResourceRegion::inRequest(ResourceRegionFamily::Native,request.authority(),{1,1,4096,65536,0});
  for(size_t i=0;i<65536;++i){auto task=group.taskChild();require(task.authority().depth()==0,"task increased source scope depth");task.close();}
  error("E_RESOURCE_REGION_LIMIT",[&]{group.taskChild();});auto retirement=request.beginClose();retirement.requestClose();require(retirement.ready(),"empty request retained physical cleanup");
 });
 run("request ownership never substitutes a physical grant",[]{
  Fixture f;ResourceRegion request(ResourceRegionFamily::Request);auto group=ResourceRegion::inRequest(ResourceRegionFamily::Native,request.authority(),small);auto actor=group.authority();
  f.physical.revoke();error("E_RESOURCE_SCOPE",[&]{f.make(actor);});require(actor.family()==ResourceRegionFamily::Native,"physical closure changed logical identity");
  auto retirement=request.beginClose();retirement.requestClose();require(retirement.ready(),"rejected physical grant retained logical slot");f.empty(0);
 });
 run("promotion and request closure serialize without leaked physical identity",[]{
  for(size_t i=0;i<256;++i){
   Fixture f;ResourceRegion request(ResourceRegionFamily::Request);auto parent=request.authority();auto group=ResourceRegion::inRequest(i%2?ResourceRegionFamily::Native:ResourceRegionFamily::Reference,parent,small);auto actor=group.authority();auto resource=f.make(actor);auto identity=resource.identity();
   std::barrier start(2);std::atomic<bool> unexpected=false;
   std::jthread promoter([&]{start.arrive_and_wait();try{resource.promoteRegion(actor,parent);}catch(const DataError &e){unexpected=e.code!="E_RESOURCE_SCOPE";}catch(...){unexpected=true;}});
   start.arrive_and_wait();auto retirement=request.beginClose();retirement.requestClose();promoter.join();
   require(!unexpected&&retirement.ready()&&!resource.isOpen()&&resource.identity()==identity,"racing transfer escaped request retirement");f.empty(1);
  }
 });
 run("registration and request closure cannot publish a live orphan group",[]{
  for(size_t i=0;i<128;++i){
   ResourceRegion request(ResourceRegionFamily::Request,{1,1,1,0,1});auto parent=request.authority();std::barrier start(2);ResourceRegionAuthority admitted;std::atomic<bool> unexpected=false;
   std::jthread creator([&]{start.arrive_and_wait();try{auto group=ResourceRegion::inRequest(ResourceRegionFamily::Native,parent,{1,1,1,0,0});admitted=group.authority();}catch(const DataError &e){unexpected=e.code!="E_RESOURCE_SCOPE";}catch(...){unexpected=true;}});
   start.arrive_and_wait();auto retirement=request.beginClose();retirement.requestClose();creator.join();require(!unexpected&&retirement.ready(),"request registration race failed");if(admitted)error("E_RESOURCE_SCOPE",[&]{admitted.check();});
  }
 });
 std::cout<<"REQUEST RESOURCE REGION CASES "<<cases<<std::endl;return 0;
}catch(const std::exception &e){std::cerr<<e.what()<<std::endl;return 1;}}
