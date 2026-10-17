#include "nex/language.h"
#include <functional>
namespace nex {
llvm::json::Value wireSchema(const Program &p,const Type &type){
  llvm::json::Object records,enums;std::set<std::string> seen;
  std::function<llvm::json::Value(const Type&)> describe=[&](const Type &t)->llvm::json::Value{
    if(t.kind==Type::List)return llvm::json::Object{{"list",describe(*t.element)}};
    if(t.kind==Type::Result)return llvm::json::Object{{"result",describe(*t.element)}};
    if(t.kind==Type::Record){const auto &nominal=p.structure(t.name);
      if(seen.insert(t.name).second){
        auto fields=[&](const auto &values){llvm::json::Array out;for(const auto &field:values)out.push_back(llvm::json::Object{{"name",field.name},{"type",describe(field.type)}});return out;};
        if(nominal.enumeration){llvm::json::Array cases;for(const auto &variant:nominal.variants)cases.push_back(llvm::json::Object{{"name",variant.name},{"fields",fields(variant.fields)}});enums[t.name]=std::move(cases);}
        else records[t.name]=fields(nominal.fields);
      }
      return llvm::json::Object{{nominal.enumeration?"enum":"record",t.name}};
    }
    if(t==Type::I64||t==Type::Bool||t==Type::Str)return typeName(t);
    throw Error("E_TYPE","type cannot cross the JSON boundary: "+typeName(t));
  };
  auto root=describe(type);return llvm::json::Object{{"schema","nex.wire/2"},{"root",std::move(root)},{"records",std::move(records)},{"enums",std::move(enums)}};
}
}
