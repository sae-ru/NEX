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
  bool opaque=false,file=false,resource=false,shape=false;
  std::optional<int64_t> integer;
  std::optional<bool> boolean,resultSuccess;
};
// Immutable binding identity is separate from its current value and visible
// spelling. Hidden outer bindings remain present until lexical scope exit.
struct Env {std::map<std::string,uint64_t> names;std::map<uint64_t,V> values;};
struct Outcome {V value;bool raises=false;};
struct ReturnState {V value;Env state;};
struct HandlerInput {Env baseline;std::optional<Env> exceptional;};
struct Analysis {
  const Program &p;
  TaskLifetimeReport report;
  uint64_t limit;
  std::map<std::string,const Function*> functions;
  std::vector<int> parents;
  std::set<const Function*> active;
  std::vector<ReturnState> *returns=nullptr;
  uint64_t nextBinding=0;
  std::vector<HandlerInput*> handlers;
  bool escaping=false;
  struct Exhausted {};
  void declare(Env &env,const std::string &name,V value){auto id=++nextBinding;env.names[name]=id;env.values[id]=std::move(value);}
  void assign(Env &env,const std::string &name,V value){auto it=env.names.find(name);if(it==env.names.end())throw Error("E_INTERNAL","lifetime assignment lost its checked binding");env.values[it->second]=std::move(value);}
  V lookup(const Env &env,const std::string &name,const Type &fallback){auto it=env.names.find(name);return it==env.names.end()?unknown(fallback):env.values.at(it->second);}
  Env project(const Env &state,const Env &baseline){
    Env result=baseline;for(auto &[id,value]:result.values){auto found=state.values.find(id);if(found!=state.values.end())value=found->second;}return result;
  }
  void sourceEdge(const Env &env){
    if(!supportsSourceExceptionTasks(p))return;
    ++report.exceptionalEdges;
    if(handlers.empty()){escaping=true;return;}
    auto &handler=*handlers.back();auto state=project(env,handler.baseline);
    if(!handler.exceptional)handler.exceptional=std::move(state);
    else{mergeEnv(*handler.exceptional,state);++report.exceptionalJoins;}
  }
  void tick(){if(report.steps>=limit)throw Exhausted{};++report.steps;}
  V plain()const{static V v=std::make_shared<Value>();return v;}
  V unknown(const Type &type){
    auto value=std::make_shared<Value>();
    value->opaque=containsAuthority(type)||type.kind==Type::Function||containsParameter(type);
    value->file=!supportsTaskFileStreams(p)&&(supportsTaskForeignCalls(p)?containsFile(p,type):containsNonTaskResource(p,type));
    value->resource=(supportsTaskForeignCalls(p)&&containsExternalResource(p,type))||(supportsTaskFileStreams(p)&&containsFile(p,type));
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
      if(!field)continue;
      value->origins.insert(field->origins.begin(),field->origins.end());
      value->opaque|=field->opaque;value->file|=field->file;value->resource|=field->resource;
    }
    return value;
  }
  V capability(int region,V payload={}){
    auto value=std::make_shared<Value>();value->origins.insert(region);
    if(payload){value->fields.push_back(payload);value->shape=true;}
    return value;
  }
  V join(V a,V b,unsigned depth=0){
    tick();if(!a)return b;if(!b)return a;if(a==b)return a;
    auto value=std::make_shared<Value>();value->origins=a->origins;
    value->origins.insert(b->origins.begin(),b->origins.end());
    value->opaque=a->opaque||b->opaque;value->file=a->file||b->file;value->resource=a->resource||b->resource;
    if(a->integer==b->integer)value->integer=a->integer;
    if(a->boolean==b->boolean)value->boolean=a->boolean;
    if(a->resultSuccess==b->resultSuccess)value->resultSuccess=a->resultSuccess;
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
    // Resource factories carry genuine runtime owners, not inferred task
    // capability regions. Promotion/borrowing remains a runtime obligation.
    bool deferred=value->opaque||value->resource;
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
  Outcome invoke(V callable,const std::vector<V> &arguments,int current,const Type &result,Span span,bool unknownThrows=false){
    tick();std::vector<V> values;bool raises=false;
    for(const auto &[name,call]:callable->calls){
      (void)name;auto out=function(*call.function,arguments,call.captures,current);if(out.value)values.push_back(out.value);raises|=out.raises;
    }
    if(callable->opaque||callable->calls.empty()){
      ++report.opaqueCalls;values.push_back(unknown(result));raises|=unknownThrows;++report.dynamic;
    }
    (void)span;return {values.empty()?V{}:joined(values,result),raises};
  }
  Outcome function(const Function &fn,const std::vector<V> &args,const std::vector<V> &captures,int current){
    tick();
    if(active.contains(&fn)||active.size()>=128||fn.foreign){
      ++report.opaqueCalls;++report.dynamic;return {unknown(fn.result),fn.effects.contains("throw")};
    }
    ++report.functions;active.insert(&fn);Env env;
    for(size_t i=0;i<fn.params.size();++i)declare(env,fn.params[i].name,i<args.size()?args[i]:unknown(fn.params[i].type));
    for(size_t i=0;i<fn.captures.size();++i)declare(env,fn.captures[i].name,i<captures.size()?captures[i]:unknown(fn.captures[i].type));
    std::vector<ReturnState> states;auto previous=returns;returns=&states;
    auto previousHandlers=std::move(handlers);handlers.clear();auto previousEscaping=escaping;escaping=false;
    bool ended=false,raised=false;
    try{ended=block(fn.body,env,current,false);raised=escaping;}
    catch(...){returns=previous;handlers=std::move(previousHandlers);escaping=previousEscaping;active.erase(&fn);throw;}
    returns=previous;handlers=std::move(previousHandlers);escaping=previousEscaping;active.erase(&fn);
    std::vector<V> values;for(const auto &state:states)values.push_back(state.value);
    if(!ended)values.push_back(fn.result==Type::Unit?plain():unknown(fn.result));
    return {values.empty()?V{}:joined(values,fn.result),raised};
  }
  V callable(const Function &fn,std::vector<V> captures){
    auto value=std::make_shared<Value>();
    for(auto capture:captures){
      value->origins.insert(capture->origins.begin(),capture->origins.end());
      value->opaque|=capture->opaque;value->file|=capture->file;value->resource|=capture->resource;
    }
    value->calls.emplace(fn.name,Callable{&fn,std::move(captures)});return value;
  }
  V request(E e,const std::vector<V> &args,int current,const Env &envForRequest){
    const auto &name=e->text;
    if(name=="current_task_scope")return capability(current);
    if(name=="task_yield")return plain();
    if(name=="with_tasks"){
      auto region=int(parents.size());parents.push_back(current);++report.regions;
      transfer(args[1],{region},e->span,"scope callback");
      sourceEdge(envForRequest); // Wait/close has a latent source error by contract.
      auto out=invoke(args[1],{capability(region)},region,e->type,e->span);
      if(out.value)transfer(out.value,{current},e->span,"scope return");return out.value;
    }
    usable(args[0],current,e->span);
    if(name=="task_spawn"){
      auto destination=owners(args[0]);transfer(args[1],destination,e->span,"spawn capture");
      auto target=destination.size()==1?*destination.begin():unknownRegion;
      auto out=invoke(args[1],{},target,*e->type.element,e->span,true);
      if(out.value)transfer(out.value,destination,e->span,"task return");
      auto value=std::make_shared<Value>(*capability(target));
      value->shape=true;value->fields.push_back(out.value);
      value->origins=std::move(destination);return value;
    }
    if(name=="channel_new"){
      auto value=std::make_shared<Value>();value->origins=owners(args[0]);return value;
    }
    if(name=="task_send"){
      transfer(args[1],owners(args[0]),e->span,"channel send");return plain();
    }
    if(name=="task_wait"){sourceEdge(envForRequest);return field(args[0],0,e->type);}
    if(name=="task_recv")return unknown(e->type);
    return plain();
  }
  void bind(P pattern,V value,Env &env){
    tick();if(pattern->kind==Pattern::Binding){declare(env,pattern->text,value);return;}
    for(size_t i=0;i<pattern->args.size();++i)bind(pattern->args[i],field(value,i,pattern->args[i]->type),env);
  }
  void mergeEnv(Env &env,const Env &other){
    for(auto &[id,value]:env.values){auto found=other.values.find(id);if(found!=other.values.end())value=join(value,found->second);}
  }
  struct MatchOutcome {V value;bool normal=false;};
  MatchOutcome match(E e,Env &env,int current,bool statements){
    auto subject=expression(e->args[0],env,current);if(!subject)return {};
    std::vector<V> values;std::optional<Env> combined;
    for(const auto &arm:e->arms){
      Env branch=env;bind(arm->pattern,subject,branch);
      if(arm->guard){auto guard=expression(e->args[arm->guard],branch,current);if(!guard||(guard->boolean&&!*guard->boolean))continue;}
      bool normal;
      if(statements)normal=!block(arm->body,branch,current,false);
      else{auto value=expression(e->args[arm->value],branch,current);normal=bool(value);if(value)values.push_back(value);}
      if(normal){auto state=project(branch,env);if(!combined)combined=std::move(state);else mergeEnv(*combined,state);}
    }
    if(combined)env=std::move(*combined);
    return {statements?plain():(values.empty()?V{}:joined(values,e->type)),combined.has_value()};
  }
  V expression(E e,Env &env,int current){
    tick();if(!e)return plain();
    switch(e->kind){
    case Expr::Name:return lookup(env,e->text,e->type);
    case Expr::FunctionRef:case Expr::Lambda:{
      std::vector<V> captures;for(auto arg:e->args){auto value=expression(arg,env,current);if(!value)return {};captures.push_back(value);}
      return callable(*functions.at(e->text),std::move(captures));
    }
    case Expr::Integer:{auto value=std::make_shared<Value>();value->integer=e->number;return value;}
    case Expr::Boolean:{auto value=std::make_shared<Value>();value->boolean=e->number!=0;return value;}
    case Expr::Floating:case Expr::String:return plain();
    case Expr::Field:{auto base=expression(e->args[0],env,current);return base?field(base,size_t(e->number),e->type):V{};}
    case Expr::Index:{
      auto base=expression(e->args[0],env,current);if(!base)return {};auto index=expression(e->args[1],env,current);if(!index)return {};
      if(index->integer&&*index->integer>=0)return field(base,size_t(*index->integer),e->type);
      return base->shape?joined(base->fields,e->type):unknown(e->type);
    }
    case Expr::List:{std::vector<V> fields;for(auto arg:e->args){auto value=expression(arg,env,current);if(!value)return {};fields.push_back(value);}return aggregate(std::move(fields));}
    case Expr::Match:return match(e,env,current,false).value;
    case Expr::Invoke:{
      auto fn=expression(e->args[0],env,current);if(!fn)return {};std::vector<V> args;
      for(size_t i=1;i<e->args.size();++i){auto value=expression(e->args[i],env,current);if(!value)return {};args.push_back(value);}
      auto out=invoke(fn,args,current,e->type,e->span,e->args[0]->type.effects.contains("throw"));if(out.raises)sourceEdge(env);return out.value;
    }
    case Expr::Propagate:{auto value=expression(e->args[0],env,current);if(!value)return {};if(value->resultSuccess!=true)returns->push_back({plain(),env});return value->resultSuccess==false?V{}:field(value,0,e->type);}
    case Expr::Unary:{auto value=expression(e->args[0],env,current);if(!value)return {};
      if(e->text=="!"&&value->boolean){auto result=std::make_shared<Value>();result->boolean=!*value->boolean;return result;}return plain();}
    case Expr::Binary:{
      auto left=expression(e->args[0],env,current);if(!left)return {};
      if((e->text=="&&"&&left->boolean&&!*left->boolean)||(e->text=="||"&&left->boolean&&*left->boolean))return left;
      auto right=expression(e->args[1],env,current);
      if(!right&&!(e->text=="&&"||e->text=="||"))return {};
      if(!right&&left->boolean)return {};
      return plain();
    }
    case Expr::Call:break;
    }
    std::vector<V> args;for(auto arg:e->args){auto value=expression(arg,env,current);if(!value)return {};args.push_back(value);}
    if(taskBuiltins().contains(e->text))return request(e,args,current,env);
    auto fn=functions.find(e->text);
    if(fn!=functions.end()){auto out=function(*fn->second,args,{},current);if(out.raises)sourceEdge(env);return out.value;}
    if(p.hasStructure(e->text)||p.variant(e->text))return aggregate(std::move(args));
    if(e->text=="ok"||e->text=="err"){auto value=std::make_shared<Value>(*aggregate(std::move(args)));value->resultSuccess=e->text=="ok";return value;}
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
    Env original=env;std::vector<std::pair<std::string,uint64_t>> declared;
    bool ended=false;
    for(const auto &s:body){
      tick();if(ended)break;
      switch(s->kind){
      case Stmt::Finally:{
        auto baseline=env,normal=env;HandlerInput handler{baseline,{}};
        std::vector<ReturnState> pendingReturns;auto outerReturns=returns;returns=&pendingReturns;handlers.push_back(&handler);
        bool bodyEnds;
        try{bodyEnds=block(s->body,normal,current);}catch(...){handlers.pop_back();returns=outerReturns;throw;}
        handlers.pop_back();returns=outerReturns;std::optional<Env> continuation;
        if(!bodyEnds){
          auto state=project(normal,baseline);
          if(!block(s->alternative,state,current))continuation=std::move(state);
        }
        for(const auto &pending:pendingReturns){
          auto state=project(pending.state,baseline);
          if(!block(s->alternative,state,current))returns->push_back({pending.value,std::move(state)});
        }
        if(handler.exceptional){
          auto state=project(*handler.exceptional,baseline);
          if(!block(s->alternative,state,current))sourceEdge(state);
        }
        if(continuation)env=std::move(*continuation);else ended=true;
        break;
      }
      case Stmt::Try:{
        if(!supportsSourceExceptionTasks(p))throw Error("E_EXCEPTION_BACKEND","task exception lifetimes require the dedicated private task parser",s->span);
        ++report.handlers;HandlerInput handler{env,{}};auto normal=env;handlers.push_back(&handler);bool bodyEnds;
        try{bodyEnds=block(s->body,normal,current);}catch(...){handlers.pop_back();throw;}handlers.pop_back();
        std::optional<Env> continuation;if(!bodyEnds)continuation=normal;
        if(handler.exceptional){
          auto caught=*handler.exceptional;declare(caught,s->name,plain());declare(caught,s->catchMessage,plain());
          bool guardReady=!s->expr||bool(expression(s->expr,caught,current));
          if(guardReady){
            if(!totalSourceHandler(s))sourceEdge(caught);
            bool catchEnds=block(s->alternative,caught,current);
            if(!catchEnds){auto state=project(caught,env);if(!continuation)continuation=std::move(state);else mergeEnv(*continuation,state);}
          }
        }
        if(continuation)env=std::move(*continuation);else ended=true;
        break;
      }
      case Stmt::Throw:{
        if(!supportsSourceExceptionTasks(p))throw Error("E_EXCEPTION_BACKEND","task exception lifetimes require the dedicated private task parser",s->span);
        bool ready=true;if(s->expr)for(auto arg:s->expr->args)if(!expression(arg,env,current)){ready=false;break;}
        if(ready)sourceEdge(env);ended=true;break;
      }
      case Stmt::Let:case Stmt::Var:{auto value=expression(s->expr,env,current);if(!value){ended=true;break;}declare(env,s->name,value);declared.push_back({s->name,env.names.at(s->name)});break;}
      case Stmt::Assign:{auto value=expression(s->expr,env,current);if(value)assign(env,s->name,value);else ended=true;break;}
      case Stmt::Expression:if(!expression(s->expr,env,current))ended=true;break;
      case Stmt::Return:{auto value=expression(s->expr,env,current);if(value)returns->push_back({value,env});ended=true;break;}
      case Stmt::Match:ended=!match(s->expr,env,current,true).normal;break;
      case Stmt::If:{
        auto condition=expression(s->expr,env,current);if(!condition){ended=true;break;}
        if(condition->boolean)ended=block(*condition->boolean?s->body:s->alternative,env,current);
        else{
          auto a=env,b=env;bool ar=block(s->body,a,current),br=block(s->alternative,b,current);
          if(ar&&!br)env=std::move(b);else if(br&&!ar)env=std::move(a);
          else if(!ar&&!br){env=std::move(a);mergeEnv(env,b);}ended=ar&&br;
        }break;
      }
      case Stmt::While:{
        auto condition=expression(s->expr,env,current);if(!condition){ended=true;break;}
        if(condition->boolean&&!*condition->boolean)break;
        auto branch=env;bool exits=block(s->body,branch,current);
        if(exits){ended=condition->boolean.value_or(false);break;}
        mergeEnv(env,branch);auto next=env;
        bool secondEnds=block(s->body,next,current);if(!secondEnds)mergeEnv(env,next);
        // Widen loop-carried state, then traverse it again so exceptional
        // edges also see the widened fixed-point approximation, not two samples.
        for(auto &[id,value]:env.values){auto found=next.values.find(id);if(found!=next.values.end()&&found->second!=value){auto widened=std::make_shared<Value>(*value);widened->opaque=true;value=widened;++report.widenings;}}
        auto widened=env;if(!block(s->body,widened,current))mergeEnv(env,widened);
        break;
      }
      }
    }
    if(lexical)for(auto i=declared.rbegin();i!=declared.rend();++i){auto old=original.names.find(i->first);if(old!=original.names.end())env.names[i->first]=old->second;else env.names.erase(i->first);env.values.erase(i->second);}
    return ended;
  }
  TaskLifetimeReport run(const std::string &entry){
    if(!p.taskPrototype)throw Error("E_TASK_STATE","lifetime analysis requires a checked private task program");
    for(const auto &fn:p.functions){if(!fn.checked&&!fn.traitSignature)throw Error("E_TASK_STATE","task program must be checked before lifetime analysis",fn.span);functions[fn.name]=&fn;}
    parents.push_back(unknownRegion);
    try{
      if(!entry.empty()){
        const auto &fn=p.function(entry);std::vector<V> args;for(const auto &param:fn.params)args.push_back(unknown(param.type));
        auto out=function(fn,args,{},0);if(out.value)transfer(out.value,{outside},fn.span,"entry return");
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
  return Analysis{program,{},analysisLimit,{}, {}, {},nullptr,0,{},false}.run(entry);
}
}
