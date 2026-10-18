/* Trusted C adapter for the NEX value contract exported by nex ffi. */
#include "nex_ffi.h"
#define OK(expression) do { nex_ffi_status s=(expression); if(s)return s; } while(0)
nex_ffi_status nex_example_c_nominal(const nex_ffi_api_v1 *api,nex_ffi_call call,
    const nex_ffi_ref *args,uint64_t count,nex_ffi_ref *out,void *user){
  nex_ffi_type input,result,reply,packet,field;uint32_t kind;uint64_t size;
  nex_ffi_ref text,model,tag;uint8_t data[]={0xd0,0xaf,0,0xf0,0x9f,0xa7,0xa0};
  nex_ffi_ref fields[2];(void)user;
  if(!api||api->abi_version!=1||api->struct_size<sizeof(*api)||count!=1)return NEX_FFI_ARGUMENT;
  OK(api->argument_type(call,0,&input));OK(api->type_kind(call,input,&kind));if(kind!=NEX_FFI_BYTES)return NEX_FFI_TYPE;
  OK(api->result_type(call,&result));OK(api->type_kind(call,result,&kind));if(kind!=NEX_FFI_RESULT)return NEX_FFI_TYPE;
  OK(api->type_child(call,result,0,0,&reply));OK(api->type_kind(call,reply,&kind));if(kind!=NEX_FFI_ENUM)return NEX_FFI_TYPE;
  OK(api->type_variant_count(call,reply,&size));if(size!=2)return NEX_FFI_TYPE;
  OK(api->type_child_count(call,reply,0,&size));if(size!=1)return NEX_FFI_TYPE;
  OK(api->type_child(call,reply,0,0,&packet));OK(api->type_kind(call,packet,&kind));if(kind!=NEX_FFI_RECORD)return NEX_FFI_TYPE;
  OK(api->type_child_count(call,packet,0,&size));if(size!=2)return NEX_FFI_TYPE;
  OK(api->type_child(call,packet,0,0,&field));OK(api->type_kind(call,field,&kind));if(kind!=NEX_FFI_BYTES)return NEX_FFI_TYPE;
  OK(api->type_child(call,packet,0,1,&field));OK(api->type_kind(call,field,&kind));if(kind!=NEX_FFI_STRING)return NEX_FFI_TYPE;
  OK(api->make_string(call,data,sizeof(data),&text));fields[0]=args[0];fields[1]=text;
  OK(api->make_nominal(call,packet,0,fields,2,&model));
  OK(api->make_nominal(call,reply,0,&model,1,&tag));return api->make_success(call,tag,out);
}
