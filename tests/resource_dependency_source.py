"""Real C11/C++20 dependent resources through public native and AST commands."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
DECLARATIONS={
 'session':('value:i64','Session'),'buffer':('parent:Session,mode:i64','Buffer'),
 'extend':('parent:Buffer,mode:i64','Buffer'),'read':('owner:Buffer','i64'),
 'status':('owner:Session','i64'),'stale':('owner:Buffer','Buffer'),
 'try_buffer':('parent:Session,mode:i64','result<Buffer>'),
 'try_session':('value:i64','result<Session>'),
 'hold':('owner:Buffer','i64'),'started':('value:i64','i64'),
}
CASES={
 'closed_parent_rejected_before_factory':('''let p:Session=session(0);let failed:result<Buffer>=try_buffer(p,16);
 assert(!is_ok(failed));assert(error_code(failed)=="CLOSED");assert(status(p)==13);''',1,0),
 'closed_parent_storage':('''let p:Session=session(0);let b:Buffer=buffer(p,0);
 assert(resource_close(p));assert(status(p)==13);assert(read(b)==42);assert(resource_close(b));''',1,1),
 'shared_parent_two_children':('''let p:Session=session(0);let a:Buffer=buffer(p,0);let b:Buffer=buffer(p,0);
 assert(resource_close(p));assert(resource_close(a));assert(read(b)==42);assert(resource_close(b));''',1,2),
 'duplicate_parent_aliases':('''let p:Session=session(0);let b:Buffer=buffer(p,4);
 assert(resource_close(p));assert(read(b)==42);assert(resource_close(b));''',1,1),
 'close_during_admitted_factory':('''let p:Session=session(0);let b:Buffer=buffer(p,1);
 assert(!resource_is_open(p));assert(read(b)==42);assert(resource_close(b));''',1,1),
 'hidden_parent_scope_return':('''let b:Buffer=with_tasks(1,server fn(s:task_scope)->Buffer !{task,ffi}{
 let p:Session=session(0);return buffer(p,0);});assert(read(b)==42);assert(resource_close(b));''',1,1),
 'hidden_parent_future_result':('''let b:Buffer=with_tasks(1,server fn(s:task_scope)->Buffer !{task,ffi}{
 let t:task<Buffer>=task_spawn(s,server fn()->Buffer !{task,ffi}{let p:Session=session(0);return buffer(p,0);});return task_wait(t);
 });assert(read(b)==42);assert(resource_close(b));''',1,1),
 'hidden_parent_sibling_channel':('''let b:Buffer=with_tasks(1,server fn(s:task_scope)->Buffer !{task,ffi}{
 let ch:channel<Buffer>=channel_new<Buffer>(s,0);
 let producer:task<bool>=task_spawn(s,server fn()->bool !{task,ffi}{let p:Session=session(0);return task_send(ch,buffer(p,0));});
 let consumer:task<Buffer>=task_spawn(s,server fn()->Buffer !{task,ffi}{return unwrap(task_recv(ch));});
 let got:Buffer=task_wait(consumer);assert(task_wait(producer));return got;
 });assert(read(b)==42);assert(resource_close(b));''',1,1),
 'transitive_hidden_parents':('''let b:Buffer=with_tasks(1,server fn(s:task_scope)->Buffer !{task,ffi}{
 let p:Session=session(0);let a:Buffer=buffer(p,0);let b:Buffer=extend(a,0);
 assert(resource_close(p));assert(resource_close(a));return b;
 });assert(read(b)==42);assert(resource_close(b));''',1,2),
 'dependent_closure_return':('''let f:server fn()->i64 !{task,ffi}=with_tasks(1,server fn(s:task_scope)->server fn()->i64 !{task,ffi} !{task,ffi}{
 let p:Session=session(0);let b:Buffer=buffer(p,0);return server fn()->i64 !{task,ffi}{task_yield();return read(b);};
 });assert(f()==42);''',1,1),
 'C_argument_thread_and_stale_tokens':('''let p:Session=session(0);var mode:i64=10;
 while mode<=15{let b:Buffer=buffer(p,mode);assert(read(b)==42);assert(resource_close(b));mode=mode+1;}
 let b:Buffer=buffer(p,0);let a:Buffer=stale(b);let c:Buffer=stale(a);assert(read(c)==42);
 assert(resource_close(p));assert(resource_close(c));''',1,7),
 'failed_factory_rolls_back':('''let p:Session=session(0);let failed:result<Buffer>=try_buffer(p,2);
 assert(!is_ok(failed));assert(error_code(failed)=="QUOTA");let b:Buffer=buffer(p,0);
 assert(resource_close(p));assert(read(b)==42);assert(resource_close(b));''',1,2),
 'closed_parent_keeps_physical_quota':('''let p:Session=session(0);let b:Buffer=buffer(p,0);assert(resource_close(p));
 let failed:result<Session>=try_session(0);assert(!is_ok(failed));assert(error_code(failed)=="QUOTA");
 assert(read(b)==42);assert(resource_close(b));var next:result<Session>=try_session(0);
 while !is_ok(next){task_yield();next=try_session(0);}let p2:Session=unwrap(next);assert(resource_close(p2));''',2,1),
}

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n', newline="\n")
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
from source_resource_cli import fixture_for_current_cli

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--compiler',type=Path,required=True);parser.add_argument('--output',type=Path);args=parser.parse_args()
 compiler=args.compiler.resolve();destination=args.output or os.environ.get('NEX_DEPENDENT_RESOURCE_EVIDENCE')
 temporary=None
 if destination:out=Path(destination).resolve();out.mkdir(parents=True)
 else:temporary=tempfile.TemporaryDirectory(prefix='nex dependent resources ');out=Path(temporary.name)
 env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'};started=time.monotonic()
 language=json.loads(subprocess.check_output([str(compiler),'describe','--kind','index','--json'],text=True))['language']
 doctor=json.loads(subprocess.check_output([str(compiler),'doctor','--json'],env=env,text=True))
 sys.path.insert(0,str(ROOT/'tools'))
 from sdk_host import compile_fixture
 report={'schema':'nex.dependent-resource-source/1','ok':False,'commands':[],'checks':[],
  'compiler_sha256':sha(compiler),'language':language,'actual_GPU_NPU_resources':False}
 def save():report['seconds']=round(time.monotonic()-started,3);write(out/'report.json',report)
 def run(label,argv,expected=0,marker=None,cwd=out):
  row={'label':label,'argv':list(map(str,argv)),'cwd':str(cwd)};report['commands'].append(row);save()
  p=compile_fixture(row['argv'],doctor=doctor,cwd=cwd,env={**env,'NEX_DEPENDENCY_MARKER':str(marker or out/(label+'.events'))},capture_output=True,text=True,timeout=240)
  (out/(label+'.stdout')).write_text(p.stdout, newline="\n");(out/(label+'.stderr')).write_text(p.stderr, newline="\n");row['exit_code']=p.returncode;save()
  assert p.returncode==expected,(label,p.returncode,p.stdout[-2500:],p.stderr[-2500:]);return p
 def source(pin,body):
  lines=['module dependencies;server resource Session;server resource Buffer;client fn client_value()->i64{return 42;}']
  for name,(parameters,result) in DECLARATIONS.items():lines.append('server extern fn '+name+'('+parameters+')->'+result+' !{ffi}=foreign("test","'+name+'","'+pin+'");')
  return '\n'.join(lines)+'\nserver fn main()->unit !{task,ffi,io}{'+body+'\nprint(42);}\n'
 def bundle(label,body,pin='0'*64):
  p=out/(label+'.json');write(p,{'schema':'nex.sources/1','entry':'main.nex','files':{'main.nex':source(pin,body)}});return p
 def command(action,path,output='-'):
  authored=fixture_for_current_cli(path,out,language)
  return [sys.executable,ROOT/'tests/source_resource_cli.py','--compiler',compiler,action,authored,out,output,language]
 try:
  template=bundle('signatures',CASES['closed_parent_storage'][0]);api=json.loads(run('signatures',command('check',template)).stdout)
  signatures=api['signatures'];assert set(signatures)==set(DECLARATIONS)
  for dialect,driver,standard in [('C11','clang','c11'),('CPP20','clang++','c++20')]:
   directory=out/dialect;directory.mkdir();header=directory/'dependent-signatures.h'
   header.write_text('\n'.join('#define PIN_'+name.upper()+' "'+digest(sig)+'"' for name,sig in signatures.items())+'\n', newline="\n")
   image=directory/'module.so'
   selected=Path(doctor['native_compiler'])
   if dialect=='C11':selected=selected.with_name('clang.exe' if os.name=='nt' else 'clang')
   driver=os.environ.get('NEX_DEPENDENCY_CC' if dialect=='C11' else 'NEX_DEPENDENCY_CXX',str(selected))
   run(dialect+'-compile',[driver,'-x','c' if dialect=='C11' else 'c++','-std='+standard,'-shared','-fPIC','-pthread','-I'+str(ROOT/'runtime'),'-I'+str(directory),ROOT/'tests/dependent_resource_module.c','-o',image])
   (directory/'NOTICE').write_text('NEX dependent resource conformance producer\n', newline="\n")
   manifest={'schema':'nex.foreign-bundle/1','platform':('windows' if os.name=='nt' else 'macos' if platform.system()=='Darwin' else 'linux')+'-'+('arm64' if platform.machine() in ('aarch64','arm64') else 'x86_64'),
    'entry':image.name,'files':[{'path':n,'sha256':sha(directory/n)} for n in (image.name,'NOTICE')],
    'exports':{name:digest(sig) for name,sig in signatures.items()},'notices':['NOTICE']}
   write(directory/'manifest.json',manifest);pin=sha(directory/'manifest.json')
   host=directory/'host.json';policy={'schema':'nex.foreign-host/1','module_limit':1,'resource_limit':16,'resource_bytes':1024,
    'libraries':{'test':{'directory':str(directory),'manifest_sha256':pin,'exports':list(signatures)}}};write(host,policy)
   quota=directory/'quota.json';write(quota,{**policy,'resource_limit':2,'resource_bytes':48})
   for name,(body,roots,children) in CASES.items():
    label=dialect+'-'+name;path=bundle(label,body,pin);configuration=quota if name=='closed_parent_keeps_physical_quota' else host
    ref=run(label+'-reference',command('reference',path,configuration));value=json.loads(ref.stdout)
    assert value['output']=='42\n' and value['external_capacity_after_scope']==0,value
    built=json.loads(run(label+'-build',command('native',path,directory/'native')).stdout)
    run(label+'-native',[built['executable'],'--nex-foreign',configuration,'--nex-task-workers','1'])
    assert (out/(label+'-native.stdout')).read_text()=='42\n'
    for mode in ['reference','native']:
     events=(out/(label+'-'+mode+'.events')).read_text()
     assert events.startswith('I') and events.endswith('D') and '!' not in events,(label,mode,events)
     assert events.count('A')==events.count('P')==roots and events.count('B')==events.count('C')==children,(label,mode,events)
     if roots==1:assert events.rfind('C')<events.index('P'),(label,mode,events)
    report['checks'].append({'dialect':dialect,'case':name,'native_and_independent_AST':True,'physical_scope_capacity_zero':True});save()
   for name,body,code,children in [('checked_exit','let p:Session=session(0);let b:Buffer=buffer(p,0);assert(false);','E_ASSERT',1),
     ('cancel_admitted_child','with_tasks(1,server fn(s:task_scope)->unit !{task,ffi}{let child:task<unit>=task_spawn(s,server fn()->unit !{task,ffi}{let p:Session=session(0);let b:Buffer=buffer(p,0);let answer:i64=hold(b);});while started(0)==0{task_yield();}assert(task_cancel(child));task_wait(child);});','E_CANCELLED',1),
     ('deadline_admitted_child','let p:Session=session(0);let b:Buffer=buffer(p,0);let answer:i64=hold(b);','E_TIMEOUT',1),
     *([('throwing_factory','let p:Session=session(0);let b:Buffer=buffer(p,3);','E_FFI',1)] if dialect=='CPP20' else [])]:
    label=dialect+'-'+name;path=bundle(label,body,pin)
    rejected=json.loads(run(label+'-reference',command('reference-timeout' if name=='deadline_admitted_child' else 'reference',path,host),1).stdout);assert rejected['code']==code,rejected
    built=json.loads(run(label+'-build',command('native',path,directory/'native')).stdout)
    failed=run(label+'-native',[built['executable'],'--nex-foreign',host,'--nex-task-workers','1',*(['--nex-task-timeout-ms','1000'] if name=='deadline_admitted_child' else [])],70);assert code in failed.stderr
    for mode in ['reference','native']:
     events=(out/(label+'-'+mode+'.events')).read_text();assert events.count('P')==1 and events.count('C')==children and events.rfind('C')<events.index('P') and events.endswith('D') and '!' not in events,events
     if name in ('cancel_admitted_child','deadline_admitted_child'):assert events.index('H')<events.index('Q')<events.index('C'),events
    report['checks'].append({'dialect':dialect,'case':name,'native_and_independent_AST':True,'checked_cleanup':True});save()
   path=bundle(dialect+'-replay',CASES['hidden_parent_scope_return'][0],pin)
   built=json.loads(run(dialect+'-replay-build',command('native',path,directory/'native')).stdout)
   project=out/'public-cli-projects'/path.stem;(project/'main.nex').unlink()
   replay=run(dialect+'-source-deleted-replay',[compiler,'run','--revision',built['revision'],'--profile','release','--foreign',host,'--json'],cwd=project)
   assert json.loads(replay.stdout)['stdout']=='42\n'
   web=directory/'web';run(dialect+'-client',command('web',bundle(dialect+'-client',CASES['hidden_parent_future_result'][0],pin),web))
   emitted='\n'.join(p.read_text() for p in web.rglob('*.ts'));assert 'client_value' in emitted and pin not in emitted and 'dependencies::Session' not in emitted and 'resource_create_with_parents' not in emitted
   report['checks'].append({'dialect':dialect,'source_deleted_replay':True,'client_reachability':True});save()
   legacy=directory/'legacy-prefix';legacy.mkdir()
   fixture=ROOT/'tests/fixtures/ffi-resource-prefix-0.130/nex_ffi.h'
   assert sha(fixture)=='5fb36a07bbe06e7a51dd94047ddfbfc55989760995234ea2718de13d5d368c3f'
   def legacy_source(pin):
    text='module legacy;server resource Session;'
    for name,parameters,result in [('legacy_session','value:i64','Session'),('legacy_read','owner:Session','i64'),('legacy_size','value:i64','i64')]:
     text+='server extern fn '+name+'('+parameters+')->'+result+' !{ffi}=foreign("test","'+name+'","'+pin+'");'
    return text+'server fn main()->unit !{task,ffi,io}{assert(legacy_size(0)==296);let p:Session=legacy_session(0);assert(legacy_read(p)==42);assert(resource_close(p));print(42);}'
   legacy_bundle=out/(dialect+'-legacy-signature.json');write(legacy_bundle,{'schema':'nex.sources/1','entry':'main.nex','files':{'main.nex':legacy_source('0'*64)}})
   old_signatures=json.loads(run(dialect+'-legacy-signatures',command('check',legacy_bundle)).stdout)['signatures']
   (legacy/'legacy-signatures.h').write_text('\n'.join('#define PIN_'+name.upper()+' "'+digest(sig)+'"' for name,sig in old_signatures.items())+'\n', newline="\n")
   old_image=legacy/'module.so'
   run(dialect+'-legacy-compile',[driver,'-x','c' if dialect=='C11' else 'c++','-std='+standard,'-shared','-fPIC','-I'+str(ROOT/'runtime'),'-I'+str(legacy),ROOT/'tests/legacy_resource_prefix_module.c','-o',old_image])
   (legacy/'NOTICE').write_text('NEX genuine old resource table prefix conformance producer\n', newline="\n")
   old_manifest={'schema':'nex.foreign-bundle/1','platform':manifest['platform'],'entry':'module.so',
    'files':[{'path':n,'sha256':sha(legacy/n)} for n in ['module.so','NOTICE']],
    'exports':{name:digest(sig) for name,sig in old_signatures.items()},'notices':['NOTICE']}
   write(legacy/'manifest.json',old_manifest);old_pin=sha(legacy/'manifest.json');old_host=legacy/'host.json'
   write(old_host,{**policy,'libraries':{'test':{'directory':str(legacy),'manifest_sha256':old_pin,'exports':list(old_signatures)}}})
   write(legacy_bundle,{'schema':'nex.sources/1','entry':'main.nex','files':{'main.nex':legacy_source(old_pin)}})
   reference=json.loads(run(dialect+'-legacy-reference',command('reference',legacy_bundle,old_host)).stdout)
   assert reference['output']=='42\n' and reference['external_capacity_after_scope']==0
   old_built=json.loads(run(dialect+'-legacy-build',command('native',legacy_bundle,legacy/'native')).stdout)
   old_result=run(dialect+'-legacy-native',[old_built['executable'],'--nex-foreign',old_host,'--nex-task-workers','1']);assert old_result.stdout=='42\n'
   report['checks'].append({'dialect':dialect,'genuine_previous_resource_header':sha(fixture),'previous_resource_table_bytes':296,
    'native_and_independent_AST':True,'legacy_factory_borrow_close':True});save()
   previous=directory/'parent-prefix-0163';previous.mkdir()
   frozen=ROOT/'tests/fixtures/ffi-parent-prefix-0.163/nex_ffi.h'
   assert sha(frozen)=='638e21da6a28639ee48828926a2875477d3cec5edae3ee2851ae2b1dcc0d0ffe'
   previous_image=previous/'module.so'
   run(dialect+'-parent-prefix-compile',[driver,'-x','c' if dialect=='C11' else 'c++','-std='+standard,'-shared','-fPIC','-pthread',
    '-I'+str(ROOT/'runtime'),'-I'+str(directory),ROOT/'tests/legacy_parent_prefix_module.c','-o',previous_image])
   (previous/'NOTICE').write_text('NEX frozen 0.163 parent-table producer\n', newline="\n")
   previous_manifest={**manifest,'files':[{'path':n,'sha256':sha(previous/n)} for n in ['module.so','NOTICE']]}
   write(previous/'manifest.json',previous_manifest);previous_pin=sha(previous/'manifest.json');previous_host=previous/'host.json'
   write(previous_host,{**policy,'libraries':{'test':{'directory':str(previous),'manifest_sha256':previous_pin,'exports':list(signatures)}}})
   for case in ['hidden_parent_scope_return','transitive_hidden_parents','close_during_admitted_factory']:
    body,roots,children=CASES[case];label=dialect+'-parent-prefix-'+case;path=bundle(label,body,previous_pin)
    reference=json.loads(run(label+'-reference',command('reference',path,previous_host)).stdout)
    assert reference['output']=='42\n' and reference['external_capacity_after_scope']==0
    built=json.loads(run(label+'-build',command('native',path,previous/'native')).stdout)
    assert run(label+'-native',[built['executable'],'--nex-foreign',previous_host,'--nex-task-workers','1']).stdout=='42\n'
    for mode in ['reference','native']:
     events=(out/(label+'-'+mode+'.events')).read_text()
     assert events.startswith('I') and events.endswith('D') and '!' not in events,events
     assert events.count('A')==events.count('P')==roots and events.count('B')==events.count('C')==children,events
     assert events.rfind('C')<events.index('P'),events
    report['checks'].append({'dialect':dialect,'case':case,'genuine_previous_parent_header':sha(frozen),'previous_parent_table_bytes':304,
     'native_and_independent_AST':True,'child_before_parent_destruction':True});save()
  assert sha(compiler)==report['compiler_sha256'];report.update(ok=True,state='passed',actual_producers=['C11','CPP20'],source_parent_FFI=True)
 except BaseException as error:
  report.update(state='failed',error=repr(error));raise
 finally:
  save();print(json.dumps({'ok':report['ok'],'checks':len(report['checks']),'output':str(out)}),flush=True)
  if temporary:temporary.cleanup()
 if not report['ok']:raise SystemExit(1)

if __name__=='__main__':main()
