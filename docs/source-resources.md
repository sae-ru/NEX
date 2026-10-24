# Opaque source resources in language0.21

The0.124 development compiler adds opaque server resource declarations. Query
`nex describe --field source_resources --json` on the actual compiler. Full
delivery/platform acceptance is separate; the approved primary0.81 installation
remains a distinct language0.16 checkpoint.

```nex
module device_contract;
pub server resource Session;
pub server resource Buffer<T>;
pub server fn alive(value:Session)->bool !{ffi} {
  return resource_is_open(value);
}
pub server fn close(value:Session)->bool !{ffi} {
  return resource_close(value);
}
pub server fn forward<T>(value:Buffer<T>)->Buffer<T> { return value; }
```

`resource` is contextual at this declaration position. Ordinary module, record,
function, parameter, import-alias and generic-parameter names resource stay valid.
Resources have no source fields, source constructor or constructor pattern. Only
a granted typed external factory returns a genuine owner; a record, integer,
digest or matching display name cannot fabricate one. T:resource is not a bound;
use known types such as Buffer<T>. Normal generic/import/visibility rules apply.

Owners are immutable aliases. Server forwarding, aggregates, closure captures
and equality preserve identity. Close is shared: resource_close returns true for
the first logical close and false afterward; resource_is_open observes the same
state. Both operations require server realm and ffi. Pure forwarding grants no
native access. Already admitted borrows retain storage until actual call end;
new access after close/revocation fails. Object slots, declared capacity and code
pins return only after physical destruction.

Nested, phantom and captured owners cannot cross wire/JSON/API/storage, parallel
or structured-task transport. TypeScript rejects reachable resource authority;
unreachable server declarations/grants are absent from clients. Source task/FFI
completion, owned GPU/NPU sessions and thread-affine device cleanup remain pending.

## Native producer and operator grant

`nex ffi FILE --symbol QUALIFIED_FACTORY --json` exports the checked signature.
Its resource node has a bounded class name and exact semantic identity including
the declaration and complete checked generic argument context. Do not synthesize
it from a display name. The graph uses nex.resource/1; hash-named native classes
keep long/generic source names within the host128-byte bound.

Trusted producers negotiate NEX_FFI_V1_RESOURCE_SIZE and use resource_create,
resource_borrow, resource_close, resource_is_open and resource_identity. Creation
requires a result-reachable type token and callbacks in the actual pinned image.
Another image can forward an owner but cannot borrow its native payload merely
by matching metadata. Call tokens and borrowed pointers cannot survive the call
or enter an asynchronous job. See [the host contract](external-resources-design.md)
for exact transfer, cancellation, quota and destructor requirements.

The operator supplies a pinned catalogue through `nex eval/run/test --foreign
HOST.json`; standalone executables accept `--nex-foreign HOST.json`. Source adds
no ambient grant or OS root. resource_limit/resource_bytes bound declared objects
and retained capacity, not total process/vendor memory. Destructors must be
nonthrowing and settle synchronously on the final-release thread. Factory errors
and checked native traps clean transferred owners before exit70; forced termination
is outside normal cleanup guarantees.

## Graph, editing and debugging

Resources retain graph identity kind type, with nex.resource/1 definitions.
Use `nex context --entity type --symbol MODULE::Session` and ordinary kind:type
declaration patches. Generic instances are derived; patch the source template.
Complete candidate checking precedes saving, and physical files change only on
explicit export. Analysis/1/2/3 and LSP expose kind resource and exact name tokens,
including `server resource resource;`. Watch input reconstruction rejects resource
authority with E_DEBUG_UNAVAILABLE; diagnostic identities grant no access.
The matching native LLDB/DAP gate checks opaque alias IDs, archived source,
ordinary pure watches, resource watch refusal, stale references and cleanup.
DAP runtime arguments use launch.args; raw LLDB CLI installs its own run-args
command once. Optimized/core resource contexts and device profiling remain separate.

## Explicit0.20 to0.21 migration

Keep the old SDK, graph snapshot and physical files. A version edit does not
migrate a project. From its existing root:

```sh
/path/to/sdk123/bin/nex migrate --expected-revision OLD_HEAD --json
/path/to/sdk123/bin/nex test --revision HEAD --json
/path/to/sdk123/bin/nex test --revision HEAD --target web --json
/path/to/sdk123/bin/nex export --revision HEAD --directory ../project021 --json
```

Migration verifies retained018/019/020/021 origins with their original parser,
then checks the target before opening a writable Store. The new hash includes021.
Historical rows, IDs, schema and namespace remain; HEAD advances transactionally.
Old physical metadata/source stay unchanged, so use --revision HEAD until export.
Retain matching SDKs for original artifacts and regenerate task/proof pins through
their reviewed workflow; old receipts are never relabeled.

Ordinary020 declarations named resource_close/resource_is_open conflict with the
new intrinsics. Retain the original graph, prepare a separate reviewed candidate
with token-level declaration/reference renames, and preserve comments/strings.
Update root source and bundle.files consistently, retaining original revision and
language fields. Run `nex migrate reviewed-candidate.graph.json` in the store
containing the unchanged verified original. Candidate sources get a new hash;
altered sources cannot authenticate an old hash without its retained original.

The maintained migration gate uses five genuine SDK122 histories/fifteen revisions
and all16 tables. It checks reviewed conflicts, stale/corrupt origins, idempotence,
native/reference/TypeScript execution, export and stable IDs through type patches.
