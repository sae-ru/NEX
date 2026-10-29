"""Public025 streams and explicit retained023 authority/source boundaries."""
import argparse,hashlib,json,os,subprocess,tempfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('compiler',type=Path);p.add_argument('--retained-probe',type=Path,required=True);p.add_argument('--output',type=Path);a=p.parse_args()
compiler=a.compiler.resolve();temporary=None
if a.output:root=a.output.resolve();root.mkdir()
else:temporary=tempfile.TemporaryDirectory(prefix='nex stream boundaries ');root=Path(temporary.name).resolve()
(root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.26','entry':'main.nex'}));source=root/'main.nex';files=root/'files';files.mkdir();(files/'input').write_text('original')
env={**os.environ,'NEX_FILES_ROOT':str(files),'NEX_FILES_WRITE':'1','PYTHONDONTWRITEBYTECODE':'1'}
commands=[]
def cli(name,*args,expected=0):
 command=[str(compiler),*map(str,args),'--json'];r=subprocess.run(command,cwd=root,env=env,capture_output=True,text=True,timeout=180)
 (root/(name+'.stdout')).write_text(r.stdout);(root/(name+'.stderr')).write_text(r.stderr);commands.append({'name':name,'exit_code':r.returncode,'expected':expected});assert r.returncode==expected,(name,r.returncode,r.stdout,r.stderr);return json.loads(r.stdout)
try:
 descriptor=cli('describe','describe');assert descriptor['version']=='0.26'
 feature=descriptor['task_file_streams_host'];assert feature['source_support'] is True and feature['public_enabled'] is True and feature['typed_one_shot_open'] is True
 assert cli('guide','guide','--kind','task-file-streams')['language']=='0.26'
 for name,body,code in [
  ('open_read','server fn main()->unit !{task,fs}{let f:file=unwrap(file_open_read("input"));assert(file_close(f));}','E_TASK_UNIMPLEMENTED'),
  ('open_write','server fn main()->unit !{task,fs}{let f:file=unwrap(file_open_write("created"));assert(file_close(f));}','E_TASK_UNIMPLEMENTED'),
  ('capture','server fn main()->unit !{task,fs}{let f:file=unwrap(file_open_read("input"));with_tasks(1,server fn(s:task_scope)->unit !{task,fs}{let child:task<bytes>=task_spawn(s,server fn()->bytes !{task,fs}{return unwrap(file_read(f,3));});task_wait(child);});}','E_TASK_TYPE')]:
  current_body=body
  if name=='capture':current_body=body.replace('server fn main()->unit !{task,fs}', 'server fn main()->unit !{task,fs,throw}').replace('server fn(s:task_scope)->unit !{task,fs}', 'server fn(s:task_scope)->unit !{task,fs,throw}')
  source.write_text('module boundary;'+current_body);cli(name+'-current-build','build')
  assert not (files/'created').exists() and (files/'input').read_text()=='original'
  source.write_text('module boundary;'+body)
  command=[str(a.retained_probe.resolve()),'build',str(source),str(root/(name+'-retained-build')),'0.23']
  r=subprocess.run(command,cwd=root,env=env,capture_output=True,text=True,timeout=180)
  (root/(name+'-retained.stdout')).write_text(r.stdout);(root/(name+'-retained.stderr')).write_text(r.stderr)
  commands.append({'name':name+'-retained','argv':command,'exit_code':r.returncode,'expected':1})
  assert r.returncode==1 and json.loads(r.stdout)['code']==code,(name,r.stdout,r.stderr)
 source.write_text('module unused;server fn read(f:file)->bytes !{task,fs}{return unwrap(file_read(f,3));}fn main()->unit{}')
 cli('unreachable-retained','build')
 source.write_text('module ordinary;struct FileOpenLease{value:i64;}struct FileStreamLease{value:i64;}fn main()->unit !{io}{print(FileOpenLease(20).value+FileStreamLease(22).value);}')
 assert cli('private-names-reference','eval')['stdout']=='42\n' and cli('private-names-native','run')['stdout']=='42\n'
 source.write_text('module browser;server fn hidden()->file !{fs}{return unwrap(file_open_read("PRIVATE_STREAM_ROOT"));}client fn client_value()->i64{return 42;}')
 generated=root/'client';cli('client-pruning','emit','--kind','typescript','--entry','client_value','--directory',generated)
 emitted='\n'.join(p.read_text() for p in generated.rglob('*.ts'));assert emitted and 'PRIVATE_STREAM_ROOT' not in emitted and 'file_open_read' not in emitted
 print(json.dumps({'ok':True,'public025_builds':3,'retained023_rejections':3,'unreachable_retained_declaration':True,'private_names_not_reserved':True,'client_prunes_file_authority':True}))
finally:
 (root/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
