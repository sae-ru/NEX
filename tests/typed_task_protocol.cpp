#include "nex_task_application.h"
#include <iostream>
#include <map>
#include <mutex>
#include <stdexcept>

using namespace nexrt;
namespace {
std::mutex allocationMutex;
std::map<const void *, int> allocations;
unsigned checks=0;
const std::string key(64,'a');
std::weak_ptr<Data> payloadOwner;
void require(bool value,const char *message){++checks;if(!value)throw std::runtime_error(message);}
int64_t leafStep(void *frame){
  if(!nex_task_frame_pc(frame)){nex_task_frame_set_pc(frame,1);return 1;}
  auto data=std::make_shared<Data>(Data::List);data->values={Value(int64_t(42))};
  payloadOwner=data;
  NativeSourceException error("Problem","typed source error","original-source-site",37,
      std::make_shared<const SourceErrorPayload>(key,Value(std::move(data))));
  auto packet=makeSourceErrorHandle(error);
  nex_task_frame_source_packet_raise_at(frame,packet,nullptr);nex_release(packet);
  return 4;
}
const TaskCodeDescriptor leaf{leafStep,nullptr,nullptr,nullptr,nullptr,
    taskCodeTypedSourceExceptionABI,0,0,0,4,taskCodeDeclaredTask|taskCodeDeclaredThrow};
int64_t rootStep(void *frame){
  switch(nex_task_frame_pc(frame)){
    case 0:{
      nex_task_frame_handler_push_at(frame,2,0,nullptr);
      nex_task_frame_set_pc(frame,1);
      auto args=makeHandle(Value(std::make_shared<Data>(Data::List)));
      nex_task_frame_call_at(frame,const_cast<TaskCodeDescriptor*>(&leaf),nullptr,args,-1,0,nullptr);
      nex_release(args);return 2;
    }
    case 1:throw std::runtime_error("typed leaf unexpectedly returned");
    case 2:
      nex_task_frame_source_enter_at(frame,nullptr);
      nex_task_frame_set_pc(frame,3);return 1;
    case 3:{
      auto packet=nex_task_frame_source_packet_at(frame,nullptr);
      auto error=readSourceErrorHandle(packet);nex_release(packet);
      require(error.line==37&&error.source=="original-source-site","typed source position lost across resumed call");
      require(error.payload&&error.payload->getObject(key,Data::List).object==payloadOwner.lock(),"typed payload ownership or key changed");
      auto value=error.payload->getObject(key,Data::List).object->values.at(0).scalar;
      nex_task_frame_source_end_at(frame,nullptr);
      nex_task_frame_return_i64(frame,value,0);return 0;
    }
  }
  throw std::runtime_error("invalid protocol probe PC");
}
int64_t simpleStep(void *frame){nex_task_frame_return_i64(frame,42,0);return 0;}
template<class F>void rejected(F action){
  try{action();}catch(const Trap &e){require(e.code=="E_TASK_STATE","unexpected cohort rejection code");return;}
  throw std::runtime_error("incompatible task cohort accepted");
}
void empty(){
  require(liveObjects.load()==0,"task packet retained a managed value");
  std::lock_guard guard(allocationMutex);require(allocations.empty(),"task packet retained a physical handle/value allocation");
}
}
extern "C" void nex_profile_enter(const char*,const char*,int64_t,const char*){}
extern "C" void nex_profile_leave(){}
extern "C" void nex_profile_unwind(){}
extern "C" void nex_profile_allocation(const void *p,size_t,int pool){
  std::lock_guard guard(allocationMutex);
  if(!allocations.emplace(p,pool).second)throw std::runtime_error("duplicate allocation");
}
extern "C" void nex_profile_free(const void *p){
  std::lock_guard guard(allocationMutex);
  if(allocations.erase(p)!=1)throw std::runtime_error("unknown allocation");
}
int main(){try{
  static_assert(sizeof(TaskCodeDescriptor)==88&&offsetof(TaskCodeDescriptor,abi)==40);
  for(auto workers:{1u,4u}){
    TaskCodeDescriptor root{rootStep,nullptr,nullptr,nullptr,nullptr,taskCodeTypedSourceExceptionABI,0,0,0,0,taskCodeDeclaredTask};
    require(executeTaskApplication(root,{10000,10000,workers},{})==42,"public typed application did not catch its resumed child error");
    require(payloadOwner.expired(),"resumed catch retained its original payload");empty();
    const char *arguments[]={"typed-task-protocol","--nex-task-workers",workers==1?"1":"4"};
    require(nex_task_application_execute_limits(&root,3,arguments,10000,10000,workers)==42,
        "ordinary compiled application thunk rejected its typed cohort");
    require(payloadOwner.expired(),"compiled application thunk retained its typed payload");empty();
  }
  for(auto abi:{taskCodeABI,taskCodeWriteABI,taskCodeStreamABI,taskCodeSourceExceptionABI}){
    TaskCodeDescriptor old{simpleStep,nullptr,nullptr,nullptr,nullptr,abi,0,0,0,0,taskCodeDeclaredTask};
    require(executeTaskApplication(old,{10000,10000,1},{})==42,"retained application cohort changed");empty();
  }
  for(auto abi:{taskCodeExceptionPrototypeABI,taskCodeExceptionHostPrototypeABI,
                taskCodeTypedErrorDevelopmentABI,taskCodeTypedAuthorityDevelopmentABI}){
    TaskCodeDescriptor experimental{simpleStep,nullptr,nullptr,nullptr,nullptr,abi,0,0,0,0,taskCodeDeclaredTask};
    {
      RequestScope request;
      rejected([&]{(void)executeTaskApplication(experimental,{10000,10000,1},{});});
    }empty();
    require(executeSourceExceptionTaskApplication(experimental,{10000,10000,1},{})==42,
        "explicit retained experimental entry changed");empty();
  }
  for(auto other:{taskCodeABI,taskCodeWriteABI,taskCodeStreamABI,taskCodeSourceExceptionABI,
                 taskCodeExceptionPrototypeABI,taskCodeExceptionHostPrototypeABI,
                 taskCodeTypedErrorDevelopmentABI,taskCodeTypedAuthorityDevelopmentABI}){
    for(bool reverse:{false,true}){
      RequestScope scope;
      TaskCodeDescriptor parent{simpleStep,nullptr,nullptr,nullptr,nullptr,
          reverse?other:taskCodeTypedSourceExceptionABI,0,0,0,4,taskCodeDeclaredTask};
      auto child=parent;child.abi=reverse?taskCodeTypedSourceExceptionABI:other;
      NativeTaskFrame frame(parent,{},{});
      rejected([&]{nex_task_frame_call_at(&frame,&child,nullptr,nullptr,-1,0,nullptr);});
      require(!frame.pendingCall&&!frame.pendingSource,"cohort rejection changed the caller");
    }
    empty();
  }
  {
    RequestScope scope;
    auto legacy=leaf;legacy.abi=taskCodeSourceExceptionABI;
    NativeTaskFrame frame(legacy,{},{});
    frame.pendingSource=std::make_shared<const NativeSourceException>("old","legacy","",1);
    rejected([&]{nex_task_frame_source_enter_at(&frame,nullptr);});
    require(bool(frame.pendingSource)&&frame.caughtSource.empty(),"typed helper modified the legacy packet on rejection");
  }empty();
  for(auto invalid:{INT64_C(0),INT64_C(-1),taskCodeTypedSourceExceptionABI+1}){
    require(!validTaskCodeRequirements(invalid,0),"unknown task cohort accepted");
  }
  std::cout<<"{\"ok\":true,\"checks\":"<<checks<<",\"descriptor_abi\":7,\"resumed_calls\":4,\"compiled_C_entry_runs\":2,\"cross_cohort_rejections\":16,\"private_entry_rejections\":4,\"private_entry_retained_runs\":4,\"physical_cleanup\":true}\n";
  return 0;
}catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 1;}}
