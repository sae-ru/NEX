#!/usr/bin/env python3
"""Check the published standard-library source API and run a small independent behavior probe."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

from sdk_compat_snapshot import cli

PROFILE = 'nex.stdlib-public-api/1'
BASELINE = Path(__file__).resolve().parents[1] / 'llm/stdlib-public-api-0.280.1.json'
IDENT = r'[A-Za-z_][A-Za-z_0-9]*'
VARIABLE = re.compile(r'\$(?:' + IDENT + r'::)*' + IDENT + r'|\?' + IDENT)
PROBE = '''module compat::standard_library;
import "std/list.nex" as lists;
import "std/java_int.nex" as java;
import "std/hash_map.nex" as maps;
import "std/hash.nex" as hash;
import "std/text.nex" as text;
fn collide(value: i64) -> i64 { return 1; }
fn behavior() -> unit !{state} {
  let counter: cell<i64> = cell_new(0);
  let mapped: list<i64> = lists::map([4,5,6],fn(n:i64)->i64 !{state} {
    cell_write(counter,cell_read(counter)+1); return n+cell_read(counter);
  });
  assert(mapped == [5,7,9] && cell_read(counter) == 3);
  assert(lists::sort([3,-1,3,0]) == [-1,0,3,3]);
  let first: maps::Map<i64,str> = maps::put(maps::empty<i64,str>(collide,hash::equal<i64>),1,"one");
  let second: maps::Map<i64,str> = maps::put(first,2,"two");
  let third: maps::Map<i64,str> = maps::remove(maps::put(second,1,"updated"),2);
  assert(!maps::has(first,2) && unwrap(maps::get(second,1)) == "one");
  assert(maps::size(third) == 1 && unwrap(maps::get(third,1)) == "updated");
  assert(error_code(maps::get(third,2)) == "E_NOT_FOUND");
  assert(java::to_i64(java::add(java::from_i64(2147483647),java::from_i64(1))) == -2147483648);
  assert(text::join(text::split("Я🌍b🌍", "🌍"),"|") == "Я|b|");
}
test fn public_behavior() -> unit !{state} { behavior(); }
fn main() -> unit !{io,state} { behavior(); print("stdlib-compat-ok"); }
'''


def require(value, why):
    if not value:
        raise ValueError('standard-library source contract: ' + why)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def signature(decl, function):
    """Project a checked source declaration, dropping optimizer/implementation data."""
    ids = decl['type_parameters']
    kinds = decl['type_parameter_kinds']
    defaults = decl.get('type_defaults', [''] * len(ids))
    require(len(ids) == len(kinds) == len(defaults) and set(decl['type_bounds']) == set(ids),
            'invalid generic metadata on ' + decl['name'])
    require(all(type(k) is int and k >= 0 for k in kinds) and len(set(ids)) == len(ids),
            'invalid generic kind or repeated parameter on ' + decl['name'])
    variables = {'$' + key: '$' + str(i) for i, key in enumerate(ids)}
    effects = {}

    def render(text):
        def variable(m):
            token = m.group()
            if token.startswith('$'):
                require(token in variables, 'unbound type parameter ' + token)
                return variables[token]
            if token not in effects:
                effects[token] = '?' + str(len(effects))
            return effects[token]
        return VARIABLE.sub(variable, text)

    def fields(values):
        return [[p['name'], render(p['type'])] for p in values]

    out = {'generics': [{'arity': kinds[i], 'bounds': sorted(render(b) for b in decl['type_bounds'][name])}
                        for i, name in enumerate(ids)]}
    for slot, default in zip(out['generics'], defaults):
        if default:
            slot['default'] = render(default)
    if function:
        out['parameters'] = [render(p['type']) for p in decl['parameters']]
        out['result'] = render(decl['result'])
        out['realm'] = decl['realm']
        out['effects'] = sorted(render(item) for item in decl['effects'])
        if decl.get('source_contract'):
            out['source_contract'] = True
    elif decl['format'].startswith('nex.resource/'):
        out['resource'] = True
    elif 'fields' in decl:
        out['fields'] = fields(decl['fields'])
    elif 'variants' in decl:
        out['variants'] = [[v['name'], fields(v['fields'])] for v in decl['variants']]
    else:
        raise ValueError('unsupported public type ' + decl['name'])
    return out


def source_project(project, source):
    project.mkdir()
    (project / 'nex.json').write_text('{"schema":"nex.project/1","language":"0.30","entry":"main.nex"}\n',
                                      encoding='utf-8')
    (project / 'main.nex').write_bytes(source.encode('utf-8'))


def extract(nex, project):
    response = cli(nex, project.parent, 'describe', '--field', 'standard_library')
    require(response['value']['status'] == 'checked_source_modules', 'missing compiled catalogue')
    discovered = response['value']['modules']
    by_module = {}
    modules = {}
    for item in discovered.values():
        name, path = item['module'], item['import']
        require(re.fullmatch('std::' + IDENT, name) and re.fullmatch('std/' + IDENT + r'\.nex', path)
                and name not in by_module and path not in modules, 'ambiguous module/import')
        by_module[name] = path
        modules[path] = {'module': name, 'functions': {}, 'types': {}}
    imports = ''.join(f'import "{path}" as lib{i};\n' for i, path in enumerate(sorted(modules)))
    source_project(project, 'module stdlib_client;\n' + imports + 'fn main() -> unit {}\n')
    checked = cli(nex, project, 'check')
    graph = cli(nex, project, 'graph', '--revision', checked['revision'])
    require(checked['ok'] is True and graph['language'] == '0.30' and graph['revision'] == checked['revision'],
            'unverified checked graph')
    for key, declarations in (('functions', (row['definition'] for row in graph['nodes'])),
                              ('types', graph['structures'])):
        for decl in declarations:
            owner = decl['owner']
            if owner not in by_module or decl['public'] is not True or decl['template']:
                continue
            members = modules[by_module[owner]][key]
            name = decl['name'][len(owner) + 2:]
            require(decl['name'] == owner + '::' + name and re.fullmatch(IDENT, name) and name not in members,
                    'invalid public member: ' + decl['name'])
            members[name] = signature(decl, key == 'functions')
    # In these catalogued modules, the summaries enumerate all public functions
    # and nominal types. Check this against independently checked source modules.
    for item in discovered.values():
        api = modules[item['import']]
        require(set(item['functions']) == api['functions'].keys(), 'incomplete function catalogue: ' + item['import'])
        names = {t.split('<', 1)[0] for t in item.get('types', [])}
        require(names == api['types'].keys(), 'incomplete type catalogue: ' + item['import'])
    return {'schema': PROFILE, 'project_language': '0.30', 'modules': modules}, response['toolchain']


def compatible(baseline, candidate):
    for field in ('schema', 'project_language'):
        require(candidate.get(field) == baseline[field], 'changed ' + field)
    for path, previous in baseline['modules'].items():
        current = candidate['modules'].get(path)
        require(current and previous['module'] == current['module'], 'missing or renamed module ' + path)
        for group in ('functions', 'types'):
            for name, contract in previous[group].items():
                require(current[group].get(name) == contract, 'changed ' + previous['module'] + '::' + name)


def check_baseline(held, actual, version):
    # Publication is established by the caller's delivery record and archive.
    # The numeric toolchain here selects the source compatibility rule only.
    match = re.fullmatch(r'([0-9]+)\.([0-9]+)\.([0-9]+)(?:[-+][A-Za-z0-9.+-]+)?', version)
    require(match, 'unrecognized baseline toolchain version ' + str(version))
    number = tuple(map(int, match.groups()))
    require(number >= (0, 280, 1), 'baseline predates the 0.280.1 source contract')
    if number == (0, 280, 1):
        require(actual == held, 'baseline differs from the published 0.280.1 API')
        return 'exact-0.280.1'
    compatible(held, actual)
    return 'preserves-0.280.1-and-pins-full-baseline'


def baseline_controls(held):
    expanded = deepcopy(held)
    releases = expanded['modules']['std/math.nex']['functions']
    releases['added_in_later_beta'] = deepcopy(releases['min'])
    missing_original = deepcopy(held)
    del missing_original['modules']['std/math.nex']['functions']['min']
    check_baseline(held, expanded, '0.281.0')
    transitions = [
        ('modified original beta', lambda: check_baseline(held, expanded, '0.280.1')),
        ('later baseline lost an original declaration', lambda: check_baseline(held, missing_original, '0.281.0')),
        ('candidate lost a later-only declaration', lambda: compatible(expanded, held)),
        ('unsupported earlier baseline', lambda: check_baseline(held, held, '0.280.0')),
    ]
    for label, check in transitions:
        try:
            check()
        except ValueError:
            continue
        raise ValueError('failed to reject ' + label)
    return {'later_baseline_with_addition': True, 'rejected': [label for label, _ in transitions]}


def counts(projection):
    modules = projection['modules']
    return {'modules': len(modules), **{key: sum(len(m[key]) for m in modules.values())
                                       for key in ('functions', 'types')}}


def mutations(baseline):
    # Modifications of real, baseline declarations. Compare each independently.
    checks = [
        ('missing module', ('modules', 'std/queue.nex'), None),
        ('module identity', ('modules', 'std/list.nex', 'module'), 'std::list'),
        ('missing function', ('modules', 'std/text.nex', 'functions', 'join'), None),
        ('parameter arity', ('modules', 'std/math.nex', 'functions', 'min', 'parameters'), ['i64']),
        ('parameter type', ('modules', 'std/math.nex', 'functions', 'min', 'parameters', 1), 'f64'),
        ('result type', ('modules', 'std/hash.nex', 'functions', 'integer', 'result'), 'bool'),
        ('callback type', ('modules', 'std/list.nex', 'functions', 'map', 'parameters', 1), 'fn($0)->$1'),
        ('effects', ('modules', 'std/list.nex', 'functions', 'map', 'effects'), []),
        ('realm', ('modules', 'std/hash.nex', 'functions', 'integer', 'realm'), 'server'),
        ('generic arity', ('modules', 'std/hash.nex', 'functions', 'equal', 'generics'), []),
        ('constructor kind', ('modules', 'std/hash.nex', 'functions', 'equal', 'generics', 0, 'arity'), 1),
        ('generic bound', ('modules', 'std/list.nex', 'functions', 'sort', 'generics', 0, 'bounds'), []),
        ('missing type', ('modules', 'std/java_int.nex', 'types', 'Int32'), None),
        ('field name', ('modules', 'std/java_int.nex', 'types', 'Int32', 'fields', 0, 0), 'bits'),
        ('field type', ('modules', 'std/java_int.nex', 'types', 'Int32', 'fields', 0, 1), 'str'),
        ('field order', ('modules', 'std/hash_map.nex', 'types', 'Entry', 'fields'), [['value', '$1'], ['key', '$0']]),
    ]
    for what, path, value in checks:
        altered = deepcopy(baseline)
        target = altered
        for token in path[:-1]:
            target = target[token]
        if value is None:
            del target[path[-1]]
        else:
            target[path[-1]] = value
        try:
            compatible(baseline, altered)
        except ValueError:
            continue
        raise ValueError('failed to reject ' + what)
    added = deepcopy(baseline)
    added['modules']['std/new.nex'] = {'module': 'std::new', 'functions': {}, 'types': {}}
    mod = added['modules']['std/java_int.nex']
    mod['functions']['extra'] = mod['functions']['to_i64']
    mod['types']['Extra'] = mod['types']['Int32']
    compatible(baseline, added)
    return {'accepted_additions': ['module', 'function', 'type'], 'rejected_changes': [case[0] for case in checks]}


def implementation_control(nex, work):
    """Compare two genuinely compiled declarations with equivalent public signatures."""
    common = 'module compatible;\nfn main() -> unit {}\n'
    before = common + '''
pub struct Pair<T> { left: T; right: T; }
pub fn apply<T>(value:T,f:fn(T)->T !{?E})->T !{?E} { return f(value); }
'''
    after = common + '''
pub struct Pair<U> { left: U; right: U; }
pub fn apply<U>(item:U,next:fn(U)->U !{?Changed})->U !{?Changed} {
  let copy: U = item;
  return next(copy);
}
pub fn extra() -> i64 { return 1; }
'''
    observed = []
    for label, source in (('before', before), ('after', after)):
        project = work / ('implementation-' + label)
        source_project(project, source)
        revision = cli(nex, project, 'check')['revision']
        graph = cli(nex, project, 'graph', '--revision', revision)
        functions = {row['name']: signature(row['definition'], True) for row in graph['nodes']
                     if row['definition']['public']}
        types = {decl['name']: signature(decl, False) for decl in graph['structures'] if decl['public']}
        module = {'module': 'compatible', 'functions': functions, 'types': types}
        observed.append((revision, {'schema': PROFILE, 'project_language': '0.30', 'modules': {'control.nex': module}}))
    old, new = observed
    require(old[0] != new[0] and counts(old[1]) == {'modules': 1, 'functions': 1, 'types': 1}
            and counts(new[1]) == {'modules': 1, 'functions': 2, 'types': 1}, 'invalid implementation control')
    compatible(old[1], new[1])
    return {'revision_changed': True, 'source_body_changed': True, 'additional_function': True,
            'renamed_positional_and_generic_and_effect_parameters': True}


def semantics(nex, project):
    source_project(project, PROBE)
    runs = cli(nex, project, 'test', '--symbol', 'compat::standard_library::public_behavior')
    require(runs['ok'] is True and len(runs['tests']) == 1, 'missing public behavior test')
    row = runs['tests'][0]
    require(row['name'] == 'compat::standard_library::public_behavior' and row['ok'] is True
            and row['native'] is True, 'public behavior test did not pass natively')
    for command in ('eval', 'run'):
        result = cli(nex, project, command)
        require(result['ok'] is True and result['stdout'] == 'stdlib-compat-ok\n', 'wrong ' + command + ' behavior')
        if command == 'run':
            require(result['exit_code'] == 0 and result['stderr'] == '', 'native probe failed')
    return {'test': row['name'], 'reference': True, 'native': True, 'stdout': result['stdout']}


def check_stdlib(baseline_nex: Path, candidate_nex: Path, root: Path) -> dict:
    require(not Path(baseline_nex).samefile(candidate_nex), 'separate SDK executables required')
    work = Path(root).resolve() / 'stdlib-api-compatibility'
    work.mkdir(parents=True, exist_ok=False)
    held = json.loads(BASELINE.read_bytes())
    result = {'schema': 'nex.stdlib-api-compatibility/1', 'contract': PROFILE,
              'published_api_sha256': digest(BASELINE.read_bytes()), 'probe_sha256': digest(PROBE.encode())}
    original = None
    for role, exe in (('baseline', baseline_nex), ('candidate', candidate_nex)):
        nex = Path(exe).resolve(strict=True)
        api, version = extract(nex, work / (role + '-catalogue'))
        if role == 'baseline':
            result['baseline_policy'] = check_baseline(held, api, version)
            original = api
        else:
            compatible(original, api)
            result['added_modules'] = sorted(api['modules'].keys() - original['modules'].keys())
        result[role] = {'toolchain': version, 'compiler_sha256': digest(nex.read_bytes()),
                        'api_sha256': digest(json.dumps(api, sort_keys=True, separators=(',', ':')).encode()),
                        **counts(api), 'behavior': semantics(nex, work / (role + '-behavior'))}
    result['controls'] = mutations(original)
    result['controls']['baseline_policy'] = baseline_controls(held)
    result['controls']['compiled_compatible_change'] = implementation_control(Path(candidate_nex).resolve(), work)
    result['ok'] = True
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', required=True, type=Path)
    parser.add_argument('--candidate', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path, help='new output directory')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    receipt = check_stdlib(args.baseline, args.candidate, args.output)
    (args.output/'report.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print(args.output/'report.json')
