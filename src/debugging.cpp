#include "nex/frontend_diagnostics.h"
#include "nex/debugging.h"
#include "nex/debug_values.h"
#include "nex/task_ir.h"
#include "nex_json.h"
#include "llvm/Support/Error.h"
#include <algorithm>
#include <charconv>
#include <limits>
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
  const bool task=m.getString("schema")=="nex.debug/2";
  if((!task&&m.getString("schema")!="nex.debug/1")||m.getString("runtime_view")!="nex.runtime-view/3"||m.getString("expression_protocol")!=(task?"nex.task-debug-expression/1":"nex.debug-expression/3")||m.getString("compiler_build")!=NEX_BUILD_ID)throw Error("E_DEBUG_BUILD","expression evaluation requires a matching compiler/debug manifest");
  auto bundle=read(std::filesystem::path(path).parent_path()/"source-bundle.json",16*1048576);
  if(hash(json(bundle,false))!=required(m,"source_hash"))throw Error("E_DEBUG_SNAPSHOT","debug source bundle hash differs");
  auto p=loadVersionedBundle(bundle,std::filesystem::absolute(path).parent_path().string(),required(m,"language"));if(revision(p)!=required(m,"revision")||m.getString("language")!=programLanguage(p))throw Error("E_DEBUG_SNAPSHOT","debug revision/language differs from its checked source bundle");
  const auto &f=object(frame);bool partial=task||f.getString("schema")=="nex.debug-frame/2";
  auto frameFields=std::set<std::string>{"schema","language","revision","build_key","function","stop","bindings","truncated"};
  if(partial)frameFields.insert("captures");if(task){frameFields.insert("function_hash");frameFields.insert("metadata_hash");}fields(f,std::move(frameFields));
  if((task?required(f,"schema")!="nex.debug-frame/3":(!partial&&required(f,"schema")!="nex.debug-frame/1"))||required(f,"language")!=programLanguage(p)||required(f,"revision")!=revision(p)||required(f,"build_key")!=required(m,"build_key"))throw Error("E_DEBUG_FRAME","frame and debug build identity differ");
  auto name=required(f,"function");const Object *compiledFunction=nullptr;auto functions=m.getArray("functions");if(functions)for(const auto &value:*functions)if(object(value).getString("name")==name){if(compiledFunction)throw Error("E_DEBUG_BUILD","duplicate compiled debug function");compiledFunction=&object(value);}
  if(!compiledFunction)throw Error("E_DEBUG_FRAME","frame is not a compiled NEX function in this manifest");const auto &fn=p.function(name);
  std::set<std::string> compiledCallables;for(const auto &value:*functions){const auto &entry=object(value);auto symbol=entry.getString("callable_symbol");if(symbol&&!symbol->empty())compiledCallables.insert(required(entry,"name"));}
  auto stop=f.getObject("stop");if(!stop)throw Error("E_DEBUG_FRAME","frame requires stop identity");
  std::map<std::string,const Object*> logicalBindings;
  if(task){
    fields(*stop,{"process_id","process_epoch","stop_id","task_id","task_generation","frame_id","publication","visit","point_id"});
    for(const auto *key:{"process_id","process_epoch","stop_id","task_id","task_generation","frame_id","publication","visit"}){
      auto text=required(*stop,key);uint64_t number=0;auto parsed=std::from_chars(text.data(),text.data()+text.size(),number);
      if(text.empty()||text.size()>20||(text.size()>1&&text.front()=='0')||parsed.ec!=std::errc()||parsed.ptr!=text.data()+text.size()||!number||(std::string(key)=="publication"&&(number&1)))throw Error("E_DEBUG_FRAME","invalid logical task stop identity");
    }
    auto view=m.getObject("task_debug");auto metadata=compiledFunction->getObject("task_debug");
    if(!view||view->getString("schema")!="nex.task-debug-view/1"||view->getInteger("abi")!=1||!metadata||
       view->getString("catalog_symbol")!="nex_task_debug_catalog_v1"||view->getString("marker_symbol")!="nex_task_debug_stop_marker"||
       required(f,"metadata_hash")!=required(*view,"metadata_hash")||required(f,"function_hash")!=hash(json(canonical(fn),false))||
       compiledFunction->getString("function_hash")!=required(f,"function_hash")||compiledFunction->getString("function_source_hash")!=hash(p.definition(fn)))throw Error("E_DEBUG_BUILD","logical frame differs from checked source metadata");
    if(functions->size()>16384)throw Error("E_DEBUG_BUILD","logical function table exceeds its bound");
    std::map<std::string,const Object*> table;for(const auto &entry:*functions){const auto &function=object(entry);if(function.getObject("task_debug")&&!table.emplace(required(function,"name"),&function).second)throw Error("E_DEBUG_BUILD","duplicate logical code function");}
    Array identity;int64_t siteId=0;for(const auto &[functionName,function]:table){const auto &checked=p.function(functionName);auto debug=function->getObject("task_debug");
      auto functionHash=hash(json(canonical(checked),false)),sourceHash=hash(p.definition(checked));
      if(function->getString("function_hash")!=functionHash||function->getString("function_source_hash")!=sourceHash||debug->getInteger("site_id")!=++siteId)throw Error("E_DEBUG_BUILD","logical code table differs from checked source");
      identity.push_back(Object{{"name",functionName},{"function_hash",functionHash},{"function_source_hash",sourceHash},{"task_debug",Object(*debug)}});
    }
    if(hash(json(JSON(std::move(identity)),false))!=required(*view,"metadata_hash"))throw Error("E_DEBUG_BUILD","logical metadata table digest differs");
    auto expected=taskDebugFunctionMetadata(p,fn,required(*metadata,"file"));auto actual=Object(*metadata);actual.erase("site_id");
    if(json(JSON(std::move(expected)),false)!=json(JSON(std::move(actual)),false))throw Error("E_DEBUG_BUILD","logical binding/point metadata differs from checked source");
    auto pointId=stop->getInteger("point_id");auto points=metadata->getArray("points"),bindings=metadata->getArray("bindings");
    if(!pointId||*pointId<1||!points||uint64_t(*pointId)>points->size()||!bindings)throw Error("E_DEBUG_FRAME","unknown logical source point");
    auto visible=object((*points)[*pointId-1]).getArray("visible");if(!visible)throw Error("E_DEBUG_BUILD","missing logical source visibility");
    std::map<int64_t,const Object*> indexed;for(const auto &entry:*bindings){const auto &binding=object(entry);auto id=binding.getInteger("id");if(!id||!indexed.emplace(*id,&binding).second)throw Error("E_DEBUG_BUILD","duplicate logical binding ID");}
    for(const auto &entry:*visible){auto id=entry.getAsInteger();if(!id||!indexed.contains(*id))throw Error("E_DEBUG_BUILD","unknown visible logical binding");auto binding=indexed.at(*id);logicalBindings[required(*binding,"name")]=binding;}
  }else{
    fields(*stop,{"process_id","thread_id","frame_id","stop_id"});
    for(const auto &key:{"process_id","thread_id","stop_id"}){auto v=required(*stop,key);if(v.empty()||v.size()>20||!std::all_of(v.begin(),v.end(),[](char c){return c>='0'&&c<='9';}))throw Error("E_DEBUG_FRAME","stop IDs must be bounded decimal strings");}
    auto frameId=stop->getInteger("frame_id");if(!frameId||*frameId<0||uint64_t(*frameId)>UINT32_MAX)throw Error("E_DEBUG_FRAME","invalid frame index");
  }
  auto bindings=f.getArray("bindings");auto truncated=f.getBoolean("truncated");if(!bindings||bindings->size()>256||!truncated)throw Error("E_DEBUG_FRAME","frame requires at most 256 bindings and a truncation flag");
  std::map<std::string,std::set<std::string>> declared;for(const auto &param:fn.params)declared[param.name].insert(typeName(param.type));
  for(const auto &capture:fn.captures)declared[capture.name].insert(typeName(capture.type));
  std::function<void(E)> locals=[&](E e){if(e){for(auto arm:e->arms)for(const auto &binding:arm->bindings)if(binding.name!="_")declared[binding.name].insert(typeName(binding.type));for(auto child:e->args)locals(child);}};
  std::function<void(const std::vector<S>&)> visit=[&](const auto &body){for(const auto &s:body){if(s->kind==Stmt::Let||s->kind==Stmt::Var)declared[s->name].insert(typeName(s->type));locals(s->expr);childBlocks(s,visit);}};visit(fn.body);
  std::map<std::string,Type> types;Object values;
  for(const auto &value:*bindings){const auto &b=object(value);fields(b,task?std::set<std::string>{"name","type","binding_id","value","unavailable"}:std::set<std::string>{"name","type","value","unavailable"});auto local=required(b,"name"),type=required(b,"type");
    if(task){auto selected=logicalBindings.find(local);if(selected==logicalBindings.end()||b.getInteger("binding_id")!=selected->second->getInteger("id")||type!=required(*selected->second,"type"))throw Error("E_DEBUG_FRAME","binding is not visible at the selected logical point");if(selected->second->getBoolean("opaque").value_or(true)&&b.get("value"))throw Error("E_DEBUG_VALUE","logical authority values are opaque");}
    if(local.empty()||local.size()>256||type.empty()||type.size()>4096||!declared[local].contains(type)||types.contains(local))throw Error("E_DEBUG_FRAME","binding is not a unique declared name/type in the selected function: "+local);
    auto t=resolveType(p,parseType(type));if(typeName(t)!=type)throw Error("E_DEBUG_FRAME","frame requires canonical NEX type names");types.emplace(local,std::move(t));
    if(b.get("value")&&b.get("unavailable"))throw Error("E_DEBUG_FRAME","binding cannot be both captured and unavailable");
    if(auto wire=b.get("value"))values[local]=*wire;else required(b,"unavailable");
  }
  const Array *captures=nullptr;
  if(partial){
    captures=f.getArray("captures");if(!captures||captures->size()>256)throw Error("E_DEBUG_FRAME","partial frame requires at most 256 captures");std::set<std::string> seen;
    for(const auto &capture:*captures){const auto &c=object(capture);fields(c,{"binding","path","kind","value","unavailable","start","count"});auto binding=required(c,"binding"),kind=required(c,"kind");auto path=c.getArray("path");
      if(task&&logicalBindings.contains(binding)&&logicalBindings.at(binding)->getBoolean("opaque").value_or(true))throw Error("E_DEBUG_VALUE","logical authority values cannot be captured");
      std::string selection=kind;
      if(kind=="text_range"){
        int64_t start=0,count=0;
        for(const auto &field:{"start","count"}){auto value=required(c,field);int64_t number=0;auto parsed=std::from_chars(value.data(),value.data()+value.size(),number);
          if(value.empty()||(value.size()>1&&value.front()=='0')||value.front()<'0'||value.front()>'9'||parsed.ec!=std::errc()||parsed.ptr!=value.data()+value.size()||number<0||(std::string(field)=="count"&&number>4096))throw Error("E_DEBUG_FRAME","string range requires canonical nonnegative i64 start and count<=4096");selection+=":"+value;if(std::string(field)=="start")start=number;else count=number;}
        if(start>std::numeric_limits<int64_t>::max()-count)throw Error("E_DEBUG_FRAME","string range end is outside i64");
        if(auto wire=c.get("value")){auto value=wire->getAsString();if(!value||value->size()>16384||int64_t(nexrt::unicodeOffsets(value->str()).size()-1)!=count)throw Error("E_DEBUG_VALUE","string range value differs from its declared scalar count");}
      }else if(c.get("start")||c.get("count"))throw Error("E_DEBUG_FRAME","start/count require a string range capture");
      if(!types.contains(binding)||values.get(binding)||!path||path->size()>56||(kind!="value"&&kind!="shape"&&kind!="text_range")||!seen.insert(binding+":"+json(Array(*path),false)+":"+selection).second)throw Error("E_DEBUG_FRAME","invalid, duplicate or conflicting partial capture");
      Type type=types.at(binding);Array prefix;for(const auto &part:*path){
        if(type.kind==Type::List||type==Type::Bytes){auto i=part.getAsInteger();if(!i||*i<0)throw Error("E_DEBUG_FRAME","collection paths require nonnegative integer indices");type=type==Type::Bytes?Type(Type::I64):*type.element;}
        else if(type.kind==Type::Record){auto field=part.getAsString();bool found=false;const auto &nominal=p.structure(type.name);if(field){if(nominal.enumeration){auto segment=field->str();auto separator=segment.find("::");if(separator!=std::string::npos)for(const auto &variant:nominal.variants)if(variant.name==segment.substr(0,separator))for(const auto &member:variant.fields)if(member.name==segment.substr(separator+2)){type=member.type;found=true;break;}}else for(const auto &member:nominal.fields)if(member.name==*field){type=member.type;found=true;break;}}if(!found)throw Error("E_DEBUG_FRAME","path field is not in its checked nominal type");}
        else if(type.kind==Type::Result){auto field=part.getAsString();if(field=="ok")type=*type.element;else if(field=="code"||field=="message")type=Type::Str;else throw Error("E_DEBUG_FRAME","invalid result path");}
        else if(type.kind==Type::Function){
          const Object *shape=nullptr;for(const auto &entry:*captures){const auto &candidate=object(entry);if(candidate.getString("binding")==binding&&candidate.getArray("path")&&json(Array(*candidate.getArray("path")),false)==json(Array(prefix),false)){auto value=candidate.getObject("value");if(value&&(candidate.getString("kind")=="shape"||candidate.getString("kind")=="value"))shape=value;}}
          if(!shape)throw Error("E_DEBUG_FRAME","callable capture path requires its captured target shape");auto target=shape->getString("function"),field=part.getAsString();if(!target||!field)throw Error("E_DEBUG_FRAME","invalid callable capture path");const auto &callable=checkedDebugCallable(p,target->str(),type,&compiledCallables);bool matched=false;for(const auto &capture:callable.captures)if(capture.name==*field){type=capture.type;matched=true;break;}if(!matched)throw Error("E_DEBUG_FRAME","path field is not in the checked callable environment");
        }
        else throw Error("E_DEBUG_FRAME","partial path descends through a scalar/string");
        prefix.push_back(part);
      }
      if(kind=="shape"&&type.kind!=Type::List&&type!=Type::Bytes&&type!=Type::Str&&type.kind!=Type::Record&&type.kind!=Type::Result&&type.kind!=Type::Function)throw Error("E_DEBUG_FRAME","shape capture requires string, bytes, list, record, result or function type");
      if(kind=="text_range"&&type!=Type::Str)throw Error("E_DEBUG_FRAME","text_range capture requires a string path");
      if(bool(c.get("value"))==bool(c.get("unavailable")))throw Error("E_DEBUG_FRAME","capture requires exactly one value or unavailable reason");if(c.get("unavailable"))required(c,"unavailable");
    }
  }
  auto watchLabel="<watch:"+name+">";E expression;Type type;std::string frontendPhase="parse";
  try{
  expression=parseExpression(source,watchLabel,1024);
  std::vector<std::pair<E,unsigned>> pending{{expression,0}};std::vector<std::pair<S,unsigned>> statements;
  while(!pending.empty()||!statements.empty()){
    if(!pending.empty()){
      auto [e,depth]=pending.back();pending.pop_back();if(depth>128)throw Error("E_DEBUG_LIMIT","expression AST exceeds its depth budget",e->span);
      for(auto arg:e->args)pending.emplace_back(arg,depth+1);
      if(e->lambda)for(auto statement:e->lambda->body)statements.emplace_back(statement,depth+1);
      for(auto arm:e->arms)for(auto statement:arm->body)statements.emplace_back(statement,depth+1);
    }else{
      auto [s,depth]=statements.back();statements.pop_back();if(depth>128)throw Error("E_DEBUG_LIMIT","expression AST exceeds its depth budget",s->span);
      if(s->expr)pending.emplace_back(s->expr,depth+1);childBlocks(s,[&](const auto &body){for(auto child:body)statements.emplace_back(child,depth+1);});
    }
  }
  frontendPhase="bind";bindExpression(p,name,expression);frontendPhase="check";type=checkExpression(p,name,expression,types);
  }catch(Error &error){
    std::map<std::string,std::string> sources;for(const auto &[key,unit]:p.units)sources[key]=unit.source;sources[watchLabel]=source;
    attachFrontendDiagnostic(error,sources,watchLabel,"expression",frontendPhase,true);
    (*error.frontend.getAsObject())["watch"]=Object{{"revision",revision(p)},{"build_key",required(m,"build_key")},
      {"frame_hash",hash(json(frame,false))},{"stop_hash",hash(json(JSON(Object(*stop)),false))},{"function_hash",hash(name)}};
    throw;
  }
  std::set<std::string> referenced;std::function<void(E,std::set<std::string>)> names=[&](E e,std::set<std::string> bound){if(e->kind==Expr::Name&&!bound.contains(e->text))referenced.insert(e->text);
    if(e->kind==Expr::Match){names(e->args[0],bound);for(auto arm:e->arms){auto local=bound;for(const auto &b:arm->bindings)if(b.name!="_")local.insert(b.name);if(arm->guard)names(e->args[arm->guard],local);if(arm->value)names(e->args[arm->value],local);}}
    else for(auto arg:e->args)names(arg,bound);
  };names(expression,{});
  if(task)for(const auto &local:referenced)if(logicalBindings.contains(local)&&logicalBindings.at(local)->getBoolean("opaque").value_or(true))throw Error("E_DEBUG_VALUE","logical authority or effectful callable is opaque: "+local);
  Object output;
  if(plan){Array requested;for(const auto &local:referenced)requested.push_back(Object{{"name",local},{"type",typeName(types.at(local))},{"wire_schema",debugValueSchema(p,types.at(local),&compiledCallables)}});output=Object{{"schema",task?"nex.task-expression-plan/1":"nex.expression-plan/1"},{"ok",true},{"type",typeName(type)},{"variables",std::move(requested)}};}
  else {auto result=evaluateExpression(p,expression,types,values,steps,captures,demand,&compiledCallables);output=std::move(*result.getAsObject());output["schema"]=task?(output.get("request")?"nex.task-expression-demand/1":"nex.task-expression/1"):(output.get("request")?"nex.expression-demand/1":"nex.expression/1");if(type!=Type::Unit)output["wire_schema"]=debugValueSchema(p,type,&compiledCallables);}
  output["language"]=programLanguage(p);output["revision"]=revision(p);output["build_key"]=required(m,"build_key");output["function"]=name;output["expression"]=source;output["stop"]=Object(*stop);output["frame_truncated"]=*truncated;
  output["limits"]=Object{{"steps",int64_t(steps)},{"value_visits",100000},{"value_depth",64},{"cumulative_text_bytes",8*1048576},{"wire_result_bytes",1048576},{"frame_captures",256},{"capture_path_depth",56},{"lazy_references",10000},{"text_range_scalars",4096},{"text_scalar_observations",100000}};
  JSON result=std::move(output);if(json(result,false).size()>4*1048576)throw Error("E_DEBUG_LIMIT","expression response exceeds 4 MiB");return result;
}
}
