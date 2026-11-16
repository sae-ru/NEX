#include "nex_cells.h"
#include "nex_files.h"
#include <atomic>
#include <barrier>
#include <chrono>
#include <cstdlib>
#include <exception>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <new>
#include <string>
#include <thread>
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#else
#include <pthread.h>
#endif

using namespace nexrt;
namespace {
thread_local bool allocationForbidden=false;
constexpr size_t depth=65536,stackBytes=256*1024;
void require(bool value,const char *message){if(!value)throw std::runtime_error(message);}
std::shared_ptr<Data> plain(Data::Kind kind){return Data::make(kind);}
Value chain(Value leaf,size_t count=depth){
  const Data::Kind kinds[]={Data::List,Data::Record,Data::Enum,Data::Success,Data::Closure};
  for(size_t i=0;i<count;++i){auto node=plain(kinds[i%5]);node->values.push_back(std::move(leaf));leaf=Value(std::move(node));}
  return leaf;
}
void release(Value &root){allocationForbidden=true;root=Value();allocationForbidden=false;}
struct Observed final:Data {
  unsigned &calls;
  explicit Observed(unsigned &calls,Value value):Data(Data::Record),calls(calls){values.push_back(std::move(value));}
  ~Observed(){
    // A genuine host destructor must run before its child vector is drained.
    if(values.size()!=1||!values[0].object||values[0].object->values.size()!=1)std::abort();
    ++calls;
  }
};
void scenario(const std::string &name){
  auto before=liveObjects.load();
  if(name=="ordinary"){
    auto root=chain(Value(string("leaf")));release(root);
  }else if(name=="closed_snapshot"){
    CellHeap heap;auto root=chain(Value(int64_t(42)));auto cell=heap.create(root);root={};
    auto snapshot=heap.read(cell);heap.close();cell={};
    require(snapshot.object&&snapshot.object->values.size()==1,"close changed snapshot");release(snapshot);
  }else if(name=="shared_tail"){
    auto tail=chain(Value(string("retained")));auto left=chain(tail),right=chain(tail);tail={};
    auto observed=right;release(left);
    require(right.object==observed.object&&right.object->values.size()==1,"shared tail was changed");
    release(right);release(observed);
  }else if(name=="duplicate_edges"){
    auto root=Value(string("leaf"));
    for(size_t i=0;i<depth;++i){auto node=plain(Data::List);node->values={root,root};root=Value(std::move(node));}
    release(root);
  }else if(name=="wide_branches"){
    auto root=Value(int64_t(42));
    for(size_t i=0;i<depth;++i){auto node=plain(Data::Record);node->values={Value(int64_t(i)),Value(string("side")),std::move(root),Value::floating(1.25)};root=Value(std::move(node));}
    auto copy=Value(Data::make(*root.object));release(root);
    require(copy.object->values.size()==4&&copy.object->values[0].scalar==int64_t(depth-1),"copy changed during cleanup");release(copy);
  }else if(name=="host_destructor"){
    unsigned calls=0;auto child=plain(Data::List);child->values.emplace_back(int64_t(42));
    auto host=Value(std::make_shared<Observed>(calls,Value(std::move(child))));
    auto root=chain(std::move(host));release(root);require(calls==1,"host destructor count differs");
  }else if(name=="owned_file"){
    namespace fs=std::filesystem;
    auto directory=fs::temp_directory_path()/("nex-value-retirement-"+std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));
    require(fs::create_directory(directory),"cannot create file fixture");
    struct Remove {fs::path path;~Remove(){std::error_code ignored;fs::remove_all(path,ignored);}}remove{directory};
    {std::ofstream out(directory/"input");out<<"retained";require(bool(out),"cannot write file fixture");}
    TextFiles files(directory.string(),false);std::weak_ptr<Data> weak;
    {auto resource=fileValue(files.open("input",FileMode::Read));weak=resource;auto root=chain(Value(std::move(resource)));release(root);}
    require(weak.expired(),"deep graph retained file wrapper");
  }else if(name=="unwind"){
    try{auto root=chain(Value(string("unwind")));allocationForbidden=true;throw 42;}
    catch(int value){allocationForbidden=false;require(value==42,"unwind changed exception");}
  }else if(name=="concurrent"){
    // Multiple immutable roots may retire on separate workers. This exercises
    // real simultaneous releases; it is not a proof for all possible schedules.
    auto tail=chain(Value(int64_t(42)),4096);std::barrier ready(8);
    std::vector<std::thread> workers;
    for(unsigned i=0;i<8;++i)workers.emplace_back([root=chain(tail,4096),&ready]()mutable{ready.arrive_and_wait();release(root);});
    tail={};for(auto &worker:workers)worker.join();
  }else throw std::runtime_error("unknown retirement scenario");
  require(liveObjects.load()==before,"retirement left live values");
}
struct Work {const std::string &name;std::exception_ptr failure;};
#ifdef _WIN32
DWORD WINAPI run(void *arg){auto &work=*static_cast<Work*>(arg);try{scenario(work.name);}catch(...){work.failure=std::current_exception();}return 0;}
void bounded(Work &work){
  auto thread=CreateThread(nullptr,stackBytes,run,&work,STACK_SIZE_PARAM_IS_A_RESERVATION,nullptr);
  require(thread,"cannot create bounded-stack worker");
  auto result=WaitForSingleObject(thread,INFINITE);CloseHandle(thread);require(result==WAIT_OBJECT_0,"cannot join bounded-stack worker");
}
#else
void *run(void *arg){auto &work=*static_cast<Work*>(arg);try{scenario(work.name);}catch(...){work.failure=std::current_exception();}return nullptr;}
void bounded(Work &work){
  pthread_attr_t attributes;require(pthread_attr_init(&attributes)==0,"cannot initialize worker attributes");
  auto stackResult=pthread_attr_setstacksize(&attributes,stackBytes);pthread_t thread{};
  auto createResult=stackResult?stackResult:pthread_create(&thread,&attributes,run,&work);pthread_attr_destroy(&attributes);
  require(createResult==0,"cannot create bounded-stack worker");require(pthread_join(thread,nullptr)==0,"cannot join bounded-stack worker");
}
#endif
}
void *operator new(std::size_t count){if(allocationForbidden)throw std::bad_alloc();if(auto *memory=std::malloc(count?count:1))return memory;throw std::bad_alloc();}
void *operator new[](std::size_t count){return ::operator new(count);}
void operator delete(void *memory)noexcept{std::free(memory);}
void operator delete[](void *memory)noexcept{std::free(memory);}
void operator delete(void *memory,std::size_t)noexcept{std::free(memory);}
void operator delete[](void *memory,std::size_t)noexcept{std::free(memory);}
int main(int argc,char **argv){try{
  require(argc==2,"expected one scenario");std::string name=argv[1];Work work{name,{}};bounded(work);
  if(work.failure)std::rethrow_exception(work.failure);
  std::cout<<"{\"ok\":true,\"scenario\":\""<<name<<"\",\"depth\":"<<depth<<",\"stack_bytes\":"<<stackBytes
           <<",\"sizeof_value\":"<<sizeof(Value)<<",\"sizeof_data\":"<<sizeof(Data)<<",\"live_value_delta\":0}\n";
  return 0;
}catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 1;}}
