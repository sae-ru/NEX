#include "host_test.h"
#include "nex/task_reference.h"
#include "nex/task_frontend.h"
#include "nex_files.h"
#include "nex_host.h"
#include <atomic>
#include <condition_variable>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <mutex>
#include <stop_token>
#include <thread>
#include <unistd.h>

using namespace nex;
using namespace std::string_literals;
namespace fs=std::filesystem;
namespace {
size_t cases=0;
void require(bool value,const std::string &message){if(!value)throw std::runtime_error(message);}
void passed(){++cases;}
template<class F>Error rejects(const std::string &code,F action){
  auto before=nexrt::liveObjects.load();
  try{action();}catch(const Error &error){require(error.code==code,"expected "+code+", got "+error.code+": "+error.what());require(nexrt::liveObjects.load()==before,"failed file task retained source values");passed();return error;}
  throw std::runtime_error("expected "+code);
}
Program source(const std::string &body,SourceLanguage language=SourceLanguage::TaskFiles020){
  auto p=parseVersioned("module reference_files;\n"+body,"reference_files.nex",language);check(p);return p;
}
void clean(const TaskReferenceResult &result){
  require(result.executionWorkers==1,"reference source execution ceased to be serial");
  require(!result.external.pending&&!result.external.reservedBytes&&!result.external.running&&!result.external.ready&&
    result.external.submitted==result.external.retired&&result.external.retired==result.external.consumed,
    "source file read completed before physical/credit retirement");
}
struct Directory {
  fs::path path;
  Directory(){std::string pattern=(fs::temp_directory_path()/"nex-reference-files-XXXXXX").string();auto value=::mkdtemp(pattern.data());require(value,"mkdtemp failed");path=value;}
  ~Directory(){std::error_code ignored;fs::remove_all(path,ignored);}
};
void write(const fs::path &path,const std::string &value){std::ofstream file(path,std::ios::binary);file.write(value.data(),value.size());require(bool(file),"cannot write read fixture");}
struct Environment {
  std::string key;std::optional<std::string> previous;
  Environment(std::string key,const std::string &value):key(std::move(key)){if(auto *old=std::getenv(this->key.c_str()))previous=old;::setenv(this->key.c_str(),value.c_str(),1);}
  ~Environment(){if(previous)::setenv(key.c_str(),previous->c_str(),1);else ::unsetenv(key.c_str());}
};
std::string text(const nexrt::Value &value){require(nexrt::isSuccess(value),"expected successful text read");return nexrt::unwrap(value).object->text;}
std::string errorCode(const nexrt::Value &value){require(!nexrt::isSuccess(value),"expected ordinary file error result");return value.object->text;}
struct UnitOperation:nexrt::TaskExternalOperation {
  nexrt::TaskExternalResult run(const nexrt::TaskExternalControl &control)override{control.checkpoint();return {};}
};
struct Host:TaskReferenceExternalHost {
  size_t prepared=0,admitted=0;
  std::optional<TaskReferenceExternalRequest> prepare(size_t,Span)override{++prepared;return TaskReferenceExternalRequest{std::make_shared<UnitOperation>(),8};}
  void admit(size_t,const nexrt::TaskExternalResult &)override{++admitted;}
};
struct HeldState {
  std::mutex mutex;std::condition_variable changed;
  bool started=false,cancelled=false,released=false;
  std::atomic<bool> physicalExited=false,destroyed=false,returned=false;
};
struct HeldOperation:nexrt::TaskExternalOperation {
  std::shared_ptr<HeldState> state;bool lateFatal;
  HeldOperation(std::shared_ptr<HeldState> state,bool lateFatal):state(std::move(state)),lateFatal(lateFatal){}
  ~HeldOperation()override{state->destroyed=true;}
  nexrt::TaskExternalResult run(const nexrt::TaskExternalControl &control)override{
    struct Exit {std::shared_ptr<HeldState> state;~Exit(){state->physicalExited=true;}} exit{state};
    {std::lock_guard lock(state->mutex);state->started=true;}state->changed.notify_all();
    try{for(;;){control.checkpoint();std::unique_lock lock(state->mutex);if(state->released)break;state->changed.wait_for(lock,std::chrono::milliseconds(1));}}
    catch(const nexrt::DataError &error){
      {std::lock_guard lock(state->mutex);state->cancelled=true;}state->changed.notify_all();
      std::unique_lock lock(state->mutex);state->changed.wait(lock,[&]{return state->released;});
      if(lateFatal)throw nexrt::DataError("E_MEMORY","late physical failure");throw;
    }
    return {};
  }
};
struct HeldHost:TaskReferenceExternalHost {
  std::shared_ptr<HeldState> state=std::make_shared<HeldState>();bool lateFatal;size_t admitted=0;
  explicit HeldHost(bool lateFatal):lateFatal(lateFatal){}
  std::optional<TaskReferenceExternalRequest> prepare(size_t,Span)override{return TaskReferenceExternalRequest{std::make_shared<HeldOperation>(state,lateFatal),7*1024*1024};}
  void admit(size_t,const nexrt::TaskExternalResult &)override{++admitted;}
};
void astTests(){
  auto p=source("server fn path()->str{return \"text\";} server fn main()->result<str> !{task,fs}{return file_read_text(path());}");
  TaskAstMachine machine(p,"main");auto wait=machine.advance();
  require(wait.kind==TaskTransition::Waiting&&wait.operation=="file_read_text"&&wait.arguments.size()==1&&
    wait.arguments[0].object->text=="text"&&wait.result==Type::result(Type::Str),"AST text read was not a typed once-evaluated suspension");passed();
  rejects("E_TASK_TYPE",[&]{machine.resume(wait.ticket,nexrt::success(nexrt::Value(42)));});
  machine.resume(wait.ticket,nexrt::success(nexrt::Value(nexrt::string("🧠\0ok"s))));
  auto done=machine.advance();require(done.kind==TaskTransition::Done&&text(done.value)=="🧠\0ok"s,"AST source value lost text content");passed();
  auto bytes=source("server fn main()->result<bytes> !{task,fs}{return file_read_bytes(\"data\");}");
  TaskAstMachine byteMachine(bytes,"main");wait=byteMachine.advance();
  require(wait.operation=="file_read_bytes"&&wait.result==Type::result(Type::Bytes),"AST bytes read lost result type");
  byteMachine.resume(wait.ticket,nexrt::success(nexrt::Value(nexrt::bytes(nexrt::ByteBuffer::copy(std::vector<uint8_t>{0,255,7})))));
  require(nexrt::byteBuffer(nexrt::unwrap(byteMachine.advance().value).object).length()==3,"AST byte response differs");passed();
  auto propagate=source("server fn main()->result<i64> !{task,fs}{let value:str=file_read_text(\"missing\")?;return ok(len(value));}");
  TaskAstMachine resultMachine(propagate,"main");wait=resultMachine.advance();
  resultMachine.resume(wait.ticket,nexrt::failure("NOT_FOUND","unchanged"));
  require(errorCode(resultMachine.advance().value)=="NOT_FOUND","AST read propagation crossed source return boundary");passed();
  auto skipped=source("server fn main()->bool !{task,fs}{return false&&is_ok(file_read_text(\"text\"));}");
  TaskAstMachine skippedMachine(skipped,"main");done=skippedMachine.advance();require(done.kind==TaskTransition::Done&&!done.value.scalar,"short circuit prepared a file read");passed();
  auto old=source("server fn main()->unit !{task,fs}{task_yield();}",SourceLanguage::Tasks019);
  rejects("E_TASK_UNIMPLEMENTED",[&]{TaskAstMachine oldMachine(old,"main");});
  auto callable=source("server fn ordinary()->result<str> !{fs}{return file_read_text(\"text\");} server fn main(f:server fn()->result<str> !{task,fs})->result<str> !{task,fs}{return f();}");
  auto closure=std::make_shared<nexrt::Data>(nexrt::Data::Closure);closure->text="ordinary";
  rejects("E_FUNCTION",[&]{TaskAstMachine forged(callable,"main",{nexrt::Value(closure)});forged.advance();});
}
void referenceTests(){
  auto ordinaryName=source("fn file_helper()->i64{return 42;}fn main()->i64 !{task}{return file_helper();}");
  {auto result=evaluateTaskReference(ordinaryName);clean(result);require(result.value.scalar==42&&!result.external.submitted,"file_ prefix was mistaken for a reserved filesystem builtin");passed();}
  Directory temporary;auto root=temporary.path/"root",other=temporary.path/"other";fs::create_directory(root);fs::create_directory(other);
  const std::string content="NEX🧠\0BOM:"s+"\xef\xbb\xbf";write(root/"text",content);write(other/"text","unrelated");
  write(root/"data",std::string("A\0\xff",3));write(root/"empty","");write(root/"maximum",std::string(1048576,'x'));write(root/"large",std::string(1048577,'x'));
  fs::create_symlink(other/"text",root/"link");
  auto read=source("server fn main()->result<str> !{task,fs}{return file_read_text(\"text\");}");
  nexrt::TextFiles capability(root.string(),false);
  {
    Environment environment("NEX_FILES_ROOT",other.string());nexrt::FileScope scope(capability);
    auto result=evaluateTaskReference(read);clean(result);require(text(result.value)==content&&result.external.submitted==1,"reference failed explicit grant or exact text read");passed();
    auto bytes=source("server fn main()->result<bytes> !{task,fs}{return file_read_bytes(\"data\");}");
    result=evaluateTaskReference(bytes);clean(result);auto raw=nexrt::byteBuffer(nexrt::unwrap(result.value).object).view();
    require(raw.size()==3&&raw[0]=='A'&&raw[1]==0&&raw[2]==255,"binary read changed raw octets");passed();
    for(const auto &[path,code]:std::vector<std::pair<std::string,std::string>>{{"missing","NOT_FOUND"},{"../escape","VALIDATION"},{"link","VALIDATION"},{"large","LIMIT"},{"data","E_UTF8"}}){
      auto program=source("server fn main()->result<str> !{task,fs}{return file_read_text(\""+path+"\");}");
      result=evaluateTaskReference(program);clean(result);require(errorCode(result.value)==code,"ordinary file failure changed category: "+path);passed();
    }
    for(const auto &path:{"empty","maximum"}){
      auto program=source("server fn main()->result<bytes> !{task,fs}{return file_read_bytes(\""s+path+"\");}");
      result=evaluateTaskReference(program);clean(result);require(nexrt::byteBuffer(nexrt::unwrap(result.value).object).length()==(path=="empty"s?0:1048576),"byte read boundary differs");passed();
    }
    auto propagated=source("server fn helper()->result<i64> !{task,fs}{let value:str=file_read_text(\"missing\")?;assert(false);return ok(len(value));}server fn main()->result<i64> !{task,fs}{return helper();}");
    result=evaluateTaskReference(propagated);clean(result);require(errorCode(result.value)=="NOT_FOUND","reference result propagation escaped helper boundary");passed();
    auto callable=source("server fn read()->result<str> !{task,fs}{return file_read_text(\"text\");}server fn helper(f:server fn()->result<str> !{task,fs})->result<str> !{task,fs}{return f();}server fn main()->result<str> !{task,fs}{return helper(read);}");
    result=evaluateTaskReference(callable);clean(result);require(text(result.value)==content,"typed indirect read helper did not suspend");passed();
    auto normal=source("server fn main()->i64 !{task,fs}{return with_tasks(1,server fn(s:task_scope)->i64 !{task,fs}{task_spawn(s,server fn()->unit !{task,fs}{assert(is_ok(file_read_text(\"text\")));});return 42;});}");
    result=evaluateTaskReference(normal);clean(result);require(result.value.scalar==42&&result.external.submitted==1&&result.scopes==1,"normal parent scope stole child read or finished early");passed();
    auto abort=source("server fn main()->result<str> !{task,fs}{return with_tasks(1,server fn(s:task_scope)->result<str> !{task,fs}{task_spawn(s,server fn()->result<str> !{task,fs}{let value:result<str>=file_read_text(\"text\");assert(false);return value;});return err(\"E_ORIGINAL\",\"preserved\");});}");
    result=evaluateTaskReference(abort);clean(result);require(errorCode(result.value)=="E_ORIGINAL"&&result.external.submitted==1,"error-result scope failed read physical drain or resumed cancelled child");passed();
    auto cancel=source("server fn main()->i64 !{task,fs}{return with_tasks(1,server fn(s:task_scope)->i64 !{task,fs}{let reader:task<unit>=task_spawn(s,server fn()->unit !{task,fs}{file_read_text(\"text\");assert(false);});task_cancel(reader);return 42;});}");
    result=evaluateTaskReference(cancel);clean(result);require(result.value.scalar==42&&result.external.submitted==1,"explicit cancellation resumed the read source or released its physical ledger early");passed();
    Host exhausted;exhausted.limits.reservedBytes=1;
    auto quota=rejects("E_LIMIT",[&]{evaluateTaskReference(abort,"main",{},1000000,{},nullptr,&exhausted);});
    require(!quota.operationSite.empty()&&quota.operationRevision==revision(abort)&&!quota.operationSource.empty(),"source read failure lost its checked operation identity");passed();
    Host synthetic;auto combined=source("server fn main()->result<str> !{task,fs}{task_yield();return file_read_text(\"text\");}");
    result=evaluateTaskReference(combined,"main",{},1000000,{},nullptr,&synthetic);clean(result);
    require(text(result.value)==content&&synthetic.prepared==1&&synthetic.admitted==1&&result.external.submitted==2,"typed reads reused the synthetic unit hook");passed();
    auto once=source("server fn path()->str !{io}{print(\"path\");return \"text\";}server fn main()->result<str> !{task,fs,io}{return file_read_text(path());}");
    result=evaluateTaskReference(once);clean(result);require(result.output=="path\n"&&text(result.value)==content&&result.external.submitted==1,"file operand did not evaluate exactly once before suspension");passed();
    auto unsupported=source("server fn main()->unit !{task,fs}{file_read_text(\"text\");file_write_text(\"must-not-write\",\"side effect\");}");
    rejects("E_TASK_UNIMPLEMENTED",[&]{evaluateTaskReference(unsupported);});require(!fs::exists(root/"must-not-write"),"unsupported task operation performed a write");passed();
    auto ordinary=source("server fn main()->result<str> !{fs}{return file_read_text(\"text\");}");
    Environment ordinaryEnvironment("NEX_FILES_ROOT",root.string());auto evaluated=evaluate(ordinary);
    require(evaluated.value.getAsObject()&&evaluated.value.getAsObject()->getString("ok")==content,"ordinary synchronous fs behavior changed");passed();
  }
  for(const auto &[directory,expected]:std::vector<std::pair<fs::path,std::string>>{{root,content},{other,"unrelated"}}){
    Environment environment("NEX_FILES_ROOT",directory.string());auto result=evaluateTaskReference(read);clean(result);
    require(text(result.value)==expected,"separate reference run reused stale environment capability");passed();
  }
  {
    Environment environment("NEX_FILES_ROOT",root.string());nexrt::FileScope denied(false);
    auto result=evaluateTaskReference(read);clean(result);require(errorCode(result.value)=="CAPABILITY"&&!result.external.submitted,"missing grant was not an ordinary attempted-read error");passed();
    auto skipped=source("server fn main()->bool !{task,fs}{return false&&is_ok(file_read_text(\"text\"));}");
    result=evaluateTaskReference(skipped);clean(result);require(!result.value.scalar&&!result.external.submitted,"skipped read required a grant");passed();
  }
  {
    nexrt::FileScope files(capability);nexrt::RequestScope request;auto grant=nexrt::captureFileReadGrant(false);
    Host host;std::stop_source stop;host.cancellation=stop.get_token();size_t reads=0;
    rejects("E_CANCELLED",[&]{evaluateTaskReference(read,"main",{},1000000,[&](size_t,const TaskTransition &transition){if(taskFileReadOperation(transition.operation)){++reads;stop.request_stop();}},nullptr,&host,&grant);});
    require(reads==1&&!host.prepared&&!host.admitted,"cancelled typed read invoked a unit host callback");passed();
  }
  {
    nexrt::FileScope files(capability);nexrt::RequestScope request;auto grant=nexrt::captureFileReadGrant(false);
    rejects("E_CANCELLED",[&]{evaluateTaskReference(read,"main",{},1000000,[&](size_t,const TaskTransition &transition){if(taskFileReadOperation(transition.operation))request.cancel();},nullptr,nullptr,&grant);});
  }
  {
    auto files=std::make_unique<nexrt::FileScope>(capability);nexrt::RequestScope request;auto grant=nexrt::captureFileReadGrant(false);
    auto twice=source("server fn main()->result<str> !{task,fs}{let first:result<str>=file_read_text(\"text\");task_yield();return file_read_text(\"text\");}");
    rejects("E_RESOURCE_SCOPE",[&]{evaluateTaskReference(twice,"main",{},1000000,[&](size_t,const TaskTransition &transition){if(transition.operation=="task_yield")files.reset();},nullptr,nullptr,&grant);});
  }
  {
    nexrt::FileScope files(capability);nexrt::RequestScope request;auto grant=nexrt::captureFileReadGrant(false);
    auto twice=source("server fn main()->result<str> !{task,fs}{file_read_text(\"text\");task_yield();return file_read_text(\"text\");}");
    auto result=evaluateTaskReference(twice,"main",{},1000000,{},nullptr,nullptr,&grant);clean(result);
    require(text(result.value)==content&&result.external.submitted==2,"explicit root grant was rebound to a temporary resume scope");passed();
  }
  {
    auto quota=source("server fn main()->result<i64> !{task,fs}{return with_tasks(2,server fn(s:task_scope)->result<i64> !{task,fs}{task_spawn(s,server fn()->unit !{task}{task_yield();assert(false);});task_spawn(s,server fn()->unit !{task,fs}{file_read_text(\"text\");assert(false);});task_yield();return err(\"E_ORIGINAL\",\"must not hide quota\");});}");
    for(bool lateFatal:{false,true}){
      nexrt::FileScope files(capability);nexrt::RequestScope request;auto grant=nexrt::captureFileReadGrant(false);HeldHost host(lateFatal);
      bool cancelled=false,draining=false,started=false;size_t parentResumed=0;
      std::jthread release([&]{std::unique_lock lock(host.state->mutex);
        cancelled=host.state->changed.wait_for(lock,std::chrono::seconds(3),[&]{return host.state->cancelled;});
        draining=!host.state->returned.load()&&!host.state->physicalExited.load();host.state->released=true;lock.unlock();host.state->changed.notify_all();
      });
      rejects("E_LIMIT",[&]{evaluateTaskReference(quota,"main",{},1000000,[&](size_t owner,const TaskTransition &transition){
        if(taskFileReadOperation(transition.operation)){std::unique_lock lock(host.state->mutex);started=host.state->changed.wait_for(lock,std::chrono::seconds(2),[&]{return host.state->started;});}
        if(owner==0&&transition.operation=="task_yield")++parentResumed;
      },nullptr,&host,&grant);});
      host.state->returned=true;release.join();
      require(started&&cancelled&&draining&&host.state->physicalExited&&host.state->destroyed&&!host.admitted&&!parentResumed,
        "file quota failure resumed source, skipped physical drain or lost first-fatal priority");passed();
    }
  }
  {
    nexrt::FileScope files(capability);nexrt::RequestScope request;auto grant=nexrt::captureFileReadGrant(false);HeldHost host(false);
    std::atomic<bool> callbackSelected=false;bool cancelled=false,draining=false;
    request.setCancellation([&]{std::lock_guard lock(host.state->mutex);if(!host.state->started)return false;callbackSelected=true;return true;});
    std::jthread release([&]{std::unique_lock lock(host.state->mutex);
      cancelled=host.state->changed.wait_for(lock,std::chrono::seconds(3),[&]{return host.state->cancelled;});
      draining=callbackSelected.load()&&!host.state->returned.load()&&!host.state->physicalExited.load();
      host.state->released=true;lock.unlock();host.state->changed.notify_all();
    });
    auto parked=source("server fn main()->result<str> !{task,fs}{file_read_text(\"text\");task_yield();assert(false);return file_read_text(\"text\");}");
    rejects("E_CANCELLED",[&]{evaluateTaskReference(parked,"main",{},1000000,{},nullptr,&host,&grant);});
    host.state->returned=true;release.join();
    require(callbackSelected&&cancelled&&draining&&host.state->physicalExited&&host.state->destroyed&&!host.admitted,
      "parked020 coordinator missed host cancellation or treated it as physical completion");passed();
  }
  {
    nexrt::FileScope files(capability);nexrt::RequestScope request(1000000,25);auto grant=nexrt::captureFileReadGrant(false);
    auto inherited=nexrt::currentRequestDeadline();require(bool(inherited),"missing inherited root deadline");
    std::this_thread::sleep_until(*inherited+std::chrono::milliseconds(1));size_t started=0;
    nexrt::TaskExecutionLimits limits{1000000,1000,1};
    rejects("E_TIMEOUT",[&]{evaluateTaskReference(read,"main",{},1000000,[&](size_t,const TaskTransition &transition){if(taskFileReadOperation(transition.operation))++started;},&limits,nullptr,&grant);});
    require(!started,"reference renewed an expired inherited request deadline");passed();
  }
  auto old=source("server fn main()->unit !{task,fs}{task_yield();}",SourceLanguage::Tasks019);
  rejects("E_TASK_UNIMPLEMENTED",[&]{evaluateTaskReference(old);});
}
}
int main(){try{astTests();referenceTests();std::cout<<"{\"ok\":true,\"cases\":"<<cases<<",\"language\":\"0.20\",\"source_task_file_reads\":true,\"independent_checked_ast\":true,\"actual_source_workers\":1}\n";return 0;}catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 1;}}
