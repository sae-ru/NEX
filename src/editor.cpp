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
  bool references=false,details=false;Array occurrences;
  std::set<std::tuple<std::string,size_t,size_t,std::string,size_t,size_t,std::string>> seen;
  Index(const Program &program,bool enabled,bool expanded):p(program),references(enabled||expanded),details(expanded){}
  struct Location {std::string file;size_t begin=0,end=0;};
  using Key=std::tuple<std::string,size_t,size_t>;
  struct Info {std::string kind,detail;};
  std::map<Key,Info> information,identifierOverrides;
  std::map<Key,Info> intrinsicIdentifiers;
  static Key key(const Location &at){return {at.file,at.begin,at.end};}
  static std::string shortName(const std::string &name){auto split=name.rfind("::");return split==std::string::npos?name:name.substr(split+2);}
  static std::string arity(unsigned count){std::string out;if(count){out="<";for(unsigned i=0;i<count;++i){if(i)out+=",";out+="_";}out+=">";}return out;}
  static Type displayType(Type type){
    if(type.kind==Type::Parameter){type.kind=Type::Record;type.name=shortName(type.name);}
    if(type.element)type.element=std::make_shared<Type>(displayType(*type.element));
    for(auto &argument:type.arguments)argument=displayType(std::move(argument));return type;
  }
  static std::string shown(const Type &type){return typeName(displayType(type));}
  static std::string boundsText(const std::set<std::string> &bounds){std::string out;for(const auto &bound:bounds){out+=out.empty()?": ":" + ";out+=bound;}return out;}
  template<class D> std::string generics(const D &value){
    std::string out;if(value.typeParameters.empty())return out;out="<";
    for(size_t i=0;i<value.typeParameters.size();++i){if(i)out+=", ";out+=shortName(value.typeParameters[i])+arity(i<value.typeArities.size()?value.typeArities[i]:0);if(i<value.typeBounds.size())out+=boundsText(value.typeBounds[i]);}return out+">";
  }
  std::string sourceSignature(const Function &f){
    std::string out=(f.exported&&!f.traitSignature?"pub ":"")+f.realm+" "+(f.foreign?"extern ":"")+(f.test?"test ":"")+"fn "+f.name+generics(f)+"(";
    for(size_t i=0;i<f.params.size();++i){if(i)out+=", ";out+=f.params[i].name+": "+shown(f.params[i].type);}out+=") -> "+shown(f.result);
    if(!f.effects.empty()){out+=" !{";bool first=true;for(const auto &effect:f.effects){if(!first)out+=", ";out+=effect;first=false;}out+="}";}return out;
  }
  void valueBinding(const Location &at,const std::string &kind,const std::string &name,const Type &type){
    if(details)information[key(at)]={kind,name+(type.kind==Type::Unknown?"":": "+shown(type))};binding(at);
  }
  void valueUse(const Location &at,const Location &target,const Type &type){
    if(!details||type.kind==Type::Unknown)return;auto found=information.find(key(target));if(found==information.end())return;
    if(found->second.kind=="parameter"||found->second.kind=="local"||found->second.kind=="pattern_binding"||found->second.kind=="field")
      identifierOverrides[key(at)]={found->second.kind,p.units.at(at.file).source.substr(at.begin,at.end-at.begin)+": "+shown(type)};
  }
  void identifierDetails(Object &result){
    if(!details)return;
    // Parameter origins come from the parser. Match them only inside their
    // actual source declaration, using the checker's bound parameter arrays.
    std::map<std::string,std::vector<const EditorName*>> parameters;
    for(const auto &name:p.editorNames)if(name.kind=="parameter_declaration")parameters[name.span.file].push_back(&name);
    for(auto &[file,list]:parameters)std::sort(list.begin(),list.end(),[](auto a,auto b){return a->span.begin<b->span.begin;});
    auto inRange=[&](const Span &span,auto visit){
      const auto &list=parameters[span.file];auto it=std::lower_bound(list.begin(),list.end(),span.begin,[](auto name,size_t at){return name->span.begin<at;});
      for(;it!=list.end()&&(*it)->span.end<=span.end;++it)visit(**it);
    };
    auto typeParameters=[&](const auto &decl){
      std::map<std::string,size_t> slots;for(size_t i=0;i<decl.typeParameters.size();++i)slots[shortName(decl.typeParameters[i])]=i;
      if(slots.empty())return;
      inRange(decl.span,[&](const EditorName &name){auto found=slots.find(name.name);if(found==slots.end())return;auto i=found->second;
        auto label="type parameter "+decl.typeParameters[i]+arity(i<decl.typeArities.size()?decl.typeArities[i]:0);
        if(i<decl.typeBounds.size())label+=boundsText(decl.typeBounds[i]);information[{name.span.file,name.span.begin,name.span.end}]={"type_parameter",label};});
    };
    auto functionInfo=[&](const Function &f){
      if(f.closure||!f.templateName.empty())return;typeParameters(f);
      auto &table=f.traitSignature?members:declarations;if(table.contains(f.name))information[key(table.at(f.name))]={f.traitSignature?"trait_method":"function",sourceSignature(f)};
      // Signature parameters also have real physical declaration tokens.
      for(const auto &param:f.params)valueBinding({param.span.file,param.span.begin,param.span.end},"parameter",param.name,param.type);
    };
    for(const auto &f:p.functions)if(!f.traitSignature)functionInfo(f);
    for(const auto &[_,f]:p.functionTemplates)if(!f.traitSignature)functionInfo(f);
    auto structureInfo=[&](const Structure &s){
      if(!s.templateName.empty())return;typeParameters(s);
      if(declarations.contains(s.name))information[key(declarations.at(s.name))]={s.opaqueResource?"resource":s.enumeration?"enum":"struct",std::string(s.exported?"pub ":"")+(s.opaqueResource?"server resource ":s.enumeration?"enum ":"struct ")+s.name+generics(s)};
      for(const auto &variant:s.variants){auto name=s.name+"::"+variant.name;std::string text="enum variant "+s.name+generics(s)+"::"+variant.name+"(";
        for(size_t i=0;i<variant.fields.size();++i){const auto &field=variant.fields[i];if(i)text+=", ";text+=field.name+": "+shown(field.type);valueBinding({field.span.file,field.span.begin,field.span.end},"field",field.name,field.type);}text+=")";
        if(variants.contains(name))information[key(variants.at(name))]={"variant",text};
      }
    };
    for(const auto &s:p.structures)structureInfo(s);for(const auto &[_,s]:p.structureTemplates)structureInfo(s);
    std::map<Key,Info> selfParameters;
    for(const auto &trait:p.traits){
      auto at=declarations.at(trait.name);information[key(at)]={"trait",std::string(trait.exported?"pub ":"")+"trait "+trait.name+"<Self"+arity(trait.selfArity)+">"};
      Info self{"type_parameter","type parameter "+trait.name+"::Self"+arity(trait.selfArity)+" (trait self)"};selfParameters[key(at)]=self;
      inRange(trait.span,[&](const EditorName &name){if(name.name=="Self")information[{name.span.file,name.span.begin,name.span.end}]=self;});
      for(const auto &[name,bounds]:trait.associated){auto target=trait.name+"::"+name;if(members.contains(target))information[key(members.at(target))]={"associated_type","associated type "+target+"<Self>"+boundsText(bounds)};}
      for(const auto &method:trait.methods)functionInfo(method);
    }
    for(const auto &impl:p.implementations){typeParameters(impl);auto at=declarations.at(impl.name);information[key(at)]={"impl",std::string(impl.exported?"pub ":"")+"impl "+impl.name+generics(impl)+": "+impl.trait+" for "+shown(impl.self)};}
    for(const auto &endpoint:p.endpoints){auto at=declarations.at(endpoint.name);information[key(at)]={"endpoint","endpoint "+endpoint.name+" "+endpoint.method+" "+endpoint.path+" = "+endpoint.target};}
    for(const auto &[file,unit]:p.units)for(const auto &dependency:unit.imports){auto at=aliases.at({file,dependency.alias});information[key(at)]={"import_alias","import "+dependency.alias+" = "+p.units.at(dependency.target).module+" ("+json(dependency.path,false)+")"};}
    for(const auto &name:p.editorNames){
      Location at{name.span.file,name.span.begin,name.span.end};
      if(name.kind=="parameter"&&name.localTarget){auto target=key({name.localTarget->file,name.localTarget->begin,name.localTarget->end});
        if(selfParameters.contains(target))identifierOverrides[key(at)]=selfParameters.at(target);
      }
      if(name.kind=="builtin_type"||name.kind=="builtin_bound"||(name.kind=="type"&&name.name=="result"&&name.target.empty())){
        auto constructor=name.name=="list"||name.name=="result";intrinsicIdentifiers[key(at)]={name.kind=="builtin_bound"?"builtin_bound":"builtin_type",name.kind=="builtin_bound"?"constraint "+name.name:constructor?"type constructor "+name.name+"<_>":"type "+name.name};
      }
    }
    std::map<Key,JSON> rows;size_t bytes=2; // Include array brackets and separators.
    auto add=[&](const Location &at,const Info &info,JSON target){
      if((info.detail.empty()&&info.kind!="syntax")||info.detail.size()>16384)throw Error("E_ANALYSIS_LIMIT","identifier detail is empty or exceeds 16 KiB");
      JSON row=Object{{"file",at.file},{"range",interval(at.begin,at.end)},{"kind",info.kind},{"detail",info.kind=="syntax"?JSON(nullptr):JSON(info.detail)},{"definition",std::move(target)}};
      auto found=rows.find(key(at));if(found!=rows.end()){if(found->second!=row)throw Error("E_ANALYSIS_CONTEXT","identifier has conflicting checked descriptions");return;}
      bytes+=json(row,false).size()+(rows.empty()?0:1);if(bytes>8*1048576)throw Error("E_ANALYSIS_LIMIT","identifier descriptions exceed 8 MiB");tick();rows.emplace(key(at),std::move(row));
    };
    for(const auto &row:occurrences){auto object=row.getAsObject();auto atRange=object->getObject("range");Location at{object->getString("file")->str(),size_t(*atRange->getInteger("begin")),size_t(*atRange->getInteger("end"))};auto target=object->getObject("definition");auto targetRange=target->getObject("range");Key targetKey{target->getString("file")->str(),size_t(*targetRange->getInteger("begin")),size_t(*targetRange->getInteger("end"))};
      auto override=identifierOverrides.find(key(at));auto info=information.find(targetKey);if(override!=identifierOverrides.end())add(at,override->second,*object->get("definition"));
      else if(info!=information.end())add(at,info->second,*object->get("definition"));
      else throw Error("E_ANALYSIS_RANGE","checked reference has no identifier description");
    }
    for(const auto &[at,info]:intrinsicIdentifiers)add({std::get<0>(at),std::get<1>(at),std::get<2>(at)},info,nullptr);
    // Every lexer word receives an exact classification. Unclassified syntax
    // deliberately has no description/definition, preventing a containing
    // expression from impersonating its keyword or builtin-type token.
    for(const auto &[file,list]:tokens)for(const auto &token:list)if(token.identifier){Location at{file,token.span.begin,token.span.end};if(!rows.contains(key(at)))add(at,{"syntax",""},nullptr);}
    Array identifiers;for(auto &[_,row]:rows)identifiers.push_back(std::move(row));result.insert({"identifiers",std::move(identifiers)});
  }
  std::map<std::string,Location> declarations,members,variants;
  std::map<std::pair<std::string,std::string>,Location> aliases;
  std::map<std::tuple<std::string,size_t,size_t>,Location> contractTargets;
  std::vector<Location> nameParts(const Span &span){
    std::vector<Location> result;const auto &list=tokens.at(span.file);
    auto it=std::lower_bound(list.begin(),list.end(),span.begin,[](const SourceToken &t,size_t begin){return t.span.begin<begin;});
    unsigned depth=0;
    for(;it!=list.end()&&it->span.end<=span.end;++it){
      if(it->text=="<"){++depth;continue;}
      if(it->text==">"){if(depth)--depth;continue;}
      if(!depth&&it->identifier)result.push_back({span.file,it->span.begin,it->span.end});
    }
    return result;
  }
  void sourceNames(){
    if(!references)return;
    for(const auto &name:p.editorNames){
      Location at{name.span.file,name.span.begin,name.span.end};
      if(name.kind=="alias"){aliases[{at.file,name.name}]=at;binding(at);}
      if(name.kind=="parameter_declaration")binding(at);
      if(name.kind=="member_declaration"){members[name.target]=at;binding(at);}
    }
    for(const auto &name:p.editorNames){
      if(name.kind=="alias"||name.kind=="parameter_declaration"||name.kind=="member_declaration")continue;
      auto parts=nameParts(name.span);if(parts.empty())continue;
      if(name.kind=="parameter"){
        if(!name.localTarget)throw Error("E_ANALYSIS_RANGE","type parameter has no lexical declaration",name.span);
        const auto &target=*name.localTarget;occurrence(parts.back(),{target.file,target.begin,target.end},"read");continue;
      }
      // Alias and nominal/trait qualifiers have independent physical identities.
      auto split=name.name.find("::");
      if(parts.size()>1&&split!=std::string::npos){
        auto alias=aliases.find({name.span.file,name.name.substr(0,split)});
        if(alias!=aliases.end())occurrence(parts.front(),alias->second,"read");
        auto parent=name.target.rfind("::");
        if(parent!=std::string::npos&&(members.contains(name.target)||variants.contains(name.target))){auto owner=name.target.substr(0,parent);
          if(declarations.contains(owner))occurrence(parts[parts.size()-2],declarations.at(owner),"read");
        }
      }
      std::optional<Location> target;
      if(declarations.contains(name.target))target=declarations.at(name.target);
      if(members.contains(name.target))target=members.at(name.target);
      if(!target)continue; // Builtin constructors have no physical declaration.
      if(name.kind=="value"||name.kind=="value_call"){
        if(members.contains(name.target)){contractTargets[{parts.back().file,parts.back().begin,parts.back().end}]=*target;occurrence(parts.back(),*target,name.kind=="value_call"?"call":"read");}
        // Ordinary calls/patterns are emitted from the checked expression tree.
        // A trait's selected implementation must not replace its source contract.
        continue;
      }
      occurrence(parts.back(),*target,"read");
    }
  }
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
      Location selected{object->getString("file")->str(),size_t(*range->getInteger("begin")),size_t(*range->getInteger("end"))};
      if(auto found=contractTargets.find({at->file,at->begin,at->end});found!=contractTargets.end())selected=found->second;
      else {const Structure *owner=nullptr;if(auto variant=p.variant(e->text,&owner)){
        auto name=(owner->templateName.empty()?owner->name:owner->templateName)+"::"+variant->name;
        if(variants.contains(name))selected=variants.at(name);
      }}
      occurrence(*at,selected,role);valueUse(*at,selected,e->kind==Expr::Invoke?e->args[0]->type:e->type);
    }
  }
  void pattern(P value){
    if(!references||!value)return;
    if(details&&value->kind==Pattern::Boolean)intrinsicIdentifiers[{value->span.file,value->span.begin,value->span.end}]={"literal",shown(value->type)};
    if(value->kind==Pattern::Constructor&&value->type.kind==Type::Record){
      const auto &owner=p.structure(value->type.name);auto name=owner.templateName.empty()?owner.name:owner.templateName;
      if(auto at=referenceName(value->span,value->sourceRange)){
        auto variant=name+"::"+p.units.at(at->file).source.substr(at->begin,at->end-at->begin);
        if(variants.contains(variant))occurrence(*at,variants.at(variant),"pattern");
        else if(declarations.contains(name))occurrence(*at,declarations.at(name),"pattern");
      }
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
  void declaration(const std::string &name,const std::string &local,const std::string &kind,const Span &span,const std::string &detail,const std::optional<Span> &origin={}){
    auto selected=origin?Location{origin->file,origin->begin,origin->end}:selection(span,local);
    if(origin&&(origin->file!=span.file||origin->begin<span.begin||origin->end>span.end||origin->end<origin->begin||p.units.at(span.file).source.substr(origin->begin,origin->end-origin->begin)!=local))throw Error("E_ANALYSIS_RANGE","declaration name origin differs from its physical token",span);
    declarations[name]=selected;tick();
    binding(selected);if(details)information[key(selected)]={kind,detail};
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
      if(details&&e->kind==Expr::Boolean)intrinsicIdentifiers[{e->span.file,e->span.begin,e->span.end}]={"literal",shown(e->type)};
      reference(e,target,e->kind==Expr::Call?"call":"read");
      if(details&&target.kind()==JSON::Null&&(e->kind==Expr::Call||e->kind==Expr::Name||e->kind==Expr::FunctionRef)&&builtinNames().contains(e->text))
        if(auto at=referenceName(e->span,e->sourceRange))intrinsicIdentifiers[key(*at)]={"builtin_function","builtin "+e->text+"; result "+shown(e->type)};
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
        if(auto at=referenceName(span,e->sourceRange)){Location target{field.span.file,field.span.begin,field.span.end};occurrence(*at,target,"read");valueUse(*at,target,e->type);}
    }
    for(const auto &arm:e->arms)pattern(arm->pattern);
    if(e->lambda){
      auto child=scope;for(const auto &parameter:e->lambda->params){auto at=Location{parameter.span.file,parameter.span.begin,parameter.span.end};child[parameter.name]=at;valueBinding(at,"parameter",parameter.name,parameter.type);}
      block(e->lambda->body,std::move(child));
    }
    for(size_t i=0;i<e->args.size();++i){
      auto child=scope;
      for(const auto &arm:e->arms)if((arm->guard&&i==arm->guard)||i==arm->value)
        for(const auto &parameter:arm->bindings)if(parameter.name!="_"){auto at=Location{parameter.span.file,parameter.span.begin,parameter.span.end};child[parameter.name]=at;valueBinding(at,"pattern_binding",parameter.name,parameter.type);}
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
        auto name=selection(span,s->name);scope[s->name]=name;valueBinding(name,"local",s->name,s->type);
      }
      block(s->body,scope);block(s->alternative,scope);
      for(const auto &arm:s->arms){auto child=scope;
        pattern(arm->pattern);
        for(const auto &parameter:arm->bindings)if(parameter.name!="_"){auto at=Location{parameter.span.file,parameter.span.begin,parameter.span.end};child[parameter.name]=at;valueBinding(at,"pattern_binding",parameter.name,parameter.type);}
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
    Scope scope;for(const auto &param:f.params){auto at=Location{param.span.file,param.span.begin,param.span.end};scope[param.name]=at;valueBinding(at,"parameter",param.name,param.type);}
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
    std::set<std::string> indexedStructures;
    auto addStructure=[&](const Structure &s){if(s.templateName.empty()&&indexedStructures.insert(s.name).second){
      declaration(s.name,s.localName,s.opaqueResource?"resource":s.enumeration?"enum":"struct",s.span,(s.opaqueResource?"server resource ":s.enumeration?"enum ":"struct ")+s.localName,s.nameOrigin);
      for(const auto &field:s.fields)valueBinding({field.span.file,field.span.begin,field.span.end},"field",field.name,field.type);
      if(references)for(const auto &variant:s.variants){auto at=Location{variant.span.file,variant.span.begin,variant.span.end};variants[s.name+"::"+variant.name]=at;binding(at);}
    }};
    for(const auto &s:p.structures)addStructure(s);
    for(const auto &[_,s]:p.structureTemplates)addStructure(s);
    for(const auto &value:p.traits)declaration(value.name,value.localName,"trait",value.span,"trait "+value.localName);
    for(const auto &value:p.implementations)declaration(value.name,value.localName,"impl",value.span,"impl "+value.localName+": "+value.trait);
    for(const auto &value:p.endpoints)declaration(value.name,value.localName,"endpoint",value.span,"endpoint "+value.method+" "+value.path);
    sourceNames();
    for(const auto &f:p.functions)if(!f.closure&&!f.traitSignature&&f.templateName.empty())function(f);
    for(const auto &[_,f]:p.functionTemplates)function(f);
    Object result{{"schema",details?"nex.analysis/3":references?"nex.analysis/2":"nex.analysis/1"},{"ok",true},{"language",programLanguage(p)},{"revision",revision(p)},
      {"entry",p.entryUnit},{"files",std::move(files)},{"symbols",std::move(symbols)},{"expressions",std::move(expressions)},
      {"graph_written",false},{"source_written",false},{"executed",false}};
    identifierDetails(result);
    if(references)result.insert({"occurrences",std::move(occurrences)});
    return result;
  }
};
}
llvm::json::Value editorAnalysis(const std::string &entry,const std::string &root,const llvm::json::Value &overlay,bool references,bool details){
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
  auto program=loadProgram(entry,root,true,sources,references||details,details);
  return Index(program,references,details).run();
}
}
