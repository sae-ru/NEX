# Codex repair of an unfamiliar multi-module NEX project

Experiment 1, specified before model calls. The project is a newly written warehouse billing application with one reproducible failing test. Each session receives the same product specification, source and visible tests. An independent verifier copies the submitted application code into a clean project, restores the protected inputs and runs the original and held-out cases. Its expected outputs and control repairs stay outside the model workspace.

## Intervention

The incoming issue contains the actual failing test diagnostic and the context returned by the compiler for the same public invoice function. Both outputs are attached automatically to the first model request. The four arms change which two outputs are delivered. This models a developer investigating a prepared issue report; reading the attached context is part of the task cost even when the model then reads source files directly.

| Arm | Function context | Failed assertion |
|---|---|---|
| old | ordinary | legacy diagnostic |
| context | brief | legacy diagnostic |
| diagnostic | ordinary | diagnostic with test name, condition, available scalar operands and replay |
| both | brief | enriched diagnostic |

Baseline SDK: commit 26e78f53. Updated SDK: commit b2e3dacc. Language 0.30 in both. The model can inspect and edit ordinary source and run the supplied CLI. No advice specific to the defect, differing startup guides, paid API keys or previous solutions. Use ChatGPT login with gpt-6.2-sol and low reasoning; fresh ephemeral workspace-write sessions. Run serially in two blocks. Block 1: old, both, context, diagnostic. Block 2: diagnostic, context, both, old. Reversing the order balances a linear time trend. Warm service-side caches, session variability and network latency remain possible. The two repetitions on a single defect do not measure randomness across projects.

## Counting

Record completed-turn input, cached input (already part of input), output, agent time and end-to-end time to the independent acceptance result including report preparation. Count retries/actions within a trial, failures and cutoffs. Preserve missing usage as unknown. Measure exact diagnostic and context payload sizes; bytes are not tokens. Report acceptance for each arm, signed differences on each fixed setting of the other factor, main effects averaging across the other factor, and the observed joint change. Positive savings mean less consumption. Total tokens are input plus output. Dollar costs are unknown unless billed amounts are supplied. Keep original JSONL private. Report the actual results even when the changes cost more.

Detailed receipts pin the fixture, base instruction, delivered prompt, packet payloads, compilers and Codex settings. A public summary is built from all eight receipts. Changes to the design after model calls, including interrupted or repeated runs, must be called out explicitly.

## Reproduction

From the repository root on a host with both SDKs, Python 3.10+ and a working
Codex CLI ChatGPT login, run the controls before starting the measured sessions:

```sh
python3 -B -m unittest discover -s experiments/quality/codex-multimodule -p 'test_compare.py'
python3 -B -c 'import sys; sys.path.insert(0,"experiments/quality/codex-multimodule"); import fixture; assert all(fixture.preflight(p)["ok"] for p in sys.argv[1:])' /path/to/old/nex /path/to/new/nex
```

The following runs all eight sessions. Use a new ignored results directory for
each experiment and retain any failed attempt. Run the two blocks serially.

```sh
p=experiments/quality/codex-multimodule
results=build/depot-ledger-runs
old_sdk=/path/to/old/nex
new_sdk=/path/to/new/nex
for block in 1 2; do
  if [ "$block" = 1 ]; then set -- old both context diagnostic
  else set -- diagnostic context both old; fi
  for arm in "$@"; do
    python3 -B "$p/run.py" --block "$block" --arm "$arm" --old "$old_sdk" --new "$new_sdk" \
      --output "$results/b$block-$arm" --timeout 300
  done
done
python3 -B "$p/compare.py" "$results"/b*-*/result.json --output "$results/comparison.json"
```

The runner captures the actual stdout bytes from the initial failing test and
the function context. It seeds a fresh graph for every arm and uses the same
new compiler for the shared check and final external verification. During the
session the supplied launcher dispatches `test` and `context` to the corresponding
SDK format. Raw prompt and event logs stay in ignored output. A fresh copy of
the starter in each session protects against reuse of a previous solution.
