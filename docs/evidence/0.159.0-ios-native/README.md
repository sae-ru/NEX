# Native iOS Simulator execution, SDK 0.159

[receipt.json](receipt.json) pins the published SDK archive, actual compiler,
source revision, source/host hashes and measured scope. [main.nex](main.nex) and
[host.cpp](host.cpp) are the exact successful inputs. Raw logs and the earlier
generator/host failures remain retained locally; their hashes and reasons are
recorded explicitly rather than presented as public downloadable artifacts.

Two real ARM64 IOSSIMULATOR processes, Debug and Release, ran against the
installed iOS27.1 runtime using CoreSimulator's `spawn --standalone` mode on a
temporary, unbooted simulator. Each ran seven cases 100 times: normal0/41,
recovered owned typed error, failed precondition, failed postcondition, escaped
owned typed error and checked overflow. In total 1400 native calls and 1400
post-scope runtime cleanup checks passed. The owned simulator was deleted.

The escaped payload preserved `Я`, a NUL and `🧠`. The source also checks finally
ordering: fatal overflow skips the user finalizer; the escaped error skips the
postcondition. Reference executions agreed with the seven outcomes. Mach-O
checks selected ARM64/IOSSIMULATOR/minimum iOS17.0; linked dependencies were
system C++/libSystem, with no LLVM or Z3 runtime dependency.

The physical entry source file was renamed away while target processes ran;
`NEX_RESOURCE_DIR` selected an absent path. This was **not** a kernel denial of
every SDK/source path. An archived-revision rebuild with the entry absent reused
the same build key and compiled zero functions.

## Reproducing the scoped probe

Use the exact 0.159 SDK identified by the receipt, a matching Clang22.1 and an
installed iOS Simulator runtime. Discover paths with `nex doctor --json` and
`xcrun --sdk iphonesimulator --show-sdk-path`. In a new scratch project, copy the
two inputs here and create `nex.json` with language 0.28 and entry `main.nex`.
Write an explicit `nex.toolchain/1` selecting target
`arm64-apple-ios17.0-simulator`, the actual compiler and simulator sysroot.

```sh
nex build main.nex --library --entry step --profile debug \
  --toolchain ios-simulator.json --json
```

Retain the JSON result and inspect its actual LLVM signature. For this exact
source it is `i64 @nex_13_ios_native159_4_step(i64, ptr)`. The second argument is
mandatory; `host.cpp` initializes its error slot, transports source errors through
the matching runtime and encloses calls in `RequestScope`.

Compile `host.cpp` with that same target/sysroot and C++20, include the matching
SDK's `runtime` directory, link the returned static archive, then ad-hoc sign the
target executable with `codesign`. Check `xcrun vtool -show-build`,
`xcrun lipo -archs` and `xcrun otool -L` before execution.

Select an installed runtime/device type with `xcrun simctl list`, create a new
temporary simulator for this probe, and use its returned UDID:

```sh
SIMCTL_CHILD_NEX_RESOURCE_DIR=/unavailable-nex-resources \
  xcrun simctl spawn --standalone --arch=arm64 OWNED_UDID /absolute/path/to/host
```

The JSON output must report the exact target runtime,700 calls,700 cleanup
checks and the seven expected outcomes. Repeat for Release. To repeat the
source-absent check, rename only this scratch project's `main.nex`, run the target
process and archived-revision build, then restore it. Delete only the simulator
created for the probe. `--standalone` uses a NULL Mach bootstrap and does not
exercise a booted application lifecycle.

UIKit/lifecycle/input handling, a physical iPhone, a stable C/Swift/JNI interface,
application signing/distribution, `.ipa` delivery and general mobile acceptance
remain pending. SDK 0.160's new [entry ABI discovery](../../native-entry-abi.md)
is separate source-development work; this receipt qualifies only the exact 0.159
inputs above.
