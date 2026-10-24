#include "nex_ffi_module.h"
#include "dependent-signatures.h"
#include <stdint.h>
#include <stdlib.h>
#include <fcntl.h>
#include <unistd.h>
#include <pthread.h>
#include <time.h>

/* Both C11 and C++20 compile this producer. Child payloads really dereference
   parent storage during use and destruction; events detect premature release. */
typedef struct Object {int64_t value;struct Object *parent;uint32_t child;} Object;
static void event(char c){const char *p=getenv("NEX_DEPENDENCY_MARKER");if(p){int f=open(p,O_WRONLY|O_APPEND|O_CREAT,0600);if(f>=0){(void)write(f,&c,1);close(f);}}}
__attribute__((constructor)) static void load(void){event('I');}
__attribute__((destructor)) static void unload(void){event('D');}
static void destroy(void *p){Object *o=(Object*)p;if(o->parent&&o->parent->value!=42)event('!');event(o->child?'C':'P');o->value=-1;free(o);}
typedef struct {Object *parent;int64_t mode;nex_ffi_ref token;} Input;
static nex_ffi_status factory(const nex_ffi_api_v1 *api,nex_ffi_call call,void *user,void **out){
  Input *in=(Input*)user;Object *o=(Object*)malloc(sizeof(*o));if(!o)return NEX_FFI_LIMIT;
  o->value=42;o->parent=in->parent;o->child=in->parent!=NULL;*out=o;event(o->child?'B':'A');
  if(in->mode==1){uint32_t closed=0;nex_ffi_status s=api->resource_close(call,in->token,&closed);if(s!=NEX_FFI_OK||!closed)return NEX_FFI_INTERNAL;}
  if(in->mode==2)return NEX_FFI_LIMIT;
#ifdef __cplusplus
  if(in->mode==3)throw 42;
#endif
  return NEX_FFI_OK;
}
#define TRY(x) do{nex_ffi_status s=(x);if(s!=NEX_FFI_OK)return s;}while(0)
typedef struct {const nex_ffi_api_v1 *api;nex_ffi_call call;nex_ffi_type type;nex_ffi_ref parent;nex_ffi_status status;} Wrong;
static void *wrong(void *p){Wrong *w=(Wrong*)p;nex_ffi_ref untouched=123;Input in={NULL,0,0};w->status=w->api->resource_create_with_parents(w->call,w->type,sizeof(Object),&w->parent,1,factory,destroy,&in,&untouched);if(untouched!=123)w->status=NEX_FFI_INTERNAL;return NULL;}
static nex_ffi_call savedCall;
static nex_ffi_ref savedRef;
static pthread_mutex_t gate=PTHREAD_MUTEX_INITIALIZER;
static int holding=0;
static nex_ffi_status callback(const nex_ffi_api_v1 *api,nex_ffi_call call,const nex_ffi_ref *args,uint64_t count,nex_ffi_ref *out,void *user){
  unsigned op=(unsigned)(uintptr_t)user;nex_ffi_type type=0;
  if(api->struct_size<NEX_FFI_V1_RESOURCE_PARENTS_SIZE||!api->resource_create_with_parents)return NEX_FFI_ARGUMENT;
  if(op==10){pthread_mutex_lock(&gate);int value=holding;pthread_mutex_unlock(&gate);return api->make_i64(call,value,out);}
  if(op==9){
    if(count!=1)return NEX_FFI_ARGUMENT;TRY(api->argument_type(call,0,&type));void *p=NULL;TRY(api->resource_borrow(call,args[0],type,&p));
    pthread_mutex_lock(&gate);holding=1;pthread_mutex_unlock(&gate);event('H');
    struct timespec pause={1,500000000};nanosleep(&pause,NULL);
    Object *o=(Object*)p;if(!o->parent||o->parent->value!=42)event('!');event('Q');
    (void)api->poll(call);return api->make_i64(call,o->parent->value,out);
  }
  if(op==1||op==8){if(count!=1)return NEX_FFI_ARGUMENT;TRY(api->result_type(call,&type));if(op==8)TRY(api->type_child(call,type,0,0,&type));Input in={NULL,0,0};nex_ffi_ref value=0;nex_ffi_status status=api->resource_create(call,type,sizeof(Object),factory,destroy,&in,&value);if(op==8&&status==NEX_FFI_LIMIT)return api->make_failure(call,(const uint8_t*)"QUOTA",5,(const uint8_t*)"capacity retained",17,out);if(status!=NEX_FFI_OK)return status;if(op==8)return api->make_success(call,value,out);*out=value;return NEX_FFI_OK;}
  if(op==3){if(count!=1)return NEX_FFI_ARGUMENT;TRY(api->argument_type(call,0,&type));void *p=NULL;TRY(api->resource_borrow(call,args[0],type,&p));Object *o=(Object*)p;return api->make_i64(call,o->parent?o->parent->value:o->value,out);}
  if(op==4){if(count!=1)return NEX_FFI_ARGUMENT;TRY(api->argument_type(call,0,&type));void *p=NULL;nex_ffi_status status=api->resource_borrow(call,args[0],type,&p);return api->make_i64(call,status,out);}
  if(op==5){if(count!=1)return NEX_FFI_ARGUMENT;TRY(api->result_type(call,&type));if(savedCall){nex_ffi_ref unchanged=123;Input in={NULL,0,0};nex_ffi_status status=api->resource_create_with_parents(savedCall,type,sizeof(Object),&savedRef,1,factory,destroy,&in,&unchanged);if(status!=NEX_FFI_SCOPE||unchanged!=123)return NEX_FFI_INTERNAL;}savedCall=call;savedRef=args[0];return api->retain(call,args[0],out);}
  if(op==2||op==6||op==7){
    if(count!=2)return NEX_FFI_ARGUMENT;int64_t mode=0;TRY(api->get_i64(call,args[1],&mode));
    TRY(api->result_type(call,&type));if(op==7)TRY(api->type_child(call,type,0,0,&type));
    nex_ffi_type parentType=0;TRY(api->argument_type(call,0,&parentType));
    if(mode>=10){
      nex_ffi_ref list[17];for(unsigned i=0;i<17;++i)list[i]=args[0];
      const nex_ffi_ref *parents=list;uint64_t n=1;nex_ffi_status expected=NEX_FFI_OK;
      if(mode==10){parents=NULL;expected=NEX_FFI_ARGUMENT;}
      if(mode==11){n=17;expected=NEX_FFI_LIMIT;}
      if(mode==12){list[0]=UINT64_MAX;expected=NEX_FFI_REF;}
      if(mode==13){list[0]=args[1];expected=NEX_FFI_TYPE;}
      if(mode==14){nex_ffi_ref released=0;TRY(api->retain(call,args[0],&released));TRY(api->release(call,released));list[0]=released;expected=NEX_FFI_REF;}
      if(mode==16){if(op!=7)return NEX_FFI_ARGUMENT;uint32_t closed=0;TRY(api->resource_close(call,args[0],&closed));if(!closed)return NEX_FFI_INTERNAL;expected=NEX_FFI_RESOURCE_CLOSED;}
      Input in={NULL,0,0};nex_ffi_ref unchanged=123;nex_ffi_status status;
      if(mode==15){Wrong w={api,call,type,args[0],0};pthread_t thread;if(pthread_create(&thread,NULL,wrong,&w)||pthread_join(thread,NULL))return NEX_FFI_INTERNAL;status=w.status;expected=NEX_FFI_THREAD;}
      else status=api->resource_create_with_parents(call,type,sizeof(Object),parents,n,factory,destroy,&in,&unchanged);
      if(status!=expected||unchanged!=123)return NEX_FFI_INTERNAL;
      if(mode==16)return api->make_failure(call,(const uint8_t*)"CLOSED",6,(const uint8_t*)"parent closed",13,out);
      /* Negative argument probes never entered the factory. Still return a
         genuine dependent child so its nominal result contract remains exact. */
      mode=0;
    }
    void *p=NULL;TRY(api->resource_borrow(call,args[0],parentType,&p));Input in={(Object*)p,mode,args[0]};
    nex_ffi_ref parents[2]={args[0],args[0]},child=0;
    nex_ffi_status status=api->resource_create_with_parents(call,type,sizeof(Object),parents,mode==4?2:1,factory,destroy,&in,&child);
    if(op==7&&status==NEX_FFI_LIMIT)return api->make_failure(call,(const uint8_t*)"QUOTA",5,(const uint8_t*)"capacity retained",17,out);
    if(status!=NEX_FFI_OK)return status;
    if(op==7)return api->make_success(call,child,out);*out=child;return NEX_FFI_OK;
  }
  return NEX_FFI_ARGUMENT;
}
static const nex_ffi_export_v1 exports[]={
  {sizeof(nex_ffi_export_v1),0,"session",PIN_SESSION,callback,(void*)1},
  {sizeof(nex_ffi_export_v1),0,"buffer",PIN_BUFFER,callback,(void*)2},
  {sizeof(nex_ffi_export_v1),0,"extend",PIN_EXTEND,callback,(void*)6},
  {sizeof(nex_ffi_export_v1),0,"read",PIN_READ,callback,(void*)3},
  {sizeof(nex_ffi_export_v1),0,"status",PIN_STATUS,callback,(void*)4},
  {sizeof(nex_ffi_export_v1),0,"stale",PIN_STALE,callback,(void*)5},
  {sizeof(nex_ffi_export_v1),0,"try_buffer",PIN_TRY_BUFFER,callback,(void*)7},
  {sizeof(nex_ffi_export_v1),0,"try_session",PIN_TRY_SESSION,callback,(void*)8},
  {sizeof(nex_ffi_export_v1),0,"hold",PIN_HOLD,callback,(void*)9},
  {sizeof(nex_ffi_export_v1),0,"started",PIN_STARTED,callback,(void*)10}
};
static const nex_ffi_module_v1 module={NEX_FFI_MODULE_ABI_V1,sizeof(nex_ffi_module_v1),sizeof(exports)/sizeof(exports[0]),sizeof(nex_ffi_export_v1),exports};
const nex_ffi_module_v1 *nex_ffi_module_entry(uint32_t abi,uint32_t size){return abi==NEX_FFI_ABI_V1&&size>=NEX_FFI_V1_RESOURCE_PARENTS_SIZE?&module:NULL;}
