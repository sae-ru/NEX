#include "nex_task_application.h"
#include <array>
#include <cstdio>
#include <cstdlib>
#include <string>

namespace {
void require(bool value){if(!value)std::abort();}
int64_t successful(void *frame){
  if(nex_task_frame_pc(frame)==0){
    auto retained=nexrt::makeHandle(nexrt::Value(nexrt::string("retained🧠")));
    nex_task_frame_put_heap(frame,0,retained);nex_release(retained);
    nex_task_frame_set_pc(frame,1);return 1;
  }
  nex_task_frame_return_i64(frame,42,0);return 0;
}
int64_t failed(void *frame){
  if(nex_task_frame_pc(frame)==0){
    auto retained=nexrt::makeHandle(nexrt::Value(nexrt::string("retained🧠")));
    nex_task_frame_put_heap(frame,0,retained);nex_release(retained);
    nex_task_frame_set_pc(frame,1);return 1;
  }
  // Worker RequestScope must reclaim this resume-local handle on the trap.
  (void)nexrt::makeHandle(nexrt::Value(nexrt::string("temporary🧠")));
  throw nexrt::Trap("E_ITEM","application task failure",7);
}
int64_t unit(void *frame){nex_task_frame_return_unit(frame);return 0;}
int64_t invalid(void *frame){nex_task_frame_return_heap(frame,nullptr);return 0;}
void clean(){require(!nexrt::inRequestScope());require(nexrt::liveObjects==0);nex_runtime_finish();}
const nexrt::TaskCodeDescriptor *selected=nullptr;
const char *expected=nullptr;
int64_t applicationEntry(int64_t,const char *const *){
  bool caught=false;try{nex_task_application_execute(selected);}catch(const nexrt::Trap &trap){require(trap.code==expected);caught=true;}require(caught);return 0;
}
void rejects(const char *code,const nexrt::TaskCodeDescriptor *descriptor){
  selected=descriptor;expected=code;
  require(nex_application_run(reinterpret_cast<void*>(applicationEntry),0,nullptr)==0);clean();
}
}
int main(){
  std::array<int64_t,1> kinds{3};
  nexrt::TaskCodeDescriptor descriptor{successful,kinds.data(),nullptr,nullptr,nullptr,nexrt::taskCodeABI,1,0,0,0};
  for(int i=0;i<3;++i){require(nex_task_application_execute(&descriptor)==42);clean();}
  descriptor.step=failed;rejects("E_ITEM",&descriptor);
  descriptor.step=unit;descriptor.resultKind=4;require(nex_task_application_execute(&descriptor)==0);clean();
  descriptor.step=invalid;descriptor.resultKind=0;rejects("E_TASK_STATE",&descriptor);
  descriptor.parameterCount=1;rejects("E_ENTRY",&descriptor);descriptor.parameterCount=0;
  descriptor.resultKind=3;rejects("E_ENTRY",&descriptor);descriptor.resultKind=0;
  descriptor.abi=0;rejects("E_TASK_STATE",&descriptor);
  rejects("E_ENTRY",nullptr);
  std::puts("task application runtime: success, unit, trap and rejected ABI cleanup passed");
}
