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
  NEX_FFI_INTERNAL=11, NEX_FFI_REENTRANT=12, NEX_FFI_RESOURCE_CLOSED=13
};
enum {
  NEX_FFI_I64=1, NEX_FFI_F64=2, NEX_FFI_BOOL=3, NEX_FFI_STRING=4,
  NEX_FFI_BYTES=5, NEX_FFI_LIST=6, NEX_FFI_RECORD=7, NEX_FFI_ENUM=8,
  NEX_FFI_SUCCESS=9, NEX_FFI_FAILURE=10, NEX_FFI_FUNCTION=11, NEX_FFI_FILE=12,
  NEX_FFI_UNIT=13, NEX_FFI_RESULT=14, NEX_FFI_EXTERNAL_RESOURCE=15
};

struct nex_ffi_api_v1;
/* Writing a nonnull native object transfers it to the host, including on error.
   The factory polls cooperatively; destroy must not throw or retain C tokens. */
typedef nex_ffi_status (*nex_ffi_resource_factory_v1)(const struct nex_ffi_api_v1*,nex_ffi_call,void*,void**);
typedef void (*nex_ffi_resource_destroy_v1)(void*);
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
  /* Host-authorized opaque resources. A borrow lasts only for this call/thread. */
  nex_ffi_status (*resource_create)(nex_ffi_call,nex_ffi_type,uint64_t,nex_ffi_resource_factory_v1,nex_ffi_resource_destroy_v1,void*,nex_ffi_ref*);
  nex_ffi_status (*resource_borrow)(nex_ffi_call,nex_ffi_ref,nex_ffi_type,void**);
  nex_ffi_status (*resource_close)(nex_ffi_call,nex_ffi_ref,uint32_t*);
  nex_ffi_status (*resource_is_open)(nex_ffi_call,nex_ffi_ref,uint32_t*);
  nex_ffi_status (*resource_identity)(nex_ffi_call,nex_ffi_ref,uint64_t*);
  /* Parent tokens belong to this call. The host admits physical parent leases
     before factory entry and retains them until the child destructor finishes.
     At most16 supplied parents; transitive identities are deduplicated. */
  nex_ffi_status (*resource_create_with_parents)(nex_ffi_call,nex_ffi_type,uint64_t,const nex_ffi_ref*,uint64_t,nex_ffi_resource_factory_v1,nex_ffi_resource_destroy_v1,void*,nex_ffi_ref*);
  /* Appended in0.164. Copy a fatal diagnostic into the host call. A valid
     packet returns HOST_TRAP and stays sticky; no exception crosses C.
     Code is E_[A-Z0-9_]+,3..128 bytes; message is strict UTF-8,0..2048 bytes.
     Neither may contain NUL. Existing host cancellation/deadline wins.
     Admitted native/device work must physically settle before reporting. */
  nex_ffi_status (*raise_trap)(nex_ffi_call,const uint8_t*,uint64_t,const uint8_t*,uint64_t);
} nex_ffi_api_v1;
#define NEX_FFI_V1_TRANSPORT_SIZE ((uint32_t)offsetof(nex_ffi_api_v1,argument_type))
#define NEX_FFI_V1_TYPED_SIZE ((uint32_t)offsetof(nex_ffi_api_v1,resource_create))
#define NEX_FFI_V1_RESOURCE_SIZE ((uint32_t)offsetof(nex_ffi_api_v1,resource_create_with_parents))
#define NEX_FFI_V1_RESOURCE_PARENTS_SIZE ((uint32_t)offsetof(nex_ffi_api_v1,raise_trap))
#define NEX_FFI_V1_TRAP_SIZE ((uint32_t)sizeof(nex_ffi_api_v1))

/* Require this major ABI and a table prefix at least minimum_size bytes long. */
const nex_ffi_api_v1 *nex_ffi_get_api(uint32_t abi_version,uint32_t minimum_size);
typedef nex_ffi_status (*nex_ffi_callback_v1)(const nex_ffi_api_v1*,nex_ffi_call,
    const nex_ffi_ref*,uint64_t,nex_ffi_ref*,void*);

#ifdef __cplusplus
}
#endif
#endif
