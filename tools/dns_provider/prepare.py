#!/usr/bin/env python3
"""Prepare a DNS module with compiled operator policy; execute no DNS lookup."""
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
RUNTIME_FILES=('nex_ffi.h','nex_ffi_module.h','nex_error.h','nex_resource.h',
               'nex_resource_region.h','nex_resource_executor.h')
CARES_VERSION='1.34.9'
CARES_MAC_PATCH_SHA256='908c595efdeba68c8abb40ef81c0fe3f36c07ef4c5b3c895dbf82bd99ddd0d24'
CARES_ARCHIVE_SHA256='9364b70a12eb59a06830fb488d9357f90100dff0d98b23ea3593a183d43e6f2f'
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def canonical(name):
    if not isinstance(name,str):raise ValueError('domain must be a string')
    if name.endswith('.'):name=name[:-1]
    if not 1<=len(name)<=253 or not name.isascii():raise ValueError('DNS names require ASCII or explicit IDNA A-labels')
    for label in name.split('.'):
        if not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?',label):raise ValueError('invalid DNS label')
    return name.lower()
def policy(path):
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('duplicate DNS policy field')
            result[key]=value
        return result
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size>1048576:raise ValueError('policy must be a regular file of at most1MiB')
        data=bytearray()
        while True:
            chunk=os.read(fd,min(65536,1048577-len(data)))
            if not chunk:break
            data.extend(chunk)
            if len(data)>1048576:raise ValueError('DNS policy grew beyond1MiB')
    finally:os.close(fd)
    value=json.loads(data.decode('utf-8'),object_pairs_hook=unique)
    if not isinstance(value,dict) or not {'schema','resolvers','authorities'}<=set(value)<={'schema','resolvers','authorities','maximum_calls'} or value['schema']!='nex.dns-targets/1':raise ValueError('expected nex.dns-targets/1')
    maximum=value.get('maximum_calls',16)
    if type(maximum) is not int or not 1<=maximum<=64:raise ValueError('maximum_calls must be1..64')
    if not isinstance(value['resolvers'],list) or not 1<=len(value['resolvers'])<=4:raise ValueError('provide1..4 explicit DNS resolvers')
    resolvers=[];seen=set()
    for row in value['resolvers']:
        if not isinstance(row,dict) or set(row)!={'address','port'} or not isinstance(row['address'],str) or '%' in row['address'] or type(row['port']) is not int or not 1<=row['port']<=65535:raise ValueError('resolver needs a numeric address and port1..65535')
        address=ipaddress.ip_address(row['address']);key=(str(address),row['port'])
        if address.is_unspecified or address.is_multicast or key in seen:raise ValueError('resolver must be unique unicast address')
        seen.add(key);resolvers.append({'address':key[0],'port':key[1]})
    if not isinstance(value['authorities'],list) or not 1<=len(value['authorities'])<=16:raise ValueError('provide1..16 DNS authorities')
    authorities=[];seen=set()
    for row in value['authorities']:
        if not isinstance(row,dict) or set(row)!={'name','domain','subdomains'}:raise ValueError('authority needs name/domain/subdomains')
        name=row['name']
        if not isinstance(name,str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}',name) or name in seen or type(row['subdomains']) is not bool:raise ValueError('invalid or duplicate DNS authority')
        domain=row['domain']
        if domain=='*':
            if not row['subdomains']:raise ValueError('explicit wildcard authority requires subdomains=true')
        else:domain=canonical(domain)
        seen.add(name);authorities.append({'name':name,'domain':domain,'subdomains':row['subdomains']})
    return {'schema':'nex.dns-targets/1','maximum_calls':maximum,'resolvers':resolvers,'authorities':authorities}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk',type=Path,required=True);parser.add_argument('--targets',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--cares-prefix',type=Path);parser.add_argument('--cxx');parser.add_argument('--check-sdk',action='store_true');parser.add_argument('--diagnostics',action='store_true')
    args=parser.parse_args();configuration=policy(args.targets);sdk=args.sdk.resolve(strict=True);resources=sdk/'share/nex';compiler=sdk/'bin/nex';out=args.output.absolute()
    if os.path.lexists(out):parser.error('output must be new')
    if platform.system() not in ('Darwin','Linux') or platform.machine() not in ('arm64','aarch64','x86_64','AMD64'):parser.error('DNS provider needs64-bit macOS/Linux')
    if not compiler.is_file() or not resources.is_dir():parser.error('SDK requires bin/nex and share/nex')
    if not args.check_sdk and args.cares_prefix is None:parser.error('select the static PIC c-ares prefix with --cares-prefix')
    for name in RUNTIME_FILES:
        if not (resources/'runtime'/name).is_file():parser.error('SDK lacks runtime header '+name)
    out.mkdir(parents=True);evidence=out/'evidence';evidence.mkdir();commands=[];environment={**os.environ,'NEX_RESOURCE_DIR':str(resources),'PYTHONDONTWRITEBYTECODE':'1'}
    def run(label,argv):
        argv=list(map(str,argv));p=subprocess.run(argv,cwd=out,env=environment,capture_output=True,text=True,timeout=180)
        (evidence/(label+'.stdout')).write_text(p.stdout);(evidence/(label+'.stderr')).write_text(p.stderr);commands.append({'label':label,'argv':argv,'exit_code':p.returncode})
        if p.returncode:raise RuntimeError(label+': '+p.stdout[-3000:]+p.stderr[-2500:])
        return p.stdout
    report={'schema':'nex.dns-provider-preparation/1','ok':False,'network_executed':False,'module_initialized':False,'native_provider_built':False,'commands':commands}
    try:
        descriptor=json.loads(run('describe',[compiler,'describe','--json']));doctor=json.loads(run('doctor',[compiler,'doctor','--json']));language=descriptor['version'];pack=json.loads((resources/'llm/language-pack.json').read_text())
        if language not in ('0.24','0.25','0.26','0.27') or doctor.get('language')!=language or pack.get('language_version')!=language:raise RuntimeError('compiler/doctor/pack must agree on a supported public language0.24,0.25,0.26 or0.27')
        if descriptor.get('foreign_boundary',{}).get('source_support') is not True or descriptor.get('structured_tasks_runtime',{}).get('source_support') is not True:raise RuntimeError('SDK needs checked source task/ffi')
        (out/'stdlib').mkdir();shutil.copy2(ROOT/'lib/dns.nex',out/'stdlib/dns.nex');write(out/'nex.json',{'schema':'nex.project/1','language':language,'entry':'main.nex','libraries':{'std':'./stdlib'}})
        first=configuration['authorities'][0];example=first['domain'] if first['domain']!='*' else 'example.test'
        template=(Path(__file__).parent/'main.nex.in').read_text().replace('@AUTHORITY@',first['name']).replace('@HOSTNAME@',example)
        (out/'main.nex').write_text(template.replace('@PIN@','0'*64));run('check-template',[compiler,'check','--json']);run('test-library',[compiler,'test','stdlib/dns.nex','--json'])
        signatures={}
        for exported,local in [('lookup','lookup_raw'),('statistics','statistics_raw')]:
            value=json.loads(run('signature-'+exported,[compiler,'ffi','--symbol',local,'--json']));signatures[exported]=hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
        report.update(compiler_sha256=sha(compiler),toolchain=doctor['version'],language=language,signature_sha256=signatures)
        if args.check_sdk:report['ok']=True;return
        inputs=evidence/'inputs';(inputs/'runtime').mkdir(parents=True);(inputs/'cares/include').mkdir(parents=True)
        for name in RUNTIME_FILES:shutil.copy2(resources/'runtime'/name,inputs/'runtime'/name)
        for name in ('module.cpp','prepare.py','main.nex.in','build_dependency.py','resolver.hpp'):shutil.copy2(Path(__file__).parent/name,inputs/name)
        shutil.copy2(out/'stdlib/dns.nex',inputs/'dns.nex')
        prefix=args.cares_prefix.resolve(strict=True);record=json.loads((prefix/'share/cares-source.json').read_text())
        if record.get('schema')!='nex.cares-install/1' or record.get('version')!=CARES_VERSION or record.get('archive_sha256')!=CARES_ARCHIVE_SHA256 or record.get('static_PIC') is not True:raise RuntimeError('c-ares prefix must come from the pinned static PIC dependency builder')
        if platform.system()=='Darwin':
            patches=record.get('local_source_patches',[])
            if len(patches)!=1 or patches[0].get('patch_sha256')!=CARES_MAC_PATCH_SHA256:raise RuntimeError('macOS c-ares prefix requires the recorded NEX alignment patch; rebuild it with the installed dependency builder')
        for name,digest in record['headers'].items():
            if Path(name).name!=name or not name.startswith('ares') or not name.endswith('.h'):raise RuntimeError('invalid c-ares header inventory')
            source=prefix/'include'/name
            if sha(source)!=digest:raise RuntimeError('c-ares header changed')
            shutil.copy2(source,inputs/'cares/include'/name)
            if sha(inputs/'cares/include'/name)!=digest:raise RuntimeError('c-ares header changed during capture')
        library=prefix/record['static_library'];license=prefix/record['license']
        if library.resolve().parent!=prefix/'lib' or license.resolve().parent!=prefix/'share/licenses/c-ares' or sha(library)!=record['static_library_sha256'] or sha(license)!=record['license_sha256']:raise RuntimeError('c-ares library/license inventory differs')
        shutil.copy2(library,inputs/'cares/libcares.a');shutil.copy2(license,inputs/'cares/LICENSE.txt');write(inputs/'cares/SOURCE.json',record)
        generated=out/'generated';generated.mkdir();write(generated/'targets.json',configuration)
        servers=','.join(('['+p['address']+']' if ':' in p['address'] else p['address'])+':'+str(p['port']) for p in configuration['resolvers'])
        header='#pragma once\n#include <array>\n#include <string>\nstruct Authority {std::string name,domain;bool subdomains;};\n'
        header+=''.join('#define PIN_'+name.upper()+' '+json.dumps(value)+'\n' for name,value in signatures.items())
        header+='#define NEX_DNS_MAX_CALLS '+str(configuration['maximum_calls'])+'\n#define NEX_DNS_DIAGNOSTICS '+str(int(args.diagnostics))+'\ninline constexpr char operatorServers[]='+json.dumps(servers)+';\n'
        header+='inline const std::array<Authority,'+str(len(configuration['authorities']))+'> operatorAuthorities{{\n'+',\n'.join('{'+json.dumps(x['name'])+','+json.dumps(x['domain'])+','+str(x['subdomains']).lower()+'}' for x in configuration['authorities'])+'\n}};\n';(generated/'operator_targets.h').write_text(header)
        bundle=out/'bundle';bundle.mkdir();cxx=args.cxx or doctor['native_compiler']
        if not Path(cxx).is_file():raise RuntimeError('operator-selected C++20 compiler is missing')
        command=[cxx,'-std=c++20','-O2','-pthread','-shared','-fPIC','-fvisibility=hidden','-DCARES_STATICLIB','-I'+str(inputs/'runtime'),'-I'+str(inputs/'cares/include'),'-I'+str(generated),inputs/'module.cpp',inputs/'cares/libcares.a','-o',bundle/'module.so']
        if platform.system()=='Darwin':command+=['-lresolv','-Wl,-exported_symbol,_nex_ffi_module_entry']
        else:command+=['-Wl,--exclude-libs,ALL']
        run('compile-module',command)
        for source,target in [(generated/'targets.json','targets.json'),(inputs/'cares/LICENSE.txt','c-ares-LICENSE.txt'),(inputs/'cares/SOURCE.json','c-ares-SOURCE.json')]:shutil.copy2(source,bundle/target)
        (bundle/'NOTICE').write_text('NEX DNS provider\nOriginal NEX runtime and adapter sources.\nc-ares1.34.9 is statically linked; its complete license, source identity and any recorded local source patches are included.\n')
        names=['module.so','targets.json','NOTICE','c-ares-LICENSE.txt','c-ares-SOURCE.json']
        manifest={'schema':'nex.foreign-bundle/1','platform':('macos' if platform.system()=='Darwin' else 'linux')+'-'+('arm64' if platform.machine() in ('arm64','aarch64') else 'x86_64'),'entry':'module.so','files':[{'path':n,'sha256':sha(bundle/n)} for n in names],'exports':signatures,'notices':['NOTICE','c-ares-LICENSE.txt','c-ares-SOURCE.json']};write(bundle/'manifest.json',manifest)
        pin=sha(bundle/'manifest.json');(out/'main.nex').write_text(template.replace('@PIN@',pin));write(out/'foreign.json',{'schema':'nex.foreign-host/1','module_limit':1,'libraries':{'dns':{'directory':'./bundle','manifest_sha256':pin,'exports':list(signatures)}}})
        run('check-pinned',[compiler,'check','--json']);catalogue=json.loads(run('catalogue',[compiler,'foreign',out/'foreign.json','--json']));assert catalogue['module_initialization'] is False
        report.update(ok=True,native_provider_built=True,manifest_sha256=pin,module_sha256=sha(bundle/'module.so'),operator_targets_sha256=sha(generated/'targets.json'),cares_static_library_sha256=record['static_library_sha256'],cares_license_sha256=record['license_sha256'],input_sha256={p.relative_to(inputs).as_posix():sha(p) for p in inputs.rglob('*') if p.is_file()})
    except BaseException as error:report['error']=repr(error);raise
    finally:write(evidence/'report.json',report)

if __name__=='__main__':main()
