---
status: current
applies_to: "toolchain 0.280.0; language 0.30"
owner: repository
---

# Blocking storage in owner-thread tasks

Source0.30 server functions can combine structured tasks and `db`. Storage
operations execute as blocking atoms on the invocation owner thread. Native
programs select task ABI8 when a reachable task graph declares `db`, including
programs with no cells. Other reference-free task programs retain ABI7.
Discover `task_storage` in the selected compiler; retained SDKs may reject this
combination. This adds backend support without changing source syntax, source
versions, canonical identities or stored graph history.

```nex
module saved;
server fn main() -> unit !{task,db,throw,io} {
  let value: str = with_tasks(1, server fn(scope: task_scope) -> str !{task,db,throw} {
    let saved: task<str> = task_spawn(scope, server fn() -> str !{task,db} {
      task_yield();
      assert(unwrap(store_put("answer", "42")));
      return unwrap(store_get("answer"));
    });
    return task_wait(saved);
  });
  print(value);
}
```

`store_get`, `store_put`, `store_remove` and `store_keys` preserve the existing
typed Result and [storage contracts](server.md#storage-and-transactions).
They require `server` and `db`. A task callback declaring `db` also declares
`task`, and its server caller must declare every requested host effect.
Ordinary blocking helper functions may declare only `db`; they are lifted into
the same continuation graph. Existing fs/ffi/state/throw requirements remain.

For CLI evaluation/native execution, configure the existing `NEX_DATABASE`
filesystem path and optional `NEX_STORAGE_OWNER`. Each standalone operation
retains its individual transaction. The task scope does not create a database
transaction spanning multiple calls.

For HTTP, all related source continuations execute on the request's owner
thread and borrow its lexical `StorageScope`. They keep the authenticated
principal and existing transaction across yields and child calls. The HTTP
boundary commits a successful response and rolls back non-success responses,
uncaught source errors and fatal controls. Ambient CLI database configuration
does not replace that borrowed request transaction. Separate requests own
separate scopes and can execute on different request threads.

SQLite calls remain blocking, including their bounded busy wait. Cancellation
cannot preempt an in-progress SQLite call; ordinary runtime/HTTP control checks
apply around source execution and before commit. There is no async database
executor, transferable SQLite connection or browser database capability here.
The existing source error, Result and cleanup rules remain distinct. The
TypeScript browser backend continues to reject reachable server code; browser
applications access this service through copied HTTP commands.

`tests/task_storage.py` checks reference/native Debug/Release storage with no
cells, callback effect rejection, retained029 behavior and actual HTTP child
calls with commit/rollback/source-error/control outcomes. The
[Workboard example](../examples/workboard/README.md) combines this path with
persistent browser state, a dedicated Worker, SQLite and file export/restore.
Complete source/platform/portable SDK qualification remains separate.

[Focused0.280 evidence](evidence/workboard-task-storage-0.280.0-2026-11-17.json)
records the19-group source block, the additional four integration repairs,
the moved normal installation and actual Chrome flow with exact artifact
identities. This is separate from the complete portable SDK workflow.

По-русски: задачи030 могут выполнять операции SQLite на потоке владельца.
В HTTP они сохраняют транзакцию и пользователя запроса; в CLI каждая операция
остаётся отдельной транзакцией. Это блокирующая БД. Соединение не переносится
на рабочие потоки и не передаётся браузеру. Для таких нативных задач выбирается
ABI8 даже без ячеек; прочие задачи без ссылок сохраняют ABI7.
