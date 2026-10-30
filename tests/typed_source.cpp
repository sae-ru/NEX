#include "nex/language.h"
#include "nex/task_frontend.h"
#include "nex/backend.h"
#include "nex/web.h"
#include "nex/operations.h"
#include "nex_source_error.h"
#include <chrono>
#include <cstdio>
#include <filesystem>

using namespace nex;
namespace {
unsigned cases=0;
void require(bool yes,const std::string &message){if(!yes)throw std::runtime_error(message);}
Program source(const std::string &text,SourceLanguage language=SourceLanguage::TypedErrors027){
  auto p=parseVersioned("module typed;\n"+text,"typed.nex",language);check(p);return p;
}
void value(const std::string &text,const std::string &output=""){
  auto before=nexrt::liveObjects.load();
  {auto p=source(text);auto actual=evaluate(p,"main");require(actual.value.getAsInteger()==42,"incorrect reference result at case "+std::to_string(cases));require(actual.output==output,"incorrect evaluation order/output");}
  require(nexrt::liveObjects.load()==before,"typed reference exit retained a value");++cases;
}
template<class F>void rejected(const char *code,F action){
  try{action();}catch(const Error &e){require(e.code==code,std::string("expected ")+code+", got "+e.code+": "+e.what());++cases;return;}
  throw std::runtime_error(std::string("expected rejection ")+code);
}
void rejects(const std::string &text,const char *code){rejected(code,[&]{(void)source(text);});}
}
int main(){try{
  static_assert(int(Stmt::Try)==8&&int(Stmt::Throw)==9&&int(Stmt::Finally)==10&&int(Stmt::TypedThrow)==11&&int(SourceLanguage::ExceptionHandlers026)==9);
  require(currentSourceLanguage==SourceLanguage::ExceptionHandlers026&&std::string(languageVersion)=="0.26","public default advanced before migration");
  value(R"(fn main()->i64{try{throw(42);}catch(error:i64){return error;}})");
  value(R"(fn make()->i64 !{io}{print("once");return 42;}fn main()->i64 !{io}{try{throw(make());}catch(error:i64){return error;}})","once\n");
  value(R"(struct Pair{a:i64;b:i64;}fn left()->i64 !{io}{print("left");return 20;}fn right()->i64 !{io}{print("right");return 22;}fn main()->i64 !{io}{try{throw(Pair(left(),right()));}catch(error:Pair){return error.a+error.b;}})","left\nright\n");
  value(R"(fn main()->i64{try{throw(true);}catch(error:i64){return 0;}catch(error:bool){assert(error);return 42;}})");
  value(R"(fn main()->i64{try{throw(1.25);}catch(error:f64){assert(error==1.25);return 42;}})");
  value(R"(fn main()->i64{try{throw("λ\u0000🙂");}catch(error:str){assert(len(error)==3&&error=="λ\u0000🙂");return 42;}})");
  value(R"(struct Failure{number:i64;message:str;}fn main()->i64{try{throw(Failure(42,"secret"));}catch(error:Failure){assert(error.message=="secret");return error.number;}})");
  value(R"(enum Failure{Missing(path:str);}fn main()->i64{try{throw(Failure::Missing("path"));}catch(error:Failure){match error{Failure::Missing(path)=>{assert(path=="path");return 42;}}}})");
  value(R"(struct A{number:i64;}struct B{number:i64;}fn main()->i64{try{throw(B(42));}catch(error:A){return 0;}catch(error:B){return error.number;}})");
  value(R"(fn main()->i64{let xs:list<str>=[];try{throw(xs);}catch(error:list<i64>){return 0;}catch(error:list<str>){return 42+len(error);}})");
  value(R"(fn main()->i64{try{throw(ok(42));}catch(error:result<i64>){return unwrap(error);}})");
  value(R"(fn main()->i64{try{throw(err<i64>("CODE","message"));}catch(error:result<i64>){assert(!is_ok(error)&&error_code(error)=="CODE");return 42;}})");
  value(R"(fn main()->i64{try{throw(utf8_bytes("λ"));}catch(error:bytes){assert(len(error)==2);return 42;}})");
  value(R"(fn main()->i64{var xs:list<i64>=[42];try{throw(xs);}catch(error:list<i64>){xs=set(xs,0,0);return error[0];}})");
  value(R"(fn main()->i64{var callback:fn()->i64=fn()->i64{return 0;};try{throw(42);}catch(error:i64){callback=fn()->i64{return error;};}return callback();})");
  value(R"(fn main()->i64{try{throw("CODE","legacy");}catch(error:str){return 0;}catch(code,message){assert(code=="CODE"&&message=="legacy");return 42;}})");
  value(R"(fn main()->i64{try{throw("do not format this secret");}catch(code,message){assert(code=="str"&&message=="typed source error");return 42;}})");
  value(R"(fn gate(tag:str,answer:bool)->bool !{io}{print(tag);return answer;}fn main()->i64 !{io}{try{throw(42);}catch(error:str) if gate("wrong",true){return 0;}catch(error:i64) if gate("first",false){return 1;}catch(error:i64) if gate("second",true){return error;}catch(code,message){return 2;}})","first\nsecond\n");
  value(R"(fn gate()->bool !{io}{print("wrong");return true;}fn main()->i64 !{io}{try{throw(42);}catch(error:i64) if false&&gate(){return 0;}catch(error:i64){return error;}})");
  value(R"(fn fail()->bool !{throw}{throw("replacement");}fn main()->i64{try{try{throw(1);}catch(error:i64) if fail(){return 0;}catch(error:str){return 1;}catch(code,message){return 2;}}catch(error:str){assert(error=="replacement");return 42;}catch(code,message){return 3;}})");
  value(R"(fn main()->i64{try{try{throw(1);}catch(error:i64){throw("replacement");}catch(error:str){return 0;}}catch(error:str){assert(error=="replacement");return 42;}})");
  value(R"(fn main()->i64{try{try{throw(42);}catch(error:i64) if false{return 0;}}catch(error:i64){return error;}})");
  value(R"(fn main()->i64{try{throw(42);}catch(error:i64) if true{return error;}})");
  value(R"(fn main()->i64 !{io}{try{try{throw(42);}finally{print("clean");}}catch(error:i64){return error;}})","clean\n");
  value(R"(fn main()->i64 !{throw}{try{throw(1);}finally{return 42;}})");
  value(R"(fn work()->result<i64>{try{let n:i64=err<i64>("RESULT","data")?;return ok(n);}catch(error:i64){return ok(0);}}fn main()->i64{let answer:result<i64>=work();assert(!is_ok(answer)&&error_code(answer)=="RESULT");return 42;})");
  value(R"(fn fail<T>(number:T)->unit !{throw}{throw(number);}fn main()->i64{try{fail(42);return 0;}catch(error:i64){return error;}catch(code,message){return 1;}})");
  value(R"(struct Box<T>{value:T;}fn fail<T>(number:T)->unit !{throw}{throw(Box<T>(number));}fn main()->i64{try{fail(42);return 0;}catch(error:Box<i64>){return error.value;}catch(code,message){return 1;}})");
  rejects(R"(fn main()->unit{throw(42);})","E_EFFECT");
  rejects(R"(fn main()->unit{try{throw(42);}catch(error:str){}})","E_EFFECT");
  rejects(R"(fn main()->unit{try{throw(42);}catch(error:i64) if false{}})","E_EFFECT");
  rejects(R"(fn fail()->unit !{throw}{throw(42);}fn main()->unit{try{fail();}catch(error:i64){}})","E_EFFECT");
  rejects(R"(fn main()->unit{try{throw(42);}catch(error:i64){error=1;}})","E_MUTABILITY");
  rejects(R"(fn main()->i64{try{throw(42);}catch(error:i64){}return error;})","E_NAME");
  rejects(R"(fn main()->unit{try{throw(42);}catch(error:i64){let callback:fn()->unit !{throw}=fn()->unit !{throw}{throw;};}})","E_RETHROW");
  rejects(R"(fn main()->unit{try{let callback:fn()->unit=fn()->unit{throw(42);};callback();}catch(error:i64){}})","E_EFFECT");
  rejects(R"(fn main()->unit{try{throw(42);}catch(error:i64){throw("new");}catch(error:str){}})","E_EFFECT");
  rejects(R"(fn main()->unit{try{}catch(error:unit){}})","E_TYPE");
  rejects(R"(fn nothing()->unit{}fn main()->unit !{throw}{throw(nothing());})","E_TYPE");
  rejects(R"(fn main()->unit !{throw}{throw(fn()->i64{return 42;});})","E_TYPED_EXCEPTION_AUTHORITY");
  rejects(R"(server fn main()->unit{try{}catch(error:file){}})","E_TYPED_EXCEPTION_AUTHORITY");
  rejects(R"(fn main()->unit !{task}{})","E_TYPED_EXCEPTION_TASK");
  {
    auto p=source(R"(fn main()->i64{try{let x:i64=9223372036854775807+1;return x;}catch(error:i64){return 0;}catch(code,message){return 1;}})");
    rejected("E_OVERFLOW",[&]{(void)evaluate(p,"main");});
  }
  {
    auto p=source("fn main()->unit !{throw}{\n try{throw(42);}\n catch(error:i64){throw;}\n}");bool caught=false;
    try{(void)evaluate(p,"main");}catch(const SourceException &e){
      auto expected=sourceErrorTypeKey(p,Type::I64);require(e.payload&&e.payload->getScalar(expected,nexrt::Value::Integer).scalar==42,"bare rethrow lost the original typed value");
      require(e.span.line==3,"bare rethrow replaced source site");
      auto native=nexrt::nativeSourceErrorException(nexrt::nativeSourceErrorRecord(nexrt::NativeSourceException(e.code,e.message,"{\"line\":3}",e.span.line,e.payload)));
      require(native.payload&&native.payload->value.scalar==42&&native.payload->typeKey==expected&&native.line==3,"checked source/native transport mismatch");caught=true;
    }require(caught,"typed error did not escape");++cases;
  }
  {
    auto p=source("fn main()->i64{try{throw(42);}catch(error:i64){return error;}}");
    rejected("E_TYPED_EXCEPTION_MIGRATION",[&]{rejectUnarchivedTasks(p,"archive");});
    rejected("E_TYPED_EXCEPTION_BACKEND",[&]{(void)emitMLIR(p,"main");});
    rejected("E_TYPED_EXCEPTION_BACKEND",[&]{(void)emitTypeScript(p,{{"entry","main"}});});
    auto nodes=operationTree(p,p.function("main"));std::set<std::string> paths;for(const auto &node:nodes)paths.insert(node.path);
    for(const auto &node:nodes)if(node.path.find("/clause/")!=std::string::npos)require(paths.contains(node.parent),"orphan typed handler operation");
    bool binding=false;for(const auto &node:nodes)if(node.kind=="exception.binding"){require(node.definition.getAsObject()->getString("type")=="i64","typed operation binding was a string");binding=true;}
    require(binding,"typed operation binding missing");++cases;
  }
  for(const std::string text:{"fn main()->unit !{throw}{throw(42);}","fn main()->unit{try{}catch(e:i64){}}","fn main()->unit{try{}catch(c,m){}catch(x,y){}}"})
    rejected("E_PARSE",[&]{(void)source(text,SourceLanguage::ExceptionHandlers026);});
  {
    auto directory=std::filesystem::temp_directory_path()/("nex142-typed-modules-"+std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));
    require(std::filesystem::create_directory(directory),"could not create bounded module fixture");
    writeFile((directory/"library.nex").string(),"module errors;pub struct Failure{number:i64;}pub fn fail()->unit !{throw}{throw(Failure(42));}");
    writeFile((directory/"main.nex").string(),"module app;import \"./library.nex\" as lib;fn main()->i64{try{lib::fail();return 0;}catch(error:lib::Failure){return error.number;}catch(code,message){return 1;}}");
    auto p=loadVersionedProgram((directory/"main.nex").string(),directory.string(),SourceLanguage::TypedErrors027);
    require(evaluate(p,"app::main").value.getAsInteger()==42,"module qualification changed typed payload identity");
    std::filesystem::remove_all(directory);++cases;
  }
  require(nexrt::liveObjects.load()==0,"typed-source cases retained owned objects");
  std::printf("{\"ok\":true,\"cases\":%u,\"public_language\":\"0.26\",\"source027_archivable\":false}\n",cases);return 0;
}catch(const std::exception &e){std::fprintf(stderr,"typed-source case%u: %s\n",cases,e.what());return 1;}}
