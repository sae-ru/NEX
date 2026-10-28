# Private source exception modules

Toolchain0.135.23 adds explicit source-checked modules to `0.25-prototype`.
Discover `source_exception_prototype.private_task_native_module_*`. Ordinary
projects remain public024; public archive/provider schemas keep their meanings.

The C++ compiler APIs in `nex/private_task_modules.h` are:

- `planSourceExceptionTaskModules`: check ownership, selected exports and direct
  dependencies against a retained `nex.private-task-source/2` context.
- `emitSourceExceptionTaskModule`: emit verified MLIR/native task code and its
  source-derived `nex.private-task-module/1` record.
- `validateSourceExceptionTaskModule`: rederive that record with the current
  compiler and checked source. A record alone cannot establish a binary's source.

These are separate experimental APIs and developer probes, without public
project selection or an installed SDK workflow. They do not manufacture graph
revisions or reinterpret public sourceBundle/provider records.

## Architecture

The full checked project context supplies source units. Every unit has one
component owner. Direct source imports and cross-component machine references
require direct architecture dependencies. Each selected provider entry/export
is a public concrete source function; imported generic exports expand to their
checked concrete instances. Private helper bodies remain inside their owner.
Unselected public functions do not become external exports automatically.

```json
{
  "schema": "nex.private-task-architecture/1",
  "mode": "shared-fixed",
  "application": "app",
  "components": {
    "leaf": {
      "entry": "leaf::answer",
      "units": ["leaf/main.nex"],
      "exports": [],
      "dependencies": []
    },
    "app": {
      "entry": "app::main",
      "units": ["app/main.nex"],
      "exports": [],
      "dependencies": ["leaf"]
    }
  }
}
```

`static` produces code-only archives linked into one application. `shared-fixed`
uses startup-loaded code images and one common runtime image. Each component
has its own emitted definitions; a consumer does not re-emit provider bodies.
The runtime, root executor, control and operator configuration belong to the
application. There is no unload or hot replacement protocol.

The private cohort uses ABI2502 in every module, including pure helpers.
Every intermodule call or function value uses a checked continuation descriptor;
pure callbacks do not accidentally use the sequential throw-output ABI.
Private standalone pure images retain their separate2501 behavior. Public
ABI3/4/5 requirements and source provider records remain unchanged.

## Values and errors

Existing checked scalars, immutable aggregates, concrete generics, function
values, File and opaque foreign resources retain their types and realms.
Scope/channel/future values can cross the checked source module interfaces in
the same joined executor. A returned callback can retain an owned resource.
Static lifetime analysis and mandatory runtime region/group checks continue
to apply; a descriptor or metadata flag does not construct a resource owner.

Direct calls, callbacks, waits and drains preserve source errors and original
throw sites across modules. Lexical rethrow preserves its payload and origin.
Runtime traps and control outcomes still bypass source catches, regardless of
whether a source error uses a string such as `E_TIMEOUT`. The application drains
admitted physical work and releases owned values before completion.

The checked transitive closure determines selected-root read/write/stream and
foreign requirements. The common runtime support union also includes exported
provider code that the root does not call. These are separate facts; unused
exports do not grant the root an operator configuration. File and foreign
configuration is captured once by the normal application host.

Raw C extern declarations are used through ordinary source task/ffi wrappers;
they are not themselves NEX module exports. C FFI still cannot transport NEX
task/scope/channel/File authority or general source callbacks.

## Source and actual images

The record is explicitly `archived:false`, with compiler identity, concrete
signatures, canonical definitions, selected imports/exports, source-unit ownership,
source hashes and a retained source projection. The whole project context remains
required for checking, including consumer-triggered generic specializations.
Consumer body edits can reuse unchanged provider records and machine artifacts.
Module records are source contracts; an actual completed image additionally needs
its compiler/target/link inputs and artifact hashes. JSON shape is insufficient.

The `source_exception_modules` functional conformance builds real code-only
archives and fixed shared libraries, uses one runtime, runs O0/O2 programs and
compares independent AST/TaskIR outcomes. It checks callbacks in both directions,
concrete generics, file/resource ownership, scopes, futures, channels, source and
runtime exits, original sites, source-absent execution, loader runtime counts,
cleanup and provider reuse. Copied shared images execute while the originals
are absent. Security-specific checks remain user-deferred.

Toolchain0.135.24 adds explicit [mixed static/shared image frontiers](source-exception-frontiers.md)
through architecture/2 and module/2, retaining the architecture/1 behavior above.
Toolchain0.135.25 adds [consumer-owned trait specializations](source-exception-instances.md)
through architecture/3 and module/3. Module HTTP integration, module profile/logical debugging, general binary-only
checking, public build/project/SDK integration, full platform delivery and explicit
history-preserving024-to025 migration remain pending. Complete inference,
unstructured parallel exception lowering and the original broader objective
also remain open. This is scoped private functional work.
