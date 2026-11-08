# Selected ELF runtime libraries — development 0.162.1

NEX uses the selected SQLite and OpenSSL files for native linking. Linux also
needs their SONAME aliases at execution: an absolute linker input such as
`/opt/vendor/lib/libssl.so.3.5.9` can produce a `DT_NEEDED` entry named
`libssl.so.3`.

The standalone and component-image link paths share one runtime-directory
planner. It reads the selected ELF dynamic tables without loading those
libraries, preserves their actual SONAME bindings and uses separate linker
arguments for every directory. First-party `$ORIGIN` paths on component images
retain their existing position.

For example, SQLite can come from `/usr/lib64`, while OpenSSL comes from a
private prefix. If `/usr/lib64` also contains `libssl.so.3`, sorting the two
directories alphabetically would select that copy first. The private OpenSSL
directory must precede `/usr/lib64`, even when the two library files have equal
bytes: their paths and packaging provenance are distinct.

For each selected shared library, its SONAME alias in the selected directory
must resolve to that library or contain the exact same bytes as a regular-file
copy restored from an archive. A missing or mismatched alias returns
`E_TARGET_LIBRARY`. Each other selected directory containing that SONAME must
come later. Independent directories retain deterministic lexical order.

If one configured directory must precede another for OpenSSL, while the reverse
is required for SQLite, there is no consistent search order. The compiler
returns `E_TARGET_LIBRARY` rather than substituting either selected dependency.
Use consistent runtime directories or a complete assembled SDK.

Static archives contribute no runtime search directory. Direct ELF inputs
without SONAME retain their absolute linker binding. Linux dynamic selectors
must be direct ELF images; GNU linker scripts are not expanded by this planner.
ELF directory names cannot contain `:`, the loader's search-path separator.
Darwin's existing directory order and Windows's separate DLL rules are unchanged.

This is a build-time check of the selected runtime inputs. Packaging still
inspects the actual dependency closure, checks file hashes and requires the
corresponding notices. Filesystem changes after building and general transitive
loader isolation remain outside this check.

The implementation introduces no source syntax, effects, canonical-format or
language-version change: language 0.28 and its graph history remain intact.
Discover the compiler's actual contract with:

```sh
nex describe --field native_runtime_search --json
```

The maintained metadata tests use actual LLVM-produced ELF32/ELF64 images in
both byte orders. Their full-source-test prerequisite is LLVM22.1 Clang,
`llvm-ar` and ELF `ld.lld`. If ELF LLD is installed separately from Clang,
configure `-DNEX_ELF_TEST_LD=/absolute/path/to/ld.lld`; the test remains registered
when that prerequisite is missing. This does not replace the independently
selected Wasm linker. A Linux-only test additionally executes a small native
program, retains the failing alphabetic-order control, and requires the selected
libraries to produce the expected result. These tests do not replace full source,
native NEX application, packaged or installed SDK acceptance. The immutable
0.162.0 SDK and its recorded results keep their original identity.

The [0.162.1 development evidence](evidence/native-runtime-search-0.162.1-2026-11-08.json)
records the macOS full301 source run, Linux metadata/loader controls and actual
source-deleted NEX shared/archive/HTTP packages. Linux's complete303 invocation
passed299 groups and failed4 when the selected private OpenSSL copies lacked
explicit test notice data. All5 command vectors affected by that configuration
correction passed on the unchanged source, compiler and dependency bytes; the
other298 vectors were unchanged. This gives exact union303 while preserving
the original failed invocation. Ordinary installed smoke also passed.

The [Fedora 0.162.1 follow-up](evidence/fedora-0.162.1-native-packaging-2026-11-08.json)
passed both ELF groups and the four previously failing packaging groups. After
closed old native outputs were cleaned, the HTTP source group passed with the
same compiler and dependencies. Ordinary installed smoke then passed native,
reference and TypeScript execution, source-deleted graph/task replay, shared
tasks, bounded scalar proof and authenticated storage across server restart.
The interrupted invocation and controller setup failures remain recorded.
All-target/full303 and portable Fedora SDK acceptance remain pending.

The fresh Windows0.162.1 compiler built all targets and passed12 native/reference
C11/CXX20 history pairs in moved Python3.10 and archive-restored Python3.14 SDKs.
Those checks verify the fixture's selected target/sysroot and preserve all16
graph tables. Complete matching SDK delivery and current physical-platform
acceptance remain pending. The separate
[Windows workflow observer](windows-appcontainer-qualification.md) supports an
explicit outer workflow ceiling and refuses packaged roots before execution.
Its calibration does not qualify NEX execution or replace SDK checks.
