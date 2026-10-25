"""Private source authority diagnostics against actual independent AST behavior."""
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

probe, reference = map(Path, sys.argv[1:3])
compiler=Path(sys.argv[3]) if len(sys.argv)>3 else None
source_root = Path(__file__).resolve().parent.parent
destination = os.environ.get('NEX_TASK_LIFETIME_OUTPUT')
temporary = None
if destination:
    output = Path(destination).resolve()
    output.mkdir(parents=True, exist_ok=False)
else:
    temporary = tempfile.TemporaryDirectory(prefix='nex-task-lifetimes-')
    output = Path(temporary.name)

def run(binary, path, *arguments):
    result = subprocess.run([str(binary), str(path), *arguments], text=True,
                            capture_output=True, timeout=30)
    assert result.returncode in (0, 1), (path.name, result.returncode, result.stdout, result.stderr)
    data = json.loads(result.stdout)
    return result.returncode, data

fixture_document=json.loads((source_root/'tests/fixtures/task-lifetimes.json').read_text())
assert fixture_document['schema']=='nex.private-task-lifetime-fixtures/1'
extras=[(case['name'],case['source'],case['analysis']) for case in fixture_document['cases']]

try:
    if compiler:
        descriptor=json.loads(subprocess.check_output([str(compiler),'describe','--json'],text=True))
        pack=json.loads((source_root/'llm/language-pack.json').read_text())
        runtime=descriptor['structured_tasks_runtime']
        assert runtime['private_lifetime_analysis']==pack['structured_tasks_runtime']['private_lifetime_analysis']
        assert runtime['source_support'] and descriptor['version']=='0.23'
        assert descriptor['effects']==['io','db','fs','ffi','task']
        guide=json.loads(subprocess.check_output([str(compiler),'guide','--kind','task-lifetime','--json'],text=True))
        assert guide['text']==(source_root/'docs/task-lifetimes.md').read_text()
    tree = ast.parse((source_root/'tests/task_native.py').read_text())
    fixtures = next(ast.literal_eval(node.value) for node in tree.body
                    if isinstance(node, ast.Assign) and any(isinstance(n, ast.Name) and n.id=='cases' for n in node.targets))
    # The native suite appends three generated capacity fixtures after this list.
    fixture_map = dict((name, body) for name, body, expected, stdout, minimum in fixtures)
    for capacity in [0,1,7]:
        node = next(n for n in tree.body if isinstance(n, ast.For) and isinstance(n.target, ast.Name) and n.target.id=='capacity')
        local = {'cases':[], 'capacity':capacity}
        # Evaluate only this literal source-construction loop body. It contains
        # no runner, source execution, imports or filesystem operations.
        assert len(node.body)==1 and isinstance(node.body[0], ast.Expr)
        call = node.body[0].value
        assert isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr=='append'
        item = eval(compile(ast.Expression(call.args[0]), '<fixture-literal>', 'eval'), {'__builtins__':{'str':str}}, local)
        fixture_map[item[0]]=item[1]
    assert len(fixture_map)==58, len(fixture_map)
    source_hashes = {}
    classifications = []
    known_bad={'scope-escape','scope-box-escape','scope-capture-escape','scope-no-current','scope-channel-escape','scope-spawn-escape'}
    for name, body in fixture_map.items():
        path=output/(name+'.nex');text='module native_steps;\n'+body+'\n';path.write_text(text)
        source_hashes[name]=hashlib.sha256(text.encode()).hexdigest()
        code, data=run(probe,path,'main')
        if name in known_bad:
            assert code==1 and data['code']=='E_TASK_LIFETIME', (name,data)
        else:
            assert code==0 and data['ok'] and data['mandatory_runtime_guards'] and not data['fully_static'], (name,data)
        classifications.append({'name':name,'analysis':data})
    for name, body, expected in extras:
        path=output/(name+'.nex');path.write_text('module native_steps;\n'+body+'\n')
        source_hashes[name]=hashlib.sha256(path.read_bytes()).hexdigest()
        code, data=run(probe,path,'main')
        if expected and not expected.startswith('DYNAMIC:'):
            assert code==1 and data['code']==expected,(name,data)
            assert data['file'].endswith(name+'.nex') and data['line']>0 and data['column']>0,(name,data)
        else:
            assert code==0 and data['ok'],(name,data)
            if expected: assert data['dynamic']>0,(name,data)
        # These are real source runs through the independent scheduler. They
        # validate runtime owner behavior, rather than duplicating the pass.
        _, behavior=run(reference,path)
        if expected:
            assert not behavior['ok'] and behavior['code']=='E_TASK_SCOPE',(name,behavior)
        else:
            assert behavior['ok'] and behavior['representation']=='42',(name,behavior)
        classifications.append({'name':name,'analysis':data,'reference':behavior})
    path=output/'scope-lifetime-borrow-alias.nex'
    _, limited=run(probe,path,'main','1')
    assert limited['dynamic']>0 and limited['widenings']>0 and limited['steps']==1,limited
    _, zero=run(probe,path,'main','0')
    assert zero['code']=='E_OPTION',zero
    for bad in ['-1','1x','1048577']:
        _, data=run(probe,path,'main',bad)
        assert data['code']=='E_OPTION',(bad,data)
    assert not (output/'.nex').exists(), 'analysis created a graph store'
    report={'ok':True,'source_scenarios':len(classifications),'native_fixtures':len(fixture_map)+len(extras),'base_native_fixtures':len(fixture_map),
            'native_fixture_sha256':source_hashes,'additional_reference_scenarios':len(extras),
            'fully_static':False,'mandatory_runtime_guards':True,'public_source_tasks':False,
            'bounded_analysis_checked':True,'classifications':classifications}
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ['classifications','native_fixture_sha256']}))
finally:
    if temporary: temporary.cleanup()
