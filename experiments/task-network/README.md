# Task TCP kernel experiment

This builds the same private host runtime as the main CMake target, without
LLVM/MLIR or a source compiler. See [the contract](../../docs/task-network-transport.md).

```sh
cmake -S experiments/task-network -B build/task-network -DCMAKE_BUILD_TYPE=Debug
cmake --build build/task-network -j 4
ctest --test-dir build/task-network --output-on-failure
```

Tests need local IPv4/IPv6 loopback sockets; external network access is unnecessary.
For ASAN/UBSAN use a matching compiler-rt and `-fsanitize=address,undefined`; for
TSAN use a separate `-fsanitize=thread` build. Record the actual runtime and host.
No NEX source network calls, source ABI or stable external C++ ABI are enabled.
