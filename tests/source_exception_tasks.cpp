#include "nex/language.h"
#include "nex/task_frontend.h"
#include "nex/task_reference.h"
#include "nex/task_ir.h"
#include "nex/task_native.h"
#include "nex/task_lifetime.h"
#include "nex/backend.h"
#include "nex/web.h"
#include "nex_host.h"
#include "nex_value.h"
#include "nex_foreign.h"
#include "nex_files.h"
#include <iostream>
#include <filesystem>
#include <functional>
#include <algorithm>
using namespace nex;
namespace {
unsigned cases=0;std::string active;bool taskIR=false;
TaskReferenceResult execute(const Program &p,const std::string &entry="main",const std::vector<nexrt::Value> &args={},uint64_t limit=1000000){return taskIR?evaluateSourceExceptionTaskIRPrototype(p,entry,args,limit):evaluateTaskReference(p,entry,args,limit);}
void require(bool value,const std::string &message){if(!value)throw std::runtime_error(active+": "+message);}
Program program(const std::string &source){auto p=parseSourceExceptionTasksPrototype("module task_exception;\n"+source,"task-source-exceptions.nex");check(p);require(sourceExceptionTasksPrototype(p)&&!isPublicTaskLanguage(p),"private task identity changed");return p;}
void value(const std::string &name,const std::string &source,int64_t expected=42){
 active=name;auto before=nexrt::liveObjects.load();
 {auto p=program(source);auto result=execute(p,"main",{},1000000);require(result.value.tag==nexrt::Value::Integer&&result.value.scalar==expected,"unexpected result");}
 require(nexrt::liveObjects.load()==before,"source values survived scheduler teardown");++cases;
}
void sourceError(const std::string &name,const std::string &source,const std::string &code,const std::string &message,int line=0){
 active=name;auto before=nexrt::liveObjects.load();bool raised=false;
 {auto p=program(source);try{execute(p,"main",{},1000000);}catch(const SourceException &error){require(error.code==code&&error.message==message,"wrong source error");require(error.span.file=="task-source-exceptions.nex"&&(!line||error.span.line==unsigned(line)),"original source span changed");raised=true;}}
 require(raised,"source exception was lost");require(nexrt::liveObjects.load()==before,"uncaught task source error retained values");++cases;
}
void rejects(const std::string &name,const std::string &source,const std::string &code){
 active=name;try{program(source);}catch(const Error &error){require(error.code==code,"wrong rejection "+error.code);++cases;return;}throw std::runtime_error(name+": expected "+code);
}
void trap(const std::string &name,const std::string &source,const std::string &code,uint64_t steps=1000000,bool parentBudget=false,bool parentCancel=false){
 active=name;auto before=nexrt::liveObjects.load();bool raised=false;
 {auto p=program(source);std::unique_ptr<nexrt::RequestScope> request;
 if(parentBudget||parentCancel){request=std::make_unique<nexrt::RequestScope>(parentBudget?200:1000000,10000);if(parentCancel)request->cancel();}
 try{execute(p,"main",{},steps);}catch(const Error &error){require(error.code==code,"wrong trap "+error.code);raised=true;}}
 require(raised,"source catch swallowed control/trap");require(nexrt::liveObjects.load()==before,"trap retained values");++cases;
}
}
int main(int argc,char **argv){try{
 if(argc==4&&(std::string(argv[1])=="public-reference"||std::string(argv[1])=="public-task-ir")){
  auto path=std::filesystem::absolute(argv[2]);auto p=parseVersioned(readFile(path.string()),path.string(),SourceLanguage::ExceptionHandlers026);check(p);
  const auto baseline=nexrt::liveObjects.load();llvm::json::Object observed;
  try{
   auto result=std::string(argv[1])=="public-task-ir"?evaluateTaskIRReference(p,"main",{},std::stoull(argv[3])):evaluateTaskReference(p,"main",{},std::stoull(argv[3]));
   llvm::json::Value value=nullptr;if(p.function("main").result!=Type::Unit)value=result.value.scalar;
   observed=llvm::json::Object{{"kind","return"},{"value",std::move(value)},{"output",result.output}};
  }catch(const SourceException &e){observed=llvm::json::Object{{"kind","exception"},{"code",e.code},{"message",e.message},{"file",e.span.file},{"line",int64_t(e.span.line)},{"column",int64_t(e.span.column)},{"output",e.output}};}
  catch(const Error &e){observed=llvm::json::Object{{"kind","trap"},{"code",e.code}};}
  require(nexrt::liveObjects.load()==baseline,"public task comparison retained managed values");std::cout<<json(std::move(observed))<<'\n';return 0;
 }
 if(argc==6&&(std::string(argv[1])=="http-reference"||std::string(argv[1])=="http-task-ir")){
  auto path=std::filesystem::absolute(argv[2]);auto saved=llvm::json::parse(readFile(path.string()));if(!saved){llvm::consumeError(saved.takeError());throw std::runtime_error("expected private source JSON");}if(!saved->getAsObject())throw std::runtime_error("expected private source context");auto p=loadSourceExceptionTaskContext(*saved->getAsObject());check(p);
  auto decoded=llvm::json::parse(readFile(argv[3]));if(!decoded){llvm::consumeError(decoded.takeError());throw std::runtime_error("expected request JSON");}if(!decoded->getAsObject())throw std::runtime_error("expected request object");
  auto limit=std::stoull(argv[4]);const auto baseline=nexrt::liveObjects.load();std::shared_ptr<nexrt::ForeignLibraries> libraries;llvm::json::Object result;
  {
   nexrt::RequestScope request(limit,30000);nexrt::FileScope files(true);std::unique_ptr<nexrt::ForeignScope> foreign;
   if(std::string(argv[5])!="-"){libraries=nexrt::loadForeignLibraries(argv[5]);foreign=std::make_unique<nexrt::ForeignScope>(libraries);}
   auto data=std::make_shared<nexrt::Data>(nexrt::Data::Record);data->text="std::http::Request";data->names={"method","path","query","body","user","request_id"};
   for(const auto &name:data->names){auto text=decoded->getAsObject()->getString(name);if(!text)throw std::runtime_error("missing request field");data->values.emplace_back(nexrt::string(text->str()));}
   nexrt::TaskExecutionLimits limits;limits.steps=limit;limits.timeoutMs=30000;limits.workers=2;
   try{auto r=std::string(argv[1])=="http-task-ir"?evaluateSourceExceptionTaskIRPrototype(p,"handle",{nexrt::Value(data)},limit,{},&limits):evaluateTaskReference(p,"handle",{nexrt::Value(data)},limit,{},&limits);
    if(r.external.pending||r.external.reservedBytes)throw Error("E_TEST","HTTP reference retained physical IO");auto value=r.value.object;
    if(!value||value->text!="std::http::Response"||value->values.size()!=3)throw Error("E_TEST","unexpected HTTP reference result");
    result=llvm::json::Object{{"kind","return"},{"status",value->values[0].scalar},{"body",value->values[1].object->text},{"content_type",value->values[2].object->text},{"output",r.output}};
   }catch(const SourceException &e){result=llvm::json::Object{{"kind","exception"},{"code",e.code},{"message",e.message},{"line",int64_t(e.span.line)},{"column",int64_t(e.span.column)}};}
   catch(const Error &e){result=llvm::json::Object{{"kind","trap"},{"code",e.code},{"line",int64_t(e.span.line)},{"column",int64_t(e.span.column)}};}
  }
  if(nexrt::liveObjects.load()!=baseline||(libraries&&libraries->resourceBytesUsed()))throw Error("E_TEST","HTTP reference retained managed values or external capacity");
  result["managed_live"]=int64_t(nexrt::liveObjects.load()-baseline);result["external_capacity"]=int64_t(libraries?libraries->resourceBytesUsed():0);libraries.reset();std::cout<<json(std::move(result))<<'\n';return 0;
 }
 if(argc==5&&(std::string(argv[1])=="host-reference"||std::string(argv[1])=="host-task-ir"||std::string(argv[1])=="host-reference-context"||std::string(argv[1])=="host-task-ir-context")){
  auto path=std::filesystem::absolute(argv[2]);auto text=readFile(path.string());auto p=[&](){if(std::string(argv[1]).ends_with("-context")){auto value=llvm::json::parse(text);if(!value){llvm::consumeError(value.takeError());throw std::runtime_error("expected private context JSON");}if(!value->getAsObject())throw std::runtime_error("expected private context object");return loadSourceExceptionTaskContext(*value->getAsObject());}return parseSourceExceptionTasksPrototype(text,path.string());}();check(p);auto limit=std::stoull(argv[3]);
  const auto baseline=nexrt::liveObjects.load();std::shared_ptr<nexrt::ForeignLibraries> libraries;llvm::json::Object result;
  {
   nexrt::RequestScope request(limit,30000);nexrt::FileScope files(true);std::unique_ptr<nexrt::ForeignScope> foreign;
   if(std::string(argv[4])!="-"){libraries=nexrt::loadForeignLibraries(argv[4]);foreign=std::make_unique<nexrt::ForeignScope>(libraries);}
   nexrt::TaskExecutionLimits limits;limits.steps=limit;limits.timeoutMs=30000;limits.workers=2;
   try{auto r=std::string(argv[1]).find("task-ir")!=std::string::npos?evaluateSourceExceptionTaskIRPrototype(p,"main",{},limit,{},&limits):evaluateTaskReference(p,"main",{},limit,{},&limits);
    if(r.external.pending||r.external.reservedBytes)throw Error("E_TEST","private host reference retained physical IO");
    result=llvm::json::Object{{"kind","return"},{"value",r.value.scalar},{"output",r.output},{"external_pending",int64_t(r.external.pending)},{"external_reserved_bytes",int64_t(r.external.reservedBytes)}};
   }catch(const SourceException &e){result=llvm::json::Object{{"kind","exception"},{"code",e.code},{"message",e.message},{"line",int64_t(e.span.line)},{"column",int64_t(e.span.column)},{"file",e.span.file},{"output",e.output}};}
   catch(const Error &e){result=llvm::json::Object{{"kind","trap"},{"code",e.code},{"line",int64_t(e.span.line)},{"column",int64_t(e.span.column)},{"file",e.span.file}};}
  }
  if(nexrt::liveObjects.load()!=baseline||(libraries&&libraries->resourceBytesUsed()))throw Error("E_TEST","private host reference retained managed values or external capacity");
  result["managed_live"]=int64_t(nexrt::liveObjects.load()-baseline);result["external_capacity"]=int64_t(libraries?libraries->resourceBytesUsed():0);libraries.reset();std::cout<<json(std::move(result))<<'\n';return 0;
 }
 if(argc==2&&std::string(argv[1])=="--task-ir"){taskIR=true;argc=1;}
 if(argc==4&&std::string(argv[1])=="task-ir")taskIR=true;
 if(argc==4&&(std::string(argv[1])=="typescript"||std::string(argv[1])=="typescript-context")){
  auto path=std::filesystem::absolute(argv[2]);auto text=readFile(path.string());auto p=[&](){if(std::string(argv[1]).ends_with("-context")){auto decoded=llvm::json::parse(text);if(!decoded){llvm::consumeError(decoded.takeError());throw std::runtime_error("expected private source context");}if(!decoded->getAsObject())throw std::runtime_error("expected private source context object");return loadSourceExceptionTaskContext(*decoded->getAsObject());}return parseSourceExceptionTasksPrototype(text,path.string());}();check(p);
  writeWebModule(emitSourceExceptionTasksPrototypeTypeScript(p,{{"main","main"}}),std::filesystem::absolute(argv[3]).string());return 0;
 }
 if(argc==2||(argc==4&&(std::string(argv[1])=="reference"||std::string(argv[1])=="reference-context"||taskIR))){
  auto limit=argc==2?uint64_t(1000000):std::stoull(argv[3]);
  auto path=std::filesystem::absolute(argv[argc==2?1:2]);auto text=readFile(path.string());auto p=[&](){if(std::string(argv[1]).ends_with("-context")){auto decoded=llvm::json::parse(text);if(!decoded){llvm::consumeError(decoded.takeError());throw std::runtime_error("expected private source context");}if(!decoded->getAsObject())throw std::runtime_error("expected private source context object");return loadSourceExceptionTaskContext(*decoded->getAsObject());}return parseSourceExceptionTasksPrototype(text,path.string());}();check(p);
  try{auto result=execute(p,"main",{},limit);llvm::json::Value value=nullptr;if(p.function("main").result!=Type::Unit)value=result.value.scalar;std::cout<<json(llvm::json::Object{{"kind","return"},{"value",std::move(value)},{"output",result.output}})<<'\n';}
  catch(const SourceException &e){std::cout<<json(llvm::json::Object{{"kind","exception"},{"code",e.code},{"message",e.message},{"file",e.span.file},{"line",int64_t(e.span.line)},{"column",int64_t(e.span.column)},{"output",e.output}})<<'\n';}
  catch(const Error &e){std::cout<<json(llvm::json::Object{{"kind","trap"},{"code",e.code},{"line",int64_t(e.span.line)},{"column",int64_t(e.span.column)},{"file",e.span.file}})<<'\n';}return 0;
 }

 value("yield-catch",R"(fn main()->i64 !{task}{try{task_yield();throw("USER","resumed");}catch(code,message){task_yield();assert(code=="USER"&&message=="resumed");return 42;}})");
 value("direct-call",R"(fn leaf()->str !{task,throw}{task_yield();throw("CALL","leaf");}fn main()->i64 !{task}{try{let values:list<str>=["prefix",leaf()];return 0;}catch(code,message){task_yield();assert(code=="CALL");return 42;}})");
 value("indirect-call",R"(fn main()->i64 !{task}{let cb:fn()->i64 !{task,throw}=fn()->i64 !{task,throw}{task_yield();throw("LAMBDA","value");};try{return cb();}catch(code,message){return 42;}})");
 value("generic-call",R"(fn leaf<T:integer>(v:T)->T !{task,throw}{task_yield();throw("GENERIC",str(v));}fn main()->i64 !{task}{try{return leaf(99);}catch(code,message){assert(message=="99");return 42;}})");
 value("nested-rethrow",R"(fn main()->i64 !{task}{try{try{task_yield();throw("ORIGINAL","payload");}catch(code,message){task_yield();throw;}}catch(code,message){assert(code=="ORIGINAL"&&message=="payload");return 42;}})");
 value("outer-assignment",R"(fn main()->i64 !{task}{var items:list<str>=["old"];try{items=["kept"];task_yield();let temp:list<str>=["discard"];throw("USER","x");}catch(code,message){assert(items[0]=="kept");return 42;}})");
 value("escaped-catch-capture",R"(fn main()->i64 !{task}{var cb:fn()->str=fn()->str{return "old";};try{task_yield();throw("USER","capture");}catch(code,message){cb=fn()->str{return code+":"+message;};task_yield();}assert(cb()=="USER:capture");return 42;})");
 value("result-question-mark",R"(fn early()->result<i64> !{task}{try{task_yield();let n:i64=err<i64>("RESULT","value")?;return ok(n);}catch(code,message){return ok(0);}}fn main()->i64 !{task}{let v:result<i64>=early();assert(!is_ok(v)&&error_code(v)=="RESULT");return 42;})");
 value("future-observed",R"(fn main()->i64 !{task,throw}{return with_tasks(2,fn(s:task_scope)->i64 !{task}{let child:task<i64>=task_spawn(s,fn()->i64 !{task,throw}{task_yield();throw("CHILD","payload");});try{return task_wait(child);}catch(code,message){assert(code=="CHILD"&&message=="payload");task_yield();return 42;}});})");
 value("future-repeated",R"(fn main()->i64 !{task,throw}{return with_tasks(2,fn(s:task_scope)->i64 !{task}{let child:task<i64>=task_spawn(s,fn()->i64 !{throw}{throw("CHILD","repeat");});var count:i64=0;try{task_wait(child);}catch(code,message){count=count+1;}try{task_wait(child);}catch(code,message){assert(code=="CHILD");count=count+1;}assert(count==2);return 42;});})");
 value("spawn-after-recovery",R"(fn main()->i64 !{task,throw}{return with_tasks(2,fn(s:task_scope)->i64 !{task,throw}{let child:task<i64>=task_spawn(s,fn()->i64 !{throw}{throw("CHILD","x");});try{task_wait(child);}catch(code,message){}let replacement:task<i64>=task_spawn(s,fn()->i64 !{task}{task_yield();return 42;});return task_wait(replacement);});})");
 value("drain-unobserved",R"(fn main()->i64 !{task}{try{return with_tasks(2,fn(s:task_scope)->i64 !{task}{let child:task<i64>=task_spawn(s,fn()->i64 !{throw}{throw("UNOBSERVED","drain");});return 0;});}catch(code,message){assert(code=="UNOBSERVED"&&message=="drain");return 42;}})");
 value("drain-cancels-parked-sibling",R"(fn main()->i64 !{task}{try{return with_tasks(2,fn(s:task_scope)->i64 !{task}{let q:channel<i64>=channel_new<i64>(s,0);let blocked:task<i64>=task_spawn(s,fn()->i64 !{task}{return unwrap(task_recv(q));});let failed:task<i64>=task_spawn(s,fn()->i64 !{task,throw}{task_yield();throw("FAILED","close");});return 0;});}catch(code,message){assert(code=="FAILED");return 42;}})");
 value("body-error-cancels-children",R"(fn main()->i64 !{task}{try{return with_tasks(1,fn(s:task_scope)->i64 !{task,throw}{let q:channel<i64>=channel_new<i64>(s,0);let blocked:task<i64>=task_spawn(s,fn()->i64 !{task}{return unwrap(task_recv(q));});task_yield();throw("BODY","wins");});}catch(code,message){assert(code=="BODY"&&message=="wins");return 42;}})");
 value("body-precedence",R"(fn main()->i64 !{task}{try{return with_tasks(2,fn(s:task_scope)->i64 !{task,throw}{let child:task<i64>=task_spawn(s,fn()->i64 !{throw}{throw("CHILD","first");});task_yield();throw("BODY","selected");});}catch(code,message){assert(code=="BODY");return 42;}})");
 value("nested-groups",R"(fn main()->i64 !{task,throw}{return with_tasks(2,fn(outer:task_scope)->i64 !{task}{try{return with_tasks(2,fn(inner:task_scope)->i64 !{task}{let child:task<i64>=task_spawn(inner,fn()->i64 !{throw}{throw("INNER","value");});return 0;});}catch(code,message){assert(code=="INNER");return 42;}});})");
 value("future-own-group",R"(fn main()->i64 !{task,throw}{return with_tasks(2,fn(s:task_scope)->i64 !{task}{let child:task<i64>=task_spawn(s,fn()->i64 !{task,throw}{return with_tasks(1,fn(inner:task_scope)->i64 !{task}{let failed:task<i64>=task_spawn(inner,fn()->i64 !{throw}{throw("NESTED","child");});return 0;});});try{return task_wait(child);}catch(code,message){assert(code=="NESTED");return 42;}});})");
 value("channel-error-data",R"(fn main()->i64 !{task,throw}{return with_tasks(1,fn(s:task_scope)->i64 !{task}{let q:channel<i64>=channel_new<i64>(s,0);assert(task_close(q));try{let result:result<i64>=task_recv(q);assert(!is_ok(result));return 42;}catch(code,message){return 0;}});})");
 value("nul-unicode",R"(fn main()->i64 !{task,throw}{return with_tasks(1,fn(s:task_scope)->i64 !{task}{let child:task<i64>=task_spawn(s,fn()->i64 !{task,throw}{task_yield();throw("A\u0000🧠","λ\u0000🙂");});try{return task_wait(child);}catch(code,message){assert(len(code)==3&&len(message)==3&&code[2]=="🧠");return 42;}});})");
 value("bounded-loop-handlers",R"(fn main()->i64 !{task}{var n:i64=0;while n<1000{try{let values:list<str>=["temporary"];task_yield();throw("LOOP",str(n));}catch(code,message){assert(code=="LOOP");}n=n+1;}return 42;})");
 sourceError("uncaught-root",R"(fn main()->i64 !{task,throw}{task_yield();throw("ROOT","payload");})","ROOT","payload");
 sourceError("uncaught-drain",R"(fn child()->i64 !{task,throw}{
task_yield();throw("ORIGIN","payload");
}fn main()->i64 !{task,throw}{return with_tasks(1,fn(s:task_scope)->i64 !{task}{let child:task<i64>=task_spawn(s,child);return 0;});})","ORIGIN","payload",3);
 sourceError("rethrow-future",R"(fn child()->i64 !{throw}{
throw("ORIGIN","source");
}fn main()->i64 !{task,throw}{return with_tasks(1,fn(s:task_scope)->i64 !{task,throw}{let child:task<i64>=task_spawn(s,child);try{return task_wait(child);}catch(code,message){task_yield();throw;}});})","ORIGIN","source",3);
 rejects("sequential-parser-stays-separate","fn main()->i64 !{task}{return with_tasks(1,fn(s:task_scope)->i64{return 42;});}","E_EFFECT");
 rejects("wait-needs-throw","fn main(t:task<i64>)->i64 !{task}{return task_wait(t);}","E_EFFECT");
 rejects("callback-effect-boundary","fn main()->i64 !{task,throw}{return with_tasks(1,fn(s:task_scope)->i64 !{task}{let child:task<i64>=task_spawn(s,fn()->i64 !{task}{throw(\"BAD\",\"undeclared\");});return 42;});}","E_EFFECT");
 trap("assert-is-fatal",R"(fn main()->i64 !{task}{try{task_yield();assert(false);}catch(code,message){return 0;}return 42;})","E_ASSERT");
 trap("child-trap-is-fatal",R"(fn main()->i64 !{task}{try{return with_tasks(1,fn(s:task_scope)->i64 !{task,throw}{let child:task<i64>=task_spawn(s,fn()->i64{return 1/0;});return task_wait(child);});}catch(code,message){return 0;}})","E_DIV_ZERO");
 trap("child-trap-beats-source",R"(fn main()->i64 !{task}{try{return with_tasks(2,fn(s:task_scope)->i64 !{task}{let fatal:task<i64>=task_spawn(s,fn()->i64{return 1/0;});let failed:task<i64>=task_spawn(s,fn()->i64 !{throw}{throw("USER","secondary");});task_yield();return 0;});}catch(code,message){return 0;}})","E_DIV_ZERO");
 trap("scheduler-budget",R"(fn main()->i64 !{task}{try{while true{task_yield();}}catch(code,message){return 0;}return 42;})","E_LIMIT",200);
 trap("parent-budget",R"(fn main()->i64 !{task}{try{while true{task_yield();}}catch(code,message){return 0;}return 42;})","E_LIMIT",1000000,true);
 trap("parent-cancellation",R"(fn main()->i64 !{task}{try{task_yield();}catch(code,message){return 0;}return 42;})","E_CANCELLED",1000000,false,true);
 active="separate-parser-gate";{bool rejected=false;try{auto p=parseSourceExceptionsPrototype("module sequential;fn main()->unit !{task}{task_yield();}","sequential.nex");check(p);}catch(const Error &e){rejected=e.code=="E_EXCEPTION_STAGE"||e.code=="E_EFFECT";}require(rejected,"sequential parser silently enabled tasks");}
 active="incomplete-backends-gated";{auto p=program(R"(fn main()->i64 !{task}{try{task_yield();throw("USER","x");}catch(code,message){return 42;}})");
 auto lowered=lowerTaskFunction(p,p.function("main"));require(std::any_of(lowered.code.begin(),lowered.code.end(),[](const auto &op){return op.kind==TaskInstruction::PushHandler;}),"exception TaskIR handler missing");
 auto lifetimes=analyzeTaskLifetimes(p,"main");require(lifetimes.handlers&&lifetimes.exceptionalEdges,"exception lifetime traversal missing");
 auto module=emitSourceExceptionTasksPrototypeTypeScript(p,{{"main","main"}});require(module.asynchronous&&module.privateSourceExceptions,"private task exception module flags missing");
 for(auto action:{std::function<void()>([&]{emitSourceExceptionsPrototypeMLIR(p);}),std::function<void()>([&]{emitSourceExceptionsPrototypeTypeScript(p,{{"main","main"}});}),std::function<void()>([&]{emitTaskNativeStep(p,"main");}),std::function<void()>([&]{rejectUnarchivedTasks(p,"archive");})}){
  bool rejected=false;try{action();}catch(const Error &e){rejected=e.code=="E_EXCEPTION_BACKEND"||e.code=="E_EXCEPTION_MIGRATION"||e.code=="E_TASK_UNIMPLEMENTED";}require(rejected,"incomplete backend accepted task exceptions");}++cases;}
 std::cout<<"{\"task_ir_experiment\":"<<(taskIR?"true":"false")<<",\"ok\":true,\"cases\":"<<cases<<",\"public_language\":\"0.24\",\"private_identity\":\"0.25-prototype\",\"task_reference_experiment\":true,\"native_task_exceptions\":true,\"native_execution_in_this_probe\":false,\"typescript_task_exceptions\":true}\n";return 0;
}catch(const SourceException &e){std::cerr<<active<<": unexpected source exception "<<e.code<<": "<<e.message<<"\n";}
catch(const Error &e){std::cerr<<active<<": "<<e.code<<": "<<e.what()<<" at "<<e.span.line<<":"<<e.span.column<<"\n";}
catch(const std::exception &e){std::cerr<<e.what()<<"\n";}return 1;}
