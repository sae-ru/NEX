#ifndef NEX_FFI_H
#define NEX_FFI_H
/* Experimental C transport. No C++ layout or source-language FFI is exported. */
#include <stdint.h>
#include <stddef.h>
#ifdef __cplusplus
extern "C" {
#endif

#define NEX_FFI_ABI_V1 UINT32_C(1)
typedef uint64_t nex_ffi_call;
typedef uint64_t nex_ffi_ref;
typedef uint64_t nex_ffi_type;
typedef uint32_t nex_ffi_status;
enum {
  NEX_FFI_OK=0, NEX_FFI_ARGUMENT=1, NEX_FFI_SCOPE=2, NEX_FFI_THREAD=3,
  NEX_FFI_REF=4, NEX_FFI_TYPE=5, NEX_FFI_BOUNDS=6, NEX_FFI_UTF8=7,
  NEX_FFI_RANGE=8, NEX_FFI_LIMIT=9, NEX_FFI_HOST_TRAP=10,
  NEX_FFI_INTERNAL=11, NEX_FFI_REENTRANT=12
};
enum {
  NEX_FFI_I64=1, NEX_FFI_F64=2, NEX_FFI_BOOL=3, NEX_FFI_STRING=4,
  NEX_FFI_BYTES=5, NEX_FFI_LIST=6, NEX_FFI_RECORD=7, NEX_FFI_ENUM=8,
  NEX_FFI_SUCCESS=9, NEX_FFI_FAILURE=10, NEX_FFI_FUNCTION=11, NEX_FFI_FILE=12,
  NEX_FFI_UNIT=13, NEX_FFI_RESULT=14, NEX_FFI_EXTERNAL_RESOURCE=15
};

typedef struct nex_ffi_api_v1 {
  uint32_t abi_version;
  uint32_t struct_size;
  nex_ffi_status (*kind)(nex_ffi_call,nex_ffi_ref,uint32_t*);
  nex_ffi_status (*get_i64)(nex_ffi_call,nex_ffi_ref,int64_t*);
  nex_ffi_status (*get_f64)(nex_ffi_call,nex_ffi_ref,double*);
  nex_ffi_status (*get_bool)(nex_ffi_call,nex_ffi_ref,uint32_t*);
  nex_ffi_status (*byte_size)(nex_ffi_call,nex_ffi_ref,uint64_t*);
  nex_ffi_status (*copy_bytes)(nex_ffi_call,nex_ffi_ref,uint64_t,uint8_t*,uint64_t,uint64_t*);
  nex_ffi_status (*child_count)(nex_ffi_call,nex_ffi_ref,uint64_t*);
  nex_ffi_status (*child)(nex_ffi_call,nex_ffi_ref,uint64_t,nex_ffi_ref*);
  nex_ffi_status (*label_size)(nex_ffi_call,nex_ffi_ref,uint64_t,uint64_t*);
  nex_ffi_status (*copy_label)(nex_ffi_call,nex_ffi_ref,uint64_t,uint64_t,uint8_t*,uint64_t,uint64_t*);
  nex_ffi_status (*file_identity)(nex_ffi_call,nex_ffi_ref,uint64_t*);
  nex_ffi_status (*make_i64)(nex_ffi_call,int64_t,nex_ffi_ref*);
  nex_ffi_status (*make_f64)(nex_ffi_call,double,nex_ffi_ref*);
  nex_ffi_status (*make_bool)(nex_ffi_call,uint32_t,nex_ffi_ref*);
  nex_ffi_status (*make_string)(nex_ffi_call,const uint8_t*,uint64_t,nex_ffi_ref*);
  nex_ffi_status (*make_bytes)(nex_ffi_call,const uint8_t*,uint64_t,nex_ffi_ref*);
  nex_ffi_status (*make_list)(nex_ffi_call,const nex_ffi_ref*,uint64_t,nex_ffi_ref*);
  nex_ffi_status (*make_success)(nex_ffi_call,nex_ffi_ref,nex_ffi_ref*);
  nex_ffi_status (*make_failure)(nex_ffi_call,const uint8_t*,uint64_t,const uint8_t*,uint64_t,nex_ffi_ref*);
  nex_ffi_status (*retain)(nex_ffi_call,nex_ffi_ref,nex_ffi_ref*);
  nex_ffi_status (*release)(nex_ffi_call,nex_ffi_ref);
  nex_ffi_status (*poll)(nex_ffi_call);
  /* Appended after the original 0.37 transport prefix. Type tokens are call-local. */
  nex_ffi_status (*argument_type)(nex_ffi_call,uint64_t,nex_ffi_type*);
  nex_ffi_status (*result_type)(nex_ffi_call,nex_ffi_type*);
  nex_ffi_status (*type_kind)(nex_ffi_call,nex_ffi_type,uint32_t*);
  nex_ffi_status (*type_child_count)(nex_ffi_call,nex_ffi_type,uint64_t,uint64_t*);
  nex_ffi_status (*type_child)(nex_ffi_call,nex_ffi_type,uint64_t,uint64_t,nex_ffi_type*);
  nex_ffi_status (*type_variant_count)(nex_ffi_call,nex_ffi_type,uint64_t*);
  nex_ffi_status (*make_nominal)(nex_ffi_call,nex_ffi_type,uint64_t,const nex_ffi_ref*,uint64_t,nex_ffi_ref*);
  nex_ffi_status (*signature_size)(nex_ffi_call,uint64_t*);
  nex_ffi_status (*copy_signature)(nex_ffi_call,uint64_t,uint8_t*,uint64_t,uint64_t*);
} nex_ffi_api_v1;
#define NEX_FFI_V1_TRANSPORT_SIZE ((uint32_t)offsetof(nex_ffi_api_v1,argument_type))

/* Require this major ABI and a table prefix at least minimum_size bytes long. */
const nex_ffi_api_v1 *nex_ffi_get_api(uint32_t abi_version,uint32_t minimum_size);
typedef nex_ffi_status (*nex_ffi_callback_v1)(const nex_ffi_api_v1*,nex_ffi_call,
    const nex_ffi_ref*,uint64_t,nex_ffi_ref*,void*);

#ifdef __cplusplus
}
#endif
#endif
