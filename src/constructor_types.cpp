#include "nex/constructor_types.h"
#include <algorithm>
#include <functional>

namespace nex {
namespace {
constexpr unsigned maxDepth=64, maxArity=64;
struct Work {
  Span span;
  unsigned steps=0;
  void enter(unsigned depth) {
    if(depth>maxDepth||++steps>16384)
      throw Error("E_GENERIC_LIMIT","constructor type matching exceeds its depth/work budget",span);
  }
};
unsigned kind(const Type &t,const KindContext &c,Work &work,unsigned depth,bool unit=false) {
  work.enter(depth);
  auto fail=[&](const std::string &why)->unsigned {throw Error("E_GENERIC_KIND",why,work.span);};
  if(t.kind==Type::Unknown)return fail("unknown type cannot be used in a constructor contract");
  if(t.kind==Type::Unit)return unit?0:fail("unit is not a value-type argument");
  if(t.kind==Type::Constructor) {
    auto found=c.constructors.find(t.name);
    if(found==c.constructors.end()||!t.constructorArity||t.constructorArity>maxArity||
       found->second!=t.constructorArity||!t.arguments.empty()||t.element)
      return fail("invalid or unknown type constructor '"+t.name+"'");
    auto slots=c.constructorParameters.find(t.name);
    if(slots!=c.constructorParameters.end()&&std::any_of(slots->second.begin(),slots->second.end(),[](auto n){return n!=0;}))return maxArity+1;
    return t.constructorArity;
  }
  if(t.kind==Type::Parameter) {
    auto found=c.parameters.find(t.name);
    if(found==c.parameters.end())return fail("unbound type parameter '"+t.name+"'");
    if(found->second>maxArity)return fail("constructor parameter arity exceeds 64");
    if(t.arguments.empty())return found->second;
    if(t.arguments.size()!=found->second)return fail("incorrect constructor parameter arity for '"+t.name+"'");
    for(const auto &a:t.arguments)if(kind(a,c,work,depth+1)!=0)return fail("constructor applications require value-type arguments");
    return 0;
  }
  if(t.kind==Type::Record) {
    auto found=c.constructors.find(t.name);
    if(found==c.constructors.end()||found->second!=t.arguments.size())
      return fail("unknown nominal type or incorrect nominal arity for '"+t.name+"'");
    auto slots=c.constructorParameters.find(t.name);
    for(size_t i=0;i<t.arguments.size();++i){auto expected=slots==c.constructorParameters.end()?0:slots->second.at(i);if(kind(t.arguments[i],c,work,depth+1)!=expected)return fail("nominal argument has the wrong constructor kind");}
    return 0;
  }
  if(t.kind==Type::List||t.kind==Type::Result) {
    if(!t.element||!t.arguments.empty()||kind(*t.element,c,work,depth+1)!=0)
      return fail("aggregate payload must be a value type");
    return 0;
  }
  if(t.kind==Type::Function) {
    if(!t.element||kind(*t.element,c,work,depth+1,true)!=0)return fail("function result must be a value type or unit");
    for(const auto &a:t.arguments)if(kind(a,c,work,depth+1)!=0)return fail("function parameters must be value types");
    return 0;
  }
  if(t.kind==Type::Projection){
    if(t.name.empty()||t.arguments.size()!=1)return fail("malformed associated type projection");
    kind(t.arguments.front(),c,work,depth+1);return 0;
  }
  if(t.element||!t.arguments.empty())return fail("scalar type has unexpected type arguments");
  return 0;
}
Type apply(Type constructor,std::vector<Type> args,const KindContext &context,Work &work,unsigned depth) {
  work.enter(depth);
  auto constructorKind=kind(constructor,context,work,depth+1);
  if((constructor.kind==Type::Constructor?constructor.constructorArity:constructorKind)!=args.size()||args.empty())
    throw Error("E_GENERIC_KIND","incorrect number of type constructor arguments",work.span);
  auto slots=constructor.kind==Type::Constructor?context.constructorParameters.find(constructor.name):context.constructorParameters.end();
  for(size_t i=0;i<args.size();++i){auto expected=slots==context.constructorParameters.end()?0:slots->second.at(i);if(kind(args[i],context,work,depth+1)!=expected)throw Error("E_GENERIC_KIND","constructor argument has the wrong kind",work.span);}
  if(constructor.kind==Type::Parameter){constructor.arguments=std::move(args);return constructor;}
  if(constructor.kind!=Type::Constructor)
    throw Error("E_GENERIC_KIND","expected an unapplied type constructor",work.span);
  if(constructor.name=="list")return Type::list(std::move(args.front()));
  if(constructor.name=="result")return Type::result(std::move(args.front()));
  auto value=Type::record(constructor.name);value.arguments=std::move(args);return value;
}
Type substitute(const Type &source,const TypeSubstitution &bindings,const KindContext &context,
                Work &work,unsigned depth,std::set<std::string> &active) {
  work.enter(depth);Type value=source;
  value.arguments.clear();for(const auto &a:source.arguments)value.arguments.push_back(substitute(a,bindings,context,work,depth+1,active));
  if(source.element)value.element=std::make_shared<Type>(substitute(*source.element,bindings,context,work,depth+1,active));
  if(source.kind!=Type::Parameter)return value;
  auto found=bindings.find(source.name);if(found==bindings.end())return value;
  if(!active.insert(source.name).second)throw Error("E_GENERIC_OCCURS","recursive type substitution",work.span);
  auto target=substitute(found->second,bindings,context,work,depth+1,active);active.erase(source.name);
  auto expected=context.parameters.find(source.name);
  if(expected==context.parameters.end()||kind(target,context,work,depth+1)!=expected->second)
    throw Error("E_GENERIC_KIND","type substitution changes the kind of '"+source.name+"'",work.span);
  return value.arguments.empty()?target:apply(std::move(target),std::move(value.arguments),context,work,depth+1);
}
Type substitute(const Type &t,const TypeSubstitution &b,const KindContext &c,Work &w,unsigned depth=0) {
  std::set<std::string> active;return substitute(t,b,c,w,depth,active);
}
bool occurs(const std::string &name,const Type &type,Work &work,unsigned depth=0) {
  work.enter(depth);if(type.kind==Type::Parameter&&type.name==name)return true;
  if(type.element&&occurs(name,*type.element,work,depth+1))return true;
  for(const auto &a:type.arguments)if(occurs(name,a,work,depth+1))return true;return false;
}
struct Application {Type constructor;std::vector<Type> arguments;};
std::optional<Application> application(const Type &type) {
  if(type.kind==Type::List||type.kind==Type::Result)
    return Application{Type::constructor(type.kind==Type::List?"list":"result",1),{*type.element}};
  if(type.kind==Type::Record&&!type.arguments.empty())
    return Application{Type::constructor(type.name,type.arguments.size()),type.arguments};
  if(type.kind==Type::Parameter&&!type.arguments.empty()) {
    auto base=type;base.arguments.clear();return Application{base,type.arguments};
  }
  return std::nullopt;
}
struct Unifier {
  KindContext context;std::set<std::string> variables;TypeSubstitution bindings;Work work;
  bool bind(const Type &parameter,const Type &value,unsigned depth) {
    if(parameter==value)return true;
    if(kind(parameter,context,work,depth+1)!=kind(value,context,work,depth+1)||occurs(parameter.name,value,work))return false;
    bindings[parameter.name]=value;return true;
  }
  bool unify(Type left,Type right,unsigned depth=0) {
    work.enter(depth);left=substitute(left,bindings,context,work);right=substitute(right,bindings,context,work);
    if(left==right)return true;
    if(left.kind==Type::Parameter&&left.arguments.empty()&&variables.contains(left.name))return bind(left,right,depth);
    if(right.kind==Type::Parameter&&right.arguments.empty()&&variables.contains(right.name))return bind(right,left,depth);
    auto a=application(left),b=application(right);
    if(a||b){
      if(!a||!b||a->arguments.size()!=b->arguments.size()||!unify(a->constructor,b->constructor,depth+1))return false;
      for(size_t i=0;i<a->arguments.size();++i)if(!unify(a->arguments[i],b->arguments[i],depth+1))return false;
      return true;
    }
    if(left.kind==Type::Function&&right.kind==Type::Function&&left.realm==right.realm&&
       left.effects==right.effects&&left.arguments.size()==right.arguments.size()) {
      for(size_t i=0;i<left.arguments.size();++i)if(!unify(left.arguments[i],right.arguments[i],depth+1))return false;
      return unify(*left.element,*right.element,depth+1);
    }
    return false;
  }
};
Type rename(Type value,const std::string &prefix) {
  if(value.kind==Type::Parameter)value.name=prefix+value.name;
  if(value.element)value.element=std::make_shared<Type>(rename(*value.element,prefix));
  for(auto &a:value.arguments)a=rename(a,prefix);return value;
}
void mergeConstructors(KindContext &to,const KindContext &from,Span span) {
  for(const auto &[name,arity]:from.constructors) {
    auto [it,inserted]=to.constructors.emplace(name,arity);
    if(!inserted&&it->second!=arity)throw Error("E_GENERIC_KIND","inconsistent nominal constructor arity",span);
  }
  for(const auto &[name,slots]:from.constructorParameters){auto [it,inserted]=to.constructorParameters.emplace(name,slots);if(!inserted&&it->second!=slots)throw Error("E_GENERIC_KIND","inconsistent nominal parameter kinds",span);}
}
}
unsigned typeKind(const Type &t,const KindContext &c,Span span){Work w{span};return kind(t,c,w,0);}
Type applyTypeConstructor(const Type &t,std::vector<Type> a,const KindContext &c,Span span){Work w{span};return apply(t,std::move(a),c,w,0);}
Type substituteConstructorTypes(const Type &t,const TypeSubstitution &b,const KindContext &c,Span span){Work w{span};kind(t,c,w,0);auto result=substitute(t,b,c,w);kind(result,c,w,0);return result;}
std::optional<TypeSubstitution> matchImplementationType(const Type &pattern,const Type &actual,const KindContext &c,Span span) {
  Work validation{span};auto patternKind=kind(pattern,c,validation,0);
  auto concrete=c;concrete.parameters.clear();if(kind(actual,concrete,validation,0)!=patternKind)return std::nullopt;
  Unifier matcher{c,{}, {},Work{span}};for(const auto &[name,arity]:c.parameters)matcher.variables.insert(name);
  if(!matcher.unify(pattern,actual))return std::nullopt;
  TypeSubstitution result;for(const auto &[name,value]:matcher.bindings)result[name]=substitute(value,matcher.bindings,c,matcher.work);
  return result;
}
bool implementationTypesOverlap(const Type &left,const KindContext &a,const Type &right,const KindContext &b,Span span) {
  Work validation{span};auto leftKind=kind(left,a,validation,0),rightKind=kind(right,b,validation,0);
  if(leftKind!=rightKind)return false;
  KindContext context;mergeConstructors(context,a,span);mergeConstructors(context,b,span);
  for(const auto &[name,arity]:a.parameters)context.parameters["$left::"+name]=arity;
  for(const auto &[name,arity]:b.parameters)context.parameters["$right::"+name]=arity;
  Unifier matcher{context,{}, {},Work{span}};for(const auto &[name,arity]:context.parameters)matcher.variables.insert(name);
  return matcher.unify(rename(left,"$left::"),rename(right,"$right::"));
}
std::optional<TypeSubstitution> matchRigidImplementationType(const Type &pattern,const Type &actual,const KindContext &context,const std::set<std::string> &variables,Span span) {
  Work validation{span};if(kind(pattern,context,validation,0)!=kind(actual,context,validation,0))return std::nullopt;
  Unifier matcher{context,variables,{},Work{span}};if(!matcher.unify(pattern,actual))return std::nullopt;
  TypeSubstitution result;for(const auto &[name,value]:matcher.bindings)result[name]=substitute(value,matcher.bindings,context,matcher.work);return result;
}
}
