"""Capture bounded compiled references for the version2 local study; no model calls."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

GUIDES = ('quick', 'stdlib', 'function', 'trait', 'match', 'result', 'exception',
          'source-contract', 'concurrency', 'task')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def snapshot(compiler, resources):
    compiler, resources = Path(compiler).resolve(), Path(resources).resolve()
    pin = digest(compiler)
    environment = {**os.environ, 'NEX_RESOURCE_DIR': str(resources), 'PYTHONDONTWRITEBYTECODE': '1'}
    def cli(*args):
        result = subprocess.run([compiler, *args, '--json'], cwd=resources,
                                env=environment, capture_output=True, text=True, check=True, timeout=30)
        return json.loads(result.stdout)
    identity = cli('describe', '--kind', 'index')
    help = cli('help', 'guide')
    known = next(o['known_values'] for o in help['options'] if o['name'] == '--kind')
    if not set(GUIDES) <= set(known):
        raise ValueError('requested guide is not advertised by this compiler')
    guides = {kind: cli('guide', '--kind', kind) for kind in GUIDES}
    if any(g['kind'] != kind or g['schema'] != 'nex.guide/1' for kind, g in guides.items()):
        raise ValueError('compiled guide identity differs')
    index = cli('explain', '--kind', 'index')
    if index['compiler_build'] != identity['compiler_build'] or index['descriptor_hash'] != identity['descriptor_hash']:
        raise ValueError('diagnostic catalogue belongs to another compiler')
    explanations = {code: cli('explain', code) for code in index['codes']}
    if any(e['compiler_build'] != identity['compiler_build'] or e['descriptor_hash'] != identity['descriptor_hash'] or
           e['catalogue_hash'] != index['catalogue_hash'] for e in explanations.values()):
        raise ValueError('diagnostic explanation belongs to another compiler/catalogue')
    if digest(compiler) != pin:
        raise ValueError('compiler changed while references were captured')
    return {'schema': 'nex.llm-compiled-references/2', 'compiler_sha256': pin,
            'identity': identity, 'guides': guides, 'explanations': explanations,
            'model_calls': 0}


class ReferenceBroker:
    """Read the version2 frozen references; source actions stay with the collection engine."""
    def __init__(self, frozen, core, detailed):
        self.frozen = frozen
        self.docs = {'guide:' + kind: value['text'] for kind, value in frozen['guides'].items()}
        self.docs.update({'llm/SYSTEM_PROMPT.md': core, 'llm/DETAILED_CODING_RULES.md': detailed,
                          'llm/QUICK_REFERENCE.md': self.docs['guide:quick'],
                          'docs/stdlib.md': self.docs['guide:stdlib']})

    def action(self, request):
        if not isinstance(request, dict) or not isinstance(request.get('action'), str):
            raise ValueError('one reference action is required')
        action = request['action']
        keys = {'guide': {'action', 'kind'}, 'explain': {'action', 'code'},
                'read': {'action', 'path', 'offset', 'limit'}, 'search': {'action', 'path', 'query'}}
        if action not in keys or set(request) != keys[action]:
            raise ValueError('unsupported reference action/fields')
        if action == 'guide':
            kind = request['kind']
            if type(kind) is not str or kind not in self.frozen['guides']:
                raise ValueError('guide is not in this frozen study scope')
            value = self.frozen['guides'][kind]
            text = value['text']
            return {'schema': 'nex.broker-guide/2', 'kind': kind, 'path': 'guide:' + kind,
                    'compiler_build': self.frozen['identity']['compiler_build'], 'hash': value['hash'],
                    'text': text[:6144], 'characters': len(text), 'truncated': len(text) > 6144}
        if action == 'explain':
            code = request['code']
            if type(code) is not str or code not in self.frozen['explanations']:
                raise ValueError('diagnostic is not covered by the selected compiled catalogue')
            # Keep the compiler's non-context-specific and illustrative-example labels.
            return self.frozen['explanations'][code]
        path = request['path']
        if type(path) is not str or path not in self.docs:
            raise ValueError('document is not in this frozen study scope')
        text = self.docs[path]
        if action == 'read':
            offset, limit = request['offset'], request['limit']
            if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 4096:
                raise ValueError('invalid character window')
            return {'path': path, 'offset': offset, 'text': text[offset:offset + limit], 'characters': len(text)}
        query = request['query']
        if type(query) is not str or not 1 <= len(query) <= 128 or '\0' in query:
            raise ValueError('invalid literal document query')
        matches, offset = [], 0
        for number, line in enumerate(text.splitlines(keepends=True), 1):
            if query.casefold() in line.casefold():
                matches.append({'line': number, 'offset': offset, 'text': line.rstrip()[:600]})
            offset += len(line)
        return {'path': path, 'query': query, 'matches': matches[:8], 'total_matches': len(matches)}
