# Version3 local Qwen preparation

This is a new protocol for the existing ten-task NEX/C++/Python comparison,
using explicit NEX0.30. It adds public byte/source-task references and a bounded
normative reference packet for independent source review. The
[protocol](protocol.md) defines the changed inputs and unchanged budgets.
Historical results and failed attempts remain in their own freezes.

The entry point is `collector.py`, with the same `freeze`, `run`, `finalize` and
`ledger` commands as the preceding collector. Run `--help` for actual arguments.
Freezing is preparation, not inference; `run` owns a separately loaded local
Qwen3.8 27B Q8_0 instance. No paid API, automatic source repair, relaxed check,
free reference request or expanded execution grant is introduced.

The implementation reuses the version1 collection/accounting engine and version2
source030 acceptance adapter without editing their code. Canonical guide files
are compared with the selected compiler's actual `guide` output. Independent
review receives the same per-language reference packet for every task and no
author conversation; its complete request cost remains counted.

Offline controls use a synthetic provider with synthetic token counters. They
are not model observations. A future observed study must use a new immutable
directory, qualified compiler/resources, fixed weights/runtime and retained raw
calls. The [latest completed study](../../../docs/llm-cost-qwen38-27b-2026-11-17.en.md)
remains6/20 NEX,18/20 C++ and20/20 Python accepted, with two unknown-usage calls.

По-русски: подготовлена отдельная версия протокола. Добавлены существующие
справки по байтам и задачам, а ревьюер получает нормативную семантику языка.
Старые результаты не пересчитаны; новый замер модели ещё не выполнен и экономия
токенов не заявлена.
