#!/usr/bin/env python3
"""Opt-in JSON Schema gate on fresh current compiler authoring artifacts.

Requires developer-only jsonschema>=4.23. No native build or model calls.
"""
import argparse
import copy
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback

# Keep tests/numbers.py out of jsonschema's decimal/stdlib imports.
TESTS = Path(__file__).resolve().parent
sys.path = [p for p in sys.path if Path(p or os.getcwd()).resolve() != TESTS]
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

REPO = TESTS.parent
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('compiler', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--schema-root', type=Path, default=REPO/'llm')
    parser.add_argument('--language', default='0.28')
    args = parser.parse_args()
    compiler = args.compiler.resolve(strict=True)
    schemas = args.schema_root.resolve(strict=True)
    output = args.output.resolve()
    if output.exists() or output == schemas or schemas in output.parents:
        parser.error('--output must be a new directory outside schema inputs')
    output.mkdir(parents=True)
    report = {'schema': 'nex.current-schema-contracts/1', 'ok': False,
              'state': 'running', 'compiler': str(compiler),
              'compiler_sha256': sha(compiler), 'schema_root': str(schemas),
              'validator_version': importlib.metadata.version('jsonschema'),
              'commands': [], 'positive': [], 'negative': [], 'failures': [],
              'native_execution': False, 'models_called': False,
              'installed_SDK_accepted': False}
    source_inputs = {}
    def save():
        temporary = output/'report.tmp'
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
        temporary.replace(output/'report.json')
    def command(label, arguments, cwd):
        result = subprocess.run([str(compiler), *map(str, arguments), '--json'],
            cwd=cwd, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'},
            stdin=subprocess.DEVNULL, capture_output=True, timeout=30)
        (output/(label+'.stdout')).write_bytes(result.stdout)
        (output/(label+'.stderr')).write_bytes(result.stderr)
        report['commands'].append({'label': label,
            'arguments': [str(compiler), *map(str, arguments), '--json'],
            'exit_code': result.returncode, 'stdout_sha256': sha(output/(label+'.stdout')),
            'stderr_sha256': sha(output/(label+'.stderr'))})
        save()
        if result.returncode:
            raise RuntimeError(label+' failed; inspect retained stdout/stderr')
        return json.loads(result.stdout)
    try:
        save()
        index = command('compiler-index', ['describe', '--kind', 'index'], output)
        if index['language'] != args.language:
            raise ValueError('selected compiler differs from requested current language')
        report.update(language=index['language'], toolchain=index['toolchain'],
                      compiler_build=index['compiler_build'], descriptor_hash=index['descriptor_hash'])
        documents = {p.name: json.loads(p.read_bytes()) for p in sorted(schemas.glob('*.schema.json'))}
        source_inputs = {name: sha(schemas/name) for name in documents}
        resources = []
        for name, document in documents.items():
            Draft202012Validator.check_schema(document)
            resource = Resource.from_contents(document)
            for uri in [document.get('$id', (schemas/name).as_uri()), (schemas/name).as_uri(),
                        'https://nex.local/schemas/'+name, 'https://nex.dev/schemas/'+name]:
                resources.append((uri, resource))
        registry = Registry().with_resources(resources)
        report['schema_documents_meta_valid'] = len(documents)
        project = output/'project'
        command('init', ['init', project], output)
        manifest = json.loads((project/'nex.json').read_bytes())
        if manifest['language'] != args.language:
            raise ValueError('initialized project did not select the actual language')
        entry = manifest['entry']
        samples = {'project': manifest}
        for label, arguments in [
                ('editor-analysis', ['analyze', entry]),
                ('editor-references', ['analyze', entry, '--references']),
                ('editor-identifiers', ['analyze', entry, '--details']),
                ('check', ['check']),
                ('operations', ['operations', '--symbol', 'main']),
                ('task', ['task', entry, '--kind', 'init'])]:
            value = command(label, arguments, project)
            if label != 'check':
                samples[label] = value
        for name, value in samples.items():
            (output/(name+'.sample.json')).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
            validator = Draft202012Validator(documents[name+'.schema.json'], registry=registry)
            errors = list(validator.iter_errors(value))
            if errors:
                report['failures'].append({'artifact': name, 'errors': [
                    {'path': e.json_path, 'message': e.message[:1000]} for e in errors[:8]]})
            else:
                report['positive'].append(name)
            # These are invalid copies of actual artifacts, not replayed old SDKs.
            for language in ['0.29', '0.99', True]:
                changed = copy.deepcopy(value)
                changed['language'] = language
                rejected = not validator.is_valid(changed)
                report['negative'].append({'artifact': name, 'invalid_language': language,
                                           'rejected': rejected})
                if not rejected:
                    report['failures'].append({'artifact': name, 'invalid_language_accepted': language})
        if len(report['positive']) != 6 or len(report['negative']) != 18 or report['failures']:
            raise RuntimeError('current artifact/schema contract failed; inspect report.json')
        if sha(compiler) != report['compiler_sha256'] or any(sha(schemas/name) != digest for name, digest in source_inputs.items()):
            raise RuntimeError('compiler or schema inputs changed during validation')
        report.update(ok=True, state='passed', inputs_unchanged=True)
    except BaseException as error:
        report.update(state='failed', error=repr(error), traceback=traceback.format_exc())
    finally:
        report['schema_input_sha256'] = source_inputs
        save()
    print(json.dumps({key: report.get(key) for key in ['ok', 'state', 'language', 'toolchain', 'error']}))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
