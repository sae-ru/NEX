# Windows GNU/UCRT core target

The current [Windows-hosted compiler guide](windows-host.md) describes the local
x64 `nex.exe`, its native dependency chain and direct Windows `.exe` workflow.
No WSL process is used by that path. Portable SDK delivery remains pending.

The Windows development adapter now enables synchronous whole-file/stream IO
and ordinary task/fs operations through the handle-relative Windows runtime.
The current language remains0.28 and current task ABI7; retained0.25/ABI6 keeps
its historical identity. Native x64 Windows/NTFS checks, WSL-producer/native
execution recipes and remaining SDK/CUDA boundaries are recorded in
[Windows acceptance](windows-native-acceptance.md).

Development0.162 also executes ordered `parallel_map`, source/static/shared
providers, task debugging/profiling and HTTP hosting on Windows x86-64 GNU/UCRT.
The [CPU execution record](evidence/windows-cpu-development-2026-11-04.json)
contains native/reference/TypeScript agreement, four physical worker threads,
profile cleanup and a live worker breakpoint/watch after source deletion.
Its accompanying platform audit binds the existing file/provider/HTTP paths to
selected Windows regression groups. These scoped receipts do not establish
complete SDK delivery, Windows ARM64 execution or positive IPv6 acceptance on
a host whose operator deliberately denies IPv6. Host networking is unchanged.

## Retained0.136.1 target notes

Toolchain0.136.1 adds ordinary compiled structured CPU tasks for both configured
GNU/UCRT64 targets, using the existing source language0.25 and task descriptor
ABI6. Scopes, futures, rendezvous/buffered channels, immutable captures, nested
tasks and source exception transport use the common runtime. Compiled step,
deadline and worker ceilings still apply; `--nex-task-*` can only lower them.
This platform adapter adds no syntax or language migration.

At that stage, Windows task foreign operations, source provider images, task
debugging/profiling and HTTP hosting were unavailable. Cross-target foreign-ABI
run/test/debug/profile commands returned `E_TARGET_RUN`; the compiler did not
launch Wine. Cross-builds, opt-in x64 Wine compatibility and execution on an
actual Windows OS are distinct evidence. The historical0.136.1 scope below
does not replace the current x64 receipt; actual ARM64 Windows execution
remains unverified.

```nex
module windows_tasks;
fn main()->unit !{io,task,throw}{
 let answer:i64=with_tasks(2,fn(scope:task_scope)->i64 !{task,throw}{
  let child:task<i64>=task_spawn(scope,fn()->i64 !{task}{task_yield();return 42;});
  return task_wait(child);
 });
 print(answer);
}
```

Query `structured_tasks_runtime.windows_cpu_tasks` for the actual compiler's
contract. The current `file_tasks`, `foreign_tasks` and combined
`file_or_foreign_tasks` fields are true. Current native Windows integration also
reports source provider images, task debugging and task profiling as enabled;
actual Windows OS execution is verified for x86-64. These current fields are
separate from the retained0.136.1 scope above. The configured `windows_targets`
suite cross-builds debug/release for
x64 and ARM64, checks current ABI7/PE imports and rebuilds from archived source after
the original is deleted. Set `NEX_WINDOWS_WINE_IMAGE` to a prepared local amd64
image exposing `/usr/lib/wine/wine64` to opt into actual x64 Wine compatibility
checks. Those checks execute normal/nested/channel/error paths, original rethrow
sites, Unicode/NUL payloads and fatal trap/step-limit boundaries in isolated
containers with external networking disabled.

Toolchain0.64 adds explicit cross-builds for `x86_64-w64-windows-gnu` and
`aarch64-w64-windows-gnu`. Debug/release executables are PE/COFF `app.exe`;
`--library --entry NAME` produces a GNU `libnex.a` archive. This adds no source
syntax or language0.16 migration. That initial core scope did not validate
Windows OS execution or a Windows-hosted compiler.

The0.65 candidate adds standalone environment reads and per-principal SQLite
storage. Their NEX realms/effects and explicit capability requirements are
unchanged. Native Windows execution was pending in that scope; record cross-build and
Wine compatibility results separately. Filesystem/resource operations were
rejected in that0.65 scope. The current [Windows filesystem adapter](windows-files-design.md)
has separate native validation and enables standalone/task file operations.

Supply an installed LLVM-MinGW UCRT toolchain and its matching target sysroot.
The maintained build uses LLVM22.1. Do not point these paths at host SDK tools
or libraries. All paths can be relative to the toolchain configuration file:

```json
{
  "schema": "nex.toolchain/1",
  "target": "x86_64-w64-windows-gnu",
  "compiler": "/tools/llvm-mingw/bin/clang++",
  "linker": "/tools/llvm-mingw/bin/ld.lld",
  "archiver": "/tools/llvm-mingw/bin/llvm-ar",
  "sysroot": "/tools/llvm-mingw/x86_64-w64-mingw32",
  "windows": {
    "runtime": "ucrt-static",
    "notices": "windows-runtime-notices.txt"
  }
}
```

The notices file must contain the applicable LLVM/libc++/libc++abi/libunwind,
compiler runtime and MinGW runtime terms from the selected installation, including
required component attributions. NEX copies the supplied text, bounded to1MiB,
into the build notices and captured runtime projection. It does not determine
whether an operator's notices are complete. The GNU driver links C++ support
statically; UCRT and Windows system DLLs remain platform dependencies. The
output is not a freestanding executable or a signed installer.

```sh
nex toolchain windows-toolchain.json --json
nex build examples/windows/main.nex --toolchain windows-toolchain.json --profile release --json
nex build examples/windows/main.nex --toolchain windows-toolchain.json --library --entry answer --json
```

For ARM64 select the `aarch64` target and matching sysroot. NEX passes the
explicit target to the installed Clang++ driver. NEX probes the
driver's actual LLVM triple, data layout and64-bit pointers and checks selected
MinGW/UCRT preprocessor definitions before code generation. It never overrides
an already-emitted host IR target. Build/cache identities include the configured
driver arguments, linker/archiver bytes, target/layout, notices and selected CRT,
libc++/ABI/unwind libraries and MinGW headers. Toolchain snapshots list the exact
captured files. Other SDK headers, compiler support files and environment remain
external inputs; this fingerprint is not a complete hermetic SDK inventory.

The initial target accepts the checked core language, immutable aggregates,
traits/generics, function values, finite numbers, Unicode and binary values,
strict JSON and `print`. Current application stdout preserves UTF-8 bytes and
explicit CR/LF/NUL values, with LF appended by `print`, matching the interpreter.
The historical adapter used CRT Windows line endings. Console rendering depends
on the receiving host.
In the0.64 baseline, reachable database, filesystem/resource operations,
environment reads, external modules, HTTP servers and profile builds fail
explicitly. The0.65 candidate adds only the environment/SQLite facilities
described below; filesystem/resource operations and external modules still fail.
Other unused source declarations do not require a target adapter. Native GUI/plugin
bindings, MSVC ABI,32-bit/ARM64EC, Windows debugger/profiler, application packaging
and SDK distribution remain pending.

In the0.65 candidate, `read_env` uses strict UTF-8/UTF-16 conversion and Windows
wide-character environment access. Empty values remain successful empty strings;
missing variables return `NOT_FOUND`, and malformed Unicode returns `E_UTF8`.
Windows variable names are case-insensitive. The existing256-byte name bound,
server realm and `io` effect still apply. Environment contents remain process
configuration and are not frozen by the compiler.

For reachable `store_*` calls, add a matching target SQLite header/static library
pair to the configuration above:

```json
"sqlite": {
  "include": "/tools/sqlite/sqlite-amalgamation-3540100",
  "library": "/tools/sqlite/x86_64/libsqlite3.a"
}
```

The current native-machine receipt uses SQLite3.54.1 with
`SQLITE_THREADSAFE=1`, built for the same GNU/UCRT target. It is an
external prerequisite. For ARM64, supply the separately compiled ARM64 archive.
The compiler captures the configured `sqlite3.h` and library bytes in build and
toolchain identities. It cannot substitute host libraries for an unconfigured
foreign dependency. Storage requires server realm/`db` and explicit execution
environment `NEX_DATABASE`; the optional `NEX_STORAGE_OWNER` selects the principal
and defaults to `local`, matching the existing standalone adapter. Both accept
Unicode; an explicitly empty/invalid principal is rejected. No default database
path is granted. Keys/values, transactions and
principal isolation use the existing runtime contract. See
`examples/windows/storage.nex`. HTTP hosting was unavailable in the retained0.65
scope; current Windows development hosting is described above.

When cross-compiling from a non-Windows host, local `run`, `test`, `debug` and
`profile` reject this foreign ABI with
`E_TARGET_RUN`; NEX starts no emulator. Cross-build success establishes code
generation/linkage. PE inspection, Wine compatibility and actual Windows/device
execution are distinct checks. Keep their results separate in evidence.

The optional real-target regression group uses a preinstalled SDK:

```sh
NEX_WINDOWS_TOOLCHAIN_ROOT=/tools/llvm-mingw ctest --test-dir build -R windows_targets --output-on-failure
```

It builds both architectures/profiles, inspects COFF objects and executable
imports, links a C++ host against the archive, verifies cache/source replay and
checks rejection boundaries. Without this environment variable, real cross-build
cases are reported skipped and the unconfigured-target checks still run. No
toolchain is downloaded or target executable launched by that regression group.

`windows_runtime` additionally checks environment PE builds and, with
`NEX_WINDOWS_SQLITE_ROOT`, matching storage PE/archive linkage and archived-source
replay. The SQLite root contains `sqlite-amalgamation-3540100/sqlite3.h`,
`x86_64/libsqlite3.a` and `aarch64/libsqlite3.a`. These are cross-build checks;
they do not launch target code or certify actual Windows execution.
