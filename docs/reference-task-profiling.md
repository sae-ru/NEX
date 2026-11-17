---
status: current
applies_to: "toolchain 0.279.0; language 0.30; task ABI8"
owner: repository
---

# Profiling reference tasks and native libraries

Ordinary030 task applications containing `cell<T>` can select the native
`profile` configuration. Source continuations retain their owner-thread heap;
physical IO completion workers remain separate. Related static, fixed shared
and mixed source-backed components use the same application executor and
collector. Profiling changes neither cell identity nor source error semantics.

```sh
nex profile app/main.nex --task-timeout-ms 10000 --json
nex project nex.build.json --kind profile --component app --configuration measured --json
```

The [example](../examples/reference-task-profiling/README.md) captures cells in
a spawned child, waits in its parent, mutates state in a library and catches a
nominal error carrying that same cell. A separate self-cycle stays live until
application teardown. Successful execution prints42.

The [focused receipt](evidence/reference-task-profiling-0.279.0-2026-11-17.json)
records the exact source/compiler, actual source and moved-install profiles,
format validation and affected checks. Complete SDK/platform qualification
remains separate.

## What the report measures

A source invocation counts once across yields and library crossings. Calls,
completed/aborted invocations, active source CPU/elapsed segments, logical
lifetimes, task waits and physical drain keep the existing
[task-profile meanings](profiling.md). An error caught in a caller still marks
the throwing leaf invocation aborted. Read completeness/drop flags before using
an aggregate or budget. `--events 0` omits timeline events while retaining the
supported complete aggregate measurements.

`task_execution.executor_workers` reports1 for ABI8 source continuations, even
when the configured worker limit is larger. The configured/effective limits are
retained separately. The profiler does not make cells transferable between OS
threads and does not measure physical IO-worker CPU or disk service time.

Memory records cover tracked shallow Handle/Data allocation sites, including
cell Data objects. They exclude the cell heap registry/index backing, dynamic
payload buffers, coroutine/scheduler backing, allocator overhead and total RAM.
Balanced teardown counts are not a measurement of peak resident memory or a
proof of bounded garbage-collection pauses. Source values and cell payloads are
not copied into the profile report.

## Explicit execution and record identities

Reference-free030 tasks retain their existing ABI7 path. A reachable reference
application and its connected pure helpers select execution ABI
`0x4e45585400000008`. Profile providers use `nex.native-task-provider/19`;
enriched static/shared linkage plans use `nex.project-task-linkage/19`.
Uninstrumented reference17 and debug18 records remain separate. The profile
extension retains registryABI1 and catalog1; no descriptor layout, source
production, canonical graph identity or public C ABI changes.

Single-image raw/saved/session profiles retain schema2. Provider profiles
retain raw/saved/session3 and completion6. The selected record explicitly binds
the execution cohort; relabeling it as typed-error ABI7 is rejected. Each
catalog binds the actual source component and physical code image. Embedded
static helpers belong to their containing image; shared helpers retain their
own image. One root joins only its checked loaded closure.

## Capture and delivery boundaries

Acceptance-task profiles capture the ABI8 source union and linkage19 selection.
Replay rechecks those checked sources and records a new actual measurement.
Packages retain original provider/catalog metadata and separately map relocated
code images. A packaged instrumented binary can write its raw report after the
original source/cache directories have been removed. Packaging itself does not
measure the program. See the retained [provider profiling contract](task-provider-profiling.md).

HTTP task profiling, simultaneous logical-debug/profile instrumentation,
persistent external host-session profile launches, parallel reference transfer,
full current source/platform regression and portable SDK qualification remain
separate work. This contract does not broaden GPU/NPU profiling.

По-русски: профилировщик считает вызовы, активное время и ожидания задач030,
включая переходы между библиотеками и ошибки с объектами. После завершения
освобождаются также циклические объекты. Память в отчёте — размеры отслеживаемых
объектов, а не вся оперативная память процесса. Для нескольких библиотек отчёт
сохраняет принадлежность функции исходному компоненту и загруженному образу.
