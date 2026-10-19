#pragma once
#include "nex/language.h"
#include "nex_value.h"
#include <functional>

namespace nex {
Type functionValueType(const Function &function);
const Function &checkedDebugCallable(const Program &program,const std::string &name,
  const Type &type,const std::set<std::string> *compiled=nullptr);
llvm::json::Value debugValueSchema(const Program &program,const Type &type,
  const std::set<std::string> *compiled=nullptr);

// Debug wire values are separate from application JSON. They never contain or
// execute a native code pointer; a target is resolved through checked source.
class DebugValues {
  using V=nexrt::Value;
  using JSON=llvm::json::Value;
  using Array=llvm::json::Array;
  const Program &program;
  const std::set<std::string> *compiled;
  std::map<const nexrt::Data*,std::pair<std::shared_ptr<nexrt::Data>,std::string>> identities;
  std::map<std::string,std::string> targets,observations;
  std::map<std::string,nexrt::ByteBuffer> binaryValues;
  std::map<std::string,std::map<int64_t,int64_t>> binaryOctets;
  std::set<std::string> active;
  uint64_t visits=0,text=0,computed=0,observationBytes=0;
  void budget(unsigned depth);
  V decode(const Type &,const JSON &,unsigned,const std::string &,const Array &);
  JSON encode(const Type &,const V &,unsigned,const std::function<V(const V&)> &,const std::function<V(const V&,size_t)> &);
public:
  DebugValues(const Program &program,const std::set<std::string> *compiled=nullptr)
    :program(program),compiled(compiled){}
  const std::set<std::string> *compiledTargets()const{return compiled;}
  void observe(const std::string &identity,const Array &path,const std::string &kind,const JSON &value);
  void observeBytes(const std::string &identity,const Array &path,const nexrt::ByteBuffer &value);
  void observeByte(const std::string &identity,const Array &path,int64_t index,int64_t value);
  std::pair<std::string,std::string> callableShape(const Type &type,const JSON &value);
  void identify(const V &value,const std::string &identity){identities[value.object.get()]={value.object,identity};}
  std::string identity(const V &value)const;
  V decode(const Type &type,const JSON &value){return decode(type,value,0,"",{});}
  V decode(const Type &type,const JSON &value,const std::string &identity,const Array &path){return decode(type,value,0,identity,path);}
  JSON encode(const Type &type,const V &value,const std::function<V(const V&)> &materialize={},const std::function<V(const V&,size_t)> &capture={}){
    return encode(type,value,0,materialize,capture);
  }
};
}
