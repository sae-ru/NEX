# LLM comparison campaign v1

Status: **prepared contracts; not an executed experiment**. Applies to NEX
language0.28. The [catalogue](tasks.json) contains ten language-neutral tasks
based on pinned learning examples. Those files establish provenance; they are
not measured candidates or reviewed C++/Python starting snapshots. The
[accounting command](../llm_cost.md) is implemented separately.

## Question and measurements

Does a model spend fewer total tokens delivering an accepted change in NEX
than in C++20 or Python3.10+, without lowering success on the same task set?
For each model/language, the primary metric is all input plus output tokens
across **all** terminal trials divided by accepted trials. Count the complete
repeated system/task prompt, documentation, source context, tool responses and
repair history in every request. Keep failed trials in the numerator. Zero
accepted trials or unknown usage leaves the metric undefined. Cached input is
a subset of input; reasoning tokens already included in output are not added
twice. Billing remains unknown unless confirmed in the actual provider record.

Report NEX/C++ and NEX/Python separately: total-token ratios, accepted/attempted
counts, terminal reasons, per-task outcomes, median/p95 trial tokens, requests,
wall time, unknown usage and confirmed cost by currency. Publish negative results.
Do not pool models or select only successes. The30% goal in
[quality.md](../../../docs/quality.md) is a hypothesis. These ten example-derived
tasks cannot establish gains for arbitrary large systems.

## Matrix and freeze

Target: three independent immutable model revisions, two fresh repeats, ten
tasks, three languages: **180 terminal slots**. Two models may form a pilot;
they do not satisfy the existing three-model comparison-review gate. Aliases
of one provider/revision count once. Pin actual tokenizer IDs, model settings,
tool permissions, trial order and budgets before any calls. Model choice and
total monetary/token ceilings require operator selection; this protocol
provides no default authorization for paid calls.

Every slot starts in a fresh conversation and copy of the starting source.
No answers, chat history or retrieved context carry across repeats. Record
provider caching as observed. Compiler caches may be prewarmed identically;
record that policy and compiler wall time separately from model usage.
Balance language order cyclically by model/repeat/task, then pin the resulting
order. Run one trial at a time initially. Never change prompts, task selection,
budgets, acceptance cases or dependency versions after seeing early results.

Before the first model call, freeze SHA256 pins for this protocol, each task
contract, prompt,30 starting source bundles and all three executable acceptance
harnesses. Include NEX compiler/descriptor/language-pack and learning inputs,
C++ compiler/options, Python runtime/dependencies, host/tool interface, exact
model settings and per-trial/total stopping rules. Human review must establish
equivalent acceptance semantics across languages. Validate harnesses against
reviewed passing solutions and intentional wrong solutions before freezing.
Keep those solutions and held-out cases outside model-visible roots.

## Fair task and tool access

Use the same change request, visible cases and behavior contract. Allow idiomatic
implementations and standard libraries. Baselines need not reproduce NEX trait,
effect or Result syntax. Conversely, unchecked C++ signed overflow or Python
arbitrary-precision results do not satisfy signed64-bit checked behavior when
the contract requires it. Explicit bounded domains may avoid overflow. These
tasks compare functional change acceptance, not equal static guarantees,
scheduler throughput, GPU support or runtime performance.

Provide the same permissions and comparable source/symbol lookup, build and
test tools. NEX may use bounded discovery/context from `llm/BOOTSTRAP.md`; count
all returned material. Record every exact request and tool response. External
network, package installation, acceptance implementation/held-out access, human
repairs and cross-trial solutions are excluded equally for every language.
The host owns acceptance and runs it from a separate pinned copy. A model's
claim that tests pass never creates a receipt. Preserve actual commands,
stdout/stderr, exit status, starting/final source pins and toolchain identities.

Declare identical operational time/resource limits. A candidate/compiler crash
is a failed trial. Distinguish setup/host failures from semantic failures and
retain both; stop a campaign with broken infrastructure before changing its
protocol. Repairs consume the original slot's budget. Stop once as `accepted`,
`failed`, `timeout` or `budget_exhausted`. Changed budgets/manual intervention
start a new campaign version; never replace a failed slot with a later success.

## Evidence and accounting

Every attempted provider call, including repairs, retries and failed requests,
belongs to its original trial. Preserve the raw response or failure record,
request/trace ID, exact messages/tool transcript and hashes. Record configured
versus returned model revision when different. Normalize actual provider usage
without estimates. A request that may have been billed but has no usage record
has `usage:null`; never omit it. Later confirmed bills may be additional pinned
evidence; rate-card guesses are not confirmed cost.

The host writes `nex.llm-acceptance/1`, bound to trial ID and contract SHA256,
with actual check exit codes. Failed/time/budget stops also receive an explicit
failed receipt with the stopping check. Keep all raw commands/outputs, final
source pins, toolchain identity, complete context trace, wall time and provider
calls in each run. `data_kind:"observed"` denotes actual trials; controls use
`synthetic`. Evidence stays within the campaign directory with immutable hashes.

```sh
nex cost /path/to/campaign/ledger.json --output /path/to/new-summary.json
```

Exit0 means accounting completeness, including a complete synthetic control.
It does not authenticate usage, omitted calls, model independence, acceptance
fairness or an actual experiment. Review those independently. Exit1 retains
incomplete results; exit2 rejects malformed input/inconsistent evidence. Keep
partial/failed summaries with raw records. The command executes no model or
acceptance calls.

## Remaining preparation

Contracts and provenance are written. The30 starting snapshots and executable
acceptance harnesses, their passing/wrong-solution controls, the selected models
and budgets and the host collection runner remain to be implemented/reviewed.
Then freeze pins and run a small infrastructure pilot before the comparable
matrix. Changed pilot rules create a new version. The learning-corpus run is
compiler evidence; it is not any of these model trials.
