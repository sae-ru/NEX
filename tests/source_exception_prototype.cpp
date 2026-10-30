#include "nex/language.h"
#include "nex/backend.h"
#include "nex/web.h"
#include "nex/operations.h"
#include "nex/task_frontend.h"
#include "nex_value.h"
#include <iostream>
#include <functional>
#include <algorithm>

using namespace nex;
namespace {
unsigned cases=0;
void require(bool value,const std::string &message){if(!value)throw std::runtime_error(message);}
Program prototype(const std::string &source){
  auto p=parseSourceExceptionsPrototype("module exception_test;\n"+source,"source-exceptions.nex");
  check(p);require(std::string(programLanguage(p))=="0.25-prototype","private identity missing");return p;
}
void value(const std::string &source,int64_t expected=42){
  auto before=nexrt::liveObjects.load();
  {auto p=prototype(source);auto result=evaluate(p,"main",100000);require(result.value.getAsInteger()==expected,"unexpected result");}
  require(nexrt::liveObjects.load()==before,"reference values survived scope cleanup");++cases;
}
void rejects(const std::string &source,const std::string &code){
  try{prototype(source);}catch(const Error &error){require(error.code==code,"expected "+code+", got "+error.code);++cases;return;}
  throw std::runtime_error("expected frontend rejection "+code);
}
void trap(const std::string &source,const std::string &code,uint64_t budget=100000){
  auto before=nexrt::liveObjects.load();bool rejected=false;
  {auto p=prototype(source);try{evaluate(p,"main",budget);}catch(const Error &error){require(error.code==code,"expected trap "+code+", got "+error.code+" after "+std::to_string(cases)+" cases: "+error.what());rejected=true;}}
  require(rejected,"a source catch swallowed a checked trap");require(nexrt::liveObjects.load()==before,"trap leaked reference values");++cases;
}
}
int main(){
  try{
    static_assert(int(SourceLanguage::TaskStreams024)==6&&int(SourceLanguage::SourceExceptions025Prototype)==7&&int(SourceLanguage::SourceExceptions025)==8);
    static_assert(int(Stmt::Match)==7&&int(Stmt::Try)==8&&int(Stmt::Throw)==9&&int(Expr::Propagate)==15);
    require(std::string(languageVersion)=="0.27"&&currentSourceLanguage==SourceLanguage::TypedErrors027,"public027 default absent");
    value(R"(fn main()->i64{try{throw("USER","message");}catch(code,message){assert(code=="USER"&&message=="message");return 42;}})");
    value(R"(fn main()->i64{try{throw("U\u0000SER","start\u0000end");}catch(code,message){assert(len(code)==5&&len(message)==9);assert(code=="U\u0000SER"&&message=="start\u0000end");return 42;}})");
    value(R"(fn leaf()->i64 !{throw}{throw("USER","leaf");}fn main()->i64{try{return leaf();}catch(code,message){return len(code)+len(message)+34;}})");
    value(R"(fn leaf<T:integer>(value:T)->T !{throw}{throw("USER",str(value));}fn main()->i64{try{return leaf(99);}catch(code,message){assert(message=="99");return 42;}})");
    value(R"(fn main()->i64{try{try{throw("ORIGINAL","data");}catch(code,message){assert(code=="ORIGINAL");throw;}}catch(code,message){assert(code=="ORIGINAL"&&message=="data");return 42;}})");
    value(R"(fn main()->i64{try{try{throw("FIRST","data");}catch(code,message){throw("SECOND",message+"!");}}catch(code,message){assert(code=="SECOND"&&message=="data!");return 42;}})");
    value(R"(fn main()->i64{let code:str="outer";try{let code:str="inner";throw("USER",code);}catch(code,message){assert(code=="USER"&&message=="inner");}assert(code=="outer");return 42;})");
    value(R"(fn main()->i64{var output:fn()->str=fn()->str{return "old";};try{throw("USER","captured");}catch(code,message){output=fn()->str{return code+":"+message;};}assert(output()=="USER:captured");return 42;})");
    value(R"(fn main()->i64{let callback:fn()->i64 !{throw}=fn()->i64 !{throw}{throw("LAMBDA","data");};try{return callback();}catch(code,message){assert(code=="LAMBDA");return 42;}})");
    value(R"(fn main()->i64{try{match ok(1){ok(value)=>{let temporary:list<str>=["a","b"];throw("MATCH",str(value));}err(code,message)=>{throw(code,message);}}}catch(code,message){assert(code=="MATCH"&&message=="1");return 42;}})");
    value(R"(fn early()->result<i64>{try{let number:i64=err<i64>("RESULT","unchanged")?;return ok(number);}catch(code,message){return ok(0);}}fn main()->i64{let result:result<i64>=early();assert(!is_ok(result)&&error_code(result)=="RESULT");return 42;})");
    {
      auto p=prototype(R"(fn part(value:str)->str !{io}{print(value);return value;}fn main()->unit !{io,throw}{throw(part("code"),part("message"));})");
      try{evaluate(p,"main",100000);throw std::runtime_error("uncaught source exception missing");}
      catch(const SourceException &error){require(error.code=="code"&&std::string(error.what())=="message"&&error.output=="code\nmessage\n","throw argument evaluation order/output changed");require(error.span.file=="source-exceptions.nex","original throw source absent");}
      ++cases;
    }
    trap(R"(fn main()->i64{try{assert(false);}catch(code,message){return 0;}return 42;})","E_ASSERT");
    trap(R"(fn main()->i64{try{let x:i64=1/0;return x;}catch(code,message){return 0;}})","E_DIV_ZERO");
    trap(R"(fn main()->i64{try{let x:i64=9223372036854775807+1;return x;}catch(code,message){return 0;}})","E_OVERFLOW");
    trap(R"(fn main()->i64{try{while true{let values:list<str>=["alive"];}return 1;}catch(code,message){return 0;}})","E_LIMIT",80);
    rejects(R"(fn main()->unit{throw("USER","missing effect");})","E_EFFECT");
    rejects(R"(fn main()->unit !{throw}{throw;})","E_RETHROW");
    rejects(R"(fn main()->unit{try{throw("USER","x");}catch(code,message){throw("AGAIN",message);}})","E_EFFECT");
    rejects(R"(fn main()->unit{try{let callback:fn()->unit=fn()->unit{throw("USER","x");};callback();}catch(code,message){}})","E_EFFECT");
    rejects(R"(fn main()->unit !{throw}{try{throw("USER","x");}catch(code,message){let callback:fn()->unit !{throw}=fn()->unit !{throw}{throw;};callback();}})","E_RETHROW");
    rejects(R"(fn main()->unit{try{throw("USER","x");}catch(code,code){}})","E_DUPLICATE");
    rejects(R"(fn main()->unit !{throw}{throw(1,"wrong type");})","E_TYPE");
    rejects(R"(fn main()->i64{try{throw("USER","x");}catch(code,message){}return code;})","E_NAME");
    rejects(R"(fn main()->i64{try{return 1;}catch(code,message){}})","E_RETURN");
    rejects(R"(fn main()->unit !{throw}{throw("USER","x");assert(true);})","E_UNREACHABLE");
    rejects(R"(server fn main()->unit !{fs}{})","E_EXCEPTION_STAGE");
    {
      auto p=prototype(R"(fn main()->i64{try{throw("USER","x");}catch(code,message){return 42;}})");
      auto ops=operationTree(p,p.function("main"));require(std::count_if(ops.begin(),ops.end(),[](const auto &op){return op.kind=="exception.binding";})==2,"catch bindings absent from operation graph");
      try{emitMLIR(p,"main",false,false);throw std::runtime_error("native backend accepted incomplete exception lowering");}catch(const Error &e){require(e.code=="E_EXCEPTION_BACKEND","unexpected native diagnostic");}
      bool taskModeRejected=false;try{emitSourceExceptionTasksPrototypeTypeScript(p,{{"main","main"}});}catch(const Error &e){taskModeRejected=e.code=="E_LANGUAGE_VERSION";}require(taskModeRejected,"sequential private program entered task exception TypeScript emitter");
      auto module=emitSourceExceptionsPrototypeTypeScript(p,{{"main","main"}});require(module.privateSourceExceptions&&!module.asynchronous,"private TypeScript helper flag missing");require(module.mapping.getAsObject()->getString("schema")=="nex.private-typescript-exception-map/1","private source map schema missing");
      try{emitTypeScript(p,{{"main","main"}});throw std::runtime_error("TypeScript accepted incomplete exception lowering");}catch(const Error &e){require(e.code=="E_EXCEPTION_BACKEND","unexpected TypeScript diagnostic");}
      try{rejectUnarchivedTasks(p,"archive");throw std::runtime_error("private exceptions were archival");}catch(const Error &e){require(e.code=="E_EXCEPTION_MIGRATION","private archival bypassed migration gate");}
      ++cases;
    }
    {
      auto p=parseVersioned(R"(module retained;fn throw(value:i64)->i64{return value;}fn try()->i64{return throw(42);}fn main()->i64{let catch:i64=try();return catch;})","retained.nex",SourceLanguage::TaskStreams024);check(p);
      require(evaluate(p,"main",100000).value.getAsInteger()==42,"retained024 contextual names changed");
      bool privateRejected=false;try{emitSourceExceptionsPrototypeTypeScript(p,{{"main","main"}});}catch(const Error &e){privateRejected=e.code=="E_LANGUAGE_VERSION";}require(privateRejected,"public program entered private TypeScript emitter");
      require(!emitTypeScript(p,{{"main","main"}}).privateSourceExceptions,"public TypeScript module requested private exception helper");
      require(json(canonical(p.function("main")),false).find("catch_message")==std::string::npos,"retained canonical statement changed");
      bool rejected=false;try{parseVersioned("module x;fn main()->i64{return 42;}","no-public025.nex",SourceLanguage::SourceExceptions025Prototype);}catch(const Error &e){rejected=e.code=="E_LANGUAGE_VERSION";}
      require(rejected,"prototype enabled public version selection");++cases;
    }
    std::cout<<"{\"ok\":true,\"cases\":"<<cases<<",\"public_language\":\"0.25\",\"retained_language\":\"0.24\",\"private_language\":\"0.25-prototype\",\"native_supported\":false,\"typescript_supported\":false,\"task_supported\":false}\n";
    return 0;
  }catch(const SourceException &error){std::cerr<<"unexpected source exception "<<error.code<<": "<<error.what()<<"\n";}
  catch(const Error &error){std::cerr<<"after "<<cases<<" cases: "<<error.code<<": "<<error.what()<<" at "<<error.span.line<<":"<<error.span.column<<"\n";}
  catch(const std::exception &error){std::cerr<<error.what()<<"\n";}
  return 1;
}
