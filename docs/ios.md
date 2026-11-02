# iOS native libraries

The exact published0.159 SDK/language0.28 now has a scoped
[native Simulator execution receipt](evidence/0.159.0-ios-native/README.md):
Debug/Release standalone IOSSIMULATOR processes on iOS27.1 passed1400 native
calls and1400 owned cleanup checks, including typed source errors, contracts
and checked overflow. This does not qualify UIKit, physical devices or mobile
application delivery. The original archive/build contract below dates to0.61.

Source development0.160 adds [physical entry ABI discovery](native-entry-abi.md).
Use it for a matching source build; with the published0.159 SDK inspect the
actual LLVM signature. A native symbol alone does not describe hidden error
outputs or the complete host calling contract.

## Original static archive contract — toolchain 0.61

A macOS NEX compiler can produce a native static library for:

| Target | Architecture | Explicit SDK platform |
|---|---|---|
| `arm64-apple-ios17.0` | ARM64 device | `iphoneos` |
| `arm64-apple-ios17.0-simulator` | ARM64 simulator | `iphonesimulator` |
| `x86_64-apple-ios17.0-simulator` | Intel simulator | `iphonesimulator` |

The deployment version is explicit and must lie within the selected SDK's
reported range. Other supported versions can replace `17.0`. A 64-bit architecture
alone does not identify the ABI: device, simulator and macOS objects have separate
platform metadata, cache keys and runtime objects.

Use `--library` and a concrete entry function with `--profile debug` or `release`.
The reachable program passes the normal checker and native MLIR/LLVM lowering.
Strings, immutable values, checked arithmetic, traits and generics keep their
language semantics. This backend has the same source syntax and language0.16.

## Explicit configuration

Create a `nex.toolchain/1` configuration using the actual matching Clang and SDK:

```json
{
  "schema": "nex.toolchain/1",
  "target": "arm64-apple-ios17.0",
  "compiler": "/path/to/llvm22/bin/clang++",
  "sysroot": "/path/to/Xcode/iPhoneOS.sdk"
}
```

Find the local SDK with `xcrun --sdk iphoneos --show-sdk-path`; for a simulator use
`iphonesimulator` and a simulator triple. Pass actual paths instead of the
illustrative values above. `nex doctor --json` reports the selected native driver.
An omitted toolchain/sysroot, wrong SDK platform, unsupported architecture or
out-of-range deployment target is rejected. SDKSettings.json must explicitly
report the matching platform and supported target. The driver is then probed
with the actual target/sysroot arguments; OS, environment, architecture, pointer
size and deployment version must match before compiling objects.

```sh
nex toolchain ios-device.json --json
nex build examples/ios/main.nex --toolchain ios-device.json \
  --library --entry answer --profile release --json
```

`kind` is `static_library`; `host_compatible` is false for device and simulator,
including an ARM64 simulator on an ARM64 Mac. Metadata records the target, probed
LLVM triple/layout, selected SDK settings and archived sources. Warm/revision
builds preserve target isolation and normal integrity checks.

## Embedding and current limits

The archive includes the matching C++ runtime objects. Link it into a host built
with the same target and SDK. Retrieve the actual symbol with `nex context
--symbol answer --json`. The existing native library ABI uses scalar LLVM types
and same-version runtime handles for heap values; it is not a general Swift or
Objective-C interface. An application wrapper must explicitly bridge this ABI,
manage handles, trap/cleanup boundaries, UI and lifecycle. Automatic Swift bindings
and a stable cross-version public mobile ABI remain pending.

Target storage needs explicit target SQLite headers/library; Mac libraries are
not inherited. Native source foreign-library loading and the Tracy profile
configuration are rejected for this target. `run`, `test`, `debug`, `profile` and
application packaging cannot execute/package these target artifacts through the
local Mac path. `nex test` on the host and `--target web` can check source behavior,
but neither validates execution on iOS.

The target regression builds debug/release archives for all three triples, checks
Mach-O architecture/platform/minimum OS in every object, links the NEX entry into
a target dylib, checks cache/source-deleted reuse and rejects mismatched SDKs,
ignored deployment arguments and host execution. These are build/link checks.
Simulator/device installation and execution, signing, `.app`/`.ipa` packaging,
UI adapters, debugging and profiling remain separate required work. An installed
Xcode SDK does not provide an installed simulator runtime.


The separate [mobile WebView adapter](mobile.md) has actual Simulator application
and HTTPS API UI evidence in0.63. It does not link these MLIR archives into its
JavaScript/React UI path, provide native plugin bindings or establish execution
of a NEX archive on a physical iPhone. Keep these validation scopes separate.
