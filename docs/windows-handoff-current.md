# Передача NEX: нативная Windows

Обновлено: 2026-11-01 12:45 UTC. Итог этапа: полный Windows CTest принят, SDK и игра
проверены в перечисленных ниже областях. Старые Mac-результаты не являются
приёмкой Windows. Версии: toolchain **0.152.1**, language **0.27**, task ABI **7**.

## Начать здесь

Пользователь просил исправить исходные 179 отказов, обеспечить локальную Windows
без WSL, нативные EXE/FFI/CUDA и учебную игру с GUI/GPU. Затем попросил сделать
игру переносимой и сохранить статус в репозитории, выполнить commit/push.
Ветка: `codex/windows-native-acceptance`, origin: `https://github.com/sae-ru/NEX.git`.
Коммит/push этого задания явно разрешены; PR, merge в main и force-push не заказаны.
Git history определяет delivery commit; перед продолжением проверь `git status`,
`git log -1` и upstream, сохрани новые изменения пользователя.

Прочитай `AGENTS.md`, README и `llm/SYSTEM_PROMPT.md`. Возможности узнавай у
выбранного бинарника через `describe --json`, контекст — `context --symbol`.
`PLAN.md` содержит будущие возможности. Язык и ABI в этом этапе не менялись.

## Доказанный результат

- **274/274 CTest groups passed**, 0 failed, 0 skipped outer groups, 7719.83 s.
  Обычный unelevated Windows token, не AppContainer. DevMode включён.
  Compiler/resources/harness SHA не менялись во время полного прогона.
- Python reporting: 1018 случаев, 48 явных пропусков в 22 группах.
  Это platform-only, opt-in live, старые cross-toolchain и отдельный genuine025
  compiler случаи; не выдавай их за исполненные. Список включён в квитанцию.
- Тот же полный прогон: **35/35 CUDA hardware cases**, reference/native,
  физический RTX 3090, enqueue/cancel/deadline и завершение/очистка.
- Новый CMake install, перемещённый SDK31: native EXE/static archive/Wasm/package,
  установленный default compiler CUDA preparation, hardware **35/35**, memcheck
  **35 native + context probe**, ноль memory errors/leaks, deadline **2000 ms**.
- Игра из установленного SDK: четыре `.bat`, native/reference/TypeScript,
  реальная очередь SDL, пять ходов до X-win/score, GPU readback (13216 цветных
  пикселей), самостоятельный пакет после скрытия исходного проекта.

Основные маленькие доказательства в Git:

- [Windows full](evidence/windows-native-2026-11-01.json).
- [Installed SDK/CUDA/memcheck](evidence/windows-sdk-2026-11-01.json).
- [Игра](evidence/tic-tac-toe-sdl-windows-final-2026-11-01.json).
- [Исходный file-sharing сбой и исправление](evidence/windows-cache-sharing-2026-11-01.json).
- [Named Pipes вместо TCP в sanitizer](evidence/windows-cuda-local-ipc-2026-11-01.json).

Сырые логи, JUnit, IR, harness/cohort pins, GPU ledger и executables остаются
в `build/`, не в Git. Их пути и SHA указаны в квитанциях. Полный отчёт:
`build/windows-final30/report.json`, JUnit: `build/windows-final30/ctest.xml`,
разбивка: `build/windows-final30/case-accounting.json`. Все процессы этого прогона
завершены; перезапускать старые exec sessions не нужно.

## Локальные инструменты и точные pins

- Windows 11 Pro for Workstations build 26200, i5-12400F, 64 GiB RAM.
- RTX 3090 24 GiB, driver 617.14, CUDA Driver API 13.4, headers 12.1.
- Compiler: `build/windows-host/nex.exe`, SHA-256
  `672077caf4a468850ea3d67f97879c07e47bd5b39d53f5df87dc3adec4493d01`.
- LLVM/MLIR **22.1.8**, host `build/deps/windows-host/clang64`;
  target `build/deps/llvm-mingw-20260616-ucrt-x86_64`. Это native PE/UCRT,
  без MSYS/Cygwin/WSL runtime. Не смешивать C++ ABI/CRT host и target.
- Отдельный LLDB **23.1.4**: `build/deps/windows-debugger23-source-f/clang64`.
  Все четыре SHA — в full receipt. Рецепт/locks/upstream patch:
  [windows-debugger-build.md](windows-debugger-build.md), `tools/windows/`.
- Python: `C:/Python314/python.exe`; CMake: `C:/Program Files/CMake/bin/cmake.exe`.
- Финальный перенесённый SDK: `build/SDK Windows 31 переезд % 🧠`.
  Его `bin/nex.exe` имеет тот же SHA. SDK включает native/Wasm toolchain,
  runtime, stdlib, notices, примеры и CUDA helpers. Python/Node/CMake/Ninja,
  GPU driver/CUDA headers, sanitizer и LLDB остаются явными prerequisites.

## Запуск и исходники игры

```powershell
Set-Location F:/sae/NEX
.\nex.cmd doctor --json
Set-Location examples/tic-tac-toe
.\build.bat
.\test.bat
.\run.bat
.\package.bat
```

Канонические исходники: [examples/tic-tac-toe](../examples/tic-tac-toe/README.md).
Правила, состояние, счёт, события и cleanup находятся в NEX; SDL3 C FFI даёт
окно/ввод/GPU. `.build/last-package.txt` указывает последний готовый пакет;
распространяется весь `dist/...`, вход — `bin/app.exe`. Сборка первого SDL
зависит от сети или `--sdl-archive build/deps/SDL3-3.4.18.tar.gz`; архив закреплён
SHA-256, сторонние notices включены. Не добавлять большой SDL архив в Git.
Старый `examples/windows-tic-tac-toe` содержит перенаправления.
Общие `.sh` собирают нативно на macOS/Linux с соответствующим SDK и драйвером;
в этой Windows-приёмке их выполнение не проверялось; Mac-дополнение находится ниже. GUI выбирает D3D11/Metal/OpenGL, software
renderer отвергается. CUDA compute — отдельный пример, не часть рисования игры.

## Воспроизведение проверки

Сначала установи закреплённые зависимости по `tools/windows` и руководству
[windows-host.md](windows-host.md). Нельзя считать старый `build/local/native-env.ps1`
актуальным: он задаёт wave9 и LLDB22. Задавай resources и LLDB явно.

```powershell
$env:PATH="F:/sae/NEX/build/deps/windows-host/clang64/bin;"+$env:PATH
$env:PYTHONUTF8='1'
& 'C:/Program Files/CMake/bin/cmake.exe' --build build/windows-host -j4
C:/Python314/python.exe -X utf8 tools/windows/freeze_cohort.py `
  --build build/windows-host --output build/my-fresh-cohort
C:/Python314/python.exe -X utf8 tools/windows/verify_native.py `
  --cohort build/my-fresh-cohort `
  --debugger-prefix build/deps/windows-debugger23-source-f/clang64 `
  --output build/my-fresh-verification --jobs 4 --cuda
```

Нужны новые output-каталоги. Запускай от обычного пользователя Windows,
вне AppContainer Codex, без UAC/admin. DevMode/LongPaths уже включены здесь.
Пока runner работает, не меняй закреплённые resources/harness/бинарники.
Обрыв времени наблюдения не означает остановку теста: проверь настоящий процесс
и report state, не запускай дубликат. `tools/windows/verify-native.cmd` использует
сохранённый cohort30 этой машины; на новом checkout сначала создай свой cohort.

Внутренние случаи учитывает публичный `tools/windows/account_tests.py`:
`python tools/windows/account_tests.py --verification build/my-fresh-verification`.
Он использует полный LastTest.log, поскольку JUnit обрезает часть verbose output.

Для SDK: `cmake --install build/windows-host --prefix NEW_PREFIX`, затем
`tools/sdk_bundle.py --sdk NEW_PREFIX --output NEW_BUNDLE --notices FILE`.
Registry notices должен содержать точные reviewed dependency roots/licenses;
локальный пример: `build/local/windows-sdk-notices.json`.
При проверке перенесённого SDK очищай NEX_* overrides и чужие toolchain PATH,
иначе source-tree fallback может скрыть ошибку установки. Все CUDA scripts
находятся в `SDK/share/nex/tools/owned-cuda`; инструкция — их README.

## Существенные исправления

Windows Jobs/ACL/Unicode, joined teardown и кооперативная остановка HTTP/tasks;
PE/DLL shared runtime, IAT ownership, FFI lifetime/packaging и static vendor
notices; профиль каждого образа и exported root identity; LLDB/DAP аргументы,
Win32 thread IDs, полные Unicode/long DLL paths и reconciled modules. Для
file cache `readFile` теперь разрешает FILE_SHARE_DELETE, а atomic publication
общая через FileRenameInfoEx. Детерминированный тест с настоящим DELETE handle
падает на старом compiler и проходит на новом. Не ослаблять эти контракты.

Default Windows watchdog только родительской тестовой CLI-обвязки — 180 s
вместо 60 s для холодной C++ компиляции под нагрузкой. Source task budgets,
явные тестовые limits, GPU deadline, проверки памяти/IR не отключались.
После full30 исправлены только установка/пути CUDA helper-скриптов и случайные
CRLF в 14 файлах (возвращены исходные LF; Python AST совпадают). SHA компилятора
не изменился, actual installed SDK перепроверен.

## Брандмауэр и прежний запрет EXE

Скриншот пользователя относился к старому `cuda SDK 23/.../context-probe.exe`:
это сетевое разрешение Firewall, не запрет исполнения. Старый probe завершился,
окно можно отменить. Sanitizer использует
`NV_COMPUTE_SANITIZER_LOCAL_CONNECTION_OVERRIDE=named-pipes`; у обычного и
инструментированного probes не наблюдались TCP/UDP endpoints. Правила Firewall,
Defender/AppLocker и TDR не менялись. Старый точный `nex-windows-...exe` по одному
префиксу не установлен; не приписывай ему диагноз context-probe.

## Что остаётся открытым

- Полная maintained 40-phase квалификация Windows SDK; scoped SDK checks выше
  не переименовывать в complete acceptance. LLDB не встроен в SDK.
- Linux-запуск SDL и повторная Windows-проверка текущей Retina-поправки; Mac-область описана ниже.
- Windows ARM64 execution, отдельные legacy cross-SDK/OS-only fixtures и
  opt-in core/live методы из case accounting требуют своих окружений/квитанций.
- General GPU lowering, matmul, NVCC/MSVC, Metal compute, NPU/mobile/UI и другие
  пункты PLAN. CUDA здесь принимает U8 Add/Affine и storage I8/I32.

Исходные 94 pass / 179 fail / 1 skip, промежуточные 258/16 и прерванный full26
сохранены в исторических квитанциях. Удачные focused проверки не заменяют full;
новый принятый full30 — отдельный результат с неизменёнными SHA.
Не коммитить build, binaries, caches, `.nex`, пользовательские графы или секреты.
Сохранять `.gitattributes` и точные исходные байты/историю.

## Дополнение macOS после Windows-передачи

Компилятор0.155 проверил отдельное исправление координат Metal readback для
Retina/letterboxing: [точный отчёт](evidence/sdl-metal-retina-0.155.0.json).
Восемь сцен включают исходный и перенесённый read-only пакет с запретом чтения
проекта/SDK; число пикселей подтверждено независимым чтением BMP. Само изображение
тестовой партии сохранилось. Это не новая Windows-приёмка: текущую поправку
`examples/tic-tac-toe/native/gui.cpp` ещё нужно запустить на Windows и Linux.
Результаты Windows выше остаются привязаны к их прежним исходникам/компилятору.
