# Local Qwen study protocol 4

This protocol adds one response form to the local runner. The provider can
return a lone `<tool_call>` opening tag followed by a single complete JSON
action object. It must contain a string `action` field. The existing broker
validates the action and its arguments. Partial JSON, duplicate keys, multiple
packets, trailing text and unadvertised actions still fail. The original raw
provider response remains the basis of token accounting.

The change addresses nine consecutive responses observed in the version 3
SDK pilot. The NEX attempt exhausted its author request budget before it
sent a check action. The provider's reason for omitting the closing tag
remains unknown. See the [pilot record](../../../docs/evidence/llm-portable-sdk-0.280.1-2026-11-17.json).

Protocol 4 uses the same tasks, budgets, model, prompt, reference snapshot and
source review workflow as [protocol 3](../llm-campaign-v3/README.md). Freeze a
separate output directory with `collector.py freeze`. Trial IDs begin with `v4-`.
The version 4 runner accepts version 4 freezes. Use the corresponding earlier
runner to inspect a historical freeze and its original outcomes.

The decoder tests include an offline replay of the observed envelope shape.
The effect on model acceptance and total token usage requires a new measured run.
