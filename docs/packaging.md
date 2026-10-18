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
loader/glibc/libstdc++/libgcc runtime remain host prerequisites. Recorded symbol
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
