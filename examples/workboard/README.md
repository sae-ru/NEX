# NEX Workboard

One language0.30 project combines a persistent browser controller, a native
HTTP server, SQLite, file export/restore and a dedicated summary Worker.
Run the example with SDK 1.0. Its installed acceptance includes this application.
The application's compiled native server and browser assets run without an LLM.

Copy this directory to your own workspace. Keep `.nex` build/graph state and
the private `var` directory out of Git; commit the `.nex` sources, `nex.json`,
this `.gitignore` and any custom `web` assets. Run from the copied directory:

```sh
nex check client.nex --json
nex check server.nex --json
nex test client.nex --target web --json
nex build client.nex --target web --profile release --json
nex build server.nex --target server --profile release --json
mkdir -p var/exports
nex token --user demo --auth var/auth.json --json
```

Use the executable and browser `dist` paths reported by the two builds:

```sh
SERVER --auth "$PWD/var/auth.json" --database "$PWD/var/workboard.sqlite" \
  --files-root "$PWD/var/exports" --files-write 1 --static DIST --port 8080
```

Open `http://127.0.0.1:8080`, enter the generated token, add a task and mark it
complete. **Calculate summary** sends copied items to a separate browser Worker;
its result counts Unicode scalars. **Export file** writes a per-user JSON file;
**Restore export** replaces that user's database snapshot from the file.
Restarting the server or reloading the page preserves saved tasks. Sign in again
after a reload: the example deliberately keeps the bearer token only in memory.

The model supports up to500 tasks of1..2000 scalars. IDs are consecutive; imported
snapshots are checked against the same model. File names encode the authenticated
principal's UTF-8 bytes, with a96-byte principal limit for export/restore.
Existing1MiB JSON/storage/file limits also apply; not every combination of the
item-count and text-length upper bounds fits in one snapshot.
SQLite transactions and file publication are separate: exporting a file does
not become part of a database rollback. Restore is an explicit replacement,
not a merge. This example has no registration, collaborative editing or detached
server job queue. The server's child task joins before its HTTP response; the
browser Worker is the independently running background computation.

Client state contains typed cells retained by one application owner. Published
views and outgoing commands are copied values. Each event carries its outgoing
command batch, so ordinary edits do not resend a previous request. Responses
are matched to the pending request/job; sign-out clears those identities and
cancels outstanding work. Server/database/filesystem code stays outside the
client's reachable browser graph.

Run the retained integration fixture from a source checkout:

```sh
python3 tests/workboard_application.py /absolute/path/to/nex --output /new/output
```

It checks native Debug/Release HTTP behavior, actual database restart and file
contents, generated TypeScript execution and a production web build. Actual
browser UI interaction and portable SDK/platform qualification are separate
evidence scopes.

По-русски: это один прикладной проект, объединяющий интерфейс, сервер, SQLite,
файлы и фоновый Worker. Исходники и манифест кладите в Git; `.nex/` и `var/` —
локальные данные. Токен вводится после каждой загрузки страницы. Экспорт
сохраняет файл, восстановление явно заменяет сохранённый список. Серверная
задача завершается в пределах запроса; Worker считает сводку отдельно от UI.
