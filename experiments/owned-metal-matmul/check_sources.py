"""Check all exact Metal Matmul hardware/reply source fixtures with no device or native build."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--sdk',required=True,type=Path);parser.add_argument('--project',required=True,type=Path);parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
 sdk=args.sdk.resolve(strict=True);project=args.project.resolve(strict=True);out=args.output.absolute();out.mkdir(parents=True,exist_ok=False)
 compiler=sdk/'bin'/('nex.exe' if os.name=='nt' else 'nex');source=Path(__file__).parent
 preparation=json.loads((project/'preparation/report.json').read_bytes());language=json.loads((project/'nex.json').read_bytes())['language']
 if not preparation['source_checked'] or preparation['source_language']!=language or preparation['compiler_sha256']!=sha(compiler):raise RuntimeError('prepared Metal source does not match the selected compiler')
 verify=load('owned_metal_source_fixtures',source/'verify.py');faults=load('owned_metal_source_faults',source/'faults.py')
 template=(project/'main.nex').read_text();prefix=template[:template.index('server fn main()->unit')]+verify.HELPERS
 env={**os.environ,'NEX_RESOURCE_DIR':str(sdk/'share/nex'),'PYTHONDONTWRITEBYTECODE':'1'}
 started=time.monotonic();report={'schema':'nex.owned-metal-matmul-source-check/1','ok':False,'source_language':language,'compiler_sha256':sha(compiler),'checks':[],
  'fixture_sha256':{name:sha(source/name) for name in ['verify.py','faults.py','main.nex.in']},'native_provider_built':False,'driver_initialized':False,'hardware_executed':False}
 def save():report['seconds']=time.monotonic()-started;(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 def check(name,body,expected,code=None):
  directory=out/name;directory.mkdir();(directory/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':language,'entry':'main.nex','libraries':{'std':str(project/'stdlib')}})+'\n')
  (directory/'main.nex').write_text(body)
  argv=[str(compiler),'check','--json'];p=subprocess.run(argv,cwd=directory,env=env,capture_output=True,text=True,timeout=120)
  (directory/'check.stdout').write_text(p.stdout);(directory/'check.stderr').write_text(p.stderr);result=json.loads(p.stdout)
  report['checks'].append({'name':name,'argv':argv,'exit_code':p.returncode,'diagnostic':result.get('code'),'source_sha256':sha(directory/'main.nex')});save()
  if p.returncode!=expected or (code is not None and result.get('code')!=code):raise RuntimeError('Metal fixture check failed: '+name+' '+p.stdout[-2000:])
 try:
  for group,cases in [('normal',verify.CASES),('error',verify.ERROR_CASES),('fault',faults.CASES)]:
   for name,case in cases.items():check(group+'-'+name,verify.source_program(prefix,case[0],language),0)
  check('missing-source-error-effect',prefix+'\nserver fn main()->unit !{task,ffi,io}{'+verify.CASES['hidden_session_after_scope_return'][0]+'print(42);}\n',1,'E_EFFECT')
  assert len(report['checks'])==53 and sha(compiler)==report['compiler_sha256']
  assert all(sha(source/name)==pin for name,pin in report['fixture_sha256'].items())
  report.update(ok=True,state='passed',accepted_programs=52,rejected_programs=1)
 except BaseException as error:report.update(state='failed',error=repr(error));raise
 finally:save()
 print(json.dumps({'ok':report['ok'],'accepted_programs':52,'rejected_programs':1,'hardware_executed':False}))
if __name__=='__main__':main()
