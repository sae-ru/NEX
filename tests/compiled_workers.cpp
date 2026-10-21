// The factory and every closure body are actual NEX compiler output. This host
// drives the private bridge ABI; it does not implement the language functions.
#include "nex_parallel.h"
#include <atomic>
#include <barrier>
#include <cstdio>
#include <cstdlib>
#include <map>
#include <mutex>
#include <set>
#include <thread>

extern "C" nexrt::Handle *nex_15_compiled_bridge_4_make();
extern "C" nexrt::Handle *nex_collection_get_heap(nexrt::Handle*,int64_t,int64_t);
extern "C" void *nex_closure_code(nexrt::Handle*);
namespace {
using nexrt::Value;using nexrt::Data;using K=nexrt::ParallelValueKind;using H=nexrt::Handle;
std::mutex mutex;
std::map<const void*,int> allocations;
size_t allocated[2]{},freed[2]{};
std::set<std::thread::id> threads;
std::atomic<unsigned> active{0},maximum{0},calls{0};
std::barrier<> *rendezvous=nullptr;
void require(bool valid,const char *message){if(!valid){std::fprintf(stderr,"compiled NEX worker: %s\n",message);std::abort();}}
struct Call {
  Call(){auto count=++active;auto previous=maximum.load();while(previous<count&&!maximum.compare_exchange_weak(previous,count)){}
    {std::lock_guard lock(mutex);threads.insert(std::this_thread::get_id());}++calls;if(rendezvous)rendezvous->arrive_and_wait();}
  ~Call(){--active;}
};
Value list(std::initializer_list<Value> values){auto data=std::make_shared<Data>(Data::List);data->values=values;return Value(std::move(data));}
Value integers(int count){auto data=std::make_shared<Data>(Data::List);for(int i=0;i<count;++i)data->values.emplace_back(i);return Value(std::move(data));}
Value closure(H *bundle,int index){return nexrt::readHandle(nex_collection_get_heap(bundle,index,0));}
void i64Heap(H *environment,int64_t scalar,H *heap,void *result){
  Call call;require(!heap,"i64 bridge received a heap argument");
  auto target=reinterpret_cast<H*(*)(H*,int64_t)>(nex_closure_code(environment));
  nex_parallel_return_heap(result,target(environment,scalar));
}
void f64Scalar(H *environment,int64_t scalar,H *heap,void *result){
  Call call;require(!heap,"f64 bridge received a heap argument");
  auto target=reinterpret_cast<double(*)(H*,double)>(nex_closure_code(environment));
  nex_parallel_return_i64(result,nexrt::floatBits(target(environment,nexrt::floatValue(scalar))),2);
}
void boolScalar(H *environment,int64_t scalar,H *heap,void *result){
  Call call;require(!heap,"bool bridge received a heap argument");
  auto target=reinterpret_cast<bool(*)(H*,bool)>(nex_closure_code(environment));
  nex_parallel_return_i64(result,target(environment,scalar!=0),1);
}
void heapHeap(H *environment,int64_t scalar,H *heap,void *result){
  Call call;require(scalar==0&&heap,"heap bridge received scalar data");
  auto target=reinterpret_cast<H*(*)(H*,H*)>(nex_closure_code(environment));
  nex_parallel_return_heap(result,target(environment,heap));
}
void i64Scalar(H *environment,int64_t scalar,H *heap,void *result){
  Call call;require(!heap,"i64 bridge received a heap argument");
  auto target=reinterpret_cast<int64_t(*)(H*,int64_t)>(nex_closure_code(environment));
  nex_parallel_return_i64(result,target(environment,scalar),0);
}
void clean(){
  require(!nexrt::inRequestScope()&&active==0,"scope or callback survived return");
  require(nexrt::liveObjects==0,"actual NEX closure/output leaked");
  {std::lock_guard lock(mutex);require(allocations.empty(),"actual NEX callback leaked a handle or object");threads.clear();}
  nex_runtime_finish();calls=0;maximum=0;rendezvous=nullptr;
}
}
extern "C" void nex_profile_enter(const char*,const char*,int64_t,const char*){}
extern "C" void nex_profile_leave(){}
extern "C" void nex_profile_unwind(){}
extern "C" void nex_profile_allocation(const void *pointer,size_t,int pool){
  std::lock_guard lock(mutex);require(pool>=0&&pool<2,"unknown allocation pool");require(allocations.emplace(pointer,pool).second,"duplicate allocation");++allocated[pool];
}
extern "C" void nex_profile_free(const void *pointer){
  std::lock_guard lock(mutex);auto found=allocations.find(pointer);require(found!=allocations.end(),"free without allocation");++freed[found->second];allocations.erase(found);
}
int main(){
  unsigned cases=0;
  {
    nexrt::RequestScope scope;auto *bundle=nex_15_compiled_bridge_4_make();std::barrier barrier(4);rendezvous=&barrier;
    auto output=nexrt::parallelCompiledValues(integers(16),closure(bundle,0),4,i64Heap,K::I64,K::Heap);
    require(calls==16&&threads.size()==4&&maximum==4,"NEX calls did not use four overlapping native workers");
    for(int i=0;i<16;++i)require(output.object->values[i].object->text=="Я🧠:"+std::to_string(i),"actual NEX closure capture/order changed");
  }clean();++cases;
  {
    nexrt::RequestScope scope;auto *bundle=nex_15_compiled_bridge_4_make();
    auto output=nexrt::parallelCompiledValues(list({Value::floating(-1.25),Value::floating(0.0),Value::floating(40.5)}),closure(bundle,1),3,f64Scalar,K::F64,K::F64);
    require(output.object->values[0].floating()==-0.75&&output.object->values[1].floating()==0.5&&output.object->values[2].floating()==41.0,"actual NEX f64 callable ABI differs");
  }clean();++cases;
  {
    nexrt::RequestScope scope;auto *bundle=nex_15_compiled_bridge_4_make();
    auto output=nexrt::parallelCompiledValues(list({Value(0,true),Value(1,true)}),closure(bundle,2),2,boolScalar,K::Bool,K::Bool);
    require(output.object->values[0].tag==Value::Boolean&&output.object->values[0].scalar==1&&output.object->values[1].scalar==0,"actual NEX bool callable ABI differs");
  }clean();++cases;
  {
    nexrt::RequestScope scope;auto *bundle=nex_15_compiled_bridge_4_make();auto text=nexrt::string("original Я🧠");
    auto output=nexrt::parallelCompiledValues(list({Value(text),Value(text)}),closure(bundle,3),2,heapHeap,K::Heap,K::Heap);
    require(output.object->values[0].object==text&&output.object->values[1].object==text,"actual NEX borrowed input return lost identity");
  }clean();++cases;
  {
    nexrt::RequestScope scope;auto *bundle=nex_15_compiled_bridge_4_make();
    auto output=nexrt::parallelCompiledValues(integers(4),closure(bundle,4),2,i64Heap,K::I64,K::Heap);
    for(int i=0;i<4;++i){auto *environment=nexrt::makeHandle(output.object->values[i]);
      auto target=reinterpret_cast<int64_t(*)(H*,int64_t)>(nex_closure_code(environment));
      require(target(environment,40)==40+i,"returned NEX closure lost a worker-local capture");}
  }clean();++cases;
  {
    nexrt::RequestScope scope;auto *bundle=nex_15_compiled_bridge_4_make();bool caught=false;
    try{(void)nexrt::parallelCompiledValues(list({Value(2),Value(0),Value(2)}),closure(bundle,5),3,i64Scalar,K::I64,K::I64);}
    catch(const nexrt::LocatedTrap &error){caught=error.code=="E_DIV_ZERO"&&error.line>0&&error.source.find("operation_site")!=std::string::npos;}
    require(caught&&active==0,"actual NEX checked error/site or worker join was lost");scope.poll();
  }clean();++cases;
  {
    nexrt::RequestScope scope;auto *bundle=nex_15_compiled_bridge_4_make();
    auto output=nexrt::parallelCompiledValues(integers(3),closure(bundle,6),3,i64Heap,K::I64,K::Heap);
    require(nexrt::isSuccess(output.object->values[0])&&nexrt::unwrap(output.object->values[0]).object->text=="Я🧠:0","actual NEX result success changed");
    const auto &error=output.object->values[1];require(!nexrt::isSuccess(error)&&error.object->text=="WORKER"&&error.object->values[0].object->text=="ошибка 🧠","actual NEX ? lost its code/message or ownership");
    require(nexrt::isSuccess(output.object->values[2]),"expected result error stopped other inputs");
  }clean();++cases;
  require(allocated[0]>0&&allocated[1]>0&&allocated[0]==freed[0]&&allocated[1]==freed[1],"managed pools did not balance");
  std::printf("{\"ok\":true,\"cases\":%u,\"actual_nex_closure_bodies\":true,\"simultaneous_workers\":4,\"live_handles\":0,\"live_objects\":0}\n",cases);
}
