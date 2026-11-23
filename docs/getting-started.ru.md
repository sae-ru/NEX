# Начать работу с NEX

Из этих исходников собирается **кандидат SDK 1.0.0**. Новые проекты используют язык **0.30**.
Если версия языка не указана, компилятор использует 0.28. Версии ABI задач — 7/8.
Обычный CLI поддерживает читаемый исходный код, runtime-контракты и явную
миграцию старых графов с сохранением истории.

[English](getting-started.en.md) · [Описание](overview.ru.md)

Выберите опубликованный тег, у которого в разделе Assets есть архив для вашей ОС
и процессора и соответствующий файл `.sha256`. Системные требования указаны
в описании релиза. [Релизы GitHub](https://github.com/sae-ru/NEX/releases)

## Установить SDK для Linux или Windows из релиза

Откройте пустой каталог, в котором хотите хранить SDK. При запуске команд
введите тег релиза и **точное имя архива** из списка Assets. Храните весь
распакованный каталог вместе. PATH изменяется только в текущем терминале.

**Linux (Bash).** Для `uname -m` = `x86_64` выберите
`nex-sdk-<версия>-linux-amd64-development.tar.gz`, для `aarch64` —
`nex-sdk-<версия>-linux-arm64-development.tar.gz`. В том же релизе должен быть файл `<архив>.sha256`.

Для нативной сборки нужны заголовочные файлы C/C++ и стартовые объектные файлы
GCC для вашей архитектуры. Команда `getconf GNU_LIBC_VERSION` покажет версию
glibc в системе. В описании релиза указаны старшие требуемые версии символов
glibc и libstdc++ для каждого архива. Полные списки находятся в
`share/nex/sdk-bundle.json` внутри SDK. Если в системных библиотеках нет нужных
версий символов, используйте сборку из исходников или Linux-контейнер с
подходящими библиотеками.

```bash
read -r -p 'Release tag: ' tag
read -r -p 'Archive filename: ' archive
url="https://github.com/sae-ru/NEX/releases/download/$tag"
curl -fL "$url/$archive" -o "$archive" &&
  curl -fL "$url/$archive.sha256" -o "$archive.sha256" &&
  sha256sum --check --strict "$archive.sha256" &&
  tar -xzf "$archive" &&
  sdk_bin="$(pwd -P)/${archive%.tar.gz}/bin" &&
  test -x "$sdk_bin/nex" &&
  export PATH="$sdk_bin:$PATH" &&
  nex doctor --json
```

**Windows x64 (PowerShell).** Выберите `nex-sdk-<версия>-windows-x86_64-development.tar.gz`
и файл `.tar.gz.sha256` из того же релиза. Для распаковки используется системная команда `tar.exe`.

Выполните команды в обычном PowerShell. Для скриптов SDK установите Python
3.10+ для Windows. Для веб-проектов также нужны Node.js 22.18+ и npm. Для живой
отладки установите LLDB и lldb-dap для Windows.

```powershell
$tag = Read-Host 'Release tag'
$archive = Read-Host 'Archive filename'
$url = "https://github.com/sae-ru/NEX/releases/download/$tag"
Invoke-WebRequest -UseBasicParsing -ErrorAction Stop -Uri "$url/$archive" -OutFile $archive
Invoke-WebRequest -UseBasicParsing -ErrorAction Stop -Uri "$url/$archive.sha256" -OutFile "$archive.sha256"
$sum = (Get-Content -LiteralPath "$archive.sha256" -Raw -ErrorAction Stop).Trim() -split '\s+', 2
if ($sum.Count -ne 2 -or $sum[1] -cne $archive -or $sum[0] -notmatch '^[0-9a-fA-F]{64}$' -or
    (Get-FileHash -Algorithm SHA256 -LiteralPath $archive -ErrorAction Stop).Hash -ine $sum[0]) {
    throw 'Archive checksum or filename mismatch'
}
tar.exe -xzf $archive
if ($LASTEXITCODE -ne 0) { throw 'Archive extraction failed' }
$bin = (Resolve-Path -LiteralPath (Join-Path ($archive -replace '\.tar\.gz$', '') 'bin') -ErrorAction Stop).Path
if (!(Test-Path -LiteralPath (Join-Path $bin 'nex.exe') -PathType Leaf)) { throw 'Missing bin/nex.exe' }
$env:Path = "$bin;$env:Path"
nex.exe doctor --json
```

Затем в том же терминале перейдите в свой обычный каталог проектов и
[создайте приложение](#создать-приложение). Если в релизе нет SDK для вашей
платформы, воспользуйтесь инструкцией по сборке из исходников ниже.

## Установить SDK для macOS ARM64

[SDK 0.280.1](releases/0.280.1.json) требует macOS 27.0+ на ARM64, Apple command-line
tools с macOS SDK и Python 3.10+. Для веб-сборок нужны также Node.js 22.18+ и npm.
Переносимый архив для разработки включает выбранный компилятор и зависимости
библиотек. Храните весь распакованный каталог вместе.

В пустом каталоге введите тег релиза (например, `v0.280.1`). Архив останется
в этом каталоге. Каждая версия SDK распакуется в свой каталог под `~/.local/nex`.

```sh
printf 'Release tag (e.g. v0.280.1): '
IFS= read -r tag
archive="nex-sdk-${tag#v}-macos-arm64-development.tar.gz"
url="https://github.com/sae-ru/NEX/releases/download/$tag"
sdk_dir="$HOME/.local/nex"
curl -fL "$url/$archive" -o "$archive" &&
  curl -fL "$url/$archive.sha256" -o "$archive.sha256" &&
  shasum -a 256 -c "$archive.sha256" &&
  mkdir -p "$sdk_dir" &&
  tar -xzf "$archive" -C "$sdk_dir" &&
  sdkroot_path="$(xcrun --sdk macosx --show-sdk-path)" &&
  export SDKROOT="$sdkroot_path" &&
  export PATH="$sdk_dir/${archive%.tar.gz}/bin:$PATH" &&
  nex doctor --json &&
  nex describe --kind index --json
```

[Результаты приёмки](evidence/sdk-current-0.280.1-2026-11-17.json) закрепляют
исходный коммит, архив и проверки перенесённой/восстановленной установок.
Живые LLDB/DAP прошли приёмку этого архива. Подписи ad-hoc; Developer ID
и notarization остаются отдельными этапами.

## Собрать актуальную версию

Установите C++20, CMake3.25+, LLVM **и MLIR22.1.x или 23.1.x**, SQLite3.37+, OpenSSL **3 или4**,
Z3 с файлами разработки и Python3.10+. Для веба/TypeScript нужны Node.js22.18+
и npm. Нативному исполнению нужен компилятор/SDK целевой платформы, живой
отладке — совместимый LLDB. Сохраняйте `web/package-lock.json` репозитория.

В Unix полному набору тестов исходников также нужны matching LLVM `ld.lld` и `llvm-ar`
для [проверок выбора ELF-библиотек](native-runtime-search.md). Если ELF LLD
установлен отдельно, добавьте `-DNEX_ELF_TEST_LD=/absolute/path/to/ld.lld` к
команде конфигурации CMake ниже. Этот параметр независим от `NEX_WASM_LD`.

```sh
git clone --branch main https://github.com/sae-ru/NEX.git
cd NEX
git rev-parse HEAD
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j 4
npm --prefix web ci --cache "$PWD/build/npm-cache" --ignore-scripts --no-audit --no-fund
NEX_TSC="$PWD/web/node_modules/typescript/bin/tsc" \
NEX_NPM_CACHE="$PWD/build/npm-cache" \
ctest --test-dir build --output-on-failure
cmake --install build --prefix /absolute/path/to/nex-sdk
export PATH="/absolute/path/to/nex-sdk/bin:$PATH"
nex doctor --json
nex describe --kind index --json
```

Полный набор тестов исходников включает TypeScript, даже если вашему приложению
не нужен браузерный клиент. `npm ci` устанавливает точные версии из lock-файла;
`NEX_TSC` и `NEX_NPM_CACHE` выбирают этот компилятор и заполненный кэш для тестов.
Команды выше выполняются из корня репозитория. В PowerShell перед CTest задайте:

```powershell
$env:NEX_TSC = (Resolve-Path web/node_modules/typescript/bin/tsc).Path
$env:NEX_NPM_CACHE = (Resolve-Path build/npm-cache).Path
ctest --test-dir build --output-on-failure
```

Укажите `LLVM_DIR`, `MLIR_DIR`, `OPENSSL_ROOT_DIR`, `NEX_Z3_ROOT`, если CMake не
находит выбранные зависимости. Дополнительным DNS/HTTP-группам нужны явные
`NEX_CARES_PREFIX` / `NEX_HTTP_PREFIX`. Там, где нет автоматического определения
владельца файлов, тестам упаковки нужен настоящий операторский
`NEX_PACKAGE_NOTICES_FILE`. Число тестов зависит от конфигурации. Рецепты:
[SDK](sdk.md), [Linux](linux.md), [Windows](windows-handoff-current.md).
Используйте согласованный OpenSSL 3 или 4: оба диапазона принимаются, OpenSSL 4 проверен на Fedora 45.
Приёмка SDK относится к конкретному архиву; см. [руководство SDK](sdk.md) и
[результаты платформ](../README.ru.md#состояние-разработки).

## Прежние архивы SDK

Выберите архив для своей платформы в [GitHub Releases](https://github.com/sae-ru/NEX/releases)
и проверьте опубликованную SHA256 перед распаковкой. Для каждого выпуска
указаны исходный коммит, поддерживаемый компьютер и область приёмки.

[Квитанция macOS ARM64 SDK0.162](releases/0.162.0.json) закрепляет точный архив
`nex-sdk-0.162.0-macos-arm64-development.tar.gz`, минимум macOS27.0:

```text
SHA256 c1393c94709d3e3290d39b1a60da7ad78e28705bfa6cea539e74ff7e40bc6208
```

Это исторический архив 0.162.0. Для текущей реализации выберите соответствующий
опубликованный SDK или соберите снимок исходников по инструкции выше и проверьте
фактические `doctor` и `describe`. Клонирование
`main` выбирает опубликованный HEAD ветки: его версия может отличаться от ещё
не опубликованного рабочего checkout. [Версия 0.159](https://github.com/sae-ru/NEX/releases/tag/v0.159.0)
тоже сохраняет свою отдельную историческую область.

Храните `bin/nex` и `share/nex` вместе. Выбирайте свою ОС/архитектуру: бинарник
macOS ARM64 не запускается под Windows. Обычная установка CMake использует
локальные зависимости; переносимые архивы требуют отдельной проверки замыкания
зависимостей и переноса. В квитанции0.162 проверены настоящие Python3.10.22/3.14.9,
запрет чтения исходников и зависимостей, перенесённый и восстановленный SDK без
права записи, веб-сборки и живая отладка. Внутренние ресурсы архива закреплены
снимком; актуальный статус публикации смотрите в этой инструкции в Git.

Проверьте версии языка, инструментария и пути через `doctor` и `describe`.
При работе из GUI-агента выполните эти команды и в его терминале.

## Создать приложение

```sh
nex init my-app --language-version 0.30
cd my-app
nex check --json
nex test --json
nex run --json
nex build --profile release --json
```

Редактируйте `.nex` и повторяйте check/test. Собранная нативная программа может работать без
NEX и LLM, когда доступны её фактические зависимости среды исполнения и системы.
Путь артефакта указан в JSON сборки. [examples/learn](../examples/learn)
показывает значения, типизированные ошибки и параллельную обработку данных на CPU.

`nex.json` задаёт язык, вход и библиотеки. `nex.build.json` добавляет компоненты,
а `nex lock` закрепляет зависимости. Старой истории графа нужна явная миграция;
замена номера версии её не выполняет.

## Что хранить в Git

Исходники, манифесты, lock-файлы, тесты, согласованные постановки задач и контракты, нужные
ресурсы и конфигурацию сборки. Исключайте пароли, локальные разрешения (grants), ключи,
кэши, бинарники и `node_modules`. [Пример `.gitignore` и команды Git для проекта](quickstart.md#3-что-хранить-в-git)

Git исходников сам по себе не хранит полную историю ревизий/ID семантического
хранилища. Для неё используйте snapshot/export отдельно от генерируемых кэшей:

```sh
nex snapshot --directory ../my-app-snapshot --json
```

При распространении runtime-кода NEX сохраняйте его [MIT-уведомление](../LICENSE)
и уведомления сторонних компонентов. Для собственных исходников приложения
можно выбрать свою лицензию.

Перед переносом хранилища или сменой языка прочитайте [snapshots](snapshots.md),
[history](history.md) и [руководство миграции на текущий язык](source-contract-migration.md).
Для графов до 0.18 поле `origin_verified: false` означает, что историческая
семантическая идентичность не подтверждена. Даже при `target_valid: true`
сначала проверьте архивный исходник и перенос отдельной копии, сохранив оригинал.

## Как подключить LLM

Дайте модели [BOOTSTRAP](../llm/BOOTSTRAP.md) и [контракт программирования](../llm/SYSTEM_PROMPT.md).
Она должна получать возможности от компилятора, запрашивать ограниченный
контекст символов и проверять поведение. [LEARNING](../llm/LEARNING.md) содержит
краткую точку входа. Приёмку определяют компилятор и тесты, а не уверенность ответа.

Откройте каталог приложения как рабочую папку агента и выполните в его терминале
`nex doctor --json`, чтобы сверить выбранный SDK. [Плагин Codex](https://github.com/sae-ru/NEX/blob/main/plugins/nex/README.ru.md) · [Настройка Hermes и общих инструкций проекта](quickstart.md#4-hermes-codex-и-другие-llm)
