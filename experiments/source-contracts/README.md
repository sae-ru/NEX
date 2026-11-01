# Explicit028 source-contract example

This requires the explicit version-selected C++ development frontend in
[source-contracts.md](../../docs/source-contracts.md). Ordinary027 CLI and
published0.156 SDK reject this syntax. It is not a delivered028 SDK example.

From a source build, run `build/nex_source_contracts_probe check experiments/source-contracts/main.nex`
and `build/nex_source_contracts_probe reference experiments/source-contracts/main.nex`.
The maintained CTest group `source_contracts` checks reference/TaskIR, native
O0/O2 and strict TypeScript/Node execution plus rejected predicates and loops.
