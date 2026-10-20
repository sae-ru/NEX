# NEX: установка и первый проект

NEX — Neural Execution Language, «язык нейронного исполнения». Вы пишете
исходники `.nex` сами или вместе с LLM; компилятор проверяет их и собирает
приложение. Готовой программе для работы не нужна LLM.

Это инструкция для **toolchain0.70 / языка0.16**. Команды ниже проверяются с
этой версией SDK. На20 октября2026 года у проекта ещё нет опубликованного
GitHub Release с готовым установщиком, `brew install nex` или `npm install nex`.
Для воспроизводимой установки ниже закреплён проверенный снимок исходников;
ветки `codex/backup-*` сохраняют работу и сами по себе не означают выпуск.
Возможности установленной версии показывает `nex describe --json`.

Порядок: [установить](#1-установить-nex) → [создать проект](#2-создать-и-запустить-проект)
→ [сохранить в Git](#3-что-хранить-в-git) → [подключить LLM](#4-hermes-codex-и-другие-llm).

## 1. Установить NEX

### Если готовый SDK уже есть

SDK — каталог с `bin/nex` и `share/nex/`. Оставьте их вместе и выберите SDK
для своей ОС/архитектуры. Обычный `cmake --install` требует также библиотеки,
которые использовались при сборке компилятора; переносимый bundle — отдельный
способ упаковки, описанный в [SDK guide](sdk.md).

```sh
export NEX_SDK="/absolute/path/to/nex-sdk"
export PATH="$NEX_SDK/bin:$PATH"
nex doctor
nex describe --json
```

Замените путь своим. `doctor` должен показать ожидаемые `version`, `language`,
`native_compiler` и `runtime_available: true`. Сохраните строки `export` со
своим постоянным путём в `~/.zshrc` или `~/.bashrc`, если хотите пользоваться
`nex` из новых терминалов. Для GUI-агента дополнительно проверьте `nex doctor`
в его собственном терминале: его PATH может отличаться.

### Скачать исходники

Нужны Git и доступ к [репозиторию NEX](https://github.com/sae-ru/NEX).
Следующие команды создают **новую** папку компилятора, отдельно от ваших приложений:

```sh
git clone https://github.com/sae-ru/NEX.git nex-toolchain
cd nex-toolchain
git checkout --detach 37f424b282c257da71dc6b8421789bfd40914448
```

Это проверенный снимок0.70, а не обещание, что `main` или случайная резервная
ветка содержат ту же версию. Для другого снимка сохраняйте его полный commit
SHA и читайте его README/STATUS. Команды работы с приложением ниже не требуют
изменять репозиторий компилятора.

### macOS: сборка и установка

На macOS ARM64 проверена вся основная цепочка. Установка на другой Mac всё
равно требует совместимой версии macOS и зависимостей. Сборки для Intel и
фактическое выполнение на Intel имеют отдельный статус в [README](../README.md).

Что установить:

| Компонент | Для чего |
|---|---|
| Xcode Command Line Tools | Apple SDK, системный компилятор/линкер |
| CMake3.25+, Python3.9+, Git | Сборка и инструменты |
| LLVM **и MLIR22.1.x** | Компилятор NEX и нативный backend |
| SQLite3.37+, OpenSSL3, Z3 | Зависимости текущего компилятора |
| Node.js22.18+ и npm | Веб-приложения и проверки TypeScript |

Если Command Line Tools ещё не установлены, выполните `xcode-select --install`
и завершите установку. Установите [Homebrew](https://brew.sh/) по его инструкции,
затем, из папки `nex-toolchain`:

```sh
brew install cmake python git llvm@22 sqlite openssl@3 z3 node@22
export NEX_LLVM_PREFIX="$(brew --prefix llvm@22)"
export PATH="$NEX_LLVM_PREFIX/bin:$(brew --prefix node@22)/bin:$PATH"
llvm-config --version

cmake -S . -B build -DCMAKE_BUILD_TYPE=Release \
  -DLLVM_DIR="$NEX_LLVM_PREFIX/lib/cmake/llvm" \
  -DMLIR_DIR="$NEX_LLVM_PREFIX/lib/cmake/mlir" \
  -DOPENSSL_ROOT_DIR="$(brew --prefix openssl@3)" \
  -DNEX_Z3_ROOT="$(brew --prefix z3)" \
  -DCMAKE_PREFIX_PATH="$(brew --prefix sqlite)"
cmake --build build -j 4
cmake --install build --prefix "$HOME/opt/nex-sdk-0.70"

export NEX_SDK="$HOME/opt/nex-sdk-0.70"
export PATH="$NEX_SDK/bin:$PATH"
nex doctor
```

`llvm-config` должен сообщить22.1.x; наличие одного LLVM без MLIR недостаточно.
Homebrew использует отдельную формулу `lld@22` для LLD: она дополнительно нужна,
например, для экспериментального Wasm, и не требуется для первого macOS CLI
приложения. Версии пакетов Homebrew меняются; фиксируйте фактически выбранные
версии. Проверенные сборки используют LLVM22.1.8 и Z3 5.3.1.
[Формула LLVM](https://formulae.brew.sh/formula/llvm@22),
[Node22](https://formulae.brew.sh/formula/node@22),
[Z3](https://formulae.brew.sh/formula/z3).

### Linux и Windows через Linux-окружение

Поддерживаемый рецепт окружения — Ubuntu24.04 в Docker. Он скачивает
LLVM/MLIR/LLD22.1.8, Z3, Node и системные зависимости с проверками, указанными
в `tools/linux/Dockerfile`. На Windows используйте Linux-окружение WSL2 с
Docker; нативный Windows-hosted SDK пока не готов. Сборка Windows-приложения
из другой ОС — отдельная возможность, см. [Windows guide](windows.md).

Установите Git и Docker с работающим Linux engine. Из папки `nex-toolchain`:

```sh
# ARM64: arm64; Intel/AMD x86-64: amd64.
export NEX_DOCKER_ARCH=arm64
mkdir -p "$HOME/projects/nex-apps"
docker build --platform "linux/$NEX_DOCKER_ARCH" \
  -f tools/linux/Dockerfile -t "nex-dev:$NEX_DOCKER_ARCH" .
docker run --rm -it --platform "linux/$NEX_DOCKER_ARCH" \
  --mount "type=bind,source=$PWD,target=/src,readonly" \
  --mount "type=volume,source=nex-build-$NEX_DOCKER_ARCH,target=/nex-build" \
  --mount "type=bind,source=$HOME/projects/nex-apps,target=/work" \
  "nex-dev:$NEX_DOCKER_ARCH"
```

Для этих ручных Docker-команд выберите пути без запятой и кавычки. Полный
проверочный runner проекта отдельно обрабатывает такие пути, см. [Linux guide](linux.md).
В открывшемся контейнере выполните:

```sh
cmake -S /src -B /nex-build/compiler -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ \
  -DLLVM_DIR=/usr/lib/llvm-22/lib/cmake/llvm \
  -DMLIR_DIR=/usr/lib/llvm-22/lib/cmake/mlir -DNEX_Z3_ROOT=/opt/z3
cmake --build /nex-build/compiler -j 4
cmake --install /nex-build/compiler --prefix /nex-build/sdk
export NEX_SDK=/nex-build/sdk
export PATH="$NEX_SDK/bin:$PATH"
nex doctor
cd /work
```

Дальнейшие команды NEX выполняются **в этом контейнере**; проекты в `/work`
сохраняются в `~/projects/nex-apps` хоста, SDK — в именованном Docker volume.
При следующем входе повторите `docker run` с теми же mounts и строки `export`.
Контейнерный SDK содержит зависимости/пути своего окружения; его нельзя просто
скопировать на произвольный Linux-компьютер как готовый переносимый установщик.
Для разработки без Docker используйте зависимости и CMake-настройки из
[Linux guide](linux.md). Проверка ARM64 не подтверждает все дистрибутивы и драйверы.

## 2. Создать и запустить проект

Выйдите из папки компилятора и выберите каталог своих приложений. На macOS,
например, `mkdir -p "$HOME/projects/nex-apps"` и `cd "$HOME/projects/nex-apps"`;
в Linux-контейнере выше это `/work`.

```sh
nex init my-app
cd my-app
nex check --json
nex eval --json
nex test --json
nex run --json
nex run --profile release --json
mkdir -p out
nex build --profile release -o out/my-app --json
./out/my-app
```

`init` создаёт `nex.json` и `src/main.nex`: сумму чисел от1 до10 и тест.
Программа печатает `55` и завершается с кодом0. `eval` выполняет эталонный
интерпретатор; `test` сравнивает тесты с нативным исполнением; `run` собирает
и запускает программу. `build` только собирает. При `--json` stdout программы
лежит в поле `stdout` ответа, а `./out/my-app` печатает его непосредственно.

Редактируйте `src/main.nex` и повторяйте `check`, `test`, `run`. Выносите код
в модули и импортируйте их относительными путями. В `nex.json` остаются язык,
точка входа и локальные корни библиотек. Для первого проекта достаточно:

```json
{"schema":"nex.project/1","language":"0.16","entry":"src/main.nex"}
```

`nex init` пока не создаёт Git-репозиторий, `.gitignore`, AGENTS.md или UI.
Выбор DLL, общий scheduler CPU/GPU/NPU и все пункты PLAN не появляются от
добавления выдуманных полей в этот файл. Проверяйте доступность через `describe`.

Часто используемые команды, из корня **своего** проекта:

| Команда | Назначение |
|---|---|
| `nex describe --json` | Реальные возможности установленного компилятора |
| `nex guide --kind language` | Спецификация языка; `prompt`, `grammar`, `web` — другие руководства |
| `nex check` | Проверка исходников, типов, эффектов и realm |
| `nex test --profile release --json` | Проверка тестов в release и сравнение с интерпретатором |
| `nex context --symbol app::sum --json` | Ограниченный контекст сохранённой функции |
| `nex history --json` / `nex changes --json` | Ревизии и журнал внутреннего графа |
| `nex debug` | Нативная отладка через установленный LLDB |
| `nex profile --scenario "first-run" --json` | Запуск с профилем функций и сохранённым отчётом |

Обычные файловые `check/eval/test/run/build` синхронизируют проверенные
исходники с внутренним графом. `analyze --json` предназначен для анализа без
такой записи. Отладке нужны LLDB и разрешение ОС запускать процесс под ним;
подробнее: [отладка](debugging.md), [профилирование](profiling.md),
[VS Code extension](editor.md). Нативный executable не требует NEX/LLM, но
его системные и используемые библиотечные зависимости остаются. Для доставки
приложения смотрите [package](packaging.md).

### Первое веб-приложение

При установленном Node22.18+ и npm, в том же новом проекте:

```sh
cp "$NEX_SDK/share/nex/examples/web/main.nex" src/web.nex
nex check src/web.nex
nex test src/web.nex --target web --json
nex build src/web.nex --target web --profile release --json
```

В JSON сборки есть `directory` с сгенерированным React/Vite-проектом и `dist`
с готовыми статическими файлами. Выполните `npm --prefix DIRECTORY run preview`,
подставив фактический `directory`, и откройте адрес из вывода Vite.
Для редактируемого dev-проекта:

```sh
nex web src/web.nex --directory build/web-dev
npm --prefix build/web-dev ci --ignore-scripts --cache "${NEX_NPM_CACHE:-$HOME/.npm}"
npm --prefix build/web-dev run dev
```

Исходником остаётся `src/web.nex`. После его изменения создавайте генерацию
в новом/пустом каталоге. Не считайте `build/web-dev` местом долговременных
ручных правок: повторная генерация их не переносит. Зависимости сборки
зафиксированы SDK в npm lock; для первого скачивания нужны сеть или заполненный
cache. Прямой `npm ci` использует `--cache` явно: переменную `NEX_NPM_CACHE`
понимает NEX, а npm сам её не читает. Это особенно важно в Docker-рецепте с
offline cache. `nex init` создаёт CLI, поэтому веб-команды указывают `src/web.nex` явно.
Клиент компилируется в TypeScript/React; общая поддержка Wasm и SSR из этого
не следует. [Веб-контракт](web.md), [сервер](server.md), [типизированный API](api.md).

## 3. Что хранить в Git

Основной вариант совместной работы: **исходники и настройки в Git**, локальный
граф `.nex` — отдельно. После чистого clone `nex check` создаст новый локальный
граф. Исходники сохранятся, а старые локальные node IDs и внутренний журнал
сами из Git не восстановятся.

| Класть в Git | Не класть в обычные исходные commits |
|---|---|
| `src/**/*.nex`, исходные тесты, свои библиотеки и нужные assets | `.nex/`: граф, кеши и локальные результаты |
| `nex.json`, `nex.lock.json`, если создан | `build/`, `out/`, `dist/`, `node_modules/`, executable/object files |
| README, AGENTS.md, требования, task/proof-контракты | Живые БД приложения, профили и большие отладочные записи |
| Версия toolchain и commit исходников компилятора | Установленный SDK, LLVM, локальные абсолютные пути |
| Согласованный пакет языка/промпт для LLM | `.env`, токены, SSH-ключи, настоящие auth-конфигурации |
| Скрипты сборки/CI, шаблоны конфигурации без секретов | Личные настройки агента и персональный `AGENTS.override.md` |

`nex lock` закрепляет содержимое достижимых библиотек, а не скачивает пакеты.
Сами библиотеки должны быть доступны после clone: например, храните их под
`vendor/` с относительными корнями в `nex.json`, лицензиями и происхождением.
Lock не заменяет их исходники или способ получения. Обновляйте pins после
проверенного изменения зависимостей. Для нескольких entry-point выполняйте
`nex lock FILE` для каждой нужной программы; старые pins сохраняются.

В новом `my-app` создайте `.gitignore`, например:

```gitignore
**/.nex/
/build/
/out/
/dist/
**/node_modules/
*.dSYM/
.DS_Store
.env
.env.*
!.env.example
/data/
/nex.toolchain.local.json
/AGENTS.override.md
```

`data/` здесь — выбранная папка рабочих данных приложения; тестовые fixtures
можно хранить в Git отдельно. Затем:

```sh
nex lock
git init
git add .gitignore nex.json nex.lock.json src
git diff --cached
git commit -m "Create NEX application"
```

Добавьте README, AGENTS.md, toolchain-version.json и документы языка, когда
создадите их в следующем разделе. Настройте remote своего приложения обычным
Git/GitHub способом. Коммит остаётся локальным, пока вы не отправили его в remote.
После каждого изменения проверяйте `nex test`, смотрите `git diff` и коммитьте
понятный набор исходников. После clone с другого компьютера сначала подключите
ту же версию SDK, затем выполните `nex check`, `nex test`, `nex run`.

### Если LLM меняет граф через `nex apply`

`apply` обновляет граф, **но не переписывает физические `.nex` файлы**. Пока
правка живёт только в графе, проверяйте `nex test --revision HEAD` и
`nex run --revision HEAD`. Обычный файловый `check` может вернуть в HEAD
старое содержимое файла. Для первого однофайлового проекта материализуйте
правку перед коммитом так:

```sh
nex test --revision HEAD --json
nex export --revision HEAD --directory ../my-app-export-001 --json
diff -u src/main.nex ../my-app-export-001/src/main.nex
# После просмотра разницы:
cp ../my-app-export-001/src/main.nex src/main.nex
nex check
nex test
git diff
git add src/main.nex
git commit -m "Apply checked NEX change"
```

Код1 у `diff` означает найденную разницу. Экспорт содержит только выбранную
достижимую программу и её исходные зависимости, а не все assets/все entry-point
вашего проекта. Для нескольких файлов перенесите нужные исходники с просмотром
разницы; отдельно согласуйте `nex.json`, корни экспортированных библиотек и lock.
Не заменяйте весь проект экспортом одной программы. Экспорт не заменяет полный
graph backup.

### Сохранить весь внутренний граф

```sh
nex snapshot --directory ../my-app-graph-001 --json
```

Скопируйте **весь** полученный каталог (`graph.db` и `snapshot.json`) в своё
резервное хранилище. Не копируйте работающий `.nex/graph.db` отдельно: часть
зафиксированных данных может находиться в SQLite WAL. Обычным SQLite-файлам
не подходит текстовый merge Git. Для командной работы по умолчанию достаточно
исходников; snapshots нужны для сохранения всей локальной истории/идентичностей.

Восстановление выполняется в новые каталоги:

```sh
nex recover ../my-app-graph-001 --directory ../my-app-recovered --json
cd ../my-app-recovered
nex history --json
nex test --revision HEAD --json
nex export --revision HEAD --directory ../my-app-recovered-source --json
```

После recovery исходники ещё не материализованы — поэтому используется
`--revision HEAD`. Snapshot не включает несохранённые в графе файлы, assets,
рабочие БД приложения, внешние библиотеки, SDK и файлы task receipts/artifacts.
Храните их отдельно и сохраняйте подходящий SDK для старых ревизий.
[Подробнее о snapshots](snapshots.md).

## 4. Hermes, Codex и другие LLM

Для работы достаточно агента, который может читать/править файлы проекта и
выполнять команды терминала. NEX не требует отдельной модели или обязательного
MCP-сервера. Учётная запись/провайдер LLM настраиваются в выбранном агенте;
ключи не записываются в NEX-исходники. Сборку и запуск приложения можно выполнять
вообще без агента.

### Один пакет языка для всех агентов

В корне нового приложения сохраните копию инструкций из **своего** SDK:

```sh
mkdir -p docs/nex
cp "$NEX_SDK/share/nex/llm/SYSTEM_PROMPT.md" docs/nex/SYSTEM_PROMPT.md
cp "$NEX_SDK/share/nex/llm/WORKFLOW.md" docs/nex/WORKFLOW.md
cp "$NEX_SDK/share/nex/docs/language.md" docs/nex/language.md
cp "$NEX_SDK/share/nex/docs/grammar.ebnf" docs/nex/grammar.ebnf
nex describe --json > docs/nex/capabilities.json
nex doctor | python3 -c 'import json,sys; d=json.load(sys.stdin); print(json.dumps({k:d[k] for k in ("version","language","llvm")},indent=2))' > toolchain-version.json
```

В toolchain-version.json дополнительно запишите фактический source commit SHA
или идентификатор/контрольную сумму полученного SDK. Не выдавайте произвольную
строку версии за точную фиксацию бинарника. Файлы `docs/nex` — документация
выбранной версии; агент всё равно запрашивает живой `nex describe`.

Создайте в корне приложения `AGENTS.md` с таким содержимым:

```markdown
# Работа над этим приложением NEX

Прочитай README.md и docs/nex/SYSTEM_PROMPT.md.
Выполни nex doctor и nex describe --json в своём терминале.
Используй поддерживаемые установленным компилятором возможности.
Документация языка: docs/nex/language.md и docs/nex/grammar.ebnf;
актуальные руководства доступны через nex guide --kind KIND.

Редактируй исходники src/*.nex; сохраняй типы, эффекты, realm и проверки.
Для существующего кода запрашивай nex context --symbol NAME --json.
После правок выполни nex check, nex test и nex run --json.
Для src/web.nex также выполни nex test src/web.nex --target web --json
и nex build src/web.nex --target web --profile release --json.
Не ослабляй согласованные тесты ради прохождения проверки.

Если используешь nex apply, проверяй --revision HEAD, затем материализуй
изменённые исходники через экспорт и просмотр разницы до Git-коммита.
Не теряй файлы/библиотеки/точки входа вне экспортированной программы.
Не коммить .nex, сборки, SDK, данные приложения или секреты.
В конце сообщи изменённое поведение, реальные проверки и ограничения.
```

Это шаблон для **приложения**. AGENTS.md из репозитория самого NEX содержит
инструкции для C++ компилятора; копировать его в своё приложение не нужно.
Удалите веб-пункт шаблона для CLI-only проекта или добавьте свои entry-point.
Закоммитьте AGENTS.md, документы языка и сведения о toolchain вместе с исходниками.

### Codex

Установите/откройте Codex по [официальной инструкции](https://learn.chatgpt.com/docs/codex/cli).
Для CLI: перейдите в `my-app` и выполните `codex`, затем войдите в свою учётную
запись. В приложении выберите папку `my-app` как проект. Codex читает проектный
[AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md).
Проверьте, что его терминал видит `nex doctor`; при необходимости укажите
абсолютный путь к `bin/nex` и matching SDK. Для контейнерного SDK команды должны
исполняться в соответствующем контейнере с доступом к проекту.

### Hermes Agent

Установите Hermes по [официальной инструкции](https://hermes-agent.nousresearch.com/docs/getting-started/installation),
настройте провайдера, перейдите в `my-app` и выполните `hermes`. Для Desktop
выберите ту же рабочую папку и проверьте в агенте `nex doctor`. В стандартном
локальном CLI рабочая папка определяется местом запуска. У Docker/SSH backend
свой PATH, SDK и файловая система — доступность NEX на хосте не устанавливает
его внутрь backend.

Hermes поддерживает [AGENTS.md](https://hermes-agent.nousresearch.com/docs/user-guide/features/context-files).
У `.hermes.md` и `AGENTS.override.md` более высокий приоритет; если такой файл
уже есть, добавьте туда ссылку на общие NEX-инструкции. Не рассчитывайте, что
все альтернативные файлы автоматически объединятся.

### Как поставить первое задание

Передайте агенту, например:

> Прочитай AGENTS.md. В src/main.nex добавь функцию factorial(n:i64)->result<i64>
> для n от0 до20: factorial(0)=1. Для остальных n верни диагностируемую ошибку
> через result<i64>. Сохрани проверяемое переполнение. Добавь тесты для0,1,5,20,
> отрицательного n и21. Вызови функцию из main. Проверь интерпретатор и
> нативные debug/release тесты. Покажи команды, результаты и Git diff.

Для UI указывайте целевую платформу, поведение, хранение данных и критерии
приёмки; агент сверяет их с `describe` и подходящим guide. В чате без терминала
команды выполняете вы или runner, а модели передаёте результаты. Промпт и
пакет языка одинаковы для разных LLM; качество конкретной модели требует
проверки. Ошибка компилятора или непрошедший тест — повод исправить программу,
а не объявлять задачу завершённой.

## 5. Если что-то не запускается

| Симптом | Следующий шаг |
|---|---|
| `nex: command not found` | Проверить путь `NEX_SDK/bin` именно в используемом терминале/агенте |
| Не найдены LLVM/MLIR/Z3 или shared libraries | Подключить зависимости сборки SDK либо matching portable bundle; один `bin/nex` недостаточен |
| Не найдены native compiler/Apple SDK | Проверить `nex doctor`, Command Line Tools или Linux compiler/sysroot |
| `E_LANGUAGE_VERSION` | Выбрать matching SDK или пройти явную [миграцию](compatibility.md); не менять номер языка вслепую |
| `E_EXISTS` при export/snapshot/recover | Выбрать новый выходной каталог; не удалять прежнюю историю ради повторения команды |
| После `apply` Git не показывает правку | Правка пока в графе: проверить `--revision HEAD` и материализовать исходники |
| Веб-сборка не скачивает npm dependencies | Проверить Node/npm, сеть или выбранный offline cache; сохранить lock SDK |
| GPU/NPU не работает | Проверить конкретный драйвер/runtime и адаптер; CPU-совместимость сама по себе не даёт поддержку ускорителя |

Проверки этой инструкции охватывают новый проект из установленного SDK,
интерпретатор/нативные тесты и сборки, web generation/build, Git clone и graph
snapshot/recovery. Скачивание/чистая установка всех сторонних пакетов на новом
компьютере и реальное программирование разными LLM — отдельные проверки.
