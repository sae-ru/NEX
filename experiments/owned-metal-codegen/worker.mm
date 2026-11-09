#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include "protocol.h"
#include "generated_kernel.h"
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <fcntl.h>
#include <limits>
#include <map>
#include <memory>
#include <thread>
#include <sys/resource.h>
using namespace owned_metal_map;

class GPU {
 struct Buffer { id<MTLBuffer> memory; uint32_t dtype; uint64_t bytes; };
 id<MTLDevice> device=nil;
 id<MTLCommandQueue> queue=nil;
 id<MTLComputePipelineState> pipeline=nil;
 id<MTLBuffer> flags=nil;
 id<MTLCommandBuffer> active=nil;
 std::map<uint64_t,Buffer> buffers;
 uint64_t next=1;
 std::string name;
 bool uncertain=false,closed=false;
 static void require(bool condition,const char *message){if(!condition)throw Error("E_METAL",message);}
 static std::string text(NSString *value){
  const char *p=value?value.UTF8String:nullptr;
  if(!p)throw Error("E_DEVICE_ABI","Metal did not provide UTF-8 text");
  return p;
 }
 static void metalError(NSError *error,const char *message){
  throw Error("E_METAL",error?text(error.localizedDescription):message);
 }
 Buffer &buffer(uint64_t id){auto found=buffers.find(id);if(found==buffers.end())throw Error("E_DEVICE_BUFFER","unknown or closed Metal buffer");return found->second;}
 void capacity()const{if(buffers.size()>=4096||next>uint64_t(INT64_MAX))throw Error("E_COMPUTE_LIMIT","worker buffer ownership limit exceeded");}
 uint64_t publish(id<MTLBuffer> memory,uint32_t dtype,uint64_t bytes){capacity();auto id=next++;buffers.emplace(id,Buffer{memory,dtype,bytes});return id;}
public:
 bool drain()noexcept{
  if(active){[active waitUntilCompleted];auto state=active.status;
   if(state!=MTLCommandBufferStatusCompleted&&state!=MTLCommandBufferStatusError)uncertain=true;
  }
  return !uncertain;
 }
 bool settled()const noexcept{return !uncertain;}
 ~GPU(){closeNoThrow();}
 void closeNoThrow()noexcept{
  if(closed||!drain())return;
  auto released=buffers.size();buffers.clear();active=nil;flags=nil;pipeline=nil;queue=nil;device=nil;
  closed=true;std::fprintf(stderr,"NEXGPU_DRAIN %llu 1\n",static_cast<unsigned long long>(released));
 }
 void open(uint32_t selected){
  NSArray<id<MTLDevice>> *devices=MTLCopyAllDevices();
  if(!devices||devices.count>64)throw Error("E_COMPUTE_LIMIT","Metal GPU inventory exceeds configured bounds");
  if(selected>=devices.count)throw Error("E_COMPUTE_UNAVAILABLE","selected physical Metal GPU is unavailable");
  device=devices[selected];
  require(device&&device.registryID!=0,"Metal returned no physical GPU identity");
  name=text(device.name);if(name.empty()||name.size()>4096)throw Error("E_DEVICE_ABI","Metal GPU name is not bounded");
  queue=[device newCommandQueue];require(queue!=nil,"Metal queue creation failed");
  NSString *source=[[NSString alloc] initWithUTF8String:GENERATED_MSL];
  MTLCompileOptions *options=[[MTLCompileOptions alloc]init];options.mathMode=MTLMathModeSafe;options.mathFloatingPointFunctions=MTLMathFloatingPointFunctionsPrecise;options.languageVersion=MTLLanguageVersion3_1;
  NSError *error=nil;id<MTLLibrary> library=[device newLibraryWithSource:source options:options error:&error];
  if(!library)metalError(error,"Metal source compilation failed");
  id<MTLFunction> function=[library newFunctionWithName:@"nex_generated_map"];
  require(function!=nil,"Metal kernel lookup failed");
  pipeline=[device newComputePipelineStateWithFunction:function error:&error];
  if(!pipeline)metalError(error,"Metal pipeline creation failed");
  flags=[device newBufferWithLength:maximumElements options:MTLResourceStorageModeShared];
  require(flags&&flags.storageMode==MTLStorageModeShared,"Metal session scratch allocation failed");
  std::fprintf(stderr,"NEXGPU_OPEN %u %llu\n",selected,static_cast<unsigned long long>(device.registryID));
 }
 Data info()const{Data output;output.text(name);output.u64(device.registryID);output.u32(maximumElements);output.u32(GENERATED_ARGUMENTS);output.text(GENERATED_SHADER_SHA256);return output;}
 uint64_t upload(uint32_t dtype,Bytes &bytes){
  if(dtype!=1||bytes.empty()||bytes.size()>maximumElements)
   throw Error("E_GPU_INPUT","invalid immutable column bytes");
  capacity();id<MTLBuffer> memory=[device newBufferWithBytes:bytes.data() length:bytes.size() options:MTLResourceStorageModeShared];
  require(memory&&memory.storageMode==MTLStorageModeShared,"Metal upload allocation failed");
  return publish(memory,dtype,bytes.size());
 }
 Data runKernel(const std::vector<Buffer> &columns,uint32_t count,uint32_t steps,
                const std::function<void(uint32_t,bool)> &admitted){
  const uint64_t elements=count,outputBytes=uint64_t(count)*8;
  id<MTLComputePipelineState> chosen=pipeline;
  capacity();id<MTLBuffer> output=[device newBufferWithLength:outputBytes options:MTLResourceStorageModeShared];
  require(output&&output.storageMode==MTLStorageModeShared,"Metal output allocation failed");
  id<MTLSharedEvent> gate=nil;std::thread gateThread;bool committed=false;
  auto releaseGate=[&]()noexcept{
   if(gateThread.joinable())gateThread.join();
   if(gate&&gate.signaledValue<1)gate.signaledValue=1;
  };
  try{
   unsigned delay=0;if(const char *value=std::getenv("NEX_OWNED_METAL_MAP_TEST_GATE_MS")){
    auto size=std::strlen(value);if(!size||size>4||std::strspn(value,"0123456789")!=size)throw Error("E_DEVICE_PROTOCOL","invalid controlled gate delay");
    auto parsed=std::strtoul(value,nullptr,10);if(parsed>5000)throw Error("E_DEVICE_PROTOCOL","controlled gate delay exceeds limit");delay=unsigned(parsed);
   }
   if(delay){gate=[device newSharedEvent];require(gate&&gate.signaledValue==0,"Metal controlled shared event creation failed");}
   MTLCommandBufferDescriptor *descriptor=[[MTLCommandBufferDescriptor alloc] init];descriptor.retainedReferences=YES;
   active=[queue commandBufferWithDescriptor:descriptor];require(active&&active.retainedReferences,"Metal command must retain its resources");
   if(gate)[active encodeWaitForEvent:gate value:1];
   id<MTLComputeCommandEncoder> encoder=[active computeCommandEncoder];require(encoder!=nil,"Metal encoder creation failed");
   [encoder setComputePipelineState:chosen];
   for(size_t i=0;i<columns.size();++i)[encoder setBuffer:columns[i].memory offset:0 atIndex:i];
   [encoder setBuffer:output offset:0 atIndex:8];[encoder setBuffer:flags offset:0 atIndex:9];
   uint32_t parameters[]={count,steps};[encoder setBytes:parameters length:sizeof(parameters) atIndex:10];
   auto threads=std::min(chosen.threadExecutionWidth,chosen.maxTotalThreadsPerThreadgroup);require(threads>0,"Metal returned no legal threadgroup size");
   [encoder dispatchThreadgroups:MTLSizeMake((elements+threads-1)/threads,1,1) threadsPerThreadgroup:MTLSizeMake(threads,1,1)];
   [encoder endEncoding];encoder=nil;
   auto completed=std::make_shared<std::atomic<unsigned>>(0);
   [active addCompletedHandler:^(id<MTLCommandBuffer>){completed->fetch_add(1);}];
   [active commit];committed=true;
   if(gate)gateThread=std::thread([pending=gate,delay]{std::this_thread::sleep_for(std::chrono::milliseconds(delay));pending.signaledValue=1;});
   auto state=active.status;if(state==MTLCommandBufferStatusError)metalError(active.error,"Metal command failed");
   require(state>=MTLCommandBufferStatusCommitted&&state<=MTLCommandBufferStatusCompleted,"Metal command was not committed");
   if(admitted)admitted(uint32_t(state),gate!=nil);
   if(!drain())throw Error("E_DEVICE_UNSETTLED","physical Metal completion could not be established");
   releaseGate();committed=false;
   if(active.status!=MTLCommandBufferStatusCompleted||active.error)metalError(active.error,"Metal command did not complete successfully");
   require(completed->load()==1,"Metal completion handler did not finish exactly once");
   const double start=active.GPUStartTime,end=active.GPUEndTime,ns=(end-start)*1000000000.0;
   if(!std::isfinite(start)||!std::isfinite(end)||start<=0||end<start||ns<0||ns>=double(INT64_MAX))throw Error("E_DEVICE_ABI","invalid completed Metal profiling interval");
   const auto *errors=static_cast<const uint32_t*>(flags.contents);uint32_t code=0,lane=0;
   for(uint32_t i=0;i<count;++i){if(errors[i]>6)throw Error("E_DEVICE_ABI","generated kernel returned an unknown lane status");if(!code&&errors[i]){code=errors[i];lane=i;}}
   std::fprintf(stderr,"NEXGPU_MAP %u %u %llu %u %u 4 %u\n",count,steps,static_cast<unsigned long long>(ns),code,lane,completed->load());
   active=nil;if(code){const char *codes[]={"","E_OVERFLOW","E_DIV_ZERO","E_ASSERT","E_GPU_STEP_LIMIT","E_GPU_INTERNAL","E_GPU_INPUT"};throw Error(codes[code],"generated GPU function failed at lane "+std::to_string(lane));}
   auto id=publish(output,1,outputBytes);Data result;result.u64(id);result.u64(outputBytes);result.u64(uint64_t(ns));
   result.u32(uint32_t(MTLCommandBufferStatusCompleted));result.u32(completed->load());return result;
  }catch(...){
   releaseGate();if(committed){if(drain())active=nil;}else active=nil;throw;
  }
 }
 Data generated(const std::vector<uint64_t> &ids,uint32_t count,uint32_t steps,const std::function<void(uint32_t,bool)> &admitted){
  if(ids.size()!=GENERATED_ARGUMENTS||!count||count>32768||!steps||steps>65536||uint64_t(count)*steps>16777216)
   throw Error("E_GPU_INPUT","generated kernel geometry exceeds declared bounds");
  std::vector<Buffer> columns;for(auto id:ids){auto value=buffer(id);if(value.dtype!=1||value.bytes!=uint64_t(count)*8)throw Error("E_GPU_INPUT","column bytes do not match selected scalar function");columns.push_back(value);}
  return runKernel(columns,count,steps,admitted);
 }
 Bytes download(uint64_t id,uint64_t offset,uint32_t count){
  auto value=buffer(id);if(offset>value.bytes||count>262144||count>value.bytes-offset)throw Error("E_DEVICE_BUFFER","read chunk exceeds immutable buffer");
  Bytes result(count);if(count)std::memcpy(result.data(),static_cast<const uint8_t*>(value.memory.contents)+offset,count);return result;
 }
 void free(uint64_t id){buffer(id);if(!drain())throw Error("E_DEVICE_UNSETTLED","Metal buffer remains physically unsettled");buffers.erase(id);}
 size_t live()const{return buffers.size();}
};

int main(){
 if(std::getenv("NEX_OWNED_METAL_MAP_TEST_NOISE"))std::fputs("controlled worker stdout diagnostic\n",stdout);
 std::signal(SIGPIPE,SIG_IGN);rlimit noCore{0,0};setrlimit(RLIMIT_CORE,&noCore);
 std::unique_ptr<GPU> gpu;uint64_t expected=1;Frame request{};bool faulted=false;
 try{
  if(const char *path=std::getenv("NEX_OWNED_METAL_MAP_TEST_CACHE_FILE")){
   if(path[0]!='/'||std::strlen(path)>4096)throw Error("E_DEVICE_TEST","controlled cache path must be absolute and bounded");
   int fd=::open(path,O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0600);if(fd<0)throw Error("E_DEVICE_TEST","controlled cache file creation failed");
   struct Close{int fd;~Close(){::close(fd);}} close{fd};char block[4096]={};std::fprintf(stderr,"NEXGPU_TEST_CACHE_BEGIN 9437184\n");
   for(size_t written=0;written<9437184;){auto n=::write(fd,block,std::min(sizeof(block),size_t(9437184-written)));if(n<0&&errno==EINTR)continue;if(n<=0)throw Error("E_DEVICE_TEST","controlled cache write failed");written+=size_t(n);}
   std::fprintf(stderr,"NEXGPU_TEST_CACHE_END 9437184\n");
  }
  if(const char *text=std::getenv("NEX_OWNED_METAL_MAP_TEST_NOISE_BYTES")){
   auto length=std::strlen(text);if(!length||length>8||std::strspn(text,"0123456789")!=length)throw Error("E_DEVICE_TEST","invalid controlled log size");
   auto count=std::strtoul(text,nullptr,10);if(count>16777216)throw Error("E_DEVICE_TEST","controlled log size exceeds16MiB");
   char block[4096];std::memset(block,'#',sizeof(block));block[sizeof(block)-1]='\n';std::fprintf(stderr,"NEXGPU_TEST_NOISE_BEGIN %lu\n",count);
   for(size_t n=0;n<count;){auto size=std::min(sizeof(block),size_t(count-n));if(std::fwrite(block,1,size,stdout)!=size)throw Error("E_DEVICE_TEST","controlled stdout write failed");n+=size;}
   if(std::fflush(stdout))throw Error("E_DEVICE_TEST","controlled stdout flush failed");std::fprintf(stderr,"NEXGPU_TEST_NOISE_END %lu\n",count);
  }
  const char *fault=std::getenv("NEX_OWNED_METAL_MAP_TEST_BAD_REPLY");
  if(fault&&std::strcmp(fault,"upload_truncated")&&std::strcmp(fault,"upload_wrong_size")&&std::strcmp(fault,"upload_reused_id")&&std::strcmp(fault,"map_reused_id")&&std::strcmp(fault,"map_truncated")&&std::strcmp(fault,"map_trailing")&&std::strcmp(fault,"download_truncated")&&std::strcmp(fault,"download_wrong_size")&&std::strcmp(fault,"free_trailing")&&std::strcmp(fault,"close_truncated")&&std::strcmp(fault,"open_trailing")&&std::strcmp(fault,"map_truncated")&&std::strcmp(fault,"map_reused_id")&&std::strcmp(fault,"map_wrong_size")&&std::strcmp(fault,"map_bad_status")&&std::strcmp(fault,"map_bad_handlers"))throw Error("E_DEVICE_PROTOCOL","unknown controlled reply fault");
  auto wants=[&](const char *name){return !faulted&&fault&&std::strcmp(fault,name)==0;};
  while(receive(3,request)){ @autoreleasepool {
   if(request.sequence!=expected++||request.status!=0)throw Error("E_DEVICE_PROTOCOL","worker sequence or request status differs");
   try{
    Data input(std::move(request.payload)),output;bool closing=false;
    switch(request.operation){
     case Open:{if(gpu)throw Error("E_DEVICE_PROTOCOL","worker session already opened");auto ordinal=input.get32();input.done();gpu=std::make_unique<GPU>();gpu->open(ordinal);output=gpu->info();break;}
     case Upload:{if(!gpu)throw Error("E_DEVICE_PROTOCOL","no GPU session");auto dtype=input.get32();auto bytes=input.getBlob();input.done();output.u64(gpu->upload(dtype,bytes));output.u64(bytes.size());break;}
     case Generated:{if(!gpu)throw Error("E_DEVICE_PROTOCOL","no GPU session");auto length=input.get32();if(length>8)throw Error("E_DEVICE_PROTOCOL","column count exceeds ABI bound");std::vector<uint64_t> columns;for(uint32_t i=0;i<length;++i)columns.push_back(input.get64());auto count=input.get32(),steps=input.get32();input.done();output=gpu->generated(columns,count,steps,[&](uint32_t status,bool gated){Data progress;progress.u32(1);progress.u32(status);progress.u32(gated?1:0);send(3,Frame{request.sequence,request.operation,Progress,std::move(progress.bytes)});});break;}
     case Download:{if(!gpu)throw Error("E_DEVICE_PROTOCOL","no GPU session");auto id=input.get64(),offset=input.get64();auto count=input.get32();input.done();output.blob(gpu->download(id,offset,count));break;}
     case Free:{if(!gpu)throw Error("E_DEVICE_PROTOCOL","no GPU session");auto id=input.get64();input.done();gpu->free(id);output.u32(uint32_t(gpu->live()));break;}
     case Close:{input.done();if(gpu&&gpu->live())throw Error("E_DEVICE_PROTOCOL","session closed before its actual buffers");if(gpu){gpu->closeNoThrow();if(!gpu->settled())throw Error("E_DEVICE_UNSETTLED","session release is not confirmed");gpu.reset();}output.u32(0);closing=true;break;}
     default:throw Error("E_DEVICE_PROTOCOL","unknown worker operation");
    }
    bool corrupt=false;
    if(request.operation==Generated&&wants("map_truncated")){output.bytes.resize(7);corrupt=true;}
    if(request.operation==Generated&&wants("map_reused_id")){for(size_t i=0;i<8;++i)output.bytes.at(i)=i==0?1:0;corrupt=true;}
    if(request.operation==Generated&&wants("map_wrong_size")){output.bytes.at(8)^=1;corrupt=true;}
    if(request.operation==Generated&&wants("map_bad_status")){output.bytes.at(24)=0;corrupt=true;}
    if(request.operation==Generated&&wants("map_bad_handlers")){output.bytes.at(28)=0;corrupt=true;}
    if(request.operation==Upload&&wants("upload_truncated")){output.bytes.resize(7);corrupt=true;}
    if(request.operation==Upload&&wants("upload_wrong_size")){output.bytes.at(8)^=1;corrupt=true;}
    if(request.operation==Upload&&wants("upload_reused_id")&&gpu->live()>1){for(size_t i=0;i<8;++i)output.bytes.at(i)=i==0?1:0;corrupt=true;}
    if((request.operation==Generated&&wants("map_trailing"))||(request.operation==Free&&wants("free_trailing"))||(request.operation==Open&&wants("open_trailing"))){output.bytes.push_back(0);corrupt=true;}
    if((request.operation==Download&&wants("download_truncated"))||(request.operation==Close&&wants("close_truncated"))){output.bytes.resize(3);corrupt=true;}
    if(request.operation==Download&&wants("download_wrong_size")){Data original(std::move(output.bytes));auto bytes=original.getBlob();original.done();if(!bytes.empty())bytes.pop_back();Data wrong;wrong.blob(bytes);output=std::move(wrong);corrupt=true;}
    if(corrupt){faulted=true;std::fprintf(stderr,"NEXGPU_FAULT %s %u\n",fault,request.operation);}
    send(3,Frame{request.sequence,request.operation,Success,std::move(output.bytes)});if(closing)return 0;
   }catch(const Error &e){auto status=e.code=="E_DEVICE_UNSETTLED"||(gpu&&!gpu->drain())?Unsettled:Failure;send(3,Frame{request.sequence,request.operation,uint32_t(status),failure(e)});if(status==Unsettled)return 3;}
  }}
  if(gpu){gpu->closeNoThrow();if(!gpu->settled())return 3;}return 0;
 }catch(const std::exception &){if(gpu){gpu->closeNoThrow();if(!gpu->settled())return 3;}return 20;}
}
