#include "nex/api.h"
#include <algorithm>
#include <cctype>
#include <filesystem>
#include <functional>
#include <random>

namespace nex {
namespace {
namespace fs=std::filesystem;
using Object=llvm::json::Object;using Array=llvm::json::Array;using Value=llvm::json::Value;
std::string quote(const std::string &s){return json(s,false);}
std::vector<const Endpoint*> ordered(const Program &p){std::vector<const Endpoint*> result;for(const auto &e:p.endpoints)result.push_back(&e);std::sort(result.begin(),result.end(),[](auto a,auto b){return a->name<b->name;});return result;}
std::string modelPath(std::string module){size_t at;while((at=module.find("::"))!=std::string::npos)module.replace(at,2,"/");return "models/"+module+".nex";}
std::string importPath(const std::string &from,const std::string &target){
  if(target.starts_with("@std/"))return "std/"+target.substr(5);
  if(target.starts_with("@pkg/"))return target.substr(5);
  auto path=fs::path(target).lexically_relative(fs::path(from).parent_path()).generic_string();return path.starts_with(".")?path:"./"+path;
}
Value bundle(const std::map<std::string,std::string> &files,const std::string &entry){Object sources;for(const auto &[key,text]:files)sources[key]=text;return Object{{"schema","nex.sources/1"},{"entry",entry},{"files",std::move(sources)}};}
std::string boundedDigits(const std::string &bound){
  std::string result="[1-9][0-9]{0,"+std::to_string(bound.size()-2)+"}";
  for(size_t i=0;i<bound.size();++i){char low=i? '0':'1',high=bound[i]-1;if(high<low)continue;result+="|"+bound.substr(0,i);result+=low==high?std::string(1,low):"["+std::string(1,low)+"-"+std::string(1,high)+"]";if(i+1<bound.size())result+="[0-9]{"+std::to_string(bound.size()-i-1)+"}";}
  return "(?:"+result+"|"+bound+")";
}
struct Schemas {
  const Program &p;Object records;std::set<std::string> seen;
  Value object(Object properties,Array required){return Object{{"type","object"},{"properties",std::move(properties)},{"required",std::move(required)},{"additionalProperties",false}};}
  Value failure(){return object(Object{{"error",object(Object{{"code",Object{{"type","string"}}},{"message",Object{{"type","string"}}}},Array{"code","message"})}},Array{"error"});}
  Value type(const Type &t){
    if(t==Type::Str)return Object{{"type","string"}};
    if(t==Type::Bytes)return Object{{"type","string"},{"contentEncoding","base64"},{"contentMediaType","application/octet-stream"},{"x-nex-type","bytes"},{"description","Immutable octets encoded as canonical padded base64 with the ordinary alphabet; whitespace and nonzero unused bits are rejected by the runtime."}};
    if(t==Type::Bool)return Object{{"type","boolean"}};
    if(t==Type::F64)return Object{{"type","number"},{"format","double"},{"x-nex-type","f64"},{"description","Finite binary64 JSON number, rounded to nearest with ties to even; zero is normalized."}};
    if(t==Type::I64)return Object{{"type","string"},{"pattern","^(?:0|"+boundedDigits("9223372036854775807")+"|-"+boundedDigits("9223372036854775808")+")(?![\\s\\S])"},{"maxLength",20},{"x-nex-type","i64"},{"description","Canonical decimal string in the signed 64-bit range; JSON numbers are rejected."}};
    if(t.kind==Type::List)return Object{{"type","array"},{"items",type(*t.element)},{"maxItems",10000}};
    if(t.kind==Type::Result)return Object{{"oneOf",Array{object(Object{{"ok",type(*t.element)}},Array{"ok"}),failure()}}};
    if(t.kind==Type::Record){auto key=nativeSymbol(t.name);if(seen.insert(t.name).second){const auto &nominal=p.structure(t.name);auto fields=[&](const auto &members){Object properties;Array required;for(const auto &field:members){properties[field.name]=type(field.type);required.push_back(field.name);}return object(std::move(properties),std::move(required));};
      if(nominal.enumeration){Array variants;for(const auto &variant:nominal.variants)variants.push_back(object(Object{{"case",Object{{"type","string"},{"const",variant.name}}},{"fields",fields(variant.fields)}},Array{"case","fields"}));records[key]=Object{{"oneOf",std::move(variants)}};}else records[key]=fields(nominal.fields);}return Object{{"$ref","#/components/schemas/"+key}};}
    throw Error("E_API_TYPE","unsupported API type");
  }
};
Value openAPI(const Program &p){
  Schemas schemas{p,{}, {}};Object paths;
  for(auto endpoint:ordered(p)){
    const auto &handler=p.function(endpoint->target);Object responses;
    auto response=[&](const std::string &description,Value schema)->Value{return Object{{"description",description},{"content",Object{{"application/json",Object{{"schema",std::move(schema)}}}}}};};
    responses[std::to_string(endpoint->successStatus)]=response("Successful typed result",schemas.object(Object{{"ok",schemas.type(*handler.result.element)}},Array{"ok"}));
    responses["400"]=response("Invalid JSON, body or query",schemas.failure());responses["422"]=response("Handler returned an error; request transaction rolls back",schemas.failure());
    responses["default"]=Object{{"description","Authentication, routing or bounded host failure; clients retain the HTTP status. Host bodies are not endpoint payloads."}};
    Object operation{{"operationId",endpoint->localName},{"responses",std::move(responses)},{"security",Array{Object{{"bearerAuth",Array{}}}}},{"x-nex-handler",handler.name}};
    if(handler.params.size()==2)operation["requestBody"]=Object{{"required",true},{"content",Object{{"application/json",Object{{"schema",schemas.type(handler.params[1].type)}}}}}};
    auto method=endpoint->method;std::transform(method.begin(),method.end(),method.begin(),[](unsigned char c){return std::tolower(c);});
    if(!paths.get(endpoint->path))paths[endpoint->path]=Object{};(*paths.getObject(endpoint->path))[method]=std::move(operation);
  }
  return Object{{"openapi","3.1.1"},{"info",Object{{"title",p.module},{"version",revision(p)}}},{"paths",std::move(paths)},{"components",Object{{"schemas",std::move(schemas.records)},{"securitySchemes",Object{{"bearerAuth",Object{{"type","http"},{"scheme","bearer"}}}}}}},{"x-nex-wire","nex.wire/2"},{"x-nex-language",languageVersion}};
}
struct SourceTypes {
  const Program &p;std::string unit,owner;std::map<std::string,std::string> aliases;
  bool extracted=true;std::set<std::string> existing;
  std::string type(const Type &t){
    if(t.kind==Type::List||t.kind==Type::Result)return std::string(t.kind==Type::List?"list<":"result<")+type(*t.element)+">";
    if(t.kind==Type::Function){
      std::string text=(t.realm=="shared"?"":t.realm+" ")+std::string("fn(");for(size_t i=0;i<t.arguments.size();++i){if(i)text+=", ";text+=type(t.arguments[i]);}
      auto result=type(*t.element);text+=")->"+(t.element->kind==Type::Function?"("+result+")":result);
      if(!t.effects.empty()){text+=" !{";bool first=true;for(const auto &effect:t.effects){if(!first)text+=", ";first=false;text+=effect;}text+="}";}return text;
    }
    if(t.kind==Type::Parameter)return t.name.substr(t.name.rfind("::")+2);
    if(t.kind!=Type::Record)return typeName(t);
    if(!t.arguments.empty()){auto result=type(Type::record(t.name))+"<";for(size_t i=0;i<t.arguments.size();++i){if(i)result+=", ";result+=type(t.arguments[i]);}return result+">";}
    const auto &nominal=p.structure(t.name);if(!nominal.templateName.empty()){auto result=type(Type::record(nominal.templateName))+"<";for(size_t i=0;i<nominal.typeArguments.size();++i){if(i)result+=", ";result+=type(nominal.typeArguments[i]);}return result+">";}
    const auto &s=p.structure(t.name);if(s.owner==owner)return s.localName;
    if(!aliases.contains(s.owner)){auto alias="_model"+std::to_string(aliases.size());while(existing.contains(alias))alias+="_";aliases[s.owner]=alias;}return aliases.at(s.owner)+"::"+s.localName;
  }
  std::string imports()const{
    std::string result;for(const auto &[module,alias]:aliases){if(existing.contains(alias))continue;std::string target=modelPath(module);for(const auto &[key,source]:p.units)if(source.module==module&&(!extracted||key.starts_with("@")))target=key;result+="import "+quote(importPath(unit,target))+" as "+alias+";\n";}return result;
  }
};
Value clientProjection(std::map<std::string,std::string> sources,const std::string &entry,const std::string &directory){
  // Remove server declarations before checking the SDK. Its standard/library
  // dependencies may themselves contain server implementations or endpoints.
  for(auto &[key,text]:sources){auto unit=parse(text,key);std::string projected="module "+unit.module+";\n";
    for(const auto &dep:unit.imports)projected+="import "+quote(dep.path)+" as "+dep.alias+";\n";
    for(const auto &s:unit.structures)projected+=unit.definition(s)+"\n";
    for(const auto &f:unit.functions)if(f.realm!="server"&&!f.test)projected+=unit.definition(f)+"\n";
    text=std::move(projected);
  }
  auto p=loadBundle(bundle(sources,entry),directory);
  std::set<std::string> functions,structures;
  std::function<void(const Type&)> type=[&](const Type &t){if(t.element)type(*t.element);if(t.kind==Type::Function)for(const auto &argument:t.arguments)type(argument);if(t.kind==Type::Record&&structures.insert(t.name).second){const auto &s=p.structure(t.name);if(!s.templateName.empty())type(Type::record(s.templateName));for(const auto &argument:s.typeArguments)type(argument);for(auto field:s.members())type(field->type);}};
  std::function<void(E)> expression=[&](E e){if(e){type(e->type);for(auto a:e->args)expression(a);}};
  std::function<void(const std::vector<S>&)> block=[&](const auto &body){for(auto s:body){type(s->type);expression(s->expr);childBlocks(s,block);}};
  std::function<void(const Function&)> function=[&](const Function &f){if(!functions.insert(f.name).second)return;if(f.realm=="server"||f.test)throw Error("E_REALM","server/test code cannot enter the client SDK",f.span);if(!f.templateName.empty())function(p.function(f.templateName));type(f.result);for(const auto &param:f.params)type(param.type);block(f.body);for(const auto &callee:f.dependencies)function(p.function(callee));};
  // Retain the generated SDK and the public client/shared surface of captured
  // dependency libraries, plus the private helpers/types those exports use.
  for(const auto &f:p.functions)if(f.exported&&(f.unit==entry||f.unit.starts_with("@")))function(f);
  std::map<std::string,std::set<std::string>> references;
  std::function<void(const Type&,const std::string&)> reference=[&](const Type &t,const std::string &unit){if(t.element)reference(*t.element,unit);if(t.kind==Type::Function)for(const auto &argument:t.arguments)reference(argument,unit);if(t.kind==Type::Record){const auto &s=p.structure(t.name);references[unit].insert(s.unit);for(const auto &argument:s.typeArguments)reference(argument,unit);}};
  for(const auto &f:p.functions)if(functions.contains(f.name)){
    reference(f.result,f.unit);for(const auto &param:f.params)reference(param.type,f.unit);
    for(const auto &callee:f.dependencies)references[f.unit].insert(p.function(callee).unit);
    std::function<void(E)> expr=[&](E e){if(e){reference(e->type,f.unit);for(auto a:e->args)expr(a);}};
    std::function<void(const std::vector<S>&)> body=[&](const auto &statements){for(auto s:statements){reference(s->type,f.unit);expr(s->expr);childBlocks(s,body);}};body(f.body);
  }
  for(const auto &s:p.structures)if(structures.contains(s.name))for(auto field:s.members())reference(field->type,s.unit);
  std::map<std::string,std::string> projected;std::set<std::string> reachable;
  std::function<void(const std::string&)> unit=[&](const std::string &key){if(!reachable.insert(key).second)return;const auto &source=p.units.at(key);std::string text="module "+source.module+";\n";
    for(const auto &dep:source.imports)if(references[key].contains(dep.target)){text+="import "+quote(dep.path)+" as "+dep.alias+";\n";unit(dep.target);}
    for(const auto &s:p.structures)if(s.unit==key&&s.templateName.empty()&&structures.contains(s.name))text+=p.definition(s)+"\n";
    for(const auto &f:p.functions)if(f.unit==key&&f.templateName.empty()&&!f.closure&&functions.contains(f.name))text+=p.definition(f)+"\n";
    projected[key]=std::move(text);
  };unit(entry);
  auto result=bundle(projected,entry);loadBundle(result,directory);return result;
}
}
Value describeAPI(const Program &p){
  Array endpoints;
  for(auto e:ordered(p)){const auto &handler=p.function(e->target);Array effects;for(const auto &effect:handler.effects)effects.push_back(effect);
    endpoints.push_back(Object{{"name",e->name},{"operation",e->localName},{"method",e->method},{"path",e->path},{"success_status",e->successStatus},{"handler",e->target},{"input",handler.params.size()==2?wireSchema(p,handler.params[1].type):Value(nullptr)},{"result",wireSchema(p,handler.result)},{"effects",std::move(effects)},{"request_function","request_"+e->localName},{"response_function","response_"+e->localName}});
  }
  return Object{{"schema","nex.api/1"},{"language",languageVersion},{"revision",revision(p)},{"endpoints",std::move(endpoints)}};
}
Value generateAPI(const Program &p,const std::string &directory){
  if(p.endpoints.empty())throw Error("E_API_EMPTY","declare at least one endpoint before generation");
  auto output=fs::absolute(directory);if(fs::exists(output)&&(!fs::is_directory(output)||!fs::is_empty(output)))throw Error("E_EXISTS","API generation requires a new or empty directory");
  std::map<std::string,std::string> server,client;
  for(const auto &[key,unit]:p.units)server[key]=unit.source;
  std::function<void(std::map<std::string,std::string>&,const std::string&)> standard=[&](auto &files,const std::string &key){
    if(files.contains(key))return;
    if(!p.units.contains(key)&&!key.starts_with("@std/"))throw Error("E_API_LIBRARY","missing captured API library source "+key);
    auto text=p.units.contains(key)?p.units.at(key).source:readFile(resourceFile("lib/"+key.substr(5)));files[key]=text;
    auto parsed=parse(text,key);for(const auto &dependency:parsed.imports){std::string target;if(dependency.path.starts_with("std/"))target="@std/"+dependency.path.substr(4);else if(dependency.path.starts_with("./")||dependency.path.starts_with("../")){target=(fs::path(key).parent_path()/dependency.path).lexically_normal().generic_string();auto base=key.starts_with("@std/")?"@std/":key.substr(0,key.find('/',5)+1);if(!target.starts_with(base))throw Error("E_API_LIBRARY","dependency escapes library root");}else target="@pkg/"+dependency.path;standard(files,target);}
  };
  standard(server,"@std/http.nex");standard(server,"@std/api.nex");standard(client,"@std/net.nex");
  auto basePrefix="_nex_api_"+hash(p.module).substr(0,16);std::string prefix=basePrefix;for(unsigned i=0;;++i){bool collision=false;for(const auto &[key,unit]:p.units)if(unit.module==prefix||unit.module.starts_with(prefix+"::"))collision=true;if(!collision)break;prefix=basePrefix+"_"+std::to_string(i);}
  std::map<std::string,std::string> routers;std::map<std::string,std::set<std::string>> used;
  for(const auto &f:p.functions)used[f.unit].insert(f.localName);for(const auto &s:p.structures)used[s.unit].insert(s.localName);for(const auto &[key,unit]:p.units)for(const auto &dep:unit.imports)used[key].insert(dep.alias);
  for(const auto &endpoint:p.endpoints)used[endpoint.unit].insert(endpoint.localName);
  auto fresh=[&](const std::string &unit,std::string value){while(used[unit].contains(value))value+="_";used[unit].insert(value);return value;};
  auto endpoints=ordered(p);std::set<std::string> allEffects;
  auto effects=[](const std::set<std::string> &values){std::string text;if(!values.empty()){text=" !{";for(const auto &v:values){if(text.back()!='{')text+=", ";text+=v;}text+="}";}return text;};
  for(auto e:endpoints)routers[e->unit]="";
  for(auto &[unit,router]:routers){
    router=fresh(unit,"_nex_api_dispatch");auto http=fresh(unit,"_nex_api_http"),context=fresh(unit,"_nex_api_context");
    SourceTypes types{p,unit,p.units.at(unit).module,{},false,{}};
    for(const auto &dep:p.units.at(unit).imports){types.aliases[p.units.at(dep.target).module]=dep.alias;types.existing.insert(dep.alias);}
    std::string body;std::set<std::string> required;
    for(auto e:endpoints)if(e->unit==unit){
      const auto &handler=p.function(e->target);required.insert(handler.effects.begin(),handler.effects.end());std::string target=handler.localName;
      if(handler.owner!=p.units.at(unit).module)for(const auto &dep:p.units.at(unit).imports)if(p.units.at(dep.target).module==handler.owner){target=dep.alias+"::"+handler.localName;break;}
      auto result=types.type(handler.result);
      auto bad=[&](const std::string &message){return "return "+http+"::json_response(400, encode_json(err<"+types.type(*handler.result.element)+">(\"E_API_INPUT\", "+quote(message)+")));";};
      body+="  if request.method == "+quote(e->method)+" && request.path == "+quote(e->path)+" {\n    if request.query != \"\" { "+bad("Query parameters are not declared")+" }\n";
      std::string arguments=context+"::Context(request.user, request.request_id)";
      if(handler.params.size()==2){auto input=types.type(handler.params[1].type);body+="    let decoded: result<"+input+"> = decode_json<"+input+">(request.body);\n    if !is_ok(decoded) { "+bad("Invalid request body")+" }\n";arguments+=", unwrap(decoded)";}
      else body+="    if request.body != \"\" { "+bad("This endpoint has no request body")+" }\n";
      body+="    let outcome: "+result+" = "+target+"("+arguments+");\n    if is_ok(outcome) { return "+http+"::json_response("+std::to_string(e->successStatus)+", encode_json(outcome)); }\n    return "+http+"::json_response(422, encode_json(outcome));\n  }\n";
    }
    allEffects.insert(required.begin(),required.end());
    server[unit]+="\nimport \"std/http.nex\" as "+http+";\nimport \"std/api.nex\" as "+context+";\n"+types.imports()+"pub server fn "+router+"(request: "+http+"::Request) -> "+http+"::Response"+effects(required)+" {\n"+body+"  return "+http+"::json_response(404, encode_json(err<bool>(\"E_API_ROUTE\", \"Unknown endpoint\")));\n}\n";
  }
  std::string entry="_nex_api_server.nex";while(server.contains(entry))entry="_"+entry;
  std::string dispatch="module "+prefix+"::server_app;\nimport \"std/http.nex\" as http;\nimport "+quote(importPath(entry,p.entryUnit))+" as root_sources;\n";
  std::map<std::string,std::string> routeAliases;for(const auto &[unit,router]:routers){auto alias="route"+std::to_string(routeAliases.size());routeAliases[unit]=alias;dispatch+="import "+quote(importPath(entry,unit))+" as "+alias+";\n";}
  dispatch+="server fn handle(request: http::Request) -> http::Response"+effects(allEffects)+" {\n";
  for(auto e:endpoints)dispatch+="  if request.method == "+quote(e->method)+" && request.path == "+quote(e->path)+" { return "+routeAliases.at(e->unit)+"::"+routers.at(e->unit)+"(request); }\n";
  std::set<std::string> paths;for(auto e:endpoints)paths.insert(e->path);for(const auto &path:paths)dispatch+="  if request.path == "+quote(path)+" { return http::json_response(405, encode_json(err<bool>(\"E_API_METHOD\", \"Method not allowed\"))); }\n";
  dispatch+="  return http::json_response(404, encode_json(err<bool>(\"E_API_ROUTE\", \"Unknown endpoint\")));\n}\n";server[entry]=dispatch;
  // Extract model declarations only. Server implementations never enter the SDK.
  std::set<std::string> models,visited;
  std::function<void(const Type&)> include=[&](const Type &t){if(t.element)include(*t.element);if(t.kind==Type::Function)for(const auto &argument:t.arguments)include(argument);if(t.kind==Type::Record&&visited.insert(t.name).second){const auto &s=p.structure(t.name);if(s.templateName.empty())models.insert(s.name);else include(Type::record(s.templateName));for(const auto &argument:s.typeArguments)include(argument);for(auto field:s.members())include(field->type);}};
  for(auto e:endpoints){const auto &handler=p.function(e->target);include(handler.result);if(handler.params.size()==2)include(handler.params[1].type);}
  std::map<std::string,std::vector<const Structure*>> groups;
  for(const auto &name:models){const auto &s=p.structure(name);if(s.unit.starts_with("@"))standard(client,s.unit);else groups[s.owner].push_back(&s);}
  for(const auto &[owner,structures]:groups){auto path=modelPath(owner);SourceTypes types{p,path,owner,{},true,{}};std::string body;
    for(auto s:structures){auto name=s->localName;if(!s->typeParameters.empty()){name+="<";for(size_t i=0;i<s->typeParameters.size();++i){if(i)name+=", ";const auto &parameter=s->typeParameters[i];name+=parameter.substr(parameter.rfind("::")+2);if(i<s->typeBounds.size()&&!s->typeBounds[i].empty()){name+=": ";bool first=true;for(const auto &bound:s->typeBounds[i]){if(!first)name+=" + ";first=false;name+=bound;}}}name+=">";}
      if(s->enumeration){body+="pub enum "+name+" { ";for(const auto &variant:s->variants){body+=variant.name;if(!variant.fields.empty()){body+="(";for(size_t i=0;i<variant.fields.size();++i){if(i)body+=", ";body+=variant.fields[i].name+": "+types.type(variant.fields[i].type);}body+=")";}body+="; ";}body+="}\n";}
      else{body+="pub struct "+name+" { ";for(const auto &field:s->fields)body+=field.name+": "+types.type(field.type)+"; ";body+="}\n";}}
    client[path]="module "+owner+";\n"+types.imports()+body;
  }
  SourceTypes clientTypes{p,"api.nex",prefix+"::client_sdk",{},true,{}};std::string helpers;
  for(auto e:endpoints){const auto &handler=p.function(e->target);auto result=clientTypes.type(handler.result),payload=clientTypes.type(*handler.result.element);std::string input,body="\"\"";
    if(handler.params.size()==2){input=", input: "+clientTypes.type(handler.params[1].type);body="encode_json(input)";}
    helpers+="pub fn request_"+e->localName+"(id: str, token: str"+input+", action: str, timeout_ms: i64) -> net::Command {\n  return net::typed_request(id, "+quote(e->method)+", "+quote(e->path)+", "+body+", token, action, timeout_ms, "+quote(json(wireSchema(p,handler.result),false))+");\n}\n";
    helpers+="pub fn response_"+e->localName+"(event: web::Event) -> "+result+" {\n  let envelope: result<net::Response> = net::response(event);\n  if !is_ok(envelope) { return err(error_code(envelope), error_message(envelope)); }\n  let response: net::Response = unwrap(envelope);\n  if !is_ok(response.body) { return err(error_code(response.body), error_message(response.body)); }\n  let decoded: result<"+result+"> = decode_json<"+result+">(unwrap(response.body));\n  if response.status == "+std::to_string(e->successStatus)+" {\n    if !is_ok(decoded) { return err(error_code(decoded), error_message(decoded)); }\n    if !is_ok(unwrap(decoded)) { return err(\"E_API_PROTOCOL\", \"Success status contains an error result\"); }\n    return unwrap(decoded);\n  }\n  if response.status >= 400 {\n    if is_ok(decoded) && !is_ok(unwrap(decoded)) { return unwrap(decoded); }\n    return err(\"HTTP_\" + str(response.status), \"Request rejected\");\n  }\n  return err(\"E_API_PROTOCOL\", \"Unexpected endpoint status\");\n}\n";
  }
  client["api.nex"]="module "+prefix+"::client_sdk;\nimport \"std/net.nex\" as net;\nimport \"std/web.nex\" as web;\n"+clientTypes.imports()+helpers;
  auto serverBundle=bundle(server,entry),clientBundle=clientProjection(std::move(client),"api.nex",output.string()+"/client");
  // Both generated projects are checked before any final output is created.
  auto checkedServer=loadBundle(serverBundle,output.string()+"/server"),checkedClient=loadBundle(clientBundle,output.string()+"/client");
  auto descriptor=describeAPI(p);auto docs=openAPI(p);
  fs::create_directories(output.parent_path());fs::path temporary;
  do{temporary=output;temporary+=".tmp."+std::to_string(std::random_device{}());}while(!fs::create_directory(temporary));
  try{
    exportProject(serverBundle,(temporary/"server").string(),languageVersion);exportProject(clientBundle,(temporary/"client").string(),languageVersion);
    writeFile((temporary/"server/nex.lock.json").string(),json(dependencyLock(checkedServer))+"\n");writeFile((temporary/"client/nex.lock.json").string(),json(dependencyLock(checkedClient))+"\n");
    writeFile((temporary/"api.json").string(),json(descriptor)+"\n");writeFile((temporary/"openapi.json").string(),json(docs)+"\n");
    writeFile((temporary/"README.md").string(),"# Generated NEX API\n\nServer: run `nex build --target server --profile release --json` in server/. Use runtime --auth/--database and optional --static/--cert/--key.\n\nClient: import client/api.nex and its extracted models from models/MODULE/PATH.nex. request_OPERATION returns a typed browser command; response_OPERATION validates the result. Use a unique request ID and ignore stale responses. Runtime credentials are not generated. The SDK contains model declarations and pure client helpers, without server implementations.\n\napi.json records the exact NEX wire contracts; openapi.json documents OpenAPI 3.1.1. Context is injected; fixed routes have no implicit query parameters. Successful bodies are tagged results; handler errors use 422 and roll back.\n\nRegenerate from reviewed NEX sources; do not edit generated files. Both projects contain pinned local dependency sources.\n");
    if(fs::exists(output)&&!fs::is_empty(output))throw Error("E_EXISTS","API destination changed during generation");
    fs::rename(temporary,output);
  }catch(...){fs::remove_all(temporary);throw;}
  return Object{{"schema","nex.api-generation/1"},{"ok",true},{"language",languageVersion},{"revision",revision(p)},{"directory",output.string()},{"server_entry",(output/"server"/entry).string()},{"client_entry",(output/"client/api.nex").string()},{"contract",(output/"api.json").string()},{"openapi",(output/"openapi.json").string()}};
}
}
