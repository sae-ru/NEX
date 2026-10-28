#include "nex_task_application.h"
#include <array>
#include <chrono>
#include <future>
#include <iostream>
#include <thread>
using namespace nexrt;
namespace {
std::atomic<unsigned> checks{0};
void require(bool value,const char *message){++checks;if(!value)throw std::runtime_error(message);}
Handle *request(const std::string &path="/ok",const std::string &user="alice"){
 auto data=std::make_shared<Data>(Data::Record);data->text="std::http::Request";data->names={"method","path","query","body","user","request_id"};
 for(const auto &s:std::vector<std::string>{"POST",path,"",std::string("λ\0🙂",7),user,"1"})data->values.emplace_back(string(s));return makeHandle(Value(data));
}
Value response(const Value &input){auto data=std::make_shared<Data>(Data::Record);data->text="std::http::Response";data->names={"status","body","content_type"};data->values={Value(int64_t(200)),Value(string(input.object->values[4].object->text+":"+input.object->values[3].object->text)),Value(string("text/plain"))};return Value(data);}
int64_t step(void *opaque){
 auto &frame=*static_cast<NativeTaskFrame*>(opaque);auto input=frame.read(0,3);auto path=input.object->values[1].object->text;
 if(!frame.pc){frame.pc=1;return 1;}
 if(path=="/source"){auto temporary=makeHandle(Value(string("source-owned")));(void)temporary;throw NativeSourceException("E_TIMEOUT",std::string("λ\0🙂",7),"{\"site\":\"original\"}",47);}
 if(path=="/trap"){auto temporary=makeHandle(Value(string("trap-owned")));(void)temporary;throw Trap("E_ASSERT","runtime control channel",48);}
 if(path=="/budget")for(unsigned i=0;i<1000;++i)nex_poll(49);
 auto value=makeHandle(response(input));nex_task_frame_return_heap(opaque,value);nex_release(value);return 0;
}
template<class F>void rejects(const char *code,F action){bool caught=false;try{action();}catch(const Trap &e){require(e.code==code,"wrong runtime trap");caught=true;}catch(const DataError &e){require(e.code==code,"wrong host error");caught=true;}require(caught,"missing failure");}
void clean(){require(!inRequestScope()&&liveObjects==0,"HTTP request retained owned values");nex_runtime_finish();}
}
int main(){try{
 const std::array<int64_t,1> kinds{3},parameters{0};
 const TaskCodeDescriptor prototype{step,kinds.data(),parameters.data(),nullptr,nullptr,taskCodeExceptionPrototypeABI,1,1,0,3,taskCodeDeclaredTask|taskCodeServer|taskCodeDeclaredThrow};
 rejects("E_TASK_SCOPE",[&]{executeSourceExceptionTaskHttpRequest(prototype,nullptr);});clean();
 for(auto abi:{taskCodeExceptionPrototypeABI,taskCodeExceptionHostPrototypeABI}){
  auto code=prototype;code.abi=abi;
  {RequestScope scope;auto deadline=scope.deadline();auto input=request();auto original=readHandle(input).object;auto result=executeSourceExceptionTaskHttpRequest(code,input);
   require(scope.deadline()==deadline&&inRequestScope(),"private HTTP replaced its parent request");require(readHandle(input).object==original,"borrowed Request changed");require(readHandle(result).object->values[1].object->text=="alice:"+std::string("λ\0🙂",7),"HTTP result changed");nex_release(result);nex_release(input);}clean();
  {RequestScope scope;auto input=request("/source");bool caught=false;
   try{executeSourceExceptionTaskHttpRequest(code,input);}catch(const NativeSourceException &e){require(e.code=="E_TIMEOUT"&&e.message==std::string("λ\0🙂",7)&&e.line==47&&e.source=="{\"site\":\"original\"}","source payload/site changed");caught=true;}
   require(caught&&inRequestScope(),"source failure lost or removed its parent request");nex_release(input);input=request();auto result=executeSourceExceptionTaskHttpRequest(code,input);require(readHandle(result).object->values[0].scalar==200,"source failure poisoned the caller's request");nex_release(result);nex_release(input);}clean();
  {RequestScope scope;auto input=request("/trap");rejects("E_ASSERT",[&]{executeSourceExceptionTaskHttpRequest(code,input);});}clean();
  {RequestScope scope(16,5000);auto input=request("/budget");rejects("E_LIMIT",[&]{executeSourceExceptionTaskHttpRequest(code,input);});}clean();
  {RequestScope scope;auto input=request();scope.cancel();rejects("E_CANCELLED",[&]{executeSourceExceptionTaskHttpRequest(code,input);});}clean();
  {RequestScope scope(1000000,1);auto input=request();std::this_thread::sleep_for(std::chrono::milliseconds(3));rejects("E_TIMEOUT",[&]{executeSourceExceptionTaskHttpRequest(code,input);});}clean();
  {RequestScope scope;auto input=request();rejects("E_TASK_HTTP_ABI",[&]{executeTaskHttpRequest(code,input);});}clean();
 }
 {RequestScope scope;auto input=request();auto code=prototype;code.abi=taskCodeStreamABI;code.requirements&=~taskCodeDeclaredThrow;rejects("E_TASK_HTTP_ABI",[&]{executeSourceExceptionTaskHttpRequest(code,input);});}clean();
 std::vector<std::future<void>> concurrent;
 for(unsigned i=0;i<8;++i)concurrent.push_back(std::async(std::launch::async,[&,i]{RequestScope scope;auto user="user"+std::to_string(i);auto input=request("/ok",user);auto result=executeSourceExceptionTaskHttpRequest(prototype,input,{},1);require(readHandle(result).object->values[1].object->text==user+":"+std::string("λ\0🙂",7),"parallel HTTP request values crossed");nex_release(result);nex_release(input);}));
 for(auto &future:concurrent)future.get();clean();
 std::cout<<"{\"ok\":true,\"checks\":"<<checks.load()<<",\"private_ABIs\":2,\"concurrent_requests\":8,\"parent_control_preserved\":true,\"source_and_runtime_separate\":true,\"compiled_NEX_claimed\":false}\n";return 0;
}catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 1;}}
