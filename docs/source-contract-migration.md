# Graph migration to language0.28

This guide targets a compiler advertising ordinary language0.28. Discover the
selected compiler with `nex describe --kind index --json`; retained SDKs can
select an earlier language. Retained027 source is checked
under its original parser and `nex.program/15` identity before any028 candidate
is accepted. New028 programs use `nex.program/16`; unchanged text therefore gets
a different semantic revision. The task packet representation remains ABI7,
while028 native cohorts also bind the source version. Rebuild dependent native
libraries instead of relabelling their manifests.

From an existing archived project, inspect a read-only plan:

```sh
nex migrate --kind plan --json
# Explicit opt-in to the retained 0.29 development language:
nex migrate --language-version 0.29 --kind plan --json
```

`--language-version 0.29` targets the explicit 0.29 language (program/17);
without it the compiler's current default remains 0.28 (program/16). After applying
a 0.29 migration, update the project manifest to `"language":"0.29"`; 0.28 still
rejects 0.29-only partial type lambdas and higher-order kind signatures.

Check `origin_language`, `origin_verified`, `expected_revision`, `target_language`
and `target_valid`. Save the returned `candidate` object when source repairs or
new contract clauses are desired. Edit only its `sources`, retaining the origin,
source hash and target guards. A false/non-bool predicate or stale HEAD is refused
before a new graph revision is written.

For origins before0.18, the compiler does not retain their historical semantic
serializers. A plan can report `origin_verified: false` and `target_valid: true`:
the source is valid for the target, while its old semantic revision has not been
independently verified. Review the archived source and its trusted backup, and
exercise migration on a separate copy before updating an original store. Keep
the original graph; changing only a language field cannot establish its history.

Apply the checked candidate against the exact reviewed HEAD:

```sh
nex migrate --candidate reviewed-candidate.json --expected-revision OLD_HEAD_HASH --json
nex eval --revision HEAD --json
nex run --revision HEAD --profile release --json
```

For unchanged compatible source, omit `--candidate`. Migration retains original
revisions, table schema, identity namespace and local IDs. It changes the selected
HEAD and records the checked target. Original physical source, nex.json and locks
are not overwritten. Repeating a current migration does not add another revision.
Use an exported old graph JSON as the positional input when no original store
is available; verified modern origins must match their retained semantic hash.

Create a separate physical028 projection explicitly:

```sh
nex export --revision HEAD --directory ../project028 --json
```

Check and test that exported project before replacing an existing checkout.
Commit its `.nex` sources, nex.json, nex.build.json when present, tests and reviewed
nex.lock.json. `.nex/` is generated local graph/cache state; use `nex snapshot` and
`nex recover` for explicit portable graph backups when history/IDs must travel.
Changing only `language` to028 is not a migration. A recovered mixed027/028 graph
retains both histories; ordinary028 execution requires a028 selected revision.

Current installed SDK and platform acceptance remain separate gates. See
[source contracts](source-contracts.md) for exact runtime semantics.
