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
#include <vector>
using namespace nexrt;
namespace {
void require(bool value,const char *text){if(!value)throw std::runtime_error(text);}
template<class F> void error(const char *code,F body){try{body();}catch(const DataError &e){require(e.code==code,"unexpected resource region error");return;}throw std::runtime_error(std::string("missing ")+code);}
struct Gate {
  std::mutex mutex;std::condition_variable changed;bool arrived=false,released=false;
  void enter(){std::unique_lock lock(mutex);arrived=true;changed.notify_all();changed.wait(lock,[&]{return released;});}
  void wait(){std::unique_lock lock(mutex);require(changed.wait_for(lock,std::chrono::seconds(5),[&]{return arrived;}),"region barrier not reached");}
  void open(){{std::lock_guard lock(mutex);released=true;}changed.notify_all();}
  bool reached(){std::lock_guard lock(mutex);return arrived;}
  ~Gate(){open();}
};
struct Box {
  std::shared_ptr<std::atomic<int>> destroyed;
  std::shared_ptr<Gate> cleanup;
  std::function<void()> callback;
  const int value=42;
  Box(std::shared_ptr<std::atomic<int>> destroyed,std::shared_ptr<Gate> cleanup={},std::function<void()> callback={}):destroyed(std::move(destroyed)),cleanup(std::move(cleanup)),callback(std::move(callback)){}
  ~Box()noexcept{if(cleanup)cleanup->enter();if(callback)callback();++*destroyed;}
};
auto type(){return ExternalResourceType<Box>("task::Buffer",std::string(64,'e'));}
auto code(){return std::make_shared<int>(1);}
template<class Budgets> ExternalResource make(ResourceAccess physical,const ResourceRegionAuthority &authority,
    const ExternalResourceType<Box> &key,const Budgets &budgets,const std::shared_ptr<std::atomic<int>> &destroyed,
    std::shared_ptr<ResourceExecutor> executor={},std::shared_ptr<Gate> cleanup={}){
  return ExternalResource::makeInRegion(std::move(physical),authority,key,budgets,4,code(),std::move(executor),
    [destroyed,cleanup](const auto&){return std::make_unique<Box>(destroyed,cleanup);});
}
struct NativeContext {
  ResourceAccess physical;ResourceRegionAuthority authority;ExternalResourceType<Box> key;
  std::array<ResourceByteBudget,1> budgets;std::shared_ptr<std::atomic<int>> destroyed;
  std::shared_ptr<ResourceExecutor> executor;std::shared_ptr<std::optional<ExternalResource>> output;
  int mode=0;std::shared_ptr<Gate> cleanup;std::shared_ptr<std::atomic<bool>> afterScope;
  std::shared_ptr<std::atomic<bool>> sourceHelper{};
};
TaskBody nativeTask(TaskGroup &group,NativeContext context){
  auto resource=make(context.physical,context.authority,context.key,context.budgets,context.destroyed,context.executor);
  for(int i=0;i<64;++i){require(resource.borrowInRegion(context.authority,context.key).value(context.key).value==42,"logical owner expired across resume");co_await group.yield();}
  *context.output=resource;co_return Value(int64_t(42));
}
TaskBody nativeFactory(TaskGroup &group,Value,Value,const void *context){return nativeTask(group,*static_cast<const NativeContext*>(context));}
TaskBody nativeScopedTask(TaskGroup &group,NativeContext context){
  auto parent=group.resourceAuthority();std::vector<TaskGroup::Scope> scopes;
  for(size_t i=0;i<(context.mode==3?256:1);++i)scopes.push_back(group.openScope(2));
  auto authority=group.resourceAuthority();require(authority.depth()==scopes.size(),"scheduler and logical resource depths differ");
  auto resource=make(context.physical,authority,context.key,context.budgets,context.destroyed,context.executor,context.cleanup);
  for(size_t i=0;i<64;++i){require(resource.borrowInRegion(group.resourceAuthority(),context.key).value(context.key).value==42,"native scoped resource failed across resume");co_await group.yield();}
  if(context.mode==2)resource.promoteRegion(group.resourceAuthority(),parent);
  *context.output=resource;
  for(auto i=scopes.rbegin();i!=scopes.rend();++i)co_await group.leaveScope(*i);
  context.afterScope->store(true);co_return Value(int64_t(42));
}
TaskBody nativeScopedFactory(TaskGroup &group,Value,Value,const void *context){return nativeScopedTask(group,*static_cast<const NativeContext*>(context));}
TaskBody nativeReleaseTask(TaskGroup &group,NativeContext context){
  while(!context.cleanup->reached())co_await group.yield();
  context.sourceHelper->store(!context.afterScope->load()&&*context.destroyed==0&&context.budgets[0].used()==4);
  context.cleanup->open();co_return Value(int64_t(1));
}
TaskBody nativeReleaseFactory(TaskGroup &group,Value,Value,const void *context){return nativeReleaseTask(group,*static_cast<const NativeContext*>(context));}
}
int main(){try{
 size_t cases=0;auto run=[&](const char *name,auto body){body();++cases;std::cout<<"PASS "<<name<<std::endl;};
 run("unavailable authority and invalid bounds fail closed",[]{
  error("E_RESOURCE_SCOPE",[]{ResourceRegionAuthority{}.check();});
  for(auto limits:std::vector<ResourceRegionLimits>{{0,1,1},{1026,1,1},{1,0,1},{1,257,1},{1,1,0},{1,1,4097}})
   error("E_RESOURCE_REGION_LIMIT",[&]{ResourceRegion region(ResourceRegionFamily::Native,limits);});
 });
 run("executor settlement markers follow slot release and run outside queue locks",[]{
  auto executor=std::make_shared<ResourceExecutor>(ResourceExecutorLimits{1,1,4});std::atomic<int> released=0;std::atomic<bool> afterQuota=true;
  auto marker=[&]{return std::shared_ptr<void>(new int(1),[&](void *p){afterQuota=afterQuota.load()&&executor->stats().resources==0;delete static_cast<int*>(p);++released;});};
  {auto abandoned=executor->reserveCleanup();abandoned.retainUntilSettled(marker());}
  require(released==1&&afterQuota,"abandoned cleanup marker ran before reservation release");
  auto cleanup=executor->reserveCleanup();cleanup.retainUntilSettled(marker());
  cleanup.retire(new int(2),[](void *p)noexcept{delete static_cast<int*>(p);});executor->finish();
  require(released==2&&afterQuota,"executed cleanup marker ran under locks or before physical quota return");
 });
 run("256 logical levels do not consume eight physical domain joins",[]{
  ResourceDomain physical(1);std::array budgets{ResourceByteBudget(4)};auto key=type();auto destroyed=std::make_shared<std::atomic<int>>(0);
  std::vector<ResourceRegion> regions;regions.reserve(257);regions.emplace_back();
  for(size_t i=0;i<256;++i)regions.push_back(regions.back().child());require(regions.back().authority().depth()==256,"logical depth changed");
  error("E_RESOURCE_REGION_LIMIT",[&]{regions.back().child();});
  auto resource=make(physical.access(),regions.back().authority(),key,budgets,destroyed);
  require(resource.borrowInRegion(regions.back().authority(),key).value(key).value==42&&physical.used()==1,"logical ancestry consumed physical joins");regions.front().close();
  require(!resource.isOpen()&&*destroyed==1&&budgets[0].used()==0,"root closure failed descendant cleanup");
 });
 run("ancestor borrowing cannot be reversed or cross siblings",[]{
  ResourceRegion root;auto left=root.child(),right=root.child(),leaf=left.child();ResourceDomain physical;std::array budgets{ResourceByteBudget(8)};auto key=type();auto destroyed=std::make_shared<std::atomic<int>>(0);
  auto parent=make(physical.access(),root.authority(),key,budgets,destroyed),child=make(physical.access(),left.authority(),key,budgets,destroyed);
  require(parent.borrowInRegion(leaf.authority(),key).value(key).value==42,"ancestor borrow refused");
  error("E_RESOURCE_SCOPE",[&]{child.borrowInRegion(root.authority(),key);});error("E_RESOURCE_SCOPE",[&]{child.borrowInRegion(right.authority(),key);});
  error("E_RESOURCE_SCOPE",[&]{child.borrow(key);});
 });
 run("native reference and independent native families cannot forge authority",[]{
  ResourceRegion native,otherNative;ResourceRegion reference(ResourceRegionFamily::Reference);ResourceDomain physical;std::array budgets{ResourceByteBudget(4)};auto key=type();auto destroyed=std::make_shared<std::atomic<int>>(0);auto resource=make(physical.access(),native.authority(),key,budgets,destroyed);
  require(native.authority().family()==ResourceRegionFamily::Native&&reference.authority().family()==ResourceRegionFamily::Reference,"family metadata wrong");
  error("E_RESOURCE_SCOPE",[&]{resource.borrowInRegion(reference.authority(),key);});error("E_RESOURCE_SCOPE",[&]{resource.borrowInRegion(otherNative.authority(),key);});
  require(!native.authority().contains(otherNative.authority()),"foreign group considered descendant");
 });
 run("logical close and physical settlement are distinct",[]{
  ResourceRegion root;auto child=root.child();ResourceDomain physical(1);std::array budgets{ResourceByteBudget(4)};auto key=type();auto destroyed=std::make_shared<std::atomic<int>>(0);auto executor=std::make_shared<ResourceExecutor>();
  auto authority=child.authority();auto resource=make(physical.access(),authority,key,budgets,destroyed,executor);auto borrow=resource.borrowInRegion(authority,key);auto *pointer=&borrow.value(key);
  auto retirement=child.beginClose();require(!resource.isOpen()&&!retirement.ready(),"logical close published physical completion");error("E_RESOURCE_SCOPE",[&]{borrow.check();});
  retirement.requestClose();require(pointer->value==42&&physical.used()==1&&budgets[0].used()==4&&!retirement.ready(),"logical close reclaimed admitted physical lease");
  borrow={};executor->finish();require(retirement.ready()&&*destroyed==1&&physical.used()==0&&budgets[0].used()==0,"physical fence did not follow complete cleanup");
 });
 run("destructor and quota retirement precede the readiness fence",[]{
  ResourceRegion root;ResourceDomain physical;std::array budgets{ResourceByteBudget(4)};auto key=type();auto destroyed=std::make_shared<std::atomic<int>>(0);auto executor=std::make_shared<ResourceExecutor>();auto gate=std::make_shared<Gate>();
  auto owner=make(physical.access(),root.authority(),key,budgets,destroyed,executor,gate);auto retirement=root.beginClose();retirement.requestClose();gate->wait();
  require(!retirement.ready()&&physical.used()==1&&budgets[0].used()==4,"cleanup queue or destructor entry signalled settlement");owner={};
  require(!retirement.ready(),"expired logical wrapper lost a physical fence");gate->open();executor->finish();require(retirement.ready()&&physical.used()==0&&budgets[0].used()==0,"physical cleanup did not settle");
 });
 run("beginClose invokes no foreign destructor while caller locks are held",[]{
  ResourceRegion root;ResourceDomain physical;std::array budgets{ResourceByteBudget(4)};auto key=type();auto destroyed=std::make_shared<std::atomic<int>>(0);std::mutex scheduler;std::atomic<bool> callback=false;
  auto owner=ExternalResource::makeInRegion(physical.access(),root.authority(),key,budgets,4,code(),{},[&](const auto&){return std::make_unique<Box>(destroyed,nullptr,[&]{std::lock_guard lock(scheduler);callback=true;});});
  ResourceRegionRetirement retirement;{std::lock_guard lock(scheduler);retirement=root.beginClose();require(!callback,"logical revocation executed a destructor");}
  retirement.requestClose();require(callback&&retirement.ready(),"deferred cleanup did not run outside caller locks");
 });
 run("reviewed ancestor promotion preserves aliases and physical identity",[]{
  ResourceRegion root;auto child=root.child();ResourceDomain physical;std::array budgets{ResourceByteBudget(4)};auto key=type();auto destroyed=std::make_shared<std::atomic<int>>(0);auto actor=child.authority();auto parent=root.authority();
  auto owner=make(physical.access(),actor,key,budgets,destroyed);auto alias=owner;auto identity=owner.identity();owner.promoteRegion(actor,parent);child.close();
  require(owner.isOpen()&&alias.borrowInRegion(parent,key).value(key).value==42&&alias.identity()==identity,"promotion copied or closed physical resource");root.close();require(*destroyed==1,"promoted owner escaped ancestor cleanup");
 });
 run("sibling promotion and promotion after close are rejected",[]{
  ResourceRegion root;auto left=root.child(),right=root.child();ResourceDomain physical;std::array budgets{ResourceByteBudget(4)};auto key=type();auto destroyed=std::make_shared<std::atomic<int>>(0);auto actor=left.authority(),target=root.authority();auto owner=make(physical.access(),actor,key,budgets,destroyed);
  error("E_RESOURCE_SCOPE",[&]{owner.promoteRegion(actor,right.authority());});auto retirement=left.beginClose();error("E_RESOURCE_SCOPE",[&]{owner.promoteRegion(actor,target);});retirement.requestClose();
 });
 run("logical owner admission precedes the resource factory",[]{
  ResourceRegion root(ResourceRegionFamily::Native,{8,7,1});ResourceDomain physical;std::array budgets{ResourceByteBudget(8)};auto key=type();auto destroyed=std::make_shared<std::atomic<int>>(0);auto owner=make(physical.access(),root.authority(),key,budgets,destroyed);int called=0;
  error("E_RESOURCE_REGION_LIMIT",[&]{ExternalResource::makeInRegion(physical.access(),root.authority(),key,budgets,4,code(),{},[&](const auto&){++called;return std::make_unique<Box>(destroyed);});});require(called==0&&physical.used()==1,"logical admission ran factory or leaked quota");
 });
 run("closed owner slots cannot be reused before physical settlement",[]{
  ResourceRegion root(ResourceRegionFamily::Native,{8,7,1});ResourceDomain physical;std::array budgets{ResourceByteBudget(8)};auto key=type();auto destroyed=std::make_shared<std::atomic<int>>(0);auto executor=std::make_shared<ResourceExecutor>();auto gate=std::make_shared<Gate>();
  auto owner=make(physical.access(),root.authority(),key,budgets,destroyed,executor,gate);owner.close();gate->wait();owner={};
  error("E_RESOURCE_REGION_LIMIT",[&]{make(physical.access(),root.authority(),key,budgets,destroyed,executor);});gate->open();executor->drain();
  auto next=make(physical.access(),root.authority(),key,budgets,destroyed,executor);next.close();executor->finish();require(*destroyed==2,"logical slot failed to recycle after physical cleanup");
 });
 run("revoked factory publication retains an otherwise invisible cleanup fence",[]{
  ResourceRegion root;auto authority=root.authority();ResourceDomain physical;std::array budgets{ResourceByteBudget(4)};auto key=type();auto destroyed=std::make_shared<std::atomic<int>>(0);auto executor=std::make_shared<ResourceExecutor>();auto creating=std::make_shared<Gate>(),cleanup=std::make_shared<Gate>();std::atomic<bool> rejected=false;
  std::thread creator([&]{try{ExternalResource::makeInRegion(physical.access(),authority,key,budgets,4,code(),executor,[&](const auto&){auto value=std::make_unique<Box>(destroyed,cleanup);creating->enter();return value;});}catch(const DataError &e){rejected=e.code=="E_RESOURCE_SCOPE";}});
  creating->wait();auto retirement=root.beginClose();retirement.requestClose();require(!retirement.ready(),"in-flight factory was treated as settled");creating->open();creator.join();cleanup->wait();
  require(rejected&&!retirement.ready()&&physical.used()==1&&budgets[0].used()==4,"failed publication forgot deferred cleanup");cleanup->open();executor->finish();require(retirement.ready()&&*destroyed==1,"unpublished resource cleanup never settled");
 });
 run("failed and null factories release logical creation reservations",[]{
  ResourceRegion root;ResourceDomain physical;std::array budgets{ResourceByteBudget(4)};auto key=type();
  error("E_DEVICE_TEST",[&]{ExternalResource::makeInRegion(physical.access(),root.authority(),key,budgets,4,code(),{},[](const auto&)->std::unique_ptr<Box>{throw DataError("E_DEVICE_TEST","failure");});});
  error("E_RESOURCE_CLOSED",[&]{ExternalResource::makeInRegion(physical.access(),root.authority(),key,budgets,4,code(),{},[](const auto&)->std::unique_ptr<Box>{return {};});});
  auto retirement=root.beginClose();retirement.requestClose();require(retirement.ready()&&physical.used()==0&&budgets[0].used()==0,"failed creation kept a pending fence");
 });
 run("explicit coordinator access survives64 actual native task resumes",[]{
  RequestScope request(1000000,5000);ResourceDomain physical(1);ResourceRegion logical;auto key=type();std::array budgets{ResourceByteBudget(4)};auto destroyed=std::make_shared<std::atomic<int>>(0);auto executor=std::make_shared<ResourceExecutor>();auto output=std::make_shared<std::optional<ExternalResource>>();
  NativeContext context{request.bindResources(physical).access(),logical.authority(),key,budgets,destroyed,executor,output,0,{}, {}};
  TaskGroup group(4);auto ticket=group.spawnWithContext(nativeFactory,&context);require(group.join(ticket).scalar==42,"native task did not finish");group.finish();
  require(output->has_value()&&output->value().isOpen()&&*destroyed==0,"worker RequestScope revoked logical owner on resume exit");
  logical.close();executor->finish();require(*destroyed==1&&budgets[0].used()==0&&physical.used()==0,"explicit logical owner failed final cleanup");
 });
 run("native scope exit parks until its resource destructor physically settles",[]{
  RequestScope request(1000000,5000);ResourceDomain physical(1);ResourceRegion unused;auto key=type();std::array budgets{ResourceByteBudget(4)};auto destroyed=std::make_shared<std::atomic<int>>(0);auto executor=std::make_shared<ResourceExecutor>();auto output=std::make_shared<std::optional<ExternalResource>>();auto cleanup=std::make_shared<Gate>();auto after=std::make_shared<std::atomic<bool>>(false);
  auto helperRan=std::make_shared<std::atomic<bool>>(false);
  NativeContext context{request.bindResources(physical).access(),unused.authority(),key,budgets,destroyed,executor,output,1,cleanup,after,helperRan};
  TaskGroup group(1);group.enableResourceRegions();
  auto ticket=group.spawnWithContext(nativeScopedFactory,&context);auto helper=group.spawnWithContext(nativeReleaseFactory,&context);
  require(group.join(ticket).scalar==42&&group.join(helper).scalar==1,"native resource scope or independent helper failed");group.finish();executor->finish();
  require(helperRan->load()&&after->load()&&*destroyed==1&&physical.used()==0&&budgets[0].used()==0&&!output->value().isOpen(),"scope published early or blocked the only source worker during physical cleanup");
 });
 run("native promotion reaches root and group finish owns final retirement",[]{
  RequestScope request(1000000,5000);ResourceDomain physical(1);ResourceRegion unused;auto key=type();std::array budgets{ResourceByteBudget(4)};auto destroyed=std::make_shared<std::atomic<int>>(0);auto executor=std::make_shared<ResourceExecutor>();auto output=std::make_shared<std::optional<ExternalResource>>();auto after=std::make_shared<std::atomic<bool>>(false);
  NativeContext context{request.bindResources(physical).access(),unused.authority(),key,budgets,destroyed,executor,output,2,{},after};
  TaskGroup group(4);group.enableResourceRegions();auto ticket=group.spawnWithContext(nativeScopedFactory,&context);require(group.join(ticket).scalar==42,"promoting task failed");
  require(after->load()&&output->value().isOpen()&&*destroyed==0,"child scope closed promoted resource");group.finish();executor->finish();
  require(!output->value().isOpen()&&*destroyed==1&&physical.used()==0&&budgets[0].used()==0,"group completion left root resource open");
 });
 run("native scheduler keeps its existing256 scope depth with resource ownership",[]{
  RequestScope request(1000000,5000);ResourceDomain physical(1);ResourceRegion unused;auto key=type();std::array budgets{ResourceByteBudget(4)};auto destroyed=std::make_shared<std::atomic<int>>(0);auto executor=std::make_shared<ResourceExecutor>();auto output=std::make_shared<std::optional<ExternalResource>>();auto after=std::make_shared<std::atomic<bool>>(false);
  NativeContext context{request.bindResources(physical).access(),unused.authority(),key,budgets,destroyed,executor,output,3,{},after};
  TaskGroup group(4);group.enableResourceRegions();auto ticket=group.spawnWithContext(nativeScopedFactory,&context);require(group.join(ticket).scalar==42,"nested native resources failed");group.finish();executor->finish();
  require(after->load()&&*destroyed==1&&physical.used()==0&&budgets[0].used()==0,"nested native region cleanup changed task depth or leaked quota");
 });
 std::cout<<"RESOURCE REGION CASES "<<cases<<std::endl;return 0;
}catch(const std::exception &e){std::cerr<<e.what()<<std::endl;return 1;}}
