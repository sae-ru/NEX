# Промпт для продолжения NEX в Codex на Windows

Скопируйте блок ниже в новый чат, открытый в вашем локальном репозитории NEX.

---

Продолжи разработку и нативную проверку NEX на этой Windows-машине.

NEX — Neural Execution Language: точный смысл и небольшие контексты для разных
LLM, проверяемые программы и нативное исполнение. Язык0.27, source task ABI7.
Текущий main поставляет development toolchain0.156.0. GitHub: sae-ru/NEX,
репозиторий public, лицензия MIT. Пользователь разрешил commit/push результатов.
Сохраняй его локальные изменения; используй рабочую ветку с префиксом codex/.

Начни с git status, git fetch origin, git log -1 и проверки выбранного
компилятора через nex doctor --json и nex describe --kind index --json.
Прочитай AGENTS.md, README.md, docs/windows-host.md,
docs/windows-handoff-current.md, docs/releases/0.156.0.json и llm/SYSTEM_PROMPT.md.
Для изменений языка прочитай docs/language.md и docs/grammar.ebnf.
PLAN.md содержит оставшуюся работу, а не список уже доступных возможностей.

Принятый Mac-снимок компилятора: 3a220f36fc978e57756d254267605b4505cfbb57.
288 групп CTest прошли; перемещённый и восстановленный SDK прошли по 40 фаз
и 48 дополнительных сценариев на Python 3.10.22 и 3.14.9. Публикуемый архив — тот же
неизменный архив, который создан до этих полных проверок.
Это Mac-приёмка, а не доказательство работы текущего исходника на Windows.

Сохранённая Windows-приёмка относится к0.152.1: 274 группы, 35 аппаратных CUDA
случаев на RTX3090, установленный SDK31 и Compute Sanitizer. Внутренние48 skips
перечислены в квитанции; не считай их исполненными. Сейчас нужно проверить новый
main0.156 на текущем Windows-хосте. Язык0.27/ABI7 сохраняются; новые типизированные
ошибки, finally, runtime loop/value contracts и их тесты должны работать вместе.
Runtime contracts используют квитанции1/2/3/4. Generic-корни проверяются
параметрически по bounds/constructor kinds и работают для всех специализаций.
Source contract syntax ещё не поддерживается. Не принимай Mac-результаты за
новую Windows/CUDA-приёмку.

Практический порядок:
1. Выбери рабочую ветку от актуального origin/main с сохранением локальных правок.
2. Проверь локальные Windows LLVM/MLIR22.1.x, Z3, SQLite/OpenSSL, Python 3.10+,
   Node/npm, CMake и Ninja. Используй закреплённые зависимости
   tools/windows/host-dependencies.lock.json и docs/windows-host.md.
   Host CLANG64/UCRT и target LLVM-MinGW — разные C++ ABI; не смешивай их библиотеки.
3. Запусти tools/windows/configure-host.ps1. Собери весь build/windows-host:
   cmake --build build/windows-host -j4
   ctest --test-dir build/windows-host --output-on-failure
   Сохрани registry, команды, JUnit, stdout/stderr и хеши неизменного compiler/resources.
   Число групп выводи из текущего registry; учитывай явные platform-only skips.
4. При отказе сохраняй исходный код, промежуточный IR и диагностику. Исправляй причину,
   не ослабляй проверку. Сравнивай reference/native/TypeScript в применимых границах.
   Используй актуальные тесты runtime_contracts.py, runtime_loop_contracts.py,
   runtime_value_contracts.py, runtime_generic_contracts.py и task_debugging.py.
5. Проверь установленный, перемещённый и восстановленный Windows SDK. Требуется
   текущая полная40-фазная цепочка, включая --browser и --live; прежний SDK31
   не закрывает это требование. Исключи source-tree fallback физическим запретом
   доступа и отрицательными controls; подтверждай неизменность SDK и provenance.
6. Подготовь CUDA provider текущим выбранным Windows-компилятором. Повтори
   native/reference U8 Add/Affine, явное GPU/CPU placement, fallback policy,
   scoped resources, enqueue/cancel/deadline и освобождение после физического fence.
   Запусти Compute Sanitizer на фактических нативных приложениях. Проверяй
   реальные device/kernel records; не выдавай probe за полную поддержку CUDA.
7. Проверь SDL Tic-Tac-Toe из examples: правила, реальную очередь событий,
   самостоятельный пакет без compiler/source и GPU readback. Новое исправление
   Retina/letterboxing использует физический SDL presentation rectangle;
   проверь DPI/resize на Windows. Добавлять большую игру не требуется.
8. При наличии Windows NPU/D3D12/других ускорителей сначала выясни hardware/API/driver
   и текущую поддержку. Чётко фиксируй pending вместо подмены CPU-исполнением.
9. Обнови точные компактные evidence, README EN/RU и этот handoff. Выполни commit/push
   проверенной рабочей ветки. Обновляй main на основе завершённой матрицы, без force-push.

Результат: нативная Windows-цепочка без обязательного WSL, честная актуальная
матрица compiler/SDK/CUDA/GUI, сохранённые отказы и оставшиеся задачи. Не закрывай
весь проект по одному успешному примеру: общие GPU kernels, mobile/UI, Studio,
конвертер, source contract syntax и остальные исходные требования ещё открыты.
