# Промпт для продолжения NEX в Codex на Windows

Скопируйте блок ниже в новый чат, открытый в локальном репозитории NEX на Windows.

---

Продолжи разработку и нативную проверку NEX на этой Windows-машине.

NEX — Neural Execution Language (язык нейронного исполнения). Главная идея:
передавать максимум точного смысла небольшим числом необходимых токенов,
сохраняя высокую производительность и безопасное исполнение. Семантический граф,
ограниченный контекст, точечные патчи и проверяемые контракты помогают разработке.
Универсальное превосходство над C++/Python и экономия токенов между разными LLM
ещё требуют измерений. Скомпилированной программе LLM не нужна.

GitHub: sae-ru/NEX, public, MIT. Пользователь разрешил commit/push результатов.
Сохраняй локальные изменения; работай в ветке codex/. Прочитай AGENTS.md,
README.md, docs/windows-host.md, docs/windows-handoff-current.md,
llm/SYSTEM_PROMPT.md и описание фактически выбранного SDK в docs/releases/.
PLAN.md содержит также будущие возможности. Для изменения языка прочитай
normative docs/language.md и docs/grammar.ebnf.

Целевая версия: toolchain 0.159.0, обычный язык 0.28, task ABI 7.
Принятый Mac SDK собран из 3165aaf56866b0c3f341b63571e808cfb061aa3a;
точные хеши исходников, компилятора и архива — docs/releases/0.159.0.json.
Последующая публикация main меняет документацию и квитанции. Выбери актуальный
origin/main либо явно нужный снимок после git status/fetch/log, сохранив правки.
Фактические версии и возможности получи через nex doctor --json,
nex describe --kind index --json и nex describe --field FIELD --json.
Полную приёмку Mac проверяй по квитанции релиза; сама версия исходника её не доказывает.

Ранее принятая Windows-проверка относится к0.152.1/language0.27:
274 группы CTest,35 аппаратных CUDA-случаев RTX3090, SDK31 и Compute Sanitizer.
В ней48 внутренних platform-only skips; не считай их исполненными.
Сохрани эту квитанцию. Для0.159/0.28 нужна новая Windows-матрица.
Mac0.159 отдельно прошёл150 браузерных проверок и21 OpenCL native/reference
сценарий на Apple M5 Max плюс6 профилей памяти,47 событий ядер.
Это аппаратная проверка Mac, а новая Windows/CUDA-приёмка остаётся задачей.

Порядок работы:

1. Проверь закреплённые LLVM/MLIR22.1.x, Z3, SQLite/OpenSSL, Python3.10+,
   Node/npm, CMake/Ninja и tools/windows/host-dependencies.lock.json.
   Host CLANG64/UCRT и target LLVM-MinGW имеют разные C++ ABI.
   Запусти tools/windows/configure-host.ps1, затем:
   cmake --build build/windows-host -j4
   ctest --test-dir build/windows-host --output-on-failure
   Сохрани registry, JUnit, команды, stdout/stderr, compiler/resource hashes.
   Число текущих групп и допустимые platform-only skips возьми из реального registry.

2. Подготовь текущие платформенные инструменты к выбранному языку.
   Windows/CUDA/Linux-подготовка выбирает явно поддержанные0.27/0.28 по
   согласованным doctor/describe, compiler_build и descriptor_hash. Смешанные
   идентичности и неизвестные версии отклоняются. Resume сохраняет исходные
   манифесты/графы; при другой версии нужен новый каталог проверок.
   CUDA prepare.py --source-only позволяет проверить исходники и FFI-подписи
   на другом хосте без CUDA headers; этот режим не собирает Windows DLL и не
   проверяет GPU. Выполни полную подготовку и аппаратные прогоны на Windows.
   Исторический tools/windows/summarize_host.py выдаёт квитанцию0.152.1/0.27:
   сохрани её происхождение; для новой сборки нужен отчёт с фактическими версиями,
   хешами и полными gate-результатами. Этот исторический summarizer не является
   новой квитанцией Windows0.28.
   Изменение строки версии в старом отчёте или графе не является новой проверкой.

3. Проверь согласованную работу типов, эффектов, checked arithmetic, Unicode,
   immutable aggregates, source errors, finally и structured tasks.
   Language0.28 добавляет requires/ensures и invariant/decreases; ложная проверка
   даёт fatal E_ASSERT даже в release. Отмена, дедлайн и source error пропускают
   postconditions; runtime-owned cleanup остаётся обязательной.
   Проверь runtime_contracts.py, runtime_loop_contracts.py,
   runtime_value_contracts.py, runtime_generic_contracts.py,
   source_contract_cli.py, source_contract_projection.py и task_debugging.py.
   Сравни native/reference/TypeScript в соответствующих границах.
   Старые027 графы мигрируй явно через nex migrate с сохранением истории и ID.
   При отказе сохраняй исходник, промежуточный IR и диагностику, исправляй причину.

4. Проверь установленный, перемещённый и восстановленный Windows SDK текущей
   версии. Для0.159 требуется41 maintained phase с --browser и --live;
   старый SDK31 эту цепочку не закрывает. Подтверди provenance и неизменность
   SDK, запрет fallback к исходникам/внешним зависимостям и отрицательные controls.
   Платформенную изоляцию и доступность отладчика проверяй фактически на Windows.
   Контракты и сборка production-web должны работать из установленного комплекта.

5. Подготовь CUDA provider текущим Windows-компилятором и выполни реальные
   native/reference U8 Add/Affine, GPU/CPU placement и fallback policy.
   Проверь owned/scoped resources, enqueue/cancel/deadline и освобождение после
   физического fence. Добавь встроенные028 контракты вместе с внешней проекцией,
   generic-корни и профили видимых managed pools. Запусти Compute Sanitizer на
   фактических native-приложениях; запиши device/kernel records и точные хеши.
   Успех готового U8-провайдера имеет свой scope; общая компиляция GPU-ядер остаётся отдельной задачей.

6. Проверь настоящие production Workers/UI в Chromium, Firefox и WebKit по
   закреплённому npm lock, включая typed errors, pre/post traps и последующий
   успешный запрос. Отдельно проверь source/server code closure в emitted client.
   Build production assets и исполнение в браузере должны иметь отдельные результаты.

7. Проверь examples/tic-tac-toe: правила, события, самостоятельный пакет без
   compiler/source, GPU readback и DPI/resize. Mac Retina/letterboxing использует
   физический SDL presentation rectangle; нужна Windows-проверка этих границ.
   Разработка большой игры не входит в задачу языка.

8. Для доступных Windows NPU/D3D12/других ускорителей выясни модель, API, драйвер
   и поддержку в текущем descriptor. Проверь реальные аппаратные пути и их scope.
   Общие GPU/NPU, полноценный Windows SDK, mobile/UI, Studio, конвертер,
   большие системы и измерения стоимости LLM сохраняются в исходном PLAN.

9. Обнови компактные evidence, описания EN/RU и этот handoff. Выполни commit/push
   проверенной ветки; main обновляй по завершённой матрице без force-push.
   В результате нужны actual compiler/SDK/CUDA/GUI receipts, сохранённые отказы
   и точный список оставшейся работы. Весь проект требует выполнения исходного PLAN.
