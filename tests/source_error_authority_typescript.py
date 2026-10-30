#!/usr/bin/env python3
"""Real Node checks of keyed typed-outcome ownership and private metadata."""
import json, os, shutil, subprocess, tempfile
from pathlib import Path

root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='nex-source-authority-ts-') as scratch:
    output=Path(scratch)
    for name in ['nex-runtime.ts','nex-bytes.ts','nex-task-runtime.ts','nex-source-exception-runtime.ts']:
        shutil.copy2(root/'web'/name,output/name)
    shutil.copy2(root/'tests/source_error_authority_typescript.mjs',output/'test.mjs')
    result=subprocess.run([os.environ.get('NEX_NODE','node'),'--experimental-strip-types','--no-warnings',str(output/'test.mjs')],text=True,capture_output=True,timeout=120)
    if result.returncode:
        raise AssertionError((result.returncode,result.stdout,result.stderr))
    report=json.loads(result.stdout)
    assert report['ok'] and report['cases']>=35,report
    print(json.dumps(report))
