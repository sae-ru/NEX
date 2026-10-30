# Typed-error provenance experiment after NEX0.145

This is a replayable development patch based on commit
`d0b9c23050256eff99593d0aaf83cdf6166fd32b`. It is not a released compiler or SDK.
The ordinary0.145 sources, compiler and full regression remain unchanged.

The prototype carries concrete payload provenance through calls, catches,
rethrow, finalizer replacement and futures. Handler dispatch preserves exact
aggregate projections and skips known mismatched clauses. At most64 concrete
error alternatives are retained; excess alternatives widen to a runtime
obligation. It checks source outcomes before revoking a logical/resource owner,
including unobserved child failures selected during group drain. Owned files are
promoted using the existing atomic resource-transfer mechanism, with an explicit
source actor and the correct receiving job/scope. Packet retention alone grants
no authority.

Verified locally:42 static cases (32 accepted,10 rejected),98 AST/TaskIR executions
across49 programs, managed-value retirement, aliased files, closure captures,
borrowed ancestor channels, futures, lexical rethrow and outcome replacement.
A70-type context exercises bounded widening. The initial file fixture omitted
its explicit file-root grant; the corrected fixture grants its own directory.
The original failure is retained locally. See `results.json` for exact scope.

Replay against the unchanged0.145 source/build and matching dependencies:

```sh
python3 replay.py --source-root /absolute/path/to/NEX \
  --base-build /absolute/path/to/its/build --output /tmp/nex-provenance-replay
```

Only the four changed C++ files and small test/build tools are materialized in
the output. No SDK or complete source tree is copied. `--prepare-only` checks
patch reconstruction without compiling. Existing outputs are never overwritten.

## Required before integration

- Remove the standalone-only `draft146SkipLifetime` conformance hook. Keep the
  published checker authority gate until every execution path has matching
  transfer validation. Do not publish the draft language.cpp independently.
- Native source completion must validate/prepare before owner revocation. For
  unobserved child errors, enqueue a bounded internal prepare phase after child
  drain and before resource retirement. Walk values and perform resource
  transfers outside scheduler locks; retain an owner lease and immutable selected
  packet. Publish success/fatal state under lock, preserving cancellation/fatal
  precedence. Do not reject all borrowed values or validate after scope closure.
- Use a separate transfer-capable development cohort; preserve public ABI6 and
  the existing0x2701 ordinary-payload meaning. Mixed cohorts must fail before
  source execution. Complete worker/race/cleanup and resource-adapter tests.
- TypeScript must validate the actual typed value at every source boundary,
  including implicit group close. Use compiler-known keyed accessors and a
  checked runtime policy; do not add an unkeyed payload getter or expose private
  values through public metadata/host callbacks. Unknown contracts must fail
  closed. Preserve fatal-finalizer suppression and existing legacy entry points.
- Reconcile all engines/specification/capability pack, then pass CMake/full tests,
  genuine history-preserving027 migration, provider/library/SDK/platform gates.
  The complete original NEX plan remains active.
