#include "nex_task_frame.h"
namespace nexrt {
static bool kindMatches(const Value &v,int64_t kind){
  if(kind==2&&v.tag==Value::Floating){(void)v.floating();return true;}
  return kind==0?v.tag==Value::Integer:kind==1?v.tag==Value::Boolean&&v.scalar>=0&&v.scalar<=1:kind==2?v.tag==Value::Floating:kind==3?v.tag==Value::Object&&bool(v.object):false;
}
NativeTaskFrame::NativeTaskFrame(TaskFrameDescriptor d,const std::vector<Value> &args):step(d.step),kinds(d.kinds.begin(),d.kinds.end()),slots(d.kinds.size()){
  if(!d.step||slots.size()>65536||args.size()!=d.parameters.size())throw DataError("E_TASK_STATE","invalid compiled task frame descriptor");
  for(auto kind:d.kinds)if(kind<0||kind>3)throw DataError("E_TASK_STATE","invalid compiled task slot kind");
  for(size_t i=0;i<args.size();++i){auto id=d.parameters[i];if(id>=slots.size())throw DataError("E_TASK_STATE","invalid compiled task parameter slot");write(id,args[i],d.kinds[id]);}
}
Value NativeTaskFrame::read(int64_t id,int64_t kind)const{
  if(completed||id<0||size_t(id)>=slots.size()||!slots[id]||kinds[id]!=kind||!kindMatches(*slots[id],kind))throw DataError("E_TASK_STATE","invalid or uninitialized compiled task slot read");
  return *slots[id];
}
void NativeTaskFrame::write(int64_t id,Value value,int64_t kind){
  if(completed||id<0||size_t(id)>=slots.size()||kinds[id]!=kind||!kindMatches(value,kind))throw DataError("E_TASK_STATE","invalid compiled task slot write");
  slots[id]=std::move(value);
}
void NativeTaskFrame::drop(int64_t id){if(completed||id<0||size_t(id)>=slots.size())throw DataError("E_TASK_STATE","invalid compiled task slot drop");slots[id].reset();}
namespace {
const TaskCodeDescriptor &checkedCode(const void *pointer){
  if(!pointer)throw DataError("E_TASK_STATE","missing compiled task code descriptor");
  const auto &d=*static_cast<const TaskCodeDescriptor*>(pointer);
  if(d.abi!=taskCodeABI||!d.step||d.slotCount<0||d.slotCount>65536||d.parameterCount<0||d.parameterCount>d.slotCount||d.captureCount<0||d.captureCount>d.slotCount||d.resultKind<0||d.resultKind>4||(!d.kinds&&d.slotCount)||(!d.parameters&&d.parameterCount)||(!d.captures&&d.captureCount))throw DataError("E_TASK_STATE","invalid compiled task code descriptor");
  return d;
}
struct CallDepth {
  size_t previous;
  explicit CallDepth(size_t depth):previous(exchangeCompiledTaskDepth(depth)){}
  ~CallDepth(){exchangeCompiledTaskDepth(previous);}
};
}
NativeTaskFrame::NativeTaskFrame(const TaskCodeDescriptor &input,const std::vector<Value> &args,const Value &environment):step(nullptr){
  const auto &d=checkedCode(&input);step=d.step;expectedResult=d.resultKind;
  if(d.slotCount)kinds.assign(d.kinds,d.kinds+d.slotCount);slots.resize(kinds.size());
  if(args.size()!=size_t(d.parameterCount))throw DataError("E_TASK_STATE","compiled task argument count differs");
  for(auto kind:kinds)if(kind<0||kind>3)throw DataError("E_TASK_STATE","invalid compiled task slot kind");
  std::vector<bool> assigned(slots.size());
  auto assign=[&](int64_t id,const Value &value){if(id<0||size_t(id)>=slots.size()||assigned[id])throw DataError("E_TASK_STATE","invalid compiled task parameter/capture slot");assigned[id]=true;write(id,value,kinds[id]);};
  if(environment.tag!=Value::Integer||environment.scalar!=0){
    if(environment.tag!=Value::Object||!environment.object||environment.object->kind!=Data::Closure||environment.object->taskCode!=&d||environment.object->values.size()!=size_t(d.captureCount))throw DataError("E_TASK_STATE","compiled task closure descriptor differs");
    for(int64_t i=0;i<d.captureCount;++i)assign(d.captures[i],environment.object->values[i]);
  }else if(d.captureCount)throw DataError("E_TASK_STATE","compiled task capture environment is missing");
  for(size_t i=0;i<args.size();++i)assign(d.parameters[i],args[i]);
}
namespace {
const TaskCodeDescriptor &closureCode(const Value &value){
  if(value.tag!=Value::Object||!value.object||value.object->kind!=Data::Closure||!value.object->taskCode)throw DataError("E_TASK_STATE","source task callback has no compiled descriptor");
  return checkedCode(value.object->taskCode);
}
thread_local TaskStepObserver spawnedObserver=nullptr;
struct ObserverScope {TaskStepObserver previous;explicit ObserverScope(TaskStepObserver observer):previous(spawnedObserver){spawnedObserver=observer;}~ObserverScope(){spawnedObserver=previous;}};
TaskBody executeTaskClosure(TaskGroup &group,Value,Value closure){return executeTaskFrame(group,NativeTaskFrame(closureCode(closure),{},closure),spawnedObserver);}
Value channelResult(TaskEvent event){
  auto data=std::make_shared<Data>(event.present?Data::Success:Data::Failure);
  if(event.present)data->values={std::move(event.value)};
  else{data->text="E_CHANNEL_CLOSED";auto text=std::make_shared<Data>(Data::String);text->text="channel is closed";data->values={Value(std::move(text))};}
  return Value(std::move(data));
}
}
TaskBody executeTaskFrame(TaskGroup &group,NativeTaskFrame frame,TaskStepObserver observer){
  std::vector<NativeTaskFrame> stack;stack.push_back(std::move(frame));
  while(!stack.empty()){
    auto &current=stack.back();int64_t transition;
    {CallDepth depth(stack.size()-1);transition=current.step(&current);}
    if(observer)observer(current,transition);
    if(transition==0){
      if(!current.completed||current.pendingCall||current.pendingRequest)throw DataError("E_TASK_STATE","compiled task returned without completing");
      auto result=std::move(current.result);auto destination=current.returnDestination;
      if(current.closingScope){
        hostOperation(current.scopeLocation,[&]{validateTaskSnapshot(group,result,current.parentScope);});
        bool failed=result.tag==Value::Object&&result.object&&result.object->kind==Data::Failure;
        co_await group.leaveScope(*current.closingScope,failed).at(current.scopeLocation);
      }
      stack.pop_back();if(stack.empty())co_return result;
      auto &caller=stack.back();if(destination>=0)caller.write(destination,std::move(result),caller.kinds.at(destination));
    }else if(transition==1){
      if(current.completed||current.pendingCall||current.pendingRequest)throw DataError("E_TASK_STATE","invalid compiled task yield transition");
      co_await group.yield();
    }else if(transition==2){
      if(current.completed||!current.pendingCall||current.pendingRequest||stack.size()>=256)throw DataError("E_TASK_STATE","invalid compiled task call transition");
      auto child=std::move(current.pendingCall);child->depth=stack.size()+1;stack.push_back(std::move(*child));
    }else if(transition==3){
      if(current.completed||current.pendingCall||!current.pendingRequest)throw DataError("E_TASK_STATE","invalid compiled task request transition");
      auto request=std::move(*current.pendingRequest);current.pendingRequest.reset();Value result;
      auto checked=[&](auto action){return hostOperation(request.location,action);};
      auto capability=[&](size_t i,Data::Kind kind)->const TaskData&{return taskData(request.arguments.at(i),kind);};
      switch(request.operation){
      case TaskRequestKind::Yield:co_await group.yield().at(request.location);break;
      case TaskRequestKind::WithTasks:{
        auto parent=group.currentScopeOrEmpty();
        auto scope=checked([&]{auto workers=request.arguments[0];if(workers.tag!=Value::Integer||workers.scalar<1||workers.scalar>16)throw DataError("E_RANGE","with_tasks requires1..16 workers");return group.openScope(size_t(workers.scalar));});
        auto child=checked([&]{
          if(stack.size()>=256)throw DataError("E_LIMIT","compiled task call depth exceeds 256");
          auto closure=request.arguments[1];const auto &code=closureCode(closure);
          auto body=std::make_unique<NativeTaskFrame>(code,std::vector<Value>{taskScopeValue(group,scope)},closure);
          body->closingScope=scope;body->parentScope=parent;body->scopeLocation=request.location;body->returnDestination=request.destination;body->depth=stack.size()+1;return body;
        });
        stack.push_back(std::move(*child));continue;
      }
      case TaskRequestKind::Spawn:result=checked([&]{
        const auto &scope=capability(0,Data::TaskScope);auto closure=request.arguments[1];const auto &code=closureCode(closure);
        if(code.parameterCount)throw DataError("E_TASK_STATE","spawn callback must take no arguments");
        ObserverScope trace(observer);return taskTicketValue(group,group.spawn(scope.scope,executeTaskClosure,{},closure),code.resultKind);
      });break;
      case TaskRequestKind::Wait:{
        auto ticket=checked([&]{const auto &task=capability(0,Data::Task);group.requireScope(task.scope);if(task.payloadKind!=request.kind)throw DataError("E_TASK_STATE","wait result schema differs");return task.ticket;});
        auto event=co_await group.await(ticket).at(request.location);result=std::move(event.value);
        checked([&]{if(request.kind!=4&&!kindMatches(result,request.kind))throw DataError("E_TASK_STATE","task returned wrong value kind");});break;
      }
      case TaskRequestKind::ChannelNew:result=checked([&]{
        const auto &scope=capability(0,Data::TaskScope);auto capacity=request.arguments[1];if(capacity.tag!=Value::Integer||capacity.scalar<0||capacity.scalar>65536)throw DataError("E_RANGE","channel capacity must be0..65536");
        return taskChannelValue(group,group.channel(scope.scope,size_t(capacity.scalar)),request.kind);
      });break;
      case TaskRequestKind::Send:{
        auto channel=checked([&]{const auto &pipe=capability(0,Data::Channel);group.requireScope(pipe.scope);if(!kindMatches(request.arguments[1],pipe.payloadKind))throw DataError("E_TASK_STATE","channel send value kind differs");return pipe.channel;});
        auto event=co_await group.send(channel,request.arguments[1]).at(request.location);result=Value(event.present,true);break;
      }
      case TaskRequestKind::Receive:{
        auto channel=checked([&]{const auto &pipe=capability(0,Data::Channel);group.requireScope(pipe.scope);return pipe.channel;});
        auto event=co_await group.receive(channel).at(request.location);
        checked([&]{if(event.present&&!kindMatches(event.value,capability(0,Data::Channel).payloadKind))throw DataError("E_TASK_STATE","channel received wrong value kind");});
        result=channelResult(std::move(event));break;
      }
      case TaskRequestKind::Close:result=checked([&]{const auto &pipe=capability(0,Data::Channel);group.requireScope(pipe.scope);return Value(group.close(pipe.channel),true);});break;
      case TaskRequestKind::Cancel:result=checked([&]{const auto &task=capability(0,Data::Task);group.requireScope(task.scope);return Value(group.cancel(task.ticket),true);});break;
      case TaskRequestKind::CurrentScope:result=checked([&]{return taskScopeValue(group,group.currentScope());});break;
      }
      if(request.destination>=0)checked([&]{current.write(request.destination,std::move(result),current.kinds.at(request.destination));});
    }else throw DataError("E_TASK_STATE","invalid compiled task transition");
  }
  throw DataError("E_TASK_STATE","compiled task exhausted its logical stack");
}
}
namespace {
nexrt::NativeTaskFrame &frame(void *p){if(!p)throw nexrt::DataError("E_TASK_STATE","missing compiled task frame");return *static_cast<nexrt::NativeTaskFrame*>(p);}
void finish(void *p,nexrt::Value value){auto &f=frame(p);if(f.completed)throw nexrt::DataError("E_TASK_STATE","compiled task completed twice");if(f.expectedResult>=0&&f.expectedResult!=4&&!nexrt::kindMatches(value,f.expectedResult))throw nexrt::DataError("E_TASK_STATE","compiled task result kind differs");f.result=std::move(value);f.slots.clear();f.completed=true;}
}
extern "C" {
int64_t nex_task_frame_pc(void *p){auto &f=frame(p);if(f.completed)throw nexrt::DataError("E_TASK_STATE","compiled task already completed");return f.pc;}
void nex_task_frame_set_pc(void *p,int64_t pc){auto &f=frame(p);if(f.completed||pc<0)throw nexrt::DataError("E_TASK_STATE","invalid compiled task program counter");f.pc=pc;}
int64_t nex_task_frame_get_i64(void *p,int64_t id,int64_t kind){return frame(p).read(id,kind).scalar;}
nexrt::Handle *nex_task_frame_get_heap(void *p,int64_t id){return nexrt::makeHandle(frame(p).read(id,3));}
void nex_task_frame_put_i64(void *p,int64_t id,int64_t value,int64_t kind){if(kind<0||kind>2)throw nexrt::DataError("E_TASK_STATE","invalid compiled task scalar kind");frame(p).write(id,nexrt::Value::taggedScalar(value,kind),kind);}
void nex_task_frame_put_heap(void *p,int64_t id,nexrt::Handle *value){if(!value)throw nexrt::DataError("E_TASK_STATE","missing compiled task heap value");frame(p).write(id,nexrt::readHandle(value),3);}
void nex_task_frame_drop(void *p,int64_t id){frame(p).drop(id);}
void nex_task_frame_return_i64(void *p,int64_t value,int64_t kind){if(frame(p).expectedResult==4)throw nexrt::DataError("E_TASK_STATE","compiled task returned unexpected value");if(kind<0||kind>2)throw nexrt::DataError("E_TASK_STATE","invalid compiled task result kind");finish(p,nexrt::Value::taggedScalar(value,kind));}
void nex_task_frame_return_heap(void *p,nexrt::Handle *value){if(frame(p).expectedResult==4)throw nexrt::DataError("E_TASK_STATE","compiled task returned unexpected value");if(!value)throw nexrt::DataError("E_TASK_STATE","missing compiled task result");finish(p,nexrt::readHandle(value));}
void nex_task_frame_return_unit(void *p){auto &f=frame(p);if(f.expectedResult>=0&&f.expectedResult!=4)throw nexrt::DataError("E_TASK_STATE","compiled task returned unexpected unit");finish(p,{});}
void nex_task_frame_call_at(void *p,void *code,nexrt::Handle *closure,nexrt::Handle *args,int64_t destination,int64_t line,const nexrt::NativeSite *site){
  nexrt::hostOperation({line,site},[&]{
    auto &caller=frame(p);
    if(caller.completed||caller.pendingCall)throw nexrt::DataError("E_TASK_STATE","compiled task call is already pending");
    if(caller.depth>=256)throw nexrt::DataError("E_LIMIT","compiled task call depth exceeds 256");
    auto environment=closure?nexrt::readHandle(closure):nexrt::Value{};
    if(closure){if(environment.tag!=nexrt::Value::Object||!environment.object||environment.object->kind!=nexrt::Data::Closure||!environment.object->taskCode)throw nexrt::DataError("E_TASK_STATE","ordinary callable has no compiled task descriptor");if(code&&code!=environment.object->taskCode)throw nexrt::DataError("E_TASK_STATE","compiled task callable descriptor differs");code=const_cast<void*>(environment.object->taskCode);}
    const auto &d=nexrt::checkedCode(code);
    if(destination < -1||(destination<0&&d.resultKind!=4)||(destination>=0&&(size_t(destination)>=caller.slots.size()||caller.kinds[destination]!=d.resultKind)))throw nexrt::DataError("E_TASK_STATE","compiled task call result destination differs");
    auto arguments=nexrt::readHandle(args);if(arguments.tag!=nexrt::Value::Object||!arguments.object||arguments.object->kind!=nexrt::Data::List)throw nexrt::DataError("E_TASK_STATE","compiled task call arguments are not a list");
    auto child=std::make_unique<nexrt::NativeTaskFrame>(d,arguments.object->values,environment);child->returnDestination=destination;caller.pendingCall=std::move(child);
  });
}
nexrt::Handle *nex_task_closure_new_at(void *code,int64_t count,const nexrt::NativeSite *site){
  return nexrt::hostValue({0,site},[&]{const auto &d=nexrt::checkedCode(code);if(count!=d.captureCount)throw nexrt::DataError("E_TASK_STATE","compiled task closure capture count differs");auto data=std::make_shared<nexrt::Data>(nexrt::Data::Closure);data->taskCode=&d;data->values.resize(count);data->names.resize(count);return nexrt::Value(data);});
}
void nex_task_closure_bind_at(nexrt::Handle *closure,void *code,const nexrt::NativeSite *site){
  nexrt::hostOperation({0,site},[&]{const auto &d=nexrt::checkedCode(code);auto value=nexrt::readHandle(closure);if(value.tag!=nexrt::Value::Object||!value.object||value.object->kind!=nexrt::Data::Closure||!value.object->code||value.object->taskCode||value.object->values.size()!=size_t(d.captureCount))throw nexrt::DataError("E_TASK_STATE","invalid compiled task callable binding");value.object->taskCode=&d;});
}
void nex_task_frame_pause_at(void *p,int64_t operation,nexrt::Handle *args,int64_t destination,int64_t kind,int64_t line,const nexrt::NativeSite *site){
  nexrt::hostOperation({line,site},[&]{
    auto &current=frame(p);
    if(current.completed||current.pendingCall||current.pendingRequest||operation<0||operation>int64_t(nexrt::TaskRequestKind::CurrentScope)||kind<0||kind>4||destination < -1||(destination>=0&&size_t(destination)>=current.slots.size()))throw nexrt::DataError("E_TASK_STATE","invalid compiled task request");
    if(!args)throw nexrt::DataError("E_TASK_STATE","missing compiled request arguments");
    auto values=nexrt::readHandle(args);if(values.tag!=nexrt::Value::Object||!values.object||values.object->kind!=nexrt::Data::List)throw nexrt::DataError("E_TASK_STATE","compiled request arguments are not a list");
    static constexpr size_t counts[]={0,2,2,1,2,2,1,1,1,0};if(values.object->values.size()!=counts[operation])throw nexrt::DataError("E_TASK_STATE","compiled request argument count differs");
    current.pendingRequest=nexrt::NativeTaskRequest{nexrt::TaskRequestKind(operation),values.object->values,destination,kind,{line,site}};
  });
}
void nex_task_frame_bad_pc(void *){throw nexrt::DataError("E_TASK_STATE","compiled task program counter is outside its checked continuation");}
}
