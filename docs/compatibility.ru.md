---
status: current
applies_to: "toolchain 1.0.0; language 0.30"
owner: repository
---

# Условия совместимости NEX 1.x

Условия совместимости 1.x действуют с выпуска SDK 1.0.0. Версия языка в
`nex.json` и версия установленного SDK задаются отдельно. Например, SDK 1.0.0
создаёт проект с `"language": "0.30"`.

| На что опирается проект | Что предусматривают условия 1.x |
| --- | --- |
| Исходники на языке 0.30 | Программа с документированным синтаксисом и стабильными API продолжает проходить проверку и сохраняет определённое спецификацией поведение при пересборке следующим SDK 1.x для поддерживаемой платформы. Смена режима языка, меняющая смысл программы, требует явного выбора и миграции. |
| Стандартная библиотека | Сохраняются пути импорта, имена модулей, сигнатуры функций, эффекты, параметры типов и порядок полей конструкторов. Возможны новые модули и функции. Каталог 1.0.0 содержит 21 модуль, 217 функций и 38 типов. |
| CLI для инструментов и LLM | Контракт описывает поля успешных JSON-ответов команд `describe`, `init`, `check`, `test`, `eval` и `run` для обычного нативного проекта. Клиент читает именованные поля и допускает появление дополнительных полей. |
| История проекта | Восстановление полного снимка графа сохраняет ревизии, их идентификаторы и версии языка. Явная миграция проверяет исходную ревизию и добавляет новую. |
| Нативные библиотеки и устройства | Для двоичных компонентов учитываются целевая платформа, версия ABI, среда исполнения и версия провайдера. В выпуске указываются конкретные проверенные SDK, устройства и операции GPU/NPU. |

В Git сохраняйте исходные файлы, `nex.json`, тесты и проверенный
`nex.lock.json` с зависимостями. Если после смены SDK команда `nex check`
возвращает `E_LOCK`, сверьте изменившиеся зависимости. Для согласованного
обновления выполните `nex lock`, проверьте изменения lock-файла и повторите
тесты. Для переноса полной локальной истории отдельно сохраните снимок графа.
[Что хранить в Git](getting-started.ru.md) · [Версии и миграция](compatibility.md)

Для каждой платформы проверена пара архивов [публичной беты 0.281.0](https://github.com/sae-ru/NEX/releases/tag/v0.281.0) и SDK 1.0.0. [Результаты по платформам](https://github.com/sae-ru/NEX/releases/download/v1.0.0/compatibility.json) Проверяются старые проекты и их зависимости, восстановление
снимка, миграции, ответы CLI, публичные сигнатуры и результаты выполнения
на поддерживаемых средах. Исходная точка для проверки конкретного выпуска —
его файл `qualification.json` и контрольная сумма архива своей платформы.
[Каталог API 1.0](../llm/stdlib-public-api-1.0.0.json) · [Контракт CLI](cli-consumer-contract.md) · [Проверка стандартной библиотеки](stdlib-source-compatibility.md)

## Как пересобрать Windows SDK из тега

Откройте чистую копию исходников тега `v0.281.0` или `v1.0.0`. Скачайте
из этого выпуска в `downloads/windows-release/` файл `qualification.json`
и три скрипта — `nex-windows-sdk-distribution.py`,
`nex-windows-native-task-sessions.py` и `nex-windows-sdk-task-streams.py`.
Они выбирают Node для npm, связывают тестовые DLL с библиотеками UCRT из SDK
и записывают пути к исходникам в отчёте потокового ввода-вывода.
[Файлы беты](https://github.com/sae-ru/NEX/releases/tag/v0.281.0) · [Файлы 1.0](https://github.com/sae-ru/NEX/releases/tag/v1.0.0)

В корне проекта перед сборкой CMake выполните команды PowerShell. Они сверяют
контрольные суммы и копируют скрипты по путям из записи выпуска.

```powershell
$ErrorActionPreference = 'Stop'
$assets = Get-Item -LiteralPath '.\downloads\windows-release'
$release = Get-Content -Raw -LiteralPath (Join-Path $assets.FullName 'qualification.json') | ConvertFrom-Json
if ((git rev-parse HEAD) -ne $release.qualification_main_commit) { throw 'Release tag and checkout differ' }
$inputs = @($release.windows_packaging_tool, $release.windows_host_session_fixture, $release.windows_stream_report_writer)
foreach ($item in $inputs) {
    $path = Join-Path $assets.FullName $item.file
    if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ne $item.sha256) { throw "SHA256 mismatch for $path" }
}
foreach ($item in $inputs) {
    Copy-Item -LiteralPath (Join-Path $assets.FullName $item.file) -Destination $item.checkout_path
}
```

Дальнейшие команды устанавливают SDK через CMake и упаковывают переносимый архив. [Сборка и упаковка Windows SDK](sdk-build.md#building-and-packaging-the-installation)

## Как проверить два архива у себя

Откройте каталог исходников NEX тега `v1.0.0` на той системе, для которой собраны оба SDK. Из каждого выпуска скачайте `qualification.json` и архив SDK для вашей ОС и процессора. Поместите файлы беты в `downloads/beta/`, файлы 1.0 — в `downloads/stable/`. В каждом каталоге переименуйте архив в `sdk.tar.gz`. Проверяющая программа сверяет размер и SHA256 с записью о выпуске и проверяет содержимое распакованного SDK. [Архивы беты 0.281.0](https://github.com/sae-ru/NEX/releases/tag/v0.281.0) · [Архивы 1.0.0](https://github.com/sae-ru/NEX/releases/tag/v1.0.0)

В корне исходников установите версию TypeScript из lock-файла командой `npm --prefix web ci`. Для Linux и macOS в Bash или Zsh выполните следующие команды.

```sh
export NEX_NODE="$(command -v node)"
export NEX_TSC="$PWD/web/node_modules/typescript/bin/tsc"
unset NEX_SKIP_TYPESCRIPT
python3 -B tools/sdk_compatibility.py --release-record downloads/beta/qualification.json --baseline-archive downloads/beta/sdk.tar.gz --candidate-release-record downloads/stable/qualification.json --candidate-archive downloads/stable/sdk.tar.gz --output build/compat-0.281-to-1.0
```

На Windows x64 выполните эти команды в PowerShell с нативными Python и Node.js.

```powershell
$env:NEX_NODE = (Get-Command node.exe -CommandType Application -ErrorAction Stop).Source
$env:NEX_TSC = (Resolve-Path -LiteralPath 'web/node_modules/typescript/bin/tsc' -ErrorAction Stop).Path
Remove-Item Env:NEX_SKIP_TYPESCRIPT -ErrorAction SilentlyContinue
python -B tools/sdk_compatibility.py --release-record downloads/beta/qualification.json --baseline-archive downloads/beta/sdk.tar.gz --candidate-release-record downloads/stable/qualification.json --candidate-archive downloads/stable/sdk.tar.gz --output build/compat-0.281-to-1.0
```

Для каждого прогона выбирайте новый выходной каталог. При успешной проверке код завершения равен нулю, а в `build/compat-0.281-to-1.0/report.json` записано `"ok": true`. Поле `baseline_target` указывает платформу. Сверьте `baseline_archive_sha256` и `candidate_archive.archive_sha256` с контрольными суммами двух скачанных архивов. [Результаты для всех платформ](https://github.com/sae-ru/NEX/releases/download/v1.0.0/compatibility.json)

## Как перенести историю проекта с Windows на macOS

Для переноса исходников через Git сохраните правило `*.nex -text` в корневом
`.gitattributes`. Мы клонировали один проект на языке 0.30 с двумя
зафиксированными файлами библиотеки, с LF и CRLF, на Windows x64, Fedora x86-64
и macOS ARM64. С этим правилом при обоих значениях `core.autocrlf` получилась
одна ревизия NEX. На каждой системе прошёл тот же тест и нативная программа
вывела `42`. Без правила при `core.autocrlf=true` Git изменил байты библиотеки,
и SDK на всех трёх системах сообщил `E_LOCK`. [Настройка Git для проекта](getting-started.ru.md#что-хранить-в-git)

В каталоге исходного проекта выполните `nex snapshot --directory ../stock-snapshot`. Скопируйте каталог снимка целиком, включая `graph.db` и `snapshot.json`, на другой компьютер. Из родительского каталога выполните следующие команды.

```sh
nex recover stock-snapshot --directory recovered
cd recovered
nex history --json
```

Выберите идентификатор ревизии из истории. Команда `nex run --revision ID --profile release` запустит эту версию, а `nex export --revision ID --directory ../stock-src` выгрузит её редактируемые исходники в новый каталог. Принимающий SDK соберёт нативную программу для своей платформы.

Перед публикацией SDK 0.281.0 для Windows x64 записал две ревизии проекта складского учёта на языке 0.30. Кандидат SDK 1.0.0 для macOS ARM64 восстановил обе. Интерпретатор и нативная сборка показали остаток 7 для первой ревизии и 6 для второй. Веб-тест прошёл в каждой ревизии. После экспорта оба исходных файла побайтово совпали с оригиналами Windows, включая переводы строк CRLF. [Контрольные суммы компиляторов, снимка и исходников](evidence/windows-macos-snapshot030-2026-11-23.json)
