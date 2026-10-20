#include "nex/editor.h"
#include <algorithm>
#include <filesystem>
#include <functional>
#include <tuple>

namespace nex {
namespace {
using Object=llvm::json::Object;using Array=llvm::json::Array;using JSON=llvm::json::Value;
Object interval(size_t begin,size_t end){return Object{{"begin",int64_t(begin)},{"end",int64_t(end)}};}
struct Index {
  const Program &p;Array symbols,expressions;std::map<std::string,std::vector<SourceToken>> tokens;
  bool references=false;Array occurrences;
  std::set<std::tuple<std::string,size_t,size_t,std::string,size_t,size_t,std::string>> seen;
  Index(const Program &program,bool enabled):p(program),references(enabled){}
  struct Location {std::string file;size_t begin=0,end=0;};
  std::map<std::string,Location> declarations;
  size_t entries=0;
  void tick(){if(++entries>200000)throw Error("E_ANALYSIS_LIMIT","editor analysis exceeds 200000 entries");}
  JSON location(const Location &value){return Object{{"file",value.file},{"range",interval(value.begin,value.end)}};}
  void occurrence(const Location &at,const Location &target,const std::string &role){
    if(!references)return;
    if(!p.units.contains(at.file)||!p.units.contains(target.file)||at.end<=at.begin||target.end<=target.begin||
       at.end>p.units.at(at.file).source.size()||target.end>p.units.at(target.file).source.size())
      throw Error("E_ANALYSIS_RANGE","reference has no captured source interval");
    if(!seen.emplace(at.file,at.begin,at.end,target.file,target.begin,target.end,role).second)return;
    tick();occurrences.push_back(Object{{"file",at.file},{"range",interval(at.begin,at.end)},
      {"definition",location(target)},{"role",role}});
  }
  void binding(const Location &at){occurrence(at,at,"declaration");}
  std::optional<Location> referenceName(const Span &span,const SourceRange &range){
    if(!references||!range.valid||!tokens.contains(span.file))return {};
    const auto &list=tokens.at(span.file);
    auto it=std::lower_bound(list.begin(),list.end(),span.begin,[](const SourceToken &t,size_t begin){return t.span.begin<begin;});
    std::optional<Location> result;unsigned depth=0;bool identifier=true;
    for(;it!=list.end()&&it->span.end<=range.end;++it){
      if(depth){if(it->text=="<")++depth;else if(it->text==">")--depth;continue;}
      if(identifier){if(!it->identifier)break;result=Location{it->span.file,it->span.begin,it->span.end};identifier=false;}
      else if(it->text=="<")++depth;
      else if(it->text=="::")identifier=true;
      else break;
    }
    return result;
  }
  void reference(E e,const JSON &target,const std::string &role){
    if(!references)return;
    if(auto object=target.getAsObject())if(auto at=referenceName(e->span,e->sourceRange)){
      auto range=object->getObject("range");
      occurrence(*at,{object->getString("file")->str(),size_t(*range->getInteger("begin")),size_t(*range->getInteger("end"))},role);
    }
  }
  void pattern(P value){
    if(!references||!value)return;
    if(value->kind==Pattern::Constructor&&value->type.kind==Type::Record){
      const auto &owner=p.structure(value->type.name);auto name=owner.templateName.empty()?owner.name:owner.templateName;
      if(declarations.contains(name))if(auto at=referenceName(value->span,value->sourceRange))occurrence(*at,declarations.at(name),"pattern");
    }
    for(auto child:value->args)pattern(child);
  }
  Location selection(const Span &span,const std::string &name){
    const auto &list=tokens.at(span.file);
    auto first=std::lower_bound(list.begin(),list.end(),span.begin,[](const SourceToken &t,size_t begin){return t.span.begin<begin;});
    for(auto it=first;it!=list.end()&&it->span.end<=span.end;++it)
      if(it->identifier&&it->text==name)return {span.file,it->span.begin,it->span.end};
    throw Error("E_ANALYSIS_RANGE","source declaration has no exact name token",span);
  }
  void declaration(const std::string &name,const std::string &local,const std::string &kind,const Span &span,const std::string &detail){
    auto selected=selection(span,local);declarations[name]=selected;tick();
    binding(selected);
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
      reference(e,target,e->kind==Expr::Call?"call":"read");
      tick();expressions.push_back(Object{{"file",e->span.file},{"range",interval(e->sourceRange.begin,e->sourceRange.end)},
        {"type",typeName(e->type)},{"definition",std::move(target)}});
    }
    // The checker rewrites f(...) into Invoke with a synthetic callee Name.
    // Attribute its physical identifier to the containing source call, while
    // leaving implicit closure-capture arguments without invented occurrences.
    if(references&&e->kind==Expr::Invoke&&!e->args.empty()&&!e->args[0]->sourceRange.valid&&e->args[0]->kind==Expr::Name){
      const auto &callee=e->args[0];auto name=callee->localName.empty()?callee->text:callee->localName;
      if(scope.contains(name))reference(e,location(scope.at(name)),"call");
    }
    if(references&&e->kind==Expr::Field&&e->args[0]->type.kind==Type::Record){
      const auto &owner=p.structure(e->args[0]->type.name);auto span=e->span;span.begin=span.end;
      for(const auto &field:owner.fields)if(field.name==e->text)
        if(auto at=referenceName(span,e->sourceRange))occurrence(*at,{field.span.file,field.span.begin,field.span.end},"read");
    }
    for(const auto &arm:e->arms)pattern(arm->pattern);
    if(e->lambda){
      auto child=scope;for(const auto &parameter:e->lambda->params){auto at=Location{parameter.span.file,parameter.span.begin,parameter.span.end};child[parameter.name]=at;binding(at);}
      block(e->lambda->body,std::move(child));
    }
    for(size_t i=0;i<e->args.size();++i){
      auto child=scope;
      for(const auto &arm:e->arms)if((arm->guard&&i==arm->guard)||i==arm->value)
        for(const auto &parameter:arm->bindings)if(parameter.name!="_"){auto at=Location{parameter.span.file,parameter.span.begin,parameter.span.end};child[parameter.name]=at;binding(at);}
      expression(e->args[i],std::move(child));
    }
  }
  void block(const std::vector<S> &body,Scope scope){
    for(const auto &s:body){
      expression(s->expr,scope);
      if(references&&s->kind==Stmt::Assign&&scope.contains(s->name)){
        auto span=s->span;span.end=s->sourceRange.end;occurrence(selection(span,s->name),scope.at(s->name),"write");
      }
      if(s->kind==Stmt::Let||s->kind==Stmt::Var){
        auto span=s->span;span.end=s->sourceRange.end;
        auto name=selection(span,s->name);scope[s->name]=name;binding(name);
      }
      block(s->body,scope);block(s->alternative,scope);
      for(const auto &arm:s->arms){auto child=scope;
        pattern(arm->pattern);
        for(const auto &parameter:arm->bindings)if(parameter.name!="_"){auto at=Location{parameter.span.file,parameter.span.begin,parameter.span.end};child[parameter.name]=at;binding(at);}
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
    Scope scope;for(const auto &param:f.params){auto at=Location{param.span.file,param.span.begin,param.span.end};scope[param.name]=at;binding(at);}
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
    auto addStructure=[&](const Structure &s){if(s.templateName.empty()){
      declaration(s.name,s.localName,s.enumeration?"enum":"struct",s.span,(s.enumeration?"enum ":"struct ")+s.localName);
      for(const auto &field:s.fields)binding({field.span.file,field.span.begin,field.span.end});
    }};
    for(const auto &s:p.structures)addStructure(s);
    for(const auto &[_,s]:p.structureTemplates)addStructure(s);
    for(const auto &value:p.traits)declaration(value.name,value.localName,"trait",value.span,"trait "+value.localName);
    for(const auto &value:p.implementations)declaration(value.name,value.localName,"impl",value.span,"impl "+value.localName+": "+value.trait);
    for(const auto &value:p.endpoints)declaration(value.name,value.localName,"endpoint",value.span,"endpoint "+value.method+" "+value.path);
    for(const auto &f:p.functions)if(!f.closure&&!f.traitSignature&&f.templateName.empty())function(f);
    for(const auto &[_,f]:p.functionTemplates)function(f);
    Object result{{"schema",references?"nex.analysis/2":"nex.analysis/1"},{"ok",true},{"language",languageVersion},{"revision",revision(p)},
      {"entry",p.entryUnit},{"files",std::move(files)},{"symbols",std::move(symbols)},{"expressions",std::move(expressions)},
      {"graph_written",false},{"source_written",false},{"executed",false}};
    if(references)result.insert({"occurrences",std::move(occurrences)});
    return result;
  }
};
}
llvm::json::Value editorAnalysis(const std::string &entry,const std::string &root,const llvm::json::Value &overlay,bool references){
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
  return Index(program,references).run();
}
}
