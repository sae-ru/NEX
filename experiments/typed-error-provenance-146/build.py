import hashlib,json,shlex,subprocess,time,os
from pathlib import Path
D=Path(__file__).resolve().parent;B=Path(os.environ.get('NEX_DRAFT_BASE_BUILD','/Users/sae/projects/NEX/build/native-026-errors'));W=Path(os.environ.get('NEX_DRAFT_SOURCE_ROOT',D.parents[1]));base=json.loads((D/'base.json').read_text());h=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def guard():
 for p,expected in base['immutable_145_inputs'].items():assert h(B/Path(p).name)==expected,p
guard();started=time.monotonic();commands=json.loads((B/'compile_commands.json').read_text());trace=[]
def run(label,args):
 r=subprocess.run(list(map(str,args)),cwd=B,text=True,capture_output=True);(D/(label+'.stdout')).write_text(r.stdout);(D/(label+'.stderr')).write_text(r.stderr);trace.append({'label':label,'exit_code':r.returncode});assert r.returncode==0,(label,r.stderr[-5000:])
objects=[]
for name in ['language','task_lifetime','source_errors','task_reference','probe']:
 original=W/('src/'+name+'.cpp' if name!='probe' else 'tests/task_lifetime_probe.cpp');row=next(r for r in commands if Path(r['file'])==original);args=shlex.split(row['command']);src=D/('src/'+name+'.cpp' if name!='probe' else 'tests/probe.cpp');obj=D/(name+'.o');args=[str(src) if a==str(original) else a for a in args];args[args.index('-o')+1]=str(obj);run('compile-'+name,args);objects.append(obj)
args=shlex.split((B/'CMakeFiles/nex_task_lifetime_probe.dir/link.txt').read_text());idx=next(i for i,a in enumerate(args) if a.endswith('tests/task_lifetime_probe.cpp.o'));args[idx:idx+1]=list(map(str,objects));args[args.index('-o')+1]=str(D/'probe');run('link',args);guard()
report={'ok':True,'scope':'isolated provenance and AST/TaskIR authority prototype','seconds':round(time.monotonic()-started,3),'base_commit':base['base_commit'],'frozen_145_inputs_unchanged':True,'commands':trace,'source_sha256':{str(p.relative_to(D)):h(p) for p in [*sorted((D/'src').glob('*.cpp')),D/'tests/probe.cpp']}}
(D/'build-report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
