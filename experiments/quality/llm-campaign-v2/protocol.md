# Qwen task study, protocol version2

The immutable [version1 protocol](../llm-campaign-v1/protocol.md) supplies the task
matrix, local-only model selection, raw request/response accounting, budgets,
sampling, candidate checks, source review, clean resume and accepted-task cost
rules. This document lists all changes. Existing version1 failures and its
published4/20 NEX result retain their exact identities.

## Changed inputs

- NEX acceptance writes explicit language0.30 projects and requires that source
  language in the actual compiler descriptor. Unconfigured fallback0.28 is not
  used as the project version. The ten task contracts and all source fixtures,
  including C++ and Python, remain those of version1; task catalogue schema2
  changes source-version metadata, not their contract hashes.
- `llm/SYSTEM_PROMPT.md` is a common contract of at most4096 UTF8 bytes. The
  previous complete contract is retained verbatim as
  `llm/DETAILED_CODING_RULES.md`. Both are listed and frozen before generation.
- The model can request `guide` for quick, stdlib, function, trait, match,
  result, exception, source-contract, concurrency or task. A response includes
  at most6144 characters and its exact path for bounded read/search continuation.
  The full quick guide fits one response. Quick/stdlib aliases resolve to the
  selected compiler's actual text.
- `explain` returns frozen compiler guidance for an indexed diagnostic code.
  Illustrative examples and non-context-specific labels are preserved. Unknown
  guides/codes remain errors. The model gets no shell or additional source view.

The ordinary check/edit/submit broker, all request/token/time budgets, fresh
source review and ledger remain the historical collection engine's operations.
Reference actions consume ordinary author requests and their full prompt/reply
tokens. There is no free discovery channel or retrospective removal of failures.

## Frozen provenance

The collection envelope is `nex.local-collection/2`; the cost ledger retains
`nex.llm-cost-ledger/1`. Version1 runners reject the new freeze, and version2
runners reject historical freezes before model loading. The envelope adds `study_protocol_version: 2`, `collector_policy_version: 5` and
`source_language: 0.30`; trial IDs begin with `v2-`. It pins both versions' implementation dependencies, the new
tasks/protocol, actual document sources, compiled guide/diagnostic snapshot,
compiler, runtime, model weights, source starts and provider settings.

No model call occurs during preparation. Partial preparation retains its new
directory and must be inspected; it cannot overwrite another freeze. The model
and paid-API policy stay local Qwen only. Never use a newer prompt/collector to
resume old trials.

## Acceptance and interpretation

Before observed collection, run the offline broker checks and all trusted NEX
solutions/wrong starts using the actual030 compiler. Passing functional controls
is distinct from an independently reviewed model result. Freeze a qualified SDK
and an idle, fixed runtime/model configuration; do not mix SDK regression load
with timed model collection.

Report complete accepted-work cost and quality, unknown usage and all failures.
Keep infrastructure pilots separate from the60-slot matched study. This version
does not claim a token saving in advance. The changed language/reference bundle
is one intervention; attributing a difference to an individual feature would
require a separate controlled experiment.
