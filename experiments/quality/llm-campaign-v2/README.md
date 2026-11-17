# Local Qwen campaign version2

This protocol keeps the historical version1 campaign and its negative NEX result
unchanged. It uses the same ten behavioral/source contracts, C++/Python controls,
local Qwen3.8 27B Q8_0, sampling, request/token/time limits, independent source
review and cost ledger. Version2 executes NEX projects explicitly as language0.30.

The NEX document set includes a short common coding contract and the complete
detailed rules. The broker exposes frozen compiler `guide` and `explain` results,
including the quick/stdlib document paths advertised by the bootstrap. Reads,
edits, checks, submission, source review and every reference action contribute
to the original whole-task accounting. No paid API is permitted.

Collection currently targets the qualified macOS ARM64 LM Studio runtime.
Windows/Linux model collection remains pending; this does not limit the language
platforms themselves.

Read [the protocol](protocol.md) before freezing a new output directory. The
historical collector is reused as a separate engine dependency; its files and
existing campaign directories must not be edited to run this version. This
version refuses to resume a freeze without `study_protocol_version: 2`.

```sh
python3 -B experiments/quality/llm-campaign-v2/collector.py freeze \
  --output /absolute/new/campaign-v2 --compiler /qualified/sdk/bin/nex \
  --cpp /absolute/path/to/clang++ --weights /absolute/path/to/weights.json \
  --runtime /absolute/path/to/selected-runtime --pilot
python3 -B experiments/quality/llm-campaign-v2/collector.py run \
  --campaign /absolute/new/campaign-v2
python3 -B experiments/quality/llm-campaign-v2/collector.py ledger \
  --campaign /absolute/new/campaign-v2
```

`--pilot` freezes three infrastructure slots; omit it for a separately frozen
60-slot study after the pilot's host/transport behavior is understood. Pilot
calls/results stay separate. Read the version1 protocol for the exact selected
runtime argument and local LM Studio setup; this command downloads no model.

Preparation and offline control checks are not observed model trials. A smaller
prompt is no evidence of accepted-task token savings. Because this version
changes both references and explicit source language, a difference from version1
cannot be attributed solely to the compact prompt.
