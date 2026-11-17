#!/usr/bin/env python3
"""Version2 local Qwen study: explicit030 and bounded compiled references.

The historical engine retains model transport, budgets, raw accounting, source
review, resume rules and candidate actions. This version has its own task/guide
freeze and cannot open a historical version1 campaign for collection.
"""
import importlib.util
from pathlib import Path
import signal

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
BASE=HERE.with_name('llm-campaign-v1')
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result
engine=module('nex_v2_collection_engine',BASE/'collector.py')
engine.__doc__=__doc__
references=module('nex_v2_references',HERE/'references.py')
acceptance=module('nex_v2_acceptance',HERE/'acceptance.py')
engine.a=acceptance
engine.DOCS=[*engine.DOCS,'llm/DETAILED_CODING_RULES.md','llm/QUICK_REFERENCE.md','docs/stdlib.md']
engine.SYSTEM+='''
For NEX only, two additional reference actions are available:
{"action":"guide","kind":"EXACT_AVAILABLE_GUIDE_KIND"}
{"action":"explain","code":"EXACT_COMPILER_DIAGNOSTIC_CODE"}
guide returns at most6144 characters and the exact listed path for read/search
continuation. Available kinds are quick, stdlib, function, trait, match, result,
exception, source-contract, concurrency and task. explain returns the selected
compiler's general diagnostic guidance; its examples are illustrative. Every
reference action counts toward the same frozen request/token/time budget.
'''

OriginalBroker=engine.Broker
class Broker(OriginalBroker):
    def __init__(self,frozen,root,slot,*,deadline=None):
        super().__init__(frozen,root,slot,deadline=deadline)
        if self.language=='nex':
            value=acceptance.decode((Path(frozen['root'])/'resources/compiled-references.json').read_bytes())
            self.reference=references.ReferenceBroker(value,self.docs['llm/SYSTEM_PROMPT.md'],
                self.docs['llm/DETAILED_CODING_RULES.md'])
            self.docs.update(self.reference.docs)
    def action(self,request):
        if isinstance(request,dict) and request.get('action') in ('guide','explain'):
            if self.language!='nex':raise ValueError('compiled references require a NEX trial')
            return self.reference.action(request)
        return super().action(request)
engine.Broker=Broker

def verify(root,*,deep=False):
    root=Path(root).resolve(strict=True)
    value=acceptance.decode(engine.checked_file(root/'freeze.json'))
    if (value.get('schema')!='nex.local-collection/2' or value.get('study_protocol_version')!=2 or
            value.get('source_language')!='0.30'):
        raise ValueError('version2 requires its own frozen030 campaign; historical trials are unchanged')
    if (root/'freeze.sha256').read_text().strip()!=engine.sha(root/'freeze.json'):
        raise ValueError('collection freeze changed')
    for row in value['pinned_files']:
        path=Path(row['path']);info=path.stat()
        if (path.is_symlink()!=row['symlink'] or str(path.resolve())!=row['resolved'] or
                [info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns]!=[row[k]for k in ('dev','ino','bytes','mtime_ns')] or
                (deep and engine.sha(path)!=row['sha256'])):
            raise ValueError('frozen input changed: '+str(path))
    engine.r.verify_weights(root/'weights.json')
    for row in value['host']['files']:
        path=Path(row['path']);info=path.stat()
        if (path.is_symlink()!=row['symlink'] or str(path.resolve())!=row['resolved'] or
                [info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns]!=[row[k]for k in ('dev','ino','bytes','mtime_ns')]):
            raise ValueError('selected runtime/default artifact changed since freeze')
    return value
engine.verify=verify

original_freeze=engine.freeze
def freeze(output,*,compiler,cpp,weights,lm_home,runtime,pilot=False):
    # Everything is frozen before the first model request. A failed preparation
    # retains its partial new directory; it never rewrites an earlier campaign.
    value=original_freeze(output,compiler=compiler,cpp=cpp,weights=weights,
        lm_home=lm_home,runtime=runtime,pilot=pilot)
    output=Path(output).resolve()
    (output/'freeze.json').rename(output/'preparation-freeze.json')
    (output/'freeze.sha256').rename(output/'preparation-freeze.sha256')
    compiled=references.snapshot(compiler,ROOT)
    documents=acceptance.decode((output/'resources/documents.json').read_bytes())
    if any((ROOT/name).read_text(encoding='utf-8')!=documents[name] for name in engine.DOCS):
        raise ValueError('source document changed during preparation')
    if any(compiled['identity'][key]!=value['compiler_index'][key] for key in ('compiler_build','descriptor_hash')):
        raise ValueError('compiled references belong to another frozen compiler')
    if compiled['compiler_sha256']!=engine.sha(compiler):
        raise ValueError('selected compiler changed during preparation')
    for kind,name in [('quick','llm/QUICK_REFERENCE.md'),('stdlib','docs/stdlib.md')]:
        if compiled['guides'][kind]['text']!=documents[name]:
            raise ValueError('compiled guide differs from frozen source document: '+name)
    if '0.30' not in acceptance.decode((output/'resources/descriptor.json').read_bytes()).get('project_languages',[]):
        raise ValueError('selected compiler does not advertise explicit030')
    path=output/'resources/compiled-references.json';acceptance.save(path,compiled)
    value.update(schema='nex.local-collection/2',study_protocol_version=2,source_language='0.30',collector_policy_version=5,
        task_contracts='version1 behavioral/source contracts retained byte-for-byte; explicit030 execution',
        reference_policy='frozen compiled guide/explanation actions, charged as ordinary requests',
        context_policy='policy5: version2 compact common contract, detailed rules retained; complete prior action/tool transcript',
        protocol='experiments/quality/llm-campaign-v2/protocol.md')
    for slot in value['order']:slot['id']='v2-'+slot['id']
    extra=[*HERE.glob('*.py'),HERE/'tasks.json',HERE/'protocol.md',HERE/'README.md',path,
        *(ROOT/name for name in engine.DOCS)]
    for item in sorted(set(extra)):
        info=item.stat();value['pinned_files'].append({'path':str(item.absolute()),'resolved':str(item.resolve()),
            'symlink':item.is_symlink(),'sha256':engine.sha(item),'dev':info.st_dev,'ino':info.st_ino,
            'bytes':info.st_size,'mtime_ns':info.st_mtime_ns})
    acceptance.save(output/'freeze.json',value)
    (output/'freeze.sha256').write_text(engine.sha(output/'freeze.json')+'\n')
    verify(output,deep=True)
    return value
engine.freeze=freeze

if __name__=='__main__':
    def interrupted(signum,frame):raise InterruptedError('collection interrupted by SIGTERM')
    signal.signal(signal.SIGTERM,interrupted)
    raise SystemExit(engine.main())
