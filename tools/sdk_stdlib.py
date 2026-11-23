"""Matching source-library pins and actual focused SDK consumption workflow."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil

EXPECTED='1,1,2,3\nЯ + 🌍\n5\n6\n'
LEGACY_FILES=('lib/text.nex','lib/list.nex','lib/math.nex','lib/map.nex','lib/set.nex','lib/queue.nex','lib/stack.nex','lib/deque.nex','lib/priority_queue.nex','lib/ordered_map.nex','lib/ordered_set.nex','lib/java_int.nex','lib/java_long.nex','lib/hash.nex','lib/hash_map.nex','lib/hash_set.nex','lib/sequence.nex','lib/fifo.nex','lib/lifo.nex','lib/heap.nex')
FILES=(*LEGACY_FILES,'lib/insertion_ordered_map.nex')
# Each module's examples are independently verified in the installed tree.
CONTAINER_EXAMPLES={
    'hash_containers':('hash-containers','nex.hash-container-consumption/1',
                       {'main.nex':'hash-containers-ok\n','tasks.nex':'42\n'}),
    'sequence_containers':('sequence-containers','nex.sequence-container-consumption/1',
                           {'main.nex':'sequence-containers-ok\n','tasks.nex':'42\n'}),
    'insertion_ordered_map':('insertion-ordered-map','nex.insertion-ordered-map-consumption/1',
                             {'main.nex':'east\nwest\n'}),
}


def example_files(programs):
    return {'README.md','nex.json','nex.lock.json',*programs}


def resource_names():
    examples=[*('examples/stdlib/'+name for name in ('main.nex','nex.json','nex.lock.json')),
        *('examples/'+example+'/'+name for example,_,programs in CONTAINER_EXAMPLES.values()
            for name in sorted(example_files(programs)))]
    return (*FILES,*examples)


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


def container_examples(*,cli,run,resources,root,browser,name,schema,expected_outputs):
    directory=root/name
    shutil.copytree(resources/'examples'/name,directory,ignore=shutil.ignore_patterns('.nex','dist'))
    hashes={path.relative_to(directory).as_posix():hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.rglob('*')) if path.is_file()}
    require(set(hashes)==example_files(expected_outputs),'container example inventory differs: '+name)
    lock=directory/'nex.lock.json';before=lock.read_bytes();programs={}
    for file,expected in expected_outputs.items():
        checked=cli('check',file,cwd=directory)
        require(cli('eval',file,cwd=directory)['stdout']==expected,'container reference result differs: '+name+'/'+file)
        native={}
        for profile in ('debug','release'):
            native[profile]=cli('run',file,'--profile',profile,cwd=directory,timeout=240)['stdout']
            require(native[profile]==expected,'container native result differs: '+name+'/'+file+'/'+profile)
        typescript={'requested':browser,'executed':False}
        if browser:
            target=root/(name+'-typescript-'+Path(file).stem)
            cli('emit',file,'--kind','typescript','--entry','main','--directory',target,cwd=directory)
            (target/'package.json').write_text('{"type":"module"}\n')
            runner=target/'runner.mjs';runner.write_text("import {entry} from './program.ts'; await entry();\n")
            actual=run([os.environ.get('NEX_NODE') or 'node','--experimental-strip-types',runner])
            require(actual==expected,'container TypeScript result differs: '+name+'/'+file)
            typescript.update(executed=True,stdout=actual)
        programs[file]={'revision':checked['revision'],'reference_stdout':expected,'native':native,'typescript':typescript}
    require(lock.read_bytes()==before,'container dependency lock changed during consumption: '+name)
    return {'schema':schema,'ok':True,'source_language':'0.30',
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
    containers={key:container_examples(cli=cli,run=run,resources=resources,root=root,browser=browser,
        name=name,schema=schema,expected_outputs=programs) for key,(name,schema,programs) in CONTAINER_EXAMPLES.items()}
    return {'schema':'nex.standard-library-consumption/2','ok':True,
        'compiler_sha256':hashlib.sha256(compiler.read_bytes()).hexdigest(),
        **{key:capability[key] for key in ('language','toolchain','compiler_build','descriptor_hash')},
        'compiled_source_pins':pins,'example_hashes':source_hashes,'revision':checked['revision'],
        'reference_stdout':EXPECTED,'native':profiles,'typescript':typescript,
        **containers,
        'existing_lock_enforced':True,'lock_unchanged':True,'complete_SDK_workflow_claimed':False}


def validate(report):
    proof=report.get('evidence',{}).get('standard_library',{})
    require(isinstance(proof,dict) and proof.get('schema') in ('nex.standard-library-consumption/1','nex.standard-library-consumption/2') and
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
    legacy=proof['schema']=='nex.standard-library-consumption/1'
    require(not legacy or 'lib/insertion_ordered_map.nex' not in inventory,
            'SDK library evidence omits insertion-ordered map consumption')
    require(isinstance(pins,dict) and set(pins)==set(LEGACY_FILES if legacy else FILES) and
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
    for key,(name,schema,programs) in CONTAINER_EXAMPLES.items():
        if legacy and key=='insertion_ordered_map':continue
        validate_container_examples(proof.get(key,{}),inventory,browser,name,schema,programs)


def validate_container_examples(containers,inventory,browser,name,schema,expected_outputs):
    require(isinstance(containers,dict) and containers.get('schema')==schema and
        containers.get('ok') is True and containers.get('source_language')=='0.30' and
        containers.get('existing_lock_enforced') is True and containers.get('lock_unchanged') is True,
        'SDK container consumption is missing or differs: '+name)
    hashes=containers.get('example_hashes',{})
    require(isinstance(hashes,dict) and set(hashes)==example_files(expected_outputs) and
        all(isinstance(digest,str) and re.fullmatch('[0-9a-f]{64}',digest) and
            inventory.get('examples/'+name+'/'+file)==digest for file,digest in hashes.items()),
        'SDK container example differs: '+name)
    programs=containers.get('programs',{})
    require(isinstance(programs,dict) and set(programs)==set(expected_outputs),'SDK container programs differ: '+name)
    for file,expected in expected_outputs.items():
        case=programs[file]
        require(isinstance(case,dict),'SDK container program is not an object: '+name+'/'+file)
        ts=case.get('typescript',{})
        require(isinstance(case.get('revision'),str) and re.fullmatch('[0-9a-f]{64}',case['revision']) and
            case.get('reference_stdout')==expected and case.get('native')=={'debug':expected,'release':expected} and
            isinstance(ts,dict) and ts.get('requested') is browser and ts.get('executed') is browser and
            (not browser or ts.get('stdout')==expected),'SDK container backend scope differs: '+name+'/'+file)
