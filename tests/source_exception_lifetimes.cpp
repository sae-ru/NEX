#include "nex/task_frontend.h"
#include "nex/task_lifetime.h"
#include "nex/task_reference.h"
#include "nex_value.h"
#include <filesystem>
#include <iostream>
using namespace nex;
namespace {
unsigned cases=0;std::string active;
void require(bool ok,const std::string &text){if(!ok)throw std::runtime_error(active+": "+text);}
std::string wrap(const std::string &body){return R"(module lifetime_exception;
fn maybe(flag:bool)->unit !{throw}{if flag{throw("USER","value");}return;}
fn stop()->i64 !{throw}{throw("STOP","no value");}
fn swallowed()->unit{try{throw("LOCAL","handled");}catch(code,message){}return;}
fn shadow(flag:bool)->unit !{throw}{let callback:fn()->i64=fn()->i64{return 42;};if flag{throw("SHADOW","source");}return;}
fn pair(first:i64,second:channel<i64>)->i64{return first;}
fn scenario(flag:bool)->i64 !{task,throw}{
 return with_tasks(1,fn(outer:task_scope)->i64 !{task,throw}{
  let target:channel<fn()->i64>=channel_new<fn()->i64>(outer,4);
  return with_tasks(1,fn(inner:task_scope)->i64 !{task,throw}{
   let local:channel<i64>=channel_new<i64>(inner,1);
   var callback:fn()->i64=fn()->i64{return 42;};
)"+body+R"(
  });
 });
}
fn main()->i64 !{task,throw}{return scenario(true);}
)";}
Program program(const std::string &source){auto p=parseSourceExceptionTasksPrototype(source,"exception-lifetimes.nex");check(p);return p;}
void accepts(const std::string &name,const std::string &body){
 active=name;auto before=nexrt::liveObjects.load();
 {auto p=program(wrap(body));auto report=analyzeTaskLifetimes(p,"scenario");require(report.handlers>0&&report.exceptionalEdges>0,"exception flow missing");auto result=evaluateTaskReference(p,"main",{},1000000);require(result.value.tag==nexrt::Value::Integer&&result.value.scalar==42,"normal semantics changed");}
 require(nexrt::liveObjects.load()==before,"accepted evaluation retained values");++cases;
}
void rejects(const std::string &name,const std::string &body){
 active=name;auto before=nexrt::liveObjects.load();
 {auto p=program(wrap(body));bool staticRejected=false;
 try{analyzeTaskLifetimes(p,"scenario");}catch(const Error &e){require(e.code=="E_TASK_LIFETIME","wrong static diagnostic "+e.code);require(e.span.file=="exception-lifetimes.nex","static source location lost");staticRejected=true;}
 require(staticRejected,"exceptional capability escape was accepted");bool runtimeRejected=false;
 try{evaluateTaskReference(p,"main",{},1000000);}catch(const Error &e){require(e.code=="E_TASK_SCOPE","wrong runtime diagnostic "+e.code);runtimeRejected=true;}
 require(runtimeRejected,"reference allowed an ended-scope capability");}
 require(nexrt::liveObjects.load()==before,"rejected evaluation retained values");++cases;
}
llvm::json::Object reportJSON(const TaskLifetimeReport &r){return llvm::json::Object{{"functions",int64_t(r.functions)},{"regions",int64_t(r.regions)},{"transfers",int64_t(r.transfers)},{"proved",int64_t(r.proved)},{"dynamic",int64_t(r.dynamic)},{"opaque_calls",int64_t(r.opaqueCalls)},{"widenings",int64_t(r.widenings)},{"steps",int64_t(r.steps)},{"handlers",int64_t(r.handlers)},{"exceptional_edges",int64_t(r.exceptionalEdges)},{"exceptional_joins",int64_t(r.exceptionalJoins)}};}
}
int main(int argc,char **argv){try{
 if(argc==2){auto path=std::filesystem::absolute(argv[1]);auto p=parseSourceExceptionTasksPrototype(readFile(path.string()),path.string());check(p);std::cout<<json(reportJSON(analyzeTaskLifetimes(p,"main")))<<'\n';return 0;}
 accepts("repair-before-edge",R"(try{callback=fn()->i64{return len([local])+41;};callback=fn()->i64{return 42;};maybe(flag);}catch(code,message){assert(task_send(target,callback));}return 42;)");
 rejects("edge-before-repair",R"(try{callback=fn()->i64{return len([local])+41;};maybe(flag);callback=fn()->i64{return 42;};}catch(code,message){task_send(target,callback);}return 42;)");
 rejects("hidden-outer-binding",R"(try{callback=fn()->i64{return len([local])+41;};if true{let callback:fn()->i64=fn()->i64{return 42;};maybe(flag);}}catch(code,message){task_send(target,callback);}return 42;)");
 accepts("inner-shadow-does-not-taint-outer",R"(try{if true{let callback:fn()->i64=fn()->i64{return len([local])+41;};maybe(flag);}}catch(code,message){assert(task_send(target,callback));}return 42;)");
 rejects("catch-binding-shadows-outer",R"(try{callback=fn()->i64{return len([local])+41;};throw("USER","shadow");}catch(callback,message){}task_send(target,callback);return 42;)");
 rejects("handler-mutation-before-rethrow",R"(try{try{throw("USER","inner");}catch(code,message){callback=fn()->i64{return len([local])+41;};throw;}}catch(code,message){task_send(target,callback);}return 42;)");
 accepts("handler-repair-before-rethrow",R"(callback=fn()->i64{return len([local])+41;};try{try{throw("USER","inner");}catch(code,message){callback=fn()->i64{return 42;};throw;}}catch(code,message){assert(task_send(target,callback));}return 42;)");
 rejects("snapshot-keeps-captured-origin",R"(callback=fn()->i64{return len([local])+41;};let saved:fn()->i64=fn()->i64{return callback();};callback=fn()->i64{return 42;};try{maybe(flag);}catch(code,message){task_send(target,saved);}return 42;)");
 accepts("snapshot-does-not-follow-later-assignment",R"(let saved:fn()->i64=fn()->i64{return callback();};callback=fn()->i64{return len([local])+41;};try{maybe(flag);}catch(code,message){assert(task_send(target,saved));}return 42;)");
 accepts("terminating-branch-not-in-normal-join",R"(try{if flag{callback=fn()->i64{return len([local])+41;};throw("USER","branch");}else{callback=fn()->i64{return 42;};}}catch(code,message){callback=fn()->i64{return 42;};}assert(task_send(target,callback));return 42;)");
 rejects("callee-spelling-is-not-caller-binding",R"(try{callback=fn()->i64{return len([local])+41;};shadow(flag);callback=fn()->i64{return 42;};}catch(code,message){task_send(target,callback);}return 42;)");
 rejects("indirect-throw-edge",R"(let run:fn()->unit !{throw}=fn()->unit !{throw}{maybe(flag);};try{callback=fn()->i64{return len([local])+41;};run();callback=fn()->i64{return 42;};}catch(code,message){task_send(target,callback);}return 42;)");
 accepts("callee-handler-is-not-dynamic-caller-handler",R"(callback=fn()->i64{return len([local])+41;};try{swallowed();return 42;}catch(code,message){task_send(target,callback);return 42;})");
 accepts("always-throw-skips-later-argument",R"(try{return pair(stop(),with_tasks(1,fn(deep:task_scope)->channel<i64> !{task}{return channel_new<i64>(deep,1);}));}catch(code,message){assert(code=="STOP");return 42;})");
 rejects("wait-edge-keeps-current-alias",R"(let child:task<i64>=task_spawn(inner,fn()->i64 !{throw}{throw("CHILD","wait");});try{callback=fn()->i64{return len([local])+41;};task_wait(child);callback=fn()->i64{return 42;};}catch(code,message){task_send(target,callback);}return 42;)");
 rejects("group-close-edge-keeps-current-alias",R"(try{callback=fn()->i64{return len([local])+41;};with_tasks(1,fn(scope:task_scope)->i64 !{task}{let child:task<i64>=task_spawn(scope,fn()->i64 !{throw}{throw("CHILD","drain");});return 0;});callback=fn()->i64{return 42;};}catch(code,message){task_send(target,callback);}return 42;)");
 rejects("loop-exception-sees-carried-state",R"(var count:i64=0;try{while count<2{callback=fn()->i64{return len([local])+41;};maybe(flag);callback=fn()->i64{return 42;};count=count+1;}}catch(code,message){task_send(target,callback);}return 42;)");
 accepts("loop-repairs-before-possible-throw",R"(var count:i64=0;try{while count<2{callback=fn()->i64{return len([local])+41;};callback=fn()->i64{return 42;};maybe(flag);count=count+1;}}catch(code,message){assert(task_send(target,callback));}return 42;)");
 active="opaque-and-budget-obligations";{
  auto p=program(R"(module opaque;fn scenario(callback:fn()->unit !{throw})->i64 !{task}{try{callback();}catch(code,message){return 42;}return 42;})");
  auto r=analyzeTaskLifetimes(p,"scenario");require(r.dynamic&&r.opaqueCalls&&r.handlers&&r.exceptionalEdges,"opaque call was incorrectly proved");
  auto small=analyzeTaskLifetimes(p,"scenario",1);require(small.dynamic&&small.widenings,"exhausted analysis claimed a static proof");++cases;
 }
 std::cout<<json(llvm::json::Object{{"ok",true},{"cases",int64_t(cases)},{"public_language","0.24"},{"private_identity","0.25-prototype"},{"exception_lifetime_analysis",true},{"complete_region_inference",false}})<<'\n';return 0;
}catch(const Error &e){std::cerr<<active<<": "<<e.code<<": "<<e.what()<<" at "<<e.span.line<<":"<<e.span.column<<'\n';}
catch(const SourceException &e){std::cerr<<active<<": unexpected source error "<<e.code<<": "<<e.message<<'\n';}
catch(const std::exception &e){std::cerr<<e.what()<<'\n';}return 1;}
