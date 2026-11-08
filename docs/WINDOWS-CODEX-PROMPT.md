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

Работаем с актуальным NEX: toolchain 0.162.2 / язык 0.28 / task ABI 7.
GitHub sae-ru/NEX, public, MIT. Прочитай AGENTS.md, README.md,
llm/SYSTEM_PROMPT.md, docs/windows-host.md, docs/windows-handoff-current.md,
docs/evidence/current-platforms-0.162.2-2026-11-08.json и PLAN.md. План включает
будущие возможности и не является списком уже реализованного. Для изменения
языка дополнительно прочитай docs/language.md и docs/grammar.ebnf.

Вначале проверь git status, git log -1, upstream и фактические doctor/describe.
Сохраняй локальные изменения и историю графа. Обновляй checkout до согласованной
актуальной версии без reset/force-push. Нативный снимок этого этапа —
78acb4395573f003807b48e1bb5694bf9630f347; Python-поправки включены в
3bdad7ab365c3d794d403031ad3ae2bfcec09b12. Позднейшая документация имеет отдельный
commit. Точные версии каждой проверки и архива указаны в evidence.
Используй актуальную реализацию, сохраняй результаты старых снимков отдельно.

Измеренные результаты: полный Mac source 301 прошёл. На Windows собраны все
цели, новый SDK перемещён/восстановлен и прошёл doctor. Реальный TCP binary
обмен прошёл в reference/Debug/Release с закрытием всех соединений. Первый
Windows SDK этого этапа прошёл 28 фаз и упал на компиляции TCP-модуля без SDK
sysroot; новый согласованный архив содержит исправление. Тот же архив уже
прошёл CUDA 35/memcheck 36 на RTX 3090: 66 физических завершений ядер, баланс ресурсов
и 36 нулевых error/leak summaries подтверждены независимой сверкой сырых логов.
Полные 82 фазы SDK и полная актуальная Windows-матрица пока не приняты.
Перед новым запуском проверь, не работают ли уже владельцы этих проверок.
Не запускай дубликат, пока его реальный процесс/handle жив.

Последовательность работы:

1. Зафиксируй точный HEAD и хеши исходников, compiler/resources, языка/ABI и
   инструментов. Запроси nex doctor --json и nex describe --kind index --json.
   Возможности извлекай через describe --field PATH --json; контекст проекта —
   через context --symbol NAME --json. Сохраняй согласованные compiler_build и
   descriptor_hash. Не меняй строки версий старых графов/отчётов.

2. Проверь C++20, LLVM/MLIR 22.1.x, Z3, SQLite, OpenSSL 3, CMake/Ninja, Python 3.10+
   и закреплённые Node/npm зависимости. Host CLANG64 и target LLVM-MinGW имеют
   разные C++ ABI. Используй отдельный build-каталог и фактически выбранный
   согласованный OpenSSL cohort. tools/windows/openssl/README.md описывает
   path corrections; не смешивай его библиотеки, DLL, configuration и providers.
   Собери все цели через cmake --build <build> -j4, сохрани unfiltered registry,
   actual CTest exit, JUnit, stdout/stderr. docs/ctest-results.md описывает
   проверку точного набора, включая обязательные fixtures.

3. Проверь обычную установку, перемещённый и восстановленный SDK. Полная цепочка
   tools/sdk_acceptance.py использует --live --browser и 41 maintained phase на
   каждую установку. На этом стенде IPv6 намеренно ограничен: профиль
   --network-profile windows-ipv6-denied требует реального Windows отказа 10013.
   Не меняй сетевую политику. Четыре положительные IPv6-группы
   task_dns_source/task_dns_delivery/task_tcp_source/task_tcp_delivery остаются
   непроверенными; 298 остальных групп не равны полному 302. Число групп всегда
   проверяй по фактическому registry, а не по историческому отчёту.
   Подтверди фактическую область изоляции, неизменность SDK, source/dependency
   denial и реальные отрицательные controls. Обычный token не равен изоляции.

4. Сохраняй checked arithmetic, left-to-right и short-circuit semantics, строгий
   UTF-8/Unicode scalars, immutable aggregates, эффекты и realms. Сравнивай
   observable native/reference/TypeScript behavior и rejected programs.
   result<T>, typed source errors, traps, cancellation и limits различаются.
   Исходные requires/ensures/invariant/decreases языка 0.28 проверяются и в
   release. Истории 0.27 мигрируются явно с сохранением ID и ревизий.

5. CUDA 35/memcheck 36 уже прошли для закреплённого архива из evidence. Сохраняй
   эти результаты; повторяй при изменении соответствующих implementation/tool
   inputs. Новую проверку готовь из experiments/owned-cuda (в установленном
   SDK: share/nex/tools/owned-cuda). Запусти 35 реальных hardware cases и
   memcheck.py: 35 native cases плюс context probe. Запиши модель GPU, драйвер,
   CUDA headers, фактические kernel/fence records, исходники и бинарные hashes.
   Проверяй cancellation/deadline, owned buffers и cleanup после физического
   завершения. CPU fallback не доказывает GPU execution. U8 Add/Affine provider
   не является общей компиляцией произвольных GPU-ядер.

6. Проверь production Workers/UI в Chromium, Firefox и WebKit по npm lock,
   включая typed errors, контракты, отмену и последующий успешный запрос.
   В клиент должны попадать только достижимые client/shared declarations.
   Для examples/tic-tac-toe проверь события, самостоятельный пакет, GPU readback,
   resize/DPI; большой новый игровой проект не входит в задачу языка.
   Доступные Windows NPU/D3D12/другие API проверяй на реальных устройствах с
   точным operation/backend/fallback scope.

7. Сохраняй исходные сбои, промежуточный IR и process ownership. Тайм-аут опроса
   не означает завершение задания. Исправляй подтверждённую причину и повторяй
   нужную область; не скрывай неудачи изменением verifier или skips.
   Обнови evidence, EN/RU описания и handoff по фактическим результатам.
   Пользователь разрешил commit/push принятого актуального SDK в main;
   сохраняй локальные изменения и историю, без force-push.

Весь исходный PLAN сохраняется: общий GPU/NPU codegen, остальные платформы,
mobile/native UI, NEX Studio, C++/Python конвертер и реальные измерения полных
принятых задач разных LLM. SDK и аппаратная проверка отдельных провайдеров —
этапы этого проекта. В результате нужны точные receipts, сохранённые отказы и
честный список оставшейся реализации; завершение всего проекта должно быть
подтверждено по каждому требованию.
