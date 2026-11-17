# Local Qwen study, protocol version3

Version3 addresses the [observed version2 failures](../../../docs/llm-cost-qwen38-27b-2026-11-17.en.md).
It requires a new freeze. No version1/2 trial, failure, unknown token count or
source-review judgment is replaced. The [version1 budgets](../llm-campaign-v1/protocol.md),
local-only Qwen selection, raw-call accounting, candidate isolation, stopping
rules and independent source-review operation remain in effect.

## Changed inputs

The NEX reference view adds existing compiler guide kinds `tasks-runtime`,
`bytes`, `bytes-construction`, `list-build`, `text-construction` and `references`.
It retains `task` for acceptance JSON and explicitly distinguishes it from
source scheduling. Guide responses keep the6144-character bound; read/search
can use the listed canonical public document paths or `guide:KIND` aliases.
Preparation compares every guide's full actual compiler output with its public
resource file. No candidate, hidden driver or trusted solution is added to this
view. Reference actions consume the same request/token/time budgets.

The independent source reviewer now receives a frozen public language-reference
packet. Every NEX task receives the same packet: the full bounded quick guide,
the current source-task introduction and current CPU-mapping introduction. It
records the compiler build, descriptor and explicit source language0.30.
C++ and Python receive their existing public baseline notes. Each language's
serialized packet is bounded to16384 UTF8 bytes and pinned before generation.
This is general language semantics, not a task solution or held-out observation.

Review remains a separate fresh call without author history. Its request carries
the added reference packet, and its input/output tokens count through the same
provider call and original ledger. The host does not override a false judgment
or grant acceptance because a reference was supplied. Every listed source rule
still needs an explicit review finding. The receipt pins the exact reference
packet; raw requests preserve what the reviewer actually received.

## Unchanged contracts and accounting

The ten behavioral/source task contracts and all C++/Python fixtures are reused
byte-for-byte from [version2's catalogue](../llm-campaign-v2/tasks.json), which
already retained version1 contract hashes. NEX projects remain explicit0.30.
There are two deterministic repeats per language. Model sampling, eleven author
requests plus one review, completion limits, wall/soft-token budgets and required
explicit submission are unchanged. This is not a protocol for retrial-until-pass.

The new envelope is `nex.local-collection/3`, collector policy6. It pins all
earlier engine dependencies, current public references and the new implementation.
Trial IDs start with `v3-`. Version3 rejects historical envelopes before model
loading. Failed preparations remain separate directories. The original
provider-failure stop and clean-prefix resume policy are retained; version2's
manual suffix amendments are not silently adopted.

## Evidence requirements

Selecting a portable macOS SDK for the NEX compiler also selects its bundled
native build resources, manifest, compiler, headers and libraries. The freeze
records the bundle inputs used for compilation and the active Apple SDK settings.
The Apple SDK path is an explicit native build input. The host's C++ comparison
driver is selected independently. The paired example check in the README
exercises the same build and execution sequence as candidate acceptance.

Offline synthetic-provider checks can prove that references reach the reviewer,
remain outside candidate edits and retain complete call accounting. They do not
measure model quality or token savings. Check the actual compiler-served guides
and execute their source examples before creating a new observed freeze.
Run future observed collection separately from heavy SDK/device work, with fixed
model weights/runtime/configuration and an idle local model service. Report all
attempts, unknown usage, source-review limitations and any execution amendment.
No observed version3 collection or token improvement is claimed by preparation.
