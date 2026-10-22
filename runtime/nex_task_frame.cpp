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
TaskBody executeTaskFrame(TaskGroup &group,NativeTaskFrame frame){
  while(!frame.completed){
    auto transition=frame.step(&frame);
    if(transition==0){if(!frame.completed)throw DataError("E_TASK_STATE","compiled task returned without completing");break;}
    if(transition!=1||frame.completed)throw DataError("E_TASK_STATE","invalid compiled task transition");
    co_await group.yield();
  }
  co_return frame.result;
}
}
namespace {
nexrt::NativeTaskFrame &frame(void *p){if(!p)throw nexrt::DataError("E_TASK_STATE","missing compiled task frame");return *static_cast<nexrt::NativeTaskFrame*>(p);}
void finish(void *p,nexrt::Value value){auto &f=frame(p);if(f.completed)throw nexrt::DataError("E_TASK_STATE","compiled task completed twice");f.result=std::move(value);f.slots.clear();f.completed=true;}
}
extern "C" {
int64_t nex_task_frame_pc(void *p){auto &f=frame(p);if(f.completed)throw nexrt::DataError("E_TASK_STATE","compiled task already completed");return f.pc;}
void nex_task_frame_set_pc(void *p,int64_t pc){auto &f=frame(p);if(f.completed||pc<0)throw nexrt::DataError("E_TASK_STATE","invalid compiled task program counter");f.pc=pc;}
int64_t nex_task_frame_get_i64(void *p,int64_t id,int64_t kind){return frame(p).read(id,kind).scalar;}
nexrt::Handle *nex_task_frame_get_heap(void *p,int64_t id){return nexrt::makeHandle(frame(p).read(id,3));}
void nex_task_frame_put_i64(void *p,int64_t id,int64_t value,int64_t kind){if(kind<0||kind>2)throw nexrt::DataError("E_TASK_STATE","invalid compiled task scalar kind");frame(p).write(id,nexrt::Value::taggedScalar(value,kind),kind);}
void nex_task_frame_put_heap(void *p,int64_t id,nexrt::Handle *value){if(!value)throw nexrt::DataError("E_TASK_STATE","missing compiled task heap value");frame(p).write(id,nexrt::readHandle(value),3);}
void nex_task_frame_drop(void *p,int64_t id){frame(p).drop(id);}
void nex_task_frame_return_i64(void *p,int64_t value,int64_t kind){if(kind<0||kind>2)throw nexrt::DataError("E_TASK_STATE","invalid compiled task result kind");finish(p,nexrt::Value::taggedScalar(value,kind));}
void nex_task_frame_return_heap(void *p,nexrt::Handle *value){if(!value)throw nexrt::DataError("E_TASK_STATE","missing compiled task result");finish(p,nexrt::readHandle(value));}
void nex_task_frame_return_unit(void *p){finish(p,{});}
void nex_task_frame_bad_pc(void *){throw nexrt::DataError("E_TASK_STATE","compiled task program counter is outside its checked continuation");}
}
