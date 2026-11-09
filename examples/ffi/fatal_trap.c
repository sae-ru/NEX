/* Callback for: server extern fn fatal(code:str,message:str)->unit !{ffi}.
   Use only for fatal host/device failures after admitted work has settled.
   Recoverable application errors belong in make_failure/result<T> instead. */
#include "nex_ffi.h"

nex_ffi_status nex_example_raise_trap(const nex_ffi_api_v1 *api,nex_ffi_call call,
    const nex_ffi_ref *args,uint64_t count,nex_ffi_ref *out,void *user){
  uint8_t code[128],message[2048];uint64_t code_size=0,message_size=0,written=0;
  nex_ffi_status status;(void)out;(void)user;
  if(count!=2||api->struct_size<NEX_FFI_V1_TRAP_SIZE||!api->raise_trap)return NEX_FFI_ARGUMENT;
  status=api->byte_size(call,args[0],&code_size);if(status)return status;
  status=api->byte_size(call,args[1],&message_size);if(status)return status;
  if(code_size<3||code_size>sizeof(code)||message_size>sizeof(message))return NEX_FFI_LIMIT;
  status=api->copy_bytes(call,args[0],0,code,code_size,&written);if(status)return status;
  if(written!=code_size)return NEX_FFI_INTERNAL;
  status=api->copy_bytes(call,args[1],0,message,message_size,&written);if(status)return status;
  if(written!=message_size)return NEX_FFI_INTERNAL;
  /* HOST_TRAP is a C status, never an exception unwinding through this frame. */
  return api->raise_trap(call,code,code_size,message,message_size);
}
