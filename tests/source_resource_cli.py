"""Run source-resource conformance through ordinary public NEX commands.

Check, graph/FFI metadata, execution, building and client emission all use the
public CLI. The parent drivers keep a separate explicit021 probe for retained
negative checks; this adapter never executes it. Preserve all raw child results.
"""
import argparse
import hashlib
import json
import re
import copy
from pathlib import Path
import subprocess
import sys

def current_fixture_sources(document, language):
 """Author current test copies; never alter archived/private input bundles."""
 result=copy.deepcopy(document)
 if language!='0.25':return result
 signature=r'(?:[^{}!\n]|!\{[^{}]*\})*?'
 patterns=[r'\bfn\s+[A-Za-z_][A-Za-z_0-9]*\([^)]*\)->'+signature+r'!\{(?P<effects>[^{}]*)\}(?=\s*\{\s*(?:return\s+)?with_tasks\b)',
           r'\bfn\s+main\([^)]*\)->'+signature+r'!\{(?P<effects>[^{}]*)\}(?=\s*\{)',
           r'\bfn\([^)]*\btask_scope\)->'+signature+r'!\{(?P<effects>[^{}]*)\}(?=\s*\{)',
           r'\btask_spawn\([^,]*,\s*(?:server\s+|client\s+)?fn\([^)]*\)->'+signature+r'!\{(?P<effects>[^{}]*)\}(?=\s*\{)']
 for name,text in result['files'].items():
  for pattern in patterns:
   # Preserve comments and string contents, including function-like payloads.
   masked=re.sub(r'//[^\n]*|"(?:\\.|[^"\\])*"',lambda m:' '*len(m[0]),text)
   edits=[]
   for m in re.finditer(pattern,masked):
    effects={v.strip() for v in m['effects'].split(',')}
    if 'task' in effects and 'throw' not in effects:
     edits.append(m.end('effects'))
   for end in reversed(edits):text=text[:end]+',throw'+text[end:]
  result['files'][name]=text
 return result


def fixture_for_current_cli(path, directory, language):
 source=json.loads(path.read_text());authored=current_fixture_sources(source,language)
 destination=directory/'public-current-sources';destination.mkdir(exist_ok=True)
 output=destination/path.name;output.write_text(json.dumps(authored,ensure_ascii=False,indent=2)+'\n')
 record={'schema':'nex.test-source-authoring/1','selected_language':language,'unversioned_fixture_input':True,
         'original_bundle':str(path),'input_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
         'authored_bundle':str(output),'authored_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
         'archived_origin_modified':False}
 output.with_suffix(output.suffix+'.authoring.json').write_text(json.dumps(record,indent=2)+'\n')
 return output


def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--compiler',required=True,type=Path)
 parser.add_argument('action',choices=['check','reference','reference-timeout','native','web'])
 parser.add_argument('bundle',type=Path);parser.add_argument('root',type=Path);parser.add_argument('output');parser.add_argument('language',nargs='?',default='0.24')
 args=parser.parse_args();assert args.language in ('0.24','0.25');language=args.language
 compiler=args.compiler.resolve();bundle=args.bundle.resolve()
 source=json.loads(bundle.read_text());assert source['schema']=='nex.sources/1'
 project=args.root.resolve()/'public-cli-projects'/bundle.stem;project.mkdir(parents=True,exist_ok=True)
 for name,text in source['files'].items():
  relative=Path(name);assert not relative.is_absolute() and '..' not in relative.parts
  path=project/relative;path.parent.mkdir(parents=True,exist_ok=True);assert not path.is_symlink();path.write_text(text)
 (project/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':language,'entry':source['entry']}))
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
  graph=json.loads(graph_result.stdout);assert graph['revision']==checked_value['revision'] and graph['language']==language
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
  value={'ok':True,'language':language,'revision':graph['revision'],'resources':resources,'signatures':signatures,'public_cli_checked':True,'compiler_sha256':compiler_sha}
  if args.output!='-':Path(args.output).write_text(json.dumps(value)+'\n')
  return finish(checked,value)
 if args.action in ('reference','reference-timeout'):
  command=[compiler,'eval',entry,'--json']
  if args.output!='-':command+=['--foreign',Path(args.output).resolve()]
  if args.action=='reference-timeout':command+=['--task-timeout-ms','1000','--task-workers','1']
  result=run(command)
  if result.returncode:return finish(result)
  value=json.loads(result.stdout);value['output']=value['stdout'];value['language']=language;value['compiler_sha256']=compiler_sha
  if args.output!='-':value['external_capacity_after_scope']=value['foreign_resource_bytes_after_scope']
  return finish(result,value)
 if args.action=='native':
  return finish(run([compiler,'build',entry,'--profile','release','--build-directory',Path(args.output).resolve(),'--json']))
 return finish(run([compiler,'emit',entry,'--kind','typescript','--entry','client_value','--directory',Path(args.output).resolve(),'--json']))

if __name__=='__main__':raise SystemExit(main())
