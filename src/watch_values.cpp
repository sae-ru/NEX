#include "nex/watch_values.h"
#include "nex_json.h"
#include <charconv>

namespace nex {
namespace {
using JSON=llvm::json::Value;using Object=llvm::json::Object;using Array=llvm::json::Array;
std::string key(const std::string &binding,const Array &path,const std::string &kind){return binding+":"+json(Array(path),false)+":"+kind;}
}
WatchValues::WatchValues(const Program &p,const std::map<std::string,Type> &t,const Object &v,const Array *c):program(p),types(t),values(v),captures(c){
  if(c)for(const auto &value:*c){const auto &o=*value.getAsObject();reads.emplace(key(o.getString("binding")->str(),*o.getArray("path"),o.getString("kind")->str()),&o);}
}
const WatchValues::Ref *WatchValues::reference(const V &v) const {auto i=refs.find(v.object.get());return i==refs.end()?nullptr:&i->second;}
const JSON &WatchValues::read(const Ref &r,const std::string &kind){
  auto k=key(r.binding,r.path,kind);bindings.insert(r.binding);paths.emplace(k,Object{{"binding",r.binding},{"path",Array(r.path)},{"kind",kind}});
  auto i=reads.find(k);if(i==reads.end())throw WatchDemand{Object{{"binding",r.binding},{"path",Array(r.path)},{"kind",kind},{"type",typeName(r.type)},{"wire_schema",wireSchema(program,r.type)}}};
  if(auto unavailable=i->second->getString("unavailable"))throw Error("E_DEBUG_UNAVAILABLE","stopped-frame read unavailable: "+k+": "+unavailable->str());
  return *i->second->get("value");
}
WatchValues::V WatchValues::decode(const Ref &r,const JSON &wire){
  auto k=key(r.binding,r.path,"value");auto i=decoded.find(k);if(i!=decoded.end())return i->second;
  auto result=nexrt::decodeJSON(json(wire,false),json(wireSchema(program,r.type),false));
  if(!nexrt::isSuccess(result))throw Error("E_DEBUG_VALUE","invalid typed wire value for stopped-frame read: "+k);
  auto value=nexrt::unwrap(result);bounded(value);decoded.emplace(k,value);return value;
}
WatchValues::V WatchValues::proxy(std::string binding,Type type,Array path){
  if(refs.size()>=10000||path.size()>56)throw Error("E_DEBUG_LIMIT","stopped-frame reference budget exceeded");
  Ref r{nullptr,std::move(binding),std::move(type),std::move(path)};
  if(!r.type.heap())return decode(r,read(r,"value"));
  auto captured=reads.find(key(r.binding,r.path,"value"));
  if(captured!=reads.end()&&captured->second->get("value"))return decode(r,read(r,"value"));
  auto kind=r.type==Type::Str?nexrt::Data::String:r.type.kind==Type::List?nexrt::Data::List:r.type.kind==Type::Record?nexrt::Data::Record:nexrt::Data::Success;
  auto data=std::make_shared<nexrt::Data>(kind);r.owner=data;refs.emplace(data.get(),std::move(r));return V(data);
}
WatchValues::V WatchValues::local(const std::string &name){
  if(auto input=values.get(name)){bindings.insert(name);paths.emplace(key(name,{},"value"),Object{{"binding",name},{"path",Array{}},{"kind","value"}});Ref r{nullptr,name,types.at(name),{}};return decode(r,*input);}
  if(captures)return proxy(name,types.at(name),{});
  throw Error("E_DEBUG_UNAVAILABLE","stopped-frame value is unavailable: "+name);
}
const Object &WatchValues::shape(const Ref &r){
  auto o=read(r,"shape").getAsObject();if(!o||o->size()!=1)throw Error("E_DEBUG_VALUE","invalid stopped-frame shape");
  if(r.type.kind==Type::List){auto s=o->getString("length");int64_t length=0;if(!s||s->empty()||(s->size()>1&&s->front()=='0')||s->front()<'0'||s->front()>'9')throw Error("E_DEBUG_VALUE","invalid stopped-list length");auto parsed=std::from_chars(s->begin(),s->end(),length);if(parsed.ec!=std::errc()||parsed.ptr!=s->end()||length<0)throw Error("E_DEBUG_VALUE","invalid stopped-list length");}
  else if(r.type.kind==Type::Record&&program.structure(r.type.name).enumeration){auto name=o->getString("case");bool found=false;if(name)for(const auto &variant:program.structure(r.type.name).variants)if(variant.name==*name)found=true;if(!found)throw Error("E_DEBUG_VALUE","invalid stopped-enum variant");}
  else if(r.type.kind==Type::Record){if(o->getString("record")!=r.type.name)throw Error("E_DEBUG_VALUE","stopped-record shape differs from its nominal type");}
  else if(r.type.kind==Type::Result){if(!o->getBoolean("ok"))throw Error("E_DEBUG_VALUE","invalid stopped-result shape");}
  else throw Error("E_DEBUG_VALUE","type does not support a stopped-frame shape");return *o;
}
WatchValues::V WatchValues::child(const Ref &r,JSON segment,Type type){auto path=Array(r.path);path.push_back(std::move(segment));return proxy(r.binding,std::move(type),std::move(path));}
WatchValues::V WatchValues::field(const V &base,int64_t index){
  auto r=reference(base);if(!r)return nexrt::get(base.object,index);shape(*r);const auto &f=program.structure(r->type.name).fields.at(index);return child(*r,f.name,f.type);
}
int64_t WatchValues::length(const V &base){
  auto r=reference(base);if(!r)return nexrt::length(base.object);
  if(r->type.kind!=Type::List)return nexrt::length(concrete(base).object);
  int64_t size=0;auto s=shape(*r).getString("length");std::from_chars(s->begin(),s->end(),size);return size;
}
WatchValues::V WatchValues::index(const V &base,int64_t index){
  auto r=reference(base);if(!r)return nexrt::get(base.object,index);
  if(r->type.kind!=Type::List)return nexrt::get(concrete(base).object,index);
  nexrt::bounds(index,length(base));return child(*r,index,*r->type.element);
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
void WatchValues::bounded(const V &value,unsigned depth){
  if(++visits>100000||depth>64)throw Error("E_DEBUG_LIMIT","expression exceeded its value visit/depth budget");
  if(value.object&&!reference(value)){bytes+=value.object->text.size();if(bytes>8*1024*1024)throw Error("E_DEBUG_LIMIT","expression exceeded its cumulative text budget");for(const auto &child:value.object->values)bounded(child,depth+1);}
}
WatchValues::V WatchValues::concrete(const V &value,unsigned depth){
  if(depth>64)throw Error("E_DEBUG_LIMIT","expression materialization exceeded its depth budget");
  if(auto r=reference(value))return decode(*r,read(*r,"value"));
  if(!value.object)return value;
  // Computed containers may carry references through pure calls/constructors.
  // Rebuild them without mutating shared interpreter values or proxy objects.
  auto data=std::make_shared<nexrt::Data>(*value.object);
  for(auto &item:data->values)item=concrete(item,depth+1);return V(data);
}
Array WatchValues::readBindings()const{Array a;for(const auto &s:bindings)a.push_back(s);return a;}
Array WatchValues::readPaths()const{Array a;for(const auto &[_,path]:paths)a.push_back(Object(path));return a;}
}
