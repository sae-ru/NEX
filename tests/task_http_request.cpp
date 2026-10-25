#include "nex_task_application.h"
#include <array>
#include <chrono>
#include <future>
#include <iostream>
#include <thread>
using namespace nexrt;
namespace {
std::atomic<unsigned> checks{0},turns{0};
void require(bool v,const char *message){++checks;if(!v)throw std::runtime_error(message);}
Handle *request(std::string path="/ok",std::string user="alice"){
 auto record=std::make_shared<Data>(Data::Record);record->text="std::http::Request";
 record->names={"method","path","query","body","user","request_id"};
 for(const auto &field:std::vector<std::string>{"GET",path,"",std::string("A🌍\0β",8),user,"1"})record->values.emplace_back(string(field));
 return makeHandle(Value(record));
}
Value response(const Value &input,bool invalid=false){
 auto record=std::make_shared<Data>(Data::Record);record->text="std::http::Response";record->names={"status","body","content_type"};
 record->values={Value(int64_t(200)),Value(string(input.object->values[4].object->text+":"+input.object->values[3].object->text)),Value(string("text/plain"))};
 if(invalid)record->values[1]=Value(int64_t(5));return Value(record);
}
const TaskCodeDescriptor *selected=nullptr;
int64_t step(void *opaque){
 ++turns;auto &frame=*static_cast<NativeTaskFrame*>(opaque);auto input=frame.read(0,3);auto path=input.object->values[1].object->text;
 if(path=="/limit")for(unsigned i=0;i<1000;++i)nex_poll(31);
 if(path=="/trap"){(void)makeHandle(Value(string("resume-local")));throw Trap("E_ITEM","actual worker trap",32);}
 if(path=="/nested"){auto temporary=makeHandle(input);(void)executeTaskHttpRequest(*selected,temporary);}
 if(!frame.pc){frame.pc=1;return 1;}
 auto returned=makeHandle(response(input,path=="/invalid-response"));nex_task_frame_return_heap(opaque,returned);nex_release(returned);return 0;
}
template<class F>void rejects(const char *code,F action){bool caught=false;try{action();}catch(const Trap &e){require(e.code==code,"unexpected trap");caught=true;}catch(const DataError &e){require(e.code==code,"unexpected host error");caught=true;}require(caught,"expected error was absent");}
void clean(){require(!inRequestScope()&&liveObjects==0,"request values survived retirement");nex_runtime_finish();}
}
int main(){try{
 const std::array<int64_t,1> kinds{3},parameters{0};const TaskCodeDescriptor code{step,kinds.data(),parameters.data(),nullptr,nullptr,taskCodeStreamABI,1,1,0,3,taskCodeDeclaredTask|taskCodeServer};selected=&code;
 rejects("E_TASK_SCOPE",[&]{executeTaskHttpRequest(code,nullptr);});clean();
 for(unsigned i=0;i<3;++i){
  {RequestScope scope;auto deadline=scope.deadline();auto input=request();auto before=readHandle(input);auto result=executeTaskHttpRequest(code,input);
   require(scope.deadline()==deadline,"handler reset the parent deadline");require(inRequestScope(),"handler removed the parent request");auto value=readHandle(result);require(value.object->values[1].object->text=="alice:"+std::string("A🌍\0β",8),"request parameters or response changed");require(readHandle(input).object==before.object,"borrowed Request handle changed");nex_release(result);nex_release(input);}
  clean();
 }
 for(auto abi:{taskCodeABI,taskCodeWriteABI}){{RequestScope scope;auto input=request();auto bad=code;bad.abi=abi;rejects("E_TASK_HTTP_ABI",[&]{executeTaskHttpRequest(bad,input);});}clean();}
 for(unsigned which=0;which<5;++which){{RequestScope scope;auto input=request();auto bad=code;if(which==0)bad.parameterCount=2;if(which==1)bad.captureCount=1;if(which==2)bad.resultKind=0;if(which==3)bad.requirements=taskCodeDeclaredTask;if(which==4)bad.requirements|=INT64_C(1)<<40;rejects("E_TASK_HTTP_ABI",[&]{executeTaskHttpRequest(bad,input);});}clean();}
 {RequestScope scope;rejects("E_TASK_HTTP_REQUEST",[&]{executeTaskHttpRequest(code,nullptr);});}clean();
 for(unsigned which=0;which<3;++which){{RequestScope scope;auto input=request();auto value=readHandle(input);if(which==0)value.object->text="foreign::Request";if(which==1)value.object->names[0]="other";if(which==2)value.object->values[3]=Value(int64_t(1));rejects("E_TASK_HTTP_REQUEST",[&]{executeTaskHttpRequest(code,input);});}clean();}
 for(auto path:{"/trap","/nested","/invalid-response"}){{RequestScope scope;auto input=request(path);auto expected=std::string(path)=="/trap"?"E_ITEM":std::string(path)=="/nested"?"E_TASK_SCOPE":"E_TASK_HTTP_RESPONSE";rejects(expected,[&]{executeTaskHttpRequest(code,input);});}clean();}
 {RequestScope scope(16,5000);auto input=request("/limit");rejects("E_LIMIT",[&]{executeTaskHttpRequest(code,input);});rejects("E_LIMIT",[&]{executeTaskHttpRequest(code,input);});}clean();
 {RequestScope scope;auto input=request();scope.cancel();rejects("E_CANCELLED",[&]{executeTaskHttpRequest(code,input);});}clean();
 {RequestScope scope(1000000,1);auto input=request();std::this_thread::sleep_for(std::chrono::milliseconds(3));rejects("E_TIMEOUT",[&]{executeTaskHttpRequest(code,input);});}clean();
 {RequestScope scope;auto input=request();auto baseline=turns.load();scope.setCancellation([&]{return turns.load()>baseline;});rejects("E_CANCELLED",[&]{executeTaskHttpRequest(code,input);});}clean();
 {RequestScope scope;auto input=request();rejects("E_OPTION",[&]{executeTaskHttpRequest(code,input,{},0);});rejects("E_OPTION",[&]{executeTaskHttpRequest(code,input,{},17);});auto io=code;io.requirements|=taskCodeDeclaredFs|taskCodeFileRead|taskCodeImageFileRead;rejects("E_TASK_HOST",[&]{executeTaskHttpRequest(io,input);});}clean();
 std::vector<std::future<void>> concurrent;
 for(unsigned i=0;i<8;++i)concurrent.push_back(std::async(std::launch::async,[&,i]{RequestScope scope;auto user="user"+std::to_string(i);auto input=request("/ok",user);auto result=executeTaskHttpRequest(code,input,{},1);require(readHandle(result).object->values[1].object->text==user+":"+std::string("A🌍\0β",8),"concurrent request identity crossed");nex_release(result);nex_release(input);}));
 for(auto &future:concurrent)future.get();clean();
 std::cout<<"{\"ok\":true,\"checks\":"<<checks.load()<<",\"concurrent_requests\":8,\"parent_control_preserved\":true,\"public_HTTP_task_target\":false,\"compiled_NEX_claimed\":false}\n";
}catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 1;}}
