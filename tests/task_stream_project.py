"""Private024 actual component plan/build/capture/replay/package contracts."""
import argparse,hashlib,json,os,shutil,subprocess,sys,tempfile,time
from pathlib import Path,PurePosixPath

parser=argparse.ArgumentParser();parser.add_argument('probe',type=Path);parser.add_argument('compiler',type=Path);parser.add_argument('reference',type=Path);parser.add_argument('--output',type=Path);parser.add_argument('--complete-tooling',action='store_true');parser.add_argument('--notices',type=Path);a=parser.parse_args()
temporary=None
if a.output:root=a.output.resolve();root.mkdir()
else:temporary=tempfile.TemporaryDirectory(prefix='nex stream project ');root=Path(temporary.name).resolve()
probe=a.probe.resolve();compiler=a.compiler.resolve();reference=a.reference.resolve();start=time.monotonic()
report={'schema':'nex.private024-stream-project/1','ok':False,'state':'starting','commands':[],'cases':[],
 'probe_sha256':hashlib.sha256(probe.read_bytes()).hexdigest(),'compiler_sha256':hashlib.sha256(compiler.read_bytes()).hexdigest(),
 'reference_probe_sha256':hashlib.sha256(reference.read_bytes()).hexdigest(),'public_language':'0.28','private_language':'0.24',
 'retained024_enabled':True,'public025_delivery_accepted':False,'full_objective_complete':False}
LEAF='''module leaf;
pub struct Box<T>{value:T;}
pub server fn opened()->Box<file> !{task,fs}{return Box(unwrap(file_open_read("input")));}
pub server fn transit(p:Box<file>)->Box<file> !{task}{task_yield();return p;}
server fn unused()->file !{task,fs}{return unwrap(file_open_write("UNREACHABLE_WRITE"));}
'''
APP='''module app;import "../leaf/main.nex" as leaf;
server fn main()->unit !{task,fs,io}{
 let box:leaf::Box<file>=leaf::transit(leaf::opened());
 assert(unwrap(file_read(box.value,6))==utf8_bytes("abcdef"));
 assert(file_close(box.value));print(42);}
'''
# Windows copytree omits target_is_directory for a copied relative symlink.
# This legacy fixture must preserve the actual reparse entry kind.
def copy_namespace(source,destination):
    """Preserve alias kind without following it to infer a Windows link type."""
    source=Path(source);destination=Path(destination);destination.mkdir()
    for item in source.iterdir():
        target=destination/item.name;info=item.lstat()
        if item.is_symlink():
            directory=bool(info.st_file_attributes&0x10)if os.name=='nt'else item.is_dir()
            os.symlink(os.readlink(item),target,target_is_directory=directory)
        elif os.name=='nt'and info.st_file_attributes&0x400:
            raise ValueError('unexpected non-symbolic reparse point in captured namespace')
        elif item.is_dir():copy_namespace(item,target)
        else:shutil.copy2(item,target)

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,v):Path(p).write_text(json.dumps(v,indent=2)+'\n', newline="\n")
notices=a.notices.resolve(strict=True) if a.notices else None
if notices:
 declared=json.loads(notices.read_text());assert declared['schema']=='nex.sdk-notices/1'
 # This opt-in test mode describes actual instrumentation dependencies; no
 # product notice guard or package dependency classification is overridden.
 assert len(declared['components'])==1
 notice_component=declared['components'][0]
 assert len(notice_component['roots'])==len(notice_component['license_files'])==1
 runtime=(notices.parent/notice_component['roots'][0]).resolve(strict=True)
 license_file=(notices.parent/notice_component['license_files'][0]).resolve(strict=True)
 assert runtime.is_file() and license_file.is_file()
 report['external_runtime']={'notices':str(notices),'notices_sha256':sha(notices),'path':str(runtime),'sha256':sha(runtime),
  'license':str(license_file),'license_sha256':sha(license_file),'component':notice_component['name']}
def save():report['seconds']=round(time.monotonic()-start,3);write(root/'report.json',report)
def run(name,argv,env=None,expected=0):
 report['state']=name;save();r=subprocess.run(list(map(str,argv)),cwd=root,env=env or os.environ,capture_output=True,text=True,timeout=600)
 (root/(name+'.stdout')).write_text(r.stdout, newline="\n");(root/(name+'.stderr')).write_text(r.stderr, newline="\n")
 report['commands'].append({'name':name,'argv':list(map(str,argv)),'exit_code':r.returncode,'expected':expected});save()
 assert r.returncode==expected,(name,r.returncode,r.stdout[-4500:],r.stderr[-4500:]);return r
def invoke(name,request,expected=0,env=None):
 request={'compiler':str(compiler),**request};p=root/(name+'.request.json');write(p,request)
 return json.loads(run(name,[probe,p],env,expected).stdout)
def executable(result):
 return Path(next(row['artifact'] for row in result['artifacts'] if row['component']=='app'))
def check_plan(plan,mode,profile,debug,language='0.24'):
 assert plan['ok'] and plan['language']==language and plan['source_checked'] and not plan['graph_store_opened']
 assert not plan['external_tools_invoked']
 rows={row['name']:row for row in plan['components']};assert set(rows)=={'leaf','app'}
 current=language=='0.28';abi=7 if current else 5;mask=7967 if current else 3871
 schema='nex.project-task-linkage/'+(('16' if debug else '15' if profile=='profile' else '14') if current else ('10' if debug else '9' if profile=='profile' else '8')) if mode=='shared' or profile=='profile' or debug else 'nex.project-static-task-linkage/'+('5' if current else '3')
 for row in rows.values():
  linkage=row['task_linkage'];assert linkage['schema']==schema and linkage['execution_abi']==abi
  assert tuple(linkage[k] for k in ['task_file_reads','task_file_writes','task_file_streams'])==(True,False,True)
  assert all(export['requirements']&~mask==0 for export in linkage['exports'].values())
 assert all(row['calling_mode']=='task-code/'+str(abi) for row in rows['app']['task_linkage']['imports'])
 return rows
try:
 assert json.loads(run('describe',[compiler,'describe','--json']).stdout)['version']=='0.28'
 for mode in ['static','shared']:
  for profile,debug in [('debug',False),('release',False),('profile',False),('debug',True)]:
   name=mode+'-'+profile+('-logical' if debug else '');case=root/name;case.mkdir();project=case/'project';project.mkdir()
   for part in ['leaf','app']:(project/part).mkdir()
   (project/'leaf/main.nex').write_text(LEAF, newline="\n");(project/'app/main.nex').write_text(APP, newline="\n")
   write(project/'nex.json',{'schema':'nex.project/1','language':'0.24','entry':'app/main.nex'})
   architecture={'schema':'nex.project-build/1','components':{
    'leaf':{'kind':'shared_library' if mode=='shared' else 'static_library','root':'leaf','entry':'leaf/main.nex','entry_function':'opened','exports':['transit']},
    'app':{'kind':'executable','root':'app','entry':'app/main.nex','dependencies':{'leaf':'dynamic' if mode=='shared' else 'static'}}},
    'configurations':{profile:{'profile':profile,'target':'native','task_limits':{'steps':1000000,'timeout_ms':60000,'workers':1}}},'default_configuration':profile}
   write(project/'nex.build.json',architecture);base={'root':str(project),'configuration':profile,'task_debug':debug}
   files=case/'files';files.mkdir();(files/'input').write_bytes(b'abcdef');env={**os.environ,'NEX_FILES_ROOT':str(files),'NEX_FILES_WRITE':'1'}
   current_project=case/'current025-project';shutil.copytree(project,current_project)
   write(current_project/'nex.json',{'schema':'nex.project/1','language':'0.28','entry':'app/main.nex'})
   public_base={**base,'root':str(current_project),'public_api':True}
   public=invoke(name+'-public-plan',{'action':'plan',**public_base});check_plan(public,mode,profile,debug,'0.28')
   public_capture=invoke(name+'-public-capture',{'action':'capture',**public_base});public_capture_file=case/'current025-capture.json';write(public_capture_file,public_capture)
   assert public_capture['language']=='0.28' and not (current_project/'.nex').exists()
   accepted=invoke(name+'-public-validate',{'action':'validate','capture':str(public_capture_file),'public_api':True});assert accepted['ok'] and accepted['language']=='0.28'

   if mode=='static' and profile=='debug' and not debug:
    namespace=case/'current-layout';original_capture=public_capture_file.read_bytes()
    current=invoke('current-layout-restore',{'action':'restore','capture':str(public_capture_file),'directory':str(namespace),'public_api':True})
    verify={'action':'verify','capture':str(public_capture_file),'directory':str(namespace),'public_api':True}
    assert invoke('current-layout-verify',verify)['ok']
    marker=namespace/'capture-layout.json';anchor='fs'
    if os.name=='nt':
     assert marker.is_file();saved_marker=marker.read_bytes();anchor=json.loads(saved_marker)['removed_prefix']
     legacy=case/'legacy-layout';target=legacy/PurePosixPath(anchor);target.parent.mkdir(parents=True)
     copy_namespace(namespace/'fs',target)
     assert invoke('legacy-layout-verify',{**verify,'directory':str(legacy)})['ok']
     write(marker,{'schema':'nex.project-capture-layout/1','removed_prefix':anchor+'/changed'})
     assert invoke('current-layout-marker-mutation',verify,1)['code']=='E_PROJECT_CAPTURE'
     marker.write_bytes(saved_marker)
    source_key=next(p for p,v in public_capture['files'].items() if p.endswith('.nex') and v)
    source=namespace/'fs'/PurePosixPath(source_key).relative_to(anchor);original=source.read_bytes()
    source.write_bytes(original+b'\n')
    assert invoke('current-layout-source-mutation',verify,1)['code']=='E_PROJECT_CAPTURE'
    source.write_bytes(original);assert invoke('current-layout-restored-verify',verify)['ok']
    assert public_capture_file.read_bytes()==original_capture
   plan=invoke(name+'-plan',{'action':'plan',**base});rows=check_plan(plan,mode,profile,debug)
   assert not (project/'.nex').exists()
   capture=invoke(name+'-capture',{'action':'capture',**base});capture_file=case/'capture.json';write(capture_file,capture)
   assert capture['language']=='0.24'
   refused=invoke(name+'-public-retained-capture',{'action':'validate','capture':str(capture_file),'public_api':True},1);assert refused['code']=='E_PROJECT_CAPTURE'
   built=invoke(name+'-build',{'action':'build','directory':str(case/'native'),**base},env=env);binary=executable(built)
   metadata=json.loads((binary.parent/'build.json').read_text());assert metadata['task_provider']['language']=='0.24' and metadata['task_execution_abi']==0x4e45585400000005
   assert metadata['task_file_streams'] is True and metadata['task_file_writes'] is False
   bundle=case/'reference.json';write(bundle,{'schema':'nex.sources/1','entry':'app/main.nex','files':{'app/main.nex':APP,'leaf/main.nex':LEAF}})
   evaluated=json.loads(run(name+'-reference',[reference,'reference',bundle,case,'-','0.24'],env).stdout)
   assert evaluated['output']=='42\n' and evaluated['language']=='0.24'
   hidden=project.with_name('project.hidden');project.rename(hidden)
   try:
    native=run(name+'-source-absent-native',[binary],env);assert native.stdout=='42\n' and native.stderr==''
    restored=invoke(name+'-restore',{'action':'restore','capture':str(capture_file),'directory':str(case/'capture-root')})
    replay_base={**base,'root':restored['root']}
    replay=invoke(name+'-replay-build',{'action':'build','directory':str(case/'replay-native'),**replay_base},env=env);replay_binary=executable(replay)
    observed=run(name+'-replay-native',[replay_binary],env);assert observed.stdout=='42\n' and observed.stderr==''
    package_request={'action':'package','directory':str(case/'replay-native'),'package_directory':str(case/'package'),**replay_base}
    if notices:
     refused=invoke(name+'-package-no-notices',package_request,1,env=env)
     assert refused['code']=='E_PROJECT_PACKAGE' and 'no component/license provenance' in refused['message']
     package_request['notices']=str(notices)
    package=invoke(name+'-package',package_request,env=env)
    assert package['language']=='0.24' and not package['graph_store_opened']
    app_package=next(row for row in package['components'] if row['component']=='app')
    manifest=json.loads((case/'package'/app_package['manifest']).read_text());assert manifest['language']=='0.24'
    if notices:
     packaged_component=next(c for c in manifest['components'] if c['name']==notice_component['name'])
     assert packaged_component['version']==notice_component['version'] and packaged_component['url']==notice_component['url']
     app_root=(case/'package'/app_package['manifest']).parent
     copied=[(n,r) for n,r in manifest['files'].items() if r.get('component')==notice_component['name']]
     libraries=[(n,r) for n,r in copied if r.get('source_sha256')==sha(runtime)]
     assert len(libraries)==1,(name,copied)
     assert sha(app_root/libraries[0][0])==libraries[0][1]['sha256']
     assert any(sha(app_root/n)==sha(license_file) for n,r in manifest['files'].items() if n.startswith('licenses/'))
    container=case/'capture-root';hidden_container=case/'capture-root.hidden';container.rename(hidden_container)
    try:
     packaged=run(name+'-packaged-native',[case/'package'/app_package['entry']],{'PATH':'/usr/bin:/bin','NEX_FILES_ROOT':str(files)})
     assert packaged.stdout=='42\n' and packaged.stderr==''
    finally:hidden_container.rename(container)
   finally:hidden.rename(project)
   assert (files/'input').read_bytes()==b'abcdef' and not (files/'UNREACHABLE_WRITE').exists()
   assert not list(project.rglob('graph.db')) and not list((case/'capture-root').rglob('graph.db'))
   report['cases'].append({'name':name,'mode':mode,'profile':profile,'task_debug':debug,'native_reference':True,'source_absent_replay':True,
    'executable':str(binary),'executable_sha256':sha(binary),'replay_executable':str(replay_binary),'replay_executable_sha256':sha(replay_binary),
    'capture':str(capture_file),'capture_sha256':sha(capture_file),'package':package});save()
 report.update(ok=not a.complete_tooling,state='tooling-pending' if a.complete_tooling else 'passed',execution_matrix_complete=True,native_reference_pairs=len(report['cases']),source_absent_replay=True,public025_refuses_retained024_capture=True,current025_plan_capture_modes=len(report['cases']),
  graph_store_never_opened=True,ABI3_ABI4_acceptance_separate=True)
 if notices:report.update(missing_notice_rejections=len(report['cases']),packaged_runtime_and_license_checks=len(report['cases']))
 save()
 if a.complete_tooling:
  scripts=Path(__file__).resolve().parent
  run('tooling-boundary',[sys.executable,'-B',scripts/'task_stream_project_boundary.py',probe,root,'--output',root/'boundary'])
  boundary=json.loads((root/'boundary/report.json').read_text());assert boundary['ok'] and boundary['rejected_captures']==84
  run('tooling-observability',[sys.executable,'-B',scripts/'task_stream_project_observability.py',probe,compiler,root,'--output',root/'observability'])
  observed=json.loads((root/'observability/report.json').read_text());assert observed['ok'] and observed['actual_profiles']==2 and observed['actual_LLDB_DAP_sessions']==2
  report.update(ok=True,state='passed',captured_plan_rejections=84,retained_public_ABI4_modes=2,actual_profiles=2,actual_LLDB_DAP_sessions=2)
except BaseException as error:report.update(ok=False,state='failed',error=repr(error));raise
finally:save();print(json.dumps({k:report.get(k) for k in ['ok','state','native_reference_pairs','error']}),flush=True)
