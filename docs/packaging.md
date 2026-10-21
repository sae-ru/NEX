# Native application packages

```sh
nex package main.nex --directory /new/my-app --json
nex package server.nex --target server --directory /new/my-server --json
/new/my-app/bin/app
```

`package` checks and builds the selected program, using the release profile by
default. `--profile`, `--entry`, `--revision`, `--toolchain` and
`--build-directory` have their native build meanings. Packaging runs on macOS
for Mach-O and Linux for ELF. It does not execute the application. Assembly
success reports `execution_verified: false`; test the relocated artifact on
the intended execution host. A macOS cross-build remains a cross-build.

The output must not exist. Assembly uses a sibling staging directory and
publishes the completed directory after dependency and signature checks.
Failures retain that stage and the compiler's request for diagnosis, without
replacing an existing destination. The package contains:

- `bin/app`: the native executable or HTTP/HTTPS server.
- `lib/nex/host`: its required non-platform dynamic libraries and Linux SONAME aliases.
- `licenses`: full notices for the libraries actually copied.
- `THIRD_PARTY_NOTICES.txt`: the generated runtime's matching notices.
- `application.json`: `nex.application-package/1`, identifying the source revision,
  build key, compiler build, target, profile, input hash and packaged file hashes.

No compiler, LLVM, Python, Node, source tree or development SDK is needed to
execute a completed package. macOS system libraries or the matching Linux GNU
loader/glibc remain host prerequisites. GNU C++/GCC runtimes resolved from
`/lib`, `/lib64`, `/usr/lib` or `/usr/lib64` remain platform prerequisites.
Copies resolved from private compiler prefixes are captured with their complete
notices and origin-relative paths, including SONAME aliases. Their version
definitions are not reported as version requirements. Recorded symbol
requirements are diagnostic data; they do not establish compatibility with an
untested distribution/OS. macOS copies receive ad hoc signatures; Developer ID
signing, notarization, GUI application bundles and installers remain pending.

Assembly requires Python 3.9+, the matching platform inspection tools, and
`patchelf` on Linux. These are packaging tools, not application dependencies.
Linux paths must not contain a colon, which is an ELF search-list delimiter.
Only copies are rewritten; original binaries/libraries remain unchanged.

Libraries from a bundled NEX SDK use that SDK's component inventory and complete
notices automatically. Their actual bytes must still match `sdk-bundle.json`.
For developer builds or external dependencies, declare full provenance using
`--notices FILE` (`nex.sdk-notices/1`, described in [the SDK guide](sdk.md)).
Linux can additionally read installed Debian/Ubuntu copyright and package
metadata with `--dpkg-notices`. Missing provenance fails assembly; it is never
silently omitted. Only used components enter the application package. The
manifest retains input hashes without local source/SDK installation paths.

Runtime configuration is supplied after packaging. For a server:

```sh
/new/my-server/bin/app --auth /private/auth.json --database /data/app.sqlite \
  --cert /private/server.pem --key /private/server.key --port 8443
```

Credentials, keys, databases, environment variables and browser assets are not
implicitly copied. Package browser `dist` separately and pass its deployed
location with `--static`. Use `build --target web` for browser assets; `package`
rejects web/interpreter/library targets and `--output`/`--kind`/application
arguments. Full-stack deployment bundles and mobile/Windows installers remain
pending. The source language and runtime semantics are unchanged by packaging.

## Trusted native modules

```sh
nex package main.nex --foreign host.json --notices notices.json \
  --directory /new/application --json
/new/application/bin/app
```

Toolchain 0.43 accepts explicit operator grants for reachable external calls on
a matching macOS/Linux host target. Only reachable logical libraries and exports
enter the deployed catalogue; unused catalogue entries are not deployment inputs.
The original inventory and recursively discovered native loader dependencies
form self-contained code bundles. Complete component notices are captured beside
them and covered by the application inventory.
Already inventoried native images keep their relative paths. System libraries
remain host prerequisites. Provenance is required for every copied external
file, including the original module. Assembly never calls a module entry point.

Relocating native images changes their bytes. Each prepared module therefore
gets a new manifest hash. The compiler edits only the exact reachable manifest
literal tokens in a derived source bundle, rechecks it and verifies that its
semantic revision differs only by those pins. Original and derived revisions
are saved in the graph store without moving HEAD or editing source files. A
package's `revision` is the derived revision actually compiled; its
`foreign_projection.source_revision` identifies the original reviewed program.
The projection records both source hashes, each changed binding, original/new
bundle pins, dependency inventories and component notices. Language 0.15 and
C ABI 1 remain unchanged.

Module image identity is preserved: aliases of one original pin share native
state, while distinct original pins remain separate even when relocation makes
their code bytes identical. Each code bundle has an inventoried
`source_identity_file` containing its original manifest SHA-256 and a newline.
Additional distribution notices are stored at catalogue scope, so differing
component labels or license paths do not split a shared module image. A
preparation report with `notices_root:"catalogue"` uses catalogue-relative
component notice paths; older reports without that field retain bundle-relative
paths. Original notice members stay in their original module inventory.

Binary/notice capture is bounded to 128 MiB and 8190 files, including discovered
dependencies and generated source identity members. Each notice member is at
most 64 MiB. Module ABI 1 still limits each code bundle to 128 members and
256 MiB, including its identity member. Generated catalogue/report metadata is
additional to the capture file count.

`foreign/host.json` grants only selected exports and preserves the operator's
module quota. The native executable resolves it relative to its actual executable
location, including invocation through a symlink or from another working
directory. Explicit `--nex-foreign` (CLI) or `--foreign` (HTTP) remains available
for operator configuration; environment variables cannot grant module access.
Source pins and signatures still have to match the compiled derived program.
HTTP authorization and request-scoped owners are unchanged; the catalogue and
module directories must remain outside the HTTP static root.

The package includes a hash-checked capture of the prepared catalogue and bytes;
assembly rejects input changes after compilation. Component notice paths in
`application.json` include both application libraries and module bundles.
The internal `tools/foreign_bundle.py` preparation stage produces
`nex.foreign-package/1`; it alone is not a compiled application package.

Native modules are trusted code. Dependency discovery follows Mach-O load
commands or ELF DT_NEEDED entries; it cannot infer arbitrary `dlopen` strings,
file accesses, external services or credentials used by native code. These must
be supplied and tested explicitly. Cross-target foreign-module assembly,
Windows/mobile packaging, stable ABI validation and general callbacks remain
pending. Current execution evidence is recorded in `STATUS.md`.

The indexed package schemas use canonical URI references. Register their local
SDK documents by `$id` in an offline schema registry before validation.

## Deployment acceptance fixtures

```sh
python3 SDK/share/nex/tools/application_acceptance.py --sdk SDK --output /new/evidence
python3 SDK/share/nex/tools/application_acceptance.py --probe /new/evidence \
  --report /new/execution.json
```

Preparation compiles numeric, SQLite and HTTPS fixture packages and generates
test-only credentials/certificates beside them, without running the applications.
An unbundled development SDK can use `--notices` or Linux `--dpkg-notices`.
The separate probe verifies every package file, actual native numeric/storage
output, HTTPS authentication, principal isolation and restart persistence.
It writes its own execution report without changing assembly manifests.

For the strongest Linux check, build `tools/linux/ApplicationRuntime.Dockerfile`
and mount only `packages`, `fixtures`, this standalone probe and a writable report
directory into it. Do not mount SDK, source or build-input directories. Use
`--network none` and pass `--require-runtime-only` to the probe. It rejects
visible NEX/Clang/GCC/CMake/Node/npm tools and checks actual ELF library resolution.
Python is the test driver; applications run with an environment containing no
NEX/SDK configuration. Record the image ID, architecture and emulation status
with the resulting report. This verifies those fixtures on that runtime, not
arbitrary applications or other operating-system versions.

## Checked multi-component projects (candidate0.76)

`nex project --kind package --configuration NAME --directory NEW_DIRECTORY`
packages declared native binary edges and browser distributions together. See
[project builds](project-build.md). A plain file `nex package` retains its source
workflow. Project packages have relative entries and file inventories in
`project.json`; shared images use exact compiler-owned provenance while external
libraries still require their real notices. Assembly remains separate from
execution, graph history and deployment.

Candidate0.84 extends the same preparation/provenance rules to declared
macOS/Linux project architectures. `project --kind package --foreign HOST.json`
projects exact manifest literals consistently across shared/source/archive
components while preserving actual binary edges. Each app receives only its
reachable grants. Original files, lock and graph stay unchanged; source/derived
identities are retained in `nex.project-foreign-projection/1`. See
[project packaging](project-build.md#foreign-project-packages-candidate084) and
[package tasks](project-tasks.md). Deployment-image debug/core provenance stays
pending; an assembled package still needs destination execution checks.
