#include "nex/language.h"
#include "nex_ffi_host.h"
#include <functional>
namespace nex {
llvm::json::Value foreignBinding(const Program &p,const Function &fn){
  if(!fn.foreign)throw Error("E_FFI_BINDING","function has no external binding",fn.span);
  return llvm::json::Object{{"schema","nex.foreign-binding/1"},{"library",fn.foreign->library},{"export",fn.foreign->symbol},{"manifest_sha256",fn.foreign->manifest},{"signature",foreignSignature(p,fn)}};
}
llvm::json::Value foreignSignature(const Program &p,const Function &fn){
  if(fn.test||fn.closure||!fn.typeParameters.empty())throw Error("E_FFI_SIGNATURE","select a concrete named function signature",fn.span);
  llvm::json::Array types;std::map<std::string,int64_t> indices;size_t members=0;
  std::function<int64_t(const Type&)> add=[&](const Type &t)->int64_t{
    if(containsParameter(t))throw Error("E_FFI_SIGNATURE","foreign signatures require concrete types",fn.span);
    auto key=typeName(t);if(auto i=indices.find(key);i!=indices.end())return i->second;
    if(types.size()>=4096)throw Error("E_FFI_SIGNATURE","foreign signature exceeds its type limit",fn.span);
    auto index=int64_t(types.size());indices.emplace(key,index);types.push_back(nullptr);llvm::json::Object row;
    if(t.kind==Type::List||t.kind==Type::Result){row["kind"]=t.kind==Type::List?"list":"result";row["item"]=add(*t.element);}
    else if(t.kind==Type::Function){row["kind"]="function";row["name"]=key;}
    else if(isExternalResource(p,t)){auto [name,identity]=sourceResourceClass(p,p.structure(t.name));row["kind"]="resource";row["name"]=name;row["identity"]=identity;}
    else if(t.kind==Type::Record){const auto &s=p.structure(t.name);row["kind"]=s.enumeration?"enum":"record";row["name"]=s.name;
      auto fields=[&](const auto &fields){llvm::json::Array out;for(const auto &f:fields){if(++members>65536)throw Error("E_FFI_SIGNATURE","foreign signature exceeds its field budget",f.span);out.push_back(llvm::json::Object{{"name",f.name},{"type",add(f.type)}});}return out;};
      if(s.enumeration){llvm::json::Array cases;for(const auto &v:s.variants)cases.push_back(llvm::json::Object{{"name",v.name},{"fields",fields(v.fields)}});row["variants"]=std::move(cases);}else row["fields"]=fields(s.fields);
    }else if(t==Type::I64||t==Type::F64||t==Type::Bool||t==Type::Unit||t==Type::Str||t==Type::Bytes||t==Type::File)row["kind"]=key;
    else throw Error("E_FFI_SIGNATURE","unsupported foreign signature type: "+key,fn.span);
    types[size_t(index)]=std::move(row);return index;
  };
  llvm::json::Array parameters;for(const auto &param:fn.params)parameters.push_back(add(param.type));auto result=add(fn.result);
  llvm::json::Value signature=llvm::json::Object{{"schema","nex.foreign-signature/1"},{"parameters",std::move(parameters)},{"result",result},{"types",std::move(types)}};
  auto text=json(signature,false);if(text.size()>1048576)throw Error("E_FFI_SIGNATURE","foreign signature exceeds its byte limit",fn.span);
  try{nexrt::ForeignSignature checked(text);}catch(const nexrt::DataError &e){throw Error("E_FFI_SIGNATURE",e.message,fn.span);}return signature;
}
}
