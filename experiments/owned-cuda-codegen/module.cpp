// Experimental generated scalar CUDA provider. Session/context ownership is
// adapted from owned-cuda; generated kernels and lane statuses have their own ABI.
#include "cuda_driver.h"
#include "generated_kernel.h"
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
#include <array>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <cstdlib>
#include <charconv>
#include <bit>
#include <limits>
using namespace cuda_api;

using JSON=nlohmann::json;
using Clock=std::chrono::steady_clock;
struct HostStatus {nex_ffi_status value;};
struct Error:std::runtime_error {
  std::string code;
  Error(std::string code,std::string message):std::runtime_error(std::move(message)),code(std::move(code)){}
};
struct GateConfiguration {uint64_t cycles;unsigned repeats;};
static uint64_t gateValue(const char *name,uint64_t maximum){
  std::string text;
#ifdef _WIN32
  std::wstring key;for(const char *p=name;*p;++p)key.push_back(wchar_t(*p));
  wchar_t data[32];auto length=GetEnvironmentVariableW(key.c_str(),data,32);
  if(!length)return 0;if(length>=32)throw Error("E_DEVICE_CONFIG","acceptance gate value exceeds its bound");
  for(unsigned i=0;i<length;++i){if(data[i]<'0'||data[i]>'9')throw Error("E_DEVICE_CONFIG","acceptance gate requires unsigned decimal values");text.push_back(char(data[i]));}
#else
  auto raw=std::getenv(name);if(!raw||!*raw)return 0;
  for(unsigned i=0;raw[i];++i){if(i>=31||raw[i]<'0'||raw[i]>'9')throw Error("E_DEVICE_CONFIG","acceptance gate requires bounded unsigned decimal values");text.push_back(raw[i]);}
#endif
  uint64_t value=0;auto parsed=std::from_chars(text.data(),text.data()+text.size(),value);
  if(parsed.ec!=std::errc{}||parsed.ptr!=text.data()+text.size()||value>maximum)
    throw Error("E_DEVICE_CONFIG","acceptance gate value exceeds its unsigned bound");
  return value;
}
static GateConfiguration gateConfiguration(){
  auto cycles=gateValue("NEX_OWNED_CUDA_MAP_GATE_CYCLES",200000000),repeats=gateValue("NEX_OWNED_CUDA_MAP_GATE_REPEATS",32);
  if((cycles==0)!=(repeats==0))throw Error("E_DEVICE_CONFIG","acceptance gate cycles and repeats must both be zero or both positive");
  if(cycles&&!GENERATED_ACCEPTANCE_GATE)throw Error("E_DEVICE_CONFIG","acceptance gate was not enabled during preparation");
  return {cycles,unsigned(repeats)};
}
static void checked(nex_ffi_status status){if(status!=NEX_FFI_OK)throw HostStatus{status};}
static uint64_t ns(Clock::time_point start){return uint64_t(std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now()-start).count());}
struct Ledger {
  std::atomic<uint64_t> contexts{0},contextFrees{0},modules{0},moduleFrees{0},streams{0},streamFrees{0};
  std::atomic<uint64_t> buffers{0},bufferFrees{0},bytes{0},peakBytes{0},events{0},eventFrees{0},launches{0},gateLaunches{0},cleanupErrors{0};
  JSON json()const{return JSON{{"contexts",contexts.load()},{"context_frees",contextFrees.load()},{"modules",modules.load()},{"module_frees",moduleFrees.load()},
    {"streams",streams.load()},{"stream_frees",streamFrees.load()},{"allocations",buffers.load()},{"frees",bufferFrees.load()},
    {"live_bytes",bytes.load()},{"peak_bytes",peakBytes.load()},{"events",events.load()},{"event_frees",eventFrees.load()},
    {"kernel_launches",launches.load()},{"acceptance_gate_launches",gateLaunches.load()},{"cleanup_errors",cleanupErrors.load()}};}
  void allocate(uint64_t size){++buffers;auto live=bytes.fetch_add(size)+size;auto peak=peakBytes.load();while(live>peak&&!peakBytes.compare_exchange_weak(peak,live)){}}
  void free(uint64_t size){++bufferFrees;bytes.fetch_sub(size);}
  bool balanced()const noexcept{return bytes==0&&cleanupErrors==0&&buffers==bufferFrees&&events==eventFrees&&
    contexts==contextFrees&&modules==moduleFrees&&streams==streamFrees;}
};
static Ledger ledger;
static std::mutex traceLock;
static std::atomic<uint64_t> identities{1};
static void trace(JSON row)noexcept{
  try{
    std::filesystem::path path;
#ifdef _WIN32
    wchar_t text[32768];auto size=GetEnvironmentVariableW(L"NEX_OWNED_CUDA_MAP_TRACE",text,32768);
    if(!size||size>=32768)return;path=text;
#else
    auto text=std::getenv("NEX_OWNED_CUDA_MAP_TRACE");if(!text||!*text)return;path=text;
#endif
    row["schema"]="nex.experimental-owned-CUDA-trace/2";
    row["steady_ns"]=uint64_t(std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now().time_since_epoch()).count());
    row["ledger"]=ledger.json();std::lock_guard lock(traceLock);std::ofstream output(path,std::ios::binary|std::ios::app);output<<row.dump()<<'\n';
  }catch(...){}
}
#define TRACE(...) do{try{trace(__VA_ARGS__);}catch(...){}}while(false)
[[noreturn]] static void unsettled(const char *operation,CUresult code)noexcept{
  ++ledger.cleanupErrors;TRACE(JSON{{"event","unsettled"},{"operation",operation},{"cuda_error",int(code)},{"physical_completion_verified",false}});
  std::fprintf(stderr,"E_DEVICE_UNSETTLED: CUDA %s returned %d; device resources and code remain retained\n",operation,int(code));
  // An unknown physical completion state is never reported as released
  // capacity. A parent deadline cannot make GPU/DMA completion true.
  for(;;)std::this_thread::sleep_for(std::chrono::seconds(1));
}
struct Driver {
  Library library;
  void *symbol(const char *name){if(!library.value)throw Error("E_COMPUTE_UNAVAILABLE","CUDA driver is unavailable");auto value=library.symbol(name);if(!value)throw Error("E_DEVICE_ABI",std::string("CUDA symbol unavailable: ")+name);return reinterpret_cast<void*>(value);}
#define CUDA_PROC(name,entry) decltype(&name) p_##name=reinterpret_cast<decltype(&name)>(symbol(entry))
  CUDA_PROC(cuInit,"cuInit");CUDA_PROC(cuDriverGetVersion,"cuDriverGetVersion");
  CUDA_PROC(cuDeviceGetCount,"cuDeviceGetCount");CUDA_PROC(cuDeviceGet,"cuDeviceGet");
  CUDA_PROC(cuDeviceGetName,"cuDeviceGetName");CUDA_PROC(cuDeviceGetUuid,"cuDeviceGetUuid");
  CUDA_PROC(cuDeviceGetPCIBusId,"cuDeviceGetPCIBusId");
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
struct Session {
  Driver driver;
  std::timed_mutex mutex;
  CUcontext context=nullptr;CUmodule module=nullptr;CUfunction kernel=nullptr;CUstream stream=nullptr;CUdeviceptr overflow=0;
  const uint64_t identity=identities.fetch_add(1);
  std::atomic<uint32_t> busy{0};
  uint64_t nextDispatch=1;
  CUfunction gate=nullptr;GateConfiguration gateConfig{0,0};
  static constexpr uint64_t scratchBytes=32768*4;
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
    driver.check(driver.p_cuCtxCreate(&context,CU_CTX_SCHED_BLOCKING_SYNC,device),"cuCtxCreate");++ledger.contexts;
    CUcontext popped=nullptr;driver.check(driver.p_cuCtxPopCurrent(&popped),"cuCtxPopCurrent");if(popped!=context)unsettled("context creation identity",CUDA_ERROR_INVALID_CONTEXT);
    TRACE(JSON{{"event","session_created"},{"session",identity},{"ordinal",ordinal},{"name",label},{"uuid",uuid},{"pci_bus_id",pci},{"driver_version",version},{"cpu_fallback",false}});
  }
  void drain()noexcept{driver.cleanup(driver.p_cuCtxSynchronize(),"cuCtxSynchronize");}
  ~Session()noexcept{
    if(!context)return;std::lock_guard lock(mutex);driver.cleanup(driver.p_cuCtxPushCurrent(context),"cuCtxPushCurrent cleanup");drain();
    if(overflow){driver.cleanup(driver.p_cuMemFree(overflow),"cuMemFree scratch");ledger.free(scratchBytes);overflow=0;
      TRACE(JSON{{"event","status_storage_released"},{"session",identity},{"bytes",scratchBytes},{"physical_completion_verified",true}});}
    if(stream){driver.cleanup(driver.p_cuStreamDestroy(stream),"cuStreamDestroy");++ledger.streamFrees;stream=nullptr;}
    if(module){driver.cleanup(driver.p_cuModuleUnload(module),"cuModuleUnload");++ledger.moduleFrees;module=nullptr;}
    CUcontext popped=nullptr;driver.cleanup(driver.p_cuCtxPopCurrent(&popped),"cuCtxPopCurrent cleanup");if(popped!=context)unsettled("context cleanup identity",CUDA_ERROR_INVALID_CONTEXT);
    driver.cleanup(driver.p_cuCtxDestroy(context),"cuCtxDestroy");++ledger.contextFrees;context=nullptr;
    TRACE(JSON{{"event","session_destroyed"},{"session",identity},{"physical_completion_verified",true}});
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
  Event(const Event&)=delete;Event& operator=(const Event&)=delete;
  ~Event(){if(value){driver.cleanup(driver.p_cuEventDestroy(value),"cuEventDestroy");++ledger.eventFrees;}}
};
struct Buffer {
  Session *session=nullptr;CUdeviceptr pointer=0;uint64_t bytes=0,kernelNs=0;uint32_t dtype=0;
  const uint64_t identity=identities.fetch_add(1);
  Buffer()=default;Buffer(const Buffer&)=delete;Buffer& operator=(const Buffer&)=delete;
  ~Buffer(){if(pointer){Context context(*session);session->drain();session->driver.cleanup(session->driver.p_cuMemFree(pointer),"cuMemFree buffer");ledger.free(bytes);
    TRACE(JSON{{"event","buffer_released"},{"session",session->identity},{"buffer",identity},{"bytes",bytes},{"physical_completion_verified",true}});}}
};
struct InFlight {
  Session &session;CUevent end;bool done=false;
  uint64_t dispatch,output;unsigned gates;
  InFlight(Session &s,CUevent event,uint64_t sequence,uint64_t buffer,unsigned controls):session(s),end(event),dispatch(sequence),output(buffer),gates(controls){}
  InFlight(const InFlight&)=delete;InFlight& operator=(const InFlight&)=delete;
  ~InFlight(){if(!done){session.drain();auto result=session.driver.p_cuEventQuery(end);if(result!=CUDA_SUCCESS)unsettled("event after physical drain",result);
    TRACE(JSON{{"event","physical_drain"},{"session",session.identity},{"dispatch",dispatch},{"output_buffer",output},{"gate_launches",gates},{"kernel_sha256",GENERATED_SHADER_SHA256},{"cpu_fallback",false},{"physical_completion_verified",true},{"event_status",int(result)},{"unwind",true}});}session.busy=0;}
};
static constexpr uint32_t maximumElements=262144;
#if GENERATED_VALUE_ABI
static const JSON &textPool(){static const JSON pool=JSON::parse(GENERATED_TEXT_POOL_JSON);return pool;}
#endif
static const char *laneError(uint32_t code){
#if GENERATED_LIST_VALUES
  if(code==9)return "E_BOUNDS";
  if(code==10)return "E_LIMIT";
#endif
#if GENERATED_VALUE_ABI
  if(code&0x80000000u){
    const auto a=(code>>10u)&1023u,b=code&1023u;
    if((code&0x7ff00000u)||a>=textPool().size()||b>=textPool().size())throw Error("E_DEVICE_ABI","invalid device Result diagnostic IDs");
    return "E_RESULT";
  }
#endif
  static const char *codes[]={"","E_OVERFLOW","E_DIV_ZERO","E_ASSERT","E_GPU_STEP_LIMIT","E_GPU_INTERNAL","E_GPU_INPUT","E_FLOAT"};
  if(code>(GENERATED_FLOATING_POINT?7u:6u))throw Error("E_DEVICE_ABI","generated kernel returned an unknown lane status");
  return codes[code];
}
static std::string laneMessage(uint32_t code,unsigned lane){
 (void)code;
#if GENERATED_LIST_VALUES
 if(code==9)return "index is outside collection bounds";
 if(code==10)return "device list exceeds declared capacity";
#endif
#if GENERATED_VALUE_ABI
 if(code&0x80000000u)return textPool().at((code>>10u)&1023u).get<std::string>()+": "+textPool().at(code&1023u).get<std::string>();
#endif
 return "generated GPU function failed at lane "+std::to_string(lane);
}
static constexpr std::array<unsigned,8> argumentWords=GENERATED_ARGUMENT_WORDS;
struct ReadCursor {
  Buffer *buffer=nullptr;uint64_t offset=0;
  const uint64_t identity=identities.fetch_add(1);
  std::mutex mutex;
  ~ReadCursor(){TRACE(JSON{{"event","read_cursor_released"},{"cursor",identity},{"session",buffer->session->identity},{"buffer",buffer->identity}});}
};
struct Creation {
  enum Kind{SessionOpen,BufferUpload,BufferGenerated,ReaderOpen}kind;
  Session *session=nullptr;Buffer *a=nullptr;
  std::vector<Buffer*> columns;
  unsigned ordinal=0,dtype=0,lanes=0,steps=0;
  std::vector<uint8_t> data;std::string code,message;
  explicit Creation(Kind value):kind(value){}
};
static void destroySession(void *p)noexcept{delete static_cast<Session*>(p);}
static void destroyBuffer(void *p)noexcept{delete static_cast<Buffer*>(p);}
static void destroyCursor(void *p)noexcept{delete static_cast<ReadCursor*>(p);}
static nex_ffi_status creationError(Creation &in,const char *code,const char *message)noexcept{
  try{in.code=code;in.message=message;return NEX_FFI_INTERNAL;}catch(...){return NEX_FFI_LIMIT;}
}
static nex_ffi_status factory(const nex_ffi_api_v1 *api,nex_ffi_call call,void *user,void **out)noexcept{
  auto &input=*static_cast<Creation*>(user);
  try{
    checked(api->poll(call));
    if(input.kind==Creation::SessionOpen){
      auto controls=gateConfiguration();
      auto value=std::make_unique<Session>();auto session=value.get();session->gateConfig=controls;*out=value.release();session->start(input.ordinal);Context context(*session,api,call);
      if(!*GENERATED_PTX)throw Error("E_DEVICE_ABI","source-only preparation has no compiled PTX");
      auto &d=session->driver;d.check(d.p_cuModuleLoadData(&session->module,GENERATED_PTX),"cuModuleLoadData");++ledger.modules;
      d.check(d.p_cuModuleGetFunction(&session->kernel,session->module,"nex_generated_cuda_map"),"cuModuleGetFunction");
      if(GENERATED_ACCEPTANCE_GATE)d.check(d.p_cuModuleGetFunction(&session->gate,session->module,"nex_acceptance_gate"),"cuModuleGetFunction acceptance gate");
      d.check(d.p_cuStreamCreate(&session->stream,CU_STREAM_NON_BLOCKING),"cuStreamCreate");++ledger.streams;
      d.check(d.p_cuMemAlloc(&session->overflow,Session::scratchBytes),"cuMemAlloc statuses");ledger.allocate(Session::scratchBytes);
      TRACE(JSON{{"event","status_storage_allocated"},{"session",session->identity},{"bytes",Session::scratchBytes}});
      TRACE(JSON{{"event","generated_session_ready"},{"session",session->identity},{"kernel_sha256",GENERATED_SHADER_SHA256},{"PTX_sha256",GENERATED_PTX_SHA256},{"gate_source_sha256",GENERATED_GATE_SOURCE_SHA256},{"acceptance_gate_compiled",bool(GENERATED_ACCEPTANCE_GATE)},{"arguments",GENERATED_ARGUMENTS},{"cpu_fallback",false}});
    }else if(input.kind==Creation::ReaderOpen){
      auto value=std::make_unique<ReadCursor>();value->buffer=input.a;*out=value.release();
      TRACE(JSON{{"event","read_cursor_created"},{"session",input.a->session->identity},{"buffer",input.a->identity},{"cursor",static_cast<ReadCursor*>(*out)->identity}});
    }else{
      auto value=std::make_unique<Buffer>();auto buffer=value.get();buffer->session=input.session;buffer->dtype=input.dtype;
      buffer->bytes=input.kind==Creation::BufferUpload?input.data.size():uint64_t(input.lanes)*8*GENERATED_OUTPUT_WORDS;*out=value.release();
      auto &session=*input.session;Context context(session,api,call);auto &d=session.driver;auto started=Clock::now();
      d.check(d.p_cuMemAlloc(&buffer->pointer,size_t(buffer->bytes)),"cuMemAlloc");ledger.allocate(buffer->bytes);
      TRACE(JSON{{"event","buffer_allocated"},{"session",session.identity},{"buffer",buffer->identity},{"bytes",buffer->bytes}});
      if(input.kind==Creation::BufferUpload){
        d.check(d.p_cuMemcpyHtoD(buffer->pointer,input.data.data(),input.data.size()),"cuMemcpyHtoD");session.drain();
        TRACE(JSON{{"event","upload_completed"},{"session",session.identity},{"bytes",buffer->bytes},{"elapsed_ns",ns(started)},{"physical_completion_verified",true}});
      }else{
        const auto dispatch=session.nextDispatch++;
        Event begin(d),end(d);d.check(d.p_cuEventRecord(begin.value,session.stream),"cuEventRecord begin");
        for(unsigned i=0;i<session.gateConfig.repeats;++i){
          auto cycles=static_cast<unsigned long long>(session.gateConfig.cycles);void *parameters[]={&cycles};
          auto queued=d.p_cuLaunchKernel(session.gate,1,1,1,1,1,1,0,session.stream,parameters,nullptr);
          if(queued!=CUDA_SUCCESS){session.drain();d.check(queued,"cuLaunchKernel acceptance gate");}++ledger.gateLaunches;
        }
        std::array<CUdeviceptr,8> columns{};std::array<void*,12> arguments{};unsigned argument=0;
        for(size_t i=0;i<input.columns.size();++i){columns[i]=input.columns[i]->pointer;arguments[argument++]=&columns[i];}
        auto output=buffer->pointer,statuses=session.overflow;unsigned lanes=input.lanes,steps=input.steps;
        arguments[argument++]=&output;arguments[argument++]=&statuses;arguments[argument++]=&lanes;arguments[argument++]=&steps;
        auto launched=d.p_cuLaunchKernel(session.kernel,(lanes+255)/256,1,1,256,1,1,0,session.stream,arguments.data(),nullptr);
        if(launched!=CUDA_SUCCESS){session.drain();d.check(launched,"cuLaunchKernel");}++ledger.launches;
        auto recorded=d.p_cuEventRecord(end.value,session.stream);
        if(recorded!=CUDA_SUCCESS){session.drain();d.check(recorded,"cuEventRecord end");}
        // This fence outlives all exception/cancellation exits after admission.
        // The borrowed event, output and columns stay live until it has drained.
        InFlight flight{session,end.value,dispatch,buffer->identity,session.gateConfig.repeats};
        auto status=d.p_cuEventQuery(end.value);
        TRACE(([&]{JSON ids=JSON::array();for(auto column:input.columns)ids.push_back(column->identity);return JSON{{"event","kernel_queued"},{"session",session.identity},{"dispatch",dispatch},{"output_buffer",buffer->identity},{"input_buffers",std::move(ids)},{"gate_launches",session.gateConfig.repeats},{"gate_cycles",session.gateConfig.cycles},{"elements",lanes},{"columns",input.columns.size()},{"steps",steps},{"event_status",int(status)},{"completion_pending",status==CUDA_ERROR_NOT_READY},{"physical_enqueue_verified",true}};})());
        // Observers see busy only after the enqueue acknowledgement is logged.
        session.busy=1;
        for(;;){status=d.p_cuEventQuery(end.value);if(status==CUDA_SUCCESS)break;if(status!=CUDA_ERROR_NOT_READY){session.drain();d.check(status,"cuEventQuery");}checked(api->poll(call));std::this_thread::sleep_for(std::chrono::milliseconds(1));}
        d.check(d.p_cuEventSynchronize(end.value),"cuEventSynchronize");session.drain();
        float milliseconds=0;d.check(d.p_cuEventElapsedTime(&milliseconds,begin.value,end.value),"cuEventElapsedTime");
        if(!std::isfinite(milliseconds)||milliseconds<0||double(milliseconds)>double(INT64_MAX)/1000000.0)throw Error("E_DEVICE_ABI","CUDA returned an invalid elapsed event time");
        buffer->kernelNs=uint64_t(double(milliseconds)*1000000.0);
        std::vector<unsigned> errors(lanes);d.check(d.p_cuMemcpyDtoH(errors.data(),session.overflow,errors.size()*sizeof(unsigned)),"cuMemcpyDtoH statuses");session.drain();flight.done=true;session.busy=0;
        unsigned code=0,lane=0;
        for(unsigned i=0;i<lanes;++i){(void)laneError(errors[i]);if(!code&&errors[i]){code=errors[i];lane=i;}}
        TRACE(JSON{{"event",code?"kernel_failure_settled":"kernel_completed"},{"session",session.identity},{"dispatch",dispatch},{"output_buffer",buffer->identity},{"elements",lanes},{"lane_status",code},{"failed_lane",lane},{"kernel_ns",buffer->kernelNs},{"elapsed_ns",ns(started)},{"kernel_sha256",GENERATED_SHADER_SHA256},{"physical_completion_verified",true},{"cpu_fallback",false}});
        if(code)throw Error(laneError(code),laneMessage(code,lane));
      }
      TRACE(JSON{{"event","buffer_created"},{"session",session.identity},{"buffer",buffer->identity},{"bytes",buffer->bytes},{"dtype",buffer->dtype}});
    }
    return api->poll(call);
  }catch(const HostStatus &error){TRACE(JSON{{"event","host_trap"},{"status",int(error.value)},{"session",input.session?input.session->identity:0}});return error.value;}
  catch(const Error &error){return creationError(input,error.code.c_str(),error.what());}
  catch(const std::exception &error){return creationError(input,"E_DEVICE_HOST",error.what());}
  catch(...){return creationError(input,"E_DEVICE_HOST","unexpected trusted CUDA provider failure");}
}
static int64_t integer(const nex_ffi_api_v1 *api,nex_ffi_call c,nex_ffi_ref r){int64_t v=0;checked(api->get_i64(c,r,&v));return v;}
static void *borrow(const nex_ffi_api_v1 *api,nex_ffi_call c,nex_ffi_ref r,uint64_t argument){nex_ffi_type t=0;checked(api->argument_type(c,argument,&t));void *p=nullptr;checked(api->resource_borrow(c,r,t,&p));return p;}
static nex_ffi_status failure(const nex_ffi_api_v1 *api,nex_ffi_call call,nex_ffi_ref *out,const std::string &code,const std::string &text){auto message=text.substr(0,2048);return api->make_failure(call,reinterpret_cast<const uint8_t*>(code.data()),code.size(),reinterpret_cast<const uint8_t*>(message.data()),message.size(),out);}
static nex_ffi_status construct(const nex_ffi_api_v1 *api,nex_ffi_call call,Creation &input,uint64_t capacity,nex_ffi_ref parent,nex_ffi_ref *out){
 nex_ffi_type type=0;checked(api->result_type(call,&type));checked(api->type_child(call,type,0,0,&type));nex_ffi_ref value=0;
 auto status=input.kind==Creation::SessionOpen?api->resource_create(call,type,capacity,factory,destroySession,&input,&value):api->resource_create_with_parents(call,type,capacity,&parent,1,factory,input.kind==Creation::ReaderOpen?destroyCursor:destroyBuffer,&input,&value);
 if(status!=NEX_FFI_OK){if(status==NEX_FFI_HOST_TRAP)return status;if(!input.code.empty())return failure(api,call,out,input.code,input.message);if(status==NEX_FFI_LIMIT)return failure(api,call,out,"E_COMPUTE_LIMIT","declared owned device capacity is exhausted");return status;}
 return api->make_success(call,value,out);
}
struct ValueReference {
 const nex_ffi_api_v1 *api;nex_ffi_call call;nex_ffi_ref value=0;
 ValueReference(const nex_ffi_api_v1 *a,nex_ffi_call c):api(a),call(c){}
 ~ValueReference(){if(value)(void)api->release(call,value);}
 ValueReference(const ValueReference&)=delete;ValueReference&operator=(const ValueReference&)=delete;
};
static constexpr uint64_t floatChunk=1024;
static uint64_t finiteWord(uint64_t bits){
 const auto magnitude=bits&UINT64_C(0x7fffffffffffffff);
 if((magnitude&UINT64_C(0x7ff0000000000000))==UINT64_C(0x7ff0000000000000))throw Error("E_FLOAT","f64 transport rejects infinities and NaNs");
 return magnitude?bits:0;
}
static nex_ffi_status floatCodec(const nex_ffi_api_v1 *api,nex_ffi_call call,const nex_ffi_ref *args,uint64_t count,nex_ffi_ref *out,bool encode){
 static_assert(sizeof(double)==8&&std::numeric_limits<double>::is_iec559&&std::numeric_limits<double>::digits==53);
 if(count!=3)return NEX_FFI_ARGUMENT;
 uint64_t length=0;
 if(encode)checked(api->child_count(call,args[0],&length));
 else {checked(api->byte_size(call,args[0],&length));if(length%8)throw Error("E_GPU_INPUT","f64 bytes must contain complete eight-byte words");length/=8;}
 auto offset=integer(api,call,args[1]),amount=integer(api,call,args[2]);
 if(length>floatChunk||offset<0||amount<0||uint64_t(amount)>floatChunk||uint64_t(offset)>length||uint64_t(amount)>length-uint64_t(offset))
  throw Error("E_GPU_INPUT","f64 codec range exceeds declared bounds");
 const auto size=uint64_t(amount);std::vector<uint8_t> bytes(size*8);
 if(encode){
  for(uint64_t i=0;i<size;++i){
   if(i%128==0)checked(api->poll(call));ValueReference child(api,call);checked(api->child(call,args[0],uint64_t(offset)+i,&child.value));double value=0;
   checked(api->get_f64(call,child.value,&value));auto bits=finiteWord(std::bit_cast<uint64_t>(value));
   for(unsigned j=0;j<8;++j)bytes[i*8+j]=uint8_t(bits>>(j*8));
  }
  ValueReference data(api,call);checked(api->make_bytes(call,bytes.data(),bytes.size(),&data.value));return api->make_success(call,data.value,out);
 }
 uint64_t copied=0;checked(api->copy_bytes(call,args[0],uint64_t(offset)*8,bytes.data(),bytes.size(),&copied));if(copied!=bytes.size())return NEX_FFI_INTERNAL;
 std::vector<nex_ffi_ref> values;values.reserve(size);
 struct References {const nex_ffi_api_v1 *api;nex_ffi_call call;std::vector<nex_ffi_ref> &values;~References(){for(auto r:values)(void)api->release(call,r);}} cleanup{api,call,values};
 for(uint64_t i=0;i<size;++i){
  if(i%128==0)checked(api->poll(call));uint64_t bits=0;for(unsigned j=0;j<8;++j)bits|=uint64_t(bytes[i*8+j])<<(j*8);
  bits=finiteWord(bits);nex_ffi_ref value=0;checked(api->make_f64(call,std::bit_cast<double>(bits),&value));values.push_back(value);
 }
 ValueReference list(api,call);checked(api->make_list(call,values.data(),values.size(),&list.value));return api->make_success(call,list.value,out);
}
static nex_ffi_status callback(const nex_ffi_api_v1 *api,nex_ffi_call call,const nex_ffi_ref *args,uint64_t count,nex_ffi_ref *out,void *user)noexcept{
 try{
  if(api->struct_size<NEX_FFI_V1_TRAP_SIZE||!api->raise_trap)return NEX_FFI_ARGUMENT;checked(api->poll(call));auto op=uint64_t(user);
  if(op==10||op==11)return floatCodec(api,call,args,count,out,op==10);
  if(op==9){
   if(count!=2)return NEX_FFI_ARGUMENT;uint64_t cn=0,mn=0,written=0;
   checked(api->byte_size(call,args[0],&cn));checked(api->byte_size(call,args[1],&mn));
   if(cn<3||cn>128||mn>2048)return NEX_FFI_LIMIT;
   uint8_t code[128],message[2048];checked(api->copy_bytes(call,args[0],0,code,cn,&written));if(written!=cn)return NEX_FFI_INTERNAL;
   checked(api->copy_bytes(call,args[1],0,message,mn,&written));if(written!=mn)return NEX_FFI_INTERNAL;
   return api->raise_trap(call,code,cn,message,mn);
  }
  if(op==1){if(count!=1)return NEX_FFI_ARGUMENT;auto ordinal=integer(api,call,args[0]);if(ordinal<0||ordinal>63)return failure(api,call,out,"E_COMPUTE_DEVICE","GPU index must be0..63");Creation in{Creation::SessionOpen};in.ordinal=uint32_t(ordinal);return construct(api,call,in,Session::scratchBytes+sizeof(Session),0,out);}
  if(op==2){if(count!=3)return NEX_FFI_ARGUMENT;auto *session=static_cast<Session*>(borrow(api,call,args[0],0));auto dtype=integer(api,call,args[1]);if(dtype!=1)return failure(api,call,out,"E_GPU_INPUT","generated input uses immutable byte columns");uint64_t size=0;checked(api->byte_size(call,args[2],&size));auto width=dtype==3?4u:1u;if(!size||size>uint64_t(maximumElements)*width||size>1044480||size%width)return failure(api,call,out,"E_COMPUTE_SIZE","buffer byte count exceeds exact dtype bounds");Creation in{Creation::BufferUpload};in.session=session;in.dtype=uint32_t(dtype);in.data.resize(size);uint64_t copied=0;checked(api->copy_bytes(call,args[2],0,in.data.data(),size,&copied));if(copied!=size)return NEX_FFI_INTERNAL;return construct(api,call,in,size+sizeof(Buffer),args[0],out);}
  if(op==3){
   if(count!=4)return NEX_FFI_ARGUMENT;
   auto *session=static_cast<Session*>(borrow(api,call,args[0],0));
   auto lanes=integer(api,call,args[2]),steps=integer(api,call,args[3]);
   if(lanes<1||lanes>32768||steps<1||steps>65536||uint64_t(lanes)*uint64_t(steps)>16777216)
    return failure(api,call,out,"E_GPU_INPUT","generated kernel geometry exceeds declared bounds");
   if(uint64_t(lanes)*8*GENERATED_OUTPUT_WORDS>262144)return failure(api,call,out,"E_GPU_INPUT","fixed output exceeds batch capacity");
   uint64_t length=0;checked(api->child_count(call,args[1],&length));
   if(length!=GENERATED_ARGUMENTS||length>8)return failure(api,call,out,"E_GPU_INPUT","column count differs from selected scalar function");
   nex_ffi_type listType=0,elementType=0;checked(api->argument_type(call,1,&listType));checked(api->type_child(call,listType,0,0,&elementType));
   Creation in{Creation::BufferGenerated};in.session=session;in.dtype=1;in.lanes=uint32_t(lanes);in.steps=uint32_t(steps);
   for(uint64_t i=0;i<length;++i){nex_ffi_ref child=0;checked(api->child(call,args[1],i,&child));void *pointer=nullptr;checked(api->resource_borrow(call,child,elementType,&pointer));
    auto *column=static_cast<Buffer*>(pointer);
    if(column->session!=session)return failure(api,call,out,"E_GPU_INPUT","column belongs to another physical session");
    if(column->dtype!=1||column->bytes!=uint64_t(lanes)*8*argumentWords[i])return failure(api,call,out,"E_GPU_INPUT","column bytes do not match selected scalar function");
    in.columns.push_back(column);
   }
   return construct(api,call,in,uint64_t(lanes)*8*GENERATED_OUTPUT_WORDS+sizeof(Buffer),args[0],out);
  }
  if(op==4){
   if(count!=1)return NEX_FFI_ARGUMENT;auto *buffer=static_cast<Buffer*>(borrow(api,call,args[0],0));
   if(!buffer->session->context)return failure(api,call,out,"E_DEVICE_LOST","persistent GPU session is no longer available");
   Creation in{Creation::ReaderOpen};in.a=buffer;return construct(api,call,in,sizeof(ReadCursor),args[0],out);
  }
  if(op==8){
   if(count!=1)return NEX_FFI_ARGUMENT;auto *cursor=static_cast<ReadCursor*>(borrow(api,call,args[0],0));
   std::unique_lock lock(cursor->mutex,std::defer_lock);while(!lock.try_lock()){checked(api->poll(call));std::this_thread::sleep_for(std::chrono::milliseconds(1));}
   checked(api->poll(call));auto *buffer=cursor->buffer;
   if(cursor->offset>buffer->bytes)return NEX_FFI_INTERNAL;
   const auto expected=std::min<uint64_t>(262144,buffer->bytes-cursor->offset);
   auto &session=*buffer->session;Context context(session,api,call);std::vector<uint8_t> bytes(expected);
   if(expected)session.driver.check(session.driver.p_cuMemcpyDtoH(bytes.data(),buffer->pointer+cursor->offset,size_t(expected)),"cuMemcpyDtoH cursor");
   session.drain();checked(api->poll(call));
   nex_ffi_ref value=0;checked(api->make_bytes(call,bytes.data(),bytes.size(),&value));auto status=api->make_success(call,value,out);
   if(status==NEX_FFI_OK){cursor->offset+=bytes.size();TRACE(JSON{{"event","read_cursor_chunk"},{"session",buffer->session->identity},
     {"cursor",cursor->identity},{"bytes",bytes.size()},{"offset",cursor->offset}});}
   return status;
  }
  if(op==5){if(count!=1)return NEX_FFI_ARGUMENT;auto *session=static_cast<Session*>(borrow(api,call,args[0],0));return api->make_string(call,reinterpret_cast<const uint8_t*>(session->name.data()),session->name.size(),out);}
  if(op==6){if(count!=1)return NEX_FFI_ARGUMENT;auto *buffer=static_cast<Buffer*>(borrow(api,call,args[0],0));if(buffer->kernelNs>uint64_t(INT64_MAX))return NEX_FFI_RANGE;return api->make_i64(call,int64_t(buffer->kernelNs),out);}
  if(op==7){if(count!=1)return NEX_FFI_ARGUMENT;auto *session=static_cast<Session*>(borrow(api,call,args[0],0));auto busy=session->busy.load();if(busy)TRACE(JSON{{"event","kernel_busy_observed"},{"session",session->identity}});return api->make_i64(call,busy,out);}
  return NEX_FFI_ARGUMENT;
 }catch(const HostStatus &e){return e.value;}catch(const Error &e){try{return failure(api,call,out,e.code,e.what());}catch(...){return NEX_FFI_LIMIT;}}catch(const std::bad_alloc&){return NEX_FFI_LIMIT;}catch(...){return NEX_FFI_INTERNAL;}
}
static const nex_ffi_export_v1 exports[]={
 {sizeof(nex_ffi_export_v1),0,"open",PIN_OPEN,callback,(void*)1},
 {sizeof(nex_ffi_export_v1),0,"upload",PIN_UPLOAD,callback,(void*)2},
 {sizeof(nex_ffi_export_v1),0,"map",PIN_MAP,callback,(void*)3},
 {sizeof(nex_ffi_export_v1),0,"download",PIN_DOWNLOAD,callback,(void*)4},
 {sizeof(nex_ffi_export_v1),0,"name",PIN_NAME,callback,(void*)5},
 {sizeof(nex_ffi_export_v1),0,"kernel_ns",PIN_KERNEL_NS,callback,(void*)6},
 {sizeof(nex_ffi_export_v1),0,"busy",PIN_BUSY,callback,(void*)7},
 {sizeof(nex_ffi_export_v1),0,"read_next",PIN_READ_NEXT,callback,(void*)8},
 {sizeof(nex_ffi_export_v1),0,"fatal",PIN_FATAL,callback,(void*)9},
 {sizeof(nex_ffi_export_v1),0,"encode_f64",PIN_ENCODE_F64,callback,(void*)10},
 {sizeof(nex_ffi_export_v1),0,"decode_f64",PIN_DECODE_F64,callback,(void*)11}
};
extern "C" const nex_ffi_module_v1 *nex_ffi_module_entry(uint32_t abi,uint32_t size){static const nex_ffi_module_v1 m{NEX_FFI_MODULE_ABI_V1,sizeof(nex_ffi_module_v1),sizeof(exports)/sizeof(exports[0]),sizeof(nex_ffi_export_v1),exports};return abi==1&&size>=NEX_FFI_V1_TRAP_SIZE?&m:nullptr;}

__attribute__((destructor)) static void unloaded(){TRACE(JSON{{"event","module_unloaded"},{"physical_completion_verified",ledger.balanced()}});}
