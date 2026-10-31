"""Actual TaskIR instructions versus checked AST actions, under the same serial coordinator."""
import argparse, ast, hashlib, json, os, re, subprocess, tempfile
from pathlib import Path
p = argparse.ArgumentParser();p.add_argument('probe');p.add_argument('--output');args = p.parse_args()
source = Path(__file__).resolve().parents[1];probe = str(Path(args.probe).resolve())
out = Path(args.output or os.environ.get('NEX_EXCEPTION_TASK_IR_OUTPUT') or tempfile.mkdtemp(prefix='nex-exception-ir-')).resolve();out.mkdir(parents=True, exist_ok=True)
fixtures = [];origins = {}
f = source/'tests/source_exception_native.py';tree = ast.parse(f.read_text())
item = next(n for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'cases' for t in n.targets))
fixtures += [('sequential-'+name, text) for name, text in ast.literal_eval(item.value)];origins[str(f.relative_to(source))] = hashlib.sha256(f.read_bytes()).hexdigest()
f = source/'tests/source_exception_tasks.cpp'
fixtures += [('task-'+name, text) for kind, name, text in re.findall(r'\b(value|sourceError|trap)\("([^"]+)",R"\((.*?)\)"', f.read_text(), re.S) if name not in {'parent-budget', 'parent-cancellation'}]
origins[str(f.relative_to(source))] = hashlib.sha256(f.read_bytes()).hexdigest()
f = source/'tests/source_exception_tasks_typescript.py';tree = ast.parse(f.read_text())
for n in tree.body:
    if isinstance(n, ast.AugAssign) and isinstance(n.target, ast.Name) and n.target.id == 'fixtures':
        fixtures += [('task-'+item[1], item[2]) for item in ast.literal_eval(n.value)]
origins[str(f.relative_to(source))] = hashlib.sha256(f.read_bytes()).hexdigest()
assert len(fixtures) == 66, len(fixtures)
extra = [
('outer-shadow', '''fn main()->i64 !{task}{var x:i64=1;try{x=42;let x:list<str>=["inner"];task_yield();throw("X",x[0]);}catch(x,message){assert(x=="X");}return x;}'''),
('nested-caught-restore', '''fn main()->i64 !{task}{try{try{throw("A","outer");}catch(code,message){try{task_yield();throw("B","inner");}catch(code,message){assert(code=="B");task_yield();}throw;}}catch(code,message){assert(code=="A"&&message=="outer");return 42;}}'''),
('normal-handler-pop', '''fn main()->i64 !{task}{try{try{task_yield();}catch(code,message){return 0;}throw("OUTER","x");}catch(code,message){assert(code=="OUTER");return 42;}}'''),
('catch-closure-snapshot', '''fn main()->i64 !{task}{var cb:fn()->str=fn()->str{return "initial";};try{throw("SNAPSHOT","value");}catch(code,message){cb=fn()->str{return code+message;};task_yield();}assert(cb()=="SNAPSHOTvalue");return 42;}'''),
('match-keeps-enclosing-input', '''enum Shape{Pair(left:i64,right:i64);}fn main()->i64 !{task}{let input:Shape=Shape::Pair(20,22);match input{Shape::Pair(a,b)=>{var answer:i64=0;try{task_yield();throw("X","x");}catch(code,message){answer=a+b;}return answer;}}}'''),
('throw-operand-order', '''fn code()->str !{io}{print("code");return "OUTER";}fn message()->str !{io,throw}{print("message");throw("INNER","value");}fn main()->i64 !{task,io}{try{throw(code(),message());}catch(code,message){assert(code=="INNER");task_yield();return 42;}}'''),
('pure-recursive-call-unwind', '''fn recurse(n:i64)->i64 !{throw}{if n==0{throw("LEAF","root");}return recurse(n-1);}fn main()->i64 !{task}{let cb:fn(i64)->i64 !{throw}=recurse;try{task_yield();return cb(20);}catch(code,message){assert(code=="LEAF");return 42;}}'''),
('catch-result-return', '''fn helper()->result<i64> !{task}{try{throw("USER","x");}catch(code,message){task_yield();let v:i64=err<i64>("RESULT","value")?;return ok(v);}}fn main()->i64 !{task}{try{let r:result<i64>=helper();assert(!is_ok(r));return 42;}catch(code,message){return 0;}}'''),
]
fixtures += [('ir-'+name, text) for name, text in extra]
report = {'ok': False, 'cases': [], 'fixtures': origins, 'ordinary_functional_only': True,
          'security_checks_deferred_by_user': True, 'shared_serial_coordinator': True,
          'independent_AST_and_IR_control': True, 'compiled_native_execution': False,
          'physical_workers': False, 'installed_SDK_acceptance_claimed': False}
def save(): (out/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', newline="\n")
save()
for name, text in fixtures:
    d = out/(("case-"+name) if os.name=="nt" and name.upper()=="NUL" else name);d.mkdir(exist_ok=True)
    (d/'nex.json').write_text(json.dumps({'schema': 'nex.project/1', 'language': '0.24', 'entry': 'main.nex'}), newline="\n")
    f = d/'main.nex';f.write_text('module task_ir_agreement;\n'+text+'\n', newline="\n")
    outcomes = {}
    for mode in ['reference', 'task-ir']:
        r = subprocess.run([probe, mode, str(f), '1000000'], text=True, capture_output=True, timeout=45)
        (d/(mode+'.json')).write_text(r.stdout, newline="\n");(d/(mode+'.stderr')).write_text(r.stderr, newline="\n")
        assert r.returncode == 0, (name, mode, r.returncode, r.stdout, r.stderr)
        outcomes[mode] = json.loads(r.stdout)
    left, right = outcomes['reference'], outcomes['task-ir']
    # Source steps are intentionally charged at different traversal granularities.
    # Exhaustion/depth remain fatal, while their last in-flight instruction can differ.
    if left.get('kind') == 'trap' and left.get('code') == 'E_LIMIT':
        assert right.get('kind') == 'trap' and right.get('code') == 'E_LIMIT', (name, outcomes)
    else:
        assert left == right, (name, outcomes)
    if name.startswith('ir-'): assert left.get('kind') == 'return' and left.get('value') == 42, (name, outcomes)
    report['cases'].append({'name': name, 'source_sha256': hashlib.sha256(f.read_bytes()).hexdigest(), 'outcomes': outcomes, 'passed': True});save()
report.update(ok=True, comparisons=len(fixtures), retained_programs=66, new_programs=len(extra));save()
print(json.dumps({'ok': True, 'comparisons': len(fixtures), 'report': str(out/'report.json')}))
