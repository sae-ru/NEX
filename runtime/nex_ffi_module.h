#ifndef NEX_FFI_MODULE_H
#define NEX_FFI_MODULE_H
#include "nex_ffi.h"
#ifdef __cplusplus
extern "C" {
#endif
#define NEX_FFI_MODULE_ABI_V1 UINT32_C(1)
typedef struct nex_ffi_export_v1 {
  uint32_t struct_size;
  uint32_t reserved;
  const char *name;
  const char *signature_sha256;
  nex_ffi_callback_v1 callback;
  void *user;
} nex_ffi_export_v1;
typedef struct nex_ffi_module_v1 {
  uint32_t abi_version;
  uint32_t struct_size;
  uint64_t export_count;
  uint64_t export_stride;
  const nex_ffi_export_v1 *exports;
} nex_ffi_module_v1;
typedef const nex_ffi_module_v1 *(*nex_ffi_module_entry_fn)(uint32_t,uint32_t);
/* A module exports exactly this getter; callbacks use the host's value table. */
#if defined(_WIN32)
#define NEX_FFI_MODULE_EXPORT __declspec(dllexport)
#else
#define NEX_FFI_MODULE_EXPORT __attribute__((visibility("default")))
#endif
NEX_FFI_MODULE_EXPORT const nex_ffi_module_v1 *nex_ffi_module_entry(
    uint32_t host_abi_version,uint32_t host_api_size);
#ifdef __cplusplus
}
#endif
#endif
