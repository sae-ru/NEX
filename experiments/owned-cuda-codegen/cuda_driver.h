#pragma once
// Minimal declarations for the explicitly versioned CUDA Driver C entry points
// used here. No CUDA implementation, vendor headers or runtime are bundled.
#include <cstddef>
#include <cstdint>
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#define CUDA_CALL __stdcall
#else
#include <dlfcn.h>
#define CUDA_CALL
#endif
namespace cuda_api {
static_assert(sizeof(void*)==8);
using CUresult=int;
using CUdevice=int;
using CUdeviceptr=unsigned long long;
using CUcontext=void*;
using CUmodule=void*;
using CUfunction=void*;
using CUstream=void*;
using CUevent=void*;
struct CUuuid {char bytes[16];};
constexpr CUresult CUDA_SUCCESS=0,CUDA_ERROR_NOT_READY=600,CUDA_ERROR_INVALID_CONTEXT=201;
constexpr unsigned CU_CTX_SCHED_BLOCKING_SYNC=4,CU_STREAM_NON_BLOCKING=1,CU_EVENT_DEFAULT=0;
struct Library {
#ifdef _WIN32
  HMODULE value=LoadLibraryExW(L"nvcuda.dll",nullptr,LOAD_LIBRARY_SEARCH_SYSTEM32);
  void *symbol(const char *name)const{return value?reinterpret_cast<void*>(GetProcAddress(value,name)):nullptr;}
  ~Library(){if(value)FreeLibrary(value);}
#else
  void *value=dlopen("libcuda.so.1",RTLD_NOW|RTLD_LOCAL);
  void *symbol(const char *name)const{return value?dlsym(value,name):nullptr;}
  ~Library(){if(value)dlclose(value);}
#endif
  Library()=default;
  Library(const Library&)=delete;
  Library& operator=(const Library&)=delete;
};
extern "C" {
CUresult CUDA_CALL cuInit(unsigned);
CUresult CUDA_CALL cuDriverGetVersion(int*);
CUresult CUDA_CALL cuDeviceGetCount(int*);
CUresult CUDA_CALL cuDeviceGet(CUdevice*,int);
CUresult CUDA_CALL cuDeviceGetName(char*,int,CUdevice);
CUresult CUDA_CALL cuDeviceGetUuid(CUuuid*,CUdevice);
CUresult CUDA_CALL cuDeviceGetPCIBusId(char*,int,CUdevice);
CUresult CUDA_CALL cuCtxCreate(CUcontext*,unsigned,CUdevice);
CUresult CUDA_CALL cuCtxDestroy(CUcontext);
CUresult CUDA_CALL cuCtxPushCurrent(CUcontext);
CUresult CUDA_CALL cuCtxPopCurrent(CUcontext*);
CUresult CUDA_CALL cuCtxGetCurrent(CUcontext*);
CUresult CUDA_CALL cuCtxSynchronize();
CUresult CUDA_CALL cuModuleLoadData(CUmodule*,const void*);
CUresult CUDA_CALL cuModuleUnload(CUmodule);
CUresult CUDA_CALL cuModuleGetFunction(CUfunction*,CUmodule,const char*);
CUresult CUDA_CALL cuStreamCreate(CUstream*,unsigned);
CUresult CUDA_CALL cuStreamDestroy(CUstream);
CUresult CUDA_CALL cuMemAlloc(CUdeviceptr*,size_t);
CUresult CUDA_CALL cuMemFree(CUdeviceptr);
CUresult CUDA_CALL cuMemcpyHtoD(CUdeviceptr,const void*,size_t);
CUresult CUDA_CALL cuMemcpyDtoH(void*,CUdeviceptr,size_t);
CUresult CUDA_CALL cuLaunchKernel(CUfunction,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,CUstream,void**,void**);
CUresult CUDA_CALL cuEventCreate(CUevent*,unsigned);
CUresult CUDA_CALL cuEventDestroy(CUevent);
CUresult CUDA_CALL cuEventRecord(CUevent,CUstream);
CUresult CUDA_CALL cuEventQuery(CUevent);
CUresult CUDA_CALL cuEventSynchronize(CUevent);
CUresult CUDA_CALL cuEventElapsedTime(float*,CUevent,CUevent);
}
}
#undef CUDA_CALL
