#include "nex/frontend_diagnostics.h"
#include <functional>
#include <iostream>
#include <stdexcept>

using namespace nex;
using JSON=llvm::json::Value;
static void require(bool value,const char *message){if(!value)throw std::runtime_error(message);}
static llvm::json::Array captured;
static JSON failure(const std::function<void()> &action){
  try{action();}catch(const Error &error){auto result=diagnosticJSON(error);captured.push_back(result);return result;}
  throw std::runtime_error("expected frontend error");
}
int main(int argc,char **argv){
  try{
    unsigned cases=0;
    auto context=[&](JSON &value,const char *kind,const char *phase){
      auto object=value.getAsObject();require(object&&object->getString("schema")=="nex.diagnostic/1","missing envelope");
      auto frontend=object->getObject("frontend");require(frontend,"missing captured frontend");
      require(frontend->getString("input_kind")==kind&&frontend->getString("phase")==phase,"wrong input scope/phase");
      require(frontend->getString("id")&&frontend->getString("id")->size()==64,"missing diagnostic identity");
      require(frontend->getObject("source")&&frontend->getObject("preview"),"missing input preview");
      ++cases;return frontend;
    };
    auto unit=failure([]{parse("module bad;fn main()->unit{ return }","<unit>");});context(unit,"unit","parse");
    auto checked=failure([]{auto p=parse("module bad;fn main()->i64{return true;}","<checked>");check(p);});context(checked,"unit","check");
    auto expression=failure([]{parseExpression("1 +","<expression>");});context(expression,"expression","parse");
    auto statement=failure([]{parseStatement("return; extra","<statement>");});context(statement,"statement","parse");
    auto pattern=failure([]{parsePattern("(","<pattern>");});context(pattern,"pattern","parse");
    auto type=failure([]{parseType("list<");});context(type,"type","parse");
    auto invalid=failure([]{parseExpression(std::string("\n")+char(0xff),"<bytes>");});
    auto bytes=context(invalid,"expression","parse");require(invalid.getAsObject()->getInteger("line")==2,"UTF-8 line lost");
    require(bytes->getObject("preview")->getString("encoding")=="base64","invalid bytes were rewritten as source text");
    require(bytes->getObject("preview")->getString("data")=="Cv8=","invalid byte preview is not lossless");
    Error raw("E_TEST","display");raw.span.file=std::string(1,char(0xff));raw.output=std::string(1,char(0xfe));
    auto rendered=diagnosticJSON(raw);auto object=rendered.getAsObject();
    require(object->getArray("escaped_fields")&&object->getString("file")=="\\xff"&&object->getString("stdout")=="\\xfe","invalid display bytes escaped incorrectly");++cases;
    Error message("E_TEST",std::string(1,char(0xff)));auto safe=diagnosticJSON(message);
    require(safe.getAsObject()->getString("message")=="\\xff","invalid error message is not JSON-safe");++cases;
    Error runtime("E_ASSERT","runtime");runtime.operationSite=std::string(64,'a');runtime.operationId=std::string(32,'b');runtime.operationRevision=std::string(64,'c');runtime.operationSource=std::string(64,'d');
    auto legacy=diagnosticJSON(runtime);require(!legacy.getAsObject()->get("frontend")&&legacy.getAsObject()->getString("operation_id")==runtime.operationId,"runtime operation metadata changed");++cases;
    Error malformed("E_TEST","malformed");malformed.frontend=llvm::json::Object{};auto ignored=diagnosticJSON(malformed);
    require(!ignored.getAsObject()->get("frontend"),"incomplete internal context should not crash or masquerade as valid");++cases;
    Error missing("E_FILE","metadata",Span{1,1,0,0,"manifest.json"});attachFrontendDiagnostic(missing,{{"main.nex","module bad;"}},"main.nex","project","load",false);
    auto unavailable=diagnosticJSON(missing);auto frontend=unavailable.getAsObject()->getObject("frontend");
    require(frontend&&frontend->get("source")->getAsNull()&&frontend->get("location")->getAsNull()&&frontend->get("preview")->getAsNull(),"unavailable location was fabricated");++cases;
    Error mismatched("E_TYPE","other input",Span{1,2,1,2,"other.nex"});
    attachFrontendDiagnostic(mismatched,{{"<expression>","some expression"}},"<expression>","expression","check",true);
    auto other=diagnosticJSON(mismatched);auto otherContext=other.getAsObject()->getObject("frontend");
    require(otherContext->get("source")->getAsNull()&&otherContext->get("location")->getAsNull()&&otherContext->get("preview")->getAsNull(),"foreign source position was reassigned to a fragment");++cases;
    Error original("E_DEBUG_LIMIT","original",Span{1,1,0,1,"<fragment>"});
    attachFrontendDiagnostic(original,{{"<fragment>","1"}},"<fragment>","expression","parse",true);
    auto first=diagnosticJSON(original);Error translated("E_PATCH_LIMIT","translated",original.span);translated.frontend=original.frontend;
    auto second=diagnosticJSON(translated);auto oldContext=first.getAsObject()->getObject("frontend"),newContext=second.getAsObject()->getObject("frontend");
    require(oldContext->getString("id")!=newContext->getString("id")&&oldContext->getString("source_inputs_hash")==newContext->getString("source_inputs_hash")&&newContext->getString("code_hash")==hash("E_PATCH_LIMIT"),"translated error retained stale identity or lost source context");++cases;
    std::string longKey(4000,char(1)),longText(8000,char(0));Error bounded("E_TEST","bounded",Span{1,1,0,0,longKey});
    attachFrontendDiagnostic(bounded,{{longKey,longText}},longKey,"unit","parse",true);auto boundedJSON=diagnosticJSON(bounded);frontend=boundedJSON.getAsObject()->getObject("frontend");
    require(frontend->getObject("entry")->getBoolean("truncated")==true,"long input label not bounded");
    require(frontend->getObject("preview")->getString("data")->size()==4096&&json(*boundedJSON.getAsObject()->get("frontend"),false).size()<65536,"bounded preview record grew beyond its scope");++cases;
    std::set<std::string> versionedIds;
    Error defaultWatch("E_EFFECT","watch effect",Span{1,1,0,1,"<watch>"});
    attachFrontendDiagnostic(defaultWatch,{{"<watch>","1"}},"<watch>","expression","check",true);
    auto defaultValue=diagnosticJSON(defaultWatch);
    for(const auto &language:std::vector<std::string>{"0.18","0.19","0.20","0.21","0.22","0.23","0.24","0.25","0.26","0.27","0.25-prototype"}){
      Error selected("E_EFFECT","watch effect",Span{1,1,0,1,"<watch>"});
      attachFrontendDiagnostic(selected,{{"<watch>","1"}},"<watch>","expression","check",true,language);
      auto value=diagnosticJSON(selected);auto front=value.getAsObject()->getObject("frontend");
      require(front->getString("language")==language,"watch source language was retagged");
      require(versionedIds.insert(front->getString("id")->str()).second,"different source languages share a diagnostic identity");
      llvm::json::Object identity{{"schema","nex.frontend-diagnostic-id/1"},{"language",language},
        {"phase",*front->get("phase")},{"input_kind",*front->get("input_kind")},
        {"source_inputs_hash",*front->get("source_inputs_hash")},{"reported_key_hash",hash(selected.span.file)},
        {"location",*front->get("location")},{"code_hash",hash(selected.code)},{"message_hash",hash(selected.what())}};
      require(front->getString("id")==hash(json(std::move(identity),false)),"diagnostic ID does not bind its actual source language");
      if(language==languageVersion)require(json(value,false)==json(defaultValue,false),"ordinary diagnostic identity changed");
      captured.push_back(value);++cases;
    }
    llvm::json::Object report{{"ok",true},{"cases",int64_t(cases)}};
    if(argc==2&&std::string(argv[1])=="--json-records"){
      for(const auto *value:{&rendered,&safe,&legacy,&ignored,&unavailable,&other,&first,&second,&boundedJSON})captured.push_back(*value);
      report["diagnostics"]=std::move(captured);
    }
    std::cout<<json(std::move(report))<<'\n';return 0;
  }catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 1;}
}
