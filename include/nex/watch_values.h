#pragma once
#include "nex/language.h"
#include "nex_value.h"
#include "nex/debug_values.h"

namespace nex {
// Interpreter-only references. They never enter generated code or the runtime ABI.
struct WatchDemand { llvm::json::Value request; };
class WatchValues {
  using V=nexrt::Value;
  using JSON=llvm::json::Value;
  using Array=llvm::json::Array;
  struct Ref { std::shared_ptr<nexrt::Data> owner; std::string binding; Type type; Array path; std::string identity;Array relative; std::vector<std::string> lineage; };
  const Program &program;
  const std::map<std::string,Type> &types;
  const llvm::json::Object &values;
  const Array *captures;
  std::map<const nexrt::Data*,Ref> refs;
  std::map<std::string,const llvm::json::Object*> reads;
  std::map<std::string,V> decoded;
  std::map<const nexrt::Data*,V> callableValues;
  std::map<const nexrt::Data*,Ref> callableOrigins;
  DebugValues codec;
  std::set<std::string> bindings;
  std::map<std::string,llvm::json::Object> paths;
  uint64_t visits=0,bytes=0;
  const Ref *reference(const V &value) const;
  const JSON &read(const Ref &ref,const std::string &kind);
  V decode(const Ref &ref,const JSON &wire);
  V proxy(std::string binding,Type type,Array path,std::string identity="",Array relative={},std::vector<std::string> lineage={});
  V child(const Ref &ref,JSON segment,Type type);
  const llvm::json::Object &shape(const Ref &ref);
public:
  WatchValues(const Program &,const std::map<std::string,Type>&,const llvm::json::Object &,const Array *,const std::set<std::string> *compiled=nullptr);
  V local(const std::string &name);
  V field(const V &base,int64_t index);
  V index(const V &base,int64_t index);
  V slice(const V &base,int64_t start,int64_t count);
  int64_t length(const V &base);
  bool isSuccess(const V &base);
  V unwrap(const V &base);
  int64_t enumTag(const V &base);
  V enumField(const V &base,int64_t tag,size_t index);
  V error(const V &base,bool code);
  V callable(const V &value);
  V capture(const V &value,size_t index);
  bool equal(const V &left,const V &right);
  JSON wire(const Type &type,const V &value){return codec.encode(type,value,[this](const V &value){return concrete(value);},[this](const V &value,size_t index){return capture(value,index);});}
  V concrete(const V &value,unsigned depth=0);
  void bounded(const V &value,unsigned depth=0);
  Array readBindings() const;
  Array readPaths() const;
};
}
