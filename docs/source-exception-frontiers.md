# Private mixed native task images

Toolchain0.135.24 extends the explicit private025 module APIs with
`nex.private-task-architecture/2`, mode `mixed-fixed`. Public language stays024.
The prior architecture/1 and module/1 keep their uniform static/shared meaning.
Discover the actual `source_exception_prototype` descriptor and read the
[module guide](source-exception-modules.md) first.

## Components and physical images

Each component/2 adds explicit `linkage`: `application`, `static` or `shared`.
Only the selected root uses `application`. Every checked source unit still has
one source component. Its emitted definitions are compiled exactly once.

```json
{
  "schema": "nex.private-task-architecture/2",
  "mode": "mixed-fixed",
  "application": "app",
  "components": {
    "leaf": {"entry": "leaf::fail", "units": ["leaf/main.nex"],
             "exports": [], "dependencies": [], "linkage": "static"},
    "mid": {"entry": "mid::run", "units": ["mid/main.nex"],
            "exports": [], "dependencies": ["leaf"], "linkage": "shared"},
    "app": {"entry": "app::main", "units": ["app/main.nex"],
            "exports": [], "dependencies": ["mid"], "linkage": "application"}
  }
}
```

Here `leaf` remains its own source component/code archive. Its machine code
belongs to the `mid` shared image. The executable contains `app`. The reverse
composition, shared leaf under a static mid, places mid's code in the executable.

The checked `nex.private-task-modules/2` plan contains:

- `component_images`: the unique physical owner of every component.
- `definition_owners`: the physical owner of each emitted source function.
- `images`: each application/shared image's exact definitions, absorbed
  `static_components` and direct shared-image `dependencies`.
- `image_load_order`: providers before their dependent images.
- `runtime_linkage`: `shared` when any shared code image is loaded, otherwise
  `application`. There is one root executor and one runtime incarnation.

Static dependency walks stop at shared boundaries. A diamond that reaches one
static component twice within the same image is deduplicated. Reaching it from
two different loaded images is rejected before emission; its function values,
type/descriptor identity and owned resources cannot silently gain two physical
incarnations. A genuinely shared dependency should use `shared` linkage instead.
All-static and all-shared layouts are also expressible in the new explicit schema.

Each `nex.private-task-module/2` source record adds `linkage` and `machine_image`.
The same compiler/source/architecture validator rederives those fields. Changes
to a consumer body can preserve provider records and binaries when their checked
source surfaces and physical image ownership remain identical. Moving a component
to a different physical image changes its record and requires a new link result.

## Linking and execution

The conformance builder compiles each component separately and includes each
static archive in its unique owning image. It retains the whole selected code
component (`-force_load` on Mach-O, whole-archive on ELF), so otherwise uncalled
selected exports are available and the image inventory matches the plan. The
loader resolves shared dependencies once; all code images use the same ABI2502
and common runtime. No runtime is placed inside a static provider archive.
Fixed startup dependencies remain loaded even when a selected provider export
is uncalled (`-needed_library` on Mach-O, no-as-needed on ELF). Such an export's
filesystem support does not add filesystem configuration to an unrelated root.

Calls, callbacks, captured File/foreign values, scope/channel/future transport,
source throw/rethrow and runtime/control exits keep the existing checked module
semantics. The root still captures its actual reachable host requirements; image
support metadata does not create an operator configuration or resource owner.

`source_exception_frontiers` runs independent AST/TaskIR outcomes against actual
O0/O2 mixed images. It inventories final native step symbols, checks descriptor
and step addresses with the platform loader, counts loaded images and common
runtimes, and checks managed values, file descriptors and external finalizers.
The test host exports executable symbols for loader inspection; it does not add
direct application references to transitively loaded source interfaces.
It includes static/shared diamonds, original rethrow sites, source-absent runs,
provider reuse and relocated applications while original images/sources are absent.
These are ordinary functional checks. Security-specific checks remain user-deferred.

The plan/record alone does not establish an arbitrary binary's provenance.
Completed images still need exact target/link commands, inputs and artifact hashes.
This is a compiler-private source-backed API/probe workflow. Public build/project/
SDK selection, module HTTP/profile/logical
debugging, general binary-only checking, full platform delivery and explicit
history-preserving024-to025 migration remain pending. The broader original
language/toolchain/Studio/converter/platform/performance objective remains open.

Toolchain0.135.25 separately adds checked [consumer-owned specializations](source-exception-instances.md)
with architecture/3, retaining the architecture/2 behavior described above.
