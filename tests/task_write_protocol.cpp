#include "nex_task_frame.h"
#include <iostream>
#include <stdexcept>
using namespace nexrt;
namespace {
int64_t step(void *){return 0;}
void require(bool value){if(!value)throw std::runtime_error("write protocol invariant failed");}
void rejected(TaskCodeDescriptor code){try{NativeTaskFrame frame(code,{},Value{});}catch(const DataError &e){require(e.code=="E_TASK_STATE");return;}throw std::runtime_error("invalid write descriptor accepted");}
}
static_assert(int64_t(TaskRequestKind::FileReadText)==10&&int64_t(TaskRequestKind::FileReadBytes)==11&&int64_t(TaskRequestKind::Foreign)==12);
static_assert(int64_t(TaskRequestKind::FileWriteText)==13&&int64_t(TaskRequestKind::FileWriteBytes)==14);
static_assert(sizeof(TaskCodeDescriptor)==88&&offsetof(TaskCodeDescriptor,abi)==40&&taskProviderRequirementsMask==31&&taskCodeRequirementsMask==255);
int main(){try{
  require(validTaskCodeRequirements(taskCodeABI,255));require(!validTaskCodeRequirements(taskCodeABI,taskCodeFileWrite));
  require(validTaskCodeRequirements(taskCodeWriteABI,1023));require(!validTaskCodeRequirements(taskCodeWriteABI,1024));
  require(!validTaskCodeRequirements(taskCodeTypedSourceExceptionABI+1,0));require(!validTaskCodeRequirements(taskCodeWriteABI,-1));
  TaskCodeDescriptor d{step,nullptr,nullptr,nullptr,nullptr,taskCodeWriteABI,0,0,0,0,7|taskCodeFileWrite|taskCodeImageFileWrite};
  {NativeTaskFrame frame(d,{},Value{});require(bool(frame.requirements&taskCodeFileWrite));}
  auto invalid=d;invalid.abi=taskCodeABI;rejected(invalid);
  for(auto missing:{taskCodeDeclaredTask,taskCodeServer,taskCodeDeclaredFs}){invalid=d;invalid.requirements&=~missing;rejected(invalid);}
  invalid=d;invalid.requirements|=1024;rejected(invalid);
  invalid=d;invalid.abi=taskCodeABI;invalid.requirements=7|taskCodeFileRead;{NativeTaskFrame frame(invalid,{},Value{});}
  std::cout<<"{\"ok\":true,\"cases\":13,\"retained_ABI3_mask31\":true,\"write_ABI4\":true}\n";return 0;
}catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 1;}}
