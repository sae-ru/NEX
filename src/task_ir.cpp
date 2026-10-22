#include "nex/task_ir.h"
#include "nex/task_frontend.h"
#include <algorithm>
#include <functional>

namespace nex {
std::string taskSlotName(TaskSlotId slot){return "$task_slot_"+std::to_string(slot);}
namespace {
class Lowering {
  const Program &program;
  TaskFunctionIR result;
  std::vector<std::map<std::string,TaskSlotId>> scopes;
  size_t emit(TaskInstruction instruction){
    if(result.code.size()>=262144)throw Error("E_TASK_LIMIT","continuation exceeds262144 instructions",instruction.span);
    result.code.push_back(std::move(instruction));return result.code.size()-1;
  }
  TaskSlotId slot(Type type,Span span,std::string name={},bool temporary=true){
    if(type==Type::Unit)return noTaskSlot;
    if(result.slots.size()>=65536)throw Error("E_TASK_LIMIT","continuation exceeds65536 retained slots",span);
    auto id=TaskSlotId(result.slots.size());result.slots.push_back({std::move(type),std::move(name),span,temporary});return id;
  }
  TaskSlotId lookup(const std::string &name,Span span){
    for(auto i=scopes.rbegin();i!=scopes.rend();++i)if(i->contains(name))return i->at(name);
    throw Error("E_INTERNAL","continuation local is missing: "+name,span);
  }
  E reference(TaskSlotId id,Span span){
    if(id==noTaskSlot)throw Error("E_INTERNAL","unit continuation operand",span);
    auto value=std::make_shared<Expr>();value->kind=Expr::Name;value->text=taskSlotName(id);value->type=result.slots.at(id).type;value->span=span;return value;
  }
  void drop(TaskSlotId id,Span span){if(id!=noTaskSlot){TaskInstruction op;op.kind=TaskInstruction::Drop;op.span=span;op.inputs={id};emit(std::move(op));}}
  void copy(TaskSlotId to,TaskSlotId from,Span span){
    if(to==noTaskSlot)return;
    TaskInstruction op;op.kind=TaskInstruction::Copy;op.span=span;op.output=to;op.inputs={from};emit(std::move(op));
  }
  size_t jump(Span span,size_t target=0){TaskInstruction op;op.kind=TaskInstruction::Jump;op.span=span;op.yes=target;return emit(std::move(op));}
  size_t branch(TaskSlotId condition,Span span){TaskInstruction op;op.kind=TaskInstruction::Branch;op.span=span;op.inputs={condition};return emit(std::move(op));}
  void constant(TaskSlotId output,bool value,Span span){
    TaskInstruction op;op.kind=TaskInstruction::Eval;op.span=span;op.output=output;op.atom=std::make_shared<Expr>();op.atom->kind=Expr::Boolean;op.atom->number=value;op.atom->type=Type::Bool;op.atom->span=span;emit(std::move(op));
  }
  void leave(Span span){for(const auto &[name,id]:scopes.back())drop(id,span);scopes.pop_back();}
  void finish(TaskSlotId value,Span span,const void *source=nullptr,bool propagated=false){
    TaskInstruction op;op.kind=TaskInstruction::Return;op.span=span;op.source=source;op.propagatedError=propagated;if(value!=noTaskSlot)op.inputs={value};emit(std::move(op));
  }
  P pattern(P original,std::vector<TaskSlotId> &bindings){
    auto value=std::make_shared<nex::Pattern>(*original);value->args.clear();
    if(value->kind==nex::Pattern::Binding){auto id=slot(value->type,value->span,value->text,false);scopes.back()[value->text]=id;bindings.push_back(id);value->text=taskSlotName(id);value->binding=id;}
    for(auto child:original->args)value->args.push_back(pattern(child,bindings));return value;
  }
  std::pair<TaskSlotId,bool> matching(E expression){
    auto input=expr(expression->args[0]);auto output=slot(expression->type,expression->span);std::vector<size_t> ends;
    bool allReturn=expression->statementMatch;
    for(const auto &arm:expression->arms){
      scopes.emplace_back();TaskInstruction test;test.kind=TaskInstruction::Pattern;test.span=arm->span;test.source=arm->pattern.get();test.output=slot(Type::Bool,arm->span);test.inputs={input};test.pattern=pattern(arm->pattern,test.bindings);
      auto condition=test.output;auto bindings=test.bindings;emit(std::move(test));auto matched=branch(condition,arm->span);result.code[matched].yes=result.code.size();drop(condition,arm->span);
      size_t guarded=0;TaskSlotId guard=noTaskSlot;
      if(arm->guard){guard=expr(expression->args[arm->guard]);guarded=branch(guard,arm->span);result.code[guarded].yes=result.code.size();drop(guard,arm->span);}
      bool returned=false;
      if(expression->statementMatch)returned=block(arm->body,false);
      else{auto value=expr(expression->args[arm->value]);copy(output,value,arm->span);drop(value,arm->span);}
      allReturn&=returned;
      if(!returned){for(const auto &[name,id]:scopes.back())drop(id,arm->span);ends.push_back(jump(arm->span));}
      if(arm->guard){result.code[guarded].no=result.code.size();drop(guard,arm->span);for(const auto &[name,id]:scopes.back())drop(id,arm->span);}
      auto failed=jump(arm->span);result.code[matched].no=result.code.size();drop(condition,arm->span);for(auto id:bindings)drop(id,arm->span);
      result.code[failed].yes=result.code.size();scopes.pop_back();
    }
    TaskInstruction failed;failed.kind=TaskInstruction::Fail;failed.operation="E_MATCH";failed.span=expression->span;emit(std::move(failed));
    for(auto end:ends)result.code[end].yes=result.code.size();
    if(!allReturn)drop(input,expression->span);return {output,allReturn};
  }
  TaskSlotId expr(E original){
    if(original->kind==Expr::Match)return matching(original).first;
    auto output=slot(original->type,original->span);
    if(original->kind==Expr::Binary&&(original->text=="&&"||original->text=="||")){
      auto left=expr(original->args[0]);auto choice=branch(left,original->span);
      auto evaluate=result.code.size();drop(left,original->span);auto right=expr(original->args[1]);copy(output,right,original->span);drop(right,original->span);auto end=jump(original->span);
      auto skip=result.code.size();drop(left,original->span);constant(output,original->text=="||",original->span);
      result.code[choice].yes=original->text=="&&"?evaluate:skip;result.code[choice].no=original->text=="&&"?skip:evaluate;result.code[end].yes=result.code.size();return output;
    }
    if(original->kind==Expr::Propagate){
      auto input=expr(original->args[0]);auto success=slot(Type::Bool,original->span);TaskInstruction test;test.kind=TaskInstruction::Eval;test.span=original->span;test.output=success;
      test.atom=std::make_shared<Expr>();test.atom->kind=Expr::Call;test.atom->text="is_ok";test.atom->type=Type::Bool;test.atom->args={reference(input,original->span)};test.atom->span=original->span;test.inputs={input};emit(std::move(test));
      auto choice=branch(success,original->span);result.code[choice].no=result.code.size();drop(success,original->span);finish(input,original->span,original.get(),true);
      result.code[choice].yes=result.code.size();drop(success,original->span);TaskInstruction unwrap;unwrap.kind=TaskInstruction::Eval;unwrap.span=original->span;unwrap.source=original.get();unwrap.output=output;unwrap.inputs={input};
      unwrap.atom=std::make_shared<Expr>();unwrap.atom->kind=Expr::Call;unwrap.atom->text="unwrap";unwrap.atom->type=original->type;unwrap.atom->span=original->span;unwrap.atom->args={reference(input,original->span)};emit(std::move(unwrap));drop(input,original->span);return output;
    }
    auto atom=std::make_shared<Expr>(*original);atom->args.clear();TaskInstruction op;op.kind=TaskInstruction::Eval;op.span=original->span;op.source=original.get();op.output=output;
    if(original->kind==Expr::Name){auto id=lookup(original->text,original->span);atom->text=taskSlotName(id);atom->localName.clear();op.inputs={id};}
    else for(auto argument:original->args){auto id=expr(argument);op.inputs.push_back(id);atom->args.push_back(reference(id,argument->span));}
    if(original->kind==Expr::Call&&taskBuiltins().contains(original->text)){op.kind=TaskInstruction::Pause;op.operation=original->text;}
    else if(original->kind==Expr::Invoke&&original->args[0]->type.effects.contains("task")){op.kind=TaskInstruction::Call;op.indirect=true;}
    else if(original->kind==Expr::Call&&!builtinNames(true).contains(original->text)&&!program.hasStructure(original->text)&&!program.variant(original->text)&&program.function(original->text).effects.contains("task")){op.kind=TaskInstruction::Call;op.operation=original->text;}
    op.atom=std::move(atom);auto inputs=op.inputs;emit(std::move(op));
    if(original->kind!=Expr::Name)for(auto id:inputs)drop(id,original->span);return output;
  }
  bool block(const std::vector<S> &body,bool scoped=true){
    if(scoped)scopes.emplace_back();bool returned=false;
    for(const auto &s:body){
      switch(s->kind){
      case Stmt::Let:case Stmt::Var:{auto value=expr(s->expr);auto id=slot(s->type,s->span,s->name,false);copy(id,value,s->span);drop(value,s->span);scopes.back()[s->name]=id;break;}
      case Stmt::Assign:{auto value=expr(s->expr);copy(lookup(s->name,s->span),value,s->span);drop(value,s->span);break;}
      case Stmt::Expression:drop(expr(s->expr),s->span);break;
      case Stmt::Return:finish(s->expr?expr(s->expr):noTaskSlot,s->span,s.get());returned=true;break;
      case Stmt::Match:returned=matching(s->expr).second;break;
      case Stmt::If:{
        auto condition=expr(s->expr);auto choice=branch(condition,s->span);result.code[choice].yes=result.code.size();drop(condition,s->span);bool yes=block(s->body);size_t end=0;if(!yes)end=jump(s->span);
        result.code[choice].no=result.code.size();drop(condition,s->span);bool no=block(s->alternative);if(!yes)result.code[end].yes=result.code.size();returned=yes&&no;break;
      }
      case Stmt::While:{
        auto top=result.code.size();TaskInstruction poll;poll.kind=TaskInstruction::Poll;poll.span=s->span;poll.source=s.get();emit(std::move(poll));auto condition=expr(s->expr);auto choice=branch(condition,s->span);result.code[choice].yes=result.code.size();drop(condition,s->span);if(!block(s->body))jump(s->span,top);
        result.code[choice].no=result.code.size();drop(condition,s->span);break;
      }
      }
      if(returned)break;
    }
    if(scoped){if(!returned)leave(body.empty()?Span{}:body.back()->span);else scopes.pop_back();}return returned;
  }
public:
  Lowering(const Program &program,const Function &function):program(program){
    result.name=function.name;result.result=function.result;scopes.emplace_back();
    for(const auto &capture:function.captures){auto id=slot(capture.type,capture.span,capture.name,false);scopes.back()[capture.name]=id;result.captures.push_back(id);}
    for(const auto &parameter:function.params){auto id=slot(parameter.type,parameter.span,parameter.name,false);scopes.back()[parameter.name]=id;result.parameters.push_back(id);}
    TaskInstruction poll;poll.kind=TaskInstruction::Poll;poll.span=function.span;poll.source=&function;emit(std::move(poll));
    if(!block(function.body,false))finish(noTaskSlot,function.span);validateTaskIR(result);
  }
  TaskFunctionIR take(){return std::move(result);}
};
}
TaskFunctionIR lowerTaskFunction(const Program &program,const Function &function){
  if(!program.taskPrototype||!function.effects.contains("task")||function.foreign||!function.typeParameters.empty()||containsParameter(function.result)||std::any_of(function.params.begin(),function.params.end(),[](const auto &p){return containsParameter(p.type);})||std::any_of(function.captures.begin(),function.captures.end(),[](const auto &p){return containsParameter(p.type);}))throw Error("E_TASK_STATE","continuation lowering requires a concrete private task function",function.span);
  return Lowering(program,function).take();
}
void validateTaskIR(const TaskFunctionIR &function){
  if(function.code.empty())throw Error("E_TASK_STATE","empty continuation");
  auto checkSlot=[&](TaskSlotId slot,Span span){if(slot>=function.slots.size())throw Error("E_TASK_STATE","invalid continuation slot",span);};
  for(size_t i=0;i<function.code.size();++i){const auto &op=function.code[i];
    if(op.output!=noTaskSlot)checkSlot(op.output,op.span);for(auto slot:op.inputs)checkSlot(slot,op.span);for(auto slot:op.bindings)checkSlot(slot,op.span);
    if((op.kind==TaskInstruction::Jump||op.kind==TaskInstruction::Branch)&&op.yes>=function.code.size())throw Error("E_TASK_STATE","invalid continuation successor",op.span);
    if(op.kind==TaskInstruction::Branch&&(op.inputs.size()!=1||op.no>=function.code.size()||function.slots[op.inputs[0]].type!=Type::Bool))throw Error("E_TASK_STATE","invalid continuation branch",op.span);
    if(op.kind==TaskInstruction::Pause&&!taskBuiltins().contains(op.operation))throw Error("E_TASK_STATE","unknown continuation wait operation",op.span);
    if(op.kind==TaskInstruction::Eval){if(!op.atom)throw Error("E_TASK_STATE","missing continuation atom",op.span);for(const auto &argument:op.atom->args)if(argument->kind!=Expr::Name||!argument->text.starts_with("$task_slot_"))throw Error("E_TASK_STATE","continuation atom contains unevaluated operands",op.span);}
    if(i+1==function.code.size()&&op.kind!=TaskInstruction::Return&&op.kind!=TaskInstruction::Fail&&op.kind!=TaskInstruction::Jump)throw Error("E_TASK_STATE","continuation falls off its code",op.span);
  }
}
}
