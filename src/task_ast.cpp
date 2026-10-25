#include "nex/task_ast.h"
#include "nex/task_frontend.h"
#include <algorithm>

namespace nex {
using AV=nexrt::Value;
struct TaskAstMachine::Impl {
  const Program &program;
  uint64_t limit,used=0,sequence=0;
  size_t pending=0,maximumActions;
  unsigned outerDepth;
  TaskControlPoll controlPoll;
  bool waiting=false,done=false,failed=false;
  Span activeSpan;
  Type response;
  uint64_t ticket=0;
  AV returned;
  std::string output;
  struct MatchState {E expression;AV subject;size_t arm=0;};
  struct Action {
    enum Kind {Statement,Expression,Apply,Bind,Assign,Discard,Return,If,Loop,
               ShortCircuit,StartMatch,TryMatch,MatchGuard,EndMatch,PopScope,Finish} kind;
    E expression;
    S statement;
    std::shared_ptr<MatchState> match;
    Action(Kind kind,E expression={},S statement={},std::shared_ptr<MatchState> match={})
      :kind(kind),expression(std::move(expression)),statement(std::move(statement)),match(std::move(match)){}
  };
  struct Frame {
    const Function *function;
    std::vector<std::map<std::string,AV>> scopes;
    std::vector<Action> actions;
    std::vector<AV> values;
  };
  std::vector<Frame> frames;
  std::map<std::string,const Function*> functions;

  void charge(Span span,uint64_t count=1){
    activeSpan=span;
    if(controlPoll)controlPoll(span);
    if(count>limit-used)throw Error("E_LIMIT","AST continuation step budget exceeded",span);
    used+=count;
  }
  void add(Action action){
    auto &actions=frames.back().actions;
    if(pending>=maximumActions)throw Error("E_LIMIT","AST continuation action limit exceeded",activeSpan);
    actions.push_back(std::move(action));++pending;
  }
  void evaluate(E expression){add({Action::Expression,std::move(expression)});}
  AV pop(){
    auto &values=frames.back().values;
    if(values.empty())throw Error("E_TASK_STATE","AST continuation value stack underflow",activeSpan);
    auto result=std::move(values.back());values.pop_back();return result;
  }
  AV &local(const std::string &name){
    for(auto i=frames.back().scopes.rbegin();i!=frames.back().scopes.rend();++i)
      if(auto found=i->find(name);found!=i->end())return found->second;
    throw Error("E_TASK_STATE","checked AST local is missing: "+name,activeSpan);
  }
  bool kind(const Type &type,const AV &value)const{
    if(type==Type::Unit)return value.tag==AV::Integer&&value.scalar==0;
    if(type==Type::I64)return value.tag==AV::Integer;
    if(type==Type::Bool)return value.tag==AV::Boolean&&(value.scalar==0||value.scalar==1);
    if(type==Type::F64)return value.tag==AV::Floating;
    if(!type.heap()||value.tag!=AV::Object||!value.object)return false;
    const auto actual=value.object->kind;
    switch(type.kind){
    case Type::Str:return actual==nexrt::Data::String;
    case Type::List:return actual==nexrt::Data::List;
    case Type::Record:return isExternalResource(program,type)?actual==nexrt::Data::External:actual==nexrt::Data::Record||actual==nexrt::Data::Enum;
    case Type::Result:
      if(value.object->values.size()!=1)return false;
      if(actual==nexrt::Data::Failure)return kind(Type::Str,value.object->values[0]);
      return actual==nexrt::Data::Success&&kind(*type.element,value.object->values[0]);
    case Type::Function:return actual==nexrt::Data::Closure;
    case Type::Bytes:return actual==nexrt::Data::Bytes;
    case Type::TaskScope:return actual==nexrt::Data::TaskScope;
    case Type::Task:return actual==nexrt::Data::Task;
    case Type::Channel:return actual==nexrt::Data::Channel;
    default:return false;
    }
  }
  void block(const std::vector<S> &body,bool scoped){
    if(scoped){frames.back().scopes.emplace_back();add({Action::PopScope});}
    for(auto i=body.rbegin();i!=body.rend();++i)add({Action::Statement,{},*i});
  }
  void push(const Function &function,const std::vector<AV> &args,const AV *closure=nullptr){
    if(supportsTaskFileReads(program)&&function.effects.contains("fs")&&!function.effects.contains("task"))
      throw Error("E_EFFECT","AST task calls require an explicitly resumable task/fs helper",function.span);
    const bool files=supportsTaskFileReads(program)&&function.realm=="server"&&
      function.effects.contains("task")&&function.effects.contains("fs");
    const bool foreign=supportsTaskForeignCalls(program)&&function.realm=="server"&&function.effects.contains("task")&&function.effects.contains("ffi");
    for(const auto &effect:function.effects)if(effect!="task"&&effect!="io"&&!(files&&effect=="fs")&&!(foreign&&effect=="ffi"))
      throw Error("E_TASK_UNIMPLEMENTED","AST continuation has no host resource bridge",function.span);
    auto unsupported=[&](const Type &type){return supportsTaskForeignCalls(program)?containsFile(program,type):containsNonTaskResource(program,type);};
    if(function.foreign||unsupported(Type::function({},function.result))||
       std::any_of(function.params.begin(),function.params.end(),[&](const auto &p){return unsupported(p.type);})||
       std::any_of(function.captures.begin(),function.captures.end(),[&](const auto &p){return unsupported(p.type);}))
      throw Error("E_TASK_UNIMPLEMENTED","AST continuation cannot carry file or foreign authority",function.span);
    if(!function.typeParameters.empty()||containsParameter(function.result))
      throw Error("E_GENERIC_ENTRY","AST continuation requires concrete functions",function.span);
    if(outerDepth+frames.size()>=256)throw Error("E_LIMIT","AST continuation call depth exceeds256",function.span);
    if(args.size()!=function.params.size())throw Error("E_TASK_STATE","AST call argument count differs",function.span);
    Frame frame{&function,{{}},{},{}};
    for(size_t i=0;i<args.size();++i){
      if(!kind(function.params[i].type,args[i]))throw Error("E_TASK_TYPE","AST call argument kind differs",function.span);
      frame.scopes.back().emplace(function.params[i].name,args[i]);
    }
    if(function.closure){
      if(!closure||closure->tag!=AV::Object||!closure->object||closure->object->kind!=nexrt::Data::Closure||
         closure->object->text!=function.name||closure->object->values.size()!=function.captures.size())
        throw Error("E_FUNCTION","AST closure environment differs",function.span);
      for(size_t i=0;i<function.captures.size();++i){
        if(!kind(function.captures[i].type,closure->object->values[i]))
          throw Error("E_TASK_TYPE","AST closure capture kind differs",function.span);
        frame.scopes.back().emplace(function.captures[i].name,closure->object->values[i]);
      }
    }
    frames.push_back(std::move(frame));add({Action::Finish});block(function.body,false);
  }
  void leave(AV value){
    if(!kind(frames.back().function->result,value))throw Error("E_TASK_TYPE","AST return kind differs",activeSpan);
    pending-=frames.back().actions.size();frames.pop_back();
    if(frames.empty()){returned=std::move(value);done=true;}
    else frames.back().values.push_back(std::move(value));
  }
  bool pattern(P p,const AV &value){
    charge(p->span);
    if(p->kind==Pattern::Wildcard)return true;
    if(p->kind==Pattern::Binding){frames.back().scopes.back()[p->text]=value;return true;}
    if(p->kind==Pattern::Integer||p->kind==Pattern::Boolean)return value.scalar==p->number;
    if(p->kind==Pattern::String)return value.object->text==p->text;
    if(p->kind==Pattern::List){if(nexrt::length(value.object)!=int64_t(p->args.size()))return false;}
    else if(p->type.kind==Type::Result){if(nexrt::isSuccess(value)!=bool(p->ordinal))return false;}
    else if(program.structure(p->type.name).enumeration&&value.object->ordinal!=p->ordinal)return false;
    for(size_t i=0;i<p->args.size();++i){
      AV child;
      if(p->type.kind==Type::Result){
        if(p->ordinal)child=nexrt::unwrap(value);
        else child=i==0?AV(nexrt::string(value.object->text)):value.object->values[0];
      }else child=nexrt::get(value.object,i);
      if(!pattern(p->args[i],child))return false;
    }
    return true;
  }
  void arm(const std::shared_ptr<MatchState> &state){
    const auto &expression=state->expression;const auto &selected=expression->arms.at(state->arm);
    add({Action::EndMatch,{},{},state});
    if(expression->statementMatch)block(selected->body,false);
    else evaluate(expression->args.at(selected->value));
  }
  TaskTransition advance(){
    if(done||failed||waiting)throw Error("E_TASK_STATE","AST continuation is completed, failed or awaiting a response");
    try{
      while(!done){
        auto &frame=frames.back();
        if(frame.actions.empty())throw Error("E_TASK_STATE","AST continuation has no pending action",activeSpan);
        auto action=std::move(frame.actions.back());frame.actions.pop_back();--pending;
        auto e=action.expression;auto s=action.statement;
        charge(e?e->span:s?s->span:frame.function->span);
        switch(action.kind){
        case Action::Statement:
          switch(s->kind){
          case Stmt::Let:case Stmt::Var:add({Action::Bind,{},s});evaluate(s->expr);break;
          case Stmt::Assign:add({Action::Assign,{},s});evaluate(s->expr);break;
          case Stmt::Expression:case Stmt::Match:add({Action::Discard});evaluate(s->expr);break;
          case Stmt::Return:if(s->expr){add({Action::Return});evaluate(s->expr);}else leave({});break;
          case Stmt::If:add({Action::If,{},s});evaluate(s->expr);break;
          case Stmt::While:add({Action::Loop,{},s});evaluate(s->expr);break;
          }
          break;
        case Action::Expression:
          if(e->kind==Expr::Name){frame.values.push_back(local(e->text));break;}
          if(e->kind==Expr::Match){add({Action::StartMatch,e});evaluate(e->args.at(0));break;}
          if(e->kind==Expr::Binary&&(e->text=="&&"||e->text=="||")){
            add({Action::ShortCircuit,e});evaluate(e->args.at(0));break;
          }
          add({Action::Apply,e});
          for(auto i=e->args.rbegin();i!=e->args.rend();++i)evaluate(*i);
          break;
        case Action::Apply:{
          std::vector<AV> args(e->args.size());
          for(size_t i=args.size();i-->0;)args[i]=pop();
          if(e->kind==Expr::Propagate){
            if(!nexrt::isSuccess(args[0]))leave(std::move(args[0]));
            else frame.values.push_back(nexrt::unwrap(args[0]));
            break;
          }
          if(e->kind==Expr::Invoke){
            auto closure=std::move(args[0]);args.erase(args.begin());
            if(closure.tag!=AV::Object||!closure.object||closure.object->kind!=nexrt::Data::Closure)
              throw Error("E_FUNCTION","AST call requires a checked closure",e->span);
            const auto &target=program.function(closure.object->text);
            std::vector<Type> parameters;for(const auto &parameter:target.params)parameters.push_back(parameter.type);
            if(Type::function(std::move(parameters),target.result,target.realm,target.effects)!=e->args[0]->type)
              throw Error("E_FUNCTION","AST callable target differs from its checked signature",e->span);
            push(target,args,&closure);break;
          }
          const bool read=e->kind==Expr::Call&&(taskFileReadOperation(e->text)||(supportsTaskFileWrites(program)&&taskFileWriteOperation(e->text)));
          if(read&&(!supportsTaskFileReads(program)||frame.function->realm!="server"||
             !frame.function->effects.contains("task")||!frame.function->effects.contains("fs")))
            throw Error("E_TASK_UNIMPLEMENTED","AST file reads require a language020 server task/fs function",e->span);
          if(e->kind==Expr::Call&&(taskBuiltins().contains(e->text)||read)){
            waiting=true;ticket=++sequence;response=e->type;
            TaskTransition next;next.kind=TaskTransition::Waiting;next.operation=e->text;
            next.arguments=std::move(args);next.result=e->type;next.span=e->span;
            next.ticket=ticket;next.callDepth=frames.size();next.pc=used;return next;
          }
          if(e->kind==Expr::Call&&functions.contains(e->text)){
            const auto &target=*functions.at(e->text);
            if(supportsTaskForeignCalls(program)&&target.foreign){
              if(frame.function->realm!="server"||!frame.function->effects.contains("task")||!frame.function->effects.contains("ffi"))
                throw Error("E_EFFECT","AST foreign task request requires a declared server task/ffi caller",e->span);
              waiting=true;ticket=++sequence;response=e->type;
              TaskTransition next;next.kind=TaskTransition::Waiting;next.operation=target.name;
              next.arguments=std::move(args);next.result=e->type;next.span=e->span;
              next.ticket=ticket;next.callDepth=frames.size();next.pc=used;return next;
            }
            push(*functions.at(e->text),args);break;
          }
          if(e->kind==Expr::Call&&taskFileBuiltin(e->text))
            throw Error("E_TASK_UNIMPLEMENTED","AST tasks support only whole-file text/bytes reads",e->span);
          // Only ordinary, already-evaluated atoms enter the shared primitives.
          // All AST control, user calls and suspension remain above this boundary.
          auto atom=std::make_shared<Expr>(*e);atom->args.clear();
          std::map<std::string,AV> inputs;
          for(size_t i=0;i<args.size();++i){
            auto name="$task_slot_"+std::to_string(i);auto child=std::make_shared<Expr>();
            child->kind=Expr::Name;child->text=name;child->type=e->args[i]->type;
            atom->args.push_back(child);inputs.emplace(std::move(name),std::move(args[i]));
          }
          auto result=evaluateTaskAtom(program,atom,inputs,limit-used,outerDepth+unsigned(frames.size()-1),&controlPoll);
          charge(e->span,result.steps);output+=result.output;frame.values.push_back(std::move(result.value));break;
        }
        case Action::Bind:{auto value=pop();frame.scopes.back()[s->name]=std::move(value);break;}
        case Action::Assign:{auto value=pop();local(s->name)=std::move(value);break;}
        case Action::Discard:pop();break;
        case Action::Return:leave(pop());break;
        case Action::If:{auto condition=pop();block(condition.scalar?s->body:s->alternative,true);break;}
        case Action::Loop:
          if(pop().scalar){add({Action::Statement,{},s});block(s->body,true);}break;
        case Action::ShortCircuit:{
          auto left=pop();
          if((e->text=="&&"&&!left.scalar)||(e->text=="||"&&left.scalar))frame.values.push_back(std::move(left));
          else evaluate(e->args.at(1));
          break;
        }
        case Action::StartMatch:{
          auto state=std::make_shared<MatchState>(MatchState{e,pop(),0});
          add({Action::TryMatch,{},{},std::move(state)});break;
        }
        case Action::TryMatch:{
          auto state=action.match;const auto &expression=state->expression;
          if(state->arm>=expression->arms.size())throw Error("E_MATCH","no checked match arm accepted the value",expression->span);
          const auto &selected=expression->arms[state->arm];frame.scopes.emplace_back();
          if(!pattern(selected->pattern,state->subject)){
            frame.scopes.pop_back();++state->arm;add({Action::TryMatch,{},{},state});
          }else if(selected->guard){
            add({Action::MatchGuard,{},{},state});evaluate(expression->args.at(selected->guard));
          }else arm(state);
          break;
        }
        case Action::MatchGuard:{
          auto accepted=pop();auto state=action.match;
          if(accepted.scalar)arm(state);
          else{frame.scopes.pop_back();++state->arm;add({Action::TryMatch,{},{},state});}
          break;
        }
        case Action::EndMatch:
          frame.scopes.pop_back();
          if(action.match->expression->statementMatch)frame.values.emplace_back();
          break;
        case Action::PopScope:frame.scopes.pop_back();break;
        case Action::Finish:leave({});break;
        }
      }
      TaskTransition next;next.kind=TaskTransition::Done;next.value=returned;next.pc=used;return next;
    }catch(Error &error){
      output+=error.output;error.output=output;failed=true;frames.clear();pending=0;throw;
    }catch(const nexrt::DataError &error){
      failed=true;frames.clear();pending=0;Error located(error.code,error.what(),activeSpan);located.output=output;throw located;
    }catch(...){failed=true;frames.clear();pending=0;throw;}
  }
  Impl(const Program &program,const std::string &entry,const std::vector<AV> &args,uint64_t limit,
       const AV &closure,unsigned outerDepth,size_t maximumActions,TaskControlPoll controlPoll):program(program),limit(limit),maximumActions(maximumActions),outerDepth(outerDepth),controlPoll(std::move(controlPoll)){
    if(!program.taskPrototype)throw Error("E_TASK_STATE","AST continuation requires private checked source");
    for(const auto &function:program.functions)functions.emplace(function.name,&function);
    if(maximumActions>262144)throw Error("E_LIMIT","AST action allowance exceeds262144");
    push(program.function(entry),args,closure.tag==AV::Object?&closure:nullptr);
  }
};
TaskAstMachine::TaskAstMachine(const Program &p,const std::string &entry,const std::vector<AV> &args,uint64_t limit,
    AV closure,unsigned outerDepth,size_t maximumActions,TaskControlPoll controlPoll)
  :impl(std::make_unique<Impl>(p,entry,args,limit,closure,outerDepth,maximumActions,std::move(controlPoll))){}
TaskAstMachine::~TaskAstMachine()=default;
TaskTransition TaskAstMachine::advance(){return impl->advance();}
void TaskAstMachine::restrictBudget(uint64_t remaining){impl->limit=impl->used+std::min(remaining,impl->limit-impl->used);}
size_t TaskAstMachine::pendingActions()const{return impl->pending;}
void TaskAstMachine::resume(uint64_t ticket,AV value){
  if(!impl->waiting||ticket!=impl->ticket)throw Error("E_TASK_STATE","AST continuation response ticket differs");
  if(!impl->kind(impl->response,value))throw Error("E_TASK_TYPE","AST continuation response kind differs",impl->activeSpan);
  impl->frames.back().values.push_back(std::move(value));impl->waiting=false;
}
bool TaskAstMachine::finished()const{return impl->done;}
uint64_t TaskAstMachine::steps()const{return impl->used;}
const std::string &TaskAstMachine::output()const{return impl->output;}
}
