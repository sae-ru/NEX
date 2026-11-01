# Запуск и проверка NEX на Windows

База — `948d72b39bf16b9e8f3797d7ac0a613be28727bb`, toolchain 0.152.1,
язык **0.27**, current native task ABI **7**. Windows-изменения находятся в
`codex/windows-native-acceptance`; это ещё не выпущенный SDK. Mac delivery
record, старые ABI и PLAN сохраняют свои области и версии.

Машина: Windows 11 Pro for Workstations **26200.9711**, x86-64,
Intel i5-12400F (6 ядер / 12 потоков), 68 477 890 560 байт видимой ОС RAM,
RTX 3090 24 GiB, драйвер **617.14**, CUDA driver API **13.4**, локальный NTFS.
Режим разработчика включён по явному запросу пользователя для настоящих symlinks.

## Цепочки исполнения

WSL Ubuntu-22.04 собирает и запускает NEX: LLVM/MLIR 22.1.8, CMake 3.31.6/Ninja,
Python 3.10.12, SQLite 3.37.2, OpenSSL 3.0.2, Z3 4.8.12. LLVM-MinGW 22.1.8/UCRT
производит Windows PE с отдельными библиотеками SQLite 3.54.1 для x64/ARM64.
Сами x64 PE запускаются native Windows Python 3.14.3 / PowerShell. TypeScript
сравнивается в native Windows Node 24.14.0. Wine не используется.

Прямые Windows runtime/CUDA tests собираются **native** LLVM-MinGW 22.1.8.
Driver-probe использует `cuda.h` из Toolkit 12.1, загружает системную `nvcuda.dll`
через driver C ABI, не линкует CUDART и не требует NVCC. MSVC C++/CRT не смешаны
с GNU/UCRT приложением. Все точные package/binary pins записаны в evidence.

Архивы и SHA-256: [dependencies.json](../tools/windows/dependencies.json).
Linux LLVM-MinGW распаковывается в **ext4 WSL**: native Windows `tar` теряет
обязательные symlinks. Большие зависимости и бинарные результаты находятся
в игнорируемом `build/` и `/home/sae/nex-deps`.

## Запуск на этой машине

Из `F:\sae\NEX`:

```powershell
.\tools\windows\run-target.ps1 `
  -Source .\build\native-acceptance-2\core\main.nex `
  -Toolchain .\build\native-acceptance-2\toolchain.json `
  -Profile release
```

Это последовательность **WSL build → native Windows execution**. Обычный
Linux `nex run --toolchain ...` продолжает возвращать `E_TARGET_RUN` для чужого
ABI. Скрипт не выдаёт себя за Windows-hosted SDK и не добавляет grants.
Он принимает `-Entry NAME` и `-ProgramArguments` для аргументов приложения.

Для standalone файлов явно задайте свой существующий Windows-каталог:

```powershell
$env:NEX_FILES_ROOT='F:\sae\NEX\build\native-acceptance-2\files\данные 🧠'
$env:NEX_FILES_WRITE='1'
.\tools\windows\run-target.ps1 `
  -Source .\build\native-acceptance-2\files\main.nex `
  -Toolchain .\build\native-acceptance-2\toolchain.json -Profile debug
```

Для БД отдельно задаются `NEX_DATABASE` и `NEX_STORAGE_OWNER`. Автотесты
проверяют реальные UTF-8/NUL bytes в stdout независимо от отображения консоли.

## Повторение проверок

Output-каталог сохраняет NEX sources, IR, notices, metadata, команды,
stdout/stderr и SHA-256 артефактов. Для нового прогона укажите новый `--output`:

```powershell
python tools/windows/acceptance.py `
  --producer /home/sae/nex-build/nex `
  --toolchain-root /home/sae/nex-deps/llvm-mingw-20260616-ucrt-ubuntu-22.04-x86_64 `
  --sqlite-root build/deps/sqlite-windows --output build/my-windows-run

python tools/windows/acceptance.py `
  --producer /home/sae/nex-build/nex `
  --toolchain-root /home/sae/nex-deps/llvm-mingw-20260616-ucrt-ubuntu-22.04-x86_64 `
  --sqlite-root build/deps/sqlite-windows `
  --section storage --output build/my-storage-run

python tools/windows/typescript_acceptance.py `
  --producer /home/sae/nex-build/nex `
  --projects build/my-windows-run --output build/my-typescript-run
```

`--resume` сохраняет исходный failed report и разрешён только для CPU/files.
Пройденный случай переиспользуется только с прежними source, compiler binary,
descriptor, target toolchain и artifact SHA-256. Старый receipt без binary pin
требует нового output-каталога. Storage требует свежую БД.

Все 15 сценариев [windows_runtime_contracts.py](../tests/windows_runtime_contracts.py)
запускаются WSL Python с аргументом `/home/sae/nex-build/nex`, `TMPDIR` на
`/mnt/f/...` и переменными:

```text
NEX_WINDOWS_CONTRACT_TOOLCHAIN=/mnt/f/sae/NEX/build/native-acceptance-2/toolchain.json
NEX_WINDOWS_CONTRACT_RUNNER=["/mnt/c/Python314/python.exe","F:\\sae\\NEX\\tools\\windows\\run_pe.py"]
NEX_WINDOWS_CONTRACT_REPORT=/mnt/f/sae/NEX/build/windows-contracts/report.json
```

Генерация, reference, TypeScript, proof и profiling в этом наборе остаются WSL.
Каждое `run`-наблюдение собирает PE и запускает его native Windows Python:
37 PE observations в 12 сценариях; ещё три сценария проверяют rejected inputs.

Для полного CTest producer в WSL сначала загрузите окружение, включая явно
выбранный **pinned TypeScript compiler** (наличия одного Node недостаточно):

```sh
source /mnt/f/sae/NEX/tools/windows/producer-env.sh
cmake --build /home/sae/nex-build -j 4
ctest --test-dir /home/sae/nex-build -j 4 --output-on-failure
```

Зависимости веба устанавливаются `npm ci --ignore-scripts` из `web/` с исходным
lock-файлом. `NEX_TSC` указывает на его `node_modules/typescript/bin/tsc`;
набор дополнительно проверяет совпадение версии с pin проекта.

В distro Z3 4.8.12 один proof исчерпывает исходный resource limit. Тот же SMT
запрос на официальном Z3 5.3.1 укладывается в прежние лимиты; отдельная сборка
`/home/sae/nex-build-z3-5.3.1/nex` прошла 11 verifier methods. Это кандидат:
Ubuntu LLVM одновременно загружает `libz3.so.4`, а NEX — `libz3.so.5.3`.
Нужно согласовать зависимость LLVM/Z3 перед SDK-приёмкой. Основной compiler и
его полный CTest не подменялись этой сборкой; бюджеты не увеличивались.

Прямой Windows-набор задаётся [tools/windows/CMakeLists.txt](../tools/windows/CMakeLists.txt)
и не требует Windows MLIR. Здесь уже настроен Ninja `build/windows`:

```powershell
& 'C:\Program Files\CMake\bin\cmake.exe' --build build/windows -j 4
& 'C:\Program Files\CMake\bin\ctest.exe' --test-dir build/windows --output-on-failure
```

Для новой конфигурации передайте `NEX_SQLITE_SOURCE` с `sqlite3.c` и пути к
native LLVM-MinGW C/C++/Ninja. Необязательный `NEX_CUDA_INCLUDE` добавляет
физический CUDA prerequisite test. Без этого параметра GPU test не регистрируется;
это не считается его прохождением.

## Проверенный scope

Точная квитанция: [windows-native-2026-10-31.json](evidence/windows-native-2026-10-31.json).

| Проверка | Состояние | Область |
|---|---|---|
| Native NTFS runtime | passed | 24: Unicode/NUL/bytes, ACL, reparse, parent/root replacement, отмена, leases, quotas, SQLite |
| Native Windows ASan | passed | Те же 24 проверки с инструментированным runtime и SQLite; это не Windows LSan |
| NEX CPU/tasks/files | passed | 36 debug/release PE executions + 3 rejected source checks; typed file payload и отмена |
| SQLite из NEX | passed | 12: Unicode path/principal, независимые процессы, повторное открытие, отсутствие grant |
| TypeScript на Windows | passed | 10 CPU/task случаев; результаты/ошибки, нулевые retained frames/calls |
| Runtime contracts | passed | 15 сценариев, 37 native PE observations; остальные среды разделены выше |
| CUDA driver prerequisite | passed | 38 launches: U8 Add/Affine, 1..262144 элементов, reuse, CPU reference, overflow |
| CUDA memcheck | passed | Compute Sanitizer 2023.1.0: 0 errors на driver-probe |
| NVCC 12.1 / MSVC 19.44 | failed | `Host compiler targets unsupported OS`; обход проверки не применялся |
| Полный CTest producer | failed | 253/271 групп passed, 18 failed; первый прогон 6226.35 s. Повторы и внутренние skips записаны отдельно |
| ARM64 Windows | pending | PE cross-build отделён от исполнения; физической ARM64 Windows здесь нет |
| Windows-hosted compiler / portable SDK | pending | Нужны Windows LLVM/MLIR и порт POSIX частей driver/process/debug/package |
| Windows `parallel_map` | pending | Обычные structured tasks проверены; отдельный native parallel mapping target всё ещё ограничен macOS/Linux |
| Windows DLL/FFI и CUDA из NEX | pending | Загрузчик POSIX; `std/device` CUDA provider не реализован |
| Windows debugger/profiler, HTTP, browser delivery | pending | Windows Node comparison не является browser/UI/SDK acceptance |
| DirectX / DirectML / NPU | pending | RTX 3090: DirectX12, feature level12_2, WDDM3.2; системная DirectML DLL есть, выполнение не проверялось. По OS name/class query NPU не найден |

CUDA probe записывает `NEX_invocation=false`, идентичность выбранного GPU 0
(PCI/UUID), не делает CPU fallback и ждёт физического завершения до освобождения
буферов. CPU/upload/kernel/download/total timing разделены; ускорение не заявляется.
CUDA cancellation/deadline, nested scopes, typed errors и owned resources остаются
pending. Успешные CPU/file проверки на CUDA не переносятся.

Первый полный прогон использовал исходные лимиты и основной compiler. В его
стартовом окружении был пропущен `NEX_TSC`: это причина девяти failed групп.
Все девять групп прошли повторные проверки с pinned TypeScript. Они записаны
отдельно и не
переписывают исходные JUnit/LastTest. Один тест завершения LLDB исправлен и
прошёл отдельно: логическая команда может закончиться выходом процесса.
Ещё пять private LLDB-наборов не прошли ожидаемые checkpoint/stop assertions;
их исходники, IR, binaries и отчёты сохранены в `build/ctest-failures`.
Один proof на Z3 4.8.12 исчерпал неизменённый resource limit. В отдельном
последовательном повторе с прежними лимитами `task_foreign` прошёл;
`public_task_write_delivery` снова завершился `E_TASK_TIMEOUT` при shared task run.

В JUnit нет пропущенных групп, но unittest сообщает **31 внутренний skip**.
Evidence содержит счётчики и JSON summaries по группам, а также буквальные
условия skip из исходников; эти условия не выдаются за runtime trace.
Не настроены дополнительные conformance-наборы DNS/c-ares и HTTP/curl/nghttp2;
они не входят в зарегистрированные здесь 271 группу. Windows cross-build
проверяет обе архитектуры; единственный внутренний skip `windows_targets` —
не настроенный Wine. Это не мешает отдельным native x64 Windows-проверкам.

Ledger driver-probe: 152 allocations/152 frees, 72 events created/destroyed,
по одному context/module создано и закрыто, live buffer bytes0, cleanup errors0,
peak buffer bytes786436. Показания общей свободной памяти GPU приведены отдельно:
устройство также обслуживает Windows display. ASan-конфигурация создаётся с
`NEX_WINDOWS_ASAN=ON`; для запуска нужен `bin` и `x86_64-w64-mingw32/bin`
той же LLVM-MinGW установки в `PATH` (динамические ASan/libc++ DLL).

Исходные sandbox/Developer Mode сбои, failed task/file IR и первоначальная ошибка
ожидаемого diagnostic code в runner сохранены в `build/local` и
`build/native-acceptance-*`. Требования не ослаблялись. Общий PLAN и полный
Windows/CUDA SDK этим этапом не завершаются.
