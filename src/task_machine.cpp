#include "nex/task_machine.h"
#include "nex/task_ir.h"
#include "nex/task_frontend.h"
#include <algorithm>

namespace nex {
using TV=nexrt::Value;
struct TaskMachine::Impl {
  const Program &program;uint64_t limit,used=0,sequence=0;
  std::string output;Span activeSpan;
  struct Frame {const TaskFunctionIR *function;size_t pc=0;std::vector<std::optional<TV>> slots;TaskSlotId returned=noTaskSlot;};
  std::map<std::string,TaskFunctionIR> functions;std::vector<Frame> frames;
  bool waiting=false,done=false,failed=false;
  TaskSlotId response=noTaskSlot;uint64_t ticket=0;
  void charge(Span span,uint64_t count=1){if(count>limit-used)throw Error("E_LIMIT","continuation step budget exceeded",span);used+=count;}
  TV read(const Frame &frame,TaskSlotId id,Span span){
    if(id>=frame.slots.size()||!frame.slots[id])throw Error("E_TASK_STATE","continuation read before initialization",span);
    return *frame.slots[id];
  }
  void write(Frame &frame,TaskSlotId id,TV value,Span span){
    if(id==noTaskSlot)return;
    const auto &type=frame.function->slots.at(id).type;
    if((type==Type::I64&&value.tag!=TV::Integer)||(type==Type::Bool&&value.tag!=TV::Boolean)||(type==Type::F64&&value.tag!=TV::Floating)||(type.heap()&&(value.tag!=TV::Object||!value.object)))
      throw Error("E_TASK_TYPE","continuation response has the wrong value kind",span);
    frame.slots[id]=std::move(value);
  }
  void push(const std::string &name,const std::vector<TV> &arguments,const TV *environment,TaskSlotId returned){
    const auto &source=program.function(name);
    for(const auto &effect:source.effects)if(effect!="task"&&effect!="io"&&!(effect=="fs"&&supportsTaskFileReads(program)&&source.realm=="server"&&source.effects.contains("task")))throw Error("E_TASK_UNIMPLEMENTED","continuation semantic harness has no host resource bridge",source.span);
    if(containsFile(program,Type::function({},source.result))||std::any_of(source.params.begin(),source.params.end(),[&](const auto &p){return containsFile(program,p.type);}))throw Error("E_TASK_UNIMPLEMENTED","continuation semantic harness cannot carry file authority",source.span);
    if(frames.size()>=256)throw Error("E_LIMIT","continuation call depth exceeds256",source.span);
    auto found=functions.find(name);if(found==functions.end())found=functions.emplace(name,lowerTaskFunction(program,source)).first;
    const auto &function=found->second;
    if(arguments.size()!=function.parameters.size()||(!function.captures.empty()&&(!environment||!environment->object||environment->object->kind!=nexrt::Data::Closure||environment->object->values.size()!=function.captures.size())))throw Error("E_TASK_STATE","continuation arguments/captures do not match",source.span);
    Frame frame{&function,0,std::vector<std::optional<TV>>(function.slots.size()),returned};
    for(size_t i=0;i<arguments.size();++i)write(frame,function.parameters[i],arguments[i],source.span);
    for(size_t i=0;i<function.captures.size();++i)write(frame,function.captures[i],environment->object->values[i],source.span);
    frames.push_back(std::move(frame));
  }
  bool match(Frame &frame,P pattern,const TV &value){
    charge(pattern->span);
    if(pattern->kind==nex::Pattern::Wildcard)return true;
    if(pattern->kind==nex::Pattern::Binding){write(frame,TaskSlotId(pattern->binding),value,pattern->span);return true;}
    if(pattern->kind==nex::Pattern::Integer||pattern->kind==nex::Pattern::Boolean)return value.scalar==pattern->number;
    if(pattern->kind==nex::Pattern::String)return value.object->text==pattern->text;
    if(pattern->kind==nex::Pattern::List){if(nexrt::length(value.object)!=int64_t(pattern->args.size()))return false;}
    else if(pattern->type.kind==Type::Result){if(nexrt::isSuccess(value)!=bool(pattern->ordinal))return false;}
    else if(program.structure(pattern->type.name).enumeration&&value.object->ordinal!=pattern->ordinal)return false;
    for(size_t i=0;i<pattern->args.size();++i){TV child;
      if(pattern->type.kind==Type::Result){if(pattern->ordinal)child=nexrt::unwrap(value);else child=i==0?TV(nexrt::string(value.object->text)):value.object->values[0];}
      else child=nexrt::get(value.object,i);
      if(!match(frame,pattern->args[i],child))return false;
    }
    return true;
  }
  TaskTransition advance(){
    if(done||failed||waiting)throw Error("E_TASK_STATE","continuation is completed, failed or awaiting a response");
    try{
      while(!frames.empty()){
        auto &frame=frames.back();const auto &op=frame.function->code.at(frame.pc);activeSpan=op.span;charge(op.span);
        switch(op.kind){
        case TaskInstruction::Poll:++frame.pc;break;
        case TaskInstruction::Eval:{
          std::map<std::string,TV> values;for(auto id:op.inputs)values.emplace(taskSlotName(id),read(frame,id,op.span));
          TaskAtomResult result;
          try{result=evaluateTaskAtom(program,op.atom,values,limit-used,unsigned(frames.size()-1));}
          catch(Error &error){output+=error.output;throw;}
          charge(op.span,result.steps);output+=result.output;
          write(frame,op.output,std::move(result.value),op.span);++frame.pc;break;
        }
        case TaskInstruction::Copy:write(frame,op.output,read(frame,op.inputs[0],op.span),op.span);++frame.pc;break;
        case TaskInstruction::Drop:frame.slots.at(op.inputs[0]).reset();++frame.pc;break;
        case TaskInstruction::Jump:frame.pc=op.yes;break;
        case TaskInstruction::Branch:frame.pc=read(frame,op.inputs[0],op.span).scalar?op.yes:op.no;break;
        case TaskInstruction::Pattern:{
          for(auto id:op.bindings)frame.slots.at(id).reset();auto matched=match(frame,op.pattern,read(frame,op.inputs[0],op.span));
          if(!matched)for(auto id:op.bindings)frame.slots.at(id).reset();write(frame,op.output,TV(matched,true),op.span);++frame.pc;break;
        }
        case TaskInstruction::Pause:{
          TaskTransition next;next.kind=TaskTransition::Waiting;next.operation=op.operation;next.span=op.span;next.result=op.output==noTaskSlot?Type(Type::Unit):frame.function->slots[op.output].type;next.ticket=++sequence;next.callDepth=frames.size();next.pc=frame.pc;
          for(auto id:op.inputs)next.arguments.push_back(read(frame,id,op.span));waiting=true;response=op.output;ticket=next.ticket;++frame.pc;return next;
        }
        case TaskInstruction::Call:{
          std::vector<TV> args;for(auto id:op.inputs)args.push_back(read(frame,id,op.span));auto name=op.operation;TV environment;
          if(op.indirect){environment=args.at(0);if(!environment.object||environment.object->kind!=nexrt::Data::Closure)throw Error("E_TASK_TYPE","task call requires a closure",op.span);name=environment.object->text;args.erase(args.begin());}
          ++frame.pc;push(name,args,op.indirect?&environment:nullptr,op.output);break;
        }
        case TaskInstruction::Return:{
          TV value;if(!op.inputs.empty())value=read(frame,op.inputs[0],op.span);auto returned=frame.returned;auto result=frame.function->result;frames.pop_back();
          if(frames.empty()){done=true;TaskTransition next;next.kind=TaskTransition::Done;next.result=result;next.value=std::move(value);return next;}
          write(frames.back(),returned,std::move(value),op.span);break;
        }
        case TaskInstruction::Fail:throw Error(op.operation,"no checked continuation match arm accepted",op.span);
        }
      }
      throw Error("E_TASK_STATE","continuation lost its root frame");
    }catch(const nexrt::DataError &error){failed=true;frames.clear();Error failure(error.code,error.what(),activeSpan);failure.output=output;throw failure;}
    catch(Error &error){failed=true;frames.clear();error.output=output;throw;}
    catch(...){failed=true;frames.clear();throw;}
  }
  Impl(const Program &p,const std::string &entry,const std::vector<TV> &arguments,uint64_t limit):program(p),limit(limit){
    if(!p.taskPrototype)throw Error("E_TASK_STATE","continuation harness requires private checked task source");push(entry,arguments,nullptr,noTaskSlot);
  }
};
TaskMachine::TaskMachine(const Program &p,const std::string &entry,const std::vector<TV> &args,uint64_t limit):impl(std::make_unique<Impl>(p,entry,args,limit)){}
TaskMachine::~TaskMachine()=default;
TaskTransition TaskMachine::advance(){return impl->advance();}
void TaskMachine::resume(uint64_t ticket,TV value){
  if(!impl->waiting||ticket!=impl->ticket||impl->failed||impl->done)throw Error("E_TASK_STATE","stale or duplicate continuation response");
  impl->write(impl->frames.back(),impl->response,std::move(value),{});impl->waiting=false;
}
bool TaskMachine::finished()const{return impl->done;}
uint64_t TaskMachine::steps()const{return impl->used;}
const std::string &TaskMachine::output()const{return impl->output;}
}
