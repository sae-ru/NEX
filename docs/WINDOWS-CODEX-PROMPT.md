# Промпт для продолжения NEX в Codex на Windows

Скопируйте текст ниже в новый чат, открытый в локальном checkout NEX на Windows.

---

Продолжи разработку и нативную проверку NEX на этой Windows-машине.

NEX — Neural Execution Language, язык нейронного исполнения. Главная идея:
максимум точного смысла на необходимый токен при высокой производительности и
безопасном исполнении. Проверяемые типы/эффекты/realms, семантический граф и
ограниченный контекст помогают изменять большие программы. Полная экономия
токенов на принятых задачах разных LLM ещё не измерена. Готовой программе LLM
не нужна.

Текущая разработка: toolchain 0.165.0 / язык 0.28 / task ABI 7. Это не готовый
бинарный релиз. GitHub sae-ru/NEX, MIT. Прочитай AGENTS.md, README.md,
llm/SYSTEM_PROMPT.md, docs/windows-host.md, docs/windows-handoff-current.md,
docs/evidence/windows-latest-build-CUDA-0.165.0-2026-11-10.json и PLAN.md.
План включает будущие возможности и не является списком уже реализованного.
Перед изменением языка прочитай docs/language.md и docs/grammar.ebnf.

Вначале проверь git status, git log -1, upstream и фактические doctor/describe.
Сохраняй локальные изменения и историю графа; не используй reset/force-push.
Опубликованная ветка, локальная разработка и архив SDK могут иметь разные версии.
Проверенный Windows-снимок 2172b35fcad4c959a34ccbb11149264d52f9daf9 содержит
2146 файлов; последующая документация не меняет его идентичность. Сверяй текущий
код и возможности по actual compiler, а каждую квитанцию — по её source/compiler
и archive hashes. Не запускай старые NEX ради нового результата.

Для обычной установки этого снимка прошли все цели сборки, 11 выбранных групп,
35 физических CUDA-сценариев и 36 Compute Sanitizer случаев на RTX 3090.
Windows compiler SHA256: 0ee1c4bdc4cc121ec020cb03af7eb39b5f4d157624c5ac0981203ec814df2a76.
Она включает 13 установленных файлов owned Metal tools; source-only preparation
прошла без запуска GPU. Это не приёмка нового переносимого SDK. HTTP callback
и census отдельно проверены в 38 debug sessions и 38 offline captures на Mac и
Windows, с исходными ограничениями. Детали и исходные сбои — в evidence.

Перед запуском проверь, не работают ли уже владельцы source/SDK/CUDA-проверок.
Сверяй реальный process/handle и время создания процесса, а не только state file.
Тайм-аут опроса не означает завершение; не запускай дубликат живой задачи.

Последовательность работы:

1. Зафиксируй HEAD и хеши compiler/resources, версии языка/ABI и инструментов.
   Запроси nex doctor --json и nex describe --kind index --json. Возможности
   извлекай через describe --field PATH --json; контекст — context --symbol NAME --json.
   Сохраняй согласованные compiler_build и descriptor_hash. Не меняй строки
   версий старых графов/отчётов.

2. Проверь C++20, LLVM/MLIR 22.1.x, Z3, SQLite, OpenSSL 3, CMake/Ninja, Python 3.10+
   и закреплённые Node/npm зависимости. Host CLANG64 и target LLVM-MinGW имеют
   разные C++ ABI. Собери все цели cmake --build build -j 4 в отдельном каталоге.
   Используй согласованный OpenSSL cohort, включая configuration/providers/notices,
   и совместимые LLDB pipe/stdio transports. Сохрани полный registry, CTest exit,
   JUnit и журналы; проверь их через tools/ctest_report.py вместе с fixtures.

3. В снимке 2172b35 зарегистрированы 303 группы. Оператор намеренно ограничил
   IPv6; не меняй эту политику. Restricted297 исключает task_dns_source,
   task_dns_delivery, task_tcp_source, task_tcp_delivery, task_network_transport
   и task_http_client_source. Отдельно проверь исходные IPv4 DNS/TCP delivery
   commands, все доступные source-сценарии, HTTP и kernel cases. Native-отказ
   10013 и windows-ipv6-denied не доказывают успешный IPv6. Restricted297 и
   дополнительные проверки не переименовываются в полный303; всегда сверяй
   фактические registry и scope, сохраняя исходные неуспешные команды.

4. Собери новый SDK из одной обычной установки через sdk_bundle/sdk_archive,
   без подмены ресурсов. Проверь перенос/восстановление, immutable inventory,
   doctor и native/reference выполнение. Полные поддерживаемые SDK phases с
   --live --browser выполняются для каждой установки; выбранные Python и
   network-profile фиксируются. Проверь реальные read-denial controls и
   read-only SDK. Обычный token не равен изоляции.

5. CUDA35/memcheck36 выше — ordinary-install evidence. Проверь новый immutable
   SDK на реальном GPU, включая CUDA provider, context, dispatches, resource
   settlement и cleanup. Сохраняй все source/compiler/provider/header/driver/
   sanitizer identities и deadline 2000ms. Metal emitter поддерживает только
   объявленный скалярный subset; Windows source-only check не исполняет Metal.
   Apple NPU и другие неподтверждённые устройства остаются pending.

6. Сохраняй checked arithmetic, left-to-right/short-circuit, строгий UTF-8 и
   Unicode scalars, immutable aggregates, эффекты, realms и owned cleanup.
   Сравнивай observable native/reference/TypeScript и rejected programs.
   result<T>, typed source errors, traps, cancellation и limits различаются.
   requires/ensures/invariant/decreases языка0.28 проверяются и в release;
   истории0.27 мигрируются явно с сохранением ID и ревизий.

7. Проверь browser/API delivery: в клиент входят только достижимые client/shared
   declarations. Windows GUI/GPU/DPI, NPU/D3D12 и остальные API проверяй на
   реальном устройстве с точным operation/backend/fallback scope. Большой новый
   игровой проект не входит в задачу языка.

8. Сохраняй исходные сбои, IR, журналы и владение процессами. Повторяй после
   подтверждённого исправления нужную область, не скрывай отказ skips или
   ослаблением verifier. Не меняй защиту, сеть или права исходного проекта ради
   зелёного результата. Обнови EN/RU, evidence и handoff по фактическим данным.
   После приёмки актуального SDK сохрани согласованные изменения commit/push
   в main, с сохранением чужих изменений и истории, без force-push.

Весь исходный PLAN сохраняется: общий GPU/NPU codegen, GPU debugging/profiling,
остальные платформы, Apple NPU, mobile/native UI, NEX Studio, C++/Python-конвертер
и реальные измерения полных принятых задач разных LLM. Завершение одного SDK или
провайдера не завершает проект; результат должен подтверждаться по требованиям.
