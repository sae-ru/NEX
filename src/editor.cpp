#include "nex/editor.h"
#include <algorithm>
#include <filesystem>
#include <functional>

namespace nex {
namespace {
using Object=llvm::json::Object;using Array=llvm::json::Array;using JSON=llvm::json::Value;
Object interval(size_t begin,size_t end){return Object{{"begin",int64_t(begin)},{"end",int64_t(end)}};}
struct Index {
  const Program &p;Array symbols,expressions;std::map<std::string,std::vector<SourceToken>> tokens;
  struct Location {std::string file;size_t begin=0,end=0;};
  std::map<std::string,Location> declarations;
  size_t entries=0;
  void tick(){if(++entries>200000)throw Error("E_ANALYSIS_LIMIT","editor analysis exceeds 200000 entries");}
  JSON location(const Location &value){return Object{{"file",value.file},{"range",interval(value.begin,value.end)}};}
  Location selection(const Span &span,const std::string &name){
    const auto &list=tokens.at(span.file);
    auto first=std::lower_bound(list.begin(),list.end(),span.begin,[](const SourceToken &t,size_t begin){return t.span.begin<begin;});
    for(auto it=first;it!=list.end()&&it->span.end<=span.end;++it)
      if(it->identifier&&it->text==name)return {span.file,it->span.begin,it->span.end};
    throw Error("E_ANALYSIS_RANGE","source declaration has no exact name token",span);
  }
  void declaration(const std::string &name,const std::string &local,const std::string &kind,const Span &span,const std::string &detail){
    auto selected=selection(span,local);declarations[name]=selected;tick();
    symbols.push_back(Object{{"symbol",name},{"name",local},{"kind",kind},{"file",span.file},
      {"range",interval(span.begin,span.end)},{"selection",interval(selected.begin,selected.end)},{"detail",detail}});
  }
  const Function *sourceFunction(std::string name){
    auto found=std::find_if(p.functions.begin(),p.functions.end(),[&](const Function &f){return f.name==name;});
    if(found!=p.functions.end()){
      if(!found->templateName.empty())name=found->templateName;
      else if(found->closure)return nullptr;
    }
    auto generic=p.functionTemplates.find(name);if(generic!=p.functionTemplates.end())return &generic->second;
    return found==p.functions.end()?nullptr:&*found;
  }
  using Scope=std::map<std::string,Location>;
  void expression(E e,Scope scope){
    if(!e)return;
    if(e->type.kind!=Type::Unknown&&e->sourceRange.valid&&p.units.contains(e->span.file)&&e->sourceRange.end<=p.units.at(e->span.file).source.size()){
      JSON target=nullptr;
      if(e->kind==Expr::Name){
        auto local=e->localName.empty()?e->text:e->localName;
        if(scope.contains(local))target=location(scope.at(local));
      }
      if(target.kind()==JSON::Null&&(e->kind==Expr::Call||e->kind==Expr::FunctionRef||e->kind==Expr::Name)){
        if(auto function=sourceFunction(e->text);function&&declarations.contains(function->name))target=location(declarations.at(function->name));
        else {
          auto name=e->text;
          auto structure=std::find_if(p.structures.begin(),p.structures.end(),[&](const Structure &s){return s.name==name;});
          if(structure!=p.structures.end()&&!structure->templateName.empty())name=structure->templateName;
          const Structure *owner=nullptr;
          if(p.variant(e->text,&owner))name=owner->templateName.empty()?owner->name:owner->templateName;
          if(declarations.contains(name))target=location(declarations.at(name));
          else if(auto split=name.rfind("::");split!=std::string::npos&&declarations.contains(name.substr(0,split)))target=location(declarations.at(name.substr(0,split)));
        }
      }
      tick();expressions.push_back(Object{{"file",e->span.file},{"range",interval(e->sourceRange.begin,e->sourceRange.end)},
        {"type",typeName(e->type)},{"definition",std::move(target)}});
    }
    if(e->lambda){
      auto child=scope;for(const auto &parameter:e->lambda->params)child[parameter.name]={parameter.span.file,parameter.span.begin,parameter.span.end};
      block(e->lambda->body,std::move(child));
    }
    for(size_t i=0;i<e->args.size();++i){
      auto child=scope;
      for(const auto &arm:e->arms)if((arm->guard&&i==arm->guard)||i==arm->value)
        for(const auto &binding:arm->bindings)child[binding.name]={binding.span.file,binding.span.begin,binding.span.end};
      expression(e->args[i],std::move(child));
    }
  }
  void block(const std::vector<S> &body,Scope scope){
    for(const auto &s:body){
      expression(s->expr,scope);
      if(s->kind==Stmt::Let||s->kind==Stmt::Var){
        auto span=s->span;span.end=s->sourceRange.end;
        auto name=selection(span,s->name);scope[s->name]=name;
      }
      block(s->body,scope);block(s->alternative,scope);
      for(const auto &arm:s->arms){auto child=scope;
        for(const auto &binding:arm->bindings)child[binding.name]={binding.span.file,binding.span.begin,binding.span.end};
        block(arm->body,std::move(child));}
    }
  }
  std::string signature(const Function &f){
    std::string text=f.realm+" fn "+f.localName+"(";
    for(size_t i=0;i<f.params.size();++i){if(i)text+=", ";text+=f.params[i].name+": "+typeName(f.params[i].type);}
    text+=") -> "+typeName(f.result);
    if(!f.effects.empty()){text+=" !{";bool first=true;for(const auto &effect:f.effects){if(!first)text+=", ";text+=effect;first=false;}text+="}";}
    return text;
  }
  void function(const Function &f){
    Scope scope;for(const auto &param:f.params)scope[param.name]={param.span.file,param.span.begin,param.span.end};
    block(f.body,std::move(scope));
  }
  JSON run(){
    Array files;size_t bytes=0;
    for(const auto &[key,unit]:p.units){
      bytes+=unit.source.size();if(bytes>16*1048576)throw Error("E_ANALYSIS_LIMIT","editor source bundle exceeds 16 MiB");
      tokens[key]=sourceTokens(unit.source,key);
      files.push_back(Object{{"key",key},{"path",unit.path},{"hash",hash(unit.source)},{"text",unit.source}});
    }
    auto addFunction=[&](const Function &f){if(!f.closure&&!f.traitSignature&&f.templateName.empty())declaration(f.name,f.localName,"function",f.span,signature(f));};
    for(const auto &f:p.functions)addFunction(f);
    for(const auto &[_,f]:p.functionTemplates)addFunction(f);
    auto addStructure=[&](const Structure &s){if(s.templateName.empty())declaration(s.name,s.localName,s.enumeration?"enum":"struct",s.span,(s.enumeration?"enum ":"struct ")+s.localName);};
    for(const auto &s:p.structures)addStructure(s);
    for(const auto &[_,s]:p.structureTemplates)addStructure(s);
    for(const auto &value:p.traits)declaration(value.name,value.localName,"trait",value.span,"trait "+value.localName);
    for(const auto &value:p.implementations)declaration(value.name,value.localName,"impl",value.span,"impl "+value.localName+": "+value.trait);
    for(const auto &value:p.endpoints)declaration(value.name,value.localName,"endpoint",value.span,"endpoint "+value.method+" "+value.path);
    for(const auto &f:p.functions)if(!f.closure&&!f.traitSignature&&f.templateName.empty())function(f);
    for(const auto &[_,f]:p.functionTemplates)function(f);
    return Object{{"schema","nex.analysis/1"},{"ok",true},{"language",languageVersion},{"revision",revision(p)},
      {"entry",p.entryUnit},{"files",std::move(files)},{"symbols",std::move(symbols)},{"expressions",std::move(expressions)},
      {"graph_written",false},{"source_written",false},{"executed",false}};
  }
};
}
llvm::json::Value editorAnalysis(const std::string &entry,const std::string &root,const llvm::json::Value &overlay){
  std::map<std::string,std::string> sources;
  if(overlay.kind()!=JSON::Null){
    auto object=overlay.getAsObject();
    if(!object||object->getString("schema")!="nex.overlay/1"||!object->getObject("files"))throw Error("E_OVERLAY","expected nex.overlay/1 with absolute source files");
    if(object->size()!=2)throw Error("E_OVERLAY","overlay accepts only schema and files");
    auto files=object->getObject("files");if(files->size()>128)throw Error("E_ANALYSIS_LIMIT","at most 128 source overlays are supported");
    for(const auto &[path,value]:*files){
      auto text=value.getAsString();auto file=std::filesystem::path(path.str());
      if(!text||text->size()>1048576||!file.is_absolute()||file.extension()!=".nex"||file.string().find('\0')!=std::string::npos||std::filesystem::weakly_canonical(file)!=file)
        throw Error("E_OVERLAY","overlays require canonical absolute .nex paths and UTF-8 source of at most 1 MiB each");
      sources[path.str()]=text->str();
    }
  }
  validateProjectMetadata(root);
  auto program=loadProgram(entry,root,true,sources);
  return Index{program,{},{},{},{},0}.run();
}
}
