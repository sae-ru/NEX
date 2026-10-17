# Third-party components in the current implementation

| Component | Current use | License/source |
|---|---|---|
| LLVM / MLIR 22.1.8 | Linked compiler infrastructure and native toolchain | [Apache-2.0 with LLVM exceptions](https://llvm.org/docs/DeveloperPolicy.html#copyright-license-and-patents) |
| BLAKE3 through LLVM Support | Content hashing via `llvm/Support/BLAKE3.h` | Uses the implementation already distributed with LLVM; [upstream licensing](https://github.com/BLAKE3-team/BLAKE3#licenses) |
| SQLite 3.53.1 | Linked project/revision database and optional native per-principal KV storage | [SQLite public-domain dedication](https://sqlite.org/copyright.html) |
| nlohmann/json 3.12.0 | Strict typed wire JSON in the compiler/interpreter and selected native runtime components | MIT; vendored `runtime/third_party/json.hpp` and `JSON-LICENSE.MIT` |
| cpp-httplib 0.61.0 | Native HTTP/HTTPS host with bounded worker/queue settings | MIT; vendored `runtime/third_party/httplib.h` and `HTTPLIB-LICENSE` |
| OpenSSL 3.6.3 | TLS and bearer digest comparison in native HTTP servers | Installed OpenSSL 3 library; [Apache-2.0](https://github.com/openssl/openssl/blob/master/LICENSE.txt) |
| Tracy 0.14.1 client | Optional instrumentation in native profile output | BSD-3-Clause with embedded LZ4/concurrentqueue/SPSCQueue/rpmalloc notices; pinned source inventory in `runtime/third_party/tracy/manifest.json` |
| Z3 5.3.1 | Linked scalar verifier in the development compiler; absent from generated applications | MIT; external official release, notice copied to `docs/licenses/Z3-LICENSE.txt`; configuration/provenance in `docs/verification.md` |
| Apple LLDB | Optional local debugger used for integration checks | Installed tool; [LLVM licensing and LLDB documentation](https://lldb.llvm.org/) |
| Python 3.9.6 | Integration-test runner | Installed interpreter; no Python runtime in generated programs |
| React / React DOM 19.3.1; Scheduler 0.28.0 | Runtime of generated browser applications | MIT; copies of package license text are included in `web/THIRD_PARTY_NOTICES.txt` and generated `dist` |
| TypeScript 7.0.2 | Checks generated browser source | Apache-2.0; npm development dependency |
| Vite 8.3.4 | Browser dev/preview server and bundler | MIT; npm development dependency |
| Playwright 1.64.1 | Browser acceptance tests | Apache-2.0; npm development dependency and separately installed browser engines |

LLVM/MLIR, SQLite and OpenSSL are found from installed development packages. The two single-header libraries above are copied unmodified into `runtime/third_party`; `manifest.json` records exact versions, source URLs, SHA256 header hashes and license filenames. Tests verify the pinned header bytes. Compiler installation copies NEX's executable and resource files, including these headers/licenses, but does not bundle the external shared libraries or platform SDK. Their configured locations remain prerequisites.

Native builds select runtime components from reachable code. Pure executables do not link SQLite/OpenSSL or embed the JSON/HTTP headers. Storage output needs SQLite; HTTP/HTTPS output also needs OpenSSL. Builds embedding nlohmann/json and/or cpp-httplib emit their full matching license texts in `THIRD_PARTY_NOTICES.txt`; an explicit `-o PATH` copies the file to `PATH.THIRD_PARTY_NOTICES.txt`. Retain that companion file when distributing the output. Native build metadata records the runtime input projection and selected components. Packaging external libraries, toolchain dependencies and their complete notices into a portable SDK remains separate work.

`web/package-lock.json` records the complete browser dependency tree, exact package versions, registry integrity hashes and license metadata, including platform-specific optional build tools. `npm ci --ignore-scripts` installs those packages into generated development projects; the C++ compiler does not link them. Browser assets bundle the required React runtime and include `THIRD_PARTY_NOTICES.txt`. Development package licenses remain in their installed package directories. Node.js 22.22.3/npm 10.9.8 were used for verification; redistributing those tools is not part of current SDK installation.

Emscripten, SDL3 and wgpu remain planned integrations and are not presently included dependencies. Their exact versions, dependency trees and distribution notices will be recorded when integrated.

Native profile builds additionally embed the unmodified Tracy 0.14.1 client and preserve its complete source/header tree and SHA256 inventory. `TRACY-NOTICES.txt` includes its BSD license and embedded dependency notices, and is appended to distributed profile output notices. Tracy is dormant until `NEX_TRACY=1`; local JSON profiling does not start it. Capture/viewer/export tools are separate upstream programs. The development compiler does not link the client.

The verified Z3 ARM64 macOS 5.3.1 release was obtained from https://github.com/Z3Prover/z3/releases/tag/z3-5.3.1, archive `z3-5.3.1-arm64-osx-13.3.zip`, SHA256 `0de02438052952153aab5d1361be4d61b6d226337440356c054d403c959da86b`. Z3 headers/shared library are external development/SDK prerequisites; only its notice and verification protocol are saved here. The configured Z3 shared-library directory is retained in this local SDK's runtime search path. Redistributing a portable solver/toolchain bundle remains separate work.
