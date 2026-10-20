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
| Apple LLDB (macOS); LLVM LLDB 22.1.8 (Linux) | Optional local debugger used for integration checks | Installed tool; [LLVM licensing and LLDB documentation](https://lldb.llvm.org/) |
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
