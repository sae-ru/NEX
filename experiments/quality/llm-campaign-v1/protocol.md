# LLM comparison campaign v1

Status: **prepared host controls, local collector and scoped macOS isolation;
task observations require their own frozen campaign evidence**. Applies to NEX
language0.28. The [catalogue](tasks.json) contains ten language-neutral tasks
based on pinned learning examples. Those files establish provenance; they are
not measured model candidates. [Preparation and executable acceptance](README.md)
now cover all30 starting bundles,32 visible and29 host-only cases. The
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

The operator limited the current study to the installed local
**`qwen/qwen3.8-27b` / Q8_0**. Two fresh repeats × ten tasks × three languages
produce **60 terminal slots**. Pin the actual weights, embedded tokenizer,
runtime/template and settings before calls; an alias is not an immutable
revision. [Selected local profile](local-model.json) records the intended host.
The user permits local models only, without paid APIs. No model download is
needed. Per-trial token/time stopping rules must be frozen with the collector.

Report within-model NEX/C++/Python results for this Qwen revision. No conclusion
about other models follows. The ledger's existing three-model comparison-review
eligibility remains false for this one-model study; that field is not a reason
to invent or launch additional models. The scope change occurred before any
model trials, so no observed results were discarded.
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

The maintained preparation/acceptance tools now materialize all30 starting
bundles and execute the full61-case set for NEX/C++/Python. Thirty positive
solutions and30 rejected starts qualify the functional host controls. Independent
source-rule review remains separately bound to exact candidate/contract pins.
The models have not attempted these tasks.

The local native-API transport, weight-pinning/readiness tools and separate
macOS compilation/execution policies are implemented with scoped host controls.
One benign real Qwen readiness response is transport evidence, not a task trial.
The collector now supplies a source/document allowlist and guarded JSON edit,
read, literal document search, source-text lookup, NEX descriptor and visible-check actions. It never
supplies a host shell, hidden fixtures or held-out feedback. Each request includes
the complete current task/source snapshot, NEX bootstrap or baseline note, and
the complete previous action/tool transcript. The server stores no conversation
history. Rejected actions and malformed
answers consume their request and actual token usage.

Freeze with `collector.py freeze` before requests. It pins all starting bundles,
host scripts/protocol, actual compiler/runtime images, selected model weights,
embedded GGUF tokenizer/template, Hub defaults and empty user prediction
overrides. The selected runtime directory and loaded instance config are retained;
no rendered-prompt API attestation is claimed. Temperature0/top-p1/top-k40/min-p0/
repeat-penalty1/reasoning-off, context16384/parallel1 and Draft MTP off are explicit.
The system SDK path remains an observation, not a complete immutable SDK closure.

Each slot allows at most11 author requests and one independent source-review
request (12 total),4096 output tokens per author response and2048 per review.
The trial wall budget is900 seconds, including checks/review; request timeout is
at most180 seconds and is lowered near the deadline. Stop at60000 observed
input+output tokens; one completed response may cross that soft threshold and
its complete usage is counted. A48000 UTF-8-byte prompt cap is a transport limit,
not an estimated token count. The provider enforces the actual context cap.
Each check uses a fresh compiler-owned cache, retained diagnostics and removal
afterward, without prewarming. Runtime/compiler OS limits remain in the runner.

Explicit submit runs the full visible/held-out set once. Behavioral success
then triggers a fresh stateless Qwen source review, without author conversation
or hidden tests. Every exact rule requires a boolean decision and specific
source evidence. The host binds that decision to exact source/contract pins;
the author cannot write receipts. The review call belongs to the original slot's
token/time budget, including a rejected/invalid review. This is model-assisted
judgment, not authenticated human review or a formal source proof. All languages
use the same process. Provider/host failures stop the campaign and remain in
evidence; no successful replacement slot is invented.

The infrastructure pilot is one task (`bounded-total`) across all three languages,
one fresh repeat. Its three slots are separate from the60-slot study. Run the
study only after the pilot is examined. Changed pilot rules create a new frozen
version. Clean completed prefixes can resume at the next untouched slot;
unclean/stopped executions require inspection rather than automatic restart.
These host controls and the learning corpus are not model task trials.

Policy2 retains earlier tool context and adds bounded literal document search.
The first three-slot infrastructure pilot used a latest-reply-only policy:
NEX repeated the same guide reads and exhausted11 author requests, while C++
and Python passed. That pilot and its exact usage remain recorded under source
`34572fa`; it is not replaced or pooled with policy2. A new frozen pilot is
required before the main study. No main-study slot has been attempted under
either pilot policy at this revision.

Policy3 accepts a single plain JSON object, one `<tool_call>...</tool_call>`
envelope or one `json` Markdown fence. It still rejects duplicate keys, multiple
objects/envelopes, surrounding text, unknown action fields and non-whitelisted
paths. Only framing is normalized; compiler, program-output JSON, budgets and
source-rule acceptance are unchanged. Policy2's partial pilot (source `98ec3b5`)
was stopped when repeated Qwen envelopes were rejected as non-JSON; all calls,
including one interrupted request with unknown usage, remain recorded. Its
unattempted Python slot is missing, not a fabricated failure or success.

Policy4 forwards bounded JSON diagnostics from compiler stdout as well as
stderr. It excludes embedded source payloads and exposes only the visible
check's code/message/location fields. Non-JSON output from a candidate is a
failed task observation, not a host-infrastructure failure. Policy3's completed
pilot (`e38990a`) retained a NEX syntax rejection (`+=` is unsupported), while
C++/Python passed; the model had not received the compiler's stdout diagnostic
during visible repair checks. That result remains recorded. The repaired
feedback policy still needs its own infrastructure pilot before the main study.
