# NEX implementation status

## Promoted0.54: current root checks pending

The exact verified isolated0.54 implementation is now in the root checkout.
The root gets a complete clean build, full64 regressions and installed SDK18
acceptance; isolated results below do not substitute for these checks.

The preceding root0.53 frontend diagnostic failure was a stale-build error:
copying sources with their older timestamps left a pre052 modules.cpp object.
Its dependency file lacked the new directly included diagnostics header.
A clean rebuild of unchanged source passes the same21 diagnostic cases (4.85s,
one macOS filename skip). The failed full62 and focused correction remain in
the graph-query evidence; no replacement full053 pass is claimed.

## Verified isolated0.54: stopped-string Unicode scalar windows

The frozen534-file source passes all64 groups on macOS ARM64 (1496.29s) and
Linux ARM64 (780.41s), with534 Python cases and12 C++ probes. Installed SDK18
passes on macOS (405.32s) and Linux (248.03s); all127 indexed resources match
frozen source. Twelve Linux live debugger suites pass. Its SDK runs without
source checkout or network. [Evidence](docs/evidence/string-ranges-0.54.0.json)
keeps exact compiler/source hashes and platform skips.

String shapes expose scalar length; bounded text_range captures support
length/index/slice and retained/overlapping replay with alias consistency.
The read-only LLDB provider streams strict UTF-8 under separate physical-read,
output and deadline limits with per-expression/stop checkpoints. Actual LLDB/DAP
and installed SDK checks capture a4MiB string at an unchanged stop and replay
the retained window after source deletion. Complete strings, language0.15,
native ABI, canonical forms and graph format remain unchanged.

The frozen source is backed up separately. The new root has independent gates
as stated above; the prior failed full053 run is retained alongside its
clean-rebuild diagnosis. Direct large-root DAP paging, editor/core/PC
mapping, traits/associated/higher-kinded types/async and the remaining full
platform/release/ABI/LLM plan remain open.

## Isolated 0.53 graph search and dependency-radius queries

The prototype adds literal name/source discovery over module/type/function/
endpoint declarations, bounded declaration previews and minimum-hop dependency/
dependent/bidirectional subgraphs. Nodes/edges page independently with explicit
byte and depth boundaries. Responses preserve revision, exact archived source,
namespace and selection identity. Queries select archived source, preserve HEAD
and its journal, and do not execute program/native-extension code. Existing
identity/edge metadata is checked against source; old stores may lazily backfill
indexes. Language0.15, canonical forms and graph schema 4 remain unchanged.
Current implementation/focused/schema/SDK/platform validation remains pending.
The full0.52 checks below are separate, on a frozen earlier source tree.

## Isolated 0.52 captured-source frontend context

The prototype adds source-buffer hashes, phase/scope, bounded UTF-8 or lossless
base64 previews and content-derived diagnostic identity for parser/binder/checker
errors. Rejected assembled candidates remain distinct from physical source and
committed graph identities. Static watch context is bound to supplied frame/stop
hashes; runtime operation metadata remains separate. Language0.15 and graph
schema 4 are unchanged. The 21 Python diagnostic cases (one macOS filesystem
skip), 15 native API cases and seven related regression groups pass. Offline
validation accepts 23 actual error forms and rejects 13 malformed variants. The
exact installed SDK diagnostic phase passes 12 commands including rejected and
repaired candidates, lossless malformed bytes and supplied-frame watch context.
The actual macOS installed SDK16 passed all phases in434.171s with live
LLDB/DAP/browser builds and all122 indexed resources matching frozen source.
Full current regression/Linux live/source-free SDK workflows remain pending.

## Verified 0.49 / language 0.15: atomic change history and restore

The preceding corrected 0.49 compiler passes all 57 regression groups on macOS ARM64
(447 Python cases + 11 C++ probes, 1375.92 s) and Linux ARM64 (1166.28 s). Both
thirteen-phase installed SDK workflows pass: macOS 412.565 s and Linux 263.748 s
in a network-disabled container without the source checkout. Linux additionally
passes eleven live debugger suites. Exact hashes, source scope, platform skips
and retained failed/cancelled baseline attempts are in
[the evidence](docs/evidence/change-history-0.49.0.json). The optional old 0.43
SDK now proves original schema 3 readability and schema 4 refusal. A legacy
migration fixture no longer fabricates unjournaled HEAD writes; an independent
case verifies tampering is rejected without candidate rows.

The journal records actual atomic HEAD transitions and declared labels, with
bounded page/link checks. Guarded restore retains sources/IDs/history and does
not materialize physical files. Schema 4 starts an explicit old HEAD base rather
than inventing prior transitions. This is scoped development evidence, not
proof of every platform, full-system safety or stable cross-SDK ABI.

The intermediate 0.50 passed its focused checks, macOS SDK14 and Linux58/live11/SDK14
matrix; no full macOS regression was run for that intermediate compiler. The
preceding isolated 0.51 source passes all59 groups on macOS/Linux ARM64, both
SDK15 workflows and eleven Linux live suites. Its exact implementation is now
promoted to the root, where the root build/SDK15 pass and full root regression
remains running. [Evidence](docs/evidence/project-versions-0.51.0.json) preserves
the pre-promotion scope. Current0.52 adds diagnostics above that implementation;
its pending checks are not implied by earlier successful versions.

The full requested objective remains open: build the NEX language and complete development chain, including web applications and model-independent authoring. The working core below is a milestone, not completion of that objective. Application products will be built later in NEX; the current deliverable is the language and complete development toolchain.

## In progress: change provenance and archived restore

Toolchain **0.49.0 / language 0.15** adds an atomic local HEAD-transition
journal, bounded paging and optimistic restoration of retained checked sources.
Graph schema 4 preserves existing revision/source/identity/task rows and begins
an empty journal at the prior HEAD. Notes/actors are bounded declared labels;
record hashes and selected adjacent links are checked without authenticating
identity or fabricating historical events. Restore retains all revisions and
IDs, accepts an expected-HEAD guard and does not materialize or execute source.

The initial thirteen history cases pass with five compatibility groups, totaling
six groups and 90 Python cases in 90.41 s. The initial installed SDK passes all
thirteen phases in 293.641 s, including four source-deleted HEAD transitions and
native/reference/TypeScript restoration. Offline JSON Schema 4.25.1 validation
accepts five actual CLI response forms and rejects ten malformed variants; a
foreign graph's claimed journal is not imported as local history.

A final implementation adjustment avoids decoding/hashing an archived bundle
when HEAD is unchanged. All thirteen targeted history cases pass again in 11.11 s.
Earlier compatibility/SDK evidence retains its pre-adjustment compiler scope.
Full current root/platform/installed-SDK validation and the complete requested
NEX language/development chain remain pending.

## Verified development milestone: exact source-operation replacements

Toolchain **0.48.0 / language 0.15** adds complete nonsemantic syntax ranges,
bounded UTF-8 context previews and revision/source-checked patches by local
operation ID. Single expression/statement/pattern fragments preserve precedence
and line-comment boundaries. Non-overlapping edits can span modules and existing
declarations; the whole candidate is checked before a final expected-HEAD
transaction. Derived owners and synthetic intervals remain explicit noneditable
targets. Canonical definitions, database schema 3, operation identity policy 1 and
the runtime tree are retained.

All **56 regression groups** pass on macOS ARM64 in **1334.39 s** and Linux
ARM64 in **1152.04 s**, including **433 Python cases and eleven C++ probes**;
Linux reports its platform-specific skips separately. Eighteen operation-patch
cases cover exact source guards, precedence/comments, nested and complete enum
patterns, generic/closure restrictions, cross-module type edits, effect/realm
rejections, limits and unchanged rejected-candidate rows. Genuine 0.47 archives
retain original revisions, IDs, sites, hashes and diagnostic locations.

Both installed SDKs pass thirteen phases, including source-deleted operation
edits, stable local IDs with changed sites and native/reference/TypeScript
agreement. macOS takes **314.901 s** and source-free Linux **278.590 s** with
networking disabled and all eleven live debugger suites passing. Resource hashes
match the frozen 498-file source. Offline schema validation accepts four actual
current/historical reports and three patch forms and rejects eleven malformed
variants. The [evidence](docs/evidence/operation-patches-0.48.0.json) records exact
scope and the initial composed-expression crash corrected by a resulting-tree
bound. Broader current Release, sanitizer, x86-64, distribution and remaining
language/development-chain work stay pending; this milestone is not project
completion.

## Verified development milestone: checked native integer fast paths

Toolchain **0.47.0 / language 0.15** keeps signed overflow checks and guarded
division/remainder in SSA, with integer runtime calls on failure branches.
Assertions branch on their evaluated boolean; failure retains checked operation
metadata. `MIN % -1` is defined without LLVM undefined behavior. Arguments still
evaluate once, left to right. Error codes/sites, floating rules, canonical
definitions and C value ABI 1 are retained.

All **55 regression groups** pass on macOS ARM64 in **1303.39 s** and Linux
ARM64 in **1098.76 s**, including **415 Python cases and eleven C++ probes**.
Both installed SDK workflows pass thirteen phases: macOS **320.447 s** and
source-free Linux **226.347 s**, with all eleven Linux live debugger suites.
Integer acceptance checks boundaries and loops across reference/native Debug
and Release/TypeScript, then deletes source and replays archived execution.
Native trap mapping and retained historical fixtures also pass. All SDK resource
hashes match the frozen 491-file source snapshot. The
[evidence](docs/evidence/native-arithmetic-0.47.0.json) records exact compiler,
source and report hashes.

Initial shared-host observations measured 71.9 ms vs 105.9 ms for a 20-million
iteration loop and 259,040 vs 391,168 bytes for a constant-expression workload
against 0.46. That initial compiler preceded final descriptor/assertion changes;
these measurements are limited observations, not a general speed guarantee.
Current full Release, sanitizer, x86-64 and SDK distribution checks remain
pending, as does the rest of the requested language and development chain.

## Verified development milestone: native runtime trap attribution

Toolchain **0.46.0 / language 0.15** adds compact constant operation descriptors,
per-link application identity, bounded `NEX_NATIVE_TRAP` records and checked local
graph resolution. `nex run --json` returns native diagnostics; `nex diagnose`
maps retained standalone/HTTP operator logs against current or archived checked
sources. Error propagation preserves the innermost located trap. Original helper
signatures, `Trap` definition, C value ABI 1 and language semantics remain intact.
The [guide](docs/native-diagnostics.md) defines data trust and attribution limits.

The corrected implementation passes all **54 regression groups** on macOS ARM64
in **1258.90 s** and Linux ARM64 in **1078.17 s**, including **412 Python cases**
and **eleven C++ probes**. Both installed SDKs pass thirteen workflow phases;
macOS takes **310.851 s**, source-free Linux takes **306.114 s** with networking
disabled. Linux also passes eleven live debugger suites. Native diagnostics agree
with interpreter operation IDs in debug/release, remain available after source
deletion, and resolve to distinct local IDs after graph import into a new store.
HTTP operator reports retain request IDs while public responses keep their generic
messages. Offline JSON Schema validation accepts actual mapped/unmapped records
and the sanitized C++ producer; six malformed variants are rejected. All 37
historical fixture hashes, six C/value headers and the original `Trap` definition
match 0.45. The [evidence](docs/evidence/native-diagnostics-0.46.0.json) binds exact
compiler/source/report hashes and preserves the initial Linux build failure.

The Linux build initially selected `std::quoted` through ADL; explicit
`nexrt::quoted` fixes that portability defect. Compact typed descriptors reduce
a synthetic many-site executable from 687,584 to 391,168 bytes compared with the
initial JSON-per-site prototype. Arithmetic-call overhead remains visible in a
limited local experiment; isolated 0.47 moves checked integer success paths into
SSA. These measurements are observations, not general performance guarantees.
Broader current Release, sanitizer, x86-64 and SDK distribution checks remain
pending. Parser/checker identities, signal/core recovery, remaining platform and
language/toolchain features are open. This milestone does not complete NEX.

## Verified development milestone: atomic source-type replacements

Toolchain **0.45.0 / language 0.15** adds replacement of existing source
structs/enums with their constructors, signatures, matches and handlers in one
optimistic patch. Optional replacement `kind` must match its declaration;
unknown fields and malformed expected digests are rejected. Source type nodes
are editable, generic instances remain derived, and retained revisions keep
their original layouts. Module/import/new-top-level-declaration edits still use
export/edit/check. Runtime semantics and graph identity policy remain unchanged.

All **52 regression groups** pass on macOS ARM64 in **1196.45 s** and Linux
ARM64 in **1007.88 s**, including 400 Python cases and ten C++ probes.
Both installed SDKs pass thirteen phases, including a partial-type-edit rejection,
a complete type/factory/caller patch, preserved type IDs and source-deleted
native/reference/TypeScript execution. The macOS workflow takes **301.940 s**;
source-free Linux takes **210.147 s**, with networking disabled and all eleven
live debugger suites passing. The final SDK resource hashes match the frozen
source snapshot. Offline schema validation accepts current and five actual 0.44
artifacts plus a legacy function patch, and rejects six malformed variants.
The [evidence](docs/evidence/type-patches-0.45.0.json) binds exact source, compiler
and report hashes. Broader current Release, sanitizer, x86-64 and SDK distribution
checks remain pending. This milestone does not complete the requested language
and development chain.

## Verified development milestone: declaration graph and cross-store references

Toolchain **0.44.0 / language 0.15** adds persistent module/type nodes,
dependency-context fingerprints, bounded declaration queries and explicit
snapshot-scoped identity reconciliation. Local function/operation IDs, database
schema 3, language hashing and runtime semantics remain unchanged. Reconciliation
checks an expected HEAD and commits a complete page atomically without changing
source or HEAD. A genuine 0.43 database fixture covers additive backfill.
The [graph guide](docs/graph.md) defines limits, provenance and mapping scope.

The initial implementation passes all 51 macOS/Linux ARM64 groups (387 Python
cases and ten C++ probes), both thirteen-phase SDK workflows and Linux live
debugger checks. Additional coverage exposed duplicate visits of nested
statement-match bodies in dependency collection: depth 25 took 0.067 s on 0.43
but exceeded a 3-s timeout in the new implementation. Each arm is now visited
once. The same corrected case passes in 0.0423 s; all 17 focused identity cases,
including depth-30 native/TypeScript execution and arm-local type dependencies,
pass in the isolated corrected build. The corrected root passes all 17 focused
cases in 11.198 s. Its full macOS ARM64 regression passes all 51 groups (389
Python cases and ten C++ probes) in 1165.35 s with two parallel workers. Linux
ARM64 passes the same full 51 groups in 999.31 s, then all eleven live debugger
suites and a source-free installed SDK. Both SDKs pass thirteen workflow phases,
including 166 reconciled graph records with destination IDs preserved; macOS
takes 289.973 s and source-free Linux takes 207.806 s with networking disabled.
The five real current graph response artifacts validate offline against JSON
Schema 4.25.1; seven malformed variants are rejected. A 56-record comparison
confirms that the traversal fix preserves identity output.

The [evidence](docs/evidence/graph-identities-0.44.0.json) separates baseline and
corrected results and preserves exact compiler/source/report hashes. Broader
current Release, sanitizer, x86-64 and SDK distribution checks remain pending.
Source type replacement is added in the current 0.45 development; it was not
advertised by the verified 0.44 compiler. Remaining platform adapters, callbacks, async
and the rest of the language/toolchain plan remain open. This milestone does
not complete NEX.

## Verified development milestone: native foreign application packaging

Toolchain **0.43.0 / language 0.15** connects explicit `nex package --foreign`
to recursive Mach-O/ELF dependency collection and complete notices. Only
reachable logical libraries/exports enter the deployed catalogue. Relocated
module bytes get new manifest hashes; the compiler changes only the exact
reachable source pin tokens, rechecks the derived bundle and retains both graph
revisions without changing HEAD or materialized sources. The binary resolves its
packaged catalogue relative to its actual executable location. Captured bytes
are rehashed before publication. C ABI 1 remains unchanged.

The initial integrated snapshot passes all **50 groups** (368 Python cases and
ten C++ probes) on macOS ARM64 in **1107.74 s** and Linux ARM64 in **940.65 s**.
Both installed SDKs pass all thirteen workflow phases, including a moved,
source-deleted nominal C-module application package. The macOS workflow takes
285.702 s; the Linux workflow takes 201.888 s in a source-free container with
networking disabled. The Linux live debugger matrix also passes. These results
describe the initial snapshot before the corrections below.

Additional checks found three defects. Python initially followed a host symlink
and omitted the native regular-file/1-MiB limit; the two new root checks pass in
0.839 s. Relative schema references were unresolved; canonical URIs now resolve
through an offline registry. JSON Schema 4.25.1 accepts three real SDK metadata
artifacts and rejects five malformed variants. Finally, component notice paths
split one shared native image: an observable counter changed from `1,2` to
`1,1` after packaging. Distribution notices are now captured at catalogue scope,
and an inventoried source-identity member preserves distinct original pins.
Both shared-state and independent-state native/reference/package cases pass in
66.212 s, including deleted original inputs and complete file/notice inventories.

The corrected implementation passes all **50 groups** (372 Python cases and ten
C++ probes) on macOS ARM64 in **1170.30 s** and Linux ARM64 in **993.26 s**.
All twelve packaging cases pass on both hosts. The corrected macOS installed SDK
passes thirteen phases in **286.713 s**; Linux passes the live debugger matrix
and thirteen-phase SDK workflow in **205.069 s**, without a source mount or
external networking. Its moved nominal C-module package runs after input/source
deletion. The current schemas validate all three real SDK metadata artifacts
offline and reject seven malformed variants. All 37 historical fixture/header
hashes remain unchanged.

The [evidence](docs/evidence/foreign-packages-0.43.0.json) keeps baseline and
corrected scope separate. Broader compiler Release, x86-64, sanitizer and SDK
distribution checks remain pending; this is not a stable release or completion
of NEX. Cross-target native modules, arbitrary dynamic native loads,
Windows/mobile installers, callbacks and the remaining language/toolchain work
stay open.

## Earlier milestone: reviewed foreign inputs for tasks

Toolchain **0.42.0 / language 0.15** adds read-only `nex foreign HOST.json`
discovery, location-independent operator fingerprints and per-check
`foreign_hash` in native task tests/runs/profiles. Task execution captures all
inventoried binary/notice/manifest bytes and passes the normalized catalogue
only to selected execution commands. Replay requires current operator trust;
rehashed captured receipts cannot grant authority. Checks validate current grants
and source binding/signature pins before native module initialization. Input
integrity is checked around each command. The exact 8192-input boundary now
counts the integrity index separately, and oversized indexes fail before running.

Before the forced-exit correction, 0.42 passed all 49 groups on macOS ARM64
(358 Python cases and ten C++ probes) in 1019.58 s and all 49 groups on Linux
ARM64 in 845.31 s. Both installed SDK workflows passed all thirteen phases,
including the reviewed nominal C-module task and source-deleted trusted replay.
The macOS SDK workflow took 247.092 s. Those results describe the initial
0.42 snapshot, not the correction below.

A real uncooperative C callback exposed a cleanup defect: the supervisor reaped
the timed-out process, but one private module snapshot remained. The task parent
now owns a fresh mode-0700 system temporary directory for each selected foreign
command, removes it after group reaping, and verifies directory identity before
cleanup. Interrupt state is retained before cleanup so cancellation still skips
remaining checks. The isolated nine-case system-temp run passes in 261.686 s;
the final timeout/interruption pair passes in 4.381 s. Existing grant, integrity,
8192-input-boundary and replay cases are included. The corrected ten-case task-FFI group and fourteen-case source-FFI group pass in
249.03 s and 312.53 s. The corrected macOS ARM64 full regression passes all
49 groups in 1058.18 s; the installed SDK passes all thirteen phases in
260.600 s. The corrected Linux ARM64 full regression passes all 49 groups, its
live debugger matrix passes, and its thirteen-phase SDK workflow passes in a
source-free container in 187.131 s with networking disabled. Broader platform,
sanitizer and distribution validation remains pending.

The [task-FFI evidence](docs/evidence/ffi-tasks-0.42.0.json) records the baseline,
correction and pending checks. This is an experimental integration, not completion
of NEX. Dependency-closure packaging, callbacks into NEX, general resources,
async and remaining platform adapters are still open.

## Verified development milestone: source foreign declarations

Toolchain **0.41.0 / language 0.15** connects experimental server-only `extern`
declarations and `ffi` to the checker, interpreter/native backend, explicit CLI
execution, profiling/debugging and browser exclusion. Source bindings identify
a manifest; a separate operator catalogue grants authority.

The final macOS ARM64 Debug regression passes all **48 groups** (350 Python cases
and ten C++ probes) in **889.25 s**. The corrected installed macOS SDK passes all
thirteen phases in **250.044 s**, including independent C module calls from NEX,
native Debug/Release, source-deleted replay, standalone output, real LLDB/DAP
and browser builds. Linux ARM64 passes all **48 groups**, the live debugger
matrix including an external-wrapper watch, and the thirteen-phase SDK workflow
in a separate source-free container with external networking disabled. That SDK
workflow takes **193.294 s**. Seven Linux cases explicitly skip unavailable
macOS cross-SDK/Mach-O checks. Supplemental current imported-callable and stronger
HTTP/static-root scenarios pass on Linux in **50.728 s**.

All 37 historical fixture/header hashes remain unchanged. Reviewed task/proof
metadata was regenerated under 0.15 without changing requirements, postconditions,
loop invariants or test bodies. The [source integration evidence](docs/evidence/source-ffi-0.41.0.json)
binds inputs, artifacts, initial failures/corrections and the executed scope.
Broader Release/Linux x86-64, sanitizer and distribution checks for 0.41 remain
pending. Its task-catalogue and package closures were explicitly unavailable;
the task integration is added in 0.42 above. The earlier 0.40 evidence below
applies to that preceding snapshot.

## Earlier milestone: scoped foreign invocation adapter

Toolchain **0.40.0 / language 0.14** adds explicit `nex.foreign-host/1` operator
catalogues, `nex.foreign-binding/1` metadata, thread-local lexical contexts and a
common invocation path with a native managed-handle bridge. Metadata caches
rebind every call to current request authority; there is no environment grant.
Native cancellation preserves the original diagnostic code/line and standalone
terminal cleanup revokes module owners. The 24 new C/C++ cases pass on macOS
ARM64, including all value kinds, real requests, callback destruction, shared
images across eight independent thread contexts and actual fatal-exit cleanup.
Full macOS ARM64 Debug regression passes all 47 suites (336 Python cases and ten
C++ probes) in 790.04 s with two parallel groups. The installed macOS SDK passes
all thirteen phases in 215.308 s, including the actual scoped native bridge with
deleted C++ sources, real LLDB/DAP and browser builds. All 125 transport, loader,
resource and context cases pass ASan/UBSan/LSan on macOS ARM64 and Linux
ARM64/emulated x86-64; macOS also passes ThreadSanitizer. Independent source-free
Linux hosts execute the scoped bridge against the same NEX value contract.
Private snapshot cleanup leaves no temporary files. Broader current Release/
Linux compiler, isolated Linux SDK and distribution checks remain pending.
[Evidence](docs/evidence/ffi-contexts-0.40.0.json) binds the checked inputs and
scope. Source
declarations, interpreter/MLIR calls, migration, browser exclusion, general
resources, callbacks and async remain pending. The descriptor keeps
`foreign_boundary.source_support:false`.

## Verified development milestone: authorized native module loading

Toolchain **0.39.0 / language 0.14** adds a separate C module descriptor and a
trusted host loader. Explicit library/export grants, manifest/signature pins,
pre-initialization file hashing, private snapshots, resource-bound authorization,
physical call leases and a weak content-addressed image cache are implemented.
The 22 loader cases, 48 legacy/typed transport cases and 31 resource cases pass
ASan/UBSan/LSan on macOS ARM64 and Linux ARM64/emulated x86-64; macOS also passes
ThreadSanitizer. The installed macOS SDK passes all thirteen phases in 223.865 s,
including a real C shared module with nominal values, deleted C/C++ sources,
real LLDB/DAP and browser builds. Separate source-free Linux ARM64/emulated
x86-64 containers execute the loaded nominal module and match the NEX model.
Private snapshot cleanup leaves no temporary files. The initial Linux run's
Docker `noexec` denial and successful corrected run are retained separately.
Full macOS ARM64 Debug regression passes all 46 suites (336 Python cases and
nine C++ probes) in 1596.33 s. Broader current Release/Linux compiler,
isolated Linux SDK and distribution validation remain pending.
[Evidence](docs/evidence/ffi-modules-0.39.0.json) binds the source, binaries and
executed checks. Source foreign
declarations/invocation, general dependency-closure packaging, callbacks and
async remain pending; `foreign_boundary.source_support` stays false.

## Verified development milestone: checked C value signatures

Toolchain **0.38.0 / language 0.14** adds compiler-derived
`nex.foreign-signature/1` metadata, exported with `nex ffi --symbol NAME`, and a
typed host invocation path. Inputs and results are checked through aggregates,
nominal/phantom identities, enum variants, callable authority and file owners.
Appended ABI-1 table slots construct checked records/enums and expose scoped type
tokens. The original C table prefix is preserved and an unchanged installed-0.37
header compiles the legacy producer. Language syntax/canonical formats remain
unchanged. Source declarations, loading/authorization, source backend invocation,
general resources and async remain pending. The descriptor continues to report
`source_support:false`.

The 25 legacy-prefix and 23 typed C/C++ cases pass ASan/UBSan/LSan on macOS ARM64
and Linux ARM64/emulated x86-64; macOS also passes ThreadSanitizer. Full macOS
Debug regression passes all 45 suites (336 Python cases and eight C++ probes) in
715.24 s. Eight new source/schema/history cases include C/native/reference/
TypeScript agreement on the same nested result, enum, generic record, binary and
NUL-string scenario. The installed macOS SDK passes all thirteen workflow phases
in 177.178 s with real LLDB/DAP and browser builds; its typed C host works after
source deletion, using only the retained contract metadata. Compiler, runtime
inputs and workflow match the checked sources. Broader current compiler and
isolated SDK/distribution validation remain pending.
[Evidence](docs/evidence/ffi-types-0.38.0.json) binds the inputs and scope.

A genuine language-0.14 source/SQL fixture was captured using the accepted
installed SDK 0.37 before future declarations. It keeps ordinary `ffi`, `extern`
and `foreign` names, actual server file signatures, callbacks and original IDs.
Its native Debug/Release, interpreter and TypeScript checks pass without retagging
history. [The C transport guide](docs/ffi-design.md) describes the new host scope.

## Verified development milestone: versioned C value transport

Toolchain **0.37.0 / language 0.14** adds an experimental C11 value table and a
trusted C++ invocation wrapper. Call-local, non-reused tokens retain immutable
values without exposing C++ layouts, pointers into NEX storage or raw file
descriptors. The boundary copies UTF-8/binary payloads, checks thread/reference
ownership and quotas, and preserves sticky host traps across cooperative polls.
The independently compiled C producer and 25 lifecycle/value cases pass on
macOS ARM64 and Linux ARM64/emulated x86-64 with ASan/UBSan/LSan; macOS also passes
ThreadSanitizer. Full macOS Debug regression passes all 43 suites (328 Python
cases and seven C++ probes) in 753.03 s. The installed macOS SDK passes thirteen
phases in 148.878 s, including an independently compiled C11 producer/C++20 host,
deleted-source execution without NEX resources, real LLDB/DAP and three browser
builds. Its compiler, runtime inputs and maintained workflow match these sources.
Current Release/Linux compiler and isolated SDK/distribution checks remain
pending. [Evidence](docs/evidence/ffi-transport-0.37.0.json) binds the checked inputs.
Language/canonical formats are unchanged. Source extern declarations, checked
signatures, library loading/authorization, packaging, general resource kinds,
callbacks into NEX and async remain pending. The descriptor keeps
`foreign_boundary.source_support:false`; [the design](docs/ffi-design.md)
defines the integration gates. This is not a stable published FFI.

## Verified development milestone: source file resources

Toolchain **0.36.0 / language 0.14** adds the `file` source type, ten server/`fs`
operations, immutable aggregate/capture owners and identity equality. The
interpreter and native debug/release paths agree on streaming, alias close,
limits and automatic cleanup. The checker excludes resource-bearing types from
client/shared functions, JSON/API and scalar proof models, including phantom
arguments. TypeScript emits no unreachable server resource code.

Source migration uses new function/11 and program/12 formats. Genuine 0.13
snapshots migrate with preserved history; conflicting old user names require
reviewed source repair and failed migrations leave HEAD unchanged. Pure watches
use opaque IDs with no IO authority. Fourteen source tests, five synthetic watch
tests and eleven live/synthetic macOS LLDB/DAP cases pass. The corrected compiler
passes all 42 suites on macOS ARM64 Debug and Release (328 Python cases and six
C++ probes), and Linux ARM64. Linux also passes ten live-debugger suites and all
twelve installed-SDK workflow phases in a separate container without the source
checkout mounted. The installed macOS SDK passes all twelve phases, including
file programs, source-deleted replay, standalone packaging and three browser
builds. Its compiler and runtime inputs match the verified sources.

All 21 managed-file cases pass ASan/UBSan/LSan on macOS ARM64, Linux ARM64 and
emulated Linux x86-64; macOS also passes ThreadSanitizer. All 33 genuine historical
fixture files and 34 previous source examples remain unchanged. Task/proof
acceptance intent and the new version's revision/content pins are checked.
The initial regression caught an inaccurate generic-add descriptor; the checker
correctly rejected file addition. Corrected macOS/Linux ARM64 and emulated Linux
x86-64 runs pass all 42 suites. Linux x86-64 also passes all twelve installed-SDK
workflow phases without the source checkout mounted; live x86-64 debugging and
physical x86-64 execution remain unverified.
Current moved/restored SDK archives, general FFI, source async and broader
platform validation remain pending. This is a development checkpoint, not an
accepted release. [Evidence](docs/evidence/source-resources-0.36.0.json) binds
the checked inputs, results and remaining scope.

## Verified milestone: managed file resource values

Toolchain **0.35.0 / language 0.13** adds immutable managed file wrappers and an
internal native streaming boundary. Copies in aggregates/results/captures share
resource identity and close state; JSON rejects resource values. Profile hooks
observe complete owned payload sizes. Native request exit, cancellation, budget
and deadline failures revoke resources across all its explicit host grants,
including values retained by trusted C++ code. Poll callbacks retain their state
and may release handles, replace themselves or end their request safely.

The new managed-value probe passes 20 cases on macOS ARM64 and Linux ARM64/
emulated x86-64 with ASan/UBSan/LSan; macOS also passes ThreadSanitizer. The prior
29-case foundation probe passes again on both Linux architectures. The installed
macOS SDK passes all twelve phases, including real LLDB/DAP and three browser
builds; its runtime inputs and compiler match these sources. Full macOS Debug
regression passes all 40 suites in 728.90 s: 309 Python cases and six C++ probes.
Broader current compiler/distribution validation remains pending. Source resource
types/intrinsics, debugger representation, language migration, FFI and async
remain open; the capability descriptor explicitly keeps `source_support:false`.
This extends the verified 0.34 runtime below; it does not publish source syntax.
[Evidence](docs/evidence/resource-values-0.35.0.json) binds the retained runs.
An additional genuine 0.13 SQL fixture captures future streaming names and a
`file` generic parameter using accepted SDK 0.34. All three 0.13 fixtures replay
through the current compiler with identical revisions and logical IDs; the 31
previous fixture files remain unchanged.

## Verified milestone: resource ownership foundation

Toolchain **0.34.0 / language 0.13** adds a typed internal C++ resource runtime
and streaming regular-file adapter. Physical leases retain payloads across
logical close; ancestor/request domains revoke aliases, reserve physical quotas
before factories and check revocation again before publication. File operations
snapshot callbacks/arguments and retain services before polling. Existing
whole-file replacements retain their commit/cancellation semantics.

The [ownership contract](docs/resources-design.md) records scope, IO errors,
partial cancellation and source/FFI integration requirements. New lifecycle,
race and real-file probe passes all 29 cases on macOS ARM64, Linux ARM64 and
emulated Linux x86-64 with ASan/UBSan/LSan. macOS also passes ThreadSanitizer.
The installed macOS SDK passes all twelve workflow phases, including real
LLDB/DAP, file programs and three browser builds. This is an installed SDK check
with source/external tools available, not a moved/restored isolated bundle check.
Full current macOS Debug regression passes all 39 suites in 657.99 s, including
309 Python cases and five C++ probes. The broader current compiler and
distribution matrix remains pending. Source resource types/streaming intrinsics,
stable FFI and async remain unimplemented. [Evidence](docs/evidence/resources-host-0.34.0.json)
binds the probe inputs and retained reports.
The verified 0.33 distribution below remains a separate historical milestone.

## Development milestone: current SDK distribution

Toolchain 0.33 / language 0.13 now has a maintained macOS distribution helper
and a shared inventory-preserving archive boundary for macOS/Linux. Eight owned
archive cases passed on macOS and Linux ARM64. The full current macOS Debug run
passed all 38 suites in 755.68 s: 309 Python cases and four C++ probes.

The macOS SDK passed all twelve workflow phases after moving and after archive
restoration, with actual LLDB/DAP, all three browser builds, kernel read denial
for the source/Homebrew/MacPorts trees, and SDK write denial. Each denial has an
actual negative control. Linux ARM64 passed both twelve-phase workflows in
containers without source or host LLVM/MLIR/Z3, followed by another complete
bundled-SDK live-debugger workflow using its declared external LLDB prerequisite.
The x86-64 compiler passed all 37 suites and its source-free SDK workflow.
Its moved/restored archive workflows also passed all twelve phases under
emulation. All three current development archives are verified.
Actual archives, hashes and scope are recorded in
[SDK evidence](docs/evidence/sdk-0.33.0.json). These are development bundles;
platform C/C++ SDKs, Python/Node and the stated debugger prerequisites remain.

Genuine language-0.13 SQL/source snapshots were captured with the accepted
restored SDK and replayed through another compiler location, preserving graph
revisions and logical IDs. Candidate resource-related names are ordinary user
definitions in these fixtures; source resources/FFI/async are not implemented.

## Development milestone: source binary integration

Development **0.33.0 / language 0.13** connects `bytes` to checked source types,
explicit UTF-8/base64 codecs, immutable operations, generic add/wire, native and
TypeScript emission, typed JSON/API models and bounded debugger demand. Binary
file calls share the server/fs capability policy. The matching specification,
grammar, model-independent prompt and schemas are validated with genuine
0.12 migration fixtures; the full requested objective remains open.

Host-poll ownership review reproduced a 0.32 adapter use-after-free under ASan
when a trusted callback dropped the last input ByteBuffer. The 0.33 writer retains
its owner until all borrowed views finish. The reproduction now exits cleanly
under ASan/UBSan, and the extended 19-case managed-value probe passes. The 0.32
compiler/SDK cohorts below use their preserved sources; they do not validate this
new source-language version. The 10-case source suite passed,
followed by the native/reference/TypeScript binary browser-state case. Seven
offline binary watch cases and the real macOS LLDB/DAP case passed, including
selected reads of a 4 MiB value, retained-slice previews, paged read-only octets
and source-deleted replay. The generic binary API/OpenAPI/SDK/live-HTTP case
passed, including strict malformed-wire rejection and cleanup after traps.
Apple LLDB's target-wide basic type selected a Swift integer; byte children now
use the actual runtime DWARF i64 type. All six production UI checks passed in
Chromium, Firefox and WebKit. The installed macOS ARM64 SDK passed all twelve
workflow phases in 126.717 s, including actual byte DAP watches, independent
binary-file packages, archived replay and all three locked browser builds.
The first SDK attempt revealed missing manifests in two new acceptance projects;
their corrected explicit projects were exercised by the complete second run.
The full 37-suite macOS Debug invocation finished in 673.14 s: 36 suites passed;
the sole failure was its stale exact add-bound inventory. After adding bytes to
that exact list, all eleven constraints cases passed in a 76.27 s CTest rerun.
Compiler/runtime code did not change for that test correction. This covers 301
declared Python cases and four native C++ probes, including the independent
48-update binary oracle and retained aliases. Both initial and corrective
reports are preserved; the initial invocation remains recorded as failed.
macOS Release then passed all 37 suites directly in 563.23 s. Linux ARM64
passed all 37 in 554.30 s; both frozen cohorts contain 300 Python cases and
four C++ probes, with the later independent oracle separately passing through
each matching compiler/SDK. All nine Linux live-debugger suites passed in
60.145 s. The source-free Linux SDK passed all twelve workflow phases, both
without live debugging (113.735 s) and with real LLDB/DAP (120.542 s).
All nineteen managed ownership cases passed under Linux GCC 13.3
ASan/UBSan/LSan; the preserved Clang image lacked sanitizer libraries, and its
initial linker failure is recorded separately. Production compiler tests use
LLVM/MLIR 22.1. The current emulated x86-64 compiler, installed SDK and all
three moved/restored development bundles have also passed.
The [source binary evidence](docs/evidence/bytes-source-0.33.0.json) records exact
source/binary hashes, browser versions, installed SDK phases and remaining scope.
See [bytes.md](docs/bytes.md).

## Historical 0.32: managed binary values

Development toolchain **0.32.0** retains source language **0.12**. Internal C++
and TypeScript value runtimes now represent immutable binary data, typed JSON
base64 and strict UTF-8 conversions. The POSIX host adapter has bounded binary
reads/writes under the same directory capability, atomic publication and HTTP
isolation as text files. Native allocation accounting and handle cleanup include
the binary subtype; ordinary object layouts retain their size and field offsets.
Generated TypeScript/browser resources include the binary module. This does not
expose a source type or binary intrinsic yet. Targeted managed-value/oracle checks
passed. The full macOS Debug run exercised all 35 suites in 1158.95 s: 34
passed, and web failed only its obsolete exact file inventory. The corrected
inventory retains the exact-set check, adds byte-for-byte module comparison,
and passed all seven web cases in a 5.19 s CTest rerun. No compiler/runtime
code changed for that correction. This covers 281 declared Python cases and
four C++ probes; the original failed invocation remains recorded. The macOS
Release invocation likewise passed 34 suites before the corrected web inventory
passed all seven cases. Both Linux compiler runs subsequently passed all 35
suites (ARM64 488.52 s; emulated x86-64 1747.18 s), and their source-free
eleven-phase SDK workflows passed. The installed macOS SDK workflow passed too.
These preserved 0.32 cohorts do not include the 0.33 host-poll ownership fix.

Source binary syntax, API/debugger support and explicit 0.12 migration were
added in 0.33 above. The [buffer design](docs/bytes-design.md) defines implemented host
semantics and the remaining integration. SDK 0.30/0.31 and genuine historical
stores are preserved. [Managed-value evidence](docs/evidence/bytes-values-0.32.0.json)
records each tested source, binary and correction separately. Initial Linux runs
used old toolchain images without `patchelf`; their failed logs are retained.
The tested packager images have the identical base layers plus that dependency.
The corrected compiler hashes match the initial cohorts; packaging and exact
web-inventory checks passed in the completed corrected Linux runs. Source
toolchain 0.32 retained language 0.12 throughout that internal-runtime milestone.

## Historical 0.31: immutable binary primitives

Development toolchain **0.31.0** retains source language **0.12** while building
the internal buffer representation and strict base64 codec. Native buffers own
immutable contiguous octets, copy mutable host imports/exports, retain slice
owners and allocate new values for updates. The TypeScript primitive uses
private storage with checked constructors and copied host boundaries. Eight native ownership/bounds cases and three cross-runtime codec-oracle checks
passed on macOS ARM64, Linux ARM64 and emulated Linux x86-64. Strict ES2020
TypeScript checking passed; macOS ASan/UBSan and native Linux ARM64
ASan/UBSan/LSan passed. The final JS boundary also rejects constructor/prototype
mutation. All 33 current macOS Debug suites passed in 1013.88 s (278 declared
Python cases and three C++ probes, including one Linux-only skip). The emitted
ES2020 primitive passed 68 assertions each in actual Chromium 156.0.8078.4,
Firefox 157.0 and WebKit 27.2, with no page errors. These are primitive checks;
full source-language binary integration remains pending. [Durable prototype
evidence](docs/evidence/bytes-runtime-0.31.0.json) binds the tested source/binaries.

This is not yet a source `bytes` type. Frontend/interpreter/MLIR/TypeScript,
JSON/API, debugger, file-operation and explicit 0.12 migration integration remain
required before exposing the next language version. [The buffer design](docs/bytes-design.md)
records scope; the verified 0.30 SDKs and genuine 0.12 fixtures remain preserved.

## Development milestone: scoped text files

Development toolchain **0.30.0 / language 0.12** exposes server-only
`file_read_text` / `file_write_text` through the distinct `fs` effect. The
interpreter and native runtime share a POSIX directory-capability adapter with
strict UTF-8, immutable results, bounded paths/text and atomic file replacement.
Standalone access requires an explicit absolute root; writes additionally require
exactly `NEX_FILES_WRITE=1`. Native HTTP scopes deny inherited environment grants;
a trusted C++ host can explicitly grant `FileScope`. File writes are not part of
SQLite rollback. Source-level resources, binary buffers, streaming and general
FFI/async remain open.

The rebuilt compiler passed all 13 source integration cases in 59.358 s:
native Debug/Release/reference agreement, Unicode/NUL/BOM, limits and denial,
evaluation order, snapshot closures, TypeScript exclusion, genuine 0.11 migration,
reserved-name repair, HTTP denial, trusted-host cancellation cleanup, reviewed
task effects and pure-watch rejection. The installed SDK adds a dedicated file
phase covering capability denial and independent packaging. All 31 suites passed
on macOS Debug/Release (1231.14/1073.95 s) and Linux ARM64 (496.79 s), with
275 declared Python cases plus the two C++ probes. macOS records one Linux-only
skip; Linux records seven macOS-only skips. Linux ARM64 also passed eight live
suites and its source-free 11-phase SDK in 83.069 s. Emulated Linux x86-64 also passed all 31 suites in 1812.18 s and its
source-free 11-phase SDK in 271.612 s, without claiming live debugger
coverage. This completes the stated 0.30 compiler/installed-SDK matrix.

The moved macOS Release SDK passed all 11 phases with actual LLDB/DAP and both
locked browser builds in 106.313 s. Its restored archive verified 2411 files and
compiled/ran new projects and file applications with kernel-denied access to the
checkout, Homebrew and MacPorts. A forbidden-read control failed as required.
The Linux ARM64 bundle passed all 11 phases in a source-free image without host
LLVM/MLIR/Z3/Clang, then repeated all 11 after extraction (105.935/108.354 s),
checking all 743 files. The first clean-image attempt exposed a missing packaging
prerequisite, patchelf; the maintained image/guide now declare it. Compiler,
runtime and language-test inputs remain the frozen `c93c4786` set; Linux SDK
resources carry the two documented recipe/guide corrections.

File packages separately passed native Unicode/NUL output, denied writes and
unchanged content in runtime-only Linux ARM64/emulated x86-64 images without SDK
or development tools. Direct runs hid `/usr/bin` and used an unavailable PATH;
the Python negative controls failed and native file execution succeeded.
[Durable 0.30 evidence](docs/evidence/sdk-0.30.0.json) records hashes, exact scopes
and explicit platform limits. The x86-64 bundle verified all 743 files and
passed 11 clean phases in 292.810 s, then repeated 11 after extraction in
271.620 s. This does not complete the broader requested project.

The earlier internal adapter passed 13 direct C++ cases on macOS ARM64, Linux
ARM64 and emulated Linux x86-64; its source-0.11 prototype passed all 30 macOS
suites in 921.16 s. Genuine SDK 0.29 / language 0.11 store/export fixtures retain
old sources/history before migration. These historical results do not substitute
for the new language-version matrix. See [the file guide](docs/files.md) and
[the design](docs/files-design.md).

Genuine SDK 0.30 / language 0.12 SQL fixtures also preserve current generic wire,
server `fs` and callable-reference code before the next language change. The
conflict fixture retains currently valid user names proposed for binary buffers.
[The next buffer design](docs/bytes-design.md) is a plan; buffers are not yet
advertised or accepted by the compiler.

## Development milestone: native application packages

Development toolchain **0.29.0** retains source language **0.11**. `nex package`
builds an application/server (release by default) and assembles its required
non-platform library closure, full notices and hash inventory into a new directory.
It reuses bundled-SDK provenance with byte-integrity checks, supports explicit
notices and Debian package metadata, rewrites copies and never executes the app.
The SDK collector shares its relocation/notice/inventory code with this path.

The compiler built successfully. Five macOS tests passed in 24.762 s: archived
source deletion, output preservation/rejected modes, actual selected SQLite after
deleting its original library/source/build, SDK-inventory reuse plus changed-library
rejection, and a moved HTTPS server with authentication, per-user storage,
persistence across restart and clean exit. An initial `/var` versus `/private/var`
prefix mismatch was fixed by canonicalizing the staging directory; the server
test requires permission to open loopback sockets. Full 0.29 validation passed
on the stated macOS/Linux development matrix. These tests do not establish broader deployment
compatibility, Windows/mobile packaging or completion of the requested toolchain.
See [application packaging](docs/packaging.md) for prerequisites and limits.

Actual numeric, SQLite and HTTPS fixture packages from a moved SDK passed on
macOS ARM64 with kernel-denied access to the checkout/SDK, Homebrew and MacPorts;
the forbidden-read negative control also failed as required. Both Linux ARM64
and emulated x86-64 passed the same native probes in network-disabled runtime
images with no NEX/Clang/GCC/CMake/Node/npm. Every packaged file and actual ELF
library resolution was checked, including authentication, principal isolation,
restart persistence and clean exits. Python is the probe driver rather than an
application dependency. Additional direct container runs hid `/usr/bin` and used
an unavailable PATH: the Python negative control failed, both architectures ran
numeric/SQLite applications, and their HTTPS servers started and exited cleanly.
The corrected installed macOS SDK separately passed all ten phases with actual
LLDB/DAP and both browser builds in 108.719 s.

The new deployment fixture initially used reserved `server` as its module name;
its one-line correction is independently exercised by those native probes.
The verified 0.29 compiler/runtime/tests are the frozen `8cf7621c` inputs.
All 29 suites passed in macOS Debug/Release (1190.77/1007.13 s), Linux ARM64
(490.65 s) and emulated Linux x86-64 (1795.98 s). Linux ARM64 passed all eight
live suites and its ten-phase source-free SDK in 68.174 s; x86-64 passed its
source-free SDK without claiming live debugger coverage. Corrected installed
Linux application drivers directly produced packages that passed the minimal
runtime probe. Both Linux SDK archives repeated all ten phases after extraction.
The macOS Release SDK passed ten phases in 83.333 s, then archive extraction,
all 2402 inventoried file checks and fresh project/build/run/test/package under
kernel-denied source/Homebrew/MacPorts access. Each Linux archive verified 734
files. [Durable SDK evidence](docs/evidence/sdk-0.29.0.json) records hashes,
tested prerequisites and exact validation scope.
[Durable package evidence](docs/evidence/application-packages-0.29.0.json)
records tested images, application manifest hashes and the fixture correction.

The most recent fully verified development checkpoint is toolchain
**0.30 / language 0.12** (function/9, program/10), using compiler/runtime/test tree
`c93c4786` with the recorded Linux recipe/guide resource corrections. Current
0.31 binary-primitive work is separate and retains source language 0.12. Windows/mobile/UI/GPU/Wasm, broader filesystem/resources/FFI/async and the other open plan items remain required work.

The historical accepted checkpoint is toolchain **0.23 / language 0.10**, commit
`e55ee8233b005671f50e193b55256417f1a3d5d1`, with typed
function values, immutable snapshot closures, the generic wire bound and
validated lazy callable watches. Canonical formats are function/8 and program/9.
It passed the macOS ARM64 and Linux ARM64/x86-64 matrix recorded below. Linux
x86-64 execution is emulated; its live debugging remains unverified. Keep SDK
0.22 for its original receipts and frames. This checkpoint does not complete
the broader requested language/development-chain/platform objective.

The checker, interpreter, typed native indirect calls, TypeScript closures,
owned cleanup, graph/cache metadata, strict debug values and callback-safe API
projection are implemented. The model-independent function guide, grammar and
prompt describe the same source semantics. `docs/function-values-design.md`
retains design and prototype evidence. Unsupported platforms and remaining
full-toolchain work stay in scope as listed later in this file.

## In progress: Linux development bundles

Development toolchain **0.28.0** retains source language **0.11**. Linux native
storage/server builds now select configured library directories at execution time,
with an observable SQLite/loader regression for comma/Unicode/percent paths and
explicit rejection of ELF search-list colons. The three macOS native-target,
host-SDK and task-toolchain suites passed in 115.07 s; their Linux/complete 0.28
validation is pending.

ELF assembly copies Clang/llvm-ar/LLD, Clang resources, SQLite/OpenSSL headers
(including multiarch configuration) and non-platform libraries. Copied images get
origin-relative RUNPATH and matching SONAME aliases. GNU loader/glibc/libstdc++/
libgcc and C/C++ development headers/CRT remain external platform prerequisites.
Debian/Ubuntu ownership metadata supplies exact package/source versions and full
copyright/common-license texts; unmanaged files need explicit component notices.
An assembly-only prototype on the preserved 0.27 SDK inventoried 723 files and
23 components. It is not accepted application evidence: ELF application paths
require the current 0.28 compiler.

`tools/linux/bundle.py` freezes an installed SDK/assembler, uses a separate
patchelf image, moves the assembled SDK, runs all ten maintained phases in a
source-free/network-disabled image with no LLVM/MLIR/Z3/Clang, creates an archive
and repeats validation after extracting it elsewhere. The first ARM64 bundle passed all ten phases in 103.287 s in the minimal
runtime and repeated them after archive extraction in 110.364 s. All 726
inventoried files and 23 components were checked; actual compiler/server library
resolutions stayed inside the relocated SDK except the declared GNU platform
runtime. Its 140,555,121-byte archive SHA256 is
`41f3f838ec2438c35ba674b17963ced8a70373e23e9198a17e5a4aa3edf01d8b`
(`build/linux-arm64-028-bundle/verification.json`). It used glibc 2.39/GCC SDK;
observed symbol requirements include GLIBC_2.38 and GLIBCXX_3.4.32, without
claiming untested host compatibility. Linux ARM64 also passed the full 28-suite
regression in 496.89 s, including the selected-SQLite test; live suites continue.

A later metadata review found unchecked SONAME/component path components.
The packager now rejects absolute/escaping SONAME aliases and `.`/`..` component
names. A real ELF fixture with an outside-output SONAME was rejected without
writing that link (`build/boundary-test/report.json`). That check is now a
maintained packaging phase in `tools/linux/bundle_boundaries.py`. A fresh bundle
with the corrected helper resources is being verified. The compiler/runtime/
existing language-test inputs remain the frozen `a979829a` set; these later
changes affect packaging resources/documentation only. The original compiler
images are unchanged.
The final guarded ARM64 and emulated x86-64 bundles each passed ten source-free
phases and repeated ten after archive extraction. ARM64 observed 95.469/88.360 s;
x86-64 observed 263.207/253.742 s. Both verified 727 files and 23 components.
The shared macOS assembler also passed ten phases with actual LLDB/DAP, native
kernel-exclusion checks, and archive extraction with all 2395 file hashes plus
new-project native execution/tests. macOS Debug/Release passed all 28 suites
(257 declared Python cases, including one Linux-only skip) in 1190.63/1003.25 s.
The full emulated x86-64 compiler regression subsequently passed all 28 suites in
1700.52 s, followed by all ten source-free SDK phases in 201.515 s. Live x86-64
debugging remains unverified. [Durable SDK evidence](docs/evidence/sdk-0.28.0.json)
records immutable archive/compiler hashes, tested prerequisites and scope.

All broader language, resource/async/FFI, compiler-cache/LTO and platform work
remains in scope; this step does not complete the requested toolchain.

## In progress: relocatable development SDK

Development toolchain **0.27.0** retains language **0.11**. Relative installed-SDK
tool/dependency selection and explicit archive/debug-tool overrides are implemented.
The compiler reports effective paths, fingerprints selected archive/debug tools,
and rejects invalid/escaping SDK descriptors. Native storage/server executables
record configured macOS library directories as runtime search paths. The dedicated
SQLite regression passed in 3.984 s with a comma/Unicode/percent dependency path;
all three moved-SDK/tool-selection cases passed with real native subprocesses.

The macOS assembler copies Clang/llvm-ar/dsymutil, builtin/runtime/libc++ resources,
available libLTO, SQLite/OpenSSL headers/libraries and the transitive non-system
Mach-O closure. It requires declared component roots and full local license texts,
records original/packaged hashes, rewrites copies and refreshes ad hoc signatures.
Original source installations remain unchanged. Select the external Apple SDK
with `SDKROOT="$(xcrun --sdk macosx --show-sdk-path)"` or an explicit `sysroot`.

The relocated Release bundle passed **all ten maintained phases in 72.493 s**,
including real archived LLDB/DAP, source-deleted replay, both locked Vite builds,
native HTTP/HTTPS authentication, per-principal Unicode storage and persistence
after restart (`build/sdk-027-release-bundle-v3-acceptance/report.json`). The
server probe uses the host's documented `/api/` dispatch prefix. A separate
kernel-sandbox test denied Homebrew, MacPorts, original dependency/SDK and source
resource paths: native numeric tests, an archive, SQLite execution and a newly
compiled HTTPS server passed. A negative control confirmed forbidden reads fail.
It explicitly selected Apple SDK 27.0; Python/Apple tools remain available.
`build/sdk-027-native-isolation-v4/report.json` records that scope. The protected
sandbox launcher strips DYLD tracing, so its empty loader log is not runtime
image evidence. The first bundle's compiler image audit separately loaded all
seven non-system images from its own prefix.

A development archive was created, extracted into another directory and checked
against every one of its **2391 inventoried files**; the restored compiler built,
ran and tested a new native project. Artifact:
`build/releases/nex-sdk-0.27.0-macos-arm64-development.tar.gz` (116,131,561 bytes),
SHA256 `779c2edd2ea1b26b2c100e6c749404d038fec6a6f336999f80cb3ed6af9d16df`.
The companion manifest records compiler tree
`333666ed7c1ad70f9e44f6e6685ea5f292379c46` and the three tested SDK-resource overlays.
Archive verification is `build/sdk-027-archive-verification.json`.

The 0.27 macOS Debug and Release compilers passed all 28 suites in 986.25 s
and 847.04 s respectively (256 declared Python cases plus the C++ probe). The
installed verified Debug SDK passed ten phases in 87.948 s. Linux ARM64 passed
all 28 suites in 429.66 s, all eight live suites and ten source-free SDK phases
in 66.587 s. Its compiler/runtime/test inputs match `333666ed`, with five recorded
SDK validation/document overlays from `7b0f8ca4`; all 64 indexed resources match.
The emulated Linux x86-64 0.27 run passed all 28 suites in 1774.58 s and its
ten-phase source-free SDK in 246.708 s, completing that compiler/SDK matrix
(`build/sdk-host-milestone-027.json`). It does not claim live x86-64 debugging. A first mixed
source-test/old-binary run was explicitly invalidated; it is not accepted evidence.
Current compiler/runtime/test inputs match the frozen `333666ed` source snapshot;
SDK validation later corrected only its `/api/` fixture and packaging resources.
Linux's installed SDK validation must receive that recorded resource correction.
This is a macOS ARM64 development bundle, requiring macOS **27.0**, Apple SDK/tools,
Python, Node/npm for web builds and host LLDB for debugging. Broader machine/OS
coverage, Linux/Windows packaging, mobile SDKs and notarization remain pending.
The complete language/development-chain objective remains open.

## Development milestone: native build overhead

Toolchain **0.26.0** retains language **0.11**. A stack sample
of a warm 0.25 build found complete MLIR generation used only to validate its
entry, plus repeated operation-tree construction. Entry checks are now shared
between the builder/emitter and run before code selection without emitting IR.
One checked operation tree per reachable function provides both debug-site
metadata and the immutable AST-site index used by the native emitters.

The first three cases passed, including already-cached libraries/tests rejected
as invalid application entries, same-file body edits and generic/closure reuse.
Full checking, source/ABI keys, artifact integrity and MLIR/LLVM verification
remain required. Actual reused-function LLDB/DAP passed in 7.872 s. The installed
macOS SDK passed all nine phases in 66.831 s, including archived watches,
source-deleted replay and both locked Vite builds. Reports:
`build/native-build-026-{targeted,live}.log` and
`build/sdk-026-native-build/report.json`. All 27 macOS Debug-compiler suites passed
in 1028.66 s. Linux ARM64 passed 252 declared Python cases (six macOS SDK skips),
all eight live suites and source-free SDK acceptance. The frozen 0.26 Release compiler passed all 27 suites in 910.45 s; its installed
SDK passed nine phases in 58.588 s. Linux emulated x86-64 passed all 27 suites
in 1792.24 s and its source-free nine-phase SDK in 201.835 s. This completes the
0.26 matrix (252 declared Python cases plus the C++ probe per platform; Linux
records six macOS-SDK skips). `build/native-build-milestone-026.json` and
`build/preserved-sdk-026.json` retain reports and four untouched SDK prefixes.

In five interleaved paired observations of the same 13-function workload on a
loaded development host, median warm builds improved from 1.4051 s (0.25) to
1.1736 s (0.26), and single-function edit builds from 2.2056 s to 1.6424 s.
Both versions compiled one/reused twelve functions after each edit and produced
the same checked outputs. The single cold observations were 5.6991 s and
3.7203 s. This is evidence for that workload/configuration, not a general speed
guarantee. All observations and compiler hashes are retained in
`build/native-build-026-comparison/report.json`; before/after stack samples are
`build/function-cache-025-sample` and `build/native-build-026-sample`.

## Development milestone: function object reuse

Toolchain **0.25.0** retains source language **0.11** and its
canonical formats. Native planning gives each concrete function, lifted closure
and generic specialization its own verified object. Call interfaces and
transitive type layouts invalidate consumers, including within one source file.
Owned source text, emitted line/column positions and captured-binding coordinates
participate in keys; unrelated absolute byte-offset changes do not.

Stable virtual DWARF paths map to each build's complete immutable sources.
LLDB uses the direct setting API, DAP receives matching sourceMap pairs, and
profile reports resolve virtual paths back to selected source projections.
Build responses add compiled/reused function counts while preserving module
counts as grouped source units. The complete frontend is still checked.

Initial same-file native/compiler-spy cases and actual LLDB/DAP reuse across
two source-deleted revisions passed. The archived library check also passed
after basing anchors on logical unit/module identity rather than a live physical
library path. The installed macOS SDK passed all nine maintained phases in
61.625 s, including one-function invalidation, both archived outputs, actual
archived DAP, numeric semantics and both locked Vite builds
(`build/sdk-025-function-cache/report.json`). LLDB's value report was checked to
resolve a real frozen file through its source map. The complete regression/platform matrix below passed. Preserve the
verified 0.24 SDKs recorded in `build/preserved-sdk-024.json`; this development
work does not replace that checkpoint or complete the broader objective.

The complete macOS regression passed all 27 suites and 251 Python cases plus
the C++ probe in 1035.82 s (`build/ctest-025-function-cache-full.log`). Linux
ARM64 passed all 27 suites in 422.57 s, with 251 declared Python cases including
six explicit macOS-SDK skips. All eight live suites passed, including actual
reused-function LLDB/DAP after source deletion. Its source-free, network-disabled
SDK passed all nine phases in 53.389 s and required one compiled/two reused
functions after a same-file edit (`build/linux-arm64-025`). The emulated x86-64 run passed all 27 suites in 1587.36 s and its source-free
nine-phase SDK acceptance in 205.889 s; that host does not claim live debugging.
`build/function-cache-milestone-025.json` records the completed matrix.

The new SDK preserves the earlier semantic revision and reviewed task hash.
SDK 0.24 still inspects/replays its own original frame/receipt; 0.25 rejects
them with E_DEBUG_BUILD/E_TASK_COMPILER. The 0.25 numeric browser assets are
byte-identical to those already exercised in Chromium, Firefox and WebKit;
all 62 indexed installed resources match. Evidence:
`build/version-025-old-sdk-compatibility.json` and
`build/sdk-resource-browser-verification-025.json`.

Local single-observation build comparisons do not yet show an end-to-end
latency win. A 13-function workload with 150 checked additions per helper
reemitted 13 functions in 0.24 and one in 0.25, but edit builds took 1.6311 s
and 1.6668 s respectively; cold builds took 2.8119 s and 4.646 s. The small
workload also showed slightly higher latency. These used development compilers
on a host running concurrent validation. Complete source checks took about
0.15 s versus about 1.06 s for warm builds in the larger case; build-pipeline
overhead needs further investigation. Frontend reuse, LTO and portable release
SDKs remain open. Reports: `build/function-cache-025-benchmark{,-large}/report.json`.

## Development milestone: finite binary64

Toolchain **0.24.0 / language 0.11** introduced finite `f64`,
decimal/exponent literals and `number` bounds. Native debug/release, interpreter
and TypeScript examples agree, including generic functions, results, aggregates,
snapshot closures and explicit conversions. Genuine SDK-0.23 SQL migrations
preserve source/history/IDs; an intrinsic-name conflict leaves HEAD unchanged
until an explicit archived-source repair. Task/proof pins were refreshed with
unchanged source hashes and acceptance intent.

Actual macOS LLDB/DAP checks read f64 roots, subnormals, closure captures and
pages and replay after source deletion; offline full/partial watches agree.
Generated API client models preserve f64 with numeric JSON schemas. A native
C++ host exercises real double parameters/results, invalid input rejection,
request trap cleanup and preservation of caller floating flags. The development
matrix below has passed. Broader platform coverage and redistributable SDK
delivery remain pending; the descriptor conservatively retains
`numeric_integration_pending` for full platform/SDK validation. Design and
acceptance scope: `docs/floats-design.md`.

The current source integration has passed all 27 Linux ARM64 CTest suites
(247 declared Python cases, including six explicit macOS-SDK skips, plus the
C++ runtime probe; 389.40 s). All seven opt-in live debugger suites passed,
including the new floating roots, negative aggregate values, subnormals,
captures and DAP pages. Its source-free SDK passed all nine phases with
external networking disabled (`build/linux-arm64-024`). The final macOS ARM64
run passed all 27 suites and 248 Python cases plus the C++ runtime probe in
959.92 s. Emulated Linux x86-64 passed the same 27-suite frozen-input regression
in 1428.14 s, with 247 declared Python cases including six macOS-SDK skips.
The later numeric-browser case passed separately on both Linux SDKs in native
debug/release and TypeScript; all 177 compiler/runtime/adapter/library inputs
remain identical to the frozen tree. Reports:
`build/ctest-024-browser-final.log`, `build/linux-{arm64,amd64}-024` and
`build/linux-numeric-web-supplement-{arm64,amd64}/report.json`.

The production `examples/numbers-web.nex` application passed six Playwright
cases across Chromium, Firefox and WebKit in 3.204 s. It exercises immutable
f64 state/history, generic arithmetic, a captured callback, JSON rounding,
subnormal/maximum values, positive-zero normalization and recoverable rejected
edits. The maintained SDK workflow now requires this example as well as the
earlier callable browser app. The updated macOS SDK passed all nine phases in
64.914 s, including both locked Vite builds and actual archived DAP watches;
all 62 indexed resources are installed. Its numeric browser assets are
byte-identical to the assets used for the browser interactions. Evidence:
`build/numeric-web-024`, `build/sdk-024-browser-final/report.json` and
`build/sdk-024-numeric-browser-artifact-agreement.json`.

The updated source-free Linux SDK workflows, including both browser examples,
passed all nine phases in 49.104 s on ARM64 and 169.091 s on emulated x86-64
(`build/linux-sdk-024-browser-{arm64,amd64}/workflow/report.json`). ARM64
includes actual archived DAP; x86-64 records live debugging false. Their earlier
complete frozen-source workflows are retained separately. These SDKs still
require the documented host development dependencies; they are not portable
redistributable toolchain bundles.

Independent jsonschema 4.23 checks passed current task/proof documents,
operation output, actual archived partial frames and callable wire descriptors,
including f64 captures and full frames with subnormal values. The preserved
0.23 SDK still inspects its old frame and replays its old receipt; 0.24 rejects
them with `E_DEBUG_BUILD` and `E_TASK_COMPILER`, retaining the original bytes.
See `build/version-011-schema-evidence.json` and
`build/version-011-old-sdk-compatibility.json`. These results do not complete
the full language/development-chain/platform objective.

The following foundation evidence predates enabling the 0.11 source type.

The runtime foundation now has finite checked arithmetic, rounding/environment
isolation, normalized zero, explicit integer conversions, distinct aggregate
scalar storage and strict numeric JSON. C++ and JavaScript agree on **4,546
deterministic vectors**, including Python bit-result oracles, gradual underflow,
rounding ties, integer bounds and rejected non-finite inputs. Native checks also
exercise caller rounding/status flags, flush-to-zero modes, threads, trap source
lines and owned cleanup. Optimized checks passed on macOS ARM64 with UBSan
(`build/float-runtime-O3-ubsan.json`), Linux ARM64 and emulated Linux x86-64
(`build/float-runtime-linux-{arm64,amd64}/report.json`). The pinned Linux images
lack compiler-rt sanitizer archives; those two runs used ordinary O3 builds.

The full macOS regression exercised 26 CTest suites: 25 passed, and profiling
passed on rerun after its old empty-notice expectation was updated to preserve
Tracy exclusion while accepting Dragonbox's license. Runtime/compiler bytes did
not change between those runs. Logs: `build/float-runtime-full-ctest.log` and
`build/float-runtime-profiling-rerun.log`. A separate installed SDK passed all nine
acceptance phases, including actual LLDB/DAP, source-deleted archive replay,
scalar proof and a locked TypeScript/Vite build in 76.573 s
(`build/sdk-float-runtime-acceptance/report.json`). These are foundation checks,
not evidence that the new source type or its whole platform matrix is complete.

Dragonbox 1.1.3 is pinned unmodified, with license/hash inventory and native
distribution notices, so formatting preserves the macOS 13.0 build target.
The accepted 0.23 SDKs are preserved and a genuine language 0.10 SQL/source/graph
fixture was captured using that SDK for the upcoming migration. No old source,
task/proof acceptance intent or archived fixture was rewritten.

## Implemented and exercised

- Toolchain 0.23 / language 0.10 adds exact typed function signatures, named/generic references, higher-order calls, immutable transitive snapshot captures, identity equality, owned cleanup, real native indirect calls and TypeScript snapshot closures. Generic wire constraints exclude actual function payloads from JSON/API while allowing serializable phantom contracts. Native/TypeScript/reference agreement, graph/cache invalidation, callable LLDB/DAP, portable SQL migration and source-free SDK checks passed as recorded below. Custom traits, effect/realm subtyping, mutable captured cells, general async and resource FFI remain pending.

- Toolchain 0.22 / language 0.9 adds typed recursive patterns, result/record/exact-list/literal matching, immutable arm bindings, ordered guards, value matches and bounded matrix coverage/usefulness analysis. Native, interpreter and TypeScript preserve selection/order/cleanup; pure watches demand selected paths. The checkpoint matrix and installed SDK workflow passed as recorded below; OR/rest/range patterns and custom extractors remain pending.

- Toolchain 0.21 / language 0.8 adds builtin generic constraints (`add`, `ordered`, `integer`), parametric capability checking and implication-aware abstract forwarding. Bounds are preserved in graph/context/API projections; unsupported custom traits/associated types/function values remain pending. The current evidence is listed below.

- Toolchain 0.20 adds the Linux container build/verification workflow, LLVM LLD selection for ELF DWARF, selected-linker fingerprints (policy 2) and filesystem-independent artifact streaming. Current Linux evidence is recorded below; other OS/mobile targets and full SDK distribution remain pending.
- Toolchain 0.19 adds read-only native toolchain fingerprint discovery, pinned native task selections, foreign artifact acceptance and trusted-catalog replay. Captured configurations, compiler/dependency fingerprints and explicit SDK settings are checked around child execution. Full external SDK/support-tool/environment capture and foreign execution remain pending.
- C++20 compiler with LLVM/MLIR 22.1.8 and SQLite on macOS ARM64 and Linux ARM64/x86-64.
- Toolchain 0.18 adds explicit native target/SDK/dependency configurations, target ABI probes and architecture-isolated module/runtime caches. macOS arm64/x86_64 cross-compilation is configured; foreign runtime/debugger verification remains pending.
- NEX 0.12 lexer/parser, explicit i64/f64/bool/unit types, functions/recursion, let/var, assignments, branches, loops and returns.
- Multi-file modules, logical qualified identities, import aliases, private/public functions and structures, public API visibility checks and cross-module type/effect/realm checks.
- Local library roots, ordinary NEX `std/math` and `std/text` libraries, dependency source-content locks and explicit lock updates. Cyclic imports and remote retrieval are not supported.
- Validated UTF-8 strings with strict escapes, Unicode scalar indexing/slicing, immutable nested lists and nominal structures with typed fields/constructors.
- Automatic managed-value ownership in native code: borrowed parameters, owned returns, temporary cleanup, assignment/scope/early-return cleanup and normal-exit live-value checks.
- Type, mutability, effect, execution-realm and test-definition checks.
- Left-to-right evaluation, logical short-circuiting and checked integer arithmetic in both interpreter and native output.
- Reference interpreter with resource limits and observable output preservation on failure.
- Checked AST/function graph, BLAKE3 identities, SQLite revision history, call edges, import/export and stable logical module/local-name function IDs across entry modules.
- Optimistic function-replacement transactions across multiple files that reject stale HEAD and invalid candidate bundles without committing.
- Complete archived source bundles for each revision, independent of changed/deleted live files or libraries, and relocatable directory export with vendored dependency sources and a generated manifest/lock.
- Structure layouts in semantic revision identity and referenced type definitions in bounded LLM context. Graph database schema migration and explicit language migration preserve old sources/history.
- MLIR verification/conversion, LLVM IR translation, object generation and native linking with preserved intermediate artifacts.
- Whole-program cache with compiler/runtime/profile/source identity and executable integrity check.
- CLI commands for init, discovery, language guides, checking, evaluation, tests, build/run, IR, graph/context/history/patches/import/export and LLDB launch.
- Default NEX tests compare interpreter and native execution. Generated native binaries run independently of the development compiler.
- Immutable entry/imported build source projections and packaged macOS debug symbols. LLDB resolves NEX function symbols and source lines, including library files; the 0.8 checkpoint adds typed parameters/locals, lexical scopes and runtime previews.
- Model-independent language specification, EBNF, system prompt, patch schema, pack manifest and JSON CLI protocol.
- SDK installation with compiler, runtime and language pack; installed tools retrieve their matching guides outside the source checkout.
- Toolchain 0.4.0 adds a TypeScript backend without changing source-language 0.3: checked BigInt arithmetic, Unicode scalar operations, nominal equality, immutable frozen values and scope/evaluation semantics are preserved.
- Browser application contract using ordinary pure initial/update/view/title functions and `std/web.nex` view/event structures, React rendering, controlled form inputs, explicit actions and history/route events.
- `nex web` project generation and real `nex build --target web` package installation/typechecking/Vite asset builds, exact npm lock, bundled runtime notices and complete asset-tree cache integrity checks.
- Client reachability excludes server/unused function bodies and literals from generated source and Vite source maps. Browser and native semantic tests are separate from Playwright interaction checks.
- Toolchain 0.5.0/source language 0.4 add immutable `result<T>`, recoverable error codes/messages and strict typed JSON across interpreter/native/TypeScript. Wire i64 values are canonical decimal strings; duplicate/unknown/missing fields, invalid Unicode and excessive input are rejected.
- Native host archives for selected reachable code and version-matched C++ request scopes. Generated frames unwind traps to a host boundary; budgets, deadlines/cancellation and scope cleanup apply to normal and failing native requests.
- Server-only `io` environment access and `db` capability, prepared SQLite operations, durable per-principal KV data, read-only requests, serialized writer transactions, sticky mutation failure and rollback on non-success/trap/cancellation. The table layout and binary key/principal collation are checked.
- Native HTTP/HTTPS server builds with cpp-httplib/OpenSSL, strict hashed-bearer configuration, identity injection, bounded workers/queue/body/URI/time, sanitized errors, static assets with canonical containment and coordinated shutdown.
- Runtime component object caches with integrity checks and captured source/header projections. Native build metadata identifies output kind and runtime components; embedded JSON/HTTP components retain their license notices alongside output, including explicit `-o` copies.
- Explicit language 0.3→0.4 migration of archived multi-file revisions, retaining both old history and complete sources. New walkthrough/task-template files explain model-independent handoff and the graph/source distinction; they do not implement automatic task contracts or prove cross-model quality.
- Toolchain 0.6.0 retains source language 0.4 and adds the optional pure `commands(before, after, event)` browser entry, `std/net.nex` command/response types and a bounded same-origin HTTP adapter. Response events preserve strict JSON/i64/UTF-8 semantics; network/timeout/cancel/limit failures are explicit values. Existing four-function applications still work.
- A connected client/server example shares public models and supports runtime bearer sign-in, durable per-user task CRUD, URL filters, refresh/cancel, sign-out/re-entry and stale-response rejection. No credentials are embedded by the build or retained across page reload in this example. General source async remains pending; the following checkpoint adds generated endpoint helpers.

- Toolchain 0.7.0/source language 0.5 adds checked endpoint declarations with unique methods/routes/operations, authenticated Context, public wire models, bounded schemas, stable graph IDs/handler edges, endpoint context and atomic declaration/function patches. nex.program/4 identities include contracts; old 0.4 bundles require explicit migration and retain history.
- `nex api` generates and checks frozen server/client projects before atomic materialization. Server routers strictly decode input and encode tagged result/status responses under existing request transactions. Client SDKs extract only required public model declarations and pure request/response helpers. Typed commands validate successful response data before callback delivery. OpenAPI 3.1.1 and exact NEX wire contracts accompany output; fixed routes/JSON are implemented, while path/query parameters and streaming remain open.

- Toolchain 0.8.0 retains source language 0.5 and adds standard MLIR/DWARF types, stack locations, parameter records and lexical binding scopes. Direct LLVM slots and hidden prologue initialization keep source breakpoints and variable ranges accurate. Debug parameter storage borrows values and does not participate in owned cleanup. LLVM module verification runs after translation.
- Native builds capture a versioned debug manifest, original/projected paths, reachable logical/native function mapping and matching LLDB formatter. Previews read stopped values without inferior function calls, use lazy children and bound recursion/item/node/text work. `nex-values` exposes bounded revision-attributed JSON; `nex debug --json`/`--kind dap` generate lldb-dap session settings. Cache validation includes source projections, manifest, formatter and macOS DWARF contents.

- Toolchain 0.9.0 retains source language 0.5 and compiles reachable NEX functions as separate source-module objects. Body-only changes reuse unaffected module objects; consumed function interfaces, effects and transitive record layouts invalidate their consumers. A dependency index records direct/reverse calls and layout providers, including type-only modules. The frontend still checks the loaded graph; finer function/frontend reuse, cross-unit LTO and test-result caching remain open.
- Native object inputs include the compiler's probed target ABI/data layout, profile, runtime ABI, consumed semantic contracts and exact immutable source projection. Content-addressed objects and IR are verified before use and published through atomic indexes; corruption triggers repair. Shared frozen source projections preserve imported-module debugging across unrelated edits and archived builds. `compilation.json` records unit inputs, dependencies and reuse; CLI counters describe the current invocation. The build guide and model-independent language pack document these contracts and limits.

- Toolchain 0.10.0 retains source language 0.5 and instruments reachable native functions in profile builds. Local reports record monotonic inclusive/self/max wall times, calls/completions/aborts, bounded timeline events and managed shallow object/handle allocation pools. Selected graph name/content matching supplies project-local node IDs; a separate link unit embeds exact build/revision identity without invalidating reusable NEX modules. Debug/release output omits the profiler.
- The pinned unmodified Tracy 0.14.1 client supports explicit localhost CPU-zone and named memory-pool capture, with matching distribution notices. Normal local profile reports leave Tracy dormant. Request-boundary cleanup and runtime traps close active frames; report limits and dropped records are explicit. The installed profile guide, descriptor, prompt, protocol and example document measured coverage and pending browser/GPU/dynamic-buffer work.

- Toolchain 0.11.0 retains source language 0.5 and adds snapshot-bound JSON scalar contracts plus linked Z3 verification. Pure i64/bool/unit roots use pre/postconditions, checked arithmetic/assertion VCs, path-sensitive acyclic body expansion and annotated inductive loops with strict nonnegative rankings. Division/remainder encode NEX truncation and MIN/-1 cases explicitly; short-circuiting, argument order, mutable bindings and nested shadows retain source rules.
- Contracts bind the semantic revision, exact source bundle, qualified function content and loop coordinates. Reports distinguish proven, concrete/inductive counterexamples, inconsistent preconditions, unknown, timeout and unsupported scope. Each run saves source/contract/query/result artifacts; graph node IDs come from the selected store. Proofs do not remove runtime guards or insert JSON pre/postconditions into execution. Heap/effect/resource proofs and recursion remain open; task-acceptance linkage is added by the 0.12 checkpoint below.

- Toolchain 0.12.0 retains source language 0.5 and adds model-independent `nex.task/1` contracts: reviewed goals/requirements, qualified graph bindings, target/check linkage, pinned test bodies and formal property intent. Checks cover native/TypeScript differential tests, builds, exact native/reference observations, scalar proofs, effects/realms, defined profile budgets and API generation. Unknown kinds/fields are rejected; unsupported targets/realms, unproven checks, output limits, timeouts and interruptions cannot pass acceptance. Static graph linkage is not dynamic coverage or proof of natural-language completeness.
- Task runs freeze checked multi-program source bundles, derived proof contracts and the selected runtime/lib/web/debug resources without changing project HEAD. Checkpointed receipts, logs, artifacts and SQLite history retain candidate/task/compiler identity. Replay validates every captured input, exact compiler and matching trusted executable resources, rebuilds derived workspaces and reruns checks after live source deletion. Named POSIX process groups clean ordinary descendants on timeout, output overflow, SIGINT/SIGTERM and normal leader exit. External tools/environment are not fully frozen, deliberate process-group escape is outside cleanup, and this is not an OS sandbox or signed attestation.

- Toolchain 0.13.0 retains source language 0.5 and evaluates pure stopped-frame NEX expressions through the existing parser, module resolver, checker and reference interpreter in a separate process. Arithmetic, Unicode, immutable aggregates, result/JSON operations and pure user calls preserve source semantics; frame realm/import visibility and effect restrictions remain checked. Snapshot decoding is lazy for unexecuted short-circuit branches. Expression/step/value-growth/wire budgets fail explicitly. The shared strict JSON validator rejects duplicate/escaped-equivalent keys and malformed UTF-8 before frame normalization, while retaining existing application wire behavior.
- LLDB commands `nex-eval` and `nex-frame` capture exact referenced roots through DWARF and read-only memory access, including long UTF-8 strings and embedded NUL, validating tags/nominal names/field order. Innermost bindings and requested frames are respected; incomplete roots are unavailable, never fabricated zeros or clipped evaluator inputs. The frozen stdio NEX DAP bridge supplies watch/hover evaluation, immutable computed children/paging, independent backend/computed references and stop expiry. Encoded internal commands prevent source newlines becoming debugger commands. At the 0.13 checkpoint large-root partial reads were pending; 0.14 adds the aggregate projections below. Current live coverage remains macOS ARM64/libc++; other host layouts, browser watches and an installed editor extension remain pending.

- Toolchain 0.14.0 retains language 0.5 and the native runtime ABI. Interpreter-only references carry stopped-frame list/record/result paths through pure calls, aliases, constructors, loops and branches. Lengths, nominal layouts, result tags and dynamically selected fields/elements are requested only when evaluated. Whole-value operations still require complete bounded operands; strings and direct large-root DAP paging remain open.
- `nex.debug-frame/2` adds exact shape/value captures and `inspect --kind demand` returns a typed missing-read request for a fixed source/stop. Legacy full `/1` frames remain accepted. The frame validator rejects ill-typed paths, duplicate reads, conflicting full bindings and invalid shapes/wire values. Exact vector reads validate raw begin/end pointers and DWARF element sizes; LLDB location errors never become fabricated empty collections. The live provider checks stop/selection before and after each read and bounds replay to 128 exchanges/ten seconds. Saved partial frames fail explicitly for uncaptured data.

- Toolchain 0.15.0 adds persistent local-store identities for checked parameters, blocks, statements and expressions, separately from Merkle content hashes and deterministic function-content/path site keys. Structural children, lexical binding references (including shadowing initializers/assignments) and qualified call references are exposed through paged `operations`/operation-context queries and an additive graph export. Conservative matching retains unambiguous roles/content, preserves recorded revisions and gives fresh identities to ambiguous duplicates. Imports rederive local identities from checked sources; cross-store reconciliation is pending.
- SQLite schema 2 upgrades transactionally to 3 without changing archived sources, revision hashes, language versions or function IDs. Current-language operation metadata backfills lazily and verifies stored content/site hashes. Candidate identity changes share the checked source transaction. Query pages/children and large-definition omission are explicit. Native MLIR NameLocs, compiled manifests and reachable TypeScript maps carry deterministic sites; `eval` failures add persistent IDs/revision/exact-source hash, and TypeScript trap sites carry the same key. `nex-operation` exposes source-position candidates in actual LLDB/DAP stops. Native optimized instruction identity, native textual trap IDs and operation profiling remain open; language 0.5/function/program/native runtime formats are unchanged.

- Toolchain 0.16.0 / source language 0.6 adds nominal algebraic enums with immutable typed payloads and exhaustive statement matches across the checker, reference interpreter, native MLIR and TypeScript. Scrutinees run once; pattern scopes, discard bindings, all-path returns, effects/realms and cleanup retain source semantics. Recursive enum/record/list values and strict tagged JSON work across backends. API generation extracts public enum models and emits wire/2 descriptors and exact OpenAPI oneOf schemas; typed browser responses reject invalid cases/payloads before event delivery.
- New canonical formats are function/4, enum/1 and program/5. Explicit 0.5→0.6 migration preserves archived sources/history and local function IDs. Runtime-view/2 and debug-expression/2 describe the added enum ordinal. Matching LLDB views validate the actual stopped tag/name/layout; pure match helpers demand only used selected-case payloads, and DAP computed enum children support paging. Operation case identities anchor on names across declaration reordering and nominal layouts invalidate native consumers. Old SDK 0.15 is retained for language 0.5 frames/receipts. Match expressions, nested patterns/guards, builtin result patterns, general user generics and richer data proofs remain pending.

- Toolchain 0.17.0 / language 0.7 adds parametrically checked generic functions, structures and enums, including unused bodies, argument/expected-type inference, finite recursive specialization and explicit resource diagnostics. Every instance carries its source template/arguments. Native/TypeScript use concrete code and retain checked arithmetic, evaluation order, immutable values, effects/realms and cleanup. Generic constraints, higher-kinded types and function values remain pending.
- Function/5, structure/3, enum/2 and program/6 distinguish checked source definitions from derived specializations; source revisions exclude instances. Context links non-editable instances to editable templates; atomic template repairs recheck all callers. Source export emits original declarations once. Native generic body edits reuse unchanged callers while concrete layouts/type arguments participate in dependencies. Public generic API extraction preserves phantom arguments/imports and emits checked wire/2/OpenAPI models. Generic watches resolve frame type arguments and instantiate uncompiled pure helpers without changing revision/stop state. Runtime-view/2 is unchanged; exact matching compiler/resources are still required. Task requirements link actual instances back to their source templates, while profile budgets retain concrete measured names. SDK 0.16 is preserved for old language 0.6 archives, frames and receipts.

## Verification evidence

- **0.23.0 / language 0.10** passed **230 cases in all 24 CTest suites** on macOS ARM64 in 311.20 seconds. Linux ARM64 and emulated Linux x86-64 each ran 230 declared cases: 224 executed and six explicit macOS-SDK skips. Their full CTest runs passed in 383.11 and 1310.15 seconds. Source/build/install verification and logs are retained under `build/linux-ARCH/checkpoints/0.23.0`; macOS evidence is `build/ctest-023-portable-final.log`.
- The installed SDK passed all nine maintained handoff phases on macOS ARM64, Linux ARM64 and Linux x86-64, in 38.247, 29.533 and 101.223 seconds respectively. Linux's second container has no `/src` mount and external network disabled. All 60 indexed resources and seventeen guides are present. The scenario exercises reviewed task failure, fixed-intent graph repair/import, generic snapshot closures and wire roundtrips, native/reference/TypeScript agreement, standalone output, profile attribution/cleanup, archived replay/export, scalar Z3 proof and an actual locked Vite build. Mac/Linux ARM64 additionally verify actual archived callable DAP and offline replay after source deletion. Linux x86-64 records live debugging false. Reports: `build/sdk-handoff-023-verified/report.json` and each Linux `source-free-sdk.json`.
- Installed macOS LLDB/DAP passed the large-capture callable case in 9.241 seconds. Linux ARM64 passed all six live suites, including eleven callable cases in 34.383 seconds. Both validate native function symbols, lazy reads through an unread 32,768-item capture, alias identities, generic closure scopes, source-deleted snapshots, DAP pages and stop expiry. The current closure-state web build passed Chromium, Firefox and WebKit interaction (three cases, 2.2 seconds). Browser dependencies/notices are unchanged. Evidence: `build/sdk-callable-dap-023.log`, Linux `live-function_debug.log`, and `build/function-web-023-browsers.log`.
- Genuine SDK 0.22 archives verify successful 0.9 migration and atomic rejection/explicit wire-bound repair, preserving original source/history and function/operation IDs. The SQL-only fixture path executes on macOS too; its legacy sidecar lacks a database field, so the reader defaults to graph.db without changing archived bytes. The first failed ARM64 and intentionally interrupted x86-64 reports are retained under `evidence-023-*`, superseded by the complete passing runs. SDK 0.22 still inspects its frame and replays its receipt; SDK 0.23 rejects those with E_DEBUG_BUILD/E_TASK_COMPILER. Task/proof pin updates assert unchanged source hashes, clauses, loops and acceptance intent; current schemas pass independent jsonschema 4.23 validation. See `build/version-010-old-sdk-compatibility.json`, `build/version-010-acceptance-pin-migration.json` and `build/version-010-schema-evidence.json`.


- **0.22.0 / language 0.9** passed **201 cases in all 22 CTest suites** on macOS ARM64, most recently in 256.01 seconds after the SDK handoff addition. Linux ARM64 and Linux x86-64 each passed 195 executed cases plus six macOS-SDK skips, in 358.20 and 733.94 seconds respectively; x86-64 executes under Docker emulation. Linux ARM64 also passed the five opt-in live debugger suites, including all 14 matching cases. The installed macOS SDK passed all 14 matching cases; an additional actual NEX DAP matching check passed separately. Evidence: `build/ctest-022-handoff.log`, `build/sdk-matching-022.log`, `build/sdk-matching-dap-022.log` and the Linux `checkpoints/0.22.0` reports/logs.
- The maintained installed-SDK scenario `tools/sdk_acceptance.py` passed its nine phases on macOS ARM64 and both Linux architectures. Linux runs in a second container with only the read-only SDK and fresh evidence mounted, `/src` absent and external networking disabled. All three perform an actual locked TypeScript/Vite build. macOS/Linux ARM64 additionally launch actual NEX DAP/LLDB after original source deletion, evaluate a nested match, capture its partial frame, exit normally and evaluate the saved frame offline. Linux x86-64 explicitly records live debugging false. The workflow requires failure of the wrong reviewed task, then unchanged-task-hash acceptance after graph repair, independent graph import, native/reference/TypeScript agreement, profile content/node attribution and balanced managed pools, archived task replay/export and the installed scalar proof. Expected failure is recorded as `not_satisfied`, never acceptance. All 56 indexed resources and sixteen guides are installed. See `build/sdk-handoff-022-verified/report.json` and Linux `source-free-sdk.json`; negative checks retain old evidence and reject an available forbidden source path (`build/sdk-acceptance-negative-022/verification.json`).

- Toolchain **0.21.0 / language 0.8** passed **188 cases in 21 CTest suites** on macOS ARM64 in 338.48 seconds, and 182 executed cases plus six macOS-SDK skips on each Linux target: ARM64 in 395.66 seconds and x86-64 under Docker emulation in 760.43 seconds. Eleven new normal cases cover builtin bounds, rejected unused/forwarding programs, contextual literals, arithmetic traps, immutable values/order/cleanup, canonical bound order, optimistic graph patches/archives, genuine 0.7 migration, bounded API model extraction, pure watch/scalar proof and pinned task repair/replay. Evidence: `build/ctest-021.log` and the Linux `checkpoints/0.21.0` reports/logs.
- Installed SDK constraint checks passed **12 cases** on macOS ARM64 and Linux ARM64, including real LLDB generic parameter scopes, an uncompiled string helper, rejected bad bounds and unchanged stop state. Linux additionally passed all seven debug, 23 expression and fifteen generic live-suite cases. The pack contains **52 indexed resources** and fifteen guides. A bounded generic browser-state/counter example passed TypeScript/Vite compilation and all three Chromium/Firefox/WebKit interaction cases, with the existing dependency lock unchanged. Evidence: `build/sdk-constraints-021.log`, Linux ARM64 `live-*.log`, `build/constraints-web-build-021.json` and the generated Playwright results.
- Both Linux 0.21 installed-SDK workflows passed with external network disabled: constrained and ordinary generic native/interpreter/TypeScript agreement, strict ELF DWARF, standalone output, profiles, pinned tasks/archived replay, scalar proof and authenticated persistent storage. Separate source-free containers passed project creation, bounded examples, backend agreement and archived execution after source deletion. All 52 indexed files/fifteen guides were synchronized without changing the tested compiler bytes. Evidence: `build/linux-ARCH/checkpoints/0.21.0` and `build/sdk-resource-verification-021.json`.
- Actual **0.20/language 0.7 → 0.21/language 0.8** migration preserved archived sources, history, function IDs and operation IDs after live-source deletion. The preserved 0.20 SDK still evaluated its original frame and replayed its original receipt; 0.21 rejected these with `E_DEBUG_BUILD`/`E_TASK_COMPILER`. Task/proof example snapshot metadata was regenerated while retaining reviewed pre/postconditions, loop invariants and acceptance assertions. Current schemas/examples and Linux SDK task/configuration/catalog documents passed independent jsonschema 4.23 validation. Evidence: `build/sdk-constraints-migration-021.json`. The 0.20 SDK is preserved on macOS and both Linux architectures.

- Toolchain **0.20.0 / language 0.7** passed all **20 CTest suites** on macOS ARM64 (177 cases, no skips, 289.30 seconds), Ubuntu 24.04 ARM64 (171 executed, six macOS-SDK skips, 253.44 seconds) and Ubuntu 24.04 x86-64 under Docker emulation (171 executed, the same six skips, 268.37 seconds). Both Linux runs declare 177 cases; historical 0.5/0.6 migration assertions execute using genuine old-SDK store fixtures instead of attempting to launch Mach-O binaries. Evidence: `build/ctest-020-final-formatter.log` and the retained aggregate `build/milestone-020-verification.json`; retained Linux SDK evidence is under `checkpoints/0.20.0`, while rolling Linux logs now describe the current checkpoint.
- Installed Linux SDK workflows passed on both architectures with external network disabled: all **51 indexed resources** and fifteen guides, generic native/interpreter/TypeScript agreement, strict ELF DWARF verification, standalone execution without NEX/LLVM/Z3 dependencies, measured profiles, pinned task acceptance and archived replay after source deletion, scalar Z3 proof, authenticated per-principal SQLite isolation and restart persistence. Streaming artifact copies also passed native/task/replay checks on Docker/macOS shared storage. Actual task, normalized toolchain and catalog documents passed independent jsonschema 4.23 validation. Separate containers with **no source checkout mounted** created/tested projects, ran native/TypeScript generic tests, executed archived revisions after live-source deletion and ran a copied standalone binary. Evidence: each `build/linux-ARCH/sdk-smoke.json`, `source-free-sdk.json` and `build/linux-schema-validation-020.json`.
- The installed macOS ARM64 and Linux ARM64 SDKs each passed **seven debugging, 23 expression and fifteen generic cases** with real LLDB/DAP; these totals include the corresponding normal cases. They cover source stops/steps, shadows/mutation, exact/partial values, pure watches, large aggregate paging, enum/generic children, archived inspection and clean resume. A Linux libstdc++ summary truncated embedded NUL; length-aware bounded reads fixed it. The new live case verifies short/long NUL strings, literal escape preservation and a UTF-8 scalar crossing the 4096-byte preview boundary. Evidence: `build/live-{debugging,expressions,generics}-020.log` and the Linux ARM64 `live-*.log`. Linux x86-64 live ptrace/debugging remains unverified under emulation.
- Identical Linux objects linked with GNU ld failed strict DWARF string-offset verification; LLVM LLD passed. The bad ELF/intermediate objects and comparison are retained under `build/linux-arm64/debug-evidence`. A separate direct-Clang probe reproduced literal-percent output-path failure, fixed by staging ELF/archive output before streaming it to the destination. Selected linker configuration/hash/cache invalidation and Unicode/percent-path archives linked into a trusted C++ host are regression-tested. Fingerprint policy is now `nex.toolchain-snapshot/2`; old receipts require their captured compiler binary/resources, and changing SDKs requires reviewing/re-pinning new toolchain hashes.

- Toolchain **0.19.0 / language 0.7** passed **175 cases in 20 CTest suites** in 238.96 seconds. Eight task-toolchain cases cover non-executing inspection, stable normalized default/explicit inputs, pinned host native/test/run/profile acceptance, real foreign application/archive output, source-deleted replay with replacement trusted configurations, unsupported foreign execution, compiler/SQLite/OpenSSL/SDK-setting changes, missing current trust and paired schema fields. A rehashed forged receipt cannot select another compiler, and a successful child cannot pass when post-execution fingerprint inspection detects changed inputs; independent checks continue. Evidence: build/ctest-019.log.
- The installed **0.19 SDK** passed all **eight task-toolchain cases** outside source projects in 59.739 seconds. A separate installed-resource workflow loaded all **46 indexed resources**, inspected host/Intel configurations, checked pinned task intent, accepted host tests/application plus an actual x86_64 archive, then replayed the same task after deleting original sources/task/config files using equivalent current trusted configurations. Actual task/catalog/normalized configurations passed independent JSON Schema validation. Evidence: build/sdk-task-toolchains-019.log and build/sdk-task-smoke-019.json. SDK 0.18 is preserved in build/sdk-0.18.0. Full SDK contents/support tools/environment and Intel execution remain outside the verified scope.

- Toolchain **0.18.0 / language 0.7** passed **167 cases in 19 CTest suites** in 190.87 seconds, including six native-target cases. Real x86_64 macOS builds cover generic/JSON programs, release/profile output, every generated/runtime object, static archives and dSYM architecture, cache separation/warm reuse, archived reconstruction after source deletion and SDK SQLite headers/stubs. Rejected cases cover unsupported targets, malformed configurations, mismatching compiler ABI, host dependency fallback and foreign execution commands. Host compiler symlink mode and Darwin/macOS normalization are exercised. Evidence: build/ctest-018.log.
- The installed **0.18 SDK** passed **15 generic cases**, including actual host LLDB/DAP, in 68.141 seconds. A separate project outside the checkout loaded all **45 indexed resources**, discovered the target capabilities/schema, passed host native/TypeScript tests, ran with matching reference output, produced x86_64 executable/library artifacts and rebuilt an archived Intel revision using its native object after deleting its source/build directory. The actual toolchain file and its schema passed independent jsonschema validation. Intel native execution/debugging remains unverified: Rosetta is unavailable. Evidence: build/sdk-generics-live-018.log and build/sdk-targets-smoke-018.json. The previous 0.17 SDK is preserved in build/sdk-0.17.0.

- The final 0.17 build passed **161 cases in 18 CTest suites** in 173.35 seconds. Fourteen generic cases cover parametric rejection of unused invalid bodies, recursive type/function instances, native debug/release/reference/TypeScript equality, implicit/explicit/contextual inference, operator result-vs-operand constraints, unwrap/intrinsic/condition/index propagation, phantom/private types, scopes/aliases/evaluation order, finite expansion limits, abstract-entry rejection, qualified-argument shorthand, template graph repair/archives, actual 0.16 migration, generic API model extraction, watch-only instantiation, scalar instance proofs, native provider/caller reuse, and template-linked task/profile/replay. Evidence: build/ctest-017-final.log.
- A real generic-state app passed TypeScript/Vite production compilation and three Playwright interaction cases (Chromium, Firefox, WebKit). Installed SDK LLDB/DAP verified concrete T scopes, exact Box<i64> captures, uncompiled pure helpers, computed children, same-stop/handle preservation and archived offline inspection after source deletion. Evidence: build/generic-web-build-017.json and build/sdk-generics-live-017.log. These are macOS ARM64/headless engine checks; other hosts remain unverified.
- Installed **0.17.0 SDK / language 0.7** passed an outside-checkout workflow with fourteen guides and 44 indexed resources. A bad first<T> failed pinned native/browser acceptance; a source-template patch preserved its operation ID, fixed all instances, and passed/replayed the same task intent, including a concrete-instance profile budget. Export contained templates once, archived execution survived live source deletion, and standalone native output did not link LLVM/Z3. Generated nested Box<Maybe<i64>> models crossed an authenticated real HTTP server with exact i64 bounds, strict invalid-input rejection, repeated trap cleanup and recovery. Actual 0.16→0.17 migration retained old source/history/function/operation IDs; the preserved 0.16 SDK replayed its old frame/receipt, while 0.17 rejected that receipt. Independent jsonschema 4.23 validation covered installed schemas/responses and nested generic OpenAPI data. Evidence: build/sdk-generics-smoke.json and retained artifacts.

- Installed **0.16.0 SDK / language 0.6** passed an outside-checkout authoring workflow with fourteen guides and 42 indexed resources: wrong enum dispatch failed pinned acceptance, an optimistic graph patch kept operation identity and fixed native/TypeScript output, and the same task intent passed and replayed after source deletion. Installed LLDB captured exact enum paths and pattern bindings at the same stop; offline inspection and exported source tests remained usable. Actual 0.15→0.16 migration retained old sources, function IDs and operation IDs. Preserved SDK 0.15 evaluated its old frame and replayed its old receipt, while 0.16 rejected that receipt with E_TASK_COMPILER. Three real installed protocol responses independently passed Draft 2020-12 JSON Schema validation; generated OpenAPI and valid/invalid enum instances passed separate jsonschema 4.23 checks. Standalone native output did not link LLVM/Z3. Evidence: build/sdk-enums-smoke.json and retained artifacts.
- The complete expression suite with real LLDB/DAP passed **23 cases in 52.742 seconds**, including six live cases. The separate existing native-debug suite passed all six cases (three live) in 25.991 seconds. These cover unchanged string/record/result previews, exact/partial captures, scopes, stop identity, huge aggregates, child paging and clean resume/termination with runtime-view/2.

- The 0.16 build passed all **147 cases in 17 CTest suites** in 169.38 seconds. Eight enum cases cover recursive values, native debug/release/reference/TypeScript agreement, evaluation order and single scrutinee evaluation, fallthrough/return/loop ownership, immutable aliasing, discarded/shadowed bindings, negative coverage/type/effect/realm/visibility programs, special payload field names, exact JSON/depth boundaries, actual 0.15 SDK migration and persistent case identities/native cache invalidation. API checks add generated enum clients/OpenAPI and live authenticated strict input/trap/recovery cleanup. Partial watch tests reject bad tags and prove unused scalar/aggregate payloads are not demanded. Evidence: build/ctest-016.log.
- The enum-state application passed real TypeScript/Vite production compilation and all three browser interaction scenarios (Chromium, Firefox, WebKit), exercising each case, Unicode text, pure transitions and reload. A real stopped LLDB/DAP session validated pattern bindings, selected enum payload reads, a large unread payload, paged computed enum children, identical stop/handle identity and offline replay. Evidence: build/enum-web-build-016.json, build/enum-live-016.log; these are macOS ARM64/headless engine checks, not wider platform certification.

- `cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug` and `cmake --build build -j 4` succeeded.
- `ctest --test-dir build --output-on-failure -j 3` passed all sixteen suites on 17 October 2026: **137 cases** in 157.95 seconds. They comprise 19 core, 13 module/lock/snapshot/migration, seven result/wire/native-host, seven storage, two HTTP/HTTPS, seven TypeScript/web, two browser-command, eight endpoint/API, three native debug metadata/cache/session, eight incremental-compilation, six profiling, ten verification, fourteen task-acceptance, sixteen expression, twelve operation-graph and three DAP-transport cases. Core tests include negative programs, generated arithmetic/Unicode oracles, debug/release traps, ownership, graph conflicts/cache integrity and LLDB source lookup. Native/TypeScript/interpreter result/JSON tests cover strict inputs and identical errors, including canonical decimal integers, Unicode scalar validation and the single optional leading UTF-8 BOM; the pinned vendored-header hashes and copied license notices are checked. Command tests exercise pure transition agreement in TypeScript/interpreter and a shared-realm native projection, signature/library-shape rejection, atomic batch rejection and transport limits/UTF-8/cancel/timeout behavior in Node.
- Expression checks cover scalar/aggregate/result/JSON semantics, exact integer wire values, shadow/context metadata, alias/private visibility and realm/effect gates, arithmetic/bounds traps, lazy unavailable inputs, source integrity after deletion, purity/step/allocation/token limits and native/TypeScript/reference observations. Raw/escaped duplicate frame keys, malformed UTF-8 and optional leading BOM are checked before normalization. DAP transport tests cover bounded UTF-8 framing, source encoding, reverse-request identity and monotonic terminate-disconnect sequencing after client EOF. Partial-capture checks additionally cover large logical lengths, dynamic helper indices, nominal/nested paths, result tags without unused payloads, pure loops/constructors/aliases, complete-value materialization, malformed paths/shapes and missing/invalid captures. The large fixture has equal native/TypeScript/interpreter observations. The final full run includes all three transport cases.
- Twelve operation cases verify editing/reordering/insertion, distinct duplicate identities and conservative rematching, parameter roles, lexical references, historical lookup/reversion, database backfill and stale-patch rollback, foreign derived-ID rejection, semantic annotation equivalence, cross-entry library identity, a 2,000-declaration unchanged function, paging/omission, native MLIR manifests and matching interpreter/TypeScript failure keys. The browser regression now checks all four error-site items against interpreter diagnostics across twelve arithmetic/bounds cases. Four actual installed query/context/export responses independently passed Draft 2020-12 validation with jsonschema 4.23.0 (`build/operations-schema-015.json`).
- Ten opt-in live cases passed: two operation LLDB/DAP cases in 4.596 seconds, five expression cases in 16.135 seconds and three legacy debugging cases in 5.093 seconds. Source-site candidates resolve to archived persistent operations after source deletion without resuming or mutating the inferior. Existing stops/steps, Unicode/NUL, shadowing, large-value projections, computed child pages, nonselected frames, source encoding, stale-reference failure and clean termination still pass on macOS ARM64/libc++.
- The installed **0.15.0 SDK/language 0.5** passed an outside-checkout workflow with fourteen guides and 41 indexed files. A deliberately wrong adjustment returned 43. Exact LLDB source-site/Watch evidence resolved its graph operation; a revision-checked repair retained the persistent ID while changing content/site keys and produced 42. The unchanged reviewed task hash/tests/output criteria then passed native/TypeScript acceptance and replay after original source deletion. Actual NEX DAP candidates resolved to the repaired graph, and the old operation/frame remained queryable. A copied binary ran independently without LLVM/Z3 links. The preserved 0.14 SDK still evaluated its prior partial frame. A project created and run by the actual 0.14 compiler then upgraded under 0.15 with the same semantic revision, source/functions, function IDs and output, plus the new operation index. Evidence: `build/sdk-operations-smoke.json` and its retained external workspaces; the old SDK is retained at `build/sdk-0.14.0`. These are host checks, without cross-platform or general performance certification.

- The installed **0.14.0 SDK/language 0.5** passed an outside-checkout debug/repair/acceptance workflow with all thirteen guides and 38 indexed files. Watch observed 85 in an intentionally wrong imported helper; a revision-checked graph repair produced 84 under the same captured inputs and unchanged task hash/tests/output criteria. One native module compiled and one was reused. The old partial frame/source snapshot still computed 85 after the graph changed and original files were deleted. The installed NEX DAP bridge evaluated the repaired archive and expanded typed records; task replay passed after deletion, and a copied binary ran with the exact reviewed output without LLVM/Z3 links. Evidence: `build/sdk-expression-014-smoke.json` and its retained external workspace.
- A second installed-SDK workspace exercises the large fixture through actual LLDB and NEX DAP: a 32,768-string list, record/result projections and a 2 MiB unread error message. The saved last-element frame is 1,144 bytes with three exact captures; it still evaluates after source deletion. Whole-list/message evaluation explicitly fails its capture limits. Stop identity and the physical list handle stay unchanged, paged computed children work, and the copied binary runs without LLVM/Z3 links. Evidence: `build/sdk-partial-smoke.json`. Both actual installed partial frames and both schema definitions passed independent Draft 2020-12 validation with jsonschema 4.23.0; raw and escaped-equivalent duplicate capture keys were independently rejected by the installed compiler (`build/partial-schema-014.json`). These are macOS ARM64 host checks, not cross-platform certification or a latency guarantee.

- Task tests exercise fixed-intent repair, changed-test/property rejection, no-execution preflight and HEAD preservation, candidate rebinding, multi-program archived selection and conflicting shared modules, independent failure propagation, unsupported scope, Unicode/zero bytes/exit status, profile budgets, exact replay after source deletion, input/resource injection rejection, timeout/output/interrupt checkpoints and real owned-grandchild cleanup. A real Vite application, native HTTP server, archive and generated API/OpenAPI are copied as artifacts; server-only code is absent from browser assets. The task schema/example independently passed Draft 2020-12 validation with jsonschema 4.23.0.
- `python3 tests/debugging.py build/nex --live Live` passed the three additional actual LLDB/DAP/bounded-preview cases in 4.550 seconds for 0.12; the three ordinary debug cases also passed in the full CTest run.
- The installed **0.12.0 SDK/language 0.5** passed an outside-checkout acceptance workflow with all twelve guides and all 34 indexed files. Seven checks/four requirements failed the deliberately broken candidate, then passed a revision-checked graph repair without changing the reviewed task hash, pinned tests or formal pre/postconditions. The original raw proof sidecar remained stale as expected; task-derived metadata was checked separately. Clean exported sources passed native/interpreter/TypeScript tests, a copied binary ran independently without LLVM/Z3 links, and all criteria passed again after original source/task/proof deletion. History retained failure, success and replay receipts. Evidence: `build/sdk-task-smoke.json` and its retained external workspace.
- Scalar verification tests cover branch/call contracts, actual overflow and negative-result counterexample replay in interpreter/native/TypeScript, signed division/remainder and MIN boundaries, short-circuit safety, nested loop invariants/rankings/shadowing, consistency and definedness of preconditions, stale/archived/exported sources with independent graph node IDs, unsupported heap/effect/recursive/missing-loop rules, resource exhaustion and SMT-LIB replay through the actual Z3 CLI. The example proves both increment and loop-based double contracts. The detached JSON schema and example independently passed Draft 2020-12 validation with jsonschema 4.23.0.
- A separate difficult nonlinear postcondition under a 1 ms solver query budget returned timeout with reason timeout; its exact source/contract/SMT/report artifacts remain under `build/verification-timeout-evidence`, indexed by `build/verification-timeout.json`. Resource-limit exhaustion returns unknown in default tests; neither status is accepted as a proof. This records the exercised host response, not a stable timing requirement for other solvers/hosts.
- Profiling tests check observable native/interpreter/TypeScript agreement, recursion/early returns, checked traps, exact graph node/content attribution, event limits with preserved aggregates, archived object reuse and Unicode/percent paths, a bounded 100-function CLI response with a complete 121-function saved report, pinned client inventory/notices and dormant release output. A real four-thread native host exercised normal/error/budget/cancellation requests: all 40 outer and 32 inner calls were balanced as completed/aborted, and every managed allocation was freed.
- Three direct Tracy captures passed with the application listener ready before capture. Upstream 0.14.1 capture/csvexport read the three NEX functions with matching call counts and frozen paths; a separate reader using upstream TracyServer verified the exact embedded build/revision identity, 402 handle allocations/frees and 321 shallow object allocations/frees, with zero active allocations/usage. Evidence: `build/tracy-profile-acceptance/acceptance.json` and its saved traces/CSV. Starting capture before the application listener was ready sometimes failed the initial handshake on this host; the verified startup ordering is documented. Viewer/capture tools remain external to SDK installation.
- Reproducible `tests/profile_benchmark.py` measured nine whole-process samples per mode for the same 50,000 checked-add workload on the host Apple M4 CPU. Observed medians were 2.589 ms in release, 2.778 ms with dormant instrumentation and 7.329 ms with local aggregation/timeline storage disabled. All results and exact call counts matched. These measurements include process launch/report flush and apply only to this workload/host; no general speed or overhead guarantee is claimed. Evidence: `build/profile-benchmark.json`.
- Incremental tests observe actual Clang object-compilation calls as well as build reports. They cover cold/warm builds, body-only edits, effects and return ABI changes, parameter renaming, nested record/JSON layout dependencies, library locks and archived reuse, profile/compiler/runtime inputs, incompatible target rejection, corrupt objects/indexes/local artifacts and concurrent applications sharing a module at Unicode and percent-containing paths. Changed behavior agrees with the interpreter, clean native builds and relevant TypeScript tests.
- Endpoint tests cover rejected declarations, stable graph identity/context, atomic patches, archived generation, explicit 0.4→0.5 migration, transitive model extraction, output atomicity and native HTTP authentication/status/rollback behavior. SDK projection tests include overridden standard libraries and package dependencies: server declarations and unused private code are absent while required client/shared helpers and nominal models remain. OpenAPI output was independently checked against the official OpenAPI 3.1 meta-schema with jsonschema 4.23.0; signed i64 boundaries and trailing line-terminator rejection were also checked with JSON Schema validation.
- The generated typed API client passed **12 Playwright scenarios** (four each in Chromium, Firefox and WebKit) against its compiled generated native dispatcher, including CRUD/isolation/restart persistence and cancellation, malformed schemas, canonical integer strings, optional leading BOM, strict UTF-8, body limits, redirects and timeouts. The latest generated application's Playwright result records `status: passed` with no failed tests. These are macOS headless engine checks, not real-device certification.
- The installed **0.7.0 SDK/language 0.5** passed the temporary-project smoke workflow with all seven matching guides, the documented graph repair and native/TypeScript tests, archived execution after source deletion, endpoint generation/model extraction/context/client transitions, and an independently running authenticated persistent generated native server. The current report is `build/sdk-smoke.json`.
- Native C++ host checks unwind generated-frame traps, bound loops/deadlines/cancellation and verify zero live handles/values across concurrent scopes. Storage checks include principal partitioning, rollback on traps/ignored mutation failure, read-only protection, incompatible schemas and concurrent increments without lost updates. HTTP checks cover trusted self-signed TLS/hostname verification, auth before body reading, oversized-body rejection, malformed models, concurrent creates, trap/budget/timeout rollback, static symlink containment, persistence across restart and shutdown cancellation while a writer transaction is active.
- `nex run examples/arithmetic.nex --json` produced `55\n3628800\n` with exit code 0.
- `nex run examples/modules/main.nex --json` matched the interpreter: `{"name":"NEX","tags":["native","web"]}\nnative + web\n10\n`, exit code 0. All three loaded application/standard-library tests passed in interpreter and optimized native modes.
- `cmake --install build --prefix build/sdk` succeeded for 0.3. In a temporary project outside this checkout, with `NEX_RESOURCE_DIR` set to the installed resources, all four matching guides loaded, the module example passed all three interpreter/native tests in release mode, interpreted/native output matched, its executable ran independently, and the saved revision still ran after both project source files were deleted.
- A separately compiled data example with AddressSanitizer/UndefinedBehaviorSanitizer enabled for its C++ runtime finished with identical output, no reported errors, and zero live managed values. This is a runtime-path check, not a claim that every generated LLVM instruction was sanitizer-instrumented.
- `python3 tests/debugging.py build/nex --live` passed all **six cases** in 17.704 seconds: the three normal debug cases and three additional live LLDB/DAP/bounded-preview cases. Real host launches outside the execution sandbox verified typed parameters at function entry, stopping before a declaration initializer, both shadowed values, scope exit, mutation, source stepping, imported frames, stack inspection and normal program exit. Archived debugging continued after original source deletion. An actual Xcode lldb-dap verified DAP breakpoints, scopes, variables, expandable record children, read-only `nex-values` through its REPL and clean resume/exit. A shared nested collection representing a very large logical tree exercised lazy children and bounded previews. These checks cover macOS ARM64/Apple LLDB with libc++; other debugger hosts remain unverified.
- The installed **0.8.0 SDK/language 0.5** passed an outside-checkout debug smoke check: all eight matching guides and every indexed document/example were present; installed example tests agreed in interpreter/native/TypeScript; the debugger captured the exact installed formatter; archived debugging after original source deletion showed typed shadowed values and completed normally. The separate current report is `build/sdk-debug-smoke.json`.
- The installed **0.9.0 SDK/language 0.5** passed an outside-checkout incremental smoke check with all nine guides and every indexed document/example. A cold module example compiled four objects; a warm build reused four. A model-body edit compiled one and reused three, with matching native/interpreter output and passing native/interpreter/TypeScript tests. After deleting the original sources, old build directory and shared source cache, the archived revision reused all four objects, restored its exact output and supported real LLDB inspection of a typed imported parameter through normal exit. Evidence: `build/sdk-incremental-smoke.json`. This single-host example observed 952 ms for a cold build and 279 ms for the body edit; these are not general performance guarantees.
- The installed **0.10.0 SDK/language 0.5** passed an outside-checkout profile smoke check with all ten guides and every indexed document/example. Installed profile output agreed with interpreter/native/TypeScript tests and a separately copied executable ran without NEX resources, retaining notices. After deleting live sources, the old build and source cache, the archived build reused its module, restored frozen files and retained exact node attribution/output. An installed instrumented HTTP/SQLite server handled authenticated Unicode CRUD and clean shutdown with balanced measured object/handle pools. Evidence: `build/sdk-profile-smoke.json`; temporary servers, credentials, databases and projects were removed/stopped.
- The installed **0.11.0 SDK/language 0.5** passed an outside-checkout verification smoke workflow with all eleven guides, contract schema and every indexed document/example. It proved the installed scalar/loop contracts using Z3 5.3.1, found the overflowing input, applied a revision-checked graph repair and proved the reviewed replacement contract. Stale contracts were rejected; native/interpreter/TypeScript behavior agreed. Exported and archived source snapshots remained verifiable after live source deletion, and independent graph IDs were attributed correctly. A copied native program ran without compiler resources and did not link Z3/LLVM; solver resource exhaustion stayed unknown. Evidence: `build/sdk-verification-smoke.json` and its retained proof artifacts. Z3 is an external development/compiler dependency, not a generated-application dependency.
- `nex build examples/web/main.nex --target web --profile release --json` succeeded with Node 22.22.3/npm 10.9.8, TypeScript 7.0.2, React/React DOM 19.3.1 and Vite 8.3.4.
- `tests/web_build.py` performed real npm/TypeScript/Vite builds outside the checkout. It verified that a server-only sentinel was absent from all assets and source maps, cache hits worked, a corrupted asset triggered a successful rebuild, `-o` copied standalone assets, and an archived revision still built after source deletion.
- Playwright 1.64.1 passed 18 production interaction cases (six each on Chromium 156.0.8078.4, Firefox 157.0 and WebKit 27.2) and three additional development-module rejection cases, one per engine. Production runs skip those direct-module cases and execute them in the separate development run. Scenarios cover Unicode input, add/toggle/delete, immutability-visible transitions, URL/back/reload navigation, keyboard submission/activation, escaped markup and mobile-width layout. macOS WebKit's native Option+Tab traversal is used under its default link-focus preference. These are headless engine checks on macOS ARM64, not real-device/browser-release certification.
- The installed 0.4.0 SDK was checked in a temporary project with `NEX_RESOURCE_DIR` explicitly pointing to installed resources. It exposed the matching web guide/prompt, ran both shared/client example tests, generated a locked application, built release browser assets with notices, and rebuilt the archived revision from cache after source deletion. Both debug (unminified) and release Vite builds were exercised.
- Desktop/mobile screenshots of the actual compiled example were inspected: `build/nex-web-preview.png` and `build/nex-web-preview-mobile.png`. The temporary screenshot server/browser were stopped afterwards.
- The installed **0.5.0 SDK/language 0.4** passed a separate temporary-project check with explicit installed resources. All six guides and every indexed document/example were present. The exact `llm/WORKFLOW.md` program first failed its intended assertion, then its revision-checked JSON patch passed native and TypeScript tests, built/ran with `144` output and exported to a runnable source project. Installed result/JSON tests agreed in all three backends and archived output still ran after source deletion. A server built entirely with installed resources ran independently, retained notices and verified authentication, user isolation, restart persistence and clean shutdown. Evidence: `build/sdk-smoke.json`; temporary projects and servers were removed/stopped. This exercises the workflow deterministically; no cross-provider LLM trial is claimed.
- `examples/fullstack/client.nex` built with locked npm packages and TypeScript checking. `tests/fullstack_browser.py` passed **12 scenarios** (four in each installed engine) against its compiled native API: real CRUD/reload/URL navigation/credential changes, isolation, cancellation/stale replies, network/schema/invalid UTF-8/size/real redirect/timeout failures and recovery, followed by persistence after native server restart. A local forwarding fixture provides a genuine same-origin redirect because WebKit cannot synthesize a 302 with route.fulfill; it confirmed that redirect targets were not fetched. All fixture/server processes stopped cleanly and temporary credentials/databases were removed. The build excluded the server sentinel and runtime-issued tokens from all assets/maps.
- After the 0.6 adapter change, real legacy web build/cache tests passed again: package/type/asset builds, excluded server data, cache hit, corrupted-asset recovery, standalone asset copy and archived-source build after source deletion. The npm lock and bundled dependency notices are unchanged.
- The legacy UI also passed its 21 browser checks again on the 0.6 adapter (18 production interactions plus three development rejection checks). Together with the connected example this gives **33 passed browser scenarios**, independent of the 56 default integration cases.
- The installed **0.6.0 SDK/language 0.4** passed the outside-checkout smoke workflow again. It includes every indexed document/example and matching guides, `std/net.nex`, the transport adapter and the shared-model full-stack sources. The installed client passed interpreter/TypeScript transition tests and generated reachable client output without the server sentinel. The repair/export/result/JSON/archive/native-server persistence checks also passed. Latest report: `build/sdk-smoke.json`. `nex doctor` confirmed toolchain 0.6.0, language 0.4 and the host ARM64 target.

## Required work still open

1. Add richer types, more reusable libraries, resource ownership/lifetimes, external interfaces and asynchronous/concurrent work. Modules, local dependency pinning, strings, immutable lists/structures and their automatic ownership are implemented; they do not complete these remaining capabilities.
2. Extend the endpoint contract where required: typed path/query parameters, streaming/resource bodies and schema compatibility. Explicit contracts now generate server dispatch, typed client helpers, wire descriptors and OpenAPI; the connected example uses these with runtime credentials and durable per-principal data. Application-specific CSS/assets/components, direct NEX source-map chains, broader session/account flows and the optional Wasm path remain open.
3. Extend the operation graph with module/type identities, cross-store reconciliation and revision-checked operation edits. Add finer frontend/function reuse, cross-unit LTO, deterministic test-result caching, stronger cross-project identity/import handling and richer graph edits. Source-module object reuse and dependency-aware invalidation are implemented.
4. Extend debugging with string chunk reads, direct large-root paging, precise optimized-operation attribution, crash/core workflows and additional host verification. Persistent source-operation IDs/candidates, demand-driven list/record/result projections, pure source-expression inspection and a stdio NEX watch adapter are implemented; editor extension packaging and browser watches remain open. Typed parameter/local inspection, bounded runtime previews and LLDB/DAP interaction are implemented on the exercised host. Native function/managed shallow allocation profiling, graph attribution and Tracy capture are implemented on the exercised host. Extend measurements to dynamic buffers, browser/GPU/system events and broader statistical comparisons.
5. Extend task contracts with dynamic coverage, dependent/generated-program steps, richer provenance and broader agent editing/search operations. Run measured cross-model authoring trials. The prompt/protocol pack is available; cross-provider success and token savings have not been measured.
6. Extend the implemented scalar Z3 subset with recursive summaries, richer data/memory/resource proofs and source-level contract/runtime enforcement. Detached snapshot-bound contracts, checked scalar arithmetic, inductive loops/rankings, explicit unproved statuses and trust boundaries are implemented; they do not prove the whole compiler/application chain.
7. Package portable SDKs, extend the verified Linux chain to broader distributions and physical x86-64 hardware, and implement/verify Windows, mobile SDK targets and native UI/GPU adapters. Finish external dependency capture and compatibility/migration procedures. macOS x86_64 cross-build artifacts are checked on ARM64; macOS Intel execution and Linux x86-64 live debugging remain unverified.

Next implementation steps include finer incremental compilation, broader profiling, optimized operation attribution/string chunks and large-root paging and the remaining target platforms, while maintaining the typed API/browser chain. Keep `describe`, specification, interpreter, both backends and tests synchronized as features are added. The full original objective remains open.
