# Продолжение NEX в Codex на Windows

Откройте отдельную локальную копию репозитория на Windows и вставьте приведённый
ниже промпт в новый чат Codex. Он передаёт рабочий контекст проекта; история
этого чата автоматически на другой компьютер не переносится этим текстом.

Codex поддерживает работу в native PowerShell; WSL является отдельной средой.
При тестировании NEX различайте фактическую среду исполнения.
[Официальная инструкция OpenAI для Windows](https://learn.chatgpt.com/docs/windows/windows-sandbox).
Инструкции проекта храните в `AGENTS.md`, который Codex читает при запуске работы.
[Официальная инструкция AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md).

## Промпт для нового чата

```text
Продолжай разработку NEX — Neural Execution Language. Репозиторий:
https://github.com/sae-ru/NEX. Работай с его актуальной main в отдельном локальном
checkout на этом Windows-компьютере. Сначала проверь git status и HEAD;
сохраняй существующие пользовательские изменения. Для работы используй ветку
с префиксом codex/.

Цель текущего этапа — довести фактическую поддержку Windows и проверить NEX
на этой машине: CPU, задачи, GPU/CUDA и нужные Windows-интеграции. Продолжай
исправления и реализацию обнаруженных пробелов, а не ограничивайся планом.
Общий PLAN проекта сохраняется; один удачный GPU-пример его не завершает.

Что прочитать:
- AGENTS.md и актуальные README.md / README.ru.md.
- docs/releases/0.151.1.json — точный принятый Mac SDK, исходный коммит,
  контрольные суммы, проверки и ограничения. Перепроверь фактические данные.
- docs/windows.md, docs/windows-files-design.md, docs/architecture.md,
  docs/sdk.md, docs/device.md и docs/compute.md для затронутых адаптеров.
- llm/BOOTSTRAP.md, llm/SYSTEM_PROMPT.md и llm/LEARNING.md.
- docs/language.md и docs/grammar.ebnf перед изменением языка.

База, которую нельзя перепутать с Windows-приёмкой:
- Текущий язык 0.27, toolchain 0.151.1; native task ABI7. Старые ABI и ревизии
  сохраняют свои версии. Язык не повышается редактированием nex.json.
- Кодовая база Mac SDK зафиксирована коммитом
  61ab2980c7d97feed9d1663925608278cac20b4c; последующая публикация добавляет
  документацию/лицензию. Сравни фактическую историю main и delivery record.
- MIT относится к NEX; сторонние компоненты имеют собственные уведомления.
- Apple M5 Max прошёл ограниченную проверку OpenCL U8 Add/Affine:31 сценарий,
  64 исполнения, 48 запусков ядер. В том числе живой GPU-буфер перенесён в
  typed exception через scope/catch/finally. Это не CUDA/Metal/универсальный GPU.
- CIX/RK Linux GPU/NPU имеют собственный отчёт toolchain 0.151.0. Он не принимает
  новый Windows SDK. См. docs/evidence/accelerators-0.151.0.json и
  docs/evidence/macos-opencl-0.151.1.json.
- Windows GNU/UCRT x64/ARM64 и x64 Wine проверялись в прежних отдельных scopes.
  Native Windows OS/hosted compiler, task fs/ffi/providers, debugger/profiler,
  DLL/packaging и CUDA требуют собственной текущей реализации/приёмки.
- Mac ARM64 SDK не запускается на Windows. Старый локальный Mac-проект0.81/0.16
  и его граф были сохранены отдельно; не переносить поверх него новую версию
  и не считать его содержимое опубликованной main.

Первые действия на этой Windows-машине:
1. Зафиксируй Windows build, архитектуру, CPU, GPU/драйверы, RAM и доступные
   Git/CMake/C++/LLVM 22.1/MLIR/SQLite/OpenSSL/Z3/Python/Node инструменты.
   Для NVIDIA проверь nvidia-smi и nvcc --version, если они установлены.
   Разделяй native Windows, MSYS2, WSL и Wine в каждом результате.
   Сохраняй `.gitattributes`: checkout должен сохранять точные байты закреплённых
   источников и fixtures; не перенормализуй их окончания строк.
2. Подготовь подходящую цепочку сборки. Сначала проверь текущие рецепты и
   реально доступные зависимости. Windows-hosted compiler ещё может требовать
   портирования POSIX-частей; исправляй настоящие причины. Для ранней проверки
   target-кода можно использовать WSL как producer для Windows PE cross-build,
   затем запускать полученный .exe в native PowerShell. Это проверяет исполнение
   программы на Windows; Windows-hosted NEX SDK остаётся отдельной задачей.
   Исполнение самого приложения внутри WSL не заменяет native Windows.
3. Когда nex запустится, запроси doctor --json, describe --kind index --json,
   затем только нужные поля. Важны source_concurrency, structured_tasks_runtime,
   source_exceptions, source_exceptions.source_providers, foreign_boundary,
   device, compute и windows_core_target. Не придумывай отсутствующие API.
4. Прогони корректность CPU: checked overflow, Unicode/NUL/bytes, aggregates,
   generics/traits, typed errors, guards/finally, задачи/каналы/отмена/лимиты.
   Сравни reference/native/TypeScript там, где backend доступен. Сохраняй
   rejected-программы и диагностику. Изменения компилятора требуют согласования
   frontend, reference, MLIR, TypeScript, спецификации, грамматики и manifest.
5. Выполни требуемые сборку и полный CTest для выбранного генератора CMake.
   Для multi-config явно указывай конфигурацию. Фиксируй реально исполненные
   случаи и пропуски внутри Python-наборов, а не только зелёный CTest group.

Порядок GPU/CUDA:
- Подтверди настоящее NVIDIA-устройство и совместимые установленные инструменты.
  Если CUDA-устройства нет, подготовь код/compile checks, оставь физическую
  CUDA-приёмку pending и продолжай доступную Windows-работу.
- Готового универсального CUDA backend сейчас нет. Используй существующие
  std/compute.nex, std/device.nex, checked FFI и owned resources как основу.
  Сначала доведи нужный Windows loader/task/FFI слой, затем явный CUDA-провайдер.
  Поддержку GNU/UCRT и MSVC/NVCC проверяй раздельно; ABI/CRT нельзя смешивать
  без проверенной C-границы и правил выделения/освобождения памяти.
- Начни с точно проверяемых операций и dtype/shape текущего контракта.
  Нужны реальные upload/kernel/download, идентичность выбранного GPU,
  независимый CPU-эталон, крайние размеры, overflow/invalid input и повторное
  использование. Один vendor C++ kernel не доказывает вызов из NEX.
- Удерживай DLL/сессию/буферы до подтверждённого физического завершения CUDA.
  Проверяй отмену, deadline, nested scopes, typed error/catch/finally и очистку.
  Отмена исходной задачи не доказывает остановку GPU/DMA.
- CPU fallback разрешается только явно и только в объявленных случаях
  unavailable/unsupported. Он не скрывает overflow, ошибки протокола,
  некорректные данные, отмену или потерю устройства.
- Разделяй время CPU, передачи, GPU-ядра и полную задержку. Фиксируй устройство,
  драйвер, версии, входные данные и повторы; не объявляй ускорение по одному
  крошечному запуску. CUDA Compute Sanitizer/ASAN используй при фактической
  поддержке установленной цепочкой. Санитайзеры для корректности разрешены;
  отдельная audit/fuzz-кампания не является задачей этого этапа.

Далее доводи Windows-файлы/пути/права, динамические библиотеки, CPU-side
отладку/профиль, HTTP/сеть и переносимый SDK. DirectX/DirectML/NPU оценивай
по реальному оборудованию и отдельным контрактам; готовую поддержку не заявляй.

Сохраняй исходники/манифесты/locks/тесты и небольшие доказательства в Git.
Кэши, большие SDK, бинарные зависимости, секреты и пользовательские графы
не добавляй. Историю графа сохраняй snapshot/export и явной миграцией.
Не ослабляй требования и не заменяй неработающую возможность заглушкой.
Исправляй найденное, проверяй изменённое поведение, сохраняй полезный failed IR.

Результат этапа: код, инструкция запуска на этой Windows-машине, точные
compiler/source/toolchain pins, результаты native Windows CPU/GPU/CUDA,
отчёт о памяти/завершении и честный список оставшегося. Для каждого пункта
укажи passed/failed/pending/skipped и конкретное доказательство. Доступность
устройства, cross-build, Wine, WSL и реальный native NEX-вызов учитывай отдельно.
```

Исходники и переносимый контекст находятся в репозитории. Пароли, SSH-ключи,
локальные Mac-кэши и полная переписка в этот публичный handoff не включаются.
