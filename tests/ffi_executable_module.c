#ifndef _GNU_SOURCE
#define _GNU_SOURCE 1
#endif
#include "nex_ffi_module.h"
#include <dlfcn.h>
#include <errno.h>
#include <spawn.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>
extern char **environ;
static nex_ffi_status callback(const nex_ffi_api_v1 *api,nex_ffi_call call,const nex_ffi_ref *args,uint64_t count,nex_ffi_ref *out,void *user){
 (void)args;(void)user;if(count!=1)return NEX_FFI_ARGUMENT;Dl_info info;if(!dladdr((const void*)&callback,&info)||!info.dli_fname)return NEX_FFI_INTERNAL;
 char directory[4096];size_t n=strlen(info.dli_fname);if(n>=sizeof(directory))return NEX_FFI_LIMIT;memcpy(directory,info.dli_fname,n+1);char *last=strrchr(directory,'/');if(!last)return NEX_FFI_INTERNAL;*last=0;
 char worker[4096],notice[4096];if(snprintf(worker,sizeof(worker),"%s/worker",directory)>=(int)sizeof(worker)||snprintf(notice,sizeof(notice),"%s/legal/NOTICE",directory)>=(int)sizeof(notice))return NEX_FFI_LIMIT;
 struct stat st;if(stat(directory,&st)||(st.st_mode&0777)!=0500)return NEX_FFI_INTERNAL;if(stat(notice,&st)||(st.st_mode&0777)!=0400)return NEX_FFI_INTERNAL;
 if(stat(worker,&st)||((st.st_mode&0777)!=0400&&(st.st_mode&0777)!=0500))return NEX_FFI_INTERNAL;
 pid_t pid=-1;char *argv[]={worker,NULL};int code=posix_spawn(&pid,worker,NULL,NULL,argv,environ);if(code)return api->make_i64(call,-code,out);
 int status=0;while(waitpid(pid,&status,0)<0){if(errno!=EINTR)return NEX_FFI_INTERNAL;}if(!WIFEXITED(status))return NEX_FFI_INTERNAL;return api->make_i64(call,WEXITSTATUS(status),out);
}
const nex_ffi_module_v1 *nex_ffi_module_entry(uint32_t abi,uint32_t bytes){
 static const nex_ffi_export_v1 exports[]={
  {sizeof(nex_ffi_export_v1),0,"echo","67271321265625b9f0499796f5997cf2f9c6161ed418867840d9551d879f987d",callback,NULL},
  {sizeof(nex_ffi_export_v1),0,"wrong","67271321265625b9f0499796f5997cf2f9c6161ed418867840d9551d879f987d",callback,NULL}};
 static const nex_ffi_module_v1 module={1,sizeof(nex_ffi_module_v1),2,sizeof(nex_ffi_export_v1),exports};return abi==1&&bytes>=sizeof(nex_ffi_api_v1)?&module:NULL;
}
