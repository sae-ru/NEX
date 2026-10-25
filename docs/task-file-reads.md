# Whole-file reads inside tasks — language 0.20

The separate [private asynchronous write bridge](task-file-writes-host.md)
provides trusted-host IO preparation in0.132.4. It does not enable source task
writes in language0.22; those remain rejected pending the complete source and
history-preserving migration integration.

The development toolchain0.110 connects `file_read_text` and `file_read_bytes`
to structured task suspension in standalone native macOS/Linux applications,
source-only native projects and the independent reference scheduler. This
candidate's complete regression, installed-SDK and platform gates are pending.
Query `nex describe --field task_file_reads --json` for the actual compiler.
Toolchain0.116 also carries this bridge through checked concrete static task
providers using the application's root grant. See [task providers](task-providers.md)
for source/ownership requirements and separate current acceptance status.

Only a **server function declaring both `task` and `fs`** uses this bridge.
The calls retain their existing types: `str -> result<str>` and
`str -> result<bytes>`. There is no new keyword, source ticket, grant type or
file handle. Ordinary fs-only functions outside task execution stay synchronous.

```nex
module read_example;
server fn length(path:str)->result<i64> !{task,fs}{
  let text:str=file_read_text(path)?;
  return ok(len(text));
}
server fn work()->result<i64> !{task,fs}{
  return with_tasks(2,server fn(scope:task_scope)->result<i64> !{task,fs}{
    let first:task<result<i64>>=task_spawn(scope,server fn()->result<i64> !{task,fs}{
      return length("input.txt");
    });
    return task_wait(first);
  });
}
server fn main()->i64 !{task,fs}{return unwrap(work());}
```

The task parks while the bounded host pool reads. Other runnable tasks can
progress. The owning scheduler validates and constructs the typed result after
the physical operation settles. The independent reference uses its own AST
scheduler and mailbox; source execution remains serial there, while host reads
can run concurrently. Native continuations use their joined executor.

## Use and authority

Install the matching SDK using [the quickstart](quickstart.md). Save the example
as `main.nex` in a separate project declaring language0.20. For a CLI run, choose
an absolute directory explicitly:

```sh
mkdir -p inputs
printf 'hello\n' > inputs/input.txt
export NEX_FILES_ROOT="$PWD/inputs"
nex check main.nex
nex eval main.nex --json
nex run main.nex --json
nex build main.nex --profile release -o read-example
./read-example
```

The operator supplies `NEX_FILES_ROOT` to each executed process. A compiled
executable does not embed the source directory or a filesystem permission.
`fs` and `task` declarations do not select an OS root. Trusted C++ hosts can
provide their explicit lexical `FileScope`/`FileReadGrant`; these are private
host interfaces and never become NEX values. Environment configuration must
not replace an existing trusted lexical grant.

The root coordinator captures the revocable grant once after its root request
control exists and before task workers start. Child frames, helper calls and
closures retain that explicit context. A resumed worker never discovers new
authority from its TLS, environment or temporary request scope. Logical
revocation remains effective while a physical lease keeps storage alive.

An unavailable grant returns `CAPABILITY` only when a read is attempted. A
branch that never reads can execute without a configured directory. Paths are
strict UTF-8, nonempty relative paths, at most4096 bytes and128 components.
Absolute paths, dot/dotdot, NUL, symlink traversal and nonregular files are
rejected. The standalone process entry still returns i64 or unit. The example unwraps
the helper result; applications can instead inspect ordinary errors before
choosing an exit code.

Each file is limited to1MiB, including growth during the read.

## Effects, calls and errors

Scope/spawn callbacks may be pure or task-only in an available realm. Language
0.20 additionally accepts exactly server `!{task,fs}` callbacks when their
caller also declares both effects. `io`, `db` and `ffi` callbacks remain
unsupported. Callable effect/realm equality stays exact, including parameters,
captures, generic instantiations and returned functions.

A task function cannot call an fs-only helper directly or indirectly: the
checker reports `E_EFFECT`. Review the helper and explicitly declare `task,fs`
if its operations belong to this supported subset. No wrapper, function-value
assignment or migration silently changes a synchronous target into a
continuation. Unsupported write/stream/db/ffi task execution is rejected before
execution; an unused server function does not enter browser output.

Inputs evaluate left to right, once. Short-circuiting remains lazy. Text
admission checks strict UTF-8 and preserves NUL/BOM; byte reads preserve all
octets. Missing files, missing capability, ordinary path/permission/file-limit
errors and invalid text return the existing typed error result. Postfix `?`
returns an ordinary error only from its current source function.

Traps, cancellation, revoked authority and execution `E_LIMIT`, `E_TIMEOUT` or
`E_MEMORY` terminate and drain. An error-result scope exit also aborts/drains
descendants. Cancellation suppresses source admission/resume; it does not prove
an OS operation has stopped. Task/future/scope completion waits for physical
retirement, adapter destruction and ticket consumption. Resource-fatal failures
retain precedence over ordinary errors/cleanup cancellation; an already selected
first fatal remains selected. No source value is decoded after cancellation wins.

## Limits and delivery boundaries

The default host transport allows at most2 I/O workers,64 pending generic
tickets,8MiB reserved payload and1MiB result data per operation. A whole-file
read reserves1MiB+4096 bytes, so at most7 such reservations fit concurrently.
In-flight cancellation retains its credit until physical settlement. These
numbers bound declared retained transport payload, not total process RAM.
Allocator metadata, source values, executor stacks and OS buffers are separate.
Use [task limits](task-limits.md) for the root deadline, steps and source workers;
helpers/scopes cannot renew the root deadline. An outer forced process timeout
does not establish joined cleanup.

This subset does not enable writes, streaming reads, db/ffi/network bridges,
task HTTP handlers, dynamic/binary-only providers, combined task debugging/profiling, TypeScript/Node
filesystem, browser filesystem, NEX UI adapters, Windows, Wasm or mobile tasks.
Browser emission still rejects reachable server code and includes only reachable
client/shared code. Existing pure/task TypeScript scheduling remains available.
Source archives capture code and declared build inputs; they do not snapshot
the external filesystem or grant future replay authority.

## Preserve 0.19 history

Keep the matching0.19 SDK and a complete graph snapshot. Public0.20 checking
never relabels a0.19 physical project, source bundle or revision. Explicit
migration rechecks original019 source with019 rules and a separate reviewed
target with020 rules, then adds a distinct020 revision. Original rows, IDs,
namespace, schema and historical HEAD transitions are retained. Unsupported
or corrupt origins and invalid targets fail before mutable destination access.
An expected-HEAD conflict rolls back the transaction.

No new reserved names or token repair is required for019→020. Adding task/fs
to helpers is an explicit source change. Program canonical format remains14;
the actual language field makes019/020 revisions distinct. Explicit018 recheck
and its original reserved-name repairs remain separate. Older known language
rechecks without a retained parser are reported as unverified origins, rather
than certified canonical verification. See [migration](task-migration.md).

Fixed startup-linked shared task providers have a separate capability descriptor
and [contract](task-shared-providers.md). When enabled, provider reads use the
same root grant and limits. The common runtime's read-code union can be true
for an unused export while the selected `task_application.task_file_reads`
remains false. Neither metadata bit creates authority. Provider profile/debug,
runtime load/unload and binary-only execution remain unsupported.
