// Physical execution harness for generated NEX scalar kernels. This is not the
// source-task provider; the persistent owned provider remains a separate gate.
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include "third_party/json.hpp"
#include <algorithm>
#include <atomic>
#include <charconv>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

using JSON=nlohmann::json;
static void require(bool condition,const std::string &message){if(!condition)throw std::runtime_error(message);}
static uint32_t number(const char *value,uint32_t minimum,uint32_t maximum){
  uint32_t result=0;const char *end=value+std::strlen(value);auto parsed=std::from_chars(value,end,result);
  require(parsed.ec==std::errc{}&&parsed.ptr==end&&result>=minimum&&result<=maximum,"invalid bounded argument");return result;
}
static std::string text(NSString *value){const char *bytes=value?value.UTF8String:nullptr;require(bytes,"Metal returned no UTF-8 text");return bytes;}
static void write(const char *path,const void *bytes,size_t size){
  std::ofstream output(path,std::ios::binary|std::ios::trunc);require(bool(output),"cannot open result file");
  output.write(static_cast<const char*>(bytes),static_cast<std::streamsize>(size));output.close();require(bool(output),"cannot write result file");
}
struct Settlement {
  id<MTLCommandBuffer> command=nil;
  ~Settlement(){if(command)[command waitUntilCompleted];}
};
int main(int argc,char **argv){
  JSON report={{"schema","nex.generated-Metal-physical/1"},{"ok",false},{"CPU_substitute",false},
    {"installed_SDK_accepted",false},{"source_task_provider_integrated",false}};
  try{
    require(argc==9,"expected shader input output errors count arguments steps device-index");
    uint32_t count=number(argv[5],1,32768),arguments=number(argv[6],0,8),steps=number(argv[7],1,65536),index=number(argv[8],0,63);
    require(uint64_t(count)*steps<=16777216,"kernel count times per-lane step bound exceeds16777216");
    __weak id<MTLBuffer> inputWitness=nil,outputWitness=nil,errorWitness=nil;
    std::vector<uint8_t> output(size_t(count)*8),errors(size_t(count)*4);
    std::atomic<unsigned> handlers{0};
    @autoreleasepool{
      NSArray<id<MTLDevice>> *devices=MTLCopyAllDevices();require(devices&&devices.count<=64&&index<devices.count,"physical Metal device unavailable");
      id<MTLDevice> device=devices[index];require(device&&device.registryID,"Metal device has no registry identity");
      report["device"]=text(device.name);report["registryID"]=device.registryID;
      NSData *shaderBytes=[NSData dataWithContentsOfFile:[NSString stringWithUTF8String:argv[1]]];
      require(shaderBytes&&shaderBytes.length>0&&shaderBytes.length<=4194304,"shader is absent or outside4MiB bound");
      NSString *source=[[NSString alloc]initWithData:shaderBytes encoding:NSUTF8StringEncoding];require(source!=nil,"shader is not UTF-8");
      MTLCompileOptions *options=[[MTLCompileOptions alloc]init];options.mathMode=MTLMathModeSafe;options.mathFloatingPointFunctions=MTLMathFloatingPointFunctionsPrecise;options.languageVersion=MTLLanguageVersion3_1;
      NSError *error=nil;id<MTLLibrary> library=[device newLibraryWithSource:source options:options error:&error];
      require(library!=nil,error?text(error.localizedDescription):"generated Metal shader did not compile");
      id<MTLFunction> function=[library newFunctionWithName:@"nex_generated_map"];require(function!=nil,"generated kernel missing");
      id<MTLComputePipelineState> pipeline=[device newComputePipelineStateWithFunction:function error:&error];
      require(pipeline!=nil,error?text(error.localizedDescription):"generated pipeline failed");
      id<MTLCommandQueue> queue=[device newCommandQueue];require(queue!=nil,"Metal queue missing");
      @autoreleasepool{
        NSData *inputBytes=[NSData dataWithContentsOfFile:[NSString stringWithUTF8String:argv[2]]];
        size_t inputSize=size_t(count)*arguments*8;require(inputBytes&&inputBytes.length==inputSize,"input does not match scalar row shape");
        id<MTLBuffer> input=[device newBufferWithLength:std::max<size_t>(8,inputSize) options:MTLResourceStorageModeShared];
        id<MTLBuffer> result=[device newBufferWithLength:output.size() options:MTLResourceStorageModeShared];
        id<MTLBuffer> status=[device newBufferWithLength:errors.size() options:MTLResourceStorageModeShared];
        require(input&&result&&status,"Metal buffers unavailable");inputWitness=input;outputWitness=result;errorWitness=status;
        if(inputSize)std::memcpy(input.contents,inputBytes.bytes,inputSize);
        std::memset(result.contents,0xa5,output.size());std::memset(status.contents,0xa5,errors.size());
        MTLCommandBufferDescriptor *descriptor=[[MTLCommandBufferDescriptor alloc]init];descriptor.retainedReferences=YES;
        id<MTLCommandBuffer> command=[queue commandBufferWithDescriptor:descriptor];require(command!=nil,"Metal command missing");
        Settlement settlement{command};auto *counter=&handlers;
        [command addCompletedHandler:^(id<MTLCommandBuffer> completed){(void)completed;counter->fetch_add(1,std::memory_order_release);}];
        id<MTLComputeCommandEncoder> encoder=[command computeCommandEncoder];require(encoder!=nil,"Metal encoder missing");
        [encoder setComputePipelineState:pipeline];[encoder setBuffer:input offset:0 atIndex:0];[encoder setBuffer:result offset:0 atIndex:1];[encoder setBuffer:status offset:0 atIndex:2];
        uint32_t parameters[2]={count,steps};[encoder setBytes:parameters length:sizeof(parameters) atIndex:3];
        NSUInteger width=std::min<NSUInteger>(pipeline.maxTotalThreadsPerThreadgroup,256);require(width>0,"Metal threadgroup missing");
        [encoder dispatchThreads:MTLSizeMake(count,1,1) threadsPerThreadgroup:MTLSizeMake(width,1,1)];[encoder endEncoding];
        require(inputWitness&&outputWitness&&errorWitness,"buffers lost before physical submission");
        [command commit];[command waitUntilCompleted];
        report["Metal_command_buffer_status"]=static_cast<unsigned>(command.status);
        require(command.status==MTLCommandBufferStatusCompleted,command.error?text(command.error.localizedDescription):"physical kernel did not complete");
        auto deadline=std::chrono::steady_clock::now()+std::chrono::seconds(10);
        while(handlers.load(std::memory_order_acquire)==0&&std::chrono::steady_clock::now()<deadline)std::this_thread::sleep_for(std::chrono::milliseconds(1));
        require(handlers.load(std::memory_order_acquire)==1,"completion handler count differs from1");
        double ns=(command.GPUEndTime-command.GPUStartTime)*1e9;require(std::isfinite(ns)&&ns>0&&ns<1e14,"physical GPU timing unavailable");
        report["kernel_ns"]=static_cast<uint64_t>(ns);report["completion_handlers"]=handlers.load();
        std::memcpy(output.data(),result.contents,output.size());std::memcpy(errors.data(),status.contents,errors.size());
        report["physical_completion_before_readback"]=true;
        settlement.command=nil;command=nil;encoder=nil;input=nil;result=nil;status=nil;
      }
      queue=nil;pipeline=nil;function=nil;library=nil;device=nil;devices=nil;
    }
    require(!inputWitness&&!outputWitness&&!errorWitness,"Metal buffer remained retained after drained scope");
    write(argv[3],output.data(),output.size());write(argv[4],errors.data(),errors.size());
    report.update({{"ok",true},{"count",count},{"arguments",arguments},{"per_lane_step_bound",steps},
      {"all_three_buffers_released_after_completion",true},{"physical_GPU_kernel_events",1}});
    std::cout<<report.dump()<<'\n';return 0;
  }catch(const std::exception &error){report["error"]=error.what();std::cout<<report.dump()<<'\n';return 1;}
}
