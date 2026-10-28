#include "fixtures/ffi-resource-prefix-0.130/nex_ffi.h"
#include "nex_ffi_module.h"
#include "legacy-signatures.h"
#include <stdint.h>
#include <stdlib.h>
#ifdef NEX_FFI_V1_RESOURCE_PARENTS_SIZE
#error This producer must compile against the original resource prefix
#endif
#if defined(__cplusplus)
static_assert(sizeof(nex_ffi_api_v1)==296);
#else
_Static_assert(sizeof(nex_ffi_api_v1)==296,"legacy resource table width changed");
#endif
static void destroy(void *p){free(p);}
static nex_ffi_status factory(const nex_ffi_api_v1 *api,nex_ffi_call call,void *user,void **out){
  (void)api;(void)call;(void)user;int64_t *p=(int64_t*)malloc(sizeof(*p));if(!p)return NEX_FFI_LIMIT;*p=42;*out=p;return NEX_FFI_OK;
}
static nex_ffi_status callback(const nex_ffi_api_v1 *api,nex_ffi_call call,const nex_ffi_ref *args,uint64_t count,nex_ffi_ref *out,void *user){
  if(count!=1||api->abi_version!=1||api->struct_size<NEX_FFI_V1_RESOURCE_SIZE)return NEX_FFI_ARGUMENT;
  unsigned op=(unsigned)(uintptr_t)user;nex_ffi_type type=0;nex_ffi_status status;
  if(op==1){status=api->result_type(call,&type);if(status!=NEX_FFI_OK)return status;return api->resource_create(call,type,sizeof(int64_t),factory,destroy,NULL,out);}
  if(op==2){status=api->argument_type(call,0,&type);if(status!=NEX_FFI_OK)return status;void *p=NULL;status=api->resource_borrow(call,args[0],type,&p);if(status!=NEX_FFI_OK)return status;return api->make_i64(call,*(int64_t*)p,out);}
  return api->make_i64(call,sizeof(nex_ffi_api_v1),out);
}
static const nex_ffi_export_v1 exports[]={
 {sizeof(nex_ffi_export_v1),0,"legacy_session",PIN_LEGACY_SESSION,callback,(void*)1},
 {sizeof(nex_ffi_export_v1),0,"legacy_read",PIN_LEGACY_READ,callback,(void*)2},
 {sizeof(nex_ffi_export_v1),0,"legacy_size",PIN_LEGACY_SIZE,callback,(void*)3}
};
static const nex_ffi_module_v1 module={NEX_FFI_MODULE_ABI_V1,sizeof(nex_ffi_module_v1),3,sizeof(nex_ffi_export_v1),exports};
const nex_ffi_module_v1 *nex_ffi_module_entry(uint32_t abi,uint32_t size){return abi==1&&size>=NEX_FFI_V1_RESOURCE_SIZE?&module:NULL;}
