# Owned generated Metal functions

This checkout prototype prepares a persistent GPU provider for an ordinary
checked NEX scalar function. The selected compiler checks the source project;
the [scalar generator](../metal-codegen/README.md) lowers its exact saved typed
graph to MSL. A new pinned bundle contains the generated worker and typed host
module. NEX reference and native task programs execute that physical GPU code
through genuine `std/device` Session/Buffer resources.

It is outside the frozen0.163 SDK candidate and now requires the0.164 explicit
fatal-trap C API. Language0.28, taskABI7 and source grammar are unchanged.
Public compiler CLI/discovery,
diagnostics/debug/profile, immutable SDK delivery and broader GPU/NPU remain
separate work.

## Prepare and call

The source project must contain the selected concrete shared pure function.
The current scalar subset supports i64/bool/unit, control flow, helper/concrete
generic calls and lowered source contracts; unsupported reachable code is
rejected before a driver is initialized.

```sh
export SDKROOT="$(xcrun --sdk macosx --show-sdk-path)"
NEX_SDK=/absolute/path/to/current/nex-sdk
python3 -B experiments/owned-metal-codegen/prepare.py --sdk "$NEX_SDK" \
  --source-project /absolute/path/to/checked-project --symbol transform \
  --output /absolute/new/gpu-project --cxx "$(xcrun --find clang++)"
```

`--check-sdk` performs source/signature preparation without native compilation,
an Apple SDK or a GPU. Native preparation requires macOS, its SDK and C++20.
Preparation does not initialize the driver. It creates a project with checked
source wrappers and nine signatures obtained from the actual compiler.

The generated project's `main.nex` contains these source-level helpers:

```nex
server fn main()->unit !{task,ffi,io} {
  let session:d::Session=unwrap(make_context());
  // For a selected transform(x:i64,y:i64)->i64:
  let result:bytes=apply(session,
    [encode_i64s([6,7]),encode_i64s([2,3])],2,512);
  print(encode_json(decode_i64s(result)));
  resource_close(session);
}
```

Replace its generated `main`, check/build with the chosen SDK and pass its exact
`foreign.json` at execution (`--foreign` to eval; `--nex-foreign` to the native
executable). The host catalogue grants the bundle; source metadata alone does
not grant native execution.

Each argument is a separate immutable column of little-endian signed64 words.
Bool words must be exactly0 or1. A root can have0..8 arguments and1..32768
lanes. Every column is at most262144 bytes, so all eight maximum columns total
2MiB while each FFI call remains inside the original copy budget. There is no
dummy input allocation for a zero-argument function. Output is at most262144
bytes; bool is0/1 and unit is0. Per-lane steps are1..65536 with a total bound
`lanes * steps <= 16777216`.

## Results, tasks and lifetime

`try_apply` returns `result<bytes>`. GPU overflow, division/assertion failures,
invalid canonical input and step exhaustion retain their codes inside that
explicit Result. Failed work does not become CPU fallback. The helper `apply`
first completes `try_apply`, including physical GPU settlement and temporary
resource close. On failure its pinned `fatal` callback submits the copied code
and message through `NEX_FFI_V1_TRAP_SIZE` / `raise_trap`. This reports the original
fatal code, bypasses source catches/finalizers and retains runtime cleanup.
Host cancellation/deadline has priority. Ordinary `unwrap(try_apply(...))` keeps
the existing **E_RESULT** contract. No artificial CPU arithmetic manufactures
trap codes. The new C suffix requires matching core and SDK qualification.

Input and output Buffers retain their genuine physical Session. An admitted
ReadCursor retains its Buffer. Logical parent close denies new use while
existing descendants retain physical owners; hidden parents survive returns
and sibling task channels. A map call keeps borrowed column owners until the
worker physically settles. Cancellation/deadline remain sticky in the host
call while the admitted command is drained. Physical command status4 and one
completion handler precede successful publication and resource release.

The worker handshake pins the generated shader hash and argument count; its
framed protocol has a distinct magic/version from the other adapters. Immutable
column shape and physical Session are checked again inside the module/worker.
Opaque resources from another provider image are rejected before native pointer
use. Arbitrary vendor stdout is kept on a separate bounded diagnostic pipe.

The scalar generator and this persistent resource path have separate
verification scopes. Malformed-reply/log-stress acceptance for this new path
and complete installed SDK remain pending.
`verify.py` covers the two-argument multiply/conditional-loop fixture from the development evidence;
`numerics.py` prepares and compares22 numerical/limit fixtures. Actual device
recovery/reset and ownership under unknown vendor completion remain pending.
