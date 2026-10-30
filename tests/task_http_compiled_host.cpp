#include "nex_task_application.h"
#include <chrono>
#include <future>
#include <iostream>
#include <thread>
#ifndef NEX_HTTP_TASK_ACCESSOR
#error The checked provider must supply the actual emitted accessor
#endif
extern "C" const nexrt::TaskCodeDescriptor *NEX_HTTP_TASK_ACCESSOR();
using namespace nexrt;
namespace {
std::atomic<unsigned> checks{0};
void require(bool value,const char *message){++checks;if(!value)throw std::runtime_error(message);}
const std::string body("A🌍\0β",8);
Handle *request(std::string path="/ok",std::string user="alice"){
 auto record=std::make_shared<Data>(Data::Record);record->text="std::http::Request";
 record->names={"method","path","query","body","user","request_id"};
 for(const auto &field:std::vector<std::string>{"POST",path,"",body,user,"request-1"})record->values.emplace_back(string(field));
 return makeHandle(Value(record));
}
template<class F>void rejects(const char *code,F action){
 bool caught=false;try{action();}catch(const Trap &e){require(e.code==code,"unexpected compiled handler trap");caught=true;}
 require(caught,"compiled handler did not reject");
}
void clean(){require(!inRequestScope()&&liveObjects==0,"compiled handler retained request values");nex_runtime_finish();}
std::string hex(const std::string &s){static const char digits[]="0123456789abcdef";std::string out;for(unsigned char c:s){out+=digits[c>>4];out+=digits[c&15];}return out;}
}
int main(){try{
 const auto *code=NEX_HTTP_TASK_ACCESSOR();require(code&&code->abi==taskCodeTypedSourceExceptionABI,"compiled descriptor ABI differs");
 require(code->parameterCount==1&&code->captureCount==0&&code->resultKind==3,"compiled HTTP signature differs");
 std::string observed;
 for(unsigned workers:{1U,2U,4U}){
  {RequestScope scope;auto deadline=scope.deadline();auto input=request();auto identity=readHandle(input).object;
   auto output=executeTaskHttpRequest(*code,input,{},workers);auto value=readHandle(output);
   require(scope.deadline()==deadline,"compiled handler reset parent deadline");
   require(readHandle(input).object==identity,"compiled handler changed borrowed request");
   require(value.object->values[0].scalar==200,"compiled response status differs");
   observed=value.object->values[1].object->text;require(observed=="alice:"+body+":42","compiled request/response bytes differ");
   require(value.object->values[2].object->text=="text/plain; charset=utf-8","compiled content type differs");
   nex_release(output);nex_release(input);}
  clean();
 }
 {RequestScope scope;auto input=request("/trap");rejects("E_DIV_ZERO",[&]{executeTaskHttpRequest(*code,input);});}clean();
 {RequestScope scope(40,5000);auto input=request("/limit");rejects("E_LIMIT",[&]{executeTaskHttpRequest(*code,input);});
  rejects("E_LIMIT",[&]{executeTaskHttpRequest(*code,input);});}clean();
 {RequestScope scope;auto input=request();scope.cancel();rejects("E_CANCELLED",[&]{executeTaskHttpRequest(*code,input);});}clean();
 {RequestScope scope(1000000,1);auto input=request();std::this_thread::sleep_for(std::chrono::milliseconds(3));
  rejects("E_TIMEOUT",[&]{executeTaskHttpRequest(*code,input);});}clean();
 std::vector<std::future<void>> concurrent;
 for(unsigned i=0;i<8;++i)concurrent.push_back(std::async(std::launch::async,[&,i]{
  RequestScope scope;auto user="user"+std::to_string(i);auto input=request("/ok",user);auto output=executeTaskHttpRequest(*code,input,{},2);
  require(readHandle(output).object->values[1].object->text==user+":"+body+":42","concurrent compiled request identities crossed");
  nex_release(output);nex_release(input);
 }));
 for(auto &future:concurrent)future.get();clean();
 std::cout<<"{\"ok\":true,\"checks\":"<<checks.load()<<",\"body_hex\":\""<<hex(observed)
  <<"\",\"concurrent_requests\":8,\"parent_control_preserved\":true,\"compiled_NEX\":true,\"public_HTTP_task_target\":true}\n";
}catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 1;}}
