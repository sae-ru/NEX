#!/usr/bin/env python3
"""Prepare a pinned TCP provider from operator targets; execute no network calls."""
import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import subprocess

ROOT=Path(__file__).resolve().parents[2]
RUNTIME_FILES=('nex_task_network.h','nex_task_network.cpp','nex_task_external.h',
 'nex_resource.h','nex_resource_region.h','nex_resource_executor.h','nex_error.h',
 'nex_ffi.h','nex_ffi_module.h')
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def targets(path):
 def unique(pairs):
  result={}
  for key,value in pairs:
   if key in result:raise ValueError('duplicate target JSON field')
   result[key]=value
  return result
 descriptor=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
 try:
  info=os.fstat(descriptor)
  if not stat.S_ISREG(info.st_mode) or info.st_size>1048576:raise ValueError('targets must be a regular file of at most1MiB')
  data=bytearray()
  while True:
   block=os.read(descriptor,min(65536,1048577-len(data)))
   if not block:break
   data.extend(block)
   if len(data)>1048576:raise ValueError('target file grew beyond1MiB')
 finally:os.close(descriptor)
 value=json.loads(data.decode('utf-8'),object_pairs_hook=unique)
 if not isinstance(value,dict) or not {'schema','endpoints'}<=set(value)<={'schema','endpoints','maximum_connections'} or value['schema']!='nex.tcp-targets/1':raise ValueError('expected nex.tcp-targets/1')
 maximum=value.get('maximum_connections',16)
 if type(maximum) is not int or not 1<=maximum<=64:raise ValueError('maximum_connections must be1..64')
 rows=value['endpoints']
 if not isinstance(rows,list) or not 1<=len(rows)<=16:raise ValueError('provide1..16 endpoints')
 names=set();normalized=[]
 for row in rows:
  if not isinstance(row,dict) or set(row)!={'name','address','port'}:raise ValueError('endpoint requires only name/address/port')
  name,address,port=row['name'],row['address'],row['port']
  if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}',name) or name in names:raise ValueError('invalid or duplicate endpoint name')
  if not isinstance(address,str) or '%' in address or type(port) is not int or not 1<=port<=65535:raise ValueError('endpoint needs a numeric address and port1..65535')
  normalized.append({'name':name,'address':str(ipaddress.ip_address(address)),'port':port});names.add(name)
 return {'schema':'nex.tcp-targets/1','maximum_connections':maximum,'endpoints':normalized}
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--sdk',type=Path,required=True);parser.add_argument('--targets',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
 parser.add_argument('--cxx');parser.add_argument('--check-sdk',action='store_true');parser.add_argument('--diagnostics',action='store_true',help='emit bounded socket-retirement counters to stderr when the module retires')
 args=parser.parse_args();configuration=targets(args.targets);sdk=args.sdk.resolve(strict=True);compiler=sdk/'bin/nex';resources=sdk/'share/nex';out=args.output.absolute()
 if os.path.lexists(out):parser.error('output must be new')
 if platform.system() not in ('Darwin','Linux') or platform.machine() not in ('arm64','aarch64','x86_64','AMD64'):parser.error('TCP provider preparation requires64-bit macOS/Linux')
 if not compiler.is_file() or not resources.is_dir():parser.error('SDK requires bin/nex and share/nex')
 for name in RUNTIME_FILES:
  if not (resources/'runtime'/name).is_file():parser.error('SDK lacks TCP host kernel resource '+name)
 out.mkdir(parents=True);evidence=out/'evidence';evidence.mkdir();commands=[];environment={**os.environ,'NEX_RESOURCE_DIR':str(resources),'PYTHONDONTWRITEBYTECODE':'1'}
 def run(label,argv):
  argv=list(map(str,argv));p=subprocess.run(argv,cwd=out,env=environment,capture_output=True,text=True,timeout=180)
  (evidence/(label+'.stdout')).write_text(p.stdout);(evidence/(label+'.stderr')).write_text(p.stderr);commands.append({'label':label,'argv':argv,'exit_code':p.returncode})
  if p.returncode:raise RuntimeError(label+': '+p.stdout[-3000:]+p.stderr[-2000:])
  return p.stdout
 report={'schema':'nex.tcp-provider-preparation/1','ok':False,'network_executed':False,'module_initialized':False,'native_provider_built':False,'diagnostics':args.diagnostics,'commands':commands}
 try:
  descriptor=json.loads(run('describe',[compiler,'describe','--json']));doctor=json.loads(run('doctor',[compiler,'doctor','--json']));language=descriptor['version']
  pack=json.loads((resources/'llm/language-pack.json').read_text())
  if doctor.get('language')!=language or pack.get('language_version')!=language:raise RuntimeError('compiler, doctor and installed language pack disagree')
  if descriptor.get('foreign_boundary',{}).get('source_support') is not True or descriptor.get('structured_tasks_runtime',{}).get('source_support') is not True or int(language.split('.')[1])<22:raise RuntimeError('SDK needs source task/ffi with copied value transport')
  (out/'stdlib').mkdir();shutil.copy2(ROOT/'lib/tcp.nex',out/'stdlib/tcp.nex');write(out/'nex.json',{'schema':'nex.project/1','language':language,'entry':'main.nex','libraries':{'std':'./stdlib'}})
  template=(Path(__file__).parent/'main.nex.in').read_text().replace('@ENDPOINT@',configuration['endpoints'][0]['name']);(out/'main.nex').write_text(template.replace('@PIN@','0'*64));run('check-template',[compiler,'check','--json']);run('test-library',[compiler,'test','stdlib/tcp.nex','--json'])
  signatures={}
  for exported,local in [('exchange','exchange_raw'),('statistics','statistics_raw')]:
   value=json.loads(run('signature-'+exported,[compiler,'ffi','--symbol',local,'--json']));signatures[exported]=hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
  generated=out/'generated';generated.mkdir();inputs=evidence/'inputs';inputs.mkdir();(inputs/'runtime').mkdir()
  for name in RUNTIME_FILES:shutil.copy2(resources/'runtime'/name,inputs/'runtime'/name)
  for name in ('module.cpp','main.nex.in','prepare.py'):shutil.copy2(Path(__file__).parent/name,inputs/name)
  shutil.copy2(out/'stdlib/tcp.nex',inputs/'tcp.nex')
  header='''#pragma once
#include <array>
'''+''.join('#define PIN_'+name.upper()+' "'+digest+'"\n' for name,digest in signatures.items())+'#define NEX_TCP_DIAGNOSTICS '+str(int(args.diagnostics))+'\n#define NEX_TCP_MAX_CONNECTIONS '+str(configuration['maximum_connections'])+'\ninline const std::array<nexrt::TaskTcpEndpoint,'+str(len(configuration['endpoints']))+'> operatorTargets{{\n'+',\n'.join('{'+json.dumps(x['name'])+','+json.dumps(x['address'])+','+str(x['port'])+'}' for x in configuration['endpoints'])+'\n}};\n'
  (generated/'operator_targets.h').write_text(header);write(generated/'targets.json',configuration)
  report.update(compiler_sha256=sha(compiler),toolchain=doctor['version'],language=language,signature_sha256=signatures,operator_targets_sha256=sha(generated/'targets.json'),runtime_source_sha256={n:sha(inputs/'runtime'/n) for n in RUNTIME_FILES},input_sha256={p.relative_to(inputs).as_posix():sha(p) for p in inputs.rglob('*') if p.is_file()})
  if args.check_sdk:report['ok']=True;return
  cxx=args.cxx or doctor['native_compiler']
  if not isinstance(cxx,str) or not Path(cxx).is_file():raise RuntimeError('a real operator-selected C++20 compiler is required')
  bundle=out/'bundle';bundle.mkdir()
  run('compile-module',[cxx,'-std=c++20','-O2','-pthread','-shared','-fPIC','-fvisibility=hidden','-I'+str(inputs/'runtime'),'-I'+str(generated),inputs/'module.cpp',inputs/'runtime/nex_task_network.cpp','-o',bundle/'module.so'])
  shutil.copy2(generated/'targets.json',bundle/'targets.json');(bundle/'NOTICE').write_text('NEX TCP provider\nOriginal NEX runtime and adapter sources.\nBuilt with the operator-selected platform C++ SDK.\n')
  manifest={'schema':'nex.foreign-bundle/1','platform':('macos' if platform.system()=='Darwin' else 'linux')+'-'+('arm64' if platform.machine() in ('arm64','aarch64') else 'x86_64'),'entry':'module.so','files':[{'path':n,'sha256':sha(bundle/n)} for n in ['module.so','targets.json','NOTICE']],'exports':signatures,'notices':['NOTICE']}
  write(bundle/'manifest.json',manifest);pin=sha(bundle/'manifest.json');(out/'main.nex').write_text(template.replace('@PIN@',pin));write(out/'foreign.json',{'schema':'nex.foreign-host/1','module_limit':1,'libraries':{'tcp':{'directory':'./bundle','manifest_sha256':pin,'exports':list(signatures)}}})
  run('check-pinned',[compiler,'check','--json']);catalogue=json.loads(run('catalogue',[compiler,'foreign',out/'foreign.json','--json']));assert catalogue['module_initialization'] is False
  report.update(ok=True,native_provider_built=True,module_sha256=sha(bundle/'module.so'),manifest_sha256=pin,source_sha256=sha(out/'main.nex'),generated_header_sha256=sha(generated/'operator_targets.h'),cxx=cxx)
 finally:write(evidence/'report.json',report)
if __name__=='__main__':main()
