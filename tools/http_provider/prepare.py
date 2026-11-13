#!/usr/bin/env python3
"""Prepare a pinned typed HTTP provider from explicit operator authority."""
import argparse
import hashlib
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import subprocess
import struct
from dependency_contract import validate_http

ROOT=Path(__file__).resolve().parents[2]
RUNTIME=('nex_socket_platform.h','nex_ffi.h','nex_ffi_module.h','nex_error.h','nex_resource.h','nex_resource_region.h','nex_resource_executor.h')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def regular(path,maximum):
 if os.name=='nt':
  import importlib.util
  spec=importlib.util.spec_from_file_location('_nex_windows_files',Path(__file__).resolve().parents[1]/'windows_files.py')
  module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  return module.regular(path,maximum)
 fd=os.open(path,os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW|os.O_NONBLOCK)
 try:
  s=os.fstat(fd)
  if not stat.S_ISREG(s.st_mode) or s.st_size>maximum:raise ValueError('operator input must be regular and bounded')
  data=bytearray()
  while True:
   block=os.read(fd,min(65536,maximum+1-len(data)))
   if not block:break
   data.extend(block)
   if len(data)>maximum:raise ValueError('operator input grew beyond its limit')
  return bytes(data)
 finally:os.close(fd)
def pairs(values):
 result={}
 for k,v in values:
  if k in result:raise ValueError('duplicate HTTP policy field')
  result[k]=v
 return result
def domain(value):
 if not isinstance(value,str) or not value.isascii() or '%' in value:raise ValueError('domain requires ASCII without IPv6 scope')
 if value=='*':return value,False
 try:ip=ipaddress.ip_address(value)
 except ValueError:
  if ':' in value:raise
 else:
  if ip.is_unspecified or ip.is_multicast or ip.version==4 and int(ip)==4294967295:raise ValueError('invalid HTTP target IP')
  return str(ip),True
 if value.endswith('.'):value=value[:-1]
 if not 1<=len(value)<=253 or any(not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?',s) for s in value.split('.')):raise ValueError('invalid HTTP domain')
 return value.lower(),False
def policy(path):
 value=json.loads(regular(path,1048576).decode('utf-8'),object_pairs_hook=pairs)
 if not isinstance(value,dict) or not {'schema','resolvers','authorities'}<=set(value)<={'schema','resolvers','authorities','maximum_calls','ca_file'} or value['schema']!='nex.http-targets/1':raise ValueError('expected nex.http-targets/1')
 maximum=value.get('maximum_calls',16)
 if type(maximum) is not int or not 1<=maximum<=64:raise ValueError('maximum_calls must be1..64')
 if not isinstance(value['resolvers'],list) or not 1<=len(value['resolvers'])<=4:raise ValueError('provide1..4 DNS resolvers')
 resolvers=[];seen=set()
 for row in value['resolvers']:
  if not isinstance(row,dict) or set(row)!={'address','port'} or not isinstance(row['address'],str) or '%' in row['address'] or type(row['port']) is not int or not 1<=row['port']<=65535:raise ValueError('invalid resolver')
  ip=ipaddress.ip_address(row['address']);key=(str(ip),row['port'])
  if ip.is_unspecified or ip.is_multicast or ip.version==4 and int(ip)==4294967295 or key in seen:raise ValueError('resolver must be unique unicast')
  seen.add(key);resolvers.append({'address':str(ip),'port':row['port']})
 if not isinstance(value['authorities'],list) or not 1<=len(value['authorities'])<=16:raise ValueError('provide1..16 HTTP authorities')
 rules=[];seen=set()
 for row in value['authorities']:
  needed={'name','domain','subdomains','schemes','ports','methods'}
  if not isinstance(row,dict) or not needed<=set(row)<=needed|{'cross_origin_redirects'}:raise ValueError('invalid HTTP authority fields')
  name=row['name']
  if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}',name) or name in seen or type(row['subdomains']) is not bool or type(row.get('cross_origin_redirects',False)) is not bool:raise ValueError('invalid authority name or switches')
  host,numeric=domain(row['domain'])
  if host=='*' and not row['subdomains'] or numeric and row['subdomains']:raise ValueError('wildcard must be explicit; IP has no subdomains')
  if not isinstance(row['schemes'],list) or not 1<=len(row['schemes'])<=2 or any(v not in ('http','https') for v in row['schemes']) or len(set(row['schemes']))!=len(row['schemes']):raise ValueError('schemes must be unique http/https')
  if not isinstance(row['ports'],list) or not 1<=len(row['ports'])<=16 or any(type(v) is not int or not 1<=v<=65535 for v in row['ports']) or len(set(row['ports']))!=len(row['ports']):raise ValueError('ports must be unique1..65535')
  if not isinstance(row['methods'],list) or not 1<=len(row['methods'])<=16 or any(not isinstance(v,str) or not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]{1,32}",v) or v.lower()=='connect' for v in row['methods']) or len(set(row['methods']))!=len(row['methods']):raise ValueError('invalid or duplicate HTTP methods')
  seen.add(name);rules.append({'name':name,'domain':host,'subdomains':row['subdomains'],'schemes':row['schemes'],'ports':row['ports'],'methods':row['methods'],'cross_origin_redirects':row.get('cross_origin_redirects',False)})
 ca=b''
 if 'ca_file' in value:
  if not isinstance(value['ca_file'],str):raise ValueError('ca_file must be a path')
  ca_path=Path(value['ca_file']);ca_path=ca_path if ca_path.is_absolute() else path.absolute().parent/ca_path;ca=regular(ca_path,1048576)
  if not ca.isascii() or b'PRIVATE KEY' in ca or b'-----BEGIN CERTIFICATE-----' not in ca:raise ValueError('CA bundle must contain public PEM certificates without private keys')
 if any('https' in row['schemes'] for row in rules) and not ca:raise ValueError('HTTPS requires an explicit public CA bundle')
 return {'schema':'nex.http-targets/1','maximum_calls':maximum,'resolvers':resolvers,'authorities':rules,'ca_sha256':hashlib.sha256(ca).hexdigest() if ca else None},ca
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--sdk',type=Path,required=True);parser.add_argument('--targets',type=Path,required=True);parser.add_argument('--http-prefix',type=Path);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--check-sdk',action='store_true');parser.add_argument('--diagnostics',action='store_true');parser.add_argument('--cxx');args=parser.parse_args();configuration,ca=policy(args.targets);sdk=args.sdk.resolve(strict=True);resources=sdk/'share/nex';compiler=sdk/'bin'/('nex.exe' if os.name=='nt' else 'nex');out=args.output.absolute()
 if os.path.lexists(out):parser.error('output must be new')
 if platform.system() not in ('Darwin','Linux','Windows') or struct.calcsize('P')!=8 or platform.machine().lower() not in ('arm64','aarch64','x86_64','amd64'):parser.error('HTTP provider requires64-bit macOS/Linux/Windows ARM64 or x86-64')
 if not args.check_sdk and not args.http_prefix:parser.error('select the pinned HTTP dependency prefix')
 out.mkdir(parents=True);evidence=out/'evidence';evidence.mkdir();env={**os.environ,'NEX_RESOURCE_DIR':str(resources),'PYTHONDONTWRITEBYTECODE':'1'};env.pop('NEX_FOREIGN_CONFIG',None);report={'schema':'nex.http-provider-preparation/1','ok':False,'network_executed':False,'module_initialized':False,'native_provider_built':False,'commands':[]}
 def run(label,argv):
  argv=list(map(str,argv))
  if label=='compile-module' and os.name=='nt':
   spec=importlib.util.spec_from_file_location('_nex_http_provider_sdk',ROOT/'tools/provider_sdk.py');helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
   p=helper.native_compile(argv,cwd=out,env=env,capture_output=True,text=True,timeout=240)
  else:p=subprocess.run(argv,cwd=out,env=env,capture_output=True,text=True,timeout=240)
  (evidence/(label+'.stdout')).write_text(p.stdout);(evidence/(label+'.stderr')).write_text(p.stderr);report['commands'].append({'label':label,'argv':list(map(str,argv)),'exit_code':p.returncode,**({'executed_argv':p.args,'link_staging':p.nex_link_staging,'requested_output':p.nex_requested_output,'staging_retained':p.returncode!=0} if hasattr(p,'nex_link_staging') else {})})
  if p.returncode:raise RuntimeError(label+': '+p.stdout[-2000:]+p.stderr[-2500:])
  return p.stdout
 try:
  descriptor=json.loads(run('describe',[compiler,'describe','--json']));doctor=json.loads(run('doctor',[compiler,'doctor','--json']));pack=json.loads((resources/'llm/language-pack.json').read_text());language=descriptor['version']
  if language not in ('0.24','0.25','0.26','0.27','0.28','0.29') or doctor['language']!=language or pack['language_version']!=language or not descriptor.get('foreign_boundary',{}).get('source_support') or not descriptor.get('structured_tasks_runtime',{}).get('source_support'):raise RuntimeError('SDK needs matching public language0.24,0.25,0.26,0.27 or0.28/source task/ffi')
  (out/'stdlib').mkdir();shutil.copy2(ROOT/'lib/http_client.nex',out/'stdlib/http_client.nex');write(out/'nex.json',{'schema':'nex.project/1','language':language,'entry':'main.nex','libraries':{'std':'./stdlib'}})
  first=configuration['authorities'][0];scheme='https' if 'https' in first['schemes'] else 'http';host=first['domain'] if first['domain']!='*' else 'example.test';host='['+host+']' if ':' in host else host;url=scheme+'://'+host+':'+str(first['ports'][0])+'/'
  template=(Path(__file__).parent/'main.nex.in').read_text().replace('@AUTHORITY@',first['name']).replace('@METHOD@',first['methods'][0]).replace('@URL@',url);(out/'main.nex').write_text(template.replace('@PIN@','0'*64));run('check-template',[compiler,'check','--json']);run('test-library',[compiler,'test','stdlib/http_client.nex','--json']);signatures={}
  for exported,local in [('send','send_raw'),('statistics','statistics_raw')]:
   data=json.loads(run('signature-'+exported,[compiler,'ffi','--symbol',local,'--json']));signatures[exported]=hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
  report.update(compiler_sha256=sha(compiler),toolchain=doctor['version'],language=language,signature_sha256=signatures)
  if args.check_sdk:report['ok']=True;return
  prefix=args.http_prefix.resolve(strict=True);record=json.loads((prefix/'share/http-source.json').read_text())
  validate_http(record,platform.system())
  if record.get('schema')!='nex.http-dependencies/1' or record['curl']['version']!='8.23.0' or record['nghttp2']['version']!='1.70.0' or not record['static_PIC'] or set(record['libraries'])!={'libcurl.a','libcares.a','libnghttp2.a'}:raise RuntimeError('HTTP dependency identity differs')
  for key in ('native_openssl_ssl','native_openssl_crypto'):
   if sha(Path(doctor[key]).resolve(strict=True))!=record['openssl_library_sha256'][key]:raise RuntimeError('selected SDK OpenSSL differs from HTTP dependency')
  inputs=evidence/'inputs';(inputs/'runtime').mkdir(parents=True);(inputs/'include').mkdir();(inputs/'lib').mkdir();(inputs/'licenses').mkdir()
  for name in RUNTIME:shutil.copy2(resources/'runtime'/name,inputs/'runtime'/name)
  for name in ['module.cpp','transport.hpp','prepare.py','main.nex.in','dependency_contract.py']:shutil.copy2(Path(__file__).parent/name,inputs/name)
  shutil.copy2(ROOT/'tools/dns_provider/resolver.hpp',inputs/'resolver.hpp');shutil.copy2(out/'stdlib/http_client.nex',inputs/'http_client.nex');write(inputs/'SOURCE.json',record)
  for name,h in record['libraries'].items():
   if Path(name).name!=name or sha(prefix/'lib'/name)!=h:raise RuntimeError('HTTP static library changed')
   shutil.copy2(prefix/'lib'/name,inputs/'lib'/name)
  for name,h in record['headers'].items():
   rel=Path(name)
   if rel.is_absolute() or '..' in rel.parts or sha(prefix/'include'/rel)!=h:raise RuntimeError('HTTP header inventory differs')
   target=inputs/'include'/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(prefix/'include'/rel,target)
  notices=[]
  for name,h in record['licenses'].items():
   rel=Path(name)
   if rel.is_absolute() or '..' in rel.parts or rel.parts[:2]!=('share','licenses') or sha(prefix/rel)!=h:raise RuntimeError('HTTP license identity differs')
   target=rel.parts[2]+'-LICENSE.txt';shutil.copy2(prefix/rel,inputs/'licenses'/target);notices.append(target)
  generated=out/'generated';generated.mkdir();write(generated/'targets.json',configuration);servers=','.join(('['+v['address']+']' if ':' in v['address'] else v['address'])+':'+str(v['port']) for v in configuration['resolvers'])
  header='#pragma once\n#define NEX_HTTP_MAX_CALLS '+str(configuration['maximum_calls'])+'\n#define NEX_HTTP_DIAGNOSTICS '+str(int(args.diagnostics))+'\n'+''.join('#define PIN_'+k.upper()+' '+json.dumps(v)+'\n' for k,v in signatures.items())
  rules=[]
  for v in configuration['authorities']:
   rules.append('{'+','.join([json.dumps(v['name']),json.dumps(v['domain']),str(v['subdomains']).lower(),'{'+','.join(map(json.dumps,v['schemes']))+'}','{'+','.join(map(json.dumps,v['methods']))+'}','{'+','.join(map(str,v['ports']))+'}',str(v['cross_origin_redirects']).lower()])+'}')
  header+='inline const nex_http::Config operatorConfig{'+json.dumps(servers)+','+json.dumps(ca.decode('ascii'))+',{'+','.join(rules)+'}};\n';(generated/'operator_targets.h').write_text(header)
  bundle=out/'bundle';bundle.mkdir();module=bundle/('module.dll' if os.name=='nt' else 'module.so');cxx=args.cxx or doctor['native_compiler'];command=[cxx,'-std=c++20','-O2','-pthread','-shared','-fPIC','-fvisibility=hidden','-DCURL_STATICLIB','-DCARES_STATICLIB','-DNGHTTP2_STATICLIB','-I'+str(inputs/'runtime'),'-I'+str(inputs/'include'),'-I'+str(generated),'-I'+str(Path(doctor['native_openssl_include']).resolve()),inputs/'module.cpp',inputs/'lib/libcurl.a',inputs/'lib/libnghttp2.a',inputs/'lib/libcares.a',Path(doctor['native_openssl_ssl']).resolve(),Path(doctor['native_openssl_crypto']).resolve(),'-o',module]
  if platform.system()=='Darwin':command+=['-lresolv','-framework','CoreFoundation','-framework','SystemConfiguration','-Wl,-exported_symbol,_nex_ffi_module_entry']
  elif os.name=='nt':command+=['-static','-lws2_32','-liphlpapi','-ladvapi32','-lcrypt32','-lbcrypt']
  else:command+=['-Wl,--exclude-libs,ALL']
  run('compile-module',command);shutil.copy2(generated/'targets.json',bundle/'targets.json');shutil.copy2(inputs/'SOURCE.json',bundle/'SOURCE.json')
  for name in notices:shutil.copy2(inputs/'licenses'/name,bundle/name)
  (bundle/'NOTICE').write_text('NEX typed HTTP provider. curl, nghttp2 and c-ares are statically linked; their complete licenses, source identities and recorded patches are included. OpenSSL is a separately selected SDK dependency.\n')
  names=[module.name,'targets.json','NOTICE','SOURCE.json',*notices];manifest={'schema':'nex.foreign-bundle/1','platform':('windows' if os.name=='nt' else 'macos' if platform.system()=='Darwin' else 'linux')+'-'+('arm64' if platform.machine() in ('arm64','aarch64') else 'x86_64'),'entry':module.name,'files':[{'path':n,'sha256':sha(bundle/n)} for n in names],'exports':signatures,'notices':['NOTICE','SOURCE.json',*notices]};write(bundle/'manifest.json',manifest);pin=sha(bundle/'manifest.json');(out/'main.nex').write_text(template.replace('@PIN@',pin));write(out/'foreign.json',{'schema':'nex.foreign-host/1','module_limit':1,'libraries':{'http':{'directory':'./bundle','manifest_sha256':pin,'exports':list(signatures)}}});run('check-pinned',[compiler,'check','--json']);catalogue=json.loads(run('catalogue',[compiler,'foreign',out/'foreign.json','--json']));assert catalogue['module_initialization'] is False
  report.update(ok=True,native_provider_built=True,manifest_sha256=pin,module_sha256=sha(module),dependency_record_sha256=sha(inputs/'SOURCE.json'),operator_targets_sha256=sha(generated/'targets.json'),input_sha256={p.relative_to(inputs).as_posix():sha(p) for p in inputs.rglob('*') if p.is_file()})
 except BaseException as error:report['error']=repr(error);raise
 finally:write(evidence/'report.json',report)
if __name__=='__main__':main()
