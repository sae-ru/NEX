# Runtime scalar contracts

This example's reviewed contract requires a nonnegative input smaller than
I64_MAX and promises `result == x + 1`. Its pins match these exact sources.

From this directory, using development toolchain0.152:

```sh
nex verify --contracts contracts.json --json
nex contract --kind runtime --contracts contracts.json --directory /tmp/nex-runtime-guarded --json
cd /tmp/nex-runtime-guarded
nex test --json
nex test --target web --json
nex run --profile release --json
```

The application prints `5`. Calling the generated increment with a disallowed
input traps with E_ASSERT before its body. Runtime generation checks a distinct
source revision and does not itself prove the contract. Retain original source,
reviewed contract and tests; preserve the receipt with generated distributions.
See [the guide](../../docs/runtime-contracts.md) for scope and overhead.
