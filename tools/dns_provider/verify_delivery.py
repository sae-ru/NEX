#!/usr/bin/env python3
"""Check DNS operator rejection, client isolation and source-deleted delivery."""
import argparse,copy,hashlib,importlib.util,json,os
from pathlib import Path
import shutil,subprocess,sys,tempfile,time

HERE=Path(__file__).resolve().parent
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
prepare=load('nex_dns_prepare',HERE/'prepare.py');conformance=load('nex_dns_conformance',HERE/'verify.py')
def write(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def check_policy_rejections(out):
 target=out/'policy-input.json';good={'schema':'nex.dns-targets/1','resolvers':[{'address':'127.0.0.1','port':5353}],'authorities':[{'name':'public','domain':'example.test','subdomains':True}]};rows=[]
 def rejected(label,path):
  try:prepare.policy(path)
  except (ValueError,OSError) as error:rows.append({'case':label,'error':type(error).__name__})
  else:raise AssertionError('invalid DNS policy accepted: '+label)
 invalid=[('resolver-hostname',{'resolvers':[{'address':'localhost','port':53}]}),('resolver-scope',{'resolvers':[{'address':'fe80::1%en0','port':53}]}),('resolver-multicast',{'resolvers':[{'address':'224.0.0.1','port':53}]}),('resolver-unspecified',{'resolvers':[{'address':'::','port':53}]}),('port-bool',{'resolvers':[{'address':'127.0.0.1','port':True}]}),('port-zero',{'resolvers':[{'address':'127.0.0.1','port':0}]}),('port-overflow',{'resolvers':[{'address':'127.0.0.1','port':65536}]}),('duplicate-resolver',{'resolvers':good['resolvers']*2}),('empty-resolvers',{'resolvers':[]}),('too-many-resolvers',{'resolvers':[{'address':'127.0.0.1','port':5350+i} for i in range(5)]}),('empty-authorities',{'authorities':[]}),('duplicate-authority',{'authorities':good['authorities']*2}),('too-many-authorities',{'authorities':[dict(good['authorities'][0],name='n'+str(i)) for i in range(17)]}),('boolean-capacity',{'maximum_calls':True}),('zero-capacity',{'maximum_calls':0}),('large-capacity',{'maximum_calls':65}),('unknown-field',{'credential':'forbidden'})]
 for label,field,value in [('unicode-name','name','Я'),('path-name','name','../bad'),('empty-name','name',''),('unicode-domain','domain','пример.рф'),('empty-domain','domain',''),('NUL-domain','domain','a\0.test'),('long-label','domain','a'*64+'.test'),('double-dot','domain','a..test'),('hyphen-edge','domain','-bad.test'),('wildcard-not-explicit','domain','*'),('subdomains-not-bool','subdomains',1)]:
  row=dict(good['authorities'][0]);row[field]=value
  if label=='wildcard-not-explicit':row['subdomains']=False
  invalid.append((label,{'authorities':[row]}))
 for label,change in invalid:write(target,{**good,**change});rejected(label,target)
 for label,data in [('duplicate-JSON',b'{"schema":"nex.dns-targets/1","schema":"nex.dns-targets/1"}'),('invalid-UTF8',b'\xff'),('oversized-JSON',b' '*(1048576+1))]:target.write_bytes(data);rejected(label,target)
 write(target,good);link=out/'policy-link';link.symlink_to(target);rejected('symlink',link);fifo=out/'policy-pipe';(load('nex_windows_files_fixture',HERE.parent/'windows_files.py').nonregular_fixture(fifo) if os.name=='nt' else os.mkfifo(fifo));rejected('nonregular',fifo)
 write(target,{**good,'resolvers':[{'address':'::1','port':53}],'authorities':[{'name':'all','domain':'*','subdomains':True},{'name':'root','domain':'EXAMPLE.TEST.','subdomains':False}]});actual=prepare.policy(target);assert actual['authorities'][1]['domain']=='example.test' and actual['maximum_calls']==16
 return rows
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--sdk',type=Path);parser.add_argument('--cares-prefix',type=Path,required=True);parser.add_argument('--compiler',type=Path);parser.add_argument('--resources',type=Path);parser.add_argument('--output',type=Path);parser.add_argument('--package-notices',type=Path);args=parser.parse_args();cares=args.cares_prefix.resolve(strict=True)
 out=args.output.absolute() if args.output else Path(tempfile.mkdtemp(prefix='nex-dns-delivery-'));temporary=args.output is None
 if not temporary:out.mkdir(parents=True)
 shutil.copy2(__file__,out/'verify-input.py');started=time.monotonic();report={'schema':'nex.dns-provider-delivery/1','verification_source_sha256':sha(out/'verify-input.py'),'ok':False,'state':'starting','commands':[],'rejections':[],'source_ABI_changed':False,'full_objective_complete':False};peers=None
 def save():report['seconds']=time.monotonic()-started;write(out/'report.json',report)
 def run(label,argv,*,cwd=None,env=None,expected=0,parsed=True):
  argv=list(map(str,argv));row={'label':label,'argv':argv,'state':'running'};report['commands'].append(row);report['state']=label;save()
  p=subprocess.run(argv,cwd=cwd or out,env=env,capture_output=True,text=True,timeout=240);(out/(label+'.stdout')).write_text(p.stdout);(out/(label+'.stderr')).write_text(p.stderr);row.update(exit_code=p.returncode,state='passed' if p.returncode==expected else 'failed');save();assert p.returncode==expected,(label,p.stdout[-3000:]+p.stderr[-2000:]);return json.loads(p.stdout) if parsed else p
 try:
  if args.sdk:sdk=args.sdk.resolve(strict=True)
  else:
   if not args.compiler or not args.resources:parser.error('use --sdk, or both --compiler and --resources')
   sdk=out/'source-projection';(sdk/'bin').mkdir(parents=True);(sdk/'share').mkdir();shutil.copy2(args.compiler.resolve(strict=True),sdk/'bin/nex');(sdk/'share/nex').symlink_to(args.resources.resolve(strict=True),target_is_directory=True)
  report['source_projection']=not bool(args.sdk)
  compiler=sdk/'bin/nex';env={**os.environ,'NEX_RESOURCE_DIR':str(sdk/'share/nex'),'PYTHONDONTWRITEBYTECODE':'1'};env.pop('NEX_FOREIGN_CONFIG',None)
  files=out/'files';files.mkdir();peers=conformance.DNS(files)
  good={'schema':'nex.dns-targets/1','resolvers':[{'address':'127.0.0.1','port':peers.port}],'authorities':[{'name':'public','domain':'example.test','subdomains':True}]};target=out/'targets.json'
  report['rejections']+=check_policy_rejections(out);write(target,good)
  project=out/'original project % 🧠';run('prepare',[sys.executable,'-B',HERE/'prepare.py','--sdk',sdk,'--targets',target,'--cares-prefix',cares,'--output',project,'--diagnostics'],env=env,parsed=False)
  prepared=json.loads((project/'evidence/report.json').read_text());assert prepared['ok'] and not prepared['network_executed'] and not prepared['module_initialized'] and peers.count()==0
  shutil.copytree(project/'evidence',out/'prepared-evidence');shutil.copytree(project/'generated',out/'prepared-configuration')
  shutil.copy2(project/'bundle/manifest.json',out/'original-provider-manifest.json')
  report.update(compiler_sha256=sha(compiler),language=prepared['language'],toolchain=prepared['toolchain'],provider_module_sha256=prepared['module_sha256'])
  source=project/'main.nex';prefix=source.read_text().split('server fn main()->unit',1)[0];program=prefix+'server fn main()->unit !{task,ffi,io}{assert(len(statistics_raw())==4);assert(unwrap(dns::lookup(make_client(),"public","service.example.test",1000))==["127.0.0.42","2001:db8::42"]);print(42);}\n';source.write_text(program)
  host=project/'foreign.json';catalogue=json.loads(host.read_text());module=project/'bundle/module.so';module_bytes=module.read_bytes();policy=project/'bundle/targets.json';policy_bytes=policy.read_bytes()
  for kind,code in [('no-grant','E_FFI_GRANT'),('no-export','E_FFI_GRANT'),('wrong-pin','E_FFI_HASH'),('wrong-signature','E_FFI_SIGNATURE'),('changed-module','E_FFI_HASH'),('changed-target-file','E_FFI_HASH')]:
   source.write_text(program);write(host,catalogue);module.write_bytes(module_bytes);policy.write_bytes(policy_bytes);selected=copy.deepcopy(catalogue)
   if kind=='no-export':selected['libraries']['dns']['exports']=[];write(host,selected)
   if kind=='wrong-pin':source.write_text(program.replace(prepared['manifest_sha256'],'f'*64))
   if kind=='wrong-signature':source.write_text(program.replace('statistics_raw()->list<i64>','statistics_raw()->list<bool>'))
   if kind=='changed-module':module.write_bytes(module_bytes+b'\0')
   if kind=='changed-target-file':policy.write_bytes(policy_bytes+b' ')
   for mode in ('eval','debug','release'):
    before=peers.count();arguments=[compiler,'eval' if mode=='eval' else 'run','--task-workers','1','--json']
    if kind!='no-grant':arguments+=['--foreign',host]
    if mode!='eval':arguments+=['--profile',mode]
    observed=run(kind+'-'+mode,arguments,cwd=project,env={**env,'NEX_FOREIGN_CONFIG':str(host)},expected=1 if mode=='eval' else 70)
    if mode=='eval':assert observed.get('code')==code,observed
    else:
     diagnostics=observed.get('native_diagnostics',{}).get('diagnostics',[]);assert len(diagnostics)==1 and diagnostics[0]['report']['code']==code,observed
    assert peers.count()==before,(kind,mode);report['rejections'].append({'case':kind,'mode':mode,'code':code,'network_connections':0});save()
  source.write_text(program);write(host,catalogue);module.write_bytes(module_bytes);policy.write_bytes(policy_bytes)
  run('client-emission',[compiler,'emit','--kind','typescript','--entry','client_value','--directory',out/'client','--json'],cwd=project,env=env)
  for p in (out/'client').rglob('*'):
   if p.is_file():
    text=p.read_text();assert not any(v in text for v in ('lookup_raw','statistics_raw','make_client',prepared['manifest_sha256'],'example.test','127.0.0.1','module.so')),p
  rejected=prefix+'client fn forbidden()->result<list<str>> !{task,ffi}{return lookup_raw("public","service.example.test",64,1000);}\n';source.write_text(rejected)
  observed=run('client-realm-rejection',[compiler,'check','--json'],cwd=project,env=env,expected=1);assert observed['code']=='E_REALM',observed
  source.write_text(program)
  # The provider is project-owned code. Preserve its actual notice without
  # inventing a project license. Platform/system dependencies keep their rules.
  components=[{'name':'nex-dns-provider','version':prepared['toolchain'],'url':'https://github.com/sae-ru/NEX','roots':[str(project/'bundle')],'license_files':[str(project/'bundle'/n) for n in ('NOTICE','c-ares-LICENSE.txt','c-ares-SOURCE.json')]}]
  if args.package_notices:
   external=args.package_notices.resolve(strict=True);selected=json.loads(external.read_text());assert selected['schema']=='nex.sdk-notices/1'
   for row in selected['components']:
    item=dict(row)
    for field in ('roots','license_files'):item[field]=[str((external.parent/p).resolve(strict=True)) for p in row[field]]
    components.append(item)
  elif sys.platform=='darwin' and not (sdk/'share/nex/sdk-bundle.json').is_file():
   # A source projection has no bundled dependency inventory. Preserve the
   # actual installed OpenSSL license; never replace it with a fixture notice.
   doctor=run('package-doctor',[compiler,'doctor','--json'],env=env);crypto=Path(doctor['native_openssl_crypto']).resolve(strict=True);prefix=crypto.parent.parent;license=prefix/'LICENSE.txt'
   if not license.is_file():raise RuntimeError('unbundled OpenSSL requires --package-notices with its actual license')
   components.append({'name':'openssl','version':prefix.name,'url':'https://www.openssl.org/','roots':[str(crypto.parent)],'license_files':[str(license)]});report['OpenSSL_license_sha256']=sha(license)
  notices=out/'notices.json';write(notices,{'schema':'nex.sdk-notices/1','components':components})
  before=peers.count();package=out/'package';arguments=[compiler,'package','--foreign',host,'--notices',notices,'--directory',package,'--json']
  if sys.platform.startswith('linux'):arguments+=['--dpkg-notices']
  packaged=run('package',arguments,cwd=project,env=env);assert peers.count()==before
  application=json.loads((package/'application.json').read_text());assert application['execution_verified'] is False
  # Remove the original source, graph, provider image and operator catalogue;
  # execute only the relocated package with no compiler/resource environment.
  moved=out/'moved package % 🧠';package.rename(moved);shutil.rmtree(project);assert not project.exists()
  result=run('source-deleted-package',[moved/'bin/app'],cwd=files,env={'PATH':'/usr/bin:/bin','NEX_RESOURCE_DIR':str(out/'absent-sdk'),'NEX_FOREIGN_CONFIG':str(out/'absent-host.json')},parsed=False)
  assert result.stdout=='42\n' and peers.count()>=before+2,(result.stdout,result.stderr)
  actual=peers.events[before:];assert {v['qtype'] for v in actual}=={1,28} and all(v['name']=='service.example.test' for v in actual),actual
  licenses=list(moved.rglob('c-ares-LICENSE.txt'));assert licenses and all(sha(v)==prepared['cares_license_sha256'] for v in licenses)
  sources=list(moved.rglob('c-ares-SOURCE.json'));assert sources and all(json.loads(v.read_text())['archive_sha256']==prepare.CARES_ARCHIVE_SHA256 for v in sources)
  write(out/'moved-inventory.json',{v.relative_to(moved).as_posix():{'sha256':sha(v),'bytes':v.stat().st_size} for v in moved.rglob('*') if v.is_file()})
  report.update(ok=True,state='passed',client_server_pruning=True,source_deleted_package=True,relocated_package=True,package_DNS_packets=len(actual),target_rejections=sum('mode' not in v for v in report['rejections']),authority_rejections=sum('mode' in v for v in report['rejections']),static_dependency_license_preserved=True)
 except BaseException as error:report.update(state='failed',error=repr(error));raise
 finally:
  if peers:peers.close();report['peer_events']=peers.events
  save()
 print(json.dumps({k:report.get(k) for k in ('ok','state','target_rejections','authority_rejections','source_deleted_package','seconds')}))
 if temporary and report['ok']:shutil.rmtree(out)
if __name__=='__main__':main()
