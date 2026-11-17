"""Public compiler-served references for a new study; no model inference."""
import hashlib
import importlib.util
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('nex_v3_reference_base',HERE.with_name('llm-campaign-v2')/'references.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
GUIDE_PATHS={
    'quick':'llm/QUICK_REFERENCE.md','stdlib':'docs/stdlib.md',
    'function':'docs/functions.md','trait':'docs/traits.md','match':'docs/matching.md',
    'result':'docs/error-propagation.md','exception':'docs/exceptions.md',
    'source-contract':'docs/source-contracts.md','concurrency':'docs/concurrency-design.md',
    'task':'docs/tasks.md','tasks-runtime':'docs/tasks-runtime-design.md',
    'bytes':'docs/bytes.md','bytes-construction':'docs/bytes-construction.md',
    'list-build':'docs/list-construction.md','text-construction':'docs/text-construction.md',
    'references':'docs/references030.md'}
base.GUIDES=tuple(GUIDE_PATHS)
REVIEW_BYTES=16384

def snapshot(compiler,resources):
    result=base.snapshot(compiler,resources)
    for kind,path in GUIDE_PATHS.items():
        if result['guides'][kind]['text']!=(Path(resources)/path).read_text(encoding='utf-8'):
            raise ValueError('compiler guide differs from the selected public resource: '+kind)
    result.update(schema='nex.llm-compiled-references/3',document_paths=GUIDE_PATHS)
    return result

def review_references(compiled,baselines):
    """Same general reference packet for every task of each language; no answers."""
    if compiled.get('schema')!='nex.llm-compiled-references/3':
        raise ValueError('version3 compiled references required')
    selected=[]
    for kind,marker in [('quick',None),('tasks-runtime','<!-- bounded-source-task-entry-end -->'),
                         ('concurrency','# Retained source language')]:
        guide=compiled['guides'][kind];text=guide['text']
        if marker:
            if marker not in text:raise ValueError('bounded public guide entry marker missing: '+kind)
            text=text.split(marker,1)[0].rstrip()+'\n'
        selected.append({'kind':kind,'path':GUIDE_PATHS[kind],
            'complete_guide_sha256':hashlib.sha256(guide['text'].encode()).hexdigest(),
            'text':text,'fragment_sha256':hashlib.sha256(text.encode()).hexdigest()})
    result={'nex':{'source_language':'0.30','compiler_build':compiled['identity']['compiler_build'],
                   'descriptor_hash':compiled['identity']['descriptor_hash'],'documents':selected}}
    for language in ('cpp','python'):
        text=baselines[language]
        result[language]={'documents':[{'path':'reference.md','text':text,
            'fragment_sha256':hashlib.sha256(text.encode()).hexdigest()}]}
    if any(len(json.dumps(value,ensure_ascii=False).encode())>REVIEW_BYTES for value in result.values()):
        raise ValueError('review reference packet exceeds the frozen byte ceiling')
    return result

class ReferenceBroker(base.ReferenceBroker):
    def __init__(self,frozen,core,detailed):
        if frozen.get('schema')!='nex.llm-compiled-references/3' or frozen.get('document_paths')!=GUIDE_PATHS:
            raise ValueError('version3 public document aliases required')
        super().__init__(frozen,core,detailed)
        self.docs.update({path:self.docs['guide:'+kind] for kind,path in GUIDE_PATHS.items()})
