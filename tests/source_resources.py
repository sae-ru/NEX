"""Source resources: checked successes/refusals and real C/CPP/native boundary."""
import argparse,datetime,hashlib,json,os,platform,subprocess,tempfile,time,traceback
from pathlib import Path
parser=argparse.ArgumentParser()
parser.add_argument('probe',type=Path);parser.add_argument('source',type=Path);parser.add_argument('--compiler',type=Path,required=True);parser.add_argument('--output',type=Path);parser.add_argument('--legacy-fixtures',type=Path);parser.add_argument('--nex',type=Path)
cli=parser.parse_args();SOURCE=cli.source.resolve();PROBE=cli.probe.resolve();OUT=cli.output.resolve() if cli.output else Path(tempfile.mkdtemp(prefix='nex-source-resources-'))
if cli.output:OUT.mkdir()
if cli.legacy_fixtures is None and os.environ.get('NEX_TEST_RESOURCE020_FIXTURES'):cli.legacy_fixtures=Path(os.environ['NEX_TEST_RESOURCE020_FIXTURES'])

ENV={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'};ENV.pop('NEX_RESOURCE_DIR',None)
report={'schema':'nex.source-resource-preflight/1','ok':False,'state':'starting','source':str(SOURCE),'probe':str(PROBE),'output':str(OUT),'commands':[],'cases':[],'public_source_resources':True,'public_language':'0.24','source_language':'0.24','migration_accepted':False,'source_task_resource_bridge':False,'actual_GPU_NPU_resources':False};started=time.monotonic()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save():report.update(seconds=round(time.monotonic()-started,3),updated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat());(OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n')
def command(label,args,cwd=OUT,expected=0,code=None,parse=True,env=ENV):
 report['state']=label;row={'label':label,'command':list(map(str,args)),'cwd':str(cwd)};report['commands'].append(row);save()
 p=subprocess.run(row['command'],cwd=cwd,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=240)
 for key in ('stdout','stderr'):(OUT/(label+'.'+key)).write_text(getattr(p,key))
 row.update(exit_code=p.returncode,passed=p.returncode==expected);save();assert p.returncode==expected,(label,p.stdout[-3000:],p.stderr[-3000:])
 result=json.loads(p.stdout) if parse else p.stdout
 if code is not None:assert result.get('code')==code,(label,result,code)
 return result
def bundle(name,files):
 root=OUT/name;root.mkdir();doc={'schema':'nex.sources/1','entry':'main.nex','files':{'main.nex':files} if isinstance(files,str) else files};path=root/'sources.json';path.write_text(json.dumps(doc,ensure_ascii=False,indent=2)+'\n');return root,path
def check(name,text,error=None,language='0.24'):
 root,path=bundle(name,text);r=command(name,[PROBE,'check',path,root,'-',language],expected=1 if error else 0,code=error);report['cases'].append({'name':name,'expected_error':error,'revision':r.get('revision')});save();return r,root,path
try:
 assert PROBE.is_file();report['probe_sha256']=sha(PROBE)
 resource='module fixture; pub server resource Session; '
 r,_,_=check('opaque-declaration',resource+'server fn forward(r:Session)->Session{return r;}')
 assert len(r['resources'])==1
 node=next(iter(r['resources'].values()));assert node['canonical']['format']=='nex.resource/1' and len(node['name'])<=128 and len(node['identity'])==64
 r,_,_=check('generic-resource-classes','''module fixture;
 pub server resource Buffer<T>;
 server fn close<T>(r:Buffer<T>)->bool !{ffi}{return resource_close(r);}
 server fn close_i(r:Buffer<i64>)->bool !{ffi}{return close<i64>(r);}
 server fn close_b(r:Buffer<bool>)->bool !{ffi}{return resource_is_open(r);}
 ''')
 assert len(r['resources'])==2 and len({v['identity'] for v in r['resources'].values()})==2
 contexts=[]
 for kind in ('i64','bool'):
  r,_,_=check('generic-payload-context-'+kind,'module fixture; server resource Buffer<T>; struct Payload{value:'+kind+';} server fn forward(r:Buffer<Payload>)->Buffer<Payload>{return r;}')
  contexts.append(next(iter(r['resources'].values()))['identity'])
 assert contexts[0]!=contexts[1],'same-name phantom payload layout was omitted from resource identity'
 check('aggregate-and-result-aliases',resource+'''struct Packet{owner:Session;} enum Maybe{Some(value:Session);None;}
 server fn close_packet(p:Packet)->bool !{ffi}{return resource_close(p.owner);}
 server fn forward(r:result<Session>)->result<Session>{return r;}
 server fn show(r:Session)->str{return str(r);}
 ''')
 check('phantom-owner-forwarding',resource+'struct Phantom<T>{} server fn forward(p:Phantom<Session>)->Phantom<Session>{return p;}')
 imported={'main.nex':'module app; import "./owner.nex" as owner; server fn forward(r:owner::Session)->owner::Session{return r;}','owner.nex':'module owners; pub server resource Session;'}
 check('imported-resource-type',imported)
 for name,text,error in [
  ('missing-server','module a; resource R;','E_REALM'),
  ('client-resource','module a; client resource R;','E_REALM'),
  ('shared-resource','module a; shared resource R;','E_REALM'),
  ('resource-fields','module a; server resource R {x:i64;}','E_PARSE'),
  ('source-constructor',resource+'server fn bad()->Session{return Session();}','E_RESOURCE_CONSTRUCTOR'),
  ('generic-source-constructor','module a; server resource R<T>; server fn bad()->R<i64>{return R<i64>();}','E_RESOURCE_CONSTRUCTOR'),
  ('constructor-pattern',resource+'server fn bad(r:Session)->i64{return match r{Session()=>0};}','E_RESOURCE_CONSTRUCTOR'),
  ('shared-owner-signature',resource+'fn bad(r:Session)->i64{return 0;}','E_REALM'),
  ('client-phantom-signature',resource+'struct Phantom<T>{} client fn bad(p:Phantom<Session>)->i64{return 0;}','E_REALM'),
  ('wire-owner',resource+'server fn bad(r:Session)->str{return encode_json(r);}','E_GENERIC_BOUND'),
  ('wire-phantom',resource+'struct Phantom<T>{} server fn bad(p:Phantom<Session>)->str{return encode_json(p);}','E_GENERIC_BOUND'),
  ('wire-bound',resource+'struct Box<T:wire>{value:T;} server fn bad(r:Session)->Box<Session>{return Box<Session>(r);}','E_GENERIC_BOUND'),
  ('close-without-effect',resource+'server fn bad(r:Session)->bool{return resource_close(r);}','E_EFFECT'),
  ('close-wrong-type','module a; server fn bad(r:i64)->bool !{ffi}{return resource_close(r);}','E_RESOURCE_TYPE'),
  ('parallel-owner',resource+'server fn bad(r:list<Session>)->list<i64>{return parallel_map(r,server fn(x:Session)->i64{return 0;},1);}','E_PARALLEL_TYPE'),
  ('parallel-captured-owner',resource+'server fn bad(r:Session)->list<i64>{return parallel_map([1],server fn(x:i64)->i64{let held:Session=r;return x;},1);}','E_PARALLEL_TYPE'),
  ('task-captured-owner',resource+'server fn bad(r:Session)->i64 !{task}{return with_tasks(1,server fn(s:task_scope)->i64 !{task}{let t:task<i64>=task_spawn(s,server fn()->i64{let held:Session=r;return 1;});return task_wait(t);});}','E_TASK_TYPE'),
  ('channel-owner',resource+'server fn bad()->i64 !{task}{return with_tasks(1,server fn(s:task_scope)->i64 !{task}{let c:channel<Session>=channel_new<Session>(s,1);return 0;});}','E_TASK_TYPE'),
 ]:
  if name in ('task-captured-owner','channel-owner'):
   check(name+'-retained021',text,error,'0.21');check(name+'-current022',text)
  else:check(name,text,error)
 check('020-resource-syntax-rejected',resource,'E_PARSE','0.20')
 # Ordinary identifiers retain their interpretation in both explicit versions.
 legacy='module a; struct resource{value:i64;} fn resource_close(resource:i64)->i64{return resource+1;} fn main()->i64{return resource_close(resource(41).value);}'
 check('020-ordinary-resource-names',legacy,language='0.20')
 check('current022-ordinary-resource-nominal','module a; struct resource{value:i64;} fn preserve<resource>(value:resource)->resource{return value;} fn main()->i64{return preserve<i64>(resource(42).value);}')
 check('current022-builtin-name-conflict',legacy,'E_DUPLICATE')
 if cli.legacy_fixtures:
  old=json.loads(cli.legacy_fixtures.read_text())
  for f in old['fixtures']:
   snapshot=json.loads(Path(f['all_rows_snapshot']).read_text());columns=snapshot['tables']['revisions']['columns'];source=columns.index('source');hash_column=columns.index('hash')
   for number,row in enumerate(snapshot['tables']['revisions']['rows']):
    root,path=bundle('legacy-'+f['name']+'-'+str(number),json.loads(row[source])['files']);r=command('legacy-'+f['name']+'-'+str(number),[PROBE,'check',path,root,'-','0.20']);assert r['revision']==row[hash_column] and not r['resources']
  report['genuine020_unchanged_revisions']=sum(f['original_revision_count'] for f in old['fixtures']);save()
 # Declare the11 independently exported fixture signatures using the new source class.
 declarations={'create':('x:i64','Session'),'read':('x:Session','i64'),'forward':('x:Session','Session'),'close_borrow':('x:Session','i64'),'status':('x:Session','i64'),'input_constructor':('x:Session','i64'),'bad_callback':('x:i64','Session'),'hold_poll':('x:Session','i64'),'result_create':('x:i64','result<Session>'),'tokens':('x:Session','i64'),'wrong_thread':('x:Session','i64')}
 def program(pin,body=None):
  lines=[resource]
  for name,(argument,result) in declarations.items():lines.append('server extern fn '+name+'('+argument+')->'+result+' !{ffi}=foreign("test","'+name+'","'+pin+'");')
  lines.append('client fn client_value()->i64{return 42;}')
  lines.append(body or '''server fn main()->i64 !{ffi,io}{
 let r:Session=create(42);let alias:Session=forward(r);assert(r==alias);assert(resource_is_open(r));assert(read(r)==42);
 assert(resource_close(alias));assert(!resource_is_open(r));assert(!resource_close(r));assert(status(r)==13);
 let second:Session=unwrap(result_create(7));assert(read(second)==7);print(str(r));return 0;
 }''');return '\n'.join(lines)
 api,project,path=check('pinned-source-program',program('0'*64))
 generated=project/'generated';generated.mkdir()
 lines=[]
 for name,sig in api['signatures'].items():lines.append('#define PIN_'+name.upper()+' "'+hashlib.sha256(json.dumps(sig,sort_keys=True,separators=(',',':')).encode()).hexdigest()+'"')
 (generated/'typed-resource-signatures.h').write_text('\n'.join(lines)+'\n')
 for kind in ('C','CPP'):
  bundle_dir=project/('bundle-'+kind);bundle_dir.mkdir();module=bundle_dir/'module.so';compiler=cli.compiler if kind=='CPP' else cli.compiler.with_name('clang')
  args=[compiler,'-x','c' if kind=='C' else 'c++','-std=c11' if kind=='C' else '-std=c++20','-shared','-fPIC','-pthread','-fvisibility=hidden','-I'+str(SOURCE/'runtime'),'-I'+str(generated),SOURCE/'tests/typed_resource_module.c','-o',module]
  command('compile-'+kind,args,parse=False)
  (bundle_dir/'NOTICE').write_text('NEX source-resource conformance module\n')
  exported={name:hashlib.sha256(json.dumps(sig,sort_keys=True,separators=(',',':')).encode()).hexdigest() for name,sig in api['signatures'].items()}
  manifest={'schema':'nex.foreign-bundle/1','platform':('macos' if platform.system()=='Darwin' else 'linux')+'-'+('arm64' if platform.machine().lower() in ('arm64','aarch64') else 'x86_64'),'entry':'module.so','files':[{'path':name,'sha256':sha(bundle_dir/name)} for name in ('module.so','NOTICE')],'exports':exported,'notices':['NOTICE']};(bundle_dir/'manifest.json').write_text(json.dumps(manifest,sort_keys=True,indent=2)+'\n');pin=sha(bundle_dir/'manifest.json')
  host=project/('host-'+kind+'.json');host.write_text(json.dumps({'schema':'nex.foreign-host/1','module_limit':1,'resource_limit':4,'resource_bytes':32,'libraries':{'test':{'directory':str(bundle_dir),'manifest_sha256':pin,'exports':list(exported)}}},indent=2)+'\n')
  root,compiled_bundle=bundle('execution-'+kind,program(pin))
  r=command('reference-'+kind,[PROBE,'reference',compiled_bundle,root,host]);assert r['value']==0 and r['output']=='<resource>\n' and r['external_capacity_after_scope']==0
  web=OUT/('client-'+kind);command('web-isolation-'+kind,[PROBE,'web',compiled_bundle,root,web]);text=(web/'program.ts').read_text();assert 'fixture::Session' not in text and pin not in text and node['identity'] not in text
  native=command('native-build-'+kind,[PROBE,'native',compiled_bundle,root,OUT/('native-'+kind)]);assert native['foreign_calls']
  output=command('native-run-'+kind,[native['executable'],'--nex-foreign',host],parse=False);assert output=='<resource>\n'
  if cli.nex:
   sources=json.loads(compiled_bundle.read_text())
   for name,text in sources['files'].items():(root/name).write_text(text)
   compiler=cli.nex.resolve()
   language=command('public-language-'+kind,[compiler,'describe','--kind','index','--json'],cwd=root)['language']
   (root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':language,'entry':sources['entry']})+'\n')
   checked=command('public-check-'+kind,[compiler,'check','main.nex','--json'],cwd=root)
   exported=command('public-ffi-'+kind,[compiler,'ffi','main.nex','--symbol','fixture::create','--json'],cwd=root)
   assert exported==api['signatures']['create']
   evaluated=command('public-reference-'+kind,[compiler,'eval','main.nex','--foreign',host,'--json'],cwd=root)
   assert evaluated['stdout']=='<resource>\n' and evaluated['value']==0
   built=command('public-build-'+kind,[compiler,'build','main.nex','--profile','release','-o',OUT/('public-native-'+kind),'--json'],cwd=root)
   output=command('public-native-'+kind,[built['executable'],'--nex-foreign',host],parse=False)
   assert output=='<resource>\n'
   report.setdefault('public_CLI',[]).append({'producer':kind,'revision':checked['revision'],'executable':built['executable'],'signature_equal':True,'reference_native_equal':True});save()
  if kind=='CPP':
   throwing='server fn main()->i64 !{ffi}{let r:Session=create(-4);return read(r);}'
   badroot,bad=bundle('throwing-factory',program(pin,throwing));marker=OUT/'throwing-events';env={**ENV,'NEX_TYPED_RESOURCE_MARKER':str(marker)}
   command('CPP-factory-throw',[PROBE,'reference',bad,badroot,host],expected=1,code='E_FFI',env=env);events=marker.read_text();assert events=='IFXD',events
   bad_native=command('CPP-factory-throw-build',[PROBE,'native',bad,badroot,OUT/'native-CPP-throw'])
   marker.unlink();command('CPP-factory-throw-native',[bad_native['executable'],'--nex-foreign',host],expected=70,parse=False,env=env);assert marker.read_text()=='IFXD';assert 'E_FFI' in (OUT/'CPP-factory-throw-native.stderr').read_text()
   trap='server fn main()->i64 !{ffi}{let r:Session=create(42);let zero:i64=0;return read(r)/zero;}'
   traproot,trapsource=bundle('checked-trap-with-live-owner',program(pin,trap));marker.unlink()
   command('CPP-owned-trap-reference',[PROBE,'reference',trapsource,traproot,host],expected=1,code='E_DIV_ZERO',env=env);assert marker.read_text()=='IFXD'
   trapped=command('CPP-owned-trap-build',[PROBE,'native',trapsource,traproot,OUT/'native-CPP-owned-trap'])
   marker.unlink();command('CPP-owned-trap-native',[trapped['executable'],'--nex-foreign',host],expected=70,parse=False,env=env);assert marker.read_text()=='IFXD';assert 'E_DIV_ZERO' in (OUT/'CPP-owned-trap-native.stderr').read_text()
  report.setdefault('execution',[]).append({'producer':kind,'source_class':node['identity'],'reference_native_output':'<resource>\n','actual_native_binary':native['executable'],'module_sha256':sha(module),'pin':pin,'reachable_client_isolation':True});save()
 report.update(ok=True,state='passed',source_resources_enabled=True,nominal_and_generic_resources=True,source_constructor_rejected=True,wire_realm_task_parallel_rejections=True,native_reference_actual_producers=['C11','C++20'],CPP_throw_after_transfer_cleanup=True,source_and_runtime_owned_aliases=True)
except BaseException as e:
 report.update(state='failed',error=repr(e),traceback=traceback.format_exc());traceback.print_exc()
finally:save();print(json.dumps({k:report.get(k) for k in ('ok','state','output','genuine020_unchanged_revisions','execution','error')}))
raise SystemExit(0 if report['ok'] else 1)
