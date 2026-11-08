# Windows OpenSSL path corrections

These patches address two observed failures in OpenSSL3.6.5 with MSYS2
relocation. A source-deleted NEX FFI replay at a 271-character path terminated
in `__stack_chk_fail` during SHA256 initialization. Correcting that buffer then
exposed UTF-8 truncation in the Windows X509 default directories: an automatically
loaded TLS configuration disappeared when its path exceeded 260 UTF-8 bytes.

`source.lock.json` pins the upstream archive and each redistributed input.
OpenSSL code retains Apache-2.0; pathtools retains Ray Donnelly's CC0 dedication.
NEX-authored corrections use the repository's MIT license. Preserve all notices.

## Reproduce the source cohort

Use a new private directory, the pinned archive, native LLVM22.1 Clang, GNU Make
and a complete compatible Perl. The development build used Clang22.1.8,
Make4.4.1 and Perl5.38.2. Git for Windows needed missing same-version core modules
in a private PERL5LIB; its installed files remained unchanged.

1. Verify the archive and local input SHA256 values against `source.lock.json`.
2. Extract the archive into a new directory.
3. Copy `pathtools.c` and `pathtools.h` into its `crypto` directory.
4. Check and apply the four patches in `apply_order`.
5. Configure in a separate build directory with the native Clang tools on PATH.

Use `CC=clang AR=llvm-ar RANLIB=llvm-ranlib RC=llvm-windres` and preserve
PERL5LIB across MSYS/native Make with `MSYS2_ENV_CONV_EXCL=PERL5LIB`.
Configure `mingw64 shared zlib-dynamic enable-camellia enable-capieng enable-idea
enable-mdc2 enable-rc5 enable-rfc3779`, logical prefix `/clang64`, libdir `lib`,
openssldir `etc/ssl`, a quoted OPENSSLBIN definition for `/clang64/bin`, and
`-fstack-protector-strong`. Preserve these logical path definitions from MSYS
argument conversion. The measured shell recipe and its exact command arguments
are retained with the development receipt.

Build using `mingw32-make -j4 SHELL=/usr/bin/sh`. Run the six upstream recipes
`test_conf test_provider test_x509 test_evp test_ssl_test_ctx test_store` with
`VERBOSE=1 test TESTS=...`; preserve their actual statuses and full logs.
Use `install_sw DESTDIR=/absolute/private/install-root` to install privately.
Retain matching headers, static/import libraries, both DLLs, CLI and provider
modules together. Copy the OpenSSL license, original pathtools notice, both NEX
patches and exact source/build provenance into `share/licenses/openssl`.
Stack protection and configuration/provider loading remain enabled.

## Observed checks and limits

Eight static/shared layout cases passed: short ASCII, UTF-16-short but UTF-8-long
Unicode, long ASCII and long Unicode. Probes checked SHA256, an automatically
loaded TLS1.3 minimum and a legacy provider from the relocated module directory.
Changing only the configuration to TLS1.2 made both negative controls fail.
The old library retained its original long-path stack-smash failure.

The six upstream recipes have a successful exact union. Five passed in the
original invocation. X509 had one text-comparison failure: both the original
signed CLI and the new CLI emitted identical CRLF PEM text, while its fixture
used LF. Scoped recovery normalized only line endings in that comparator,
rejected a one-byte certificate-content mutation, reran X509 and restored the
original recipe. The original invocation remains failed. The full upstream run
timed out under the operator's intentional IPv6 restriction; it is not accepted.

Actual NEX0.162.1 native debug/release FFI tests and direct images passed at a
288-UTF16-unit Unicode path and agreed with reference execution. All16 graph
tables and original artifacts remained intact. Complete Windows SDK acceptance
and arbitrary Windows namespace/UNC paths remain separate.

For SDK assembly select this same prefix with `--windows-openssl-prefix`.
Its native headers/static-library paths must match `nex doctor`. The assembler
captures the selected DLLs, CLI and provider directories with explicit notice
provenance. Complete moved/restored SDK acceptance using ordinary Python;
Store Python is not an accepted root for the private-job supervisor.
