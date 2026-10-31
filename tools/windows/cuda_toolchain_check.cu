// Compile-only NVCC/MSVC compatibility check, separate from the driver probe.
// No device is initialized and this is not a NEX invocation.
#include <cuda_runtime.h>
__global__ void nex_cuda_toolchain_check(unsigned *output){*output=42;}
int main(){return 0;}
