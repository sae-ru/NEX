#!/usr/bin/env python3
import argparse,hashlib,json,os,shutil,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--source-root',type=Path,required=True);p.add_argument('--base-build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--prepare-only',action='store_true');a=p.parse_args();here=Path(__file__).resolve().parent;W=a.source_root.resolve();B=a.base_build.resolve();O=a.output.resolve();base=json.loads((here/'base.json').read_text())
for name,wanted in json.loads((here/'manifest.json').read_text()).items():assert hashlib.sha256((here/name).read_bytes()).hexdigest()==wanted,name
subprocess.run(['git','diff','--quiet',base['base_commit'],'--','src','include','runtime','tests','web','CMakeLists.txt'],cwd=W,check=True)
for original,wanted in base['immutable_145_inputs'].items():assert hashlib.sha256((B/Path(original).name).read_bytes()).hexdigest()==wanted,original
O.mkdir(parents=True,exist_ok=False)
for name in ['language','source_errors','task_lifetime','task_reference']:
 target=O/'src'/(name+'.cpp');target.parent.mkdir(exist_ok=True);target.write_bytes(subprocess.check_output(['git','show',base['base_commit']+':src/'+name+'.cpp'],cwd=W))
subprocess.run(['/usr/bin/patch','-t','-p1','-i',str(here/'source.patch')],cwd=O,check=True)
for name in ['base.json','build.py','tests/probe.cpp','tests/check.py','tests/runtime_check.py','tests/bounded-types.nex']:
 target=O/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(here/name,target)
expected=json.loads((here/'results.json').read_text())['build']['source_sha256']
for name,wanted in expected.items():assert hashlib.sha256((O/name).read_bytes()).hexdigest()==wanted,name
if not a.prepare_only:
 env={**os.environ,'NEX_DRAFT_SOURCE_ROOT':str(W),'NEX_DRAFT_BASE_BUILD':str(B)}
 for script in ['build.py','tests/check.py','tests/runtime_check.py']:subprocess.run(['python3',str(O/script)],env=env,check=True)
print(json.dumps({'ok':True,'prepared':str(O),'compiled':not a.prepare_only,'public027_enabled':False}))
