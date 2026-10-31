"""Existing sequential and task exception fixtures through the shared lifetime model."""
import argparse,ast,hashlib,json,os,re,subprocess,tempfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('probe');p.add_argument('--output');a=p.parse_args()
source=Path(__file__).resolve().parents[1];probe=str(Path(a.probe).resolve());out=Path(a.output or os.environ.get('NEX_EXCEPTION_LIFETIME_OUTPUT') or tempfile.mkdtemp(prefix='nex-exception-lifetimes-')).resolve();out.mkdir(parents=True,exist_ok=True)
fixtures=[];origins={}
f=source/'tests/source_exception_native.py';tree=ast.parse(f.read_text());item=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='cases' for t in n.targets));fixtures += [('sequential-'+name,text) for name,text in ast.literal_eval(item.value)];origins[str(f.relative_to(source))]=hashlib.sha256(f.read_bytes()).hexdigest()
f=source/'tests/source_exception_tasks.cpp';fixtures += [('task-'+name,text) for kind,name,text in re.findall(r'\b(value|sourceError|trap)\("([^"]+)",R"\((.*?)\)"',f.read_text(),re.S) if name not in {'parent-budget','parent-cancellation'}];origins[str(f.relative_to(source))]=hashlib.sha256(f.read_bytes()).hexdigest()
f=source/'tests/source_exception_tasks_typescript.py';tree=ast.parse(f.read_text())
for n in tree.body:
 if isinstance(n,ast.AugAssign) and isinstance(n.target,ast.Name) and n.target.id=='fixtures':fixtures += [('task-'+item[1],item[2]) for item in ast.literal_eval(n.value)]
origins[str(f.relative_to(source))]=hashlib.sha256(f.read_bytes()).hexdigest();assert len(fixtures)==66,len(fixtures)
report={'ok':False,'cases':[],'fixtures':origins,'ordinary_functional_only':True,'security_checks_deferred_by_user':True,'full_region_inference':False}
def save():(out/'report.json').write_text(json.dumps(report,indent=2)+'\n', newline="\n")
save()
for name,text in fixtures:
 d=out/name;d.mkdir(exist_ok=True);(d/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.24','entry':'main.nex'}), newline="\n");f=d/'main.nex';f.write_text('module lifetime_compatibility;\n'+text+'\n', newline="\n")
 r=subprocess.run([probe,str(f)],text=True,capture_output=True,timeout=30);(d/'stdout.json').write_text(r.stdout, newline="\n");(d/'stderr.txt').write_text(r.stderr, newline="\n");assert r.returncode==0,(name,r.returncode,r.stdout,r.stderr)
 data=json.loads(r.stdout);assert data['steps']>0 and data['dynamic']>=0 and data['handlers']>=0
 report['cases'].append({'name':name,'source_sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'analysis':data,'passed':True});save()
report['ok']=True;report['source_programs']=len(report['cases']);save();print(json.dumps({'ok':True,'source_programs':len(report['cases']),'report':str(out/'report.json')}))
