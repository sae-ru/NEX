#!/usr/bin/env python3
"""Version3: public task/bytes guides and independent normative review context.

No paid APIs, changed task answers, expanded execution grants or free requests.
Historical protocol1/2 campaigns remain immutable and are rejected here.
"""
import importlib.util
import json
from pathlib import Path
import signal

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result
v2=module('nex_v3_previous_engine',HERE.with_name('llm-campaign-v2')/'collector.py')
references=module('nex_v3_references',HERE/'references.py')
v2.references=references
engine=v2.engine;acceptance=v2.acceptance;Broker=v2.Broker
sdk_toolchain=module('nex_v3_sdk_toolchain',HERE/'sdk_toolchain.py')
original_check=acceptance.check

def check(candidate, task, language, output, **kwargs):
    if language == 'nex' and kwargs.get('isolate'):
        kwargs['sandbox_factory'] = sdk_toolchain.MacSDKBuildSandbox
    return original_check(candidate, task, language, output, **kwargs)
acceptance.check=check

engine.__doc__=__doc__
engine.DOCS=list(dict.fromkeys([*engine.DOCS,*references.GUIDE_PATHS.values()]))
engine.SYSTEM+='''
Version3 adds guide kinds tasks-runtime, bytes, bytes-construction, list-build,
text-construction and references. tasks-runtime describes source scheduling;
task describes acceptance JSON. Canonical public guide document paths are also
listed for bounded read/search. All these actions keep the original budgets.
'''
engine.REVIEW_SYSTEM+='''
Use the host-supplied language_reference for the selected language's semantics.
Do not replace its builtin contracts with assumptions from other languages.
It is general public reference material, not a solution or a behavior-test result.
'''

def verify(root,*,deep=False):
    root=Path(root).resolve(strict=True)
    value=acceptance.decode(engine.checked_file(root/'freeze.json'))
    if (value.get('schema')!='nex.local-collection/3' or value.get('study_protocol_version')!=3
        or value.get('source_language')!='0.30'):
        raise ValueError('version3 requires a new freeze; historical campaigns remain unchanged')
    if (root/'freeze.sha256').read_text().strip()!=engine.sha(root/'freeze.json'):
        raise ValueError('collection freeze changed')
    for row in value['pinned_files']:
        path=Path(row['path']);info=path.stat()
        if (path.is_symlink()!=row['symlink'] or str(path.resolve())!=row['resolved']
            or [info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns]!=[row[k] for k in ('dev','ino','bytes','mtime_ns')]
            or (deep and engine.sha(path)!=row['sha256'])):
            raise ValueError('frozen input changed: '+str(path))
    engine.r.verify_weights(root/'weights.json')
    for row in value['host']['files']:
        path=Path(row['path']);info=path.stat()
        if (path.is_symlink()!=row['symlink'] or str(path.resolve())!=row['resolved']
            or [info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns]!=[row[k] for k in ('dev','ino','bytes','mtime_ns')]):
            raise ValueError('selected runtime/default artifact changed since freeze')
    if engine.sha(root/'resources/review-references.json')!=value['review_reference_sha256']:
        raise ValueError('frozen review references changed')
    if value.get('portable_sdk') and str(sdk_toolchain.apple_macos_sysroot())!=value['portable_sdk']['apple_sysroot']:
        raise ValueError('selected Apple macOS SDK changed since freeze')
    return value
engine.verify=verify

def freeze(output,**kwargs):
    value=v2.freeze(output,**kwargs)
    output=Path(output).resolve()
    (output/'freeze.json').rename(output/'preparation-v2-freeze.json')
    (output/'freeze.sha256').rename(output/'preparation-v2-freeze.sha256')
    compiled=acceptance.decode((output/'resources/compiled-references.json').read_bytes())
    review=references.review_references(compiled,engine.BASELINE)
    path=output/'resources/review-references.json';acceptance.save(path,review)
    value.update(schema='nex.local-collection/3',study_protocol_version=3,collector_policy_version=6,
        protocol='experiments/quality/llm-campaign-v3/protocol.md',
        review_reference_sha256=engine.sha(path),review_reference_utf8_bytes_max=references.REVIEW_BYTES,
        review_system_prompt=engine.REVIEW_SYSTEM,
        context_policy='policy6: version2 full accounting plus public task/bytes/reference guides and canonical document aliases',
        source_review_policy='fresh stateless review with the same frozen per-language public reference packet for every task; all added input tokens counted')
    portable_inputs=set()
    descriptor=sdk_toolchain.sdk_manifest(value['compiler'])
    if descriptor:
        sdk=sdk_toolchain.PortableSDKToolchain(value['compiler'],descriptor)
        portable_inputs=sdk.frozen_files()
        value['portable_sdk']={'manifest':str(descriptor),'sha256':engine.sha(descriptor),
                               'native_resources':str(sdk.resources),'apple_sysroot':str(sdk.apple_sysroot),
                               'frozen_files':len(portable_inputs)}
    for slot in value['order']:
        if not slot['id'].startswith('v2-'):raise ValueError('unexpected preparation trial identity')
        slot['id']='v3-'+slot['id'][3:]
    for item in sorted(set(HERE.glob('*.py')) | {HERE/'protocol.md',HERE/'README.md',path} | portable_inputs):
        info=item.stat();value['pinned_files'].append({'path':str(item.absolute()),'resolved':str(item.resolve()),
            'symlink':item.is_symlink(),'sha256':engine.sha(item),'dev':info.st_dev,'ino':info.st_ino,
            'bytes':info.st_size,'mtime_ns':info.st_mtime_ns})
    acceptance.save(output/'freeze.json',value)
    (output/'freeze.sha256').write_text(engine.sha(output/'freeze.json')+'\n')
    verify(output,deep=True)
    return value
engine.freeze=freeze

original_review=engine.local_review
def local_review(broker,directory,client,instance,number,deadline):
    root=Path(broker.frozen['root']);path=root/'resources/review-references.json'
    if engine.sha(path)!=broker.frozen['review_reference_sha256']:
        raise ValueError('review references do not belong to this freeze')
    reference=acceptance.decode(path.read_bytes())[broker.language]
    class ReferencedClient:
        @property
        def timeout(self):return client.timeout
        @timeout.setter
        def timeout(self,value):client.timeout=value
        def chat(self,instance,system,prompt,output,**kwargs):
            payload=json.loads(prompt);payload['language_reference']=reference
            prompt=json.dumps(payload,ensure_ascii=False)
            if len((system+prompt).encode())>engine.LIMITS['prompt_utf8_bytes']:
                raise ValueError('source review with references exceeds the frozen byte limit')
            return client.chat(instance,system,prompt,output,**kwargs)
    review=original_review(broker,directory,ReferencedClient(),instance,number,deadline)
    review['language_reference_sha256']=acceptance.sha(json.dumps(reference,sort_keys=True,ensure_ascii=False).encode())
    engine.save(Path(directory)/'source-review.json',review)
    return review
engine.local_review=local_review

if __name__=='__main__':
    def interrupted(signum,frame):raise InterruptedError('collection interrupted by SIGTERM')
    signal.signal(signal.SIGTERM,interrupted)
    raise SystemExit(engine.main())
