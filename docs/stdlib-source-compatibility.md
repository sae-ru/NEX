---
status: current
applies_to: "toolchain 0.281.0; language 0.30"
owner: repository
---

# Proposed 1.0 standard-library source contract

`nex.stdlib-public-api/1` names a proposed compatibility profile for NEX 0.30
programs that import the checked source modules listed by `nex describe --field
standard_library --json`. The 1.0 compatibility promise starts with the 1.0
release. The published 0.280.1 beta provides the baseline of **20 imports, 207
public functions and 35 public structures**. Each entry in the baseline records
the actual checked declaration. For example, the import `std/list.nex` resolves
to the logical module `std::lists`. [Machine-readable baseline](../llm/stdlib-public-api-0.280.1.json)

| A caller relies on | What later SDKs preserve |
| --- | --- |
| Module lookup | The import path and logical module name. |
| Public function calls | Qualified name, realm, positional parameter types and order, result type and declared effects. Callback types include their own parameters, results and permitted effects. |
| Generic calls and types | The number and order of type parameters, their constructor arities, bounds and any declared defaults. Repeated occurrences refer to the same parameter. |
| Nominal values | Qualified type name and ordered constructor fields, including each field's name and type. Existing callers may construct these values positionally and read fields by name. |

New modules and new declarations within existing modules are compatible.
For example, 0.281.0 adds `std/insertion_ordered_map.nex`. Changing a function
body or renaming a positional argument leaves its public signature intact.
Type and effect parameter names are local binders. In the baseline, `$0`, `$1`
and `?0` identify their positions within a declaration. A new field on an
existing structure changes its positional constructor.

The compatibility check imports the catalogued modules together in a fresh
0.30 project for each SDK. It compares the catalogue names with the checked
graph, then compares each original public declaration with its candidate
counterpart. The 0.280.1 catalogue contains functions and structures. Other
SDK modules such as `std/compute.nex` have separate platform and provider
contracts. Native ABI and runtime behavior outside the executed probes have
separate qualification. [Version boundaries](compatibility.md)

A reference and native consumer additionally checks the order of effectful
callbacks, sorting, collision handling and persistence, Java-style signed
32-bit wraparound, and Unicode splitting and joining. The change controls
compile a pair of programs with different function bodies, renamed type and
effect parameters and an added function. They also exercise incompatible
signature changes against the real baseline, including a changed callback
effect and reordered constructor fields.

On macOS ARM64, the installed 0.281.0 candidate retained all 207 functions
and 35 structures from the published 0.280.1 beta. Its catalogue contained
217 functions and 38 structures across 21 modules. Both SDKs executed the
behavior probe successfully. A separate local control used 0.281.0 as the
baseline and compared all 217 functions against a copy of that SDK.
[Observed versions, signatures and controls](evidence/stdlib-public-api-7f1b75ea-2026-11-23.json)

```sh
python3 -B tools/sdk_compat_stdlib.py --baseline /path/to/beta/bin/nex \
  --candidate /path/to/candidate/bin/nex --output build/stdlib-compatibility-run
```

Use the installed SDK from the selected baseline release and a new output
directory for each run. For 0.280.1 the full API must match the frozen
inventory exactly. For a later baseline, the check first verifies that it
retains the 0.280.1 API, then requires the candidate to preserve every public
declaration in the selected baseline, including additions made since 0.280.1.
The release workflow establishes publication from the delivery record and
archive digest. [Executable check](../tools/sdk_compat_stdlib.py)
