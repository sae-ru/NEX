---
status: current
applies_to: "language 0.30; toolchain 0.280.1"
owner: repository
---

# Bounded coding contract and local study version2

The [common coding contract](../llm/SYSTEM_PROMPT.md) fits one4096-character read
and at most4096 UTF8 bytes. The previous complete contract is preserved verbatim
as [detailed coding rules](../llm/DETAILED_CODING_RULES.md). The normative language
specification, grammar, compiler capabilities and ownership/effect requirements
retain their authority. Shorter entry text does not enable additional syntax.

The [version2 study](../experiments/quality/llm-campaign-v2/README.md) integrates
frozen compiler guide and diagnostic actions with ordinary source reads, edits,
checks, submission and independent source review. Large guides have explicit
bounds and a path for read/search continuation. Quick/stdlib document aliases
resolve to actual compiler text. All reference requests and their prompt/reply
tokens are charged through the existing whole-task ledger.

The collection runtime currently targets macOS ARM64 LM Studio; Windows/Linux
model collection is pending. The new study executes NEX as explicit0.30, retains the same ten task contracts
and C++/Python fixtures, and uses only local Qwen3.8 27B Q8_0. Historical study
freezes cannot be resumed under its changed protocol. New freezes pin both
implementation dependencies and actual reference/compiler/model identities.
The [protocol](../experiments/quality/llm-campaign-v2/protocol.md) describes the
preserved budgets, boundaries and changed inputs.

The [offline evidence](evidence/llm-entry-v2-0.280.1-2026-11-17.json) passes ten
trusted030 solutions and rejects ten wrong starts.
The reference broker composes with source edits/submission. A synthetic action
loop confirms that guide, explanation, edit, check, submission and independent
review remain six accounted calls. These are host controls with zero real model
calls. They do not establish an observed quality improvement or token saving.

The [original local comparison](llm-cost-qwen38-27b-2026-11-11.en.md) remains
unchanged: NEX4/20, C++14/20, Python20/20 accepted tasks. Because version2 changes
both references and explicit project language, any later difference cannot be
attributed solely to the common prompt without another controlled experiment.
Collect observed model trials only with an idle, fixed runtime and qualified
compiler/resources, separately from SDK regression load. Each immutable SDK
retains its own frozen document snapshot.

По-русски: короткий общий промпт дополнен полной инструкцией и справкой
компилятора по запросу. Все обращения, исправления и повторы входят в стоимость
принятой задачи. Офлайн-проверки готовы; новый замер модели ещё не выполнен,
экономия токенов не заявлена. Прежние неудачные попытки сохранены.
