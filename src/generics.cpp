#include "nex/task_frontend.h"
#include "nex/language.h"
#include "nex/traits.h"
#include <functional>

namespace nex {
namespace {
constexpr size_t maxInstances=4096;
std::vector<S> cloneBlock(const std::vector<S> &,const std::map<std::string,Type> &);
P clonePattern(P source){auto value=std::make_shared<Pattern>(*source);value->type=Type::Unknown;value->args.clear();for(auto child:source->args)value->args.push_back(clonePattern(child));return value;}
E cloneExpression(E source,const std::map<std::string,Type> &arguments){
  if(!source)return nullptr;auto value=std::make_shared<Expr>(*source);value->type=Type::Unknown;
  value->annotation=substituteType(source->annotation,arguments);value->args.clear();
  for(auto child:source->args)value->args.push_back(cloneExpression(child,arguments));
  for(auto &type:value->typeArguments)type=substituteType(type,arguments);
  for(auto &type:value->methodArguments)type=substituteType(type,arguments);
  for(auto &type:value->traitArguments)type=substituteType(type,arguments);
  if(source->lambda){value->lambda=std::make_shared<Function>(*source->lambda);auto &fn=*value->lambda;fn.checked=false;fn.captures.clear();fn.closure=false;fn.closureOwner.clear();fn.name.clear();fn.result=substituteType(fn.result,arguments);for(auto &param:fn.params)param.type=substituteType(param.type,arguments);fn.body=cloneBlock(source->lambda->body,arguments);if(value->kind==Expr::Lambda){value->text.clear();value->args.clear();}}
  value->arms.clear();for(auto original:source->arms){auto arm=std::make_shared<MatchArm>(*original);arm->pattern=clonePattern(original->pattern);arm->bindings.clear();arm->body=cloneBlock(original->body,arguments);value->arms.push_back(std::move(arm));}return value;
}
std::vector<S> cloneBlock(const std::vector<S> &source,const std::map<std::string,Type> &arguments){
  std::vector<S> result;for(auto original:source){auto statement=std::make_shared<Stmt>(*original);
    statement->type=substituteType(original->type,arguments);statement->expr=cloneExpression(original->expr,arguments);
    statement->body=cloneBlock(original->body,arguments);statement->alternative=cloneBlock(original->alternative,arguments);statement->arms.clear();
    if(statement->kind==Stmt::Match)statement->arms=statement->expr->arms;
    result.push_back(std::move(statement));}return result;
}
std::map<std::string,Type> bindTypeArguments(const Program &program,const std::vector<std::string> &parameters,const TypeBounds &bounds,const std::vector<Type> &arguments,Span span){
  if(parameters.size()!=arguments.size())throw Error("E_GENERIC_ARITY","incorrect number of generic type arguments",span);
  std::map<std::string,Type> bound;for(size_t i=0;i<parameters.size();++i){if(arguments[i]==Type::Unit||arguments[i]==Type::Unknown)throw Error("E_TYPE","generic arguments must be non-unit types",span);
    if(argumentKind(program,arguments[i],span)!=program.parameterKinds.at(parameters[i]))throw Error("E_GENERIC_KIND","generic argument has the wrong constructor kind",span);
    if(i<bounds.size())for(const auto &constraint:bounds[i])if(!satisfiesConstraint(program,arguments[i],constraint))throw Error("E_GENERIC_BOUND",typeName(arguments[i])+" does not satisfy '"+constraint+"' for "+parameters[i],span);
    bound[parameters[i]]=arguments[i];}return bound;
}
}
E cloneSourceExpression(E source){return cloneExpression(source,{});}
bool containsFile(const Program &program,const Type &type){
  std::set<std::string> seen;
  std::function<bool(const Type&)> visit=[&](const Type &value){
    if(value==Type::File)return true;
    if(value.element&&visit(*value.element))return true;
    for(const auto &argument:value.arguments)if(visit(argument))return true;
    if(value.kind==Type::Record&&program.hasStructure(value.name)&&seen.insert(value.name).second){
      const auto &record=program.structure(value.name);
      for(const auto &argument:record.typeArguments)if(visit(argument))return true;
      for(auto field:record.members())if(visit(field->type))return true;
    }
    return false;
  };return visit(type);
}
bool isExternalResource(const Program &program,const Type &type){return type.kind==Type::Record&&program.hasStructure(type.name)&&program.structure(type.name).opaqueResource;}
bool containsExternalResource(const Program &program,const Type &type){
  std::set<std::string> seen;
  std::function<bool(const Type&)> visit=[&](const Type &value){
    if(isExternalResource(program,value))return true;
    if(value.element&&visit(*value.element))return true;
    for(const auto &argument:value.arguments)if(visit(argument))return true;
    if(value.kind==Type::Record&&program.hasStructure(value.name)&&seen.insert(value.name).second){const auto &record=program.structure(value.name);for(const auto &argument:record.typeArguments)if(visit(argument))return true;for(auto field:record.members())if(visit(field->type))return true;}
    return false;
  };return visit(type);
}
bool containsNonTaskResource(const Program &program,const Type &type){return containsFile(program,type)||containsExternalResource(program,type);}
std::pair<std::string,std::string> sourceResourceClass(const Program &program,const Structure &declaration){
  if(!declaration.opaqueResource)throw Error("E_RESOURCE_TYPE","resource class requires an opaque declaration",declaration.span);
  llvm::json::Object context;std::set<std::string> seen;size_t nodes=0;
  std::function<void(const Type&,unsigned)> visit;
  std::function<void(const Structure&,bool,unsigned)> nominal;
  nominal=[&](const Structure &value,bool generic,unsigned depth){
    auto key=(generic?"template:":"type:")+value.name;if(!seen.insert(key).second)return;
    if(seen.size()>16384)throw Error("E_RESOURCE_TYPE","resource type context exceeds its declaration budget",declaration.span);
    context[key]=canonical(value);
    for(const auto &argument:value.typeArguments)visit(argument,depth+1);
    for(auto field:value.members())visit(field->type,depth+1);
    if(!value.templateName.empty()){auto found=program.structureTemplates.find(value.templateName);if(found!=program.structureTemplates.end())nominal(found->second,true,depth+1);}
  };
  visit=[&](const Type &type,unsigned depth){
    if(depth>256||++nodes>100000)throw Error("E_RESOURCE_TYPE","resource type context exceeds its depth/node budget",declaration.span);
    if(type.element)visit(*type.element,depth+1);for(const auto &argument:type.arguments)visit(argument,depth+1);
    if(type.kind==Type::Record&&program.hasStructure(type.name))nominal(program.structure(type.name),false,depth+1);
    if(type.kind==Type::Constructor){auto found=program.structureTemplates.find(type.name);if(found!=program.structureTemplates.end())nominal(found->second,true,depth+1);}
  };
  for(const auto &argument:declaration.typeArguments)visit(argument,0);
  if(!declaration.templateName.empty()){auto found=program.structureTemplates.find(declaration.templateName);if(found!=program.structureTemplates.end())nominal(found->second,true,0);}
  // Names alone do not bind a phantom argument's layout or resource declaration.
  // Include its complete checked nominal context, including generic templates.
  auto identity=hash(json(llvm::json::Object{{"format","nex.resource-type/2"},{"module",declaration.owner.empty()?program.module:declaration.owner},{"definition",canonical(declaration)},{"type_context",std::move(context)}},false));
  // Specialization/source names can contain punctuation and reach4096 bytes.
  // The complete digest keeps the host class bounded without truncating names.
  return {"nex_resource::r"+identity,identity};
}
bool satisfiesConstraint(const Program &program,const Type &type,const std::string &constraint){
  if(!std::set<std::string>{"wire","add","ordered","number","integer"}.contains(constraint))return hasTraitWitness(program,type,constraint);
  if(type.kind==Type::Projection){auto sep=type.name.rfind("::");const auto &owner=traitDefinition(program,type.name.substr(0,sep));auto found=owner.associated.find(type.name.substr(sep+2));
    if(found!=owner.associated.end()){const auto &bounds=found->second;return bounds.contains(constraint)||((constraint=="add"||constraint=="ordered"||constraint=="wire")&&(bounds.contains("integer")||bounds.contains("number")))||(constraint=="number"&&bounds.contains("integer"))||(constraint=="wire"&&bounds.contains("ordered"));}return false;}
  if(constraint=="wire"){
    if(containsNonTaskResource(program,type)||containsTaskAuthority(program,type))return false;
    std::set<std::string> seen;std::function<bool(const Type&)> visit=[&](const Type &value){
      if(value==Type::I64||value==Type::F64||value==Type::Bool||value==Type::Str||value==Type::Bytes)return true;
      if(value.kind==Type::Projection)return satisfiesConstraint(program,value,"wire");
      if(value.kind==Type::Parameter){auto found=program.parameterBounds.find(value.name);return found!=program.parameterBounds.end()&&(found->second.contains("wire")||found->second.contains("integer")||found->second.contains("number")||found->second.contains("ordered"));}
      if(value.kind==Type::List||value.kind==Type::Result)return visit(*value.element);
      if(value.kind==Type::Record){if(!seen.insert(value.name).second)return true;const auto &record=program.structure(value.name);for(auto field:record.members())if(!visit(field->type))return false;return true;}
      return false;
    };return visit(type);
  }
  if(type.kind==Type::Parameter){auto found=program.parameterBounds.find(type.name);return found!=program.parameterBounds.end()&&(found->second.contains(constraint)||((constraint=="add"||constraint=="ordered")&&(found->second.contains("integer")||found->second.contains("number")))||(constraint=="number"&&found->second.contains("integer")));}
  if(constraint=="add")return type==Type::I64||type==Type::F64||type==Type::Str||type==Type::Bytes||type.kind==Type::List;
  if(constraint=="ordered"||constraint=="number")return type==Type::I64||type==Type::F64;
  if(constraint=="integer")return type==Type::I64;
  return false;
}
llvm::json::Value canonicalBounds(const std::vector<std::string> &parameters,const TypeBounds &bounds){
  llvm::json::Object result;for(size_t i=0;i<parameters.size();++i){llvm::json::Array values;if(i<bounds.size())for(const auto &bound:bounds[i])values.push_back(bound);result[parameters[i]]=std::move(values);}return result;
}
bool containsParameter(const Type &type){
  if(type.kind==Type::Parameter||(type.kind==Type::Record&&type.name.find('$')!=std::string::npos))return true;if(type.element&&containsParameter(*type.element))return true;
  for(const auto &argument:type.arguments)if(containsParameter(argument))return true;return false;
}
std::string genericName(const std::string &name,const std::vector<Type> &arguments){
  auto result=name+"<";for(size_t i=0;i<arguments.size();++i){if(i)result+=",";result+=typeName(arguments[i]);if(result.size()+1>4096)throw Error("E_GENERIC_LIMIT","specialized type/function name exceeds limit");}return result+">";
}
Type substituteType(Type type,const std::map<std::string,Type> &arguments){
  if(type.kind==Type::Parameter){
    for(auto &argument:type.arguments)argument=substituteType(argument,arguments);
    auto found=arguments.find(type.name);if(found==arguments.end())return type;
    if(type.arguments.empty())return found->second;
    auto constructor=found->second;
    if(constructor.kind==Type::Parameter&&constructor.arguments.empty()){constructor.arguments=type.arguments;return constructor;}
    if(constructor.kind!=Type::Constructor||constructor.constructorArity!=type.arguments.size())throw Error("E_GENERIC_KIND","cannot apply a substituted value type as a constructor");
    if(constructor.name=="list")return Type::list(type.arguments.at(0));if(constructor.name=="result")return Type::result(type.arguments.at(0));if(constructor.name=="task")return Type::task(type.arguments.at(0));if(constructor.name=="channel")return Type::channel(type.arguments.at(0));auto value=Type::record(constructor.name);value.arguments=std::move(type.arguments);return value;
  }
  if(type.element)type.element=std::make_shared<Type>(substituteType(*type.element,arguments));
  for(auto &argument:type.arguments)argument=substituteType(argument,arguments);return type;
}
void prepareGenerics(Program &p){
  auto registerBounds=[&](const auto &source){for(size_t i=0;i<source.typeParameters.size();++i) {p.parameterBounds[source.typeParameters[i]]=i<source.typeBounds.size()?source.typeBounds[i]:std::set<std::string>{};p.parameterKinds[source.typeParameters[i]]=i<source.typeArities.size()?source.typeArities[i]:0;}};
  for(const auto &source:p.structures)registerBounds(source);for(const auto &source:p.functions)registerBounds(source);for(const auto &source:p.implementations)registerBounds(source);
  // Bound instance counts keep references stable while checking recursive calls.
  size_t functionInstances=0,structureInstances=0;for(const auto &f:p.functions)functionInstances+=!f.templateName.empty();for(const auto &s:p.structures)structureInstances+=!s.templateName.empty();
  if(functionInstances>maxInstances||structureInstances>maxInstances)throw Error("E_GENERIC_LIMIT","generic instance limit exceeded");
  p.functions.reserve(p.functions.size()+2*maxInstances-functionInstances);p.structures.reserve(p.structures.size()+maxInstances-structureInstances);
  for(const auto &f:p.functions)if(!f.typeParameters.empty()&&!p.functionTemplates.contains(f.name)){auto source=f;source.body=cloneBlock(f.body,{});p.functionTemplates.emplace(f.name,std::move(source));}
  for(const auto &s:p.structures)if(!s.typeParameters.empty()&&!p.structureTemplates.contains(s.name))p.structureTemplates.emplace(s.name,s);
}
Type resolveType(Program &p,Type type,Span span,unsigned depth){
  if(depth>64)throw Error("E_GENERIC_LIMIT","generic type expansion exceeds depth limit",span);
  if(!p.taskPrototype&&(type.kind==Type::Task||type.kind==Type::Channel||type.kind==Type::TaskScope))throw Error("E_TASK_UNIMPLEMENTED","task types are not part of language0.18",span);
  if(type.kind==Type::Record){
    auto sep=type.name.rfind("::");
    if(sep!=std::string::npos)for(const auto &trait:p.traits)if(trait.name==type.name.substr(0,sep)&&trait.associated.contains(type.name.substr(sep+2)))type.kind=Type::Projection;
    if(type.kind==Type::Record&&type.arguments.empty()){
      if((type.name=="list"||type.name=="result")&&!p.hasStructure(type.name))return Type::constructor(type.name,1);
      auto found=p.structureTemplates.find(type.name);if(found!=p.structureTemplates.end())return Type::constructor(type.name,found->second.typeParameters.size());
    }
  }
  if(type.kind==Type::Projection)return resolveProjection(p,type,span,depth);
  if(type.kind==Type::Parameter){
    auto found=p.parameterKinds.find(type.name);if(found==p.parameterKinds.end())throw Error("E_GENERIC_SCOPE","unknown scoped type parameter",span);
    for(auto &argument:type.arguments){argument=resolveType(p,argument,span,depth+1);if(argument==Type::Unit)throw Error("E_TYPE","generic argument cannot be unit",span);if(argumentKind(p,argument,span)!=0)throw Error("E_GENERIC_KIND","constructor argument must be a value type",span);}
    if(!type.arguments.empty()&&type.arguments.size()!=found->second)throw Error("E_GENERIC_KIND","wrong constructor parameter arity",span);return type;
  }
  if(type.kind==Type::Constructor){argumentKind(p,type,span);return type;}
  if(type.element){type.element=std::make_shared<Type>(resolveType(p,*type.element,span,depth+1));if(*type.element==Type::Unit&&type.kind!=Type::Function&&type.kind!=Type::Task)throw Error("E_TYPE","aggregate payload cannot have type unit",span);}
  for(auto &argument:type.arguments)argument=resolveType(p,argument,span,depth+1);
  if(type.kind==Type::Function){
    if(type.arguments.size()>1024||typeName(type).size()>4096)throw Error("E_FUNCTION_LIMIT","callable signature exceeds its parameter/name budget",span);
    for(const auto &argument:type.arguments)if(argument==Type::Unit||argument==Type::Unknown)throw Error("E_TYPE","function parameters require non-unit types",span);
    for(const auto &effect:type.effects)if(effect!="io"&&effect!="db"&&effect!="fs"&&effect!="ffi"&&!(p.taskPrototype&&effect=="task")&&!(supportsSourceExceptions(p)&&effect=="throw"))throw Error("E_EFFECT","unsupported callable effect '"+effect+"'",span);
    if(type.effects.contains("db")&&type.realm!="server")throw Error("E_REALM","db callable effect requires server realm",span);
    if(type.effects.contains("ffi")&&type.realm!="server")throw Error("E_REALM","ffi callable effect requires server realm",span);
    if(type.effects.contains("fs")&&type.realm!="server")throw Error("E_REALM","fs callable effect requires server realm",span);
    return type;
  }
  if(type.kind!=Type::Record)return type;
  auto found=p.structureTemplates.find(type.name);
  if(found==p.structureTemplates.end()){
    if(!type.arguments.empty())throw Error("E_GENERIC_ARITY","type is not generic: "+type.name,span);
    if(!p.hasStructure(type.name))throw Error("E_TYPE","unknown type '"+type.name+"'",span);return type;
  }
  const auto &source=found->second;auto arguments=bindTypeArguments(p,source.typeParameters,source.typeBounds,type.arguments,span);auto name=genericName(source.name,type.arguments);
  if(p.hasStructure(name))return Type::record(name);
  size_t instances=0;for(const auto &s:p.structures)instances+=!s.templateName.empty();if(instances>=maxInstances)throw Error("E_GENERIC_LIMIT","generic nominal instance limit exceeded",span);
  auto instance=source;instance.name=name;instance.localName=genericName(source.localName.empty()?source.name:source.localName,type.arguments);instance.templateName=source.name;instance.typeArguments=type.arguments;instance.typeParameters.clear();instance.typeBounds.clear();instance.typeArities.clear();
  for(auto field:instance.members())field->type=substituteType(field->type,arguments);
  p.structures.push_back(std::move(instance));auto &stored=p.structures.back();
  for(auto field:stored.members())field->type=resolveType(p,field->type,field->span,depth+1);
  return Type::record(name);
}
Function &instantiateFunction(Program &p,const Function &source,const std::vector<Type> &types,Span span){
  auto original=p.functionTemplates.find(source.name);if(original==p.functionTemplates.end())throw Error("E_GENERIC_ARITY","function is not generic: "+source.name,span);
  const auto &raw=original->second;auto arguments=bindTypeArguments(p,raw.typeParameters,raw.typeBounds,types,span);
  if(raw.traitSignature&&!containsParameter(types.at(0)))return instantiateTraitMethod(p,raw,types,span);
  auto name=genericName(raw.name,types);
  for(auto &f:p.functions)if(f.name==name)return f;
  size_t instances=0;for(const auto &f:p.functions)instances+=!f.templateName.empty();if(instances>=maxInstances)throw Error("E_GENERIC_LIMIT","generic function instance limit exceeded",span);
  auto instance=raw;instance.name=name;instance.localName=genericName(raw.localName.empty()?raw.name:raw.localName,types);instance.templateName=raw.name;instance.typeArguments=types;instance.typeParameters.clear();instance.typeBounds.clear();instance.typeArities.clear();instance.dependencies.clear();instance.checked=false;
  instance.result=resolveType(p,substituteType(raw.result,arguments),span);
  for(auto &parameter:instance.params)parameter.type=resolveType(p,substituteType(parameter.type,arguments),parameter.span);
  instance.body=cloneBlock(raw.body,arguments);p.functions.push_back(std::move(instance));return p.functions.back();
}
}
