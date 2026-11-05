## Historical0.24 observation and resource accounting

For recorded model experiments, use the [offline task-cost ledger](llm_cost.md).
It accounts for all attempts and flags missing usage; the maintained tests use
synthetic controls. Actual multi-model measurement remains required.

The [recorded024 observation](../../docs/evidence/checked-core-0.134.4-current.json)
records fresh native/reference/TypeScript checks and NEX/checked-C++/Python
measurements on macOS ARM64 and a Linux ARM64 VM. Linux is below the initial90%
throughput target for this algorithm; broader parity and token cost remain open.

Report schema2 uses a tiny C fork/exec/wait4 launcher on Linux, compiled with the
already selected Clang driver from adjacent `usage_launcher.c`. This excludes the
Python measurement driver's inherited memory peak. Bootstrap Linux RSS readings
are flagged invalid and are excluded from comparison samples. macOS retains its
direct wait4 byte accounting. CPU includes waited descendants; RSS is the largest
process peak, not a sum of simultaneous processes or NEX heap allocations. The
small launcher pre-exec floor is retained in its control observation. Timeouts
terminate the owned command process group. Historical schema1 receipts remain.
The source checkout must contain both the Python helper and its C companion.

## Explicit current-language comparison

Run the source-checkout helper against the actual installed current SDK:

```sh
python3 experiments/quality/checked_core.py --language 0.28 \
  --compiler /path/to/current/sdk/bin/nex --output /new/current-comparison
```

The default is current language0.28 and must match both actual describe and
doctor responses. This generates and checks a fresh project/revision; it does
not relabel the old0.18 report. Explicit0.18/0.24 choices remain for reproducing
archived observations with their matching SDKs. New development runs use0.28.
The NEX, checked C++ and Python algorithms are unchanged, and all output,
source/compiler/executable hashes, measurements and host load are retained.
Host isolation, general parity and model/token cost are not established by this
one algorithm. The helper remains source-checkout tooling; it is not installed
under the SDK tools directory. Existing SDK/CTest and Q1–Q5 gates are unchanged.

# Checked integer core comparison

This opt-in probe builds actual NEX and C++ release applications and retains the
NEX/C++/Python input sources, hashes, commands, every observed output, timing,
per-process CPU time and maximum RSS. The default requires a matching
language0.28 SDK. The retained algorithm was first measured with0.18; the
retained0.24 choice requires a matching0.24 compiler. It also requires
Clang-compatible C++20 driver, Python3, Node22.18+ and a new output directory. It works through
the matching compiler's actual doctor/describe commands; it does not import a source tree
or a private root-workspace verifier. Its recorded0.94 observations do not certify
a later SDK. Adapting this corpus requires an explicit recheck with fresh
language/revision pins; changing a version label alone is not a new measurement.
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

## Version-selected scale acceptance runner

`scale_100x100.py` repeats the historical100-module/10000-declaration corpus with
fresh current-language source and revision pins. It checks cold/warm/one-edit
native units, bounded graph context and both archived outputs after source
deletion. It retains commands, failures and timing/RSS observations; these are
separate from runtime parity or model-token measurements. The runner is opt-in,
outside CTest and the ordinary SDK phase list. Preparation/generator validation
does not establish that a current full scale run passed.

```sh
python3 experiments/quality/scale_100x100.py --language 0.28 \
  --compiler /path/to/sdk/bin/nex --output /new/scale100x100
# Installed SDK copy:
python3 /path/to/sdk/share/nex/tools/scale_100x100.py --language 0.28 \
  --compiler /path/to/sdk/bin/nex --output /another/new/scale100x100
```

The output directory must not exist. Development compilers may pass
`--resources /path/to/matching/source`; installed-SDK evidence uses the actual
installed resources. The default `--language 0.28` must match discovery. The
retained018 checked-core probe above and all094–096 receipts remain unchanged.


## Finite current-language Q1–Q5 development-chain acceptance

The updated source runners accept actual0.21 or0.28 discovery and create fresh
projects with that version. The aggregate runner passes the same version to Q5
and verifies every child report's language, toolchain and compiler identity.
Existing SDK archives keep their recorded helper copies; this source update
requires its own delivery qualification. Historical reports and graphs are not
relabelled.

The installed SDK includes `tools/run_acceptance.py` and its matching helpers.
It executes the five scenarios from `docs/quality.md`: an atomic shared-type edit
across CLI/HTTP, a server/web edit with30 checks in three real browsers, an
unchanged-intent debugger/profile repair, CPU tasks with cancellation/error
cleanup, and the fixed100-module/10000-declaration corpus. Q4 additionally joins
a controlled generated-DSO physical-completion observer in plain, ASAN/UBSAN/LSAN
and TSAN modes. Sanitizers cover the common C++ runtime and driver; generated
provider LLVM IR is not instrumented. Reports preserve commands, original failures,
compiler/resource pins, outputs and timings. This is an opt-in acceptance run,
separate from CTest and the selected SDK's maintained phase list.

```sh
python3 /path/to/sdk/share/nex/tools/run_acceptance.py \
  --compiler /path/to/sdk/bin/nex --output /new/quality-evidence \
  --browsers-path /path/to/installed/playwright-browsers
```

Use matching Node/npm/Playwright/browser versions from the SDK lock, LLDB with
Python/DAP, the native C++ toolchain and working loopback sockets. Browser cache
location may also come from the normal Playwright environment. The output must
not exist. The scale phase compiles9900 selected native units on its cold build;
keep its full report rather than estimating performance from a short smoke run.
The individual `type_edit_workflow.py`, `server_web_edit.py`, `repair_workflow.py`,
`task_cleanup_workflow.py` and `scale_100x100.py` runners accept `--compiler` and
`--output`; development preflights may additionally pass matching `--resources`.
Passing these fixed scenarios does not establish general C++/Python parity,
cross-model token savings, all-platform delivery or kernel source isolation.
