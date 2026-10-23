#include "common.h"
std::mutex modelMutex;
#include "model-broker.inc"

static std::vector<std::vector<uint8_t>> dispatch(const std::vector<std::vector<uint8_t>>&inputs,uint32_t device,const nex_ffi_api_v1*a,nex_ffi_call call){
 std::unique_lock<std::mutex> lock(modelMutex,std::defer_lock);
 while(!lock.try_lock()){auto status=a->poll(call);if(status)throw HostStatus{status};std::this_thread::sleep_for(std::chrono::milliseconds(2));}
 auto status=a->poll(call);if(status)throw HostStatus{status};
 auto frame=isolatedModel(inputs,device,a,call);size_t cursor=0;
 if(get32(frame,cursor)!=1||get32(frame,cursor)!=config().at("outputs").size())throw Failure("E_MODEL_PROTOCOL","unexpected model output version/count");
 std::vector<std::vector<uint8_t>> output;output.reserve(config().at("outputs").size());
 for(const auto&port:config().at("outputs")){
  auto n=get32(frame,cursor);if(n!=tensorBytes(port)||cursor>frame.size()||n>frame.size()-cursor)throw Failure("E_MODEL_PROTOCOL","unexpected model output byte count");
  output.emplace_back(frame.begin()+cursor,frame.begin()+cursor+n);cursor+=n;validateBytes(output.back(),port);
 }
 if(cursor!=frame.size())throw Failure("E_MODEL_PROTOCOL","trailing model output bytes");return output;
}
extern "C" nex_ffi_status model_run(const nex_ffi_api_v1*a,nex_ffi_call call,const nex_ffi_ref*args,uint64_t count,nex_ffi_ref*out,void*){
 try{
  if(count!=2)return NEX_FFI_ARGUMENT;FFI(a->poll(call));validateConfiguration();int64_t device=-1;FFI(a->get_i64(call,args[1],&device));if(device<0||device>1)return failure(a,call,out,"E_MODEL_DEVICE","device must be0 CPU or1 Zhouyi NPU");
  uint64_t n=0;FFI(a->child_count(call,args[0],&n));if(n!=config().at("inputs").size())return failure(a,call,out,"E_MODEL_PORT","input count disagrees with prepared model");
  std::vector<std::vector<uint8_t>> inputs;inputs.reserve(n);
  for(uint64_t i=0;i<n;++i){nex_ffi_ref child=0;uint64_t size=0,copied=0;FFI(a->child(call,args[0],i,&child));FFI(a->byte_size(call,child,&size));if(size!=tensorBytes(config().at("inputs")[i]))return failure(a,call,out,"E_MODEL_SIZE","input bytes disagree with prepared port");inputs.emplace_back(size);FFI(a->copy_bytes(call,child,0,inputs.back().data(),size,&copied));if(copied!=size)return NEX_FFI_INTERNAL;validateBytes(inputs.back(),config().at("inputs")[i]);}
  if(device==1&&!config().at("zhouyi").get<bool>())return failure(a,call,out,"E_MODEL_UNSUPPORTED","this pinned model bundle has no Zhouyi provider binding");
  auto output=dispatch(inputs,uint32_t(device),a,call);FFI(a->poll(call));std::vector<nex_ffi_ref> values;values.reserve(output.size());
  for(const auto&v:output){nex_ffi_ref ref=0;FFI(a->make_bytes(call,v.data(),v.size(),&ref));values.push_back(ref);}
  nex_ffi_ref result=0;FFI(a->make_list(call,values.data(),values.size(),&result));return a->make_success(call,result,out);
 }catch(const HostStatus&e){return e.value;}catch(const Failure&e){return failure(a,call,out,e.code,e.what());}catch(const std::exception&e){return failure(a,call,out,"E_MODEL_ADAPTER",e.what());}catch(...){return NEX_FFI_INTERNAL;}
}
NEX_FFI_MODULE_EXPORT const nex_ffi_module_v1*nex_ffi_module_entry(uint32_t abi,uint32_t size){
 static const nex_ffi_export_v1 exports[]={{sizeof(nex_ffi_export_v1),0,"model_run",NEX_MODEL_SIGNATURE,model_run,nullptr}};
 static const nex_ffi_module_v1 module={NEX_FFI_MODULE_ABI_V1,sizeof(nex_ffi_module_v1),1,sizeof(nex_ffi_export_v1),exports};return abi==NEX_FFI_ABI_V1&&size>=sizeof(nex_ffi_api_v1)?&module:nullptr;
}
