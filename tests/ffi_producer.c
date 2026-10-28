#include "nex_ffi.h"
#include <stddef.h>
#include <limits.h>
#include <string.h>
_Static_assert(sizeof(nex_ffi_call)==8 && sizeof(nex_ffi_ref)==8,"token ABI");
_Static_assert(offsetof(nex_ffi_api_v1,kind)==8,"table prefix ABI");
#define CHECK(expression) do { nex_ffi_status status=(expression); if(status!=NEX_FFI_OK)return status; } while(0)

nex_ffi_status nex_test_c_values(const nex_ffi_api_v1 *api,nex_ffi_call call,
    const nex_ffi_ref *args,uint64_t count,nex_ffi_ref *out,void *user){
  int64_t integer;double floating;uint32_t boolean;uint64_t size,written,i;
  uint8_t text[32],binary[32];nex_ffi_ref result[5],list;
  (void)user;
  if(count!=5||api->abi_version!=NEX_FFI_ABI_V1||api->struct_size<sizeof(*api))return NEX_FFI_ARGUMENT;
  CHECK(api->get_i64(call,args[0],&integer));
  if(integer==INT64_MAX)return NEX_FFI_RANGE;
  CHECK(api->make_i64(call,integer+1,&result[0]));
  CHECK(api->get_f64(call,args[1],&floating));CHECK(api->make_f64(call,floating,&result[1]));
  CHECK(api->get_bool(call,args[2],&boolean));CHECK(api->make_bool(call,!boolean,&result[2]));
  CHECK(api->byte_size(call,args[3],&size));if(size>=sizeof(text))return NEX_FFI_LIMIT;
  CHECK(api->copy_bytes(call,args[3],0,text,size,&written));if(written!=size)return NEX_FFI_INTERNAL;
  text[size]='!';CHECK(api->make_string(call,text,size+1,&result[3]));memset(text,0,sizeof(text));
  CHECK(api->byte_size(call,args[4],&size));if(size>sizeof(binary))return NEX_FFI_LIMIT;
  CHECK(api->copy_bytes(call,args[4],0,binary,size,&written));if(written!=size)return NEX_FFI_INTERNAL;
  for(i=0;i<size/2;++i){uint8_t saved=binary[i];binary[i]=binary[size-i-1];binary[size-i-1]=saved;}
  CHECK(api->make_bytes(call,binary,size,&result[4]));memset(binary,0,sizeof(binary));
  CHECK(api->make_list(call,result,5,&list));
  for(i=0;i<5;++i)CHECK(api->release(call,result[i]));
  CHECK(api->poll(call));return api->make_success(call,list,out);
}
nex_ffi_status nex_test_c_forward(const nex_ffi_api_v1 *api,nex_ffi_call call,
    const nex_ffi_ref *args,uint64_t count,nex_ffi_ref *out,void *user){
  (void)user;if(count!=1)return NEX_FFI_ARGUMENT;
  return api->retain(call,args[0],out);
}
