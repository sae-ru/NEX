# Repairing the same Depot Ledger invoice in NEX, C++ and Python

How much time and model usage does Codex need to produce an independently accepted repair in each language? This experiment uses the warehouse invoice from the [multi-module NEX study](../codex-multimodule/README.md), its eight production modules, and the same interval-accounting defect. On the disputed invoice all three implementations produce 1,252 cents. The correct amount is 2,079 cents.

## What Codex receives

Start every attempt with a clean copy of that language's application, the same product policy in a neutral README, the same task prompt in bytes, and the visible regression test. The model can run `./test` to reproduce the failure and verify its edit. Each language uses its own compiler or interpreter and normal source files. The NEX condition, C++ expectations and Python checks express the same public behavior. The controller and hidden cases remain outside the model's project.

Use the same Codex model and reasoning setting in all nine fresh sessions. Run them serially in this order so each language appears once in each position.

| Block | First | Second | Third |
|---|---|---|---|
| 1 | NEX | C++ | Python |
| 2 | C++ | Python | NEX |
| 3 | Python | NEX | C++ |

## Independent acceptance

The [shared oracle](../codex-multimodule/fixture.py) enumerates calendar days to compute the union of outages, then applies the business rules to produce all five invoice fields. The visible test checks the disputed final balance. Hidden verification also checks unavailable days, billable days, and all invoice fields for the disputed case and 13 additional cases. These include nested periods, repeated notices, touching endpoints, and events clipped to the rental.

For acceptance the controller starts from a clean project and imports production edits. It retains the original test inputs and checks, including the hidden checks, then runs the relevant toolchain. NEX is checked in reference and native execution, C++20 is compiled and run, and Python executes in the selected interpreter. The controls must reproduce the initial failure, accept the reference repair, and reject a fix that returns the expected balance only for the visible test.

## Reproduction

From the repository root, use Python 3.10+, a built NEX SDK, a C++20 compiler and an authenticated Codex CLI. Set `cpp` and `py` to absolute executable paths. On macOS the C++ launcher passes the SDK path from `xcrun` explicitly so the model's shell can find the standard library even with an empty `SDKROOT`. The controls and summary tests use no model calls. Use fresh ignored output directories for controls and measured sessions.

```sh
p=experiments/quality/codex-billing-languages
out=build/codex-billing-languages-v1
cpp=/path/to/clang++
py=/path/to/python3

python3 -B -m unittest discover -s "$p" -p 'test_compare.py'
python3 -B "$p/campaign.py" --nex build/nex --cpp "$cpp" --python "$py" \
  --output "${out}-controls" --controls-only
python3 -B "$p/campaign.py" --nex build/nex --cpp "$cpp" --python "$py" \
  --output "$out"
```

The measured campaign writes `comparison.json`. To recompute it independently, pass all nine trial receipts to the summary tool and select a fresh output file.

```sh
python3 -B "$p/compare.py" "$out"/*/result.json --output "$out/independent-comparison.json"
```

To export the per-session measurements, controls and first accepted patch in each language, run the publisher. It checks each private transcript against its receipt and recomputes the comparison before writing the public JSON. The output path must be new.

```sh
python3 -B "$p/publish.py" --input "$out" --output "$out/public.json"
```

## Reading the measurements

For each language, divide the time and usage of **all attempts**, including failures, by its number of accepted repairs. Report the acceptance count alongside these ratios. Agent time measures the Codex session. End-to-end time also includes the independent acceptance step. The latter includes language-specific build and execution overhead. The receipts retain the observed times and usage for each session.

The Codex CLI's input count includes tokens served from its provider cache. The report distinguishes four quantities.

| Metric | Calculation |
|---|---|
| Gross tokens | Input + output |
| Cached input | Provider-reported cache reads |
| Uncached input | Input − cached input |
| Uncached input plus output | Input − cached input + output |

Count reasoning tokens within output only once. Missing provider usage remains unknown. The cache-adjusted token count does not establish a monetary charge or a latency saving. Three independent sessions per language repeat a single defect on one host; service-side cache hits and load may vary between sessions. The results characterize this billing repair and these tools.
