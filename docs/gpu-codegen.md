# Checked scalar Metal emission

Development toolchain0.165 adds a compiler backend for ordinary checked
language0.28 functions. It emits Metal Shading Language directly from the
compiler's typed AST. It uses no second NEX parser and initializes no driver.
Native, reference and TypeScript source semantics and graph identities are
unchanged; no language migration is required.

```sh
nex describe --field gpu_codegen --json
nex emit --kind metal --entry transform --input-layout columns -o kernel.metal --json
```

Select a shared pure concrete function, including a concrete generic instance
reached by an ordinary root. Only its reachable functions are emitted.
Unsupported reachable types or instructions fail with a source diagnostic;
unreachable server/foreign code is excluded. Failed emission preserves an
existing output file. Text output goes to stdout when `-o` is absent; `--json`
returns the [versioned emission record](../llm/metal-emission.schema.json), with
inline source or its output path, actual shader hash, revision, compiler and
descriptor identities, parameter/result types and reachable function hashes.
Generated function line ranges map to their original declarations. This is
function attribution; GPU stepping and operation profiling remain pending.

The current subset supports checked i64, bool and unit, locals and assignment,
arithmetic/comparisons, lazy boolean operators, branches, loops, ordinary helper
calls and lowered source/loop contracts. Arguments and operands execute once in
source order. Signed arithmetic uses unsigned bits and explicit overflow guards;
division truncates toward zero and `MIN % -1` is zero. Fatal arithmetic/assertion
outcomes retain a separate lane status and publish no partial result.

The root has0..8 i64/bool parameters. At most128 reachable functions and128 call
levels are supported, with emitted UTF-8 source bounded to16MiB. Recursion,
effects, non-shared realms, heap values, f64, closures, indirect calls, match and
source-error/finally control are rejected. Diagnostics use `E_GPU_TYPE`,
`E_GPU_REALM`, `E_GPU_RECURSION`, `E_GPU_LIMIT` and `E_GPU_UNSUPPORTED`.

## Kernel host contract

The entry is `nex_generated_map`. A trusted host supplies physical Metal buffers
and validates their exact lengths and explicit device authority before dispatch.
Source emission grants neither host access nor a fallback to CPU.

Each input is a signed64 word; bool must be exactly0 or1. `rows` uses one row-major
input at buffer0, output at1, uint32 lane statuses at2 and constant uint2
`{lanes,steps}` at3. `columns` uses one input buffer per parameter at0..7, output
at8, statuses at9 and the same parameters at10. A zero-argument columns root
needs no dummy input buffer. Output is one signed64 word per lane: bool0/1,
unit0 and zero for a failed lane.

The host must enforce1..32768 lanes,1..65536 steps per lane and
`lanes * steps <= 16777216`. The step counter bounds generated expressions and
statements across helper calls. It is separate from CPU/reference task budgets.
Lane status0 means success;1 overflow,2 division by zero,3 assertion,4 GPU step
limit,5 internal failure and6 invalid canonical input. A source diagnostic is
not a runtime lane status.

The public emitter's [scoped acceptance](evidence/macos-public-Metal-emission-0.165.0-2026-11-10.json)
passed20 reference/native Debug/Release/TypeScript/Metal cases with1799 oracle
lanes per layout. Rows and columns executed physically on Apple M5 Max, with48
dispatches including eight boundary dispatches; nine invalid host inputs were
rejected. The independent record also covers all native targets, six CLI tests
and actual JSON contract validation. This establishes the named scalar scope.

## Execute through owned NEX resources

The checkout [owned-provider preparer](../experiments/owned-metal-codegen/README.md)
now calls the selected compiler's public emitter with `columns` layout. It keeps
the exact emission record, source maps, canonical function hashes and shader
SHA256, then obtains nine actual FFI signatures and builds a pinned worker/module
bundle. Select a0.165 or later SDK and a source project containing the scalar root:

```sh
python3 -B experiments/owned-metal-codegen/prepare.py --sdk "$NEX_SDK" \
  --source-project /absolute/path/to/project --symbol transform \
  --output /absolute/new/gpu-project --cxx "$(xcrun --find clang++)"
```

`--check-sdk` checks preparation and source signatures without native compilation
on other hosts. Native preparation requires macOS and its SDK. Execution uses
the generated project's `make_context`, `try_apply`/`apply` and the explicitly
granted `foreign.json`. See the preparer guide for a complete caller. Buffers and
read cursors retain their physical parents; cancellation and failures drain the
admitted GPU command before resource release. `try_apply` returns explicit
Results, while `apply` forwards original fatal codes through the trusted C API.

This is a checkout integration. Discoverable installed tools, full regression
and matching immutable SDK qualification remain pending. GPU operation debugging
and profiling, further types/backends and device-loss recovery are also pending.
Emitting a shader alone does not establish device execution or speedup.
