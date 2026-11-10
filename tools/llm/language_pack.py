"""Read-only, type-preserving validation of every declared shared capability field."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
MAX_BYTES=2*1024*1024


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def parse(raw):
    if len(raw)>MAX_BYTES:raise ValueError('JSON input exceeds2MiB')
    def pairs(items):
        result={}
        for key,value in items:
            if key in result:raise ValueError('duplicate JSON field: '+key)
            result[key]=value
        return result
    def invalid(value):raise ValueError('invalid JSON number: '+value)
    return json.loads(raw.decode('utf-8'),object_pairs_hook=pairs,parse_constant=invalid)


def compare(pack,descriptor,index):
    errors=[];compared=0
    def fail(path,reason):
        if len(errors)<64:errors.append({'path':path,'reason':reason})
    def equal(a,b,path,depth=0):
        nonlocal compared
        compared+=1
        if depth>64:fail(path,'JSON nesting exceeds64');return
        if type(a)is not type(b):fail(path,'JSON value types differ');return
        if isinstance(a,dict):
            for key in sorted(a.keys()|b.keys()):
                if key not in a or key not in b:fail(path+'.'+key,'field is missing')
                else:equal(a[key],b[key],path+'.'+key,depth+1)
        elif isinstance(a,list):
            if len(a)!=len(b):fail(path,'array lengths differ')
            for i,(x,y)in enumerate(zip(a,b)):equal(x,y,path+'.'+str(i),depth+1)
        elif a!=b:fail(path,'JSON values differ')
    if not all(isinstance(x,dict)for x in [pack,descriptor,index]):raise ValueError('expected JSON objects')
    if pack.get('schema')!='nex.language-pack/1'or descriptor.get('schema')!='nex.language/1':fail('schema','unexpected envelope schema')
    contract=descriptor.get('language_pack_contract',{})
    if contract.get('schema')!='nex.language-pack-contract/1':fail('language_pack_contract','missing comparison contract')
    fields=contract.get('shared_fields',[])
    if not isinstance(fields,list)or not fields or any(not isinstance(x,str)for x in fields):raise ValueError('invalid shared_fields')
    if fields!=sorted(set(fields)):fail('language_pack_contract.shared_fields','must be sorted and unique')
    actual=(pack.keys()&descriptor.keys())-{'schema'}
    for key in sorted(set(fields)|actual):
        if key not in fields:fail(key,'undeclared shared capability field')
        elif key not in pack or key not in descriptor:fail(key,'declared shared field is missing')
        else:equal(pack[key],descriptor[key],key)
    if pack.get('language_version')!=descriptor.get('version')or index.get('language')!=descriptor.get('version'):fail('language_version','manifest/compiler/index language mismatch')
    if index.get('schema')!='nex.discovery/1'or index.get('kind')!='index'or index.get('fields')!=sorted(descriptor):fail('discovery','index does not describe the complete descriptor')
    return {'ok':not errors,'shared_fields':fields,'shared_field_count':len(fields),'compared_JSON_values':compared,'errors':errors}


def discover(compiler,resources):
    compiler=Path(compiler).resolve();resources=Path(resources).resolve();pin=sha(compiler)
    env={**os.environ,'NEX_RESOURCE_DIR':str(resources),'PYTHONDONTWRITEBYTECODE':'1'}
    outputs={}
    for name,args in [('descriptor',[]),('index',['--kind','index'])]:
        result=subprocess.run([compiler,'describe',*args,'--json'],cwd=resources,env=env,capture_output=True,timeout=60)
        if result.returncode:raise ValueError('compiler discovery failed: '+name)
        outputs[name]=result.stdout
    if sha(compiler)!=pin:raise ValueError('compiler changed during discovery')
    pack_path=resources/'llm/language-pack.json';raw=pack_path.read_bytes()
    proof=compare(parse(raw),parse(outputs['descriptor']),parse(outputs['index']))
    proof.update(schema='nex.language-pack-validation/1',compiler_sha256=pin,manifest_sha256=hashlib.sha256(raw).hexdigest(),language=parse(outputs['index'])['language'],toolchain=parse(outputs['index'])['toolchain'],compiler_build=parse(outputs['index'])['compiler_build'],descriptor_hash=parse(outputs['index'])['descriptor_hash'])
    return proof,outputs


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--compiler',required=True,type=Path);parser.add_argument('--resources',type=Path,default=ROOT);parser.add_argument('--check',action='store_true');parser.add_argument('--output',type=Path);args=parser.parse_args()
    try:
        proof,outputs=discover(args.compiler,args.resources)
        if args.output:
            args.output.mkdir(parents=True,exist_ok=False)
            for name,raw in outputs.items():(args.output/(name+'.json')).write_bytes(raw)
            (args.output/'report.json').write_text(json.dumps(proof,indent=2)+'\n')
        print(json.dumps(proof,ensure_ascii=False));raise SystemExit(0 if proof['ok']else 1)
    except (OSError,ValueError,subprocess.SubprocessError)as error:
        print(json.dumps({'schema':'nex.language-pack-validation/1','ok':False,'error':str(error)}));raise SystemExit(2)
