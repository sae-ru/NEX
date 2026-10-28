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
 parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,required=True);parser.add_argument('--cares-archive',type=Path,required=True);parser.add_argument('--compiler',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--repeats',type=int,default=2);parser.add_argument('--modes',nargs='+',choices=['normal','ASAN-UBSAN','TSAN'],default=['normal','ASAN-UBSAN','TSAN']);args=parser.parse_args();assert 1<=args.repeats<=10
 archive=args.cares_archive.resolve(strict=True);source=args.source.resolve(strict=True);compiler=args.compiler.resolve(strict=True);out=args.output.absolute();out.mkdir(parents=True,exist_ok=False);started=time.monotonic();peers=None;ipv6=None
 inputs={p.relative_to(source).as_posix():sha(p) for p in (source/'runtime').rglob('*') if p.is_file()}
 inputs.update({p.relative_to(source).as_posix():sha(p) for p in (source/'tools/dns_provider').rglob('*') if p.is_file()});inputs['lib/dns.nex']=sha(source/'lib/dns.nex')
 report={'schema':'nex.dns-typed-runtime-sanitizers/1','ok':False,'state':'starting','machine':platform.machine(),'platform':platform.system(),'source':str(source),'compiler_sha256':sha(compiler),'dependency_builder_sha256':sha(source/'tools/dns_provider/build_dependency.py'),'inputs':inputs,'test_inputs':{p.name:sha(p) for p in HERE.iterdir() if p.is_file()},'commands':[],'observations':[],'NEX_compiler_or_generated_IR_instrumented':False,'full_objective_complete':False}
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
  spec=importlib.util.spec_from_file_location('dns_provider_peers',source/'tools/dns_provider/verify.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);files=out/'gates';files.mkdir();peers=module.DNS(files);ipv6=module.DNS(files,'::1')
  for mode in args.modes:
   flags=['-g','-fno-omit-frame-pointer']+([] if mode=='normal' else ['-fsanitize='+('address,undefined' if mode=='ASAN-UBSAN' else 'thread'),'-fno-sanitize-recover=all'])
   settings={} if mode=='normal' else ({'ASAN_OPTIONS':'detect_leaks='+('0' if sys.platform=='darwin' else '1')+':halt_on_error=1','UBSAN_OPTIONS':'halt_on_error=1:print_stacktrace=1'} if mode=='ASAN-UBSAN' else {'TSAN_OPTIONS':'halt_on_error=1'})
   env={**environment,**settings};folder=out/mode;folder.mkdir();driver=folder/'instrumented-cxx';driver.write_text('#!/usr/bin/python3\nimport os,sys\ncxx='+repr(doctor['native_compiler'])+'\nos.execv(cxx,[cxx,'+','.join(repr(f) for f in flags)+(',' if flags else '')+'*sys.argv[1:]])\n');driver.chmod(0o700)
   report.setdefault('compiler_driver_sha256',{})[mode]=sha(driver)
   ccompiler=Path(doctor['native_compiler']).with_name('clang');assert ccompiler.is_file(),'matching clang C compiler is required'
   dependency_env={**env,'CC':str(ccompiler),'CFLAGS':' '.join(['-O1',*flags]),'LDFLAGS':' '.join(flags)}
   dependency=folder/'cares-dependency';run(mode+'-cares-build',[sys.executable,'-B',source/'tools/dns_provider/build_dependency.py','--archive',archive,'--output',dependency,'--jobs','4'],env=dependency_env,timeout=1200)
   cares=dependency/'prefix';cache=(dependency/'build/CMakeCache.txt').read_text();assert 'CARES_STATIC_PIC:BOOL=ON' in cache and 'CMAKE_C_FLAGS:STRING='+dependency_env['CFLAGS'] in cache
   record=json.loads((cares/'share/cares-source.json').read_text());assert record['archive_sha256']=='9364b70a12eb59a06830fb488d9357f90100dff0d98b23ea3593a183d43e6f2f'
   nm=Path(doctor['native_compiler']).with_name('llvm-nm');nm=str(nm) if nm.is_file() else shutil.which('llvm-nm') or shutil.which('nm');assert nm
   symbols=run(mode+'-cares-symbols',[nm,'-u',cares/'lib/libcares.a'],env=environment).stdout
   if mode!='normal':assert ('__asan_init' if mode=='ASAN-UBSAN' else '__tsan_init') in symbols
   report.setdefault('instrumented_cares',{})[mode]={'static_library_sha256':record['static_library_sha256'],'CFLAGS':dependency_env['CFLAGS'],'compiler':str(ccompiler),'symbol_probe':mode+'-cares-symbols.stdout','complete_license_sha256':record['license_sha256']};save()
   build=folder/'host-build';cmake=['cmake','-S',HERE,'-B',build,'-DNEX_SOURCE='+str(source),'-DCMAKE_CXX_COMPILER='+doctor['native_compiler'],'-DCMAKE_BUILD_TYPE=RelWithDebInfo','-DCMAKE_EXPORT_COMPILE_COMMANDS=ON','-DCMAKE_CXX_FLAGS='+' '.join(['-O1','-g',*flags]),'-DCMAKE_EXE_LINKER_FLAGS='+' '.join(flags)]
   cmake+=['-DOPENSSL_INCLUDE_DIR='+doctor['native_openssl_include'],'-DOPENSSL_CRYPTO_LIBRARY='+doctor['native_openssl_crypto'],'-DOPENSSL_SSL_LIBRARY='+doctor['native_openssl_ssl']]
   run(mode+'-configure',cmake,env=env);run(mode+'-build',['cmake','--build',build,'-j','2'],env=env,timeout=1200);binary=build/'dns_typed_host';report.setdefault('binary_sha256',{})[mode]=sha(binary)
   for capacity,transport,host_mode in [(16,'IPv4','full'),(1,'IPv4','capacity'),(16,'IPv6','ipv6')]:
    peer=ipv6 if transport=='IPv6' else peers;label=mode+'-'+str(capacity)+'-'+transport;targets=folder/(label+'-targets.json');write(targets,{'schema':'nex.dns-targets/1','maximum_calls':capacity,'resolvers':[{'address':'::1' if transport=='IPv6' else '127.0.0.1','port':peer.port}],'authorities':[{'name':'public','domain':'example.test','subdomains':True}]});project=folder/(label+'-project')
    before=peer.count();run(label+'-prepare',[sys.executable,'-B',source/'tools/dns_provider/prepare.py','--sdk',sdk,'--targets',targets,'--cares-prefix',cares,'--output',project,'--cxx',driver,'--diagnostics'],env=env)
    prepared=json.loads((project/'evidence/report.json').read_text());assert prepared['ok'] and not prepared['network_executed'] and not prepared['module_initialized'] and peer.count()==before;pin=prepared['manifest_sha256'];bindings={}
    for name in ('lookup','statistics'):bindings[name]={'schema':'nex.foreign-binding/1','library':'dns','export':name,'manifest_sha256':pin,'signature':json.loads((project/'evidence'/('signature-'+name+'.stdout')).read_text())}
    catalogue=json.loads((project/'foreign.json').read_text());catalogue['module_limit']=2;write(project/'two-context-foreign.json',catalogue);write(project/'host-input.json',bindings)
    for index in range(args.repeats):
     run_id=label+'-'+str(index);before=peer.count();p=run(run_id,[binary,project,files,run_id,host_mode],env=env,timeout=180);observed=json.loads(p.stdout);expected=15 if host_mode=='full' else 4 if host_mode=='ipv6' else 1;assert observed['ok'] and len(observed['checks'])==expected and len(set(observed['checks']))==expected
     counters=[json.loads(s) for s in re.findall(r'NEX_DNS_RETIRE (\{[^\n]+\})',p.stderr)];assert counters and all(v['live']==0 and v['opened']==v['closed'] for v in counters),(run_id,p.stderr)
     events=peer.events[before:];assert events and {v['qtype'] for v in events}=={1,28}
     if host_mode!='capacity':assert any(v['transport']=='tcp' for v in events)
     report['observations'].append({'mode':mode,'capacity':capacity,'resolver_transport':transport,'repeat':index,'checks':observed['checks'],'retired':counters,'DNS_events':events});save()
  report.update(ok=True,state='passed',actual_pinned_module_and_host_runtime=True,checks_per_mode=20*args.repeats,actual_cares_library_instrumented_with_host_and_module=True,Mac_leak_sanitizer_enabled=False if sys.platform=='darwin' else None,Linux_leak_sanitizer_enabled=True if sys.platform.startswith('linux') else None)
 except BaseException as error:report.update(state='failed',error=repr(error));raise
 finally:
  if peers:peers.close();report['peer_events']=peers.events
  if ipv6:ipv6.close();report['IPv6_peer_events']=ipv6.events
  save()
 print(json.dumps({k:report.get(k) for k in ('ok','state','error','checks_per_mode','seconds')}))
if __name__=='__main__':main()
