#include "nex/debug_values.h"
#include <charconv>
#include <limits>

namespace nex {
namespace {
using JSON=llvm::json::Value;using Object=llvm::json::Object;using Array=llvm::json::Array;
[[noreturn]] void invalid(const std::string &message){throw Error("E_DEBUG_VALUE",message);}
const Object &object(const JSON &value){auto result=value.getAsObject();if(!result)invalid("expected a debug wire object");return *result;}
std::string string(const JSON &value){auto text=value.getAsString();if(!text)invalid("expected debug wire text");nexrt::unicodeOffsets(text->str(),false);return text->str();}
std::string field(const Object &value,const char *name){auto item=value.get(name);if(!item)invalid(std::string("missing debug wire field: ")+name);return string(*item);}
Array path(const Array &prefix,JSON part){auto result=Array(prefix);result.push_back(std::move(part));return result;}
int64_t integer(const JSON &value){
  auto text=string(value);size_t first=text.starts_with('-')?1:0;
  if(first==text.size()||(text[first]=='0'&&(first||text.size()!=1)))invalid("debug i64 requires canonical decimal text");
  int64_t result=0;auto parsed=std::from_chars(text.data(),text.data()+text.size(),result);
  if(parsed.ec!=std::errc()||parsed.ptr!=text.data()+text.size())invalid("debug integer is outside i64");return result;
}
std::string identity(const Object &value){
  auto text=field(value,"identity");uint64_t number=0;
  if(text.empty()||text.size()>20||text.front()<'1'||text.front()>'9')invalid("stopped callable identity requires nonzero canonical u64 text");
  auto parsed=std::from_chars(text.data(),text.data()+text.size(),number);
  if(parsed.ec!=std::errc()||parsed.ptr!=text.data()+text.size()||!number)invalid("invalid stopped callable identity");return text;
}
std::string symbol(const Function &fn){return nativeSymbol(fn.name)+(fn.closure?"":"__closure_bridge");}
bool concrete(const Function &fn){
  if(fn.test||!fn.typeParameters.empty()||containsParameter(fn.result))return false;
  for(const auto &param:fn.params)if(containsParameter(param.type))return false;
  for(const auto &capture:fn.captures)if(containsParameter(capture.type))return false;return true;
}
}
Type functionValueType(const Function &fn){std::vector<Type> args;for(const auto &param:fn.params)args.push_back(param.type);return Type::function(std::move(args),fn.result,fn.realm,fn.effects);}
const Function &checkedDebugCallable(const Program &program,const std::string &name,const Type &type,const std::set<std::string> *compiled){
  if(type.kind!=Type::Function)invalid("callable value has a non-callable type");
  const Function *target=nullptr;for(const auto &fn:program.functions)if(fn.name==name){target=&fn;break;}
  if(!target||!concrete(*target)||functionValueType(*target)!=type)invalid("stopped callable target/signature differs from checked source");
  if(compiled&&!compiled->contains(name))invalid("stopped callable target has no compiled entry in this debug build");return *target;
}
JSON debugValueSchema(const Program &program,const Type &type,const std::set<std::string> *compiled){
  if(satisfiesConstraint(program,type,"wire"))return wireSchema(program,type);
  Object records,enums,targets;std::set<std::string> seen,wanted,done;size_t nodes=0;
  std::function<JSON(const Type&)> describe=[&](const Type &value)->JSON{
    if(++nodes>100000)throw Error("E_DEBUG_LIMIT","debug type descriptor exceeds node budget");
    if(value.kind==Type::Function){auto name=typeName(value);wanted.insert(name);return Object{{"function",name}};}
    if(value.kind==Type::List)return Object{{"list",describe(*value.element)}};
    if(value.kind==Type::Result)return Object{{"result",describe(*value.element)}};
    if(value.kind==Type::Record){const auto &nominal=program.structure(value.name);if(seen.insert(value.name).second){
      auto fields=[&](const auto &values){Array result;for(const auto &field:values)result.push_back(Object{{"name",field.name},{"type",describe(field.type)}});return result;};
      if(nominal.enumeration){Array cases;for(const auto &variant:nominal.variants)cases.push_back(Object{{"name",variant.name},{"fields",fields(variant.fields)}});enums[value.name]=std::move(cases);}else records[value.name]=fields(nominal.fields);
    }return Object{{nominal.enumeration?"enum":"record",value.name}};}
    if(value==Type::I64||value==Type::F64||value==Type::Bool||value==Type::Str||value==Type::Bytes||value==Type::File)return typeName(value);
    invalid("unsupported debug value type: "+typeName(value));
  };
  auto root=describe(type);
  while(done.size()<wanted.size()){
    std::string signature;for(const auto &name:wanted)if(!done.contains(name)){signature=name;break;}done.insert(signature);
    for(const auto &fn:program.functions)if(concrete(fn)&&typeName(functionValueType(fn))==signature){
      Array captures;for(const auto &capture:fn.captures)captures.push_back(Object{{"name",capture.name},{"type",describe(capture.type)}});
      targets[fn.name]=Object{{"type",signature},{"symbol",symbol(fn)},{"compiled",!compiled||compiled->contains(fn.name)},{"captures",std::move(captures)}};
    }
  }
  return Object{{"schema","nex.debug-wire/1"},{"root",std::move(root)},{"records",std::move(records)},{"enums",std::move(enums)},{"targets",std::move(targets)}};
}
void DebugValues::budget(unsigned depth){if(depth>64||++visits>100000||text>8*1048576)throw Error("E_DEBUG_LIMIT","debug wire value exceeds its depth/node/text budget");}
void DebugValues::observe(const std::string &id,const Array &path,const std::string &kind,const JSON &value){
  if(id.empty())return;auto key=id+":"+json(Array(path),false)+":"+kind;auto data=json(value,false);auto at=observations.find(key);
  if(at!=observations.end()){if(at->second!=data)invalid("conflicting captures for one stopped callable identity");return;}
  auto bytes=key.size()+data.size();if(observationBytes+bytes>8*1048576)throw Error("E_DEBUG_LIMIT","callable alias observations exceed byte budget");
  observationBytes+=bytes;observations.emplace(std::move(key),std::move(data));
}
void DebugValues::observeBytes(const std::string &id,const Array &path,const nexrt::ByteBuffer &value){
  if(id.empty())return;auto key=id+":"+json(Array(path),false);
  if(auto old=binaryValues.find(key);old!=binaryValues.end()&&old->second!=value)invalid("conflicting binary captures for one stopped callable identity");
  if(auto selected=binaryOctets.find(key);selected!=binaryOctets.end())for(auto [index,octet]:selected->second)
    if(index<0||index>=value.length()||value.at(index)!=octet)invalid("binary value conflicts with a captured octet");
  binaryValues.emplace(std::move(key),value);
}
void DebugValues::observeByte(const std::string &id,const Array &path,int64_t index,int64_t value){
  if(value<0||value>255)invalid("stopped binary octet is outside 0..255");
  if(id.empty())return;auto key=id+":"+json(Array(path),false);
  if(auto whole=binaryValues.find(key);whole!=binaryValues.end())
    if(index<0||index>=whole->second.length()||whole->second.at(index)!=value)invalid("captured octet conflicts with its binary value");
  auto [at,inserted]=binaryOctets[key].emplace(index,value);if(!inserted&&at->second!=value)invalid("conflicting captured binary octets");
}
void DebugValues::observeString(const std::string &id,const Array &path,const std::string &value){
  if(id.empty())return;auto key=id+":"+json(Array(path),false);auto offsets=nexrt::unicodeOffsets(value);
  observe(id,path,"shape",Object{{"length",std::to_string(offsets.size()-1)}});
  if(auto old=stringValues.find(key);old!=stringValues.end()&&old->second.text!=value)invalid("conflicting string captures for one stopped callable identity");
  if(auto selected=stringScalars.find(key);selected!=stringScalars.end())for(const auto &[index,scalar]:selected->second)
    if(index<0||uint64_t(index)>=offsets.size()-1||value.substr(offsets[index],offsets[index+1]-offsets[index])!=scalar)invalid("string value conflicts with a captured scalar range");
  stringValues.emplace(std::move(key),TextValue{value,std::move(offsets)});
}
void DebugValues::observeTextRange(const std::string &id,const Array &path,int64_t start,const std::string &value){
  if(id.empty())return;auto key=id+":"+json(Array(path),false);auto offsets=nexrt::unicodeOffsets(value);
  for(size_t i=0;i+1<offsets.size();++i){auto index=start+int64_t(i);auto scalar=value.substr(offsets[i],offsets[i+1]-offsets[i]);
    if(auto whole=stringValues.find(key);whole!=stringValues.end()){
      const auto &full=whole->second;if(index<0||uint64_t(index)>=full.offsets.size()-1||full.text.substr(full.offsets[index],full.offsets[index+1]-full.offsets[index])!=scalar)invalid("captured string range conflicts with its whole value");
    }
    auto &selected=stringScalars[key];auto at=selected.find(index);
    if(at!=selected.end()){if(at->second!=scalar)invalid("conflicting overlapping string scalar ranges");}
    else{if(++textScalarObservations>100000)throw Error("E_DEBUG_LIMIT","stopped-string scalar observations exceed 100000 values");selected.emplace(index,std::move(scalar));}
  }
}
std::pair<std::string,std::string> DebugValues::callableShape(const Type &type,const JSON &wire){
  const auto &value=object(wire);if(value.size()!=2)invalid("callable shape requires function and identity");auto name=field(value,"function"),id=nex::identity(value);
  checkedDebugCallable(program,name,type,compiled);auto descriptor=name+"\n"+typeName(type);auto [at,inserted]=targets.emplace(id,descriptor);if(!inserted&&at->second!=descriptor)invalid("one callable identity has conflicting checked targets");return {name,id};
}
std::string DebugValues::identity(const V &value)const{auto found=identities.find(value.object.get());return found==identities.end()?"":found->second.second;}
DebugValues::V DebugValues::decode(const Type &type,const JSON &wire,unsigned depth,const std::string &id,const Array &prefix){
  budget(depth);
  if(type==Type::I64){auto value=integer(wire);observe(id,prefix,"value",wire);return V(value);}
  if(type==Type::F64){nexrt::FloatEnvironment environment;auto value=wire.getAsNumber();if(!value||!std::isfinite(*value))invalid("expected finite debug f64 number");auto result=V::floating(*value);observe(id,prefix,"value",JSON(result.floating()));return result;}
  if(type==Type::Bool){auto value=wire.getAsBoolean();if(!value)invalid("expected debug boolean");observe(id,prefix,"value",wire);return V(*value,true);}
  if(type==Type::Str){auto value=string(wire);text+=value.size();budget(depth);observe(id,prefix,"value",wire);observeString(id,prefix,value);return V(nexrt::string(std::move(value)));}
  if(type==Type::Bytes){
    auto encoded=string(wire);text+=encoded.size();budget(depth);nexrt::ByteBuffer buffer;
    try{buffer=nexrt::ByteBuffer::fromBase64(encoded);}catch(const nexrt::DataError&){invalid("debug bytes require canonical padded base64");}
    text+=buffer.length();budget(depth);observe(id,prefix,"shape",Object{{"length",std::to_string(buffer.length())}});observe(id,prefix,"value",wire);observeBytes(id,prefix,buffer);
    return V(nexrt::bytes(std::move(buffer)));
  }
  if(type==Type::File){
    const auto &value=object(wire);if(value.size()!=1)invalid("debug file requires only its opaque identity");
    auto text=field(value,"file");auto canonical=nex::identity(Object{{"identity",text}});uint64_t number=0;
    std::from_chars(canonical.data(),canonical.data()+canonical.size(),number);observe(id,prefix,"value",wire);
    return V(nexrt::diagnosticFile(number));
  }
  if(type.kind==Type::Function){
    const auto &value=object(wire);if(value.size()!=3||!value.get("captures"))invalid("debug callable requires function, identity and captures");
    JSON shape=Object{{"function",field(value,"function")},{"identity",field(value,"identity")}};auto [name,identity]=callableShape(type,shape);observe(id,prefix,"shape",shape);
    const auto &fn=checkedDebugCallable(program,name,type,compiled);const auto &captures=object(*value.get("captures"));if(captures.size()!=fn.captures.size())invalid("stopped callable capture layout differs");
    if(!active.insert(identity).second)invalid("stopped callable captures contain an identity cycle");auto data=std::make_shared<nexrt::Data>(nexrt::Data::Closure);data->text=name;
    try{for(const auto &capture:fn.captures){auto child=captures.get(capture.name);if(!child)invalid("missing callable capture: "+capture.name);data->names.push_back(capture.name);data->values.push_back(decode(capture.type,*child,depth+2,identity,Array{capture.name}));}}catch(...){active.erase(identity);throw;}
    active.erase(identity);V result(data);identify(result,identity);return result;
  }
  if(type.kind==Type::List){auto array=wire.getAsArray();if(!array||array->size()>10000)invalid("debug list exceeds its item limit");observe(id,prefix,"shape",Object{{"length",std::to_string(array->size())}});auto data=std::make_shared<nexrt::Data>(nexrt::Data::List);for(size_t i=0;i<array->size();++i)data->values.push_back(decode(*type.element,(*array)[i],depth+1,id,path(prefix,int64_t(i))));return V(data);}
  if(type.kind==Type::Result){
    const auto &value=object(wire);if(value.size()!=1)invalid("invalid tagged debug result");if(auto child=value.get("ok")){observe(id,prefix,"shape",Object{{"ok",true}});return nexrt::success(decode(*type.element,*child,depth+1,id,path(prefix,"ok")));}
    auto error=value.getObject("error");if(!error||error->size()!=2)invalid("invalid debug result error");auto code=field(*error,"code"),message=field(*error,"message");text+=code.size()+message.size();budget(depth+2);observe(id,prefix,"shape",Object{{"ok",false}});observe(id,path(prefix,"code"),"value",code);observe(id,path(prefix,"message"),"value",message);return nexrt::failure(std::move(code),std::move(message));
  }
  if(type.kind==Type::Record){
    const auto &nominal=program.structure(type.name);const auto &value=object(wire);const Object *fields=&value;const std::vector<Param> *members=&nominal.fields;int64_t ordinal=0;
    if(nominal.enumeration){auto name=field(value,"case");fields=value.getObject("fields");if(value.size()!=2||!fields)invalid("invalid tagged debug enum");members=nullptr;for(const auto &variant:nominal.variants)if(variant.name==name){members=&variant.fields;ordinal=variant.ordinal;break;}if(!members)invalid("unknown stopped enum case");observe(id,prefix,"shape",Object{{"case",name}});}
    else observe(id,prefix,"shape",Object{{"record",type.name}});
    if(fields->size()!=members->size()||members->size()>10000)invalid("debug nominal fields differ from their checked layout/item budget");auto data=std::make_shared<nexrt::Data>(nominal.enumeration?nexrt::Data::Enum:nexrt::Data::Record);data->text=type.name;data->ordinal=ordinal;if(nominal.enumeration)data->text+="::"+nominal.variants[ordinal].name;
    for(const auto &member:*members){auto child=fields->get(member.name);if(!child)invalid("missing stopped nominal field");data->names.push_back(member.name);auto segment=nominal.enumeration?nominal.variants[ordinal].name+"::"+member.name:member.name;data->values.push_back(decode(member.type,*child,depth+(nominal.enumeration?2:1),id,path(prefix,segment)));}return V(data);
  }
  invalid("unsupported stopped value type");
}
DebugValues::JSON DebugValues::encode(const Type &type,const V &original,unsigned depth,const std::function<V(const V&)> &materialize,const std::function<V(const V&,size_t)> &capture){
  budget(depth);auto value=materialize?materialize(original):original;
  if(type==Type::I64)return std::to_string(value.scalar);if(type==Type::F64){if(value.tag!=V::Floating)invalid("computed f64 lost its scalar tag");return value.floating();}if(type==Type::Bool)return bool(value.scalar);if(type==Type::Str){text+=value.object->text.size();budget(depth);return value.object->text;}
  if(type==Type::Bytes){const auto &buffer=nexrt::byteBuffer(value.object);text+=uint64_t(buffer.length());budget(depth);auto encoded=buffer.base64();text+=encoded.size();budget(depth);return encoded;}
  if(type==Type::File)return Object{{"file",std::to_string(nexrt::fileIdentity(value.object))}};
  if(type.kind==Type::Function){
    const auto &fn=checkedDebugCallable(program,value.object->text,type);if(value.object->values.size()!=fn.captures.size()||value.object->names.size()!=fn.captures.size())invalid("computed callable capture layout differs");
    auto identity=this->identity(value);if(identity.empty()){identity="computed:"+std::to_string(++computed);identify(value,identity);}Object captures;
    for(size_t i=0;i<fn.captures.size();++i){if(value.object->names[i]!=fn.captures[i].name)invalid("computed callable capture names differ");captures[fn.captures[i].name]=encode(fn.captures[i].type,capture?capture(value,i):value.object->values[i],depth+2,materialize,capture);}
    return Object{{"function",fn.name},{"identity",identity},{"captures",std::move(captures)}};
  }
  if(type.kind==Type::List){Array result;if(value.object->values.size()>10000)invalid("computed debug list exceeds its item limit");for(const auto &child:value.object->values)result.push_back(encode(*type.element,child,depth+1,materialize,capture));return result;}
  if(type.kind==Type::Result){if(nexrt::isSuccess(value))return Object{{"ok",encode(*type.element,value.object->values[0],depth+1,materialize,capture)}};return Object{{"error",Object{{"code",value.object->text},{"message",value.object->values[0].object->text}}}};}
  if(type.kind==Type::Record){const auto &nominal=program.structure(type.name);const auto &members=nominal.enumeration?nominal.variants.at(value.object->ordinal).fields:nominal.fields;Object result;if(members.size()!=value.object->values.size()||members.size()>10000)invalid("computed nominal layout/item budget differs");for(size_t i=0;i<members.size();++i)result[members[i].name]=encode(members[i].type,value.object->values[i],depth+(nominal.enumeration?2:1),materialize,capture);if(nominal.enumeration)return Object{{"case",nominal.variants.at(value.object->ordinal).name},{"fields",std::move(result)}};return result;}
  invalid("unsupported computed debug value type");
}
}
