---
status: current
applies_to: "toolchain 0.175; language 0.28"
owner: repository
---

# Repeated native runtime benchmark

`nex bench` measures one checked native program with a bounded, reproducible
procedure. It is a development measurement, not an acceptance gate and not a
claim of universal speed.

```sh
nex bench examples/arithmetic.nex --repetitions 7 --warmup 2 --json
nex bench examples/arithmetic.nex --repetitions 7 --output bench.json
nex bench examples/arithmetic.nex --baseline previous.json --json
```

The compiler builds the native executable once with the selected profile
(`release` by default), performs the warmup runs, then measures process wall time
for the requested repetitions. Every measured run must exit successfully and
produce byte-identical stdout; otherwise the command fails instead of reporting a
misleading sample. The JSON report contains `nex.bench/1`, per-run seconds,
min/median/mean/max, exit codes, stdout SHA256/size, build key, source revision,
toolchain, compiler build, host and CPU, and the exact measurement definition.

`--baseline FILE` reads an earlier `nex.bench/1` report and adds
`baseline.median_seconds`, `delta_seconds` and `ratio`. A baseline is only
comparable when the program, profile, compiler and host are the same; the report
records identities but does not normalize different hosts.

The timer includes executable startup, runtime initialization, program work,
captured output and process exit. It excludes the one-time compilation, file
cache state and concurrent load. Warmup is not measured. Use `--` to pass
arguments to the program; those arguments become part of the measured process.

Currently only `--kind runtime` is implemented. Cold/warm/edit build timing,
cross-host normalization, statistical significance and GPU/device timing remain
pending. Install/portable-SDK acceptance and the full platform matrix are
separate. Profiling for per-function attribution remains `nex profile`.
