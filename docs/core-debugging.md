# Native core reports (development 0.58.1)

This development command reads a native core with its matching retained build:
`nex core PROCESS.core --manifest BUILD/debug.json --json`.
An optional `--expression TEXT` uses the existing pure, bounded watch evaluator.
It does not run, attach to or resume an application. This draft is implemented
in an isolated source tree. macOS focused/live checks pass; wider validation is pending.

The report records core bytes/SHA-256, executable bytes/hash, actual module UUID,
stop reason, bounded thread/stack summaries and the selected NEX frame. A frame
must belong to the executable's loaded module before receiving a graph revision,
operation candidates or typed values. Function names alone are insufficient.
For Linux cores, the recorded PC mapping must name the retained executable and
its loaded image must be unambiguous. Missing mapping evidence is rejected.
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

This first command requires the retained build workspace. It does not package
or relocate native dependencies and does not make a core portable between OS
versions, CPU architectures or runtime layouts. LLDB raw-core probes have shown
matching image relocation with copied symbols/sources, but a reviewed portable
core capsule is a subsequent integration. Original failure reports and the
wrong-image negative control are retained separately.

Validation must include actual macOS/Linux cores, source deletion, Unicode/list
exact watches, unchanged stops and bytes, malformed/oversized inputs, wrong
images, changed executable/symbol/source artifacts, range limits, and use from
an installed SDK. The command must leave graph storage and HEAD untouched.

References: [LLDB core commands](https://lldb.llvm.org/use/map.html),
[LoadCore](https://lldb.llvm.org/python_api/lldb.SBTarget.html#lldb.SBTarget.LoadCore),
[SaveCoreOptions](https://lldb.llvm.org/python_api/lldb.SBSaveCoreOptions.html).
