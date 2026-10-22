# Explicit task execution limits

The development toolchain0.106 adds host controls for language0.19 task
applications. Query `nex describe --field task_execution_limits --json` on the
compiler you actually use. Source syntax, semantic identities and stored history
are unchanged. Acceptance of a particular SDK/platform is separate evidence.

```sh
nex run main.nex --task-steps 2000000 --task-timeout-ms 10000 --task-workers 2 --json
nex eval main.nex --task-steps 2000000 --task-timeout-ms 10000 --task-workers 2 --json
nex test main.nex --symbol checks --target web --task-workers 1 --json
nex build main.nex --task-workers 2 -o application --json
./application --nex-task-workers 1 --nex-task-timeout-ms 1000
```

Defaults are1,000,000 charged steps,5000 milliseconds and a native worker pool
ceiling of16. Steps accept positive integers through9,007,199,254,740,991;
timeout accepts1..3,600,000ms; workers accepts1..16. CLI values are strict decimal
strings, without signs, spaces, suffixes or duplicate options. Ambient environment
variables do not configure these controls or grant resources.

Build/run/test/package flags set reviewed native application ceilings and enter
the build/cache identity. The copied executable's separate `--nex-task-*` flags
can only lower its embedded ceilings. Raising a ceiling needs an explicit new
build. Unknown reserved flags, duplicates and invalid values fail before a task
worker starts. Other application arguments retain their literal meaning.
Task controls require an actual task entry/test. `--steps` remains the general
interpreter option for eval; run/build/test/package reject it. Do not combine
eval `--steps` with task controls.

All child scopes and tasks share one root budget and monotonic deadline. A child
cannot restart the clock or replenish the budget. Worker counts bound a native
pool; a source scope's own count remains an additional ancestor ceiling. Reference
and TypeScript task schedulers execute serially and report executor_workers1.
Their worker option is an upper bound and does not start OS/browser workers.
The native workers setting limits the task executor pool. The separate pure
parallel_map API retains its own CPU-worker contract; this is not a global
process-thread limit. Its work still shares the request step/deadline control.

Steps count backend work: native resumes/runtime polls, checked AST actions/atoms,
or TypeScript generator/checkpoint work. Equal numeric budgets do not establish
equal exhaustion thresholds. With sufficient budgets, ordinary value/error
semantics still agree. Deadlines and cancellation are cooperative; a trusted
operation can delay a poll. Completion and checked failures retain joined scope
cleanup. Forced process termination has a separate guarantee.

Compiler run/test JSON records `task_execution.configured`, `effective`, backend,
executor workers, step model and the outer supervisor timeout. An outer process
timeout remains independent and can terminate the process before its cooperative
deadline. Ordinary task CLI capture allows deadline plus cleanup grace by default;
an explicit `--timeout` is preserved. Reviewed acceptance/project timeouts are
never silently enlarged.

## Projects and captured acceptance

Project ceilings belong to the reviewed configuration in `nex.build.json`:

```json
{
  "profile": "release",
  "task_limits": {"steps": 2000000, "timeout_ms": 10000, "workers": 2}
}
```

The object is nonempty; omitted fields retain defaults. Configuration task
limits apply to task applications/tests, leaving pure components with their
ordinary execution contract. Plans and captured architecture identity preserve
the settings through build, run, test, package and replay. Project CLI task flags
are rejected; edit the reviewed configuration. Standalone executable argv can
still lower the embedded values.

A nonproject `nex.task/1` build/run/test check may add the same `task_limits`
object. It is part of the acceptance intent/hash and captured inputs. Both its
reference observation and selected native/TypeScript backend receive it.
Project-backed checks use their captured configuration and reject a second
check-local override. An emitted web module/application build has no executing
scheduler; its build check rejects task_limits. A TypeScript test does execute
the scheduler and accepts the controls.

An independent TypeScript host passes `task.run(invocation,{steps:2000000,
timeoutMs:10000,workers:2})`; the existing AbortSignal remains separate. Server
resources, task UI adapters, task providers and async debugger/profiler integration
retain their explicit unsupported boundaries. These limits add no asynchronous
file/network bridge or accelerator authority.
