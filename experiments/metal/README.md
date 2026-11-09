# Metal backend prerequisites

`probe.mm` exercises native Metal compute before integrating a provider with
`std/device`. It is a development prerequisite, not a Metal backend exposed by
the NEX compiler or an accepted SDK feature. The separate
[owned Metal development provider](../owned-metal/README.md) now uses these
native prerequisites. General GPU code generation and qualified Metal SDK
delivery remain pending.

The twelve cases check exact U8 Add/Affine results against a CPU oracle, every
octet, scales0/1/2/127/255,262144 elements, overflow flags and reuse after overflow.
A real shared-event wait checks that output stays unchanged before admission
is released, completion is not reported early, and the command buffer retains
input objects after their caller releases its references. GPU timestamps and
successful completion are read after `waitUntilCompleted`. No CPU path supplies
the GPU output.

Build on a Mac with the selected Apple SDK and a C++20 Objective-C++ compiler:

```sh
clang++ -std=c++20 -fobjc-arc -fobjc-arc-exceptions -fblocks -O2 -I runtime \
  experiments/metal/probe.mm -framework Foundation -framework Metal \
  -o /absolute/new/output/metal-probe
/absolute/new/output/metal-probe --ordinal 0
```

Select a new output directory. The executable emits its own JSON result and
actual device identity. Execution requires a real available Metal GPU; this
source file alone establishes no hardware result. Object-release observations
do not account for all driver caches or total process/device memory.

Integration must preserve the existing device resource parent/dependency rules,
physical settlement before capacity release, pinned worker protocol and log
isolation, checked overflow, explicit placement/fallback and native/reference
agreement. Cancellation, malformed worker replies and current installed SDK
delivery need their own actual acceptance tests.

Primary API contracts: [retained references](https://developer.apple.com/documentation/metal/mtlcommandbuffer/retainedreferences),
[completion](https://developer.apple.com/documentation/metal/mtlcommandbuffer/waituntilcompleted%28%29),
[GPU timing](https://developer.apple.com/documentation/metal/mtlcommandbuffer/gpuendtime),
and [CPU/GPU shared events](https://developer.apple.com/documentation/metal/mtlsharedevent/signaledvalue).
