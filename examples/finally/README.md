# Synchronous finally development example

Use the actual compiler with the `source_exceptions.finally_development`
capability. From this directory run `nex eval`, `nex run`, `nex test`, or `nex test --target web`.
The finalizer runs before the pending Result failure returns. Task finalization remains pending and is explicitly rejected.
This example is development evidence; complete platform/SDK delivery is separate.

See [the rules](../../docs/exceptions.md). The complete language/toolchain
and platform plan remains open.
