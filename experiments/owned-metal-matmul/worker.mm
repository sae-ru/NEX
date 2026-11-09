#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include "protocol.h"
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
using namespace owned_metal;

class GPU {
 struct Buffer { id<MTLBuffer> memory; uint32_t dtype; uint64_t bytes; };
 id<MTLDevice> device=nil;
 id<MTLCommandQueue> queue=nil;
 id<MTLComputePipelineState> pipeline=nil,matmulPipeline=nil;
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
  auto released=buffers.size();buffers.clear();active=nil;flags=nil;pipeline=nil;matmulPipeline=nil;queue=nil;device=nil;
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
  NSString *source=[[NSString alloc] initWithUTF8String:R"MSL(
#include <metal_stdlib>
using namespace metal;
kernel void affine(device const uchar*a[[buffer(0)]],device const uchar*b[[buffer(1)]],
 device uchar*out[[buffer(2)]],device uchar*flags[[buffer(3)]],constant uint2&p[[buffer(4)]],uint i[[thread_position_in_grid]]){
 if(i>=p.y)return;uint v=uint(a[i])*p.x+uint(b[i]);out[i]=uchar(v);flags[i]=uchar(v>255);
}
kernel void exact_matmul(device const uchar*a[[buffer(0)]],device const uchar*b[[buffer(1)]],
 device uchar*out[[buffer(2)]],device uchar*flags[[buffer(3)]],constant uint4&p[[buffer(4)]],uint i[[thread_position_in_grid]]){
 if(i>=p.w)return;uint row=i/p.z,col=i%p.z,lo=0;int hi=0;
 for(uint j=0;j<p.y;++j){
  int x=int(a[row*p.y+j]),y=int(b[j*p.z+col]);if(x>=128)x-=256;if(y>=128)y-=256;
  int product=x*y;uint before=lo;lo+=uint(product);hi+=(product<0?-1:0)+int(lo<before);
 }
 bool negative=(lo&0x80000000u)!=0;bool fits=(hi==0&&!negative)||(hi==-1&&negative);
 uint offset=4*i;out[offset]=uchar(lo);out[offset+1]=uchar(lo>>8);out[offset+2]=uchar(lo>>16);out[offset+3]=uchar(lo>>24);
 flags[i]=uchar(!fits);
}
)MSL"];
  NSError *error=nil;id<MTLLibrary> library=[device newLibraryWithSource:source options:nil error:&error];
  if(!library)metalError(error,"Metal source compilation failed");
  id<MTLFunction> function=[library newFunctionWithName:@"affine"];
  require(function!=nil,"Metal kernel lookup failed");
  pipeline=[device newComputePipelineStateWithFunction:function error:&error];
  if(!pipeline)metalError(error,"Metal pipeline creation failed");
  function=[library newFunctionWithName:@"exact_matmul"];require(function!=nil,"Metal matmul lookup failed");
  matmulPipeline=[device newComputePipelineStateWithFunction:function error:&error];
  if(!matmulPipeline)metalError(error,"Metal matmul pipeline creation failed");
  flags=[device newBufferWithLength:maximumElements options:MTLResourceStorageModeShared];
  require(flags&&flags.storageMode==MTLStorageModeShared,"Metal session scratch allocation failed");
  std::fprintf(stderr,"NEXGPU_OPEN %u %llu\n",selected,static_cast<unsigned long long>(device.registryID));
 }
 Data info()const{Data output;output.text(name);output.u64(device.registryID);output.u32(maximumElements);return output;}
 uint64_t upload(uint32_t dtype,Bytes &bytes){
  auto width=dtype==3?4u:1u;
  if(dtype<1||dtype>3||bytes.empty()||bytes.size()>uint64_t(maximumElements)*width||bytes.size()%width)
   throw Error("E_COMPUTE_SIZE","invalid typed buffer bytes");
  capacity();id<MTLBuffer> memory=[device newBufferWithBytes:bytes.data() length:bytes.size() options:MTLResourceStorageModeShared];
  require(memory&&memory.storageMode==MTLStorageModeShared,"Metal upload allocation failed");
  return publish(memory,dtype,bytes.size());
 }
 Data runKernel(Buffer a,Buffer b,bool matrix,uint32_t scale,uint32_t m,uint32_t k,uint32_t n,
                const std::function<void(uint32_t,bool)> &admitted){
  const uint64_t elements=matrix?uint64_t(m)*n:a.bytes,outputBytes=elements*(matrix?4:1);
  id<MTLComputePipelineState> chosen=matrix?matmulPipeline:pipeline;
  capacity();id<MTLBuffer> output=[device newBufferWithLength:outputBytes options:MTLResourceStorageModeShared];
  require(output&&output.storageMode==MTLStorageModeShared,"Metal output allocation failed");
  id<MTLSharedEvent> gate=nil;std::thread gateThread;bool committed=false;
  auto releaseGate=[&]()noexcept{
   if(gateThread.joinable())gateThread.join();
   if(gate&&gate.signaledValue<1)gate.signaledValue=1;
  };
  try{
   unsigned delay=0;if(const char *value=std::getenv("NEX_OWNED_METAL_TEST_GATE_MS")){
    auto size=std::strlen(value);if(!size||size>4||std::strspn(value,"0123456789")!=size)throw Error("E_DEVICE_PROTOCOL","invalid controlled gate delay");
    auto parsed=std::strtoul(value,nullptr,10);if(parsed>5000)throw Error("E_DEVICE_PROTOCOL","controlled gate delay exceeds limit");delay=unsigned(parsed);
   }
   if(delay){gate=[device newSharedEvent];require(gate&&gate.signaledValue==0,"Metal controlled shared event creation failed");}
   MTLCommandBufferDescriptor *descriptor=[[MTLCommandBufferDescriptor alloc] init];descriptor.retainedReferences=YES;
   active=[queue commandBufferWithDescriptor:descriptor];require(active&&active.retainedReferences,"Metal command must retain its resources");
   if(gate)[active encodeWaitForEvent:gate value:1];
   id<MTLComputeCommandEncoder> encoder=[active computeCommandEncoder];require(encoder!=nil,"Metal encoder creation failed");
   [encoder setComputePipelineState:chosen];[encoder setBuffer:a.memory offset:0 atIndex:0];[encoder setBuffer:b.memory offset:0 atIndex:1];
   [encoder setBuffer:output offset:0 atIndex:2];[encoder setBuffer:flags offset:0 atIndex:3];
   if(matrix){uint32_t parameters[]={m,k,n,uint32_t(elements)};[encoder setBytes:parameters length:sizeof(parameters) atIndex:4];}
   else{uint32_t parameters[]={scale,uint32_t(elements)};[encoder setBytes:parameters length:sizeof(parameters) atIndex:4];}
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
   const auto *overflow=static_cast<const uint8_t*>(flags.contents);bool rejected=std::any_of(overflow,overflow+elements,[](uint8_t v){return v!=0;});
   std::fprintf(stderr,"NEXGPU_KERNEL %llu %u %llu %u\n",static_cast<unsigned long long>(elements),scale,static_cast<unsigned long long>(ns),rejected?1u:0u);
   if(matrix)std::fprintf(stderr,"NEXGPU_MATMUL %u %u %u %llu %u\n",m,k,n,static_cast<unsigned long long>(ns),rejected?1u:0u);
   active=nil;if(rejected)throw Error("E_COMPUTE_OVERFLOW",matrix?"exact physical matmul output does not fit i32":"exact physical GPU output does not fit u8");
   auto id=publish(output,matrix?3:1,outputBytes);Data result;result.u64(id);result.u64(outputBytes);result.u64(uint64_t(ns));
   result.u32(uint32_t(MTLCommandBufferStatusCompleted));result.u32(completed->load());return result;
  }catch(...){
   releaseGate();if(committed){if(drain())active=nil;}else active=nil;throw;
  }
 }
 Data affine(uint64_t aid,uint64_t bid,uint32_t scale,const std::function<void(uint32_t,bool)> &admitted){
  auto a=buffer(aid),b=buffer(bid);
  if(a.dtype!=1||b.dtype!=1||a.bytes!=b.bytes||a.bytes>maximumElements||scale>255)
   throw Error("E_COMPUTE_SIZE","invalid exact u8 Metal affine buffers");
  return runKernel(a,b,false,scale,0,0,0,admitted);
 }
 Data matmul(uint64_t aid,uint64_t bid,uint32_t m,uint32_t k,uint32_t n,const std::function<void(uint32_t,bool)> &admitted){
  auto a=buffer(aid),b=buffer(bid);
  if(!m||!k||!n||m>maximumElements||k>maximumElements||n>maximumElements||a.dtype!=2||b.dtype!=2||
     uint64_t(m)*k!=a.bytes||uint64_t(k)*n!=b.bytes||uint64_t(m)*n>maximumElements)
   throw Error("E_COMPUTE_SIZE","invalid exact i8 Metal matmul buffers or dimensions");
  return runKernel(a,b,true,0,m,k,n,admitted);
 }
 Bytes download(uint64_t id,uint64_t offset,uint32_t count){
  auto value=buffer(id);if(offset>value.bytes||count>262144||count>value.bytes-offset)throw Error("E_DEVICE_BUFFER","read chunk exceeds immutable buffer");
  Bytes result(count);if(count)std::memcpy(result.data(),static_cast<const uint8_t*>(value.memory.contents)+offset,count);return result;
 }
 void free(uint64_t id){buffer(id);if(!drain())throw Error("E_DEVICE_UNSETTLED","Metal buffer remains physically unsettled");buffers.erase(id);}
 size_t live()const{return buffers.size();}
};

int main(){
 if(std::getenv("NEX_OWNED_METAL_TEST_NOISE"))std::fputs("controlled worker stdout diagnostic\n",stdout);
 std::signal(SIGPIPE,SIG_IGN);rlimit noCore{0,0};setrlimit(RLIMIT_CORE,&noCore);
 std::unique_ptr<GPU> gpu;uint64_t expected=1;Frame request{};bool faulted=false;
 try{
  if(const char *path=std::getenv("NEX_OWNED_METAL_TEST_CACHE_FILE")){
   if(path[0]!='/'||std::strlen(path)>4096)throw Error("E_DEVICE_TEST","controlled cache path must be absolute and bounded");
   int fd=::open(path,O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0600);if(fd<0)throw Error("E_DEVICE_TEST","controlled cache file creation failed");
   struct Close{int fd;~Close(){::close(fd);}} close{fd};char block[4096]={};std::fprintf(stderr,"NEXGPU_TEST_CACHE_BEGIN 9437184\n");
   for(size_t written=0;written<9437184;){auto n=::write(fd,block,std::min(sizeof(block),size_t(9437184-written)));if(n<0&&errno==EINTR)continue;if(n<=0)throw Error("E_DEVICE_TEST","controlled cache write failed");written+=size_t(n);}
   std::fprintf(stderr,"NEXGPU_TEST_CACHE_END 9437184\n");
  }
  if(const char *text=std::getenv("NEX_OWNED_METAL_TEST_NOISE_BYTES")){
   auto length=std::strlen(text);if(!length||length>8||std::strspn(text,"0123456789")!=length)throw Error("E_DEVICE_TEST","invalid controlled log size");
   auto count=std::strtoul(text,nullptr,10);if(count>16777216)throw Error("E_DEVICE_TEST","controlled log size exceeds16MiB");
   char block[4096];std::memset(block,'#',sizeof(block));block[sizeof(block)-1]='\n';std::fprintf(stderr,"NEXGPU_TEST_NOISE_BEGIN %lu\n",count);
   for(size_t n=0;n<count;){auto size=std::min(sizeof(block),size_t(count-n));if(std::fwrite(block,1,size,stdout)!=size)throw Error("E_DEVICE_TEST","controlled stdout write failed");n+=size;}
   if(std::fflush(stdout))throw Error("E_DEVICE_TEST","controlled stdout flush failed");std::fprintf(stderr,"NEXGPU_TEST_NOISE_END %lu\n",count);
  }
  const char *fault=std::getenv("NEX_OWNED_METAL_TEST_BAD_REPLY");
  if(fault&&std::strcmp(fault,"upload_truncated")&&std::strcmp(fault,"upload_wrong_size")&&std::strcmp(fault,"upload_reused_id")&&std::strcmp(fault,"affine_reused_id")&&std::strcmp(fault,"affine_truncated")&&std::strcmp(fault,"affine_trailing")&&std::strcmp(fault,"download_truncated")&&std::strcmp(fault,"download_wrong_size")&&std::strcmp(fault,"free_trailing")&&std::strcmp(fault,"close_truncated")&&std::strcmp(fault,"open_trailing")&&std::strcmp(fault,"matmul_truncated")&&std::strcmp(fault,"matmul_reused_id")&&std::strcmp(fault,"matmul_wrong_size")&&std::strcmp(fault,"matmul_bad_status")&&std::strcmp(fault,"matmul_bad_handlers"))throw Error("E_DEVICE_PROTOCOL","unknown controlled reply fault");
  auto wants=[&](const char *name){return !faulted&&fault&&std::strcmp(fault,name)==0;};
  while(receive(3,request)){ @autoreleasepool {
   if(request.sequence!=expected++||request.status!=0)throw Error("E_DEVICE_PROTOCOL","worker sequence or request status differs");
   try{
    Data input(std::move(request.payload)),output;bool closing=false;
    switch(request.operation){
     case Open:{if(gpu)throw Error("E_DEVICE_PROTOCOL","worker session already opened");auto ordinal=input.get32();input.done();gpu=std::make_unique<GPU>();gpu->open(ordinal);output=gpu->info();break;}
     case Upload:{if(!gpu)throw Error("E_DEVICE_PROTOCOL","no GPU session");auto dtype=input.get32();auto bytes=input.getBlob();input.done();output.u64(gpu->upload(dtype,bytes));output.u64(bytes.size());break;}
     case Affine:{if(!gpu)throw Error("E_DEVICE_PROTOCOL","no GPU session");auto a=input.get64(),b=input.get64();auto scale=input.get32();input.done();output=gpu->affine(a,b,scale,[&](uint32_t status,bool gated){Data progress;progress.u32(1);progress.u32(status);progress.u32(gated?1:0);send(3,Frame{request.sequence,request.operation,Progress,std::move(progress.bytes)});});break;}
     case Matmul:{if(!gpu)throw Error("E_DEVICE_PROTOCOL","no GPU session");auto a=input.get64(),b=input.get64();auto m=input.get32(),k=input.get32(),n=input.get32();input.done();output=gpu->matmul(a,b,m,k,n,[&](uint32_t status,bool gated){Data progress;progress.u32(1);progress.u32(status);progress.u32(gated?1:0);send(3,Frame{request.sequence,request.operation,Progress,std::move(progress.bytes)});});break;}
     case Download:{if(!gpu)throw Error("E_DEVICE_PROTOCOL","no GPU session");auto id=input.get64(),offset=input.get64();auto count=input.get32();input.done();output.blob(gpu->download(id,offset,count));break;}
     case Free:{if(!gpu)throw Error("E_DEVICE_PROTOCOL","no GPU session");auto id=input.get64();input.done();gpu->free(id);output.u32(uint32_t(gpu->live()));break;}
     case Close:{input.done();if(gpu&&gpu->live())throw Error("E_DEVICE_PROTOCOL","session closed before its actual buffers");if(gpu){gpu->closeNoThrow();if(!gpu->settled())throw Error("E_DEVICE_UNSETTLED","session release is not confirmed");gpu.reset();}output.u32(0);closing=true;break;}
     default:throw Error("E_DEVICE_PROTOCOL","unknown worker operation");
    }
    bool corrupt=false;
    if(request.operation==Matmul&&wants("matmul_truncated")){output.bytes.resize(7);corrupt=true;}
    if(request.operation==Matmul&&wants("matmul_reused_id")){for(size_t i=0;i<8;++i)output.bytes.at(i)=i==0?1:0;corrupt=true;}
    if(request.operation==Matmul&&wants("matmul_wrong_size")){output.bytes.at(8)^=1;corrupt=true;}
    if(request.operation==Matmul&&wants("matmul_bad_status")){output.bytes.at(24)=0;corrupt=true;}
    if(request.operation==Matmul&&wants("matmul_bad_handlers")){output.bytes.at(28)=0;corrupt=true;}
    if((request.operation==Upload&&wants("upload_truncated"))||(request.operation==Affine&&wants("affine_truncated"))){output.bytes.resize(7);corrupt=true;}
    if(request.operation==Upload&&wants("upload_wrong_size")){output.bytes.at(8)^=1;corrupt=true;}
    if((request.operation==Upload&&wants("upload_reused_id")&&gpu->live()>1)||(request.operation==Affine&&wants("affine_reused_id"))){for(size_t i=0;i<8;++i)output.bytes.at(i)=i==0?1:0;corrupt=true;}
    if((request.operation==Affine&&wants("affine_trailing"))||(request.operation==Free&&wants("free_trailing"))||(request.operation==Open&&wants("open_trailing"))){output.bytes.push_back(0);corrupt=true;}
    if((request.operation==Download&&wants("download_truncated"))||(request.operation==Close&&wants("close_truncated"))){output.bytes.resize(3);corrupt=true;}
    if(request.operation==Download&&wants("download_wrong_size")){Data original(std::move(output.bytes));auto bytes=original.getBlob();original.done();if(!bytes.empty())bytes.pop_back();Data wrong;wrong.blob(bytes);output=std::move(wrong);corrupt=true;}
    if(corrupt){faulted=true;std::fprintf(stderr,"NEXGPU_FAULT %s %u\n",fault,request.operation);}
    send(3,Frame{request.sequence,request.operation,Success,std::move(output.bytes)});if(closing)return 0;
   }catch(const Error &e){auto status=e.code=="E_DEVICE_UNSETTLED"||(gpu&&!gpu->drain())?Unsettled:Failure;send(3,Frame{request.sequence,request.operation,uint32_t(status),failure(e)});if(status==Unsettled)return 3;}
  }}
  if(gpu){gpu->closeNoThrow();if(!gpu->settled())return 3;}return 0;
 }catch(const std::exception &){if(gpu){gpu->closeNoThrow();if(!gpu->settled())return 3;}return 20;}
}
