#include "nex/task_machine.h"
#include "nex/task_frontend.h"
#include "nex/task_reference.h"
#include "nex/language.h"
#include "nex/watch_values.h"
#include <algorithm>
#include "nex/operations.h"
#include "nex_value.h"
#include "nex_parallel_value.h"
#include "nex_json.h"
#include "nex_io.h"
#include "nex_files.h"
#include "nex_foreign.h"
#include "llvm/Support/Error.h"
#include <limits>
#include <functional>

namespace nex {
namespace {
using V=nexrt::Value;
struct Returned { V value; };
class Interpreter {
  nexrt::FileScope files;
  E atomRoot;unsigned outerDepth=0;
  const TaskControlPoll *controlPoll=nullptr;
  const Program &p; uint64_t limit; Evaluation result;
  struct Scope {std::map<std::string,V> values;std::map<std::string,std::function<V()>> lazy;};
  std::vector<std::vector<Scope>> frames;
  std::vector<SourceException> caughtExceptions;
  struct PopScope {
    decltype(frames) &stack;bool active=true;
    ~PopScope(){if(active)stack.back().pop_back();}
  };
  struct PopCaught {
    std::vector<SourceException> &stack;
    ~PopCaught(){stack.pop_back();}
  };
  const std::map<std::string,Type> *watchTypes=nullptr;
  std::unique_ptr<WatchValues> watch;
  std::map<const void*,std::string> sites;
  V full(const V &value){return watch?watch->concrete(value):value;}
  void step(Span s){if(controlPoll&&*controlPoll)(*controlPoll)(s);if(++result.steps>limit)throw Error("E_LIMIT","interpreter step limit exceeded",s);}
  V &local(const std::string &name,Span span={}) {
    for(auto i=frames.back().rbegin();i!=frames.back().rend();++i){if(auto lazy=i->lazy.find(name);lazy!=i->lazy.end()){auto value=lazy->second();i->values[name]=std::move(value);i->lazy.erase(lazy);}if(i->values.contains(name))return i->values.at(name);}
    if(watchTypes&&frames.size()==1&&watchTypes->contains(name)){
      try{return frames.back().back().values.emplace(name,watch->local(name)).first->second;}catch(Error &error){error.span=span;throw;}
    }
    throw Error("E_INTERNAL","checked local is missing");
  }
  V expression(E e) {
    try{if(!atomRoot||e==atomRoot||e->kind!=Expr::Name||!e->text.starts_with("$task_slot_"))step(e->span);auto value=expr(e);if(watch)watch->bounded(value);return value;}
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
    auto value=expression(e->args[0]);for(auto arm:e->arms){frames.back().emplace_back();PopScope scope{frames};
      if(pattern(arm->pattern,[value]{return value;})&&(!arm->guard||expression(e->args[arm->guard]).scalar)){
        V result;if(e->statementMatch)block(arm->body,false);else result=expression(e->args[arm->value]);return result;
      }
    }throw Error("E_MATCH","no checked match arm accepted the value",e->span);
  }
  V expr(E e) {
    if(e->kind==Expr::FunctionRef||e->kind==Expr::Lambda){auto data=std::make_shared<nexrt::Data>(nexrt::Data::Closure);data->text=e->text;const auto &fn=p.function(e->text);if(fn.captures.size()!=e->args.size())throw Error("E_FUNCTION","closure captures differ from the checked target",e->span);for(size_t i=0;i<e->args.size();++i){data->values.push_back(expression(e->args[i]));data->names.push_back(fn.captures[i].name);}return V(std::move(data));}
    if(e->kind==Expr::Invoke){auto target=expression(e->args[0]);std::vector<V> args;for(size_t i=1;i<e->args.size();++i)args.push_back(expression(e->args[i]));if(watch)target=watch->callable(target);return call(p.function(target.object->text),args,&target);}
    if(e->kind==Expr::Propagate){auto value=expression(e->args[0]);
      if(!(watch?watch->isSuccess(value):nexrt::isSuccess(value)))throw Returned{value};
      return watch?watch->unwrap(value):nexrt::unwrap(value);
    }
    if(e->kind==Expr::Match)return matching(e);
    if(e->kind==Expr::Integer||e->kind==Expr::Boolean)return V(e->number,e->kind==Expr::Boolean);
    if(e->kind==Expr::Floating)return V::floating(nexrt::floatValue(e->number));
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
      if(e->text=="parallel_map"){
        auto items=full(args[0]);auto callback=watch?watch->callable(args[1]):args[1];auto workers=full(args[2]).scalar;
        if(workers<1||workers>nexrt::parallelMaximumWorkers)throw Error("E_RANGE","parallel worker count must be in 1..16",e->span);
        if(items.object->values.size()>nexrt::parallelMaximumItems)throw Error("E_LIMIT","parallel input exceeds 65536 items",e->span);
        auto poll=[&]{step(e->span);};nexrt::validateParallelValue(items,poll);nexrt::validateParallelValue(callback,poll);
        auto output=std::make_shared<nexrt::Data>(nexrt::Data::List);output->values.resize(items.object->values.size());std::exception_ptr failure;
        for(size_t i=0;i<items.object->values.size();++i)try{
          poll();auto value=call(p.function(callback.object->text),{items.object->values[i]},&callback);
          nexrt::validateParallelValue(value,poll);output->values[i]=std::move(value);
        }catch(const Error &error){
          if(error.code=="E_LIMIT"||error.code=="E_TIMEOUT"||error.code=="E_CANCELLED"||error.code=="E_MEMORY")throw;
          if(!failure)failure=std::current_exception();
        }catch(const nexrt::DataError &error){
          if(error.code=="E_LIMIT"||error.code=="E_MEMORY")throw;
          if(!failure)failure=std::make_exception_ptr(Error(error.code,error.what(),e->span));
        }
        if(failure)std::rethrow_exception(failure);return V(std::move(output));
      }
      if(e->text=="ok")return nexrt::success(args[0]);
      if(e->text=="bytes")return nexrt::bytesFromIntegers(full(args[0]));
      if(e->text=="utf8_bytes")return V(nexrt::utf8Bytes(full(args[0]).object->text));
      if(e->text=="decode_utf8")return nexrt::decodeUTF8(nexrt::byteBuffer(full(args[0]).object));
      if(e->text=="encode_base64")return V(nexrt::string(nexrt::byteBuffer(full(args[0]).object).base64()));
      if(e->text=="decode_base64")return nexrt::decodeBase64(full(args[0]).object->text);
      if(e->text=="as_f64")return V::floating(nexrt::integerToFloat(full(args[0]).scalar));
      if(e->text=="as_i64"){int64_t value=0;return nexrt::floatToInteger(full(args[0]).floating(),value)?nexrt::success(V(value)):nexrt::failure("E_RANGE","f64 value is outside i64 range");}
      if(e->text=="err"){auto code=full(args[0]);auto message=full(args[1]);return nexrt::failure(code.object->text,message.object->text);}
      if(e->text=="is_ok")return V(watch?watch->isSuccess(args[0]):nexrt::isSuccess(args[0]),true);
      if(e->text=="unwrap")return watch?watch->unwrap(args[0]):nexrt::unwrap(args[0]);
      if(e->text=="error_code")return watch?watch->error(args[0],true):V(nexrt::string(nexrt::isSuccess(args[0])?"":args[0].object->text));
      if(e->text=="error_message")return watch?watch->error(args[0],false):V(nexrt::string(nexrt::isSuccess(args[0])?"":args[0].object->values[0].object->text));
      if(e->text=="encode_json")return V(nexrt::string(nexrt::encodeJSON(full(args[0]))));
      if(e->text=="decode_json")return nexrt::decodeJSON(full(args[0]).object->text,json(wireSchema(p,e->annotation),false));
      if(e->text=="read_env")return nexrt::readEnvironment(args[0].object->text);
      if(supportsExternalResources(p)&&externalResourceBuiltins().contains(e->text)){
        auto value=full(args[0]);auto resource=nexrt::externalResource(value.object);step(e->span);
        return V(e->text=="resource_close"?resource.close():resource.isOpen(),true);
      }
      if(streamFileBuiltins().contains(e->text)){
        auto poll=[&]{step(e->span);};
        if(e->text=="file_close"||e->text=="file_is_open"){
          auto file=nexrt::fileResource(full(args[0]).object);poll();
          return V(e->text=="file_close"?file.close():file.isOpen(),true);
        }
        try{
          if(e->text.starts_with("file_open_")){
            auto mode=e->text=="file_open_read"?nexrt::FileMode::Read:e->text=="file_open_write"?nexrt::FileMode::WriteTruncate:nexrt::FileMode::Append;
            return nexrt::success(V(nexrt::fileValue(nexrt::fileOpen(full(args[0]).object->text,mode,true,poll))));
          }
          auto file=nexrt::fileResource(full(args[0]).object);
          if(e->text=="file_read")return nexrt::success(V(nexrt::bytes(file.read(full(args[1]).scalar,poll))));
          if(e->text=="file_write")return nexrt::success(V(file.write(nexrt::byteBuffer(full(args[1]).object),poll)));
          if(e->text=="file_seek")return nexrt::success(V(file.seek(full(args[1]).scalar,poll)));
          if(e->text=="file_size")return nexrt::success(V(file.size(poll)));
          file.flush(poll);return nexrt::success(V(1,true));
        }catch(const nexrt::DataError &error){return nexrt::failure(error.code,error.what());}
      }
      if(e->text=="file_read_text")return nexrt::fileReadText(args[0].object->text,true,[&]{step(e->span);});
      if(e->text=="file_write_text")return nexrt::fileWriteText(args[0].object->text,args[1].object->text,true,[&]{step(e->span);});
      if(e->text=="file_read_bytes")return nexrt::fileReadBytes(args[0].object->text,true,[&]{step(e->span);});
      if(e->text=="file_write_bytes")return nexrt::fileWriteBytes(args[0].object->text,nexrt::byteBuffer(args[1].object),true,[&]{step(e->span);});
      if(e->text=="store_get")return nexrt::storageGet(args[0].object->text);
      if(e->text=="store_put")return nexrt::storagePut(args[0].object->text,args[1].object->text);
      if(e->text=="store_remove")return nexrt::storageRemove(args[0].object->text);
      if(e->text=="store_keys")return nexrt::storageKeys(args[0].object->text);
      if(e->text=="print"){result.output+=nexrt::printable(full(args[0]))+"\n";return {};}
      if(e->text=="assert"){if(!args[0].scalar)throw Error("E_ASSERT","assertion failed",e->span);return {};}
      if(e->text=="len")return V(watch?watch->length(args[0]):nexrt::length(args[0].object));
      if(e->text=="str")return V(nexrt::string(nexrt::printable(full(args[0]))));
      if(e->text=="slice")return watch?watch->slice(args[0],args[1].scalar,args[2].scalar):V(nexrt::slice(args[0].object,args[1].scalar,args[2].scalar));
      if(e->text=="contains"){auto haystack=full(args[0]);auto needle=full(args[1]);return V(haystack.object->text.find(needle.object->text)!=std::string::npos,true);}
      if(e->text=="push"||e->text=="set"){
        auto base=full(args[0]);
        if(base.object->kind==nexrt::Data::Bytes){const auto &buffer=nexrt::byteBuffer(base.object);return V(nexrt::bytes(e->text=="push"?buffer.append(full(args[1]).scalar):buffer.set(full(args[1]).scalar,full(args[2]).scalar)));}
        auto d=std::make_shared<nexrt::Data>(*base.object);
        if(e->text=="push")d->values.push_back(args[1]);
        else{nexrt::bounds(args[1].scalar,d->values.size());d->values[args[1].scalar]=args[2];}return V(d);
      }
      return call(p.function(e->text),args);
    }
    V left=expression(e->args[0]);int64_t a=left.scalar,out=0;
    auto overflow=[&](){throw Error("E_OVERFLOW","i64 arithmetic overflow",e->span);};
    if(e->kind==Expr::Unary) {
      if(e->text=="!")return V(!a,true);
      if(e->type==Type::F64)return V::floating(nexrt::negateFloat(full(left).floating()));
      if(__builtin_sub_overflow(int64_t(0),a,&out))overflow();return V(out);
    }
    if(e->text=="&&")return V(a&&expression(e->args[1]).scalar,true);
    if(e->text=="||")return V(a||expression(e->args[1]).scalar,true);
    V right=expression(e->args[1]);int64_t b=right.scalar;const auto &op=e->text;
    if(op=="=="||op=="!="){auto same=watch?watch->equal(left,right):nexrt::equal(left,right);return V(op=="=="?same:!same,true);}
    if(e->args[0]->type==Type::F64){
      double a=full(left).floating(),b=full(right).floating();
      if(op=="<"||op=="<="||op==">"||op==">=")return V(nexrt::compareFloat(a,b,op=="<"?2:op=="<="?3:op==">"?4:5),true);
      return V::floating(nexrt::floatArithmetic(a,b,op.front()));
    }
    if(op=="+"&&left.object){
      left=full(left);right=full(right);
      if(left.object->kind==nexrt::Data::String)return V(nexrt::string(left.object->text+right.object->text));
      if(left.object->kind==nexrt::Data::Bytes)return V(nexrt::bytes(nexrt::byteBuffer(left.object).concat(nexrt::byteBuffer(right.object))));
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
    PopScope scope{frames,scoped};
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
      case Stmt::Try:{
        try{block(s->body);}
        catch(const SourceException &error){
          frames.back().emplace_back();PopScope handler{frames};
          frames.back().back().values[s->name]=V(nexrt::string(error.code));
          frames.back().back().values[s->catchMessage]=V(nexrt::string(error.message));
          caughtExceptions.push_back(error);PopCaught caught{caughtExceptions};
          block(s->alternative,false);
        }
        break;
      }
      case Stmt::Throw:{
        if(!s->expr){
          if(caughtExceptions.empty())throw Error("E_RETHROW","bare throw has no current lexical exception",s->span);
          throw caughtExceptions.back();
        }
        auto code=expression(s->expr->args[0]);auto message=expression(s->expr->args[1]);
        throw SourceException(full(code).object->text,full(message).object->text,s->span);
      }
      }
      }catch(Error &error){if(error.operationSite.empty()&&sites.contains(s.get())){error.operationSite=sites.at(s.get());error.operationRevision=revision(p);error.operationSource=hash(json(sourceBundle(p),false));}throw;}
    }
  }
  V call(const Function &f,const std::vector<V> &args,const V *environment=nullptr) {
    if(atomRoot&&(f.effects.contains("fs")||f.effects.contains("db")||f.effects.contains("ffi")))
      throw Error("E_TASK_UNIMPLEMENTED","task atoms cannot execute synchronous resource helpers",f.span);
    if(frames.size()+outerDepth>=256)throw Error("E_LIMIT","interpreter call depth limit exceeded",f.span);
    if(f.foreign)return nexrt::invokeScopedForeign(json(foreignBinding(p,f),false),args,[&]{step(f.span);});
    frames.emplace_back(1);struct PopFrame {decltype(frames)&stack;~PopFrame(){stack.pop_back();}} pop{frames};
    for(size_t i=0;i<args.size();++i)frames.back().back().values[f.params[i].name]=args[i];
    if(f.closure){if(!environment||environment->object->values.size()!=f.captures.size())throw Error("E_FUNCTION","closure environment does not match checked target",f.span);for(size_t i=0;i<f.captures.size();++i){if(watch)frames.back().back().lazy[f.captures[i].name]=[this,value=*environment,i]{return watch->capture(value,i);};else frames.back().back().values[f.captures[i].name]=environment->object->values[i];}}
    V value;try{block(f.body,false);}catch(const Returned &r){value=r.value;}
    return value;
  }
public:
  Interpreter(const Program &p,uint64_t limit,bool atoms=false,const TaskControlPoll *control=nullptr):controlPoll(control),p(p),limit(limit){if(!atoms&&p.sourceLanguage!=SourceLanguage::SourceExceptions025Prototype&&(!p.taskPrototype||isPublicTaskLanguage(p)))for(const auto &f:p.functions)for(const auto &o:operationTree(p,f))if(o.ast)sites[o.ast]=o.site;}
  TaskAtomResult atom(E expression,const std::map<std::string,V> &values,unsigned depth){
    atomRoot=expression;outerDepth=depth;frames.emplace_back(1);frames.back().back().values=values;
    try{auto value=this->expression(expression);return {std::move(value),result.steps,result.output};}
    catch(Error &error){error.output=result.output;throw;}
  }
  llvm::json::Value inspect(E expression,const std::map<std::string,Type> &types,const llvm::json::Object &values,const llvm::json::Array *captures,bool demand,const std::set<std::string> *compiledCallables){
    watchTypes=&types;watch=std::make_unique<WatchValues>(p,types,values,captures,compiledCallables);frames.emplace_back(1);V value;
    llvm::json::Value wire=nullptr;std::string display="unit";bool truncated=false;
    try{value=full(this->expression(expression));if(expression->type!=Type::Unit){wire=watch->wire(expression->type,value);if(json(wire,false).size()>1048576)throw Error("E_DEBUG_LIMIT","expression wire result exceeds 1 MiB");display=nexrt::representation(value);}}catch(const WatchDemand &needed){
      if(!demand)throw Error("E_DEBUG_UNAVAILABLE","stopped-frame read was not captured: "+json(needed.request,false));
      return llvm::json::Object{{"ok",true},{"type",typeName(expression->type)},{"request",needed.request},{"steps",int64_t(result.steps)}};
    }
    if(display.size()>4096){size_t end=4096;while(end&&(static_cast<unsigned char>(display[end])&0xc0)==0x80)--end;display.resize(end);display+="…";truncated=true;}
    return llvm::json::Object{{"ok",true},{"type",typeName(expression->type)},{"value",std::move(wire)},{"display",display},{"display_truncated",truncated},{"steps",int64_t(result.steps)},{"read_bindings",watch->readBindings()},{"read_paths",watch->readPaths()}};
  }
  Evaluation run(const std::string &entry) {
    const auto &f=p.function(entry);if(!f.typeParameters.empty()||std::any_of(f.typeArguments.begin(),f.typeArguments.end(),containsParameter))throw Error("E_GENERIC_ENTRY","entry must be concrete",f.span);if(!f.params.empty())throw Error("E_ENTRY","entry must take no arguments",f.span);
    try {
      auto value=call(f,{});
      if(f.result!=Type::Unit){auto parsed=llvm::json::parse(nexrt::representation(value));if(!parsed)throw Error("E_INTERNAL",llvm::toString(parsed.takeError()));result.value=std::move(*parsed);}
    }catch(Error &e){e.output=result.output;throw;}
    catch(SourceException &e){e.output=result.output;throw;}
    return result;
  }
};
}
TaskAtomResult evaluateTaskAtom(const Program &p,E atom,const std::map<std::string,nexrt::Value> &values,uint64_t limit,unsigned depth,const TaskControlPoll *controlPoll){
  if(!p.taskPrototype)throw Error("E_TASK_STATE","continuation atom execution requires private checked source");
  if(atom&&atom->kind==Expr::Call&&taskFileBuiltin(atom->text))
    throw Error("E_TASK_UNIMPLEMENTED","file operations cannot enter synchronous task atom evaluation",atom->span);
  return Interpreter(p,limit,true,controlPoll).atom(std::move(atom),values,depth);
}
Evaluation evaluate(const Program &p,const std::string &entry,uint64_t stepLimit,const nexrt::TaskExecutionLimits *taskLimits){
  rejectUnloweredTasks(p,"reference execution");
  const auto &function=p.function(entry);
  if(taskLimits&&!nexrt::validTaskExecutionLimits(*taskLimits))throw Error("E_OPTION","invalid task execution limits",function.span);
  const bool taskExecution=isPublicTaskLanguage(p)&&usesTaskEffects(p,entry);
  if(taskLimits&&!taskExecution)
    throw Error("E_OPTION","task execution limits require a task-effect entry",function.span);
  if(taskExecution){
    if(!function.typeParameters.empty()||std::any_of(function.typeArguments.begin(),function.typeArguments.end(),containsParameter))throw Error("E_GENERIC_ENTRY","entry must be concrete",function.span);
    if(!function.params.empty())throw Error("E_ENTRY","entry must take no arguments",function.span);
    auto actual=evaluateTaskReference(p,entry,{},stepLimit,{},taskLimits);Evaluation result;
    result.output=std::move(actual.output);result.steps=actual.steps;
    if(function.result!=Type::Unit){auto parsed=llvm::json::parse(nexrt::representation(actual.value));if(!parsed)throw Error("E_INTERNAL",llvm::toString(parsed.takeError()));result.value=std::move(*parsed);}
    return result;
  }
  return Interpreter(p,stepLimit).run(entry);
}
llvm::json::Value evaluateExpression(const Program &p,E expression,const std::map<std::string,Type> &types,const llvm::json::Object &values,uint64_t limit,const llvm::json::Array *captures,bool demand,const std::set<std::string> *compiledCallables){
  rejectUnloweredTasks(p,"reference inspection");
  try{return Interpreter(p,limit).inspect(expression,types,values,captures,demand,compiledCallables);}catch(const nexrt::DataError &error){throw Error(error.code,error.what(),expression->span);}
}
llvm::json::Value evaluateSourceExceptionWatchPrototype(const Program &p,E expression,const std::map<std::string,Type> &types,const llvm::json::Object &values,uint64_t limit,const llvm::json::Array *captures,bool demand,const std::set<std::string> *compiledCallables){
  if(!sourceExceptionTasksPrototype(p))throw Error("E_LANGUAGE_VERSION","private watch requires the checked task/exception frontend");
  try{return Interpreter(p,limit).inspect(expression,types,values,captures,demand,compiledCallables);}catch(const nexrt::DataError &error){throw Error(error.code,error.what(),expression->span);}
}
}
