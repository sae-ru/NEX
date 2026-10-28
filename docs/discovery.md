# Scoped compiler discovery

Toolchain0.87 adds readonly discovery projections. These are external tooling;
language0.16, canonical identities and graph history remain unchanged. Existing
`nex describe --json` and explicit `--kind full` return the complete existing
`nex.language/1` descriptor, including the additive `scoped_discovery` field.

```sh
nex describe --kind index --json
nex describe --field types --json
nex describe --field project_build.server_workload --json
nex describe --field source_concurrency.status --json
nex guide --kind bootstrap --json
```

The index returns `nex.discovery/1`, language/toolchain/compiler-build identity,
a hash of the complete descriptor, sorted top-level `fields` and lookup commands.
Select an indexed name or a dotted object path. The field response carries the
same envelope plus `field` and the exact untruncated `value` from the full
descriptor. Strings, numbers, booleans, objects, arrays and null retain their
JSON types. A field query neither adds support nor changes a pending capability
into an implemented one. The compiler build and descriptor hash bind the lookup;
neither is an authenticity signature.

Paths contain1..256 ASCII bytes and at most8 identifier components. Each component
starts with a letter or underscore; following characters may include digits.
Only object members can be traversed: there are no array indices, wildcards,
expressions, filesystem paths or graph reads. Unknown/malformed paths and
unsupported/mixed options fail with `E_OPTION`; there is no silent full-output
fallback. `--kind field --field PATH` is the explicit equivalent. `--kind index`
and `--kind full` cannot be combined with a field selection.

Discovery ignores physical project metadata, sources and Store contents. It
opens no graph and writes no files even inside an invalid/stale project. Plain
describe remains compatible; old SDKs may reject index/field options. For an old
SDK, inspect its full descriptor once instead of assuming new commands exist.

Use [BOOTSTRAP.md](../llm/BOOTSTRAP.md) as a short routing prompt, then follow the
model-independent workflow and applicable normative guides. Retrieve only
needed capability sections and graph contexts. Do not repaste the whole pack on
every turn. This reduces a discovery response's measured bytes; actual LLM
token/cost and task-success improvements require the [quality evaluation](quality.md).
