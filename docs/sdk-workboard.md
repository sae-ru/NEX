---
status: current
applies_to: "toolchain 0.280.0; language 0.30"
owner: repository
---

# Installed Workboard SDK workflow

Starting with toolchain0.280, the complete SDK acceptance contract requires
phase43, `workboard-application`, after the [reference030 phase](sdk-reference030.md).
The0.279 contract remains42 phases; earlier SDKs retain their own original
phase lists. This workflow change does not alter the compiler or source version.

[Focused preparation](evidence/sdk-workboard-preparation-0.280.0-2026-11-17.json)
passed both web modes from a matching moved normal installation, with three
SDK unit groups. It does not qualify a portable archive.

The installed helper consumes the SDK's [Workboard example](../examples/workboard/README.md)
and installed test scripts. It verifies both native Debug/Release images select
ABI8, then runs24 ordinary HTTP requests across four clean server starts.
Each profile creates Unicode data, updates it, exports an actual JSON file,
changes the database, restores the file and checks data after a server restart.
Requests carry profile/server identities, so a missing release or restart cannot
be replaced by repeated debug requests. Two ordinary users retain separate data.
The local source copy is absent during native server execution.

Generated TypeScript runs the persistent application controller and isolated
Worker entry. It checks retained state, immutable published views, command
batches, Unicode scalar counts, file commands, late response handling and
closed-state cleanup. The example, helper, test scripts and required
storage/task/library resources have SHA256 identities in the SDK receipt.
The final validator checks commands, actual response values, file hashes,
profile coverage, cleanup and declared web scope.

`--browser` additionally requires a real locked TypeScript/Vite production
build. Without it, the helper generates the web project and executes its
TypeScript controller without a Vite build; its static HTTP fixture is not
advertised as a browser application. Portable SDK assemblers select `--browser`.
This phase does not claim actual browser UI interaction or a complete SDK on
its own. The separate [0.280 application evidence](evidence/workboard-task-storage-0.280.0-2026-11-17.json)
records an actual Chrome flow.

For focused development, use an installed compiler and its matching resources:

```sh
python3 SDK/share/nex/tests/sdk_workboard.py SDK/bin/nex \
  --resources SDK/share/nex --output /new/workboard-check --browser
```

This requires the documented native and Node/npm development tools. Full
qualification still requires the [committed source-to-archive workflow](sdk-build.md),
all source groups and the complete moved/restored SDK workflows. A successful
focused check does not publish an archive or qualify other platforms.

По-русски: новая обязательная фаза проверяет прикладной проект именно из SDK —
два профиля сервера, SQLite после перезапуска, экспорт и восстановление файла,
постоянное состояние UI и Worker. Полный пакет собирает production-клиент;
упрощённый режим явно отмечает отсутствие такой сборки. Одна фаза не заменяет
всю приёмку SDK.
