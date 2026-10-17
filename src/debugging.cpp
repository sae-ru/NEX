#include "nex/debugging.h"
#include "nex_json.h"
#include "llvm/Support/Error.h"
#include <algorithm>
#include <filesystem>
#include <functional>

namespace nex {
namespace {
using JSON=llvm::json::Value;using Object=llvm::json::Object;using Array=llvm::json::Array;
const Object &object(const JSON &v){auto o=v.getAsObject();if(!o)throw Error("E_DEBUG_FRAME","expected an object");return *o;}
std::string required(const Object &o,const std::string &key){auto value=o.getString(key);if(!value||value->size()>4096||value->contains('\0'))throw Error("E_DEBUG_FRAME","missing/invalid string: "+key);return value->str();}
void fields(const Object &o,std::set<std::string> allowed){for(const auto &[key,_]:o)if(!allowed.contains(key.str()))throw Error("E_DEBUG_FRAME","unknown frame field: "+key.str());}
JSON read(const std::filesystem::path &path,uint64_t limit){if(!std::filesystem::is_regular_file(path)||std::filesystem::file_size(path)>limit)throw Error("E_DEBUG_SNAPSHOT","missing/oversized debug snapshot: "+path.string());auto value=llvm::json::parse(readFile(path.string()));if(!value)throw Error("E_DEBUG_SNAPSHOT",llvm::toString(value.takeError()));return std::move(*value);}
}
JSON parseDebugFrame(const std::string &text){
  try{nexrt::validateJSONText(text);}catch(const nexrt::DataError &error){throw Error("E_DEBUG_FRAME",error.what());}
  llvm::StringRef input(text);if(input.starts_with("\xef\xbb\xbf"))input=input.drop_front(3);
  auto value=llvm::json::parse(input);if(!value)throw Error("E_DEBUG_FRAME",llvm::toString(value.takeError()));return std::move(*value);
}
JSON inspectExpression(const std::string &path,const JSON &frame,const std::string &source,bool plan,uint64_t steps,bool demand){
  if(source.empty()||source.size()>8192||!steps||steps>1000000)throw Error("E_DEBUG_LIMIT","expression requires 1..8192 source bytes and 1..1000000 steps");
  auto manifest=read(path,8*1048576);const auto &m=object(manifest);
  if(m.getString("schema")!="nex.debug/1"||m.getString("runtime_view")!="nex.runtime-view/2"||m.getString("expression_protocol")!="nex.debug-expression/2"||m.getString("language")!=languageVersion||m.getString("compiler_build")!=NEX_BUILD_ID)throw Error("E_DEBUG_BUILD","expression evaluation requires a matching compiler/debug manifest");
  auto bundle=read(std::filesystem::path(path).parent_path()/"source-bundle.json",16*1048576);
  if(hash(json(bundle,false))!=required(m,"source_hash"))throw Error("E_DEBUG_SNAPSHOT","debug source bundle hash differs");
  auto p=loadBundle(bundle,std::filesystem::absolute(path).parent_path().string());if(revision(p)!=required(m,"revision"))throw Error("E_DEBUG_SNAPSHOT","debug revision differs from its checked source bundle");
  const auto &f=object(frame);bool partial=f.getString("schema")=="nex.debug-frame/2";fields(f,partial?std::set<std::string>{"schema","language","revision","build_key","function","stop","bindings","truncated","captures"}:std::set<std::string>{"schema","language","revision","build_key","function","stop","bindings","truncated"});
  if((!partial&&required(f,"schema")!="nex.debug-frame/1")||required(f,"language")!=languageVersion||required(f,"revision")!=revision(p)||required(f,"build_key")!=required(m,"build_key"))throw Error("E_DEBUG_FRAME","frame and debug build identity differ");
  auto name=required(f,"function");bool found=false;auto functions=m.getArray("functions");if(functions)for(const auto &value:*functions)if(object(value).getString("name")==name)found=true;
  if(!found)throw Error("E_DEBUG_FRAME","frame is not a compiled NEX function in this manifest");const auto &fn=p.function(name);
  auto stop=f.getObject("stop");if(!stop)throw Error("E_DEBUG_FRAME","frame requires stop identity");fields(*stop,{"process_id","thread_id","frame_id","stop_id"});
  for(const auto &key:{"process_id","thread_id","stop_id"}){auto v=required(*stop,key);if(v.empty()||v.size()>20||!std::all_of(v.begin(),v.end(),[](char c){return c>='0'&&c<='9';}))throw Error("E_DEBUG_FRAME","stop IDs must be bounded decimal strings");}
  auto frameId=stop->getInteger("frame_id");if(!frameId||*frameId<0||uint64_t(*frameId)>UINT32_MAX)throw Error("E_DEBUG_FRAME","invalid frame index");
  auto bindings=f.getArray("bindings");auto truncated=f.getBoolean("truncated");if(!bindings||bindings->size()>256||!truncated)throw Error("E_DEBUG_FRAME","frame requires at most 256 bindings and a truncation flag");
  std::map<std::string,std::set<std::string>> declared;for(const auto &param:fn.params)declared[param.name].insert(typeName(param.type));
  std::function<void(E)> locals=[&](E e){if(e){for(auto arm:e->arms)for(const auto &binding:arm->bindings)if(binding.name!="_")declared[binding.name].insert(typeName(binding.type));for(auto child:e->args)locals(child);}};
  std::function<void(const std::vector<S>&)> visit=[&](const auto &body){for(const auto &s:body){if(s->kind==Stmt::Let||s->kind==Stmt::Var)declared[s->name].insert(typeName(s->type));locals(s->expr);childBlocks(s,visit);}};visit(fn.body);
  std::map<std::string,Type> types;Object values;
  for(const auto &value:*bindings){const auto &b=object(value);fields(b,{"name","type","value","unavailable"});auto local=required(b,"name"),type=required(b,"type");
    if(local.empty()||local.size()>256||type.empty()||type.size()>4096||!declared[local].contains(type)||types.contains(local))throw Error("E_DEBUG_FRAME","binding is not a unique declared name/type in the selected function: "+local);
    auto t=resolveType(p,parseType(type));if(typeName(t)!=type)throw Error("E_DEBUG_FRAME","frame requires canonical NEX type names");types.emplace(local,std::move(t));
    if(b.get("value")&&b.get("unavailable"))throw Error("E_DEBUG_FRAME","binding cannot be both captured and unavailable");
    if(auto wire=b.get("value"))values[local]=*wire;else required(b,"unavailable");
  }
  const Array *captures=nullptr;
  if(partial){
    captures=f.getArray("captures");if(!captures||captures->size()>256)throw Error("E_DEBUG_FRAME","partial frame requires at most 256 captures");std::set<std::string> seen;
    for(const auto &capture:*captures){const auto &c=object(capture);fields(c,{"binding","path","kind","value","unavailable"});auto binding=required(c,"binding"),kind=required(c,"kind");auto path=c.getArray("path");
      if(!types.contains(binding)||values.get(binding)||!path||path->size()>56||(kind!="value"&&kind!="shape")||!seen.insert(binding+":"+json(Array(*path),false)+":"+kind).second)throw Error("E_DEBUG_FRAME","invalid, duplicate or conflicting partial capture");
      Type type=types.at(binding);for(const auto &part:*path){
        if(type.kind==Type::List){auto i=part.getAsInteger();if(!i||*i<0)throw Error("E_DEBUG_FRAME","list paths require nonnegative integer indices");type=*type.element;}
        else if(type.kind==Type::Record){auto field=part.getAsString();bool found=false;const auto &nominal=p.structure(type.name);if(field){if(nominal.enumeration){auto segment=field->str();auto separator=segment.find("::");if(separator!=std::string::npos)for(const auto &variant:nominal.variants)if(variant.name==segment.substr(0,separator))for(const auto &member:variant.fields)if(member.name==segment.substr(separator+2)){type=member.type;found=true;break;}}else for(const auto &member:nominal.fields)if(member.name==*field){type=member.type;found=true;break;}}if(!found)throw Error("E_DEBUG_FRAME","path field is not in its checked nominal type");}
        else if(type.kind==Type::Result){auto field=part.getAsString();if(field=="ok")type=*type.element;else if(field=="code"||field=="message")type=Type::Str;else throw Error("E_DEBUG_FRAME","invalid result path");}
        else throw Error("E_DEBUG_FRAME","partial path descends through a scalar/string");
      }
      if(kind=="shape"&&type.kind!=Type::List&&type.kind!=Type::Record&&type.kind!=Type::Result)throw Error("E_DEBUG_FRAME","shape capture requires list, record or result type");
      if(bool(c.get("value"))==bool(c.get("unavailable")))throw Error("E_DEBUG_FRAME","capture requires exactly one value or unavailable reason");if(c.get("unavailable"))required(c,"unavailable");
    }
  }
  auto expression=parseExpression(source,"<watch:"+name+">",1024);std::vector<std::pair<E,unsigned>> pending{{expression,0}};while(!pending.empty()){auto [e,depth]=pending.back();pending.pop_back();if(depth>128)throw Error("E_DEBUG_LIMIT","expression AST exceeds its depth budget");for(auto arg:e->args)pending.emplace_back(arg,depth+1);}
  bindExpression(p,name,expression);auto type=checkExpression(p,name,expression,types);
  std::set<std::string> referenced;std::function<void(E,std::set<std::string>)> names=[&](E e,std::set<std::string> bound){if(e->kind==Expr::Name&&!bound.contains(e->text))referenced.insert(e->text);
    if(e->kind==Expr::Match){names(e->args[0],bound);for(auto arm:e->arms){auto local=bound;for(const auto &b:arm->bindings)if(b.name!="_")local.insert(b.name);if(arm->guard)names(e->args[arm->guard],local);if(arm->value)names(e->args[arm->value],local);}}
    else for(auto arg:e->args)names(arg,bound);
  };names(expression,{});
  Object output;
  if(plan){Array requested;for(const auto &local:referenced)requested.push_back(Object{{"name",local},{"type",typeName(types.at(local))},{"wire_schema",wireSchema(p,types.at(local))}});output=Object{{"schema","nex.expression-plan/1"},{"ok",true},{"type",typeName(type)},{"variables",std::move(requested)}};}
  else {auto result=evaluateExpression(p,expression,types,values,steps,captures,demand);output=std::move(*result.getAsObject());output["schema"]=output.get("request")?"nex.expression-demand/1":"nex.expression/1";if(type!=Type::Unit)output["wire_schema"]=wireSchema(p,type);}
  output["language"]=languageVersion;output["revision"]=revision(p);output["build_key"]=required(m,"build_key");output["function"]=name;output["expression"]=source;output["stop"]=Object(*stop);output["frame_truncated"]=*truncated;
  output["limits"]=Object{{"steps",int64_t(steps)},{"value_visits",100000},{"value_depth",64},{"cumulative_text_bytes",8*1048576},{"wire_result_bytes",1048576},{"frame_captures",256},{"capture_path_depth",56},{"lazy_references",10000}};
  JSON result=std::move(output);if(json(result,false).size()>4*1048576)throw Error("E_DEBUG_LIMIT","expression response exceeds 4 MiB");return result;
}
}
