# Локальный компилятор NEX для Windows

Нативный `nex.exe` собран для Windows x64. Он читает/проверяет NEX-проекты,
генерирует MLIR/LLVM IR и вызывает Windows LLVM-MinGW для создания PE `.exe`.
Сборка и исполнение выполняются Windows-процессами; WSL для этого пути не нужен.
Язык остаётся **0.27**, toolchain — **0.152.1 development**, task ABI — **7**.
Это локальная development-сборка; полная приёмка переносимого SDK — отдельный scope.

## Запуск на этой машине

Из PowerShell:

```powershell
$Nex='F:\sae\NEX\build\windows-host\nex.exe'
Set-Location F:\sae\NEX\examples\windows-host
& $Nex doctor --json
& $Nex run --json
& $Nex build --profile release --json
```

Короткий launcher: `F:\sae\NEX\nex.cmd`. Он передаёт аргументы локальному
`nex.exe` и сохраняет текущий каталог проекта. Добавлять WSL или менять PATH
для запуска компилятора не требуется.

Пример выводит `NEX: локальная Windows 🧠` и `42`. Поле `executable` в результате
`build` содержит путь к самостоятельному Windows-приложению. Его можно запускать
обычным оператором PowerShell `&`. Compiler и target application — разные `.exe`.
Manifest компилятора включает UTF-8 и long-path awareness и запрашивает
`asInvoker`. Нативный цикл проверяется в обычном пользовательском Windows-контексте.
Отказ доступа к Temp песочницы Codex сохраняется отдельно от этих результатов.

Рядом с `nex.exe` находятся измеренные DLL-зависимости. Их граф и SHA-256
записаны в `build/local/windows-host-dll-closure.json`; зависимости от
`msys-2.0.dll`, `cygwin1.dll` и WSL отвергаются проверкой сборщика комплекта.
Папку `build/windows-host` пока не следует переносить отдельно: development
сборка использует явные локальные пути к исходникам runtime и target toolchain.

## Windows-цепочка сборки

Host: CLANG64/UCRT Clang/LLVM/MLIR **22.1.8**, libc++/libunwind22.1.8,
OpenSSL3.6.5, SQLite3.54.0, Z3 4.16.0. Нативные MSYS2-пакеты проверены
PGP-подписями с официальным keyring; это Windows PE-библиотеки.
Точные версии, SHA-256, fingerprints и зависимости находятся в
[host-dependencies.lock.json](../tools/windows/host-dependencies.lock.json).

Target: отдельный Windows LLVM-MinGW22.1.8 из закреплённого ZIP и статический
SQLite3.54.1. Host/target C++-библиотеки не передаются через ABI-границу:
target Clang и приложения запускаются отдельными Windows-процессами.
LLVM-MinGW Windows ZIP хранит общие headers в `prefix/include`;
`configure-host.ps1` создаёт архитектурные junction внутри этого же SDK.
Проверки UCRT/libc++/headers и notices при этом сохраняются.

```powershell
.\tools\windows\configure-host.ps1
$env:PATH="F:\sae\NEX\build\deps\windows-host\clang64\bin;$env:PATH"
& 'C:\Program Files\CMake\bin\cmake.exe' --build build/windows-host --target nex -j4
python tools/windows/bundle_native.py build/windows-host/nex.exe `
  --dependencies build/deps/windows-host/clang64/bin `
  --readobj build/deps/windows-host/clang64/bin/llvm-readobj.exe `
  --report build/local/windows-host-dll-closure.json
```

`NEX_DEFAULT_TOOLCHAIN` задаётся при конфигурации CMake и входит в compiler
build identity вместе с SHA-256 JSON. `--toolchain FILE` остаётся явным override.
Выбор ABI, sysroot, runtime notices и содержимого зависимостей продолжает
участвовать в toolchain/build fingerprints. MLIR использует те же пять conversion
passes и проверки IR; для Windows линкуются соответствующие C++ static components.

## Проверки

Тот же corpus CPU/tasks/files используется с нативным producer:

```powershell
python tools/windows/acceptance.py --producer-environment windows `
  --producer build/windows-host/nex.exe `
  --toolchain-root build/deps/llvm-mingw-20260616-ucrt-x86_64 `
  --sqlite-root build/deps/sqlite-windows --output build/my-native-host-run
```

Для SQLite добавьте `--section storage` и новый output-каталог. Для TypeScript
используйте `typescript_acceptance.py --producer-environment windows` с тем же
producer, `--projects` предыдущего corpus и отдельным `--output`.
Все команды/IR/stdout/stderr и binary SHA-256 сохраняются в output-каталогах.

Итоговый локальный corpus: **41** CPU/tasks/files case (38 PE-исполнений в
debug/release и3 rejected-программы), **12** SQLite case и **10** TypeScript case.
`print` сравнивается без нормализации строк, включая CR/LF/NUL и UTF-8.
Пример из каталога `Проект 🧠` прошёл build/run/test, standalone PE execution,
snapshot/recover, исполнение `--revision HEAD` и явный source export.
Результаты одной сборки и её SHA закрепляет
[Windows host evidence](evidence/windows-host-2026-10-31.json).

Готовый пример на этой машине: `F:\sae\NEX\build\windows-host-ready\hello.exe`.
Нативный compiler: `F:\sae\NEX\build\windows-host\nex.exe`;
compiler DLL closure хранится рядом и измерена отдельно от target-приложения.

Канонический Windows CTest завершён за **1578.41s**: **94 passed**, **179 failed**,
**1 skipped** из274 групп. Из179 неуспешных групп20 не были исполнены из-за
непостроенных executables или failed fixtures; это не зачтено как успешный skip.
Ещё **89** пропусков зарегистрированы внутри Python-наборов, включая наборы с
ошибками. Исходные guards и сырые статусы JUnit сохранены в receipt.
Всецельная сборка вернула1:22 тестовых compile steps пока используют POSIX API.
Среди остальных отказов — POSIX fixtures (`/dev/null`, `os.uname`, `/tmp`),
Windows cleanup открытых SQLite fixtures и недоступные shared/FFI/HTTP/profile
интеграции. Полная Windows-регрессия не принята; ошибки не объявлены решёнными.

Проверка доказательств прошла **11/11**. Runtime-контракты прошли **13/15**;
два оставшихся сценария требуют Windows profile build, который явно отклоняется.
Эти результаты относятся к binary SHA-256
`b92dbe5d2aa22ccfc317a1ea6fd56c592750779a5b0bf39a91cefa84f46c9bfc`.

Дополнительный `windows_host_runtime` CTest проверяет реальную private ACL,
reparse rejection, sparse read за4GiB без изменения cursor, Unicode argv/env/cwd,
exit42, отсутствие утечки process handles, joined job timeout, orphan descendants
и8MiB output cap. Процессы создаются suspended, включаются в Job Object до resume,
наследуют только три standard handles; завершение job проверяется перед возвратом.
Ошибка запуска содержит Windows error code и имя `.exe`.

После `TerminateJobObject` supervisor удерживает handles всех полученных через
completion port участников и ожидает их signaled state. Число уведомлений
проверяется по `TotalProcesses`; потеря уведомления или незавершённый teardown
даёт явную ошибку после10s, а не успешный результат. Основание для process-handle
barrier — [описание завершения процесса Microsoft](https://learn.microsoft.com/en-us/windows/win32/procthread/terminating-a-process).

Для проверок настоящих символических ссылок на этой машине включён Windows
Developer Mode. Компилятор и пример исполняются с обычным пользовательским
токеном, без elevation и без AppContainer. Исключения Defender/AppLocker не
добавлялись. По сообщённому префиксу `nex-windows-` точный прежний заблокированный
файл установить не удалось; доступные журналы проверены отдельно.

Предыдущий [target-only этап](windows-native-acceptance.md) с WSL producer
сохранён исторически в коммите `4ed5453`. Его SHA/результаты не переносятся на
новый Windows-hosted compiler. CUDA driver-probe также остаётся отдельной
проверкой; CUDA-вызовы из NEX и полный Windows debugger/provider/profiler/SDK
сохраняют собственные незавершённые области.


## Продолжение Windows-переноса 2026-10-31

Результат 94 passed / 179 failed относится к исторической сборке выше.
Диагностический полный повтор на компиляторе
`e4580209356dff08e4bb3b11fce33bf788501385182762d58eff88ccd64b1c43`
дал 175 passed / 98 failed / 1 skipped из 274 за 2878.29 s. Обвязки тестов
продолжали переноситься во время этого прогона; это не окончательная приёмка.
Хеши исходных журналов и JUnit сохранены в
[evidence/windows-progress-2026-10-31.json](evidence/windows-progress-2026-10-31.json).

Последующая сборка отдельно прошла HTTP/TLS/ACL/остановку сервера,
`native_tool_arguments`, `task_typescript_public`, исключения native/TypeScript
и `typed_source_native`. Настоящие PE/DLL-проекты с двумя библиотеками уже
исполняют обычные функции и задачи с общим runtime; профиль содержит точную
идентичность приложения и нулевой остаток объектов/handle. Пакет приложения
запускался после переноса из другого cwd с PATH только из System32. Остальные
проверки упаковки, debugger и SDK ещё требуют общего повторного прогона.

CUDA теперь проверена из NEX, включая независимый evaluator и native EXE:
35 сценариев прошли на RTX 3090 без WSL/NVCC/CPU-подмены. Отдельный host probe
проверил вложенные реальные CUDA contexts, очистку и запрет повторного входа.
См. [точную квитанцию CUDA](evidence/windows-cuda-2026-10-31.json) и
[провайдер с командой аппаратной проверки](../experiments/owned-cuda/README.md).
Результат относится к закреплённому в квитанции компилятору и модулю;
полная Windows-регрессия пока не принята.

Windows HTTP-сервер поддерживает кооперативную остановку через событие
`Local\NEX.Server.Stop.<PID>` с защищённым ACL текущего пользователя.
Контроллер открывает его с `EVENT_MODIFY_STATE` и вызывает `SetEvent`.
Запросы получают отмену, сервер ожидает завершения обработчиков и освобождает
runtime. Нативный task supervisor аналогично принимает прерывание через
`Local\NEX.Task.Stop.<PID>` и подтверждает физическое завершение Job Object.
Это позволяет управляющим процессам проверить очистку без TerminateProcess.
