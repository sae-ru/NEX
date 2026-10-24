#include "nex_ffi_types.h"
#include "nex_json.h"
#include "third_party/json.hpp"
#include <algorithm>
#include <map>
#include <set>

namespace nexrt {
namespace {
using J=nlohmann::ordered_json;
[[noreturn]] void schemaError(const std::string &message){throw DataError("E_FFI_SIGNATURE",message);}
[[noreturn]] void valueError(const std::string &message){throw DataError("E_FFI_TYPE",message);}
void keys(const J &value,std::initializer_list<const char*> names){
  if(!value.is_object()||value.size()!=names.size())schemaError("foreign signature object fields differ");
  for(auto name:names)if(!value.contains(name))schemaError("missing foreign signature field");
}
uint64_t number(const J &value){
  if(!value.is_number_integer()||(!value.is_number_unsigned()&&value.get<int64_t>()<0))schemaError("foreign type index must be an unsigned integer");
  return value.get<uint64_t>();
}
std::string name(const J &value,bool identifier=false){
  if(!value.is_string())schemaError("foreign signature name must be text");auto text=value.get<std::string>();
  if(text.empty()||text.size()>4096||text.find('\0')!=std::string::npos)schemaError("invalid foreign signature name");
  unicodeOffsets(text,false);
  if(identifier){auto letter=[](unsigned char c){return(c>='a'&&c<='z')||(c>='A'&&c<='Z')||c=='_';};
    if(!letter(text.front())||!std::all_of(text.begin(),text.end(),[&](unsigned char c){return letter(c)||(c>='0'&&c<='9');}))schemaError("foreign field/case names must be source identifiers");
  }
  return text;
}
struct Field {std::string name;size_t type;};
struct Variant {std::string name;std::vector<Field> fields;};
struct Shape {uint32_t kind=0;std::string name,identity;size_t item=0;std::vector<Field> fields;std::vector<Variant> variants;};
const std::map<std::string,uint32_t> kinds={{"i64",NEX_FFI_I64},{"f64",NEX_FFI_F64},{"bool",NEX_FFI_BOOL},{"str",NEX_FFI_STRING},{"bytes",NEX_FFI_BYTES},{"list",NEX_FFI_LIST},{"record",NEX_FFI_RECORD},{"enum",NEX_FFI_ENUM},{"result",NEX_FFI_RESULT},{"function",NEX_FFI_FUNCTION},{"file",NEX_FFI_FILE},{"unit",NEX_FFI_UNIT},{"resource",NEX_FFI_EXTERNAL_RESOURCE}};
}
struct ForeignSignature::Layout {
  std::string description,canonical;
  std::vector<Shape> types;
  std::vector<size_t> parameters;
  size_t result=0;
  std::set<size_t> resultReachable;
};
ForeignSignature::ForeignSignature(const std::string &text){
  try{
    validateJSONText(text);auto doc=J::parse(text);keys(doc,{"schema","parameters","result","types"});
    if(doc.at("schema")!="nex.foreign-signature/1"||!doc.at("types").is_array()||doc.at("types").empty()||doc.at("types").size()>4096||!doc.at("parameters").is_array()||doc.at("parameters").size()>4096)schemaError("unsupported foreign signature shape/limits");
    auto out=std::make_shared<Layout>();size_t fields=0;
    auto index=[&](const J &value){auto n=number(value);if(n>=doc.at("types").size())schemaError("foreign type index is outside its table");return size_t(n);};
    auto members=[&](const J &value){
      if(!value.is_array()||value.size()>1024)schemaError("foreign fields exceed their limit");
      std::vector<Field> result;std::set<std::string> names;
      for(const auto &field:value){if(++fields>65536)schemaError("foreign signature exceeds field budget");keys(field,{"name","type"});auto key=name(field.at("name"),true);if(!names.insert(key).second)schemaError("duplicate foreign field");result.push_back({std::move(key),index(field.at("type"))});}
      return result;
    };
    std::set<std::string> unique;
    for(const auto &item:doc.at("types")){
      if(!item.is_object()||!item.contains("kind")||!item.at("kind").is_string())schemaError("missing foreign type kind");
      auto kind=item.at("kind").get<std::string>();if(!kinds.contains(kind))schemaError("unknown foreign type kind");Shape type;type.kind=kinds.at(kind);std::string identity=kind;
      if(kind=="list"||kind=="result"){keys(item,{"kind","item"});type.item=index(item.at("item"));identity+=':'+std::to_string(type.item);}
      else if(kind=="record"){keys(item,{"kind","name","fields"});type.name=name(item.at("name"));type.fields=members(item.at("fields"));identity="nominal:"+type.name;}
      else if(kind=="enum"){
        keys(item,{"kind","name","variants"});type.name=name(item.at("name"));identity="nominal:"+type.name;auto &cases=item.at("variants");
        if(!cases.is_array()||cases.empty()||cases.size()>4096)schemaError("invalid foreign enum cases");std::set<std::string> names;
        for(const auto &variant:cases){keys(variant,{"name","fields"});auto key=name(variant.at("name"),true);if(!names.insert(key).second)schemaError("duplicate foreign enum case");type.variants.push_back({std::move(key),members(variant.at("fields"))});}
      }else if(kind=="resource"){
        keys(item,{"kind","name","identity"});type.name=name(item.at("name"));type.identity=name(item.at("identity"));
        // Reuse the exact host registration metadata validator. Registration
        // identity itself is assigned by the loaded image, never by this text.
        ExternalResourceClass checked(type.name,type.identity);identity="nominal:"+type.name;
      }else if(kind=="function"){keys(item,{"kind","name"});type.name=name(item.at("name"));identity+=':'+type.name;}
      else keys(item,{"kind"});
      if(!unique.insert(identity).second)schemaError("duplicate foreign type identity");out->types.push_back(std::move(type));
    }
    for(const auto &value:doc.at("parameters"))out->parameters.push_back(index(value));out->result=index(doc.at("result"));
    auto nonunit=[&](size_t i){if(out->types[i].kind==NEX_FFI_UNIT)schemaError("unit is only a foreign function result");};
    for(auto i:out->parameters)nonunit(i);
    for(const auto &type:out->types){if(type.kind==NEX_FFI_LIST||type.kind==NEX_FFI_RESULT)nonunit(type.item);for(const auto &f:type.fields)nonunit(f.type);for(const auto &v:type.variants)for(const auto &f:v.fields)nonunit(f.type);}
    std::set<size_t> visited;std::vector<size_t> pending=out->parameters;pending.push_back(out->result);
    while(!pending.empty()){auto i=pending.back();pending.pop_back();if(!visited.insert(i).second)continue;const auto &t=out->types[i];if(t.kind==NEX_FFI_LIST||t.kind==NEX_FFI_RESULT)pending.push_back(t.item);for(const auto &f:t.fields)pending.push_back(f.type);for(const auto &v:t.variants)for(const auto &f:v.fields)pending.push_back(f.type);}
    if(visited.size()!=out->types.size())schemaError("foreign signature contains unreachable types");
    pending={out->result};
    while(!pending.empty()){auto i=pending.back();pending.pop_back();if(!out->resultReachable.insert(i).second)continue;const auto &t=out->types[i];if(t.kind==NEX_FFI_LIST||t.kind==NEX_FFI_RESULT)pending.push_back(t.item);for(const auto &f:t.fields)pending.push_back(f.type);for(const auto &v:t.variants)for(const auto &f:v.fields)pending.push_back(f.type);}
    for(size_t i=0;i<out->types.size();++i){std::set<size_t> chain;auto at=i;while(out->types[at].kind==NEX_FFI_LIST||out->types[at].kind==NEX_FFI_RESULT){if(!chain.insert(at).second)schemaError("recursive foreign containers need a nominal type");at=out->types[at].item;}}
    out->description=doc.dump();out->canonical=nlohmann::json(doc).dump();layout=std::move(out);
  }catch(const DataError &e){if(e.code=="E_FFI_SIGNATURE")throw;schemaError(e.what());}
  catch(const J::exception &){schemaError("invalid foreign signature JSON");}
}
const std::string &ForeignSignature::canonical()const{if(!layout)schemaError("foreign signature has no layout");return layout->canonical;}
bool ForeignSignature::hasResources()const{return layout&&std::any_of(layout->types.begin(),layout->types.end(),[](const auto &t){return t.kind==NEX_FFI_EXTERNAL_RESOURCE;});}
namespace foreign_detail {
struct TypedContext::Impl {
  std::shared_ptr<const ForeignSignature::Layout> layout;
  std::map<const Data*,size_t> functions;
  bool bound=false;
  explicit Impl(const ForeignSignature &signature):layout(signature.layout){if(!layout)schemaError("foreign signature has no layout");}
  const Shape &shape(size_t index)const{if(index>=layout->types.size())valueError("unknown foreign type");return layout->types[index];}
  const std::vector<Field> &fields(size_t index,uint64_t variant)const{
    const auto &t=shape(index);if(t.kind==NEX_FFI_RECORD){if(variant)valueError("record has no such variant");return t.fields;}
    if(t.kind!=NEX_FFI_ENUM||variant>=t.variants.size())valueError("invalid foreign nominal variant");return t.variants[size_t(variant)].fields;
  }
  struct Validation {
    Impl &context;const std::function<void()> &poll;bool arguments;
    size_t nodes=0;std::set<std::pair<const Data*,size_t>> active,done;
    Validation(Impl &context,const std::function<void()> &poll,bool arguments):context(context),poll(poll),arguments(arguments){}
    void check(const Value &value,size_t type,unsigned depth=0){
      if(depth>128||++nodes>100000)throw DataError("E_FFI_LIMIT","foreign value validation exceeds its depth/node budget");
      if(poll&&(nodes==1||nodes%64==0))poll();const auto &t=context.shape(type);
      if(t.kind==NEX_FFI_I64){if(value.tag!=Value::Integer)valueError("foreign result requires i64");return;}
      if(t.kind==NEX_FFI_F64){if(value.tag!=Value::Floating)valueError("foreign result requires f64");(void)value.floating();return;}
      if(t.kind==NEX_FFI_BOOL){if(value.tag!=Value::Boolean||(value.scalar!=0&&value.scalar!=1))valueError("foreign result requires bool");return;}
      if(value.tag!=Value::Object||!value.object)valueError("foreign result requires an owned value");
      const auto &d=*value.object;auto key=std::pair{&d,type};if(done.contains(key))return;
      if(!active.insert(key).second)valueError("cyclic foreign value graph");
      if(t.kind==NEX_FFI_STRING){if(d.kind!=Data::String)valueError("foreign result requires str");}
      else if(t.kind==NEX_FFI_BYTES){if(d.kind!=Data::Bytes)valueError("foreign result requires bytes");(void)byteBuffer(value.object);}
      else if(t.kind==NEX_FFI_FILE){if(d.kind!=Data::File||static_cast<const FileData&>(d).diagnosticIdentity||!static_cast<const FileData&>(d).resource.identity())valueError("foreign result requires a genuine file owner");}
      else if(t.kind==NEX_FFI_EXTERNAL_RESOURCE){
        if(d.kind!=Data::External)valueError("foreign result requires an external owner");
        const auto &r=externalResource(value.object);
        if(!r.identity()||r.typeName()!=t.name||r.typeHash()!=t.identity)valueError("foreign external resource identity differs");
      }
      else if(t.kind==NEX_FFI_FUNCTION){
        if(d.kind!=Data::Closure)valueError("foreign result requires a function value");
        if(arguments){auto [i,added]=context.functions.emplace(&d,type);if(!added&&i->second!=type)valueError("one callable has conflicting input types");}
        else{auto i=context.functions.find(&d);if(i==context.functions.end()||i->second!=type)valueError("foreign function value has a different signature or authority");}
      }else if(t.kind==NEX_FFI_LIST){if(d.kind!=Data::List)valueError("foreign result requires list");for(const auto &v:d.values)check(v,t.item,depth+1);}
      else if(t.kind==NEX_FFI_RESULT){
        if(d.kind==Data::Success){if(d.values.size()!=1)valueError("foreign success payload differs");check(d.values[0],t.item,depth+1);}
        else if(d.kind==Data::Failure){if(d.values.size()!=1||d.values[0].tag!=Value::Object||!d.values[0].object||d.values[0].object->kind!=Data::String)valueError("foreign failure payload differs");}
        else valueError("foreign result requires result");
      }else if(t.kind==NEX_FFI_RECORD||t.kind==NEX_FFI_ENUM){
        if(d.kind!=(t.kind==NEX_FFI_RECORD?Data::Record:Data::Enum))valueError("foreign nominal kind differs");uint64_t variant=0;std::string expected=t.name;
        if(t.kind==NEX_FFI_ENUM){if(d.ordinal<0||uint64_t(d.ordinal)>=t.variants.size())valueError("foreign enum discriminant differs");variant=uint64_t(d.ordinal);expected+="::"+t.variants[size_t(variant)].name;}
        const auto &fields=context.fields(type,variant);if(d.text!=expected||d.values.size()!=fields.size()||d.names.size()!=fields.size())valueError("foreign nominal identity/layout differs");
        for(size_t i=0;i<fields.size();++i){if(d.names[i]!=fields[i].name)valueError("foreign nominal field names differ");check(d.values[i],fields[i].type,depth+1);}
      }else valueError("unit cannot be a foreign value");
      active.erase(key);done.insert(key);
    }
  };
};
TypedContext::TypedContext(const ForeignSignature &signature):impl(std::make_unique<Impl>(signature)){}
TypedContext::~TypedContext()=default;
std::pair<std::string,std::string> TypedContext::resource(size_t type)const{const auto &t=impl->shape(type);if(t.kind!=NEX_FFI_EXTERNAL_RESOURCE)valueError("foreign type is not an external resource");return {t.name,t.identity};}
bool TypedContext::resourceConstructible(size_t type)const{return impl->shape(type).kind==NEX_FFI_EXTERNAL_RESOURCE&&impl->layout->resultReachable.contains(type);}
bool TypedContext::resourceDeclared(const std::string &name,const std::string &identity)const{return std::any_of(impl->layout->types.begin(),impl->layout->types.end(),[&](const auto &t){return t.kind==NEX_FFI_EXTERNAL_RESOURCE&&t.name==name&&t.identity==identity;});}
void TypedContext::arguments(std::span<const Value> values,const std::function<void()> &poll){
  if(values.size()!=impl->layout->parameters.size())valueError("foreign argument count differs");
  impl->functions.clear();impl->bound=false;Impl::Validation validation{*impl,poll,true};for(size_t i=0;i<values.size();++i)validation.check(values[i],impl->layout->parameters[i]);impl->bound=true;
}
void TypedContext::result(const Value &value,const std::function<void()> &poll){if(!impl->bound)valueError("unbound foreign signature");Impl::Validation validation{*impl,poll,false};validation.check(value,impl->layout->result);}
bool TypedContext::unitResult()const{return kind(resultType())==NEX_FFI_UNIT;}
size_t TypedContext::parameter(uint64_t index)const{if(index>=impl->layout->parameters.size())throw DataError("E_BOUNDS","foreign argument type index differs");return impl->layout->parameters[size_t(index)];}
size_t TypedContext::resultType()const{return impl->layout->result;}
uint32_t TypedContext::kind(size_t type)const{return impl->shape(type).kind;}
uint64_t TypedContext::variants(size_t type)const{auto &t=impl->shape(type);if(t.kind!=NEX_FFI_ENUM)valueError("foreign type is not an enum");return t.variants.size();}
uint64_t TypedContext::children(size_t type,uint64_t variant)const{auto &t=impl->shape(type);if(t.kind==NEX_FFI_LIST||t.kind==NEX_FFI_RESULT){if(variant)valueError("container has no such variant");return 1;}return impl->fields(type,variant).size();}
size_t TypedContext::child(size_t type,uint64_t variant,uint64_t index)const{auto &t=impl->shape(type);if(t.kind==NEX_FFI_LIST||t.kind==NEX_FFI_RESULT){if(variant||index)valueError("container item index differs");return t.item;}auto &fields=impl->fields(type,variant);if(index>=fields.size())valueError("foreign field type index differs");return fields[size_t(index)].type;}
uint64_t TypedContext::nominalBytes(size_t type,uint64_t variant)const{
  const auto &t=impl->shape(type);const auto &fields=impl->fields(type,variant);
  uint64_t bytes=t.name.size()+fields.size()*(sizeof(Value)+sizeof(std::string));
  if(t.kind==NEX_FFI_ENUM)bytes+=2+t.variants[size_t(variant)].name.size();
  for(const auto &field:fields)bytes+=field.name.size();return bytes;
}
Value TypedContext::nominal(size_t type,uint64_t variant,std::span<const Value> values,const std::function<void()> &poll){
  if(!impl->bound)valueError("unbound foreign signature");const auto &t=impl->shape(type);const auto &fields=impl->fields(type,variant);
  if(values.size()!=fields.size())valueError("foreign nominal constructor arity differs");Impl::Validation validation{*impl,poll,false};for(size_t i=0;i<values.size();++i)validation.check(values[i],fields[i].type);
  auto data=std::make_shared<Data>(t.kind==NEX_FFI_RECORD?Data::Record:Data::Enum);data->text=t.name;data->ordinal=int64_t(variant);
  if(t.kind==NEX_FFI_ENUM)data->text+="::"+t.variants[size_t(variant)].name;
  for(size_t i=0;i<values.size();++i){data->names.push_back(fields[i].name);data->values.push_back(values[i]);}return Value(std::move(data));
}
const std::string &TypedContext::description()const{return impl->layout->description;}
}
}
