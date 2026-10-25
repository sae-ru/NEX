#include "nex/task_frontend.h"
#include <functional>

namespace nex {
const char *programLanguage(SourceLanguage language){
  switch(language){
  case SourceLanguage::Language018:return "0.18";
  case SourceLanguage::Tasks019:return "0.19";
  case SourceLanguage::TaskFiles020:return "0.20";
  case SourceLanguage::OwnedResources021:return "0.21";
  case SourceLanguage::TaskForeign022:return "0.22";
  case SourceLanguage::TaskWrites023:return "0.23";
  case SourceLanguage::TaskStreams024:return "0.24";
  }
  throw Error("E_LANGUAGE_VERSION","unknown checked program source language");
}
const char *programLanguage(const Program &program){return programLanguage(program.sourceLanguage);}
bool isPublicTaskLanguage(const Program &program){
  return program.sourceLanguage==SourceLanguage::Tasks019||program.sourceLanguage==SourceLanguage::TaskFiles020||program.sourceLanguage==SourceLanguage::OwnedResources021||program.sourceLanguage==SourceLanguage::TaskForeign022||program.sourceLanguage==SourceLanguage::TaskWrites023||program.sourceLanguage==SourceLanguage::TaskStreams024;
}
bool supportsTaskFileReads(const Program &program){return program.sourceLanguage==SourceLanguage::TaskFiles020||program.sourceLanguage==SourceLanguage::OwnedResources021||program.sourceLanguage==SourceLanguage::TaskForeign022||program.sourceLanguage==SourceLanguage::TaskWrites023||program.sourceLanguage==SourceLanguage::TaskStreams024;}
bool supportsTaskFileWrites(const Program &program){return program.sourceLanguage==SourceLanguage::TaskWrites023||program.sourceLanguage==SourceLanguage::TaskStreams024;}
bool supportsTaskFileStreams(const Program &program){return program.sourceLanguage==SourceLanguage::TaskStreams024;}
bool taskFileWriteOperation(const std::string &operation){return operation=="file_write_text"||operation=="file_write_bytes";}
bool supportsTaskForeignCalls(const Program &program){return program.sourceLanguage==SourceLanguage::TaskForeign022||program.sourceLanguage==SourceLanguage::TaskWrites023||program.sourceLanguage==SourceLanguage::TaskStreams024;}
bool usesTaskEffects(const Program &program,const std::string &entry){
  std::vector<std::string> pending{entry};std::set<std::string> seen;
  while(!pending.empty()){
    auto name=std::move(pending.back());pending.pop_back();
    const auto &function=program.function(name);if(!seen.insert(function.name).second)continue;
    if(function.effects.contains("task"))return true;
    pending.insert(pending.end(),function.dependencies.begin(),function.dependencies.end());
  }
  return false;
}
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
  if(program.taskPrototype&&!isPublicTaskLanguage(program))throw Error("E_TASK_UNIMPLEMENTED",
    std::string(operation)+" requires continuation lowering and an explicit language migration; private task typing is not an executable language0.18 program");
}
void rejectUnarchivedTasks(const Program &program,const char *operation){
  if(isPublicTaskLanguage(program)){
    if(!program.taskPrototype)throw Error("E_TASK_STATE","public task language requires its checked task frontend");
    for(const auto &function:program.functions)if(!function.checked&&!function.traitSignature)
      throw Error("E_TASK_STATE","public task language contains an unchecked function",function.span);
    return;
  }
  rejectUnloweredTasks(program,operation);
}
}
