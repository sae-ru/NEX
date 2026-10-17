#include "nex/language.h"
#include <functional>

namespace nex {
namespace {
constexpr size_t maxInstances=4096;
E cloneExpression(E source,const std::map<std::string,Type> &arguments){
  if(!source)return nullptr;auto value=std::make_shared<Expr>(*source);value->type=Type::Unknown;
  value->annotation=substituteType(source->annotation,arguments);value->args.clear();
  for(auto child:source->args)value->args.push_back(cloneExpression(child,arguments));
  for(auto &type:value->typeArguments)type=substituteType(type,arguments);return value;
}
std::vector<S> cloneBlock(const std::vector<S> &source,const std::map<std::string,Type> &arguments){
  std::vector<S> result;for(auto original:source){auto statement=std::make_shared<Stmt>(*original);
    statement->type=substituteType(original->type,arguments);statement->expr=cloneExpression(original->expr,arguments);
    statement->body=cloneBlock(original->body,arguments);statement->alternative=cloneBlock(original->alternative,arguments);statement->arms.clear();
    for(auto old:original->arms){auto arm=std::make_shared<MatchArm>(*old);arm->body=cloneBlock(old->body,arguments);for(auto &binding:arm->bindings)binding.type=Type::Unknown;statement->arms.push_back(std::move(arm));}
    result.push_back(std::move(statement));}return result;
}
std::map<std::string,Type> bindTypeArguments(const std::vector<std::string> &parameters,const std::vector<Type> &arguments,Span span){
  if(parameters.size()!=arguments.size())throw Error("E_GENERIC_ARITY","incorrect number of generic type arguments",span);
  std::map<std::string,Type> bound;for(size_t i=0;i<parameters.size();++i){if(arguments[i]==Type::Unit||arguments[i]==Type::Unknown)throw Error("E_TYPE","generic arguments must be non-unit types",span);bound[parameters[i]]=arguments[i];}return bound;
}
}
bool containsParameter(const Type &type){
  if(type.kind==Type::Parameter||(type.kind==Type::Record&&type.name.find('$')!=std::string::npos))return true;if(type.element&&containsParameter(*type.element))return true;
  for(const auto &argument:type.arguments)if(containsParameter(argument))return true;return false;
}
std::string genericName(const std::string &name,const std::vector<Type> &arguments){
  auto result=name+"<";for(size_t i=0;i<arguments.size();++i){if(i)result+=",";result+=typeName(arguments[i]);if(result.size()+1>4096)throw Error("E_GENERIC_LIMIT","specialized type/function name exceeds limit");}return result+">";
}
Type substituteType(Type type,const std::map<std::string,Type> &arguments){
  if(type.kind==Type::Parameter){auto found=arguments.find(type.name);if(found!=arguments.end())return found->second;return type;}
  if(type.element)type.element=std::make_shared<Type>(substituteType(*type.element,arguments));
  for(auto &argument:type.arguments)argument=substituteType(argument,arguments);return type;
}
void prepareGenerics(Program &p){
  // Bound instance counts keep references stable while checking recursive calls.
  size_t functionInstances=0,structureInstances=0;for(const auto &f:p.functions)functionInstances+=!f.templateName.empty();for(const auto &s:p.structures)structureInstances+=!s.templateName.empty();
  if(functionInstances>maxInstances||structureInstances>maxInstances)throw Error("E_GENERIC_LIMIT","generic instance limit exceeded");
  p.functions.reserve(p.functions.size()+maxInstances-functionInstances);p.structures.reserve(p.structures.size()+maxInstances-structureInstances);
  for(const auto &f:p.functions)if(!f.typeParameters.empty()&&!p.functionTemplates.contains(f.name)){auto source=f;source.body=cloneBlock(f.body,{});p.functionTemplates.emplace(f.name,std::move(source));}
  for(const auto &s:p.structures)if(!s.typeParameters.empty()&&!p.structureTemplates.contains(s.name))p.structureTemplates.emplace(s.name,s);
}
Type resolveType(Program &p,Type type,Span span,unsigned depth){
  if(depth>64)throw Error("E_GENERIC_LIMIT","generic type expansion exceeds depth limit",span);
  if(type.element){type.element=std::make_shared<Type>(resolveType(p,*type.element,span,depth+1));if(*type.element==Type::Unit)throw Error("E_TYPE","aggregate payload cannot have type unit",span);}
  for(auto &argument:type.arguments)argument=resolveType(p,argument,span,depth+1);
  if(type.kind!=Type::Record)return type;
  auto found=p.structureTemplates.find(type.name);
  if(found==p.structureTemplates.end()){
    if(!type.arguments.empty())throw Error("E_GENERIC_ARITY","type is not generic: "+type.name,span);
    if(!p.hasStructure(type.name))throw Error("E_TYPE","unknown type '"+type.name+"'",span);return type;
  }
  const auto &source=found->second;auto arguments=bindTypeArguments(source.typeParameters,type.arguments,span);auto name=genericName(source.name,type.arguments);
  if(p.hasStructure(name))return Type::record(name);
  size_t instances=0;for(const auto &s:p.structures)instances+=!s.templateName.empty();if(instances>=maxInstances)throw Error("E_GENERIC_LIMIT","generic nominal instance limit exceeded",span);
  auto instance=source;instance.name=name;instance.localName=genericName(source.localName.empty()?source.name:source.localName,type.arguments);instance.templateName=source.name;instance.typeArguments=type.arguments;instance.typeParameters.clear();
  for(auto field:instance.members())field->type=substituteType(field->type,arguments);
  p.structures.push_back(std::move(instance));auto &stored=p.structures.back();
  for(auto field:stored.members())field->type=resolveType(p,field->type,field->span,depth+1);
  return Type::record(name);
}
Function &instantiateFunction(Program &p,const Function &source,const std::vector<Type> &types,Span span){
  auto original=p.functionTemplates.find(source.name);if(original==p.functionTemplates.end())throw Error("E_GENERIC_ARITY","function is not generic: "+source.name,span);
  const auto &raw=original->second;auto arguments=bindTypeArguments(raw.typeParameters,types,span);auto name=genericName(raw.name,types);
  for(auto &f:p.functions)if(f.name==name)return f;
  size_t instances=0;for(const auto &f:p.functions)instances+=!f.templateName.empty();if(instances>=maxInstances)throw Error("E_GENERIC_LIMIT","generic function instance limit exceeded",span);
  auto instance=raw;instance.name=name;instance.localName=genericName(raw.localName.empty()?raw.name:raw.localName,types);instance.templateName=raw.name;instance.typeArguments=types;instance.typeParameters.clear();instance.dependencies.clear();instance.checked=false;
  instance.result=resolveType(p,substituteType(raw.result,arguments),span);
  for(auto &parameter:instance.params)parameter.type=resolveType(p,substituteType(parameter.type,arguments),parameter.span);
  instance.body=cloneBlock(raw.body,arguments);p.functions.push_back(std::move(instance));return p.functions.back();
}
}
