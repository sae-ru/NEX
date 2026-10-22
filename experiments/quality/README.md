# Checked integer core comparison

This opt-in probe builds actual NEX and C++ release applications and retains the
NEX/C++/Python input sources, hashes, commands, every observed output, timing,
per-process CPU time and maximum RSS. It requires a matching language0.18 SDK,
Clang-compatible C++20 driver, Python3, Node22.18+ and a new output directory. It works through
the compiler's actual doctor/describe commands; it does not import a source tree
or a private root-workspace verifier.
The maintained runner has an actual macOS check; Linux validation and native
Windows support remain pending.

```sh
python3 experiments/quality/checked_core.py \
  --compiler /path/to/sdk/bin/nex --output /new/comparison
```

For a development compiler add `--resources /path/to/source`. The normal case is
ten batches of ten million iterations, five rotating-order repetitions and one
warmup for each implementation. `--count`, `--rounds` and `--repeats` allow an
explicit shorter operational check; very short kernels are dominated by process
startup and are not useful throughput evidence. Each batch changes its seed.

The algorithm uses a positive modular recurrence with all intermediate values
provably within i64. Native/reference/TypeScript tests and five additional
original/reference/native/C++/Python observations precede measurement. C++ uses
checked add/multiply/remainder. Python arbitrary precision and floor remainder
agree on this defined positive domain. The C++ baseline has no cancellation or
step-budget runtime; those NEX runtime costs are included. Wall latency includes
process startup. Failed commands remain in the incomplete report.

The maintained probe follows a recorded0.94 macOS observation: for100million
steps, median process wall time was0.307272s NEX,0.292982s checked C++ and9.922024s
CPython3.9.6, over five repetitions. Other compiler/SDK verification ran on the
same host. This is one algorithm/hardware/compiler observation, not isolated
throughput, general C++/Python parity, a model-cost measurement or an application
benchmark. See [the exact receipt](../../docs/evidence/checked-core-0.94.0.json).
Broader algorithms, operating systems, realistic application loads and repeated
multi-model task/cost comparisons remain required by [quality.md](../../docs/quality.md).
