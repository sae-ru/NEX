#include "nex_ffi_module.h"
#include "ffi_marker.h"
#include <fcntl.h>
#include <stdlib.h>
#include <unistd.h>
static void mark(char event){nex_test_marker("NEX_FOREIGN_TEST_MARKER",event);}
__attribute__((constructor)) static void initialized(void){mark('I');}
__attribute__((destructor)) static void finalized(void){mark('D');}
static nex_ffi_status echo(const nex_ffi_api_v1 *api,nex_ffi_call call,const nex_ffi_ref *args,uint64_t count,nex_ffi_ref *out,void *user){
  (void)user;if(count!=1)return NEX_FFI_TYPE;mark('C');(void)api->poll(call);*out=args[0];return NEX_FFI_OK;
}
static nex_ffi_status unit(const nex_ffi_api_v1 *api,nex_ffi_call call,const nex_ffi_ref *args,uint64_t count,nex_ffi_ref *out,void *user){
  (void)args;(void)user;if(count)return NEX_FFI_TYPE;mark('U');(void)api->poll(call);*out=0;return NEX_FFI_OK;
}
static nex_ffi_status values(const nex_ffi_api_v1 *api,nex_ffi_call call,const nex_ffi_ref *args,uint64_t count,nex_ffi_ref *out,void *user){
  nex_ffi_type type=0;nex_ffi_status status;(void)user;if(count!=8)return NEX_FFI_TYPE;mark('V');status=api->result_type(call,&type);if(status)return status;return api->make_nominal(call,type,0,args,count,out);
}
static nex_ffi_status wrong(const nex_ffi_api_v1 *api,nex_ffi_call call,const nex_ffi_ref *args,uint64_t count,nex_ffi_ref *out,void *user){
  (void)args;(void)count;(void)user;mark('W');return api->make_bool(call,1,out);
}
NEX_FFI_MODULE_EXPORT const nex_ffi_module_v1 *nex_ffi_module_entry(uint32_t abi,uint32_t size){
  static const nex_ffi_export_v1 exports[]={
    {sizeof(nex_ffi_export_v1),0,"echo","67271321265625b9f0499796f5997cf2f9c6161ed418867840d9551d879f987d",echo,0},
    {sizeof(nex_ffi_export_v1),0,"unit","0fd6b2c1abde32e3920eb418056e2541481467996780270c18371cb53b552890",unit,0},
    {sizeof(nex_ffi_export_v1),0,"values","135390dc734edcea51086bbcc490b9d1ec52edc504e4c2c4f97f13a3ca1bdb7d",values,0},
    {sizeof(nex_ffi_export_v1),0,"wrong","67271321265625b9f0499796f5997cf2f9c6161ed418867840d9551d879f987d",wrong,0}
  };
  static const nex_ffi_module_v1 module={NEX_FFI_MODULE_ABI_V1,sizeof(nex_ffi_module_v1),4,sizeof(nex_ffi_export_v1),exports};
  mark('G');return abi==NEX_FFI_ABI_V1&&size>=sizeof(nex_ffi_api_v1)?&module:0;
}
