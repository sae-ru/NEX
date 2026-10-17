#include "nex/incremental.h"
#include <functional>

namespace nex {
namespace {
llvm::json::Array array(const std::set<std::string> &values){
  llvm::json::Array result;for(const auto &value:values)result.push_back(value);return result;
}
llvm::json::Value interface(const Function &f){
  llvm::json::Array parameters;for(const auto &p:f.params)parameters.push_back(typeName(p.type));
  return llvm::json::Object{{"name",f.name},{"parameters",std::move(parameters)},{"result",typeName(f.result)},
    {"effects",array(f.effects)},{"realm",f.realm},{"exported",f.exported},{"test",f.test}};
}
}
NativePlan planNative(const Program &p,const std::string &entry){
  std::set<std::string> reachable;
  std::function<void(const Function&)> visit=[&](const Function &f){if(reachable.insert(f.name).second)for(const auto &name:f.dependencies)visit(p.function(name));};
  visit(p.function(entry));
  std::map<std::string,std::set<std::string>> members,callers,unitDependencies,unitConsumers;
  for(const auto &name:reachable){
    const auto &f=p.function(name);members[f.unit].insert(name);
    for(const auto &callee:f.dependencies)callers[callee].insert(name);
  }
  NativePlan plan;
  for(const auto &[key,names]:members){
    NativeUnit unit;unit.unit=key;unit.module=p.function(*names.begin()).owner;unit.functions=names;
    if(unit.module.empty())unit.module=p.module;
    std::set<std::string> types,externalCalls;llvm::json::Array definitions,interfaces,layouts;
    std::function<void(Type)> type=[&](Type t){
      if(t.element)type(*t.element);
      if(t.kind!=Type::Record||!types.insert(t.name).second)return;
      const auto &record=p.structure(t.name);if(record.unit!=key)unitDependencies[key].insert(record.unit);
      for(const auto &argument:record.typeArguments)type(argument);
      for(auto field:record.members())type(field->type);
    };
    std::function<void(E)> expr=[&](E e){
      if(!e)return;type(e->type);type(e->annotation);
      if(e->kind==Expr::Call){
        if(e->text=="encode_json"||e->text=="decode_json")unit.wire=true;
        if(e->text.starts_with("store_"))unit.storage=true;
      }
      for(auto child:e->args)expr(child);
    };
    std::function<void(const std::vector<S>&)> block=[&](const auto &body){
      for(auto s:body){type(s->type);expr(s->expr);childBlocks(s,block);}
    };
    for(const auto &name:names){
      const auto &f=p.function(name);definitions.push_back(canonical(f));
      type(f.result);for(const auto &param:f.params)type(param.type);block(f.body);
      for(const auto &callee:f.dependencies)if(!names.contains(callee)){
        externalCalls.insert(callee);unitDependencies[key].insert(p.function(callee).unit);
      }
    }
    for(const auto &name:externalCalls){
      const auto &callee=p.function(name);interfaces.push_back(interface(callee));
      type(callee.result);for(const auto &param:callee.params)type(param.type);
    }
    for(const auto &name:types)layouts.push_back(canonical(p.structure(name)));
    unit.contract=json(llvm::json::Object{{"schema","nex.native-unit-input/1"},{"language",languageVersion},
      {"unit",key},{"module",unit.module},{"definitions",std::move(definitions)},
      {"external_interfaces",std::move(interfaces)},{"type_layouts",std::move(layouts)}},false);
    plan.units.push_back(std::move(unit));
  }
  std::set<std::string> allUnits;for(const auto &unit:plan.units)allUnits.insert(unit.unit);
  for(const auto &[key,deps]:unitDependencies){
    allUnits.insert(key);for(const auto &dep:deps){allUnits.insert(dep);unitConsumers[dep].insert(key);}
  }
  llvm::json::Array functions,units;
  for(const auto &name:reachable){const auto &f=p.function(name);functions.push_back(llvm::json::Object{
    {"name",name},{"unit",f.unit},{"callees",array(f.dependencies)},{"callers",array(callers[name])}});}
  for(const auto &key:allUnits)units.push_back(llvm::json::Object{{"unit",key},{"emitted",members.contains(key)},
    {"dependencies",array(unitDependencies[key])},{"consumers",array(unitConsumers[key])}});
  plan.dependencies=llvm::json::Object{{"schema","nex.native-dependencies/1"},{"functions",std::move(functions)},{"units",std::move(units)}};
  return plan;
}
}
