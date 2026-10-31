# Source this file in WSL after installing the pinned dependencies. It configures
# the Linux producer/tests only; native Windows execution remains separate.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  echo 'Use: source tools/windows/producer-env.sh' >&2
  exit 2
fi
NEX_PRODUCER_REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
NEX_PRODUCER_NODE="${NEX_PRODUCER_NODE:-/home/sae/nex-deps/node-v22.18.0-linux-x64}"
export PATH="$NEX_PRODUCER_NODE/bin:/usr/lib/llvm-22/bin:$NEX_PRODUCER_REPO/build/deps/producer-venv/bin:$PATH"
export NEX_TSC="${NEX_TSC:-$NEX_PRODUCER_REPO/web/node_modules/typescript/bin/tsc}"
export NEX_WINDOWS_TOOLCHAIN_ROOT="${NEX_WINDOWS_TOOLCHAIN_ROOT:-/home/sae/nex-deps/llvm-mingw-20260616-ucrt-ubuntu-22.04-x86_64}"
export NEX_WINDOWS_SQLITE_ROOT="${NEX_WINDOWS_SQLITE_ROOT:-$NEX_PRODUCER_REPO/build/deps/sqlite-windows}"
