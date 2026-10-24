#include "nex_external_resource.h"
#include <array>
#include <atomic>
#include <chrono>
#include <iostream>
#include <thread>

using namespace nexrt;
static void require(bool value){if(!value)throw DataError("E_TEST","resource dependency invariant failed");}
template<class F>static void expect(const char *code,F action){
  try{action();}catch(const DataError &e){if(e.code==code)return;throw;}
  throw DataError("E_TEST",std::string("expected ")+code);
}
struct Trace {
  std::mutex mutex;std::string events;std::atomic<bool> violation{false};
  Trace(){events.reserve(4096);}
  void add(char value)noexcept{std::lock_guard lock(mutex);events.push_back(value);}
  std::string text(){std::lock_guard lock(mutex);return events;}
};
struct Object {
  std::shared_ptr<Trace> trace;char label;
  std::shared_ptr<std::atomic<bool>> alive=std::make_shared<std::atomic<bool>>(true);
  std::vector<std::shared_ptr<std::atomic<bool>>> parents;
  Object(std::shared_ptr<Trace> trace,char label,std::vector<std::shared_ptr<std::atomic<bool>>> parents={})
      :trace(std::move(trace)),label(label),parents(std::move(parents)){}
  ~Object()noexcept{for(const auto &parent:parents)if(!parent->load())trace->violation=true;alive->store(false);trace->add(label);}
};
struct Host {
  ResourceDomain access{4096};ResourceByteBudget bytes{8192};
  ExternalResourceType<Object> type{"owned::Dependent",std::string(64,'d')};
  std::shared_ptr<void> code=std::make_shared<int>(1);
  std::shared_ptr<Trace> trace=std::make_shared<Trace>();
  ExternalResource make(char label,std::span<const ExternalResource> parents={},ResourceRegionAuthority actor={},std::shared_ptr<ResourceExecutor> executor={}){
    std::vector<std::shared_ptr<std::atomic<bool>>> alive;
    for(const auto &parent:parents){auto borrow=actor?parent.borrowInRegion(actor,type):parent.borrow(type);alive.push_back(borrow.value(type).alive);}
    auto factory=[trace=trace,label,alive=std::move(alive)](const ResourcePermit &permit){permit.check();return std::make_unique<Object>(trace,label,alive);};
    if(actor)return ExternalResource::makeInRegion(access.access(),actor,type,std::span(&bytes,1),8,code,executor,factory,false,parents);
    if(executor)return ExternalResource::makeOnExecutor(access,type,std::span(&bytes,1),8,code,executor,factory,parents);
    return ExternalResource::make(access,type,std::span(&bytes,1),8,code,factory,parents);
  }
};
static void close(ResourceRegion &region){auto retired=region.beginClose();retired.requestClose();while(!retired.ready())std::this_thread::yield();}
int main()try{
  size_t checks=0;
  auto passed=[&](const char *name){++checks;std::cout<<"PASS "<<name<<std::endl;};
  {
    Host h;auto parent=h.make('P');std::array parents{parent};auto child=h.make('C',parents);
    require(child.dependencyCount()==1&&child.dependencyDepth()==1);require(parent.close());require(h.trace->text().empty()&&h.bytes.used()==16);
    require(child.isOpen());{auto borrow=child.borrow(h.type);require(borrow.value(h.type).parents[0]->load());}
    require(child.close());require(h.trace->text()=="CP"&&h.bytes.used()==0&&!h.trace->violation);
    // Closed aliases retain only metadata, never an extra physical parent lease.
    require(parent.identity()&&child.identity());passed("parent logical close preserves child physical lease until child destruction");
  }
  {
    Host h;auto parent=h.make('P');std::array parents{parent};auto first=h.make('A',parents),second=h.make('B',parents);
    require(parent.close());require(first.close());require(h.trace->text()=="A"&&h.bytes.used()==16);
    require(second.close());require(h.trace->text()=="ABP"&&h.bytes.used()==0&&!h.trace->violation);passed("shared parent quota survives the first child");
  }
  {
    Host h;auto parent=h.make('P');std::array repeated{parent,parent};auto child=h.make('C',repeated);
    require(child.dependencyCount()==1);require(parent.close());auto borrow=child.borrow(h.type);require(child.close());
    require(h.trace->text().empty()&&h.bytes.used()==16);borrow={};require(h.trace->text()=="CP"&&h.bytes.used()==0);passed("aliases deduplicate and admitted child borrows retain both payloads");
  }
  {
    Host h;auto parent=h.make('P');std::array parents{parent};require(parent.close());bool called=false;
    expect("E_RESOURCE_CLOSED",[&]{(void)ExternalResource::make(h.access,h.type,std::span(&h.bytes,1),8,h.code,
      [&](const ResourcePermit&){called=true;return std::make_unique<Object>(h.trace,'C');},parents);});
    require(!called&&h.bytes.used()==0);passed("ended parent is rejected before child factory");
  }
  {
    Host h;ResourceDomain other;auto parent=h.make('P');std::array parents{parent};auto child=ExternalResource::make(other,h.type,std::span(&h.bytes,1),8,h.code,
      [&](const ResourcePermit&){return std::make_unique<Object>(h.trace,'C');},parents);
    h.access.revoke();require(!child.isOpen());expect("E_RESOURCE_SCOPE",[&]{(void)child.borrow(h.type);});
    child.close();require(h.trace->text()=="CP"&&h.bytes.used()==0);passed("parent grant revocation denies fresh child use");
  }
  {
    Host h;ResourceDomain other;auto parent=h.make('P');std::array parents{parent};
    expect("E_RESOURCE_SCOPE",[&]{(void)ExternalResource::make(other,h.type,std::span(&h.bytes,1),8,h.code,
      [&](const ResourcePermit&){auto value=std::make_unique<Object>(h.trace,'C');h.access.revoke();return value;},parents);});
    require(h.trace->text()=="CP"&&h.bytes.used()==0);passed("revocation during factory cleans unpublished child before parent");
  }
  for(auto family:{ResourceRegionFamily::Native,ResourceRegionFamily::Reference}){
    Host h;ResourceRegion root(family);auto inner=root.child();auto parent=h.make('P',{},inner.authority());std::array parents{parent};auto child=h.make('C',parents,inner.authority());
    child.promoteRegion(inner.authority(),root.authority());close(inner);
    require(parent.isOpen()&&child.isOpen());{auto borrow=child.borrowInRegion(root.authority(),h.type);require(borrow.value(h.type).parents[0]->load());}
    close(root);require(h.trace->text()=="CP"&&h.bytes.used()==0&&!h.trace->violation);
    passed(family==ResourceRegionFamily::Native?"native promotion includes hidden parent":"reference promotion includes hidden parent");
  }
  {
    Host h;ResourceRegion request(ResourceRegionFamily::Request,{.owners=1});auto group=ResourceRegion::inRequest(ResourceRegionFamily::Native,request.authority());
    auto parent=h.make('P',{},group.authority());std::array parents{parent};auto child=h.make('C',parents,group.authority());
    expect("E_RESOURCE_REGION_LIMIT",[&]{ExternalResource::transferRegions(std::span(&child,1),group.authority(),request.authority());});
    close(group);require(!child.isOpen()&&!parent.isOpen()&&h.trace->text()=="CP"&&h.bytes.used()==0);passed("hidden parent destination capacity fails atomically");
  }
  {
    Host h;ResourceRegion root;auto inner=root.child(),sibling=root.child();auto parent=h.make('P',{},inner.authority());std::array parents{parent};auto child=h.make('C',parents,inner.authority()),other=h.make('O',{},sibling.authority());
    std::array values{child,other};expect("E_RESOURCE_SCOPE",[&]{ExternalResource::transferRegions(values,inner.authority(),root.authority());});
    close(inner);require(!child.isOpen()&&!parent.isOpen()&&other.isOpen()&&h.bytes.used()==8);close(sibling);require(h.bytes.used()==0);passed("mixed sibling batch never partly promotes a dependency graph");
  }
  {
    Host h;ResourceRegion root;auto parent=h.make('P',{},root.authority());std::array parents{parent};bool called=false;
    expect("E_RESOURCE_SCOPE",[&]{(void)ExternalResource::make(h.access,h.type,std::span(&h.bytes,1),8,h.code,
      [&](const ResourcePermit&){called=true;return std::make_unique<Object>(h.trace,'C');},parents);});
    require(!called);close(root);require(h.bytes.used()==0);passed("scoped parent cannot enter an unscoped child factory");
  }
  {
    Host h;auto parent=h.make('P');std::array one{parent};auto a=h.make('A',one),b=h.make('B',one);std::array two{a,b};auto out=h.make('O',two);
    require(out.dependencyCount()==3&&out.dependencyDepth()==2);parent.close();a.close();b.close();require(h.trace->text().empty());out.close();
    auto text=h.trace->text();require(text.size()==4&&text.front()=='O'&&text.back()=='P'&&h.bytes.used()==0&&!h.trace->violation);passed("diamond graph deduplicates ancestry and preserves destruction order");
  }
  {
    Host h;auto value=h.make('P');for(size_t i=1;i<=256;++i){std::array parents{value};value=h.make('C',parents);require(value.dependencyDepth()==i);}
    std::array parents{value};bool called=false;expect("E_RESOURCE_DEPENDENCY_LIMIT",[&]{(void)ExternalResource::make(h.access,h.type,std::span(&h.bytes,1),8,h.code,
      [&](const ResourcePermit&){called=true;return std::make_unique<Object>(h.trace,'X');},parents);});
    require(!called);value.close();require(h.bytes.used()==0&&!h.trace->violation);passed("actual depth256 succeeds and depth257 rejects before factory");
  }
  {
    Host h;auto parent=h.make('P');std::array<ExternalResource,17> parents;parents.fill(parent);bool called=false;
    expect("E_RESOURCE_DEPENDENCY_LIMIT",[&]{(void)ExternalResource::make(h.access,h.type,std::span(&h.bytes,1),8,h.code,
      [&](const ResourcePermit&){called=true;return std::make_unique<Object>(h.trace,'X');},parents);});
    require(!called);parent.close();require(h.bytes.used()==0);passed("parent input bound rejects before side effects");
  }
  {
    Host h;auto executor=std::make_shared<ResourceExecutor>();ResourceRegion root;auto parent=h.make('P',{},root.authority(),executor);std::array parents{parent};auto child=h.make('C',parents,root.authority(),executor);
    parent.close();executor->close();child.close();auto retired=root.beginClose();retired.requestClose();
    auto deadline=std::chrono::steady_clock::now()+std::chrono::seconds(5);
    while(!retired.ready()){require(std::chrono::steady_clock::now()<deadline);std::this_thread::yield();}
    executor->finish();require(h.trace->text()=="CP"&&h.bytes.used()==0&&executor->stats().resources==0);passed("reserved executor cleanup and both physical fences settle after closure");
  }
  {
    Host h;ResourceByteBudget tiny{8};auto parent=ExternalResource::make(h.access,h.type,std::span(&tiny,1),8,h.code,
      [&](const ResourcePermit&){return std::make_unique<Object>(h.trace,'P');});std::array parents{parent};bool called=false;
    expect("E_RESOURCE_BYTES",[&]{(void)ExternalResource::make(h.access,h.type,std::span(&tiny,1),8,h.code,
      [&](const ResourcePermit&){called=true;return std::make_unique<Object>(h.trace,'C');},parents);});
    require(!called&&tiny.used()==8&&h.access.used()==1);parent.close();require(tiny.used()==0&&h.access.used()==0);passed("child capacity rejection preserves parent accounting without factory side effects");
  }
  {
    struct Pin {
      std::shared_ptr<Trace> trace;ResourceByteBudget *budget;char label;
      Pin(std::shared_ptr<Trace> trace,ResourceByteBudget *budget,char label):trace(std::move(trace)),budget(budget),label(label){}
      ~Pin()noexcept{if(!budget->used())trace->violation=true;trace->add(label);}
    };
    Host h;auto p=std::make_shared<Pin>(h.trace,&h.bytes,'p'),c=std::make_shared<Pin>(h.trace,&h.bytes,'c');
    auto parent=ExternalResource::make(h.access,h.type,std::span(&h.bytes,1),8,p,[&](const ResourcePermit&){return std::make_unique<Object>(h.trace,'P');});
    std::array parents{parent};auto child=ExternalResource::make(h.access,h.type,std::span(&h.bytes,1),8,c,[&](const ResourcePermit&){return std::make_unique<Object>(h.trace,'C');},parents);
    p.reset();c.reset();parent.close();require(h.trace->text().empty());child.close();
    require(h.trace->text()=="CcPp"&&h.bytes.used()==0&&!h.trace->violation);passed("child destructor and code pin settle before parent destructor pin and quota");
  }
  {
    Host h;ResourceByteBudget large{65536};ResourceDomain destination;std::array<ExternalResource,16> leaves;
    auto make=[&](std::span<const ExternalResource> parents){return ExternalResource::make(h.access,h.type,std::span(&large,1),8,h.code,
      [&](const ResourcePermit&){return std::make_unique<Object>(h.trace,'P');},parents);};
    for(auto &leaf:leaves){leaf=make({});for(size_t depth=1;depth<256;++depth){std::array parents{leaf};leaf=make(parents);}}
    require(h.access.used()==4096&&large.used()==32768);bool called=false;
    expect("E_RESOURCE_DEPENDENCY_LIMIT",[&]{(void)ExternalResource::make(destination,h.type,std::span(&large,1),8,h.code,
      [&](const ResourcePermit&){called=true;return std::make_unique<Object>(h.trace,'X');},leaves);});
    require(!called&&destination.used()==0&&h.access.used()==4096);for(auto &leaf:leaves)leaf.close();
    require(h.access.used()==0&&large.used()==0);passed("actual4096 parent objects reject an oversized dependency closure before publication");
  }
  {
    Host h;ResourceRegion root;auto parent=h.make('P');std::array parents{parent};bool called=false;
    expect("E_RESOURCE_SCOPE",[&]{(void)ExternalResource::makeInRegion(h.access.access(),root.authority(),h.type,std::span(&h.bytes,1),8,h.code,{},
      [&](const ResourcePermit&){called=true;return std::make_unique<Object>(h.trace,'C');},false,parents);});
    require(!called);close(root);require(parent.isOpen()&&h.bytes.used()==8);parent.close();require(h.bytes.used()==0);passed("unscoped parent cannot fabricate a scoped dependency owner or leave a phantom fence");
  }
  {
    Host h;ResourceRegion root;auto inner=root.child();auto parent=h.make('P',{},inner.authority());std::array parents{parent};auto child=h.make('C',parents,inner.authority());
    ExternalResource::transferRegions(std::span(&child,1),inner.authority(),root.authority(),false);close(inner);
    require(!child.isOpen()&&!parent.isOpen()&&h.bytes.used()==0);passed("dependency transfer preflight remains read-only");
  }
  std::cout<<"RESOURCE DEPENDENCIES "<<checks<<" CASES PASSED\n";return 0;
}catch(const DataError &e){std::cerr<<e.code<<": "<<e.what()<<'\n';return 1;}
