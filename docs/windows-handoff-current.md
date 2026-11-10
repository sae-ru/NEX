# Передача NEX: Windows 0.165.0 / язык 0.28 / task ABI 7

Текущая реализация развивается как NEX 0.165.0. Это не объявление готового
переносимого SDK. [Промпт нового чата](WINDOWS-CODEX-PROMPT.md) сохраняет исходный
объём проекта и порядок проверки. Всегда сверяйте локальный HEAD и фактические
`doctor` / `describe`: опубликованная ветка, рабочий checkout и архив SDK могут
иметь разные версии.

## Что подтверждено

[Точный Windows-снимок `2172b35`](evidence/windows-latest-build-CUDA-0.165.0-2026-11-10.json)
содержит 2146 файлов и включает установку публичных инструментов Metal и
исправленные HTTP-тесты. Он собрал все цели, прошёл 11 выбранных групп и обычную
установку. Все 13 файлов owned Metal tools установлены без изменений; подготовка
через публичный emitter проверена без запуска GPU.

Через эту обычную установку на RTX 3090 прошли 35 физических CUDA-сценариев и
36 случаев Compute Sanitizer, включая context probe. Deadline native-сценариев
остался 2000 ms. Сырые журналы и идентичности проверены независимо.

- Source commit: `2172b35fcad4c959a34ccbb11149264d52f9daf9`.
- Windows compiler SHA256: `0ee1c4bdc4cc121ec020cb03af7eb39b5f4d157624c5ac0981203ec814df2a76`.
- Build evidence archive SHA256: `dddfadfc5d70dd23455d5e98b14cbe776bd343f3d9b137a29fd4a84fc294c235`.
- CUDA evidence archive SHA256: `1f014d95833c5ca12f5a7f262fc500049d0d74e34c65878850858a6bd23fd9c1`.

Это хеши проверенной обычной установки и архивов **журналов**, а не нового
переносимого SDK. Полные исходная и SDK-матрицы ещё не приняты. Позднейшие
коммиты документации сохраняют свои HEAD и не меняют идентичность этого снимка.

[HTTP callback/census follow-up](evidence/HTTP-debug-callback-census-0.165.0-2026-11-10.json)
отдельно прошёл по 38 сессий отладки и 38 offline captures на Mac и Windows.
Тест ждёт настоящего listener до старта прежнего клиентского таймера и настоящего
выбора task stop до чтения памяти. Baseline и final census используются
одновременно для проверки и отчёта; Windows проверяет точные множества handles.
Исходные числовые ограничения, сбои и диагностические материалы сохранены.

## Продолжить на Windows

1. Прочитайте [инструкцию сборки](getting-started.ru.md), [Windows host](windows-host.md),
   [описание языка](language.md), [правила LLM](../llm/SYSTEM_PROMPT.md) и
   [состояние разработки](../STATUS.md). Проверяйте возможности установленного
   компилятора через `nex describe --kind index --json`, затем `--field PATH --json`.

2. Сверьте выбранные C++20, LLVM/MLIR 22.1.x, SQLite, Z3, OpenSSL 3 и Python 3.10+.
   Host CLANG64 и target LLVM-MinGW имеют разные C++ ABI. Используйте одну
   проверенную цепочку OpenSSL — static libraries, DLL, configuration, providers
   и notices. [Подготовка Windows OpenSSL](../tools/windows/openssl/README.md)
   описывает поправки длинных путей. Для LLDB нужны совместимые pipe- и
   stdio-транспорты; сохраните версии/хеши реально выбранных host tools.

3. Соберите все цели через `cmake --build build -j 4`. Сохраните полный CTest
   registry, исходный exit code, JUnit и stdout/stderr. [Проверка результатов](ctest-results.md)
   должна учитывать обязательные fixtures. В снимке `2172b35` зарегистрированы
   303 группы; число зависит от конфигурации и проверяется заново.

4. На текущем операторском стенде IPv6 ограничен намеренно. Сохраняйте эту
   политику. Ограниченный профиль 297 исключает `task_dns_source`,
   `task_dns_delivery`, `task_tcp_source`, `task_tcp_delivery`,
   `task_network_transport`, `task_http_client_source`. Отдельные DNS/TCP delivery
   используют IPv4 и должны проверяться своими исходными командами; выбранные
   source-сценарии и native-контроль отказа 10013 не подтверждают успешный IPv6.
   Профиль SDK `--network-profile windows-ipv6-denied` также имеет отдельную
   область и не заменяет полный профиль. Не записывайте исключённые группы как
   passed или skipped для получения полного зелёного результата.

5. Соберите новый переносимый SDK через `tools/sdk_bundle.py` с выбранным
   `--windows-openssl-prefix`, затем `tools/sdk_archive.py`. Используйте одну
   установку исходников, без overlays. Проверьте archive inventory, перенос,
   восстановление, `doctor`, нативную сборку и явные foreign/providers. Полная
   `tools/sdk_acceptance.py --live --browser` выполняется для каждой установки;
   scope, выбранные Python, read-only SDK и реальные read-denial controls
   фиксируются отдельно. Обычный token и успешный `doctor` не доказывают изоляцию.

6. CUDA 35/memcheck 36 выше относятся к обычной установке. Новому переносимому SDK
   нужна собственная аппаратная проверка. Сохраняйте compiler/provider/header,
   driver и sanitizer pins, реальные dispatches, settlement и cleanup. Metal
   source-only preparation на Windows не означает выполнение Metal. GPU/NPU и
   остальные Windows API проверяются только в своей фактической области.

Не дублируйте живую проверку: сверяйте настоящий process/handle, включая время
создания Windows-процесса. Тайм-аут опроса не означает завершение задачи.
Сохраняйте исходный сбой, IR, журналы и команды. Права исходного проекта,
настройки сети и защиты остаются действующими; новый диагностический результат
сам по себе не разрешает их менять.

## История и следующий результат

[SDK/CUDA 0.162.2](evidence/windows-SDK-CUDA-0.162.2-2026-11-08.json) и остальные
прежние записи остаются доказательствами только своих архивов. Они не закрывают
приёмку SDK 0.165. Обновляйте EN/RU и evidence после фактических результатов.
Согласованные изменения принятого актуального SDK нужно сохранить commit/push
в main с сохранением чужих изменений и истории, без force-push.

Весь [PLAN](../PLAN.md) остаётся в работе: более общая GPU/NPU-компиляция,
пошаговая отладка/профилирование GPU, Apple NPU, остальные платформы и Windows API,
mobile/native UI, NEX Studio, C++/Python-конвертер и измерения полных принятых задач
разных LLM. Завершение отдельного SDK или провайдера не завершает этот объём.
