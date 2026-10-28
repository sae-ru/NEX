#include "nex_task_frame.h"
#include <iostream>
#include <stdexcept>
using namespace nexrt;
int64_t step(void*){return 0;}
void require(bool b){if(!b)throw std::runtime_error("stream protocol invariant failed");}
static_assert(sizeof(TaskCodeDescriptor)==88&&offsetof(TaskCodeDescriptor,abi)==40);
static_assert(taskProviderRequirementsMask==31&&taskWriteProviderRequirementsMask==799);
static_assert(int64_t(TaskRequestKind::FileWriteBytes)==14&&int64_t(TaskRequestKind::FileOpenRead)==15&&int64_t(TaskRequestKind::FileIsOpen)==24);
int main(){try{
 size_t cases=0;auto check=[&](bool b){require(b);++cases;};
 check(validTaskCodeRequirements(taskCodeStreamABI,4095));check(!validTaskCodeRequirements(taskCodeStreamABI,4096));
 check(!validTaskCodeRequirements(taskCodeStreamABI,-1));check(!validTaskCodeRequirements(taskCodeWriteABI,taskCodeFileStream));
 check(!validTaskCodeRequirements(taskCodeABI,taskCodeFileStream));check(!validTaskCodeRequirements(taskCodeSourceExceptionABI+1,0));
 check(taskCodeSourceExceptionABI==INT64_C(0x4e45585400000006));
 check(validTaskCodeRequirements(taskCodeSourceExceptionABI,taskCodeStreamRequirementsMask|taskCodeDeclaredThrow));
 check(!validTaskCodeRequirements(taskCodeSourceExceptionABI,8192));check(!validTaskCodeRequirements(taskCodeSourceExceptionABI,-1));
 check(sourceExceptionTaskABI(taskCodeSourceExceptionABI)&&fileStreamTaskABI(taskCodeSourceExceptionABI));
 int64_t kinds[]={3};TaskCodeDescriptor code{step,kinds,nullptr,nullptr,nullptr,taskCodeStreamABI,1,0,0,0,7|taskCodeFileStream|taskCodeImageFileStream};
 {NativeTaskFrame frame(code,{},Value{});check(frame.abi==taskCodeStreamABI&&bool(frame.requirements&taskCodeFileStream));}
 auto reject=[&](TaskCodeDescriptor d){try{NativeTaskFrame frame(d,{},Value{});}catch(const DataError &e){check(e.code=="E_TASK_STATE");return;}throw std::runtime_error("invalid stream descriptor accepted");};
 for(auto absent:{taskCodeDeclaredTask,taskCodeServer,taskCodeDeclaredFs}){auto d=code;d.requirements&=~absent;reject(d);}
 for(auto abi:{taskCodeABI,taskCodeWriteABI}){auto d=code;d.abi=abi;reject(d);}
 RequestScope request;auto values=std::make_shared<Data>(Data::List);values->values={Value(string("never-opened"))};auto *arguments=makeHandle(Value(values));
 auto rejectedPause=[&](TaskCodeDescriptor d,int64_t operation,int64_t kind){
  NativeTaskFrame frame(d,{},Value{});
  try{nex_task_frame_pause_at(&frame,operation,arguments,0,kind,1,nullptr);}
  catch(const Trap &e){check(e.code=="E_TASK_STATE"&&!frame.pendingRequest);return;}
  throw std::runtime_error("invalid stream request accepted");
 };
 auto old=code;old.abi=taskCodeWriteABI;old.requirements=7|taskCodeFileWrite;
 rejectedPause(old,int64_t(TaskRequestKind::FileOpenRead),3);
 rejectedPause(code,int64_t(TaskRequestKind::FileClose),3);
 rejectedPause(code,int64_t(TaskRequestKind::FileIsOpen)+1,3);
 rejectedPause(code,int64_t(TaskRequestKind::FileRead),3); // Requires two actual operands.
 {NativeTaskFrame frame(code,{},Value{});nex_task_frame_pause_at(&frame,int64_t(TaskRequestKind::FileOpenRead),arguments,0,3,1,nullptr);check(frame.pendingRequest&&frame.pendingRequest->operation==TaskRequestKind::FileOpenRead);}
 std::cout<<"{\"ok\":true,\"stream_protocol_cases\":"<<cases<<",\"retained_ABI3_ABI4_strict\":true}\n";return 0;
}catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 1;}}
