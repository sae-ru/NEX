# Как дать NEX другой LLM

В toolchain0.87 начните с `llm/BOOTSTRAP.md` и
`nex describe --kind index --json`. Получайте нужный раздел через
`nex describe --field PATH --json`, сохраняя compiler_build/descriptor_hash.
Для старого SDK остаётся полное `nex describe --json`. Это сокращает выдачу
discovery; весь авторитетный workflow и нужные разделы спецификации обязательны.
Полную стоимость задачи измеряем по [критериям качества](../docs/quality.md).

Пакет языка — обычные текстовые файлы и команды CLI. Подойдут модель в чате, агент с терминалом и локальная модель. Способ подключения модели не меняет правила языка или проверки компилятора.

## Что передать модели

1. `llm/SYSTEM_PROMPT.md`: порядок работы, основные конструкции, ограничения и правила правок.
2. `docs/language.md` и `docs/grammar.ebnf`: точную семантику и грамматику поддерживаемой версии.
3. Задание по `llm/TASK_TEMPLATE.md` и подходящий пример из `examples/`.
4. Для существующего проекта — вывод `nex describe --json` и `nex context --symbol NAME` для затронутых функций. Дополнительные зависимости запрашиваются по необходимости.

Если у модели есть терминал, она получает документы установленной версии сама:

```sh
nex describe --json
nex guide --kind prompt --json
nex guide --kind language --json
nex guide --kind grammar --json
```

Для браузерной задачи нужен `nex guide --kind web --json`, для серверной — `nex guide --kind server --json`. Для генерации типизированного API нужен также `nex guide --kind api --json`. Ответы guide содержат версию, текст и хеш документа. `llm/language-pack.json` индексирует пакет, `llm/patch.schema.json` описывает формат правки. Файл плана не служит перечнем доступных конструкций.

Если модель работает только в чате, человек или внешний runner выполняет эти команды и передаёт результаты модели. Она возвращает исходник или JSON-правку; тот же компилятор проверяет результат. Обучение новой модели и отдельный язык для каждого провайдера не требуются. Качество конкретных моделей нужно измерять на задачах.

## Пример: исправить существующую функцию

В отдельной пустой папке создайте `main.nex`:

```nex
module lesson;

fn square(x: i64) -> i64 {
  return x + x;
}

fn main() -> unit !{io} {
  print(square(12));
}

test fn square_test() -> unit {
  assert(square(12) == 144);
  assert(square(-3) == 9);
  assert(square(0) == 0);
}
```

Задание модели: «Исправь `lesson::square`: функция должна возвращать квадрат аргумента. Сохрани сигнатуру и проверяемое переполнение i64; существующие тесты не ослабляй. Верни JSON-правку и результаты проверок».

```sh
nex check main.nex --json
nex test main.nex --json
nex context --symbol lesson::square --json
```

Первый `check` должен пройти, исходный тест — завершиться ошибкой. Передайте модели диагностику и контекст. Корректная правка имеет следующую форму; вместо маркера модель подставляет **точную** ревизию из context:

```json
{
  "expected_revision": "REVISION_FROM_CONTEXT",
  "replacements": [
    {
      "name": "lesson::square",
      "source": "fn square(x: i64) -> i64 { return x * x; }"
    }
  ]
}
```

Сохраните ответ в `patch.json`, затем выполните:

```sh
nex apply --patch patch.json --json
nex test --revision HEAD --json
nex test --revision HEAD --target web --json
nex build --revision HEAD --profile release --json
nex run --revision HEAD --json
nex export --revision HEAD --directory ../lesson-fixed --json
```

Ожидаемый stdout исправленной программы — `144` и перевод строки. Обычный `test` сравнивает интерпретатор и нативное исполнение; `--target web` сравнивает интерпретатор и TypeScript. Это проверка семантики функции, не сборка UI: для приложения нужны контракты из web/server guide.

`apply` обновляет граф и сохраняет историю, но не переписывает рабочие `.nex` файлы. После правки используйте `--revision HEAD`, пока не экспортируете новый проект. Каталог экспорта должен быть новым или пустым. Вызов с прежним исходным файлом повторно загрузит его содержимое и может вернуть старую версию функции в HEAD. На `E_CONFLICT` запросите свежий контекст и пересоберите правку.

Замена существующих функций, endpoint-деклараций и исходных struct/enum может быть атомарной сразу в нескольких модулях. Для типов сначала проверьте `type` в `patch_entities` установленного компилятора. Заменяйте тип вместе с затронутыми конструкторами, сигнатурами и исчерпывающими match; generic-экземпляры пересоздаются из исходного шаблона. Необязательный `kind` (`type`, `function`, `endpoint`) должен совпадать с выбранным объявлением. Пример: `examples/type-patches`. Добавление определений и изменение импортов выполняются через экспорт и редактирование исходников с последующим `check`; таких операций в JSON replacements нет.

## Как оценивать пригодность пакета

Для каждой модели фиксируйте её имя/версию, задание, пакет языка и его хеши, предоставленный контекст, команды/диагностику, итоговую программу, число попыток и полный расход токенов. Приёмка определяется проверками поведения. Наличие промпта само по себе не доказывает успешность всех моделей или экономию токенов.

## Проверяемый контракт задания

Для задания с уже согласованными критериями используйте `nex guide --kind task --json`
и `llm/task.schema.json`. `nex task main.nex --kind init -o task.json` создаёт
заготовку из существующих тестов и точки сборки; её цель и требования нужно
заменить на реальные. В `examples/tasks` есть готовый контракт из семи проверок.

1. Выполните `nex task task.json --kind check --json` и сохраните `task_hash`.
2. Изменяйте реализацию, сохраняя согласованные тесты и формальные свойства.
3. Для правки графа выполните `nex task task.json --kind run --revision HEAD --task-hash HASH --json`.
4. Откройте сохранённый `receipt.json`, логи и артефакты. Успех требует всех
   обязательных проверок; неизвестно/тайм-аут/неподдерживаемая цель не являются успехом.
5. Для повторной проверки используйте `nex task /absolute/run/receipt.json --kind replay --json`.

Контракт может описывать несколько входных программ клиента/сервера. Их архивные
ревизии передаются через `--candidates FILE`. Исходный task-файл и HEAD при этом
не изменяются. Статическая связь требования с графом не доказывает полноту
тестов или человеческой формулировки. Снимки не замораживают всю ОС, внешние
инструменты и окружение; границы повторения описаны в руководстве.

For checked source references, query describe.editor_analysis and use its advertised references_command/schema. Keep analysis/1 consumers on the default command. Treat the new occurrence locations as bounded captured-source metadata and continue normal check/test/task acceptance after any edit.

For source-reference navigation, keep the exact declaration file/byte interval from the checked occurrence. Do not conflate a trait method with its implementation function, an enum qualifier with its variant, an import alias with its imported symbol, or equally spelled parameters in different generic scopes. Default analysis/1 remains available; these source projections add no graph identity or source-edit authority.

Для точных подсказок идентификаторов используйте `editor_analysis.identifiers_command`
и схему analysis/3, если их сообщает установленный компилятор. `--details` нельзя
совмещать с `--references`; старые форматы остаются отдельными командами.
`detail:null` означает слово синтаксиса без семантической подсказки,
`definition:null` — отсутствие физического определения. Нельзя заменять их
описанием окружающего выражения. Сигнатура обобщённой функции описывает исходный
шаблон, а тип чтения значения может быть конкретным. Лимиты и сохранность
версии контекста обязательны; эти сведения не выполняют переименование и не
дают права записи графа.

Для нативных компонентов читайте project guide: source компилирует исходники,
static подключает проверенный архив. Храните exports и зависимости в
nex.build.json. План явно перечисляет consumer_instantiations для generics;
отсутствующий обычный экспорт должен быть исправлен в контракте библиотеки.
