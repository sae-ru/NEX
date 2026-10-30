#include "nex/language.h"
#include <functional>
namespace nex {
std::string sourceErrorTypeKey(const Program &program,const Type &root){
  if(root.kind==Type::Constructor)throw Error("E_SOURCE_TYPE","an unapplied constructor is not a source error value type");
  llvm::json::Object context;std::set<std::string> seen;size_t nodes=0;
  auto qualified=[&](const std::string &name,const std::string &owner){return name.find("::")!=std::string::npos?name:(owner.empty()?program.module:owner)+"::"+name;};
  std::function<Type(Type,unsigned)> normalized;
  std::function<Structure(Structure)> declarationIdentity;
  normalized=[&](Type type,unsigned depth)->Type{
    if(depth>256)throw Error("E_SOURCE_TYPE","source error normalized type exceeds its depth budget");
    if(type.element)type.element=std::make_shared<Type>(normalized(*type.element,depth+1));
    for(auto &argument:type.arguments)argument=normalized(argument,depth+1);
    if(type.kind==Type::Constructor){auto found=program.structureTemplates.find(type.name);if(found!=program.structureTemplates.end())type.name=qualified(found->second.name,found->second.owner);}
    if(type.kind!=Type::Record)return type;
    const Structure *declaration=nullptr;
    if(program.hasStructure(type.name))declaration=&program.structure(type.name);
    else if(auto found=program.structureTemplates.find(type.name);found!=program.structureTemplates.end())declaration=&found->second;
    if(!declaration)return type; // The concrete traversal diagnoses this later.
    if(declaration->templateName.empty())type.name=qualified(declaration->name,declaration->owner);
    else{
      type.name=qualified(declaration->templateName,declaration->owner)+"<";
      for(size_t i=0;i<declaration->typeArguments.size();++i){if(i)type.name+=",";type.name+=typeName(normalized(declaration->typeArguments[i],depth+1));}
      type.name+=">";
    }
    return type;
  };
  declarationIdentity=[&](Structure value){
    auto record=normalized(Type::record(value.name),0);value.name=record.name;
    if(value.owner.empty())value.owner=program.module;
    if(!value.templateName.empty())value.templateName=qualified(value.templateName,value.owner);
    for(auto &argument:value.typeArguments)argument=normalized(argument,0);
    for(auto field:value.members())field->type=normalized(field->type,0);
    for(auto &bounds:value.typeBounds){std::set<std::string> result;for(const auto &bound:bounds){
      auto name=bound;for(const auto &trait:program.traits)if(trait.name==bound){name=qualified(trait.name,trait.owner);break;}result.insert(std::move(name));
    }bounds=std::move(result);}
    return value;
  };
  std::function<void(const Type&,unsigned)> visit;
  auto addTemplate=[&](const std::string &name,unsigned arity=0){
    auto found=program.structureTemplates.find(name);
    if(found==program.structureTemplates.end())throw Error("E_SOURCE_TYPE","source error type constructor is not a checked declaration: "+name);
    if(arity&&found->second.typeParameters.size()!=arity)throw Error("E_SOURCE_TYPE","source error constructor arity differs from its checked declaration");
    auto value=declarationIdentity(found->second);context["template:"+value.name]=canonical(value);
  };
  visit=[&](const Type &type,unsigned depth){
    if(depth>256||++nodes>100000)throw Error("E_SOURCE_TYPE","source error type context exceeds its depth/node budget");
    if(type.kind==Type::Unknown||type.kind==Type::Parameter||type.kind==Type::Projection)
      throw Error("E_SOURCE_TYPE","source error type must be fully concrete before computing its identity");
    if(type.kind==Type::Constructor){
      if(type.name=="list"||type.name=="result"||type.name=="task"||type.name=="channel"){
        if(type.constructorArity!=1)throw Error("E_SOURCE_TYPE","invalid built-in source error type constructor");
      }else{if(!type.constructorArity)throw Error("E_SOURCE_TYPE","invalid source error constructor arity");addTemplate(type.name,type.constructorArity);}
      return;
    }
    if(type.element)visit(*type.element,depth+1);
    for(const auto &argument:type.arguments)visit(argument,depth+1);
    if(type.kind!=Type::Record)return;
    if(!program.hasStructure(type.name))throw Error("E_SOURCE_TYPE","source error type is not a checked declaration: "+type.name);
    if(!seen.insert(type.name).second)return;
    if(seen.size()>16384)throw Error("E_SOURCE_TYPE","source error type context exceeds its declaration budget");
    const auto &declaration=program.structure(type.name);
    if(!declaration.typeParameters.empty())throw Error("E_SOURCE_TYPE","source error nominal type is not specialized");
    auto identity=declarationIdentity(declaration);context["type:"+identity.name]=canonical(identity);
    for(const auto &argument:declaration.typeArguments)visit(argument,depth+1);
    if(!declaration.templateName.empty())addTemplate(declaration.templateName);
    for(auto field:declaration.members())visit(field->type,depth+1);
  };
  visit(root,0);
  return hash(json(llvm::json::Object{{"format","nex.source-error-type/1"},{"type",typeName(normalized(root,0))},
                                    {"nominal_context",std::move(context)}},false));
}
}
