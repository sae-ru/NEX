#include "npu-common.h"
#include "npu-broker.inc"
extern "C" nex_ffi_status npu_matmul_bytes(const nex_ffi_api_v1 *api,nex_ffi_call call,const nex_ffi_ref *args,uint64_t count,nex_ffi_ref *out,void*) {
 try {
  if(count!=5)return NEX_FFI_ARGUMENT;
  FFI(api->poll(call));
  std::array<int64_t,3> shape{};
  for(size_t i=0;i<3;++i)FFI(api->get_i64(call,args[i+2],&shape[i]));
  auto [m,k,n]=shape;
  if(m<1||m>32||k<32||k>128||k%32||n<32||n>128||n%32)
   return error(api,call,out,"E_SHAPE","matmul requires 1<=M<=32; K,N multiples of32 in32..128");
  // Products are bounded before they are evaluated. Exact int8 products fit int32.
  std::array<uint64_t,2> sizes{uint64_t(m*k),uint64_t(k*n)};
  std::vector<uint8_t> payload;
  for(auto value:shape)for(int j=0;j<4;++j)payload.push_back(uint8_t(uint32_t(value)>>(8*j)));
  for(size_t i=0;i<2;++i) {
   uint64_t length=0;FFI(api->byte_size(call,args[i],&length));
   if(length!=sizes[i])return error(api,call,out,"E_INPUT_SIZE","row-major input length disagrees with shape");
   const auto offset=payload.size();payload.resize(offset+length);uint64_t copied=0;
   FFI(api->copy_bytes(call,args[i],0,payload.data()+offset,length,&copied));
   if(copied!=length)return NEX_FFI_INTERNAL;
  }
  std::vector<uint8_t> data;
  {std::lock_guard lock(acceleratorMutex);data=isolatedNPU(payload,uint64_t(m*n)*4,api,call);}
  FFI(api->poll(call));
  nex_ffi_ref result=0;FFI(api->make_bytes(call,data.data(),data.size(),&result));
  return api->make_success(call,result,out);
 }catch(const HostStatus &e){return e.value;}
 catch(const Failure &e){return error(api,call,out,e.code,e.what());}
 catch(const std::exception &e){return error(api,call,out,"E_ACCELERATOR",e.what());}
 catch(...){return NEX_FFI_INTERNAL;}
}
NEX_FFI_MODULE_EXPORT const nex_ffi_module_v1 *nex_ffi_module_entry(uint32_t abi,uint32_t size) {
 static const nex_ffi_export_v1 exports[]={{sizeof(nex_ffi_export_v1),0,"npu_matmul_bytes",NEX_NPU_SIGNATURE,npu_matmul_bytes,nullptr}};
 static const nex_ffi_module_v1 module={NEX_FFI_MODULE_ABI_V1,sizeof(nex_ffi_module_v1),1,sizeof(nex_ffi_export_v1),exports};
 return abi==NEX_FFI_ABI_V1&&size>=sizeof(nex_ffi_api_v1)?&module:nullptr;
}
