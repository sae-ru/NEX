---
status: development
applies_to: "toolchain 0.272.0; project language 0.30"
owner: repository
---

# Persistent application state in the browser

Source0.30 browser applications may retain `cell<T>` identity between events
and suspend inside structured tasks. The generated application owns one heap
for its lifetime. Source state stays inside that owner; the renderer receives
copied immutable `View` and command values. Persistence here means the lifetime
of the running application; disk storage and reload restoration are explicit
application work.

Discover `managed_references.source030_development.persistent_UI` in the selected
compiler. Older SDKs may not implement this adapter. The
[example](../examples/persistent-ui/main.nex) includes shared aliases, preserved
snapshots, caught errors after suspension and a separate browser Worker.

## Source contract

The existing `initial`, `update`, `title` and `view` signatures in
[web.md](web.md#application-functions) remain. Optional `commands` and
`worker_commands` keep their existing wire layouts. For030, these entries may
use `state`, `task` and `throw`. A reachable cell or task effect selects the
persistent adapter. Pure immutable applications retain the synchronous adapter;
retained028/029 UI entries retain their existing restrictions.

State is non-unit. It may contain cells, immutable aggregates and source
closures. It cannot retain task/scope/channel authority. Source code remains
client/shared, with no source filesystem, database, FFI or direct browser IO.
`parallel_map` is rejected in the persistent application graph. One cooperative
JavaScript source owner executes it; this does not introduce shared mutable
memory between native threads or browser workers.

The initial invocation runs `initial → title → view`. Each admitted event runs
`update → commands → worker_commands → title → view`, omitting absent command
entries. Structured child tasks join before the new snapshot is published.
Events are processed in admission order; at most256 wait in the queue. Network
and Worker commands execute through the existing adapters after publication,
then deliver copied response events to the same queue. Source tasks do not stay
detached across events. Reference-free Worker computation has its own isolated
execution context and wire boundary; no cell is transferred to it.

Cell writes take effect during the invocation. This is serialization, not
rollback: an uncaught source error, fatal control or unexpected host failure
closes the application. A rejected event or queue admission does not execute
source code and leaves the healthy application usable. Retained old `View`
snapshots do not change when subsequent events mutate source cells.

## Generated host API

```typescript
import {createApplication, makeEvent} from './src/program.ts';
const app = createApplication({steps: 1000000, timeoutMs: 2000});
try {
  const first = await app.ready;
  const next = await app.dispatch(makeEvent('add', '', '/'));
  // Render first.view or next.view. Neither snapshot exposes live State.
} finally {
  await app.close();
}
```

`createApplication` returns an owner with `ready`, `dispatch`, `statistics`
and idempotent async `close`. The generated React adapter manages that lifecycle
and closes its request/Worker runners on failure or unmount. It displays the
copied error code, source site and message through its error boundary.

Options select the existing task `steps`, `timeoutMs`, `workers`, `signal` and
`complete` hook. Limits apply to each invocation. The `workers` option does not
make source cells concurrent. The signal closes the whole application; the
completion hook observes ordinary scheduler statistics. No raw source `observe`
callback is exposed. A throwing completion hook closes the application too.

`dispatch` checks and copies the wire event at admission. It returns a `Promise`
of `{title, view, commands, worker_commands}`. `statistics()` returns copied
phase/queue/activity/completed counts and heap counters, without live state.
Closing rejects queued work, cancels the active source invocation and retires
its roots before closing the application heap. The close promise settles after
that cleanup. Fatal cancellation skips source finalizers according to the
existing language rules; runtime cleanup remains required.

Generated modules use `nex.typescript-application/1`, with the checked revision,
source hash, reachable unit hashes, entries and operation sites. Their matching
managed scheduler, heap, controller and React adapter participate in generated
file identities. No npm dependency/lock/notice changes are introduced. The
TypeScript checking library includes ES2022 for existing runtime array APIs;
the generated JavaScript target stays ES2020.

## Qualification and remaining work

`tests/persistent_ui.py` compares ordinary source execution and native/web test
adapters, checks complete generated projects under strict TypeScript and runs
the persistent controller in Node. It exercises event ordering, copied inputs,
independent applications, retained views, transient cycles, typed errors,
Worker responses, stateful HTTP commands, cancellation, deadlines, budgets,
queue admission, cleanup and rejected programs. Actual browser interaction is
recorded separately from these controller checks. The
[focused0.272 receipt](evidence/persistent-ui-0.272.0-2026-11-17.json) retains
matching identities, original fixture failures and qualification limits.

Native persistent application/task-provider lifetimes, reference transport to
workers, reference task debug/profile and complete current platform/portable
SDK qualification remain open. Source versions, canonical graph identities,
public task ABIs7/8 and C ABI1 are unchanged. Published SDK0.246.1 is immutable.
