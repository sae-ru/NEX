# Comparable task preparation and acceptance

These host tools prepare30 starting bundles (ten tasks × NEX/C++/Python),
execute functional acceptance, retain raw evidence and bind independent source
reviews. Preparation/acceptance make no model requests. The separate local
transport and readiness command can invoke the selected Qwen model. Control
solutions are experiment fixtures, not observed LLM answers. The [protocol](protocol.md)
and [task contracts](tasks.json) define the intended comparison. The serial
collector is implemented; actual task results require a separate frozen run.

From a checkout or matching SDK resource root, prepare one fresh candidate:

```sh
python3 experiments/quality/llm-campaign-v1/acceptance.py prepare \
  --task unicode-window --language nex --directory /new/model-visible-candidate
```

The candidate receives only its own starting source files and `task.json`, which
contains the neutral request, visible cases, editable-file list and initial pins.
Do not give a model the host resource directory: `fixtures.py` includes control
solutions and held-out cases, and `drivers.py` contains acceptance implementation.
The collection runner must enforce this boundary in its file/tool API.

Check a candidate with actual execution:

```sh
python3 experiments/quality/llm-campaign-v1/acceptance.py check \
  --task unicode-window --language nex --candidate /path/to/candidate \
  --compiler /absolute/path/to/nex --output /new/acceptance \
  --functional-only --isolate
```

For C++, select `--language cpp --cpp-compiler /absolute/path/to/clang++`.
Repeated `--cpp-arg=OPTION` supplies explicit target/sysroot/other host options.
Python uses the selected Python3.10+ interpreter. Baselines use standard-library
facilities only. NEX runs reference and native Release observations; C++ compiles
as C++20 and executes; Python executes in isolated mode. Every engine must emit
one actual JSON observation per case, with exact JSON types and no missing or
extra lines. Unicode and embedded NUL remain length-aware. Input observations
also reject mutation in byte/list cases. No model-authored pass marker is used.
NEX's standard JSON wire format encodes i64 as strings; the private observation
driver uses explicitly typed decimal i64/list adapters for this neutral numeric
contract. It does not change the language's wire representation or coerce a
candidate's wrong return type. The C++ compiler invocation preserves its driver
name (`clang++` may be a symlink to `clang-N`); the underlying image is hashed
separately, so resolving a symlink never silently selects the C linker mode.

Acceptance combines32 public cases with29 fixed host-only cases. The latter
include previously unseen numeric values, Unicode windows, malformed UTF-8
(overlong sequences, surrogates, out-of-range scalars and bad continuations),
module callers, map ordering and typed error/finalization payloads. Cases are
frozen before model trials and never adapt to answers. A visible-case lookup
must fail the held-out checks. These finite observations do not prove general
correctness, thread bounds or the internal use of a requested abstraction.

## Functional checks and source rules

`--functional-only` exits0 on behavioral success, while its receipt remains
`passed:false` without independent source review. Default `check` exits0 only
when both the full functional set and a bound source review pass. Exit1 is an
unaccepted candidate; exit2 is invalid configuration/evidence. The distinction
prevents outputs alone from certifying source-level requirements such as a
bounded executor, reusable generic interface, dependency boundary or finalizer.

Supply `--source-review /host/review.json`, outside model-visible candidate files:

```json
{
  "schema": "nex.llm-source-review/1",
  "candidate_digest": "<source_digest of the exact reviewed files>",
  "contract_sha256": "<task contract SHA256>",
  "passed": true,
  "reviewer": "<independent reviewer identity>",
  "rules": ["<every exact acceptance_rules entry in task.json, in order>"]
}
```

Placeholders are not valid evidence. `source_digest` is SHA256 of UTF-8 compact
JSON with sorted file paths and each file's SHA256. Every rule must be reviewed;
a changed source, contract or partial rule list rejects the review before any
execution. This binding cannot authenticate the reviewer's identity or judgment.
The collection host must own the review input, exclude model-authored receipts
and account for any model-assisted review calls as trial costs. Host-only control
attestations in tests are explicitly synthetic and establish no model result.

`report.json` retains source/tool hashes, commands, raw logs, observed values,
failures and acceptance scope; `acceptance.json` uses the existing cost-ledger
receipt format. Success and failure retain bounded source/driver/log evidence;
temporary executable workspaces are removed. NEX caches are reusable only with
an owner marker for the selected compiler; successful control cohorts remove
their cache. The input candidate directory and existing NEX graphs are untouched.

## Host limits and remaining delivery

POSIX commands run in fresh owned process groups with wall/output limits and
group retirement. Windows execution requires the existing calibrated native
private-job observer through `--windows-observer`; it is never replaced with a
process-name/PID-tree scan. That helper's native binary must already be built
for the host. Current Windows qualification remains separate.

`--isolate` requires the qualified macOS Seatbelt backend. It uses separate
compilation and execution profiles: compilation writes only its private workspace
and explicitly owned cache; execution cannot fork/spawn, connect to the network,
read arbitrary host files or write its source directory. Threads remain available.
The environment excludes API keys and inherited proxy settings. Hard CPU/file/
descriptor limits, owned-group wall/output limits and observed group RSS budgets
apply. C++ and NEX select the actual Xcode linker directly. The OS loader profile
is pinned. These policies have scoped host checks; they are not a VM or a proof
against kernel/compiler vulnerabilities. Other hosts require their own qualified
isolation backend. Without this option, the runner provides process ownership
and limits only; use it for maintained trusted controls.

The isolated checks cover three unchanged task solutions (21 case observations),
actual file/network/process/signal denials and rejection of a Python candidate
attempting to read the expected-value oracle. The private driver passes inputs
only to Python candidates; expected values stay in the parent. The earlier
244 control observations retain their original harness pins and execution mode.
See [scoped evidence](../../../docs/evidence/llm-local-transport-isolation-0.165.0-2026-11-11.json).

## Selected local model readiness

User policy is the existing **Qwen3.8 27B GGUF Q8_0 only**, without paid APIs.
Start the operator's LM Studio local server on `http://127.0.0.1:1234`. Hash
the existing directory into a new host manifest (this reads all artifact bytes):

```sh
python3 experiments/quality/llm-campaign-v1/weights.py \
  --root /absolute/path/to/Qwen3.8-27B-GGUF --output /new/weights.json
python3 experiments/quality/llm-campaign-v1/readiness.py \
  --weights /new/weights.json --output /new/readiness
```

`weights.py` neither downloads nor loads a model. Readiness requires an idle
local service, creates its own uniquely named instance, sets context16384 /
parallel1 / full GPU offload and performs **one benign transport probe**, then
unloads only that instance. It executes no model-authored programs and is not
one of the60 task trials. Existing user instances are never replaced or unloaded.
The GGUF tokenizer is covered by its full-file hash; runtime/effective template
and all study stopping rules still need to be frozen before task trials.

The native API client permits only numeric loopback, ignores proxy environment
variables, rejects redirects and disables server integrations/history storage.
Requests explicitly disable reasoning and fix temperature0/top-p1. Exact transmitted
requests, raw responses, usage, errors and interrupted calls are retained. Actual
input/output totals are counted once; an unreported cached-input subtotal stays
`null`, never an invented zero. The observed readiness call used36 input and6
output tokens with an unreported cache split; the owned instance was unloaded.

## Collect and account for task attempts

The collector restricts model reads/edits to its own candidate and frozen language
references. `read` windows, literal document search, source-text lookup and NEX descriptor queries are
bounded. `check` returns only visible observations. `submit` performs the terminal
held-out check once, followed by an independent fresh-context local Qwen source
review. Review usage is counted in the same trial. The host creates the receipt;
the author cannot supply one. Model-assisted source judgment is not formal proof.

```sh
python3 experiments/quality/llm-campaign-v1/collector.py freeze \
  --output /new/pilot --pilot --weights /path/to/weights.json \
  --compiler /absolute/path/to/nex --cpp /absolute/path/to/clang++ \
  --runtime /absolute/path/to/selected/llama.cpp-mac-arm64-apple-metal-advsimd-VERSION
python3 experiments/quality/llm-campaign-v1/collector.py run --campaign /new/pilot
python3 experiments/quality/llm-campaign-v1/collector.py ledger --campaign /new/pilot
```

`--pilot` creates three separate infrastructure slots; omit it for the60-slot
study after pilot review. The freeze includes all operational rules in the
[protocol](protocol.md): at most11 author calls plus one review, observed usage
soft stop, wall/context/output limits, current source plus complete action/tool history,
fresh caches and isolated execution. It rejects user prediction/template overrides
and pins the selected runtime, Hub defaults and embedded GGUF template. Pinning
the template is not an API attestation of the exact rendered token stream.

Raw requests/responses, every rejected action, check output, source pin, review,
interruption and terminal result remain in the campaign. Host/provider failure
stops collection; existing attempts are not overwritten. Use `--max-slots N` to
end at a clean prefix and `--resume` for the next untouched slot, after the owned
instance has been unloaded. A stopped/unclean process is never blindly resumed.
External host reviews can finalize explicitly pending manual-review records with
`finalize --reviews DIR`; they cannot repair source or change frozen conditions.
`ledger` uses the existing offline accounting engine. Missing/pending slots keep
the comparison incomplete; one model keeps multi-model review eligibility false.
Full60-slot token-saving results and matching portable SDK qualification remain pending.
The first latest-reply-only pilot remains a separate negative infrastructure
result: NEX repeated guide pages and exhausted its request budget. Policy2
preserves earlier replies and supports targeted search; it requires a new pilot,
without discarding or merging the earlier three outcomes. The partial policy2
pilot also remains recorded: Qwen used tool-call envelopes and the host rejected
their framing. Policy3 normalizes one strict advertised data envelope before
the same action validation; it never executes arbitrary tools. Each version's
pilot remains separate from the60-slot main study.
Policy4 additionally exposes bounded stdout JSON compiler diagnostics alongside
stderr. This repairs a missing-error-feedback path found by the third pilot;
source/program acceptance is unchanged. Its own real pilot remains pending.
