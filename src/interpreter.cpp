#include "nex/language.h"
#include "nex/watch_values.h"
#include <algorithm>
#include "nex/operations.h"
#include "nex_value.h"
#include "nex_json.h"
#include "nex_io.h"
#include "llvm/Support/Error.h"
#include <limits>
#include <functional>

namespace nex {
namespace {
using V=nexrt::Value;
struct Returned { V value; };
class Interpreter {
  const Program &p; uint64_t limit; Evaluation result;
  struct Scope {std::map<std::string,V> values;std::map<std::string,std::function<V()>> lazy;};
  std::vector<std::vector<Scope>> frames;
  const std::map<std::string,Type> *watchTypes=nullptr;
  std::unique_ptr<WatchValues> watch;
  std::map<const void*,std::string> sites;
  V full(const V &value){return watch?watch->concrete(value):value;}
  void step(Span s){if(++result.steps>limit)throw Error("E_LIMIT","interpreter step limit exceeded",s);}
  V &local(const std::string &name,Span span={}) {
    for(auto i=frames.back().rbegin();i!=frames.back().rend();++i){if(auto lazy=i->lazy.find(name);lazy!=i->lazy.end()){auto value=lazy->second();i->values[name]=std::move(value);i->lazy.erase(lazy);}if(i->values.contains(name))return i->values.at(name);}
    if(watchTypes&&frames.size()==1&&watchTypes->contains(name)){
      try{return frames.back().back().values.emplace(name,watch->local(name)).first->second;}catch(Error &error){error.span=span;throw;}
    }
    throw Error("E_INTERNAL","checked local is missing");
  }
  V expression(E e) {
    try{step(e->span);auto value=expr(e);if(watch)watch->bounded(value);return value;}
    catch(const nexrt::DataError &err){Error error(err.code,err.what(),e->span);if(sites.contains(e.get())){error.operationSite=sites.at(e.get());error.operationRevision=revision(p);error.operationSource=hash(json(sourceBundle(p),false));}throw error;}
    catch(Error &error){if(error.operationSite.empty()&&sites.contains(e.get())){error.operationSite=sites.at(e.get());error.operationRevision=revision(p);error.operationSource=hash(json(sourceBundle(p),false));}throw;}
  }
  bool pattern(P p,const std::function<V()> &read){
    step(p->span);
    if(p->kind==Pattern::Wildcard)return true;
    if(p->kind==Pattern::Binding){frames.back().back().lazy[p->text]=read;return true;}
    auto value=read();
    if(p->kind==Pattern::Integer||p->kind==Pattern::Boolean)return full(value).scalar==p->number;
    if(p->kind==Pattern::String)return full(value).object->text==p->text;
    if(p->kind==Pattern::List){if((watch?watch->length(value):nexrt::length(value.object))!=int64_t(p->args.size()))return false;}
    else if(p->type.kind==Type::Result){if((watch?watch->isSuccess(value):nexrt::isSuccess(value))!=bool(p->ordinal))return false;}
    else if(this->p.structure(p->type.name).enumeration){if((watch?watch->enumTag(value):value.object->ordinal)!=p->ordinal)return false;}
    for(size_t i=0;i<p->args.size();++i){auto child=[this,p,read,i]{auto value=read();
      if(p->kind==Pattern::List)return watch?watch->index(value,i):nexrt::get(value.object,i);
      if(p->type.kind==Type::Result){if(p->ordinal)return watch?watch->unwrap(value):nexrt::unwrap(value);return watch?watch->error(value,i==0):V(nexrt::string(i==0?value.object->text:value.object->values[0].object->text));}
      if(this->p.structure(p->type.name).enumeration)return watch?watch->enumField(value,p->ordinal,i):nexrt::get(value.object,i);
      return watch?watch->field(value,i):nexrt::get(value.object,i);
    };if(!pattern(p->args[i],child))return false;}return true;
  }
  V matching(E e){
    auto value=expression(e->args[0]);for(auto arm:e->arms){frames.back().emplace_back();
      if(pattern(arm->pattern,[value]{return value;})&&(!arm->guard||expression(e->args[arm->guard]).scalar)){
        V result;if(e->statementMatch)block(arm->body,false);else result=expression(e->args[arm->value]);frames.back().pop_back();return result;
      }frames.back().pop_back();
    }throw Error("E_MATCH","no checked match arm accepted the value",e->span);
  }
  V expr(E e) {
    if(e->kind==Expr::Match)return matching(e);
    if(e->kind==Expr::Integer||e->kind==Expr::Boolean)return V(e->number,e->kind==Expr::Boolean);
    if(e->kind==Expr::String)return V(nexrt::string(e->text));
    if(e->kind==Expr::Name)return local(e->text,e->span);
    if(e->kind==Expr::List){auto d=std::make_shared<nexrt::Data>(nexrt::Data::List);for(auto a:e->args)d->values.push_back(expression(a));return V(d);}
    if(e->kind==Expr::Field){auto base=expression(e->args[0]);return watch?watch->field(base,e->number):nexrt::get(base.object,e->number);}
    if(e->kind==Expr::Index){auto base=expression(e->args[0]);auto index=expression(e->args[1]);return watch?watch->index(base,index.scalar):nexrt::get(base.object,index.scalar);}
    if(e->kind==Expr::Call) {
      std::vector<V> args;for(auto a:e->args)args.push_back(expression(a));
      if(auto variant=p.variant(e->text)){auto d=std::make_shared<nexrt::Data>(nexrt::Data::Enum);d->text=e->text;d->ordinal=variant->ordinal;d->values=std::move(args);for(const auto &field:variant->fields)d->names.push_back(field.name);return V(d);}
      if(p.hasStructure(e->text)){
        auto d=std::make_shared<nexrt::Data>(nexrt::Data::Record);d->text=e->text;d->values=std::move(args);
        for(const auto &field:p.structure(e->text).fields)d->names.push_back(field.name);return V(d);
      }
      if(e->text=="ok")return nexrt::success(args[0]);
      if(e->text=="err"){auto code=full(args[0]);auto message=full(args[1]);return nexrt::failure(code.object->text,message.object->text);}
      if(e->text=="is_ok")return V(watch?watch->isSuccess(args[0]):nexrt::isSuccess(args[0]),true);
      if(e->text=="unwrap")return watch?watch->unwrap(args[0]):nexrt::unwrap(args[0]);
      if(e->text=="error_code")return watch?watch->error(args[0],true):V(nexrt::string(nexrt::isSuccess(args[0])?"":args[0].object->text));
      if(e->text=="error_message")return watch?watch->error(args[0],false):V(nexrt::string(nexrt::isSuccess(args[0])?"":args[0].object->values[0].object->text));
      if(e->text=="encode_json")return V(nexrt::string(nexrt::encodeJSON(full(args[0]))));
      if(e->text=="decode_json")return nexrt::decodeJSON(full(args[0]).object->text,json(wireSchema(p,e->annotation),false));
      if(e->text=="read_env")return nexrt::readEnvironment(args[0].object->text);
      if(e->text=="store_get")return nexrt::storageGet(args[0].object->text);
      if(e->text=="store_put")return nexrt::storagePut(args[0].object->text,args[1].object->text);
      if(e->text=="store_remove")return nexrt::storageRemove(args[0].object->text);
      if(e->text=="store_keys")return nexrt::storageKeys(args[0].object->text);
      if(e->text=="print"){result.output+=nexrt::printable(full(args[0]))+"\n";return {};}
      if(e->text=="assert"){if(!args[0].scalar)throw Error("E_ASSERT","assertion failed",e->span);return {};}
      if(e->text=="len")return V(watch?watch->length(args[0]):nexrt::length(args[0].object));
      if(e->text=="str")return V(nexrt::string(nexrt::printable(full(args[0]))));
      if(e->text=="slice")return V(nexrt::slice(full(args[0]).object,args[1].scalar,args[2].scalar));
      if(e->text=="contains"){auto haystack=full(args[0]);auto needle=full(args[1]);return V(haystack.object->text.find(needle.object->text)!=std::string::npos,true);}
      if(e->text=="push"||e->text=="set"){
        auto base=full(args[0]);auto d=std::make_shared<nexrt::Data>(*base.object);
        if(e->text=="push")d->values.push_back(args[1]);
        else{nexrt::bounds(args[1].scalar,d->values.size());d->values[args[1].scalar]=args[2];}return V(d);
      }
      return call(p.function(e->text),args);
    }
    V left=expression(e->args[0]);int64_t a=left.scalar,out=0;
    auto overflow=[&](){throw Error("E_OVERFLOW","i64 arithmetic overflow",e->span);};
    if(e->kind==Expr::Unary) {
      if(e->text=="!")return V(!a,true);
      if(__builtin_sub_overflow(int64_t(0),a,&out))overflow();return V(out);
    }
    if(e->text=="&&")return V(a&&expression(e->args[1]).scalar,true);
    if(e->text=="||")return V(a||expression(e->args[1]).scalar,true);
    V right=expression(e->args[1]);int64_t b=right.scalar;const auto &op=e->text;
    if(op=="=="||op=="!="){auto x=full(left),y=full(right);auto same=nexrt::equal(x,y);return V(op=="=="?same:!same,true);}
    if(op=="+"&&left.object){
      left=full(left);right=full(right);
      if(left.object->kind==nexrt::Data::String)return V(nexrt::string(left.object->text+right.object->text));
      auto d=std::make_shared<nexrt::Data>(*left.object);d->values.insert(d->values.end(),right.object->values.begin(),right.object->values.end());return V(d);
    }
    if(op=="+"){if(__builtin_add_overflow(a,b,&out))overflow();return V(out);}
    if(op=="-"){if(__builtin_sub_overflow(a,b,&out))overflow();return V(out);}
    if(op=="*"){if(__builtin_mul_overflow(a,b,&out))overflow();return V(out);}
    if(op=="/"||op=="%") {
      if(b==0)throw Error("E_DIV_ZERO","division by zero",e->span);
      if(a==std::numeric_limits<int64_t>::min()&&b==-1){if(op=="/")overflow();return V(0);}
      return V(op=="/"?a/b:a%b);
    }
    if(op=="<")return V(a<b,true);if(op=="<=")return V(a<=b,true);if(op==">")return V(a>b,true);if(op==">=")return V(a>=b,true);
    throw Error("E_INTERNAL","unknown checked operator");
  }
  void block(const std::vector<S> &body,bool scoped=true) {
    if(scoped)frames.back().emplace_back();
    for(auto s:body) {
      try{step(s->span);
      switch(s->kind) {
      case Stmt::Let:case Stmt::Var:{auto v=expression(s->expr);frames.back().back().values[s->name]=std::move(v);break;}
      case Stmt::Assign:{auto v=expression(s->expr);local(s->name)=std::move(v);break;}
      case Stmt::Expression:expression(s->expr);break;
      case Stmt::Return:throw Returned{s->expr?expression(s->expr):V()};
      case Stmt::If:block(expression(s->expr).scalar?s->body:s->alternative);break;
      case Stmt::While:while(expression(s->expr).scalar){step(s->span);block(s->body);}break;
      case Stmt::Match:matching(s->expr);break;
      }
      }catch(Error &error){if(error.operationSite.empty()){error.operationSite=sites.at(s.get());error.operationRevision=revision(p);error.operationSource=hash(json(sourceBundle(p),false));}throw;}
    }
    if(scoped)frames.back().pop_back();
  }
  V call(const Function &f,const std::vector<V> &args) {
    if(frames.size()>=256)throw Error("E_LIMIT","interpreter call depth limit exceeded",f.span);
    frames.emplace_back(1);for(size_t i=0;i<args.size();++i)frames.back().back().values[f.params[i].name]=args[i];
    V value;try{block(f.body,false);}catch(const Returned &r){value=r.value;}
    frames.pop_back();return value;
  }
public:
  Interpreter(const Program &p,uint64_t limit):p(p),limit(limit){for(const auto &f:p.functions)for(const auto &o:operationTree(p,f))if(o.ast)sites[o.ast]=o.site;}
  llvm::json::Value inspect(E expression,const std::map<std::string,Type> &types,const llvm::json::Object &values,const llvm::json::Array *captures,bool demand){
    watchTypes=&types;watch=std::make_unique<WatchValues>(p,types,values,captures);frames.emplace_back(1);V value;
    try{value=full(this->expression(expression));}catch(const WatchDemand &needed){
      if(!demand)throw Error("E_DEBUG_UNAVAILABLE","stopped-frame read was not captured: "+json(needed.request,false));
      return llvm::json::Object{{"ok",true},{"type",typeName(expression->type)},{"request",needed.request},{"steps",int64_t(result.steps)}};
    }
    llvm::json::Value wire=nullptr;
    std::string display="unit";bool truncated=false;
    if(expression->type!=Type::Unit){auto encoded=llvm::json::parse(nexrt::encodeJSON(value));if(!encoded)throw Error("E_INTERNAL",llvm::toString(encoded.takeError()));wire=std::move(*encoded);display=nexrt::representation(value);}
    if(display.size()>4096){size_t end=4096;while(end&&(static_cast<unsigned char>(display[end])&0xc0)==0x80)--end;display.resize(end);display+="…";truncated=true;}
    return llvm::json::Object{{"ok",true},{"type",typeName(expression->type)},{"value",std::move(wire)},{"display",display},{"display_truncated",truncated},{"steps",int64_t(result.steps)},{"read_bindings",watch->readBindings()},{"read_paths",watch->readPaths()}};
  }
  Evaluation run(const std::string &entry) {
    const auto &f=p.function(entry);if(!f.typeParameters.empty()||std::any_of(f.typeArguments.begin(),f.typeArguments.end(),containsParameter))throw Error("E_GENERIC_ENTRY","entry must be concrete",f.span);if(!f.params.empty())throw Error("E_ENTRY","entry must take no arguments",f.span);
    try {
      auto value=call(f,{});
      if(f.result!=Type::Unit){auto parsed=llvm::json::parse(nexrt::representation(value));if(!parsed)throw Error("E_INTERNAL",llvm::toString(parsed.takeError()));result.value=std::move(*parsed);}
    }catch(Error &e){e.output=result.output;throw;}
    return result;
  }
};
}
Evaluation evaluate(const Program &p,const std::string &entry,uint64_t stepLimit){return Interpreter(p,stepLimit).run(entry);}
llvm::json::Value evaluateExpression(const Program &p,E expression,const std::map<std::string,Type> &types,const llvm::json::Object &values,uint64_t limit,const llvm::json::Array *captures,bool demand){
  try{return Interpreter(p,limit).inspect(expression,types,values,captures,demand);}catch(const nexrt::DataError &error){throw Error(error.code,error.what(),expression->span);}
}
}
