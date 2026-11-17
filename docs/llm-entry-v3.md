---
status: current
applies_to: "language 0.30; toolchain 0.280.1"
owner: repository
---

# Public reference context for LLM authors and reviewers

The [version3 preparation](../experiments/quality/llm-campaign-v3/README.md)
responds to the [completed local study](llm-cost-qwen38-27b-2026-11-17.en.md).
It changes reference delivery, not NEX syntax or the study's task contracts.
No observed version3 model result or token saving is claimed.

Use `nex guide --kind tasks-runtime` for `with_tasks`, `task_spawn`, `task_wait`
and `task_yield`. The `task` guide describes JSON acceptance contracts. The
source guide now starts with a complete current example and ownership/effect
rules; historical ABI notes remain below a marked boundary. `bytes` describes
immutable binary updates; `bytes-construction` describes linear bulk construction.
These are existing compiler guide kinds. The common coding contract still fits
4096 bytes; the quick sheet stays within its6144-byte ceiling.

The new study broker exposes those guides, list/text construction and reference
state, plus their verified canonical public document paths. Preparation compares
each full compiler-served guide with its selected resource file. Bounded
read/search can continue through the actual named document. Every discovery,
edit, check and review request remains charged through the whole-task ledger.

Independent review receives the same frozen public language-reference packet
for every task in that language. NEX's packet includes the quick guide and current
source-task/CPU-mapping introductions; C++/Python receive their existing baseline
notes. The packet is bounded to16384 UTF8 bytes, independent of source inputs,
and pinned before generation. The reviewer receives no author history, trusted
solution or held-out output. A false review remains a failure. Raw requests and
receipt hashes retain exactly which references were supplied.

The [protocol](../experiments/quality/llm-campaign-v3/protocol.md) keeps model,
sampling, request/time/token budgets and clean-prefix resume rules. New envelope3
and trial IDs prevent continuation of version1/2 freezes with changed inputs.
Their results, source-review mistakes, unknown usage and execution amendments
remain preserved. Synthetic-provider tests and executed guide examples establish
host/reference behavior; they do not establish an improvement in model output.

These source documentation changes were added after the immutable0.280.1 SDK
snapshot. They do not rewrite the published SDK or its exact qualification.

По-русски: справка по исходным задачам отделена от JSON-заданий приёмки, доступны
документы по байтам и построению коллекций. Ревьюер получает семантику выбранного
языка, а её стоимость учитывается. Это подготовка нового протокола; прежний замер
не пересчитан, новый запуск модели ещё не выполнен.
