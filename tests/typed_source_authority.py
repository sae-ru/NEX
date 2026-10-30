#!/usr/bin/env python3
"""Known exceptional escapes and bounded type joins through the real checker."""
import json, subprocess, sys, tempfile
from pathlib import Path

root=Path(__file__).resolve().parents[1]
probe=str(Path(sys.argv[1]).resolve())
rows=json.loads((root/'tests/fixtures/typed-error-authority-static.json').read_text())['cases']
with tempfile.TemporaryDirectory(prefix='nex-typed-authority-static-') as scratch:
    for row in rows:
        path=Path(scratch)/(row['name']+'.nex');path.write_text(row['source'])
        result=subprocess.run([probe,'check',str(path)],text=True,capture_output=True,timeout=30)
        if row['expected']=='accepted':
            assert result.returncode==0,(row['name'],result.stderr)
        else:
            assert result.returncode==1 and row['expected'] in result.stderr,(row['name'],result.returncode,result.stderr)
    result=subprocess.run([probe,'lifetime',str(root/'tests/fixtures/typed-error-authority-bounded.nex')],text=True,capture_output=True,timeout=30)
    assert result.returncode==0,result.stderr
    bounded=json.loads(result.stdout)
    assert 0<bounded['widenings'] and bounded['steps']<262144,bounded
    print(json.dumps({'ok':True,'cases':len(rows),'known_escapes_rejected':10,'bounded':bounded}))
