// Native Metal prerequisites for the future owned-device provider.
// This executable is not a NEX backend or a compiler acceptance test.
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include "third_party/json.hpp"
#include <algorithm>
#include <atomic>
#include <charconv>
#include <chrono>
#include <cmath>
#include <cstring>
#include <cstdint>
#include <iostream>
#include <limits>
#include <memory>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

using JSON = nlohmann::json;
using Bytes = std::vector<uint8_t>;
static constexpr size_t maximumElements = 262144;

static void require(bool value, const char *message) {
  if (!value) throw std::runtime_error(message);
}

static std::string text(NSString *value) {
  const char *bytes = value ? value.UTF8String : nullptr;
  require(bytes != nullptr, "Metal returned no UTF-8 text");
  return bytes;
}

static void checkedCase(id<MTLDevice> device, id<MTLCommandQueue> queue,
                        id<MTLComputePipelineState> pipeline, JSON &report,
                        const std::string &name, Bytes left, Bytes right,
                        uint32_t scale, bool gated = false) {
  require(!left.empty() && left.size() == right.size() && left.size() <= maximumElements && scale <= 255,
          "invalid exact U8 case");
  JSON result = { {"name", name}, {"elements", left.size()}, {"scale", scale},
                  {"controlled_shared_event", gated} };
  __weak id<MTLBuffer> inputWitnessA = nil;
  __weak id<MTLBuffer> inputWitnessB = nil;
  @autoreleasepool {
    const size_t count = left.size();
    id<MTLBuffer> a = [device newBufferWithBytes:left.data() length:count options:MTLResourceStorageModeShared];
    id<MTLBuffer> b = [device newBufferWithBytes:right.data() length:count options:MTLResourceStorageModeShared];
    id<MTLBuffer> output = [device newBufferWithLength:count options:MTLResourceStorageModeShared];
    id<MTLBuffer> flags = [device newBufferWithLength:count options:MTLResourceStorageModeShared];
    require(a && b && output && flags, "Metal buffer allocation failed");
    require(a.storageMode == MTLStorageModeShared && b.storageMode == MTLStorageModeShared &&
            output.storageMode == MTLStorageModeShared && flags.storageMode == MTLStorageModeShared,
            "the probe requires shared storage");
    std::memset(output.contents, 0xa5, count);
    std::memset(flags.contents, 0xa5, count);
    inputWitnessA = a;
    inputWitnessB = b;
    MTLCommandBufferDescriptor *descriptor = [[MTLCommandBufferDescriptor alloc] init];
    descriptor.retainedReferences = YES;
    id<MTLCommandBuffer> command = [queue commandBufferWithDescriptor:descriptor];
    require(command && command.retainedReferences, "command buffer does not retain its resources");
    id<MTLSharedEvent> gate = gated ? [device newSharedEvent] : nil;
    require(!gated || (gate && gate.signaledValue == 0), "shared event did not start unsignaled");
    struct SettleOnExit {
      id<MTLCommandBuffer> command;
      id<MTLSharedEvent> gate;
      bool committed = false;
      ~SettleOnExit() {
        if (committed) {
          if (gate && gate.signaledValue < 1) gate.signaledValue = 1;
          [command waitUntilCompleted];
        }
      }
    } settlement{command, gate};
    if (gate) [command encodeWaitForEvent:gate value:1];
    id<MTLComputeCommandEncoder> encoder = [command computeCommandEncoder];
    require(encoder != nil, "Metal did not create a compute encoder");
    [encoder setComputePipelineState:pipeline];
    [encoder setBuffer:a offset:0 atIndex:0];
    [encoder setBuffer:b offset:0 atIndex:1];
    [encoder setBuffer:output offset:0 atIndex:2];
    [encoder setBuffer:flags offset:0 atIndex:3];
    uint32_t parameters[] = {scale, static_cast<uint32_t>(count)};
    [encoder setBytes:parameters length:sizeof(parameters) atIndex:4];
    const NSUInteger threads = std::min<NSUInteger>(pipeline.threadExecutionWidth,
                                                   pipeline.maxTotalThreadsPerThreadgroup);
    require(threads > 0, "Metal returned no legal threadgroup size");
    [encoder dispatchThreadgroups:MTLSizeMake((count + threads - 1) / threads, 1, 1)
              threadsPerThreadgroup:MTLSizeMake(threads, 1, 1)];
    [encoder endEncoding];
    encoder = nil;
    auto completed = std::make_shared<std::atomic<unsigned>>(0);
    [command addCompletedHandler:^(id<MTLCommandBuffer>) { completed->fetch_add(1); }];
    [command commit];
    settlement.committed = true;
    const auto submitted = std::chrono::steady_clock::now();
    if (gated) {
      // Drop the caller's two strong input references while a real GPU wait is
      // pending. The command buffer must keep those exact resources alive.
      a = nil;
      b = nil;
      std::this_thread::sleep_for(std::chrono::milliseconds(100));
      const auto pending = command.status;
      require(pending == MTLCommandBufferStatusCommitted || pending == MTLCommandBufferStatusScheduled,
              "the gated command was not pending on the actual Metal queue");
      require(completed->load() == 0 && command.GPUStartTime == 0.0 && command.GPUEndTime == 0.0,
              "a gated command reported completion before the shared event was signaled");
      require(inputWitnessA != nil && inputWitnessB != nil, "input references disappeared before GPU completion");
      auto *before = static_cast<const uint8_t *>(output.contents);
      require(std::all_of(before, before + count, [](uint8_t value) { return value == 0xa5; }),
              "output changed before the GPU wait was released");
      result.update({ {"pending_status", static_cast<unsigned>(pending)},
                      {"caller_inputs_dropped_while_pending", true},
                      {"command_retained_inputs_while_pending", true},
                      {"output_untouched_while_pending", true} });
      gate.signaledValue = 1;
    }
    [command waitUntilCompleted];
    settlement.committed = false;
    require(command.status == MTLCommandBufferStatusCompleted && command.error == nil,
            "Metal command did not complete successfully");
    require(completed->load() == 1, "completion handler did not finish exactly once");
    const double start = command.GPUStartTime, end = command.GPUEndTime;
    const double nanoseconds = (end - start) * 1000000000.0;
    require(std::isfinite(start) && std::isfinite(end) && start > 0 && end >= start &&
            nanoseconds >= 0 && nanoseconds < static_cast<double>(INT64_MAX),
            "Metal did not provide a bounded completed GPU interval");
    const auto *actual = static_cast<const uint8_t *>(output.contents);
    const auto *overflow = static_cast<const uint8_t *>(flags.contents);
    size_t expectedOverflow = 0;
    for (size_t i = 0; i < count; ++i) {
      const uint32_t expected = uint32_t(left[i]) * scale + uint32_t(right[i]);
      require(actual[i] == uint8_t(expected) && overflow[i] == uint8_t(expected > 255),
              "physical Metal result differs from the exact independent CPU oracle");
      expectedOverflow += expected > 255;
    }
    result.update({ {"ok", true}, {"completed_status", static_cast<unsigned>(command.status)},
                    {"completion_handlers", completed->load()}, {"physical_GPU_interval_ns", uint64_t(nanoseconds)},
                    {"overflow_elements", expectedOverflow}, {"would_require_checked_overflow_error", expectedOverflow != 0},
                    {"host_wait_seconds", std::chrono::duration<double>(std::chrono::steady_clock::now() - submitted).count()},
                    {"GPU_output_matches_oracle", true}, {"CPU_fallback", false} });
    // The CPU oracle only verifies the device result. No NEX result is
    // published here, especially for the checked-overflow cases.
  }
  result["input_objects_released_after_scope"] = inputWitnessA == nil && inputWitnessB == nil;
  report["cases"].push_back(std::move(result));
}

int main(int argc, char **argv) {
  JSON report = { {"schema", "nex.Metal-native-prerequisite/1"}, {"ok", false},
                  {"cases", JSON::array()}, {"NEX_provider_integrated", false},
                  {"general_GPU_codegen_accepted", false}, {"complete_SDK_accepted", false} };
  try {
    unsigned ordinal = 0;
    if (argc != 1) {
      require(argc == 3 && std::string(argv[1]) == "--ordinal", "use --ordinal 0..63");
      const std::string number = argv[2];
      auto parsed = std::from_chars(number.data(), number.data() + number.size(), ordinal);
      require(!number.empty() && number.size() <= 2 && parsed.ec == std::errc{} &&
              parsed.ptr == number.data() + number.size() && ordinal < 64, "ordinal must be 0..63");
    }
    @autoreleasepool {
      NSArray<id<MTLDevice>> *devices = MTLCopyAllDevices();
      require(devices && devices.count > ordinal, "the selected Metal GPU is unavailable");
      id<MTLDevice> device = devices[ordinal];
      require(device && device.registryID != 0, "Metal returned no physical device identity");
      id<MTLCommandQueue> queue = [device newCommandQueue];
      require(queue != nil, "Metal command queue creation failed");
      NSString *source = @"#include <metal_stdlib>\nusing namespace metal;\n"
        "kernel void exact_affine(device const uchar *a [[buffer(0)]],device const uchar *b [[buffer(1)]],"
        "device uchar *out [[buffer(2)]],device uchar *flags [[buffer(3)]],constant uint2 &parameters [[buffer(4)]],"
        "uint i [[thread_position_in_grid]]){if(i>=parameters.y)return;uint v=uint(a[i])*parameters.x+uint(b[i]);"
        "out[i]=uchar(v);flags[i]=uchar(v>255);}";
      NSError *error = nil;
      id<MTLLibrary> library = [device newLibraryWithSource:source options:nil error:&error];
      if (!library) throw std::runtime_error(error ? text(error.localizedDescription) : "Metal library creation failed");
      id<MTLFunction> function = [library newFunctionWithName:@"exact_affine"];
      require(function != nil, "Metal kernel lookup failed");
      id<MTLComputePipelineState> pipeline = [device newComputePipelineStateWithFunction:function error:&error];
      if (!pipeline) throw std::runtime_error(error ? text(error.localizedDescription) : "Metal pipeline creation failed");
      report.update({ {"device", text(device.name)}, {"registryID", std::to_string(device.registryID)},
                      {"ordinal", ordinal}, {"available_devices", devices.count},
                      {"thread_execution_width", pipeline.threadExecutionWidth},
                      {"maximum_threads_per_threadgroup", pipeline.maxTotalThreadsPerThreadgroup},
                      {"uses_shared_storage", true}, {"actual_Metal_pipeline_created", true} });
      checkedCase(device, queue, pipeline, report, "small_affine", {1,20,50}, {2,3,4}, 3);
      Bytes all(256), complement(256);
      for (size_t i = 0; i < 256; ++i) { all[i] = uint8_t(i); complement[i] = uint8_t(255 - i); }
      checkedCase(device, queue, pipeline, report, "all_octets", all, complement, 1);
      for (uint32_t scale : {0u,1u,2u,127u,255u})
        checkedCase(device, queue, pipeline, report, "scale_" + std::to_string(scale), {1}, {0}, scale);
      checkedCase(device, queue, pipeline, report, "maximum_262144", Bytes(maximumElements,85), Bytes(maximumElements,0), 3);
      Bytes last(maximumElements,254); last.back() = 255;
      checkedCase(device, queue, pipeline, report, "overflow_last_262144", Bytes(maximumElements,1), last, 1);
      checkedCase(device, queue, pipeline, report, "overflow_first", {255}, {1}, 1);
      checkedCase(device, queue, pipeline, report, "queue_recovers_after_overflow", {20}, {22}, 1);
      checkedCase(device, queue, pipeline, report, "physical_shared_event_and_retained_inputs", {20}, {22}, 1, true);
      require(report["cases"].size() == 12, "native corpus incomplete");
      report.update({ {"ok", true}, {"state", "native-prerequisites-passed"},
                      {"actual_GPU_compute_cases", report["cases"].size()},
                      {"NEX_provider_integration_pending", true} });
    }
  } catch (const std::exception &error) {
    report.update({ {"state", "failed"}, {"error", error.what()} });
  }
  std::cout << report.dump(2) << '\n';
  return report["ok"].get<bool>() ? 0 : 1;
}
