#include "nex/task_frontend.h"
#include <functional>

namespace nex {
const std::set<std::string> &taskBuiltins(){
  static const std::set<std::string> names={"with_tasks","task_spawn","task_wait",
    "channel_new","task_send","task_recv","task_close","task_cancel",
    "task_yield","current_task_scope"};
  return names;
}
bool containsTaskAuthority(const Program &program,const Type &type){
  std::set<std::string> seen;
  std::function<bool(const Type&)> visit=[&](const Type &value){
    if(value.kind==Type::Task||value.kind==Type::Channel||value.kind==Type::TaskScope)return true;
    if(value.element&&visit(*value.element))return true;
    for(const auto &argument:value.arguments)if(visit(argument))return true;
    if(value.kind==Type::Record&&program.hasStructure(value.name)&&seen.insert(value.name).second){
      const auto &record=program.structure(value.name);
      for(const auto &argument:record.typeArguments)if(visit(argument))return true;
      for(auto field:record.members())if(visit(field->type))return true;
    }
    return false;
  };
  return visit(type);
}
void rejectUnloweredTasks(const Program &program,const char *operation){
  if(program.taskPrototype)throw Error("E_TASK_UNIMPLEMENTED",
    std::string(operation)+" requires continuation lowering and an explicit language migration; private task typing is not an executable language0.18 program");
}
}
