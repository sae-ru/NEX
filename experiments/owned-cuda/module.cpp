// Trusted Windows CUDA Driver API provider. Only the versioned C value/resource
// table crosses the NEX boundary; CUDA pointers remain private to this image.
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <cuda.h>
#include "nex_ffi_module.h"
#include "signatures.h"
#include "third_party/json.hpp"
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstring>
#include <cstdio>
#include <exception>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

using JSON=nlohmann::json;
using Clock=std::chrono::steady_clock;
struct HostStatus {nex_ffi_status value;};
struct Error:std::runtime_error {
  std::string code;
  Error(std::string code,std::string message):std::runtime_error(std::move(message)),code(std::move(code)){}
};
static void checked(nex_ffi_status status){if(status!=NEX_FFI_OK)throw HostStatus{status};}
static uint64_t ns(Clock::time_point start){return uint64_t(std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now()-start).count());}
struct Ledger {
  std::atomic<uint64_t> contexts{0},contextFrees{0},modules{0},moduleFrees{0},streams{0},streamFrees{0};
  std::atomic<uint64_t> buffers{0},bufferFrees{0},bytes{0},peakBytes{0},events{0},eventFrees{0},launches{0},cleanupErrors{0};
  JSON json()const{return JSON{{"contexts",contexts.load()},{"context_frees",contextFrees.load()},{"modules",modules.load()},{"module_frees",moduleFrees.load()},
    {"streams",streams.load()},{"stream_frees",streamFrees.load()},{"allocations",buffers.load()},{"frees",bufferFrees.load()},
    {"live_bytes",bytes.load()},{"peak_bytes",peakBytes.load()},{"events",events.load()},{"event_frees",eventFrees.load()},
    {"kernel_launches",launches.load()},{"cleanup_errors",cleanupErrors.load()}};}
  void allocate(uint64_t size){++buffers;auto live=bytes.fetch_add(size)+size;auto peak=peakBytes.load();while(live>peak&&!peakBytes.compare_exchange_weak(peak,live)){}}
  void free(uint64_t size){++bufferFrees;bytes.fetch_sub(size);}
};
static Ledger ledger;
static SRWLOCK traceLock=SRWLOCK_INIT;
static std::atomic<uint64_t> identities{1};
static void trace(JSON row)noexcept{
  try{
    wchar_t path[32768];auto size=GetEnvironmentVariableW(L"NEX_OWNED_CUDA_TRACE",path,32768);
    if(!size||size>=32768)return;
    row["steady_ns"]=uint64_t(std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now().time_since_epoch()).count());
    row["ledger"]=ledger.json();auto data=row.dump()+"\n";
    AcquireSRWLockExclusive(&traceLock);
    HANDLE file=CreateFileW(path,FILE_APPEND_DATA,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,nullptr,OPEN_ALWAYS,FILE_ATTRIBUTE_NORMAL,nullptr);
    if(file!=INVALID_HANDLE_VALUE){size_t offset=0;while(offset<data.size()){DWORD written=0;if(!WriteFile(file,data.data()+offset,DWORD(data.size()-offset),&written,nullptr)||!written)break;offset+=written;}CloseHandle(file);}
    ReleaseSRWLockExclusive(&traceLock);
  }catch(...){}
}
[[noreturn]] static void unsettled(const char *operation,CUresult code)noexcept{
  ++ledger.cleanupErrors;trace(JSON{{"event","unsettled"},{"operation",operation},{"cuda_error",int(code)},{"physical_completion_verified",false}});
  std::fprintf(stderr,"E_DEVICE_UNSETTLED: CUDA %s returned %d; device resources and code remain retained\n",operation,int(code));
  // An unknown physical completion state is never reported as released
  // capacity. A parent deadline cannot make GPU/DMA completion true.
  for(;;)Sleep(1000);
}
struct Library {
  HMODULE value=LoadLibraryExW(L"nvcuda.dll",nullptr,LOAD_LIBRARY_SEARCH_SYSTEM32);
  ~Library(){if(value)FreeLibrary(value);}
};
struct Driver {
  Library library;
  void *symbol(const char *name){if(!library.value)throw Error("E_COMPUTE_UNAVAILABLE","Windows CUDA driver is unavailable");auto value=GetProcAddress(library.value,name);if(!value)throw Error("E_DEVICE_ABI",std::string("CUDA symbol unavailable: ")+name);return reinterpret_cast<void*>(value);}
#define CUDA_PROC(name,entry) decltype(&name) p_##name=reinterpret_cast<decltype(&name)>(symbol(entry))
  CUDA_PROC(cuInit,"cuInit");CUDA_PROC(cuDriverGetVersion,"cuDriverGetVersion");
  CUDA_PROC(cuDeviceGetCount,"cuDeviceGetCount");CUDA_PROC(cuDeviceGet,"cuDeviceGet");
  CUDA_PROC(cuDeviceGetName,"cuDeviceGetName");CUDA_PROC(cuDeviceGetUuid,"cuDeviceGetUuid");
  CUDA_PROC(cuDeviceGetPCIBusId,"cuDeviceGetPCIBusId");CUDA_PROC(cuDeviceGetAttribute,"cuDeviceGetAttribute");
  CUDA_PROC(cuCtxCreate,"cuCtxCreate_v2");CUDA_PROC(cuCtxDestroy,"cuCtxDestroy_v2");
  CUDA_PROC(cuCtxPushCurrent,"cuCtxPushCurrent_v2");CUDA_PROC(cuCtxPopCurrent,"cuCtxPopCurrent_v2");
  CUDA_PROC(cuCtxSynchronize,"cuCtxSynchronize");CUDA_PROC(cuModuleLoadData,"cuModuleLoadData");
  CUDA_PROC(cuModuleUnload,"cuModuleUnload");CUDA_PROC(cuModuleGetFunction,"cuModuleGetFunction");
  CUDA_PROC(cuStreamCreate,"cuStreamCreate");CUDA_PROC(cuStreamDestroy,"cuStreamDestroy_v2");
  CUDA_PROC(cuMemAlloc,"cuMemAlloc_v2");CUDA_PROC(cuMemFree,"cuMemFree_v2");
  CUDA_PROC(cuMemcpyHtoD,"cuMemcpyHtoD_v2");CUDA_PROC(cuMemcpyDtoH,"cuMemcpyDtoH_v2");
  CUDA_PROC(cuLaunchKernel,"cuLaunchKernel");CUDA_PROC(cuEventCreate,"cuEventCreate");
  CUDA_PROC(cuEventDestroy,"cuEventDestroy_v2");CUDA_PROC(cuEventRecord,"cuEventRecord");
  CUDA_PROC(cuEventQuery,"cuEventQuery");CUDA_PROC(cuEventSynchronize,"cuEventSynchronize");
  CUDA_PROC(cuEventElapsedTime,"cuEventElapsedTime");
#undef CUDA_PROC
  void check(CUresult code,const char *operation){if(code!=CUDA_SUCCESS)throw Error("E_DEVICE_API",std::string(operation)+" returned CUDA "+std::to_string(int(code)));}
  void cleanup(CUresult code,const char *operation)noexcept{if(code!=CUDA_SUCCESS)unsettled(operation,code);}
};
static constexpr char ptx[]=R"ptx(
.version 7.0
.target sm_52
.address_size 64
.visible .entry u8_op(.param .u64 input_a,.param .u64 input_b,.param .u64 output,
 .param .u64 overflow,.param .u32 length,.param .u32 mode,.param .u32 scale,.param .u64 delay_cycles){
 .reg .pred %p<5>;
 .reg .b32 %r<18>;
 .reg .b64 %rd<18>;
 ld.param.u64 %rd1,[input_a];ld.param.u64 %rd2,[input_b];
 ld.param.u64 %rd3,[output];ld.param.u64 %rd4,[overflow];
 ld.param.u32 %r1,[length];ld.param.u32 %r2,[mode];ld.param.u32 %r3,[scale];
 ld.param.u64 %rd9,[delay_cycles];
 mov.u32 %r5,%ctaid.x;mov.u32 %r6,%ntid.x;mov.u32 %r7,%tid.x;
 mad.lo.u32 %r8,%r5,%r6,%r7;setp.ge.u32 %p1,%r8,%r1;@%p1 bra DONE;
 setp.ne.u32 %p4,%r8,0;@%p4 bra CALCULATE;
 mov.u64 %rd10,%clock64;
 WAIT:mov.u64 %rd11,%clock64;sub.u64 %rd12,%rd11,%rd10;
 setp.lt.u64 %p4,%rd12,%rd9;@%p4 bra WAIT;
 CALCULATE:cvt.u64.u32 %rd5,%r8;add.u64 %rd6,%rd1,%rd5;ld.global.u8 %r9,[%rd6];
 add.u64 %rd7,%rd2,%rd5;ld.global.u8 %r10,[%rd7];
 setp.eq.u32 %p2,%r2,1;@!%p2 bra AFFINE;
 add.u32 %r11,%r9,%r10;bra STORE;
 AFFINE:mad.lo.u32 %r11,%r9,%r3,%r10;
 STORE:setp.gt.u32 %p3,%r11,255;@%p3 atom.global.add.u32 %r12,[%rd4],1;
 add.u64 %rd8,%rd3,%rd5;st.global.u8 [%rd8],%r11;
 DONE:ret;
}
)ptx";
struct Session {
  Driver driver;
  std::timed_mutex mutex;
  CUcontext context=nullptr;CUmodule module=nullptr;CUfunction kernel=nullptr;CUstream stream=nullptr;CUdeviceptr overflow=0;
  const uint64_t identity=identities.fetch_add(1);
  std::atomic<uint32_t> busy{0};
  uint64_t delayCycles=0;unsigned acceptanceLaunches=1;
  std::string name,uuid,pci;
  void start(unsigned ordinal){
    driver.check(driver.p_cuInit(0),"cuInit");int count=0,version=0;driver.check(driver.p_cuDeviceGetCount(&count),"cuDeviceGetCount");
    if(ordinal>=unsigned(std::max(0,count)))throw Error("E_COMPUTE_UNAVAILABLE","selected physical CUDA GPU is unavailable");
    CUdevice device=0;driver.check(driver.p_cuDeviceGet(&device,int(ordinal)),"cuDeviceGet");
    char label[256]{},bus[32]{};CUuuid id{};
    driver.check(driver.p_cuDeviceGetName(label,sizeof(label),device),"cuDeviceGetName");
    driver.check(driver.p_cuDeviceGetPCIBusId(bus,sizeof(bus),device),"cuDeviceGetPCIBusId");
    driver.check(driver.p_cuDeviceGetUuid(&id,device),"cuDeviceGetUuid");driver.check(driver.p_cuDriverGetVersion(&version),"cuDriverGetVersion");
    for(unsigned char byte:id.bytes){uuid+="0123456789abcdef"[byte>>4];uuid+="0123456789abcdef"[byte&15];}
    pci=bus;name=std::string(label)+" UUID="+uuid+" PCI="+pci;
    wchar_t delay[32];auto n=GetEnvironmentVariableW(L"NEX_CUDA_ACCEPTANCE_DELAY_CYCLES",delay,32);
    if(n){if(n>=32)throw Error("E_DEVICE_CONFIG","invalid bounded acceptance delay");wchar_t *end=nullptr;auto value=wcstoull(delay,&end,10);if(!end||*end||value>200000000)throw Error("E_DEVICE_CONFIG","acceptance delay must be0..200000000 GPU cycles");delayCycles=value;}
    n=GetEnvironmentVariableW(L"NEX_CUDA_ACCEPTANCE_KERNEL_REPEATS",delay,32);
    if(n){if(n>=32)throw Error("E_DEVICE_CONFIG","invalid bounded acceptance repeat count");wchar_t *end=nullptr;auto value=wcstoul(delay,&end,10);if(!end||*end||!value||value>32)throw Error("E_DEVICE_CONFIG","acceptance kernel repeats must be1..32");acceptanceLaunches=unsigned(value);}
    driver.check(driver.p_cuCtxCreate(&context,CU_CTX_SCHED_BLOCKING_SYNC,device),"cuCtxCreate");++ledger.contexts;
    CUcontext popped=nullptr;driver.check(driver.p_cuCtxPopCurrent(&popped),"cuCtxPopCurrent");if(popped!=context)unsettled("context creation identity",CUDA_ERROR_INVALID_CONTEXT);
    trace(JSON{{"event","session_created"},{"session",identity},{"ordinal",ordinal},{"name",label},{"uuid",uuid},{"pci_bus_id",pci},{"driver_version",version},{"acceptance_delay_cycles",delayCycles},{"acceptance_kernel_repeats",acceptanceLaunches},{"cpu_fallback",false}});
  }
  void drain()noexcept{driver.cleanup(driver.p_cuCtxSynchronize(),"cuCtxSynchronize");}
  ~Session()noexcept{
    if(!context)return;std::lock_guard lock(mutex);driver.cleanup(driver.p_cuCtxPushCurrent(context),"cuCtxPushCurrent cleanup");drain();
    if(overflow){driver.cleanup(driver.p_cuMemFree(overflow),"cuMemFree scratch");ledger.free(4);overflow=0;}
    if(stream){driver.cleanup(driver.p_cuStreamDestroy(stream),"cuStreamDestroy");++ledger.streamFrees;stream=nullptr;}
    if(module){driver.cleanup(driver.p_cuModuleUnload(module),"cuModuleUnload");++ledger.moduleFrees;module=nullptr;}
    CUcontext popped=nullptr;driver.cleanup(driver.p_cuCtxPopCurrent(&popped),"cuCtxPopCurrent cleanup");if(popped!=context)unsettled("context cleanup identity",CUDA_ERROR_INVALID_CONTEXT);
    driver.cleanup(driver.p_cuCtxDestroy(context),"cuCtxDestroy");++ledger.contextFrees;context=nullptr;
    trace(JSON{{"event","session_destroyed"},{"session",identity},{"physical_completion_verified",true}});
  }
};
struct Context {
  Session &session;std::unique_lock<std::timed_mutex> lock;
  Context *previous=nullptr;
  static thread_local Context *active;
  Context(Session &session,const nex_ffi_api_v1 *api=nullptr,nex_ffi_call call=0):session(session),lock(session.mutex,std::defer_lock){
    bool held=false;
    for(auto frame=active;frame;frame=frame->previous)if(&frame->session==&session){
      if(api)throw Error("E_DEVICE_REENTRANT","a CUDA operation cannot reenter its active session");
      held=true;break;
    }
    // A host poll can retire a different, unborrowed buffer on this thread.
    // Private physical cleanup reuses that already-held session lock, pushes
    // its context, drains, and restores the previous context. Source API calls
    // still reject reentry before touching shared scratch or queue state.
    if(!held){if(api){while(!lock.try_lock_for(std::chrono::milliseconds(1)))checked(api->poll(call));}else lock.lock();}
    previous=active;active=this;
    try{
      if(api)checked(api->poll(call));
      auto status=session.driver.p_cuCtxPushCurrent(session.context);
      if(api)session.driver.check(status,"cuCtxPushCurrent");else session.driver.cleanup(status,"cuCtxPushCurrent cleanup");
    }catch(...){active=previous;throw;}
  }
  ~Context(){CUcontext popped=nullptr;session.driver.cleanup(session.driver.p_cuCtxPopCurrent(&popped),"cuCtxPopCurrent");if(popped!=session.context)unsettled("operation context identity",CUDA_ERROR_INVALID_CONTEXT);active=previous;}
};
thread_local Context *Context::active=nullptr;
struct Event {
  Driver &driver;CUevent value=nullptr;
  explicit Event(Driver &driver):driver(driver){driver.check(driver.p_cuEventCreate(&value,CU_EVENT_DEFAULT),"cuEventCreate");++ledger.events;}
  ~Event(){if(value){driver.cleanup(driver.p_cuEventDestroy(value),"cuEventDestroy");++ledger.eventFrees;}}
};
struct Buffer {
  Session *session=nullptr;CUdeviceptr pointer=0;uint64_t bytes=0,kernelNs=0;uint32_t dtype=0;
  ~Buffer(){if(pointer){Context context(*session);session->drain();session->driver.cleanup(session->driver.p_cuMemFree(pointer),"cuMemFree buffer");ledger.free(bytes);
    trace(JSON{{"event","buffer_released"},{"session",session->identity},{"bytes",bytes},{"physical_completion_verified",true}});}}
};
struct InFlight {
  Session &session;CUevent end;bool done=false;
  ~InFlight(){if(!done){session.drain();auto result=session.driver.p_cuEventQuery(end);if(result!=CUDA_SUCCESS)unsettled("event after physical drain",result);
    trace(JSON{{"event","physical_drain"},{"session",session.identity},{"physical_completion_verified",true},{"event_status",int(result)},{"unwind",true}});}session.busy=0;}
};
struct Creation {
  enum Kind{Open,Upload,Dispatch}kind;
  Session *session=nullptr;Buffer *a=nullptr,*b=nullptr;unsigned ordinal=0,mode=0,scale=0,dtype=0;
  std::vector<uint8_t> data;std::string code,message;
};
static void destroySession(void *p)noexcept{delete static_cast<Session*>(p);}
static void destroyBuffer(void *p)noexcept{delete static_cast<Buffer*>(p);}
static nex_ffi_status factory(const nex_ffi_api_v1 *api,nex_ffi_call call,void *user,void **out)noexcept{
  auto &input=*static_cast<Creation*>(user);
  try{
    checked(api->poll(call));
    if(input.kind==Creation::Open){
      auto value=std::make_unique<Session>();auto session=value.get();*out=value.release();session->start(input.ordinal);Context context(*session,api,call);
      auto &d=session->driver;d.check(d.p_cuModuleLoadData(&session->module,ptx),"cuModuleLoadData");++ledger.modules;
      d.check(d.p_cuModuleGetFunction(&session->kernel,session->module,"u8_op"),"cuModuleGetFunction");
      d.check(d.p_cuStreamCreate(&session->stream,CU_STREAM_NON_BLOCKING),"cuStreamCreate");++ledger.streams;
      d.check(d.p_cuMemAlloc(&session->overflow,4),"cuMemAlloc scratch");ledger.allocate(4);
    }else{
      auto value=std::make_unique<Buffer>();auto buffer=value.get();buffer->session=input.session;buffer->dtype=input.dtype;
      buffer->bytes=input.kind==Creation::Upload?input.data.size():input.a->bytes;*out=value.release();
      auto &session=*input.session;Context context(session,api,call);auto &d=session.driver;auto started=Clock::now();
      d.check(d.p_cuMemAlloc(&buffer->pointer,size_t(buffer->bytes)),"cuMemAlloc");ledger.allocate(buffer->bytes);
      if(input.kind==Creation::Upload){
        d.check(d.p_cuMemcpyHtoD(buffer->pointer,input.data.data(),input.data.size()),"cuMemcpyHtoD");session.drain();
        trace(JSON{{"event","upload_completed"},{"session",session.identity},{"bytes",buffer->bytes},{"elapsed_ns",ns(started)},{"physical_completion_verified",true}});
      }else{
        unsigned overflow=0;d.check(d.p_cuMemcpyHtoD(session.overflow,&overflow,sizeof(overflow)),"cuMemcpyHtoD overflow");session.drain();
        Event begin(d),end(d);d.check(d.p_cuEventRecord(begin.value,session.stream),"cuEventRecord begin");
        auto a=input.a->pointer,b=input.b->pointer,output=buffer->pointer,flag=session.overflow;unsigned length=unsigned(buffer->bytes),mode=input.mode,scale=input.scale;auto delay=session.delayCycles;
        void *arguments[]={&a,&b,&output,&flag,&length,&mode,&scale,&delay};
        for(unsigned repeat=0;repeat<session.acceptanceLaunches;++repeat){
          auto launched=d.p_cuLaunchKernel(session.kernel,(length+255)/256,1,1,256,1,1,0,session.stream,arguments,nullptr);
          if(launched!=CUDA_SUCCESS){session.drain();d.check(launched,"cuLaunchKernel");}++ledger.launches;
        }
        // Once queued, every exit drains before events, buffers or parents go.
        auto recorded=d.p_cuEventRecord(end.value,session.stream);
        if(recorded!=CUDA_SUCCESS){session.drain();d.check(recorded,"cuEventRecord end");}
        InFlight flight{session,end.value};session.busy=1;
        auto status=d.p_cuEventQuery(end.value);
        trace(JSON{{"event","kernel_queued"},{"session",session.identity},{"elements",length},{"mode",mode},{"scale",scale},{"event_status",int(status)},{"completion_pending",status==CUDA_ERROR_NOT_READY},{"physical_enqueue_verified",true}});
        for(;;){status=d.p_cuEventQuery(end.value);if(status==CUDA_SUCCESS)break;if(status!=CUDA_ERROR_NOT_READY){session.drain();d.check(status,"cuEventQuery");}checked(api->poll(call));Sleep(1);}
        d.check(d.p_cuEventSynchronize(end.value),"cuEventSynchronize");session.drain();
        float milliseconds=0;d.check(d.p_cuEventElapsedTime(&milliseconds,begin.value,end.value),"cuEventElapsedTime");
        buffer->kernelNs=uint64_t(std::max(0.0,double(milliseconds))*1000000.0);
        d.check(d.p_cuMemcpyDtoH(&overflow,session.overflow,sizeof(overflow)),"cuMemcpyDtoH overflow");session.drain();flight.done=true;session.busy=0;
        trace(JSON{{"event","kernel_completed"},{"session",session.identity},{"elements",length},{"overflow",overflow},{"kernel_ns",buffer->kernelNs},{"elapsed_ns",ns(started)},{"physical_completion_verified",true},{"cpu_fallback",false}});
        if(overflow)throw Error("E_COMPUTE_OVERFLOW","exact CUDA U8 output is outside0..255");
      }
      trace(JSON{{"event","buffer_created"},{"session",session.identity},{"bytes",buffer->bytes},{"dtype",buffer->dtype}});
    }
    return api->poll(call);
  }catch(const HostStatus &error){trace(JSON{{"event","host_trap"},{"status",int(error.value)}});return error.value;}
  catch(const Error &error){try{input.code=error.code;input.message=error.what();}catch(...){return NEX_FFI_LIMIT;}return NEX_FFI_INTERNAL;}
  catch(...){try{input.code="E_DEVICE_HOST";input.message="trusted CUDA provider failure";}catch(...){}return NEX_FFI_INTERNAL;}
}
static int64_t integer(const nex_ffi_api_v1 *api,nex_ffi_call call,nex_ffi_ref ref){int64_t value=0;checked(api->get_i64(call,ref,&value));return value;}
static void *borrow(const nex_ffi_api_v1 *api,nex_ffi_call call,nex_ffi_ref ref,uint64_t argument){nex_ffi_type type=0;checked(api->argument_type(call,argument,&type));void *value=nullptr;checked(api->resource_borrow(call,ref,type,&value));return value;}
static nex_ffi_status failure(const nex_ffi_api_v1 *api,nex_ffi_call call,nex_ffi_ref *out,const std::string &code,const std::string &text){
  auto message=text.substr(0,2048);return api->make_failure(call,reinterpret_cast<const uint8_t*>(code.data()),code.size(),reinterpret_cast<const uint8_t*>(message.data()),message.size(),out);
}
static nex_ffi_status construct(const nex_ffi_api_v1 *api,nex_ffi_call call,Creation &input,uint64_t capacity,nex_ffi_ref parent,nex_ffi_ref *out){
  nex_ffi_type type=0;checked(api->result_type(call,&type));checked(api->type_child(call,type,0,0,&type));nex_ffi_ref value=0;
  auto status=input.kind==Creation::Open?api->resource_create(call,type,capacity,factory,destroySession,&input,&value):
    api->resource_create_with_parents(call,type,capacity,&parent,1,factory,destroyBuffer,&input,&value);
  if(status!=NEX_FFI_OK){if(status==NEX_FFI_HOST_TRAP)return status;if(!input.code.empty())return failure(api,call,out,input.code,input.message);
    if(status==NEX_FFI_LIMIT)return failure(api,call,out,"E_COMPUTE_LIMIT","declared CUDA resource capacity is exhausted");return status;}
  return api->make_success(call,value,out);
}
static nex_ffi_status callback(const nex_ffi_api_v1 *api,nex_ffi_call call,const nex_ffi_ref *args,uint64_t count,nex_ffi_ref *out,void *user)noexcept{
  try{
    checked(api->poll(call));auto operation=reinterpret_cast<uintptr_t>(user);
    if(operation==1){if(count!=1)return NEX_FFI_ARGUMENT;auto ordinal=integer(api,call,args[0]);if(ordinal<0||ordinal>63)return failure(api,call,out,"E_COMPUTE_DEVICE","CUDA ordinal must be0..63");Creation input{Creation::Open};input.ordinal=unsigned(ordinal);return construct(api,call,input,sizeof(Session)+4,0,out);}
    if(operation==2){
      if(count!=3)return NEX_FFI_ARGUMENT;auto session=static_cast<Session*>(borrow(api,call,args[0],0));auto dtype=integer(api,call,args[1]);uint64_t size=0;checked(api->byte_size(call,args[2],&size));
      if(dtype<1||dtype>3)return failure(api,call,out,"E_COMPUTE_DTYPE","unsupported CUDA buffer dtype");auto width=dtype==3?4u:1u;
      if(!size||size>1044480||size>262144*width||size%width)return failure(api,call,out,"E_COMPUTE_SIZE","CUDA upload exceeds checked dtype/byte limits");
      Creation input{Creation::Upload};input.session=session;input.dtype=unsigned(dtype);input.data.resize(size);uint64_t copied=0;checked(api->copy_bytes(call,args[2],0,input.data.data(),size,&copied));if(copied!=size)return NEX_FFI_INTERNAL;
      return construct(api,call,input,size+sizeof(Buffer),args[0],out);
    }
    if(operation==3){
      if(count!=5)return NEX_FFI_ARGUMENT;auto session=static_cast<Session*>(borrow(api,call,args[0],0));auto a=static_cast<Buffer*>(borrow(api,call,args[1],1)),b=static_cast<Buffer*>(borrow(api,call,args[2],2));auto mode=integer(api,call,args[3]),scale=integer(api,call,args[4]);
      if(mode==3)return failure(api,call,out,"E_COMPUTE_UNSUPPORTED","CUDA provider has no checked Matmul kernel");
      if((mode!=1&&mode!=2)||scale<0||scale>255||(mode==1&&scale!=1))return failure(api,call,out,"E_COMPUTE_RANGE","invalid exact CUDA operation");
      if(a->session!=session||b->session!=session)return failure(api,call,out,"E_COMPUTE_DEVICE","buffers belong to a different physical CUDA session");
      if(a->dtype!=1||b->dtype!=1||a->bytes!=b->bytes||!a->bytes||a->bytes>262144)return failure(api,call,out,"E_COMPUTE_SIZE","CUDA kernel input dtype/shape differs");
      Creation input{Creation::Dispatch};input.session=session;input.a=a;input.b=b;input.dtype=1;input.mode=unsigned(mode);input.scale=unsigned(scale);
      return construct(api,call,input,a->bytes+sizeof(Buffer),args[0],out);
    }
    if(operation==4){
      if(count!=1)return NEX_FFI_ARGUMENT;auto buffer=static_cast<Buffer*>(borrow(api,call,args[0],0));auto &session=*buffer->session;Context context(session,api,call);std::vector<uint8_t> data(buffer->bytes);auto started=Clock::now();
      session.driver.check(session.driver.p_cuMemcpyDtoH(data.data(),buffer->pointer,data.size()),"cuMemcpyDtoH");session.drain();checked(api->poll(call));
      trace(JSON{{"event","download_completed"},{"session",session.identity},{"bytes",data.size()},{"elapsed_ns",ns(started)},{"physical_completion_verified",true}});
      nex_ffi_ref value=0;checked(api->make_bytes(call,data.data(),data.size(),&value));return api->make_success(call,value,out);
    }
    if(operation==5){if(count!=1)return NEX_FFI_ARGUMENT;auto session=static_cast<Session*>(borrow(api,call,args[0],0));return api->make_string(call,reinterpret_cast<const uint8_t*>(session->name.data()),session->name.size(),out);}
    if(operation==6){if(count!=1)return NEX_FFI_ARGUMENT;auto buffer=static_cast<Buffer*>(borrow(api,call,args[0],0));if(buffer->kernelNs>uint64_t(INT64_MAX))return NEX_FFI_RANGE;return api->make_i64(call,int64_t(buffer->kernelNs),out);}
    if(operation==7){if(count!=1)return NEX_FFI_ARGUMENT;auto session=static_cast<Session*>(borrow(api,call,args[0],0));auto busy=session->busy.load();if(busy)trace(JSON{{"event","kernel_busy_observed"},{"session",session->identity}});return api->make_i64(call,busy,out);}
    return NEX_FFI_ARGUMENT;
  }catch(const HostStatus &error){return error.value;}catch(const Error &error){return failure(api,call,out,error.code,error.what());}catch(...){return NEX_FFI_INTERNAL;}
}
static const nex_ffi_export_v1 exports[]={
  {sizeof(nex_ffi_export_v1),0,"open",PIN_OPEN,callback,(void*)1},
  {sizeof(nex_ffi_export_v1),0,"upload",PIN_UPLOAD,callback,(void*)2},
  {sizeof(nex_ffi_export_v1),0,"dispatch",PIN_DISPATCH,callback,(void*)3},
  {sizeof(nex_ffi_export_v1),0,"download",PIN_DOWNLOAD,callback,(void*)4},
  {sizeof(nex_ffi_export_v1),0,"name",PIN_NAME,callback,(void*)5},
  {sizeof(nex_ffi_export_v1),0,"kernel_ns",PIN_KERNEL_NS,callback,(void*)6},
  {sizeof(nex_ffi_export_v1),0,"busy",PIN_BUSY,callback,(void*)7}
};
extern "C" const nex_ffi_module_v1 *nex_ffi_module_entry(uint32_t abi,uint32_t size){
  static const nex_ffi_module_v1 module{NEX_FFI_MODULE_ABI_V1,sizeof(nex_ffi_module_v1),sizeof(exports)/sizeof(exports[0]),sizeof(nex_ffi_export_v1),exports};
  return abi==NEX_FFI_ABI_V1&&size>=NEX_FFI_V1_RESOURCE_PARENTS_SIZE?&module:nullptr;
}
__attribute__((destructor)) static void unloaded(){trace(JSON{{"event","module_unloaded"},{"physical_completion_verified",ledger.bytes==0&&ledger.cleanupErrors==0}});}
