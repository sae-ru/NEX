#!/usr/bin/env bash
set -euo pipefail
if [[ $# != 5 ]]; then
  echo 'usage: build.sh configure|build|test-scoped|install SOURCE BUILD INSTALL_ROOT LLVM_PREFIX' >&2
  exit 2
fi
mode=$1
source_dir=$(cd "$2" && pwd)
mkdir -p "$3" "$4"
build_dir=$(cd "$3" && pwd)
install_root=$(cd "$4" && pwd)
llvm_prefix=$(cd "$5" && pwd)
export PATH="$llvm_prefix/bin:/usr/bin:$PATH"
export CC=clang AR=llvm-ar RANLIB=llvm-ranlib RC=llvm-windres
export MSYS2_ENV_CONV_EXCL=PERL5LIB
export MSYS2_ARG_CONV_EXCL='--prefix=;-DENGINESDIR=;-DMODULESDIR=;-DOPENSSLDIR=;-DINSTALLTOP=;-DOPENSSLBIN='
cd "$build_dir"
case "$mode" in
  configure)
    perl "$source_dir/Configure" mingw64 shared zlib-dynamic \
      enable-camellia enable-capieng enable-idea enable-mdc2 enable-rc5 enable-rfc3779 \
      --prefix=/clang64 --libdir=lib --openssldir=etc/ssl \
      '-DOPENSSLBIN=\"/clang64/bin\"' -fstack-protector-strong
    ;;
  build) mingw32-make -j4 SHELL=/usr/bin/sh ;;
  test-scoped)
    mingw32-make -j4 SHELL=/usr/bin/sh VERBOSE=1 test \
      TESTS='test_conf test_provider test_x509 test_evp test_ssl_test_ctx test_store'
    ;;
  install)
    mingw32-make -j1 SHELL=/usr/bin/sh install_sw install_ssldirs DESTDIR="$install_root"
    ;;
  *) echo 'unknown build mode' >&2; exit 2 ;;
esac
