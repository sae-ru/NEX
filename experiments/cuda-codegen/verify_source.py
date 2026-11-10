"""Compare experimental CUDA lowering with checked NEX; never claims a GPU run."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

MIN, MAX = -(1 << 63), (1 << 63) - 1


def arithmetic(a, b, op):
    if op in ('/', '%') and b == 0:
        return 0, 2
    if op in ('/', '%'):
        quotient = abs(a) // abs(b) * (-1 if (a < 0) != (b < 0) else 1)
        value = quotient if op == '/' else a - quotient * b
    else:
        value = {'+': lambda: a + b, '-': lambda: a - b, '*': lambda: a * b}[op]()
    return (value, 0) if MIN <= value <= MAX else (0, 1)


def fixtures():
    cases = []
    pairs = [(MIN, 0), (MAX, 0), (MIN, 1), (MIN, -1), (MAX, 1),
             (-7, 3), (7, -3), (-7, -3), (0, 0), (3037000499, 3037000499),
             (3037000500, 3037000500), (-1, 1), (0, MIN)]
    for operator in ['+', '-', '*', '/', '%']:
        cases.append(({'+' : 'add', '-': 'sub', '*': 'mul', '/': 'div', '%': 'mod'}[operator],
                      'pub fn transform(a:i64,b:i64)->i64{return a' + operator + 'b;}',
                      [(list(p), *arithmetic(*p, operator)) for p in pairs]))
    cases.extend([
        ('neg', 'pub fn transform(x:i64)->i64{return -x;}',
         [([MIN], 0, 1), ([MAX], -MAX, 0), ([-17], 17, 0)]),
        ('short_or', 'fn fail()->bool{assert(false);return true;}pub fn transform(x:bool)->bool{return x||fail();}',
         [([1], 1, 0), ([0], 0, 3), ([2], 0, 6), ([-1], 0, 6)]),
        ('short_and', 'fn fail()->bool{assert(false);return true;}pub fn transform(x:bool)->bool{return x&&fail();}',
         [([0], 0, 0), ([1], 0, 3), ([2], 0, 6)]),
        ('left_to_right', 'fn first(x:i64)->i64{return x/0;}fn second(x:i64)->i64{assert(false);return x;}pub fn transform(x:i64)->i64{return first(x)+second(x);}',
         [([5], 0, 2)]),
        ('left_assert_first', 'fn first(x:i64)->i64{assert(false);return x;}fn second(x:i64)->i64{return x/0;}pub fn transform(x:i64)->i64{return first(x)+second(x);}',
         [([5], 0, 3)]),
        ('generic_loop', 'fn twice<T:integer>(x:T)->T{return x*2;}pub fn transform(x:i64)->i64{var n:i64=x;var sum:i64=0;while n>0{sum=sum+twice<i64>(n);n=n-1;}return sum;}',
         [([0], 0, 0), ([1], 2, 0), ([10], 110, 0)]),
        ('contracts', 'pub fn transform(x:i64)->i64 requires(x>=0) ensures(r=>r>x){return x+1;}',
         [([0], 1, 0), ([41], 42, 0), ([-1], 0, 3), ([MAX], 0, 1)]),
        ('loop_contracts', 'pub fn transform(x:i64)->i64 requires(x>=0&&x<20){var n:i64=x;var sum:i64=0;while n>0 invariant(n>=0) decreases(n){sum=sum+n;n=n-1;}return sum;}',
         [([0], 0, 0), ([10], 55, 0), ([-1], 0, 3), ([20], 0, 3)]),
        ('unit_zero', 'pub fn transform()->unit{assert(true);}', [([], 0, 0)]),
        ('eight', 'pub fn transform(a:i64,b:bool,c:i64,d:i64,e:i64,f:i64,g:i64,h:i64)->bool{return b&&a==h&&c==d&&e<f&&g>=a;}',
         [([MIN, 1, 9, 9, -5, 5, MAX, MIN], 1, 0),
          ([MAX, 0, 2, 3, 10, 0, MIN, MIN], 0, 0),
          ([0, 2, 0, 0, 0, 0, 0, 0], 0, 6)]),
        ('quota', 'pub fn transform(x:i64)->i64{while true{}return x;}', [([1], 0, 4)]),
        ('match_returns', 'pub fn transform(x:bool)->i64{match x{true=>{return 1;},false=>{return 0;}}}',
         [([1], 1, 0), ([0], 0, 0), ([2], 0, 6)]),
        ('match_integers', 'pub fn transform(x:i64)->i64{return match x{-9223372036854775808=>11,9223372036854775807=>12,0=>13,n=>n};}',
         [([MIN], 11, 0), ([MAX], 12, 0), ([0], 13, 0), ([-7], -7, 0)]),
        ('match_guards', 'pub fn transform(x:i64)->i64{return match x{n if n==0=>1,n if n<0=>-n,n=>n+2};}',
         [([0], 1, 0), ([-3], 3, 0), ([7], 9, 0), ([MIN], 0, 1)]),
        ('match_guard_trap', 'fn fail()->bool{assert(false);return true;}pub fn transform(x:i64)->i64{return match x{0 if fail()=>1,n=>n+1};}',
         [([1], 2, 0), ([0], 0, 3), ([MAX], 0, 1)]),
        ('match_unselected_value', 'fn fail()->i64{assert(false);return 0;}pub fn transform(x:i64)->i64{return match x{0=>42,_=>fail()};}',
         [([0], 42, 0), ([1], 0, 3)]),
        ('match_shadowing', 'pub fn transform(x:i64)->i64{var y:i64=100;match x{0=>{let y:i64=7;assert(y==7);},n=>{y=n+1;}}return y;}',
         [([0], 100, 0), ([5], 6, 0), ([MAX], 0, 1)]),
        ('match_nested', 'pub fn transform(x:bool,y:i64)->i64{return match x{true=>match y{0=>7,n=>n},false=>-1};}',
         [([1, 0], 7, 0), ([1, 9], 9, 0), ([0, MAX], -1, 0), ([2, 0], 0, 6)]),
        ('match_loop', 'pub fn transform(x:i64)->i64{var i:i64=0;var sum:i64=0;while i<x{sum=sum+match i%3{0=>10,1=>20,_=>30};i=i+1;}return sum;}',
         [([0], 0, 0), ([3], 60, 0), ([6], 120, 0)]),
        ('match_generic', 'fn choose<T:integer>(x:T)->T{return match x{0=>1,n=>n};}pub fn transform(x:i64)->i64{return choose<i64>(x);}',
         [([0], 1, 0), ([MIN], MIN, 0), ([MAX], MAX, 0)]),
        ('match_unit_statement', 'pub fn transform(x:bool)->unit{match x{true=>{assert(true);},false=>{assert(false);}}}',
         [([1], 0, 0), ([0], 0, 3)]),
        ('match_unit_expression', 'pub fn transform(x:bool)->unit{match x{true=>assert(true),false=>assert(false)};}',
         [([1], 0, 0), ([0], 0, 3)]),
        ('match_subject_once', 'fn subject(x:i64)->i64{var i:i64=0;while i<128{i=i+1;}return x;}pub fn transform(x:i64)->i64{return match subject(x){' +
         ','.join(str(i) + '=>' + str(i) for i in range(10)) + ',n=>n};}',
         [([100], 100, 0), ([MIN], MIN, 0)]),
    ])
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['emitter', 'compiler', 'cxx', 'output']:
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args()
    out = args.output.absolute()
    out.mkdir(exist_ok=False)
    report = {'schema': 'nex.experimental-cuda-source-controls/1', 'ok': False,
              'GPU_execution_claimed': False, 'cases': [], 'commands': []}
    sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
    report.update(emitter_sha256=sha(args.emitter), compiler_sha256=sha(args.compiler))

    def run(name, argv, cwd, expected=0, timeout=180):
        result = subprocess.run(list(map(str, argv)), cwd=cwd, capture_output=True,
                                text=True, timeout=timeout)
        number = len(report['commands'])
        (out / (str(number) + '-' + name + '.stdout')).write_text(result.stdout)
        (out / (str(number) + '-' + name + '.stderr')).write_text(result.stderr)
        report['commands'].append({'name': name, 'argv': list(map(str, argv)),
                                   'exit_code': result.returncode})
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
        assert (result.returncode == 0) == (expected == 0), (name, result.stdout[-2000:], result.stderr[-2000:])
        return result.stdout

    def manifest(root):
        (root / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1', 'language': '0.28', 'entry': 'main.nex'}) + '\n')

    references = out / 'references'
    references.mkdir()
    manifest(references)
    imports, assertions, negatives = [], [], []
    try:
        for index, (name, body, rows) in enumerate(fixtures()):
            project = out / name
            project.mkdir()
            manifest(project)
            source = 'module cuda' + str(index) + ';' + body + '\nfn main()->unit{}\n'
            source += 'server fn unselected()->str{return "UNREACHABLE_DEVICE_SECRET";}\n'
            (project / 'main.nex').write_text(source)
            (references / ('f' + str(index) + '.nex')).write_text(source)
            imports.append('import "./f' + str(index) + '.nex" as c' + str(index) + ';')
            for layout in ['rows', 'columns']:
                shader = project / (layout + '.cu')
                metadata = json.loads(run(name + '-' + layout, [args.emitter, project, 'transform', layout, shader], project))
                assert metadata['ok'] and not metadata['device_executed'] and metadata['language'] == '0.28'
                assert metadata['shader_sha256'] == sha(shader)
                code = shader.read_text()
                assert 'UNREACHABLE_DEVICE_SECRET' not in code
                assert all(1 <= f['first_line'] <= f['last_line'] <= len(code.splitlines()) for f in metadata['functions'])
                count, arity = len(rows), len(metadata['parameter_types'])
                steps = 64 if name == 'quota' else 4096 if name == 'match_subject_once' else 65536
                matrix = [r[0] for r in rows]
                values = [v for row in matrix for v in row] if layout == 'rows' else [matrix[lane][p] for p in range(arity) for lane in range(count)]
                literals = ','.join('nex_bits(0x%016xULL)' % (v % (1 << 64)) for v in values) or '0LL'
                inputs = ['input'] if layout == 'rows' else ['input+' + str(p * count) for p in range(arity)]
                call = ','.join([*inputs, 'output', 'errors', str(count) + 'U', str(steps) + 'U'])
                harness = project / (layout + '-host.cpp')
                harness.write_text('#include <iostream>\n#define __device__\n#define __global__\n'
                    'struct Index{unsigned int x;};Index blockIdx,blockDim,threadIdx;\n#include ' + json.dumps(str(shader)) + '\n'
                    'int main(){long long input[]={' + literals + '};long long output[' + str(count + 3) + '];unsigned int errors[' + str(count + 3) + '];'
                    'for(unsigned int i=0;i<' + str(count + 3) + ';++i){output[i]=123456789LL;errors[i]=98765U;}'
                    'blockDim.x=128;for(unsigned int lane=0;lane<' + str(count + 256) + ';++lane){blockIdx.x=lane/128;threadIdx.x=lane%128;nex_generated_cuda_map(' + call + ');}'
                    'std::cout<<"{\\\"values\\\":[";for(unsigned int i=0;i<' + str(count + 3) + ';++i){if(i)std::cout<<",";std::cout<<output[i];}'
                    'std::cout<<"],\\\"errors\\\":[";for(unsigned int i=0;i<' + str(count + 3) + ';++i){if(i)std::cout<<",";std::cout<<errors[i];}std::cout<<"]}\\n";}\n')
                executable = project / (layout + '-host')
                run(name + '-host-compile', [args.cxx, '-std=c++20', '-O2', '-fsanitize=undefined', '-fno-sanitize-recover=all', harness, '-o', executable], project)
                actual = json.loads(run(name + '-host-execute', [executable], project))
                assert actual['values'] == [r[1] for r in rows] + [123456789] * 3, (name, layout, actual)
                assert actual['errors'] == [r[2] for r in rows] + [98765] * 3, (name, layout, actual)
                row = {'name': name, 'layout': layout, 'shader': str(shader.relative_to(out)),
                       'shader_sha256': sha(shader), 'metadata': metadata,
                       'lanes': [{'arguments': list(map(str, r[0])), 'value': str(r[1]), 'error': r[2]} for r in rows],
                       'steps': steps,
                       'host_UBSan_passed': True, 'excess_lanes_untouched': True}
                report['cases'].append(row)
            types = metadata['parameter_types']
            for arguments, value, error in rows:
                if error in (4, 6):
                    continue
                words = [('true' if v else 'false') if t == 'bool' else str(v) for t, v in zip(types, arguments)]
                call = 'c' + str(index) + '::transform(' + ','.join(words) + ')'
                if error == 0:
                    expected = ('true' if value else 'false') if metadata['result_type'] == 'bool' else str(value)
                    assertions.append(call + ';' if metadata['result_type'] == 'unit' else 'assert(' + call + '==' + expected + ');')
                elif not any(n[0] == index for n in negatives):
                    negatives.append((index, call, error))
        main_source = 'module oracle;' + ''.join(imports) + 'fn agree()->unit{' + ''.join(assertions) + '}fn main()->unit{agree();}test fn backend_agreement()->unit{agree();}'
        (references / 'main.nex').write_text(main_source)
        for argv in [('eval',), ('test', '--profile', 'release'), ('test', '--target', 'web')]:
            result = json.loads(run('NEX-backend-agreement', [args.compiler, *argv, '--json'], references, timeout=600))
            assert result['ok']
        for index, call, error in negatives:
            root = out / ('reference-error-' + str(index))
            root.mkdir()
            manifest(root)
            (root / 'f.nex').write_bytes((references / ('f' + str(index) + '.nex')).read_bytes())
            (root / 'main.nex').write_text('module failure;import "./f.nex" as c' + str(index) + ';fn main()->unit{' + call + ';}')
            result = json.loads(run('NEX-reference-trap', [args.compiler, 'eval', '--json'], root, expected=1))
            assert result['code'] == {1: 'E_OVERFLOW', 2: 'E_DIV_ZERO', 3: 'E_ASSERT'}[error]
        rejected = [
            ('dynamic_result', 'pub fn transform(x:list<f64>)->result<list<f64>>{return ok(x);}', 'E_GPU_TYPE'),
            ('dynamic_text', 'pub fn transform(x:str)->str{return x+"x";}', 'E_GPU_UNSUPPORTED'),
            ('server', 'pub server fn transform(x:i64)->i64{return x;}', 'E_GPU_REALM'),
            ('effect', 'pub fn transform()->unit !{io}{print(1);}', 'E_GPU_REALM'),
            ('recursive', 'pub fn transform(x:i64)->i64{return transform(x);}', 'E_GPU_RECURSION'),
            ('dynamic_match', 'pub fn transform(x:list<i64>)->i64{return match x{[]=>0,_=>1};}', 'E_GPU_TYPE'),
            ('uncovered_match', 'pub fn transform(x:bool)->i64{return match x{true=>1};}', 'E_MATCH_EXHAUSTIVE'),
            ('duplicate_match', 'pub fn transform(x:bool)->i64{return match x{true=>1,true=>2,false=>0};}', 'E_MATCH_DUPLICATE'),
            ('nine', 'pub fn transform(' + ','.join('a' + str(i) + ':i64' for i in range(9)) + ')->i64{return a0;}', 'E_GPU_LIMIT'),
        ]
        for name, body, expected in rejected:
            root = out / ('rejected-' + name)
            root.mkdir()
            manifest(root)
            (root / 'main.nex').write_text('module rejected;' + body + 'fn main()->unit{}')
            target = root / 'preserved.cu'
            target.write_bytes(b'original output must survive\n')
            result = json.loads(run('reject-' + name, [args.emitter, root, 'transform', 'columns', target], root, expected=1))
            assert result['code'] == expected, (name, result)
            assert target.read_bytes() == b'original output must survive\n'
        report.update(ok=True, source_fixtures=len(fixtures()), emitted_layout_cases=len(report['cases']),
                      lane_results_checked=sum(len(c['lanes']) for c in report['cases']),
                      rejected_programs=len(rejected), NEX_reference_native_TypeScript_agreement=True)
    finally:
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ['ok', 'source_fixtures', 'emitted_layout_cases', 'lane_results_checked', 'rejected_programs']}))


if __name__ == '__main__':
    main()
