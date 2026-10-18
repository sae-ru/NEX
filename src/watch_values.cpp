#include "nex/watch_values.h"
#include "nex_json.h"
#include <charconv>
#include <algorithm>

namespace nex {
namespace {
using JSON=llvm::json::Value;using Object=llvm::json::Object;using Array=llvm::json::Array;
std::string key(const std::string &binding,const Array &path,const std::string &kind){return binding+":"+json(Array(path),false)+":"+kind;}
}
WatchValues::WatchValues(const Program &p,const std::map<std::string,Type> &t,const Object &v,const Array *c,const std::set<std::string> *compiled):program(p),types(t),values(v),captures(c),codec(p,compiled){
  if(c)for(const auto &value:*c){const auto &o=*value.getAsObject();reads.emplace(key(o.getString("binding")->str(),*o.getArray("path"),o.getString("kind")->str()),&o);}
}
const WatchValues::Ref *WatchValues::reference(const V &v) const {auto i=refs.find(v.object.get());return i==refs.end()?nullptr:&i->second;}
const JSON &WatchValues::read(const Ref &r,const std::string &kind){
  auto k=key(r.binding,r.path,kind);bindings.insert(r.binding);paths.emplace(k,Object{{"binding",r.binding},{"path",Array(r.path)},{"kind",kind}});
  auto i=reads.find(k);if(i==reads.end())throw WatchDemand{Object{{"binding",r.binding},{"path",Array(r.path)},{"kind",kind},{"type",typeName(r.type)},{"wire_schema",debugValueSchema(program,r.type,codec.compiledTargets())}}};
  if(auto unavailable=i->second->getString("unavailable"))throw Error("E_DEBUG_UNAVAILABLE","stopped-frame read unavailable: "+k+": "+unavailable->str());
  auto &value=*i->second->get("value");codec.observe(r.identity,r.relative,kind,value);return value;
}
WatchValues::V WatchValues::decode(const Ref &r,const JSON &wire){
  auto k=key(r.binding,r.path,"value");auto i=decoded.find(k);if(i!=decoded.end())return i->second;
  auto value=codec.decode(r.type,wire,r.identity,r.relative);bounded(value);decoded.emplace(k,value);return value;
}
WatchValues::V WatchValues::proxy(std::string binding,Type type,Array path,std::string identity,Array relative,std::vector<std::string> lineage){
  if(refs.size()>=10000||path.size()>56)throw Error("E_DEBUG_LIMIT","stopped-frame reference budget exceeded");
  Ref r{nullptr,std::move(binding),std::move(type),std::move(path),std::move(identity),std::move(relative),std::move(lineage)};
  if(!r.type.heap())return decode(r,read(r,"value"));
  auto captured=reads.find(key(r.binding,r.path,"value"));
  if(captured!=reads.end()&&captured->second->get("value"))return decode(r,read(r,"value"));
  auto kind=r.type==Type::Str?nexrt::Data::String:r.type.kind==Type::List?nexrt::Data::List:r.type.kind==Type::Record?nexrt::Data::Record:r.type.kind==Type::Function?nexrt::Data::Closure:nexrt::Data::Success;
  auto data=r.type==Type::Bytes?nexrt::bytes({}):std::make_shared<nexrt::Data>(kind);r.owner=data;refs.emplace(data.get(),std::move(r));return V(data);
}
WatchValues::V WatchValues::local(const std::string &name){
  if(auto input=values.get(name)){bindings.insert(name);paths.emplace(key(name,{},"value"),Object{{"binding",name},{"path",Array{}},{"kind","value"}});Ref r{nullptr,name,types.at(name),{},"",{}, {}};return decode(r,*input);}
  if(captures)return proxy(name,types.at(name),{});
  throw Error("E_DEBUG_UNAVAILABLE","stopped-frame value is unavailable: "+name);
}
const Object &WatchValues::shape(const Ref &r){
  auto o=read(r,"shape").getAsObject();if(!o)throw Error("E_DEBUG_VALUE","invalid stopped-frame shape");
  if(r.type.kind==Type::Function){codec.callableShape(r.type,Object(*o));return *o;}
  if(o->size()!=1)throw Error("E_DEBUG_VALUE","invalid stopped-frame shape");
  if(r.type.kind==Type::List||r.type==Type::Bytes){auto s=o->getString("length");int64_t length=0;if(!s||s->empty()||(s->size()>1&&s->front()=='0')||s->front()<'0'||s->front()>'9')throw Error("E_DEBUG_VALUE","invalid stopped-collection length");auto parsed=std::from_chars(s->begin(),s->end(),length);if(parsed.ec!=std::errc()||parsed.ptr!=s->end()||length<0)throw Error("E_DEBUG_VALUE","invalid stopped-collection length");}
  else if(r.type.kind==Type::Record&&program.structure(r.type.name).enumeration){auto name=o->getString("case");bool found=false;if(name)for(const auto &variant:program.structure(r.type.name).variants)if(variant.name==*name)found=true;if(!found)throw Error("E_DEBUG_VALUE","invalid stopped-enum variant");}
  else if(r.type.kind==Type::Record){if(o->getString("record")!=r.type.name)throw Error("E_DEBUG_VALUE","stopped-record shape differs from its nominal type");}
  else if(r.type.kind==Type::Result){if(!o->getBoolean("ok"))throw Error("E_DEBUG_VALUE","invalid stopped-result shape");}
  else throw Error("E_DEBUG_VALUE","type does not support a stopped-frame shape");return *o;
}
WatchValues::V WatchValues::child(const Ref &r,JSON segment,Type type){auto path=Array(r.path),relative=Array(r.relative);path.push_back(segment);if(!r.identity.empty())relative.push_back(std::move(segment));return proxy(r.binding,std::move(type),std::move(path),r.identity,std::move(relative),r.lineage);}
WatchValues::V WatchValues::field(const V &base,int64_t index){
  auto r=reference(base);if(!r)return nexrt::get(base.object,index);shape(*r);const auto &f=program.structure(r->type.name).fields.at(index);return child(*r,f.name,f.type);
}
int64_t WatchValues::length(const V &base){
  auto r=reference(base);if(!r)return nexrt::length(base.object);
  if(r->type.kind!=Type::List&&r->type!=Type::Bytes)return nexrt::length(concrete(base).object);
  int64_t size=0;auto s=shape(*r).getString("length");std::from_chars(s->begin(),s->end(),size);return size;
}
WatchValues::V WatchValues::index(const V &base,int64_t index){
  auto r=reference(base);if(!r)return nexrt::get(base.object,index);
  if(r->type.kind!=Type::List&&r->type!=Type::Bytes)return nexrt::get(concrete(base).object,index);
  nexrt::bounds(index,length(base));auto value=child(*r,index,r->type==Type::Bytes?Type(Type::I64):*r->type.element);
  if(r->type==Type::Bytes)codec.observeByte(r->identity,r->relative,index,value.scalar);return value;
}
WatchValues::V WatchValues::slice(const V &base,int64_t start,int64_t count){
  auto r=reference(base);if(!r||r->type!=Type::Bytes)return V(nexrt::slice(concrete(base).object,start,count));
  auto size=length(base);if(start<0||count<0||start>size||count>size-start)throw nexrt::DataError("E_BOUNDS","slice is outside byte buffer bounds");
  if(count>255)throw Error("E_DEBUG_LIMIT","stopped-byte slice exceeds its selected-octet budget; capture a bounded whole value or select a smaller slice");
  std::vector<int64_t> values;values.reserve(size_t(count));for(int64_t i=0;i<count;++i)values.push_back(index(base,start+i).scalar);
  return V(nexrt::bytes(nexrt::ByteBuffer::fromIntegers(values)));
}
bool WatchValues::isSuccess(const V &base){auto r=reference(base);return r?*shape(*r).getBoolean("ok"):nexrt::isSuccess(base);}
WatchValues::V WatchValues::error(const V &base,bool code){
  auto r=reference(base);if(!r)return V(nexrt::string(nexrt::isSuccess(base)?"":code?base.object->text:base.object->values[0].object->text));
  if(isSuccess(base))return V(nexrt::string(""));return child(*r,code?"code":"message",Type::Str);
}
WatchValues::V WatchValues::unwrap(const V &base){
  auto r=reference(base);if(!r)return nexrt::unwrap(base);
  if(!isSuccess(base)){auto code=concrete(error(base,true));auto message=concrete(error(base,false));throw nexrt::DataError("E_RESULT",code.object->text+": "+message.object->text);}
  return child(*r,"ok",*r->type.element);
}
int64_t WatchValues::enumTag(const V &base){auto r=reference(base);if(!r)return base.object->ordinal;auto name=shape(*r).getString("case");for(const auto &variant:program.structure(r->type.name).variants)if(variant.name==*name)return variant.ordinal;throw Error("E_DEBUG_VALUE","invalid enum tag");}
WatchValues::V WatchValues::enumField(const V &base,int64_t tag,size_t index){auto r=reference(base);if(!r)return nexrt::get(base.object,index);if(enumTag(base)!=tag)throw Error("E_DEBUG_VALUE","enum payload path has another variant");const auto &variant=program.structure(r->type.name).variants.at(tag);const auto &field=variant.fields.at(index);return child(*r,variant.name+"::"+field.name,field.type);}
WatchValues::V WatchValues::callable(const V &value){
  auto r=reference(value);if(!r)return value;auto cached=callableValues.find(value.object.get());if(cached!=callableValues.end())return cached->second;
  auto [name,identity]=codec.callableShape(r->type,Object(shape(*r)));const auto &fn=checkedDebugCallable(program,name,r->type,codec.compiledTargets());auto data=std::make_shared<nexrt::Data>(nexrt::Data::Closure);data->text=name;
  if(std::find(r->lineage.begin(),r->lineage.end(),identity)!=r->lineage.end())throw Error("E_DEBUG_VALUE","stopped callable captures contain an identity cycle");
  for(const auto &capture:fn.captures)data->names.push_back(capture.name);data->values.resize(fn.captures.size());
  V result(data);codec.identify(result,identity);callableOrigins.emplace(data.get(),*r);callableValues.emplace(value.object.get(),result);return result;
}
WatchValues::V WatchValues::capture(const V &value,size_t index){
  auto origin=callableOrigins.find(value.object.get());if(origin==callableOrigins.end())return value.object->values.at(index);
  const auto &r=origin->second;auto identity=codec.identity(value);const auto &fn=program.function(value.object->text);const auto &capture=fn.captures.at(index);auto path=Array(r.path);path.push_back(capture.name);auto lineage=r.lineage;lineage.push_back(identity);
  return proxy(r.binding,capture.type,std::move(path),identity,Array{capture.name},std::move(lineage));
}
bool WatchValues::equal(const V &a,const V &b){
  auto left=concrete(a),right=concrete(b);std::function<bool(const V&,const V&,unsigned)> compare=[&](const V &left,const V &right,unsigned depth){
    if(depth>64||++visits>100000)throw Error("E_DEBUG_LIMIT","expression equality exceeded its value budget");
    if(left.tag!=right.tag)return false;if(left.tag!=V::Object)return left.scalar==right.scalar;
    if(left.object->kind==nexrt::Data::Bytes||right.object->kind==nexrt::Data::Bytes)return nexrt::equal(left,right);
    if(left.object->kind==nexrt::Data::Closure||right.object->kind==nexrt::Data::Closure){if(left.object->kind!=right.object->kind)return false;auto l=callable(left),r=callable(right);auto li=codec.identity(l),ri=codec.identity(r);return !li.empty()&&!ri.empty()?li==ri:l.object==r.object;}
    const auto &l=*left.object,&r=*right.object;if(l.kind!=r.kind||l.ordinal!=r.ordinal||l.text!=r.text||l.names!=r.names||l.values.size()!=r.values.size())return false;for(size_t i=0;i<l.values.size();++i)if(!compare(l.values[i],r.values[i],depth+1))return false;return true;
  };return compare(left,right,0);
}
void WatchValues::bounded(const V &value,unsigned depth){
  if(++visits>100000||depth>64)throw Error("E_DEBUG_LIMIT","expression exceeded its value visit/depth budget");
  if(value.object&&!reference(value)){bytes+=value.object->kind==nexrt::Data::Bytes?uint64_t(nexrt::byteBuffer(value.object).length()):value.object->text.size();if(bytes>8*1024*1024)throw Error("E_DEBUG_LIMIT","expression exceeded its cumulative text/byte budget");for(const auto &child:value.object->values)bounded(child,depth+1);}
}
WatchValues::V WatchValues::concrete(const V &value,unsigned depth){
  if(depth>64)throw Error("E_DEBUG_LIMIT","expression materialization exceeded its depth budget");
  if(auto r=reference(value)){if(r->type.kind==Type::Function)return callable(value);return decode(*r,read(*r,"value"));}
  if(!value.object)return value;
  if(value.object->kind==nexrt::Data::Closure||value.object->kind==nexrt::Data::Bytes)return value;
  // Computed containers may carry references through pure calls/constructors.
  // Rebuild them without mutating shared interpreter values or proxy objects.
  auto data=std::make_shared<nexrt::Data>(*value.object);
  for(auto &item:data->values)item=concrete(item,depth+1);return V(data);
}
Array WatchValues::readBindings()const{Array a;for(const auto &s:bindings)a.push_back(s);return a;}
Array WatchValues::readPaths()const{Array a;for(const auto &[_,path]:paths)a.push_back(Object(path));return a;}
}
