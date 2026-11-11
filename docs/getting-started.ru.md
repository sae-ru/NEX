# Начать работу с NEX

Текущие исходники: **toolchain 0.223.0 / язык 0.28 / task ABI 7**, в разработке.
Обычный CLI поддерживает читаемый исходный код, runtime-контракты и явную
миграцию старых графов с сохранением истории.

[English](getting-started.en.md) · [Описание](overview.ru.md)

## Собрать актуальную версию

Установите C++20, CMake3.25+, LLVM **и MLIR22.1.x или 23.1.x**, SQLite3.37+, OpenSSL **3**,
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
Используйте согласованный OpenSSL 3 или 4: оба диапазона принимаются, OpenSSL 4 проверен на Fedora 45. Приёмка
текущего переносимого SDK ещё идёт; см. [результаты платформ](../README.ru.md#состояние-разработки).

## Прежние архивы SDK

[Квитанция macOS ARM64 SDK0.162](releases/0.162.0.json) закрепляет точный архив
`nex-sdk-0.162.0-macos-arm64-development.tar.gz`, минимум macOS27.0:

```text
SHA256 c1393c94709d3e3290d39b1a60da7ad78e28705bfa6cea539e74ff7e40bc6208
```

Это исторический архив 0.162.0, а не SDK 0.165. Приёмка переносимого SDK 0.165
ещё идёт. Для текущей реализации соберите соответствующий снимок исходников
по инструкции выше и проверьте фактические `doctor` и `describe`. Клонирование
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
nex init /path/to/my-app
cd /path/to/my-app
nex check --json
nex run --json
nex test --json
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
кэши, бинарники и `node_modules`.

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
