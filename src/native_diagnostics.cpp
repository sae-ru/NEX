#include "nex/native_diagnostics.h"
#include "nex/operations.h"
#include <deque>
#include <algorithm>

namespace nex {
namespace {
using Object=llvm::json::Object;using Array=llvm::json::Array;using JSON=llvm::json::Value;
bool same(const Object &left,const Object &right,const char *key){
  auto a=left.getString(key),b=right.getString(key);return a&&b&&*a==*b;
}
bool boundedNesting(llvm::StringRef text){
  unsigned depth=0;bool string=false,escape=false;
  for(char c:text){
    if(string){if(escape)escape=false;else if(c=='\\')escape=true;else if(c=='"')string=false;continue;}
    if(c=='"')string=true;
    else if(c=='{'||c=='['){if(++depth>64)return false;}
    else if(c=='}'||c==']'){if(!depth)return false;--depth;}
  }
  return !depth&&!string;
}
bool digest(llvm::StringRef text){return text.size()==64&&text.find_first_not_of("0123456789abcdef")==llvm::StringRef::npos;}
JSON mapReport(const Program &p,const JSON &manifest,Store *store,JSON report){
  Object result{{"status","unmapped"},{"reason","report does not match the selected checked build"},{"report",std::move(report)}};
  auto raw=result.getObject("report");auto build=manifest.getAsObject();
  if(!raw||!build)return result;
  auto site=raw->getObject("source"),app=raw->getObject("application");
  if(!site||!app||raw->getString("schema")!="nex.native-trap/1"||site->getString("schema")!="nex.native-site/1"||app->getString("schema")!="nex.native-application/1")return result;
  if(!raw->getString("code")||raw->getString("code")->size()>512||!raw->getString("message")||raw->getString("message")->size()>16384||!raw->getInteger("reported_line"))return result;
  if(*raw->getInteger("reported_line")<0||!raw->getBoolean("code_truncated")||!raw->getBoolean("message_truncated"))return result;
  if(raw->get("request_id")&&(!raw->getString("request_id")||raw->getString("request_id")->size()>768))return result;
  if(!build->getString("build_key")||!digest(*build->getString("build_key")))return result;
  if(build->getString("schema")!="nex.debug/1"||build->getString("compiler_build")!=NEX_BUILD_ID||build->getString("language")!=languageVersion||build->getString("toolchain")!=NEX_VERSION)return result;
  if(build->getString("revision")!=revision(p)||build->getString("source_hash")!=hash(json(sourceBundle(p),false)))return result;
  for(auto key:{"toolchain","language","revision","source_hash","build_key","compiler_build"})if(!same(*app,*build,key))return result;
  if(!same(*site,*build,"compiler_build"))return result;
  auto operation=site->getString("operation_site"),functionHash=site->getString("function_hash"),sourceHash=site->getString("function_source_hash");
  if(!operation||!functionHash||!sourceHash||!digest(*operation)||!digest(*functionHash)||!digest(*sourceHash))return result;
  auto functions=build->getArray("functions");if(!functions)return result;
  for(const auto &value:*functions){
    auto function=value.getAsObject();if(!function||!same(*site,*function,"function_hash")||!same(*site,*function,"function_source_hash"))continue;
    auto name=function->getString("name");if(!name||name->size()>8192)return result;
    const Function *checked=nullptr;try{checked=&p.function(name->str());}catch(const Error&){return result;}
    if(hash(json(canonical(*checked),false))!=*functionHash||hash(p.definition(*checked))!=*sourceHash)return result;
    auto operations=function->getArray("operation_sites");if(!operations)return result;
    for(const auto &candidate:*operations){
      auto point=candidate.getAsObject();if(!point||point->getString("site")!=*operation)continue;
      if(!same(*site,*point,"kind")||!site->getInteger("byte_begin")||!site->getInteger("byte_end")||site->getInteger("byte_begin")!=point->getInteger("byte_begin")||site->getInteger("byte_end")!=point->getInteger("byte_end"))return result;
      Object node;
      if(store){
        auto context=store->operations(p,name->str(),operation->str(),0,1,true);
        auto nodes=context.getAsObject()->getArray("nodes");if(!nodes||nodes->empty())return result;
        node=*(*nodes)[0].getAsObject();
      }else{
        auto tree=operationTree(p,*checked);
        auto found=std::find_if(tree.begin(),tree.end(),[&](const auto &o){return o.site==*operation;});
        if(found==tree.end())return result;
        node=Object{{"kind",found->kind},{"id",nullptr},{"function_id",nullptr},
          {"location",Object{{"file",checked->unit},{"line",int64_t(found->span.line)},{"column",int64_t(found->span.column)},
            {"byte_begin",int64_t(found->span.begin)},{"byte_end",int64_t(found->span.end)}}}};
      }
      const auto &location=*node.getObject("location");
      if(node.getString("kind")!=site->getString("kind")||*location.getInteger("byte_begin")-int64_t(checked->span.begin)!=*site->getInteger("byte_begin")||*location.getInteger("byte_end")-int64_t(checked->span.begin)!=*site->getInteger("byte_end"))return result;
      result["status"]="mapped";result.erase("reason");
      for(auto key:{"revision","source_hash","build_key"})result[key]=build->getString(key)->str();
      result["symbol"]=name->str();result["operation_site"]=operation->str();
      result["operation_id"]=*node.get("id");result["function_id"]=*node.get("function_id");result["location"]=*node.get("location");
      if(!store)result["identity_scope"]="captured_project";
      return result;
    }
    return result;
  }
  return result;
}
}
JSON parseNativeManifest(const std::string &text){
  if(!boundedNesting(text))throw Error("E_DIAGNOSTIC_LIMIT","native manifest JSON exceeds depth 64 or has unbalanced containers/strings");
  auto parsed=llvm::json::parse(text);if(!parsed)throw Error("E_JSON",llvm::toString(parsed.takeError()));return std::move(*parsed);
}
static JSON diagnostics(const Program &p,const JSON &manifest,Store *store,const std::string &errors){
  constexpr size_t maximum=32,recordBytes=65536;std::deque<JSON> records;size_t total=0,ignored=0;
  llvm::StringRef remaining(errors);
  while(!remaining.empty()){
    auto [line,rest]=remaining.split('\n');remaining=rest;
    if(!line.consume_front("NEX_NATIVE_TRAP "))continue;
    if(line.size()>recordBytes||!boundedNesting(line)){++ignored;continue;}
    auto parsed=llvm::json::parse(line);if(!parsed){llvm::consumeError(parsed.takeError());++ignored;continue;}
    auto object=parsed->getAsObject();if(!object||object->getString("schema")!="nex.native-trap/1"){++ignored;continue;}
    ++total;if(records.size()==maximum)records.pop_front();records.push_back(std::move(*parsed));
  }
  Array diagnostics;for(auto &record:records)diagnostics.push_back(mapReport(p,manifest,store,std::move(record)));
  return Object{{"schema","nex.native-diagnostics/1"},{"diagnostics",std::move(diagnostics)},{"total",int64_t(total)},{"omitted",int64_t(total-records.size())},{"ignored",int64_t(ignored)},{"limit",int64_t(maximum)}};
}
JSON nativeDiagnostics(const Program &p,const JSON &manifest,Store &store,const std::string &errors){return diagnostics(p,manifest,&store,errors);}
JSON nativeDiagnostics(const Program &p,const JSON &manifest,const std::string &errors){return diagnostics(p,manifest,nullptr,errors);}
}
