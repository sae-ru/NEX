# Source-operation edit walkthrough

Use a copied directory with `nex` on PATH. Check `nex describe --json` for
`operation` in `patch_entities`; older compilers support declaration patches.
The source prints 41. The following edit changes its offset and prints 42,
preserving the affine-step test and the archived original program.

```sh
nex check --json
nex operations --symbol operation_patch::adjust --limit 100 --json > operations.json
python3 - <<'PY'
import json
from pathlib import Path
page = json.loads(Path('operations.json').read_text())
node, = [n for n in page['nodes'] if n['kind'] == 'expression.integer'
         and n['definition']['number'] == '1']
assert node['source_range']['editable']
Path('patch.json').write_text(json.dumps({
    'expected_revision': page['revision'],
    'expected_source_hash': page['source_hash'],
    'replacements': [{'operation_id': node['id'], 'source': '2'}]
}))
PY
nex apply --patch patch.json --json
nex test --revision HEAD --json
nex test --revision HEAD --target web --json
nex run --revision HEAD --json
```

Query `nex context --operation ID --revision HASH --json` to inspect the selected
operation, ancestors and a bounded source preview. The context's revision and
source hash must identify the same archived snapshot. Never substitute the
diagnostic `location` for the complete `source_range`, and never invent IDs or
offsets. A truncated preview is not the complete replacement source.

An operation replacement contains one expression, one statement or one pattern.
Expression insertion preserves precedence; surrounding newlines isolate line
comments. Parameters and synthetic block/arm wrappers have no replaceable source
interval. Simple enum case nodes carry the full constructor pattern, while nested
and guarded cases expose separate pattern children. Generic instances and lifted closures are derived: edit the source
template or owner lambda. Change pattern bindings and their references together.
Non-overlapping declaration and operation edits may share a checked transaction.

The patch updates graph HEAD and retains history. Physical `main.nex` still
contains `+1`; ordinary file-based checks can synchronize that projection back
into HEAD. Validate with `--revision HEAD`, then export to a new directory to
materialize the revised project. Conflicting or invalid patches leave HEAD and
all graph rows unchanged. Behavior tests remain required after an accepted edit.
