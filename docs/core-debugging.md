# Native core reports and capsules

This development command reads a native core with its matching retained build:
`nex core PROCESS.core --manifest BUILD/debug.json --json`.
An optional `--expression TEXT` uses the existing pure, bounded watch evaluator.
It does not run, attach to or resume an application. Development0.162 has
[scoped Windows minidump evidence](evidence/windows-minidump-capsules-development-2026-11-04.json)
for relocated capsules, including captured project DLLs, closure watches,
wrong UUID rejection and source/image-deleted reads. Full installed-SDK and
platform receipts retain their own compiler, helper and archive identities;
these focused checks do not replace the remaining delivery gates.

The report records core bytes/SHA-256, executable bytes/hash, actual module UUID,
stop reason, bounded thread/stack summaries and the selected NEX frame. A frame
must belong to the executable or a captured owned native image before receiving a graph revision,
operation candidates or typed values. Function names alone are insufficient.
For Linux cores, the recorded PC mapping must name the retained executable and
its loaded image must be unambiguous. Missing mapping evidence is rejected. ELF64 uses the core's own NT_FILE note;
LLDB does not expose its filenames through SBMemoryRegionInfo on the exercised
Linux host. The parser bounds note bytes, entries, reads and elapsed time.
The retained directory must be named by its64-digit build key. Keep this
content-addressed directory intact; arbitrary directory renaming is rejected.
LLDB can resolve a core PC through another supplied executable; checking
SBModule equality alone does not establish the recorded image.

For minidumps, the reader obtains the original name, load base and CodeView
UUID directly from the dump's module-list stream. An LLDB memory-region name
can describe the relocated image instead of the recorded one. The reader binds
the authenticated frame module's base and UUID; it does not treat LLDB's saved
PE header extent as the whole executable range. LLVM build IDs and PDB70
GUID/age records are checked, with bounded stream/module counts, reads, UTF-16
names and elapsed time. Missing or ambiguous identities fail the read.

The matching compiler build, language/runtime protocols, source bundle/revision,
trusted installed formatter and retained native build completion are checked before
LLDB starts. Core memory remains untrusted process data. Hashes detect changes
relative to these retained artifacts; they do not authenticate their publisher.
Keep the matching SDK/resources with older retained builds: a newly changed
formatter does not become trusted merely because its compiler binary is unchanged.
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

Toolchain0.134.5 creates the private staging directory beside the destination,
including literal percent signs and Unicode in its parent path. Publication
therefore stays on that filesystem when a project lives on a container bind
mount or another volume. The exclusive rename remains mandatory; unsupported
atomic publication fails with its operating-system error rather than replacing
an existing destination or copying a partial capsule into place.

`capsule.json` follows `nex.core-capsule/1`; successful export returns
`nex.core-capsule-export/1`. Both are described by
[the capsule schema](../llm/core-capsule.schema.json). Read reports use the
ordinary core-report schema with an additional checked `capsule` binding.
The inventory records every file's bytes and SHA256, compiler/language/runtime
identities, original executable path, resolved historical image path, build key
and host. The recorded mapping survives removal or retargeting of an original
directory alias. Shared-image records may retain the physical build root while
`program` names the validated alias. Export checks that both resolve to the same
captured image paths; later reads use the recorded paths without consulting the
removed or retargeted alias. Image order and completion identities remain checked.
Missing/extra files,
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
and external non-system native dependencies; this excludes current TLS/SQLite application
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

The0.72 candidate extends retained native completion with an ordered ABI/archive
input list (`nex.native-completion/2`). The reader hashes those additional files
and capsule export/import preserves their exact bytes. Legacy records without
these fields keep the earlier six-file contract. This adds no source syntax or
language migration and does not establish project-artifact DAP integration.

## Captured project images (candidate0.75)

Completion/3 capsules retain the final application's `images/` closure and every
captured native symbol file. Before LLDB starts, C++ checks BLAKE3/SHA-256, native
UUID/build ID, typed relative inventory and debug/input agreement, then rechecks
image/symbol hashes after reading. Live selected frames also require a matching
image path, SHA-256 and UUID; ambiguous loaded modules reject. Function/source
names do not substitute for image identity.

Shared receipts keep `nex.core-capsule/1`, adding dependency scope
`captured_first_party_and_matching_host_system` and a bounded `recorded_images`
map. Keys name inventoried relative images; values preserve historical physical
paths recorded by the core. Verified staging projects image/symbol paths into a
fresh temporary directory while retaining original build/completion inputs.
Current loader paths do not replace recorded PC evidence. Private relocation
fields are supplied by the checked reader, never by serialized debug metadata.
Legacy system-only capsules preserve their previous receipt shape and checks.

Load the final application's `debug.json` for a manual LLDB library session; use
its frozen provider-source projection for breakpoints. Keep all images/symbols.
Shared deployment packages and combined project DAP/editor sessions remain
pending. External non-system dependencies keep the restrictions above.
