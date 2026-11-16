"""Matching source-library pins and actual focused SDK consumption workflow."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil

EXPECTED='1,1,2,3\nЯ + 🌍\n5\n6\n'
FILES=('lib/text.nex','lib/list.nex','lib/math.nex','lib/map.nex','lib/set.nex','lib/queue.nex','lib/stack.nex','lib/deque.nex','lib/priority_queue.nex','lib/ordered_map.nex','lib/ordered_set.nex','lib/java_int.nex','lib/java_long.nex','lib/hash.nex','lib/hash_map.nex','lib/hash_set.nex')
HASH_EXAMPLE_FILES={'README.md','main.nex','tasks.nex','nex.json','nex.lock.json'}


def require(condition,message):
    if not condition:raise RuntimeError(message)


def resource_pins(resources,capability):
    modules=capability.get('modules',{})
    require(set(modules)=={Path(name).stem for name in FILES},'standard library module set differs')
    pins={}
    for name in FILES:
        module=modules[Path(name).stem]
        path=resources/name
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        require(module.get('resource')==name and module.get('sha256')==digest,
            'standard library resource differs from compiled pin: '+name)
        path.read_text(encoding='utf-8');pins[name]=digest
    return pins


def hash_containers(*,cli,run,resources,root,browser):
    directory=root/'hash-containers'
    shutil.copytree(resources/'examples/hash-containers',directory,ignore=shutil.ignore_patterns('.nex','dist'))
    hashes={path.relative_to(directory).as_posix():hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.rglob('*')) if path.is_file()}
    require(set(hashes)==HASH_EXAMPLE_FILES,'hash container example inventory differs')
    lock=directory/'nex.lock.json';before=lock.read_bytes();programs={}
    for file,expected in [('main.nex','hash-containers-ok\n'),('tasks.nex','42\n')]:
        checked=cli('check',file,cwd=directory)
        require(cli('eval',file,cwd=directory)['stdout']==expected,'hash container reference result differs: '+file)
        native={}
        for profile in ('debug','release'):
            native[profile]=cli('run',file,'--profile',profile,cwd=directory,timeout=240)['stdout']
            require(native[profile]==expected,'hash container native result differs: '+file+'/'+profile)
        typescript={'requested':browser,'executed':False}
        if browser:
            target=root/('hash-containers-typescript-'+Path(file).stem)
            cli('emit',file,'--kind','typescript','--entry','main','--directory',target,cwd=directory)
            (target/'package.json').write_text('{"type":"module"}\n')
            runner=target/'runner.mjs';runner.write_text("import {entry} from './program.ts'; await entry();\n")
            actual=run([os.environ.get('NEX_NODE') or 'node','--experimental-strip-types',runner])
            require(actual==expected,'hash container TypeScript result differs: '+file)
            typescript.update(executed=True,stdout=actual)
        programs[file]={'revision':checked['revision'],'reference_stdout':expected,'native':native,'typescript':typescript}
    require(lock.read_bytes()==before,'hash container dependency lock changed during consumption')
    return {'schema':'nex.hash-container-consumption/1','ok':True,'source_language':'0.30',
        'example_hashes':hashes,'programs':programs,'existing_lock_enforced':True,'lock_unchanged':True}


def exercise(*,cli,run,compiler,resources,root,browser):
    capability=cli('describe','--field','standard_library')
    value=capability['value']
    require(value.get('status')=='checked_source_modules' and value.get('source_language_changed') is False,
        'standard library capability differs')
    pins=resource_pins(resources,value)
    directory=root/'standard-library'
    shutil.copytree(resources/'examples/stdlib',directory,ignore=shutil.ignore_patterns('.nex','dist'))
    source_hashes={path.relative_to(directory).as_posix():hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.rglob('*')) if path.is_file()}
    require(set(source_hashes)=={'nex.json','main.nex','nex.lock.json'},'standard library example inventory differs')
    lock=directory/'nex.lock.json';before=lock.read_bytes()
    checked=cli('check',cwd=directory)
    cli('test','--interpreter-only',cwd=directory)
    require(cli('eval',cwd=directory)['stdout']==EXPECTED,'standard library reference result differs')
    profiles={}
    for profile in ('debug','release'):
        output=cli('run','--profile',profile,cwd=directory,timeout=240)
        require(output['stdout']==EXPECTED,'standard library native result differs: '+profile)
        profiles[profile]=output['stdout']
    typescript={'requested':browser,'executed':False}
    if browser:
        folder=root/'standard-library-typescript'
        cli('emit','--kind','typescript','--entry','main','--directory',folder,cwd=directory)
        (folder/'package.json').write_text('{"type":"module"}\n',encoding='utf-8')
        runner=folder/'runner.mjs';runner.write_text("import {entry} from './program.ts';entry();\n",encoding='utf-8')
        output=run([os.environ.get('NEX_NODE') or 'node','--experimental-strip-types',runner])
        require(output==EXPECTED,'standard library TypeScript result differs')
        typescript.update(executed=True,stdout=output)
    require(lock.read_bytes()==before,'standard library workflow silently changed dependency pins')
    containers=hash_containers(cli=cli,run=run,resources=resources,root=root,browser=browser)
    return {'schema':'nex.standard-library-consumption/1','ok':True,
        'compiler_sha256':hashlib.sha256(compiler.read_bytes()).hexdigest(),
        **{key:capability[key] for key in ('language','toolchain','compiler_build','descriptor_hash')},
        'compiled_source_pins':pins,'example_hashes':source_hashes,'revision':checked['revision'],
        'reference_stdout':EXPECTED,'native':profiles,'typescript':typescript,
        'hash_containers':containers,
        'existing_lock_enforced':True,'lock_unchanged':True,'complete_SDK_workflow_claimed':False}


def validate(report):
    proof=report.get('evidence',{}).get('standard_library',{})
    require(isinstance(proof,dict) and proof.get('schema')=='nex.standard-library-consumption/1' and
        proof.get('ok') is True and proof.get('compiler_sha256')==report.get('compiler_sha256') and
        proof.get('language')==report.get('language') and proof.get('toolchain')==report.get('version') and
        proof.get('descriptor_hash')==report.get('evidence',{}).get('scoped_discovery',{}).get('descriptor_hash') and
        proof.get('reference_stdout')==EXPECTED and proof.get('native')=={'debug':EXPECTED,'release':EXPECTED} and
        proof.get('existing_lock_enforced') is True and proof.get('lock_unchanged') is True and
        proof.get('complete_SDK_workflow_claimed') is False,'SDK standard-library consumption is missing or differs')
    for field in ('compiler_build','descriptor_hash','revision'):
        require(isinstance(proof.get(field),str) and re.fullmatch('[0-9a-f]{64}',proof[field]),
            'SDK standard library identity is missing: '+field)
    pins=proof.get('compiled_source_pins',{});inventory=report.get('resource_hashes',{})
    require(isinstance(pins,dict) and set(pins)==set(FILES) and
        all(isinstance(digest,str) and re.fullmatch('[0-9a-f]{64}',digest) and inventory.get(name)==digest
            for name,digest in pins.items()),'SDK compiled standard-library pins differ')
    hashes=proof.get('example_hashes',{})
    require(isinstance(hashes,dict) and set(hashes)=={'main.nex','nex.json','nex.lock.json'} and
        all(isinstance(digest,str) and re.fullmatch('[0-9a-f]{64}',digest) and
            inventory.get('examples/stdlib/'+name)==digest for name,digest in hashes.items()),
        'SDK standard library example differs')
    browser=report.get('evidence',{}).get('browser_build');ts=proof.get('typescript',{})
    require(type(browser) is bool and isinstance(ts,dict) and ts.get('requested') is browser and
        ts.get('executed') is browser and (not browser or ts.get('stdout')==EXPECTED),
        'SDK standard-library browser scope differs')
    containers=proof.get('hash_containers',{})
    require(isinstance(containers,dict) and containers.get('schema')=='nex.hash-container-consumption/1' and
        containers.get('ok') is True and containers.get('source_language')=='0.30' and
        containers.get('existing_lock_enforced') is True and containers.get('lock_unchanged') is True,
        'SDK hash-container consumption is missing or differs')
    hashes=containers.get('example_hashes',{})
    require(isinstance(hashes,dict) and set(hashes)==HASH_EXAMPLE_FILES and
        all(isinstance(digest,str) and re.fullmatch('[0-9a-f]{64}',digest) and
            inventory.get('examples/hash-containers/'+name)==digest for name,digest in hashes.items()),
        'SDK hash-container example differs')
    programs=containers.get('programs',{})
    require(isinstance(programs,dict) and set(programs)=={'main.nex','tasks.nex'},'SDK hash-container programs differ')
    for file,expected in [('main.nex','hash-containers-ok\n'),('tasks.nex','42\n')]:
        case=programs[file];ts=case.get('typescript',{})
        require(isinstance(case.get('revision'),str) and re.fullmatch('[0-9a-f]{64}',case['revision']) and
            case.get('reference_stdout')==expected and case.get('native')=={'debug':expected,'release':expected} and
            isinstance(ts,dict) and ts.get('requested') is browser and ts.get('executed') is browser and
            (not browser or ts.get('stdout')==expected),'SDK hash-container backend scope differs: '+file)
