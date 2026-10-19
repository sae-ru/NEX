# Scalar browser compute example

This example belongs to the experimental adapter described in `docs/wasm.md`.
Its current validation scope is recorded in `STATUS.md`.

Build to a new directory and copy the committed HTML alongside the four module
artifacts, then serve that directory on localhost:

```sh
nex test examples/wasm/main.nex
nex build examples/wasm/main.nex --target wasm --entry compute --profile release -o /new/calculator
cp examples/wasm/index.html /new/calculator/index.html
python3 -m http.server 8080 --directory /new/calculator
```

Open `http://localhost:8080`. Test `6 * 7`, a value above JavaScript's exact Number
range, overflow, invalid input and a valid computation after an error. Integer
values cross the wrapper as BigInt. This example does not select Wasm as an
automatic optimization for the separate React/TypeScript application backend.
