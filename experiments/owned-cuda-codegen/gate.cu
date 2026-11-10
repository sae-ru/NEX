// Explicit acceptance-only delay, queued before the unchanged generated root.
// One thread, bounded unsigned clock difference; repeated short kernels keep
// the test separate from a single long watchdog-sensitive launch.
extern "C" __global__ void nex_acceptance_gate(unsigned long long cycles) {
  if (blockIdx.x || threadIdx.x) return;
  const unsigned long long start = static_cast<unsigned long long>(clock64());
  while (static_cast<unsigned long long>(clock64()) - start < cycles) {}
}
