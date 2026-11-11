# NEX: передача разработки в DeepSeek

Дата: 11 ноября 2026. Codex поставлен пользователем на паузу.
Этот документ фиксирует текущие исходники и результаты, а не готовность релиза.

## 1. Задача следующему агенту

Продолжи разработку **NEX — Neural Execution Language** и исходный объём `PLAN.md`.
Идея: передавать максимум точного смысла минимальным необходимым количеством
токенов, сохраняя производительность, строгую семантику и безопасность исполнения.
Приложения работают без LLM. Цель пользователя — полноценный язык и инструменты
для больших серверных, веб-, настольных и мобильных систем, CPU/GPU/NPU.

Сначала прочитай этот handoff и фактический код. Сохрани уже сделанные изменения,
затем продолжай незавершённые языковые возможности. Не объявляй весь проект
завершённым по результатам отдельных тестов или старого SDK.

**Важные действующие указания пользователя:**

- Дополнительная работа по кибербезопасности, ASan/UBSan/LSan/TSan и fuzz отложена.
  Не запускать и не восстанавливать её CI без нового явного указания пользователя.
  Список и архив: `docs/deferred-checks.ru.md`.
- Продолжать обычную функциональную разработку. Делать законченные блоки,
  одну сборку и короткие затронутые проверки; полные регрессии/SDK/стенды —
  на согласованном финальном этапе, с учётом отложенных проверок.
- Использовать актуальный код. Не тратить время на повторную квалификацию старых SDK.
- Для будущих сравнительных LLM-замеров выбрана только локальная
  **Qwen3.8 27B Q8_0**, без платных API, дополнительных моделей и скачивания весов.
  Пользователь отдельно передаёт саму разработку в DeepSeek.
- Сохранять прежние результаты и отказы. Повторять проверки, когда изменился
  затронутый код, появился отказ или остался конкретный нерешённый вопрос.
- В конце всей работы пользователь разрешил актуальный `main`/push и уборку
  старых веток/build. Сейчас финальные требования и SDK ещё не выполнены.

## 2. Где находится актуальный проект

**Работать здесь:**

```text
/Users/sae/.codex/worktrees/runtime-loop-contracts/NEX
ветка: codex/windows-observation-capture-root
origin: https://github.com/sae-ru/NEX.git
HEAD: 991849da3c6996dfc495015b0d67043f15e7d99c
```

HEAD содержит завершённый блок **0.169**. Поверх него лежит большой
**незакоммиченный, собранный и функционально проверенный блок 0.170**.
Только `git clone`/GitHub не заменяет текущее рабочее дерево!

Другие копии нужно сохранить:

| Путь | Состояние/назначение |
| --- | --- |
| `/Users/sae/projects/NEX` | Защищённая основная копия, HEAD `b2595149aacc25c0729773dd0dcd25509390021d`; её исходники и пользовательский граф не менялись в текущем блоке. |
| `/Users/sae/.codex/worktrees/checked-rename-next/NEX` | Другая чистая копия, HEAD `78acb4395573f003807b48e1bb5694bf9630f347`; это не актуальное рабочее дерево. |

`build` в активном дереве — symlink на
`/Users/sae/projects/NEX/build/ctest-fixture-verifier-162`.
Сборка из активного дерева использует его. Не подменяй основной
`/Users/sae/projects/NEX/build/nex`: это другой сохранённый бинарник.
В основном пользовательском графе сохранены 48 ревизий, включая исходные
47 ревизий и локальные ID. Не удаляй и не пересоздавай этот граф.

Старый рабочий checkpoint:
`/Users/sae/projects/NEX/build/windows-platform-discovery162-v1/stands-returned-current028-v1/checkpoint124.json`.
Он заканчивается на **закоммиченном 0.169**; незакоммиченный 0.170 описан здесь.
Его старые указания «реализовать list builder» уже устарели.

## 3. Архив для переноса на другой компьютер

```text
/Users/sae/projects/NEX/build/handoff-deepseek-0170-20261111/NEX-0.170-working-source.tar.gz
```

SHA256:

```text
19398bfa5d7f931f92cfdecddef75ca6d182980c40557f12396bef55868a4742
```

Архив: **7 784 002 байта**, 2356 исходных файлов, включая незакоммиченные
изменения; исходные файлы занимают 31 224 596 байт. Прочитан обратно,
SHA256 каждого исходного файла сверен. Внутри каталог `NEX/`, а также:

- `HANDOFF-SOURCE-MANIFEST.json`: базовый коммит, ветка, размеры и SHA256 файлов.
- `HANDOFF-EVIDENCE/`: выбранные сырые отчёты последнего блока и профиля.

Это исходники, не переносимый SDK. `.git`, build-кэши, модели и пользовательский
граф не включены. История локальных коммитов в архив не входит. Распаковывай в
новый каталог; исходное рабочее дерево с его `.git` остаётся на Mac.
Сам этот Markdown передаётся отдельно от архива.

## 4. Точные версии текущего кода

| Компонент | Значение |
| --- | --- |
| Toolchain | **0.170.0**, development |
| Язык | **0.28**, не повышался |
| Формат checked program | `nex.program/16` |
| Task ABI | 7 |
| C ABI major | 1 |
| Стек | C++20, CMake, LLVM/MLIR 22.1, SQLite, OpenSSL 3, Z3 |

Последний проверенный бинарник активного дерева: `build/nex`.

```text
SHA256: 4c70deb596ce800b62d83ed62fb7cb12a17fa06d1a6d5524fd362fa89de40edb
compiler_build: 5a909907e6f16bb21c5e104fa6650c5b40cdd4560ccdbc19cd420d43a0b7b396
descriptor_hash: e04fe4672dc4ec72c68b1368f4ca87b65f7ef4b6cf8800a698b7728674caa496
```

Начальные документы: `README.md`, `AGENTS.md`, `docs/language.md`,
`docs/grammar.ebnf`, `llm/SYSTEM_PROMPT.md`, `PLAN.md`,
`docs/development-priorities.md`. Верхняя версия в заголовке `PLAN.md` устарела:
текущую версию определяют CMake и реальный compiler descriptor.

```sh
./build/nex describe --kind index --json
./build/nex describe --field list_construction --json
./build/nex guide --kind list-build --json
```

## 5. Что уже было завершено до 0.170

- **0.166:** bounded language entry, `nex explain CODE`, compiled-каталог
  103 диагностик, quick guide до 6144 байт и проверенные примеры.
- **0.167:** source text/list/math helpers: Unicode split/replace/trim,
  стабильная сортировка, checked integer math, компилируемые pins библиотек.
  Старые ограничения копирования остаются в историческом отчёте этой версии.
- **0.168:** `nex fmt FILE`, preview/`--check`/`--write`, комментарии и литералы,
  parser-owned разметка типов/операторов, идемпотентность, отсутствие записи в граф.
- **0.169:** общий compiled CLI-каталог для парсера параметров, отдельной справки,
  completion и `--quiet`. Bash 3.2/5.3 и zsh проверены исполнением;
  fish/PowerShell-адаптеры сгенерированы, их исполнение пока не проверено.

Локальные коммиты:

```text
54292db — formatter и документирование отложенных проверок
3b7f403 — evidence formatter
dc834d8 — compiled help/completion/quiet
991849d — evidence CLI
```

Их подробные ограничения — в `docs/evidence/`, `docs/formatting.md`, `docs/cli.md`.

## 6. Что именно сделано в незакоммиченном 0.170

### Языковая операция list

```nex
list(count, make)
list(values, transform)
list(values, predicate, transform)
list(count, initial, next, emit)
```

Аргументы вычисляются один раз слева направо. Обход последовательный.
Предикат вызывается один раз для каждого входа, transform — для выбранных.
Stateful-форма: emit вызывается count раз, next — max(0,count-1), без лишнего
перехода после последнего элемента. Отрицательный count даёт `E_ASSERT`.

Эффекты callbacks выводятся объединением и проверяются обычными правилами
caller/realm/грантов. Поддержаны IO, source errors и Task-приостановки.
`Result ?` выходит только из текущего callback: err остаётся элементом результата.
Входы/алиасы не меняются. Новых неявных workers, authority или parallel-лимитов нет.

Имя `list` уже было зарезервировано: конфликта с прежними допустимыми именами
нет. Язык остаётся 0.28; в более ранних retained source versions операция
отклоняется. Старые compiler builds с языком 0.28 могут её не поддерживать:
проверяй capability. CUDA/Metal/Wasm lowering этого конструктора пока отсутствует.

### Реализация и важные инварианты

- `src/list_build.cpp`, `include/nex/list_build.h`: разворачивание в обычную
  проверенную lambda с циклом. Существующие механизмы Invoke, exceptions и tasks
  выполняют этот код во всех трёх движках.
- `Function::compilerListBuilder` в `include/nex/language.h`: только для
  compiler-generated helper. Source не может выставить этот признак.
- `$list_start`, `$list_append`, `$list_finish` доступны только такому helper;
  исходный язык не может записать эти имена. Буфер не передаётся callback.
- `src/language.cpp`: типизация/inference, эффекты, lowering. Отрицательные
  номера generated lambdas исключают коллизию с source lambdas.
- **Гигиена:** внутренние len/assert связываются с builtin, а не с одноимёнными
  locals вызывающего кода. Пользовательские callbacks сохраняют свой lexical scope.
- `src/interpreter.cpp`, `src/backend.cpp`, `src/typescript.cpp`: private primitives.
  Native использует имеющиеся list allocation/append вызовы, без нового runtime ABI.
- `web/nex-runtime.ts`: незавершённый массив закрыт внутри helper, при публикации
  замораживается без полного копирования. Public push/set остаются immutable.
- `src/task_lifetime.cpp`: отслеживает перенос происхождения элементов в private
  buffer. Не отключать статические/обязательные runtime owner checks.

### Стандартная библиотека

`lib/list.nex`: добавлен `generate`; map/filter/reverse теперь линейные, merge
сортировки использует stateful-конструктор и immutable cursor. Сортировка стабильна.
Итого text7/list10/math10 — **27 публичных функций** в этом индексе.

Native/reference: amortized O(n) для построения, O(n log(n+1)) для sort;
стоимость callbacks/состояний/значений дополнительна. TypeScript убирает повторные
копии растущего префикса; устройство JS-массива зависит от движка.
Named std/list wrappers пока принимают pure callbacks; inferred effects доступны
на прямом конструкторе. Generic effect-параметры именованных функций ещё pending.

Компилируемый descriptor, manifest, grammar/spec, quick guide, документация
и примеры обновлены. `examples/stdlib/nex.lock.json` обновлён **явной командой
lock в отдельном private project**; пользовательские locks/графы не менялись.

Примеры `examples/list-construction/` содержат точный source/expected output
проверенных value/effect/task сценариев. Новый quick guide — 5512 байт.

## 7. Фактически выполненные проверки 0.170

Все пути ниже относительно:

```text
/Users/sae/projects/NEX/build/windows-platform-discovery162-v1/stands-returned-current028-v1/stands-return-20261109-v1/
```

| Набор | Результат |
| --- | --- |
| `list-construction-v4/report.json` | Последняя сборка всех целей `-j 4` прошла; затем 8 constructor methods за 58.020 с, 6 stdlib methods за 44.066 с, 12 core за 22.84 с, shared manifest/descriptor validation — успешно. |
| `list-construction-extra-v1/report.json` | Ещё 2 метода за 45.076 с на **том же финальном бинарнике**: Result callback boundaries и Task-budget retirement. |
| `list-construction-v4/allocation-comparison/report.json` | Один текущий compiler, n=4096, одинаковый результат: managed objects 8195→7, handles 36869→20494; live=0 и allocations=frees в обоих случаях. |

Покрыты reference, native Debug/Release, strict TypeScript 7.0.2 и фактическое
исполнение TS. Включены nested values, generic refs, callable captures,
immutable aliases, IO-порядок, typed throw/finally, suspending callbacks,
genuine Task/Future lists, 65537 элементов, отвергнутые типы/эффекты/lifetimes,
гигиена, сохранение старой graph revision и local IDs.
Native профили подтвердили освобождение partial construction на fatal и
Task-budget выходах; user finally при fatal/budget не выполняется.

Это **не** полный regression/SDK/platform gate и не замер total RAM/RSS или
ускорения в 1000 раз. Профили считают managed/shallow objects, а не все backing
vector bytes. Алгоритм-baseline профилирован текущим compiler, без старого SDK.

Реестр: 326 Mac CTest groups, 331 запись с conditional platforms, core=12.
Для дополнительных 2 тестов не повторялись уже пройденные 8: отчёты раздельные.

**Сохранённые отказы и пояснения:**

- v1: первые тесты ошибочно предполагали отсутствие `throw` у caller с typed
  catch и запуск Task generator обычным `entry()`. Исправлены тесты, правила
  языка не ослаблялись. Правильный driver:
  `await task.runTypedSourceErrors(task.call(()=>entry()),sourceErrorContracts)`.
- v2: 6 методов прошли; compatibility fixture не имела поля user_version.
  Реальная версия SQLite schema — 0; metadata исправлена. Отказ не переписан.
- v3: compatibility/stdlib/core прошли на предыдущем 0.170 candidate.
- `list-construction-hygiene-control-v1/`: настоящий lexical-shadow bug
  воспроизведён (`wrong` вместо `hygiene-ok`), сохранены source, JSON и точный
  `checker-before-fix.cpp`. Исправление вошло в финальный v4.
- В v4 report поле `same_compiler_sha256` унаследовало **pre-build** значение.
  Для финального бинарника используй `compiler_sha256`; пояснение сохранено
  отдельно в `report-annotation.json`, оригинальный отчёт не переписывался.

## 8. Незавершённая фиксация этого блока

0.170 **ещё не закоммичен и не отправлен в GitHub**. Завершены исходники,
примеры, локальная сборка и перечисленные проверки. Не создан итоговый публичный
`docs/evidence/...0.170...json`, не обновлён основной progress checkpoint после 124.
Текущий результат сохранён рабочими файлами, отчётами и handoff-архивом.

Первый шаг продолжения: сверить `git status`, сохранить именно этот блок
локальным коммитом и оформить scoped evidence с точными хешами, версиями,
раздельными cohort-результатами и ограничениями. Не объявлять старые SDK или
старые model trials проверкой 0.170. Успешные неизменённые тесты повторять не нужно.

## 9. Что ещё необходимо реализовать

Полный исходный scope — в `PLAN.md`; старые исторические checkbox не заменяют
проверку текущего descriptor/кода. Основные оставшиеся направления:

1. **Язык/stdlib:** линейное построение текста, более широкие контейнеры,
   generic effect-параметры именованных функций, оставшийся advanced
   type-constructor inference/effect handling. Следующий содержательный блок
   разумно выбрать здесь, а не снова расширять вспомогательные проверки.
2. **GPU/NPU:** общее покрытие компиляции/типов, дальнейший Metal, GPU operation
   debugging/profiling, Apple NPU; constructor lowering для CUDA/Metal/Wasm.
   Готовые scalar/bounded CUDA/Metal и provider-контракты не универсальны.
3. **Web:** компоненты/стили, async UI boundaries, browser debug/profile и
   оставшиеся части `docs/web.md`. В клиент выдавать только reachable client/shared.
4. **Native UI/mobile:** Android/iOS toolchains, lifecycle/permissions/signing,
   packages, device launch/debugging, graphics adapter и архитектуры платформ.
5. **Studio/AI/porting:** NEX Studio, task-to-change слой, конвертер C++/Python
   по `docs/project-porting-design.md`; не создавать большие редакторы/игры
   вместо самого языка/toolchain.
6. **Graph/debug:** identity-preserving edits и оставшаяся полная атрибуция
   source/optimized machine/core/profile.
7. **Developer tools:** formatter editor/directory/width integration;
   исполнение fish/PowerShell completion; CMake hygiene, docs indexing/drift,
   общий backend-agreement corpus/generator, release benchmarks/`nex bench`.
8. **Доставка:** hosted CI, один последний согласованный source→SDK цикл,
   installed/moved/restored SDK и актуальная платформа/CPU/GPU/NPU матрица.
   Только затем актуальный main/push/release и аккуратная уборка старого build/веток.

Дополнительные sanitizer/fuzz/security работы остаются **отложенными**,
не включай их в автоматический очередной прогон старого full-плана.

## 10. Результат LLM-эксперимента нельзя потерять

Замер локальной Qwen3.8 27B Q8_0 закончен: 60 попыток, 479 запросов,
1 288 404 фактически учтённых токена. Принято NEX **4/20**, C++ **14/20**,
Python **20/20**. Экономия токенов NEX не получилась. Cache split/денежная
стоимость неизвестны; выводов про другие модели нет.

Документы: `docs/llm-cost-qwen38-27b-2026-11-11.en.md` и `.ru.md`.
Полный sealed набор локально: `LLM-Qwen-cost-study-v1/` под корнем результатов
из раздела 7. Старый compiler/source и отказы пилотов сохранены. Сборщик
завершён, активных model jobs нет. Не перезапускать и не переписывать это
исследование ради новой документации/версии. Будущий замер — новый versioned
protocol и отдельный каталог, только с выбранной локальной моделью.

## 11. Как продолжать на этом Mac

```sh
cd /Users/sae/.codex/worktrees/runtime-loop-contracts/NEX
git status --short
./build/nex describe --kind index --json
```

Обязательные инварианты: checked arithmetic, left-to-right once, short-circuit,
effects/realms, strict UTF-8 и Unicode scalar strings, immutable aggregates,
owned cleanup на всех native exits, исходные graph revisions/local IDs.
Изменения языка согласовывать в checker/reference/MLIR/TypeScript/spec/grammar/
descriptor/manifest/examples. При настоящем language-version change нужна
явная history-preserving migration.

Доступные инструменты:

```text
CMake: /opt/local/bin/cmake
CTest: /opt/local/bin/ctest
LLVM: /opt/homebrew/Cellar/llvm@22/22.1.8
Python: /Users/sae/.hermes/tools/python-3.14.9+20261021-darwin-arm64/bin/python3.14
Node: /Users/sae/.local/bin/node
```

После следующего содержательного блока:

```sh
/opt/local/bin/cmake --build build -j 4
# Затем конкретный затронутый functional group, с нужными Node/TS зависимостями.
# Для малого compiler-loop:
/opt/local/bin/ctest --test-dir build -L '^core$' --output-on-failure
```

Для TS нужна закреплённая версия из `web/package.json`/lock (**7.0.2**).
Локальный уже установленный tsc использовался здесь:

```text
/Users/sae/projects/NEX/build/runtime-contracts-152/full-v1/failures/__main__.Tasks.test_api_server_web_application_and_native_library_deliverables-nex_test_1q55nrfe/.nex/build/13c51b70b01e2dd44fa69595db19e86670e4178a2f3ce2421d5f5ddb3da8747a/web/node_modules/typescript/bin/tsc
```

Его задавали через `NEX_TSC`, Node через `NEX_NODE`. Успешные проверки этого
блока уже выполнены; путь не является указанием повторить весь набор.
На Mac тяжёлые процессы запускались только с открытой крышкой и AC-питанием,
через `power_capture.py`/`power_watch.py` в локальном каталоге результатов.
Все созданные для текущего блока процессы завершены; старые tool-session ID
не являются живыми jobs и не должны перезапускаться из старых checkpoint.

## 12. Стенды и финальные условия

Ранее использовались Astra/Debian `.78`, CIX `.88`, RK3588 `.200`, Windows
`.99` (`F:\sae\NEX`, пользователь sae), Fedora `.55` в сети 192.168.1.x.
Последний блок 0.170 на них не передавался и не исполнялся. Их прежние отчёты
сохраняют собственные версии/хеши; не приписывай им новую квалификацию.
У Windows ранее возникала нерешённая сверка изменившегося SSH host key;
это нужно разрешить перед передачей исходников при возобновлении стендов.
IPv6 на Windows пользователь ограничил намеренно.

MIT уже выбрана пользователем. Материалы языка на русском/английском и
LLM-пакет должны остаться в проекте. После настоящего завершения потребуется
проверить все требования по фактическому коду/артефактам, оформить последнюю
согласованную SDK/platform приёмку и выполнить разрешённую публикацию main.
Сейчас исходный общий проект **не завершён и не квалифицирован для финального релиза**.
