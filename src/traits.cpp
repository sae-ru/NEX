#include "nex/traits.h"
#include <algorithm>
#include <functional>

namespace nex {
namespace {
Type parameter(const std::string &name){Type t(Type::Parameter);t.name=name;return t;}
bool builtin(const std::string &name){return std::set<std::string>{"add","ordered","integer","number","wire"}.contains(name);}
struct Selection {const Implementation *implementation=nullptr;TypeSubstitution arguments;};
struct ProofState {std::set<std::string> active;unsigned steps=0;};
thread_local ProofState *activeProof=nullptr;
struct ProofScope {
  ProofState local;ProofState *previous;
  ProofScope():previous(activeProof){if(!activeProof)activeProof=&local;}
  ~ProofScope(){activeProof=previous;}
};
KindContext implementationKinds(const Program &p,const Implementation &value){
  auto result=programKinds(p);result.parameters.clear();
  for(size_t i=0;i<value.typeParameters.size();++i)result.parameters[value.typeParameters[i]]=i<value.typeArities.size()?value.typeArities[i]:0;return result;
}
Type renameParameters(Type value,const std::string &prefix){
  if(value.kind==Type::Parameter)value.name=prefix+value.name;
  if(value.element)value.element=std::make_shared<Type>(renameParameters(*value.element,prefix));
  for(auto &a:value.arguments)a=renameParameters(a,prefix);return value;
}
std::optional<TypeSubstitution> match(const Program &p,const Implementation &value,const Type &actual){
  auto context=programKinds(p);std::string prefix="$impl-witness::"+value.name+"::";std::set<std::string> variables;
  for(size_t i=0;i<value.typeParameters.size();++i){auto name=prefix+value.typeParameters[i];context.parameters[name]=i<value.typeArities.size()?value.typeArities[i]:0;variables.insert(name);}
  auto found=matchRigidImplementationType(renameParameters(constructorPattern(p,value.self),prefix),constructorPattern(p,actual),context,variables,value.span);
  if(!found)return std::nullopt;TypeSubstitution result;
  for(const auto &name:value.typeParameters){auto it=found->find(prefix+name);if(it==found->end())throw Error("E_TRAIT_HEAD","implementation parameter is not determined by its head",value.span);result[name]=it->second;}return result;
}
Selection select(const Program &p,const Type &actual,const std::string &name,Span span){
  ProofScope scope;auto &state=*activeProof;auto key=name+"<"+typeName(actual)+">";
  if(state.active.size()>=64||++state.steps>4096)throw Error("E_TRAIT_LIMIT","trait obligations exceed their depth/work budget",span);
  if(!state.active.insert(key).second)throw Error("E_TRAIT_CYCLE","trait obligation has no finite witness",span);
  struct Guard{ProofState &s;std::string key;~Guard(){s.active.erase(key);}} guard{state,key};
  Selection selected;
  for(const auto &value:p.implementations)if(value.trait==name){auto arguments=match(p,value,actual);if(!arguments)continue;
    if(selected.implementation)throw Error("E_TRAIT_OVERLAP","multiple implementation heads match a request",span);
    selected={&value,std::move(*arguments)};
  }
  if(!selected.implementation)return {};
  const auto &value=*selected.implementation;
  for(size_t i=0;i<value.typeParameters.size();++i)if(i<value.typeBounds.size())for(const auto &bound:value.typeBounds[i])
    if(!satisfiesConstraint(p,selected.arguments.at(value.typeParameters[i]),bound))return {};
  return selected;
}
bool containsProjection(const Type &value){if(value.kind==Type::Projection)return true;if(value.element&&containsProjection(*value.element))return true;for(const auto &a:value.arguments)if(containsProjection(a))return true;return false;}
Type implementationType(Program &p,Type type,const Trait &trait,const Implementation &value,std::set<std::string> &active,unsigned depth=0){
  if(depth>64)throw Error("E_TRAIT_LIMIT","associated type normalization exceeds64 levels",value.span);
  if(type.kind==Type::Projection&&type.name.starts_with(trait.name+"::")&&type.arguments.size()==1&&constructorPattern(p,type.arguments.front())==constructorPattern(p,value.self)){
    auto name=type.name.substr(trait.name.size()+2);auto found=value.associated.find(name);
    if(found==value.associated.end())throw Error("E_TRAIT_ASSOCIATED","missing associated type '"+name+"'",value.span);
    if(!active.insert(name).second)throw Error("E_TRAIT_CYCLE","recursive associated type definition",value.span);
    auto result=implementationType(p,found->second,trait,value,active,depth+1);active.erase(name);return result;
  }
  if(type.element)type.element=std::make_shared<Type>(implementationType(p,*type.element,trait,value,active,depth+1));
  for(auto &a:type.arguments)a=implementationType(p,a,trait,value,active,depth+1);return type;
}
Type implementationType(Program &p,Type type,const Trait &trait,const Implementation &value){std::set<std::string> active;return resolveType(p,implementationType(p,std::move(type),trait,value,active),value.span);}
}
const Trait &traitDefinition(const Program &p,const std::string &name,Span span){for(const auto &value:p.traits)if(value.name==name)return value;throw Error("E_GENERIC_BOUND","unknown trait '"+name+"'",span);}
KindContext programKinds(const Program &p){
  KindContext result;result.parameters=p.parameterKinds;
  for(const auto &s:p.structures){result.constructors[s.name]=s.typeParameters.size();auto slots=s.typeArities;slots.resize(s.typeParameters.size());result.constructorParameters[s.name]=std::move(slots);}return result;
}
Type constructorPattern(const Program &p,Type value){
  if(value.kind==Type::Record&&p.hasStructure(value.name)){const auto &s=p.structure(value.name);if(!s.templateName.empty()){value.name=s.templateName;value.arguments=s.typeArguments;}}
  if(value.element)value.element=std::make_shared<Type>(constructorPattern(p,*value.element));
  for(auto &a:value.arguments)a=constructorPattern(p,a);return value;
}
unsigned argumentKind(const Program &p,const Type &type,Span span){return typeKind(constructorPattern(p,type),programKinds(p),span);}
void prepareTraits(Program &p){
  if(p.traitsPrepared)return;p.traitsPrepared=true;
  for(const auto &value:p.traits){
    if(value.methods.size()+value.associated.size()>1024)throw Error("E_TRAIT_LIMIT","trait member count exceeds1024",value.span);
    auto self=value.name+"::Self";p.parameterKinds[self]=value.selfArity;p.parameterBounds[self]={value.name};std::set<std::string> methods;
    for(const auto &[name,bounds]:value.associated)for(const auto &bound:bounds)if(!builtin(bound)&&traitDefinition(p,bound,value.span).selfArity!=0)throw Error("E_GENERIC_KIND","associated value type bound requires a value-kind trait",value.span);
    for(const auto &original:value.methods){
      if(!methods.insert(original.name).second)throw Error("E_DUPLICATE","duplicate trait method",original.span);
      auto method=original;method.traitOwner=value.name;method.traitSignature=true;
      if(method.name.find("::")==std::string::npos){method.name=value.name+"::"+method.name;for(auto &param:method.params)param.type=substituteType(param.type,{{"Self",parameter(self)}});method.result=substituteType(method.result,{{"Self",parameter(self)}});}
      method.typeParameters.insert(method.typeParameters.begin(),self);method.typeBounds.insert(method.typeBounds.begin(),{value.name});method.typeArities.insert(method.typeArities.begin(),value.selfArity);
      if(method.typeParameters.size()>64)throw Error("E_GENERIC_LIMIT","trait Self plus method parameters exceed64",method.span);
      p.functions.push_back(std::move(method));
    }
  }
}
bool hasTraitWitness(const Program &p,const Type &type,const std::string &name){
  const auto &trait=traitDefinition(p,name);
  if(argumentKind(p,type)!=trait.selfArity)return false;
  if(type.kind==Type::Parameter&&type.arguments.empty()){auto found=p.parameterBounds.find(type.name);if(found!=p.parameterBounds.end()&&found->second.contains(name))return true;}
  if(type.kind==Type::Projection){auto sep=type.name.rfind("::");const auto &owner=traitDefinition(p,type.name.substr(0,sep));auto found=owner.associated.find(type.name.substr(sep+2));if(found!=owner.associated.end()&&found->second.contains(name))return true;}
  return select(p,type,name,{}).implementation;
}
Type resolveProjection(Program &p,Type type,Span span,unsigned depth){
  if(depth>64)throw Error("E_TRAIT_LIMIT","associated projection depth exceeds64",span);
  auto sep=type.name.rfind("::");if(sep==std::string::npos||type.arguments.size()!=1)throw Error("E_TRAIT_ASSOCIATED","malformed associated projection",span);
  const auto &trait=traitDefinition(p,type.name.substr(0,sep),span);auto item=type.name.substr(sep+2);
  if(!trait.associated.contains(item)||argumentKind(p,type.arguments[0],span)!=trait.selfArity)throw Error("E_TRAIT_ASSOCIATED","unknown or kind-invalid associated type",span);
  auto selected=select(p,type.arguments[0],trait.name,span);
  if(selected.implementation){auto found=selected.implementation->associated.find(item);if(found==selected.implementation->associated.end())throw Error("E_TRAIT_ASSOCIATED","missing associated type",span);
    auto next=substituteType(found->second,selected.arguments);if(next==type)throw Error("E_TRAIT_CYCLE","associated projection does not normalize",span);return resolveType(p,next,span,depth+1);}
  if(containsParameter(type.arguments[0])&&hasTraitWitness(p,type.arguments[0],trait.name))return type;
  throw Error("E_GENERIC_BOUND","associated type requires a trait witness",span);
}
void checkImplementations(Program &p){
  if(p.implementations.size()>4096||p.traits.size()>4096)throw Error("E_TRAIT_LIMIT","trait/implementation count exceeds4096");
  for(const auto &[parameter,bounds]:p.parameterBounds)for(const auto &bound:bounds){
    if(builtin(bound)){if(p.parameterKinds.at(parameter)!=0)throw Error("E_GENERIC_KIND","builtin capability bounds require a value type");}
    else {const auto &trait=traitDefinition(p,bound);if(p.parameterKinds.at(parameter)!=trait.selfArity)throw Error("E_GENERIC_KIND","trait bound has the wrong Self kind");}}
  for(size_t index=0;index<p.implementations.size();++index){const auto &value=p.implementations[index];const auto &trait=traitDefinition(p,value.trait,value.span);
    if(containsProjection(value.self))throw Error("E_TRAIT_HEAD","implementation head cannot contain associated projections",value.span);
    auto context=implementationKinds(p,value);if(typeKind(constructorPattern(p,value.self),context,value.span)!=trait.selfArity)throw Error("E_GENERIC_KIND","implementation Self has the wrong kind",value.span);
    std::set<std::string> used;std::function<void(const Type&)> visit=[&](const auto &type){if(type.kind==Type::Parameter)used.insert(type.name);if(type.element)visit(*type.element);for(const auto &a:type.arguments)visit(a);};visit(value.self);
    for(const auto &name:value.typeParameters)if(!used.contains(name))throw Error("E_TRAIT_HEAD","implementation parameter is absent from its head",value.span);
    bool local=trait.owner==value.owner;
    if((value.self.kind==Type::Record||value.self.kind==Type::Constructor)&&p.hasStructure(value.self.name))local=local||p.structure(value.self.name).owner==value.owner;
    if(!local)throw Error("E_TRAIT_ORPHAN","implementation requires a local trait or outer nominal head",value.span);
    for(size_t previous=0;previous<index;++previous){const auto &other=p.implementations[previous];if(other.trait==value.trait&&implementationTypesOverlap(constructorPattern(p,other.self),implementationKinds(p,other),constructorPattern(p,value.self),context,value.span))throw Error("E_TRAIT_OVERLAP","implementation heads overlap",value.span);}
    if(value.associated.size()!=trait.associated.size()||value.methods.size()!=trait.methods.size())throw Error("E_TRAIT_CONFORMANCE","implementation must bind every associated type and method exactly once",value.span);
    for(const auto &[name,bounds]:trait.associated){auto found=value.associated.find(name);if(found==value.associated.end())throw Error("E_TRAIT_ASSOCIATED","missing associated type",value.span);auto type=implementationType(p,found->second,trait,value);
      if(type==Type::Unit||argumentKind(p,type,value.span)!=0)throw Error("E_GENERIC_KIND","associated type must be a non-unit value type",value.span);
      for(const auto &bound:bounds)if(!satisfiesConstraint(p,type,bound))throw Error("E_GENERIC_BOUND","associated type fails its declared bound",value.span);}
    for(const auto &method:trait.methods){auto localName=method.name.substr(method.name.rfind("::")+2);auto binding=value.methods.find(localName);if(binding==value.methods.end())throw Error("E_TRAIT_METHOD","missing method "+localName,value.span);
      const auto &target=p.function(binding->second.target,binding->second.span);if(target.traitSignature||target.test)throw Error("E_TRAIT_METHOD","method binding requires an ordinary non-test NEX function",binding->second.span);
      std::vector<Type> arguments=binding->second.typeArguments;for(const auto &name:method.typeParameters)arguments.push_back(parameter(name));
      if(arguments.size()!=target.typeParameters.size())throw Error("E_TRAIT_METHOD","method target arguments are explicit implementation arguments followed by trait method parameters",binding->second.span);
      const Function *actual=&target;if(!arguments.empty())actual=&instantiateFunction(p,target,arguments,binding->second.span);
      if(actual->params.size()!=method.params.size()||actual->realm!=method.realm||actual->effects!=method.effects)throw Error("E_TRAIT_METHOD","method arity/realm/effects differ from its trait contract",binding->second.span);
      auto expected=[&](const Type &type){return implementationType(p,substituteType(type,{{trait.name+"::Self",value.self}}),trait,value);};
      if(actual->result!=expected(method.result))throw Error("E_TRAIT_METHOD","method result differs from its trait contract",binding->second.span);
      for(size_t i=0;i<method.params.size();++i)if(actual->params[i].type!=expected(method.params[i].type))throw Error("E_TRAIT_METHOD","method parameter differs from its trait contract",binding->second.span);
    }
  }
}
Function &instantiateTraitMethod(Program &p,const Function &source,const std::vector<Type> &types,Span span){
  if(types.empty())throw Error("E_GENERIC_ARITY","trait method requires Self",span);
  auto selected=select(p,types.front(),source.traitOwner,span);
  if(!selected.implementation)throw Error("E_GENERIC_BOUND","no finite implementation witness for "+source.traitOwner,span);
  auto local=source.name.substr(source.name.rfind("::")+2);const auto &binding=selected.implementation->methods.at(local);
  auto arguments=binding.typeArguments;for(auto &type:arguments)type=resolveType(p,substituteType(type,selected.arguments),span);
  arguments.insert(arguments.end(),types.begin()+1,types.end());const auto &target=p.function(binding.target,span);
  if(!arguments.empty())return instantiateFunction(p,target,arguments,span);
  return const_cast<Function&>(target);
}
std::optional<TraitWitness> selectedTraitWitness(const Program &p,const Type &type,const std::string &trait,Span span){auto found=select(p,type,trait,span);if(!found.implementation)return std::nullopt;return TraitWitness{found.implementation,std::move(found.arguments)};}
std::string selectedImplementation(const Program &p,const Type &type,const std::string &trait,Span span){auto found=selectedTraitWitness(p,type,trait,span);return found?found->implementation->name:std::string{};}
}
