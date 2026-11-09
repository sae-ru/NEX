# NEX scalar functions on Metal

This experimental backend generates GPU code from **ordinary checked NEX
functions**. It does not ask the application author to rewrite each function
as a Metal shader. The current language0.28 compiler checks the project first;
the generator reads its saved, versioned typed graph and emits only functions
reachable from the selected root. It has no second NEX parser.

Implemented scalar code includes i64, bool, unit, arithmetic and comparisons,
short-circuit boolean operators, local variables, branches, loops, concrete
generic calls and ordinary helper calls. Existing source pre/postconditions and
loop contracts retain the compiler's generated checks. Arguments and operands
are evaluated once in source order. Checked i64 operations use unsigned bits
and explicit guards, preserving both endpoints, division toward zero and
`MIN % -1 == 0`. Signed overflow is never delegated to Metal's undefined behavior.

The prototype currently emits MSL directly from the canonical checked graph.
It is separate from MLIR/LLVM native emission and the frozen0.163 SDK candidate.
Connecting generated kernels to the persistent owned task/device provider,
public compiler discovery/CLI, debug/profile sites and installed delivery is
the next integration. Other GPU backends, F64, aggregates, captures, recursion,
source errors/finally and general GPU/NPU execution remain pending. Unsupported
reachable code fails generation; the generator does not substitute CPU results.

## Try it

Select a language0.28 SDK and a checked project containing a pure shared function:

```nex
module example;
fn helper(x:i64)->i64 { return x*3; }
fn transform(x:i64,y:i64)->i64 {
  var answer:i64=helper(x);
  var i:i64=0;
  while i<y { answer=answer+1; i=i+1; }
  return answer;
}
fn main()->unit {}
```

```sh
NEX_SDK=/absolute/path/to/current/nex-sdk
python3 -B experiments/metal-codegen/codegen.py --sdk "$NEX_SDK" \
  --project /absolute/path/to/project --symbol transform \
  --output /absolute/new/generated-kernel

export SDKROOT="$(xcrun --sdk macosx --show-sdk-path)"
"$(xcrun --find clang++)" -std=c++20 -O2 -pthread -fobjc-arc \
  -fobjc-arc-exceptions -fblocks -isysroot "$SDKROOT" \
  -I"$NEX_SDK/share/nex/runtime" experiments/metal-codegen/runner.mm \
  -framework Foundation -framework Metal -o /absolute/new/metal-runner
python3 -B experiments/metal-codegen/verify.py --sdk "$NEX_SDK" \
  --runner /absolute/new/metal-runner --output /absolute/new/agreement
python3 -B experiments/metal-codegen/boundaries.py --sdk "$NEX_SDK" \
  --runner /absolute/new/metal-runner --output /absolute/new/boundaries
```

Code generation needs no Apple SDK or driver. The physical runner needs macOS
and a real Metal device. New output directories retain exact compiler,
revision, function, generator, runtime and shader identities. Raw graph reports
are development evidence and can include unrelated source; only `kernel.metal`
is emitted device code. The native runner is a test harness, not a NEX FFI grant
or a source-task provider.

## Dispatch and limits

Each GPU lane invokes the selected function on one row of arguments. Inputs are
little-endian signed64 words; bool arguments must be exactly0 or1. Results use
one signed64 word, with bool0/1 and unit0. A separate uint32 status per lane
reports overflow, division by zero, assertion failure, explicit GPU step-limit
exhaustion or invalid input. A failed lane never exposes a partial result.

The root has at most8 arguments; the reachable acyclic graph has at most128
functions and depth128. Dispatch has1..32768 lanes and1..65536 steps per lane,
with `lanes * steps <= 16777216`. The step counter bounds generated statement
and expression evaluations across loops and helper calls. It is distinct from
the CPU/reference task-step accounting. No wall-time speedup is claimed.

The runner verifies physical Metal command status4 and exactly one completion
handler before readback, then checks that all three buffers lose their retained
owners after the drained scope. The persistent provider still needs its own
task cancellation, resource ownership and relocation acceptance for these newly
generated kernels.

Apple documents the [64-bit Metal integer type](https://developer.apple.com/documentation/metal/mtldatatype/long)
and [undefined signed-overflow behavior](https://developer.apple.com/videos/play/wwdc2020/10632/?time=1940).
The actual target compilation and numerical comparisons establish this
prototype's tested scope.
