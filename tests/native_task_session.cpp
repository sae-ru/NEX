#include "host_test.h"
#include "nex_task_session.h"
#include <atomic>
#include <iostream>
#include <thread>

namespace {
using namespace nexrt;
void require(bool value,const char *message){if(!value)throw std::runtime_error(message);}
template<class F> void trap(const std::string &code,F action){
  try{action();}catch(const Trap &error){require(error.code==code,("expected "+code+", got "+error.code+": "+std::string(trapMessage(error))).c_str());return;}
  throw std::runtime_error("expected session error "+code);
}
int64_t make(void *frame){auto *value=nex_cell_new_i64(nex_task_frame_get_i64(frame,0,0),0,0);nex_task_frame_return_heap(frame,value);return 0;}
int64_t get(void *frame){auto value=nex_cell_read_i64(nex_task_frame_get_heap(frame,0),0,0);nex_task_frame_return_i64(frame,value,0);return 0;}
int64_t add(void *frame){
  if(nex_task_frame_pc(frame)==0){nex_task_frame_set_pc(frame,1);return 1;}
  auto *value=nex_task_frame_get_heap(frame,0);nex_cell_write_i64(value,nex_cell_read_i64(value,0,0)+nex_task_frame_get_i64(frame,1,0),0,0);
  nex_task_frame_return_heap(frame,value);return 0;
}
int64_t fail(void *frame){
  auto value=static_cast<NativeTaskFrame*>(frame)->read(0,3);
  throw NativeSourceException("session::Fault","typed session error","",0,
    std::make_shared<const SourceErrorPayload>(std::string(64,'a'),std::move(value)));
}
int64_t spin(void*){return 1;}
int64_t fatal(void*){runtimeFail("E_ASSERT","session fatal exit",0);}
int64_t cycle(void *frame){
  auto empty=Data::make(Data::List);auto *cell=nex_cell_new_heap(makeHandle(Value(std::move(empty))),0);
  auto link=Data::make(Data::List);link->values={readHandle(cell)};
  nex_cell_write_heap(cell,makeHandle(Value(std::move(link))),0);nex_task_frame_return_heap(frame,cell);return 0;
}
const int64_t integer[]={0},heap[]={3},heapInteger[]={3,0},parameters[]={0,1};
const TaskCodeDescriptor makeCode{make,integer,parameters,nullptr,nullptr,taskCodeManagedReferencesABI,1,1,0,3,taskCodeDeclaredState};
const TaskCodeDescriptor getCode{get,heap,parameters,nullptr,nullptr,taskCodeManagedReferencesABI,1,1,0,0,taskCodeDeclaredState};
const TaskCodeDescriptor addCode{add,heapInteger,parameters,nullptr,nullptr,taskCodeManagedReferencesABI,2,2,0,3,taskCodeDeclaredState|taskCodeDeclaredTask};
const TaskCodeDescriptor failCode{fail,heap,parameters,nullptr,nullptr,taskCodeManagedReferencesABI,1,1,0,4,taskCodeDeclaredThrow|taskCodeDeclaredState};
const TaskCodeDescriptor spinCode{spin,nullptr,nullptr,nullptr,nullptr,taskCodeManagedReferencesABI,0,0,0,4,taskCodeDeclaredTask};
const TaskCodeDescriptor fatalCode{fatal,nullptr,nullptr,nullptr,nullptr,taskCodeManagedReferencesABI,0,0,0,4,0};
const TaskCodeDescriptor cycleCode{cycle,nullptr,nullptr,nullptr,nullptr,taskCodeManagedReferencesABI,0,0,0,3,taskCodeDeclaredState};
int kernel(){
  auto baseline=liveObjects.load();unsigned cases=0;
  {
    PersistentRequestContext context;RequestScope call(context,100,1);
    std::this_thread::sleep_for(std::chrono::milliseconds(5));
    trap("E_TIMEOUT",[]{(void)managedReferenceContext(nullptr,nullptr,nullptr);});
  }
  {
    NativeTaskSession first,second;auto a=first.invoke(makeCode,{Value(40)}),b=second.invoke(makeCode,{Value(7)});
    // Idle time belongs to the host, not to a previously completed deadline.
    NativeTaskInvocationOptions shortCall;shortCall.limits.timeoutMs=100;
    require(first.invoke(getCode,{a},shortCall).scalar==40,"initial session read differs");
    std::this_thread::sleep_for(std::chrono::milliseconds(150));
    for(unsigned i=0;i<64;++i){auto copy=first.invoke(addCode,{a,Value(1)});require(copy.object==a.object,"invocation copied cell identity");}
    require(first.invoke(getCode,{a}).scalar==104&&second.invoke(getCode,{b}).scalar==7,"independent session state mixed");++cases;
    trap("E_CELL_HEAP",[&]{second.invoke(getCode,{a});});
    require(!second.closed()&&second.invoke(getCode,{b}).scalar==7,"rejected foreign cell destroyed healthy session");++cases;
    trap("E_TASK_STATE",[&]{first.invoke(makeCode,{Value(1,true)});});
    auto old=makeCode;old.abi=taskCodeTypedSourceExceptionABI;
    trap("E_TASK_SESSION_ABI",[&]{first.invoke(old,{Value(1)});});
    require(first.invoke(getCode,{a}).scalar==104,"preflight error changed source state");++cases;
    try{first.invoke(failCode,{a});throw std::runtime_error("source packet disappeared");}
    catch(const NativeSourceException &error){require(error.payload&&error.payload->value.object==a.object,"source packet lost persistent cell");}
    require(!first.closed()&&first.invoke(getCode,{a}).scalar==104,"typed error ended session");++cases;
    auto loop=first.invoke(cycleCode);WeakValueOwner<Data> weak=loop.object;loop=Value();
    auto collected=first.collect();require(collected.reclaimedCells==1&&weak.expired(),"idle collection retained cycle");++cases;
    std::exception_ptr failure;
    std::jthread foreign([&]{try{trap("E_CONTEXT",[&]{first.invoke(getCode,{a});});}catch(...){failure=std::current_exception();}});foreign.join();if(failure)std::rethrow_exception(failure);
    require(!first.closed()&&!first.cancel(),"foreign-thread preflight or idle cancel ended session");++cases;
    auto stats=first.statistics();require(stats.heap.cells==1&&stats.sourceErrors==1&&stats.invocations>64,"session statistics differ");
    first.finish();require(first.closed()&&first.statistics().heap.cells==0,"explicit close left live heap");
    trap("E_CONTEXT",[&]{first.invoke(getCode,{a});});
    trap("E_CELL_HEAP",[&]{second.invoke(getCode,{a});});second.finish();++cases;
  }
  for(const auto &reason:{std::string("E_LIMIT"),std::string("E_TIMEOUT"),std::string("E_CANCELLED"),std::string("E_RUNTIME"),std::string("E_ASSERT")}){
    NativeTaskSession session;auto value=session.invoke(makeCode,{Value(1)});NativeTaskInvocationOptions options;unsigned polls=0;
    if(reason=="E_LIMIT")options.limits.steps=50;
    if(reason=="E_TIMEOUT"){options.limits.steps=maximumTaskExecutionSteps;options.limits.timeoutMs=5;}
    if(reason=="E_CANCELLED")options.cancelled=[&]{return ++polls>20;};
    if(reason=="E_RUNTIME")options.cancelled=[&]() -> bool {if(++polls>20)throw std::runtime_error("host callback failed");return false;};
    trap(reason,[&]{session.invoke(reason=="E_ASSERT"?fatalCode:spinCode,{},options);});
    require(session.closed()&&session.statistics().fatalExits==1,"fatal call did not close persistent owner");session.finish();++cases;
  }
  {
    NativeTaskSession session;auto value=session.invoke(makeCode,{Value(1)});std::atomic<bool> active=false,cancelled=false;
    std::jthread canceller([&]{while(!active.load())std::this_thread::yield();cancelled=session.cancel();});
    NativeTaskInvocationOptions options;options.limits.steps=maximumTaskExecutionSteps;options.cancelled=[&]{active=true;return false;};
    trap("E_CANCELLED",[&]{session.invoke(spinCode,{},options);});canceller.join();require(cancelled&&session.closed(),"external cancellation was lost");session.finish();++cases;
  }
  {
    auto session=std::make_unique<NativeTaskSession>();auto value=session->invoke(makeCode,{Value(1)});auto *call=session.get();unsigned polls=0;
    NativeTaskInvocationOptions options;options.cancelled=[&]{if(++polls==20)session.reset();return false;};
    trap("E_CANCELLED",[&]{call->invoke(spinCode,{},options);});require(!session,"callback did not close its session");++cases;
  }
  require(liveObjects.load()==baseline&&!inRequestScope(),"session exits retained source objects or TLS");nex_runtime_finish();
  require(cases==14,"session kernel case count differs");
#ifndef NEX_NATIVE_TASK_SESSION_INLINE
  std::cout<<"{\"ok\":true,\"cases\":"<<cases<<",\"live_delta\":0,\"persistent_contexts\":true}\n";
#endif
  return 0;
}
}
int runNativeTaskSessionKernel(){try{return kernel();}catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 1;}}
#ifndef NEX_NATIVE_TASK_SESSION_INLINE
int runNativeTaskSessionImages(int,char **);
int main(int argc,char **argv){return argc==1?runNativeTaskSessionKernel():runNativeTaskSessionImages(argc,argv);}
#endif
