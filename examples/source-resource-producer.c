#include "nex_ffi_module.h"
#include "resource-signatures.h"
#include <stdint.h>
#include <stdlib.h>
#include <fcntl.h>
#include <unistd.h>

#ifndef NEX_RESOURCE_MARKER
#error "Compile this conformance producer with its explicit marker path"
#endif
typedef struct {int64_t value;} Object;
static void event(char value){int fd=open(NEX_RESOURCE_MARKER,O_CREAT|O_APPEND|O_WRONLY,0600);if(fd>=0){(void)write(fd,&value,1);close(fd);}}
__attribute__((constructor)) static void loaded(void){event('I');}
__attribute__((destructor)) static void unloaded(void){event('D');}
static void destroy(void *pointer){event('X');free(pointer);}
static nex_ffi_status factory(const nex_ffi_api_v1 *api,nex_ffi_call call,void *user,void **out){
  (void)api;(void)call;Object *object=(Object*)malloc(sizeof(Object));
  if(!object)return NEX_FFI_LIMIT;
  object->value=*(int64_t*)user;*out=object;event('F');
#ifdef __cplusplus
  if(object->value==-4)throw 42;
#endif
  return NEX_FFI_OK;
}
#define TRY(expr) do{nex_ffi_status code=(expr);if(code!=NEX_FFI_OK)return code;}while(0)
static nex_ffi_status invoke(const nex_ffi_api_v1 *api,nex_ffi_call call,const nex_ffi_ref *args,uint64_t count,nex_ffi_ref *out,void *user){
  nex_ffi_type type=0;
  if(api->struct_size<NEX_FFI_V1_RESOURCE_SIZE||count!=1)return NEX_FFI_ARGUMENT;
  if((uintptr_t)user==1){
    int64_t value=0;TRY(api->get_i64(call,args[0],&value));TRY(api->result_type(call,&type));
    return api->resource_create(call,type,sizeof(Object),factory,destroy,&value,out);
  }
  void *pointer=NULL;TRY(api->argument_type(call,0,&type));TRY(api->resource_borrow(call,args[0],type,&pointer));
  return api->make_i64(call,((Object*)pointer)->value,out);
}
static const nex_ffi_export_v1 exports[]={
  {sizeof(nex_ffi_export_v1),0,"create",PIN_CREATE,invoke,(void*)1},
  {sizeof(nex_ffi_export_v1),0,"read",PIN_READ,invoke,(void*)2}
};
NEX_FFI_MODULE_EXPORT const nex_ffi_module_v1 *nex_ffi_module_entry(uint32_t abi,uint32_t size){
  static const nex_ffi_module_v1 module={1,sizeof(nex_ffi_module_v1),sizeof(exports)/sizeof(exports[0]),sizeof(nex_ffi_export_v1),exports};
  return abi==1&&size>=NEX_FFI_V1_RESOURCE_SIZE?&module:NULL;
}
