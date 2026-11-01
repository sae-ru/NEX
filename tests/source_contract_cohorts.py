"""Exact source-version binding for real027/028 native task archives."""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,tempfile,time
p=argparse.ArgumentParser();p.add_argument('project_probe');p.add_argument('native_probe');p.add_argument('--output',type=Path);a=p.parse_args()
root=Path(__file__).resolve().parents[1];project_probe=str(Path(a.project_probe).resolve());native_probe=str(Path(a.native_probe).resolve())
out=a.output.resolve() if a.output else Path(tempfile.mkdtemp(prefix='nex-contract-cohorts-'));out.mkdir(parents=True,exist_ok=a.output is None)
env={**os.environ,'NEX_RESOURCE_DIR':str(root),'PYTHONDONTWRITEBYTECODE':'1'}
report={'schema':'nex.source-contract-cohort-checks/1','ok':False,'commands':[],'cases':[]};started=time.monotonic()
def save():
 report['seconds']=round(time.monotonic()-started,3);(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
def run(label,command,allowed=(0,)):
 r=subprocess.run(list(map(str,command)),text=True,capture_output=True,env=env,timeout=300)
 (out/(label+'.stdout')).write_text(r.stdout);(out/(label+'.stderr')).write_text(r.stderr)
 report['commands'].append({'label':label,'exit_code':r.returncode});save()
 assert r.returncode in allowed,(label,r.returncode,r.stdout[-3000:],r.stderr[-4000:])
 return r
save();built={}
for language in ['0.27','0.28']:
 d=out/language;d.mkdir();(d/'leaf').mkdir();(d/'app').mkdir()
 (d/'leaf/main.nex').write_text('module leaf;\npub fn work(value:i64)->i64 !{task}{task_yield();return value;}\n')
 (d/'app/main.nex').write_text('module app;\nimport "../leaf/main.nex" as leaf;\nfn main()->unit !{task,io}{print(leaf::work(42));}\n')
 (d/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':language,'entry':'app/main.nex'})+'\n')
 manifest={'schema':'nex.project-build/1','default_configuration':'debug','configurations':{'debug':{'profile':'debug'}},'components':{
 'leaf':{'kind':'static_library','root':'leaf','entry':'leaf/main.nex','entry_function':'work','exports':['work']},
 'app':{'kind':'executable','root':'app','entry':'app/main.nex','dependencies':{'leaf':'static'}}}}
 (d/'nex.build.json').write_text(json.dumps(manifest,indent=2)+'\n')
 req=out/(language+'.request.json');req.write_text(json.dumps({'root':str(d),'action':'run','component':'app','source_language':language})+'\n')
 v=json.loads(run(language+'-project',[project_probe,req]).stdout)
 assert v['observation']['exit_code']==0 and v['observation']['stdout']=='42\n' and not v['observation']['stderr']
 leaf=next(x for x in v['artifacts'] if x.get('component')=='leaf' or x.get('name')=='leaf')
 archive=Path(leaf['artifact']);provider=archive.parent/'task-provider.json';record=json.loads(provider.read_text())
 assert record['language']==language and record['descriptor_abi']==0x4e45585400000007
 built[language]={'root':d,'archive':archive,'provider':provider,'record':record,'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest()}
 report['cases'].append({'language':language,'actual_archive_built':True,'actual_application_executed':True});save()
old=built['0.27'];new=built['0.28']
assert old['record']['cohort']!=new['record']['cohort'],'028 reused027 native cohort'
d=new['root'];source=d/'app/main.nex'
r=run('027-import-refused',[native_probe,'cohort-import',source,out/'wrong-version-build',old['archive'],d,old['provider']],allowed=(1,))
assert 'E_TASK_PROVIDER' in r.stderr,r.stderr
retagged=out/'retagged-provider.json';record=dict(old['record'],language='0.28');retagged.write_text(json.dumps(record)+'\n')
r=run('relabelled027-import-refused',[native_probe,'cohort-import',source,out/'wrong-cohort-build',old['archive'],d,retagged],allowed=(1,))
assert 'E_PROJECT_ABI' in r.stderr,r.stderr
accepted=json.loads(run('matching028-import',[native_probe,'cohort-import',source,out/'matching-build',new['archive'],d,new['provider']]).stdout)
assert accepted['language']=='0.28' and accepted['library_abi']==new['record']['cohort']
r=run('matching028-execute',[accepted['artifact']]);assert r.stdout=='42\n' and not r.stderr
for item in built.values():assert hashlib.sha256(item['archive'].read_bytes()).hexdigest()==item['archive_sha256']
report.update(ok=True,different_source_cohorts=True,old_version_refused=True,relabelled_old_cohort_refused=True,matching028_executed=True,input_archives_unchanged=True);save()
print(json.dumps({'ok':True,'report':str(out/'report.json')}))
