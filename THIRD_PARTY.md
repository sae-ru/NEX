# NEX project license

NEX-authored code and documentation are licensed under the [MIT License](LICENSE).
The components listed below retain their original licenses, copyright notices
and redistribution conditions. The project license does not replace those terms.

An ordinary CMake prefix and a portable SDK have different contents. The
[delivery record](docs/releases/0.151.1.json) identifies the accepted development
bundle; its inventory and license directory describe the redistributed files.
Version-specific historical notes below retain their original scope.

# Owned OpenCL preparation

The experimental owned-device preparation installs the existing unmodified
Khronos OpenCL headers and OPENCL-LICENSE from experiments/cix-p1/include.
Prepared bundles retain that notice and the MIT notice for the installed
nlohmann/json header compiled into their provider. The OpenCL vendor loader
and driver remain operator-selected external platform dependencies.

# Third-party components in the current implementation

| Component | Current use | License/source |
|---|---|---|
| LLVM / MLIR 22.1.8 | Linked compiler infrastructure and native toolchain | [Apache-2.0 with LLVM exceptions](https://llvm.org/docs/DeveloperPolicy.html#copyright-license-and-patents) |
| LLVM compiler-rt 22.1.8 `__multi3` | Freestanding legalizer helper linked into scalar Wasm modules | Apache-2.0 WITH LLVM-exception; unmodified source, required headers, full license and SHA-256 provenance in `runtime/third_party/compiler-rt` |
| BLAKE3 through LLVM Support | Content hashing via `llvm/Support/BLAKE3.h` | Uses the implementation already distributed with LLVM; [upstream licensing](https://github.com/BLAKE3-team/BLAKE3#licenses) |
| SQLite 3.53.1 (macOS); 3.45.1 Ubuntu package (Linux) | Linked project/revision database and optional native per-principal KV storage | [SQLite public-domain dedication](https://sqlite.org/copyright.html) |
| nlohmann/json 3.12.0 | Strict typed wire JSON in the compiler/interpreter and selected native runtime components | MIT; vendored `runtime/third_party/json.hpp` and `JSON-LICENSE.MIT` |
| Dragonbox 1.1.3 | Portable shortest binary64 decimal conversion for the numeric runtime under development | Boost Software License 1.0 selected from the upstream dual license; unmodified header, both licenses and hash inventory in `runtime/third_party/dragonbox` |
| cpp-httplib 0.61.0 | Native HTTP/HTTPS host with bounded worker/queue settings | MIT; vendored `runtime/third_party/httplib.h` and `HTTPLIB-LICENSE` |
| OpenSSL 3.6.3 (macOS); 3.0.13 Ubuntu package (Linux) | TLS and bearer digest comparison in native HTTP servers | Installed OpenSSL 3 library; [Apache-2.0](https://github.com/openssl/openssl/blob/master/LICENSE.txt) |
| Tracy 0.14.1 client | Optional instrumentation in native profile output | BSD-3-Clause with embedded LZ4/concurrentqueue/SPSCQueue/rpmalloc notices; pinned source inventory in `runtime/third_party/tracy/manifest.json` |
| Z3 5.3.1 | Linked scalar verifier in the development compiler; absent from generated applications | MIT; external official release, notice copied to `docs/licenses/Z3-LICENSE.txt`; configuration/provenance in `docs/verification.md` |
| Apple LLDB (macOS); LLVM LLDB 23.1.5 APT snapshot (Linux) | Optional debugger, independently pinned from the LLVM/MLIR22.1.8 compiler | Installed tool; [LLVM licensing and LLDB documentation](https://lldb.llvm.org/); exact Linux package inputs in `tools/linux/debugger-packages.json`. The optional Linux `Debugger.Dockerfile` builds a locally patched `lldb-dap` under Apache-2.0 WITH LLVM-exception; source and patch hashes are in `tools/linux/lldb23-indexed-pages.json` and `tools/linux/lldb23-za-registers.json`. The matching cohort includes the ARM64 optional-register inventory repair. |
| Python 3.9.6 (macOS); 3.12.3 (Linux) | Integration-test runner | Installed interpreter; no Python runtime in generated programs |
| React / React DOM 19.3.1; Scheduler 0.28.0 | Runtime of generated browser applications | MIT; copies of package license text are included in `web/THIRD_PARTY_NOTICES.txt` and generated `dist` |
| TypeScript 7.0.2 | Checks generated browser source | Apache-2.0; npm development dependency |
| Vite 8.3.4 | Browser dev/preview server and bundler | MIT; npm development dependency |
| Playwright 1.64.1 | Browser acceptance tests | Apache-2.0; npm development dependency and separately installed browser engines |

LLVM/MLIR, SQLite and OpenSSL are found from installed development packages. The JSON/HTTP single-header libraries above are copied unmodified into `runtime/third_party`; `manifest.json` records exact versions, source URLs, SHA256 header hashes and license filenames. Tests verify the pinned header bytes. Compiler installation copies NEX's executable and resource files, including these headers/licenses, but does not bundle the external shared libraries or platform SDK. Their configured locations remain prerequisites.

Native builds select runtime components from reachable code. Pure executables do not link SQLite/OpenSSL or embed the JSON/HTTP headers. Storage output needs SQLite; HTTP/HTTPS output also needs OpenSSL. Builds embedding nlohmann/json and/or cpp-httplib emit their full matching license texts in `THIRD_PARTY_NOTICES.txt`; an explicit `-o PATH` copies the file to `PATH.THIRD_PARTY_NOTICES.txt`. Retain that companion file when distributing the output. Native build metadata records the runtime input projection and selected components. Development 0.27 adds an opt-in macOS bundle assembler. It copies tools, headers and transitive non-system libraries, requires explicit component roots and full local license texts, records original/packaged hashes and retains notices in `share/nex/licenses/sdk`. Copied Mach-O load commands/signatures change; original installations remain unchanged. Relocation acceptance and broader delivery are recorded separately in `STATUS.md` and [the SDK guide](docs/sdk.md).

`web/package-lock.json` records the complete browser dependency tree, exact package versions, registry integrity hashes and license metadata, including platform-specific optional build tools. `npm ci --ignore-scripts` installs those packages into generated development projects; the C++ compiler does not link them. Browser assets bundle the required React runtime and include `THIRD_PARTY_NOTICES.txt`. Development package licenses remain in their installed package directories. Node.js 22.22.3/npm 10.9.8 were used for verification; redistributing those tools is not part of current SDK installation.

Emscripten, SDL3 and wgpu remain planned integrations and are not presently included dependencies. Their exact versions, dependency trees and distribution notices will be recorded when integrated.

Native profile builds additionally embed the unmodified Tracy 0.14.1 client and preserve its complete source/header tree and SHA256 inventory. `TRACY-NOTICES.txt` includes its BSD license and embedded dependency notices, and is appended to distributed profile output notices. Tracy is dormant until `NEX_TRACY=1`; local JSON profiling does not start it. Capture/viewer/export tools are separate upstream programs. The development compiler does not link the client.

The verified Z3 ARM64 macOS 5.3.1 release was obtained from https://github.com/Z3Prover/z3/releases/tag/z3-5.3.1, archive `z3-5.3.1-arm64-osx-13.3.zip`, SHA256 `0de02438052952153aab5d1361be4d61b6d226337440356c054d403c959da86b`. Z3 headers/shared library are external development/SDK prerequisites; only its notice and verification protocol are saved here. The configured Z3 shared-library directory is retained in this local SDK's runtime search path. Redistributing a portable solver/toolchain bundle remains separate work.

## Linux development environment (0.20)

`tools/linux/Dockerfile` uses the official Ubuntu 24.04 image (pinned manifest digest), official LLVM/MLIR/LLD 22.1.8 Ubuntu packages (pinned package version/key), official Node.js 22.22.3 and Z3 5.3.1 archives (architecture-specific SHA-256 checks). Package copyright notices remain under `/usr/share/doc`; Node/Z3 archive notices are retained with their installed files. These are external development dependencies, not vendored application sources. Existing browser lock/integrity and runtime notices are unchanged. Recipe/URLs are documented in `docs/linux.md`; Ubuntu security-package updates are not an immutable mirror.

## Binary64 runtime foundation (in progress)

Dragonbox 1.1.3 is pinned to commit `3053a74ac81099591a12a55341a203d9688fbb92`. Its single `dragonbox.h` header is copied byte-for-byte from that revision, with no transitive third-party dependency. `runtime/third_party/dragonbox/manifest.json` records upstream paths, byte sizes and SHA-256 hashes for the header and both original licenses. NEX selects the Boost Software License 1.0 option. Native runtime source projections preserve the header, inventory and licenses; native output notices include the selected license. The JavaScript implementation uses the engine’s built-in conversion, and this dependency is absent from browser assets. This foundation does not yet enable `f64` source programs in language 0.10.

## Editor development tooling

The editor/vscode package pins @vscode/vsce4.0.0 and @vscode/test-electron3.1.0
as development-only npm tools. Its separate package-lock.json retains exact
versions, integrity hashes and package license metadata. npm ci --ignore-scripts
installs development tools; the VSIX contains only NEX's own manifest/configuration,
JavaScript and README, with no third-party runtime npm tree. Dependency licenses
remain in development node_modules. The official separate VS Code1.142.0 ARM64
test application (commit b224f6bf5a4fcad5fa4c640ed10f179c3b613e48) stays in a local
build cache and is not redistributed by NEX. Its test profile is separate from
the user's editor profile. Project licensing/Marketplace publication are pending.

## Candidate mobile host (toolchain0.62)

Mobile project generation pins Capacitor core/CLI/iOS/Android8.5.3 in the separate
`mobile/package-lock.json`. It does not change the browser dependency lock.
`mobile/ios-artifacts.json` pins the two official XCFramework zip hashes from
SwiftPM commit4c7f346d16196e21fbe23d4a7a6fc7af62af6742. Framework bytes are fetched
into an explicit development cache and copied locally into generated projects.
MIT license texts for the SwiftPM distribution and npm iOS source, the Apache2
license and Cordova notices are stored under `mobile/`; generated app assets
include these notices. Native project generation grants no plugin capabilities.
Apple/Android SDKs and JDK/Gradle remain external development prerequisites with
their own licenses and are not included in the NEX source or compiler runtime.
Native application plugins and resolved build dependencies require their own
corresponding inventories and notices before distribution.

## Windows core cross-toolchain (toolchain0.64)

The explicit Windows GNU/UCRT target uses an external LLVM-MinGW installation,
including libc++, libc++abi, libunwind, compiler-rt and the MinGW CRT. These
components are not vendored here. Static linking does not remove their notice
requirements. The operator supplies the matching complete runtime notices in
the toolchain configuration; NEX captures and appends them to artifact notices.
UCRT and Windows system DLLs remain platform dependencies. SDK/installer
distribution, signed delivery and actual Windows OS validation remain pending.

The0.65 Windows storage prerequisite separately builds official SQLite3.54.1
amalgamation source for x86-64 and ARM64 GNU/UCRT, with THREADSAFE=1 and loadable
extensions omitted. Archive `sqlite-amalgamation-3540100.zip` has published
SHA3-256 `92281c86e2957f9b9305890f9ac04204caa7b677cc868dc326d942689df28e30`
and verified SHA-256 `0a9c8e34352dad46006aa82836d5383bff9dc6bc9ce5a60553c05aa30e6ad1f9`.
Source: [official SQLite download](https://www.sqlite.org/2026/sqlite-amalgamation-3540100.zip),
with the existing [public-domain dedication](https://sqlite.org/copyright.html).
The source/libraries are external prerequisites, not bundled NEX runtime files.
Host macOS/Linux SQLite versions remain as listed above.


## Optional experimental CIX fixture headers

`experiments/cix-p1/` is an optional source example outside the installed SDK
and default test suite. Its Khronos OpenCL-Headers v2024.10.24 files retain the
Apache-2.0 notices/license in include/CL and include/OPENCL-LICENSE. Microsoft
ONNX Runtime v1.20.0 C API and the embedded Mul fixture are covered by the
MIT notice in include/ONNX-LICENSE. The Arm China Compass ONNX Runtime
rel-1.22.0 Zhouyi factory declaration retains its Apache-2.0 header notice;
the included Apache-2.0 license text accompanies it. The example's preparation
tool includes these and its matching SDK nlohmann/json MIT notice in the bundle.
The CIX/ARM GPU and Zhouyi runtime/driver binaries are external installed
prerequisites; they are not redistributed here. A module pin does not cover
those external files. Driver packaging/redistribution requires its own inventory
and permissions. See experiments/cix-p1/README.md for exact tested boundaries.

## Windows OpenSSL relocation corrections (development0.162.1)

`tools/windows/openssl/` pins OpenSSL3.6.5 and the MSYS2 relocation inputs used
by the isolated Windows development build. OpenSSL remains an external
Apache-2.0 prerequisite. The redistributed `pathtools.c`/`.h` retain Ray
Donnelly's CC0 dedication in their headers; the MSYS2 patches retain their
attribution. NEX's two long-path corrections use MIT. The source lock records
exact hashes and upstream locations. The private build and SDK assembler retain
the OpenSSL license, pathtools notice and correction provenance with the matching
headers, libraries, CLI and providers. See the [recipe](tools/windows/openssl/README.md)
for the measured scope and retained failed upstream attempts.
