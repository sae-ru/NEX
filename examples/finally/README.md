# Synchronous finally development example

Use the actual compiler with the `source_exceptions.finally_development`
capability. From this directory run `nex eval` or `nex test --target web`.
The finalizer runs before the pending Result failure returns. Ordinary
native and task finalization remain pending and are explicitly rejected;
this example is not evidence of native or task delivery.

See [the rules](../../docs/exceptions.md). The complete language/toolchain
and platform plan remains open.
