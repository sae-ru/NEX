#include "nex_ffi_module.h"
#include <fcntl.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
static void mark(char event){const char *path=getenv("NEX_FFI_TEST_MARKER");if(path){int fd=open(path,O_WRONLY|O_CREAT|O_APPEND,0600);if(fd>=0){(void)write(fd,&event,1);close(fd);}}}
__attribute__((constructor)) static void initialized(void){mark('I');}
__attribute__((destructor)) static void finalized(void){mark('D');}
static nex_ffi_status echo(const nex_ffi_api_v1 *api,nex_ffi_call call,const nex_ffi_ref *args,uint64_t count,nex_ffi_ref *out,void *user){
  (void)user;if(count!=1)return NEX_FFI_TYPE;mark('C');(void)api->poll(call);*out=args[0];return NEX_FFI_OK;
}
static nex_ffi_status wrong(const nex_ffi_api_v1 *api,nex_ffi_call call,const nex_ffi_ref *args,uint64_t count,nex_ffi_ref *out,void *user){
  (void)args;(void)count;(void)user;return api->make_bool(call,1,out);
}
#ifndef NEX_FFI_TEST_NO_ENTRY
static const nex_ffi_export_v1 exports[]={
  {sizeof(nex_ffi_export_v1),0,"echo","67271321265625b9f0499796f5997cf2f9c6161ed418867840d9551d879f987d",echo,0},
  {sizeof(nex_ffi_export_v1),0,"wrong","67271321265625b9f0499796f5997cf2f9c6161ed418867840d9551d879f987d",wrong,0}
};
NEX_FFI_MODULE_EXPORT const nex_ffi_module_v1 *nex_ffi_module_entry(uint32_t abi,uint32_t size){
  static nex_ffi_module_v1 module;static nex_ffi_export_v1 selected[2];const char *mode=getenv("NEX_FFI_TEST_ABI");mark('G');
  if(abi!=NEX_FFI_ABI_V1||size<sizeof(nex_ffi_api_v1))return 0;
  memcpy(selected,exports,sizeof(selected));
  module.abi_version=mode&&strcmp(mode,"wrong")==0?2:NEX_FFI_MODULE_ABI_V1;module.struct_size=sizeof(module);module.export_count=2;
  module.export_stride=sizeof(nex_ffi_export_v1);module.exports=selected;
  if(mode){
    if(strcmp(mode,"null")==0)return 0;
    if(strcmp(mode,"short")==0)module.struct_size=0;
    if(strcmp(mode,"count")==0)module.export_count=UINT64_MAX;
    if(strcmp(mode,"stride")==0)module.export_stride=1;
    if(strcmp(mode,"reserved")==0)selected[0].reserved=1;
    if(strcmp(mode,"name")==0)selected[0].name="wrong";
    if(strcmp(mode,"hash")==0)selected[0].signature_sha256="0000000000000000000000000000000000000000000000000000000000000000";
    if(strcmp(mode,"callback")==0)selected[0].callback=0;
  }
  return &module;
}
#endif
