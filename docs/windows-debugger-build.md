# Сборка отдельного Windows-отладчика

Компилятор NEX и его target toolchain используют LLVM/MLIR 22.1.8.
Для проверки остановок в Windows DLL подготовлен отдельный LLDB 23.1.4
с исходными Windows-исправлениями. Этот отладчик не меняет версию языка,
task ABI или компилятор приложений. Сборка и запуск встроенного Python
проверены. Последующий полный Windows-прогон с этим LLDB принят: CLI/DAP
результаты и SHA находятся в окончательной квитанции в конце этого документа.
Полная квалификация установленного SDK остаётся отдельной областью.

В [манифесте исходников](../tools/windows/lldb23-windows-backport.json)
закреплены SHA-256 официального архива LLVM, общего патча и каждого из
11 изменённых файлов, а также пять исходных upstream PR/commit.
[Патч](../tools/windows/lldb23-windows-backport.patch) переносит исправления
учёта путей DLL, устаревших trap, блокировок потоков и совместной доставки
очереди Windows debug events. Дополнительная адаптация использует IPv4
loopback для внутренней пары сокетов; политики сети Windows не меняются.
Также перенесено управление временем жизни активного исключения, необходимое
для нового event loop. Локальное исправление сверяет список DLL с PSAPI через
`EnumProcessModulesEx` и `GetModuleFileNameExW` с буфером 32768 символов.
Это устраняет потерю раннего `LOAD_DLL` и обрезание имени по `MAX_PATH`
в Toolhelp32; временные speculative mappings Windows не считаются отдельным
постоянным runtime приложения.
Кандидат с этими изменениями прошёл 12 повторов настоящих DLL breakpoint,
stack/watch и продолжения до нормального выхода. Полная DAP/SDK-приёмка
сохраняет отдельный статус.

## Подготовка зависимостей

Нужны обычный Windows x64, Python 3.14, CMake, Git for Windows и свободное
место для LLVM SDK и C++ objects. WSL, MSYS shell и Visual Studio не нужны.
Все пути ниже задаются из корня репозитория. Native CLANG64/UCRT пакеты
проверяются PGP-подписями, а не исполняются в MSYS.

`build/deps/clang64-current-yandex.db` — сохранённый снимок package database;
`build/deps/msys2.gpg` — официальный MSYS2 keyring. Для воспроизведения
именно этой сборки версии и хеши пакетов должны совпадать с двумя lock-файлами:
[runtime](../tools/windows/debugger23-dependencies.lock.json) и
[build SDK](../tools/windows/debugger-build23-dependencies.lock.json).
Более новый снимок database может содержать другие версии и не считается
эквивалентным этим входам.

```powershell
python -X utf8 tools/windows/fetch_host_deps.py `
  --database build/deps/clang64-current-yandex.db --keyring build/deps/msys2.gpg `
  --debugger-only --debugger-version 23.1.4-1 `
  --prefix build/deps/windows-debugger23-native `
  --lock-output build/local/debugger23-runtime-reproduced.lock.json

python -X utf8 tools/windows/fetch_host_deps.py `
  --database build/deps/clang64-current-yandex.db --keyring build/deps/msys2.gpg `
  --debugger-build-sdk --debugger-version 23.1.4-1 `
  --prefix build/deps/windows-debugger-build23 `
  --lock-output build/local/debugger23-sdk-reproduced.lock.json
```

Официальный архив `llvm-project-23.1.4.src.tar.xz` берётся по `source_url`
из манифеста и сохраняется в `build/deps/`. Скрипт ниже проверяет SHA-256
до распаковки. В существующем source-каталоге он проверяет хеши всех
изменённых исходников и отвергает несовпадение.

## Компиляция и установка кандидата

```powershell
python -X utf8 tools/windows/build_debugger.py `
  --output build/deps/windows-debugger23-reproduced/clang64
```

Output должен быть новым каталогом. Скрипт собирает все цели с `-j4`,
копирует отдельный runtime, устанавливает LLDB и проверяет настоящий запуск
встроенного Python. Значение `LLDB_PYTHON_HOME=..` разрешается относительно
`bin/liblldb.dll`; рядом с `bin` остаётся `lib/python3.14`.
При ручном вызове CMake в PowerShell весь аргумент нужно заключать в кавычки:
`'-DLLDB_PYTHON_HOME:STRING=..'`.

Сборщик также встраивает [process manifest](../tools/windows/debugger-windows.manifest)
в EXE-инструменты LLDB: UTF-8, `longPathAware` и `asInvoker`. Это требуется
встроенному Python при чтении захваченных DLL и sidecar из длинных каталогов.
Глобальные политики Windows сборщик не меняет.

В установленном prefix сохраняется `nex-debugger-build.json` с командами,
выводом startup, хешами executable/DLL и lock-файлов.
Поле `full_debugger_regression_accepted` остаётся `false`: успешная сборка
сама по себе не подтверждает работу breakpoint, stack/watch и DAP.

Для выбора кандидата задайте абсолютные `NEX_LLDB` и `NEX_LLDB_DAP`,
а его `bin` поставьте первым в PATH. Не смешивайте `liblldb.dll`, Python
и `lldb-server.exe` из разных prefix. Проверки NEX должны использовать
компилятор и resources из одного сохранённого cohort.

## Полная проверка

После focused CLI/DAP проверок запустите из обычного пользовательского
Windows-терминала, без elevation и AppContainer:

```powershell
python -X utf8 tools/windows/freeze_cohort.py `
  --build build/windows-host --output build/windows-wave30-cohort

python -X utf8 tools/windows/verify_native.py `
  --cohort build/windows-wave30-cohort `
  --debugger-prefix build/deps/windows-debugger23-reproduced/clang64 `
  --output build/my-windows-final-verification --cuda
```

Каталог результата должен быть новым. Runner сохраняет полную JUnit CTest,
аппаратную проверку CUDA и SHA входов до/после. Изменение compiler/resources
или тестовых обвязок во время прогона не допускает приёмку. Переносимый SDK
проверяется отдельно после установки и переноса в другой каталог.

## Окончательный прогон 2026-11-01

Вспомогательная сборка `windows-debugger23-source-f/clang64` прошла CLI/DAP,
provider, typed-error и modular HTTP debugger группы в полном неизменяемом
Windows-прогоне **274/274**. Точные четыре executable/DLL SHA и ограничения
содержит [финальная квитанция](evidence/windows-native-2026-11-01.json).
`full_debugger_regression_accepted=false` в старом build-only manifest остаётся
описанием области того отдельного шага сборки. Приёмка его последующего
использования хранится в новом full-run receipt. Полный installed SDK workflow
по-прежнему требует отдельного результата.

## Страницы переменных: исправление 2026-11-04

Прежняя сборка `source-f` воспроизвела тайм-аут установленного SDK 0.162
при запросе последних двух элементов `bytes` размером 4 МиБ на Python 3.10
и 3.14. Рецепт теперь применяет общий с Linux патч ленивого чтения страниц.
Манифест закрепляет хеши патча и исходного/изменённого `Variables.cpp`;
неизвестные исходники отвергаются. Уже исправленный файл проверяется повторно.

Отдельный новый префикс с согласованными LLDB, DAP, сервером, DLL и Python
прошёл тот же сценарий на обеих версиях Python без изменения компилятора NEX,
страничных лимитов или времени ожидания. Прежний префикс сохранён.
[Квитанция](evidence/windows-indexed-pages-development-2026-11-04.json)
описывает этот ограниченный результат. Полный прогон установленного SDK
и изоляция перенесённой/восстановленной установки ещё требуют завершения.
