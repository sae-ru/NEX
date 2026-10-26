from pathlib import Path
import argparse,hashlib,importlib.util,json,os,platform,re,shutil,subprocess,sys,time
HERE=Path(__file__).resolve().parent
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def write(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,required=True);parser.add_argument('--compiler',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--repeats',type=int,default=2);parser.add_argument('--modes',nargs='+',choices=['normal','ASAN-UBSAN','TSAN'],default=['normal','ASAN-UBSAN','TSAN']);args=parser.parse_args();assert 1<=args.repeats<=10
 source=args.source.resolve(strict=True);compiler=args.compiler.resolve(strict=True);out=args.output.absolute();out.mkdir(parents=True);started=time.monotonic();peers=None
 inputs={p.relative_to(source).as_posix():sha(p) for p in (source/'runtime').rglob('*') if p.is_file()}
 inputs.update({p.relative_to(source).as_posix():sha(p) for p in (source/'tools/tcp_provider').rglob('*') if p.is_file()});inputs['lib/tcp.nex']=sha(source/'lib/tcp.nex')
 report={'schema':'nex.tcp-typed-runtime-sanitizers/1','ok':False,'state':'starting','machine':platform.machine(),'platform':platform.system(),'source':str(source),'compiler_sha256':sha(compiler),'inputs':inputs,'test_inputs':{p.name:sha(p) for p in HERE.iterdir() if p.is_file()},'commands':[],'observations':[],'NEX_compiler_or_generated_IR_instrumented':False,'full_objective_complete':False}
 def save():report['seconds']=time.monotonic()-started;write(out/'report.json',report)
 def guard():
  for n,h in inputs.items():assert sha(source/n)==h,n
 def run(label,argv,*,env=None,timeout=600):
  row={'label':label,'argv':list(map(str,argv)),'state':'running'};report['commands'].append(row);report['state']=label;save();guard()
  p=subprocess.run(row['argv'],cwd=out,env=env,capture_output=True,text=True,timeout=timeout);(out/(label+'.stdout')).write_text(p.stdout);(out/(label+'.stderr')).write_text(p.stderr);row.update(exit_code=p.returncode,state='passed' if p.returncode==0 else 'failed');save();guard();assert p.returncode==0,(label,p.stderr[-4000:]+p.stdout[-2000:]);return p
 try:
  sdk=out/'compiler-projection';(sdk/'bin').mkdir(parents=True);(sdk/'share').mkdir();shutil.copy2(compiler,sdk/'bin/nex');(sdk/'share/nex').symlink_to(source,target_is_directory=True)
  environment={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','NEX_RESOURCE_DIR':str(source)}
  for key in ('NEX_FOREIGN_CONFIG','ASAN_OPTIONS','UBSAN_OPTIONS','TSAN_OPTIONS','DYLD_INSERT_LIBRARIES','LD_PRELOAD'):environment.pop(key,None)
  doctor=json.loads(run('doctor',[compiler,'doctor','--json'],env=environment).stdout);report['toolchain']=doctor['version'];report['language']=doctor['language'];assert doctor['language']=='0.24'
  capability=json.loads(run('task-FFI-capability',[compiler,'describe','--field','task_foreign_prototype','--json'],env=environment).stdout);assert capability['language']=='0.24' and capability['value']['source_support'] is True
  spec=importlib.util.spec_from_file_location('tcp_provider_peers',source/'tools/tcp_provider/verify.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);files=out/'gates';files.mkdir();peers=module.Peers(files)
  for mode in args.modes:
   flags=['-g','-fno-omit-frame-pointer']+([] if mode=='normal' else ['-fsanitize='+('address,undefined' if mode=='ASAN-UBSAN' else 'thread'),'-fno-sanitize-recover=all'])
   settings={} if mode=='normal' else ({'ASAN_OPTIONS':'detect_leaks='+('0' if sys.platform=='darwin' else '1')+':halt_on_error=1','UBSAN_OPTIONS':'halt_on_error=1:print_stacktrace=1'} if mode=='ASAN-UBSAN' else {'TSAN_OPTIONS':'halt_on_error=1'})
   env={**environment,**settings};folder=out/mode;folder.mkdir();driver=folder/'instrumented-cxx';driver.write_text('#!/usr/bin/python3\nimport os,sys\ncxx='+repr(doctor['native_compiler'])+'\nos.execv(cxx,[cxx,'+','.join(repr(f) for f in flags)+(',' if flags else '')+'*sys.argv[1:]])\n');driver.chmod(0o700)
   report.setdefault('compiler_driver_sha256',{})[mode]=sha(driver)
   build=folder/'host-build';cmake=['cmake','-S',HERE,'-B',build,'-DNEX_SOURCE='+str(source),'-DCMAKE_CXX_COMPILER='+doctor['native_compiler'],'-DCMAKE_BUILD_TYPE=RelWithDebInfo','-DCMAKE_EXPORT_COMPILE_COMMANDS=ON','-DCMAKE_CXX_FLAGS='+' '.join(['-O1','-g',*flags]),'-DCMAKE_EXE_LINKER_FLAGS='+' '.join(flags)]
   cmake+=['-DOPENSSL_ROOT_DIR='+str(Path(doctor['native_openssl_include']).parent)]
   run(mode+'-configure',cmake,env=env);run(mode+'-build',['cmake','--build',build,'-j','2'],env=env,timeout=1200);binary=build/'tcp_typed_host';report.setdefault('binary_sha256',{})[mode]=sha(binary)
   for capacity in (16,1):
    label=mode+'-'+str(capacity);targets=folder/(str(capacity)+'-targets.json');write(targets,{'schema':'nex.tcp-targets/1','maximum_connections':capacity,'endpoints':peers.endpoints});project=folder/(str(capacity)+'-project')
    run(label+'-prepare',[sys.executable,'-B',source/'tools/tcp_provider/prepare.py','--sdk',sdk,'--targets',targets,'--output',project,'--cxx',driver,'--diagnostics'],env=env)
    prepared=json.loads((project/'evidence/report.json').read_text());assert prepared['ok'] and not prepared['network_executed'] and not prepared['module_initialized'];pin=prepared['manifest_sha256'];bindings={}
    for name in ('exchange','statistics'):bindings[name]={'schema':'nex.foreign-binding/1','library':'tcp','export':name,'manifest_sha256':pin,'signature':json.loads((project/'evidence'/('signature-'+name+'.stdout')).read_text())}
    # Two simultaneously live lexical scopes require two explicit logical
    # module authorizations, even though the pinned DSO image is shared.
    catalogue=json.loads((project/'foreign.json').read_text());catalogue['module_limit']=2;write(project/'two-context-foreign.json',catalogue)
    write(project/'host-input.json',bindings)
    for index in range(args.repeats):
     run_id=mode+'-'+str(capacity)+'-'+str(index);p=run(run_id,[binary,project,files,run_id,'capacity' if capacity==1 else 'full'],env=env,timeout=120);observed=json.loads(p.stdout);assert observed['ok'] and len(observed['checks'])==(1 if capacity==1 else 15) and len(set(observed['checks']))==len(observed['checks'])
     counters=[json.loads(s) for s in re.findall(r'NEX_TCP_RETIRE (\{[^\n]+\})',p.stderr)];assert counters and all(v['live']==0 and v['opened']==v['closed'] for v in counters),(run_id,p.stderr)
     report['observations'].append({'mode':mode,'capacity':capacity,'repeat':index,'checks':observed['checks'],'retired':counters});save()
  report.update(ok=True,state='passed',actual_pinned_module_and_host_runtime=True,checks_per_mode=16*args.repeats,Mac_leak_sanitizer_enabled=False if sys.platform=='darwin' else None,Linux_leak_sanitizer_enabled=True if sys.platform.startswith('linux') else None)
 except BaseException as error:report.update(state='failed',error=repr(error));raise
 finally:
  if peers:peers.close();report['peer_events']=peers.events
  save()
 print(json.dumps({k:report.get(k) for k in ('ok','state','error','checks_per_mode','seconds')}))
if __name__=='__main__':main()
