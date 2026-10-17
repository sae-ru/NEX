# Snapshot-bound scalar verification

Toolchain 0.11 links Z3 to check an explicit subset of existing NEX 0.5 semantics. The first contract format is a separate versioned JSON document. It is tied to the semantic revision, exact complete source bundle and function content hashes. It does not change source syntax, execution behavior or graph identity. No language migration is needed for this tooling addition.

```sh
nex contract examples/verification/main.nex --symbol increment -o /tmp/increment.json
# Review/edit the generated preconditions and postconditions.
nex verify examples/verification/main.nex --contracts /tmp/increment.json --json
```

`nex contract --symbol NAME` produces a scaffold for one fully qualified function and its loop coordinates. An empty precondition list and `ensures: ["true"]` request only execution safety, with no useful result property. Loop scaffolds require an invariant and decreases expression before they can be proved. Copy function entries into one contract document to verify several roots or provide annotations/preconditions for called functions. `--revision HASH` selects archived sources. Regenerate and review contracts after source edits: even comment/location changes invalidate the exact-source hash. Generating against live source and against a stored revision can select different source projections of the same semantic revision; keep the contract and source projection together.

```json
{
  "schema": "nex.verification-contracts/1",
  "language": "0.5",
  "expected_revision": "CURRENT_SEMANTIC_REVISION",
  "source_hash": "EXACT_SOURCE_BUNDLE_HASH",
  "functions": [{
    "symbol": "verified::increment",
    "content_hash": "FUNCTION_CANONICAL_HASH",
    "returns": "result",
    "requires": ["x < 9223372036854775807"],
    "ensures": ["result == x + 1"],
    "loops": []
  }]
}
```

The generated hashes are actual compiler values; the strings above are explanatory placeholders. `returns` binds a non-unit result under a fresh identifier distinct from parameters; it is empty for a unit result. Preconditions see parameters. Postconditions see original parameters and the result binding, not function locals. Loop predicates see the bindings in scope at the identified `while` header. Coordinates are one-based byte columns in that function's logical source file; the mandatory exact-source hash prevents an old coordinate from silently referring to another loop.

Predicates use the NEX expression parser with integer/bool literals, scalar variables, unary `-`/`!`, arithmetic, comparisons, equality and `&&`/`||`. Calls, strings, collections and field/index access are outside this initial predicate subset. Predicate expressions follow the same checked i64 arithmetic, truncation toward zero and left-to-right/short-circuit rules as source. They are not unbounded mathematical-integer expressions. Preconditions are evaluated in order: each expression must be defined for all inputs satisfying previous preconditions, then its truth restricts the admitted inputs. For example `requires: ["x != 0", "10 / x > 0"]` has an explicit division guard; `requires: ["10 / x > 0"]` fails contract definedness at zero. Postcondition and invariant expressions also generate definedness obligations.

## What a successful result covers

For selected pure scalar roots, `proven` means that all well-typed i64/bool inputs satisfying the checked preconditions satisfy all generated obligations: source arithmetic does not overflow or divide by zero, source assertions hold, normal returns satisfy the declared postconditions, and supported loops terminate by their supplied ranking. Both branches and all integer values in the input domain are considered. No runtime checks are removed after verification. The standalone interpreter still has a step/call budget, native requests still have deadlines/budgets/cancellation, and those resource failures are outside the proof.

The implementation models i64 values as Z3 integers with explicit signed bounds and an obligation at every checked source/predicate operation. Signed division is encoded through nonnegative magnitudes and sign restoration, rather than assuming SMT integer division matches NEX. The `MIN / -1` trap and `MIN % -1 == 0` are distinct. It preserves left-to-right arguments and skips right-hand safety obligations on short-circuited paths.

Pure i64/bool/unit function bodies are fully inlined into proof conditions; a callee's preconditions must be established at each call site, and its body/postconditions are checked in that context. Unchecked summaries are never assumed. Recursion or depth above 32 is `unsupported`, including syntactically present recursive calls in unreachable branches. Heap parameters/results/operations, effects and external operations are also `unsupported`. The complete loaded program is type/effect/realm checked before verification, while the proof covers only selected roots and their traversed bodies.

For a loop such as the `double` example, an annotation can be:

```json
{"line": 8, "column": 3,
 "invariants": ["i >= 0", "i <= n", "total == i * 2"],
 "decreases": "n - i"}
```

Use coordinates from `nex contract`; the numbers here illustrate the fields. The verifier proves invariant initialization, then replaces variables assigned by the loop with arbitrary bounded values, assumes the invariant and checks one iteration. Nested/local shadows do not count as writes to outer bindings. It proves invariant preservation and a nonnegative ranking at every iteration that strictly decreases at each back edge. Returns inside loops instead check the function's postconditions. A missing invariant/decreases rule is `unsupported`. This is an inductive proof, not bounded loop unrolling.

## Results and evidence

The CLI returns `nex.verification-session/1`, with at most 32 non-success obligation details per function. `output` points to a full `nex.verification/1` report. The run directory retains the exact contract, complete source bundle, per-obligation SMT-LIB queries and solver/model results. There is no proof-result cache; every invocation checks again. Queries contain the configured solver resource/timeout settings and can be rerun with a matching `z3 QUERY.smt2` CLI. Graph node IDs are taken from the selected project's current store, not trusted from the contract.

Function statuses are `proven`, `counterexample`, `inconsistent_preconditions`, `unknown`, `timeout` or `unsupported`. Any status other than `proven` gives a nonzero CLI result. Contradictory preconditions never become a successful proof through vacuity. Counterexample inputs/locals use decimal strings for i64 and JSON booleans. `concrete_input` can be replayed against a wrapper calling the root with those inputs; failures can concern a declared contract as well as an execution trap. `inductive_state` refers to an arbitrary invariant/loop state and need not be reachable from the root inputs: it shows a failed proof rule, not necessarily a concrete application bug.

Defaults are 2,000 ms per solver query, Z3 resource limit 1,000,000 and a 30-second run budget. Use `--solver-timeout MS` (1..60,000), `--resource-limit COUNT` (1..100,000,000) and `--timeout SECONDS` (1..300). Other bounds are 64 root contracts, 64 clauses per list, 4,096 bytes per predicate, 64 loop annotations per function, 4,096 obligations per function, 256 active symbolic paths, 50,000 symbolic steps and 8 MiB per emitted query. Limits are reported explicitly and exhaustion is not success. These are work/output limits, not an OS memory sandbox for the solver.

The proof trusts Z3 and this verifier's translation/VC rules. It does not prove the parser/checker, reference interpreter, MLIR/LLVM/TypeScript backends, runtime memory ownership, external libraries, compiler implementation or platform SDKs correct. Runtime checked arithmetic/assertions and native/interpreter/TypeScript tests remain necessary. Contract predicates are verification metadata; they are not automatically inserted as runtime pre/postcondition checks. Source-level contract syntax, general memory/resource proofs, recursive summaries and richer data models remain open work. Toolchain 0.12 links approved pre/postcondition intent to external task acceptance checks; see [tasks.md](tasks.md) for candidate rebinding, reviewed intent hashes and their limits.

## Solver dependency

The compiler needs Z3 development headers/library; generated native/browser applications do not link or execute Z3. Set `-DNEX_Z3_ROOT=/path/to/z3` for a prefix containing `include/z3++.h` and `lib/libz3` or the official distribution's `bin/libz3`. `nex doctor --json` reports the loaded solver version. This host was configured with the official Z3 5.3.1 ARM64 macOS release; its archive SHA256 is `0de02438052952153aab5d1361be4d61b6d226337440356c054d403c959da86b`. Z3 is an external MIT-licensed dependency; its headers/library and configured shared-library location remain prerequisites of this local SDK, as do LLVM/MLIR and other development dependencies. Portable solver/toolchain packaging remains open.
