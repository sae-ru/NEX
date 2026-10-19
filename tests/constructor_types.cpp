#include "nex/constructor_types.h"
#include <functional>
#include <iostream>

namespace {
using namespace nex;
Type parameter(std::string name,std::vector<Type> args={}) {Type t(Type::Parameter);t.name=std::move(name);t.arguments=std::move(args);return t;}
Type nominal(std::string name,std::vector<Type> args={}) {auto t=Type::record(std::move(name));t.arguments=std::move(args);return t;}
void require(bool condition,const char *message){if(!condition)throw std::runtime_error(message);}
void rejects(const std::string &code,const std::function<void()> &body) {
  try{body();}catch(const Error &e){require(e.code==code,"unexpected diagnostic");return;}
  throw std::runtime_error("expected rejection");
}
}
int main()try {
  using namespace nex;unsigned cases=0;
  KindContext c;c.parameters={{"T",0},{"U",0},{"F",1}};c.constructors["Pair"]=2;c.constructors["Box"]=1;c.constructors["Tag"]=0;
  auto t=parameter("T"),u=parameter("U"),f=parameter("F");
  require(typeKind(f,c)==1&&typeKind(t,c)==0,"parameter kinds");
  require(applyTypeConstructor(Type::constructor("list",1),{Type::Str},c)==Type::list(Type::Str),"builtin application");
  require(applyTypeConstructor(Type::constructor("Box",1),{Type::I64},c)==nominal("Box",{Type::I64}),"nominal application");++cases;
  rejects("E_GENERIC_KIND",[&]{applyTypeConstructor(f,{Type::I64,Type::Str},c);});
  rejects("E_GENERIC_KIND",[&]{applyTypeConstructor(f,{Type::constructor("list",1)},c);});
  rejects("E_GENERIC_KIND",[&]{typeKind(parameter("missing"),c);});
  rejects("E_GENERIC_KIND",[&]{typeKind(Type::constructor("Box",2),c);});
  rejects("E_GENERIC_KIND",[&]{typeKind(Type::Unit,c);});
  rejects("E_GENERIC_KIND",[&]{typeKind(Type::list(Type::Unknown),c);});++cases;
  auto m=matchImplementationType(parameter("F",{t}),Type::list(Type::Str),c);
  require(m&&m->at("F")==Type::constructor("list",1)&&m->at("T")==Type::Str,"constructor inference");
  require(substituteConstructorTypes(parameter("F",{Type::result(t)}),*m,c)==Type::list(Type::result(Type::Str)),"higher-kinded substitution");++cases;
  auto pair=nominal("Pair",{t,t});
  require(matchImplementationType(pair,nominal("Pair",{Type::I64,Type::I64}),c).has_value(),"repeated agreement");
  require(!matchImplementationType(pair,nominal("Pair",{Type::I64,Type::Str}),c),"repeated disagreement");++cases;
  auto callback=Type::function({t},Type::result(u),"server",{"fs"});
  auto concrete=Type::function({Type::Str},Type::result(Type::Bytes),"server",{"fs"});
  auto cm=matchImplementationType(callback,concrete,c);
  require(cm&&cm->at("T")==Type::Str&&cm->at("U")==Type::Bytes,"function contract inference");
  concrete.effects.clear();require(!matchImplementationType(callback,concrete,c),"effects distinguish contracts");
  concrete.effects={"fs"};concrete.realm="shared";require(!matchImplementationType(callback,concrete,c),"realms distinguish contracts");++cases;
  KindContext a=c,b=c;a.parameters={{"T",0}};b.parameters={{"T",0}};
  require(implementationTypesOverlap(Type::list(parameter("T")),a,Type::list(Type::I64),b),"blanket/specific overlap");
  require(!implementationTypesOverlap(Type::list(parameter("T")),a,Type::result(parameter("T")),b),"different constructors disjoint");++cases;
  require(implementationTypesOverlap(nominal("Pair",{parameter("T"),Type::I64}),a,
                                     nominal("Pair",{Type::Str,parameter("T")}),b),"independent scopes may bind same-spelled T differently");++cases;
  require(!implementationTypesOverlap(nominal("Pair",{parameter("T"),parameter("T")}),a,
                                      nominal("Pair",{Type::I64,Type::Str}),b),"repeated parameter coherence");++cases;
  require(!implementationTypesOverlap(nominal("Pair",{parameter("T"),Type::list(parameter("T"))}),a,
                                      nominal("Pair",{Type::list(parameter("T")),parameter("T")}),b),"occurs check rejects infinite overlap");++cases;
  require(implementationTypesOverlap(parameter("F",{t}),c,nominal("Box",{Type::Bytes}),b),"higher-kinded overlap");
  require(!implementationTypesOverlap(parameter("F",{t}),c,nominal("Pair",{Type::I64,Type::Str}),b),"constructor arity distinguishes heads");++cases;
  rejects("E_GENERIC_OCCURS",[&]{substituteConstructorTypes(t,{{"T",Type::list(t)}},c);});
  rejects("E_GENERIC_KIND",[&]{substituteConstructorTypes(f,{{"F",Type::I64}},c);});
  rejects("E_GENERIC_KIND",[&]{matchImplementationType(t,u,c);});++cases;
  auto deep=Type(Type::I64);for(unsigned i=0;i<70;++i)deep=Type::list(deep);
  rejects("E_GENERIC_LIMIT",[&]{typeKind(deep,c);});++cases;
  KindContext bad=b;bad.constructors["Pair"]=1;
  rejects("E_GENERIC_KIND",[&]{implementationTypesOverlap(Type::I64,c,Type::I64,bad);});++cases;
  auto unitCallback=Type::function({Type::I64},Type::Unit);
  require(typeKind(unitCallback,c)==0,"unit is legal only as a function result");
  rejects("E_GENERIC_KIND",[&]{typeKind(Type::function({Type::Unit},Type::Unit),c);});++cases;
  require(typeName(parameter("F",{Type::I64}))=="$F<i64>","applied parameter identity retains arguments");
  require(Type::constructor("list",1)!=Type::constructor("list",2),"constructor arity is identity");++cases;
  auto constructorSelf=matchImplementationType(f,Type::constructor("list",1),c);
  require(constructorSelf&&constructorSelf->at("F")==Type::constructor("list",1),"constructor-valued Self head");
  require(implementationTypesOverlap(f,c,Type::constructor("Box",1),b),"constructor Self coherence");
  require(!matchImplementationType(f,Type::I64,c),"value and constructor Self kinds differ");++cases;
  auto repeatedConstructor=nominal("Pair",{parameter("F",{t}),parameter("F",{u})});
  require(!matchImplementationType(repeatedConstructor,nominal("Pair",{Type::list(Type::I64),Type::result(Type::Str)}),c),"one constructor parameter cannot select different constructors");
  auto rc=matchImplementationType(repeatedConstructor,nominal("Pair",{Type::list(Type::I64),Type::list(Type::Str)}),c);
  require(rc&&substituteConstructorTypes(repeatedConstructor,*rc,c)==nominal("Pair",{Type::list(Type::I64),Type::list(Type::Str)}),"repeated constructor substitution");++cases;
  auto aliases=c;aliases.parameters["G"]=1;
  require(substituteConstructorTypes(parameter("F",{u}),{{"F",parameter("G")},{"G",Type::constructor("Box",1)},{"U",Type::Bytes}},aliases)==nominal("Box",{Type::Bytes}),"constructor alias chains normalize");
  rejects("E_GENERIC_OCCURS",[&]{substituteConstructorTypes(f,{{"F",parameter("G")},{"G",f}},aliases);});++cases;
  std::vector<Type> patterns={t,Type::list(t),Type::result(t),pair,parameter("F",{t}),repeatedConstructor,callback};
  std::vector<Type> actuals={Type::I64,Type::list(Type::Str),Type::result(Type::Bytes),nominal("Pair",{Type::I64,Type::I64}),nominal("Box",{Type::Bool})};
  for(const auto &pattern:patterns)for(const auto &actual:actuals) {
    auto selected=matchImplementationType(pattern,actual,c);
    if(selected)require(substituteConstructorTypes(pattern,*selected,c)==actual,"a successful witness reconstructs the exact concrete head");
  }++cases;
  for(const auto &left:patterns)for(const auto &right:patterns)
    require(implementationTypesOverlap(left,c,right,c)==implementationTypesOverlap(right,c,left,c),"coherence is symmetric under independent alpha-renamed binders");++cases;
  std::cout<<"constructor kind/matching invariants passed: "<<cases<<"\n";return 0;
}catch(const std::exception &e){std::cerr<<e.what()<<"\n";return 1;}
