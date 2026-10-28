# Private consumer-owned template instances

Toolchain0.135.25 extends the private module APIs with architecture/3 and
module/3. Public language stays024; source generics, traits, associated types,
constructor parameters, effects and realms keep their checked meanings.
Read [modules](source-exception-modules.md) and
[mixed physical images](source-exception-frontiers.md) first. Earlier
architecture/1 and /2 keep their original uniform/mixed behavior.

## Discover and place checked instances

`describeSourceExceptionTaskInstances(program)` returns
`nex.private-task-instances/1`, `archived:false`, without a graph revision.
The developer probe accepts `instances PRIVATE_CONTEXT.json [TEMPLATE [OFFSET [LIMIT]]]`. Its catalogue
lists existing checked concrete generic functions, their canonical template/source
identities, concrete arguments/signatures and selected trait witnesses.
Use those exact names; a selector does not parse invented types or instantiate
an unchecked source program. Normal source calls/function references establish
the concrete instances before placement.
Results are sorted by concrete function name. The default limit is64 and the
maximum256. Prefer an exact template filter; use `total`, `next_offset` and
`truncated` for pagination. A page does not establish the absence of a later
instance. This keeps LLM context bounded without inventing another name format.

Architecture/3 adds a required `instantiations` array to every component:

```json
{
  "schema": "nex.private-task-architecture/3",
  "mode": "mixed-fixed",
  "application": "app",
  "components": {
    "leaf": {"entry": "leaf::anchor", "units": ["leaf/main.nex"],
      "exports": [], "dependencies": [], "linkage": "shared", "instantiations": []},
    "app": {"entry": "app::main", "units": ["app/main.nex"],
      "exports": [], "dependencies": ["leaf"], "linkage": "application",
      "instantiations": ["leaf::read<app::Number>"]}
  }
}
```

Here the public generic template originates in leaf, while app owns Number and
its Readable implementation. The read specialization is emitted in app and calls
its actual local method target. Leaf retains its own source and compiled anchor.
A library consumer may own the specialization instead of the application and
explicitly export it for an upstream caller. Its canonical name continues to
identify the original template; the physical owner comes from the checked plan.

External selected roots require public templates and direct source-component
dependencies. The compiler follows their checked generic helper instances,
selected local implementation targets and nested snapshot closures. Each concrete
definition has one machine component. Conflicting family owners are rejected.
A previously selected provider export remains an explicit binary boundary; a
consumer cannot silently take the same specialization away from that provider.
The component's entry remains locally sourced; it is not replaced by a template
borrowed from another source component.

## Private support and exact records

A public template may call a private ordinary helper in its original component.
The checked family can derive a `support_exports` descriptor there and a matching
`instantiation-support` import in the consumer. This is a machine interface for
that already checked template-body edge. It does not make the helper public in
NEX source or allow unrelated source imports. Private generic helpers and nested
closures in the selected family are emitted with the consumer. Arbitrary private
external templates cannot be selected as roots.

When two consumers need the same private helper specialization, its source
component may explicitly instantiate that local helper. The checked families
derive a support interface to the single origin-owned instance. This preserves
source privacy and one physical definition while avoiding an arbitrary first
consumer owner. Omitting an unambiguous owner for such conflicting families is
a diagnostic. Local private templates may be selected only by their own source
component; external roots still require public templates.

Module/3 records retain the actual `unit` origin and add separate
`source_component`/`machine_component` fields to definitions. They record explicit
`instantiation_roots`, derived `instantiation_families`, `template_instances`,
`trait_witnesses`, `instantiation_descriptors`, `support_exports` and `import_kinds`.
Witnesses bind the trait contract, selected implementation, concrete arguments,
actual target and signature. Explicit root descriptors retain requested instances
even when they are not source exports. Other components still need an explicitly
selected public export before using that binary specialization.

The modules/3 plan keeps the unique physical image ledger and adds
`specialization_owners`/`instantiation_roots`. Image definitions distinguish
source and machine components. A static consumer's instances live in its next
application/shared frontier. The entire checked project context remains required;
neither a standalone source record nor JSON shape verifies an arbitrary binary.
No public graph revision, source bundle or ABI3/4/5 provider is manufactured.

Changes to a method body or implementation binding invalidate the affected
consumer record. Binding changes also update the concrete witness/target metadata.
An unchanged template provider can retain its exact record/archive/shared image.
Its source context does not gain a back-import into the consumer. Static lifetime
analysis, native host requirements, owned cleanup, source throw/rethrow and the
separate runtime/control channel remain in force. All code uses private ABI2502
and one root runtime/executor.

## Verification and remaining work

`source_exception_instances` compares independent AST and TaskIR execution with
real static/shared O0/O2 images and their actual symbol/descriptor/step ownership.
Cases include associated types, constructor-trait generic methods, recursion,
captured generic callbacks, private support, multiple consumer types, exported
consumer instances, exact source errors, runtime traps, File futures/channels and
owned foreign resources. Pure programs also run through private TypeScript with
strict type checking. Ordinary rejected-source/contract tests preserve visibility,
effect/bound conformance and exact record derivation. Consumer-only rebuild and
relocation checks retain actual machine artifact hashes and run without original
sources/images. Security-specific checks remain user-deferred.

This remains an explicit compiler-private source-backed workflow. Automatic
placement policy, module HTTP/profile/logical debugging, public build/project/SDK
selection, general binary-only checking, complete inference and full platform
delivery remain pending. Public025 still requires explicit history-preserving
migration and complete delivery acceptance. Original language/toolchain/Studio/
converter/accelerator/platform/quality/performance/token goals remain open.
