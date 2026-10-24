"""Run source-resource conformance through ordinary public NEX commands.

Check, graph/FFI metadata, execution, building and client emission all use the
public CLI. The parent drivers keep a separate explicit021 probe for retained
negative checks; this adapter never executes it. Preserve all raw child results.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--compiler',required=True,type=Path)
 parser.add_argument('action',choices=['check','reference','reference-timeout','native','web'])
 parser.add_argument('bundle',type=Path);parser.add_argument('root',type=Path);parser.add_argument('output');parser.add_argument('language',nargs='?',default='0.22')
 args=parser.parse_args();assert args.language=='0.22'
 compiler=args.compiler.resolve();bundle=args.bundle.resolve()
 source=json.loads(bundle.read_text());assert source['schema']=='nex.sources/1'
 project=args.root.resolve()/'public-cli-projects'/bundle.stem;project.mkdir(parents=True,exist_ok=True)
 for name,text in source['files'].items():
  relative=Path(name);assert not relative.is_absolute() and '..' not in relative.parts
  path=project/relative;path.parent.mkdir(parents=True,exist_ok=True);assert not path.is_symlink();path.write_text(text)
 (project/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.22','entry':source['entry']}))
 logs=project/'cli-evidence';logs.mkdir(exist_ok=True);compiler_sha=hashlib.sha256(compiler.read_bytes()).hexdigest()
 def run(command):
  stem=logs/('%03d'%(1+len(list(logs.glob('*.command.json')))))
  stem.with_suffix('.command.json').write_text(json.dumps({'argv':list(map(str,command)),'cwd':str(project),'compiler_sha256':compiler_sha},indent=2)+'\n')
  p=subprocess.run(list(map(str,command)),cwd=project,capture_output=True,text=True,timeout=240)
  stem.with_suffix('.stdout').write_text(p.stdout);stem.with_suffix('.stderr').write_text(p.stderr)
  stem.with_suffix('.process.json').write_text(json.dumps({'exit_code':p.returncode})+'\n')
  return p
 def finish(process,value=None):
  if process.stderr:sys.stderr.write(process.stderr)
  sys.stdout.write(json.dumps(value)+'\n' if value is not None else process.stdout)
  return process.returncode
 entry=source['entry']
 if args.action=='check':
  checked=run([compiler,'check',entry,'--json'])
  if checked.returncode:return finish(checked)
  checked_value=json.loads(checked.stdout);graph_result=run([compiler,'graph','--json'])
  if graph_result.returncode:return finish(graph_result)
  graph=json.loads(graph_result.stdout);assert graph['revision']==checked_value['revision'] and graph['language']=='0.22'
  signatures={};resources={}
  for node in graph['nodes']:
   foreign=node['definition'].get('foreign')
   if not foreign:continue
   result=run([compiler,'ffi','--symbol',node['name'],'--json'])
   if result.returncode:return finish(result)
   signature=json.loads(result.stdout);export=foreign['export']
   assert export not in signatures or signatures[export]==signature,'ambiguous conformance producer export'
   signatures[export]=signature
   for item in signature['types']:
    if item['kind']=='resource':resources[item['name']]={'name':item['name'],'identity':item['identity']}
  value={'ok':True,'language':'0.22','revision':graph['revision'],'resources':resources,'signatures':signatures,'public_cli_checked':True,'compiler_sha256':compiler_sha}
  if args.output!='-':Path(args.output).write_text(json.dumps(value)+'\n')
  return finish(checked,value)
 if args.action in ('reference','reference-timeout'):
  command=[compiler,'eval',entry,'--json']
  if args.output!='-':command+=['--foreign',Path(args.output).resolve()]
  if args.action=='reference-timeout':command+=['--task-timeout-ms','1000','--task-workers','1']
  result=run(command)
  if result.returncode:return finish(result)
  value=json.loads(result.stdout);value['output']=value['stdout'];value['language']='0.22';value['compiler_sha256']=compiler_sha
  if args.output!='-':value['external_capacity_after_scope']=value['foreign_resource_bytes_after_scope']
  return finish(result,value)
 if args.action=='native':
  return finish(run([compiler,'build',entry,'--profile','release','--build-directory',Path(args.output).resolve(),'--json']))
 return finish(run([compiler,'emit',entry,'--kind','typescript','--entry','client_value','--directory',Path(args.output).resolve(),'--json']))

if __name__=='__main__':raise SystemExit(main())
