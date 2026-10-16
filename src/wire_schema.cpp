#include "nex/language.h"
#include <functional>

namespace nex {
llvm::json::Value wireSchema(const Program &p,const Type &type){
  llvm::json::Object records;std::set<std::string> seen;
  std::function<llvm::json::Value(const Type&)> describe=[&](const Type &t)->llvm::json::Value{
    if(t.kind==Type::List)return llvm::json::Object{{"list",describe(*t.element)}};
    if(t.kind==Type::Result)return llvm::json::Object{{"result",describe(*t.element)}};
    if(t.kind==Type::Record){
      if(seen.insert(t.name).second){
        llvm::json::Array fields;for(const auto &field:p.structure(t.name).fields)fields.push_back(llvm::json::Object{{"name",field.name},{"type",describe(field.type)}});
        records[t.name]=std::move(fields);
      }
      return llvm::json::Object{{"record",t.name}};
    }
    if(t==Type::I64||t==Type::Bool||t==Type::Str)return typeName(t);
    throw Error("E_TYPE","type cannot cross the JSON boundary: "+typeName(t));
  };
  auto root=describe(type);return llvm::json::Object{{"schema","nex.wire/1"},{"root",std::move(root)},{"records",std::move(records)}};
}
}
