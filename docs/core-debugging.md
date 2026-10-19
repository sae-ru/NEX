# Native core reports and capsules (development 0.59)

This development command reads a native core with its matching retained build:
`nex core PROCESS.core --manifest BUILD/debug.json --json`.
An optional `--expression TEXT` uses the existing pure, bounded watch evaluator.
It does not run, attach to or resume an application. This draft is implemented
in an isolated source tree. The preceding0.58.2 retained-build pipeline has
separate platform evidence. Current capsule C++/live/full/SDK validation is pending.

The report records core bytes/SHA-256, executable bytes/hash, actual module UUID,
stop reason, bounded thread/stack summaries and the selected NEX frame. A frame
must belong to the executable's loaded module before receiving a graph revision,
operation candidates or typed values. Function names alone are insufficient.
For Linux cores, the recorded PC mapping must name the retained executable and
its loaded image must be unambiguous. Missing mapping evidence is rejected. ELF64 uses the core's own NT_FILE note;
LLDB does not expose its filenames through SBMemoryRegionInfo on the exercised
Linux host. The parser bounds note bytes, entries, reads and elapsed time.
The retained directory must be named by its64-digit build key. Keep this
content-addressed directory intact; arbitrary directory renaming is rejected.
LLDB can resolve a core PC through another supplied executable; checking
SBModule equality alone does not establish the recorded image.

The matching compiler build, language/runtime protocols, source bundle/revision,
trusted installed formatter and retained native build completion are checked before
LLDB starts. Core memory remains untrusted process data. Hashes detect changes
relative to these retained artifacts; they do not authenticate their publisher.
The report keeps source-line/column candidates explicit. It does not claim a
unique optimized operation when the available debug information is ambiguous.

Core files are64-bit ELF, Mach-O or LLDB minidump regular, non-symlink files of at most32GiB and are hashed in
bounded chunks. Debug manifests are at most8MiB; source bundles at most16MiB.
Reports list at most64 threads and64 frames of the selected thread. The optional
thread/frame selection uses zero-based indices. Out-of-range selections fail.
An unavailable local is represented explicitly; a failed requested watch makes
the report unsuccessful. Reading a core must preserve stop identity and bytes.
`--thread INDEX` selects a thread; `--frame INDEX` selects its frame. Without
these options, the reader uses the core's selected thread and its first mapped
NEX frame. `--timeout SECONDS` bounds the LLDB child (default60, maximum300).
File-size-bounded hashing and retained-build checks happen before/after it.
Minidumps require the standard signature/version, a bounded in-file stream
directory and a single64-bit x86-64/ARM64 system-information stream.
A captured SIGABRT test restores caller-frame values after source deletion;
the exercised Mach-O core itself retains no signal cause. Stop metadata is
reported as available, without inferring a cause absent from the core.
Successful reports follow [the schema](../llm/core-report.schema.json). Rejections
use the normal `nex.diagnostic/1` protocol and a nonzero process exit status.

The ordinary `--manifest` command requires its retained build workspace.
Use the following explicit workflow to keep the core with its build inputs:

```sh
nex core process.core --manifest BUILD/debug.json --export NEW_DIRECTORY --json
nex core --capsule MOVED_DIRECTORY --expression 'text + str(items[1])' --json
```

Export requires an absent destination under an existing parent. It first checks
the original core/build, copies the executable, symbols, source projections and
unchanged completion/build/IR records, then reads the new capsule before an
exclusive publication. Existing destinations are preserved. An interrupted or
failed export cannot publish a partial capsule.

`capsule.json` follows `nex.core-capsule/1`; successful export returns
`nex.core-capsule-export/1`. Both are described by
[the capsule schema](../llm/core-capsule.schema.json). Read reports use the
ordinary core-report schema with an additional checked `capsule` binding.
The inventory records every file's bytes and SHA256, compiler/language/runtime
identities, original executable path, resolved historical image path, build key
and host. The recorded mapping survives removal or retargeting of an original
directory alias. Missing/extra files,
symlinks, special files, duplicate JSON fields, escaping paths and mismatching
identities are rejected. Limits are4096 files/directories,32 path components,
4096 UTF-8 bytes per relative path,512MiB per build file,32GiB per core and33GiB
total file bytes. Copy/hash work has a900-second deadline; native dependency
inspection has a30-second deadline and1MiB output limit. These are separate
from the selected LLDB timeout. Source/debug metadata keeps the limits above.

The capsule may move and its original source/executable paths may disappear.
Read-only verification copies the build inputs into a private temporary
workspace. The content-addressed directory name and original build key remain
unchanged. Linux keeps checking the original core-recorded PC mapping; the
loaded module/UUID must identify the copied executable. Mach-O retains its
loaded-module/UUID check. Reports identify the actual inspection workspace,
which is removed afterward. Core bytes and the capsule remain unchanged.

The matching installed SDK supplies the compiler, formatter, Python helper and
LLDB reader. Paths naming scripts or compilers inside capsule data never select
executable tooling. Hashes establish agreement with the receipt, not publisher
authentication. The current slice requires a matching macOS/Linux ARM64 or
x86-64 host, debugger and system runtime. It rejects source foreign declarations
and non-system native dependencies; this excludes current TLS/SQLite application
packages. `otool` on macOS or `readelf` on Linux reads dependency headers without
launching the application. Cross-OS/architecture/runtime relocation and native
dependency packaging remain pending. Exact optimized operation attribution
retains explicit candidates.

Validation must include actual macOS/Linux cores, source deletion, Unicode/list
exact watches, unchanged stops and bytes, malformed/oversized inputs, wrong
images, changed executable/symbol/source artifacts, range limits, and use from
an installed SDK. The command must leave graph storage and HEAD untouched.

References: [LLDB core commands](https://lldb.llvm.org/use/map.html),
[LoadCore](https://lldb.llvm.org/python_api/lldb.SBTarget.html#lldb.SBTarget.LoadCore),
[SaveCoreOptions](https://lldb.llvm.org/python_api/lldb.SBSaveCoreOptions.html).
