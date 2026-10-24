#include "nex/task_lifetime.h"
#include "nex/task_frontend.h"
#include <algorithm>
#include <functional>
#include <limits>

namespace nex {
namespace {
// This is abstract source traversal, never execution of source functions.
// Region -1 is a borrowed/unknown owner; -2 is outside the whole invocation.
constexpr int unknownRegion=-1,outside=-2;
struct Value;
using V=std::shared_ptr<const Value>;
struct Callable {const Function *function;std::vector<V> captures;};
struct Value {
  std::set<int> origins;
  std::vector<V> fields;
  std::map<std::string,Callable> calls;
  bool opaque=false,file=false,shape=false;
  std::optional<int64_t> integer;
  std::optional<bool> boolean;
};
using Env=std::map<std::string,V>;
struct Analysis {
  const Program &p;
  TaskLifetimeReport report;
  uint64_t limit;
  std::map<std::string,const Function*> functions;
  std::vector<int> parents;
  std::set<const Function*> active;
  std::vector<V> *returns=nullptr;
  struct Exhausted {};
  void tick(){if(report.steps>=limit)throw Exhausted{};++report.steps;}
  V plain()const{static V v=std::make_shared<Value>();return v;}
  V unknown(const Type &type){
    auto value=std::make_shared<Value>();
    value->opaque=containsAuthority(type)||type.kind==Type::Function||containsParameter(type);
    value->file=containsNonTaskResource(p,type);
    return value;
  }
  bool containsAuthority(const Type &type)const{
    // Includes callable signatures and phantom generic arguments. Unknown
    // actual authority remains an obligation, not an invented concrete owner.
    return containsTaskAuthority(p,type);
  }
  V aggregate(std::vector<V> fields){
    auto value=std::make_shared<Value>();value->fields=std::move(fields);value->shape=true;
    for(const auto &field:value->fields){
      value->origins.insert(field->origins.begin(),field->origins.end());
      value->opaque|=field->opaque;value->file|=field->file;
    }
    return value;
  }
  V capability(int region,V payload={}){
    auto value=std::make_shared<Value>();value->origins.insert(region);
    if(payload){value->fields.push_back(payload);value->shape=true;}
    return value;
  }
  V join(V a,V b,unsigned depth=0){
    tick();if(a==b)return a;
    auto value=std::make_shared<Value>();value->origins=a->origins;
    value->origins.insert(b->origins.begin(),b->origins.end());
    value->opaque=a->opaque||b->opaque;value->file=a->file||b->file;
    if(a->integer==b->integer)value->integer=a->integer;
    if(a->boolean==b->boolean)value->boolean=a->boolean;
    if(depth>=32){value->opaque=true;++report.widenings;return value;}
    if(a->shape&&b->shape&&a->fields.size()==b->fields.size()){
      value->shape=true;
      for(size_t i=0;i<a->fields.size();++i)value->fields.push_back(join(a->fields[i],b->fields[i],depth+1));
    }
    value->calls=a->calls;
    for(const auto &[name,call]:b->calls){
      auto found=value->calls.find(name);
      if(found==value->calls.end())value->calls.emplace(name,call);
      else for(size_t i=0;i<call.captures.size();++i)
        found->second.captures[i]=join(found->second.captures[i],call.captures[i],depth+1);
    }
    return value;
  }
  V joined(const std::vector<V> &values,const Type &fallback){
    if(values.empty())return unknown(fallback);
    auto result=values.front();for(size_t i=1;i<values.size();++i)result=join(result,values[i]);return result;
  }
  V field(V base,size_t index,const Type &type){
    if(base->shape&&index<base->fields.size())return base->fields[index];
    // Whole-aggregate provenance must not contaminate an unrelated field. Its
    // missing projection is unknown and will be checked at an actual transfer.
    return unknown(type);
  }
  enum Relation {Safe,Invalid,Unknown};
  Relation relation(int origin,int target)const{
    if(origin==unknownRegion)return Unknown;
    if(target==outside)return Invalid;
    if(target==unknownRegion)return origin>0?Invalid:Unknown;
    for(int r=target;r>=0;r=parents.at(size_t(r)))if(origin==r)return Safe;
    // Root0 models a borrowed ambient scope, not a fresh owned child. Its
    // relation to another borrowed scope is unknown. Fresh regions are local
    // descendants, so they cannot be ancestors of a pre-existing target.
    return origin>0?Invalid:Unknown;
  }
  void transfer(V value,const std::set<int> &targets,Span span,const char *operation){
    tick();++report.transfers;
    if(value->file)throw Error("E_TASK_VALUE",std::string(operation)+" cannot transport file authority",span);
    bool deferred=value->opaque;
    for(int origin:value->origins){
      bool allInvalid=!targets.empty(),allSafe=!targets.empty();
      for(int target:targets){auto r=relation(origin,target);allInvalid&=r==Invalid;allSafe&=r==Safe;}
      if(allInvalid)throw Error("E_TASK_LIFETIME",std::string(operation)+" would let a task capability outlive its owning scope",span);
      deferred|=!allSafe;
    }
    if(deferred)++report.dynamic;else ++report.proved;
  }
  std::set<int> owners(V value)const{
    auto result=value->origins;if(value->opaque||result.empty())result.insert(unknownRegion);return result;
  }
  void usable(V value,int current,Span span){transfer(value,{current},span,"task operation");}
  V invoke(V callable,const std::vector<V> &arguments,int current,const Type &result,Span span){
    tick();std::vector<V> values;
    for(const auto &[name,call]:callable->calls){
      (void)name;values.push_back(function(*call.function,arguments,call.captures,current));
    }
    if(callable->opaque||callable->calls.empty()){
      ++report.opaqueCalls;values.push_back(unknown(result));
      // Hidden callable captures still require the mandatory runtime snapshot
      // check even when the output itself is a scalar.
      ++report.dynamic;
    }
    (void)span;return joined(values,result);
  }
  V function(const Function &fn,const std::vector<V> &args,const std::vector<V> &captures,int current){
    tick();
    if(active.contains(&fn)||active.size()>=128||fn.foreign){
      ++report.opaqueCalls;++report.dynamic;return unknown(fn.result);
    }
    ++report.functions;active.insert(&fn);Env env;
    for(size_t i=0;i<fn.params.size();++i)env[fn.params[i].name]=i<args.size()?args[i]:unknown(fn.params[i].type);
    for(size_t i=0;i<fn.captures.size();++i)env[fn.captures[i].name]=i<captures.size()?captures[i]:unknown(fn.captures[i].type);
    std::vector<V> values;auto previous=returns;returns=&values;
    try{block(fn.body,env,current,false);}
    catch(...){returns=previous;active.erase(&fn);throw;}
    returns=previous;active.erase(&fn);return joined(values,fn.result);
  }
  V callable(const Function &fn,std::vector<V> captures){
    auto value=std::make_shared<Value>();
    for(auto capture:captures){
      value->origins.insert(capture->origins.begin(),capture->origins.end());
      value->opaque|=capture->opaque;value->file|=capture->file;
    }
    value->calls.emplace(fn.name,Callable{&fn,std::move(captures)});return value;
  }
  V request(E e,const std::vector<V> &args,int current){
    const auto &name=e->text;
    if(name=="current_task_scope")return capability(current);
    if(name=="task_yield")return plain();
    if(name=="with_tasks"){
      auto region=int(parents.size());parents.push_back(current);++report.regions;
      transfer(args[1],{region},e->span,"scope callback");
      auto value=invoke(args[1],{capability(region)},region,e->type,e->span);
      transfer(value,{current},e->span,"scope return");return value;
    }
    usable(args[0],current,e->span);
    if(name=="task_spawn"){
      auto destination=owners(args[0]);transfer(args[1],destination,e->span,"spawn capture");
      auto target=destination.size()==1?*destination.begin():unknownRegion;
      auto result=invoke(args[1],{},target,*e->type.element,e->span);
      transfer(result,destination,e->span,"task return");
      auto value=std::make_shared<Value>(*capability(target,result));
      value->origins=std::move(destination);return value;
    }
    if(name=="channel_new"){
      auto value=std::make_shared<Value>();value->origins=owners(args[0]);return value;
    }
    if(name=="task_send"){
      transfer(args[1],owners(args[0]),e->span,"channel send");return plain();
    }
    if(name=="task_wait")return field(args[0],0,e->type);
    if(name=="task_recv")return unknown(e->type);
    return plain();
  }
  void bind(P pattern,V value,Env &env){
    tick();if(pattern->kind==Pattern::Binding){env[pattern->text]=value;return;}
    for(size_t i=0;i<pattern->args.size();++i)bind(pattern->args[i],field(value,i,pattern->args[i]->type),env);
  }
  void mergeEnv(Env &env,const Env &other){
    for(auto &[name,value]:env){auto found=other.find(name);if(found!=other.end())value=join(value,found->second);}
  }
  V match(E e,Env &env,int current,bool statements){
    auto subject=expression(e->args[0],env,current);std::vector<V> values;
    Env combined=env;
    for(const auto &arm:e->arms){
      Env branch=env;bind(arm->pattern,subject,branch);
      if(arm->guard){auto guard=expression(e->args[arm->guard],branch,current);if(guard->boolean&&!*guard->boolean)continue;}
      if(statements)block(arm->body,branch,current,false);
      else values.push_back(expression(e->args[arm->value],branch,current));
      visitPattern(arm->pattern,[&](P pattern){if(pattern->kind==Pattern::Binding){
        auto old=env.find(pattern->text);if(old!=env.end())branch[pattern->text]=old->second;else branch.erase(pattern->text);
      }});
      mergeEnv(combined,branch);
    }
    env=std::move(combined);return statements?plain():joined(values,e->type);
  }
  V expression(E e,Env &env,int current){
    tick();if(!e)return plain();
    switch(e->kind){
    case Expr::Name:{auto it=env.find(e->text);return it==env.end()?unknown(e->type):it->second;}
    case Expr::FunctionRef:case Expr::Lambda:{
      std::vector<V> captures;for(auto arg:e->args)captures.push_back(expression(arg,env,current));
      return callable(*functions.at(e->text),std::move(captures));
    }
    case Expr::Integer:{auto value=std::make_shared<Value>();value->integer=e->number;return value;}
    case Expr::Boolean:{auto value=std::make_shared<Value>();value->boolean=e->number!=0;return value;}
    case Expr::Floating:case Expr::String:return plain();
    case Expr::Field:return field(expression(e->args[0],env,current),size_t(e->number),e->type);
    case Expr::Index:{
      auto base=expression(e->args[0],env,current);auto index=expression(e->args[1],env,current);
      if(index->integer&&*index->integer>=0)return field(base,size_t(*index->integer),e->type);
      return base->shape?joined(base->fields,e->type):unknown(e->type);
    }
    case Expr::List:{std::vector<V> fields;for(auto arg:e->args)fields.push_back(expression(arg,env,current));return aggregate(std::move(fields));}
    case Expr::Match:return match(e,env,current,false);
    case Expr::Invoke:{
      auto fn=expression(e->args[0],env,current);std::vector<V> args;
      for(size_t i=1;i<e->args.size();++i)args.push_back(expression(e->args[i],env,current));
      return invoke(fn,args,current,e->type,e->span);
    }
    case Expr::Propagate:{auto value=expression(e->args[0],env,current);return field(value,0,e->type);}
    case Expr::Unary:{auto value=expression(e->args[0],env,current);
      if(e->text=="!"&&value->boolean){auto result=std::make_shared<Value>();result->boolean=!*value->boolean;return result;}return plain();}
    case Expr::Binary:{
      auto left=expression(e->args[0],env,current);
      if((e->text=="&&"&&left->boolean&&!*left->boolean)||(e->text=="||"&&left->boolean&&*left->boolean))return left;
      expression(e->args[1],env,current);return plain();
    }
    case Expr::Call:break;
    }
    std::vector<V> args;for(auto arg:e->args)args.push_back(expression(arg,env,current));
    if(taskBuiltins().contains(e->text))return request(e,args,current);
    auto fn=functions.find(e->text);
    if(fn!=functions.end())return function(*fn->second,args,{},current);
    if(p.hasStructure(e->text)||p.variant(e->text))return aggregate(std::move(args));
    if(e->text=="ok")return aggregate(std::move(args));
    if(e->text=="unwrap")return field(args[0],0,e->type);
    if(e->text=="push"){
      if(args[0]->shape&&args[0]->fields.size()<64){auto fields=args[0]->fields;fields.push_back(args[1]);return aggregate(std::move(fields));}
      auto value=std::make_shared<Value>(*join(args[0],args[1]));value->shape=false;value->fields.clear();value->opaque=true;return value;
    }
    if(e->text=="set"){
      if(args[0]->shape&&args[1]->integer&&*args[1]->integer>=0&&uint64_t(*args[1]->integer)<args[0]->fields.size()){
        auto fields=args[0]->fields;fields[size_t(*args[1]->integer)]=args[2];return aggregate(std::move(fields));
      }
      auto value=std::make_shared<Value>(*join(args[0],args[2]));value->shape=false;value->fields.clear();value->opaque=true;return value;
    }
    // Other checked builtins cannot manufacture known task owners. Resource
    // output, higher-order callbacks and opaque projections remain dynamic.
    return unknown(e->type);
  }
  bool block(const std::vector<S> &body,Env &env,int current,bool lexical=true){
    Env original=env;std::set<std::string> declared;
    bool ended=false;
    for(const auto &s:body){
      tick();if(ended)break;
      switch(s->kind){
      case Stmt::Let:case Stmt::Var:declared.insert(s->name);[[fallthrough]];
      case Stmt::Assign:env[s->name]=expression(s->expr,env,current);break;
      case Stmt::Expression:expression(s->expr,env,current);break;
      case Stmt::Return:returns->push_back(expression(s->expr,env,current));ended=true;break;
      case Stmt::Match:match(s->expr,env,current,true);break;
      case Stmt::If:{
        auto condition=expression(s->expr,env,current);
        if(condition->boolean)ended=block(*condition->boolean?s->body:s->alternative,env,current);
        else{
          auto a=env,b=env;bool ar=block(s->body,a,current),br=block(s->alternative,b,current);
          if(ar&&!br)env=std::move(b);else if(br&&!ar)env=std::move(a);
          else{env=std::move(a);mergeEnv(env,b);}ended=ar&&br;
        }
        break;
      }
      case Stmt::While:{
        auto condition=expression(s->expr,env,current);
        if(condition->boolean&&!*condition->boolean)break;
        // Two abstract iterations expose loop-carried aliases without executing
        // the loop. Remaining iterations are explicitly widened, never declared
        // safe by a finite unrolling or a source-run timeout.
        auto branch=env;block(s->body,branch,current);mergeEnv(env,branch);
        block(s->body,branch,current);mergeEnv(env,branch);
        for(auto &[name,value]:env){
          auto found=branch.find(name);
          if(found!=branch.end()&&found->second!=value){auto widened=std::make_shared<Value>(*value);widened->opaque=true;value=widened;++report.widenings;}
        }
        break;
      }
      }
    }
    if(lexical)for(const auto &name:declared){auto old=original.find(name);if(old!=original.end())env[name]=old->second;else env.erase(name);}
    return ended;
  }
  TaskLifetimeReport run(const std::string &entry){
    if(!p.taskPrototype)throw Error("E_TASK_STATE","lifetime analysis requires a checked private task program");
    for(const auto &fn:p.functions){if(!fn.checked&&!fn.traitSignature)throw Error("E_TASK_STATE","task program must be checked before lifetime analysis",fn.span);functions[fn.name]=&fn;}
    parents.push_back(unknownRegion);
    try{
      if(!entry.empty()){
        const auto &fn=p.function(entry);std::vector<V> args;for(const auto &param:fn.params)args.push_back(unknown(param.type));
        auto value=function(fn,args,{},0);transfer(value,{outside},fn.span,"entry return");
      }else{
        for(const auto &fn:p.functions)if(!fn.closure&&fn.typeParameters.empty()&&!fn.traitSignature&&!fn.foreign){
          std::vector<V> args;for(const auto &param:fn.params)args.push_back(unknown(param.type));function(fn,args,{},0);
        }
      }
    }catch(const Exhausted&){++report.widenings;++report.dynamic;}
    return report;
  }
};
}
TaskLifetimeReport analyzeTaskLifetimes(const Program &program,const std::string &entry,uint64_t analysisLimit){
  if(!analysisLimit||analysisLimit>1048576)throw Error("E_OPTION","task lifetime analysis budget must be1..1048576");
  return Analysis{program,{},analysisLimit,{}, {}, {},nullptr}.run(entry);
}
}
