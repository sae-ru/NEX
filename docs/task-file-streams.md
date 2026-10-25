# Source task file streams: language0.24

Language0.24 enables ordinary checked server task/fs functions to open, read,
write, append, seek, size, flush and close regular files. Discover the actual
compiler with `nex describe --field task_file_streams --json`. This source
enablement is separate from installed SDK and target-platform acceptance.

```nex
module stream_example;
server fn main()->unit !{task,fs,io}{
  let stream:file=unwrap(file_open_read("input"));
  let prefix:bytes=with_tasks(1,server fn(s:task_scope)->bytes !{task,fs}{
    let child:task<bytes>=task_spawn(s,server fn()->bytes !{task,fs}{
      return unwrap(file_read(stream,3));
    });
    return task_wait(child);
  });
  assert(prefix==utf8_bytes("abc"));
  assert(file_close(stream));
  print(42);
}
```

An operator supplies `NEX_FILES_ROOT` explicitly when running or evaluating the
example. `NEX_FILES_WRITE=1` additionally grants writing; declaring fs does not
grant an OS root or writable access. A readonly opened file stays readonly.
Use the matching [example](../examples/task-streams/main.nex) and its files/input.

## Values, ordering and limits

The existing [file signatures](resources.md) are unchanged. `file_open_*`,
read/write/seek/size/flush return typed results; close/is_open return booleans.
File-bearing immutable aggregates, captures, task futures, channels and returned
closures retain genuine owner identity and original grants. A child may borrow
an ancestor owner; checked scope/future promotion preserves ownership and hidden
dependencies. An ended owner cannot be revived by an ID, callback or scope copy.

Aliases share one cursor. A physical operation is serialized against that
cursor; concurrent tasks do not have an implicit cross-task order. Use explicit
task/channel sequencing when order matters. Reads and writes are bounded to
1MiB per call; larger files are processed in chunks. A write reports its actual
possibly partial byte count. Append remains append after seek. Strict UTF-8
paths, no-follow containment and regular-file checks remain mandatory. Bytes
are arbitrary octets; decode text explicitly and handle split UTF-8 sequences.

The current host pool has2 IO workers,64 tickets and8MiB declared payload
reservations. These limits are not a bound on total process RAM, OS caches or
application frames. Requested read length reserves reply capacity; write inputs
are owned snapshots. No source Value, borrowed frame, file descriptor or C FFI
call/type/value token is carried on an IO worker.

## Close, failures and physical completion

`file_close` immediately revokes all logical aliases. An admitted physical lease
and its quota survive until real IO and owning cleanup settle. A concurrent
closed alias may produce E_RESOURCE_CLOSED; another open cannot reuse the held
quota prematurely. Request cancellation, deadlines, revoked grants and fatal
limits drain physical work before task completion. Ordinary file errors remain
typed results; caller result propagation and checked traps keep their existing
meaning and cleanup rules.

Cancellation or close cannot undo a completed write, append, seek, creation or
truncation. This API does not promise interruption of an arbitrary blocked
syscall, rollback or directory crash durability. Flush reports writeback failure;
close alone is not a durability receipt. See [physical IO](task-stream-inflight.md)
for trusted host observation and the tested admission boundary.

## Projects, binaries and debugging

Ordinary check/eval/build/run/test/project/package/profile/debug use024 after
the project has selected the matching source language. Static and fixed shared
providers use ABI5 records8/9/10 and root stage3. Source is required for checking;
one root runtime owns the executor, request and grants. Reachable read/write/
stream requirements are recorded separately and cannot grant authority.
Retained ABI3/4 records and masks31/799 keep their original interpretation.

LLDB/DAP pure watches can inspect a file's diagnostic identity. They cannot
reconstruct IO authority or execute effectful operations. Captured sessions and
profiles retain exact source, language, image/build and formatter identities.
Capture/review them again after migration; never relabel an old capture.

File authority cannot cross JSON, wire/API, browser, C FFI or unstructured
parallel boundaries. TypeScript remains a client/shared adapter; unreachable
server File/FFI code is pruned. Async network/DB, task HTTP handlers and other
platform/provider integrations remain separate work.

## Explicit migration from023

Use the matching old SDK to archive the original project. With its graph and
original SDK retained, run the new compiler's explicit `nex migrate --json`.
The origin is parsed under its original rules and identity before a024 target
is checked; only then can a writable Store append the new revision. All old
rows, schema and logical IDs remain. A rejected preflight does not create or
upgrade the destination. An expected-revision guard rejects a competing HEAD.

Migration does not overwrite physical source, nex.json or locks. Export the
accepted HEAD to a separate directory with `nex export --revision HEAD
--directory ../project024 --json`, then check/test that project. Merely editing
nex.json to024 is not a migration. Whole-file023 behavior and its stream
E_TASK_UNIMPLEMENTED rules remain reproducible with the original SDK; archived
023 rows and foreign manifest pins are not rewritten.
