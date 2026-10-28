#include "nex/task_ir.h"
#include "nex/task_frontend.h"
#include "nex/operations.h"
#include <algorithm>
#include <functional>

namespace nex {
std::string taskSlotName(TaskSlotId slot){return "$task_slot_"+std::to_string(slot);}
namespace {
class Lowering {
  const Program &program;
  bool fileReads=false,fileWrites=false,fileStreams=false;
  TaskFunctionIR result;
  std::vector<std::map<std::string,TaskSlotId>> scopes;
  std::vector<std::map<std::string,uint32_t>> debugScopes;
  std::vector<uint32_t> debugScopeIds;
  uint32_t nextDebugScope=0;
  size_t debugVisibleCount=0;
  bool opaqueType(const Type &type,bool unknownFunctions,std::set<std::string> &seen)const{
    // Private024 File watches expose only a diagnostic identity, never an IO
    // lease. Retained task languages keep their historical opaque metadata.
    if((type==Type::File&&!supportsTaskFileStreams(program))||type.kind==Type::Task||type.kind==Type::TaskScope||type.kind==Type::Channel)return true;
    if(type.kind==Type::Function&&(!type.effects.empty()||unknownFunctions))return true;
    if(type.element&&opaqueType(*type.element,unknownFunctions,seen))return true;
    for(const auto &argument:type.arguments)if(opaqueType(argument,unknownFunctions,seen))return true;
    if(type.kind==Type::Record&&seen.insert(type.name).second)
      for(auto field:program.structure(type.name).members())if(opaqueType(field->type,unknownFunctions,seen))return true;
    return false;
  }
  bool opaqueType(const Type &type,bool unknownFunctions)const{std::set<std::string> seen;return opaqueType(type,unknownFunctions,seen);}
  bool opaqueValue(E value)const{
    if(!value)return true;
    if(opaqueType(value->type,false))return true;
    if(!opaqueType(value->type,true))return false;
    if(value->kind==Expr::Name){
      for(auto scope=debugScopes.rbegin();scope!=debugScopes.rend();++scope)
        if(auto found=scope->find(value->text);found!=scope->end())return result.debug->bindings[found->second-1].opaque;
      return true;
    }
    if(value->kind==Expr::FunctionRef||value->kind==Expr::Lambda){
      const auto &function=program.function(value->text);
      for(const auto &capture:function.captures){
        bool known=false;
        for(auto scope=debugScopes.rbegin();scope!=debugScopes.rend();++scope)
          if(auto found=scope->find(capture.name);found!=scope->end()){
            if(result.debug->bindings[found->second-1].opaque)return true;
            known=true;break;
          }
        if(!known&&opaqueType(capture.type,true))return true;
      }
      return false;
    }
    if(value->kind==Expr::List||(value->kind==Expr::Call&&(program.hasStructure(value->text)||program.variant(value->text)))){
      for(auto argument:value->args)if(opaqueValue(argument))return true;
      return false;
    }
    if((value->kind==Expr::Index||value->kind==Expr::Field)&&!value->args.empty())return opaqueValue(value->args[0]);
    return true; // A dynamic function result can carry an unexposed authority capture.
  }
  void enter(){
    scopes.emplace_back();
    if(result.debug){debugScopes.emplace_back();debugScopeIds.push_back(++nextDebugScope);}
  }
  void leaveScope(){
    scopes.pop_back();if(result.debug){debugScopes.pop_back();debugScopeIds.pop_back();}
  }
  void binding(TaskSlotId slot,const std::string &name,const Type &type,Span span,E value={}){
    if(!result.debug)return;
    auto &metadata=*result.debug;
    if(metadata.bindings.size()>=65536)throw Error("E_DEBUG_INIT","task debugger exceeds65536 named bindings",span);
    auto id=uint32_t(metadata.bindings.size()+1);
    metadata.bindings.push_back({id,debugScopeIds.back(),uint32_t(debugScopes.size()-1),slot,name,type,span,value?opaqueValue(value):opaqueType(type,true)});
    debugScopes.back()[name]=id;
  }
  void point(TaskDebugPointIR::Kind kind,Span span,const void *source=nullptr){
    if(!result.debug)return;
    auto &metadata=*result.debug;
    if(metadata.points.size()>=262144)throw Error("E_DEBUG_INIT","task debugger exceeds262144 source points",span);
    TaskDebugPointIR point;point.kind=kind;point.pc=result.code.size();point.span=span;point.source=source;
    for(const auto &scope:debugScopes)for(const auto &[name,id]:scope)point.visible.push_back(id);
    if(point.visible.size()>1048576-debugVisibleCount)throw Error("E_DEBUG_INIT","task debugger exceeds1048576 visibility entries",span);
    debugVisibleCount+=point.visible.size();
    metadata.points.push_back(std::move(point));
  }
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
  void leave(Span span){for(const auto &[name,id]:scopes.back())drop(id,span);leaveScope();}
  void finish(TaskSlotId value,Span span,const void *source=nullptr,bool propagated=false){
    point(TaskDebugPointIR::Return,span,source);
    TaskInstruction op;op.kind=TaskInstruction::Return;op.span=span;op.source=source;op.propagatedError=propagated;if(value!=noTaskSlot)op.inputs={value};emit(std::move(op));
  }
  P pattern(P original,std::vector<TaskSlotId> &bindings){
    auto value=std::make_shared<nex::Pattern>(*original);value->args.clear();
    if(value->kind==nex::Pattern::Binding){auto id=slot(value->type,value->span,value->text,false);scopes.back()[value->text]=id;binding(id,value->text,value->type,value->span);bindings.push_back(id);value->text=taskSlotName(id);value->binding=id;}
    for(auto child:original->args)value->args.push_back(pattern(child,bindings));return value;
  }
  std::pair<TaskSlotId,bool> matching(E expression){
    auto input=expr(expression->args[0]);auto output=slot(expression->type,expression->span);std::vector<size_t> ends;
    bool allReturn=expression->statementMatch;
    for(const auto &arm:expression->arms){
      enter();TaskInstruction test;test.kind=TaskInstruction::Pattern;test.span=arm->span;test.source=arm->pattern.get();test.output=slot(Type::Bool,arm->span);test.inputs={input};test.pattern=pattern(arm->pattern,test.bindings);
      auto condition=test.output;auto bindings=test.bindings;emit(std::move(test));auto matched=branch(condition,arm->span);result.code[matched].yes=result.code.size();drop(condition,arm->span);
      size_t guarded=0;TaskSlotId guard=noTaskSlot;
      if(arm->guard){point(TaskDebugPointIR::Statement,expression->args[arm->guard]->span,expression->args[arm->guard].get());guard=expr(expression->args[arm->guard]);guarded=branch(guard,arm->span);result.code[guarded].yes=result.code.size();drop(guard,arm->span);}
      bool returned=false;
      if(expression->statementMatch)returned=block(arm->body,false);
      else{auto value=expr(expression->args[arm->value]);copy(output,value,arm->span);drop(value,arm->span);}
      allReturn&=returned;
      if(!returned){for(const auto &[name,id]:scopes.back())drop(id,arm->span);ends.push_back(jump(arm->span));}
      if(arm->guard){result.code[guarded].no=result.code.size();drop(guard,arm->span);for(const auto &[name,id]:scopes.back())drop(id,arm->span);}
      auto failed=jump(arm->span);result.code[matched].no=result.code.size();drop(condition,arm->span);for(auto id:bindings)drop(id,arm->span);
      result.code[failed].yes=result.code.size();leaveScope();
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
    if(original->kind==Expr::Call&&(taskBuiltins().contains(original->text)||(fileReads&&(original->text=="file_read_text"||original->text=="file_read_bytes"))||(fileWrites&&taskFileWriteOperation(original->text))||(fileStreams&&streamFileBuiltins().contains(original->text)))){op.kind=TaskInstruction::Pause;op.operation=original->text;}
    else if(supportsTaskForeignCalls(program)&&original->kind==Expr::Call&&
        !builtinNames(true,supportsExternalResources(program)).contains(original->text)&&!program.hasStructure(original->text)&&!program.variant(original->text)&&program.function(original->text).foreign){
      op.kind=TaskInstruction::Pause;op.foreign=true;op.operation=original->text;
    }
    else if(original->kind==Expr::Invoke&&(sourceExceptionTasksPrototype(program)||original->args[0]->type.effects.contains("task"))){op.kind=TaskInstruction::Call;op.indirect=true;}
    else if(original->kind==Expr::Call&&!builtinNames(true,supportsExternalResources(program)).contains(original->text)&&!program.hasStructure(original->text)&&!program.variant(original->text)&&(sourceExceptionTasksPrototype(program)||program.function(original->text).effects.contains("task"))){op.kind=TaskInstruction::Call;op.operation=original->text;}
    bool sourceCall=original->kind==Expr::Call||original->kind==Expr::Invoke;
    bool resumes=op.kind==TaskInstruction::Pause||op.kind==TaskInstruction::Call;
    if(sourceCall)point(TaskDebugPointIR::Call,original->span,original.get());
    op.atom=std::move(atom);auto inputs=op.inputs;emit(std::move(op));
    if(resumes)point(TaskDebugPointIR::Resume,original->span,original.get());
    if(original->kind!=Expr::Name)for(auto id:inputs)drop(id,original->span);return output;
  }
  bool block(const std::vector<S> &body,bool scoped=true){
    if(scoped)enter();bool returned=false;
    for(const auto &s:body){
      if(s->kind!=Stmt::While)point(TaskDebugPointIR::Statement,s->span,s.get());
      switch(s->kind){
      case Stmt::Try:{
        if(!sourceExceptionTasksPrototype(program))throw Error("E_EXCEPTION_BACKEND","exception TaskIR requires the separate private task parser",s->span);
        TaskInstruction install;install.kind=TaskInstruction::PushHandler;install.span=s->span;install.source=s.get();install.no=result.slots.size();auto start=emit(std::move(install));
        bool bodyEnds=block(s->body);size_t skip=0;
        if(!bodyEnds){TaskInstruction pop;pop.kind=TaskInstruction::PopHandler;pop.span=s->span;emit(std::move(pop));skip=jump(s->span);}
        result.code[start].yes=result.code.size();enter();
        TaskInstruction caught;caught.kind=TaskInstruction::Catch;caught.span=s->span;caught.source=s.get();
        for(const auto &name:{s->name,s->catchMessage}){auto id=slot(Type::Str,s->span,name,false);caught.bindings.push_back(id);binding(id,name,Type::Str,s->span);scopes.back()[name]=id;}
        emit(std::move(caught));bool catchEnds=block(s->alternative,false);
        if(!catchEnds){TaskInstruction end;end.kind=TaskInstruction::EndCatch;end.span=s->span;emit(std::move(end));leave(s->span);}else leaveScope();
        if(!bodyEnds)result.code[skip].yes=result.code.size();returned=bodyEnds&&catchEnds;break;
      }
      case Stmt::Throw:{
        if(!sourceExceptionTasksPrototype(program))throw Error("E_EXCEPTION_BACKEND","exception TaskIR requires the separate private task parser",s->span);
        TaskInstruction raised;raised.kind=s->expr?TaskInstruction::Raise:TaskInstruction::Rethrow;raised.span=s->span;raised.source=s.get();
        if(s->expr){raised.inputs.push_back(expr(s->expr->args[0]));raised.inputs.push_back(expr(s->expr->args[1]));}
        emit(std::move(raised));returned=true;break;
      }
      case Stmt::Let:case Stmt::Var:{auto value=expr(s->expr);auto id=slot(s->type,s->span,s->name,false);copy(id,value,s->span);drop(value,s->span);binding(id,s->name,s->type,s->span,s->expr);scopes.back()[s->name]=id;break;}
      case Stmt::Assign:{auto value=expr(s->expr);copy(lookup(s->name,s->span),value,s->span);drop(value,s->span);if(result.debug&&opaqueValue(s->expr))for(auto scope=debugScopes.rbegin();scope!=debugScopes.rend();++scope)if(auto found=scope->find(s->name);found!=scope->end()){result.debug->bindings[found->second-1].opaque=true;break;}break;}
      case Stmt::Expression:drop(expr(s->expr),s->span);break;
      case Stmt::Return:finish(s->expr?expr(s->expr):noTaskSlot,s->span,s.get());returned=true;break;
      case Stmt::Match:returned=matching(s->expr).second;break;
      case Stmt::If:{
        auto condition=expr(s->expr);auto choice=branch(condition,s->span);result.code[choice].yes=result.code.size();drop(condition,s->span);bool yes=block(s->body);size_t end=0;if(!yes)end=jump(s->span);
        result.code[choice].no=result.code.size();drop(condition,s->span);bool no=block(s->alternative);if(!yes)result.code[end].yes=result.code.size();returned=yes&&no;break;
      }
      case Stmt::While:{
        auto top=result.code.size();point(TaskDebugPointIR::Loop,s->expr->span,s->expr.get());TaskInstruction poll;poll.kind=TaskInstruction::Poll;poll.span=s->span;poll.source=s.get();emit(std::move(poll));auto condition=expr(s->expr);auto choice=branch(condition,s->span);result.code[choice].yes=result.code.size();drop(condition,s->span);if(!block(s->body))jump(s->span,top);
        result.code[choice].no=result.code.size();drop(condition,s->span);break;
      }
      }
      if(returned)break;
    }
    if(scoped){if(!returned)leave(body.empty()?Span{}:body.back()->span);else leaveScope();}return returned;
  }
public:
  Lowering(const Program &program,const Function &function,bool debugMetadata):program(program){
    fileReads=supportsTaskFileReads(program)&&function.realm=="server"&&function.effects.contains("task")&&function.effects.contains("fs");
    fileWrites=fileReads&&supportsTaskFileWrites(program);
    fileStreams=fileReads&&supportsTaskFileStreams(program);
    result.name=function.name;result.result=function.result;if(debugMetadata)result.debug.emplace();enter();
    for(const auto &capture:function.captures){auto id=slot(capture.type,capture.span,capture.name,false);scopes.back()[capture.name]=id;binding(id,capture.name,capture.type,capture.span);result.captures.push_back(id);}
    for(const auto &parameter:function.params){auto id=slot(parameter.type,parameter.span,parameter.name,false);scopes.back()[parameter.name]=id;binding(id,parameter.name,parameter.type,parameter.span);result.parameters.push_back(id);}
    point(TaskDebugPointIR::Entry,function.span,&function);
    TaskInstruction poll;poll.kind=TaskInstruction::Poll;poll.span=function.span;poll.source=&function;emit(std::move(poll));
    if(!block(function.body,false))finish(noTaskSlot,function.span);validateTaskIR(result);
  }
  TaskFunctionIR take(){return std::move(result);}
};
}
TaskFunctionIR lowerTaskFunction(const Program &program,const Function &function,bool liftPure,bool debugMetadata){
  if(sourceExceptionTasksPrototype(program)&&usesParallelMap(function))throw Error("E_EXCEPTION_STAGE","private exception TaskIR does not yet lower parallel_map workers",function.span);
  if(!program.taskPrototype||(!liftPure&&!function.effects.contains("task"))||function.foreign||!function.typeParameters.empty()||containsParameter(function.result)||std::any_of(function.params.begin(),function.params.end(),[](const auto &p){return containsParameter(p.type);})||std::any_of(function.captures.begin(),function.captures.end(),[](const auto &p){return containsParameter(p.type);}))throw Error("E_TASK_STATE","continuation lowering requires a concrete private task function",function.span);
  return Lowering(program,function,debugMetadata).take();
}
void validateTaskIR(const TaskFunctionIR &function){
  if(function.code.empty())throw Error("E_TASK_STATE","empty continuation");
  auto checkSlot=[&](TaskSlotId slot,Span span){if(slot>=function.slots.size())throw Error("E_TASK_STATE","invalid continuation slot",span);};
  for(size_t i=0;i<function.code.size();++i){const auto &op=function.code[i];
    if(op.output!=noTaskSlot)checkSlot(op.output,op.span);for(auto slot:op.inputs)checkSlot(slot,op.span);for(auto slot:op.bindings)checkSlot(slot,op.span);
    if((op.kind==TaskInstruction::Jump||op.kind==TaskInstruction::Branch)&&op.yes>=function.code.size())throw Error("E_TASK_STATE","invalid continuation successor",op.span);
    if(op.kind==TaskInstruction::Branch&&(op.inputs.size()!=1||op.no>=function.code.size()||function.slots[op.inputs[0]].type!=Type::Bool))throw Error("E_TASK_STATE","invalid continuation branch",op.span);
    if(op.kind<TaskInstruction::Eval||op.kind>TaskInstruction::Rethrow)throw Error("E_TASK_STATE","unknown continuation instruction",op.span);
    if(op.kind==TaskInstruction::PushHandler&&(op.yes>=function.code.size()||function.code[op.yes].kind!=TaskInstruction::Catch||op.no>function.slots.size()||!op.inputs.empty()||!op.bindings.empty()))throw Error("E_TASK_STATE","invalid continuation handler target/slot floor",op.span);
    if(op.kind==TaskInstruction::Catch&&(op.bindings.size()!=2||op.bindings[0]==op.bindings[1]||function.slots[op.bindings[0]].type!=Type::Str||function.slots[op.bindings[1]].type!=Type::Str))throw Error("E_TASK_STATE","invalid continuation catch bindings",op.span);
    if(op.kind==TaskInstruction::Raise&&(op.inputs.size()!=2||function.slots[op.inputs[0]].type!=Type::Str||function.slots[op.inputs[1]].type!=Type::Str))throw Error("E_TASK_STATE","invalid continuation source error operands",op.span);
    if((op.kind==TaskInstruction::Rethrow||op.kind==TaskInstruction::PopHandler||op.kind==TaskInstruction::EndCatch)&&(!op.inputs.empty()||!op.bindings.empty()||op.output!=noTaskSlot))throw Error("E_TASK_STATE","invalid continuation exception control shape",op.span);
    if(op.kind==TaskInstruction::Pause&&!taskBuiltins().contains(op.operation)){
      if(op.foreign){
        if(op.operation.empty()||!op.atom||op.atom->kind!=Expr::Call||op.atom->text!=op.operation||op.inputs.size()!=op.atom->args.size())
          throw Error("E_TASK_STATE","invalid continuation foreign call operation",op.span);
      }else if(streamFileBuiltins().contains(op.operation)){
        std::vector<Type> parameters;Type result;
        if(op.operation.starts_with("file_open_")){parameters={Type::Str};result=Type::result(Type::File);}
        else if(op.operation=="file_read"){parameters={Type::File,Type::I64};result=Type::result(Type::Bytes);}
        else if(op.operation=="file_write"){parameters={Type::File,Type::Bytes};result=Type::result(Type::I64);}
        else if(op.operation=="file_seek"){parameters={Type::File,Type::I64};result=Type::result(Type::I64);}
        else {parameters={Type::File};result=op.operation=="file_size"?Type::result(Type::I64):op.operation=="file_flush"?Type::result(Type::Bool):Type(Type::Bool);}
        if(op.inputs.size()!=parameters.size()||op.output==noTaskSlot||function.slots[op.output].type!=result)throw Error("E_TASK_STATE","invalid file stream continuation shape",op.span);
        for(size_t i=0;i<parameters.size();++i)if(function.slots[op.inputs[i]].type!=parameters[i])throw Error("E_TASK_STATE","invalid file stream continuation operand",op.span);
      }else if(taskFileWriteOperation(op.operation)){
        if(op.inputs.size()!=2||function.slots[op.inputs[0]].type!=Type::Str||function.slots[op.inputs[1]].type!=(op.operation=="file_write_text"?Type(Type::Str):Type(Type::Bytes))||op.output==noTaskSlot||function.slots[op.output].type!=Type::result(Type::Bool))
          throw Error("E_TASK_STATE","invalid continuation file write operation",op.span);
      }else if((op.operation!="file_read_text"&&op.operation!="file_read_bytes")||op.inputs.size()!=1||function.slots[op.inputs[0]].type!=Type::Str||op.output==noTaskSlot||function.slots[op.output].type!=Type::result(op.operation=="file_read_text"?Type(Type::Str):Type(Type::Bytes)))
        throw Error("E_TASK_STATE","invalid continuation file read operation",op.span);
    }
    if(op.kind==TaskInstruction::Eval){if(!op.atom)throw Error("E_TASK_STATE","missing continuation atom",op.span);for(const auto &argument:op.atom->args)if(argument->kind!=Expr::Name||!argument->text.starts_with("$task_slot_"))throw Error("E_TASK_STATE","continuation atom contains unevaluated operands",op.span);}
    if(i+1==function.code.size()&&op.kind!=TaskInstruction::Return&&op.kind!=TaskInstruction::Fail&&op.kind!=TaskInstruction::Jump&&op.kind!=TaskInstruction::Raise&&op.kind!=TaskInstruction::Rethrow)throw Error("E_TASK_STATE","continuation falls off its code",op.span);
  }
  if(function.debug){const auto &metadata=*function.debug;
    for(size_t i=0;i<metadata.bindings.size();++i){const auto &binding=metadata.bindings[i];
      if(binding.id!=i+1||binding.name.empty()||!binding.scope||
         (binding.slot==noTaskSlot?binding.type!=Type::Unit:binding.slot>=function.slots.size()||function.slots[binding.slot].temporary||function.slots[binding.slot].type!=binding.type))
        throw Error("E_TASK_STATE","invalid task debug binding",binding.span);
    }
    for(const auto &point:metadata.points){
      if(point.pc>=function.code.size()||point.kind<TaskDebugPointIR::Entry||point.kind>TaskDebugPointIR::Return)
        throw Error("E_TASK_STATE","invalid task debug source point",point.span);
      std::set<uint32_t> seen;
      for(auto id:point.visible)if(!id||id>metadata.bindings.size()||!seen.insert(id).second)
        throw Error("E_TASK_STATE","invalid task debug visibility",point.span);
    }
  }
}
llvm::json::Object taskDebugFunctionMetadata(const Program &program,const Function &function,const TaskFunctionIR &ir,const std::string &file){
  if(!ir.debug||ir.name!=function.name)throw Error("E_TASK_STATE","task debug metadata requires its checked function",function.span);
  validateTaskIR(ir);
  auto operations=operationTree(program,function);std::map<const void*,std::string> sites;std::string body;
  for(const auto &operation:operations){if(operation.ast)sites[operation.ast]=operation.site;if(operation.path=="body")body=operation.site;}
  llvm::json::Array bindings,points;
  for(const auto &binding:ir.debug->bindings)bindings.push_back(llvm::json::Object{
    {"id",binding.id},{"slot",binding.slot==noTaskSlot?-1:int64_t(binding.slot)},{"name",binding.name},
    {"type",typeName(binding.type)},{"scope",binding.scope},{"depth",binding.depth},{"opaque",binding.opaque}});
  static const char *phases[]={"entry","statement","loop_test","call_entry","resume","return"};
  for(size_t i=0;i<ir.debug->points.size();++i){const auto &point=ir.debug->points[i];llvm::json::Array visible;
    for(auto id:point.visible)visible.push_back(id);
    auto found=sites.find(point.source);auto site=found==sites.end()?body:found->second;
    points.push_back(llvm::json::Object{{"id",i+1},{"pc",point.pc},{"line",point.span.line},{"column",point.span.column},
      {"begin",point.span.begin},{"end",point.span.end},{"kind",int64_t(point.kind)},{"phase",phases[point.kind]},
      {"site",site},{"visible",std::move(visible)}});
  }
  return llvm::json::Object{{"file",file},{"slot_count",ir.slots.size()},{"bindings",std::move(bindings)},{"points",std::move(points)}};
}
llvm::json::Object taskDebugFunctionMetadata(const Program &program,const Function &function,const std::string &file){
  return taskDebugFunctionMetadata(program,function,lowerTaskFunction(program,function,true,true),file);
}
}
