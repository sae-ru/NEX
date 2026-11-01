"""Run the actual SDK migration gate early through a real compiler, without mocks."""
import argparse,hashlib,importlib.util,json,os,subprocess,time
from pathlib import Path

p=argparse.ArgumentParser();p.add_argument('compiler',type=Path);p.add_argument('--resources',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
compiler=a.compiler.resolve();resources=a.resources.resolve();root=a.output.resolve();root.mkdir();logs=root/'logs';logs.mkdir()
helper=Path(__file__).resolve().parents[1]/'tools/sdk_task_file_migration.py';spec=importlib.util.spec_from_file_location('checked_sdk_migration',helper);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'};env.pop('NEX_RESOURCE_DIR',None);env.pop('NEX_FILES_ROOT',None);env.pop('NEX_FILES_WRITE',None)
report={'schema':'nex.actual-sdk-migration-gate/1','ok':False,'commands':[],'compiler_sha256':hashlib.sha256(compiler.read_bytes()).hexdigest(),'helper_sha256':hashlib.sha256(helper.read_bytes()).hexdigest(),'compiled_source_path_hidden':False,'full_SDK_accepted':False,'full_objective_complete':False};start=time.monotonic()
def save():report['seconds']=round(time.monotonic()-start,3);(root/'report.json').write_text(json.dumps(report,indent=2)+'\n', newline="\n")
def cli(*args,cwd=None,expected_success=True,timeout=180):
 name='%03d'%len(report['commands']);command=[str(compiler),*map(str,args),'--json'];r=subprocess.run(command,cwd=cwd or root,env=env,capture_output=True,text=True,timeout=timeout)
 (logs/(name+'.stdout')).write_text(r.stdout, newline="\n");(logs/(name+'.stderr')).write_text(r.stderr, newline="\n");report['commands'].append({'command':command,'cwd':str(cwd or root),'exit_code':r.returncode,'expected_success':expected_success});save()
 assert (r.returncode==0) is expected_success,(name,r.returncode,r.stdout[-2500:],r.stderr[-2500:]);return json.loads(r.stdout)
try:
 report['evidence']=module.check_installed_task_migration(cli,root,resources)
 assert report['evidence']['language']=='0.24' and set(report['evidence']['stores'])=={'history','tasks'}
 assert hashlib.sha256(compiler.read_bytes()).hexdigest()==report['compiler_sha256']
 report.update(ok=True,state='passed')
except BaseException as e:report.update(state='failed',error=repr(e));raise
finally:save();print(json.dumps({k:report.get(k) for k in ['ok','state','seconds','error']}),flush=True)
