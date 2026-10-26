#!/usr/bin/env python3
"""Exercise an installed NEX development chain, retaining reviewable evidence."""
import argparse
import base64
import concurrent.futures
import hashlib
import json
import os
import platform
from pathlib import Path
import queue
import re
import shutil
import signal
import sqlite3
import ssl
import subprocess
import sys
import threading
import tempfile
import time
import urllib.error
import urllib.request


# Distribution validators import the contract from their matching SDK. Keep
# action registration checked against it so a missing phase cannot look green.
ACCEPTANCE_PHASES = (
    'discovery', 'editor-tools', 'new-project', 'reviewed-failure',
    'graph-repair-import', 'backend-agreement', 'graph-snapshot-recovery',
    'project-version-boundaries', 'frontend-diagnostics', 'graph-queries',
    'string-ranges', 'binary-values', 'compute-contract', 'model-contract', 'native-indexed-pages', 'core-reports', 'wasm-compute', 'foreign-boundary', 'source-resources', 'text-files', 'profile',
    'structured-task-file-reads', 'structured-task-profile', 'structured-task-debug', 'static-task-providers', 'shared-task-providers', 'task-provider-profiling', 'task-provider-debugging', 'archive-debug-replay-export', 'scalar-proof', 'traits',
    'authenticated-storage', 'browser', 'project-build')


ACCEPTANCE_PHASES_023 = ACCEPTANCE_PHASES[:ACCEPTANCE_PHASES.index('structured-task-file-reads')+1] + ('structured-task-file-writes',) + ACCEPTANCE_PHASES[ACCEPTANCE_PHASES.index('structured-task-file-reads')+1:]
ACCEPTANCE_PHASES_024 = ACCEPTANCE_PHASES_023[:ACCEPTANCE_PHASES_023.index('structured-task-file-writes')+1] + ('structured-task-file-streams',) + ACCEPTANCE_PHASES_023[ACCEPTANCE_PHASES_023.index('structured-task-file-writes')+1:]
ACCEPTANCE_PHASES_024_HTTP = ACCEPTANCE_PHASES_024[:ACCEPTANCE_PHASES_024.index('structured-task-file-streams')+1] + ('structured-task-http',) + ACCEPTANCE_PHASES_024[ACCEPTANCE_PHASES_024.index('structured-task-file-streams')+1:]


ACCEPTANCE_PHASES_024_TCP = ACCEPTANCE_PHASES_024_HTTP[:ACCEPTANCE_PHASES_024_HTTP.index('structured-task-http')+1] + ('structured-task-tcp',) + ACCEPTANCE_PHASES_024_HTTP[ACCEPTANCE_PHASES_024_HTTP.index('structured-task-http')+1:]


def acceptance_phases(version):
    parts=version.split('.')
    if len(parts)==3 and all(part.isascii() and part.isdigit() for part in parts) and tuple(map(int,parts))>=(0,135,1):
        return ACCEPTANCE_PHASES_024_TCP
    if len(parts)==3 and all(part.isascii() and part.isdigit() for part in parts) and tuple(map(int,parts))>=(0,134,4):
        return ACCEPTANCE_PHASES_024_HTTP
    if len(parts)==3 and all(part.isascii() and part.isdigit() for part in parts) and tuple(map(int,parts))>=(0,134,0):
        return ACCEPTANCE_PHASES_024
    current=len(parts)==3 and all(part.isascii() and part.isdigit() for part in parts) and tuple(map(int,parts))>=(0,133,0)
    return ACCEPTANCE_PHASES_023 if current else ACCEPTANCE_PHASES


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def captured_task_build_artifacts(command, expected_linkages):
    """Bind a retained build to its actual checked command, not another CWD."""
    require(isinstance(command,dict) and type(command.get('exit_code')) is int and command['exit_code']==0 and
            type(command.get('interrupted')) is int and command['interrupted']==0 and
            all(command.get(key) is False for key in ('timed_out','output_limit')),
            'captured task build command did not complete normally')
    response=command.get('response',{})
    require(isinstance(response,dict) and response.get('ok') is True and
            isinstance(response.get('artifacts'),list) and 1<=len(response['artifacts'])<=128,
            'captured task build has no bounded successful artifact response')
    components=response.get('plan',{}).get('components',[])
    require(isinstance(components,list) and len(components)==len(expected_linkages) and
            {row.get('name'):row.get('task_linkage') for row in components if isinstance(row,dict)}==expected_linkages,
            'captured task build checked linkage differs')
    artifacts={}
    for row in response['artifacts']:
        require(isinstance(row,dict) and row.get('component') in expected_linkages and row['component'] not in artifacts and
                isinstance(row.get('build_key'),str) and re.fullmatch('[0-9a-f]{64}',row['build_key']) and
                isinstance(row.get('artifact'),str) and '\0' not in row['artifact'] and '\\' not in row['artifact'],
                'captured task build artifact component/key differs')
        path=Path(row['artifact'])
        require(path.is_absolute() and path.parent.name==row['build_key'] and
                row.get('kind') in ('executable','shared_library','static_library'),
                'captured task build artifact path/kind differs')
        artifacts[row['component']]=row
    require(set(artifacts)==set(expected_linkages),'captured task build artifact component set differs')
    return artifacts


def task_sdk_regular(base,name,maximum=64*1024*1024):
    require(type(name) is str and 0<len(name.encode())<=16384 and '\\' not in name and '\0' not in name,
            'invalid task SDK path text')
    relative=Path(name)
    require(not relative.is_absolute() and relative.as_posix()==name and
            all(part not in ('','.','..') for part in relative.parts),'task SDK path escapes its root')
    path=base;require(not path.is_symlink(),'task SDK root is a symlink')
    for part in relative.parts:
        path=path/part;require(not path.is_symlink(),'task SDK path contains a symlink')
    require(path.is_file() and path.stat().st_size<=maximum,'task SDK input is not a bounded regular file')
    return path


def task_debug_namespace(directory, completion_inputs, compiler_build, build_key):
    """Check one raw completion7 namespace, preserving the producer's B3 pins."""
    metadata=json.loads(task_sdk_regular(directory,'build.json',8*1024*1024).read_text())
    require(metadata.get('compiler_build')==compiler_build and metadata.get('key')==build_key and
            metadata.get('completion_schema')=='nex.native-completion/7' and metadata.get('task_debug') is True,
            'provider debug raw completion identity differs')
    inputs=completion_inputs(metadata)
    tail=['debug.json','debugger/lldb_nex.py','debugger/nex_dap.py']
    if metadata.get('completion_mode') in ('static-application','shared-application') and '-apple-' in metadata.get('compiler_target',''):
        tail+=['debug-symbols.complete','app.dSYM/Contents/Info.plist','app.dSYM/Contents/Resources/DWARF/app']
    require(isinstance(inputs,list) and 6<=len(inputs)<=16384 and
            inputs[:4]==['library-abi.json','task-provider.json','task-debug-catalog.json','task-debug-sources.json'] and
            inputs[-len(tail):]==tail and len(inputs)==len(set(inputs)),
            'provider debug completion7 order differs')
    provider=json.loads(task_sdk_regular(directory,'task-provider.json').read_text())
    require(provider.get('schema')==('nex.native-task-provider/10' if provider.get('language')=='0.24' else 'nex.native-task-provider/7' if provider.get('language')=='0.23' else 'nex.native-task-provider/4') and metadata.get('task_provider')==provider and
            provider.get('debugging',{}).get('schema')=='nex.native-task-debug/1',
            'provider debug completed record differs')
    catalog=json.loads(task_sdk_regular(directory,'task-debug-catalog.json').read_text())
    artifact=catalog.get('artifact_kind')
    require(artifact in ('code-archive','pic-stage','shared-image','application'),'provider debug artifact kind differs')
    executable='app' if artifact=='application' else 'libnex.a' if artifact in ('pic-stage','code-archive') else \
        'libnex_'+provider['component']+'_'+build_key+('.dylib' if platform.system()=='Darwin' else '.so')
    names=list(dict.fromkeys([executable,'program.mlir','program.ll','compilation.json','build.json','source-bundle.json',*inputs,'complete']))
    require(len(names)<=16391,'provider debug namespace exceeds bound')
    sources=json.loads(task_sdk_regular(directory,'task-debug-sources.json').read_text())
    require(catalog.get('schema')=='nex.task-debug-catalog/1' and catalog.get('catalog_abi')==2 and
            sources.get('schema')=='nex.task-debug-source-union/1' and
            catalog.get('mode')==sources.get('mode')==provider.get('mode') and
            catalog.get('owner_image')==sources.get('owner_image') and
            (provider.get('mode')!='shared-fixed' or catalog.get('owner_image')==provider.get('owner_image')),
            'provider debug raw source/catalog ownership differs')
    return metadata,provider,names


def retained_task_debug_build(receipt_root,check,artifact,component,compiler_build,completion_inputs):
    """Bind captured debug4 bytes to this checked action's artifact index."""
    name=component.get('component');check_id=check.get('id')
    require(isinstance(name,str) and re.fullmatch('[A-Za-z_][A-Za-z_0-9]{0,63}',name) and
            name==artifact.get('component') and isinstance(check_id,str) and
            re.fullmatch('[A-Za-z_][A-Za-z_0-9-]{0,63}',check_id),'provider debug capture component differs')
    base='artifacts/'+check_id+'/';prefix=base+'components/'+name+'/retained-build/'
    require(component.get('retained_build')==prefix+'retained.json','provider debug retained record moved')
    record_path=task_sdk_regular(receipt_root,component['retained_build'],16*1024*1024)
    record=json.loads(record_path.read_text());index=check.get('artifacts',{})
    def indexed(path,data,pin=None):
        row=index.get(path[len(base):])
        require(isinstance(row,dict) and set(row)=={'hash','bytes'} and type(row.get('bytes')) is int and
                row['bytes']==len(data) and isinstance(row.get('hash'),str) and re.fullmatch('[0-9a-f]{64}',row['hash']) and
                (pin is None or row['hash']==pin),'provider debug retained byte/index pin differs')
    indexed(component['retained_build'],record_path.read_bytes())
    require(isinstance(record,dict) and set(record)=={'schema','compiler_build','build_key','original_directory',
            'metadata_rewritten','hash_algorithm','completion_schema','files'} and
            record.get('schema')=='nex.retained-native-task-build/4' and
            record.get('completion_schema')=='nex.native-completion/7' and
            record.get('metadata_rewritten') is False and record.get('hash_algorithm')=='BLAKE3' and
            record.get('compiler_build')==compiler_build and record.get('build_key')==artifact.get('build_key') and
            isinstance(record.get('files'),list) and 12<=len(record['files'])<=16391,
            'provider debug retained envelope differs')
    original=Path(record['original_directory']);executable=Path(artifact['artifact'])
    require(original==executable.parent and original.is_absolute() and original.resolve(strict=True)==original and
            original.name==record['build_key'],'provider debug original capture directory differs')
    namespace=receipt_root/prefix
    metadata,provider,names=task_debug_namespace(namespace,completion_inputs,compiler_build,record['build_key'])
    require(executable.name==names[0] and component.get('kind')==artifact.get('kind') and
            provider.get('component')==name and len(record['files'])==len(names),'provider debug artifact kind/name differs')
    rows={};total=0;proof=[]
    for row,relative in zip(record['files'],names):
        require(isinstance(row,dict) and set(row)=={'original','retained','hash','bytes'} and
                row.get('original')==str(original/relative) and row.get('retained')==prefix+relative and
                type(row.get('bytes')) is int and 0<=row['bytes']<=512*1024*1024 and
                isinstance(row.get('hash'),str) and re.fullmatch('[0-9a-f]{64}',row['hash']),
                'provider debug retained mapping order/path differs')
        copied=task_sdk_regular(receipt_root,row['retained'],512*1024*1024);raw=copied.read_bytes()
        source=task_sdk_regular(original,relative,512*1024*1024);total+=len(raw)
        require(total<=1024*1024*1024 and raw==source.read_bytes() and len(raw)==row['bytes'],
                'provider debug retained bytes differ from original')
        indexed(row['retained'],raw,row['hash']);rows[relative]=row
        proof.append({'relative':relative,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'compiler_checked_hash':row['hash']})
    require(metadata.get('task_provider_hash')==rows['task-provider.json']['hash'],
            'provider debug own provider BLAKE3 pin differs')
    return {'component':name,'build_key':record['build_key'],'record_sha256':hashlib.sha256(record_path.read_bytes()).hexdigest(),
        'files':proof,'verification':'matching compiler receipt BLAKE3 index plus own original/copied bytes, SHA256 and sizes; no Python BLAKE3 recomputation'}


def relocated_task_debug(package_root,package_meta,project_root,completion_inputs):
    """Verify a package's own raw namespace and loaded-image relocation."""
    fresh_path=task_sdk_regular(package_root,package_meta.get('debug_manifest'),8*1024*1024)
    fresh=json.loads(fresh_path.read_text());directory=fresh_path.parent
    receipt_path=task_sdk_regular(package_root,package_meta.get('debug_relocation'),16*1024*1024)
    receipt=json.loads(receipt_path.read_text());key=package_meta.get('build_key')
    require(receipt.get('schema')=='nex.task-debug-relocation/1' and receipt.get('metadata_rewritten') is False and
            receipt.get('build_key')==fresh.get('build_key')==key and
            receipt.get('compiler_build')==package_meta.get('compiler_build')==fresh.get('compiler_build') and
            receipt.get('artifact_directory')==str(directory)==fresh.get('artifact_directory') and
            directory==package_root/'debugger/retained-build' and
            receipt.get('original_directory')==str(project_root/'.nex/build'/key),
            'packaged provider debug relocation context differs')
    metadata,provider,names=task_debug_namespace(directory,completion_inputs,package_meta['compiler_build'],key)
    rows=receipt.get('raw_files')
    require(isinstance(rows,list) and len(rows)==len(names),'packaged provider debug raw mapping count differs')
    provenance=package_meta.get('task_debug_provenance')
    require(isinstance(provenance,dict) and set(provenance)=={'schema','metadata_rewritten','hash_algorithm','files'} and
            provenance.get('schema')=='nex.application-task-debug-provenance/1' and
            provenance.get('metadata_rewritten') is False and provenance.get('hash_algorithm')=='BLAKE3' and
            isinstance(provenance.get('files'),list) and len(provenance['files'])==len(names),
            'packaged provider debug raw provenance envelope differs')
    kinds=['base_binary','base_mlir','base_llvm','base_compilation','base_build','base_source_bundle']+\
        [row['kind'] for row in metadata['completion_inputs']]+['complete']
    inventory=package_meta.get('files',{});proof=[];total=0
    for row,name,transport,kind in zip(rows,names,provenance['files'],kinds):
        require(isinstance(row,dict) and set(row)=={'path','hash','bytes'} and row.get('path')==name and
                isinstance(row.get('hash'),str) and re.fullmatch('[0-9a-f]{64}',row['hash']) and
                type(row.get('bytes')) is int and 0<=row['bytes']<=512*1024*1024,
                'packaged provider debug raw mapping order/pin differs')
        raw=task_sdk_regular(directory,name,512*1024*1024).read_bytes();total+=len(raw)
        own=task_sdk_regular(project_root,'.nex/build/'+key+'/'+name,512*1024*1024).read_bytes()
        relative=(directory/name).relative_to(package_root).as_posix();sha=hashlib.sha256(raw).hexdigest()
        require(total<=1024*1024*1024 and raw==own and len(raw)==row['bytes'] and
                inventory.get(relative,{}).get('sha256')==sha and inventory[relative].get('bytes')==len(raw),
                'packaged provider debug raw bytes differ from own action/or output inventory')
        require(isinstance(transport,dict) and set(transport)=={'relative','kind','path','input_hash','input_sha256','bytes',
                'component','input_image_key','input_image_sha256','input_uuid','output_image','output_image_sha256'} and
                transport.get('relative')==name and transport.get('kind')==kind and transport.get('path')==relative and
                transport.get('input_hash')==row['hash'] and transport.get('input_sha256')==sha and
                type(transport.get('bytes')) is int and transport['bytes']==len(raw),
                'packaged provider debug provenance order/raw pin differs')
        proof.append({'relative':name,'sha256':sha,'bytes':len(raw),'compiler_validated_input_hash':row['hash']})
    mappings=receipt.get('images');expected={image['path']:image for image in fresh['task_debug']['images']}
    expected[fresh['task_debug']['runtime_image']['path']]=fresh['task_debug']['runtime_image'];seen=set()
    require(isinstance(mappings,list) and len(mappings)==len(expected),'packaged provider debug physical image count differs')
    for row in mappings:
        before,after=row.get('input',{}),row.get('output',{})
        require(after==expected.get(after.get('path')) and after.get('path') not in seen and
                all(before.get(field)==after.get(field) for field in ('component','key','kind')),
                'packaged provider debug physical image ownership differs')
        source=Path(before['path']).relative_to(receipt['original_directory']).as_posix()
        raw=task_sdk_regular(directory,source,512*1024*1024).read_bytes()
        relative=Path(after['path']).relative_to(package_root).as_posix()
        target=task_sdk_regular(package_root,relative,512*1024*1024);sha=hashlib.sha256(target.read_bytes()).hexdigest()
        require(hashlib.sha256(raw).hexdigest()==before.get('sha256') and sha==after.get('sha256') and
                inventory.get(relative,{}).get('sha256')==sha and inventory[relative].get('bytes')==target.stat().st_size,
                'packaged provider debug original/loaded image SHA differs')
        seen.add(after['path'])
    for row in provenance['files']:
        if row['output_image'] is None:
            require(all(row[key] is None for key in ('component','input_image_key','input_image_sha256','input_uuid','output_image_sha256')),
                    'packaged nonimage debug input claims an image')
        else:
            physical=next((mapping for mapping in mappings if mapping['output']['path']==str(package_root/row['output_image'])),None)
            require(physical is not None and row['component']==physical['input']['component'] and
                    all(row[field]==physical['input'][key] for field,key in (('input_image_key','key'),('input_image_sha256','sha256'),('input_uuid','uuid'))) and
                    row['output_image_sha256']==physical['output']['sha256'],
                    'packaged provider debug provenance physical image association differs')
    return {'build_key':key,'raw_files':proof,'physical_images':len(seen),
        'verification':'matching compiler validated completion7/relocation BLAKE3; own-action raw bytes, SHA256, sizes and relocated output inventory independently checked'}



def retained_task_profile_build(receipt_root, check, artifact, component, compiler_build, completion_inputs):
    """Verify one measured action against its own checked artifact index.

    BLAKE3 pins come from the matching compiler's receipt; independent checks
    compare every original/copied byte, SHA256 and size. No Python BLAKE3 claim.
    """
    check_id=check.get('id');name=component.get('component')
    require(isinstance(check_id,str) and re.fullmatch('[A-Za-z_][A-Za-z_0-9-]{0,63}',check_id) and
            name==artifact.get('component') and isinstance(name,str) and re.fullmatch('[A-Za-z_][A-Za-z_0-9]{0,63}',name),
            'profile retention component/check association differs')
    base='artifacts/'+check_id+'/'
    prefix=base+'components/'+name+'/retained-build/'
    require(component.get('retained_build')==prefix+'retained.json','profile retained record moved')
    record_path=task_sdk_regular(receipt_root,component['retained_build'],2*1024*1024)
    record_pin=check.get('artifacts',{}).get(component['retained_build'][len(base):],{})
    require(isinstance(record_pin,dict) and set(record_pin)=={'hash','bytes'} and
            type(record_pin['bytes']) is int and record_pin['bytes']==record_path.stat().st_size and
            isinstance(record_pin['hash'],str) and re.fullmatch('[0-9a-f]{64}',record_pin['hash']),
            'profile retained record lacks checked receipt BLAKE3 index/size')
    record=json.loads(record_path.read_text())
    require(isinstance(record,dict) and set(record)=={'schema','compiler_build','build_key','original_directory',
            'metadata_rewritten','hash_algorithm','completion_schema','files'} and
            record['schema']=='nex.retained-native-task-build/3' and record['completion_schema']=='nex.native-completion/6' and
            record['metadata_rewritten'] is False and record['hash_algorithm']=='BLAKE3' and
            record['compiler_build']==compiler_build and record['build_key']==artifact.get('build_key') and
            isinstance(record['files'],list) and 11<=len(record['files'])<=2056,
            'invalid measured retained completion6 record')
    executable=Path(artifact['artifact']);original=Path(record['original_directory'])
    require(executable.is_absolute() and executable.parent==original and original.resolve(strict=True)==original and original.name==record['build_key'] and
            re.fullmatch('[0-9a-f]{64}',record['build_key']) and
            executable.name==('app' if component['kind']=='executable' else 'libnex.a' if component['kind']=='static_library'
                else 'libnex_'+name+'_'+record['build_key']+executable.suffix),
            'profile retained artifact does not match measured component')
    metadata=json.loads(task_sdk_regular(receipt_root,prefix+'build.json',8*1024*1024).read_text())
    require(metadata.get('key')==record['build_key'] and metadata.get('compiler_build')==compiler_build and
            metadata.get('completion_schema')=='nex.native-completion/6','retained profile build identity differs')
    inputs=completion_inputs(metadata)
    require(3<=len(inputs)<=2048 and inputs[:3]==['library-abi.json','task-provider.json','task-profile-catalog.json'],
            'profile retained completion6 input order differs')
    names=[executable.name,'program.mlir','program.ll','compilation.json','build.json','source-bundle.json',*inputs,'complete','debug.json']
    require(len(names)==len(set(names))==len(record['files']),'profile retained mapping count differs')
    mapped={};total=0;independent=[]
    for expected,row in zip(names,record['files']):
        require(isinstance(row,dict) and set(row)=={'original','retained','hash','bytes'} and
                row['original']==str(original/expected) and row['retained']==prefix+expected and
                type(row['bytes']) is int and 0<=row['bytes']<=64*1024*1024 and
                isinstance(row['hash'],str) and re.fullmatch('[0-9a-f]{64}',row['hash']),
                'profile retained row/path/order differs')
        copied=task_sdk_regular(receipt_root,row['retained']).read_bytes()
        source=task_sdk_regular(original,expected).read_bytes();total+=len(copied)
        require(total<=256*1024*1024 and copied==source and len(copied)==row['bytes'],
                'profile retained bytes differ from measured originals')
        require(check.get('artifacts',{}).get(row['retained'][len(base):])=={'hash':row['hash'],'bytes':row['bytes']},
                'profile retained bytes lack the checked receipt BLAKE3 pin')
        mapped[expected]=(row,copied)
        independent.append({'path':row['retained'],'sha256':hashlib.sha256(copied).hexdigest(),'bytes':len(copied)})
    require(re.fullmatch(b'[0-9a-f]{64}\n',mapped['complete'][1]),'profile completion digest is malformed')
    provider=json.loads(mapped['task-provider.json'][1]);catalog=json.loads(mapped['task-profile-catalog.json'][1])
    require(provider.get('schema')==('nex.native-task-provider/9' if provider.get('language')=='0.24' else 'nex.native-task-provider/6' if provider.get('language')=='0.23' else 'nex.native-task-provider/3') and provider.get('component')==name and
            provider==metadata.get('task_provider') and metadata.get('task_provider_hash')==mapped['task-provider.json'][0]['hash'] and
            catalog.get('schema')=='nex.task-profile-catalog/1' and catalog.get('registry_abi')==1 and
            catalog.get('mode')==provider.get('mode') and
            provider.get('profiling',{}).get('catalog_file')=='task-profile-catalog.json' and
            isinstance(provider.get('profiling',{}).get('catalog_hash'),str) and
            re.fullmatch('[0-9a-f]{64}',provider['profiling']['catalog_hash']),
            'profile retained provider/catalog identity differs')
    abi=json.loads(mapped['library-abi.json'][1])
    for index,dependency in enumerate(abi.get('static_libraries',[])):
        archive='libraries/%d.a'%index;sidecar='libraries/%d.task-provider.json'%index
        catalog_path='libraries/%d.task-profile-catalog.json'%index
        require(archive in mapped and sidecar in mapped and catalog_path in mapped and
                dependency.get('hash')==mapped[archive][0]['hash'] and
                dependency.get('task_provider_hash')==mapped[sidecar][0]['hash'] and
                dependency.get('task_profile_catalog_hash')==mapped[catalog_path][0]['hash'] and
                dependency.get('task_provider')==json.loads(mapped[sidecar][1]),'profile static frontier raw triple pins differ')
    if 'image-inputs.json' in mapped:
        links=json.loads(mapped['image-inputs.json'][1])
        require(links.get('schema')=='nex.native-image-inputs/3' and
                sum(row.get('kind')=='runtime' for row in links.get('images',[]))==1,
                'profile retained shared closure/runtime differs')
        runtime=next(row for row in links['images'] if row.get('kind')=='runtime')
        if provider.get('mode')=='shared-fixed' and provider.get('artifact_kind') in ('shared-image','application'):
            image=provider.get('image',{})
            require(image.get('key')==record['build_key'] and image.get('hash')==mapped[executable.name][0]['hash'] and
                    image.get('sha256')==hashlib.sha256(mapped[executable.name][1]).hexdigest() and
                    image.get('runtime_key')==runtime.get('key') and image.get('runtime_hash')==runtime.get('hash'),
                    'retained own profile image/runtime identity differs')
        for image in links.get('images',[]):
            path='images/'+Path(image['path']).name
            require(path in mapped and image.get('hash')==mapped[path][0]['hash'] and
                    image.get('sha256')==hashlib.sha256(mapped[path][1]).hexdigest(),'profile retained owned image pin differs')
        for field in ('task_providers','task_profile_catalogs'):
            for entry in links.get(field,[]):
                path=entry.get('path')
                require(path in mapped and entry.get('hash')==mapped[path][0]['hash'],
                        'profile retained owned metadata pin differs')
    return {'component':name,'build_key':record['build_key'],'record':str(record_path),'record_sha256':hashlib.sha256(record_path.read_bytes()).hexdigest(),'files':independent,
        'bytes':total,'verification':'compiler-checked receipt BLAKE3 pins plus own-original/copied bytes, SHA256 and sizes; no Python BLAKE3 recomputation'}



def package_task_profile_provenance(package_root, package_meta, project_root):
    """Bind raw profile metadata to this package action and relocated outputs."""
    key=package_meta.get('build_key')
    require(isinstance(key,str) and re.fullmatch('[0-9a-f]{64}',key),'packaged profile build key differs')
    prefix='.nex/build/'+key+'/'
    original=lambda name:task_sdk_regular(project_root,prefix+name,64*1024*1024)
    metadata=json.loads(original('build.json').read_text())
    require(metadata.get('key')==key and metadata.get('compiler_build')==package_meta.get('compiler_build') and
            metadata.get('completion_schema')=='nex.native-completion/6' and metadata.get('profile')=='profile',
            'packaged profile own completed build identity differs')
    shared=metadata.get('completion_mode')=='shared-application'
    require(shared or metadata.get('completion_mode')=='static-application','packaged profile is not an application')
    links=json.loads(original('image-inputs.json').read_text()) if shared else {}
    providers=links.get('task_providers',[]);catalogs=links.get('task_profile_catalogs',[]);images=links.get('images',[])
    require(isinstance(providers,list) and isinstance(catalogs,list) and len(providers)==len(catalogs)<=128 and
            [row.get('image') for row in providers]==sorted({row.get('image') for row in providers}) and
            (not shared or links.get('schema')=='nex.native-image-inputs/3' and
                sum(row.get('kind')=='runtime' for row in images)==1 and
                len(providers)==sum(row.get('kind')=='library' for row in images)),
            'packaged profile own loaded closure differs')
    expected=[('application_provider','task-provider.json',metadata.get('task_provider_hash')),
        ('application_profile_catalog','task-profile-catalog.json',metadata.get('task_profile_catalog_file_hash'))]
    for provider in providers:
        catalog=next((row for row in catalogs if row.get('image')==provider.get('image')),None)
        require(catalog is not None and provider.get('component')==catalog.get('component'),
                'packaged provider/catalog physical owner differs')
        expected.extend([('owned_provider',provider['path'],provider['hash']),
            ('owned_profile_catalog',catalog['path'],catalog['hash'])])
    if shared:expected.append(('image_inputs','image-inputs.json',None))
    expected.extend([('build','build.json',None),('complete','complete',None)])
    provenance=package_meta.get('task_profile_provenance')
    require(isinstance(provenance,dict) and set(provenance)=={'schema','metadata_rewritten','hash_algorithm','files'} and
            provenance.get('schema')=='nex.application-task-profile-provenance/1' and
            provenance.get('metadata_rewritten') is False and provenance.get('hash_algorithm')=='BLAKE3' and
            isinstance(provenance.get('files'),list) and len(provenance['files'])==len(expected),
            'packaged profile raw provenance envelope/count differs')
    identities={};proof=[];total=0
    for index,(row,(kind,name,pin)) in enumerate(zip(provenance['files'],expected)):
        require(isinstance(row,dict) and set(row)=={'kind','path','input_hash','input_sha256','bytes','component',
                'input_image_key','input_image_sha256','input_uuid','output_image','output_image_sha256'} and
                row.get('kind')==kind and row.get('path')=='provenance/task/%03d-'%index+Path(name).name and
                type(row.get('bytes')) is int and 0<row['bytes']<=64*1024*1024 and
                isinstance(row.get('input_hash'),str) and re.fullmatch('[0-9a-f]{64}',row['input_hash']) and
                (pin is None or row['input_hash']==pin),'packaged profile raw row/order/pin differs')
        raw=task_sdk_regular(package_root,row['path']).read_bytes();source=original(name).read_bytes();total+=len(raw)
        sha=hashlib.sha256(raw).hexdigest()
        require(total<=64*1024*1024 and raw==source and len(raw)==row['bytes'] and sha==row['input_sha256'] and
                package_meta.get('files',{}).get(row['path'],{}).get('sha256')==sha and
                package_meta['files'][row['path']].get('bytes')==len(raw),
                'packaged profile raw bytes differ from own original/output inventory')
        if kind in ('application_provider','owned_provider','application_profile_catalog','owned_profile_catalog'):
            require(isinstance(row['component'],str) and isinstance(row['output_image'],str),
                    'packaged profile metadata lost image association')
            application=kind.startswith('application_')
            owner=metadata['task_provider'] if application else None
            if kind.endswith('provider'):
                owner=json.loads(raw)
                require(owner.get('schema')==('nex.native-task-provider/9' if owner.get('language')=='0.24' else 'nex.native-task-provider/6' if owner.get('language')=='0.23' else 'nex.native-task-provider/3') and owner.get('component')==row['component'] and
                        owner.get('profiling',{}).get('schema')=='nex.native-task-profile/1',
                        'packaged profile provider extension differs')
                if application:
                    require(owner==metadata['task_provider'] and row['output_image']==package_meta.get('entry'),
                            'packaged profile application provider differs from own completed root')
                else:
                    pinrow=next(item for item in providers if item['path']==name)
                    physical=next((image for image in images if Path(image['path']).name==Path(pinrow['image']).name),{})
                    require(owner.get('component')==pinrow['component'] and owner.get('owner_image')==pinrow['component'] and
                            owner.get('artifact_kind')=='shared-image' and physical.get('kind')=='library' and
                            all(owner.get('image',{}).get(k)==physical.get(k) for k in ('key','hash','sha256','uuid')),
                            'packaged profile provider differs from its own original loaded image')
                identity=owner.get('image') if shared else {'key':key,'sha256':hashlib.sha256(original('app').read_bytes()).hexdigest(),
                    'uuid':row['input_uuid']}
                if application:
                    require(identity.get('key')==key and identity.get('sha256')==hashlib.sha256(original('app').read_bytes()).hexdigest(),
                            'packaged profile root image differs from own original bytes')
                elif shared:
                    root_image=metadata['task_provider'].get('image',{})
                    require(all(identity.get(k)==root_image.get(k) for k in ('runtime_key','runtime_hash')),
                            'packaged profile providers bind different runtime images')
                require(isinstance(identity,dict) and (identity.get('key'),identity.get('sha256'),identity.get('uuid'))==
                        (row['input_image_key'],row['input_image_sha256'],row['input_uuid']),
                        'packaged profile original image identity differs')
                identities[row['output_image']]=(row['component'],row['input_image_key'],row['input_image_sha256'],row['input_uuid'])
            else:
                catalog=json.loads(raw)
                require(catalog.get('schema')=='nex.task-profile-catalog/1' and catalog.get('registry_abi')==1 and
                        catalog.get('owner_image')==row['component'] and
                        identities.get(row['output_image'])==(row['component'],row['input_image_key'],row['input_image_sha256'],row['input_uuid']),
                        'packaged raw catalog differs from preceding physical provider')
            output=task_sdk_regular(package_root,row['output_image'])
            output_sha=hashlib.sha256(output.read_bytes()).hexdigest();inventory=package_meta.get('files',{}).get(row['output_image'],{})
            require(output_sha==row['output_image_sha256']==inventory.get('sha256') and output.stat().st_size==inventory.get('bytes'),
                    'packaged profile relocated image differs from output inventory')
        else:
            require(all(row[k] is None for k in ('component','input_image_key','input_image_sha256','input_uuid','output_image','output_image_sha256')),
                    'nonprovider profile provenance claims image identity')
        proof.append({'kind':kind,'original':str(original(name)),'path':row['path'],'sha256':sha,'bytes':len(raw),
            'compiler_validated_input_hash':row['input_hash']})
    return {'build_key':key,'files':proof,'verification':'matching compiler validated package completion BLAKE3; independent own-original/copied bytes, SHA256, sizes, raw metadata pins and relocated output inventory; no capture-index equivalence or Python BLAKE3 recomputation'}


def package_task_provenance(package_root,package_meta,project_root):
    """Check this package's own completed originals; capture keys may differ.

    The matching compiler verified its completion and produced BLAKE3 pins.
    This checker independently checks raw bytes/SHA/size, provider pins and the
    relocated output inventory. It does not recompute BLAKE3 in Python.
    """
    key=package_meta.get('build_key')
    require(isinstance(key,str) and re.fullmatch('[0-9a-f]{64}',key),'packaged task build key differs')
    prefix='.nex/build/'+key+'/'
    original=lambda name:task_sdk_regular(project_root,prefix+name,16*1024*1024)
    metadata=json.loads(original('build.json').read_text());links=json.loads(original('image-inputs.json').read_text())
    require(metadata.get('key')==key and metadata.get('completion_schema')=='nex.native-completion/5' and
            metadata.get('compiler_build')==package_meta.get('compiler_build') and
            links.get('schema')=='nex.native-image-inputs/2','package original completion/build identity differs')
    provenance=package_meta.get('task_provenance',{})
    require(isinstance(provenance,dict) and set(provenance)=={'schema','metadata_rewritten','hash_algorithm','files'} and
            provenance['schema']=='nex.application-task-provenance/1' and provenance['metadata_rewritten'] is False and
            provenance['hash_algorithm']=='BLAKE3' and isinstance(provenance['files'],list),
            'packaged raw task provenance differs')
    providers=links.get('task_providers');images=links.get('images')
    require(isinstance(providers,list) and len(providers)<=128 and
            all(isinstance(row,dict) and isinstance(row.get('path'),str) for row in providers) and
            isinstance(images,list) and all(isinstance(image,dict) for image in images) and
            sum(image.get('kind')=='runtime' for image in images)==1 and
            len(providers)==sum(image.get('kind')=='library' for image in images) and
            [row.get('path') for row in providers]==sorted({row.get('path') for row in providers}),
            'package original image/provider closure differs')
    expected=[('application_provider','task-provider.json',metadata.get('task_provider_hash'))]
    expected += [('owned_provider',row['path'],row['hash']) for row in providers]
    expected += [(kind,name,None) for kind,name in (('image_inputs','image-inputs.json'),('build','build.json'),('complete','complete'))]
    require(len(provenance['files'])==len(expected),'packaged task provenance count differs')
    result=[];total=0
    for index,(row,(kind,name,pin)) in enumerate(zip(provenance['files'],expected)):
        require(isinstance(row,dict) and set(row)=={'kind','path','input_hash','input_sha256','bytes','component',
                'input_image_key','input_image_sha256','input_uuid','output_image','output_image_sha256'} and
                row['kind']==kind and row['path']=='provenance/task/%03d-'%index+Path(name).name and
                type(row['bytes']) is int and 0<=row['bytes']<=16*1024*1024 and
                isinstance(row['input_hash'],str) and re.fullmatch('[0-9a-f]{64}',row['input_hash']) and
                (pin is None or row['input_hash']==pin),'packaged task provenance row/order/pin differs')
        total+=row['bytes'];require(total<=32*1024*1024,'packaged task provenance exceeds aggregate bound')
        raw=task_sdk_regular(package_root,row['path'],16*1024*1024).read_bytes();source=original(name).read_bytes()
        sha=hashlib.sha256(raw).hexdigest()
        require(raw==source and len(raw)==row['bytes'] and sha==row['input_sha256'],
                'packaged raw provenance changed its own completed original bytes')
        inventory=package_meta.get('files',{}).get(row['path'],{})
        require(inventory.get('sha256')==sha and inventory.get('bytes')==len(raw),
                'packaged raw provenance differs from package inventory')
        if kind in ('application_provider','owned_provider'):
            provider=json.loads(raw);image=provider.get('image',{})
            require(provider.get('schema')==('nex.native-task-provider/8' if provider.get('language')=='0.24' else 'nex.native-task-provider/5' if provider.get('language')=='0.23' else 'nex.native-task-provider/2') and provider.get('mode')=='shared-fixed' and
                    provider.get('component')==row['component'] and provider.get('owner_image')==row['component'] and
                    image.get('key')==row['input_image_key'] and image.get('sha256')==row['input_image_sha256'] and
                    image.get('uuid')==row['input_uuid'] and isinstance(row['output_image'],str),
                    'packaged task original image association differs')
            if kind=='application_provider':
                require(provider==metadata.get('task_provider') and image['key']==key and
                        row['output_image']==package_meta.get('entry') and provider.get('artifact_kind')=='application',
                        'packaged application provider differs from its own completed root')
            else:
                selected=next(value for value in providers if value['path']==name)
                physical=next((value for value in images if Path(value['path']).name==Path(selected['image']).name),{})
                require(provider.get('component')==selected['component'] and provider.get('artifact_kind')=='shared-image' and
                        physical.get('kind')=='library' and all(image.get(k)==physical.get(k) for k in ('key','hash','sha256','uuid')),
                        'packaged provider differs from its own completed loaded image')
            output=task_sdk_regular(package_root,row['output_image'])
            output_sha=hashlib.sha256(output.read_bytes()).hexdigest()
            indexed=package_meta.get('files',{}).get(row['output_image'],{})
            require(output_sha==row['output_image_sha256']==indexed.get('sha256') and
                    output.stat().st_size==indexed.get('bytes'),'packaged relocated task image differs from output inventory')
        else:
            require(all(row[name] is None for name in ('component','input_image_key','input_image_sha256','input_uuid',
                    'output_image','output_image_sha256')),'nonprovider package provenance claims an image')
        result.append({'kind':kind,'original':str(original(name)),'path':row['path'],'sha256':sha,'bytes':len(raw),
            'compiler_validated_input_hash':row['input_hash']})
    return {'build_key':key,'files':result,'verification':'matching compiler validated package completion BLAKE3; independent own-original/copied bytes, SHA256, sizes, provider pins and output inventory; no capture-index equivalence or Python BLAKE3 recomputation'}


def merge_notice_components(*groups):
    """Deduplicate reviewed metadata, allowing identical relocated licenses."""
    selected = {}
    signatures = {}
    for group in groups:
        for component in group:
            item = {field: component[field] for field in
                    ('name', 'version', 'url', 'roots', 'license_files')}
            item['roots'] = [str(Path(value).resolve(strict=True)) for value in item['roots']]
            item['license_files'] = [str(Path(value).resolve(strict=True)) for value in item['license_files']]
            signature = (item['version'], item['url'], tuple(sorted(set(item['roots']))),
                         tuple(sorted(hashlib.sha256(Path(value).read_bytes()).hexdigest()
                                      for value in item['license_files'])))
            name = item['name']
            require(name not in signatures or signatures[name] == signature,
                    'conflicting package notice component: ' + name)
            signatures[name] = signature
            selected[name] = item
    return list(selected.values())


def external_crypto_components(sdk, crypto_path, reviewed=()):
    """Review external provider metadata before capturing package task inputs."""
    sdk = Path(sdk).resolve(strict=True)
    crypto = Path(crypto_path).resolve(strict=True)
    if sdk in crypto.parents:
        return []
    matching = [component for component in reviewed
                if any(crypto == Path(root).resolve(strict=True) or
                       Path(root).resolve(strict=True) in crypto.parents
                       for root in component['roots'])]
    if matching:
        return merge_notice_components(matching)
    if platform.system() == 'Linux':
        from sdk_bundle import DebianNotices
        installed = []
        DebianNotices(installed).component(crypto)
        # Task notice inputs intentionally accept only these reviewed fields.
        return [{name: component[name] for name in
                 ('name', 'version', 'url', 'roots', 'license_files')}
                for component in installed]
    prefix = crypto.parent.parent
    license_file = next((prefix / name for name in ('LICENSE.txt', 'LICENSE')
                         if (prefix / name).is_file()), None)
    require(license_file is not None, 'development Crypto installation needs its complete vendor license')
    return [{'name': 'acceptance-crypto', 'version': 'installed-vendor',
             'url': 'https://openssl-library.org', 'roots': [str(prefix)],
             'license_files': [str(license_file)]}]


def project_notice_components(project, *groups):
    """Copy full reviewed license bytes inside the project before task capture."""
    project = Path(project).resolve(strict=True)
    components = merge_notice_components(*groups)
    directory = project / 'reviewed-package-licenses'
    directory.mkdir()
    captured = []
    for i, component in enumerate(components):
        licenses = []
        for j, original in enumerate(component['license_files']):
            target = directory / ('%d-%d.txt' % (i, j))
            shutil.copyfile(original, target)
            licenses.append(str(target.relative_to(project)))
        captured.append({**component, 'license_files': licenses})
    return captured


def lldb_script_import(script):
    # LLDB parses command arguments, not JSON Unicode escape sequences. Keep
    # UTF-8 path characters literal while quoting spaces, quotes and slashes.
    return 'command script import ' + json.dumps(str(script), ensure_ascii=False)


def standalone_crypto_link(doctor):
    # Bundled Darwin libraries use @rpath install names; ELF bundles also need
    # their selected SDK directory at runtime. Pass linker operands separately
    # so commas, quotes, backslashes and UTF-8 stay literal.
    library = doctor['native_openssl_crypto']
    flags = [library]
    if platform.system() in ('Darwin', 'Linux'):
        flags += ['-Xlinker', '-rpath', '-Xlinker', str(Path(library).parent)]
    if platform.system() == 'Linux':
        flags.append('-ldl')
    return flags


def _stream_host_contract():
    # Validators may be loaded by absolute path from another SDK's controller.
    # Resolve this SDK's self-contained contract instead of ambient sys.path.
    import importlib.util
    spec=importlib.util.spec_from_file_location('nex_sdk_stream_host_contract',Path(__file__).with_name('sdk_task_streams.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def validate_task_http_evidence(report):
    """Validate this gate's receipt shape; other SDK gates remain mandatory."""
    http=report.get('evidence',{}).get('structured_task_http',{})
    delivery=http.get('delivery',{}) if isinstance(http,dict) else {}
    flags=('source_absent_execution','request_identity_preserved','TLS_verified','compiler_unchanged',
           'task_whole_file_and_stream_IO','grant_denial_and_path_containment',
           'trap_budget_deadline_disconnect_cleanup','public_HTTP_task_target')
    helper='tests/task_http_server.py'
    resources=report.get('resource_hashes',{})
    digest=resources.get(helper) if isinstance(resources,dict) else None
    require(report.get('language')=='0.24' and isinstance(http,dict) and isinstance(delivery,dict) and
            http.get('installed_helper') is True and isinstance(digest,str) and
            re.fullmatch('[0-9a-f]{64}',digest) and http.get('helper_sha256')==digest and
            delivery.get('helper_sha256')==digest and
            isinstance(http.get('delivery_report_sha256'),str) and
            re.fullmatch('[0-9a-f]{64}',http['delivery_report_sha256']) and
            delivery.get('schema')=='nex.task-http-server/1' and delivery.get('ok') is True and
            delivery.get('state')=='passed' and delivery.get('language')=='0.24' and
            isinstance(report.get('compiler_sha256'),str) and re.fullmatch('[0-9a-f]{64}',report['compiler_sha256']) and
            delivery.get('compiler_sha256')==report['compiler_sha256'] and
            all(delivery.get(key) is True for key in flags) and
            delivery.get('async_network_DB_claimed') is False and delivery.get('full_objective_complete') is False and
            all(type(delivery.get(key)) is int and delivery[key]==expected for key,expected in
                [('checks',148),('profiles',2),('concurrent_requests_each',8),('compiled_limit_ceiling_rejections',14)]),
            'SDK acceptance lacks actual installed public task HTTP/TLS execution')
    servers=delivery.get('servers',[]);images=delivery.get('images',[]);cancels=delivery.get('cancel_observations',[])
    require(isinstance(servers,list) and len(servers)==14 and all(isinstance(row,dict) for row in servers) and
            {row.get('number') for row in servers}==set(range(1,15)) and
            all(type(row.get('number')) is int and type(row.get('exit_code')) is int and row['exit_code']==0 and type(row.get('TLS')) is bool for row in servers) and
            sum(row['TLS'] for row in servers)==2 and
            isinstance(images,list) and len(images)==2 and all(isinstance(row,dict) for row in images) and {row.get('profile') for row in images}=={'debug','release'} and
            all(all(isinstance(row.get(key),str) and re.fullmatch('[0-9a-f]{64}',row[key])
                    for key in ('sha256','metadata_sha256')) and
                row.get('task_limits')=={'steps':100000000,'timeout_ms':5000,'workers':4} for row in images) and
            isinstance(cancels,list) and len(cancels)==2 and all(isinstance(row,dict) for row in cancels) and {row.get('profile') for row in cancels}=={'debug','release'} and
            all(row.get('code')=='E_CANCELLED' and row.get('opened_file_and_marker_before_disconnect') is True and
                row.get('sole_HTTP_worker_released_before_deadline') is True for row in cancels),
            'SDK task HTTP cleanup, TLS or compiled ceiling evidence differs')
    requests=delivery.get('requests',[])
    require(isinstance(requests,list) and len(requests)==50 and all(isinstance(row,dict) for row in requests) and
            all(type(row.get('TLS')) is bool and type(row.get('status')) is int for row in requests) and
            {status:sum(row['status']==status for row in requests) for status in [200,401,403,429,500,504]}==
            {200:34,401:2,403:6,429:2,500:4,504:2} and
            sum(row['TLS'] for row in requests)==4,
            'SDK task HTTP retained request outcomes differ')
    require(all(isinstance(row.get('response'),dict) and isinstance(row['response'].get('error'),dict) and
                row['response']['error'].get('code')=={401:'UNAUTHORIZED',429:'E_LIMIT',500:'E_DIV_ZERO',504:'E_TIMEOUT'}[row['status']]
                for row in requests if row['status'] in (401,429,500,504)) and
            all(row.get('response')==('VALIDATION' if row.get('path')=='/api/traversal' else 'CAPABILITY')
                for row in requests if row['status']==403),
            'SDK task HTTP control or file-authority diagnostics differ')
    echoes=[row for row in requests if row.get('path')=='/api/echo' and row['status']==200]
    require(len(echoes)==26 and sum(row['TLS'] for row in echoes)==2 and
            all(isinstance(row.get('response'),dict) and
                set(row['response'])=={'user','request_id','body','answer'} and
                row['response']['user'] in ('alice','bob') and row['response']['answer']=='42' and
                row['response']['body']==(row.get('input_body') or '') and
                isinstance(row.get('request_id'),str) and re.fullmatch('[0-9]+',row['request_id']) and
                row['response']['request_id']==row['request_id'] for row in echoes) and
            all(row['input_body']=='A🌍\0β' for row in echoes if row['TLS']),
            'SDK task HTTP authenticated identity or Unicode/NUL echo differs')


def validate_task_tcp_evidence(report):
    tcp=report.get('evidence',{}).get('structured_task_tcp',{})
    require(isinstance(tcp,dict),'SDK TCP evidence is missing')
    resources=report.get('resource_hashes',{})
    for key,script,schema in [('source','verify.py','nex.task-tcp-source-conformance/1'),('delivery','verify_delivery.py','nex.tcp-provider-delivery/1')]:
        observed=tcp.get(key,{})
        require(isinstance(observed,dict) and observed.get('schema')==schema and observed.get('ok') is True and
                observed.get('state')=='passed' and observed.get('language')==report.get('language')=='0.24' and
                observed.get('toolchain')==report.get('version') and observed.get('compiler_sha256')==report.get('compiler_sha256') and
                observed.get('source_projection') is False,
                'SDK TCP evidence lacks installed matching compiler execution')
        digest=resources.get('tools/tcp_provider/'+script)
        require(isinstance(digest,str) and re.fullmatch('[0-9a-f]{64}',digest) and
                observed.get('verification_source_sha256')==digest,
                'SDK TCP evidence helper identity differs')
    source=tcp['source'];delivery=tcp['delivery']
    names={'binary','ipv6','boundary','denied','invalid','overflow','reset','own-timeout','progress','cancel','parent-deadline','capacity'}
    cases=source.get('cases',[])
    require(type(source.get('case_count')) is int and source['case_count']==36 and isinstance(cases,list) and len(cases)==36 and
            all(isinstance(row,dict) and row.get('passed') is True for row in cases) and
            {(row.get('name'),row.get('mode')) for row in cases}=={(name,mode) for name in names for mode in ('eval','debug','release')} and
            all(row.get('expected_error')=={'cancel':'E_CANCELLED','parent-deadline':'E_TIMEOUT'}.get(row['name']) for row in cases),
            'SDK TCP evidence lacks complete actual source cases')
    require(all(isinstance(row.get('retired'),list) and row['retired'] and all(
                type(r.get('opened')) is int and r['opened']>=0 and r.get('closed')==r['opened'] and r.get('live')==0
                for r in row['retired']) for row in cases if row['name']!='invalid') and
            all(row.get('peer_connections')==0 for row in cases if row['name'] in ('invalid','denied')),
            'SDK TCP physical retirement or rejected connection evidence differs')
    require(all(delivery.get(key) is True for key in ('client_server_pruning','source_deleted_package','relocated_package')) and
            type(delivery.get('package_execution_network_connections')) is int and delivery['package_execution_network_connections']==1 and
            type(delivery.get('target_rejections')) is int and delivery['target_rejections']==22 and
            type(delivery.get('authority_rejections')) is int and delivery['authority_rejections']==18,
            'SDK TCP relocated delivery or authority evidence is missing')
    rows=delivery.get('rejections',[]);authorities=[row for row in rows if isinstance(row,dict) and 'mode' in row]
    require(len(rows)==40 and len(authorities)==18 and
            {(row.get('case'),row.get('mode')) for row in authorities}=={(name,mode) for name in
                ('no-grant','no-export','wrong-pin','wrong-signature','changed-module','changed-target-file') for mode in ('eval','debug','release')} and
            all(row.get('network_connections')==0 and row.get('code')=={'no-grant':'E_FFI_GRANT','no-export':'E_FFI_GRANT','wrong-pin':'E_FFI_HASH','wrong-signature':'E_FFI_SIGNATURE','changed-module':'E_FFI_HASH','changed-target-file':'E_FFI_HASH'}[row['case']] for row in authorities),
            'SDK TCP rejected execution outcomes differ')


def validate_completed_report(report):
    require(report.get('schema') == 'nex.sdk-acceptance/1' and report.get('ok') is True,
            'SDK acceptance did not complete successfully')
    phases = report.get('phases', [])
    require(tuple(phase.get('name') for phase in phases) == acceptance_phases(report.get('doctor',{}).get('version') or report.get('version','0.0.0')) and
            all(phase.get('status') == 'passed' for phase in phases),
            'SDK acceptance differs from the complete workflow phase contract')
    commands = report.get('commands', [])
    # Expected rejections and runtime traps have nonzero exit codes. Their
    # recorded status comes from the acceptance action's expected outcome.
    require(bool(commands) and all(command.get('status') == 'passed' for command in commands),
            'SDK acceptance contains an incomplete or failed command')
    doctor_version=report.get('doctor',{}).get('version')
    if report.get('version') is not None and doctor_version is not None:
        require(report['version']==doctor_version,'SDK acceptance version identities differ')
    version = (doctor_version or report.get('version', '0.0.0')).split('.')
    if len(version)==3 and all(part.isascii() and part.isdigit() for part in version) and tuple(map(int,version))>=(0,134,4):
        require(report.get('required_phases')==list(acceptance_phases(doctor_version or report.get('version','0.0.0'))),
                'SDK required phase declaration differs from public task HTTP workflow')
        validate_task_http_evidence(report)
    if len(version)==3 and all(part.isascii() and part.isdigit() for part in version) and tuple(map(int,version))>=(0,135,1):
        validate_task_tcp_evidence(report)
    if len(version)==3 and all(part.isascii() and part.isdigit() for part in version) and tuple(map(int,version))>=(0,134,0):
        streams=report.get('evidence',{}).get('structured_task_file_streams',{})
        delivery=streams.get('delivery',{});history=streams.get('histories',{})
        require(report.get('language')=='0.24' and streams.get('original_SDK_execution_claimed') is False and
                delivery.get('ok') is True and delivery.get('language')=='0.24' and
                delivery.get('compiler_sha256')==report.get('compiler_sha256') and
                type(delivery.get('native_reference_pairs')) is int and delivery['native_reference_pairs']==5 and
                delivery.get('rejected_programs')==3 and delivery.get('old_metadata_rejected_before_store') is True and
                isinstance(delivery.get('cases'),list) and len(delivery['cases'])==5 and
                {row.get('name') for row in delivery['cases']}=={'aliases','write_append','future_owner','scoped_cleanup','source_cancel'} and
                all(row.get('native_reference') is True and row.get('source_absent_native') is True for row in delivery['cases']),
                'SDK acceptance lacks actual public024 CLI stream execution')
        require(history.get('ok') is True and history.get('language')=='0.24' and
                history.get('compiler_sha256')==report.get('compiler_sha256') and
                history.get('genuine023_histories')==9 and history.get('genuine023_revisions')==27 and
                history.get('native_reference_pairs')==27 and history.get('rejected_migrations')==9 and
                isinstance(history.get('cases'),list) and len(history['cases'])==27 and
                len({row.get('origin_revision') for row in history['cases']})==27 and
                len({row.get('revision') for row in history['cases']})==27 and
                all(all(row.get(key) is True for key in ('all16_tables_schema_rows_ids_preserved',
                    'physical_sources_manifest_lock_preserved','idempotent','materialized_current_project_checked',
                    'source_absent_native','native_reference')) and row.get('origin_revision')!=row.get('revision')
                    for row in history['cases']) and
                all(isinstance(streams.get(key),str) and re.fullmatch('[0-9a-f]{64}',streams[key])
                    for key in ('delivery_report_sha256','history_report_sha256')),
                'SDK acceptance lacks all genuine023 public024 migrations and preserved histories')
    if len(version)==3 and all(part.isascii() and part.isdigit() for part in version) and tuple(map(int,version))>=(0,133,2):
        contract=_stream_host_contract();CASES,HEADERS,SOURCES=contract.CASES,contract.HEADERS,contract.SOURCES
        writes=report.get('evidence',{}).get('structured_task_file_writes',{})
        host=writes.get('private_stream_host',{}) if isinstance(writes,dict) else {}
        pins=host.get('installed_sources',{}) if isinstance(host,dict) else {}
        names=host.get('case_names',[]) if isinstance(host,dict) else []
        required={'tools/task_file_stream_host_acceptance.cpp',*('runtime/'+n for n in (*HEADERS,*SOURCES))}
        require(isinstance(host,dict) and host.get('schema')=='nex.installed-task-stream-host/1' and
                all(host.get(key) is True for key in ('ok','actual_partial_write','typed_open_no_raw_file_ids','original_grants',
                    'physical_quota_retention','single_CPU_worker_progress','cancel_physical_drain','immutable_input_snapshots',
                    'large_file_streaming','protocol_rejections')) and host.get('source_support') is False and
                type(host.get('cases')) is int and host['cases']==27 and isinstance(names,list) and len(names)==27 and
                all(isinstance(n,str) for n in names) and set(names)==set(CASES) and
                isinstance(host.get('probe_sha256'),str) and re.fullmatch('[0-9a-f]{64}',host['probe_sha256']) and
                isinstance(pins,dict) and set(pins)==required and all(isinstance(v,str) and re.fullmatch('[0-9a-f]{64}',v) for v in pins.values()),
                'SDK acceptance lacks actual installed private stream host evidence')
    if len(version)==3 and all(part.isascii() and part.isdigit() for part in version) and tuple(map(int,version))>=(0,133,1):
        writes=report.get('evidence',{}).get('structured_task_file_writes',{})
        history=writes.get('extended_histories',{}) if isinstance(writes,dict) else {}
        names={'resources','nominal','callable','imports','tasks','model-compute-device-imports'}
        require(isinstance(history,dict) and history.get('schema')=='nex.public-task-write-histories/1' and
                history.get('compiler_sha256')==report.get('compiler_sha256') and history.get('language')==report.get('language') and report.get('language') in ('0.23','0.24') and
                history.get('origin_SDK_sha256')=='a75421b899a7e47d617a8ef6257123f75db4ee4f9869fe2aa11c3be6b87bb1a8' and
                all(history.get(key) is True for key in ('ok','all16_tables_schema_rows_ids_preserved','native_reference','retained_web_tests')) and
                type(history.get('genuine022_histories')) is int and history['genuine022_histories']==6 and
                type(history.get('genuine022_revisions')) is int and history['genuine022_revisions']==18 and
                isinstance(history.get('origins'),list) and len(history['origins'])==6 and
                {row.get('name') for row in history['origins'] if isinstance(row,dict)}==names and
                all(isinstance(row,dict) and row.get('origin_SDK_sha256')==history['origin_SDK_sha256'] and type(row.get('revisions')) is int and row['revisions']==3 and
                    isinstance(row.get('sql_sha256'),str) and re.fullmatch('[0-9a-f]{64}',row['sql_sha256']) for row in history['origins']) and
                isinstance(history.get('migrations'),list) and len(history['migrations'])==18 and
                all(isinstance(row,dict) and all(row.get(key) is True for key in ('all16_tables_schema_rows_ids_preserved',
                    'native_reference','retained_web_tests','implicit_HEAD_upgrade_rejected','physical_manifest_unchanged','idempotent')) and
                    all(isinstance(row.get(key),str) and re.fullmatch('[0-9a-f]{64}',row[key]) for key in ('origin_revision','revision')) and
                    row['origin_revision']!=row['revision'] for row in history['migrations']) and
                len({row['origin_revision'] for row in history['migrations']})==18 and len({row['revision'] for row in history['migrations']})==18,
                'SDK acceptance lacks extended genuine022 history evidence')
    if len(version)==3 and all(part.isascii() and part.isdigit() for part in version) and tuple(map(int,version))>=(0,133,0):
        writes=report.get('evidence',{}).get('structured_task_file_writes',{})
        require(isinstance(writes,dict) and writes.get('schema')=='nex.public-task-write-delivery/1' and
                writes.get('language')==report.get('language') and report.get('language') in ('0.23','0.24') and writes.get('compiler_sha256')==report.get('compiler_sha256') and
                all(writes.get(key) is True for key in ('ok','all16_tables_schema_rows_ids_preserved','native_reference',
                    'static_shared_binary_edges','mixed_static_shared','explicit_write_grant_denied','source_deleted_package','source_deleted_replay','browser_exclusion')) and
                type(writes.get('genuine022_migrations')) is int and writes['genuine022_migrations']==3 and
                isinstance(writes.get('migrations'),list) and len(writes['migrations'])==3 and
                isinstance(writes.get('projects'),list) and len(writes['projects'])==3 and
                {row.get('mode') for row in writes['projects'] if isinstance(row,dict)}=={'static','shared','mixed'} and
                all(isinstance(row,dict) and all(row.get(key) is True for key in
                    ('actual_binary_edges','native_reference','write_grant_denied','source_deleted_package','source_deleted_replay')) for row in writes['projects']) and
                all(isinstance(row,dict) and all(row.get(key) is True for key in
                    ('origin_verified','all16_tables_schema_rows_ids_preserved','physical_projection_unchanged','implicit_upgrade_rejected','native_reference')) and
                    all(isinstance(row.get(key),str) and re.fullmatch('[0-9a-f]{64}',row[key]) for key in ('origin_revision','revision')) and
                    row['origin_revision']!=row['revision'] for row in writes['migrations']) and
                len({row['origin_revision'] for row in writes['migrations']})==3,
                'SDK acceptance lacks actual public023 task file-write delivery evidence')
    if len(version)==3 and all(part.isascii() and part.isdigit() for part in version) and tuple(map(int,version))>=(0,132,6):
        migration=report.get('evidence',{}).get('task_file_migration',{})
        guard=migration.get('head_language_guard',{}) if isinstance(migration,dict) else {}
        stores=migration.get('stores',{}) if isinstance(migration,dict) else {}
        require(isinstance(guard,dict) and guard.get('schema')=='nex.head-language-guard/1' and
                guard.get('compiler_language')==report.get('language') and guard.get('origin_language')=='0.19' and
                guard.get('fixtures')==['history','tasks'] and guard.get('command')=='check' and
                guard.get('code')=='E_LANGUAGE_VERSION' and all(guard.get(key) is True for key in
                    ('actual_cli','all16_tables_schema_rows_ids_preserved','physical_projection_restored')) and
                isinstance(stores,dict) and all(isinstance(stores.get(name),dict) and
                    stores[name].get('implicit_HEAD_language_change_rejected') is True for name in ('history','tasks')),
                'SDK acceptance lacks actual retained HEAD language guard evidence')
    if len(version)==3 and all(part.isascii() and part.isdigit() for part in version) and tuple(map(int,version))>=(0,132,3):
        require(report.get('evidence',{}).get('owned_device_contract',{}).get('log_harness_installed') is True,
                'SDK acceptance lacks installed owned device log harness')
    if len(version)==3 and all(part.isascii() and part.isdigit() for part in version) and tuple(map(int,version))>=(0,132,2):
        require(report.get('evidence',{}).get('owned_device_contract',{}).get('fault_harness_installed') is True,
                'SDK acceptance lacks installed owned device fault harness')
    if len(version)==3 and all(part.isascii() and part.isdigit() for part in version) and tuple(map(int,version))>=(0,132,0):
        device=report.get('evidence',{}).get('owned_device_contract',{})
        require(isinstance(device,dict) and all(device.get(key) is True for key in
                ('descriptor','native_reference','typescript_reference','installed_provider_source_checked')),
                'SDK acceptance lacks installed owned device contract evidence')
        preparation=device.get('preparation',{})
        require(isinstance(preparation,dict) and preparation.get('schema')=='nex.owned-opencl-preparation/1' and
                preparation.get('ok') is True and preparation.get('source_checked') is True and
                preparation.get('compiler_sha256')==report.get('compiler_sha256') and
                preparation.get('source_language')==report.get('language') and
                all(preparation.get(key) is False for key in ('native_provider_built','driver_initialized','hardware_executed')) and
                isinstance(preparation.get('signature_sha256'),dict) and
                set(preparation['signature_sha256'])=={'open','upload','dispatch','download','name','kernel_ns','busy'} and
                all(isinstance(pin,str) and re.fullmatch('[0-9a-f]{64}',pin) for pin in preparation['signature_sha256'].values()),
                'SDK acceptance lacks actual owned device preparation evidence')
    if len(version)==3 and all(part.isascii() and part.isdigit() for part in version) and tuple(map(int,version))>=(0,131,0):
        dependent=report.get('evidence',{}).get('dependent_resource_ffi',{})
        require(isinstance(dependent,dict) and type(dependent.get('source_checks')) is int and dependent['source_checks']==37 and
                all(dependent.get(key) is True for key in ('ok','native_reference','genuine_previous_C_prefix',
                    'hidden_parent_scope_future_channel_closure','physical_parent_quota','cancel_deadline_borrow_fence','source_deleted_replay','client_exclusion')),
                'SDK acceptance lacks installed dependent resource FFI evidence')
        proof=dependent.get('source_report',{})
        require(isinstance(proof,dict) and proof.get('schema')=='nex.dependent-resource-source/1' and
                proof.get('ok') is True and proof.get('source_parent_FFI') is True and proof.get('compiler_sha256')==report.get('compiler_sha256') and
                isinstance(proof.get('checks'),list) and len(proof['checks'])==37 and
                proof.get('actual_producers')==['C11','CPP20'] and proof.get('actual_GPU_NPU_resources') is False,
                'SDK acceptance lacks actual dependent resource source report')
    if len(version)==3 and all(part.isascii() and part.isdigit() for part in version) and tuple(map(int,version))>=(0,130,0):
        require(report.get('version')==report.get('doctor',{}).get('version') and report.get('language')==('0.24' if tuple(map(int,version))>=(0,134,0) else '0.23' if tuple(map(int,version))>=(0,133,0) else '0.22'),
                'SDK acceptance source task/FFI version identities differ')
        resources=report.get('evidence',{}).get('source_resources',{})
        require(isinstance(resources,dict),'SDK acceptance lacks installed public source task/FFI resource transport evidence')
        producers=resources.get('producers',[])
        require(resources.get('ok') is True and isinstance(producers,list) and len(producers)==2 and
                all(isinstance(row,dict) and isinstance(row.get('language'),str) for row in producers) and
                {row.get('language') for row in producers}=={'C11','CPP20'} and
                all(row.get(key) is True for row in producers for key in
                    ('native_reference','destruction_before_unload','checked_exit70_cleanup','source_task_FFI',
                     'scope_channel_result_transfer','physical_quota_settled','source_deleted_task_replay')),
                'SDK acceptance lacks installed public source task/FFI resource transport evidence')
        migrations=resources.get('task_foreign_migration',{})
        require(isinstance(migrations,dict) and set(migrations)=={'resources','nominal','callable','imports','tasks'} and
                all(isinstance(row,dict) and type(row.get('original_revisions')) is int and
                    row['original_revisions']==3 and all(row.get(key) is True for key in
                    ('origin_verified','all16_tables_schema_rows_ids_preserved','native_reference','actual_retained_tests'))
                    for row in migrations.values()),
                'SDK acceptance lacks installed genuine021 public task/FFI migration evidence')
        model=report.get('evidence',{}).get('model_contract',{})
        require(model.get('preparer_source_checked') is True and model.get('preparer_source_language')==report.get('language'),
                'SDK acceptance lacks current model provider source preparation evidence')
    if len(version)==3 and all(part.isascii() and part.isdigit() for part in version) and tuple(map(int,version))>=(0,129,0):
        ownership=report.get('evidence',{}).get('source_resources',{}).get('request_resources',{})
        require(ownership.get('primitive_cases')==17 and ownership.get('native_cases')==13 and
                ownership.get('source_value_transport') is False and ownership.get('installed_reference_private_host_gate') is False and all(ownership.get(key) is True for key in
                ('ok','native_per_task_ownership','future_publication_waits_physical_settlement','caller_borrow_survives_group',
                 'explicit_request_return_preserves_identity','sibling_authority_refused','single_source_worker_progress_during_cleanup',
                 'cancel_deadline_physical_fence','combined_256_task_scope_depth','ancestor_spawn_preserves_lifetime','unpublished_creation_physical_fence')),
                'SDK acceptance lacks installed native task/request resource ownership evidence')
    if len(version)==3 and all(part.isascii() and part.isdigit() for part in version) and tuple(map(int,version))>=(0,128,0):
        values=report.get('evidence',{}).get('source_resources',{}).get('task_value_retirement',{})
        require(values.get('cases')==15 and all(values.get(key) is True for key in
                ('ok','destructors_outside_scheduler_mutex','cancelled_event_cleanup','task_scope_publication_fence',
                 'buffer_storage_quota_fence','nested_reentrant_cleanup','root_results_remain_joinable','iterative_256_scope_retirement','api_cleanup_isolation','stolen_completion_fence')),
                'SDK acceptance lacks installed task value retirement evidence')
    if len(version)==3 and all(part.isascii() and part.isdigit() for part in version) and tuple(map(int,version))>=(0,126,0):
        regions=report.get('evidence',{}).get('source_resources',{}).get('resource_regions',{})
        require(regions.get('cases')==18 and all(regions.get(key) is True for key in
                ('ok','native_scope_ownership','scope_exit_waits_physical_cleanup','only_source_worker_remains_available',
                 'native_256_scope_depth','ancestor_promotion','root_group_retirement','prepared_access_survives_64_resumes','unpublished_factory_fence')),
                'SDK acceptance lacks installed logical resource region lifetime evidence')
    if len(version)==3 and all(part.isascii() and part.isdigit() for part in version) and tuple(map(int,version))>=(0,125,0):
        executor=report.get('evidence',{}).get('source_resources',{}).get('resource_executor',{})
        require(executor.get('cases')==21 and all(executor.get(key) is True for key in
                ('ok','owning_thread_factory_cleanup','physical_fence_and_quota_retention','queued_running_cancellation',
                 'actual_module_destructor_unload','module_exceptions_destroyed_before_unload')),
                'SDK acceptance lacks installed physical resource executor lifetime evidence')
    if len(version)==3 and all(part.isascii() and part.isdigit() for part in version) and tuple(map(int,version))>=(0,124,0) and report.get('evidence',{}).get('live_debugger'):
        debug=report.get('evidence',{}).get('source_resources',{}).get('resource_debug',{})
        require(all(debug.get(key) is True for key in ('ok','actual_resource_DAP','native_CLI_arguments_delivered_once','source_deleted_archived_debug','opaque_resource_aliases','resource_watch_authority_refused','stale_references_refused','destruction_before_unload','graceful_adapter_shutdown')),
                'SDK acceptance lacks actual resource CLI/DAP arguments, archived values, safe watches and graceful cleanup')
    if len(version)==3 and all(part.isascii() and part.isdigit() for part in version) and tuple(map(int,version))>=(0,123,0):
        resources=report.get('evidence',{}).get('source_resources',{})
        require(all(resources.get(key) is True for key in ('ok','descriptor','genuine020','history_preserved','native_reference','actual_C11_CPP20','checked_cleanup')) and
                resources.get('original_revisions_preserved')==15 and len(resources.get('producers',[]))==2,
                'SDK acceptance lacks actual opaque resource, checked cleanup and genuine020 migration evidence')
    if len(version)==3 and all(part.isascii() and part.isdigit() for part in version) and tuple(map(int,version))>=(0,122,0):
        model=report.get('evidence',{}).get('model_contract',{})
        require(all(model.get(key) is True for key in ('descriptor','native_reference','typescript_reference',
                'source_deleted_replay','standalone','managed_memory_balanced','preparer_installed')),
                'SDK acceptance lacks checked model contract delivery evidence')
    if len(version)==3 and all(part.isascii() and part.isdigit() for part in version) and tuple(map(int,version))>=(0,121,0):
        compute=report.get('evidence',{}).get('compute_contract',{})
        require(all(compute.get(key) is True for key in ('descriptor','native_reference','typescript_reference',
                'source_deleted_replay','standalone','cpu_device_reported')),
                'SDK acceptance lacks checked compute contract delivery evidence')
    if len(version) == 3 and all(part.isascii() and part.isdigit() for part in version) and tuple(map(int, version)) >= (0, 119, 0):
        provider_debug=report.get('evidence',{}).get('task_provider_debugging',{})
        require(all(provider_debug.get(key) is True for key in ('descriptor','native_reference','static_and_shared_artifacts',
                'original_registry_symbols','closed_owned_images','source_union','retained_completion7','raw_package_provenance',
                'source_deleted_capture','source_deleted_replay')),
                'SDK acceptance lacks task provider debugger delivery evidence')
        if report.get('evidence',{}).get('live_debugger'):
            require(all(provider_debug.get(key) is True for key in ('provider_locals','component_pure_watch','next_in_out',
                    'stale_references','retained_live_debug','package_live_debug','replay_live_debug')),
                    'SDK acceptance lacks actual task provider debugger execution evidence')
    if len(version) == 3 and all(part.isascii() and part.isdigit() for part in version) and tuple(map(int, version)) >= (0, 118, 0):
        profiles=report.get('evidence',{}).get('task_provider_profiling',{})
        require(all(profiles.get(key) is True for key in ('descriptor','native_reference','exact_source_calls',
                'zero_provider_generic','physical_owners','defined_registry_accessors','one_runtime','managed_cleanup',
                'event_only_completeness','root_limits','unused_read_excluded','warm_cache','measured_retained_completion6',
                'raw_package_provenance','source_deleted_replay','copied_profile_without_resources','source_deleted_package_profile')),
                'SDK acceptance lacks complete native task provider profiling delivery evidence')
    if len(version) == 3 and all(part.isascii() and part.isdigit() for part in version) and tuple(map(int, version)) >= (0, 117, 0):
        providers = report.get('evidence', {}).get('shared_task_providers', {})
        require(all(providers.get(key) is True for key in ('descriptor','actual_shared_images',
                'defined_descriptor_accessors','consumer_ownership','actual_loaded_closure','one_runtime',
                'native_reference','unused_read_excluded','root_file_grant','root_limits','warm_cache',
                'retained_completion5','raw_package_provenance','source_deleted_replay',
                'copied_closure_without_resources','source_deleted_package')),
                'SDK acceptance lacks complete fixed shared task provider delivery evidence')
    if len(version) == 3 and all(part.isascii() and part.isdigit() for part in version) and tuple(map(int, version)) >= (0, 116, 0):
        providers = report.get('evidence', {}).get('static_task_providers', {})
        require(all(providers.get(key) is True for key in ('descriptor', 'actual_static_archives',
                'descriptor_accessors', 'consumer_ownership', 'native_reference', 'unused_read_excluded',
                'root_file_grant', 'root_limits', 'warm_cache', 'retained_completion',
                'source_deleted_replay', 'standalone_without_resources', 'source_deleted_package')),
                'SDK acceptance lacks complete static task provider delivery evidence')
    if len(version) == 3 and all(part.isascii() and part.isdigit() for part in version) and tuple(map(int, version)) >= (0, 115, 0):
        debug = report.get('evidence', {}).get('structured_task_debug', {})
        require(all(debug.get(key) is True for key in ('descriptor', 'actual_image_identity',
                'source_deleted_archive', 'source_only_project', 'standalone_without_resources')),
                'SDK acceptance lacks complete native task debugger delivery evidence')
        if report.get('evidence', {}).get('live_debugger'):
            require(all(debug.get(key) is True for key in ('logical_stack', 'initialized_locals',
                    'pure_watch', 'logical_step', 'stale_references_rejected', 'graceful_exit')),
                    'SDK acceptance lacks actual logical task debugger execution evidence')
    if len(version) == 3 and all(part.isascii() and part.isdigit() for part in version) and tuple(map(int, version)) >= (0, 114, 0):
        profile = report.get('evidence', {}).get('structured_task_profile', {})
        require(all(profile.get(key) is True for key in ('native_reference', 'exact_source_calls',
                'managed_cleanup', 'event_only_truncation', 'archived_source_deleted',
                'standalone_without_resources', 'source_only_project', 'source_deleted_replay')),
                'SDK acceptance lacks complete local native task profile delivery evidence')
    if len(version) == 3 and all(part.isascii() and part.isdigit() for part in version) and tuple(map(int, version)) >= (0, 110, 0):
        reads = report.get('evidence', {}).get('structured_task_file_reads', {})
        require(all(reads.get(key) is True for key in ('native_reference', 'standalone_without_resources',
                'source_only_project', 'source_deleted_package', 'source_deleted_replay')),
                'SDK acceptance lacks actual public task file-read delivery evidence')
        migration = report.get('evidence', {}).get('task_file_migration', {})
        require(migration.get('ok') is True and migration.get('genuine019') is True and
                migration.get('history_preserved') is True,
                'SDK acceptance lacks genuine019 migration and retained history evidence')
    if len(version) == 3 and all(part.isascii() and part.isdigit() for part in version) and tuple(map(int, version)) >= (0, 92, 0):
        cpu = report.get('evidence', {}).get('cpu_mapping', {})
        require(all(cpu.get(key) is True for key in ('native_reference', 'typescript',
                'profile_cleanup', 'source_deleted', 'standalone_without_resources', 'overlapping_callbacks')) and
                len(cpu.get('thread_ids', [])) >= 2,
                'SDK acceptance lacks actual ordered CPU mapping/thread/ownership/replay evidence')
    if len(version) == 3 and all(part.isascii() and part.isdigit() for part in version) and tuple(map(int, version)) >= (0, 89, 0):
        propagation = report.get('evidence', {}).get('result_propagation', {})
        require(all(propagation.get(key) is True for key in ('native_reference', 'typescript',
                'profile_cleanup', 'source_deleted', 'standalone_without_resources')),
                'SDK acceptance lacks complete result propagation evidence')
        if report.get('evidence', {}).get('live_debugger'):
            require(report.get('evidence', {}).get('dap_shutdown_checks', 0) >= 2,
                    'SDK acceptance lacks checked normal DAP adapter shutdowns')
    if len(version) == 3 and all(part.isascii() and part.isdigit() for part in version) and tuple(map(int, version)) >= (0, 59, 0):
        core = report.get('evidence', {}).get('core_reports', {})
        require(core.get('capsule_helper_input_rejected') is True,
                'SDK acceptance lacks the installed core capsule helper control')
        if report.get('evidence', {}).get('live_debugger'):
            capsule = core.get('capsule_report', {})
            require(core.get('actual_capsule_read') is True and core.get('original_executable_absent') is True and
                    capsule.get('capsule', {}).get('inventory_checked') is True and
                    capsule.get('watch', {}).get('value') == 'Я🧠2' and not capsule.get('inferior_execution', True),
                    'SDK acceptance lacks actual source-deleted moved core capsule evidence')
    if len(version) == 3 and all(part.isascii() and part.isdigit() for part in version) and tuple(map(int, version)) >= (0, 60, 0):
        wasm = report.get('evidence', {}).get('wasm_compute', {})
        require(all(wasm.get(key) is True for key in ('exact_bigint', 'checked_overflow',
                'input_rejection', 'resource_stop', 'post_trap_recovery', 'module_integrity',
                'source_deleted', 'independent_runtime', 'cache_integrity', 'server_exclusion')),
                'SDK acceptance lacks complete installed scalar Wasm evidence')
    if len(version) == 3 and all(part.isascii() and part.isdigit() for part in version) and tuple(map(int, version)) >= (0, 84, 0):
        foreign = report.get('evidence', {}).get('foreign_boundary', {}).get('source_external', {}).get('project_package', {})
        require(all(foreign.get(key) is True for key in ('actual_shared_provider', 'task_package',
                'source_deleted_replay', 'module_inputs_deleted', 'environment_without_sdk', 'nominal_contract_agreement')),
                'SDK acceptance lacks complete installed foreign project packaging evidence')
    if len(version) == 3 and all(part.isascii() and part.isdigit() for part in version) and tuple(map(int, version)) >= (0, 85, 0):
        server=report.get('evidence',{}).get('server_debug',{})
        require(server.get('descriptor') is True and server.get('actual_shared_provider') is True and server.get('editor_preparation') is True,
                'SDK acceptance lacks checked server/editor debug preparation')
        if report.get('evidence',{}).get('live_debugger'):
            require(all(server.get(key) is True for key in ('live_worker_stop','source_deleted','request_completed','graceful_exit')),
                    'SDK acceptance lacks actual source-deleted HTTP worker debugging')


class DAP:
    """Small bounded client for the installed stdio adapter, with no test imports."""
    successful_shutdowns = 0
    def __init__(self, command, directory, environment):
        self.log = (directory / 'dap-stderr.log').open('wb')
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=self.log, env=environment)
        self.messages = queue.Queue()
        self.pending = []
        self.sequence = 0

        def read():
            try:
                while True:
                    headers = {}
                    while True:
                        line = self.process.stdout.readline(8193)
                        if not line:
                            return
                        require(len(line) <= 8192, 'oversized DAP header')
                        if line == b'\r\n':
                            break
                        key, value = line.decode().split(':', 1)
                        headers[key.lower()] = value.strip()
                    size = int(headers['content-length'])
                    require(0 < size <= 4 * 1024 * 1024, 'oversized DAP message')
                    body = bytearray()
                    while len(body) < size:
                        part = self.process.stdout.read(size - len(body))
                        require(part, 'truncated DAP message')
                        body.extend(part)
                    self.messages.put(json.loads(body))
            except Exception as error:
                self.messages.put(error)
            finally:
                self.messages.put(None)

        self.reader = threading.Thread(target=read, daemon=True)
        self.reader.start()

    def send(self, command, arguments=None):
        self.sequence += 1
        body = json.dumps({'seq': self.sequence, 'type': 'request',
                           'command': command, 'arguments': arguments or {}}).encode()
        self.process.stdin.write(('Content-Length: %d\r\n\r\n' % len(body)).encode() + body)
        self.process.stdin.flush()
        return self.sequence

    def wait(self, predicate, timeout=30):
        deadline = time.monotonic() + timeout
        while True:
            for index, message in enumerate(self.pending):
                if predicate(message):
                    return self.pending.pop(index)
            message = self.messages.get(timeout=max(.01, deadline - time.monotonic()))
            require(message is not None and not isinstance(message, Exception),
                    'DAP stream stopped: ' + str(message))
            self.pending.append(message)

    def response(self, sequence):
        value = self.wait(lambda m: m.get('type') == 'response' and m.get('request_seq') == sequence)
        require(value.get('success'), 'DAP request failed: ' + str(value))
        return value.get('body', {})

    def request(self, command, arguments=None):
        return self.response(self.send(command, arguments))

    def event(self, name):
        return self.wait(lambda m: m.get('type') == 'event' and m.get('event') == name).get('body', {})

    def close(self):
        try:
            if self.process.poll() is None:
                try:
                    self.send('disconnect', {'terminateDebuggee': True})
                    self.process.stdin.close()
                    self.process.wait(timeout=5)
                except (Exception, KeyboardInterrupt):
                    self.process.kill()
                    self.process.wait(timeout=5)
        finally:
            self.process.stdin.close()
            self.reader.join(timeout=5)
            self.process.stdout.close()
            self.log.close()
        require(not self.reader.is_alive(), 'DAP output reader failed to stop')
        require(self.process.returncode == 0,
                'DAP adapter failed during shutdown: exit ' + str(self.process.returncode))
        DAP.successful_shutdowns += 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sdk', type=Path, help='Installed SDK prefix containing bin/nex and share/nex')
    parser.add_argument('--output', required=True, type=Path, help='New or empty evidence directory')
    parser.add_argument('--live', action='store_true', help='Require actual LLDB and NEX DAP child launches')
    parser.add_argument('--browser', action='store_true', help='Require a real locked TypeScript/Vite release build')
    parser.add_argument('--package-notices', type=Path,
                        help='Additional operator nex.sdk-notices/1 provenance for private application/module runtime dependencies')
    parser.add_argument('--forbid-source', action='append', type=Path, default=[],
                        help='Require this source mount path to be absent (repeatable)')
    args = parser.parse_args()
    sdk = args.sdk.resolve()
    root = args.output.resolve()
    resources = sdk / 'share/nex'
    compiler = sdk / 'bin/nex'
    if not compiler.is_file() or not (resources / 'llm/language-pack.json').is_file():
        parser.error('sdk must be an installed NEX SDK')
    if root == sdk or sdk in root.parents:
        parser.error('--output must be outside the SDK')
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        parser.error('--output must be new or empty; previous evidence is never replaced')
    root.mkdir(parents=True, exist_ok=True)
    # Source commands without a deeper manifest must remain inside this owned
    # evidence project, even when --output is below another NEX workspace.
    (root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.24','entry':'acceptance-scope.nex'})+'\n')
    (root/'acceptance-scope.nex').write_text('module acceptance_scope;fn main()->unit{}\n')
    logs = root / 'logs'
    logs.mkdir()
    environment = dict(os.environ, NEX_RESOURCE_DIR=str(resources))
    report = {'schema': 'nex.sdk-acceptance/1', 'ok': False, 'sdk': str(sdk),
              'output': str(root), 'required_phases': list(ACCEPTANCE_PHASES_024_TCP),
              'phases': [], 'commands': [], 'evidence': {}}
    started = time.monotonic()

    def notice_components(path):
        path = path.resolve(strict=True)
        document = json.loads(path.read_text())
        require(document.get('schema') == 'nex.sdk-notices/1', 'expected nex.sdk-notices/1')
        components = []
        for component in document['components']:
            item = dict(component)
            for field in ('roots', 'license_files'):
                item[field] = [str((path.parent / value).resolve(strict=True)) for value in item[field]]
            components.append(item)
        return components

    extra_notices = notice_components(args.package_notices) if args.package_notices else []
    if args.package_notices:
        report['package_notices'] = {'path': str(args.package_notices.resolve()),
            'sha256': hashlib.sha256(args.package_notices.read_bytes()).hexdigest()}

    def save():
        (root / 'report.json').write_text(json.dumps(report, indent=2) + '\n')

    def run(command, cwd=root, expected_success=True, timeout=180):
        command = list(map(str, command))
        project_package = (len(command) > 1 and command[0] == str(compiler) and
                           command[1] == 'project' and '--kind' in command and
                           command.index('--kind') + 1 < len(command) and
                           command[command.index('--kind') + 1] == 'package')
        packaging = (len(command) > 1 and
                     ((command[0] == str(compiler) and command[1] == 'package') or project_package or
                      command[1] == str(resources / 'tools/foreign_bundle.py')))
        if extra_notices and packaging:
            components = list(extra_notices)
            if '--notices' in command:
                index = command.index('--notices')
                notice_path = Path(command[index + 1])
                if not notice_path.is_absolute():
                    notice_path = Path(cwd) / notice_path
                components = merge_notice_components(components, notice_components(notice_path))
                del command[index:index + 2]
            directory = root / 'package-notices'; directory.mkdir(exist_ok=True)
            path = directory / ('%03d.json' % len(report['commands']))
            path.write_text(json.dumps({'schema': 'nex.sdk-notices/1', 'components': components}) + '\n')
            command += ['--notices', str(path)]
        number = len(report['commands'])
        row = {'command': list(map(str, command)), 'cwd': str(cwd),
               'stdout': str(logs / ('%03d.stdout' % number)),
               'stderr': str(logs / ('%03d.stderr' % number)), 'status': 'running'}
        report['commands'].append(row)
        save()
        with open(row['stdout'], 'wb') as out, open(row['stderr'], 'wb') as err:
            process = subprocess.Popen(row['command'], cwd=cwd, env=environment,
                                       stdout=out, stderr=err, start_new_session=True)
            try:
                code = process.wait(timeout=timeout)
            except BaseException:
                # Let NEX clean up task-owned children before escalating to SIGKILL.
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                    process.wait(timeout=10)
                except ProcessLookupError:
                    pass
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=10)
                row['status'] = 'interrupted'
                save()
                raise
        row.update(exit_code=code, status='passed' if (code == 0) == expected_success else 'failed')
        save()
        require(row['status'] == 'passed', 'unexpected command result; inspect ' + row['stderr'])
        return Path(row['stdout']).read_text()

    def cli(*arguments, cwd=root, expected_success=True, timeout=180):
        arguments=list(arguments);boundary=arguments.index('--') if '--' in arguments else len(arguments)
        arguments.insert(boundary,'--json')
        return json.loads(run([compiler, *arguments], cwd, expected_success, timeout))

    def phase(name, action):
        row = {'name': name, 'status': 'running'}
        report['phases'].append(row)
        save()
        action()
        row['status'] = 'passed'
        save()

    project = root / 'project'
    project.mkdir()
    state = {}
    expected = '42\nA\0🌍\n'
    model = '''module handoff_model;
pub enum Maybe<T> { None; Some(value:T); }
pub struct Box<T> { value:T; }
pub fn normalized<T:integer>(value:T) -> T { return value+0; }
pub fn capture<T>(value:T) -> (fn()->T) { return fn()->T { return value; }; }
pub fn roundtrip<T:wire>(value:T) -> T { return unwrap(decode_json<T>(encode_json(value))); }
'''
    choose = '''pub fn choose(value:result<model::Maybe<i64>>) -> i64 {
 return match value { ok(model::Maybe::Some(n)) if n>0 => model::normalized(n), _ => -1 };
}'''
    source = '''module handoff;
import "./model.nex" as model;
CHOOSE
fn observe(value:result<model::Maybe<i64>>,callback:fn()->i64) -> i64 {
 let answer:i64 = choose(value)+callback()-2;
 return answer; // sdk-breakpoint
}
fn main() -> unit !{io} {
 print(observe(ok(model::Maybe::Some(42)),model::capture(2)));
 print(model::Box("A\\u0000🌍").value);
}
test fn examples() -> unit {
 assert(choose(ok(model::Maybe::Some(42))) == 42);
 assert(choose(ok(model::Maybe<i64>::None())) == -1);
 assert(choose(err<model::Maybe<i64>>("E","unread")) == -1);
 assert(model::capture(40)()==40);
 assert(model::capture("A\\u0000🌍")()=="A\\u0000🌍");
 assert(model::roundtrip(["A\\u0000🌍"])==["A\\u0000🌍"]);
}
'''.replace('CHOOSE', choose.replace('model::normalized(n)', 'model::normalized(n)+1'))

    def compute_contract():
        descriptor=cli('describe','--field','compute')['value']
        pack=json.loads((resources/'llm/language-pack.json').read_text())
        require(descriptor==pack['compute'] and descriptor['source_support'] and
                descriptor['context_wire'] is False, 'compute descriptor differs from installed pack')
        require(cli('guide','--kind','compute')['text']==(resources/'docs/compute.md').read_text(),
                'compute guide not selected from installed SDK')
        directory=root/'compute-contract';directory.mkdir()
        shutil.copy2(resources/'examples/compute/main.nex',directory/'main.nex')
        (directory/'nex.json').write_text(json.dumps({'schema':'nex.project/1',
            'language':report['doctor']['language'],'entry':'main.nex'}))
        expected=cli('eval',cwd=directory)['stdout']
        cli('test',cwd=directory,timeout=240);cli('test','--target','web',cwd=directory,timeout=240)
        observed=cli('run','--profile','release',cwd=directory,timeout=240)
        require(observed['stdout']==expected,'compute native/reference observations differ')
        response=json.loads(expected.splitlines()[1])
        require(response['device']['kind']['case']=='CPU' and response['fallback_used'] is False and
                response['id']=='matrix-1','compute actual CPU response differs')
        built=cli('build','--profile','release',cwd=directory)
        copied=root/'compute-standalone';shutil.copy2(built['executable'],copied)
        (directory/'main.nex').unlink()
        require(cli('run','--revision',built['revision'],'--profile','release',cwd=directory)['stdout']==expected,
                'compute archived std library replay failed')
        before=environment.get('NEX_RESOURCE_DIR');environment['NEX_RESOURCE_DIR']=str(root/'unavailable-compute-resources')
        try:require(run([copied],cwd=root)==expected,'compute standalone output differs')
        finally:
            if before is None:environment.pop('NEX_RESOURCE_DIR',None)
            else:environment['NEX_RESOURCE_DIR']=before
        report['evidence']['compute_contract']={'descriptor':True,'native_reference':True,
            'typescript_reference':True,'source_deleted_replay':True,'standalone':True,'cpu_device_reported':True,
            'library_sha256':hashlib.sha256((resources/'lib/compute.nex').read_bytes()).hexdigest(),
            'revision':built['revision'],'copied_executable_resource_override':'unavailable',
            'generic_gpu_npu_execution_proved':False}
        owned=cli('describe','--field','device')['value']
        require(owned==pack['device'] and owned['source_support'] and owned['source_task_bridge'] and
                owned['context_wire'] is False,'owned device descriptor differs from installed pack')
        require(cli('guide','--kind','device')['text']==(resources/'docs/device.md').read_text(),
                'owned device guide not selected from installed SDK')
        directory=root/'owned-device-contract';directory.mkdir()
        shutil.copy2(resources/'examples/device/main.nex',directory/'main.nex')
        (directory/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':report['doctor']['language'],'entry':'main.nex'}))
        expected=cli('eval',cwd=directory)['stdout'];require(expected=='42\n','owned device metadata example failed')
        cli('test','--target','web',cwd=directory,timeout=240)
        require(cli('run','--profile','release',cwd=directory,timeout=240)['stdout']==expected,
                'owned device metadata native/reference differs')
        prepared=root/'owned-device-preparation'
        run([sys.executable,'-B',resources/'tools/owned-opencl/prepare.py','--sdk',sdk,'--output',prepared,'--check-sdk'],cwd=root,timeout=240)
        preparation=json.loads((prepared/'preparation/report.json').read_text())
        require(preparation['compiler_sha256']==report['compiler_sha256'] and preparation['source_checked'] is True,
                'owned device preparer did not check the installed compiler')
        fault_help=run([sys.executable,'-B',resources/'tools/owned-opencl/faults.py','--help'],cwd=root,timeout=60)
        require('upload_reused_id' in fault_help and 'execute_fallback_never_masks_protocol' in fault_help,
                'installed owned device fault harness is not callable')
        log_help=run([sys.executable,'-B',resources/'tools/owned-opencl/logs.py','--help'],cwd=root,timeout=60)
        require('--old-limit-red' in log_help,'installed owned device log harness is not callable')
        report['evidence']['owned_device_contract']={'descriptor':True,'native_reference':True,'typescript_reference':True,
            'installed_provider_source_checked':True,'preparation':preparation,'fault_harness_installed':True,'log_harness_installed':True,
            'library_sha256':hashlib.sha256((resources/'lib/device.nex').read_bytes()).hexdigest(),
            'hardware_execution_proved':False}

    def model_contract():
        descriptor=cli('describe','--field','model')['value']
        pack=json.loads((resources/'llm/language-pack.json').read_text())
        require(descriptor==pack['model'] and descriptor['source_support'] and
                descriptor['builtin_cpu_inference'] is False and descriptor['context_wire'] is False,
                'model descriptor differs from installed pack')
        require(cli('guide','--kind','model')['text']==(resources/'docs/models.md').read_text(),
                'model guide not selected from installed SDK')
        preparer=resources/descriptor['provider_preparation']['tool']
        for name in ('prepare.py','common.h','model-module.cpp','model-worker.cpp','model-broker.inc','main.nex.in'):
            require((preparer.parent/name).is_file(),'model provider preparation input is missing: '+name)
        require('ONNX' in run([sys.executable,preparer,'--help']), 'installed model preparer help differs')
        source_check=json.loads(run([sys.executable,preparer,'--sdk',sdk,'--check-sdk'],timeout=120))
        require(source_check.get('schema')=='nex.provider-sdk-check/1' and
                source_check.get('ok') is True and source_check.get('source_checked') is True and
                source_check.get('source_language')==report['doctor']['language'] and
                source_check.get('compiler_sha256')==report['compiler_sha256'] and
                source_check.get('hardware_executed') is False and source_check.get('native_worker_built') is False and
                source_check.get('temporary_project_removed') is True and
                set(source_check.get('signature_sha256',{}))=={'model_run'} and
                source_check.get('source_sha256')==hashlib.sha256(source_check.get('probe_source','').encode()).hexdigest() and
                source_check.get('library_sha256')=={name:hashlib.sha256((resources/'lib'/name).read_bytes()).hexdigest() for name in ('model.nex','compute.nex')},
                'installed model preparer did not check its actual current source template and signature')
        directory=root/'model-contract';directory.mkdir()
        shutil.copy2(resources/'examples/models/main.nex',directory/'main.nex')
        (directory/'nex.json').write_text(json.dumps({'schema':'nex.project/1',
            'language':report['doctor']['language'],'entry':'main.nex'}))
        expected=base64.b64encode(bytes.fromhex('000000c0000080bf000000000000803f0000004000004040')).decode()+'\n'
        require(cli('eval',cwd=directory)['stdout']==expected,'model binary32 reference bytes differ')
        cli('test',cwd=directory,timeout=240);cli('test','--target','web',cwd=directory,timeout=240)
        require(cli('run','--profile','release',cwd=directory,timeout=240)['stdout']==expected,
                'model native/reference observations differ')
        measured=cli('profile','--scenario','installed model tensor',cwd=directory,timeout=240)
        profile=json.loads(Path(measured['output']).read_text())
        require(profile['ok'] and profile['exit_code']==0 and all(v['live']==0 and
                v['allocations']==v['frees'] for v in profile['memory']) and all(v['calls']==v['completed'] and
                v['aborted']==0 for v in profile['functions']), 'model native managed cleanup differs')
        built=cli('build','--profile','release',cwd=directory)
        copied=root/'model-standalone';shutil.copy2(built['executable'],copied)
        (directory/'main.nex').unlink()
        # Installed SDKs can be mounted read-only. Use an explicitly selected
        # private resource projection to prove replay needs neither std source.
        replay_resources=root/'model-replay-resources'
        shutil.copytree(resources,replay_resources)
        removed_libraries=('model.nex','compute.nex')
        original_library_hashes={name:hashlib.sha256((resources/'lib'/name).read_bytes()).hexdigest()
                                 for name in removed_libraries}
        for name in removed_libraries:
            (replay_resources/'lib'/name).unlink()
        require(all(not (replay_resources/'lib'/name).exists() for name in removed_libraries),
                'model replay resource projection still contains standard sources')
        before=environment.get('NEX_RESOURCE_DIR')
        negative_controls={}
        try:
            environment['NEX_RESOURCE_DIR']=str(replay_resources)
            selected=cli('doctor')
            require(Path(selected['runtime']).resolve()==(replay_resources/'runtime/runtime.cpp').resolve(),
                    'model replay did not select its source-free resource projection')
            control=root/'model-replay-negative-control';control.mkdir()
            (control/'nex.json').write_text(json.dumps({'schema':'nex.project/1',
                'language':report['doctor']['language'],'entry':'main.nex'}))
            for name in removed_libraries:
                (control/'main.nex').write_text('module replay_control;import "std/'+name+'" as missing;fn main()->unit{}\n')
                rejected=cli('check',cwd=control,expected_success=False)
                require(rejected.get('code')=='E_RESOURCE',
                        'model replay resource projection fell back to an installed standard source')
                negative_controls[name]=rejected['code']
            # Force actual recompilation from the graph instead of reusing the
            # executable built before the library sources became unavailable.
            shutil.rmtree(directory/'.nex/build')
            rebuilt=cli('build','--revision',built['revision'],'--profile','release',cwd=directory)
            require(rebuilt.get('cached') is False and rebuilt['revision']==built['revision'],
                    'model replay did not rebuild the archived revision without cache')
            require(cli('eval','--revision',built['revision'],cwd=directory)['stdout']==expected,
                    'model reference replay depends on physical standard library source')
            require(cli('run','--revision',built['revision'],'--profile','release',cwd=directory)['stdout']==expected,
                    'model replay depends on physical standard library source')
            environment['NEX_RESOURCE_DIR']=str(root/'unavailable-model-resources')
            require(run([copied],cwd=root)==expected,'model standalone output differs')
        finally:
            if before is None:environment.pop('NEX_RESOURCE_DIR',None)
            else:environment['NEX_RESOURCE_DIR']=before
        require(original_library_hashes=={name:hashlib.sha256((resources/'lib'/name).read_bytes()).hexdigest()
                                         for name in removed_libraries},'model replay changed installed standard sources')
        report['evidence']['model_contract']={'descriptor':True,'native_reference':True,
            'typescript_reference':True,'source_deleted_replay':True,'standalone':True,
            'managed_memory_balanced':True,'preparer_installed':True,'physical_standard_sources_absent_for_replay':True,
            'replay_resource_isolation':{'root':str(replay_resources),'removed_libraries':list(removed_libraries),
                'negative_controls':negative_controls,'selected_runtime':selected['runtime'],
                'rebuilt_without_cache':True,'reference_replay':True,'installed_libraries_unchanged':True,
                'installed_library_sha256':original_library_hashes},
            'preparer_source_checked':True,'preparer_source_language':source_check['source_language'],'preparer_source_check':source_check,
            'library_sha256':hashlib.sha256((resources/'lib/model.nex').read_bytes()).hexdigest(),
            'revision':built['revision'],'native_model_inference_proved':False}

    def discover():
        for path in args.forbid_source:
            require(not path.exists(), 'source mount must be absent: ' + str(path))
        report['absent_source_probes'] = list(map(str, args.forbid_source))
        doctor = cli('doctor')
        full_command = len(report['commands'])
        descriptor = cli('describe')
        if 'scoped_discovery' in descriptor:
            index_command = len(report['commands'])
            index = cli('describe', '--kind', 'index')
            field_command = len(report['commands'])
            selected = cli('describe', '--field', 'scoped_discovery')
            require(index['fields'] == sorted(descriptor), 'scoped discovery index differs from full capabilities')
            require(selected['value'] == descriptor['scoped_discovery'], 'scoped field changed its capability value')
            require(index['language'] == doctor['language'] and index['toolchain'] == doctor['version'],
                    'scoped discovery language/toolchain differs from installed SDK')
            require(all(selected[key] == index[key] for key in ('compiler_build', 'descriptor_hash')),
                    'scoped discovery identities changed between requests')
            sizes = {name: Path(report['commands'][number]['stdout']).stat().st_size for name, number in
                     [('full_bytes', full_command), ('index_bytes', index_command), ('field_bytes', field_command)]}
            require(sizes['index_bytes'] < sizes['full_bytes'] and sizes['field_bytes'] < sizes['full_bytes'],
                    'scoped discovery failed to reduce its response payload')
            report['evidence']['scoped_discovery'] = {'ok': True, **sizes,
                'descriptor_hash': index['descriptor_hash'], 'fields': len(index['fields']),
                'metric': 'response_bytes_only', 'model_token_savings_measured': False}
        require(Path(doctor['runtime']).resolve() == (resources / 'runtime/runtime.cpp').resolve(),
                'compiler selected resources outside this SDK')
        require('typed_nested_patterns' in descriptor['match_features'], 'SDK lacks checked nested patterns')
        require('snapshot_closures' in descriptor['function_value_features'], 'SDK lacks snapshot closures')
        require('snapshot_scoped_identity_reconciliation' in descriptor['graph_features'] and
                descriptor['graph_identity_policy'] == 'nex.graph-identity/1',
                'SDK lacks checked graph references')
        require('type' in descriptor.get('patch_entities', []), 'SDK lacks atomic source-type replacements')
        require('operation' in descriptor.get('patch_entities', []) and
                'exact_source_guard' in descriptor.get('patch_features', []),
                'SDK lacks exact source-operation replacements')
        require('optimistic_archived_restore' in descriptor.get('history_features', []) and
                descriptor.get('graph_database_schema') == 4,
                'SDK lacks checked change history and revision restore')
        require({'unicode_scalar_shape', 'bounded_text_range_captures', 'readonly_utf8_streaming_provider'} <=
                set(descriptor.get('string_debug_features', [])), 'SDK lacks bounded stopped-string ranges')
        require({'literal_source_search', 'paged_dependency_radius', 'independent_node_edge_pages'} <=
                set(descriptor.get('graph_query_features', [])), 'SDK lacks bounded archived graph queries')
        require({'captured_source_inputs', 'uncommitted_candidate_context', 'watch_frame_bound_context'} <=
                set(descriptor.get('frontend_diagnostic_features', [])), 'SDK lacks captured frontend error context')
        require({'declared_source_language_guard', 'root_version_preflight_before_store',
                 'reachable_library_language_guard', 'archived_manifest_independence'} <=
                set(descriptor.get('project_features', [])), 'SDK lacks explicit physical project version boundaries')
        require('consistent_sqlite_backup' in descriptor.get('snapshot_features', []) and
                descriptor.get('snapshot_external_artifacts_included') is False,
                'SDK lacks identity-preserving graph snapshot/recovery')
        require('manifest_checked_trap_mapping' in descriptor.get('diagnostic_features', []),
                'SDK lacks checked native runtime diagnostics')
        require({'native_checked_i64_ssa', 'cold_integer_failure_calls', 'cold_native_assertions'} <=
                set(descriptor.get('build_features', [])), 'SDK lacks checked native scalar fast paths')
        require('wire' in descriptor['generic_constraints'], 'SDK lacks checked wire constraints')
        require('bytes' in descriptor['types'] and
                'immutable_contiguous_octets' in descriptor['binary_features'],
                'SDK lacks checked binary values')
        require('fs' in descriptor['effects'] and
                'no_implicit_http_capability' in descriptor['file_features'] and
                descriptor['file_environment']['http_inherits_environment'] is False,
                'SDK lacks explicit filesystem capability policy')
        pack = json.loads((resources / 'llm/language-pack.json').read_text())
        require({'frame_module_identity_guard', 'core_recorded_mapping_image_guard'} <= set(descriptor['debug_features']) and
                descriptor['native_debug_image_binding'] == pack['native_debug_image_binding'],
                'SDK lacks frame-to-loaded-image identity binding')
        require(descriptor['native_core'] == pack['native_core'] and descriptor['native_core']['readonly'], 'SDK lacks checked read-only core reports')
        require(pack['language_version'] == doctor['language'] == descriptor['version'], 'language pack mismatch')
        require(descriptor['browser_workers']==pack['browser_workers'] and
                descriptor['structured_tasks_runtime']==pack['structured_tasks_runtime'] and
                descriptor['structured_tasks_runtime']['source_support'] is True and
                descriptor['structured_tasks_runtime']['ordinary_applications_enabled'] is True and
                descriptor['structured_tasks_runtime']['private_lifetime_analysis']['mandatory_runtime_guards'] is True and
                descriptor['structured_tasks_runtime']['private_lifetime_analysis']['fully_static'] is False,
                'worker/task capability pack mismatch')
        state['descriptor'] = descriptor
        inventory = {}
        for name in [*pack['documents'].values(), *pack['examples'].values()]:
            path = (resources / name).resolve()
            require(resources.resolve() in path.parents and path.is_file(), 'missing/escaped language resource: ' + name)
            path.read_text()  # A pack offered to another model must contain actual UTF-8 text.
            inventory[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        for kind in ('tasks-runtime', 'browser-worker', 'prompt', 'language', 'grammar', 'protocol', 'web', 'server', 'api',
                     'debug', 'build', 'profile', 'verify', 'task', 'expression', 'operation', 'graph', 'history', 'snapshot', 'compatibility', 'frontend', 'query', 'string-debug', 'linux', 'match', 'function', 'files', 'bytes', 'resources', 'ffi', 'editor', 'lsp', 'core', 'wasm', 'project', 'server-workload', 'task-workload'):
            require(cli('guide', '--kind', kind)['text'], 'empty guide: ' + kind)
        report.update(doctor=doctor, compiler_sha256=hashlib.sha256(compiler.read_bytes()).hexdigest(),
                      version=doctor['version'], language=doctor['language'], host=doctor['host'],
                      resource_hashes=inventory)

    def editor_tools():
        node = os.environ.get('NEX_NODE') or shutil.which('node')
        require(node, 'editor acceptance requires the SDK Node development prerequisite')
        directory = resources / 'editor/vscode'
        names = ['package.json', 'package-lock.json', 'extension.js', 'session.js', 'project-command.js',
                 'language-configuration.json', 'README.md', 'test.js', 'language.js', 'lsp-client.js', 'language.test.js', 'lsp-acceptance.js']
        hashes = {name: hashlib.sha256((directory / name).read_bytes()).hexdigest() for name in names}
        package = json.loads((directory / 'package.json').read_text())
        require(package['name'] == 'nex-language-tools' and not package.get('dependencies'),
                'installed editor extension runtime dependencies differ')
        require(package['capabilities']['untrustedWorkspaces']['supported'] is False,
                'installed editor extension lost its workspace trust gate')
        # Node's test entry is a glob pattern. A literal backslash in a POSIX
        # SDK directory must stay in cwd rather than entering that pattern.
        run([node, '--test', 'test.js', 'language.test.js'], cwd=directory)
        evidence = {'extension_version': package['version'], 'installed_sources': hashes,
                    'focused_node_contracts': True, 'actual_ide_run': False,
                    'native_session_preparation': False}
        if args.live:
            project = root / 'editor-session'; project.mkdir()
            source = project / 'main with spaces.nex'
            source.write_text('module editor_sdk; fn main()->unit!{io} {print(42);}')
            (project / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1',
                'language': report['doctor']['language'], 'entry': source.name}))
            code = ('const {prepareSession}=require(process.argv[1]);'
                'prepareSession(JSON.parse(process.argv[2]),{compiler:process.argv[3]})'
                '.then(value=>process.stdout.write(JSON.stringify(value)))'
                '.catch(error=>{console.error(error.message);process.exitCode=1;});')
            prepared = json.loads(run([node, '-e', code, directory / 'session.js',
                json.dumps({'type': 'nex', 'request': 'launch', 'source': str(source), 'cwd': str(project)}),
                compiler], cwd=project))
            require(any(pair[1] == str(source) for pair in prepared['originalSourceMappings']),
                    'installed editor lost the exact original-file mapping')
            require(not prepared['frozenSourceFallbacks'] and Path(prepared['launch']['program']).is_file(),
                    'installed editor did not prepare its exact native build')
            evidence.update(native_session_preparation=True, revision=prepared['revision'],
                            build_key=prepared['buildKey'])
        report['evidence']['editor'] = evidence
        language_report = json.loads(run([sys.executable, resources / 'editor/lsp/acceptance.py',
            compiler, '--output', root / 'language-server']))
        require(language_report['ok'] and language_report['source_and_graph_unchanged'] and language_report.get('reference_checks') and language_report.get('type_reference_checks') and language_report.get('identifier_checks'),
                'installed compiler language-server acceptance failed')
        report['evidence']['language_server'] = language_report
        client_report = json.loads(run([node, directory / 'lsp-acceptance.js', compiler, root / 'editor-language-client']))
        require(client_report['ok'] and client_report['source_and_graph_unchanged'] and client_report.get('reference_checks') and client_report.get('type_reference_checks') and client_report.get('identifier_checks'), 'installed Node language client failed')
        report['evidence']['editor_language_client'] = client_report

    def new_project():
        directory = root / 'created'
        cli('init', directory)
        cli('check', cwd=directory)
        cli('test', cwd=directory)
        cli('run', cwd=directory)

    def baseline_failure():
        (project / 'model.nex').write_text(model)
        (project / 'main.nex').write_text(source)
        (project / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1',
            'language': report['doctor']['language'], 'entry': 'main.nex'}))
        state['before'] = cli('check', cwd=project)['revision']
        context = cli('context', '--symbol', 'choose', cwd=project)
        require(context['symbol'] == 'handoff::choose', 'bounded context selected another function')
        state['graph_before'] = cli('graph', cwd=project)
        operations = cli('operations', '--symbol', 'choose', cwd=project)
        require(any(n['kind'] == 'pattern.binding' for n in operations['nodes']), 'pattern bindings missing from graph')
        task = cli('task', project / 'main.nex', '--kind', 'init', cwd=project)
        task.update(id='sdk-handoff', title='Installed SDK development chain',
                    goal='Preserve the reviewed positive-result selection, error fallback and exact Unicode output.')
        native = next(c for c in task['checks'] if c['kind'] == 'test')
        task['checks'] += [dict(native, id='web-examples', target='web'),
            {'id': 'observable', 'kind': 'run', 'program': 'app', 'target': 'native',
             'entry': 'handoff::main', 'expect': {'stdout': expected, 'exit_code': 0}}]
        task['requirements'] = [{'id': 'selection',
            'text': 'Positive Some values are preserved; None/errors return -1. Main prints 42 and the exact NUL/Unicode string.',
            'bindings': [{'program': 'app', 'kind': 'function', 'symbol': 'handoff::choose'}],
            'targets': ['native', 'web'], 'checks': [c['id'] for c in task['checks']]}]
        state['task'] = project / 'task.json'
        state['task'].write_text(json.dumps(task, indent=2) + '\n')
        cli('task', state['task'], '--kind', 'check', cwd=project)
        failed = cli('task', state['task'], '--kind', 'run', cwd=project, expected_success=False, timeout=300)
        require(failed['status'] == 'not_satisfied' and not failed['ok'] and
                all(c['status'] == 'failed' for c in failed['checks'] if c['kind'] in ('test', 'run')),
                'deliberately wrong implementation did not fail its behavior checks')
        state['task_hash'] = failed['task_hash']
        report['evidence'].update(before_revision=state['before'], failed_receipt=failed['output'], task_hash=failed['task_hash'])

    def repair():
        patch = root / 'repair.json'
        patch.write_text(json.dumps({'expected_revision': state['before'],
            'replacements': [{'name': 'handoff::choose', 'source': choose}]}, indent=2) + '\n')
        state['after'] = cli('apply', '--patch', patch, cwd=project)['revision']
        require(state['after'] != state['before'], 'repair did not change semantic revision')
        conflict = cli('apply', '--patch', patch, cwd=project, expected_success=False)
        require(conflict['code'] == 'E_CONFLICT', 'stale patch was accepted')
        after_graph = cli('graph', cwd=project)
        require({n['name']: n['id'] for n in after_graph['nodes']} ==
                {n['name']: n['id'] for n in state['graph_before']['nodes']}, 'function identities changed')
        exported_graph = root / 'graph.json'
        exported_graph.write_text(json.dumps(after_graph, indent=2) + '\n')
        imported = root / 'imported'
        imported.mkdir()
        (imported / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1',
            'language': report['doctor']['language'], 'entry': 'main.nex'}))
        adopted = cli('import', exported_graph, cwd=imported)
        require(adopted['revision'] == state['after'], 'graph import changed checked revision')
        require((imported / '.nex/graph.db').is_file(), 'graph import used an enclosing project store')
        require(cli('run', '--revision', 'HEAD', cwd=imported)['stdout'] == expected, 'imported graph output differs')
        imported_ids = cli('identities', '--limit', '1000', cwd=imported)
        mappings = []
        offset = 0
        first_node = None
        while True:
            page = cli('identities', '--offset', str(offset), '--limit', '100', cwd=project)
            require(page['revision'] == state['after'], 'identity export selected another revision')
            if first_node is None:
                first_node = page['nodes'][0]
                source_namespace = page['namespace']
            packet = root / ('identities-'+str(offset)+'.json')
            packet.write_text(json.dumps(page))
            reconciled = cli('identities', '--kind', 'reconcile', '--manifest', packet,
                             '--expected-revision', state['after'], cwd=imported)
            mappings += reconciled['mappings']
            offset += len(page['nodes'])
            if not page['truncated']:
                break
        require(cli('identities', '--limit', '1000', cwd=imported) == imported_ids,
                'reconciliation rewrote destination identities')
        resolved = cli('identities', '--kind', 'resolve', '--origin', source_namespace,
                       '--from-revision', state['after'], '--node', first_node['id'], cwd=imported)
        require(resolved['target']['node']['context_hash'] == first_node['context_hash'] and
                cli('history', cwd=imported)['head'] == state['after'],
                'imported graph reference changed content or HEAD')
        report['evidence']['graph_reconciliation'] = {
            'source_namespace': source_namespace, 'target_namespace': imported_ids['namespace'],
            'mappings': len(mappings), 'resolved': resolved, 'destination_ids_unchanged': True}
        typed_project = root / 'atomic-type-patch'
        typed_project.mkdir()
        for name in ('main.nex', 'model.nex', 'nex.json', 'patch.json'):
            shutil.copy2(resources / 'examples/type-patches' / name, typed_project / name)
        typed_before = cli('check', cwd=typed_project)['revision']
        typed_ids = {n['symbol']: n['id'] for n in cli('declarations', '--entity', 'type', cwd=typed_project)['nodes']}
        typed_patch = json.loads((typed_project / 'patch.json').read_text())
        require(typed_patch['expected_revision'] == typed_before, 'type example source no longer matches its reviewed patch')
        partial_file = typed_project / 'partial.json'
        partial_file.write_text(json.dumps({'expected_revision': typed_before,
                                          'replacements': [typed_patch['replacements'][0]]}))
        cli('apply', '--patch', partial_file, cwd=typed_project, expected_success=False)
        require(cli('history', cwd=typed_project)['head'] == typed_before, 'invalid type-only edit changed HEAD')
        typed_after = cli('apply', '--patch', typed_project / 'patch.json', cwd=typed_project)['revision']
        require({n['symbol']: n['id'] for n in cli('declarations', '--entity', 'type', cwd=typed_project)['nodes']} == typed_ids,
                'atomic type replacement rewrote persistent type IDs')
        require(cli('context', '--entity', 'type', '--symbol', 'type_patch::model::Parcel', cwd=typed_project)['node']['editable'],
                'source type context is not editable')
        for name in ('main.nex', 'model.nex'):
            (typed_project / name).unlink()
        typed_expected = '43\nготово\n'
        require(cli('eval', '--revision', 'HEAD', cwd=typed_project)['stdout'] == typed_expected and
                cli('run', '--revision', 'HEAD', cwd=typed_project)['stdout'] == typed_expected,
                'source-deleted type replacement disagrees across reference/native')
        cli('test', '--revision', 'HEAD', cwd=typed_project)
        cli('test', '--revision', 'HEAD', '--target', 'web', cwd=typed_project)
        require(cli('eval', '--revision', typed_before, cwd=typed_project)['stdout'] == '42\n',
                'type replacement changed archived layout behavior')
        report['evidence']['atomic_type_patches'] = {
            'before_revision': typed_before, 'after_revision': typed_after,
            'persistent_type_ids': len(typed_ids), 'invalid_partial_edit_rejected': True,
            'source_deleted': True, 'native_reference_typescript': True}
        passed = cli('task', state['task'], '--kind', 'run', '--revision', state['after'],
                     '--task-hash', state['task_hash'], cwd=project, timeout=300)
        require(passed['status'] == 'passed' and passed['task_hash'] == state['task_hash'], 'reviewed task changed or failed')
        state['accepted'] = passed
        report['evidence'].update(after_revision=state['after'], passed_receipt=passed['output'], graph=str(exported_graph))

    def wasm_compute():
        workspace = root / 'wasm-project'
        workspace.mkdir()
        (workspace / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1',
            'language': report['doctor']['language'], 'entry': 'main.nex'}))
        source = workspace / 'main.nex'
        source.write_text((resources / 'examples/wasm/main.nex').read_text() + '''
pub fn bounded(n:i64)->i64{var i:i64=0;while i<n{i=i+1;}return i;}
server fn excluded()->str !{io}{print("SDK_WASM_SERVER_EXCLUDED_060");return "SDK_WASM_SERVER_EXCLUDED_060";}
''')
        cli('test', cwd=workspace)
        cli('test', '--target', 'web', cwd=workspace)
        arguments = ['build', '--target', 'wasm', '--entry', 'compute', '--profile', 'release']
        built = cli(*arguments, cwd=workspace)
        require(not built['cached'], 'cold Wasm build unexpectedly reused an artifact')
        require(cli(*arguments, cwd=workspace)['cached'], 'warm Wasm build did not reuse complete artifacts')
        module = Path(built['module'])
        original = module.read_bytes()
        module.write_bytes(original + b'changed')
        require(not cli(*arguments, cwd=workspace)['cached'] and module.read_bytes() == original,
                'changed Wasm module survived cache validation')
        bounded = cli('build', '--target', 'wasm', '--entry', 'bounded', '--profile', 'release', cwd=workspace)
        for label in ('module', 'wrapper', 'metadata', 'mlir', 'llvm'):
            require(b'SDK_WASM_SERVER_EXCLUDED_060' not in Path(built[label]).read_bytes(),
                    'server code entered a scalar Wasm artifact')
        source.unlink()
        exported = root / 'independent-wasm'
        materialized = cli(*arguments, '--revision', built['revision'], '-o', exported, cwd=workspace)
        require(Path(materialized['module']).read_bytes() == original, 'archived Wasm export differs')
        bounded_export = exported / 'bounded'
        bounded_export.mkdir()
        for name in ('module.wasm', 'module.mjs', 'module.json', 'THIRD_PARTY_NOTICES.txt'):
            shutil.copyfile(Path(bounded['directory']) / name, bounded_export / name)
        driver = exported / 'check.mjs'
        driver.write_text('''import fs from 'node:fs';
import {createNexWasm} from './module.mjs';
const raw=fs.readFileSync(new URL('./module.wasm',import.meta.url));
const module=await createNexWasm(raw);
if(module.call([9007199254740993n,1n])!==9007199254740993n)throw Error('integer precision differs');
let overflow;try{module.call([9223372036854775807n,2n])}catch(error){overflow=error;}
if(overflow?.code!=='E_OVERFLOW'||!overflow.site?.site)throw Error('checked overflow differs');
for(const args of [[1,2n],[9223372036854775808n,1n]]){
 let code;try{module.call(args)}catch(error){code=error.code;}if(code!=='E_WASM_INPUT')throw Error('input accepted');
}
if(module.call([6n,7n])!==42n)throw Error('failed post-trap recovery');
const mutated=raw.slice();mutated[mutated.length-1]^=1;
let rejected;try{await createNexWasm(mutated)}catch(error){rejected=error.code;}
if(rejected!=='E_WASM_MODULE')throw Error('changed module accepted');
const boundedFactory=(await import('./bounded/module.mjs')).createNexWasm;
const bounded=await boundedFactory(fs.readFileSync(new URL('./bounded/module.wasm',import.meta.url)));
let stopped;try{bounded.call([1000n],{budget:10})}catch(error){stopped=error.code;}
if(stopped!=='E_WASM_BUDGET'||bounded.call([3n])!==3n)throw Error('resource bound/recovery differs');
console.log(JSON.stringify({exact_bigint:true,checked_overflow:true,input_rejection:true,
 resource_stop:true,post_trap_recovery:true,module_integrity:true}));
''')
        previous = environment['NEX_RESOURCE_DIR']
        try:
            environment['NEX_RESOURCE_DIR'] = str(root / 'absent-wasm-resources')
            # Node treats literal backslashes in physical POSIX module paths as
            # separators. Execute byte-identical independent assets in an owned
            # ordinary /tmp path, including when the SDK work root has one.
            with tempfile.TemporaryDirectory(prefix='nex-sdk-wasm-', dir='/tmp') as temporary:
                independent = Path(temporary) / 'runtime'
                shutil.copytree(exported, independent)
                for path in exported.rglob('*'):
                    if path.is_file():
                        require(path.read_bytes() == (independent / path.relative_to(exported)).read_bytes(),
                                'independent Wasm runtime copy differs')
                observed = json.loads(run([os.environ.get('NEX_NODE') or shutil.which('node'), independent / 'check.mjs'], cwd=independent))
                require(not (independent / '.nex').exists(), 'independent Wasm runtime created a graph')
        finally:
            environment['NEX_RESOURCE_DIR'] = previous
        require(not source.exists() and not (exported / '.nex').exists(), 'standalone Wasm execution created source/graph state')
        observed.update(source_deleted=True, independent_runtime=True, cache_integrity=True, server_exclusion=True,
                        build=built, exported=materialized, bounded=bounded,
                        module_sha256=hashlib.sha256(original).hexdigest())
        report['evidence']['wasm_compute'] = observed

    def backend_agreement():
        for profile in ('debug', 'release'):
            cli('test', '--revision', state['after'], '--profile', profile, cwd=project)
            observed = cli('run', '--revision', state['after'], '--profile', profile, cwd=project)
            require(observed['stdout'] == expected and observed['exit_code'] == 0, 'native profile output differs')
        require(cli('eval', '--revision', state['after'], cwd=project)['stdout'] == expected, 'reference output differs')
        cli('test', '--revision', state['after'], '--target', 'web', cwd=project)
        built = cli('build', '--revision', state['after'], '--profile', 'release', cwd=project)
        standalone = root / 'standalone'
        shutil.copyfile(built['executable'], standalone)
        standalone.chmod(0o755)
        unavailable = environment['NEX_RESOURCE_DIR']
        try:
            environment['NEX_RESOURCE_DIR'] = str(root / 'absent-resources')
            require(run([standalone]) == expected, 'independent executable output differs')
        finally:
            environment['NEX_RESOURCE_DIR'] = unavailable
        report['evidence']['standalone'] = str(standalone)
        numeric = root / 'numbers'
        numeric.mkdir()
        shutil.copyfile(resources / 'examples/numbers.nex', numeric / 'main.nex')
        (numeric / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1',
            'language': report['doctor']['language'], 'entry': 'main.nex'}))
        number_revision = cli('check', cwd=numeric)['revision']
        number_output = cli('eval', cwd=numeric)['stdout']
        require(number_output.startswith('2.5e0\n') and '"E_RANGE"' in number_output,
                'numeric SDK example selected another behavior')
        for profile in ('debug', 'release'):
            cli('test', '--profile', profile, cwd=numeric)
            require(cli('run', '--profile', profile, cwd=numeric)['stdout'] == number_output,
                    'numeric native/reference output differs')
        cli('test', '--target', 'web', cwd=numeric)
        number_build = cli('build', '--profile', 'release', cwd=numeric)
        number_standalone = root / 'numeric-standalone'
        shutil.copyfile(number_build['executable'], number_standalone)
        number_standalone.chmod(0o755)
        (numeric / 'main.nex').unlink()
        require(cli('run', '--revision', number_revision, cwd=numeric)['stdout'] == number_output,
                'numeric archived revision did not survive source deletion')
        try:
            environment['NEX_RESOURCE_DIR'] = str(root / 'absent-resources')
            require(run([number_standalone]) == number_output, 'independent numeric executable differs')
        finally:
            environment['NEX_RESOURCE_DIR'] = unavailable
        report['evidence']['numeric_language'] = {'revision': number_revision,
            'native_profiles': ['debug', 'release'], 'typescript': True,
            'source_deleted_replay': True, 'standalone_without_resources': str(number_standalone)}
        if state['descriptor'].get('result_propagation'):
            directory = root / 'result-propagation'; directory.mkdir()
            shutil.copyfile(resources / 'examples/propagation.nex', directory / 'main.nex')
            (directory / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1',
                'language': report['doctor']['language'], 'entry': 'main.nex'}))
            saved_revision = cli('check', cwd=directory)['revision']
            output = cli('eval', cwd=directory)['stdout']
            require(output == '{"ok":"value=42"}\n{"error":{"code":"PARTIAL","message":"same error 🦊"}}\n{"ok":"outer:INNER"}\n',
                    'result propagation SDK sample differs from its defined output')
            for profile in ('debug', 'release'):
                cli('test', '--profile', profile, cwd=directory)
                require(cli('run', '--profile', profile, cwd=directory)['stdout'] == output,
                        'result propagation native/reference disagreement')
            cli('test', '--target', 'web', cwd=directory)
            measured = cli('profile', '--scenario', 'result propagation SDK', cwd=directory)
            profile = json.loads(Path(measured['output']).read_text())
            require(measured['stdout'] == output and all(pool['live'] == 0 and
                    pool['allocations'] == pool['frees'] for pool in profile['memory']) and
                    all(f['calls'] == f['completed'] and f['aborted'] == 0 for f in profile['functions']),
                    'result propagation profile has incomplete calls or managed ownership')
            built = cli('build', '--profile', 'release', cwd=directory)
            standalone = root / 'result-propagation-standalone'
            shutil.copyfile(built['executable'], standalone); standalone.chmod(0o755)
            (directory / 'main.nex').unlink()
            require(cli('run', '--revision', saved_revision, cwd=directory)['stdout'] == output,
                    'result propagation archived replay changed after source deletion')
            try:
                environment['NEX_RESOURCE_DIR'] = str(root / 'absent-resources')
                require(run([standalone]) == output, 'standalone result propagation needs compiler resources')
            finally:
                environment['NEX_RESOURCE_DIR'] = unavailable
            report['evidence']['result_propagation'] = {'native_reference': True, 'typescript': True,
                'profile_cleanup': True, 'source_deleted': True, 'standalone_without_resources': True,
                'revision': saved_revision}
        if state['descriptor'].get('source_concurrency', {}).get('source_operations'):
            directory = root / 'cpu-mapping'; directory.mkdir()
            shutil.copyfile(resources / 'examples/parallel.nex', directory / 'main.nex')
            (directory / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1',
                'language': report['doctor']['language'], 'entry': 'main.nex'}))
            saved_revision = cli('check', cwd=directory)['revision']
            output = cli('eval', cwd=directory)['stdout']
            require(output == '[{"ok":"value=40"},{"error":{"code":"NEGATIVE","message":"negative input"}},{"ok":"value=42"}]\n2029000\n',
                    'ordered CPU SDK sample differs from its defined output')
            for profile in ('debug', 'release'):
                cli('test', '--profile', profile, cwd=directory)
                require(cli('run', '--profile', profile, cwd=directory)['stdout'] == output,
                        'ordered CPU native/reference disagreement')
            cli('test', '--target', 'web', cwd=directory)
            measured = cli('profile', '--scenario', 'ordered CPU SDK', cwd=directory)
            profile_path = Path(measured['output']); profile = json.loads(profile_path.read_text())
            events = [e for e in profile['traceEvents'] if e.get('name') == 'parallel_example::compute']
            thread_ids = sorted({e['tid'] for e in events})
            overlapping = any(a['tid'] != z['tid'] and max(a['ts'], z['ts']) <
                    min(a['ts'] + a['dur'], z['ts'] + z['dur']) for a in events for z in events)
            require(len(events) == 16 and len(thread_ids) >= 2 and overlapping,
                    'native CPU callbacks did not overlap on distinct actual profile threads')
            require(measured['stdout'] == output and all(p['live'] == 0 and p['allocations'] == p['frees'] for p in profile['memory']) and
                    all(f['calls'] == f['completed'] and f['aborted'] == 0 for f in profile['functions']),
                    'CPU group damaged caller profiles or leaked managed values')
            built = cli('build', '--profile', 'release', cwd=directory)
            standalone = root / 'cpu-mapping-standalone'; shutil.copyfile(built['executable'], standalone); standalone.chmod(0o755)
            (directory / 'main.nex').unlink()
            require(cli('run', '--revision', saved_revision, cwd=directory)['stdout'] == output,
                    'CPU archived replay changed after deleting source')
            try:
                environment['NEX_RESOURCE_DIR'] = str(root / 'absent-resources')
                require(run([standalone]) == output, 'standalone CPU application needs compiler resources')
            finally:
                environment['NEX_RESOURCE_DIR'] = unavailable
            report['evidence']['cpu_mapping'] = {'native_reference': True, 'typescript': True,
                'profile_cleanup': True, 'source_deleted': True, 'standalone_without_resources': True,
                'overlapping_callbacks': True, 'thread_ids': thread_ids, 'profile_json': str(profile_path),
                'profile_sha256': hashlib.sha256(profile_path.read_bytes()).hexdigest(), 'revision': saved_revision}
        operation_project = root / 'operation-patches'
        operation_project.mkdir()
        for name in ('main.nex', 'nex.json'):
            shutil.copy2(resources / 'examples/operation-patches' / name, operation_project / name)
        operation_before = cli('check', cwd=operation_project)['revision']
        page = cli('operations', '--symbol', 'operation_patch::adjust', cwd=operation_project)
        selected, = [n for n in page['nodes'] if n['kind'] == 'expression.integer'
                     and n['definition']['number'] == '1']
        context = cli('context', '--operation', selected['id'], cwd=operation_project)
        require(context['nodes'][0]['source_range']['editable'] and
                context['nodes'][0]['source_preview'] == '1', 'SDK operation context differs')
        operation_file = root / 'operation-edit.json'
        operation_file.write_text(json.dumps({'expected_revision': operation_before,
            'expected_source_hash': page['source_hash'],
            'replacements': [{'operation_id': selected['id'], 'source': '2 // isolated comment'}]}))
        (operation_project / 'main.nex').unlink()
        operation_after = cli('apply', '--patch', operation_file, cwd=operation_project)['revision']
        require(cli('context', '--operation', selected['id'], cwd=operation_project)['nodes'][0]['site'] != selected['site'],
                'SDK source-operation edit lost its local ID or retained its old site')
        require(cli('run', '--revision', operation_before, cwd=operation_project)['stdout'] == '41\n' and
                cli('eval', '--revision', operation_after, cwd=operation_project)['stdout'] == '42\n' and
                cli('run', '--revision', operation_after, cwd=operation_project)['stdout'] == '42\n',
                'SDK source-deleted operation patch disagrees across native/reference/history')
        cli('test', '--revision', operation_after, cwd=operation_project)
        cli('test', '--revision', operation_after, '--target', 'web', cwd=operation_project)
        require(cli('apply', '--patch', operation_file, cwd=operation_project,
                    expected_success=False)['code'] == 'E_CONFLICT', 'SDK accepted stale operation patch')
        restored = cli('restore', '--revision', operation_before, '--expected-revision', operation_after,
                       '--note', 'Return to retained original', '--actor', 'SDK scenario', cwd=operation_project)
        require(restored['changed'] and not restored['materialized'] and
                cli('run', '--revision', 'HEAD', cwd=operation_project)['stdout'] == '41\n',
                'SDK source-deleted restore did not recover the original')
        cli('restore', '--revision', operation_after, '--expected-revision', operation_before,
            '--note', 'Return to revised implementation', cwd=operation_project)
        require(cli('run', '--revision', 'HEAD', cwd=operation_project)['stdout'] == '42\n',
                'SDK restore lost the revised source')
        transitions = cli('changes', cwd=operation_project)
        require(transitions['total'] == 4 and transitions['changes'][0]['action'] == 'restore' and
                transitions['changes'][0]['previous_revision'] == operation_before and
                transitions['changes'][1]['previous_revision'] == operation_after and
                transitions['author_trust'] == 'declared', 'SDK change provenance differs')
        report['evidence']['change_history'] = {'transitions': 4,
            'namespace': transitions['namespace'], 'tip_hash': transitions['changes'][0]['hash'],
            'before': operation_before, 'after': operation_after, 'source_deleted_restore': True,
            'physical_sources_absent': not (operation_project / 'main.nex').exists(),
            'both_archives_preserved': True, 'declared_author_labels': True}
        report['evidence']['source_operation_patches'] = {'before': operation_before,
            'after': operation_after, 'local_operation_id': selected['id'],
            'source_deleted': True, 'native_reference_typescript': True,
            'stale_rejected': True, 'same_local_id_new_site': True}
        cached_project = root / 'function-cache'
        cached_project.mkdir()
        cached_source = cached_project / 'main.nex'
        cached_source.write_text('module sdk_cache;\n'
            'fn changed(value:i64)->i64{return value+1;}\n'
            'fn sibling(value:i64)->i64{return value*2;}\n'
            'fn main()->unit!{io}{print(changed(2));print(sibling(3));}\n')
        (cached_project / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1',
            'language': report['doctor']['language'], 'entry': 'main.nex'}))
        before = cli('build', cwd=cached_project)
        require(before['compiled_functions'] == 3, 'initial function cache did not compile all reachable bodies')
        require(run([before['executable']]) == '3\n6\n', 'initial function cache output differs')
        warm = cli('build', cwd=cached_project)
        require(warm['cached'] and warm['compiled_functions'] == 0 and warm['reused_functions'] == 3,
                'warm function cache did not reuse all bodies')
        cached_source.write_text(cached_source.read_text().replace('value+1;', 'value+100;'))
        after = cli('build', cwd=cached_project)
        require(after['compiled_functions'] == 1 and after['reused_functions'] == 2,
                'a same-file body edit recompiled unrelated functions')
        require(run([after['executable']]) == '102\n6\n' and
                cli('eval', cwd=cached_project)['stdout'] == '102\n6\n', 'cached native/reference output differs')
        cached_source.unlink()
        require(cli('run', '--revision', before['revision'], cwd=cached_project)['stdout'] == '3\n6\n' and
                cli('run', '--revision', after['revision'], cwd=cached_project)['stdout'] == '102\n6\n',
                'function cache did not preserve both source-deleted revisions')
        report['evidence']['function_cache'] = {'before_revision': before['revision'],
            'after_revision': after['revision'], 'compiled_after_edit': after['compiled_functions'],
            'reused_after_edit': after['reused_functions'], 'source_deleted_replay': True}

        integer_project = root / 'native-integers'
        integer_project.mkdir()
        (integer_project / 'nex.json').write_text(json.dumps({'language': report['doctor']['language'], 'entry': 'main.nex'}))
        integer_source = integer_project / 'main.nex'
        shutil.copy2(resources / 'examples/native-arithmetic.nex', integer_source)
        integer_revision = cli('check', cwd=integer_project)['revision']
        cli('test', cwd=integer_project)
        cli('test', '--target', 'web', cwd=integer_project)
        cli('test', '--profile', 'release', cwd=integer_project)
        integer_source.unlink()
        cli('test', '--revision', integer_revision, cwd=integer_project)
        cli('test', '--revision', integer_revision, '--target', 'web', cwd=integer_project)
        report['evidence']['native_integer_lowering'] = {'revision': integer_revision,
            'source_example': 'examples/native-arithmetic.nex', 'sample_loop_iterations': 1000,
            'checked_boundaries': True, 'native_and_reference': True, 'typescript': True,
            'native_profiles': ['debug', 'release'], 'source_deleted': True}

        diagnostic_project = root / 'native-diagnostics'
        diagnostic_project.mkdir()
        (diagnostic_project / 'nex.json').write_text(json.dumps({'language': report['doctor']['language'], 'entry': 'main.nex'}))
        diagnostic_source = diagnostic_project / 'main.nex'
        diagnostic_source.write_text('module sdk_trap;fn divide(n:i64)->i64{return 42/n;}fn main()->unit!{io}{print("before");print(divide(0));}')
        checked = cli('check', cwd=diagnostic_project)
        expected_error = cli('eval', cwd=diagnostic_project, expected_success=False)
        for profile in ('debug', 'release'):
            failed = cli('run', '--profile', profile, cwd=diagnostic_project, expected_success=False)
            records = failed['native_diagnostics']['diagnostics']
            require(failed['exit_code'] == 70 and failed['stdout'] == 'before\n' and len(records) == 1,
                    'native trap process observation differs')
            record = records[0]
            require(record['status'] == 'mapped' and record['report']['code'] == 'E_DIV_ZERO' and
                    record['operation_id'] == expected_error['operation_id'] and
                    record['operation_site'] == expected_error['operation_site'],
                    'native/interpreter operation attribution differs')
        built = cli('build', '--profile', 'release', cwd=diagnostic_project)
        graph_file = root / 'native-diagnostic-graph.json'
        graph_file.write_text(json.dumps(cli('graph', cwd=diagnostic_project)))
        standalone = root / 'native-diagnostic-app'
        shutil.copy2(built['executable'], standalone)
        diagnostic_source.unlink()
        require(run([standalone], expected_success=False) == 'before\n' and report['commands'][-1]['exit_code'] == 70,
                'source-deleted standalone did not retain its native trap')
        diagnostic_log = Path(report['commands'][-1]['stderr'])
        restored = root / 'native-diagnostic-restored'
        restored.mkdir()
        (restored / 'nex.json').write_text(json.dumps({'language': report['doctor']['language'], 'entry': 'main.nex'}))
        cli('import', graph_file, cwd=restored)
        mapped = cli('diagnose', '--revision', checked['revision'], '--manifest', built['debug_manifest'],
                     '--log', diagnostic_log, cwd=restored)['diagnostics'][0]
        require(mapped['status'] == 'mapped' and mapped['operation_site'] == record['operation_site'] and
                mapped['operation_id'] != record['operation_id'] and not (restored / 'main.nex').exists(),
                'source-deleted imported graph did not resolve its own local operation ID')
        report['evidence']['native_diagnostics'] = {'revision': checked['revision'],
            'site': mapped['operation_site'], 'native_profiles': ['debug', 'release'],
            'native_interpreter_agreement': True, 'source_deleted': True,
            'standalone_without_sdk_lookup': str(standalone), 'new_store_local_ids': True,
            'manifest': built['debug_manifest']}

        # Run a real task application with the installed headers/runtime. This
        # phase executes with the original compiler source path unavailable.
        task_project = root / 'structured-task-limits'
        task_project.mkdir()
        (task_project / 'nex.json').write_text(json.dumps({'schema':'nex.project/1',
            'language':report['doctor']['language'],'entry':'main.nex'}))
        (task_project / 'main.nex').write_text('module installed_task_limits;\nfn solve()->i64 !{task}{return with_tasks(2,fn(scope:task_scope)->i64 !{task}{\n let child:task<i64>=task_spawn(scope,fn()->i64 !{task}{task_yield();return 42;});\n return task_wait(child);\n});}\nfn main()->i64 !{io,task}{print(solve());return 0;}\ntest fn checks()->unit !{task}{assert(solve()==42);}\n')
        caps={'steps':2000000,'timeout_ms':10000,'workers':2}
        controls=['--task-steps','2000000','--task-timeout-ms','10000','--task-workers','2']
        task_revision=cli('check',cwd=task_project)['revision']
        evaluated=cli('eval',*controls,cwd=task_project)
        require(evaluated['stdout']=='42\n' and evaluated['task_execution']['effective']==caps and
                evaluated['task_execution']['executor_workers']==1,'installed reference task limits differ')
        for profile in ('debug','release'):
            observed=cli('run','--profile',profile,*controls,cwd=task_project)
            require(observed['stdout']=='42\n' and observed['task_execution']['effective']==caps and
                    observed['task_execution']['executor_workers']==2,'installed native task limits differ')
        for target in ('native','web'):
            observed=cli('test','--target',target,*controls,cwd=task_project)
            require(all(t['task_execution']['effective']==caps and
                        t['task_execution']['executor_workers']==(2 if target=='native' else 1)
                        for t in observed['tests']),'installed task test limits differ')
        built=cli('build','--profile','release',*controls,cwd=task_project)
        require(built['task_limits']==caps,'installed build lost task limits')
        standalone=root/'task-limits-standalone'
        shutil.copyfile(built['executable'],standalone);standalone.chmod(0o755)
        (task_project/'main.nex').unlink()
        try:
            environment['NEX_RESOURCE_DIR']=str(root/'absent-resources')
            require(run([standalone,'--nex-task-steps','100000','--nex-task-timeout-ms','1000',
                         '--nex-task-workers','1'])=='42\n','copied task application lost embedded/lowered limits')
            run([standalone,'--nex-task-workers','3'],expected_success=False)
            require('E_OPTION' in Path(report['commands'][-1]['stderr']).read_text(),
                    'copied task application raised embedded worker ceiling')
            run([standalone,'--nex-task-steps','1'],expected_success=False)
            require('E_LIMIT' in Path(report['commands'][-1]['stderr']).read_text(),
                    'copied task application ignored its lowered budget')
        finally:
            environment['NEX_RESOURCE_DIR']=unavailable
        require(cli('run','--revision',task_revision,*controls,cwd=task_project)['stdout']=='42\n',
                'installed task archive lost runtime controls after source deletion')
        report['evidence']['structured_task_limits']={'revision':task_revision,'limits':caps,
            'native_profiles':['debug','release'],'reference_workers':1,'typescript_workers':1,
            'native_pool_workers':2,'source_deleted':True,'standalone_without_resources':str(standalone),
            'launcher_lowered_limits':True,'launcher_raise_rejected':True,'lowered_budget_enforced':True,
            'identical_step_thresholds':False}

    def structured_task_file_writes():
        destination=root/'public-task-write-delivery'
        run([sys.executable,'-B',resources/'tests/task_write_delivery.py','--compiler',compiler,'--resources',resources,'--output',destination],timeout=2400)
        proof=json.loads((destination/'report.json').read_text())
        require(proof.get('ok') is True and proof.get('compiler_sha256')==report['compiler_sha256'],
                'installed public file-write workflow differs from actual compiler')
        report['evidence']['structured_task_file_writes']=proof
        history_destination=root/'public-task-write-histories'
        run([sys.executable,'-B',resources/'tests/task_write_histories.py','--compiler',compiler,'--resources',resources,'--output',history_destination],timeout=2400)
        history=json.loads((history_destination/'report.json').read_text())
        require(history.get('ok') is True and history.get('compiler_sha256')==report['compiler_sha256'],
                'installed extended history workflow differs from actual compiler')
        proof['extended_histories']=history
        from sdk_task_streams import check_installed_task_streams
        feature=cli('describe','--field','task_file_streams_host')['value']
        pack=json.loads((resources/'llm/language-pack.json').read_text())
        require(feature==pack['task_file_streams_host'] and feature['source_support'] is (report['language']=='0.24') and
                feature['typed_one_shot_open'] is True and feature['worker_ambient_authority'] is False,
                'installed private stream descriptor differs')
        proof['private_stream_host']=check_installed_task_streams(run,root,resources,report['doctor']['native_compiler'])

    def structured_task_http():
        feature=state['descriptor']['structured_tasks_runtime'].get('http_server',{})
        require(feature.get('public_enabled') is True and feature.get('minimum_language')=='0.24' and
                feature.get('profiles')==['debug','release'] and feature.get('async_network') is False and
                feature.get('async_database') is False,'installed compiler task HTTP capability differs')
        helper=resources/'tests/task_http_server.py'
        require(helper.is_file(),'installed public task HTTP acceptance helper is missing')
        digest=hashlib.sha256(helper.read_bytes()).hexdigest()
        require(report['resource_hashes'].get('tests/task_http_server.py')==digest,
                'installed public task HTTP helper is absent from its indexed resources')
        destination=root/'public-task-http'
        run([sys.executable,'-B',helper,compiler,'--output',destination],timeout=1200)
        delivery=json.loads((destination/'report.json').read_text())
        report['evidence']['structured_task_http']={'installed_helper':True,'helper_sha256':digest,
            'delivery':delivery,'delivery_report_sha256':hashlib.sha256((destination/'report.json').read_bytes()).hexdigest()}
        validate_task_http_evidence(report)

    def structured_task_file_streams():
        feature=state['descriptor']['task_file_streams']
        require(feature['language']=='0.24' and feature['public_enabled'] and feature['source_support'] and
                feature['execution_ABI']==5 and not feature['source_values_on_IO_workers'],
                'installed source stream descriptor differs')
        destination=root/'public-task-stream-delivery'
        run([sys.executable,'-B',resources/'tests/task_stream_delivery.py',compiler,'--output',destination],timeout=2400)
        delivery=json.loads((destination/'report.json').read_text())
        require(delivery.get('ok') and delivery.get('compiler_sha256')==report['compiler_sha256'] and
                delivery.get('native_reference_pairs')==5 and delivery.get('rejected_programs')==3 and
                delivery.get('old_metadata_rejected_before_store') is True,
                'installed public stream CLI delivery failed')
        history_destination=root/'public-task-stream-histories'
        previous=environment.get('NEX_MIXED_COMPILER')
        environment['NEX_MIXED_COMPILER']=report['doctor']['native_compiler']
        try:
            run([sys.executable,'-B',resources/'tests/task_stream_cli_histories.py',compiler,
                 '--resources',resources,'--output',history_destination],timeout=3600)
        finally:
            if previous is None:environment.pop('NEX_MIXED_COMPILER',None)
            else:environment['NEX_MIXED_COMPILER']=previous
        history=json.loads((history_destination/'report.json').read_text())
        require(history.get('ok') and history.get('compiler_sha256')==report['compiler_sha256'] and
                history.get('genuine023_histories')==9 and history.get('genuine023_revisions')==27 and
                history.get('native_reference_pairs')==27 and history.get('rejected_migrations')==9 and
                all(row.get('all16_tables_schema_rows_ids_preserved') and row.get('physical_sources_manifest_lock_preserved') and
                    row.get('idempotent') and row.get('materialized_current_project_checked') and row.get('source_absent_native')
                    for row in history['cases']), 'installed public stream migration workflow failed')
        report['evidence']['structured_task_file_streams']={'delivery':delivery,'histories':history,
            'original_SDK_execution_claimed':False,'delivery_report_sha256':hashlib.sha256((destination/'report.json').read_bytes()).hexdigest(),
            'history_report_sha256':hashlib.sha256((history_destination/'report.json').read_bytes()).hexdigest()}

    def structured_task_file_reads():
        from sdk_task_file_migration import check_installed_task_migration
        descriptor = state['descriptor']['task_file_reads']
        pack = json.loads((resources/'llm/language-pack.json').read_text())
        require(descriptor == pack['task_file_reads'] and descriptor['source_support'] and
                descriptor['language'] == report['language'] == '0.24' and not descriptor['typescript'],
                'installed task file-read descriptor/pack differs')
        report['evidence']['task_file_migration'] = check_installed_task_migration(cli, root, resources)
        directory = root/'structured-task-file-project'
        (directory/'app').mkdir(parents=True)
        (directory/'core').mkdir()
        data = root/'structured-task-file-inputs'
        data.mkdir()
        (data/'text').write_bytes('A🧠\0B'.encode())
        (data/'bytes').write_bytes(b'A\0\xff')
        (directory/'nex.json').write_text(json.dumps({'schema':'nex.project/1',
            'language':report['language'],'entry':'app/main.nex'}))
        (directory/'nex.build.json').write_text(json.dumps({'schema':'nex.project-build/1',
            'default_configuration':'release','configurations':{'release':{'profile':'release','target':'native',
                'task_limits':{'steps':2000000,'timeout_ms':10000,'workers':2}}},
            'components':{'core':{'kind':'source','root':'core','entry':'core/read.nex'},
                'app':{'kind':'executable','root':'app','entry':'app/main.nex','dependencies':{'core':'source'}}}}))
        (directory/'core/read.nex').write_text('''module installed_task_files::core;
pub server fn count(path:str)->result<i64> !{task,fs}{
 let text:str=file_read_text(path)?;task_yield();return ok(len(text));
}
''')
        (directory/'app/main.nex').write_text('''module installed_task_files::app;
import "../core/read.nex" as core;
server fn solve()->result<i64> !{task,fs}{
 return with_tasks(2,server fn(s:task_scope)->result<i64> !{task,fs}{
  let child:task<result<i64>>=task_spawn(s,server fn()->result<i64> !{task,fs}{return core::count("text");});
  let binary:bytes=file_read_bytes("bytes")?;
  let count:i64=task_wait(child)?;return ok(count+len(binary));
 });
}
server fn main()->unit !{task,fs,io}{print(unwrap(solve()));}
server test fn reads()->unit !{task,fs}{assert(unwrap(solve())==7);assert(error_code(core::count("missing"))=="NOT_FOUND");}
''')
        previous = {key:environment.get(key) for key in ('NEX_FILES_ROOT','NEX_FILES_WRITE','NEX_RESOURCE_DIR')}
        environment['NEX_FILES_ROOT'] = str(data)
        environment.pop('NEX_FILES_WRITE',None)
        try:
            revision = cli('check',cwd=directory)['revision']
            require(cli('eval',cwd=directory)['stdout']=='7\n','installed reference task read differs')
            require(cli('run',cwd=directory)['stdout']=='7\n','installed native task read differs')
            tests = cli('test',cwd=directory)
            require(tests['tests'] and all(test['native'] and test['ok'] for test in tests['tests']),
                    'installed read tests did not compare native/reference')
            built = cli('build','--profile','release',cwd=directory)
            standalone = root/'task-file-read-standalone'
            shutil.copy2(built['executable'],standalone)
            source = directory/'app/main.nex'; hidden = directory/'app/main.hidden'
            source.rename(hidden)
            try:
                environment['NEX_RESOURCE_DIR'] = str(root/'absent-task-file-resources')
                require(run([standalone],cwd=root)=='7\n','copied task read executable needs compiler resources')
                environment.pop('NEX_FILES_ROOT')
                run([standalone],cwd=root,expected_success=False)
                require('E_RESULT' in Path(report['commands'][-1]['stderr']).read_text(),
                        'compiled task executable retained an implicit root grant')
            finally:
                hidden.rename(source)
                environment['NEX_FILES_ROOT'] = str(data)
                environment['NEX_RESOURCE_DIR'] = str(resources)
            action = cli('project','--kind','run','--component','app',cwd=directory)
            require(action['observation']['stdout']=='7\n','source-only project task read differs')
            deployment = root/'task-file-read-package'
            packaged = cli('project','--kind','package','--component','app','--directory',deployment,cwd=directory,timeout=300)
            require(not packaged['application_execution'],'packaging executed task file reads')
            criteria = cli('task','nex.build.json','--kind','init','--component','app','--configuration','release',cwd=directory)
            criteria['checks'] = [{'id':'read','program':'app','kind':'run','target':'native',
                'configuration':'release','entry':'installed_task_files::app::main',
                'expect':{'stdout':'7\n','exit_code':0},'timeout_seconds':30}]
            criteria['requirements'] = [{'id':'read','text':'Read explicit external inputs through captured source-only task project',
                'targets':['native'],'checks':['read'],'bindings':[{'program':'app','kind':'function','symbol':'installed_task_files::app::main'}]}]
            task = directory/'task.json';task.write_text(json.dumps(criteria))
            checked = cli('task',task,'--kind','check',cwd=directory)
            accepted = cli('task',task,'--kind','run','--task-hash',checked['task_hash'],
                '--directory',root/'task-file-read-capture',cwd=directory,timeout=300)
            require(accepted['ok'],'source-only task read capture failed')
            receipt = Path(accepted['output'])
            shutil.rmtree(directory)
            environment['NEX_RESOURCE_DIR'] = str(root/'absent-task-file-resources')
            require(run([deployment/'apps/app/bin/app'],cwd=root)=='7\n','packaged read needs deleted project')
            environment['NEX_RESOURCE_DIR'] = str(resources)
            replay = cli('task',receipt,'--kind','replay','--directory',root/'task-file-read-replay',timeout=300)
            require(replay['ok'] and replay['programs']==accepted['programs'],'source-deleted task read replay differs')
            report['evidence']['structured_task_file_reads'] = {'native_reference':True,'revision':revision,
                'standalone_without_resources':True,'source_only_project':True,'source_deleted_package':True,
                'source_deleted_replay':True,'receipt':str(receipt),'replay':replay['output'],
                'external_inputs_retained':True,'external_filesystem_snapshot_claim':False,
                'operator_supplied_root_required':True,'typescript_filesystem':False}
        finally:
            for key,value in previous.items():
                if value is None:environment.pop(key,None)
                else:environment[key]=value

    def structured_task_profile():
        descriptor = state['descriptor']['task_profiling']
        pack = json.loads((resources/'llm/language-pack.json').read_text())
        require(descriptor == pack['task_profiling'] and descriptor['source_support'] and
                descriptor['cli_language'] == report['language'] == '0.24',
                'installed task profiler descriptor/pack differs')
        limits = {'steps':2000000,'timeout_ms':10000,'workers':2}
        controls = ['--task-steps','2000000','--task-timeout-ms','10000','--task-workers','2']
        directory = root/'structured-task-profile'
        directory.mkdir()
        source = '''module installed_task_profile;
fn helper(x:i64)->i64{return x+1;}
fn leaf()->i64!{task}{task_yield();return helper(41);}
fn main()->unit!{io,task}{
 print(with_tasks(2,fn(scope:task_scope)->i64!{task}{
  let child:task<i64>=task_spawn(scope,leaf);task_yield();return task_wait(child);
 }));
}
'''
        (directory/'nex.json').write_text(json.dumps({'schema':'nex.project/1',
            'language':report['language'],'entry':'main.nex'}))
        (directory/'main.nex').write_text(source)
        revision = cli('check',cwd=directory)['revision']
        require(cli('eval',*controls,cwd=directory)['stdout']=='42\n' and
                cli('run','--profile','release',*controls,cwd=directory)['stdout']=='42\n',
                'task profile scenario differs between native and independent reference')

        def measured(profile, effective=limits):
            require(profile['schema']=='nex.profile/2' and profile['stdout']=='42\n' and
                    profile['language']=='0.24' and profile['build']['language']=='0.24' and
                    not profile['tracy'], 'installed task profile identity/output differs')
            require(all(profile['completeness'][key] for key in ('aggregates','memory','cpu','elapsed','lifetime')),
                    'installed task profile lost required measurements')
            execution = profile['task_execution']
            require(execution['configured']==limits and execution['effective']==effective and
                    execution['executor_workers']==effective['workers'], 'task profile launch limits differ')
            functions = {item['name']:item for item in profile['functions']}
            for name in ('main','leaf','helper'):
                item = functions['installed_task_profile::'+name]
                require((item['calls'],item['completed'],item['aborted'])==(1,1,0),
                        'task profiler counted scheduler resumes as source calls')
                require(item['inclusive_cpu_ns']>=item['self_cpu_ns'] and 'self_ns' not in item,
                        'task profiler confused CPU with synchronous wall metrics')
            require(all(item['live']==0 and item['live_shallow_bytes']==0 and
                        item['allocations']==item['frees'] for item in profile['memory']),
                    'task profile managed ownership did not retire')

        session = cli('profile','--events','0','--scenario','installed task suspension',*controls,cwd=directory)
        require(session['schema']=='nex.profile-session/2','installed task profile used old session schema')
        profile = json.loads(Path(session['output']).read_text())
        measured(profile)
        require(not profile['completeness']['timeline'] and profile['dropped_events']>0,
                'zero-event task profile omitted its timeline truncation')
        public_profile = root/'task-profile-public.json'
        shutil.copy2(session['output'],public_profile)
        built = cli('build','--profile','profile',*controls,cwd=directory)
        standalone = root/'standalone-task-profile'
        shutil.copy2(built['executable'],standalone)
        (directory/'main.nex').unlink()
        archived = cli('profile','--revision',revision,'--events','0',*controls,cwd=directory)
        measured(json.loads(Path(archived['output']).read_text()))
        shutil.rmtree(directory)
        previous = {key:environment.get(key) for key in ('NEX_PROFILE_OUTPUT','NEX_PROFILE_EVENTS',
                    'NEX_TRACY','NEX_RESOURCE_DIR','PATH')}
        raw_path = root/'standalone-task-profile-runtime.json'
        try:
            environment.update(NEX_PROFILE_OUTPUT=str(raw_path),NEX_PROFILE_EVENTS='0',NEX_TRACY='0',
                NEX_RESOURCE_DIR=str(root/'absent-task-profile-resources'),PATH='/usr/bin:/bin')
            require(run([standalone,'--nex-task-workers','1'],cwd=root)=='42\n',
                    'copied task profile executable needs its original source/SDK')
        finally:
            for key,value in previous.items():
                if value is None:environment.pop(key,None)
                else:environment[key]=value
        raw = json.loads(raw_path.read_text())
        require(raw['schema']=='nex.profile-runtime/2' and raw['build']['revision']==revision and
                raw['build']['compiler_build']==profile['build']['compiler_build'] and not raw['tracy'] and
                raw['task_execution']['effective']==dict(limits,workers=1),
                'independent task profile lost exact build or lowered worker limits')

        project = root/'structured-task-profile-project'
        (project/'app').mkdir(parents=True)
        (project/'nex.json').write_text(json.dumps({'schema':'nex.project/1',
            'language':report['language'],'entry':'app/main.nex'}))
        (project/'app/main.nex').write_text(source)
        (project/'nex.build.json').write_text(json.dumps({'schema':'nex.project-build/1',
            'default_configuration':'measured','configurations':{'measured':{'profile':'profile',
                'target':'native','task_limits':limits}},
            'components':{'app':{'kind':'executable','root':'app','entry':'app/main.nex'}}}))
        observation = cli('project','--kind','profile','--component','app','--events','0',
            '--','--nex-task-workers','1',cwd=project,timeout=300)
        measured(json.loads(Path(observation['observation']['output']).read_text()),dict(limits,workers=1))
        require(not observation['graph_store_opened'] and not (project/'.nex/graph.db').exists(),
                'source-only project task profiler opened a mutable graph store')
        criteria = cli('task','nex.build.json','--kind','init','--component','app',
            '--configuration','measured',cwd=project)
        criteria['checks'] = [{'id':'profile','program':'app','kind':'profile','target':'native',
            'configuration':'measured','entry':'installed_task_profile::main',
            'scenario':'installed exact source calls','timeout_seconds':180,
            'budget':{'max_calls':{'installed_task_profile::helper':'1'},
                'max_peak_handles':'10000','max_peak_objects':'10000'}}]
        criteria['requirements'] = [{'id':'profile','text':'Profile exact source calls across task suspension',
            'targets':['native'],'checks':['profile'],
            'bindings':[{'program':'app','kind':'function','symbol':'installed_task_profile::main'}]}]
        task = project/'task.json';task.write_text(json.dumps(criteria))
        checked = cli('task',task,'--kind','check',cwd=project)
        accepted = cli('task',task,'--kind','run','--task-hash',checked['task_hash'],
            '--directory',root/'task-profile-capture',cwd=project,timeout=300)
        require(accepted['ok'],'installed task profile capture or exact budget failed')
        receipt = Path(accepted['output'])
        measured(json.loads((receipt.parent/'artifacts/profile/profile.json').read_text()))
        shutil.rmtree(project)
        replay = cli('task',receipt,'--kind','replay','--directory',root/'task-profile-replay',timeout=300)
        require(replay['ok'] and replay['programs']==accepted['programs'],
                'source-deleted installed task profile replay differs')
        report['evidence']['structured_task_profile'] = {'native_reference':True,
            'exact_source_calls':True,'managed_cleanup':True,'event_only_truncation':True,
            'archived_source_deleted':True,'standalone_without_resources':True,
            'source_only_project':True,'source_deleted_replay':True,'cli_language':'0.24',
            'revision':revision,'profile':str(public_profile),'raw_profile':str(raw_path),
            'receipt':str(receipt),'replay':replay['output'],'configured_task_limits':limits,
            'lowered_workers':1,'memory_scope':'managed shallow handles/objects; not total heap/RAM'}

    def static_task_providers():
        import importlib.util
        feature = cli('describe')['task_providers']
        identity = cli('describe','--kind','index')
        pack = json.loads((resources/'llm/language-pack.json').read_text())
        require(feature == pack['task_providers'] and feature['public_enabled'] and feature['static_linkage'] and
                feature['source_required'] and feature['execution_task_abi']==5 and
                feature['descriptor_bytes']==88 and not feature['dynamic_linkage'] and
                not feature['profiling'] and not feature['logical_debugging'],
                'installed static task provider capability differs')
        directory = root/'static-task-providers';directory.mkdir()
        for name in ('leaf','mid','app'):(directory/name).mkdir()
        (directory/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.24','entry':'app/main.nex'}))
        limits = {'steps':1000000,'timeout_ms':10000,'workers':2}
        description = {'schema':'nex.project-build/1','default_configuration':'release',
            'configurations':{mode:{'profile':mode,'task_limits':limits} for mode in ('debug','release','profile')},
            'components':{
                'leaf':{'kind':'static_library','root':'leaf','entry':'leaf/value.nex','entry_function':'answer','exports':['read']},
                'mid':{'kind':'static_library','root':'mid','entry':'mid/value.nex','entry_function':'answer','dependencies':{'leaf':'static'}},
                'app':{'kind':'executable','root':'app','entry':'app/main.nex','dependencies':{'mid':'static','leaf':'static'}}}}
        (directory/'nex.build.json').write_text(json.dumps(description))
        (directory/'leaf/value.nex').write_text('''module installed_provider_leaf;
fn pure(value:i64)->i64{return value+1;}
pub fn answer(value:i64)->i64!{task}{task_yield();return pure(value);}
pub server fn read(path:str)->result<str>!{task,fs}{task_yield();return file_read_text(path);}
''')
        (directory/'mid/value.nex').write_text('module installed_provider_mid;import "../leaf/value.nex" as leaf;pub fn answer()->i64!{task}{return leaf::answer(41);}')
        application = directory/'app/main.nex'
        application.write_text('module installed_provider_app;import "../mid/value.nex" as mid;import "../leaf/value.nex" as leaf;fn main()->unit!{task,io}{print(mid::answer());}')
        plan = cli('project','--kind','plan','--component','app',cwd=directory)
        require(not plan['external_tools_invoked'] and not (directory/'.nex').exists(),
                'static task provider plan invoked tools or opened state')
        require(all(item['task_linkage']['execution_abi']==5 for item in plan['components']),
                'static task source ownership plan is absent')
        require(cli('eval',cwd=directory)['stdout']=='42\n','independent task provider source observation differs')
        built = cli('project','--kind','build','--component','app',cwd=directory,timeout=300)
        artifacts = {item['component']:item for item in built['artifacts']}
        records = {}
        archive_hashes = {}
        for name in ('leaf','mid'):
            archive = Path(artifacts[name]['artifact'])
            require(archive.read_bytes().startswith(b'!<arch>\n'),'provider is not an actual static archive')
            record = json.loads((archive.parent/'task-provider.json').read_text());records[name]=record
            require(record['schema']=='nex.native-task-provider/8' and record['code_only'] and
                    record['descriptor_abi']==0x4e45585400000005 and record['descriptor_size']==88 and
                    record['abi_offset']==40 and record['component']==name,
                    'provider sidecar identity/layout differs')
            archive_hashes[name]=hashlib.sha256(archive.read_bytes()).hexdigest()
            symbols = {}
            for line in run(['nm','-g',archive]).splitlines():
                words = line.split()
                if len(words)>=2 and len(words[-2])==1:
                    symbols.setdefault(words[-1].lstrip('_'),set()).add(words[-2])
            require(record['exports'] and all(symbols.get(export['accessor'],set()) & {'T','W'}
                    for export in record['exports'].values()),
                    'archive lacks defined descriptor accessor symbols')
        require(records['leaf']['cohort']==records['mid']['cohort'],'provider cohorts differ')
        app = artifacts['app']
        compilation = json.loads(Path(app['compilation']).read_text())
        require({name for unit in compilation['units'] for name in unit['functions']}=={'installed_provider_app::main'} and
                len(compilation['static_libraries'])==2,'consumer recompiles provider definitions')
        metadata = json.loads(Path(app['metadata']).read_text())
        require(records['leaf']['task_file_reads'] and not metadata['runtime_requirements']['task_file_reads'],
                'uncalled provider read export inflated root file requirements')
        require(run([app['artifact']],cwd='/')=='42\n','static provider standalone output differs')
        warm = cli('project','--kind','build','--component','app',cwd=directory,timeout=300)
        require(all(item['cached'] for item in warm['artifacts']),'static task provider warm cache missed')
        low = cli('project','--kind','run','--component','app','--','--nex-task-steps','500000',
            '--nex-task-timeout-ms','5000','--nex-task-workers','1',cwd=directory,timeout=300)
        require(low['observation']['stdout']=='42\n' and low['observation']['task_execution']['effective']==
                {'steps':500000,'timeout_ms':5000,'workers':1},'provider root controls were not inherited')
        grant = root/'static-task-provider-files';grant.mkdir();(grant/'text').write_bytes('A🌍\0λ'.encode())
        application.write_text('''module installed_provider_app;
import "../mid/value.nex" as mid;import "../leaf/value.nex" as leaf;
server fn main()->unit!{task,fs,io}{
 let outcome:result<str>=leaf::read("text");
 if error_code(outcome)=="CAPABILITY"{print("CAPABILITY");return;}
 let value:str=unwrap(outcome);assert(value=="A🌍\\u0000λ");print(mid::answer());print(len(value));
}
''')
        read_build = cli('project','--kind','build','--component','app',cwd=directory,timeout=300)
        read_artifacts = {item['component']:item for item in read_build['artifacts']}
        require(all(hashlib.sha256(Path(read_artifacts[name]['artifact']).read_bytes()).hexdigest()==archive_hashes[name]
                    for name in ('leaf','mid')),'root policy change rebuilt different provider machine code')
        require(json.loads(Path(read_artifacts['app']['metadata']).read_text())['runtime_requirements']['task_file_reads'],
                'provider-only read failed to request root grant transport')
        previous_grant = environment.pop('NEX_FILES_ROOT',None)
        try:
            require(run([read_artifacts['app']['artifact']],cwd='/')=='CAPABILITY\n','missing provider grant is not typed CAPABILITY')
            environment['NEX_FILES_ROOT']=str(grant)
            require(run([read_artifacts['app']['artifact']],cwd='/')=='42\n4\n','provider root file grant/UTF-8/NUL differs')
            criteria = cli('task','nex.build.json','--kind','init','--component','app','--configuration','release',cwd=directory)
            criteria['checks'].append({'id':'observe','kind':'run','program':'app','target':'native','configuration':'release',
                'expect':{'stdout':'42\n4\n','exit_code':0},'timeout_seconds':120})
            criteria['requirements'].append({'id':'observe','text':'Keep the checked static task providers',
                'bindings':[{'program':'app','kind':'function','symbol':'installed_provider_app::main'}],
                'targets':['native'],'checks':['observe']})
            taskfile = directory/'task.json';taskfile.write_text(json.dumps(criteria))
            accepted = cli('task',taskfile,'--kind','run','--directory',root/'static-task-provider-capture',cwd=directory,timeout=600)
            require(accepted['ok'],'static provider reviewed capture failed')
            receipt = Path(accepted['output']);saved = json.loads(receipt.read_text())
            native = next(check for check in saved['checks'] if check['id']=='build-native')
            retained = []
            spec = importlib.util.spec_from_file_location('sdk_static_provider_capsule',resources/'tools/core_capsule.py')
            capsule = importlib.util.module_from_spec(spec);spec.loader.exec_module(capsule)
            artifact_base = receipt.parent/'artifacts/build-native'
            retained_sha256 = {}
            total_bytes = 0

            def regular(base,name,maximum=64*1024*1024):
                require(type(name) is str and 0<len(name.encode())<=16384 and '\\' not in name and '\0' not in name,
                        'invalid retained completion path text')
                relative = Path(name)
                require(not relative.is_absolute() and relative.as_posix()==name and
                        all(part not in ('','.','..') for part in relative.parts),
                        'retained completion path escapes its root')
                path = base
                require(not path.is_symlink(),'retained completion root is a symlink')
                for part in relative.parts:
                    path = path/part
                    require(not path.is_symlink(),'retained completion contains a symlink')
                require(path.is_file() and path.stat().st_size<=maximum,'retained completion is not a bounded regular file')
                return path

            require({item['component'] for item in native['components']}=={'leaf','mid','app'} and
                    len(native['components'])==3,'retained component set differs')
            for component in native['components']:
                prefix = 'artifacts/build-native/components/'+component['component']+'/retained-build/'
                require(component['retained_build']==prefix+'retained.json','retained record moved outside its component')
                path = regular(receipt.parent,component['retained_build'],2*1024*1024)
                record = json.loads(path.read_text());retained.append(str(path))
                record_index = native['artifacts'].get(path.relative_to(artifact_base).as_posix(),{})
                require(set(record_index)=={'hash','bytes'} and record_index['bytes']==path.stat().st_size and
                        re.fullmatch('[0-9a-f]{64}',record_index['hash']),
                        'retained mapping is absent from the checked artifact index')
                require(set(record)=={'schema','compiler_build','build_key','original_directory','metadata_rewritten',
                        'hash_algorithm','completion_schema','files'} and
                        record['schema']=='nex.retained-native-task-build/1' and record['metadata_rewritten'] is False and
                        record['hash_algorithm']=='BLAKE3' and record['completion_schema']=='nex.native-completion/4' and
                        record['compiler_build']==identity['compiler_build'] and
                        type(record['files']) is list and 10<=len(record['files'])<=266,
                        'invalid retained completion record')
                original_directory = directory/'.nex/build'/record['build_key']
                require(re.fullmatch('[0-9a-f]{64}',record['build_key']) and
                        record['original_directory']==str(original_directory),'retained original directory differs')
                metadata = json.loads(regular(receipt.parent,prefix+'build.json',8*1024*1024).read_text())
                require(metadata['completion_schema']=='nex.native-completion/4' and
                        metadata['key']==record['build_key'] and metadata['compiler_build']==identity['compiler_build'],
                        'retained build/compiler identity differs')
                inputs = capsule.completion_inputs(metadata)
                require(2<=len(inputs)<=258 and (len(inputs)-2)%2==0 and inputs==['library-abi.json','task-provider.json']+
                        [part for index in range((len(inputs)-2)//2) for part in
                         ('libraries/%d.a'%index,'libraries/%d.task-provider.json'%index)],
                        'retained completion4 inputs are not the exact bounded ordered pin list')
                executable_name = 'libnex.a' if metadata['kind']=='static_library' else 'app'
                require(metadata['kind'] in ('static_library','executable'),'unsupported retained build kind')
                names = [executable_name,'program.mlir','program.ll','compilation.json','build.json','source-bundle.json',
                         *inputs,'complete','debug.json']
                require(len(names)==len(record['files']) and len(set(names))==len(names),
                        'retained completion map count/order differs')
                mapped = {}
                for name,row in zip(names,record['files']):
                    require(set(row)=={'original','retained','hash','bytes'} and
                            row['original']==str(original_directory/name) and row['retained']==prefix+name and
                            type(row['bytes']) is int and 0<=row['bytes']<=64*1024*1024 and
                            re.fullmatch('[0-9a-f]{64}',row['hash']),
                            'retained completion map path/type differs')
                    original = regular(directory,'.nex/build/'+record['build_key']+'/'+name).read_bytes()
                    copied = regular(receipt.parent,row['retained']).read_bytes()
                    total_bytes += len(copied)
                    require(total_bytes<=128*1024*1024 and len(original)==len(copied)==row['bytes'] and original==copied,
                            'retained completion changed original bytes or exceeded its bound')
                    index_name = (receipt.parent/row['retained']).relative_to(artifact_base).as_posix()
                    require(native['artifacts'].get(index_name)=={'hash':row['hash'],'bytes':row['bytes']},
                            'retained file differs from compiler-checked receipt BLAKE3 index')
                    retained_sha256[row['retained']]=hashlib.sha256(copied).hexdigest()
                    mapped[name]=(row,copied)
                require(re.fullmatch(b'[0-9a-f]{64}\n',mapped['complete'][1]),'retained raw completion is malformed')
                own = json.loads(mapped['task-provider.json'][1]);abi = json.loads(mapped['library-abi.json'][1])
                compiled = json.loads(mapped['compilation.json'][1])
                require(own==metadata['task_provider'] and own['component']==component['component'] and
                        own['compiler_build']==identity['compiler_build'] and own['cohort']==abi['abi'] and
                        own['cohort']==records['leaf']['cohort'] and own['language']=='0.24' and
                        own['code_only']==(executable_name=='libnex.a') and
                        metadata['task_provider_hash']==mapped['task-provider.json'][0]['hash'] and
                        compiled['static_libraries']==abi['static_libraries'] and
                        len(inputs)==2+2*len(abi['static_libraries']),
                        'retained archive/sidecar/cohort identity differs')
                for index,dependency in enumerate(abi['static_libraries']):
                    archive_name='libraries/%d.a'%index;sidecar_name='libraries/%d.task-provider.json'%index
                    sidecar=json.loads(mapped[sidecar_name][1])
                    require(dependency['hash']==mapped[archive_name][0]['hash'] and
                            dependency['task_provider_hash']==mapped[sidecar_name][0]['hash'] and
                            dependency['abi']==own['cohort'] and dependency['task_provider']==sidecar and
                            sidecar==records[sidecar['component']] and sidecar['code_only'] is True,
                            'retained dependency archive/sidecar pins differ')
                    for original_key,mapped_name in (('path',archive_name),('task_provider_path',sidecar_name)):
                        original = Path(dependency[original_key])
                        require(original.is_absolute() and original.is_relative_to(directory/'.nex/build'),
                                'retained dependency original escapes the selected build root')
                        original_name=original.relative_to(directory/'.nex/build').as_posix()
                        require(regular(directory,'.nex/build/'+original_name).read_bytes()==mapped[mapped_name][1],
                                'retained dependency differs from its completed original')
            packaged = cli('project','--kind','package','--component','app','--directory',root/'static-task-provider-package',cwd=directory,timeout=300)
            package = Path(packaged['directory']) if 'directory' in packaged else root/'static-task-provider-package'
            standalone = root/'static-task-provider-app';shutil.copy2(read_artifacts['app']['artifact'],standalone)
            shutil.rmtree(directory)
            prior_resources=environment.get('NEX_RESOURCE_DIR');environment['NEX_RESOURCE_DIR']='/absent'
            try:
                require(run([standalone],cwd='/')=='42\n4\n' and
                        run([package/'apps/app/bin/app'],cwd='/')=='42\n4\n',
                        'copied static task application/package needs compiler sources/resources')
            finally:
                if prior_resources is None:environment.pop('NEX_RESOURCE_DIR',None)
                else:environment['NEX_RESOURCE_DIR']=prior_resources
            replay = cli('task',receipt,'--kind','replay','--directory',root/'static-task-provider-replay',timeout=600)
            require(replay['ok'] and replay['programs']==accepted['programs'],'source-deleted static provider replay differs')
        finally:
            if previous_grant is None:environment.pop('NEX_FILES_ROOT',None)
            else:environment['NEX_FILES_ROOT']=previous_grant
        report['evidence']['static_task_providers'] = {key:True for key in (
            'descriptor','actual_static_archives','descriptor_accessors','consumer_ownership','native_reference',
            'unused_read_excluded','root_file_grant','root_limits','warm_cache','retained_completion',
            'source_deleted_replay','standalone_without_resources','source_deleted_package')}
        report['evidence']['static_task_providers'].update(execution_task_abi=5,descriptor_bytes=88,
            original_archives_sha256=archive_hashes,records=records,receipt=str(receipt),replay=replay['output'],retained=retained,
            retained_file_sha256=retained_sha256,retained_bytes=total_bytes,
            retained_hash_verification='compiler-checked receipt BLAKE3 index plus exact original/retained bytes and independent SHA256; no Python BLAKE3 recomputation')

    def shared_task_providers():
        import importlib.util
        feature=cli('describe')['task_shared_providers']
        identity=cli('describe','--kind','index')
        pack=json.loads((resources/'llm/language-pack.json').read_text())
        require(feature==pack['task_shared_providers'] and feature['public_enabled'] and
                feature['source_required'] and feature['execution_task_abi']==5 and feature['descriptor_bytes']==88 and
                feature['completion_schema']=='nex.native-completion/5' and not feature['runtime_load_unload'] and
                not feature['profiling'] and not feature['logical_debugging'],
                'installed shared task provider descriptor differs')
        directory=root/'shared-task-providers';directory.mkdir()
        for name in ('leaf','mid','app'):(directory/name).mkdir()
        (directory/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.24','entry':'app/main.nex'}))
        description={'schema':'nex.project-build/1','default_configuration':'release',
            'configurations':{'release':{'profile':'release','task_limits':{'steps':1000000,'timeout_ms':10000,'workers':2}}},
            'components':{
                'leaf':{'kind':'shared_library','root':'leaf','entry':'leaf/value.nex','entry_function':'answer','exports':['read']},
                'mid':{'kind':'shared_library','root':'mid','entry':'mid/value.nex','entry_function':'answer','dependencies':{'leaf':'dynamic'}},
                'app':{'kind':'executable','root':'app','entry':'app/main.nex','dependencies':{'mid':'dynamic','leaf':'dynamic'}}}}
        (directory/'nex.build.json').write_text(json.dumps(description))
        (directory/'leaf/value.nex').write_text('''module installed_shared_leaf;
fn pure(value:i64)->i64{return value+1;}
pub fn answer(value:i64)->i64!{task}{task_yield();return pure(value);}
pub server fn read(path:str)->result<str>!{task,fs}{return file_read_text(path);}
''')
        (directory/'mid/value.nex').write_text('module installed_shared_mid;import "../leaf/value.nex" as leaf;pub fn answer()->i64!{task}{return leaf::answer(41);}')
        application=directory/'app/main.nex'
        application.write_text('module installed_shared_app;import "../mid/value.nex" as mid;import "../leaf/value.nex" as leaf;fn main()->unit!{task,io}{print(mid::answer());}')
        plan=cli('project','--kind','plan','--component','app',cwd=directory)
        require(not plan['external_tools_invoked'] and not (directory/'.nex').exists(),
                'shared task provider planning invoked tools/state')
        source_plan={row['name']:row['task_linkage'] for row in plan['components']}
        require(all(row['schema']=='nex.project-task-linkage/8' and row['mode']=='shared-fixed' for row in source_plan.values()) and
                [image['component'] for image in source_plan['app']['load_closure']['images']]==['leaf','mid','app'],
                'shared task source/final ownership plan differs')
        require(cli('eval',cwd=directory)['stdout']=='42\n','shared provider independent source result differs')
        built=cli('project','--kind','build','--component','app',cwd=directory,timeout=300)
        artifacts={row['component']:row for row in built['artifacts']}
        records={};image_sha256={}
        for name in ('leaf','mid','app'):
            artifact=Path(artifacts[name]['artifact']);record=json.loads((artifact.parent/'task-provider.json').read_text())
            records[name]=record;image_sha256[name]=hashlib.sha256(artifact.read_bytes()).hexdigest()
            require(record['schema']=='nex.native-task-provider/8' and record['mode']=='shared-fixed' and
                    record['descriptor_abi']==0x4e45585400000005 and record['descriptor_size']==88 and
                    record['abi_offset']==40 and record['component']==record['owner_image']==name and
                    record['artifact_kind']==('application' if name=='app' else 'shared-image') and
                    record['image']['sha256']==image_sha256[name] and record['image']['key']==artifacts[name]['build_key'],
                    'actual shared image/provider identity differs')
            if name!='app':
                symbols={}
                for line in run(['nm','-g',artifact]).splitlines():
                    words=line.split()
                    if len(words)>=2 and len(words[-2])==1:
                        symbols.setdefault(words[-1].lstrip('_'),set()).add(words[-2])
                require(record['exports'] and all(symbols.get(export['accessor'],set()) & {'T','W'}
                        for export in record['exports'].values()),'shared image lacks a defined descriptor accessor')
                require(not symbols.get('main',set()) & {'T','W'} and all(not symbols.get(name,set()) & {'T','W'}
                        for name in ('nex_task_application_execute_limits_at','nex_application_run_at',
                                     'nex_release','nex_retain','nex_task_frame_call_at')) and
                        not any(types & {'T','W'} for name,types in symbols.items() if name.endswith('__task_step')),
                        'provider defines application/kernel entry')
        app=artifacts['app'];compilation=json.loads(Path(app['compilation']).read_text())
        require({name for unit in compilation['units'] for name in unit['functions']}=={'installed_shared_app::main'},
                'shared consumer recompiled provider definitions')
        images=compilation['owned_images']
        require(len(images)==3 and sum(image['kind']=='runtime' for image in images)==1 and
                len({Path(image['path']).name for image in images})==3,'shared closure/runtime inventory differs')
        metadata=json.loads(Path(app['metadata']).read_text())
        require(records['leaf']['task_file_reads'] and not metadata['task_application']['task_file_reads'] and
                not metadata['stage_runtime_requirements']['task_file_reads'] and
                built['native_runtime_image']['requirements']['task_file_reads'],
                'unused provider read code created root authority or was omitted from runtime support')
        loader_logs=[]
        def loaded_run(executable,expected_output):
            old_loader={key:environment.pop(key,None) for key in ('DYLD_PRINT_LIBRARIES','DYLD_PRINT_TO_FILE','LD_DEBUG','LD_DEBUG_OUTPUT')}
            loader_key='DYLD_PRINT_LIBRARIES' if platform.system()=='Darwin' else 'LD_DEBUG'
            environment[loader_key]='1' if platform.system()=='Darwin' else 'libs'
            try:
                require(run([executable],cwd='/')==expected_output,'loaded shared application result differs')
                loader_log=Path(report['commands'][-1]['stderr']);loader_logs.append(str(loader_log))
                loaded=loader_log.read_text().splitlines()
                if platform.system()=='Linux':loaded=[line.split('calling init:',1)[1].strip() for line in loaded if 'calling init:' in line]
                require(all(sum(line.rstrip().endswith('/'+Path(image['path']).name) for line in loaded)==1 for image in images),
                        'executing loader did not map each checked shared image exactly once')
                actual_runtime={Path(match).name for line in loaded for match in
                    re.findall(r'\S*libnex_runtime_[0-9a-f]{64}\.(?:dylib|so)',line)}
                require(actual_runtime=={Path(image['path']).name for image in images if image['kind']=='runtime'},
                        'executing loader mapped a different/additional task runtime')
            finally:
                environment.pop(loader_key,None)
                for key,value in old_loader.items():
                    if value is not None:environment[key]=value
        loaded_run(app['artifact'],'42\n')
        warm=cli('project','--kind','build','--component','app',cwd=directory,timeout=300)
        require(all(row['cached'] for row in warm['artifacts']),'shared task image warm cache missed')
        lowered=cli('project','--kind','run','--component','app','--','--nex-task-steps','500000',
            '--nex-task-timeout-ms','5000','--nex-task-workers','1',cwd=directory,timeout=300)
        require(lowered['observation']['stdout']=='42\n' and lowered['observation']['task_execution']['effective']==
                {'steps':500000,'timeout_ms':5000,'workers':1},'shared providers did not inherit lowered root controls')
        application.write_text('''module installed_shared_app;
import "../mid/value.nex" as mid;import "../leaf/value.nex" as leaf;
server fn main()->unit!{task,fs,io}{let read:result<str>=leaf::read("text");
 if error_code(read)=="CAPABILITY"{print("CAPABILITY");return;}
 let text:str=unwrap(read);assert(text=="A🌍\\u0000λ");print(mid::answer());print(len(text));}
''')
        read_build=cli('project','--kind','build','--component','app',cwd=directory,timeout=300)
        read_artifacts={row['component']:row for row in read_build['artifacts']}
        require(all(hashlib.sha256(Path(read_artifacts[name]['artifact']).read_bytes()).hexdigest()==image_sha256[name]
                    for name in ('leaf','mid')) and read_build['native_runtime_image']==built['native_runtime_image'],
                'root read policy changed unchanged provider/runtime machine code')
        grant=root/'shared-task-provider-files';grant.mkdir();(grant/'text').write_bytes('A🌍\0λ'.encode())
        previous_grant=environment.pop('NEX_FILES_ROOT',None)
        try:
            require(run([read_artifacts['app']['artifact']],cwd='/')=='CAPABILITY\n','missing shared read grant was not typed')
            environment['NEX_FILES_ROOT']=str(grant)
            require(run([read_artifacts['app']['artifact']],cwd='/')=='42\n4\n','shared root file grant/Unicode/NUL differs')
            criteria=cli('task','nex.build.json','--kind','init','--component','app','--configuration','release',cwd=directory)
            criteria['checks'].append({'id':'observe','kind':'run','program':'app','target':'native','configuration':'release',
                'expect':{'stdout':'42\n4\n','exit_code':0},'timeout_seconds':120})
            criteria['requirements'].append({'id':'observe','text':'Preserve the checked fixed shared task closure',
                'bindings':[{'program':'app','kind':'function','symbol':'installed_shared_app::main'}],
                'targets':['native'],'checks':['observe']})
            taskfile=directory/'task.json';taskfile.write_text(json.dumps(criteria))
            accepted=cli('task',taskfile,'--kind','run','--directory',root/'shared-task-provider-capture',cwd=directory,timeout=600)
            require(accepted['ok'],'shared task provider reviewed capture failed')
            receipt=Path(accepted['output']);saved=json.loads(receipt.read_text())
            native=next(row for row in saved['checks'] if row['id']=='build-native')
            command_path=task_sdk_regular(receipt.parent,'artifacts/build-native/commands/build.json',16*1024*1024)
            command_pin=native['artifacts'].get('commands/build.json',{})
            require(set(command_pin)=={'hash','bytes'} and command_pin['bytes']==command_path.stat().st_size and
                    re.fullmatch('[0-9a-f]{64}',command_pin['hash']),
                    'captured project command is absent from its compiler-checked receipt index')
            captured_artifacts=captured_task_build_artifacts(json.loads(command_path.read_text()),
                {row['name']:row['task_linkage'] for row in read_build['plan']['components']})
            spec=importlib.util.spec_from_file_location('sdk_shared_completion',resources/'tools/core_capsule.py')
            capsule=importlib.util.module_from_spec(spec);spec.loader.exec_module(capsule)
            retained_sha256={};retained=[];total_bytes=0

            def regular(base,name,maximum=64*1024*1024):
                require(type(name) is str and 0<len(name.encode())<=16384 and '\\' not in name and '\0' not in name,
                        'invalid retained shared path text')
                relative=Path(name)
                require(not relative.is_absolute() and relative.as_posix()==name and
                        all(part not in ('','.','..') for part in relative.parts),'retained shared path escapes')
                path=base;require(not path.is_symlink(),'retained shared root is a symlink')
                for part in relative.parts:
                    path=path/part;require(not path.is_symlink(),'retained shared path contains a symlink')
                require(path.is_file() and path.stat().st_size<=maximum,'retained shared file is not bounded/regular')
                return path

            require({row['component'] for row in native['components']}=={'leaf','mid','app'} and len(native['components'])==3,
                    'retained shared component set differs')
            artifact_base=receipt.parent/'artifacts/build-native'
            for component in native['components']:
                prefix='artifacts/build-native/components/'+component['component']+'/retained-build/'
                require(component['retained_build']==prefix+'retained.json','retained shared record moved')
                path=regular(receipt.parent,component['retained_build'],2*1024*1024)
                record=json.loads(path.read_text());retained.append(str(path))
                require(native['artifacts'].get(path.relative_to(artifact_base).as_posix(),{}).get('bytes')==path.stat().st_size,
                        'retained shared record is absent from the checked artifact index')
                require(set(record)=={'schema','compiler_build','build_key','original_directory','metadata_rewritten',
                        'hash_algorithm','completion_schema','files'} and record['schema']=='nex.retained-native-task-build/2' and
                        record['completion_schema']=='nex.native-completion/5' and record['metadata_rewritten'] is False and
                        record['hash_algorithm']=='BLAKE3' and record['compiler_build']==identity['compiler_build'] and
                        type(record['files']) is list and 13<=len(record['files'])<=1032,
                        'invalid retained completion5 mapping')
                original_directory=Path(record['original_directory'])
                require(original_directory.is_absolute() and original_directory.is_relative_to(directory/'.nex') and
                        original_directory.name==record['build_key'] and re.fullmatch('[0-9a-f]{64}',record['build_key']),
                        'retained completion5 original directory differs')
                metadata=json.loads(regular(receipt.parent,prefix+'build.json',8*1024*1024).read_text())
                require(metadata['completion_schema']=='nex.native-completion/5' and metadata['key']==record['build_key'] and
                        metadata['compiler_build']==identity['compiler_build'],'retained shared build identity differs')
                inputs=capsule.completion_inputs(metadata)
                require(5<=len(inputs)<=1024 and inputs[:4]==['library-abi.json','task-provider.json','image-inputs.json','objects.a'],
                        'retained completion5 typed ordered input list differs')
                own=json.loads(regular(receipt.parent,prefix+'task-provider.json',16*1024*1024).read_text())
                actual_artifact=Path(captured_artifacts[component['component']]['artifact'])
                require(actual_artifact.parent==original_directory and
                        actual_artifact.name==('app' if component['component']=='app' else
                            'libnex_'+component['component']+'_'+record['build_key']+actual_artifact.suffix) and
                        metadata['kind']==('executable' if component['component']=='app' else 'shared_library'),
                        'retained executable does not match the actual captured component artifact')
                executable=actual_artifact.name
                names=[executable,'program.mlir','program.ll','compilation.json','build.json','source-bundle.json',*inputs,'complete','debug.json']
                require(len(names)==len(set(names))==len(record['files']),'retained shared map count differs')
                mapped={}
                for name,row in zip(names,record['files']):
                    require(set(row)=={'original','retained','hash','bytes'} and row['original']==str(original_directory/name) and
                            row['retained']==prefix+name and type(row['bytes']) is int and 0<=row['bytes']<=64*1024*1024 and
                            re.fullmatch('[0-9a-f]{64}',row['hash']),'invalid retained shared map row')
                    original=regular(directory,original_directory.relative_to(directory).as_posix()+'/'+name).read_bytes()
                    copied=regular(receipt.parent,row['retained']).read_bytes();total_bytes+=len(copied)
                    require(total_bytes<=256*1024*1024 and len(original)==len(copied)==row['bytes'] and original==copied,
                            'retained shared bytes changed/exceeded bound')
                    key=(receipt.parent/row['retained']).relative_to(artifact_base).as_posix()
                    require(native['artifacts'].get(key)=={'hash':row['hash'],'bytes':row['bytes']},
                            'retained shared file differs from compiler-checked BLAKE3 artifact index')
                    retained_sha256[row['retained']]=hashlib.sha256(copied).hexdigest();mapped[name]=(row,copied)
                require(re.fullmatch(b'[0-9a-f]{64}\n',mapped['complete'][1]),'retained completion5 raw digest is malformed')
                abi=json.loads(mapped['library-abi.json'][1]);links=json.loads(mapped['image-inputs.json'][1])
                require(own==metadata['task_provider'] and own['component']==component['component'] and
                        own['compiler_build']==identity['compiler_build'] and own['cohort']==abi['abi'] and
                        own['schema']=='nex.native-task-provider/8' and own['mode']=='shared-fixed' and
                        metadata['task_provider_hash']==mapped['task-provider.json'][0]['hash'] and
                        own['image']['sha256']==hashlib.sha256(mapped[executable][1]).hexdigest() and
                        links['schema']=='nex.native-image-inputs/2','retained shared sidecar/image pins differ')
                for index,dependency in enumerate(abi['static_libraries']):
                    archive='libraries/%d.a'%index;sidecar='libraries/%d.task-provider.json'%index
                    require(dependency['hash']==mapped[archive][0]['hash'] and
                            dependency['task_provider_hash']==mapped[sidecar][0]['hash'] and
                            dependency['task_provider']==json.loads(mapped[sidecar][1]),'retained static frontier pins differ')
                require(sum(image['kind']=='runtime' for image in links['images'])==1 and
                        len(links['task_providers'])==sum(image['kind']=='library' for image in links['images']),
                        'retained loaded closure/provider cardinality differs')
                for image in links['images']:
                    name='images/'+Path(image['path']).name
                    require(image['hash']==mapped[name][0]['hash'] and
                            image['sha256']==hashlib.sha256(mapped[name][1]).hexdigest(),'retained owned image pin differs')
                for provider in links['task_providers']:
                    sidecar=json.loads(mapped[provider['path']][1]);image=next(row for row in links['images'] if Path(row['path']).name==Path(provider['image']).name)
                    require(provider['hash']==mapped[provider['path']][0]['hash'] and sidecar['component']==provider['component'] and
                            all(sidecar['image'][key]==image[key] for key in ('key','hash','sha256','uuid')) and
                            sidecar['image']['runtime_key']==own['image']['runtime_key'] and
                            sidecar['image']['runtime_hash']==own['image']['runtime_hash'],
                            'retained owned sidecar/raw image/runtime identity differs')
            package=root/'shared-task-provider-package'
            cli('project','--kind','package','--component','app','--directory',package,cwd=directory,timeout=300)
            application_package=package/'apps/app';package_meta=json.loads((application_package/'application.json').read_text())
            package_provenance=package_task_provenance(application_package,package_meta,directory)
            # The original-CWD package and captured-workspace build have distinct
            # valid identities. Trace/copy this package's own completed closure.
            app_folder=directory/'.nex/build'/package_meta['build_key']
            images=json.loads((app_folder/'compilation.json').read_text())['owned_images']
            copied=root/'shared-task-provider-copied';copied.mkdir()
            shutil.copy2(app_folder/'app',copied/'app')
            shutil.copytree(app_folder/'images',copied/'images')
            shutil.rmtree(directory)
            previous_resources=environment.get('NEX_RESOURCE_DIR');environment['NEX_RESOURCE_DIR']='/absent'
            try:
                loaded_run(copied/'app','42\n4\n')
                loaded_run(application_package/'bin/app','42\n4\n')
            finally:
                if previous_resources is None:environment.pop('NEX_RESOURCE_DIR',None)
                else:environment['NEX_RESOURCE_DIR']=previous_resources
            replay=cli('task',receipt,'--kind','replay','--directory',root/'shared-task-provider-replay',timeout=600)
            require(replay['ok'] and replay['programs']==accepted['programs'],'source-deleted shared task provider replay differs')
        finally:
            if previous_grant is None:environment.pop('NEX_FILES_ROOT',None)
            else:environment['NEX_FILES_ROOT']=previous_grant
        report['evidence']['shared_task_providers']={key:True for key in (
            'descriptor','actual_shared_images','defined_descriptor_accessors','consumer_ownership','actual_loaded_closure',
            'one_runtime','native_reference','unused_read_excluded','root_file_grant','root_limits','warm_cache',
            'retained_completion5','raw_package_provenance','source_deleted_replay',
            'copied_closure_without_resources','source_deleted_package')}
        report['evidence']['shared_task_providers'].update(execution_task_abi=5,descriptor_bytes=88,records=records,
            original_images_sha256=image_sha256,loader_logs=loader_logs,receipt=str(receipt),replay=replay['output'],
            captured_artifacts=captured_artifacts,package_provenance=package_provenance,
            retained=retained,retained_file_sha256=retained_sha256,retained_bytes=total_bytes,
            retained_hash_verification='compiler-checked receipt BLAKE3 index plus exact original/retained bytes and independent SHA256; no Python BLAKE3 recomputation',
            physical_file_retirement_claim=False)

    def task_provider_debuggers():
        import importlib.util
        feature=cli('describe')['task_provider_debugging'];identity=cli('describe','--kind','index')
        pack=json.loads((resources/'llm/language-pack.json').read_text())
        require(feature==pack['task_provider_debugging'] and feature['public_enabled'] is True and
                feature['source_support'] is True and feature['record_schema']=='nex.native-task-provider/10' and
                feature['catalog_schema']=='nex.task-debug-catalog/1' and feature['catalog_abi']==2 and
                feature['registry_abi']==1 and feature['maximum_total_registries_including_root']==128 and
                not feature['combined_debug_profile'] and not feature['runtime_load_unload'],
                'installed task provider debugger descriptor differs')
        directory=root/'task-provider-debug';directory.mkdir()
        for name in ('leaf','mid','unused','app'):(directory/name).mkdir()
        (directory/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.24','entry':'app/main.nex'}))
        (directory/'leaf/value.nex').write_text('''module installed_debug_leaf;
pub fn work(input:i64)->i64!{task}{
 let value:i64=input;
 task_yield();
 return value+1;
}
''')
        (directory/'mid/value.nex').write_text('''module installed_debug_mid;import "../leaf/value.nex" as leaf;
pub fn work(input:i64)->i64!{task}{let answer:i64=leaf::work(input);task_yield();return answer;}
''')
        (directory/'unused/value.nex').write_text('module installed_debug_unused;pub fn unused()->str{return "provider-only";}')
        (directory/'app/main.nex').write_text('module installed_debug_app;import "../mid/value.nex" as mid;fn main()->unit!{task,io}{print(mid::work(41));}')
        description={'schema':'nex.project-build/1','default_configuration':'logical_debug',
            'configurations':{'logical_debug':{'profile':'debug','task_limits':{'steps':1000000,'timeout_ms':60000,'workers':2}}},
            'components':{'leaf':{'kind':'static_library','root':'leaf','entry':'leaf/value.nex','entry_function':'work'},
                'mid':{'kind':'static_library','root':'mid','entry':'mid/value.nex','entry_function':'work','dependencies':{'leaf':'static'}},
                'unused':{'kind':'static_library','root':'unused','entry':'unused/value.nex','entry_function':'unused'},
                'app':{'kind':'executable','root':'app','entry':'app/main.nex','dependencies':{'mid':'static','unused':'static'}}}}
        manifest_path=directory/'nex.build.json';manifest_path.write_text(json.dumps(description))
        require(cli('eval',cwd=directory)['stdout']=='42\n','provider debugger reference output differs')
        static=cli('project','--kind','debug','--component','app','--adapter','nex-dap',cwd=directory,timeout=300)
        static_session=static['observation'];static_manifest=json.loads(Path(static_session['manifest']).read_text())
        require(static_manifest['schema']=='nex.debug/3' and static_manifest['task_debug']['abi']==2 and
                static_manifest['task_debug']['catalog']['mode']=='static' and not static_manifest.get('owned_images'),
                'static debugger did not retain its one executable runtime')
        require(run([static_manifest['program']])=='42\n','actual static provider debug source output differs from reference')
        description['components']['mid']['kind']='shared_library';description['components']['unused']['kind']='shared_library'
        description['components']['app']['dependencies']={'mid':'dynamic','unused':'dynamic'};manifest_path.write_text(json.dumps(description))
        prepared=cli('project','--kind','debug','--component','app','--adapter','nex-dap',cwd=directory,timeout=300)
        session=prepared['observation'];view_manifest=json.loads(Path(session['manifest']).read_text());view=view_manifest['task_debug']
        require(session['task_debug']['schema']=='nex.task-debug-session/2' and view['schema']=='nex.task-debug-view/2' and
                view['catalog']['mode']=='shared-fixed' and view['runtime_image']['kind']=='runtime' and
                view['runtime_image']['component'] is None and {r['component'] for r in view['registries']}=={'leaf','mid','unused','app'} and
                next(r['code_count'] for r in view['registries'] if r['component']=='unused')==0,
                'fixed shared debugger lost original/zero-code registries or runtime owner')
        require({row['component'] for row in view['source_union']['components']}=={'leaf','mid','unused','app'},
                'provider debugger checked source union is incomplete')
        # Actual exported original-registry symbols, never undefined-name substrings.
        symbols={}
        for image in view['images']:
            output=run(['nm','-g',image['path']]);defined=set()
            for line in output.splitlines():
                parts=line.split()
                if len(parts)>=2 and parts[-2].upper() in ('T','W'):
                    symbol=parts[-1];defined.add(symbol[1:] if symbol.startswith('_') else symbol)
            symbols[image['component']]=defined
        for row in view['registries']:
            require(row['accessor'] in symbols[row['owner_image']],
                    'provider original registry accessor is not physically defined by its owner')
        expected_paths={image['path'] for image in view['images']}|{view['runtime_image']['path']}
        require(expected_paths=={view_manifest['program']}|{image['path'] for image in view_manifest['owned_images']} and
                sum(image['kind']=='runtime' for image in view_manifest['owned_images'])==1,
                'provider debug fixed loaded closure differs')
        require(run([view_manifest['program']])=='42\n','actual shared provider debug source output differs from reference')
        spec=importlib.util.spec_from_file_location('sdk_debug_capsule',resources/'tools/core_capsule.py')
        capsule=importlib.util.module_from_spec(spec);spec.loader.exec_module(capsule)
        task=cli('task','nex.build.json','--kind','init','--component','app','--configuration','logical_debug',cwd=directory)
        task['checks']=[{'id':'prepare-debug','kind':'build','program':'app','target':'native','configuration':'logical_debug',
            'task_debug':True,'timeout_seconds':300}]
        task['requirements']=[{'id':'prepare-debug','text':'Prepare checked task provider debug artifacts without execution',
            'bindings':[{'program':'app','kind':'function','symbol':'installed_debug_app::main'}],
            'targets':['native'],'checks':['prepare-debug']}]
        taskfile=directory/'task.json';taskfile.write_text(json.dumps(task))
        accepted=cli('task',taskfile,'--kind','run','--directory',root/'task-provider-debug-capture',cwd=directory,timeout=600)
        receipt=Path(accepted['output']);record=json.loads(receipt.read_text());check,=record['checks']
        require(check['status']=='passed','captured provider debug preparation failed')
        command_path=task_sdk_regular(receipt.parent,check['receipt'],4*1024*1024)
        command=json.loads(command_path.read_text())
        linkages={item['name']:item['task_linkage'] for item in command['response']['plan']['components']}
        require(all(row['schema']=='nex.project-task-linkage/10' for row in linkages.values()),
                'captured provider debug source plan lacks instrumentation linkage')
        artifacts=captured_task_build_artifacts(command,linkages)
        retention=[retained_task_debug_build(receipt.parent,check,artifacts[item['component']],item,
            identity['compiler_build'],capsule.completion_inputs) for item in check['components']]
        app=next(row for row in check['components'] if row['component']=='app')
        retained_session=json.loads(task_sdk_regular(receipt.parent,app['debug_session'],2*1024*1024).read_text())
        require(Path(retained_session['manifest'])==receipt.parent/app['debug_manifest'] and
                task_sdk_regular(receipt.parent,app['debug_relocation']).is_file(),
                'captured provider debugger fresh session is absent')
        package=root/'task-provider-debug-package'
        cli('project','--kind','package','--component','app','--task-debug','--directory',package,cwd=directory,timeout=600)
        package_app=package/'apps/app';package_meta=json.loads((package_app/'application.json').read_text())
        package_proof=relocated_task_debug(package_app,package_meta,directory,capsule.completion_inputs)
        packaged_session=json.loads(task_sdk_regular(package_app,package_meta['debug_session'],2*1024*1024).read_text())
        require(Path(packaged_session['manifest'])==package_app/package_meta['debug_manifest'],
                'packaged provider debugger session/manifest disagree')
        live=[]
        def observe(selected,label,enter=False):
            log=root/('task-provider-debug-live-'+label);log.mkdir();trace=[]
            class Recorded(DAP):
                def send(self,command,arguments=None):
                    trace.append({'request':command,'arguments':arguments});return super().send(command,arguments)
                def wait(self,predicate,timeout=30):
                    result=super().wait(predicate,timeout);trace.append({'response_or_event':result});return result
            client=Recorded(selected['adapter_command'],log,environment)
            try:
                client.request('initialize',{'adapterID':'nex','pathFormat':'path','linesStartAt1':True})
                pending=client.send('launch',dict(selected['launch'],disableASLR=False));client.event('initialized')
                points=client.request('setFunctionBreakpoints',{'breakpoints':[{'name':'installed_debug_mid::work' if enter else 'installed_debug_leaf::work'}]})
                require(points['breakpoints'][0]['verified'],'provider function breakpoint is unverified')
                client.request('configurationDone');client.response(pending);stop=client.event('stopped')
                require(stop.get('allThreadsStopped') is True and 'threadId' not in stop,'provider stop leaked physical thread identity')
                tasks=client.request('threads');logical=tasks['nex']['selected'];before=client.request('stackTrace',{'threadId':logical})
                caller=before['nex']['frames'][0]['id']
                if enter:
                    for _ in range(16):
                        client.request('stepIn',{'threadId':logical,'singleThread':True});client.event('stopped')
                        before=client.request('stackTrace',{'threadId':logical})
                        if before['stackFrames'][0]['name']=='installed_debug_leaf::work':break
                    require(before['stackFrames'][0]['name']=='installed_debug_leaf::work' and
                            before['nex']['frames'][0]['id']!=caller,'provider stepIn did not enter a distinct logical activation')
                require([row['name'] for row in before['stackFrames']]==['installed_debug_leaf::work','installed_debug_mid::work','installed_debug_app::main'],
                        'provider logical source stack differs')
                frame=before['stackFrames'][0]['id'];scope=client.request('scopes',{'frameId':frame})['scopes'][0]['variablesReference']
                values=client.request('variables',{'variablesReference':scope})['variables']
                require(next(row['value'] for row in values if row['name']=='input')=='41',
                        'provider initialized owned local is absent')
                watch=client.request('evaluate',{'expression':'input+1','frameId':frame,'context':'watch'})
                require(watch['nex']['value']=='42' and watch['nex']['source_identity']['component']=='leaf',
                        'provider watch used the wrong checked component')
                client.request('next',{'threadId':logical});client.event('stopped')
                after=client.request('stackTrace',{'threadId':logical})
                require(before['nex']['task_id']==after['nex']['task_id']==logical and
                        before['nex']['generation']==after['nex']['generation'] and
                        after['nex']['frames'][0]['id']==before['nex']['frames'][0]['id'] and
                        after['stackFrames'][0]['line']>before['stackFrames'][0]['line'] and
                        after['nex']['frames'][0]['point_id']!=before['nex']['frames'][0]['point_id'] and
                        int(after['nex']['stop_id'])>int(before['nex']['stop_id']),
                        'provider next did not advance the selected activation/epoch')
                stale=client.send('variables',{'variablesReference':scope})
                require(client.wait(lambda m:m.get('type')=='response' and m.get('request_seq')==stale)['success'] is False,
                        'provider variable reference survived resume')
                client.request('stepOut',{'threadId':logical});client.event('stopped')
                parent=client.request('stackTrace',{'threadId':logical})
                require(parent['stackFrames'][0]['name']=='installed_debug_mid::work' and
                        (not enter or parent['nex']['frames'][0]['id']==caller),'provider stepOut lost its caller')
                client.request('continue',{'threadId':logical});require(client.event('exited')['exitCode']==0,'provider debuggee failed')
                live.append({'label':label,'source_identity':watch['nex']['source_identity'],'before':before['nex'],'after':after['nex']})
            finally:
                try:client.close()
                finally:(log/'protocol.json').write_text(json.dumps(trace,ensure_ascii=False,indent=2)+'\n')
        if args.live:
            observe(static_session,'static');observe(session,'shared',True)
        # Source/cache removal tests the independently relocated sessions, not stale originals.
        for name in description['components']:shutil.rmtree(directory/name)
        shutil.rmtree(directory/'.nex');taskfile.unlink()
        if args.live:
            observe(retained_session,'retained');observe(packaged_session,'package')
        replay=cli('task',receipt,'--kind','replay','--directory',root/'task-provider-debug-replay',cwd=root,timeout=600)
        replay_path=Path(replay['output']);replayed=json.loads(replay_path.read_text());again,=replayed['checks']
        require(again['status']=='passed' and replayed['programs']==record['programs'],'source-deleted debug preparation replay differs')
        replay_app=next(row for row in again['components'] if row['component']=='app')
        replay_session=json.loads(task_sdk_regular(replay_path.parent,replay_app['debug_session'],2*1024*1024).read_text())
        if args.live:observe(replay_session,'replay')
        evidence={name:True for name in ('descriptor','native_reference','static_and_shared_artifacts','original_registry_symbols',
            'closed_owned_images','source_union','retained_completion7','raw_package_provenance','source_deleted_capture','source_deleted_replay')}
        evidence.update({name:bool(args.live) for name in ('provider_locals','component_pure_watch','next_in_out','stale_references',
            'retained_live_debug','package_live_debug','replay_live_debug')})
        evidence.update(receipt=str(receipt),replay=str(replay_path),retained=retention,package=package_proof,live=live,
            execution_task_abi=5,catalog_abi=2,source_language='0.24',inferior_function_calls=False)
        report['evidence']['task_provider_debugging']=evidence

    def task_provider_profiles():
        import importlib.util
        # Registered only after the matching compiler's generated-source proof.
        feature=cli('describe')['task_provider_profiling'];identity=cli('describe','--kind','index')
        pack=json.loads((resources/'llm/language-pack.json').read_text())
        require(feature==pack['task_provider_profiling'] and feature['public_enabled'] is True and
                feature['source_support'] is True and feature['record_schema']=='nex.native-task-provider/9' and
                feature['registry_abi']==1 and feature['registry_bytes']==32 and
                feature['execution_task_abi']==5 and not feature['runtime_load_unload'] and not feature['tracy'],
                'installed task provider profiling descriptor differs')
        directory=root/'task-provider-profile';directory.mkdir()
        for name in ('leaf','mid','unused','app'):(directory/name).mkdir()
        (directory/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.24','entry':'app/main.nex'}))
        limits={'steps':1000000,'timeout_ms':10000,'workers':2}
        description={'schema':'nex.project-build/1','default_configuration':'measured',
            'configurations':{'measured':{'profile':'profile','task_limits':limits}},'components':{
                'leaf':{'kind':'static_library','root':'leaf','entry':'leaf/value.nex','entry_function':'work','exports':['read']},
                'mid':{'kind':'shared_library','root':'mid','entry':'mid/value.nex','entry_function':'work','dependencies':{'leaf':'static'}},
                'unused':{'kind':'shared_library','root':'unused','entry':'unused/value.nex','entry_function':'unused'},
                'app':{'kind':'executable','root':'app','entry':'app/main.nex','dependencies':{'mid':'dynamic','unused':'dynamic'}}}}
        (directory/'nex.build.json').write_text(json.dumps(description))
        (directory/'leaf/value.nex').write_text(r'''module installed_profile_leaf;
fn helper(value:i64)->i64{let owned:list<str>=["A🌍\u0000λ"];assert(len(owned[0])==4);return value+1;}
pub fn work(value:i64)->i64!{task}{task_yield();return helper(value);}
pub server fn read()->result<str>!{task,fs}{return file_read_text("unused");}
''')
        (directory/'mid/value.nex').write_text('module installed_profile_mid;import "../leaf/value.nex" as leaf;pub fn work(value:i64)->i64!{task}{task_yield();return leaf::work(value);}')
        (directory/'unused/value.nex').write_text('module installed_profile_unused;fn identity<T>(value:T)->T{return value;}pub fn unused()->str{return identity("only provider generic");}')
        (directory/'app/main.nex').write_text('module installed_profile_app;import "../mid/value.nex" as mid;fn main()->unit!{task,io}{print(mid::work(41));print(mid::work(41));}')
        expected={'installed_profile_app::main':1,'installed_profile_mid::work':2,'installed_profile_leaf::work':2,
            'installed_profile_leaf::helper':2,'installed_profile_leaf::read':0,
            'installed_profile_unused::unused':0,'installed_profile_unused::identity<str>':0}
        output='42\n42\n'
        plan=cli('project','--kind','plan','--component','app',cwd=directory)
        require(plan['external_tools_invoked'] is False and not (directory/'.nex').exists(),
                'profiled provider readonly planning invoked tools/state')
        source_plan={row['name']:row['task_linkage'] for row in plan['components']}
        require(set(source_plan)=={'leaf','mid','unused','app'} and all(value['schema']=='nex.project-task-linkage/9' and
                value['profiling']['schema']=='nex.project-task-profile/1' and value['profiling']['registry_abi']==1
                for value in source_plan.values()),'profiled source ownership plan differs')
        require(cli('eval',cwd=directory)['stdout']==output,'profile provider independent source oracle differs')
        def checked(session,timeline=True):
            require(session['schema']=='nex.profile-session/3' and session['stdout']==output and
                    session['build']['schema']=='nex.profile-build/2','profiled provider session identity differs')
            saved=json.loads(Path(session['output']).read_text())
            require(saved['schema']=='nex.profile/3' and saved['build_key']==session['build_key'] and
                    saved['build']['build_key']==session['build_key'] and saved['build']['compiler_build']==identity['compiler_build'] and
                    all(saved['completeness'][key] is True for key in ('aggregates','memory','cpu','elapsed','lifetime')) and
                    saved['completeness']['timeline'] is timeline,'profiled provider completeness/build differs')
            functions={row['name']:row for row in saved['functions']}
            require(len(functions)==len(saved['functions']) and set(functions)==set(expected),
                    'provider profile source function set differs from independent fixture oracle')
            for name,count in expected.items():
                row=functions[name];require((row['calls'],row['completed'],row['aborted'])==(count,count,0),
                    'provider exact source-call oracle differs: '+name)
            require(all(row['terminal'] and row['active_invocations']==0 for row in saved['tasks']) and
                    all(row['live']==0 and row['live_shallow_bytes']==0 and row['allocations']==row['frees'] for row in saved['memory']),
                    'provider profile published before owned cleanup')
            catalog=saved['task_provider_profile']['catalog'];registries=catalog['registries']
            require({row['component']:row['owner_image'] for row in registries}=={'app':'app','leaf':'mid','mid':'mid','unused':'unused'} and
                    {site['name'] for row in registries for site in row['sites']}==set(functions) and
                    functions['installed_profile_unused::identity<str>']['node_id'] is None and
                    functions['installed_profile_unused::identity<str>']['identity_scope']=='captured_project_component',
                    'provider-only zero site/physical source owner differs')
            return saved
        profiled=cli('project','--kind','profile','--component','app',cwd=directory,timeout=300)
        saved=checked(profiled['observation']);artifacts={row['component']:row for row in profiled['artifacts']}
        require(saved['build_key']==artifacts['app']['build_key'],'profile command measured another artifact')
        for name,registries in (('mid',('leaf','mid')),('unused',('unused',))):
            symbols={}
            for line in run(['nm','-g',artifacts[name]['artifact']]).splitlines():
                words=line.split()
                if len(words)>=2 and len(words[-2])==1:symbols.setdefault(words[-1].lstrip('_'),set()).add(words[-2])
            require(all(symbols.get('nex_task_profile_registry_'+component+'_v1',set()) & {'T','W'} for component in registries) and
                    all(not symbols.get(symbol,set()) & {'T','W'} for symbol in
                        ('nex_profile_enter','nex_profile_build_info','nex_task_profile_prepare_registries','nex_release')),
                    'provider registry accessor is undefined or image duplicates profiling runtime')
            if name=='unused':
                debug=json.loads(Path(artifacts[name]['debug_manifest']).read_text())
                generic=next(row for row in debug['functions'] if row['name']=='installed_profile_unused::identity<str>')
                checked_generic=next(site for registry in saved['task_provider_profile']['catalog']['registries']
                    for site in registry['sites'] if site['name']==generic['name'])
                require(generic['function_hash']==checked_generic['function_hash'] and
                        generic['function_source_hash']==checked_generic['function_source_hash'] and
                        symbols.get(generic['native_symbol'],set()) & {'T','W'},
                        'zero-call provider-only generic has no actual checked physical definition')
        metadata=json.loads(Path(artifacts['app']['metadata']).read_text())
        require(metadata['task_application']['task_file_reads'] is False and
                profiled['native_runtime_image']['requirements']['task_file_reads'] is True,
                'unused instrumented provider read code changed root grant policy')
        require(all(row['cached'] for row in cli('project','--kind','build','--component','app',cwd=directory,timeout=300)['artifacts']),
                'profile provider warm cache missed')
        lowered=cli('project','--kind','profile','--component','app','--events','0','--',
            '--nex-task-steps','500000','--nex-task-workers','1',cwd=directory,timeout=300)
        reduced=checked(lowered['observation'],False)
        require(reduced['task_execution']['effective']==dict(limits,steps=500000,workers=1) and reduced['dropped_events']>0,
                'provider profile lost lowered root policy/event-only completeness')
        task=cli('task','nex.build.json','--kind','init','--component','app','--configuration','measured',cwd=directory)
        task['checks']=[{'id':'measure-provider','kind':'profile','program':'app','target':'native','configuration':'measured',
            'entry':'installed_profile_app::main','scenario':'provider source calls over suspension',
            'budget':{'max_calls':{name:str(count) for name,count in expected.items()},'max_peak_handles':'100000','max_peak_objects':'100000'},
            'timeout_seconds':300}]
        task['requirements']=[{'id':'measure-provider','text':'Measure the checked physical task provider closure',
            'bindings':[{'program':'app','kind':'function','symbol':'installed_profile_app::main'}],
            'targets':['native'],'checks':['measure-provider']}]
        taskfile=directory/'task.json';taskfile.write_text(json.dumps(task))
        accepted=cli('task',taskfile,'--kind','run','--directory',root/'task-provider-profile-capture',cwd=directory,timeout=600)
        receipt=Path(accepted['output']);full=json.loads(receipt.read_text());check,=full['checks']
        require(check['status']=='passed' and not check['budget_failures'],'provider profile reviewed budget failed')
        command_file_sha256={}
        for field in ('build','receipt'):
            path=task_sdk_regular(receipt.parent,check[field],64*1024*1024)
            relative=path.relative_to(receipt.parent/'artifacts/measure-provider').as_posix()
            pin=check['artifacts'].get(relative,{})
            require(isinstance(pin,dict) and set(pin)=={'hash','bytes'} and type(pin['bytes']) is int and
                    pin['bytes']==path.stat().st_size and isinstance(pin['hash'],str) and re.fullmatch('[0-9a-f]{64}',pin['hash']),
                    'measured profile command lacks checked artifact index/size')
            command_file_sha256[check[field]]=hashlib.sha256(path.read_bytes()).hexdigest()
        command_path=task_sdk_regular(receipt.parent,check['build'],16*1024*1024)
        captured=captured_task_build_artifacts(json.loads(command_path.read_text()),source_plan)
        measured=json.loads(task_sdk_regular(receipt.parent,check['receipt'],64*1024*1024).read_text())
        captured_saved=checked(measured['response'],False)
        require(captured_saved['build_key']==captured['app']['build_key']==measured['build_key'],
                'provider profile capture associated a different CWD/build action')
        spec=importlib.util.spec_from_file_location('sdk_profile_completion',resources/'tools/core_capsule.py')
        capsule=importlib.util.module_from_spec(spec);spec.loader.exec_module(capsule)
        require({row['component'] for row in check['components']}==set(captured),'provider retained component set differs')
        retained=[retained_task_profile_build(receipt.parent,check,captured[row['component']],row,
            identity['compiler_build'],capsule.completion_inputs) for row in check['components']]
        package=root/'task-provider-profile-package'
        cli('project','--kind','package','--component','app','--directory',package,cwd=directory,timeout=300)
        application_package=package/'apps/app';package_meta=json.loads((application_package/'application.json').read_text())
        package_proof=package_task_profile_provenance(application_package,package_meta,directory)
        original=directory/'.nex/build'/package_meta['build_key']
        images=json.loads((original/'compilation.json').read_text())['owned_images']
        require(sum(row['kind']=='runtime' for row in images)==1,'profile package closure has multiple runtimes')
        copied=root/'task-provider-profile-copied';copied.mkdir();shutil.copy2(original/'app',copied/'app');shutil.copytree(original/'images',copied/'images')
        shutil.rmtree(directory);loader_logs=[];raw_reports=[]
        previous={key:environment.pop(key,None) for key in ('NEX_PROFILE_OUTPUT','NEX_PROFILE_EVENTS','NEX_TRACY','NEX_RESOURCE_DIR',
            'DYLD_PRINT_LIBRARIES','DYLD_PRINT_TO_FILE','LD_DEBUG','LD_DEBUG_OUTPUT')}
        try:
            environment.update(NEX_PROFILE_EVENTS='0',NEX_TRACY='0',NEX_RESOURCE_DIR='/absent')
            loader_key='DYLD_PRINT_LIBRARIES' if platform.system()=='Darwin' else 'LD_DEBUG'
            environment[loader_key]='1' if platform.system()=='Darwin' else 'libs'
            for label,executable in (('copied',copied/'app'),('package',application_package/'bin/app')):
                raw_path=root/('task-provider-profile-'+label+'-runtime.json');environment['NEX_PROFILE_OUTPUT']=str(raw_path)
                require(run([executable],cwd='/')==output,'source-deleted profile closure output differs')
                loader=Path(report['commands'][-1]['stderr']);loader_logs.append(str(loader));lines=loader.read_text().splitlines()
                if platform.system()=='Linux':lines=[line.split('calling init:',1)[1].strip() for line in lines if 'calling init:' in line]
                require(all(sum(line.rstrip().endswith('/'+Path(image['path']).name) for line in lines)==1 for image in images),
                        'source-deleted profile closure did not map each image exactly once')
                runtime={Path(match).name for line in lines for match in re.findall(r'\S*libnex_runtime_[0-9a-f]{64}\.(?:dylib|so)',line)}
                require(runtime=={Path(image['path']).name for image in images if image['kind']=='runtime'},
                        'source-deleted provider profile mapped a different runtime')
                raw=json.loads(raw_path.read_text());functions={row['name']:row for row in raw['functions']}
                require(raw['schema']=='nex.profile-runtime/3' and raw['build']['build_key']==package_meta['build_key'] and
                        len(functions)==len(raw['functions']) and set(functions)==set(expected) and
                        all(functions[name]['calls']==count for name,count in expected.items()) and
                        raw['completeness']['aggregates'] is True and raw['completeness']['memory'] is True and
                        all(row['live']==0 for row in raw['memory']),'source-deleted raw3 profile differs')
                raw_reports.append(str(raw_path))
        finally:
            for key,value in previous.items():
                environment.pop(key,None)
                if value is not None:environment[key]=value
        replay=cli('task',receipt,'--kind','replay','--directory',root/'task-provider-profile-replay',timeout=600)
        repeated=json.loads(Path(replay['output']).read_text());again,=repeated['checks']
        require(replay['ok'] and repeated['programs']==full['programs'] and again['status']=='passed',
                'source-deleted provider profile replay differs')
        observed=json.loads((Path(replay['output']).parent/again['receipt']).read_text());checked(observed['response'],False)
        report['evidence']['task_provider_profiling']={name:True for name in (
            'descriptor','native_reference','exact_source_calls','zero_provider_generic','physical_owners',
            'defined_registry_accessors','one_runtime','managed_cleanup','event_only_completeness','root_limits',
            'unused_read_excluded','warm_cache','measured_retained_completion6','raw_package_provenance',
            'source_deleted_replay','copied_profile_without_resources','source_deleted_package_profile')}
        report['evidence']['task_provider_profiling'].update(receipt=str(receipt),replay=replay['output'],
            source_oracle=expected,retained=retained,package_provenance=package_proof,loader_logs=loader_logs,command_file_sha256=command_file_sha256,
            raw_reports=raw_reports,physical_file_retirement_claim=False)

    def graph_snapshot_recovery():
        original = root / 'snapshot-original'
        original.mkdir()
        (original / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1',
            'language': report['doctor']['language'], 'entry': 'main.nex'}))
        source = original / 'main.nex'
        source.write_text('module sdk_snapshot;fn value()->i64{return 41;}'
            'fn main()->unit!{io}{print(value());}'
            'test fn retains_value()->unit{assert(value()>=41);}')
        first = cli('check', cwd=original)['revision']
        patch = original / 'patch.json'
        patch.write_text(json.dumps({'expected_revision': first, 'replacements': [
            {'name': 'value', 'source': 'fn value()->i64{return 42;}'}]}))
        second = cli('apply', '--patch', patch, cwd=original)['revision']
        graph = cli('graph', cwd=original)
        changes = cli('changes', cwd=original)
        source.unlink()
        def rows(project):
            with sqlite3.connect(project / '.nex/graph.db') as database:
                names = [name for name, in database.execute("SELECT name FROM sqlite_schema WHERE type='table'")]
                return {name: sorted(database.execute('SELECT * FROM "' + name.replace('"', '""') + '"').fetchall(), key=repr)
                        for name in names}
        before = rows(original)
        archive = root / 'graph-snapshot'
        captured = cli('snapshot', '--directory', archive, cwd=original)
        require(rows(original) == before and captured['source_unchanged'], 'snapshot changed original graph rows')
        require(not (archive / 'graph.db-wal').exists() and not (archive / 'graph.db-shm').exists(),
                'snapshot depends on SQLite sidecar files')
        manifest = json.loads((archive / 'snapshot.json').read_text())
        digest = hashlib.sha256((archive / 'graph.db').read_bytes()).hexdigest()
        require(manifest['database']['sha256'] == captured['database_sha256'] == digest,
                'snapshot manifest differs from database bytes')
        shutil.rmtree(original)
        moved = root / 'moved-graph-snapshot'
        archive.rename(moved)
        recovered = root / 'snapshot-recovered'
        result = cli('recover', moved, '--directory', recovered)
        require(rows(recovered) == before and not result['materialized'] and
                result['namespace'] == changes['namespace'], 'recovery changed database rows or namespace')
        require(cli('recover', moved, '--directory', recovered, expected_success=False)['code'] == 'E_EXISTS' and
                rows(recovered) == before, 'existing recovered project was overwritten')
        require(cli('graph', cwd=recovered)['nodes'] == graph['nodes'] and
                cli('changes', cwd=recovered) == changes, 'recovery lost local IDs or change journal')
        require(cli('run', '--revision', first, cwd=recovered)['stdout'] == '41\n' and
                cli('eval', '--revision', second, cwd=recovered)['stdout'] == '42\n' and
                cli('run', '--revision', 'HEAD', cwd=recovered)['stdout'] == '42\n',
                'recovered native/reference archives disagree')
        cli('test', '--revision', 'HEAD', cwd=recovered)
        cli('test', '--revision', 'HEAD', '--target', 'web', cwd=recovered)
        require(not (recovered / 'main.nex').exists() and rows(recovered) == before,
                'archived execution materialized sources or changed retained graph rows')
        report['evidence']['graph_snapshot'] = {'before': first, 'head': second,
            'namespace': changes['namespace'], 'database_sha256': digest,
            'tables': len(before), 'all_rows_preserved': True, 'local_ids_preserved': True,
            'change_journal_preserved': True, 'original_project_deleted': True,
            'snapshot_moved': True, 'materialized': False, 'existing_target_rejected': True,
            'native_reference_typescript': True, 'external_artifacts_included': False}

    def project_version_boundaries():
        project = root / 'project-version-boundaries'
        project.mkdir()
        manifest = project / 'nex.json'
        source = project / 'main.nex'
        source.write_text('module sdk_version_boundary;fn main()->unit{}')
        config = {'schema': 'nex.project/1', 'language': '0.14', 'entry': 'main.nex'}
        manifest.write_text(json.dumps(config))
        require(cli('check', cwd=project, expected_success=False)['code'] == 'E_LANGUAGE_VERSION' and
                not (project / '.nex').exists(), 'old root language created/upgraded graph state')
        library = project / 'library'
        library.mkdir()
        library_manifest = library / 'nex.json'
        library_manifest.write_text(json.dumps({'schema': 'nex.project/1', 'language': '0.14'}))
        (library / 'value.nex').write_text('module sdk_version_library;pub fn answer()->i64{return 42;}')
        source.write_text('module sdk_version_boundary;import "numbers/value.nex" as n;'
            'fn main()->unit!{io}{print(n::answer());}test fn accepted()->unit{assert(n::answer()==42);}')
        config.update(language=report['doctor']['language'], libraries={'numbers': './library'})
        manifest.write_text(json.dumps(config))
        require(cli('check', cwd=project, expected_success=False)['code'] == 'E_LANGUAGE_VERSION' and
                cli('history', cwd=project)['head'] == '', 'old library was silently adopted')
        library_manifest.write_text(json.dumps({'schema': 'nex.project/1', 'language': report['doctor']['language']}))
        revision = cli('check', cwd=project)['revision']
        changes = cli('changes', cwd=project)
        config['language'] = '0.14'
        manifest.write_text(json.dumps(config))
        require(cli('check', cwd=project, expected_success=False)['code'] == 'E_LANGUAGE_VERSION',
                'stale physical root declaration was ignored')
        require(cli('eval', '--revision', revision, cwd=project)['stdout'] == '42\n' and
                cli('run', '--revision', 'HEAD', cwd=project)['stdout'] == '42\n' and
                cli('changes', cwd=project) == changes, 'archived execution used stale physical metadata')
        exported = root / 'current-version-export'
        cli('export', '--revision', revision, '--directory', exported, cwd=project)
        require(json.loads((exported / 'nex.json').read_text())['language'] == report['doctor']['language'] and
                cli('check', cwd=exported)['revision'] == revision, 'archive export did not create current source projection')
        report['evidence']['project_versions'] = {'revision': revision,
            'old_root_rejected_before_store': True, 'old_reachable_library_rejected': True,
            'current_library_accepted': True, 'stale_physical_manifest_rejected': True,
            'archived_native_reference_execution': True, 'journal_preserved': True,
            'current_export_checked': True}

    def frontend_diagnostics():
        project = root / 'frontend-error-context'
        project.mkdir()
        (project / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1',
            'language': report['doctor']['language'], 'entry': 'main.nex'}))
        source = project / 'main.nex'
        original = ('module sdk_frontend;fn value()->i64{return 41;}'
            'fn main()->unit!{io}{print(value());}test fn retained()->unit{assert(value()>=41);}')
        source.write_text(original)
        before = cli('check', cwd=project)['revision']
        changes = cli('changes', cwd=project)
        patch = project / 'candidate.json'
        request = {'expected_revision': before, 'replacements': [
            {'name': 'value', 'source': 'fn value()->i64{return "bad";}'}]}
        patch.write_text(json.dumps(request))
        error = cli('apply', '--patch', patch, cwd=project, expected_success=False)
        context = error.get('frontend', {})
        require(error['code'] == 'E_TYPE' and context.get('schema') == 'nex.frontend-diagnostic/1' and
                context.get('phase') == 'check' and context.get('input_kind') == 'project' and
                context.get('source_inputs_complete') is True and
                'return "bad"' in context['preview']['data'], 'failed candidate context refers to wrong input')
        require(source.read_text() == original and cli('changes', cwd=project) == changes and
                'revision' not in error and 'operation_id' not in error,
                'failed candidate changed source/history or fabricated graph identity')
        require(cli('apply', '--patch', patch, cwd=project, expected_success=False)['frontend']['id'] == context['id'],
                'identical failed input changed diagnostic identity')
        session = cli('debug', cwd=project)
        identity = json.loads(Path(session['manifest']).read_text())
        frame = {'schema': 'nex.debug-frame/1', 'language': report['doctor']['language'],
            'revision': identity['revision'], 'build_key': identity['build_key'],
            'function': 'sdk_frontend::value',
            'stop': {'process_id': '1', 'thread_id': '2', 'frame_id': 0, 'stop_id': '1'},
            'bindings': [], 'truncated': False}
        frame_file = project / 'frame.json'
        frame_file.write_text(json.dumps(frame))
        watched = cli('inspect', frame_file, '--manifest', session['manifest'], '--expression', '1 + true',
                      cwd=project, expected_success=False)
        require(watched['frontend']['input_kind'] == 'expression' and
                watched['frontend']['phase'] == 'check' and
                watched['frontend']['watch']['revision'] == before and
                watched['frontend']['watch']['build_key'] == identity['build_key'],
                'static watch error lost its source/frame identity')
        raw = b'module bad;\n\xff'
        source.write_bytes(raw)
        invalid = cli('check', cwd=project, expected_success=False)
        require(invalid['code'] == 'E_UTF8' and invalid['frontend']['source']['utf8'] is False and
                invalid['frontend']['preview']['encoding'] == 'base64' and
                base64.b64decode(invalid['frontend']['preview']['data'], validate=True) == raw and
                cli('changes', cwd=project) == changes, 'invalid UTF-8 source context is lossy or mutates history')
        source.write_text(original)
        request['replacements'][0]['source'] = 'fn value()->i64{return 42;}'
        patch.write_text(json.dumps(request))
        after = cli('apply', '--patch', patch, cwd=project)['revision']
        require(cli('run', '--revision', after, cwd=project)['stdout'] == '42\n' and source.read_text() == original,
                'repaired candidate failed archived execution or overwrote physical source')
        report['evidence']['frontend_diagnostics'] = {'before': before, 'after': after,
            'diagnostic_id': context['id'], 'candidate_source_hash': context['source']['hash'],
            'source_inputs_hash': context['source_inputs_hash'], 'captured_uncommitted_candidate': True,
            'physical_source_preserved': True, 'failed_transition_absent': True,
            'repeatable_error_identity': True, 'invalid_utf8_lossless': True,
            'static_watch_supplied_frame': True, 'watch_frame_hash': watched['frontend']['watch']['frame_hash'],
            'repaired_archived_native_execution': True}

    def graph_queries():
        project = root / 'graph-query-workflow'
        project.mkdir()
        (project / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1',
            'language': report['doctor']['language'], 'entry': 'main.nex'}))
        source = project / 'main.nex'
        original = ('module sdk_query;fn leaf()->i64{return 40;}'
            'fn middle()->i64{return leaf()+2;}fn main()->unit!{io}{print(middle());}')
        source.write_text(original)
        revision = cli('check', cwd=project)['revision']
        changes = cli('changes', cwd=project)
        found = cli('search', '--query', 'leaf', '--field', 'symbol', cwd=project)
        require(found['revision'] == revision and len(found['nodes']) == 1 and
                found['nodes'][0]['symbol'] == 'sdk_query::leaf', 'query did not discover exact checked declaration')
        graph = cli('subgraph', '--symbol', 'main', '--depth', '2', cwd=project)
        require({n['symbol'] for n in graph['nodes']} ==
                {'sdk_query::main', 'sdk_query::middle', 'sdk_query::leaf'} and
                graph['edge_page']['total'] == 2 and graph['depth_limited'] is False,
                'query dependency radius differs from the checked program')
        reverse = cli('subgraph', '--symbol', 'leaf', '--direction', 'dependents', '--depth', '2', cwd=project)
        require('sdk_query::main' in {n['symbol'] for n in reverse['nodes']} and
                any(e['source']['symbol'] == 'sdk_query::middle' and
                    e['target']['symbol'] == 'sdk_query::leaf' for e in reverse['edges']),
                'reverse query changed edge direction or lost incoming references')
        page = cli('search', '--query', '::', '--field', 'symbol', '--limit', '1', cwd=project)
        seen = list(page['nodes'])
        identity = page['query_hash']
        while page['page']['next_offset'] is not None:
            page = cli('search', '--query', '::', '--field', 'symbol', '--limit', '1',
                '--offset', str(page['page']['next_offset']), '--revision', revision, cwd=project)
            require(page['query_hash'] == identity, 'query pages mixed selection identities')
            seen.extend(page['nodes'])
        require(len(seen) == 3 and len({n['id'] for n in seen}) == 3, 'query cursor lost or duplicated declarations')
        context = cli('context', '--symbol', found['nodes'][0]['symbol'], '--revision', revision, cwd=project)
        require('return 40' in context['source'], 'query followup read another declaration')
        source.unlink()
        (project / 'nex.json').write_text(json.dumps({'language': '0.14', 'entry': 'main.nex'}))
        require(cli('search', '--query', 'leaf', '--field', 'symbol', '--revision', revision, cwd=project) == found and
                cli('subgraph', '--symbol', 'main', '--depth', '2', '--revision', revision, cwd=project) == graph and
                cli('changes', cwd=project) == changes, 'query depended on physical source or changed graph history')
        patch = project / 'discovered-repair.json'
        patch.write_text(json.dumps({'expected_revision': revision, 'expected_source_hash': found['source_hash'],
            'replacements': [{'name': found['nodes'][0]['symbol'], 'source': 'fn leaf()->i64{return 41;}'}]}))
        after = cli('apply', '--patch', patch, cwd=project)['revision']
        require(cli('eval', '--revision', after, cwd=project)['stdout'] == '43\n' and
                cli('run', '--revision', after, cwd=project)['stdout'] == '43\n' and not source.exists(),
                'discovered guarded repair failed archived native/reference execution')
        report['evidence']['graph_queries'] = {'before': revision, 'after': after,
            'namespace': found['namespace'], 'node_id': found['nodes'][0]['id'],
            'search_query_hash': found['query_hash'], 'subgraph_query_hash': graph['query_hash'],
            'exact_archived_source_hash': found['source_hash'], 'source_deleted_lookup': True,
            'stale_physical_metadata_ignored': True, 'incoming_edges_checked': True,
            'stable_complete_query_pages': True, 'queries_preserve_history': True,
            'guarded_repair_from_discovery': True, 'native_reference_after_repair': True}

    def traits():
        require({'associated_value_types','constructor_kinds','static_dispatch'} <= set(cli('describe').get('trait_features',[])),'SDK lacks source trait capabilities')
        project = root / 'trait-workflow'; project.mkdir()
        (project / 'nex.json').write_text(json.dumps({'schema':'nex.project/1',
            'language':report['doctor']['language'],'entry':'main.nex'}))
        for filename, expected in [('main.nex','🧠\n'),('mapping.nex','[2,3]\n')]:
            source = project / filename
            source.write_text((resources / 'examples/traits' / filename).read_text())
            require(cli('eval',source,cwd=project)['stdout']==expected,'trait reference result differs')
            require(cli('run',source,cwd=project)['stdout']==expected,'trait native result differs')
            cli('test',source,cwd=project);cli('test',source,'--target','web',cwd=project)
        source = project / 'main.nex'
        source.write_text((resources / 'examples/traits/watch.nex').read_text())
        revision = cli('check',cwd=project)['revision'];changes=cli('changes',cwd=project)
        session = cli('debug',cwd=project);identity=json.loads(Path(session['manifest']).read_text())
        frame={'schema':'nex.debug-frame/1','language':report['doctor']['language'],
            'revision':revision,'build_key':identity['build_key'],'function':'trait_watch::observe<list>',
            'stop':{'process_id':'1','thread_id':'2','frame_id':0,'stop_id':'1'},
            'bindings':[{'name':'value','type':'list<i64>','value':['41']}],'truncated':False}
        framefile=project/'supplied-frame.json';framefile.write_text(json.dumps(frame))
        expression='Mapper<F>::map<i64,i64>(value,increase)'
        require(cli('inspect',framefile,'--manifest',session['manifest'],'--expression',expression,cwd=project)['value']==['42'],'trait constructor watch failed')
        live=None
        if args.live:
            projected=identity['sources'][0]['projection']
            line=next(i+1 for i,text in enumerate(source.read_text().splitlines()) if '// TRAIT_STOP' in text)
            script,recording=project/'record_trait_frame.py',project/'native-recording.json'
            script.write_text('''import json,lldb
def __lldb_init_module(debugger,_):
 debugger.SetAsync(False);debugger.HandleCommand('settings set target.disable-aslr false')
 target=debugger.GetSelectedTarget();target.BreakpointCreateByLocation(SOURCE,LINE)
 process=target.LaunchSimple(None,None,None)
 def command(text):
  result=lldb.SBCommandReturnObject();debugger.GetCommandInterpreter().HandleCommand(text,result)
  assert result.Succeeded(),(text,result.GetOutput(),result.GetError())
  return json.loads(result.GetOutput())
 try:
  assert process.GetState()==lldb.eStateStopped
  frame=process.GetSelectedThread().GetSelectedFrame();stop=process.GetStopID();handle=frame.FindVariable('value').GetValueAsUnsigned()
  values={'value':command('nex-eval Mapper<F>::map<i64,i64>(value,increase)'),
   'identity':command('nex-eval identity<F<i64>>(value)'),
   'snapshot':command('nex-frame Mapper<F>::map<i64,i64>(value,increase)')}
  assert process.GetState()==lldb.eStateStopped and process.GetStopID()==stop
  assert frame.FindVariable('value').GetValueAsUnsigned()==handle
  values['unchanged_stop_and_handle']=True
  with open(RECORDING,'w') as output:json.dump(values,output)
  process.Continue();assert process.GetState()==lldb.eStateExited and process.GetExitStatus()==0
 finally:
  if process.GetState() not in (lldb.eStateExited,lldb.eStateInvalid):process.Kill()
'''.replace('SOURCE',repr(projected)).replace('LINE',str(line)).replace('RECORDING',repr(str(recording))))
            run([compiler,'debug','--revision',revision,'--','--no-lldbinit','--batch','-o',
                 lldb_script_import(script)],cwd=project,timeout=180)
            require(recording.is_file(),'live constructor trait frame was not recorded')
            live=json.loads(recording.read_text());require(live['value']['value']==['42'] and live['identity']['value']==['41'] and live['unchanged_stop_and_handle'],'live constructor trait watch differs or changed stop')
            framefile=project/'native-frame.json';framefile.write_text(json.dumps(live['snapshot']))
        source.unlink()
        require(cli('inspect',framefile,'--manifest',session['manifest'],'--expression',expression,cwd=project)['value']==['42'],'source-deleted trait frame replay failed')
        require(cli('changes',cwd=project)==changes,'trait watch changed graph history')
        legacy=project/'legacy';legacy.mkdir();(legacy/'.nex').mkdir()
        (legacy/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.15','entry':'main.nex'}))
        metadata=json.loads((resources/'examples/traits/legacy-0.15.json').read_text());sql=(resources/'examples/traits/legacy-0.15.sql').read_bytes()
        require(hashlib.sha256(sql).hexdigest()==metadata['sql_sha256'],'historical trait fixture hash differs')
        database=legacy/'.nex/graph.db'
        with sqlite3.connect(database) as db:db.executescript(sql.decode())
        def rows():
            with sqlite3.connect(database) as db:
                names=[name for name, in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")]
                return {name:set(db.execute('SELECT * FROM "'+name.replace('"','""')+'"').fetchall()) for name in names}
        before=rows();migrated=cli('migrate','--revision',metadata['revision'],cwd=legacy)
        require(migrated['revision']!=metadata['revision'],'migration reused the old language identity')
        after=rows()
        require(all(old<=after[name] for name,old in before.items() if name!='head'),'migration rewrote historical rows')
        require(cli('eval','--revision','HEAD',cwd=legacy)['stdout']==metadata['stdout'],'migrated contextual names changed meaning')
        api_project=project/'api-models'
        shutil.copytree(resources/'examples/traits/api',api_project)
        cli('test',cwd=api_project)
        generated=cli('api','--directory',api_project/'generated',cwd=api_project)
        client=Path(generated['client_entry']).parent
        consumer=client/'consumer.nex';shutil.copyfile(api_project/'client.nex',consumer)
        for path in client.rglob('*.nex'):
            require('NEX_SERVER_TRAIT_EXAMPLE_SENTINEL' not in path.read_text(),
                    'server trait body entered generated client')
        client_native=cli('test',consumer,cwd=client)
        client_web=cli('test',consumer,'--target','web',cwd=client)
        required_test='traits::api::consumer::values'
        require(required_test in {test['name'] for test in client_native['tests']} and
                required_test in {test['name'] for test in client_web['tests']},
                'generated trait API consumer was not tested')
        server_build=cli('build',generated['server_entry'],'--target','server',cwd=api_project,timeout=180)
        report['evidence']['traits']={'revision':revision,'build_key':identity['build_key'],
            'native_typescript_reference':True,'source_deleted_watch_replay':True,
            'live_constructor_trait_frame':bool(live),'unchanged_stop_and_handle':bool(live),
            'genuine015_fixture':True,'old_revision':metadata['revision'],'migrated_revision':migrated['revision'],
            'old_non_head_rows_retained':True,
            'api_models':{'generated_revision':generated['revision'],'native_typescript_consumer':True,
                'real_client_shared_trait_method':True,'excluded_server_trait_body':True,
                'server_native_build':server_build['executable']}}

    def string_ranges():
        project = root / 'string-range-workflow'
        project.mkdir()
        (project / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1',
            'language': report['doctor']['language'], 'entry': 'main.nex'}))
        source = project / 'main.nex'
        source.write_text((resources / 'examples/debugging/strings.nex').read_text())
        revision = cli('check', cwd=project)['revision']
        changes = cli('changes', cwd=project)
        session = cli('debug', cwd=project)
        identity = json.loads(Path(session['manifest']).read_text())
        frame = {'schema': 'nex.debug-frame/2', 'language': report['doctor']['language'],
            'revision': revision, 'build_key': identity['build_key'], 'function': 'string_debug::observe',
            'stop': {'process_id': '1', 'thread_id': '2', 'frame_id': 0, 'stop_id': '1'},
            'bindings': [{'name': 'text', 'type': 'str', 'unavailable': 'whole string not captured'}],
            'truncated': False, 'captures': [
                {'binding': 'text', 'path': [], 'kind': 'shape', 'value': {'length': '2097152'}},
                {'binding': 'text', 'path': [], 'kind': 'text_range', 'start': '2097148', 'count': '4',
                 'value': 'A🌍\u0000λ'}]}
        # The first frame is supplied data; an optional live recording below has
        # separately verified process/stop identity and actual memory reads.
        frame['captures'][-1]['value'] = 'A🌍' + chr(0) + 'λ'
        framefile = project / 'supplied-frame.json'
        framefile.write_text(json.dumps(frame))
        length = cli('inspect', framefile, '--manifest', session['manifest'], '--expression', 'len(text)', cwd=project)
        window = cli('inspect', framefile, '--manifest', session['manifest'], '--expression', 'slice(text,len(text)-4,4)', cwd=project)
        last = cli('inspect', framefile, '--manifest', session['manifest'], '--expression', 'text[len(text)-1]', cwd=project)
        require(length['value'] == '2097152' and window['value'] == 'A🌍' + chr(0) + 'λ' and last['value'] == 'λ',
                'supplied string windows lost Unicode scalar semantics or contained-range reuse')
        demand = cli('inspect', framefile, '--manifest', session['manifest'], '--expression', 'text[0]', '--kind', 'demand', cwd=project)
        require(demand['request']['kind'] == 'text_range' and demand['request']['start'] == '0' and
                demand['request']['count'] == '1', 'missing string range became a fabricated whole/empty value')
        live = None
        if args.live:
            projected = identity['sources'][0]['projection']
            line = next(i+1 for i, text in enumerate(source.read_text().splitlines()) if '// STRING_STOP' in text)
            script, recording = project / 'record_string_range.py', project / 'native-recording.json'
            script.write_text('''import json,lldb

def __lldb_init_module(debugger,_):
 debugger.SetAsync(False);debugger.HandleCommand('settings set target.disable-aslr false')
 target=debugger.GetSelectedTarget();target.BreakpointCreateByLocation(SOURCE,LINE)
 process=target.LaunchSimple(None,None,None)
 def command(text):
  result=lldb.SBCommandReturnObject();debugger.GetCommandInterpreter().HandleCommand(text,result)
  assert result.Succeeded(),(text,result.GetOutput(),result.GetError())
  return json.loads(result.GetOutput())
 try:
  assert process.GetState()==lldb.eStateStopped
  stop=process.GetStopID();handle=process.GetSelectedThread().GetSelectedFrame().FindVariable('text').GetValueAsUnsigned()
  values={'length':command('nex-eval len(text)'), 'range':command('nex-eval slice(text,len(text)-4,4)'),
   'snapshot':command('nex-frame slice(text,len(text)-4,4)')}
  assert process.GetState()==lldb.eStateStopped and process.GetStopID()==stop
  assert process.GetSelectedThread().GetSelectedFrame().FindVariable('text').GetValueAsUnsigned()==handle
  values['unchanged_stop_and_handle']=True
  with open(RECORDING,'w') as output:json.dump(values,output)
  process.Continue();assert process.GetState()==lldb.eStateExited and process.GetExitStatus()==0
 finally:
  if process.GetState() not in (lldb.eStateExited,lldb.eStateInvalid):process.Kill()
'''.replace('SOURCE', repr(projected)).replace('LINE', str(line)).replace('RECORDING', repr(str(recording))))
            run([compiler, 'debug', '--revision', revision, '--', '--no-lldbinit', '--batch', '-o',
                 lldb_script_import(script)], cwd=project, timeout=180)
            require(recording.is_file(), 'live string provider did not retain a recording')
            live = json.loads(recording.read_text())
            require(live['length']['value'] == '2097152' and live['range']['value'] == 'A🌍' + chr(0) + 'λ' and
                    live['unchanged_stop_and_handle'] is True and
                    any(c['kind'] == 'text_range' for c in live['snapshot']['captures']),
                    'live string scan/range changed the stop or returned another payload')
            (project / 'native-frame.json').write_text(json.dumps(live['snapshot']))
        source.unlink()
        replay_file = project / 'native-frame.json' if live else framefile
        replay = cli('inspect', replay_file, '--manifest', session['manifest'], '--expression', 'text[len(text)-1]', cwd=project)
        require(replay['value'] == 'λ' and cli('changes', cwd=project) == changes,
                'string snapshot replay depended on physical source or changed graph history')
        report['evidence']['string_ranges'] = {'revision': revision, 'build_key': identity['build_key'],
            'supplied_frame_scalar_length': length['value'], 'contained_range_replay': True,
            'missing_range_is_explicit_demand': True, 'physical_source_deleted': True, 'history_preserved': True,
            'live_native_streaming': bool(live), 'live_unchanged_stop_and_handle': bool(live),
            'native_utf8_bytes': 4194304 if live else None,
            'native_snapshot': str(replay_file) if live else None,
            'supplied_frame': str(framefile), 'replayed_stop': replay['stop']}

    def core_reports():
        directory = root / 'core-reports'
        directory.mkdir()
        source = directory / 'main.nex'
        source.write_text('''module sdk_core;
fn observe(value:i64,text:str,items:list<i64>)->unit !{io}{
 let answer:i64=value+items[1];
 print(answer);
}
fn main()->unit !{io}{observe(40,"Я🧠",[1,2,3]);}
''')
        (directory / 'nex.json').write_text(json.dumps({'language': report['doctor']['language'], 'entry': 'main.nex'}))
        session = cli('debug', '--kind', 'nex-dap', cwd=directory)
        core = directory / 'process.core'
        core.write_bytes(b'x')
        rejected = cli('core', core, '--manifest', session['manifest'],
                       cwd=directory, expected_success=False)
        require(rejected['code'] == 'E_CORE_INPUT', 'core reader accepted a truncated core')
        evidence = {'retained_build': session['manifest'], 'truncated_core_rejected': True,
                    'actual_core_read': False, 'actual_capsule_read': False}
        malformed = directory / 'invalid-capsule'
        malformed.mkdir()
        (malformed / 'capsule.json').write_text('{}')
        rejected = cli('core', '--capsule', malformed, cwd=directory, expected_success=False)
        require(rejected['code'] == 'E_CORE_CAPSULE', 'installed capsule helper accepted an invalid receipt')
        evidence['capsule_helper_input_rejected'] = True
        if args.live:
            core.unlink()
            captured = run([compiler, 'debug', '--', '--no-lldbinit', '--batch',
                '-o', 'settings set target.disable-aslr false',
                '-o', 'breakpoint set --file source.nex --line 4', '-o', 'run',
                '-o', 'process save-core --style modified-memory ' + json.dumps(str(core), ensure_ascii=False),
                '-o', 'continue'], cwd=directory, timeout=90)
            require('exited with status = 0' in captured and core.is_file() and core.stat().st_size < 16*1024*1024,
                    'native core fixture did not stop/save/complete')
            digest = hashlib.sha256(core.read_bytes()).hexdigest()
            source.unlink()
            graph = directory / '.nex/graph.db'
            graph_before = graph.read_bytes()
            observed = cli('core', core, '--manifest', session['manifest'],
                           '--expression', 'text + str(items[1])', cwd=directory, timeout=120)
            require(observed['schema'] == 'nex.core-report/1' and observed['ok'] and
                    observed['watch']['value'] == 'Я🧠2' and observed['core']['sha256'] == digest and
                    observed['core']['unchanged'] and observed['stop_unchanged'] and
                    observed['build_completion_checked'] and not observed['inferior_execution'] and
                    observed['revision'] == session['revision'] and
                    observed['executable']['uuid'] == observed['frames'][observed['selected_frame']]['module_uuid'],
                    'read-only core report differs from the retained program')
            require(graph.read_bytes() == graph_before and not source.exists() and
                    hashlib.sha256(core.read_bytes()).hexdigest() == digest,
                    'core inspection changed source/graph/core bytes')
            evidence.update(actual_core_read=True, source_deleted=True, graph_unchanged=True,
                            exact_watch=observed['watch']['value'], report=observed)
            capsule = directory / 'capsule'
            exported = cli('core', core, '--manifest', session['manifest'], '--export', capsule,
                           '--expression', 'text + str(items[1])', cwd=directory, timeout=180)
            require(exported['schema'] == 'nex.core-capsule-export/1' and exported['read_after_export'],
                    'installed SDK did not validate a newly exported core capsule')
            original_program = Path(session['launch']['program'])
            original_program.parent.rename(directory / 'retained-original-build')
            moved = directory / 'moved capsule "quoted" \\ % `data` 🧠'
            capsule.rename(moved)
            require(not original_program.exists(), 'original core executable path still exists')
            capsule_report = cli('core', '--capsule', moved, '--expression', 'text + str(items[1])',
                                 cwd=directory, timeout=120)
            require(capsule_report['capsule']['inventory_checked'] and capsule_report['watch']['value'] == 'Я🧠2' and
                    capsule_report['revision'] == session['revision'] and capsule_report['core']['sha256'] == digest and
                    capsule_report['stop_unchanged'] and not capsule_report['inferior_execution'] and
                    graph.read_bytes() == graph_before and not source.exists(),
                    'moved core capsule lost its original values/build/graph identity')
            evidence.update(actual_capsule_read=True, original_executable_absent=True,
                            capsule_export=exported, capsule_report=capsule_report)
        report['evidence']['core_reports'] = evidence

    def foreign_boundary():
        directory = root / 'foreign-boundary'
        directory.mkdir()
        descriptor = cli('describe')['foreign_boundary']
        require(descriptor['source_support'] is True and descriptor['abi_version'] == 1,
                'source FFI requires the current checked C transport')
        c = directory / 'producer.c'
        c.write_text(r'''#include "nex_ffi.h"
#include <string.h>
nex_ffi_status producer(const nex_ffi_api_v1 *api,nex_ffi_call call,
    const nex_ffi_ref *args,uint64_t count,nex_ffi_ref *out,void *user) {
  uint8_t bytes[4],text[]={0xd0,0xaf,0,0xf0,0x9f,0xa7,0xa0};
  uint64_t n=0; nex_ffi_ref value=0; nex_ffi_status status; (void)user;
  if(count!=1 || api->abi_version!=1)return NEX_FFI_ARGUMENT;
  status=api->copy_bytes(call,args[0],0,bytes,4,&n);
  if(status || n!=4 || bytes[0]!=0 || bytes[1]!=255 || bytes[2]!=128 || bytes[3]!=1)return NEX_FFI_TYPE;
  status=api->make_string(call,text,sizeof(text),&value);memset(text,0,sizeof(text));
  if(status)return status;
  return api->make_success(call,value,out);
}
''')
        host = directory / 'host.cpp'
        host.write_text(r'''#include "nex_ffi_host.h"
#include <array>
#include <iostream>
extern "C" nex_ffi_status producer(const nex_ffi_api_v1*,nex_ffi_call,const nex_ffi_ref*,uint64_t,nex_ffi_ref*,void*);
int main() {
  std::array<uint8_t,4> data{0,255,128,1};
  std::vector<nexrt::Value> args{nexrt::Value(nexrt::bytes(nexrt::ByteBuffer::copy(data)))};
  auto value=nexrt::unwrap(nexrt::invokeForeign(producer,args));
  if(value.object->text!=std::string("\xd0\xaf\0\xf0\x9f\xa7\xa0",7))return 1;
  std::cout<<"C ABI OK\n";
}
''')
        runtime = resources / 'runtime'
        driver = report['doctor']['native_compiler']
        obj = directory / 'producer.o'
        executable = directory / 'host'
        run([driver, '-x', 'c', '-std=c11', '-I' + str(runtime), '-c', c, '-o', obj])
        run([driver, '-std=c++20', '-pthread', '-I' + str(runtime), host, obj,
             runtime / 'nex_ffi.cpp', runtime / 'nex_ffi_types.cpp', runtime / 'nex_ffi_resources.cpp', runtime / 'nex_external_resource.cpp', runtime / 'nex_resource_region.cpp', runtime / 'nex_resource_executor.cpp',
             runtime / 'nex_files.cpp', runtime / 'nex_json.cpp', '-o', executable])
        c.unlink(); host.unlink(); obj.unlink()
        original = environment['NEX_RESOURCE_DIR']
        try:
            environment['NEX_RESOURCE_DIR'] = str(root / 'absent-foreign-resources')
            require(run([executable]) == 'C ABI OK\n', 'independent installed C ABI example differs')
        finally:
            environment['NEX_RESOURCE_DIR'] = original
        report['evidence']['foreign_boundary'] = {'abi_version': 1, 'source_support': True,
            'c11_producer': True, 'cpp20_host': True, 'copied_utf8_and_bytes': True,
            'sources_deleted': True, 'standalone': str(executable),
            'runtime_inputs': {name: hashlib.sha256((runtime / name).read_bytes()).hexdigest()
                for name in ('nex_ffi.h', 'nex_ffi_host.h', 'nex_ffi.cpp', 'nex_ffi_types.h',
                             'nex_ffi_types.cpp', 'nex_ffi_resources.h', 'nex_ffi_resources.cpp', 'nex_external_resource.h', 'nex_resource_executor.h', 'nex_resource_region.h', 'nex_external_resource.cpp', 'nex_resource_region.cpp', 'nex_resource_executor.cpp', 'nex_resource.h', 'nex_files.cpp', 'nex_json.cpp')}}
        typed = directory / 'typed'
        typed.mkdir()
        for name in ('main.nex', 'producer.c', 'host.cpp'):
            shutil.copyfile(resources / 'examples/ffi' / name, typed / name)
        (typed / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1',
            'language': report['doctor']['language'], 'entry': 'main.nex'}))
        revision = cli('check', cwd=typed)['revision']
        contract = cli('ffi', '--symbol', 'ffi_example::contract', cwd=typed)
        contract_file = typed / 'signature.json'
        contract_file.write_text(json.dumps(contract))
        expected_typed = cli('eval', cwd=typed)['stdout']
        for profile in ('debug', 'release'):
            require(cli('run', '--profile', profile, cwd=typed)['stdout'] == expected_typed,
                    'typed C model native/reference output differs')
        cli('test', '--target', 'web', cwd=typed)
        typed_obj = typed / 'producer.o'
        typed_host = typed / 'host'
        run([driver, '-x', 'c', '-std=c11', '-I' + str(runtime), '-c', typed / 'producer.c', '-o', typed_obj])
        run([driver, '-std=c++20', '-pthread', '-I' + str(runtime), typed / 'host.cpp', typed_obj,
             runtime / 'nex_ffi.cpp', runtime / 'nex_ffi_types.cpp', runtime / 'nex_ffi_resources.cpp', runtime / 'nex_external_resource.cpp', runtime / 'nex_resource_region.cpp', runtime / 'nex_resource_executor.cpp',
             runtime / 'nex_files.cpp', runtime / 'nex_json.cpp', '-o', typed_host])
        for name in ('main.nex', 'producer.c', 'host.cpp', 'producer.o'):
            (typed / name).unlink()
        require(cli('ffi', '--revision', revision, '--symbol', 'ffi_example::contract', cwd=typed) == contract,
                'archived C value contract changed after source deletion')
        try:
            environment['NEX_RESOURCE_DIR'] = str(root / 'absent-typed-foreign-resources')
            require(run([typed_host, contract_file]) == expected_typed,
                    'independent typed C/NEX model output differs')
        finally:
            environment['NEX_RESOURCE_DIR'] = original
        report['evidence']['foreign_boundary']['typed_nominal'] = {
            'schema': contract['schema'], 'model_revision': revision,
            'contract_sha256': hashlib.sha256(contract_file.read_bytes()).hexdigest(),
            'checked_record_enum_result': True, 'source_deleted': True,
            'native_reference_typescript_model_agreement': True, 'standalone': str(typed_host)}
        loaded = directory / 'loaded'
        loaded.mkdir()
        bundle = loaded / 'bundle'
        bundle.mkdir()
        for name in ('producer.c', 'module.c', 'module_host.cpp', 'NOTICE'):
            shutil.copyfile(resources / 'examples/ffi' / name, loaded / name)
        canonical = json.dumps(contract, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
        signature_pin = hashlib.sha256(canonical.encode()).hexdigest()
        module = bundle / 'module'
        run([driver, '-x', 'c', '-std=c11', '-shared', '-fPIC', '-fvisibility=hidden',
             '-I' + str(runtime), '-DNEX_EXAMPLE_SIGNATURE_SHA256="' + signature_pin + '"',
             loaded / 'producer.c', loaded / 'module.c', '-o', module])
        shutil.copyfile(loaded / 'NOTICE', bundle / 'NOTICE')
        machine = {'aarch64': 'arm64', 'arm64': 'arm64', 'x86_64': 'x86_64', 'AMD64': 'x86_64'}[platform.machine()]
        host_platform = ('macos' if platform.system() == 'Darwin' else 'linux') + '-' + machine
        manifest = {'schema': 'nex.foreign-bundle/1', 'platform': host_platform, 'entry': 'module',
            'files': [{'path': name, 'sha256': hashlib.sha256((bundle / name).read_bytes()).hexdigest()}
                      for name in ('module', 'NOTICE')],
            'exports': {'contract': signature_pin}, 'notices': ['NOTICE']}
        (bundle / 'manifest.json').write_text(json.dumps(manifest))
        manifest_pin = hashlib.sha256((bundle / 'manifest.json').read_bytes()).hexdigest()
        module_host = loaded / 'host'
        run([driver, '-std=c++20', '-pthread', '-I' + str(runtime),
             '-I' + report['doctor']['native_openssl_include'], loaded / 'module_host.cpp',
             runtime / 'nex_ffi_loader.cpp', runtime / 'nex_ffi.cpp', runtime / 'nex_ffi_types.cpp', runtime / 'nex_ffi_resources.cpp', runtime / 'nex_external_resource.cpp', runtime / 'nex_resource_region.cpp', runtime / 'nex_resource_executor.cpp',
             runtime / 'nex_files.cpp', runtime / 'nex_json.cpp',
             *standalone_crypto_link(report['doctor']), '-o', module_host])
        for name in ('producer.c', 'module.c', 'module_host.cpp', 'NOTICE'):
            (loaded / name).unlink()
        try:
            environment['NEX_RESOURCE_DIR'] = str(root / 'absent-module-resources')
            require(run([module_host, bundle, manifest_pin, contract_file]) == expected_typed,
                    'loaded module/NEX model output differs')
        finally:
            environment['NEX_RESOURCE_DIR'] = original
        report['evidence']['foreign_boundary']['loaded_module'] = {
            'platform': host_platform, 'manifest_sha256': manifest_pin,
            'signature_sha256': signature_pin, 'c11_shared_module': True,
            'explicit_library_and_export_grant': True, 'source_deleted': True,
            'native_reference_typescript_model_agreement': True,
            'standalone': str(module_host), 'bundle': str(bundle),
            'runtime_inputs': {name: hashlib.sha256((runtime / name).read_bytes()).hexdigest()
                for name in ('nex_ffi_loader.cpp', 'nex_ffi_loader.h', 'nex_ffi_module.h', 'nex_resource.h')}}
        scoped_source = loaded / 'scoped_host.cpp'
        shutil.copyfile(resources / 'examples/ffi/scoped_host.cpp', scoped_source)
        host_file = loaded / 'host.json'
        binding_file = loaded / 'binding.json'
        host_file.write_text(json.dumps({'schema': 'nex.foreign-host/1', 'module_limit': 64,
            'libraries': {'example': {'directory': 'bundle', 'manifest_sha256': manifest_pin,
                                      'exports': ['contract']}}}))
        binding_file.write_text(json.dumps({'schema': 'nex.foreign-binding/1', 'library': 'example',
            'export': 'contract', 'manifest_sha256': manifest_pin, 'signature': contract}))
        scoped_host = loaded / 'scoped-host'
        run([driver, '-std=c++20', '-pthread', '-I' + str(runtime),
             '-I' + report['doctor']['native_openssl_include'], scoped_source,
             runtime / 'runtime.cpp', runtime / 'foreign_runtime.cpp', runtime / 'nex_foreign.cpp',
             runtime / 'nex_ffi_loader.cpp', runtime / 'nex_ffi.cpp', runtime / 'nex_ffi_types.cpp', runtime / 'nex_ffi_resources.cpp', runtime / 'nex_external_resource.cpp', runtime / 'nex_resource_region.cpp', runtime / 'nex_resource_executor.cpp',
             runtime / 'nex_files.cpp', runtime / 'nex_json.cpp',
             *standalone_crypto_link(report['doctor']), '-o', scoped_host])
        scoped_source.unlink()
        try:
            environment['NEX_RESOURCE_DIR'] = str(root / 'absent-scoped-foreign-resources')
            require(run([scoped_host, host_file, binding_file]) == expected_typed,
                    'scoped native value bridge/NEX model output differs')
        finally:
            environment['NEX_RESOURCE_DIR'] = original
        report['evidence']['foreign_boundary']['scoped_native_bridge'] = {
            'source_support': False, 'host_schema': 'nex.foreign-host/1',
            'binding_schema': 'nex.foreign-binding/1', 'real_request_scope': True,
            'native_managed_handle_bridge': True, 'sources_deleted': True,
            'matches_nex_model': True, 'standalone': str(scoped_host),
            'host_file': str(host_file), 'binding_file': str(binding_file),
            'runtime_inputs': {name: hashlib.sha256((runtime / name).read_bytes()).hexdigest()
                for name in ('nex_foreign.cpp', 'nex_foreign.h', 'foreign_runtime.cpp',
                             'nex_foreign_abi.h', 'runtime.cpp', 'nex_host.h')}}
        source = directory / 'source'
        source.mkdir()
        source_file = source / 'main.nex'
        source_file.write_text((resources / 'examples/ffi/source.nex.in').read_text().replace('@MANIFEST_SHA256@', manifest_pin))
        (source / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1',
            'language': report['doctor']['language'], 'entry': 'main.nex'}))
        source_revision = cli('check', cwd=source)['revision']
        require(cli('ffi', '--symbol', 'ffi_example::contract', cwd=source) == contract,
                'source declaration changed the value signature')
        require(cli('eval', '--foreign', host_file, cwd=source)['stdout'] == expected_typed,
                'source external interpreter output differs')
        for profile in ('debug', 'release'):
            require(cli('run', '--foreign', host_file, '--profile', profile, cwd=source)['stdout'] == expected_typed,
                    'source external native output differs')
        cli('test', '--foreign', host_file, cwd=source)
        cli('test', '--target', 'web', cwd=source)
        external = cli('build', '--profile', 'release', cwd=source)
        catalogue = cli('foreign', host_file, cwd=source)
        external_task = cli('task', source_file, '--kind', 'init', cwd=source)
        for check in external_task['checks']:
            if check['kind'] == 'test':
                check['foreign_hash'] = catalogue['hash']
        external_task_file = source / 'task.json'
        external_task_file.write_text(json.dumps(external_task))
        checked = cli('task', external_task_file, '--kind', 'check', '--foreign', host_file, cwd=source)
        accepted = cli('task', external_task_file, '--kind', 'run', '--task-hash', checked['task_hash'],
                       '--foreign', host_file, cwd=source)
        require(accepted['ok'] and accepted['foreign_catalogue']['hash'] == catalogue['hash'],
                'reviewed external task failed')
        source_file.unlink()
        external_task_file.unlink()
        require(cli('eval', '--revision', source_revision, '--foreign', host_file, cwd=source)['stdout'] == expected_typed,
                'source-deleted external interpreter replay differs')
        try:
            environment['NEX_RESOURCE_DIR'] = str(root / 'absent-source-foreign-resources')
            require(run([external['executable'], '--nex-foreign', host_file]) == expected_typed,
                    'standalone source external binary output differs')
        finally:
            environment['NEX_RESOURCE_DIR'] = original
        replayed = cli('task', accepted['output'], '--kind', 'replay', '--foreign', host_file, cwd=source)
        require(replayed['ok'] and replayed['task_hash'] == accepted['task_hash'],
                'source-deleted trusted external task replay differs')
        report['evidence']['foreign_boundary']['source_external'] = {
            'source_support': True, 'language': report['doctor']['language'],
            'revision': source_revision, 'interpreter_debug_release_agreement': True,
            'server_tests': True, 'portable_web_test': True, 'sources_deleted': True,
            'standalone': external['executable'], 'host_file': str(host_file),
            'reviewed_task': {'hash': checked['task_hash'], 'foreign_hash': catalogue['hash'],
                'receipt': accepted['output'], 'replay': replayed['output'],
                'source_deleted_trusted_replay': True}}
        package_bundle = directory / 'package-input-bundle'
        shutil.copytree(bundle, package_bundle)
        package_host = directory / 'package-host.json'
        package_host.write_text(json.dumps({'schema': 'nex.foreign-host/1', 'module_limit': 64,
            'libraries': {'example': {'directory': str(package_bundle), 'manifest_sha256': manifest_pin,
                                     'exports': ['contract']}}}))
        notice_components = [{'name': 'acceptance-module', 'version': 'fixture',
            'url': 'https://example.invalid/nex-sdk-acceptance', 'roots': [str(package_bundle)],
            'license_files': [str(package_bundle / 'NOTICE')]}]
        # Direct packaging can resolve installed metadata, but replay consumes
        # captured reviewed inputs and cannot inherit a command-line switch.
        notice_components = merge_notice_components(notice_components, extra_notices,
            external_crypto_components(sdk, report['doctor']['native_openssl_crypto'], extra_notices))
        package_flags = ['--dpkg-notices'] if platform.system() == 'Linux' else []
        package_notices = directory / 'package-notices.json'
        package_notices.write_text(json.dumps({'schema': 'nex.sdk-notices/1', 'components': notice_components}))
        package = directory / 'before-package'
        packaged = cli('package', '--revision', source_revision, '--foreign', package_host,
                       '--notices', package_notices, '--directory', package, *package_flags, cwd=source)
        manifest = json.loads((package / 'application.json').read_text())
        projection = manifest['foreign_projection']
        require(packaged['source_revision'] == source_revision and
                projection['source_revision'] == source_revision and
                projection['packaged_revision'] == packaged['revision'],
                'packaged foreign source projection differs from actual compiled revision')
        require(manifest['execution_verified'] is False, 'assembly must retain separate execution evidence')
        for name, record in manifest['files'].items():
            path = package / name
            if 'symlink' in record:
                require(path.is_symlink() and str(path.readlink()) == record['symlink'], 'packaged alias differs')
            else:
                require(hashlib.sha256(path.read_bytes()).hexdigest() == record['sha256'], 'packaged file hash differs')
        project = directory/'foreign-project'
        for name in ('core','app','licenses'):
            (project/name).mkdir(parents=True)
        (project/'core/main.nex').write_text((resources/'examples/ffi/source.nex.in').read_text().replace('@MANIFEST_SHA256@',manifest_pin))
        (project/'app/main.nex').write_text('''module packaged_consumer;
import "../core/main.nex" as c;
server fn main()->unit!{ffi,io}{print(encode_json(c::contract(unwrap(bytes([0,255,128,1])))));}
''')
        (project/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':report['doctor']['language'],'entry':'app/main.nex'}))
        (project/'nex.build.json').write_text(json.dumps({'schema':'nex.project-build/1','default_configuration':'release',
            'configurations':{'release':{'profile':'release'}},'components':{
                'core':{'kind':'shared_library','root':'core','entry':'core/main.nex','entry_function':'contract'},
                'app':{'kind':'executable','root':'app','entry':'app/main.nex','dependencies':{'core':'dynamic'}}}}))
        components = []
        for i, component in enumerate(notice_components):
            licenses = []
            for j, source_license in enumerate(component['license_files']):
                target = project/'licenses'/('%d-%d.txt' % (i,j))
                shutil.copyfile(source_license,target)
                licenses.append(str(target.relative_to(project)))
            components.append({**component,'license_files':licenses})
        (project/'notices.json').write_text(json.dumps({'schema':'nex.sdk-notices/1','components':components}))
        readonly = cli('project','--foreign',package_host,cwd=project)
        require(not readonly['external_tools_invoked'] and readonly['foreign_packaging']['applications']=={'app':{'example':['contract']}},
                'foreign project readonly selection differs')
        deployment = directory/'foreign-project-package'
        captured = cli('project','--kind','package','--foreign',package_host,'--notices','notices.json',
            '--directory',deployment,*package_flags,cwd=project,timeout=300)
        require(captured['foreign_projection']['source_files_modified'] is False and not (project/'.nex/graph.db').exists(),
                'project packaging modified its source or opened a graph')
        app_manifest=json.loads((deployment/'apps/app/application.json').read_text())
        require(sum(row.get('owned_image_kind')=='library' for row in app_manifest['files'].values())==1,
                'foreign project did not consume its actual shared provider')
        task=cli('task','nex.build.json','--kind','init','--component','app','--configuration','release',cwd=project)
        notice_pin=cli('task','notices.json','--kind','notices',cwd=project)['inputs_hash']
        package_catalogue=cli('foreign',package_host,cwd=project)
        task.update(checks=[{'id':'package','kind':'package','target':'native','program':'app','configuration':'release',
            'timeout_seconds':300,'foreign_hash':package_catalogue['hash'],'notices':'notices.json','notices_hash':notice_pin}],
            requirements=[{'id':'delivery','text':'Capture the actual checked foreign project package',
                'targets':['native'],'checks':['package'],'bindings':[{'program':'app','kind':'function','symbol':'packaged_consumer::main'}]}])
        (project/'task.json').write_text(json.dumps(task))
        cli('task','task.json','--kind','check','--foreign',package_host,cwd=project)
        task_run=cli('task','task.json','--kind','run','--foreign',package_host,'--directory',directory/'foreign-project-task',cwd=project,timeout=480)
        require(task_run['ok'],'installed foreign project package task failed')
        shutil.rmtree(project)
        task_replay=cli('task',task_run['output'],'--kind','replay','--foreign',package_host,
            '--directory',directory/'foreign-project-replayed',cwd=directory,timeout=480)
        require(task_replay['ok'],'source-deleted foreign project package task replay failed')
        shutil.rmtree(package_bundle)
        package_host.unlink()
        package_notices.unlink()
        moved_package = directory / 'moved-package'
        package.rename(moved_package)
        saved_environment = dict(environment)
        try:
            environment.clear()
            environment.update(PATH='/usr/bin:/bin', NEX_RESOURCE_DIR=str(root / 'absent-packaged-resources'))
            require(run([moved_package / 'bin/app'], cwd=moved_package) == expected_typed,
                    'independent packaged nominal foreign application differs')
            require(run([deployment/'apps/app/bin/app'],cwd=directory)==expected_typed,
                    'independent project shared foreign application differs')
            replay_receipt=Path(task_replay['output'])
            row=json.loads(replay_receipt.read_text())['checks'][0]
            require(run([replay_receipt.parent/row['package']/'apps/app/bin/app'],cwd=directory)==expected_typed,
                    'independent replayed project foreign application differs')
        finally:
            environment.clear()
            environment.update(saved_environment)
        report['evidence']['foreign_boundary']['source_external']['application_package'] = {
            'source_revision': source_revision, 'packaged_revision': packaged['revision'],
            'source_deleted': True, 'module_inputs_deleted': True, 'moved': True,
            'environment_without_sdk': True, 'exact_file_inventory': True,
            'nominal_contract_agreement': True, 'manifest': str(moved_package / 'application.json')}
        report['evidence']['foreign_boundary']['source_external']['project_package'] = {
            'actual_shared_provider':True,'task_package':True,'source_deleted_replay':True,
            'module_inputs_deleted':True,'environment_without_sdk':True,'nominal_contract_agreement':True,
            'manifest':str(deployment/'project.json'),'receipt':task_run['output'],'replay':task_replay['output']}

    def binary_values():
        directory = root / 'binary-values'
        directory.mkdir()
        shutil.copyfile(resources / 'examples/bytes.nex', directory / 'main.nex')
        (directory / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1',
            'language': report['doctor']['language'], 'entry': 'main.nex'}))
        revision = cli('check', cwd=directory)['revision']
        expected_binary = 'AP+AQQ==\nE_UTF8\n{"name":"raw","data":"AP+AQQ=="}\n'
        require(cli('eval', cwd=directory)['stdout'] == expected_binary, 'binary reference output differs')
        for profile in ('debug', 'release'):
            cli('test', '--profile', profile, cwd=directory)
            require(cli('run', '--profile', profile, cwd=directory)['stdout'] == expected_binary,
                    'binary native/reference output differs')
        cli('test', '--target', 'web', cwd=directory)
        built = cli('build', '--profile', 'release', cwd=directory)
        standalone = root / 'binary-standalone'
        shutil.copyfile(built['executable'], standalone); standalone.chmod(0o755)
        (directory / 'main.nex').unlink()
        require(cli('run', '--revision', revision, cwd=directory)['stdout'] == expected_binary,
                'binary archived revision failed after source deletion')
        unavailable = environment['NEX_RESOURCE_DIR']
        try:
            environment['NEX_RESOURCE_DIR'] = str(root / 'absent-resources')
            require(run([standalone]) == expected_binary, 'independent binary executable differs')
        finally:
            environment['NEX_RESOURCE_DIR'] = unavailable
        files = root / 'binary-files'; files.mkdir()
        (files / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1',
            'language': report['doctor']['language'], 'entry': 'main.nex'}))
        (files / 'main.nex').write_text('''module binary_file_handoff;
server fn main()->unit!{io,fs}{
 let value:bytes=unwrap(bytes([0,255,128,65]));
 assert(unwrap(file_write_bytes("octets.bin",value)));
 print(encode_base64(unwrap(file_read_bytes("octets.bin"))));
 print(error_code(file_read_text("octets.bin")));
}
''')
        data = root / 'binary data % 🧠'; data.mkdir()
        saved = {name: environment.get(name) for name in ('NEX_FILES_ROOT', 'NEX_FILES_WRITE')}
        try:
            environment.update(NEX_FILES_ROOT=str(data), NEX_FILES_WRITE='1')
            expected_file = 'AP+AQQ==\nE_UTF8\n'
            require(cli('eval', cwd=files)['stdout'] == expected_file, 'binary file reference differs')
            require(cli('run', cwd=files)['stdout'] == expected_file, 'binary file native differs')
            packaged = cli('package', '--directory', root / 'binary-file-application', cwd=files)
            manifest = json.loads(Path(packaged['manifest']).read_text())
            executable = Path(packaged['directory']) / 'bin/app'
            environment['NEX_RESOURCE_DIR'] = str(root / 'absent-resources')
            require(run([executable]) == expected_file and
                    (data / 'octets.bin').read_bytes() == bytes([0, 255, 128, 65]),
                    'independent binary file application changed octets')
            require(hashlib.sha256(executable.read_bytes()).hexdigest() == manifest['files']['bin/app']['sha256'],
                    'binary file executable differs from package inventory')
        finally:
            environment['NEX_RESOURCE_DIR'] = unavailable
            for name, value in saved.items():
                if value is None: environment.pop(name, None)
                else: environment[name] = value
        evidence = {'revision': revision, 'native_profiles': ['debug', 'release'], 'typescript': True,
                    'source_deleted_replay': True, 'standalone_without_resources': str(standalone),
                    'binary_file_package': str(executable), 'live_watch': False}
        if args.live:
            debug = root / 'binary-debug'; debug.mkdir()
            (debug / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1',
                'language': report['doctor']['language'], 'entry': 'main.nex'}))
            source = debug / 'main.nex'
            source.write_text('''module binary_debug_handoff;
fn observe(data:bytes)->unit!{io}{
 print(data[1]); // binary-sdk-stop
}
fn main()->unit!{io}{observe(unwrap(bytes([0,255,128,65])));}
''')
            session = cli('debug', '--kind', 'nex-dap', cwd=debug)
            manifest = json.loads(Path(session['manifest']).read_text())
            projected = manifest['sources'][0]['projection']
            line = next(i+1 for i, text in enumerate(source.read_text().splitlines()) if '// binary-sdk-stop' in text)
            source.unlink()
            client = DAP(session['adapter_command'], debug, environment)
            try:
                client.request('initialize', {'adapterID': 'nex', 'pathFormat': 'path', 'linesStartAt1': True})
                pending = client.send('launch', dict(session['launch'], disableASLR=False))
                client.event('initialized')
                client.request('setBreakpoints', {'source': {'path': projected}, 'breakpoints': [{'line': line}]})
                client.request('configurationDone'); client.response(pending)
                stopped = client.event('stopped')
                frame = client.request('stackTrace', {'threadId': stopped['threadId']})['stackFrames'][0]['id']
                value = client.request('evaluate', {'expression': 'data[1]', 'frameId': frame, 'context': 'watch'})
                require(value['nex']['value'] == '255', 'installed binary index watch differs')
                binary = client.request('evaluate', {'expression': 'data', 'frameId': frame, 'context': 'watch'})
                require(binary['type'] == 'bytes' and binary['indexedVariables'] == 4,
                        'installed byte watch lost its type or length')
                children = client.request('variables', {'variablesReference': binary['variablesReference'],
                    'start': 1, 'count': 2})['variables']
                require([(v['name'], v['value']) for v in children] == [('[1]', '255'), ('[2]', '128')],
                        'installed byte watch page differs')
                client.request('continue', {'threadId': stopped['threadId']})
                require(client.event('exited')['exitCode'] == 0, 'binary debuggee failed')
                evidence['live_watch'] = True
            finally:
                client.close()
        report['evidence']['binary_language'] = evidence

    def native_pages():
        descriptor=cli('describe')
        require('paged_native_indexed_roots' in descriptor['debug_features'] and
                descriptor['native_debug_pages']['page_items']==1000,
                'SDK lacks bounded native indexed pages')
        directory=root/'native-indexed-pages';directory.mkdir()
        source=directory/'main.nex'
        source.write_bytes((resources/'examples/debugging/pages.nex').read_bytes())
        (directory/'nex.json').write_text(json.dumps({'schema':'nex.project/1',
            'language':report['doctor']['language'],'entry':source.name}))
        session=cli('debug','--kind','nex-dap',cwd=directory)
        evidence={'native_descriptor':True,'live_dap_pages':False,'page_limit':1000}
        if args.live:
            require(session['nex_adapter']['available'],'installed SDK lacks its native DAP backend')
            manifest=json.loads(Path(session['manifest']).read_text())
            projected=manifest['sources'][0]['projection']
            line=next(i+1 for i,text in enumerate(source.read_text().splitlines()) if 'NATIVE_PAGE_STOP' in text)
            client=DAP(session['adapter_command'],directory,environment)
            try:
                client.request('initialize',{'adapterID':'nex','pathFormat':'path','linesStartAt1':True,'supportsVariablePaging':True})
                pending=client.send('launch',dict(session['launch'],disableASLR=False));client.event('initialized')
                placed=client.request('setBreakpoints',{'source':{'path':projected},'breakpoints':[{'line':line}]})
                require(placed['breakpoints'][0]['verified'],'native pages breakpoint was not verified')
                client.request('configurationDone');client.response(pending)
                stop=client.event('stopped');frame=client.request('stackTrace',{'threadId':stop['threadId']})['stackFrames'][0]['id']
                scopes=client.request('scopes',{'frameId':frame})['scopes'];roots={}
                for scope in scopes:
                    if not scope.get('expensive'):
                        roots.update({v['name']:v for v in client.request('variables',{'variablesReference':scope['variablesReference']})['variables']})
                before=client.request('evaluate',{'expression':'len(items)+len(data)','frameId':frame,'context':'watch'})
                require(before['nex']['value']=='4227072','native root lengths differ before paging')
                pages={}
                for name,total,expected in [('items',32768,['40','42']),('data',4194304,['120','255'])]:
                    reference=roots[name]['variablesReference']
                    require(roots[name]['indexedVariables']==total,'native root lost its indexed child count')
                    tail=client.request('variables',{'variablesReference':reference,'filter':'indexed','start':total-2,'count':2})
                    require([(v['name'],v['value']) for v in tail['variables']]==[(f'[{total-2}]',expected[0]),(f'[{total-1}]',expected[1])],
                        'native indexed tail differs')
                    require(not client.request('variables',{'variablesReference':reference,'filter':'named','count':2})['variables'],
                        'native indexed root returned named children')
                    default=client.request('variables',{'variablesReference':reference})
                    large=client.request('variables',{'variablesReference':reference,'start':1000,'count':1000000})
                    require(len(default['variables'])==len(large['variables'])==1000 and large['variables'][0]['name']=='[1000]',
                        'native page request exceeded or lost its bound/offset')
                    require(large['nex']['native_page']=={'start':1000,'requested_count':1000000,'returned_count':1000,'limit':1000},
                        'native page metadata differs')
                    pages[name]={'indexed_children':total,'tail':[(v['name'],v['value']) for v in tail['variables']],
                        'default_count':len(default['variables']),'large_request_count':len(large['variables'])}
                first=client.request('evaluate',{'expression':'items[len(items)-1]+data[len(data)-1]','frameId':frame,'context':'watch'})
                second=client.request('evaluate',{'expression':'len(data)','frameId':frame,'context':'watch'})
                require(first['nex']['value']=='297' and second['nex']['stop']==first['nex']['stop']==before['nex']['stop'],
                    'native paging changed the stopped watch state')
                client.request('continue',{'threadId':stop['threadId']});require(client.event('exited')['exitCode']==0,'native page application failed')
                for name in ('items','data'):
                    try:client.request('variables',{'variablesReference':roots[name]['variablesReference'],'count':1})
                    except RuntimeError as error:require('unknown or stale variables reference' in str(error),'native page failed for a different reason after execution')
                    else:raise RuntimeError('native page handle survived execution')
                evidence.update(live_dap_pages=True,pages=pages,unchanged_watch_stop=first['nex']['stop'],native_exit_code=0,stale_handles_rejected=True)
            finally:client.close()
        report['evidence']['native_indexed_pages']=evidence

    def text_files():
        directory = root / 'text-files'
        directory.mkdir()
        data = root / 'file data % 🧠'
        data.mkdir()
        shutil.copyfile(resources / 'examples/files.nex', directory / 'main.nex')
        (directory / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1',
            'language': report['doctor']['language'], 'entry': 'main.nex'}))
        keys = ('NEX_FILES_ROOT', 'NEX_FILES_WRITE', 'NEX_RESOURCE_DIR')
        saved = {key: environment.get(key) for key in keys}
        try:
            environment.update(NEX_FILES_ROOT=str(data), NEX_FILES_WRITE='1')
            revision = cli('check', cwd=directory)['revision']
            expected_text = 'Я🧠\0text\n'
            require(cli('eval', cwd=directory)['stdout'] == expected_text,
                    'installed text-file interpreter output differs')
            for profile in ('debug', 'release'):
                cli('test', '--profile', profile, cwd=directory)
                require(cli('run', '--profile', profile, cwd=directory)['stdout'] == expected_text,
                        'installed text-file native/reference output differs')
            built = cli('build', '--profile', 'release', cwd=directory)
            metadata = json.loads((Path(built['executable']).parent / 'build.json').read_text())
            require('nex_files.cpp' in metadata['runtime_components'] and
                    'nex_store.cpp' not in metadata['runtime_components'] and
                    'nex_json.cpp' not in metadata['runtime_components'],
                    'file-only program selected unrelated runtime components')
            package = root / 'file-application'
            cli('package', '--directory', package, cwd=directory)
            manifest = json.loads((package / 'application.json').read_text())
            require(not manifest['execution_verified'], 'assembly falsely certified execution')
            (directory / 'main.nex').unlink()
            require(cli('run', '--revision', revision, cwd=directory)['stdout'] == expected_text,
                    'text-file revision did not survive source deletion')
            environment['NEX_RESOURCE_DIR'] = str(root / 'absent-resources')
            executable = package / 'bin/app'
            require(run([executable]) == expected_text and
                    (data / 'nex-message.txt').read_bytes() == expected_text[:-1].encode(),
                    'packaged file program needs compiler resources or changed text bytes')
            require(hashlib.sha256(executable.read_bytes()).hexdigest() == manifest['files']['bin/app']['sha256'],
                    'executed file application differs from package inventory')
            environment['NEX_RESOURCE_DIR'] = saved['NEX_RESOURCE_DIR']
            denied = root / 'file-denial'
            denied.mkdir()
            (denied / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1',
                'language': report['doctor']['language'], 'entry': 'main.nex'}))
            (denied / 'main.nex').write_text('''module file_denial;
server fn main()->unit!{fs,io}{
 print(error_code(file_read_text("nex-message.txt")));
 print(error_code(file_write_text("nex-message.txt","must not replace")));
}
''')
            environment.pop('NEX_FILES_ROOT', None)
            for command in ('eval', 'run'):
                require(cli(command, cwd=denied)['stdout'] == 'CAPABILITY\nCAPABILITY\n',
                        'missing file capability unexpectedly permitted access')
            environment.update(NEX_FILES_ROOT=str(data), NEX_FILES_WRITE='0')
            for command in ('eval', 'run'):
                require(cli(command, cwd=denied)['stdout'] == '\nCAPABILITY\n',
                        'read-only file capability unexpectedly permitted writes')
            require((data / 'nex-message.txt').read_bytes() == expected_text[:-1].encode(),
                    'denied write changed the existing file')
            report['evidence']['text_files'] = {'revision': revision,
                'native_profiles': ['debug', 'release'], 'source_deleted_replay': True,
                'strict_unicode_nul_roundtrip': True, 'missing_capability_denied': True,
                'read_only_write_denied': True, 'standalone_without_resources': str(executable),
                'application_manifest_sha256': hashlib.sha256((package / 'application.json').read_bytes()).hexdigest()}
            streams = root / 'file-resources'
            streams.mkdir()
            shutil.copyfile(resources / 'examples/resources.nex', streams / 'main.nex')
            (streams / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1',
                'language': report['doctor']['language'], 'entry': 'main.nex'}))
            environment.update(NEX_FILES_ROOT=str(data), NEX_FILES_WRITE='1')
            stream_revision = cli('check', cwd=streams)['revision']
            expected_stream = 'Я🧠\n<file>\n'
            require(cli('eval', cwd=streams)['stdout'] == expected_stream,
                    'installed file resource interpreter output differs')
            for profile in ('debug', 'release'):
                cli('test', '--profile', profile, cwd=streams)
                require(cli('run', '--profile', profile, cwd=streams)['stdout'] == expected_stream,
                        'installed file resource native/reference output differs')
            stream_package = root / 'resource-application'
            cli('package', '--directory', stream_package, cwd=streams)
            (streams / 'main.nex').unlink()
            require(cli('run', '--revision', stream_revision, cwd=streams)['stdout'] == expected_stream,
                    'file resource replay needs original source')
            environment['NEX_RESOURCE_DIR'] = str(root / 'absent-resources')
            require(run([stream_package / 'bin/app']) == expected_stream and
                    (data / 'nex-stream.bin').read_bytes() == 'Я🧠'.encode(),
                    'packaged streaming resource program needs compiler resources')
            report['evidence']['file_resources'] = {'revision': stream_revision,
                'language': report['doctor']['language'], 'native_profiles': ['debug', 'release'],
                'alias_close': True, 'seek_and_eof': True, 'scoped_cleanup_iterations': 80,
                'source_deleted_replay': True, 'standalone_without_resources': str(stream_package / 'bin/app')}
        finally:
            for key, value in saved.items():
                if value is None:
                    environment.pop(key, None)
                else:
                    environment[key] = value

    def structured_task_debug():
        feature = cli('describe')['task_debugging']
        require(feature['source_support'] and feature['public_launch'] and feature['catalog_abi'] == 1,
                'SDK task debugger integration is not enabled')
        directory = root/'structured-task-debug';directory.mkdir()
        source = directory/'main.nex'
        text = '''module task_debug_handoff;
fn child(input:i64)->i64 !{task} {
 let payload:list<i64>=[input,input+1];
 task_yield();
 let answer:i64=payload[1]; // task-sdk-break
 return answer;
}
fn main()->unit !{task,io} {
 let answer:i64=child(41);
 print(answer);
}
'''
        source.write_text(text)
        (directory/'nex.json').write_text(json.dumps({'schema':'nex.project/1',
            'language':report['doctor']['language'],'entry':'main.nex'}))
        checked = cli('check',cwd=directory)
        limits = ['--task-steps','2000000','--task-timeout-ms','60000','--task-workers','2']
        session = cli('debug','--kind','nex-dap',*limits,cwd=directory)
        manifest = json.loads(Path(session['manifest']).read_text())
        metadata = json.loads((Path(manifest['program']).parent/'build.json').read_text())
        view = manifest['task_debug']
        require(manifest['schema']=='nex.debug/2' and view['schema']=='nex.task-debug-view/1' and
                view['abi']==1 and view['deadline_advances_while_stopped'] is True and
                metadata['task_debug'] is True and metadata['runtime_requirements']['task_debug'] is True,
                'installed task debug artifact or ABI differs')
        executable = Path(manifest['program'])
        require(hashlib.sha256(executable.read_bytes()).hexdigest()==view['image_sha256'] and
                bool(view['image_uuid']), 'task debug image identity is absent or differs')
        source.unlink()
        archived = cli('debug','--revision',checked['revision'],'--kind','nex-dap',*limits,cwd=directory)
        require(archived['revision']==checked['revision'],'task debug archived revision differs')
        session = archived;manifest = json.loads(Path(session['manifest']).read_text())
        projected = manifest['sources'][0]['projection']
        line = next(i+1 for i,value in enumerate(Path(projected).read_text().splitlines()) if '// task-sdk-break' in value)
        evidence = {'descriptor':True,'actual_image_identity':True,'source_deleted_archive':True,
            'source_only_project':False,'standalone_without_resources':False,'logical_stack':False,
            'initialized_locals':False,'pure_watch':False,'logical_step':False,
            'stale_references_rejected':False,'graceful_exit':False,'manifest':session['manifest']}
        standalone = root/'task-debug-independent';shutil.copy2(manifest['program'],standalone)
        previous = environment.get('NEX_RESOURCE_DIR')
        try:
            environment['NEX_RESOURCE_DIR']=str(root/'absent-task-debug-resources')
            require(run([standalone,'--nex-task-workers','1'])=='42\n',
                    'instrumented standalone task debug executable differs without resources')
        finally:
            if previous is None:environment.pop('NEX_RESOURCE_DIR',None)
            else:environment['NEX_RESOURCE_DIR']=previous
        evidence['standalone_without_resources']=True
        architecture = root/'structured-task-debug-project';(architecture/'app').mkdir(parents=True)
        (architecture/'app/main.nex').write_text(text)
        (architecture/'nex.json').write_text(json.dumps({'schema':'nex.project/1',
            'language':report['doctor']['language'],'entry':'app/main.nex'}))
        (architecture/'nex.build.json').write_text(json.dumps({'schema':'nex.project-build/1',
            'default_configuration':'debug','configurations':{'debug':{'profile':'debug',
                'task_limits':{'steps':2000000,'timeout_ms':60000,'workers':2}}},
            'components':{'app':{'kind':'executable','root':'app','entry':'app/main.nex'}}}))
        prepared = cli('project','--kind','debug','--component','app','--adapter','nex-dap',cwd=architecture)
        project_session=prepared['observation']
        evidence['project_manifest']=project_session['manifest']
        require(prepared['graph_store_opened'] is False and not (architecture/'.nex/graph.db').exists(),
                'project debug opened a graph store')
        require(json.loads(Path(project_session['manifest']).read_text())['schema']=='nex.debug/2' and
                project_session['launch']['nexTaskDebug'] is True,
                'source-only project debug lost task manifest')
        evidence['source_only_project']=True
        if args.live:
            client = DAP(session['adapter_command'],directory,environment)
            try:
                client.request('initialize',{'adapterID':'nex','pathFormat':'path','linesStartAt1':True})
                pending=client.send('launch',dict(session['launch'],disableASLR=False));client.event('initialized')
                placed=client.request('setBreakpoints',{'source':{'path':projected},'breakpoints':[{'line':line}]})
                require(placed['breakpoints'][0]['verified'],'logical source breakpoint was not verified')
                client.request('configurationDone');client.response(pending);client.event('stopped')
                tasks=client.request('threads');identity=tasks['nex']['selected']
                require(type(identity) is int and any(t['id']==identity for t in tasks['threads']),
                        'selected logical task is absent from task threads')
                initial_stack=client.request('stackTrace',{'threadId':identity})
                stack=initial_stack['stackFrames']
                require([f['name'] for f in stack]==['task_debug_handoff::child','task_debug_handoff::main'],
                        'actual retained child/caller stack differs')
                frame=stack[0]['id'];scope=client.request('scopes',{'frameId':frame})['scopes'][0]
                locals_=client.request('variables',{'variablesReference':scope['variablesReference']})['variables']
                require({'input','payload'} <= {v['name'] for v in locals_} and
                        'answer' not in {v['name'] for v in locals_},'locals include an uninitialized binding')
                value=client.request('evaluate',{'expression':'input+1','frameId':frame,'context':'watch'})
                require(value['nex']['value']=='42','logical pure scalar watch differs')
                aggregate=client.request('evaluate',{'expression':'payload','frameId':frame,'context':'watch'})
                reference=aggregate['variablesReference']
                children=client.request('variables',{'variablesReference':reference})['variables']
                require([v['value'] for v in children]==['41','42'],'owned immutable watch capture differs')
                client.request('next',{'threadId':identity});client.event('stopped')
                advanced_stack=client.request('stackTrace',{'threadId':identity})
                advanced=advanced_stack['stackFrames'][0]
                before,after=initial_stack['nex'],advanced_stack['nex']
                require(advanced['name']=='task_debug_handoff::child' and
                        before['task_id']==after['task_id']==identity and before['generation']==after['generation'] and
                        before['frames'][0]['id']==after['frames'][0]['id'] and
                        int(after['stop_id'])>int(before['stop_id']) and
                        before['frames'][0]['point_id']!=after['frames'][0]['point_id'] and advanced['line']>line,
                        'logical next did not advance the same task activation to a later source point')
                answer=client.request('evaluate',{'expression':'answer','frameId':advanced['id'],'context':'watch'})
                require(answer['nex']['value']=='42','logical next did not expose the initialized result')
                try:client.request('variables',{'variablesReference':reference})
                except RuntimeError as error:require('stale' in str(error),'old watch failed for another reason')
                else:raise RuntimeError('logical watch reference survived continue')
                client.request('continue',{'threadId':identity})
                require(client.event('exited')['exitCode']==0,'logical task debug application failed')
                evidence.update(logical_stack=True,initialized_locals=True,pure_watch=True,
                    logical_step=True,stale_references_rejected=True,graceful_exit=True,
                    step_before=before,step_after=after)
            finally:client.close()
        report['evidence']['structured_task_debug']=evidence

    def measured():
        measured = cli('profile', '--revision', state['after'], '--scenario', 'installed SDK handoff', cwd=project)
        require(measured['stdout'] == expected and measured['exit_code'] == 0, 'profile changed output')
        saved = json.loads(Path(measured['output']).read_text())
        nodes = {n['name']: n for n in cli('graph', cwd=project)['nodes']}
        choose_profile = next(f for f in saved['functions'] if f['name'] == 'handoff::choose')
        require(choose_profile['calls'] == choose_profile['completed'] == 1 and choose_profile['aborted'] == 0,
                'profile call/completion evidence differs')
        for function in saved['functions']:
            require(function['node_id'] == nodes[function['name']]['id'] and
                    function['content_hash'] == nodes[function['name']]['hash'], 'profile graph attribution differs')
        for pool in saved['memory']:
            require(pool['allocations'] == pool['frees'] and pool['live'] == pool['live_shallow_bytes'] == 0,
                    'managed values remain live after normal exit')
        for field in ('dropped_events', 'dropped_functions', 'dropped_frames', 'dropped_allocations', 'untracked_frees'):
            require(saved[field] == 0, 'incomplete profile evidence: ' + field)
        report['evidence']['profile'] = measured['output']

    def sources_and_debug():
        # Only the stale live sources are removed; archived projections and receipts remain.
        (project / 'main.nex').unlink()
        (project / 'model.nex').unlink()
        state['task'].unlink()
        session = cli('debug', '--revision', state['after'], '--kind', 'nex-dap', cwd=project)
        state['session'] = session
        manifest = json.loads(Path(session['manifest']).read_text())
        for item in manifest['sources']:
            require(Path(item['projection']).is_file(), 'archived debugger source is missing')
        if args.live:
            projected = next(s['projection'] for s in manifest['sources'] if Path(s['original']).name == 'main.nex')
            line = next(i + 1 for i, s in enumerate(Path(projected).read_text().splitlines()) if '// sdk-breakpoint' in s)
            client = DAP(session['adapter_command'], root, environment)
            try:
                client.request('initialize', {'adapterID': 'nex', 'pathFormat': 'path', 'linesStartAt1': True})
                pending = client.send('launch', dict(session['launch'], disableASLR=False))
                client.event('initialized')
                placed = client.request('setBreakpoints', {'source': {'path': projected}, 'breakpoints': [{'line': line}]})
                require(placed['breakpoints'][0]['verified'], 'archived source breakpoint was not verified')
                client.request('configurationDone')
                client.response(pending)
                stopped = client.event('stopped')
                frame = client.request('stackTrace', {'threadId': stopped['threadId']})['stackFrames'][0]['id']
                expression = '(match value {ok(model::Maybe::Some(n)) if n>0=>n,_=>-1})+callback()-2'
                value = client.request('evaluate', {'expression': expression, 'frameId': frame, 'context': 'watch'})
                require(value['nex']['value'] == '42' and value['nex']['revision'] == state['after'], 'stopped watch differs')
                callback = client.request('evaluate', {'expression': 'callback', 'frameId': frame, 'context': 'watch'})
                require(callback['type'] == 'fn()->i64' and
                        callback['nex']['wire_schema']['schema'] == 'nex.debug-wire/1' and
                        callback['nex']['value']['captures'] == {'value': '2'}, 'stopped callback differs')
                children = client.request('variables', {'variablesReference': callback['variablesReference'],
                    'start': 1, 'count': 1})['variables']
                require(len(children) == 1 and children[0]['name'] == 'value' and children[0]['value'] == '2',
                        'stopped callback children differ')
                raw = client.request('evaluate', {'expression': '`nex-frame ' + expression, 'frameId': frame, 'context': 'repl'})
                snapshot = root / 'frame.json'
                snapshot.write_text(json.dumps(json.loads(raw['result']), indent=2) + '\n')
                client.request('continue', {'threadId': stopped['threadId']})
                require(client.event('exited')['exitCode'] == 0, 'debuggee failed')
                offline = cli('inspect', snapshot, '--manifest', session['manifest'], '--expression', expression, cwd=project)
                require(offline['value'] == '42', 'offline captured watch differs')
                report['evidence']['frame'] = str(snapshot)
                report['evidence']['checked_callable_watch'] = True
            finally:
                client.close()
        report['evidence']['debug_manifest'] = session['manifest']
        replay = cli('task', state['accepted']['output'], '--kind', 'replay', cwd=project, timeout=300)
        require(replay['status'] == 'passed' and replay['task_hash'] == state['task_hash'], 'source-free replay failed')
        require(cli('run', '--revision', state['before'], cwd=project)['stdout'] == expected.replace('42\n', '43\n', 1),
                'old revision no longer executes its own behavior')
        materialized = root / 'exported'
        cli('export', '--revision', state['after'], '--directory', materialized, cwd=project)
        require(cli('check', cwd=materialized)['revision'] == state['after'], 'materialization changed revision')
        require(cli('run', cwd=materialized)['stdout'] == expected, 'exported sources do not execute')
        report['evidence'].update(replay_receipt=replay['output'], exported=str(materialized),
                                  original_sources_deleted=True, live_debugger=args.live)

    def proof():
        directory = root / 'proof'
        shutil.copytree(resources / 'examples/verification', directory)
        verified = cli('verify', '--contracts', directory / 'contracts.json', cwd=directory)
        require(verified['ok'] and verified['functions'] and
                all(f['status'] == 'proven' for f in verified['functions']), 'installed scalar contracts were not proven')
        report['evidence']['scalar_proof'] = 'proven (installed scalar example, not a proof of matching or compiler correctness)'

    def authenticated_storage():
        directory = root / 'service'
        directory.mkdir()
        (directory / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1',
            'language': report['doctor']['language'], 'entry': 'main.nex'}))
        (directory / 'main.nex').write_text('''module installed_service;
import "std/http.nex" as http;
server fn handle(request:http::Request) -> http::Response !{db} {
  if request.method == "POST" {
    let saved:result<bool> = store_put("value",request.body);
    return match saved {ok(_) => http::Response(200,request.user+":"+request.body,"text/plain"),err(_,_) => http::Response(500,"storage failure","text/plain")};
  }
  let loaded:result<str> = store_get("value");
  return match loaded {ok(value) => http::Response(200,request.user+":"+value,"text/plain"),err(_,_) => http::Response(404,"missing","text/plain")};
}
''')
        auth = directory / 'auth.json'
        tokens = {user: cli('token', '--user', user, '--auth', auth, cwd=directory)['token']
                  for user in ('alice', 'bob')}
        built = cli('build', '--target', 'server', '--profile', 'release', cwd=directory)
        certificate, key = directory / 'cert.pem', directory / 'key.pem'
        run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-sha256', '-days', '1',
             '-subj', '/CN=localhost', '-addext', 'subjectAltName=IP:127.0.0.1,DNS:localhost',
             '-keyout', key, '-out', certificate], cwd=directory)
        context = ssl.create_default_context(cafile=str(certificate))
        for encrypted in (False, True):
            command = [built['executable'], '--auth', str(auth), '--database', str(directory / 'data.sqlite'), '--port', '0']
            if encrypted:
                command += ['--cert', str(certificate), '--key', str(key)]
            stderr = logs / ('service-https.stderr' if encrypted else 'service-http.stderr')
            with stderr.open('w') as errors:
                process = subprocess.Popen(command, cwd=directory, env=environment,
                                           stdout=subprocess.PIPE, stderr=errors, text=True)
                try:
                    lines = queue.Queue()
                    threading.Thread(target=lambda: lines.put(process.stdout.readline()), daemon=True).start()
                    line = lines.get(timeout=20)
                    match = re.fullmatch(r'NEX server (https?://127\.0\.0\.1:[0-9]+)\s*', line)
                    require(match is not None, 'installed server did not start; inspect ' + str(stderr))
                    base = match.group(1)
                    require(base.startswith('https:') == encrypted, 'server selected wrong transport')
                    def request(user, body=None):
                        headers = {} if user is None else {'Authorization': 'Bearer ' + tokens[user]}
                        payload = None if body is None else body.encode()
                        value = urllib.request.Request(base + '/api/value', data=payload, headers=headers)
                        try:
                            response = urllib.request.urlopen(value, context=context if encrypted else None, timeout=15)
                        except urllib.error.HTTPError as error:
                            response = error
                        with response:
                            return response.status, response.read().decode()
                    unauthenticated = request(None)
                    require(unauthenticated[0] == 401, 'expected unauthenticated rejection (401), received ' + str(unauthenticated[0]))
                    if not encrypted:
                        require(request('alice', 'Unicode 🧠') == (200, 'alice:Unicode 🧠'), 'alice write failed')
                        require(request('bob')[0] == 404, 'bob could read alice data')
                        require(request('bob', 'separate') == (200, 'bob:separate'), 'bob write failed')
                    require(request('alice') == (200, 'alice:Unicode 🧠'), 'alice persistence/isolation failed')
                    require(request('bob') == (200, 'bob:separate'), 'bob persistence/isolation failed')
                finally:
                    if process.poll() is None:
                        process.terminate()
                    try:
                        process.communicate(timeout=15)
                    except subprocess.TimeoutExpired:
                        process.kill(); process.communicate(timeout=5)
                require(process.returncode == 0, 'installed server failed; inspect ' + str(stderr))
            require('E_INTERNAL_LEAK' not in stderr.read_text(), 'installed server leaked owned values')
        report['evidence']['authenticated_storage'] = {'executable': built['executable'],
            'http_https': True, 'unauthenticated_rejected': True,
            'principal_isolation': True, 'persistent_across_restart': True,
            'metadata': built['metadata']}

    def browser():
        directory = root / 'browser'
        directory.mkdir()
        client = (resources / 'examples/functions/web.nex').read_text()
        client += '\nserver fn sdk_unreachable_sentinel() -> str {return "SDK_SERVER_ONLY_SENTINEL";}\n'
        (directory / 'main.nex').write_text(client)
        (directory / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1',
            'language': report['doctor']['language'], 'entry': 'main.nex'}))
        tested = cli('test', '--target', 'web', cwd=directory)
        require('functions::web::transitions' in {t['name'] for t in tested['tests']},
                'browser tests selected another project')
        generated = root / 'generated-web'
        cli('web', '--directory', generated, cwd=directory)
        require(not any('SDK_SERVER_ONLY_SENTINEL' in f.read_text() for f in generated.rglob('*.ts')),
                'server code entered generated client')
        if args.browser:
            built = cli('build', '--target', 'web', '--profile', 'release', cwd=directory, timeout=300)
            dist = Path(built['dist'])
            require((dist / 'index.html').is_file() and any(dist.rglob('*.js')), 'missing production browser assets')
            for path in dist.rglob('*'):
                if path.is_file():
                    require(b'SDK_SERVER_ONLY_SENTINEL' not in path.read_bytes(), 'server code entered browser assets')
            report['evidence']['browser_dist'] = str(dist)
        numeric = root / 'numeric-browser'
        numeric.mkdir()
        shutil.copyfile(resources / 'examples/numbers-web.nex', numeric / 'main.nex')
        (numeric / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1',
            'language': report['doctor']['language'], 'entry': 'main.nex'}))
        cli('test', cwd=numeric)
        numeric_tests = cli('test', '--target', 'web', cwd=numeric)
        require('numbers_web::transitions' in {t['name'] for t in numeric_tests['tests']},
                'numeric browser tests selected another project')
        numeric_generated = root / 'generated-numeric-web'
        numeric_project = cli('web', '--directory', numeric_generated, cwd=numeric)
        require(not any('FINITE_NUMBERS_SERVER_SENTINEL' in path.read_text()
                        for path in numeric_generated.rglob('*.ts')),
                'numeric server code entered generated client')
        numeric_evidence = {'revision': numeric_project['revision'], 'native_tests': True,
                            'typescript_tests': True, 'generated': str(numeric_generated),
                            'browser_build': args.browser}
        if args.browser:
            numeric_built = cli('build', '--target', 'web', '--profile', 'release', cwd=numeric, timeout=300)
            numeric_dist = Path(numeric_built['dist'])
            require((numeric_dist / 'index.html').is_file() and any(numeric_dist.rglob('*.js')),
                    'missing numeric production browser assets')
            for path in numeric_dist.rglob('*'):
                if path.is_file():
                    require(b'FINITE_NUMBERS_SERVER_SENTINEL' not in path.read_bytes(),
                            'numeric server code entered browser assets')
            numeric_evidence['dist'] = str(numeric_dist)
        report['evidence']['numeric_browser'] = numeric_evidence
        binary = root / 'binary-browser'; binary.mkdir()
        shutil.copyfile(resources / 'examples/bytes-web.nex', binary / 'main.nex')
        (binary / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1',
            'language': report['doctor']['language'], 'entry': 'main.nex'}))
        cli('test', cwd=binary)
        binary_tests = cli('test', '--target', 'web', cwd=binary)
        require('bytes_web::transitions' in {t['name'] for t in binary_tests['tests']},
                'binary browser tests selected another project')
        generated_binary = root / 'generated-binary-web'
        cli('web', '--directory', generated_binary, cwd=binary)
        require(not any('BINARY_WEB_SERVER_ONLY_SENTINEL' in path.read_text()
                        for path in generated_binary.rglob('*.ts')), 'binary server code entered client')
        binary_evidence = {'native_tests': True, 'typescript_tests': True,
                           'generated': str(generated_binary), 'browser_build': args.browser}
        if args.browser:
            built = cli('build', '--target', 'web', '--profile', 'release', cwd=binary, timeout=300)
            dist = Path(built['dist'])
            require((dist / 'index.html').is_file() and any(dist.rglob('*.js')), 'missing binary browser assets')
            for path in dist.rglob('*'):
                if path.is_file():
                    require(b'BINARY_WEB_SERVER_ONLY_SENTINEL' not in path.read_bytes(),
                            'binary server code entered browser assets')
            binary_evidence['dist'] = str(dist)
        report['evidence']['binary_browser'] = binary_evidence
        for example,module_name,evidence_name in [('workers','worker_example','browser_workers'),
                                                   ('task-workers','task_worker_example','browser_task_workers')]:
            worker = root / ('worker-browser' if example=='workers' else 'task-worker-browser'); worker.mkdir()
            worker_source = (resources/'examples'/example/'main.nex').read_text()
            (worker/'nex.json').write_text(json.dumps({'schema':'nex.project/1',
                'language':report['doctor']['language'],'entry':'main.nex'}))
            (worker/'main.nex').write_text(worker_source.replace('client fn','shared fn').replace('client test fn','shared test fn'))
            cli('test',cwd=worker)
            (worker/'main.nex').write_text(worker_source+'\nserver fn sdk_worker_secret()->str{return "SDK_WORKER_SERVER_SENTINEL";}\n')
            worker_tests=cli('test','--target','web',cwd=worker)
            require(module_name+'::worker_values_test' in {t['name'] for t in worker_tests['tests']},
                    'worker browser tests selected another project')
            worker_generated=root/('generated-worker-web' if example=='workers' else 'generated-task-worker-web')
            worker_project=cli('web','--directory',worker_generated,cwd=worker)
            require((worker_generated/'src/worker-program.ts').is_file() and
                    (worker_generated/'src/worker-entry.ts').is_file(),'worker module was not emitted')
            require('as compute' not in (worker_generated/'src/program.ts').read_text(),
                    'worker compute entered the main closure')
            require(not any('SDK_WORKER_SERVER_SENTINEL' in path.read_text()
                            for path in worker_generated.rglob('*.ts')),'server code entered worker/client source')
            if example=='task-workers':
                require((worker_generated/'src/nex-task-runtime.ts').is_file() and
                        'task.run(task.call(' in (worker_generated/'src/worker-program.ts').read_text(),
                        'task worker lacks its independent scheduler host')
            worker_evidence={'revision':worker_project['revision'],'native_tests':True,
                             'typescript_tests':True,'generated':str(worker_generated),
                             'browser_build':args.browser,'actual_worker_execution':False}
            if args.browser:
                (worker/'main.nex').unlink()
                built=cli('build','--revision',worker_project['revision'],'--target','web',
                          '--profile','release',cwd=worker,timeout=300)
                dist=Path(built['dist'])
                require(any(dist.rglob('worker-entry-*.js')),'missing production module worker asset')
                for path in dist.rglob('*'):
                    if path.is_file():require(b'SDK_WORKER_SERVER_SENTINEL' not in path.read_bytes(),
                                             'worker server code entered production assets')
                worker_evidence.update(dist=str(dist),physical_source_deleted=True,archived_build=True)
            report['evidence'][evidence_name]=worker_evidence
        report['evidence']['browser_build'] = args.browser

    def server_debugging():
        project=root/'server-debugging';shutil.copytree(resources/'examples/server-debug',project)
        private=project/'private';private.mkdir();auth=private/'auth.json';database=private/'runtime.sqlite'
        token=cli('token','--user','sdk-debugger','--auth',auth,cwd=project)['token']
        runtime=['--auth',auth,'--database',database,'--port','0','--timeout-ms','60000']
        response=cli('project','--kind','debug','--component','service','--adapter','nex-dap','--',*runtime,cwd=project,timeout=300)
        session=response['observation'];artifact=next(a for a in response['artifacts'] if a['component']=='service')
        require(session['application_kind']=='http_server' and session['host_compatible'] and session['launch']['program']==artifact['artifact'] and
            session['build_key']==artifact['build_key'] and not database.exists() and not (project/'.nex/graph.db').exists(), 'server debug preparation changed runtime state or artifact identity')
        compilation=json.loads(Path(artifact['compilation']).read_text())
        require(len(compilation['owned_images'])==2 and all(u['identity'].startswith('debug_service::') or u['identity'].startswith('std::') for u in compilation['units']),
            'server debugger did not consume its actual shared provider')
        node=os.environ.get('NEX_NODE') or shutil.which('node');require(node,'server editor preparation requires Node')
        code=('const {prepareSession}=require(process.argv[1]);prepareSession(JSON.parse(process.argv[2]),{compiler:process.argv[3]})'
              '.then(value=>process.stdout.write(JSON.stringify(value))).catch(error=>{console.error(error.message);process.exitCode=1;});')
        prepared=json.loads(run([node,'-e',code,resources/'editor/vscode/session.js',json.dumps({'type':'nex','request':'launch','cwd':str(project),
            'project':{'manifest':'nex.build.json','component':'service','configuration':'debug'},'args':list(map(str,runtime))}),compiler],cwd=project,timeout=300))
        require(prepared['buildKey']==artifact['build_key'] and prepared['launch']['program']==artifact['artifact'] and
                prepared['launch']['args']==list(map(str,runtime)) and any(Path(pair[1]).resolve()==(project/'core/main.nex').resolve() for pair in prepared['originalSourceMappings']),
                'server editor preparation lost artifact, runtime arguments or original provider mappings')
        evidence={'descriptor':True,'actual_shared_provider':True,'editor_preparation':True,'live_worker_stop':False,'source_deleted':False,
            'request_completed':False,'graceful_exit':False,'manifest':session['manifest']}
        if args.live:
            manifest=json.loads(Path(session['manifest']).read_text())
            symbol=next(f['native_symbol'] for f in manifest['functions'] if f['name']=='debug_core::render')
            for name in ('core','service'):shutil.rmtree(project/name)
            for name in ('nex.json','nex.build.json'):(project/name).unlink()
            client=DAP(prepared['command'],project,environment);executor=concurrent.futures.ThreadPoolExecutor(max_workers=1)
            try:
                client.request('initialize',{'adapterID':'nex','pathFormat':'path','linesStartAt1':True,'supportsVariableType':True})
                launch=dict(prepared['launch'],disableASLR=False,preRunCommands=[*prepared['launch'].get('preRunCommands',[]),'process handle -s false -n false -p true SIGTERM'])
                pending=client.send('launch',launch);client.event('initialized')
                client.request('setFunctionBreakpoints',{'breakpoints':[{'name':symbol}]})
                client.request('configurationDone');client.response(pending);pid=client.event('process')['systemProcessId']
                output='';port=None
                for _ in range(64):
                    output+=client.event('output').get('output','');found=re.search(r'NEX server http://127\.0\.0\.1:([0-9]+)',output)
                    if found:port=int(found.group(1));break
                require(port is not None,'debug server did not report its loopback listener')
                def send_request():
                    request=urllib.request.Request('http://127.0.0.1:'+str(port)+'/api/debug',data=b'payload',
                        headers={'Authorization':'Bearer '+token,'Content-Type':'text/plain'},method='POST')
                    with urllib.request.urlopen(request,timeout=90) as response:return response.status,json.loads(response.read())
                request=executor.submit(send_request);stop=client.event('stopped');require(stop['reason']=='breakpoint','server worker did not stop at its provider')
                frame=client.request('stackTrace',{'threadId':stop['threadId']})['stackFrames'][0]
                watch=client.request('evaluate',{'expression':'body','frameId':frame['id'],'context':'watch'})
                require(watch['nex']['value']=='payload' and 'debug_core' in frame['name'],'server provider watch differs')
                client.request('continue',{'threadId':stop['threadId']});require(request.result(timeout=80)==(200,'Я🧠:payload'),'resumed server request differs')
                os.kill(pid,signal.SIGTERM);require(client.event('exited')['exitCode']==0,'server debuggee failed graceful shutdown')
                evidence.update(live_worker_stop=True,source_deleted=True,request_completed=True,graceful_exit=True,watch='payload')
            finally:client.close();executor.shutdown(wait=True)
        require(not (project/'.nex/graph.db').exists(),'server debugger synchronized a graph Store')
        report['evidence']['server_debug']=evidence

    def project_build():
        server_debugging()
        full_descriptor = cli('describe'); description = full_descriptor['project_build']
        require('project_architecture_tasks' in full_descriptor['task_features'], 'SDK lacks project task captures/replay')
        require('project_task_packages' in full_descriptor['task_features'], 'SDK lacks project package acceptance checks')
        require('project_task_server_workloads' in full_descriptor['task_features'], 'SDK lacks captured server workload profiles')
        require(description['manifest_schema'] == 'nex.project-build/1' and
                description['dependency_linkage'] == ['source', 'static', 'dynamic'] and
                'shared_library' in description['artifact_kinds'] and
                {'project_binary_execution','project_owned_tests','project_native_debug_descriptors','project_native_profiles','project_server_workload_profiles'} <= set(description['features']), 'SDK project build contract differs')
        architecture = root / 'project-architecture'
        shutil.copytree(resources / 'examples/project-build', architecture)
        planned = cli('project', '--kind', 'plan', cwd=architecture)
        require(planned['schema'] == 'nex.project-plan/1' and planned['source_checked'] and
                not planned['external_tools_invoked'] and not (architecture / '.nex').exists(),
                'project plan did not remain read-only')
        selected = cli('project', '--kind', 'plan', '--component', 'app', cwd=architecture)
        require([c['name'] for c in selected['components']] == ['core', 'app'], 'project dependency closure differs')
        native = cli('project', '--kind', 'build', '--component', 'app', '--configuration', 'release', cwd=architecture)
        application, = native['artifacts']
        require(application['kind'] == 'executable' and run([application['artifact']]) == '22\n',
                'project application did not execute its shared source')
        archive = cli('project', '--kind', 'build', '--component', 'archive', '--configuration', 'release', cwd=architecture)
        library, = archive['artifacts']
        debug = json.loads(Path(library['debug_manifest']).read_text())
        symbol = next(f['native_symbol'] for f in debug['functions'] if f['name'] == 'project::archive::answer')
        host = architecture / 'archive-host.cpp'
        host.write_text('extern "C" long long ' + symbol + '();int main(){return ' + symbol + '()==22?0:1;}')
        executable = architecture / 'archive-host'
        run([report['doctor']['native_compiler'], '-std=c++20', host, library['artifact'], '-o', executable])
        run([executable])
        warm = cli('project', '--kind', 'build', '--component', 'app', '--configuration', 'release', cwd=architecture)
        require(warm['plan_hash'] == native['plan_hash'] and warm['artifacts'][0]['cached'], 'project cache/plan changed')
        manifest = architecture / 'nex.build.json'
        broken = json.loads(manifest.read_text()); broken['components']['app']['dependencies'] = {}
        manifest.write_text(json.dumps(broken))
        rejected = cli('project', '--kind', 'build', '--component', 'app', cwd=architecture, expected_success=False)
        require(rejected['code'] == 'E_PROJECT_BOUNDARY', 'undeclared architecture edge was accepted')
        shutil.copy2(resources / 'examples/project-build/nex.build.json', manifest)
        web_result = None
        if args.browser:
            built = cli('project', '--kind', 'build', '--component', 'browser', '--configuration', 'release', cwd=architecture, timeout=300)
            web_result, = built['artifacts']
            require(web_result['kind'] == 'web' and (Path(web_result['result']['dist']) / 'index.html').is_file(),
                    'project browser artifact is missing')
        require(not (architecture / '.nex/graph.db').exists(), 'project build synchronized graph history')
        binary_project = root / 'native-library-project'
        shutil.copytree(resources / 'examples/native-libraries', binary_project)
        binary_plan = cli('project', '--kind', 'plan', cwd=binary_project)
        require(not (binary_project / '.nex').exists(), 'binary dependency plan created a cache/store')
        binary_build = cli('project', '--kind', 'build', '--configuration', 'release', cwd=binary_project)
        binary_artifacts = {a['component']: a for a in binary_build['artifacts']}
        require(run([binary_artifacts['app']['artifact']]) == '22\nNEX 🧠\n', 'archive consumer differs')
        compilation = json.loads(Path(binary_artifacts['app']['compilation']).read_text())
        require(not any(f.startswith('native_library::math::') for u in compilation['units'] for f in u['functions'])
                and len(compilation['static_libraries']) == 1, 'consumer recompiled its binary dependency')
        binary_archive = Path(binary_artifacts['core']['artifact'])
        binary_abi = json.loads((binary_archive.parent / 'library-abi.json').read_text())
        require(binary_abi['code_only'] and binary_archive.read_bytes().startswith(b'!<arch>\n'), 'code-only archive missing')
        binary_warm = cli('project', '--kind', 'build', '--configuration', 'release', cwd=binary_project)
        require(all(a['cached'] for a in binary_warm['artifacts']), 'binary dependencies did not reuse checked artifacts')
        require(not (binary_project / '.nex/graph.db').exists(), 'binary build opened graph history')
        report['evidence']['project_build'] = {'plan_hash': planned['plan_hash'], 'selected_plan_hash': selected['plan_hash'],
            'native_artifact': application['artifact'], 'archive': library['artifact'], 'archive_host_executed': True,
            'source_linkage': True, 'undeclared_import_rejected': True, 'web_built': web_result is not None,
            'static_archive_consumption': True, 'consumer_definitions_excluded': True,
            'binary_plan_hash': binary_plan['plan_hash'], 'binary_artifacts': binary_artifacts,
            'graph_store_opened': False}
        shared_project = root/'shared-library-project'
        shutil.copytree(resources/'examples/native-libraries', shared_project)
        shared_description = json.loads((shared_project/'nex.build.json').read_text())
        shared_description['configurations']['profile'] = {'profile': 'profile'}
        shared_description['components']['core']['kind'] = 'shared_library'
        (shared_project/'bridge').mkdir()
        bridge = shared_project/'bridge/main.nex'
        bridge.write_text('''module sdk_shared::bridge;
import "../core/math.nex" as m;
pub fn render(x:i64)->str{
 let held:str=str(m::make(40)(x));
 return m::decorate(held); // SHARED_STOP
}
test fn bridge_checks()->unit{assert(render(2)=="42 🧠");}
''')
        shared_description['components']['bridge'] = {'kind': 'shared_library', 'root': 'bridge',
            'entry': 'bridge/main.nex', 'entry_function': 'render', 'dependencies': {'core': 'dynamic'}}
        shared_description['components']['app']['dependencies'] = {'bridge': 'dynamic'}
        app_source = shared_project/'app/main.nex'
        app_source.write_text('module sdk_shared::app;import "../bridge/main.nex" as b;fn main()->unit!{io}{print(b::render(2));}test fn app_checks()->unit{assert(b::render(2)=="42 🧠");}')
        (shared_project/'nex.build.json').write_text(json.dumps(shared_description))
        def shared_build(profile):
            return cli('project', '--kind', 'build', '--configuration', profile, cwd=shared_project, timeout=300)
        linked = shared_build('release'); images = {a['component']: a for a in linked['artifacts']}
        require(run([images['app']['artifact']]) == '42 🧠\n', 'shared project application differs')
        compilation = json.loads(Path(images['app']['compilation']).read_text())
        require(len(compilation['owned_images']) == 3 and not compilation['static_libraries'] and
                sum(i['kind'] == 'runtime' for i in compilation['owned_images']) == 1 and
                all(u['identity'].startswith('sdk_shared::app::') for u in compilation['units']),
                'shared project did not consume separate binary images and one runtime')
        require(all(a['cached'] for a in shared_build('release')['artifacts']), 'shared project cache missed')
        app_source.write_text(app_source.read_text().replace('render(2)', 'render(3)'))
        edited = shared_build('release'); edited_images = {a['component']: a for a in edited['artifacts']}
        require(edited['native_runtime_image'] == linked['native_runtime_image'] and
                all(edited_images[n]['build_key'] == images[n]['build_key'] and edited_images[n]['cached']
                    for n in ('core', 'bridge')) and run([edited_images['app']['artifact']]) == '43 🧠\n',
                'application edit changed independent shared providers/runtime')
        moved_app = root/'moved shared app % 🧠'; moved_app.mkdir()
        executable = Path(edited_images['app']['artifact'])
        shutil.copy2(executable, moved_app/'app'); shutil.copytree(executable.parent/'images', moved_app/'images')
        hidden = root/'retained-shared-project'
        shared_project.rename(hidden)
        try:
            require(run([moved_app/'app'], cwd=moved_app) == '43 🧠\n', 'moved shared application needs its original project')
        finally:
            hidden.rename(shared_project)
        app_source.write_text(app_source.read_text().replace('render(3)', 'render(2)'))
        profiled = {a['component']: a for a in shared_build('profile')['artifacts']}
        profile_path = root/'shared-profile.json'
        previous = {k: environment.get(k) for k in ('NEX_TRACY', 'NEX_PROFILE_OUTPUT')}
        environment.update(NEX_TRACY='0', NEX_PROFILE_OUTPUT=str(profile_path))
        try:
            require(run([profiled['app']['artifact']]) == '42 🧠\n', 'shared profile execution differs')
        finally:
            for key, value in previous.items():
                if value is None: environment.pop(key, None)
                else: environment[key] = value
        measured = json.loads(profile_path.read_text())
        require(measured['build']['build_key'] == profiled['app']['build_key'] and measured['memory'] and
                all(p['live'] == 0 and p['allocations'] == p['frees'] for p in measured['memory']),
                'shared profile is unbound or retains owned values')
        action_run=cli('project','--kind','run','--component','app','--configuration','release',cwd=shared_project,timeout=300)
        require(action_run['observation']['stdout']=='42 🧠\n' and not action_run['graph_store_opened'], 'project run did not execute its declared images')
        action_tests=cli('project','--kind','test','--component','app','--configuration','debug',cwd=shared_project,timeout=300)
        require({t['name'] for t in action_tests['tests']}=={'sdk_shared::bridge::bridge_checks','sdk_shared::app::app_checks'} and
                all(t['native'] and t['reference'] and t['typescript'] and t['ok'] for t in action_tests['tests']), 'project owned/native/TypeScript/reference tests differ')
        action_debug=cli('project','--kind','debug','--component','app','--adapter','nex-dap',cwd=shared_project,timeout=300)
        debug_artifact=next(a for a in action_debug['artifacts'] if a['component']=='app')
        require(action_debug['observation']['launch']['program']==debug_artifact['artifact'] and
                action_debug['observation']['build_key']==debug_artifact['build_key'], 'project debugger independently rebuilt source')
        node=os.environ.get('NEX_NODE') or shutil.which('node');require(node,'project editor preparation requires Node')
        code=('const {prepareSession}=require(process.argv[1]);prepareSession(JSON.parse(process.argv[2]),{compiler:process.argv[3]})'
              '.then(value=>process.stdout.write(JSON.stringify(value))).catch(error=>{console.error(error.message);process.exitCode=1;});')
        project_editor=json.loads(run([node,'-e',code,resources/'editor/vscode/session.js',json.dumps({'type':'nex','request':'launch','cwd':str(shared_project),
            'project':{'manifest':'nex.build.json','component':'app','configuration':shared_description['default_configuration']}}),compiler],cwd=shared_project,timeout=300))
        require(project_editor['launch']['program']==debug_artifact['artifact'] and project_editor['buildKey']==debug_artifact['build_key'] and
                project_editor['command']==action_debug['observation']['adapter_command'] and
                any(Path(pair[1]).resolve()==bridge.resolve() for pair in project_editor['originalSourceMappings']), 'project editor lost its actual binary artifact/provider sources')
        report['evidence']['editor'].update(project_session_preparation=True,project_actual_binary_dependencies=True)
        action_profile=cli('project','--kind','profile','--component','app','--configuration','profile',cwd=shared_project,timeout=300)
        actual_profile=action_profile['observation']
        require(actual_profile['stdout']=='42 🧠\n' and any(f['name']=='sdk_shared::bridge::render' for f in actual_profile['functions']) and
                all(f['node_id'] is None and f['identity_scope']=='captured_project' for f in actual_profile['functions']) and
                not (shared_project/'.nex/graph.db').exists(), 'project profile lost provider attribution or created graph IDs')
        task_project=root/'project-task-example';shutil.copytree(resources/'examples/project-tasks',task_project)
        notice_fixture=task_project/'fixture-notice.txt';notice_fixture.write_text('SDK acceptance notice-capture data fixture; not a dependency redistribution notice.\n')
        (task_project/'notices.json').write_text(json.dumps({'schema':'nex.sdk-notices/1','components':project_notice_components(task_project, [
            {'name':'sdk-notice-capture-fixture','version':'test','url':'https://github.com/sae-ru/NEX',
             'roots':[str(compiler)],'license_files':[str(notice_fixture)]}], extra_notices)}))
        notice_pin=cli('task','notices.json','--kind','notices',cwd=task_project)
        require(not notice_pin['graph_store_opened'] and not notice_pin['external_tools_invoked'] and not (task_project/'.nex').exists(), 'notice inspector executed tools or opened a graph')
        task_contract=json.loads((task_project/'task.json').read_text())
        next(c for c in task_contract['checks'] if c['kind']=='package').update(notices='notices.json',notices_hash=notice_pin['inputs_hash'])
        (task_project/'task.json').write_text(json.dumps(task_contract))
        task_checked=cli('task','task.json','--kind','check',cwd=task_project,timeout=300)
        task_run=cli('task','task.json','--kind','run','--task-hash',task_checked['task_hash'],'--directory',root/'project-task-run',cwd=task_project,timeout=600)
        require(task_run['ok'] and all(c['status']=='passed' for c in task_run['checks']), 'project acceptance task failed')
        task_receipt=Path(task_run['output']);saved_task=json.loads(task_receipt.read_text())
        task_build=next(c for c in saved_task['checks'] if c['id']=='build-native')
        task_app=task_receipt.parent/next(c['directory'] for c in task_build['components'] if c['component']=='app')/'compilation.json'
        task_compilation=json.loads(task_app.read_text())
        require(len(task_compilation['owned_images'])==2 and all(u['identity'].startswith('project_task::app::') for u in task_compilation['units']), 'task recompiled its shared provider')
        task_native=json.loads((task_receipt.parent/'artifacts/output/commands/native.json').read_text())
        require(task_native['command'][0]!=str(compiler) and '--revision' not in task_native['command'], 'task did not supervise the actual native image directly')
        task_package=next(c for c in saved_task['checks'] if c['kind']=='package')
        require(task_package['notices_hash']==notice_pin['inputs_hash'] and (task_receipt.parent/'inputs/package-notices/package/licenses/0.txt').is_file(), 'task did not capture its reviewed notice data')
        task_deployment=task_receipt.parent/task_package['package']
        require(not task_package['application_execution'] and (task_deployment/'apps/app/THIRD_PARTY_NOTICES.txt').is_file(), 'task package is missing build-only deployment evidence')
        shutil.rmtree(task_project)
        packaged_task_stdout=run([task_deployment/'apps/app/bin/app'],cwd=root,timeout=30)
        require(packaged_task_stdout=='42 🧠\n', 'task package failed after source deletion')
        task_replay=cli('task',task_receipt,'--kind','replay','--directory',root/'project-task-replay',cwd=root,timeout=600)
        require(task_replay['ok'] and task_replay['programs']==task_run['programs'], 'project task replay fell back to deleted source')
        require((Path(task_replay['output']).parent/'state/.nex/graph.db').is_file() and not (task_receipt.parent/'.nex/graph.db').exists() and not (root/'.nex/graph.db').exists(), 'project replay used its input or enclosing evidence/workspace graph')
        report['evidence']['project_architecture_task']={'ok':True,'source_deleted_replay':True,'original':str(task_receipt),'replay':task_replay['output'],
            'task_hash':task_checked['task_hash'],'actual_shared_provider':True,'native_execution_supervised_directly':True,
            'deployment_package_after_source_deletion':True,'pinned_notice_source_deleted_replay':True,'checks':len(saved_task['checks'])}
        deployment = root/'shared-project-package'
        packaged = cli('project', '--kind', 'package', '--configuration', 'release', '--component', 'app',
                       '--directory', deployment, cwd=shared_project, timeout=300)
        require(packaged['schema'] == 'nex.project-package/1' and not packaged['application_execution'] and
                not packaged['graph_store_opened'], 'project package executed/synchronized its source')
        package_app = next(c for c in packaged['components'] if c['component'] == 'app')
        native_package = json.loads((deployment/package_app['manifest']).read_text())
        owned = [r for r in native_package['files'].values() if 'owned_image_kind' in r]
        require(len(owned) == 3 and sum(r['owned_image_kind'] == 'runtime' for r in owned) == 1,
                'project package did not retain its two libraries and common runtime')
        hidden = root/'source-hidden-during-package-run'; shared_project.rename(hidden)
        moved_deployment = root/'moved project package % 🧠'; deployment.rename(moved_deployment)
        try:
            require(run([moved_deployment/package_app['entry']]) == '42 🧠\n', 'relocated project package needs its original build')
        finally:
            hidden.rename(shared_project)
        architecture_package = root/'architecture-package'
        package_selection = [] if args.browser else ['--component', 'app']
        architecture_deployment = cli('project', '--kind', 'package', '--configuration', 'release',
            '--directory', architecture_package, *package_selection, cwd=architecture, timeout=300)
        require(run([architecture_package/'apps/app/bin/app']) == '22\n', 'source-architecture package differs')
        if args.browser:
            require((architecture_package/'web/browser/index.html').is_file() and
                    (architecture_package/'web/browser/THIRD_PARTY_NOTICES.txt').is_file(), 'project package lost browser assets/notices')
        shared_evidence = {'separate_shared_libraries': 2, 'one_runtime': True, 'consumer_did_not_recompile_providers': True,
            'moved_application': str(moved_app/'app'), 'provider_reuse_after_app_edit': True,
            'profile_identity_checked': True, 'profile_cleanup_checked': True, 'actual_shared_core': False}
        shared_evidence.update(project_package=str(moved_deployment), relocated_project_package_executed=True,
            package_preserved_shared_edges=True, architecture_package=str(architecture_package), native_and_web_packaged=args.browser)
        shared_evidence.update(project_run=True,project_owned_tests=len(action_tests['tests']),project_debug_descriptor=True,
            project_profile=True,captured_project_identities=True)
        if args.live:
            debug_images = {a['component']: a for a in shared_build('debug')['artifacts']}
            debug_app = debug_images['app']; manifest = Path(debug_app['debug_manifest'])
            metadata = json.loads(manifest.read_text())
            projection = next(s['projection'] for s in metadata['sources'] if Path(s['original']).resolve() == bridge.resolve())
            line = next(i+1 for i, s in enumerate(Path(projection).read_text().splitlines()) if 'SHARED_STOP' in s)
            core = root/'shared-project.core'
            lldb = os.environ.get('NEX_LLDB') or shutil.which('lldb')
            require(lldb is not None, 'shared core acceptance requires LLDB')
            captured = run([lldb, debug_app['artifact'], '--no-lldbinit', '--batch',
                '-o', 'settings set target.disable-aslr false',
                '-o', 'command script import '+json.dumps(str(manifest.parent/'debugger/lldb_nex.py'), ensure_ascii=False),
                '-o', 'nex-load-debug '+json.dumps(str(manifest), ensure_ascii=False)+' --compiler '+json.dumps(str(compiler), ensure_ascii=False),
                '-o', 'breakpoint set --file '+json.dumps(projection, ensure_ascii=False)+' --line '+str(line),
                '-o', 'run', '-o', 'nex-eval held',
                '-o', 'process save-core --style modified-memory '+json.dumps(str(core), ensure_ascii=False),
                '-o', 'continue'], cwd=shared_project, timeout=120)
            require(core.is_file() and 'exited with status = 0' in captured, 'shared library stop/core did not complete')
            for name in ('core', 'bridge', 'app'): shutil.rmtree(shared_project/name)
            observed = cli('core', core, '--manifest', manifest, '--expression', 'held', cwd=shared_project, timeout=120)
            require(observed['watch']['value'] == '42' and not observed['inferior_execution'] and
                    'libnex_bridge_' in observed['frames'][observed['selected_frame']]['module'], 'shared core frame/watch differs')
            capsule = root/'shared-core-capsule'
            exported = cli('core', core, '--manifest', manifest, '--export', capsule, '--expression', 'held', cwd=shared_project, timeout=180)
            require(exported['read_after_export'], 'shared capsule was not checked after export')
            original = Path(debug_app['artifact']).parent; original.rename(root/'retained-shared-core-build')
            moved = root/'moved shared core % 🧠'; capsule.rename(moved)
            replay = cli('core', '--capsule', moved, '--expression', 'held', cwd=shared_project, timeout=120)
            require(replay['watch']['value'] == '42' and replay['stop_unchanged'] and not replay['inferior_execution'] and
                    replay['capsule']['dependency_scope'] == 'captured_first_party_and_matching_host_system',
                    'source/image-deleted shared capsule replay differs')
            shared_evidence.update(actual_shared_core=True, moved_capsule=str(moved), exact_watch='42')
        report['evidence']['shared_project_build'] = shared_evidence
        workload_project=root/'native-server-workload'
        shutil.copytree(resources/'examples/server-workload',workload_project)
        workload_definition=workload_project/'workload.json'
        checked_workload=cli('project','--kind','plan','--component','api','--workload',workload_definition,cwd=workload_project)
        require(checked_workload['server_workload']['total_requests']==16 and not (workload_project/'.nex').exists(), 'server workload plan is not readonly')
        auth_path=root/'workload-auth.json'
        workload_token=cli('token','--auth',auth_path,'--user','bench')['token']
        profile_output=root/'server-workload-profile.json'
        environment['NEX_WORKLOAD_TOKEN']=workload_token
        try:
            measured_workload=json.loads(run([compiler,'project','--kind','profile','--component','api','--workload',workload_definition,
                '--profile-output',profile_output,'--json','--','--auth',auth_path,'--database',root/'workload.sqlite','--workers','4'],cwd=workload_project,timeout=300))
        finally:environment.pop('NEX_WORKLOAD_TOKEN',None)
        workload_profile=measured_workload['observation'];metrics=workload_profile['workload']
        expected_workload_hash=hashlib.sha256(workload_definition.read_bytes()).hexdigest()
        require(metrics['ok'] and metrics['completed_requests']==metrics['planned_requests']==16 and metrics['definition_sha256']==expected_workload_hash,
            'workload request expectations/counts/hash differ')
        require(metrics['runner_sha256']==hashlib.sha256((resources/'tools/server_workload.py').read_bytes()).hexdigest(), 'workload helper differs from installed resources')
        saved_workload=json.loads(profile_output.read_text());functions={f['name']:f for f in saved_workload['functions']}
        require(functions['workload_example::core::render']['calls']==16 and functions['workload_example::service::handle']['calls']==16 and
            saved_workload['memory'] and all(m['live']==0 and m['allocations']==m['frees'] for m in saved_workload['memory']), 'native workload attribution/cleanup differs')
        server_artifact=next(a for a in measured_workload['artifacts'] if a['component']=='api')
        require(workload_profile['build_key']==server_artifact['build_key'] and len(json.loads(Path(server_artifact['compilation']).read_text())['owned_images'])==2,
            'workload did not execute its actual shared provider/runtime')
        require(workload_token not in json.dumps(measured_workload) and not (workload_project/'.nex/graph.db').exists(), 'workload leaked runtime credential or synchronized graph')
        report['evidence']['server_workload']={'ok':True,'requests':16,'phase_concurrency':[1,4],'definition_sha256':expected_workload_hash,
            'runner_sha256':metrics['runner_sha256'],'actual_dynamic_provider':True,'profile_identity_checked':True,'owned_cleanup_checked':True,
            'runtime_credential_captured':False,'profile':str(profile_output)}
        workload_task=cli('task','nex.build.json','--kind','init','--component','api','--configuration','measured',cwd=workload_project)
        workload_task['checks']=[{'id':'measure','program':'app','kind':'profile','target':'server','configuration':'measured',
            'entry':'workload_example::service::handle','scenario':'installed SDK captured server workload',
            'workload':'workload.json','workload_hash':expected_workload_hash,'server_workers':4,'timeout_seconds':180,
            'budget':{'max_calls':{'workload_example::core::render':'16'},'max_peak_handles':'100000'}}]
        workload_task['requirements']=[{'id':'measure','text':'Reviewed local request behavior and actual native memory/call budget',
            'targets':['server'],'checks':['measure'],'bindings':[{'program':'app','kind':'function','symbol':'workload_example::service::handle'}]}]
        task_path=workload_project/'task.json';task_path.write_text(json.dumps(workload_task))
        checked_task=cli('task',task_path,'--kind','check',cwd=workload_project)
        require(checked_task['workloads']['measure']['definition_sha256']==expected_workload_hash, 'task lost its reviewed workload identity')
        measured_task=cli('task',task_path,'--kind','run','--directory',root/'server-workload-task-run',cwd=workload_project,timeout=300)
        require(measured_task['ok'], 'captured server workload task failed')
        task_receipt=Path(measured_task['output']);task_profile=json.loads((task_receipt.parent/'artifacts/measure/profile.json').read_text())
        require(task_profile['workload']['completed_requests']==16 and task_profile['workload']['ok'], 'task request observations differ')
        task_inputs=json.loads((task_receipt.parent/'inputs/manifest.json').read_text())['files']
        require('inputs/workloads/measure/workload.json' in task_inputs and 'inputs/resources/tools/server_workload.py' in task_inputs and
            not any('auth.json' in path or 'state.sqlite' in path for path in task_inputs), 'task workload inputs or synthetic-state separation differ')
        shutil.rmtree(workload_project)
        replayed_task=cli('task',task_receipt,'--kind','replay','--directory',root/'server-workload-task-replay',timeout=300)
        require(replayed_task['ok'] and replayed_task['task_hash']==checked_task['task_hash'], 'source-deleted workload task replay failed')
        report['evidence']['server_workload_task']={'ok':True,'source_deleted_replay':True,'actual_dynamic_provider':True,
            'requests_per_measurement':16,'synthetic_runtime_state':True,'operator_credentials_captured':False,'receipt':str(task_receipt),
            'replay':replayed_task['output'],'definition_sha256':expected_workload_hash}

    def source_resources():
        from sdk_source_resources import check_installed_source_resources
        report['evidence']['source_resources']=check_installed_source_resources(
            cli,run,lambda:report['commands'][-1],root,resources,report['doctor']['native_compiler'],compiler=compiler,live=args.live)
        tool=resources/'tests/resource_dependency_source.py'
        require(tool.is_file(),'installed dependent resource acceptance source is missing')
        destination=root/'dependent-resource-source'
        run([sys.executable,'-B',tool,'--compiler',compiler,'--output',destination],timeout=1800)
        dependent=json.loads((destination/'report.json').read_text())
        require(dependent.get('ok') is True and dependent.get('compiler_sha256')==report['compiler_sha256'] and
                dependent.get('actual_producers')==['C11','CPP20'] and len(dependent.get('checks',[]))==37,
                'installed dependent resources differ from actual compiler/source checks')
        report['evidence']['dependent_resource_ffi']={key:True for key in ('ok','native_reference','genuine_previous_C_prefix',
            'hidden_parent_scope_future_channel_closure','physical_parent_quota','cancel_deadline_borrow_fence','source_deleted_replay','client_exclusion')}
        report['evidence']['dependent_resource_ffi'].update(source_checks=37,source_report=dependent,
            source_report_sha256=hashlib.sha256((destination/'report.json').read_bytes()).hexdigest())

    def structured_task_tcp():
        descriptor=cli('describe','--field','tcp_provider')['value']
        pack=json.loads((resources/'llm/language-pack.json').read_text())
        require(descriptor==pack['tcp_provider'] and descriptor['source_support'] and
                descriptor['source_ABI_changed'] is False and descriptor['browser_execution'] is False,
                'installed TCP provider capability differs')
        require(cli('guide','--kind','tcp')['text']==(resources/'docs/tcp-provider.md').read_text(),
                'installed TCP provider guide differs')
        evidence={}
        for key,script in [('source','verify.py'),('delivery','verify_delivery.py')]:
            tool=resources/'tools/tcp_provider'/script;destination=root/('TCP-'+key)
            command=[sys.executable,'-B',tool,'--sdk',sdk,'--output',destination]
            if key=='delivery' and args.package_notices:command+=['--package-notices',args.package_notices.resolve()]
            run(command,timeout=1800)
            evidence[key]=json.loads((destination/'report.json').read_text())
        report['evidence']['structured_task_tcp']=evidence
        validate_task_tcp_evidence(report)

    try:
        actions = [('discovery', discover), ('editor-tools', editor_tools), ('new-project', new_project),
                ('reviewed-failure', baseline_failure), ('graph-repair-import', repair),
                ('backend-agreement', backend_agreement), ('graph-snapshot-recovery', graph_snapshot_recovery),
                ('project-version-boundaries', project_version_boundaries), ('frontend-diagnostics', frontend_diagnostics),
                ('graph-queries', graph_queries), ('string-ranges', string_ranges),
                ('binary-values', binary_values), ('compute-contract', compute_contract), ('model-contract', model_contract), ('native-indexed-pages', native_pages), ('core-reports', core_reports), ('wasm-compute', wasm_compute),
                ('foreign-boundary', foreign_boundary), ('source-resources', source_resources), ('text-files', text_files), ('profile', measured),
                ('structured-task-file-reads', structured_task_file_reads),
                ('structured-task-file-writes', structured_task_file_writes),
                ('structured-task-file-streams', structured_task_file_streams),
                ('structured-task-http', structured_task_http),
                ('structured-task-tcp', structured_task_tcp),
                ('structured-task-profile', structured_task_profile),
                ('structured-task-debug', structured_task_debug),
                ('static-task-providers', static_task_providers),
                ('shared-task-providers', shared_task_providers),
                ('task-provider-profiling', task_provider_profiles),
                ('task-provider-debugging', task_provider_debuggers),
                ('archive-debug-replay-export', sources_and_debug), ('scalar-proof', proof),
                ('traits', traits), ('authenticated-storage', authenticated_storage), ('browser', browser), ('project-build', project_build)]
        require(tuple(name for name, _ in actions) == acceptance_phases(report['doctor']['version']),
                'SDK action registration differs from its workflow phase contract')
        for name, action in actions:
            phase(name, action)
        report['evidence']['dap_shutdown_checks'] = DAP.successful_shutdowns
        report['ok'] = True
        validate_completed_report(report)
    except BaseException as error:
        report['ok'] = False
        report['error'] = type(error).__name__ + ': ' + str(error)
        if report['phases'] and report['phases'][-1]['status'] == 'running':
            report['phases'][-1]['status'] = 'failed'
        raise
    finally:
        report['seconds'] = round(time.monotonic() - started, 3)
        save()
    print(json.dumps({'ok': True, 'report': str(root / 'report.json'), 'host': report['doctor']['host'],
                      'version': report['doctor']['version'], 'live_debugger': args.live,
                      'browser_build': args.browser, 'seconds': report['seconds']}, indent=2), flush=True)


if __name__ == '__main__':
    main()
