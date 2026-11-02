# Локальный компилятор NEX для Windows

## Текущий выбор компилятора на стенде 2026-11-02

`F:\sae\NEX\nex.cmd` выбирает отдельно установленный **toolchain0.160.0 /
язык0.28 / ABI7** через `build/current-sdk`. Это устраняет прежний жёсткий
выбор0.152.1 в `build/windows-host`. В обычном пользовательском контексте
прошли check, Debug/Release run/test, Release build и прямое исполнение PE:
контракты, типизированная Unicode/NUL ошибка и joined CPU task дали `42`.
Точные compiler/launcher SHA и границы результата записаны в
[квитанции выбора](evidence/windows-current-compiler-2026-11-02.json).

Полный прогон текущего Windows compiler/CUDA и квалификация переносимого SDK
ещё не завершены. Историческая приёмка0.152.1 ниже сохраняет свою версию.
Переключение launcher не обновляет исходники старого checkout и не мигрирует
язык или граф пользовательских проектов.

## Ранее принятая Windows0.152.1

Текущая подготовка Windows/CUDA выбирает поддержанный язык0.27/0.28 по
согласованным doctor/describe и проверяет идентичность feature-запросов.
Режим CUDA `--source-only` проверяет исходники и FFI-подписи на другом хосте;
Windows DLL, CUDA, GUI/DPI и установленный SDK требуют новых нативных прогонов.
См. [правила cohort и resume](platform-cohorts.md). Результат ниже относится
к точному Windows0.152.1; эти исправления не превращают его в приёмку0.159.

Нативный `nex.exe` собран для Windows x64. Он читает/проверяет NEX-проекты,
генерирует MLIR/LLVM IR и вызывает Windows LLVM-MinGW для создания PE `.exe`.
Сборка и исполнение выполняются Windows-процессами; WSL для этого пути не нужен.
Язык остаётся **0.27**, toolchain — **0.152.1 development**, task ABI — **7**.
Это локальная development-сборка; полная приёмка переносимого SDK — отдельный scope.

Актуальный результат 2026-11-01: **274/274 групп CTest прошли**, 35/35 аппаратных
CUDA-сценариев прошли на том же неизменённом compiler cohort. См.
[окончательную квитанцию](evidence/windows-native-2026-11-01.json),
[перенесённый SDK](evidence/windows-sdk-2026-11-01.json) и
[передачу следующему Codex](windows-handoff-current.md). Промежуточные отказы ниже
сохранены как история, а не текущий результат.

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
`nex.exe` и сохраняет текущий каталог проекта. Если существует
`build/current-sdk/bin/nex.exe`, launcher выбирает этот SDK; иначе выбирает
исторический `build/windows-host/nex.exe`. Проверяйте `doctor --json` именно
через launcher, которым пользуетесь. Добавлять WSL или менять PATH не требуется.

Для выбора отдельно установленной версии создайте junction в игнорируемом
каталоге сборки. `Target` должен указывать на корень SDK с `bin` и `share/nex`:

```powershell
New-Item -ItemType Junction -Path F:\sae\NEX\build\current-sdk `
  -Target 'F:\NEX-SDKs\selected-version'
& F:\sae\NEX\nex.cmd doctor --json
```

Эта команда создаёт новый указатель; существующий `current-sdk` сначала
проверьте. SDK и указатель не входят в Git. Исходники проекта и его история
остаются отдельными от установки компилятора. Выбор новой версии сам по себе
не мигрирует проекты со старой версией языка.

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

## Первоначальные проверки 2026-10-31

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

Для оставшихся debugger-проверок подготовлен отдельный исходный LLDB-кандидат.
Его [рецепт сборки](windows-debugger-build.md), версии зависимостей и upstream
патчи сохранены отдельно; compiler продолжает использовать LLVM/MLIR22.1.8.
Окончательный полный CTest на текущем cohort ещё не завершён.


## Промежуточные полные повторы 2026-11-01

На зафиксированном Windows x64 compiler/resources cohort с SHA-256
`05aab8e2d11eba0f6e2ea836ac1064ba4b54734263b5a8a7d86ffd8df72f1ab2`
завершены все 274 группы: **258 passed / 16 failed / 0 skipped**.
Обвязки и ресурсы во время этого прогона не менялись. Все 35 аппаратных
CUDA-сценариев прошли на том же компиляторе. Это промежуточный результат,
оставшиеся ошибки исправляются; полной приёмкой Windows он не является.
Хеши журналов, JUnit и квитанций сохранены в
[evidence/windows-native-progress-2026-11-01.json](evidence/windows-native-progress-2026-11-01.json).

Все 16 оставшихся групп затем прошли адресные проверки с исправленными
Windows-обвязками. Последние два сценария `task_foreign` проверили повтор
после удаления исходников и исходного FFI bundle; холодные release-сборки
заняли 42–52 s. Windows-фикстура задаёт явный бюджет сборки 300 s для работы
под параллельной нагрузкой; стандартный бюджет production supervisor не менялся.
Сумма отдельных прогонов не заменяет новый полный прогон неизменяемого cohort.

Кроссплатформенный [пример игры](../examples/tic-tac-toe/README.md) использует
SDL 3.4.18 с проверяемым архивом исходников: Direct3D 11, Metal или OpenGL.
В Windows прошли все четыре батника из копии проекта с Unicode/`%` в пути,
native/reference/TypeScript, реальная очередь SDL и чтение пикселей RTX 3090,
а также запуск перенесённого автономного пакета без исходников.
Точная область: [квитанция SDL-примера](evidence/tic-tac-toe-sdl-windows-2026-11-01.json).
Исполнение этой версии в macOS/Linux остаётся непроверенным.

Свежий SDK отдельно прошёл перенос в путь с пробелами, `%` и Unicode,
сборку/исполнение EXE и автономного пакета, native/reference tests,
создание статического архива и Wasm при PATH только из System32.
Python указан явно; полная независимая SDK-приёмка сохраняет отдельный статус.

Учебная игра с правилами на NEX и аппаратным Direct3D 11 доступна в
[examples/windows-tic-tac-toe](../examples/windows-tic-tac-toe/README.md).
В ней есть `build.bat`, `test.bat`, `run.bat`, `package.bat`, исходники
GUI-провайдера и описание нового проекта с нуля. Проверены правила
native/reference/TypeScript и чтение реальных пикселей GPU на RTX 3090.
`nex.cmd` выбирает собранный нативный отладчик, если он находится в локальном
каталоге исходной сборки; явные NEX_LLDB/NEX_LLDB_DAP имеют приоритет.

## Дополнительная гонка публикации 2026-11-01

Повтор cohort26 остановлен после 155 завершённых групп: 153 passed и две
ошибки, `incremental` и `web_workers`. Это частичный диагностический прогон,
не приёмка. Первый сбой воспроизведён отдельным тестом на старом компиляторе:
чтение runtime-заголовка отказывает, пока издатель держит открытый Windows
DELETE handle. Новый compiler использует совместное чтение с
`FILE_SHARE_DELETE` и атомарный `FileRenameInfoEx` для снимков кеша.
Второй сбой — 60-секундный watchdog холодной release-компиляции в Python-тесте.
Windows-обвязка теперь даёт CLI до 180 s; явные бюджеты отдельных проверок и
дедлайны исполняемых NEX-задач сохраняются. После адресных проверок требуется
новый полный прогон на новом compiler/resources cohort.

## Локальный канал CUDA Sanitizer

Запрос брандмауэра для `context-probe.exe` относится к диагностическому
CUDA-процессу, а не к запрету запуска приложения. Для memcheck выбран локальный
`NV_COMPUTE_SANITIZER_LOCAL_CONNECTION_OVERRIDE=named-pipes`. Обычный CUDA probe
и инструментированный probe прошли проверку без обнаруженных TCP/UDP endpoints;
все 35 нативных случаев и context probe прошли memcheck с исходным дедлайном 2 s.
Правила брандмауэра не менялись. [Квитанция](evidence/windows-cuda-local-ipc-2026-11-01.json)
сохраняет точные бинарники, выборки сетевой таблицы и хеши журналов.

## Завершённая Windows-регрессия 2026-11-01

`build/windows-final30/report.json`: `ok=true`, `state=complete`,
`full_windows_regression_accepted=true`, `inputs_unchanged=true`.
Все 274 группы прошли за 7719.83 s; failed/skipped CTest groups — 0/0.
Внутри Python-наборов учтены 1018 случаев и 48 явных пропусков.
Пропуски ОС, opt-in live и старых cross-toolchain fixtures не считаются
исполненными; полная разбивка находится в финальной квитанции.
Компилятор SHA-256 `672077caf4a468850ea3d67f97879c07e47bd5b39d53f5df87dc3adec4493d01`.

После полного прогона изменена только поставка CUDA helpers и восстановлены
исходные LF там, где были случайно добавлены CRLF; Python AST совпадают.
Всецельная сборка сохранила тот же compiler SHA. Настоящий CMake install и
перенос SDK31 проверены с минимальным PATH: native EXE, static archive, Wasm,
автономный package, все четыре батника игры, 35 hardware CUDA и memcheck.
Полная 40-phase квалификация SDK остаётся отдельной незавершённой областью.
