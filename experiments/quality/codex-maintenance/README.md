# Codex NEX maintenance comparison, protocol 1

Compare two developer interfaces to NEX 0.30. The baseline is main 26e78f53 and its public llm/SYSTEM_PROMPT.md. The second arm uses the updated CLI and its matching author instructions. The task prompt, starter files, acceptance criteria and Codex settings remain identical. This measures the combined change to tooling and instructions.

Run the three task IDs in order: summary-repair, retry-delay, queue-interface. Finish the baseline before changing NEX. Run the same sequence from fresh directories in fresh Codex CLI sessions after the change. Use the ChatGPT login, gpt-6.2-sol, low reasoning effort, normal workspace sandbox, no extra connector, no paid API key. The model may read only the starter project and its provided guide and may invoke the supplied NEX executable. Keep the controller, previous solutions, raw transcripts, hidden checks and controls outside its project. The clients may have different server-side cache hits and system load. This small ordered pilot does not isolate those effects.

Measure each attempt from model launch to exit and from launch through independent acceptance. Preserve failures including cutoff and transport errors. Sum positive provider-reported turn usage across all completed turns, separately tracking input (includes cached input), cached input and output. Count input plus output once. Missing usage is unknown. Sum costs over all attempts, divide by number of accepted tasks only when appropriate, and show each paired outcome and the absolute and percentage changes. Money is unknown unless billing is supplied. Compare only like-for-like measurement coverage and report what could not be measured.

The summary repair checks Unicode scalar length across all items, the new feature checks bounded retry delays across the i64 range, and the multi-file change checks backward compatibility and actual use of the new queue interface. Accept each task using the clean-room visible and held-out reference/native checks in fixtures.py. First test the controls with the original compiler. Keep model-generated patches and detailed logs private under build/. Publish aggregate receipts including prompt, fixture and executable digests and validation outcomes. This campaign concerns changes to NEX and its documentation, not a cross-language or large-project performance comparison.

## Reproducing one pair

Use Python 3.10+ and a matching compiler/resources installation per arm. Run
`codex login status` and confirm the ChatGPT login. From the repository root:

```sh
p=experiments/quality/codex-maintenance
python3 -B -m unittest discover -s "$p" -p 'test_compare.py'
python3 -B "$p/run.py" --arm before --task summary-repair \
  --nex /path/to/baseline/bin/nex --guide /path/to/baseline/share/nex/llm/SYSTEM_PROMPT.md \
  --output build/codex-trials/before-summary
```

Use a new output directory for each run. Complete all before tasks and repeat
with the changed SDK, guide and `--arm after`. Summarize the six receipts:

```sh
python3 -B "$p/compare.py" build/codex-trials/*/result.json --output build/codex-trials/comparison.json
```

The runner measures one user turn per trial. Its usage includes all agent/tool
steps in that turn, as reported by Codex. Source acceptance runs separately after
the timer for the agent stops and is included in end-to-end time. The model's
private JSONL, stderr and prompts remain in the ignored output directory. The
public comparison contains counters and digests. Keep SDK versions and their
resources together if you rerun a historical arm.
