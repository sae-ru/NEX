#include "nex_external_resource.h"
#include "nex_task_values.h"
#include <array>
#include <atomic>
#include <iostream>
#include <thread>

using namespace nexrt;
template<class F> static void expect(const char *code,F action){
  try{action();}catch(const DataError &error){if(error.code==code)return;throw;}
  throw DataError("E_TEST",std::string("expected ")+code);
}
static void require(bool value){if(!value)throw DataError("E_TEST","resource transfer invariant failed");}
struct Object {std::shared_ptr<std::atomic<size_t>> destroyed;explicit Object(std::shared_ptr<std::atomic<size_t>> counter):destroyed(std::move(counter)){}~Object()noexcept{++*destroyed;}};
struct Host {
  ResourceDomain access{16};ResourceByteBudget bytes{1024};
  ExternalResourceType<Object> type{"owned::Batch",std::string(64,'a')};
  std::shared_ptr<void> code=std::make_shared<int>(1);
  std::shared_ptr<std::atomic<size_t>> destroyed=std::make_shared<std::atomic<size_t>>(0);
  ExternalResource make(const ResourceRegionAuthority &region){
    return ExternalResource::makeInRegion(access.access(),region,type,std::span<const ResourceByteBudget>(&bytes,1),8,code,{},[&](const ResourcePermit &permit){permit.check();return std::make_unique<Object>(destroyed);});
  }
};
static void close(ResourceRegion &region){auto retirement=region.beginClose();retirement.requestClose();while(!retirement.ready())std::this_thread::yield();}
static TaskBody mixedSnapshot(TaskGroup &group,Value,Value,const void *context){
  auto &host=*static_cast<Host*>(const_cast<void*>(context));
  auto outer=group.openScope(1),inner=group.openScope(1);auto owner=host.make(group.resourceAuthority());
  auto record=std::make_shared<Data>(Data::Record);record->text="test::Mixed";
  // The walker sees the resource first, then discovers an escaping task scope.
  record->values={taskScopeValue(group,inner),Value(externalValue(owner))};
  expect("E_TASK_SCOPE",[&]{validateTaskSnapshot(group,Value(record),outer);});
  co_await group.leaveScope(inner);require(!owner.isOpen());
  co_await group.leaveScope(outer);co_return Value(42);
}
int main()try{
  size_t checks=0;
  {
    Host host;ResourceRegion root;auto first=root.child(),sibling=root.child();
    auto a=host.make(first.authority()),b=host.make(sibling.authority());
    std::array values{a,b};
    expect("E_RESOURCE_SCOPE",[&]{ExternalResource::transferRegions(values,first.authority(),root.authority());});
    close(first);require(!a.isOpen()&&b.isOpen()&&*host.destroyed==1);++checks;
  }
  {
    Host host;ResourceRegion root;auto first=root.child(),ended=root.child();
    auto a=host.make(first.authority()),b=host.make(ended.authority());close(ended);
    std::array values{a,b};expect("E_RESOURCE_SCOPE",[&]{ExternalResource::transferRegions(values,first.authority(),root.authority());});
    close(first);require(!a.isOpen());++checks;
  }
  {
    Host host;ResourceRegion root,foreign;auto child=root.child();auto a=host.make(child.authority());
    expect("E_RESOURCE_SCOPE",[&]{ExternalResource::transferRegions(std::span(&a,1),child.authority(),foreign.authority());});
    close(child);require(!a.isOpen());++checks;
  }
  {
    Host host;ResourceRegionLimits limits;limits.owners=1;ResourceRegion request(ResourceRegionFamily::Request,limits);
    auto group=ResourceRegion::inRequest(ResourceRegionFamily::Native,request.authority());
    auto a=host.make(group.authority()),b=host.make(group.authority());std::array values{a,b};
    expect("E_RESOURCE_REGION_LIMIT",[&]{ExternalResource::transferRegions(values,group.authority(),request.authority());});
    close(group);require(!a.isOpen()&&!b.isOpen()&&host.bytes.used()==0&&*host.destroyed==2);
    auto available=host.make(request.authority());require(available.isOpen());++checks;
  }
  {
    Host host;ResourceRegion request(ResourceRegionFamily::Request);auto group=ResourceRegion::inRequest(ResourceRegionFamily::Native,request.authority());
    auto a=host.make(group.authority()),alias=a,b=host.make(group.authority());std::array values{a,b,a};
    ExternalResource::transferRegions(values,group.authority(),request.authority());close(group);
    require(a.isOpen()&&b.isOpen()&&alias.identity()==a.identity()&&host.bytes.used()==16);
    close(request);require(!a.isOpen()&&!b.isOpen()&&host.bytes.used()==0&&*host.destroyed==2);++checks;
  }
  {
    Host host;ResourceRegion request(ResourceRegionFamily::Request);auto owner=host.make(request.authority());
    auto group=ResourceRegion::inRequest(ResourceRegionFamily::Reference,request.authority());
    ExternalResource::transferRegions(std::span(&owner,1),group.authority(),group.authority());close(group);
    require(owner.isOpen());close(request);require(!owner.isOpen());++checks;
  }
  {
    Host host;ResourceRegion root;auto child=root.child();auto owner=host.make(child.authority());
    ExternalResource::transferRegions(std::span(&owner,1),child.authority(),root.authority(),false);
    close(child);require(!owner.isOpen());++checks;
  }
  {
    Host host;ResourceRegion root;auto child=root.child();auto owner=host.make(child.authority());require(owner.close());
    ExternalResource::transferRegions(std::span(&owner,1),child.authority(),root.authority());close(child);
    require(!owner.isOpen()&&host.bytes.used()==0);expect("E_RESOURCE_CLOSED",[&]{(void)owner.borrowInRegion(root.authority(),host.type);});++checks;
  }
  {
    Host host;ResourceRegion root;auto child=root.child();auto owner=host.make(child.authority());
    std::array values{owner,ExternalResource{}};expect("E_RESOURCE_SCOPE",[&]{ExternalResource::transferRegions(values,child.authority(),root.authority());});
    close(child);require(!owner.isOpen());++checks;
  }
  {
    RequestScope request;Host host;TaskGroup group(1);group.enableResourceRegions({},true);
    auto result=group.join(group.spawnWithContext(mixedSnapshot,&host));group.finish();
    require(result.scalar==42&&host.bytes.used()==0&&*host.destroyed==1);++checks;
  }
  std::cout<<"ATOMIC RESOURCE TRANSFERS "<<checks<<" CASES PASSED\n";return 0;
}catch(const DataError &error){std::cerr<<error.code<<": "<<error.what()<<'\n';return 1;}
