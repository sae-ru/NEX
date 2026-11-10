#pragma once
// Device-only control using Clang's own builtin register declarations.
// No NVIDIA headers, libdevice or host runtime are needed by this scalar subset.
#if !defined(__clang__) || !defined(__CUDA__) || !defined(__CUDA_ARCH__)
#error Clang CUDA device-only compilation is required
#endif
#define __device__ __attribute__((device))
#define __global__ __attribute__((global))
#include <__clang_cuda_builtin_vars.h>
__device__ inline long long clock64(){return __nvvm_read_ptx_sreg_clock64();}
