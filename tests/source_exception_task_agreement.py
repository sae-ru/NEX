"""Independent AST scheduler vs ordinary interpreter using exact native/TS fixtures."""
import argparse,ast,hashlib,json,os,subprocess,tempfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('tasks');p.add_argument('sequential');p.add_argument('--output');a=p.parse_args()
source=Path(__file__).resolve().parents[1];tasks=str(Path(a.tasks).resolve());sequential=str(Path(a.sequential).resolve())
out=Path(a.output or os.environ.get('NEX_EXCEPTION_TASK_AGREEMENT_OUTPUT') or tempfile.mkdtemp(prefix='nex-task-exception-agreement-')).resolve();out.mkdir(parents=True,exist_ok=True)
fixture=source/'tests/source_exception_native.py';tree=ast.parse(fixture.read_text());item=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='cases' for t in n.targets));cases=ast.literal_eval(item.value)
report={'ok':False,'cases':[],'shared_native_TS_fixture_sha256':hashlib.sha256(fixture.read_bytes()).hexdigest(),'public_language':'0.24','private_identity':'0.25-prototype','ordinary_functional_only':True,'security_checks_deferred_by_user':True}
def save():(out/'report.json').write_text(json.dumps(report,indent=2)+'\n', newline="\n")
def run(cmd):
 r=subprocess.run(cmd,text=True,capture_output=True,timeout=30)
 assert r.returncode==0,(cmd,r.returncode,r.stdout,r.stderr)
 return json.loads(r.stdout)
save()
for name,text in cases:
 d=out/name;d.mkdir(exist_ok=True);(d/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.24','entry':'main.nex'}), newline="\n");f=d/'main.nex';f.write_text('module native_exception;\n'+text.replace('\\\\u','\\u')+'\n', newline="\n")
 ordinary=run([sequential,'reference',str(f)]);actual=run([tasks,str(f)])
 (d/'sequential.json').write_text(json.dumps(ordinary,indent=2)+'\n', newline="\n");(d/'tasks.json').write_text(json.dumps(actual,indent=2)+'\n', newline="\n")
 assert actual==ordinary,(name,actual,ordinary)
 report['cases'].append({'name':name,'kind':actual['kind'],'source_sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'passed':True});save()
report['ok']=True;report['comparisons']=len(report['cases']);save();print(json.dumps({'ok':True,'comparisons':report['comparisons'],'report':str(out/'report.json')}))
