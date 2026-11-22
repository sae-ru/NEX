#include "nex_host.h"
#include "nex_cell_host.h"
#include "nex_cells.h"
#include <atomic>
#include <memory>
#include <stdexcept>
#include <thread>

using namespace nexrt;
namespace {
void require(bool value,const char *message){if(!value)throw std::runtime_error(message);}
template<class F>void dataError(const char *code,F body){try{body();}catch(const DataError &error){require(error.code==code,"wrong request context diagnostic");return;}throw std::runtime_error("expected request context diagnostic");}
template<class F>void trap(const char *code,int64_t line,F body){try{body();}catch(const Trap &error){require(error.code==code&&error.line==line,"request trap lost code/line");return;}throw std::runtime_error("expected request trap");}
unsigned created=0,destroyed=0,denied=0;
void *factory(void *){++created;return new int(42);}
void *other(void *){return new int(43);}
void destroy(void *value)noexcept{
  delete static_cast<int*>(value);++destroyed;
  try{(void)managedReferenceContext(factory,nullptr,destroy);}catch(const DataError &error){if(error.code=="E_CELL_CONTEXT")++denied;}
}
void *failed(void *){throw std::bad_alloc();}
void *empty(void *){return nullptr;}
void *reentrant(void *){
  dataError("E_CELL_CONTEXT",[]{managedReferenceContext(factory,nullptr,destroy);});
  return factory(nullptr);
}
void *endRequest(void *argument){static_cast<std::unique_ptr<RequestScope>*>(argument)->reset();return factory(nullptr);}
bool handlesBeforeHeap=false;
void *heapFactory(void *){return new CellHeap;}
void heapDestroy(void *value)noexcept{delete static_cast<CellHeap*>(value);}
struct CleanupProbe final:Data {
  CellHeap *heap;
  explicit CleanupProbe(CellHeap *heap):Data(Data::List),heap(heap){}
  ~CleanupProbe(){try{handlesBeforeHeap=heap->stats().cells==1;}catch(...){handlesBeforeHeap=false;}}
};
int64_t enclosingApplication(int64_t,const char *const*){
  trap("E_CELL_CONTEXT",1,[]{nex_cell_request_enter(1);});
  auto outer=nex_cell_new_i64(42,0,1);Value original=readHandle(outer),escaped;
  {
    RequestScope request;auto inner=nex_cell_new_i64(7,0,2);escaped=readHandle(inner);
    require(nex_cell_read_i64(inner,0,3)==7,"request did not create its own cell");
    auto foreign=makeHandle(original);trap("E_CELL_HEAP",4,[&]{nex_cell_read_i64(foreign,0,4);});
  }
  require(nex_cell_read_i64(outer,0,5)==42,"request exit closed enclosing application heap");
  require(escaped.object->values.empty(),"closed request retained its mutable payload");
  original={};escaped={};nex_release(outer);return 0;
}
int64_t endedInsideFactory(int64_t,const char *const*){
  auto outer=managedReferenceContext(factory,nullptr,destroy);
  auto request=std::make_unique<RequestScope>();
  dataError("E_CELL_CONTEXT",[&]{managedReferenceContext(endRequest,&request,destroy);});
  require(!request&&!inRequestScope(),"factory did not end its request");
  require(managedReferenceContext(factory,nullptr,destroy)==outer,"ended factory switched to/replaced application attachment");
  return 0;
}
}
unsigned testManagedReferenceRequests(){
  const auto baseline=liveObjects.load();unsigned cases=0;
  dataError("E_CELL_CONTEXT",[]{managedReferenceContext(factory,nullptr,destroy);});++cases;
  created=destroyed=denied=0;
  {
    RequestScope request;
    try{managedReferenceContext(failed,nullptr,destroy);throw std::runtime_error("failed factory succeeded");}catch(const std::bad_alloc&){}
    dataError("E_CELL_CONTEXT",[]{managedReferenceContext(empty,nullptr,destroy);});
    auto owner=managedReferenceContext(factory,nullptr,destroy);
    require(owner==managedReferenceContext(factory,nullptr,destroy),"request replaced a reused attachment");
    dataError("E_CELL_CONTEXT",[]{managedReferenceContext(other,nullptr,destroy);});
    dataError("E_CELL_CONTEXT",[]{managedReferenceContext(factory,nullptr,destroy,true);});
  }
  require(created==1&&destroyed==1&&denied==1,"request attachment factory/destructor counts differ");++cases;
  {RequestScope request;managedReferenceContext(reentrant,nullptr,destroy);}
  require(created==2&&destroyed==2&&denied==2,"reentrant creation guard differs");++cases;
  for(unsigned i=0;i<64;++i){RequestScope request;nex_cell_context_limits(2,8,16,10);auto cell=nex_cell_new_i64(i,0,11);nex_cell_write_i64(cell,i+1,0,12);require(nex_cell_read_i64(cell,0,13)==i+1,"requests mixed cell state");}
  require(liveObjects.load()==baseline,"repeated request roots leaked values");++cases;
  {
    Value escaped,snapshot;
    {RequestScope request;auto text=makeHandle(Value(string("before")));auto cell=nex_cell_new_heap(text,20);escaped=readHandle(cell);snapshot=readHandle(nex_cell_read_heap(cell,21));}
    require(escaped.object->values.empty()&&snapshot.object->text=="before","request close damaged snapshot or retained cell payload");
    {RequestScope request;auto foreign=makeHandle(escaped);trap("E_CELL_HEAP",22,[&]{nex_cell_read_heap(foreign,22);});}
  }
  require(liveObjects.load()==baseline,"escaped cell/snapshot retirement leaked");++cases;
  handlesBeforeHeap=false;
  {RequestScope request;auto heap=static_cast<CellHeap*>(managedReferenceContext(heapFactory,nullptr,heapDestroy));auto cell=heap->create(Value(int64_t(42)));makeHandle(cell);makeHandle(Value(makeValueOwner<CleanupProbe>(heap)));}
  require(handlesBeforeHeap&&liveObjects.load()==baseline,"request closed heap before retiring source handles");++cases;
  {
    RequestScope request(2);auto cell=nex_cell_new_i64(1,0,30);
    trap("E_LIMIT",31,[&]{nex_cell_read_i64(cell,0,31);});
    trap("E_LIMIT",0,[]{managedReferenceContext(factory,nullptr,destroy);});
  }++cases;
  {
    RequestScope request;auto cell=nex_cell_new_i64(1,0,40);
    std::thread cancellation([&]{request.cancel();});cancellation.join();
    trap("E_CANCELLED",41,[&]{nex_cell_read_i64(cell,0,41);});
    trap("E_CANCELLED",0,[]{managedReferenceContext(factory,nullptr,destroy);});
  }++cases;
  {
    RequestScope request;auto cell=nex_cell_new_i64(1,0,42);unsigned polls=0;
    request.setCancellation([&]{return ++polls==2;});
    trap("E_CANCELLED",43,[&]{nex_cell_write_i64(cell,42,0,43);});
    require(readHandle(cell).object->values[0].scalar==42,"post-write cancellation rolled back the completed write");
  }++cases;
  {
    const auto before=created;
    RequestScope request(1000,0);
    trap("E_TIMEOUT",0,[]{managedReferenceContext(factory,nullptr,destroy);});
    require(created==before,"expired request invoked a reference factory");
    trap("E_TIMEOUT",50,[]{nex_cell_new_i64(1,0,50);});
  }++cases;
  {
    auto request=std::make_unique<RequestScope>();auto cell=nex_cell_new_i64(1,0,60);
    request->setCancellation([&]{request.reset();return false;});
    trap("E_CANCELLED",61,[&]{nex_cell_read_i64(cell,0,61);});
    require(!request&&!inRequestScope(),"ending a request in a poll left the request active");
  }
  require(liveObjects.load()==baseline,"request callback cancellation retained values");++cases;
  require(nex_application_run(reinterpret_cast<void*>(enclosingApplication),0,nullptr)==0,"request/application context separation failed");++cases;
  const auto before=destroyed;
  require(nex_application_run(reinterpret_cast<void*>(endedInsideFactory),0,nullptr)==0,"request ended during creation was not rejected");
  require(destroyed==before+2&&denied==destroyed,"ended factory leaked or revived an attachment");++cases;
  std::atomic<unsigned> completed{0};std::exception_ptr failures[2];std::jthread workers[2];
  for(unsigned id=0;id<2;++id)workers[id]=std::jthread([&,id]{try{for(unsigned i=0;i<100;++i){RequestScope request;auto cell=nex_cell_new_i64(id*1000+i,0,70);nex_cell_collect(71);require(nex_cell_read_i64(cell,0,72)==id*1000+i,"parallel request contexts shared state");++completed;}}catch(...){failures[id]=std::current_exception();}});
  for(auto &worker:workers)worker.join();for(auto &failure:failures)if(failure)std::rethrow_exception(failure);
  require(completed==200&&liveObjects.load()==baseline,"independent request threads leaked or lost a result");++cases;
  return cases;
}
