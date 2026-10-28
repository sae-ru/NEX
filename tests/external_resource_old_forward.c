#include "nex_ffi.h"
/* Separately compiled against the genuine 0.37 transport header. */
nex_ffi_status old_resource_forward(const nex_ffi_api_v1 *api,nex_ffi_call call,
    const nex_ffi_ref *args,uint64_t count,nex_ffi_ref *out,void *user) {
  (void)user;
  if(count!=1)return NEX_FFI_ARGUMENT;
  nex_ffi_ref retained=0;
  nex_ffi_status status=api->retain(call,args[0],&retained);
  if(status)return status;
  return api->make_success(call,retained,out);
}
