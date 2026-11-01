// Physical CUDA prerequisite probe. This deliberately does not claim NEX FFI
// integration: it exercises the installed driver through its C ABI only.
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <cuda.h>
#include "third_party/json.hpp"
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <vector>

using J=nlohmann::ordered_json;
namespace {
struct Driver {
 uint64_t allocations=0,frees=0,liveBytes=0,peakBytes=0,events=0,eventFrees=0,contexts=0,contextFrees=0,modules=0,moduleFrees=0,cleanupErrors=0;
 int lastCleanupError=0;const char *lastCleanupOperation="";
 bool cleanup(CUresult result,const char *operation)noexcept{if(result==CUDA_SUCCESS)return true;++cleanupErrors;lastCleanupError=int(result);lastCleanupOperation=operation;return false;}
 HMODULE library=LoadLibraryExW(L"nvcuda.dll",nullptr,LOAD_LIBRARY_SEARCH_SYSTEM32);
 void *symbol(const char *name){if(!library)throw std::runtime_error("system CUDA driver unavailable");auto p=GetProcAddress(library,name);if(!p)throw std::runtime_error(std::string("CUDA symbol unavailable: ")+name);return reinterpret_cast<void*>(p);}
#define CUDA_PROC(name,entry) decltype(&name) p_##name=reinterpret_cast<decltype(&name)>(symbol(entry))
 CUDA_PROC(cuInit,"cuInit");CUDA_PROC(cuDriverGetVersion,"cuDriverGetVersion");
 CUDA_PROC(cuDeviceGetCount,"cuDeviceGetCount");CUDA_PROC(cuDeviceGet,"cuDeviceGet");
 CUDA_PROC(cuDeviceGetName,"cuDeviceGetName");CUDA_PROC(cuDeviceGetUuid,"cuDeviceGetUuid");
 CUDA_PROC(cuDeviceGetPCIBusId,"cuDeviceGetPCIBusId");
 CUDA_PROC(cuCtxCreate,"cuCtxCreate_v2");CUDA_PROC(cuCtxDestroy,"cuCtxDestroy_v2");
 CUDA_PROC(cuCtxSynchronize,"cuCtxSynchronize");CUDA_PROC(cuModuleLoadData,"cuModuleLoadData");
 CUDA_PROC(cuModuleUnload,"cuModuleUnload");CUDA_PROC(cuModuleGetFunction,"cuModuleGetFunction");
 CUDA_PROC(cuMemAlloc,"cuMemAlloc_v2");CUDA_PROC(cuMemFree,"cuMemFree_v2");
 CUDA_PROC(cuMemGetInfo,"cuMemGetInfo_v2");CUDA_PROC(cuMemcpyHtoD,"cuMemcpyHtoD_v2");
 CUDA_PROC(cuMemcpyDtoH,"cuMemcpyDtoH_v2");CUDA_PROC(cuLaunchKernel,"cuLaunchKernel");
 CUDA_PROC(cuEventCreate,"cuEventCreate");CUDA_PROC(cuEventDestroy,"cuEventDestroy_v2");
 CUDA_PROC(cuEventRecord,"cuEventRecord");CUDA_PROC(cuEventSynchronize,"cuEventSynchronize");
 CUDA_PROC(cuEventElapsedTime,"cuEventElapsedTime");
#undef CUDA_PROC
 void check(CUresult result){if(result!=CUDA_SUCCESS)throw std::runtime_error("CUDA driver error "+std::to_string(int(result)));}
 ~Driver(){if(library)FreeLibrary(library);}
};
constexpr char ptx[]=R"ptx(
.version 7.0
.target sm_52
.address_size 64
.visible .entry u8_op(.param .u64 input_a,.param .u64 input_b,.param .u64 output,
 .param .u64 overflow,.param .u32 length,.param .u32 mode,.param .u32 scale,.param .u32 bias){
 .reg .pred %p<4>;
 .reg .b32 %r<20>;
 .reg .b64 %rd<12>;
 ld.param.u64 %rd1,[input_a];ld.param.u64 %rd2,[input_b];
 ld.param.u64 %rd3,[output];ld.param.u64 %rd4,[overflow];
 ld.param.u32 %r1,[length];ld.param.u32 %r2,[mode];
 ld.param.u32 %r3,[scale];ld.param.u32 %r4,[bias];
 mov.u32 %r5,%ctaid.x;mov.u32 %r6,%ntid.x;mov.u32 %r7,%tid.x;
 mad.lo.u32 %r8,%r5,%r6,%r7;setp.ge.u32 %p1,%r8,%r1;@%p1 bra DONE;
 cvt.u64.u32 %rd5,%r8;add.u64 %rd6,%rd1,%rd5;ld.global.u8 %r9,[%rd6];
 setp.eq.u32 %p2,%r2,0;@!%p2 bra AFFINE;
 add.u64 %rd7,%rd2,%rd5;ld.global.u8 %r10,[%rd7];add.u32 %r11,%r9,%r10;bra STORE;
 AFFINE:mad.lo.u32 %r11,%r9,%r3,%r4;
 STORE:setp.gt.u32 %p3,%r11,255;@%p3 atom.global.add.u32 %r12,[%rd4],1;
 add.u64 %rd8,%rd3,%rd5;st.global.u8 [%rd8],%r11;
 DONE:ret;
}
)ptx";
struct Context {
 Driver &driver;CUcontext context=nullptr;CUmodule module=nullptr;
 explicit Context(Driver &d,CUdevice device):driver(d){driver.check(driver.p_cuCtxCreate(&context,0,device));++driver.contexts;}
 ~Context(){if(context){driver.cleanup(driver.p_cuCtxSynchronize(),"cuCtxSynchronize");if(module&&driver.cleanup(driver.p_cuModuleUnload(module),"cuModuleUnload"))++driver.moduleFrees;if(driver.cleanup(driver.p_cuCtxDestroy(context),"cuCtxDestroy"))++driver.contextFrees;}}
};
struct Buffer {
 Driver &driver;CUdeviceptr pointer=0;const size_t bytes;
 Buffer(Driver &d,size_t bytes):driver(d),bytes(bytes){driver.check(driver.p_cuMemAlloc(&pointer,bytes));++driver.allocations;driver.liveBytes+=bytes;driver.peakBytes=std::max(driver.peakBytes,driver.liveBytes);}
 ~Buffer(){if(pointer&&driver.cleanup(driver.p_cuMemFree(pointer),"cuMemFree")){++driver.frees;driver.liveBytes-=bytes;}}
};
struct Event {
 Driver &driver;CUevent event=nullptr;
 explicit Event(Driver &d):driver(d){driver.check(driver.p_cuEventCreate(&event,0));++driver.events;}
 ~Event(){if(event&&driver.cleanup(driver.p_cuEventDestroy(event),"cuEventDestroy"))++driver.eventFrees;}
};
double elapsed(std::chrono::steady_clock::time_point start){return std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count();}
}
int main(){J report={{"schema","nex.windows-cuda-prerequisite/1"},{"ok",false},{"execution","native Windows"},
 {"NEX_invocation",false},{"owned_NEX_device_adapter_accepted",false},{"fallback",false},{"cases",J::array()}};
 try{
  Driver d;d.check(d.p_cuInit(0));int count=0,version=0;d.check(d.p_cuDeviceGetCount(&count));d.check(d.p_cuDriverGetVersion(&version));
  if(count<1)throw std::runtime_error("no physical CUDA device");
  CUdevice device=0;d.check(d.p_cuDeviceGet(&device,0));char name[256]{},pci[32]{};CUuuid uuid{};
  d.check(d.p_cuDeviceGetName(name,sizeof(name),device));d.check(d.p_cuDeviceGetPCIBusId(pci,sizeof(pci),device));d.check(d.p_cuDeviceGetUuid(&uuid,device));
  std::string uuidHex;for(unsigned char byte:uuid.bytes){uuidHex+="0123456789abcdef"[byte>>4];uuidHex+="0123456789abcdef"[byte&15];}
  report["device"]={{"ordinal",0},{"count",count},{"name",name},{"pci_bus_id",pci},{"uuid_hex",uuidHex},{"driver_version",version}};
  unsigned launches=0;
  {
   Context context(d,device);d.check(d.p_cuModuleLoadData(&context.module,ptx));++d.modules;CUfunction kernel=nullptr;
   d.check(d.p_cuModuleGetFunction(&kernel,context.module,"u8_op"));size_t freeBefore=0,total=0;d.check(d.p_cuMemGetInfo(&freeBefore,&total));
   for(unsigned n:{1u,31u,32u,255u,256u,257u,1023u,4096u,262144u})for(unsigned mode:{0u,1u})for(unsigned repeat:{0u,1u}){
    std::vector<uint8_t> a(n),b(n),output(n),reference(n);unsigned scale=2,bias=7,overflows=0;
    auto cpuStart=std::chrono::steady_clock::now();for(unsigned i=0;i<n;++i){a[i]=uint8_t((i*17+repeat)%100);b[i]=uint8_t((i*7+3)%100);reference[i]=uint8_t(mode?unsigned(a[i])*scale+bias:unsigned(a[i])+b[i]);}
    double cpuMs=elapsed(cpuStart);auto wall=std::chrono::steady_clock::now();
    Buffer da(d,n),db(d,n),dc(d,n),flag(d,sizeof(unsigned));Event start(d),end(d);
    auto copy=std::chrono::steady_clock::now();d.check(d.p_cuMemcpyHtoD(da.pointer,a.data(),n));d.check(d.p_cuMemcpyHtoD(db.pointer,b.data(),n));d.check(d.p_cuMemcpyHtoD(flag.pointer,&overflows,sizeof(overflows)));double uploadMs=elapsed(copy);
    void *params[]={&da.pointer,&db.pointer,&dc.pointer,&flag.pointer,&n,&mode,&scale,&bias};
    d.check(d.p_cuEventRecord(start.event,nullptr));d.check(d.p_cuLaunchKernel(kernel,(n+255)/256,1,1,256,1,1,0,nullptr,params,nullptr));
    d.check(d.p_cuEventRecord(end.event,nullptr));d.check(d.p_cuEventSynchronize(end.event));++launches;
    float kernelMs=0;d.check(d.p_cuEventElapsedTime(&kernelMs,start.event,end.event));copy=std::chrono::steady_clock::now();
    d.check(d.p_cuMemcpyDtoH(output.data(),dc.pointer,n));d.check(d.p_cuMemcpyDtoH(&overflows,flag.pointer,sizeof(overflows)));double downloadMs=elapsed(copy);
    if(overflows||output!=reference)throw std::runtime_error("physical CUDA result differs from independent CPU reference");
    report["cases"].push_back({{"status","passed"},{"operation",mode?"U8 Affine(2,7)":"U8 Add"},{"elements",n},{"repeat",repeat},
     {"cpu_reference_ms",cpuMs},{"upload_ms",uploadMs},{"GPU_kernel_ms",kernelMs},{"download_ms",downloadMs},{"total_ms",elapsed(wall)}});
   }
   // Exercise overflow on the actual GPU and inspect its out-of-band flag.
   for(unsigned mode:{0u,1u}){
    unsigned n=1,scale=2,bias=7,overflow=0;uint8_t a=255,b=1,result=0;
    Buffer da(d,1),db(d,1),dc(d,1),flag(d,sizeof(unsigned));
    d.check(d.p_cuMemcpyHtoD(da.pointer,&a,1));d.check(d.p_cuMemcpyHtoD(db.pointer,&b,1));d.check(d.p_cuMemcpyHtoD(flag.pointer,&overflow,sizeof(overflow)));
    void *params[]={&da.pointer,&db.pointer,&dc.pointer,&flag.pointer,&n,&mode,&scale,&bias};
    d.check(d.p_cuLaunchKernel(kernel,1,1,1,1,1,1,0,nullptr,params,nullptr));d.check(d.p_cuCtxSynchronize());++launches;
    d.check(d.p_cuMemcpyDtoH(&result,dc.pointer,1));d.check(d.p_cuMemcpyDtoH(&overflow,flag.pointer,sizeof(overflow)));
    if(overflow!=1)throw std::runtime_error("GPU overflow flag differs");
    report["cases"].push_back({{"status","passed"},{"operation",mode?"Affine overflow":"Add overflow"},{"elements",1},{"GPU_overflow_count",overflow}});
   }
   d.check(d.p_cuCtxSynchronize());size_t freeAfter=0;d.check(d.p_cuMemGetInfo(&freeAfter,&total));
   report["device_memory"]={{"free_before",freeBefore},{"free_after",freeAfter},{"total",total},{"shared_display_device",true}};
  }
  report["resource_ledger"]={{"buffers_allocated",d.allocations},{"buffers_freed",d.frees},{"live_buffer_bytes",d.liveBytes},{"peak_buffer_bytes",d.peakBytes},
   {"events_created",d.events},{"events_destroyed",d.eventFrees},{"contexts_created",d.contexts},{"contexts_destroyed",d.contextFrees},
   {"modules_loaded",d.modules},{"modules_unloaded",d.moduleFrees},{"cleanup_errors",d.cleanupErrors},{"last_cleanup_error",d.lastCleanupError},{"last_cleanup_operation",d.lastCleanupOperation}};
  if(d.allocations!=d.frees||d.liveBytes||d.events!=d.eventFrees||d.contexts!=d.contextFrees||d.modules!=d.moduleFrees||d.cleanupErrors)
   throw std::runtime_error("CUDA physical resource cleanup did not balance");
  report["kernel_launches"]=launches;report["physical_completion_before_resource_release"]=true;
  report["pending"]=J::array({"NEX Windows checked FFI loader","std/device CUDA provider","task cancellation/deadline/typed errors","CUDA provider sanitizer acceptance","Windows SDK acceptance"});
  report["ok"]=true;std::cout<<report.dump(2)<<'\n';return 0;
 }catch(const std::exception &error){report["failure"]=error.what();std::cout<<report.dump(2)<<'\n';return 1;}
}
