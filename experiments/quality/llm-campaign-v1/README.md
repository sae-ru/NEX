# Comparable task preparation and acceptance

These host tools prepare30 starting bundles (ten tasks × NEX/C++/Python),
execute functional acceptance, retain raw evidence and bind independent source
reviews. They make no model requests. Control solutions are experiment fixtures,
not observed LLM answers. The [protocol](protocol.md) and [task contracts](tasks.json)
define the intended comparison. Actual local-model trials remain a later step.

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
  --functional-only
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

Process ownership is **not an OS security sandbox**. This tool currently executes
maintained trusted host controls. Before running model-generated candidates,
the collection host must enforce restricted source/tool access and OS isolation
for untrusted execution. It must also pin model weights/tokenizers/settings,
collect exact local-provider usage and retain every failed/retried call. User
policy for the experiment is the installed Qwen3.8 27B Q8_0 only, without paid
APIs. The [selected profile](local-model.json) must acquire real revision pins
before the60-slot study. No weights
are downloaded or models loaded by these tools. The full60-slot experiment,
token-saving result, independent review and portable SDK qualification are pending.
