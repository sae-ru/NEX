#include "nex/language.h"
#include "nex_source_error.h"
#include "nex/task_machine.h"
#include "nex/task_ast.h"
#include <future>
#include <filesystem>
#include <chrono>
#include <iostream>
#include <thread>
using namespace nex;
namespace {
unsigned cases=0;
void require(bool value,const char *message){if(!value)throw std::runtime_error(message);}
template<class F>void rejected(F action){try{action();}catch(const Error &e){require(e.code=="E_SOURCE_TYPE","wrong type-key diagnostic");++cases;return;}throw std::runtime_error("missing type-key rejection");}
template<class F>void rejectedValue(F action){try{action();}catch(const nexrt::DataError &e){require(e.code=="E_SOURCE_TYPE","wrong payload diagnostic");++cases;return;}throw std::runtime_error("missing payload rejection");}
Program source(const std::string &body){auto p=parse("module payloads;"+body,"payloads.nex");check(p);return p;}
template<class Machine>void resumedPayload(const std::string &body,bool suppressed=false,bool cancelled=false){
  auto p=source("fn main()->"+std::string(suppressed?"i64":"unit")+" !{task,throw}{"+body+"}");
  const auto baseline=nexrt::liveObjects.load();bool cancel=false;
  std::weak_ptr<const nexrt::SourceErrorPayload> weak;
  {
    auto key=sourceErrorTypeKey(p,Type::Str);
    auto owned=std::make_shared<const nexrt::SourceErrorPayload>(key,nexrt::Value(nexrt::string(std::string("λ\0🙂",7))));weak=owned;
    Machine machine(p,"main",{},1000000,{},0,262144,[&](Span span){if(cancel)throw Error("E_CANCELLED","cancel pending typed packet",span);});
    auto pause=machine.advance();require(pause.kind==TaskTransition::Waiting&&pause.operation=="task_yield","missing protected-body suspension");
    Span origin{71,9,10,20,"typed-original.nex"};SourceException error("TYPED","generic",origin,owned);
    machine.resumeSourceException(pause.ticket,error);owned.reset();error.payload.reset();
    pause=machine.advance();require(pause.kind==TaskTransition::Waiting&&pause.operation=="task_yield"&&!weak.expired(),"typed packet was lost while catch/finally suspended");
    machine.resume(pause.ticket);cancel=cancelled;bool raised=false;
    try{auto done=machine.advance();require(suppressed&&done.kind==TaskTransition::Done&&done.value.scalar==42,"pending source packet was not replaced by finalizer return");}
    catch(const SourceException &e){require(!suppressed&&!cancelled&&e.payload&&e.payload->get(key).object->text==std::string("λ\0🙂",7)&&e.span.file==origin.file&&e.span.line==71&&e.span.column==9,"source rethrow lost typed ownership or origin");raised=true;}
    catch(const Error &e){require(cancelled&&e.code=="E_CANCELLED","fatal control was replaced by a pending typed source error");raised=true;}
    require(suppressed||raised,"typed source error disappeared");
  }
  require(weak.expired()&&nexrt::liveObjects.load()==baseline,"resumable source packet outlived its return/error/cancellation boundary");++cases;
}

}
int main(){try{
  auto p=source("struct Detail{value:str;}struct Envelope{items:list<Detail>;}fn main()->unit{}");
  auto original=revision(p);auto key=sourceErrorTypeKey(p,Type::record("Envelope"));
  require(nexrt::SourceErrorPayload::validKey(key),"type identity is not a complete digest");
  auto changed=source("struct Detail{value:i64;}struct Envelope{items:list<Detail>;}fn main()->unit{}");
  require(sourceErrorTypeKey(changed,Type::record("Envelope"))!=key,"nested nominal layout was omitted from type identity");
  auto reordered=source("struct Extra{unrelated:bool;}struct Envelope{items:list<Detail>;}struct Detail{value:str;}fn main()->unit{}");
  require(sourceErrorTypeKey(reordered,Type::record("Envelope"))==key,"unrelated/declaration order changed a type identity");
  require(revision(p)==original,"type identity changed the source graph");++cases;
  {
    auto path=std::filesystem::temp_directory_path()/("nex-payload-identity-"+std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));
    require(std::filesystem::create_directory(path),"cannot create isolated module identity fixture");
    struct Cleanup{std::filesystem::path path;~Cleanup(){std::error_code error;std::filesystem::remove_all(path,error);}}cleanup{path};
    writeFile((path/"main.nex").string(),p.source);
    writeFile((path/"nex.json").string(),"{\"schema\":\"nex.project/1\",\"language\":\"0.26\",\"entry\":\"main.nex\"}");
    auto loaded=loadVersionedProgram((path/"main.nex").string(),path.string(),SourceLanguage::ExceptionHandlers026);check(loaded);
    require(sourceErrorTypeKey(loaded,Type::record("payloads::Envelope"))==key,"source/module-loader qualification changed the same nominal identity");++cases;
  }
  auto q=parse("module another;fn main()->unit{}","another.nex");check(q);
  for(auto type:{Type(Type::Unit),Type(Type::I64),Type(Type::Bool),Type(Type::F64),Type(Type::Str),Type(Type::Bytes)})
    require(sourceErrorTypeKey(p,type)==sourceErrorTypeKey(q,type),"primitive type identity depends on the caller's module");
  require(sourceErrorTypeKey(p,Type::list(Type::I64))!=sourceErrorTypeKey(p,Type::list(Type::Str)),"empty-list payload types would alias");
  require(sourceErrorTypeKey(p,Type::function({Type::I64},Type::Str))!=sourceErrorTypeKey(p,Type::function({Type::I64},Type::Str,"server",{"io"})),"callable realm/effects were omitted");++cases;
  auto phantom=[](const char *field){return source(std::string("struct Marker{value:")+field+";}struct Phantom<T>{value:i64;}fn main()->unit{let v:Phantom<Marker>=Phantom<Marker>(1);}");};
  auto a=phantom("str"),b=phantom("i64");
  rejected([&]{sourceErrorTypeKey(a,Type::list(Type::constructor("Phantom",2)));});
  auto at=a.function("main").body.at(0)->type,bt=b.function("main").body.at(0)->type;
  require(typeName(at)==typeName(bt),"phantom fixture names differ");
  require(sourceErrorTypeKey(a,at)!=sourceErrorTypeKey(b,bt),"phantom argument's nominal context was omitted");++cases;
  auto higher=source("struct Higher<F<_>>{value:F<i64>;}fn main()->unit{let v:Higher<list>=Higher<list>([1]);}");
  require(nexrt::SourceErrorPayload::validKey(sourceErrorTypeKey(higher,higher.function("main").body.at(0)->type)),"closed higher-kinded arguments were rejected");++cases;
  rejected([&]{sourceErrorTypeKey(p,Type::Unknown);});rejected([&]{sourceErrorTypeKey(p,Type::Parameter);});
  rejected([&]{sourceErrorTypeKey(p,Type::Projection);});rejected([&]{sourceErrorTypeKey(p,Type::record("missing::Type"));});
  rejected([&]{sourceErrorTypeKey(p,Type::constructor("list",1));});
  rejected([&]{sourceErrorTypeKey(p,Type::list(Type::constructor("list",2)));});
  const auto baseline=nexrt::liveObjects.load();auto scalarKey=sourceErrorTypeKey(p,Type::I64);
  rejectedValue([&]{nexrt::SourceErrorPayload payload("short",nexrt::Value(42));});
  rejectedValue([&]{nexrt::SourceErrorPayload payload(std::string(64,'A'),nexrt::Value(42));});
  rejectedValue([&]{nexrt::SourceErrorPayload payload(scalarKey,nexrt::Value(2,true));});
  rejectedValue([&]{nexrt::SourceErrorPayload payload(scalarKey,nexrt::Value(std::shared_ptr<nexrt::Data>{}));});
  {unsigned releases=0;std::weak_ptr<nexrt::Data> weakFailure;
   auto value=std::shared_ptr<nexrt::Data>(new nexrt::Data(nexrt::Data::String),[&](nexrt::Data *p){++releases;delete p;});weakFailure=value;
   rejectedValue([&]{nexrt::SourceErrorPayload invalid("bad",nexrt::Value(std::move(value)));});
   require(weakFailure.expired()&&releases==1&&nexrt::liveObjects.load()==baseline,"rejected packet leaked its already-owned input");}
  {nexrt::SourceErrorPayload payload(scalarKey,nexrt::Value(42));require(payload.get(scalarKey).scalar==42,"typed scalar changed");
   rejectedValue([&]{payload.get(sourceErrorTypeKey(p,Type::Bool));});}
  {nexrt::SourceErrorPayload payload(sourceErrorTypeKey(p,Type::F64),nexrt::Value::floating(1.25));require(payload.value.floating()==1.25,"finite floating payload changed");}++cases;
  std::weak_ptr<nexrt::Data> weak;unsigned destroyed=0;
  {
    auto data=std::shared_ptr<nexrt::Data>(new nexrt::Data(nexrt::Data::String),[&](nexrt::Data *value){++destroyed;delete value;});
    data->text=std::string("λ\0🙂",7);weak=data;
    auto payload=std::make_shared<const nexrt::SourceErrorPayload>(sourceErrorTypeKey(p,Type::Str),nexrt::Value(data));
    SourceException ref("TYPED","generic",Span{47,3,10,20,"origin.nex"},payload);
    nexrt::NativeSourceException native("TYPED","generic","{\"site\":\"original\"}",47,payload);
    auto refCopy=ref;auto nativeCopy=native;data.reset();payload.reset();ref.payload.reset();native.payload.reset();
    require(!weak.expired()&&destroyed==0,"source packet copied a borrow instead of retaining owned data");
    require(refCopy.payload==nativeCopy.payload&&refCopy.payload->value.object->text==std::string("λ\0🙂",7),"reference/native owned payloads disagree");
    require(refCopy.span.file=="origin.nex"&&refCopy.span.line==47&&nativeCopy.line==47&&nativeCopy.source=="{\"site\":\"original\"}","payload transport replaced the original source site");
    auto error=std::make_exception_ptr(nativeCopy);nativeCopy.payload.reset();refCopy.payload.reset();
    std::promise<std::exception_ptr> promise;auto ready=promise.get_future();
    std::thread worker([owned=std::move(error),handoff=std::move(promise)]()mutable{handoff.set_value(std::move(owned));});worker.join();
    auto received=ready.get();require(nexrt::isNativeSourceException(received),"typed packet became a fatal host error");
    try{std::rethrow_exception(received);}catch(const nexrt::NativeSourceException &e){require(e.payload&&e.payload->value.object->text==std::string("λ\0🙂",7)&&e.line==47,"thread handoff lost immutable payload or origin");}
    require(!weak.expired()&&destroyed==0,"exception_ptr handoff dropped its data early");
  }
  require(weak.expired()&&destroyed==1&&nexrt::liveObjects.load()==baseline,"last packet release did not destroy its owned value exactly once");++cases;
  for(const auto &body:{std::string("try{task_yield();}catch(code,message){assert(code==\"TYPED\");task_yield();throw;}"),std::string("try{task_yield();}finally{task_yield();}")}){
    resumedPayload<TaskMachine>(body);resumedPayload<TaskAstMachine>(body);
  }
  const std::string replaced="try{task_yield();}finally{task_yield();return 42;}";
  resumedPayload<TaskMachine>(replaced,true);resumedPayload<TaskAstMachine>(replaced,true);
  const std::string cancelled="try{task_yield();}finally{task_yield();assert(false);}";
  resumedPayload<TaskMachine>(cancelled,false,true);resumedPayload<TaskAstMachine>(cancelled,false,true);
  auto fatal=std::make_exception_ptr(nexrt::DataError("E_MEMORY","fatal"));require(!nexrt::isNativeSourceException(fatal),"typed transport branded a host failure as source control");++cases;
  std::cout<<json(llvm::json::Object{{"ok",true},{"cases",cases},{"owned_payload_packets",true},{"concrete_type_context",true},{"source_syntax_enabled",false}})<<'\n';return 0;
}catch(const Error &e){std::cerr<<e.code<<": "<<e.what()<<'\n';}catch(const std::exception &e){std::cerr<<e.what()<<'\n';}return 1;}
