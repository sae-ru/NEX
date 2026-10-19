# Proposed NEX core capsule — implementation not yet accepted

The current0.58.2 command reads a core against an intact retained build. The next
step is an explicit export/read workflow for the same OS, architecture and
runtime layout. It must work after the original project and build paths vanish.
It must preserve the core, graph history, original build identity and all existing
wrong-image rejection controls. No application execution is needed to read it.

Proposed commands:

```text
nex core CORE --manifest BUILD/debug.json --export NEW_DIRECTORY --json
nex core --capsule DIRECTORY [--expression TEXT] [--thread N] [--frame N] --json
```

Export performs the ordinary matching retained-build/core inspection first.
The destination must be absent. A private sibling staging directory is renamed
only after all copied bytes have been checked; failure removes only that staging
directory. An existing destination is never replaced. The first version exports
a directory; archive compression/extraction can use the existing reviewed
packaging utilities in a later step. Do not introduce a general tar extractor.

The manifest `nex.core-capsule/1` records compiler/language/runtime protocols,
host OS/architecture, original executable path and build key, core size/SHA256,
original debug-manifest hash and a strict inventory of every bundled file.
Inventory names are relative POSIX paths without empty/dot/dotdot components,
absolute paths, backslashes or NUL. Every entry is a regular non-symlink file;
symlinks, special files, duplicate normalized paths, missing and extra files
are errors. Copies use bounded streaming, stable open descriptors and explicit
per-file/total/count limits. Core files retain the existing32GiB ceiling.

Bundle the original executable, Mach-O dSYM where needed, source-bundle, frozen
source projections, compilation/build/IR/completion records, and the unchanged
original debug manifest. Keep the executable under `build/<build_key>/app`.
Any rewritten runtime debug manifest is a derived temporary projection. Record
which fields can be relocated and require all other values to remain byte/data
equivalent to the checked original. Do not recompute a completion record to
accept a modified executable or build input.

The capsule is data. Never load scripts, compiler binaries, formatters or loader
configuration from it. The current matching installed SDK provides the trusted
formatter, core reader and pure expression evaluator. Host compatibility and
exact compiler build remain mandatory. Hashes detect changes relative to the
receipt; they do not authenticate an untrusted publisher.

Relocation needs two separate identities: the physical copied executable and
the original executable path recorded in the core. Both parent directory names
must equal the retained build key. Linux mapping evidence must continue to come
from minidump recorded regions or the ELF core's own NT_FILE note. A different
recorded path/build key is rejected. The selected SBModule/UUID must identify
the copied executable, with same-path ambiguity rejected. A relocation receipt
must never allow a caller-supplied replacement executable to satisfy a different
core's identity. LLDB module/source search mappings are bounded explicit data.

Do not claim a self-contained OS image or system-library portability. Enumerate
required native dependencies and their identities. For the first product slice,
reject foreign modules and non-system dependencies unless their exact bytes and
symbol lookup can be bundled and validated; list this limit in describe/guide.
Do not silently fall back to missing original project/toolchain paths.

Tests must exercise actual macOS Mach-O and Linux ELF/minidump cores, moved
capsules, absent original executable/source paths, exact Unicode/list watch
values, unchanged core bytes/stops/graph, and installed SDK use. Negative cases
include copied wrong executable, wrong original mapping/key/UUID, altered symbol
or source bytes, extra/missing/duplicate/escaping entries, symlink/FIFO/oversized
inputs, malformed receipts, incompatible compiler/host and partial export.
Preserve previous failures and show optimized source candidates explicitly.

Keep the frontend/reference interpreter/native and TypeScript semantics at
language0.16; this workflow adds no source syntax or implicit effect. Synchronize
the capability descriptor, language-pack manifest, command help, prompt, schema,
guide and SDK acceptance only after the product path is implemented.
