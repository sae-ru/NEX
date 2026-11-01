#!/usr/bin/env python3
"""Validate real compiler/editor/debug/project artifacts against the LLM schemas.

Developer gate: use Python with jsonschema>=4.23. No validator is linked into
NEX applications. Generated binaries and captured test projects are temporary.
"""
import argparse
import copy
import hashlib
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

# tests/numbers.py must not shadow the standard numbers module imported by
# decimal/jsonschema. Load external dependencies before exposing test modules.
TESTS = Path(__file__).resolve().parent
sys.path = [p for p in sys.path if Path(p or os.getcwd()).resolve() != TESTS]
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
sys.path.insert(0, str(TESTS))

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('nex', type=Path)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--retained-nex', type=Path)
args = parser.parse_args()
REPO = Path(__file__).resolve().parents[1]
COMPILER = args.nex.resolve()
OUTPUT = args.output.resolve()
OUTPUT.mkdir(parents=True, exist_ok=False)
sys.argv = [str(Path(__file__)), str(COMPILER)]
import support as harness

NAMES = (
    'debug-frame', 'debug-frame-v2', 'editor-analysis', 'editor-identifiers',
    'editor-references', 'frontend-diagnostics', 'graph-identity', 'graph-query',
    'native-diagnostics', 'operations', 'project-capture', 'project-package',
    'verification', 'wasm-module', 'task-debug-frame', 'task-debug-expression',
    'task-debug-source-union', 'provider-task-debug-frame',
    'provider-task-debug-expression', 'provider-task-debug-view',
    'native-source-error-task-provider', 'native-stream-task-provider', 'task',
)
raw_documents = {p.name: p.read_bytes() for p in (REPO/'llm').glob('*.schema.json')}
documents = {name: json.loads(raw) for name, raw in raw_documents.items()}
resources = []
for filename, document in documents.items():
    Draft202012Validator.check_schema(document)
    resource = Resource.from_contents(document)
    for uri in [document.get('$id', (REPO/'llm'/filename).as_uri()), (REPO/'llm'/filename).as_uri(),
                'https://nex.local/schemas/'+filename, 'https://nex.dev/schemas/'+filename]:
        resources.append((uri, resource))
registry = Registry().with_resources(resources)
validators = {name: Draft202012Validator(documents[name+'.schema.json'], registry=registry) for name in NAMES}


def tags(node, document):
    if '$ref' in node:
        ref = node['$ref']
        if ref.startswith('#/'):
            target = document
            for part in ref[2:].split('/'):
                target = target[part.replace('~1', '/').replace('~0', '~')]
            return tags(target, document)
        return set()
    kind = node.get('properties', {}).get('schema', {})
    result = {kind['const']} if 'const' in kind else set(kind.get('enum', []))
    for key in ('oneOf', 'anyOf', 'allOf'):
        for child in node.get(key, []):
            result.update(tags(child, document))
    return result


by_tag = {}
for name, validator in validators.items():
    for tag in tags(validator.schema, validator.schema):
        by_tag.setdefault(tag, []).append(name)
counts = {name: 0 for name in NAMES}
errors = []
seen = set()
read_paths = {}
samples = {}
variants = {name: {} for name in NAMES}
original_run = subprocess.run
compiler_paths = {COMPILER}
retained_schema_path = REPO/'llm/native-stream-task-provider.schema.json'
retained_schema_sha256 = hashlib.sha256(retained_schema_path.read_bytes()).hexdigest()


def validate(value, origin, only=None):
    if isinstance(value, dict):
        candidates = [only] if only else by_tag.get(value.get('schema'), [])
        if candidates:
            raw = json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
            key = (tuple(candidates), hashlib.sha256(raw).hexdigest())
            if key not in seen:
                seen.add(key)
                checked = [(name, list(validators[name].iter_errors(value))) for name in candidates]
                passed = [name for name, failures in checked if not failures]
                if not passed:
                    number = len(errors)
                    (OUTPUT/('invalid-'+str(number)+'.json')).write_bytes(raw+b'\n')
                    errors.append({'origin': origin, 'schema': value.get('schema'),
                                   'candidates': {name: [e.json_path+': '+e.message[:500] for e in failures[:8]]
                                                  for name, failures in checked}})
                for name in passed:
                    counts[name] += 1
                    variant = value.get('schema', '')+':'+str(value.get('mode', ''))
                    variants[name][variant] = variants[name].get(variant, 0)+1
                    samples.setdefault(name, value)
        for child in value.values():
            validate(child, origin)
    elif isinstance(value, list):
        for child in value:
            validate(child, origin)


def document(path, origin):
    path = Path(path)
    try:
        path = path.resolve()
        if not path.is_file() or path.stat().st_size > 16*1024*1024:
            return
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if read_paths.get(path) == digest:
            return
        read_paths[path] = digest
        value = json.loads(raw)
    except (OSError, ValueError, UnicodeError):
        return
    validate(value, origin+': '+str(path.name))


def references(value, origin):
    if isinstance(value, dict):
        for child in value.values():
            references(child, origin)
    elif isinstance(value, list):
        for child in value:
            references(child, origin)
    elif isinstance(value, str) and value.endswith('.json') and Path(value).is_absolute():
        document(value, origin)
        if Path(value).name == 'receipt.json':
            for capture in (Path(value).parent/'inputs/projects').glob('*.json'):
                document(capture, origin)


def run(command, *positional, **options):
    result = original_run(command, *positional, **options)
    if not isinstance(command, (list, tuple)) or not command:
        return result
    executable = Path(str(command[0])).resolve()
    is_compiler = executable in compiler_paths
    if not is_compiler and executable.name != 'lldb':
        return result
    # Descriptor fields name schemas; they are declarations, not instances of
    # those schemas. Only executable responses/captures enter this artifact gate.
    if is_compiler and len(command)>1 and command[1] in ('describe','doctor','guide'):
        return result
    stdout = result.stdout
    if not isinstance(stdout, str):
        return result
    values = []
    try:
        values.append(json.loads(stdout))
    except ValueError:
        if executable.name == 'lldb':
            for line in stdout.splitlines():
                if line.startswith('{'):
                    try:
                        values.append(json.loads(line))
                    except ValueError:
                        pass
    origin = ' '.join(map(str, command[:3]))
    for value in values:
        validate(value, origin)
        if result.returncode == 0:
            references(value, origin)
    if is_compiler and result.returncode == 0:
        for option in ('--contracts',):
            if option in command:
                path = Path(command[command.index(option)+1])
                document(path if path.is_absolute() else Path(options.get('cwd', '.'))/path, origin)
        if len(command)>1 and command[1]=='inspect':
            document(command[2], origin)
    return result


class AdditionalArtifacts(harness.ToolchainCase):
    def capture(self, session, symbol, expression):
        manifest=json.loads(Path(session['manifest']).read_text())
        argv=[os.environ.get('NEX_LLDB','lldb'),'--no-lldbinit','--batch',session['launch']['program']]
        for command in ['settings set target.disable-aslr false',
                        'command script import '+json.dumps(manifest['formatter']),
                        'nex-load-debug '+json.dumps(session['manifest'])+' --compiler '+json.dumps(str(COMPILER)),
                        'nex-task-break function '+symbol,'run','nex-frame '+expression,
                        'nex-eval '+expression,'breakpoint disable','continue']:
            argv += ['-o',command]
        result=subprocess.run(argv,cwd=self.root,capture_output=True,text=True,timeout=120)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        return result.stdout

    def test_throw_operations_and_real_task_frame(self):
        self.source('''module schema_task;
fn leaf(value:i64)->i64 !{task}{task_yield();return value+1;}
fn caught()->i64{try{throw("USER","data");}catch(code,message){return 42;}}
fn main()->unit !{io,task}{print(leaf(41));}
''')
        self.cli('check')
        self.cli('operations','--symbol','caught')
        session=self.cli('debug','--kind','nex-dap')
        self.assertIn('"nex.debug-frame/3"',self.capture(session,'schema_task::leaf','value'))

    def test_current_provider_records_and_native_package(self):
        for name in ('core','app'):
            (self.root/name).mkdir()
        (self.root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':harness.CURRENT_LANGUAGE,'entry':'app/main.nex'}), newline="\n")
        (self.root/'core/main.nex').write_text('module core;pub fn answer(value:i64)->i64 !{task,throw}{task_yield();try{throw("USER","data");}catch(code,message){return value+1;}}', newline="\n")
        (self.root/'app/main.nex').write_text('module app;import "../core/main.nex" as c;fn main()->unit !{io,task,throw}{print(c::answer(41));}', newline="\n")
        for edge in ('static','dynamic'):
            architecture={'schema':'nex.project-build/1','default_configuration':'debug',
                'configurations':{p:{'profile':p} for p in ('debug','profile')},'components':{
                    'core':{'kind':'static_library' if edge=='static' else 'shared_library','root':'core','entry':'core/main.nex','entry_function':'answer'},
                    'app':{'kind':'executable','root':'app','entry':'app/main.nex','dependencies':{'core':edge}}}}
            (self.root/'nex.build.json').write_text(json.dumps(architecture), newline="\n")
            for kind,extra in [('build',[]),('build',['--configuration','profile']),('debug',['--adapter','nex-dap'])]:
                built=self.cli('project','--kind',kind,'--component','app',*extra,timeout=240)
                for artifact in built['artifacts']:
                    document(Path(artifact['artifact']).parent/'task-provider.json','current '+edge+' '+kind)
                if kind=='debug':
                    self.assertIn('"nex.debug-frame/4"',self.capture(built['observation'],'core::answer','value'))
            if edge=='static':
                self.cli('project','--kind','package','--component','app','--directory',self.root/'package',timeout=240)

    def test_retained_provider_record_is_not_retagged_as_025(self):
        if not args.retained_nex:
            return
        old=args.retained_nex.resolve()
        environment={**os.environ,'NEX_RESOURCE_DIR':str(old.parent.parent/'share/nex')}
        for name in ('core','app'):
            (self.root/name).mkdir()
        (self.root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.24','entry':'app/main.nex'}), newline="\n")
        (self.root/'core/main.nex').write_text('module core;pub fn answer(value:i64)->i64 !{task}{task_yield();return value+1;}', newline="\n")
        (self.root/'app/main.nex').write_text('module app;import "../core/main.nex" as c;fn main()->unit !{io,task}{print(c::answer(41));}', newline="\n")
        architecture={'schema':'nex.project-build/1','default_configuration':'debug','configurations':{'debug':{'profile':'debug'}},'components':{
            'core':{'kind':'static_library','root':'core','entry':'core/main.nex','entry_function':'answer'},
            'app':{'kind':'executable','root':'app','entry':'app/main.nex','dependencies':{'core':'static'}}}}
        (self.root/'nex.build.json').write_text(json.dumps(architecture), newline="\n")
        result=original_run([str(old),'project','--kind','build','--component','app','--json'],cwd=self.root,env=environment,capture_output=True,text=True,timeout=240)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        built=json.loads(result.stdout)
        for artifact in built['artifacts']:
            record=json.loads((Path(artifact['artifact']).parent/'task-provider.json').read_text())
            self.assertEqual((record['schema'],record['language']),('nex.native-task-provider/8','0.24'))
            validate(record,'actual retained SDK024 record',only='native-stream-task-provider')
            self.assertFalse(validators['native-source-error-task-provider'].is_valid(record))
            renamed=copy.deepcopy(record);renamed['language']='0.26'
            self.assertFalse(validators['native-stream-task-provider'].is_valid(renamed))
        app=next(row['artifact'] for row in built['artifacts'] if row['component']=='app')
        result=original_run([app],capture_output=True,text=True,timeout=30)
        self.assertEqual((result.returncode,result.stdout),(0,'42\n'),result.stderr)


selected = {
    'graph_identities': ['GraphIdentities.test_declared_type_and_module_ids_survive_edits_and_old_revisions',
                         'GraphIdentities.test_same_graph_reconciles_every_entity_kind_without_rewriting_local_ids'],
    'graph_queries': ['GraphQueries.test_literal_discovery_names_sources_and_fields',
                      'GraphQueries.test_dependency_radius_minimum_distances_and_explicit_boundary'],
    'lsp': ['LanguageServer.test_details_preserve_both_legacy_projections_and_classify_exact_words'],
    'frontend_diagnostics': ['FrontendDiagnostics.test_checker_error_uses_uncommitted_candidate_instead_of_physical_source'],
    'native_diagnostics': ['NativeDiagnostics.test_nested_calls_ltr_short_circuit_and_profile_preserve_the_actual_failure'],
    'numbers': ['NumericDebug.test_demand_reads_only_selected_float_payloads',
                'NumericDebug.test_full_scalar_aggregate_closure_watches_are_finite_and_exact'],
    'verification': ['Verification.test_bundled_proof_snapshots_and_task_intent_are_current'],
    'wasm': ['Wasm.test_bool_and_unit_abi_accept_only_checked_input_types'],
    'project_tasks': ['ProjectTasks.test_real_binary_run_tests_profile_artifacts_and_source_deleted_replay'],
}
suite=unittest.TestSuite()
for module, names in selected.items():
    spec=importlib.util.spec_from_file_location('nex_schema_'+module,TESTS/(module+'.py'))
    loaded=importlib.util.module_from_spec(spec);sys.modules[spec.name]=loaded;spec.loader.exec_module(loaded)
    suite.addTests(unittest.defaultTestLoader.loadTestsFromNames(names,loaded))
suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(AdditionalArtifacts))
report={'ok':False,'state':'running','validator_version':importlib.metadata.version('jsonschema'),
        'compiler_sha256':hashlib.sha256(COMPILER.read_bytes()).hexdigest(),
        'schema_input_sha256':{name:hashlib.sha256(raw).hexdigest() for name,raw in raw_documents.items()}}
subprocess.run=run
try:
    with (OUTPUT/'tests.log').open('w') as log:
        result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    required=set(NAMES)-({'native-stream-task-provider'} if not args.retained_nex else set())
    missing=sorted(name for name in required if not counts[name])
    provider_variants={'nex.native-task-provider/'+str(n)+':'+mode for n in (11,12,13) for mode in ('static','shared-fixed')}
    missing_variants=sorted(provider_variants-set(variants['native-source-error-task-provider']))
    retained_unchanged=hashlib.sha256(retained_schema_path.read_bytes()).hexdigest()==retained_schema_sha256
    passed=result.wasSuccessful() and not errors and not missing and not missing_variants and retained_unchanged
    report.update(ok=passed, state='passed' if passed else 'failed',
                  tests=result.testsRun,failures=len(result.failures),test_errors=len(result.errors),
                  schema_errors=errors,validated=counts,variants=variants,missing=missing,
                  missing_provider_variants=missing_variants,retained_provider_unchanged=retained_unchanged,
                  retained_provider_schema_sha256=retained_schema_sha256,
                  retained_runtime_verified=bool(args.retained_nex) and counts['native-stream-task-provider']>0 and result.wasSuccessful())
finally:
    subprocess.run=original_run
    (OUTPUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n', newline="\n")
    for name,value in samples.items():
        (OUTPUT/(name+'.sample.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n', newline="\n")
print(json.dumps({k:report.get(k) for k in ['ok','state','tests','failures','test_errors','missing']}))
raise SystemExit(0 if report['ok'] else 1)
