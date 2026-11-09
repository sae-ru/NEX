#include "nex_ffi_module.h"
#include "typed-resource-signatures.h"
/* Self-contained marker for copied C ABI fixtures. */
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
static void nex_test_marker(const char *variable,char event){
  wchar_t name[256],path[32768];
  if(!MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,variable,-1,name,256))return;
  DWORD size=GetEnvironmentVariableW(name,path,32768);if(!size||size>=32768)return;
  HANDLE file=CreateFileW(path,FILE_APPEND_DATA,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,NULL,OPEN_ALWAYS,FILE_ATTRIBUTE_NORMAL,NULL);
  if(file==INVALID_HANDLE_VALUE)return;DWORD written=0;(void)WriteFile(file,&event,1,&written,NULL);CloseHandle(file);
}
#else
#include <fcntl.h>
#include <stdlib.h>
#include <unistd.h>
static void nex_test_marker(const char *variable,char event){
  const char *path=getenv(variable);if(!path)return;
  int fd=open(path,O_WRONLY|O_CREAT|O_APPEND,0600);if(fd<0)return;(void)write(fd,&event,1);close(fd);
}
#endif

#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <pthread.h>
#include <fcntl.h>
#include <unistd.h>

typedef struct {int64_t value;} Object;
static void event(char value){nex_test_marker("NEX_TYPED_RESOURCE_MARKER",value);}
__attribute__((constructor)) static void loaded(void){
#ifdef DIFFERENT_IMAGE
  event('J');
#else
  event('I');
#endif
}
__attribute__((destructor)) static void unloaded(void){event('D');}
static void destroy(void *pointer){event('X');free(pointer);}
static nex_ffi_status factory(const nex_ffi_api_v1 *api,nex_ffi_call call,void *user,void **out){
  int64_t value=*(int64_t*)user;Object *object=(Object*)malloc(sizeof(*object));if(!object)return NEX_FFI_LIMIT;
  object->value=value;*out=object;event('F');
#ifdef __cplusplus
  if(value==-4)throw 42;
#endif
  if(value==-1)return NEX_FFI_LIMIT;
  if(value==-5){
    if(api->struct_size<NEX_FFI_V1_TRAP_SIZE||!api->raise_trap)return NEX_FFI_ARGUMENT;
    return api->raise_trap(call,(const uint8_t*)"E_OVERFLOW",10,(const uint8_t*)"partial factory overflow",24);
  }
  if(value==-3)(void)api->poll(call);
  return NEX_FFI_OK;
}
static nex_ffi_status null_factory(const nex_ffi_api_v1 *api,nex_ffi_call call,void *user,void **out){(void)api;(void)call;(void)user;(void)out;event('N');return NEX_FFI_OK;}
#define TRY(expr) do{nex_ffi_status code=(expr);if(code!=NEX_FFI_OK)return code;}while(0)
typedef struct {const nex_ffi_api_v1 *api;nex_ffi_call call;nex_ffi_ref ref;nex_ffi_type type;nex_ffi_status status;} WrongThread;
static void *wrong_thread(void *argument){WrongThread *w=(WrongThread*)argument;void *untouched=(void*)(uintptr_t)123;w->status=w->api->resource_borrow(w->call,w->ref,w->type,&untouched);if(untouched!=(void*)(uintptr_t)123)w->status=NEX_FFI_INTERNAL;return NULL;}
static nex_ffi_call old_call;
static nex_ffi_ref old_ref;
static nex_ffi_type old_type;
static nex_ffi_status callback(const nex_ffi_api_v1 *api,nex_ffi_call call,const nex_ffi_ref *args,uint64_t count,nex_ffi_ref *out,void *user){
  unsigned op=(unsigned)(uintptr_t)user;nex_ffi_type type=0;
  if(api->struct_size<NEX_FFI_V1_RESOURCE_SIZE||count!=1)return NEX_FFI_ARGUMENT;
  if(op==1||op==7||op==9){
    int64_t value=0;TRY(api->get_i64(call,args[0],&value));TRY(api->result_type(call,&type));
    if(op==9)TRY(api->type_child(call,type,0,0,&type));
    nex_ffi_ref resource=0;
    nex_ffi_resource_destroy_v1 deleter=destroy;
    if(op==7){
#ifdef _WIN32
      // An ordinary MinGW import address can be a JMP thunk owned by this
      // DLL. Use the actual foreign CRT procedure for this negative control.
      HMODULE crt=GetModuleHandleW(L"ucrtbase.dll"),owner=NULL;
      deleter=crt?(nex_ffi_resource_destroy_v1)(uintptr_t)GetProcAddress(crt,"free"):NULL;
      if(!deleter||!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
          (LPCWSTR)(uintptr_t)deleter,&owner)||owner!=crt)return NEX_FFI_INTERNAL;
#else
      deleter=free;
#endif
      event('R');
    }
    TRY(api->resource_create(call,type,sizeof(Object),value==-2?null_factory:factory,deleter,&value,&resource));
    if(op==9)return api->make_success(call,resource,out);
    *out=resource;return NEX_FFI_OK;
  }
  TRY(api->argument_type(call,0,&type));
  if(op==3){*out=args[0];return NEX_FFI_OK;}
  if(op==6){nex_ffi_ref untouched=123;int64_t value=7;nex_ffi_status s=api->resource_create(call,type,sizeof(Object),factory,destroy,&value,&untouched);if(untouched!=123)return NEX_FFI_INTERNAL;return api->make_i64(call,s,out);}
  if(op==10){
    if(old_call){void *untouched=(void*)(uintptr_t)123;
      if(api->resource_borrow(old_call,old_ref,old_type,&untouched)!=NEX_FFI_SCOPE||untouched!=(void*)(uintptr_t)123)return NEX_FFI_INTERNAL;
      if(api->resource_borrow(call,args[0],old_type,&untouched)!=NEX_FFI_REF)return NEX_FFI_INTERNAL;
    }
    old_call=call;old_ref=args[0];old_type=type;return api->make_i64(call,42,out);
  }
  if(op==11){WrongThread w={api,call,args[0],type,0};pthread_t thread;if(pthread_create(&thread,NULL,wrong_thread,&w))return NEX_FFI_INTERNAL;if(pthread_join(thread,NULL))return NEX_FFI_INTERNAL;return api->make_i64(call,w.status,out);}
  void *pointer=NULL;nex_ffi_status borrowed=api->resource_borrow(call,args[0],type,&pointer);
  if(op==5)return api->make_i64(call,borrowed,out);
  if(borrowed!=NEX_FFI_OK)return borrowed;
  uint32_t kind=0;uint64_t unused=0;TRY(api->kind(call,args[0],&kind));
  if(kind!=NEX_FFI_EXTERNAL_RESOURCE||api->child_count(call,args[0],&unused)!=NEX_FFI_TYPE||api->file_identity(call,args[0],&unused)!=NEX_FFI_TYPE)return NEX_FFI_INTERNAL;
  TRY(api->resource_identity(call,args[0],&unused));if(!unused)return NEX_FFI_INTERNAL;
  if(op==4){uint32_t closed=0,opened=1;TRY(api->resource_close(call,args[0],&closed));TRY(api->resource_is_open(call,args[0],&opened));if(!closed||opened)return NEX_FFI_INTERNAL;
    void *untouched=(void*)(uintptr_t)123;if(api->resource_borrow(call,args[0],type,&untouched)!=NEX_FFI_RESOURCE_CLOSED||untouched!=(void*)(uintptr_t)123)return NEX_FFI_INTERNAL;
    TRY(api->release(call,args[0]));
  }
  if(op==8){event('B');(void)api->poll(call);}
  int64_t value=((Object*)pointer)->value;
  if(op==8)event('P');
  return api->make_i64(call,value,out);
}
#define EXPORT(name,op) {sizeof(nex_ffi_export_v1),0,#name,PIN_##name,callback,(void*)(uintptr_t)op}
static const nex_ffi_export_v1 exports[]={
  {sizeof(nex_ffi_export_v1),0,"create",PIN_CREATE,callback,(void*)1},
  {sizeof(nex_ffi_export_v1),0,"read",PIN_READ,callback,(void*)2},
  {sizeof(nex_ffi_export_v1),0,"forward",PIN_FORWARD,callback,(void*)3},
  {sizeof(nex_ffi_export_v1),0,"close_borrow",PIN_CLOSE_BORROW,callback,(void*)4},
  {sizeof(nex_ffi_export_v1),0,"status",PIN_STATUS,callback,(void*)5},
  {sizeof(nex_ffi_export_v1),0,"input_constructor",PIN_INPUT_CONSTRUCTOR,callback,(void*)6},
  {sizeof(nex_ffi_export_v1),0,"bad_callback",PIN_BAD_CALLBACK,callback,(void*)7},
  {sizeof(nex_ffi_export_v1),0,"hold_poll",PIN_HOLD_POLL,callback,(void*)8},
  {sizeof(nex_ffi_export_v1),0,"result_create",PIN_RESULT_CREATE,callback,(void*)9},
  {sizeof(nex_ffi_export_v1),0,"tokens",PIN_TOKENS,callback,(void*)10},
  {sizeof(nex_ffi_export_v1),0,"wrong_thread",PIN_WRONG_THREAD,callback,(void*)11}
};
static const nex_ffi_module_v1 module={NEX_FFI_MODULE_ABI_V1,sizeof(nex_ffi_module_v1),sizeof(exports)/sizeof(exports[0]),sizeof(nex_ffi_export_v1),exports};
const nex_ffi_module_v1 *nex_ffi_module_entry(uint32_t abi,uint32_t bytes){return abi==NEX_FFI_ABI_V1&&bytes>=NEX_FFI_V1_RESOURCE_SIZE?&module:NULL;}
