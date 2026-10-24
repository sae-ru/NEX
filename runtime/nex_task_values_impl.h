// Included inside namespace nexrt, after TaskGroup::Impl is complete.
const TaskData &taskData(const Value &value,Data::Kind kind){
  if(value.tag!=Value::Object||!value.object||value.object->kind!=kind||
     value.object->taskOwnerFamily()!=Data::TaskOwnerFamily::Native)
    throw DataError("E_TASK_VALUE","expected an owned task capability");
  return static_cast<const TaskData&>(*value.object);
}
struct TaskValueAccess {
  static Value scope(TaskGroup &group,const TaskGroup::Scope &scope){
    group.requireScope(scope);auto index=group.scopeIndex(scope);std::lock_guard lock(group.impl->mutex);
    auto &cached=group.impl->regions[index]->capability;
    auto value=cached.lock();if(!value){value=std::shared_ptr<Data>(new TaskData(scope,{}, {},Data::TaskScope,-1));cached=value;}
    return Value(std::move(value));
  }
  static Value ticket(TaskGroup &group,const TaskGroup::Ticket &ticket,int64_t kind){
    if(kind<0||kind>4)throw DataError("E_TASK_STATE","invalid compiled task outcome kind");
    group.impl->require();auto index=group.taskIndex(ticket);std::lock_guard lock(group.impl->mutex);auto &job=*group.impl->jobs[index];
    if(job.memberScope==TaskGroup::none)throw DataError("E_TASK_SCOPE","source task requires a logical owner scope");
    auto value=job.capability.lock();if(!value){value=std::shared_ptr<Data>(new TaskData(TaskGroup::Scope(group.impl,job.memberScope),ticket,{},Data::Task,kind));job.capability=value;}
    if(static_cast<const TaskData&>(*value).payloadKind!=kind)throw DataError("E_TASK_STATE","compiled task outcome schema differs");return Value(std::move(value));
  }
  static Value channel(TaskGroup &group,const TaskGroup::Channel &channel,int64_t kind){
    if(kind<0||kind>3)throw DataError("E_TASK_STATE","invalid compiled channel payload kind");
    group.impl->require();auto index=group.channelIndex(channel);std::lock_guard lock(group.impl->mutex);auto &pipe=*group.impl->pipes[index];
    if(pipe.scope==TaskGroup::none)throw DataError("E_TASK_SCOPE","source channel requires a logical owner scope");
    auto value=pipe.capability.lock();if(!value){value=std::shared_ptr<Data>(new TaskData(TaskGroup::Scope(group.impl,pipe.scope),{},channel,Data::Channel,kind));pipe.capability=value;}
    if(static_cast<const TaskData&>(*value).payloadKind!=kind)throw DataError("E_TASK_STATE","compiled channel payload schema differs");return Value(std::move(value));
  }
};
Value taskScopeValue(TaskGroup &group,const TaskGroup::Scope &scope){return TaskValueAccess::scope(group,scope);}
Value taskTicketValue(TaskGroup &group,const TaskGroup::Ticket &ticket,int64_t kind){return TaskValueAccess::ticket(group,ticket,kind);}
Value taskChannelValue(TaskGroup &group,const TaskGroup::Channel &channel,int64_t kind){return TaskValueAccess::channel(group,channel,kind);}
std::vector<ExternalResource> collectTaskSnapshot(TaskGroup &group,const Value &value,const TaskGroup::Scope &target){
  std::vector<Value> pending{value};std::unordered_set<const Data*> seen;size_t members=1;
  std::vector<ExternalResource> resources;std::unordered_set<uint64_t> resourceIds;
  while(!pending.empty()){
    auto next=std::move(pending.back());pending.pop_back();
    if(next.tag==Value::Floating){(void)next.floating();continue;}
    if(next.tag==Value::Integer)continue;
    if(next.tag==Value::Boolean){if(next.scalar<0||next.scalar>1)throw DataError("E_TASK_VALUE","invalid task boolean");continue;}
    if(next.tag!=Value::Object||!next.object)throw DataError("E_TASK_VALUE","task snapshot has an invalid value");
    if(!seen.insert(next.object.get()).second)continue;
    if(seen.size()>parallelMaximumNodes)throw DataError("E_LIMIT","task snapshot exceeds its object limit");
    if(seen.size()%64==0)pollHostOperation(0);
    auto kind=next.object->kind;
    if(kind==Data::External){const auto &owner=externalResource(next.object);
      if(resourceIds.insert(owner.identity()).second){
        if(resources.size()==4096)throw DataError("E_RESOURCE_REGION_LIMIT","task snapshot exceeds4096 distinct resource owners");
        resources.push_back(owner);
      }
    }
    if(kind==Data::File)throw DataError("E_TASK_VALUE","task snapshot cannot contain file authority");
    if(kind==Data::TaskScope||kind==Data::Task||kind==Data::Channel){
      const auto &cap=taskData(next,kind);group.requireScope(cap.scope);
      if(target.empty()||!group.scopeContains(cap.scope,target))throw DataError("E_TASK_SCOPE","task capability escapes its logical owner scope");
    }
    if(next.object->values.size()>parallelMaximumNodes-members)throw DataError("E_LIMIT","task snapshot exceeds its member limit");
    members+=next.object->values.size();pending.insert(pending.end(),next.object->values.begin(),next.object->values.end());
  }
  return resources;
}
void validateTaskSnapshot(TaskGroup &group,const Value &value,const TaskGroup::Scope &target,bool scopeReturn){
  auto resources=collectTaskSnapshot(group,value,target);group.transferSourceResources(resources,target,scopeReturn);
}
