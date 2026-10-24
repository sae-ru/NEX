#include "nex/task_frontend.h"
#include "nex/task_lifetime.h"
#include "nex/language.h"
#include "nex/frontend_diagnostics.h"
#include "nex/traits.h"
#include "llvm/Support/Error.h"
#include <filesystem>
#include <functional>
#include <algorithm>
#include <cctype>

namespace nex {
namespace {
namespace fs=std::filesystem;
llvm::json::Value decoded(const std::string &text){auto v=llvm::json::parse(text);if(!v)throw Error("E_JSON",llvm::toString(v.takeError()));return std::move(*v);}
std::string required(const llvm::json::Object &o,const std::string &name){auto value=o.getString(name);if(!value)throw Error("E_BUNDLE","missing string '"+name+"'");return value->str();}
bool identifier(const std::string &s){
  if(s.empty()||!(std::isalpha(static_cast<unsigned char>(s[0]))||s[0]=='_'))return false;
  return std::all_of(s.begin(),s.end(),[](unsigned char c){return std::isalnum(c)||c=='_';});
}
void projectVersion(const llvm::json::Object &object,const std::string &file){
  Span span{1,1,0,0,file};
  if(auto value=object.get("schema");value&&value->getAsString()!="nex.project/1")
    throw Error("E_MANIFEST","unsupported project schema; expected nex.project/1",span);
  if(auto value=object.get("entry")){
    auto entry=value->getAsString();
    if(!entry||entry->empty()||entry->find('\0')!=llvm::StringRef::npos)
      throw Error("E_MANIFEST","project entry must be a nonempty path without NUL",span);
  }
  if(auto value=object.get("language")){
    auto language=value->getAsString();
    if(!language||language->empty()||language->size()>32||language->find('\0')!=llvm::StringRef::npos)
      throw Error("E_MANIFEST","project language must be a nonempty version of at most 32 UTF-8 bytes without NUL",span);
    if(*language!=languageVersion)
      throw Error("E_LANGUAGE_VERSION","project declares language "+language->str()+"; use its matching SDK to archive source, then nex migrate and export a current-language project",span);
  }
  if(auto value=object.get("libraries")){
    auto libraries=value->getAsObject();if(!libraries)throw Error("E_MANIFEST","libraries must map package names to local directories",span);
    for(const auto &[name,path]:*libraries){auto text=path.getAsString();if(!identifier(name.str())||!text||text->empty()||text->find('\0')!=llvm::StringRef::npos)throw Error("E_MANIFEST","invalid library name or directory",span);}
  }
}
void safeKey(const std::string &key){
  if(!llvm::json::isUTF8(key))throw Error("E_IMPORT_PATH","source paths must be valid UTF-8");
  if(key.empty()||key.front()=='/'||key.find_first_of("\\:")!=std::string::npos||key.find('\0')!=std::string::npos||!key.ends_with(".nex")||fs::path(key).lexically_normal().generic_string()!=key)
    throw Error("E_IMPORT_PATH","source paths must be normalized relative .nex paths");
  for(const auto &part:fs::path(key))if(part==".."||part==".")throw Error("E_IMPORT_PATH","source path escapes its module root");
  if(key.starts_with("@")){
    if(key.starts_with("@std/")&&key.size()>5)return;
    if(key.starts_with("@pkg/")){auto slash=key.find('/',5);if(slash!=std::string::npos&&identifier(key.substr(5,slash-5)))return;}
    throw Error("E_IMPORT_PATH","invalid package source key");
  }
}
std::string anchor(const std::string &key){
  if(key.starts_with("@std/"))return "@std/";
  if(key.starts_with("@pkg/"))return key.substr(0,key.find('/',5)+1);
  return "";
}
std::string importTarget(const std::string &from,const std::string &path,Span span){
  try{
    if(path.find_first_of("\\:")!=std::string::npos||path.find('\0')!=std::string::npos)throw Error("E_IMPORT_PATH","invalid import path");
    std::string target;
    if(path.starts_with("./")||path.starts_with("../")){
      target=(fs::path(from).parent_path()/path).lexically_normal().generic_string();auto base=anchor(from);
      if(!base.empty()&&!target.starts_with(base))throw Error("E_IMPORT_PATH","relative import escapes its package root");
    }else if(path.starts_with("std/"))target="@std/"+path.substr(4);
    else{
      auto slash=path.find('/');if(slash==std::string::npos||!identifier(path.substr(0,slash)))throw Error("E_IMPORT_PATH","use ./relative.nex, std/name.nex, or a configured package/name.nex");
      target="@pkg/"+path;
    }
    safeKey(target);return target;
  }catch(Error &e){e.span=span;throw;}
}
bool inside(const fs::path &path,const fs::path &base){
  auto relative=path.lexically_relative(base);if(relative.empty())return path==base;
  for(const auto &part:relative)if(part=="..")return false;return !relative.is_absolute();
}
struct Symbols{std::map<std::string,bool> functions,structures,variants,traits,projections;std::set<std::string> enumerations,traitMethods;};
template<class Units> std::string resolveSymbol(const Units &units,const std::map<std::string,Symbols> &symbols,const std::string &key,const std::string &name,bool type,Span span){
  if(!type&&builtinNames(units.at(key).taskPrototype,units.at(key).sourceLanguage==SourceLanguage::OwnedResources021).contains(name))return name;
  auto target=key,local=name;auto separator=name.find("::");bool external=separator!=std::string::npos;
  if(external&&(symbols.at(key).enumerations.contains(name.substr(0,separator))||symbols.at(key).traits.contains(name.substr(0,separator)))){external=false;}
  else if(external){auto alias=name.substr(0,separator);local=name.substr(separator+2);bool found=false;
    for(const auto &dependency:units.at(key).imports)if(dependency.alias==alias){target=dependency.target;found=true;break;}
    if(!found)throw Error("E_IMPORT_ALIAS","unknown import alias '"+alias+"'",span);
  }
  const auto &table=symbols.at(target);bool exported=false,found=false;
  if(table.structures.contains(local)){found=true;exported=table.structures.at(local);}
  if(type&&table.projections.contains(local)){found=true;exported=table.projections.at(local);}
  if(!type&&table.variants.contains(local)){found=true;exported=table.variants.at(local);}
  if(!type&&table.functions.contains(local)){found=true;exported=table.functions.at(local);}
  if(!found)throw Error(type?"E_TYPE":"E_NAME","unknown "+std::string(type?"type '":"function '")+name+"'",span);
  if(external&&!exported)throw Error("E_VISIBILITY","'"+name+"' is private to module "+units.at(target).module,span);
  return units.at(target).module+"::"+local;
}
template<class Units> std::string resolveTraitSymbol(const Units &units,const std::map<std::string,Symbols> &symbols,const std::string &key,const std::string &name,Span span){
  auto target=key,local=name;auto sep=name.find("::");bool external=sep!=std::string::npos;
  if(external){auto alias=name.substr(0,sep);local=name.substr(sep+2);bool found=false;for(const auto &dependency:units.at(key).imports)if(dependency.alias==alias){target=dependency.target;found=true;break;}if(!found)throw Error("E_IMPORT_ALIAS","unknown trait import alias",span);}
  const auto &table=symbols.at(target).traits;auto found=table.find(local);if(found==table.end())throw Error("E_GENERIC_BOUND","unknown trait '"+name+"'",span);
  if(external&&!found->second)throw Error("E_VISIBILITY","trait is private: "+name,span);
  return units.at(target).module+"::"+local;
}
template<class Units> void bindValueName(const Units &units,const std::map<std::string,Symbols> &symbols,const std::string &key,E expression){
  if(expression->kind!=Expr::Call&&expression->kind!=Expr::Name)return;
  const auto &name=expression->text;bool qualified=name.find("::")!=std::string::npos;
  if(!qualified)expression->localName=name;
  const auto &local=symbols.at(key);
  if(qualified||local.functions.contains(name)||(expression->kind==Expr::Call&&(builtinNames(units.at(key).taskPrototype,units.at(key).sourceLanguage==SourceLanguage::OwnedResources021).contains(name)||local.structures.contains(name)||local.variants.contains(name))))
    expression->text=resolveSymbol(units,symbols,key,name,false,expression->span);
}
class Loader {
  fs::path root;bool frozen,captureNames,captureDetails,taskPrototype;SourceLanguage sourceVersion;std::string entry;size_t capturedNames=0;
  std::map<std::string,std::string> overlays;
  std::map<std::string,std::string> texts;
  std::map<std::string,fs::path> packages;
  std::map<std::string,Program> parsed;
  std::map<std::string,std::string> owners;
  std::map<std::string,int> states;
  std::vector<std::string> stack;
  std::map<std::string,Symbols> symbols;
  std::set<std::string> checkedPackages;
  const std::set<std::string> &builtins;
  fs::path physical(const std::string &key){
    if(frozen)return root/(key.starts_with("@")?fs::path(".nex/snapshot")/key:fs::path(key));
    fs::path base=root;std::string relative=key;
    if(key.starts_with("@std/")){
      relative=key.substr(5);
      if(packages.contains("std"))base=packages.at("std");
      else return resourceFile("lib/"+relative);
    }else if(key.starts_with("@pkg/")){
      auto slash=key.find('/',5);auto name=key.substr(5,slash-5);relative=key.substr(slash+1);
      if(!packages.contains(name))throw Error("E_IMPORT_PACKAGE","package '"+name+"' is not configured in nex.json libraries");base=packages.at(name);
    }
    base=fs::weakly_canonical(base);
    if(key.starts_with("@")&&checkedPackages.insert(base.string()).second&&fs::is_regular_file(base/"nex.json")){
      auto file=(base/"nex.json").string();auto value=decoded(readFile(file));auto object=value.getAsObject();
      if(!object)throw Error("E_MANIFEST","library nex.json must be an object",Span{1,1,0,0,file});projectVersion(*object,file);
    }
    auto path=fs::weakly_canonical(base/relative);
    if(!inside(path,base))throw Error("E_IMPORT_PATH","import resolves outside its declared root");
    if(!fs::is_regular_file(path)&&!(overlays.contains(path.string())&&!fs::exists(path)))throw Error("E_IMPORT_FILE","source file not found: "+path.string());return path;
  }
  void visit(const std::string &key,Span importing={}){
    if(states[key]==2)return;
    if(states[key]==1){std::string chain;for(const auto &s:stack)chain+=s+" -> ";throw Error("E_IMPORT_CYCLE",chain+key,importing);}
    if(stack.size()>=128)throw Error("E_IMPORT_DEPTH","module import depth limit exceeded",importing);
    safeKey(key);if(importing.file.empty())importing.file=key;states[key]=1;stack.push_back(key);
    fs::path path;
    try{
      path=physical(key);
      if(!texts.contains(key)){if(frozen)throw Error("E_BUNDLE","snapshot is missing source "+key);texts[key]=overlays.contains(path.string())?overlays.at(path.string()):readFile(path.string());}
    }catch(Error &e){if((e.code!="E_LANGUAGE_VERSION"&&e.code!="E_MANIFEST")||e.span.file.empty())e.span=importing;throw;}
    catch(const fs::filesystem_error &e){throw Error("E_IMPORT_FILE",e.what(),importing);}
    Program unit;
    try{unit=taskPrototype&&sourceVersion==SourceLanguage::Language018
      ?parseTaskPrototype(texts.at(key),path.string(),captureNames,captureDetails)
      :parseVersioned(texts.at(key),path.string(),sourceVersion,captureNames,captureDetails);}catch(Error &e){e.span.file=key;throw;}
    capturedNames+=unit.editorNames.size();if(capturedNames>200000)throw Error("E_ANALYSIS_LIMIT","editor names exceed 200000 entries",Span{1,1,0,0,key});
    if(owners.contains(unit.module))throw Error("E_MODULE_DUPLICATE","module '"+unit.module+"' is declared by both "+owners.at(unit.module)+" and "+key,Span{1,1,0,0,key});
    owners[unit.module]=key;
    std::function<void(E)> expr;std::function<void(const std::vector<S>&)> block;
    expr=[&](E e){if(e){e->span.file=key;if(e->lambda){auto &fn=*e->lambda;fn.span.file=key;for(auto &param:fn.params)param.span.file=key;block(fn.body);}for(auto arm:e->arms){arm->span.file=key;visitPattern(arm->pattern,[&](P pattern){pattern->span.file=key;});}for(auto a:e->args)expr(a);}};
    block=[&](const auto &body){for(auto s:body){s->span.file=key;for(auto arm:s->arms){arm->span.file=key;for(auto &binding:arm->bindings)binding.span.file=key;}expr(s->expr);childBlocks(s,block);}};
    for(auto &f:unit.functions){f.span.file=key;f.owner=unit.module;f.localName=f.name;f.unit=key;for(auto &p:f.params)p.span.file=key;block(f.body);}
    for(auto &s:unit.structures){s.span.file=key;s.owner=unit.module;s.localName=s.name;s.unit=key;for(auto &f:s.fields)f.span.file=key;for(auto &v:s.variants){v.span.file=key;for(auto &f:v.fields)f.span.file=key;}}
    for(auto &value:unit.traits){value.span.file=key;value.owner=unit.module;value.localName=value.name;value.unit=key;for(auto &method:value.methods){method.span.file=key;method.owner=unit.module;method.unit=key;method.localName=value.localName+"::"+method.name;for(auto &parameter:method.params)parameter.span.file=key;}}
    for(auto &value:unit.implementations){value.span.file=key;value.owner=unit.module;value.localName=value.name;value.unit=key;for(auto &[name,method]:value.methods)method.span.file=key;}
    for(auto &endpoint:unit.endpoints){endpoint.span.file=key;endpoint.owner=unit.module;endpoint.localName=endpoint.name;endpoint.unit=key;}
    for(auto &name:unit.editorNames){name.span.file=key;if(name.localTarget)name.localTarget->file=key;}
    std::set<std::string> aliases;
    for(auto &dependency:unit.imports){dependency.span.file=key;if(!aliases.insert(dependency.alias).second)throw Error("E_IMPORT_ALIAS","duplicate import alias '"+dependency.alias+"'",dependency.span);dependency.target=importTarget(key,dependency.path,dependency.span);}
    parsed.emplace(key,std::move(unit));
    for(const auto &dependency:parsed.at(key).imports)visit(dependency.target,dependency.span);
    stack.pop_back();states[key]=2;
  }
  std::string resolve(const std::string &key,const std::string &name,bool type,Span span){
    return resolveSymbol(parsed,symbols,key,name,type,span);
  }
  void bind(){
    for(const auto &[key,unit]:parsed){
      auto &table=symbols[key];std::set<std::string> names;
      for(const auto &f:unit.functions){if(!names.insert(f.localName).second||builtins.contains(f.localName))throw Error("E_DUPLICATE","duplicate or reserved name '"+f.localName+"'",f.span);table.functions[f.localName]=f.exported;}
      for(const auto &value:unit.traits){
        if(!names.insert(value.localName).second||builtins.contains(value.localName))throw Error("E_DUPLICATE","duplicate or reserved trait name",value.span);
        table.traits[value.localName]=value.exported;
        for(const auto &[name,bounds]:value.associated)table.projections[value.localName+"::"+name]=value.exported;
        for(const auto &method:value.methods){auto symbol=value.localName+"::"+method.name;if(table.functions.contains(symbol))throw Error("E_DUPLICATE","duplicate trait method",method.span);table.functions[symbol]=value.exported;table.traitMethods.insert(symbol);}
        for(const auto &dependency:unit.imports)if(dependency.alias==value.localName)throw Error("E_IMPORT_ALIAS","trait name conflicts with import alias",value.span);
      }
      for(const auto &value:unit.implementations)if(!names.insert(value.localName).second||builtins.contains(value.localName))throw Error("E_DUPLICATE","duplicate or reserved implementation name",value.span);
      for(const auto &s:unit.structures){if(!names.insert(s.localName).second||builtins.contains(s.localName))throw Error("E_DUPLICATE","duplicate or reserved name '"+s.localName+"'",s.span);table.structures[s.localName]=s.exported;if(s.enumeration){table.enumerations.insert(s.localName);for(const auto &v:s.variants)table.variants[s.localName+"::"+v.name]=s.exported;for(const auto &dependency:unit.imports)if(dependency.alias==s.localName)throw Error("E_IMPORT_ALIAS","enum name conflicts with an import alias",s.span);}}
    }
    for(auto &[key,unit]:parsed){
      std::map<std::string,std::string> parameters;
      auto bounds=[&](TypeBounds &values,Span span){for(auto &items:values){std::set<std::string> bound;for(const auto &name:items)bound.insert(std::set<std::string>{"add","ordered","integer","number","wire"}.contains(name)?name:resolveTraitSymbol(parsed,symbols,key,name,span));items=std::move(bound);}};
      auto parameterScope=[&](auto &declaration){parameters.clear();for(auto &name:declaration.typeParameters){auto original=name;name=unit.module+"::"+declaration.localName+"::"+name;parameters[original]=name;}bounds(declaration.typeBounds,declaration.span);};
      std::function<void(Type&,Span)> type=[&](Type &t,Span span){
        if(t.kind==Type::Parameter){if(!parameters.contains(t.name))throw Error("E_GENERIC_SCOPE","type parameter is outside its declaration",span);t.name=parameters.at(t.name);}
        if(t.kind==Type::Record){
          if(t.name=="result"&&!symbols.at(key).structures.contains("result")&&t.arguments.empty()){t=Type::constructor("result",1);return;}
          t.name=resolve(key,t.name,true,span);
          bool projection=false;
          for(const auto &[source,decls]:symbols)for(const auto &[name,exported]:decls.projections)if(parsed.at(source).module+"::"+name==t.name)projection=true;
          if(projection)t.kind=Type::Projection;
          else if(t.arguments.empty())for(const auto &[source,unitValue]:parsed)for(const auto &nominal:unitValue.structures)if(unitValue.module+"::"+nominal.localName==t.name&&!nominal.typeParameters.empty())t=Type::constructor(t.name,nominal.typeParameters.size());
        }
        if(t.element){t.element=std::make_shared<Type>(*t.element);type(*t.element,span);}
        for(auto &argument:t.arguments)type(argument,span);
      };
      std::function<void(E)> expr;std::function<void(const std::vector<S>&)> block;
      expr=[&](E e){if(e){type(e->annotation,e->span);for(auto &argument:e->typeArguments)type(argument,e->span);for(auto &argument:e->methodArguments)type(argument,e->span);bindValueName(parsed,symbols,key,e);
        if(!e->methodArguments.empty()){bool method=false;for(const auto &[file,table]:symbols)for(const auto &name:table.traitMethods)if(parsed.at(file).module+"::"+name==e->text)method=true;if(!method)throw Error("E_GENERIC_ARITY","second type argument list requires a trait method",e->span);e->typeArguments.insert(e->typeArguments.end(),e->methodArguments.begin(),e->methodArguments.end());e->methodArguments.clear();}if(e->lambda){auto &fn=*e->lambda;type(fn.result,fn.span);for(auto &param:fn.params)type(param.type,param.span);block(fn.body);}for(auto arm:e->arms)visitPattern(arm->pattern,[&](P pattern){if(pattern->kind==Pattern::Constructor)pattern->text=resolve(key,pattern->text,false,pattern->span);});for(auto a:e->args)expr(a);}};
      block=[&](const auto &body){for(auto s:body){type(s->type,s->span);expr(s->expr);childBlocks(s,block);}};
      for(auto &value:unit.traits){
        value.name=unit.module+"::"+value.localName;
        for(auto &[name,items]:value.associated){TypeBounds temp{items};bounds(temp,value.span);items=temp.front();}
        for(auto &method:value.methods){auto local=method.name;method.name=value.name+"::"+local;parameterScope(method);parameters["Self"]=value.name+"::Self";type(method.result,method.span);for(auto &parameter:method.params)type(parameter.type,parameter.span);method.traitOwner=value.name;method.traitSignature=true;method.exported=value.exported;}
      }
      for(auto &value:unit.implementations){value.name=unit.module+"::"+value.localName;parameterScope(value);value.trait=resolveTraitSymbol(parsed,symbols,key,value.trait,value.span);type(value.self,value.span);for(auto &[name,alias]:value.associated)type(alias,value.span);for(auto &[name,method]:value.methods){method.target=resolve(key,method.target,false,method.span);for(auto &argument:method.typeArguments)type(argument,method.span);}}
      for(auto &f:unit.functions){f.name=unit.module+"::"+f.localName;parameterScope(f);type(f.result,f.span);for(auto &p:f.params)type(p.type,p.span);block(f.body);}
      for(auto &s:unit.structures){s.name=unit.module+"::"+s.localName;parameterScope(s);for(auto field:s.members())type(field->type,field->span);}
      for(auto &endpoint:unit.endpoints){endpoint.name=unit.module+"::"+endpoint.localName;endpoint.target=resolve(key,endpoint.target,false,endpoint.span);}
      // Resolve source projections with the exact same visibility/alias tables.
      for(auto &name:unit.editorNames){
        if(name.kind=="type"){
          if(name.name=="result"&&!symbols.at(key).structures.contains("result"))continue;
          name.target=resolve(key,name.name,true,name.span);
        }else if(name.kind=="trait")name.target=resolveTraitSymbol(parsed,symbols,key,name.name,name.span);
        else if(name.kind=="function"||name.kind=="value"||name.kind=="value_call")name.target=resolve(key,name.name,false,name.span);
        else if(name.kind=="member_declaration")name.target=unit.module+"::"+name.name;
        else if(name.kind=="member_binding"){
          auto split=name.name.rfind("::");name.target=resolveTraitSymbol(parsed,symbols,key,name.name.substr(0,split),name.span)+name.name.substr(split);
        }
      }
    }
  }
public:
  Loader(fs::path root,std::string entry,bool frozen,std::map<std::string,std::string> sources={},std::map<std::string,std::string> overlays={},bool editorNames=false,bool editorDetails=false,bool tasks=false,SourceLanguage version=SourceLanguage::Language018)
      :root(fs::weakly_canonical(root)),frozen(frozen),captureNames(editorNames||editorDetails),captureDetails(editorDetails),taskPrototype(tasks),sourceVersion(version),entry(std::move(entry)),overlays(std::move(overlays)),texts(std::move(sources)),builtins(builtinNames(tasks,version==SourceLanguage::OwnedResources021)){
    if(!frozen&&fs::is_regular_file(this->root/"nex.json")){
      auto value=decoded(readFile((this->root/"nex.json").string()));auto obj=value.getAsObject();if(!obj)throw Error("E_MANIFEST","nex.json must be an object");
      projectVersion(*obj,"nex.json");
      if(auto item=obj->get("libraries")){
        for(const auto &[name,path]:*item->getAsObject())packages[name.str()]=fs::weakly_canonical(this->root/path.getAsString()->str());
      }
    }
  }
  Program run(bool validate=true){
    std::string phase="load";bool complete=false;
    try{
    safeKey(entry);if(entry.starts_with("@"))throw Error("E_BUNDLE","entry must be a project source path");visit(entry);
    if(frozen&&parsed.size()!=texts.size())throw Error("E_BUNDLE","snapshot contains unreachable source files");
    complete=true;phase="bind";bind();
    Program p;p.taskPrototype=taskPrototype;p.sourceLanguage=sourceVersion;p.module=parsed.at(entry).module;p.source=texts.at(entry);p.path=parsed.at(entry).path;p.entryUnit=entry;
    std::vector<std::string> order{entry};for(const auto &[key,unit]:parsed)if(key!=entry)order.push_back(key);
    for(const auto &key:order){auto &unit=parsed.at(key);if(p.editorNames.size()+unit.editorNames.size()>200000)throw Error("E_ANALYSIS_LIMIT","editor names exceed 200000 entries");for(auto &name:unit.editorNames)p.editorNames.push_back(std::move(name));p.units[key]={key,unit.module,unit.source,unit.path,unit.imports,taskPrototype,sourceVersion};for(auto &f:unit.functions)p.functions.push_back(std::move(f));for(auto &s:unit.structures)p.structures.push_back(std::move(s));for(auto &endpoint:unit.endpoints)p.endpoints.push_back(std::move(endpoint));for(auto &value:unit.traits)p.traits.push_back(std::move(value));for(auto &value:unit.implementations)p.implementations.push_back(std::move(value));}
    p.imports=p.units.at(entry).imports;if(validate){phase="check";check(p);}return p;
    }catch(Error &error){
      if(phase=="check")if(auto context=error.frontend.getAsObject();context&&context->getString("input_kind")=="project")throw;
      if(phase=="load")if(auto context=error.frontend.getAsObject())if(auto value=context->getString("phase"))phase=value->str();
      attachFrontendDiagnostic(error,texts,entry,"project",phase,complete);throw;
    }
  }
};
std::string materialized(const std::string &key,const std::string &prefix){
  if(key.starts_with("@std/"))return prefix+"/std/"+key.substr(5);
  if(key.starts_with("@pkg/"))return prefix+"/packages/"+key.substr(5);
  return key;
}
}
void validateProjectMetadata(const std::string &root){
  auto path=fs::path(root)/"nex.json";if(!fs::is_regular_file(path))return;
  auto value=decoded(readFile(path.string()));auto object=value.getAsObject();
  if(!object)throw Error("E_MANIFEST","nex.json must be an object",Span{1,1,0,0,"nex.json"});projectVersion(*object,"nex.json");
}
Program loadProgram(const std::string &entry,const std::string &root,bool enforceLock,const std::map<std::string,std::string> &overlays,bool editorNames,bool editorDetails){
  auto base=std::filesystem::weakly_canonical(root);auto path=std::filesystem::weakly_canonical(entry);
  if(!inside(path,base))throw Error("E_IMPORT_PATH","entry is outside the project root");
  auto p=Loader(base,path.lexically_relative(base).generic_string(),false,{},overlays,editorNames,editorDetails,true,SourceLanguage::TaskFiles020).run();
  auto lock=base/"nex.lock.json";
  if(enforceLock&&std::filesystem::is_regular_file(lock)){
    auto locked=decoded(readFile(lock.string()));auto object=locked.getAsObject();
    if(!object||object->getString("schema")!="nex.lock/1"||object->getString("language")!=languageVersion||!object->getObject("dependencies"))throw Error("E_LOCK","dependency lock format/version differs; review dependencies and run nex lock");
    auto current=dependencyLock(p);auto expected=object->getObject("dependencies");
    for(const auto &[key,value]:*current.getAsObject()->getObject("dependencies"))if(!expected->get(key)||*expected->get(key)!=value)throw Error("E_LOCK","loaded package sources differ from nex.lock.json; review dependencies and run nex lock");
  }
  return p;
}
static Program bundleProgram(const llvm::json::Value &bundle,const std::string &root,bool validate,bool tasks=true,SourceLanguage version=SourceLanguage::TaskFiles020){
  auto obj=bundle.getAsObject();if(!obj||required(*obj,"schema")!="nex.sources/1")throw Error("E_BUNDLE","expected nex.sources/1");
  auto files=obj->getObject("files");if(!files||files->empty())throw Error("E_BUNDLE","snapshot requires source files");
  std::map<std::string,std::string> sources;
  for(const auto &[key,value]:*files){safeKey(key.str());auto text=value.getAsString();if(!text)throw Error("E_BUNDLE","source file must contain text");sources[key.str()]=text->str();}
  return Loader(root,required(*obj,"entry"),true,std::move(sources),{},false,false,tasks,version).run(validate);
}
Program loadBundle(const llvm::json::Value &bundle,const std::string &root){return bundleProgram(bundle,root,true);}
Program loadVersionedBundle(const llvm::json::Value &bundle,const std::string &root,const std::string &language){
  if(language=="0.18")return bundleProgram(bundle,root,true,false,SourceLanguage::Language018);
  if(language=="0.19")return bundleProgram(bundle,root,true,true,SourceLanguage::Tasks019);
  if(language=="0.20")return bundleProgram(bundle,root,true,true,SourceLanguage::TaskFiles020);
  if(language=="0.21")return bundleProgram(bundle,root,true,true,SourceLanguage::OwnedResources021);
  throw Error("E_LANGUAGE_VERSION","versioned source recheck supports explicit languages0.18,0.19,0.20 and private0.21");
}
Program bindBundle(const llvm::json::Value &bundle,const std::string &root){return bundleProgram(bundle,root,false);}
void bindExpression(const Program &p,const std::string &function,E expression){
  const auto &f=p.function(function);std::map<std::string,Symbols> symbols;
  const Function *generic=&f;for(unsigned depth=0;generic->closure&&depth<64;++depth)generic=&p.function(generic->closureOwner);
  std::map<std::string,Type> parameters;if(!generic->templateName.empty()){const auto &source=p.functionTemplates.at(generic->templateName);for(size_t i=0;i<source.typeParameters.size();++i){const auto &name=source.typeParameters[i];parameters[name.substr(name.rfind("::")+2)]=generic->typeArguments[i];}}
  for(const auto &[key,_]:p.units)symbols[key];
  for(const auto &fn:p.functions)symbols[fn.unit].functions[fn.localName]=fn.exported;
  for(const auto &s:p.structures){auto &table=symbols[s.unit];table.structures[s.localName]=s.exported;if(s.enumeration){table.enumerations.insert(s.localName);for(const auto &v:s.variants)table.variants[s.localName+"::"+v.name]=s.exported;}}
  for(const auto &value:p.traits){auto &table=symbols[value.unit];table.traits[value.localName]=value.exported;for(const auto &[name,bounds]:value.associated)table.projections[value.localName+"::"+name]=value.exported;for(const auto &method:value.methods)table.traitMethods.insert(value.localName+"::"+method.name.substr(method.name.rfind("::")+2));}
  std::function<void(Type&,Span)> type=[&](Type &t,Span span){if(t.kind==Type::Record&&parameters.contains(t.name)){auto base=parameters.at(t.name);auto args=t.arguments;for(auto &a:args)type(a,span);t=args.empty()?base:applyTypeConstructor(base,std::move(args),programKinds(p),span);return;}if(t.kind==Type::Record)t.name=resolveSymbol(p.units,symbols,f.unit,t.name,true,span);if(t.element){t.element=std::make_shared<Type>(*t.element);type(*t.element,span);}for(auto &argument:t.arguments)type(argument,span);};
  std::function<void(E)> visit;std::function<void(const std::vector<S>&)> block;
  block=[&](const auto &body){for(auto statement:body){type(statement->type,statement->span);if(statement->expr)visit(statement->expr);childBlocks(statement,block);}};
  visit=[&](E e){type(e->annotation,e->span);for(auto &argument:e->typeArguments)type(argument,e->span);for(auto &argument:e->methodArguments)type(argument,e->span);bindValueName(p.units,symbols,f.unit,e);if(!e->methodArguments.empty()){const auto &method=p.function(e->text,e->span);if(!method.traitSignature)throw Error("E_GENERIC_ARITY","second argument list requires a trait method",e->span);e->typeArguments.insert(e->typeArguments.end(),e->methodArguments.begin(),e->methodArguments.end());e->methodArguments.clear();}if(e->lambda){type(e->lambda->result,e->span);for(auto &param:e->lambda->params)type(param.type,param.span);block(e->lambda->body);}for(auto arm:e->arms)visitPattern(arm->pattern,[&](P pattern){if(pattern->kind==Pattern::Constructor)pattern->text=resolveSymbol(p.units,symbols,f.unit,pattern->text,false,pattern->span);});for(auto a:e->args)visit(a);};visit(expression);
}
Program loadTaskPrototype(const std::string &entry,const std::string &root,const std::map<std::string,std::string> &overlays){
  auto base=fs::weakly_canonical(root),path=fs::weakly_canonical(entry);
  if(!inside(path,base))throw Error("E_IMPORT_PATH","entry is outside the project root");
  return Loader(base,path.lexically_relative(base).generic_string(),false,{},overlays,false,false,true).run();
}
llvm::json::Value sourceBundle(const Program &p){
  rejectUnarchivedTasks(p,"source archival");
  llvm::json::Object files;for(const auto &[key,unit]:p.units)files[key]=unit.source;
  return llvm::json::Object{{"schema","nex.sources/1"},{"entry",p.entryUnit},{"files",std::move(files)}};
}
llvm::json::Value dependencyLock(const Program &p){
  rejectUnarchivedTasks(p,"dependency locking");
  llvm::json::Object dependencies;
  for(const auto &[key,unit]:p.units)if(key.starts_with("@"))dependencies[key]=llvm::json::Object{{"module",unit.module},{"source_hash",hash(unit.source)}};
  return llvm::json::Object{{"schema","nex.lock/1"},{"language",programLanguage(p)},{"dependencies",std::move(dependencies)}};
}
void exportProject(const llvm::json::Value &bundle,const std::string &directory,const std::string &language){
  auto obj=bundle.getAsObject();if(!obj||required(*obj,"schema")!="nex.sources/1")throw Error("E_BUNDLE","expected nex.sources/1");
  auto files=obj->getObject("files");if(!files||files->empty())throw Error("E_BUNDLE","snapshot requires files");
  auto entry=required(*obj,"entry");safeKey(entry);if(entry.starts_with("@")||!files->get(entry))throw Error("E_BUNDLE","invalid entry source");
  fs::path output=fs::absolute(directory);if(fs::exists(output)&&(!fs::is_directory(output)||!fs::is_empty(output)))throw Error("E_EXISTS","project export requires a new or empty directory");
  llvm::json::Object libraries;
  std::string prefix="_nex_deps";
  for(unsigned suffix=1;;++suffix){bool collision=false;for(const auto &[key,value]:*files)if(!key.str().starts_with("@")&&key.str().starts_with(prefix+"/"))collision=true;if(!collision)break;prefix="_nex_deps_"+std::to_string(suffix);}
  std::set<std::string> destinations;
  for(const auto &[key,value]:*files){safeKey(key.str());if(!value.getAsString())throw Error("E_BUNDLE","source must be text");
    if(!destinations.insert(materialized(key.str(),prefix)).second)throw Error("E_BUNDLE","source paths collide when materialized");
    if(key.str().starts_with("@std/"))libraries["std"]=prefix+"/std";
    if(key.str().starts_with("@pkg/")){auto slash=key.str().find('/',5);auto name=key.str().substr(5,slash-5);libraries[name]=prefix+"/packages/"+name;}
  }
  // All paths and source values have been checked before writing any file.
  fs::create_directories(output);
  for(const auto &[key,value]:*files)writeFile((output/materialized(key.str(),prefix)).string(),value.getAsString()->str());
  writeFile((output/"nex.json").string(),json(llvm::json::Object{{"schema","nex.project/1"},{"language",language},{"entry",entry},{"libraries",std::move(libraries)}})+"\n");
}
}
