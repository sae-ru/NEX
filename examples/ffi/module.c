#include "nex_ffi_module.h"
#ifndef NEX_EXAMPLE_SIGNATURE_SHA256
#error Compile with the canonical exported contract SHA-256.
#endif
extern nex_ffi_status nex_example_c_nominal(const nex_ffi_api_v1*,nex_ffi_call,
    const nex_ffi_ref*,uint64_t,nex_ffi_ref*,void*);
NEX_FFI_MODULE_EXPORT const nex_ffi_module_v1 *nex_ffi_module_entry(uint32_t abi,uint32_t size){
  static const nex_ffi_export_v1 exports[]={
    {sizeof(nex_ffi_export_v1),0,"contract",NEX_EXAMPLE_SIGNATURE_SHA256,nex_example_c_nominal,0}
  };
  static const nex_ffi_module_v1 module={NEX_FFI_MODULE_ABI_V1,sizeof(nex_ffi_module_v1),1,sizeof(nex_ffi_export_v1),exports};
  return abi==NEX_FFI_ABI_V1&&size>=sizeof(nex_ffi_api_v1)?&module:0;
}
