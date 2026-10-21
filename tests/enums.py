"""Nominal enum semantics, exhaustiveness, wire boundaries and migrations."""
import json
from pathlib import Path
import subprocess
import sys
import unittest
import support as harness


class Enums(harness.ToolchainCase):
    def agree(self, expected):
        self.assertEqual(self.cli('eval')['stdout'], expected)
        for profile in ('debug', 'release'):
            self.assertEqual(self.cli('run', '--profile', profile)['stdout'], expected)
        self.cli('test', '--target', 'web')

    def test_recursive_values_and_codec_across_backends(self):
        self.source((harness.REPO/'examples/enums/main.nex').read_text())
        self.agree('42\n5\n{"case":"Label","fields":{"text":"🧠","tags":["NEX"]}}\n')
        self.cli('test', '--profile', 'release')

    def test_order_once_fallthrough_discard_shadow_cleanup_and_aliases(self):
        self.source('''module order;
enum Event { Pair(text: str, n: i64); Empty; }
fn text() -> str !{io} { print("text"); return "🧠"; }
fn number() -> i64 !{io} { print("number"); return 42; }
fn subject() -> Event !{io} { print("subject"); return Event::Pair(text(),number()); }
fn main() -> unit !{io} {
 let original: Event = subject(); var current: Event = original;
 let n: i64 = 5; let _: i64 = 7; var i: i64 = 0;
 while i < 20 {
  match current {
   Event::Empty() => { current = original; },
   Event::Pair(text,n) => { assert(len(text) == 1); assert(n == 42); current = Event::Empty(); }
  }
  i = i + 1;
 }
 match original {
  Event::Pair(_,_) => { assert(_ == 7); },
  Event::Empty() => { assert(false); }
 }
 assert(n == 5); assert(current == original); print("done");
}
test fn branch_return() -> unit { assert(identity(Event::Pair("x",42)) == Event::Pair("x",42)); }
fn identity(e: Event) -> Event {
 match e { Event::Empty() => { return Event::Empty(); }, Event::Pair(t,n) => { return Event::Pair(t,n); } }
}''')
        self.agree('subject\ntext\nnumber\ndone\n')

    def test_rejected_programs(self):
        cases=[
            ('enum E {} fn main() -> unit {}', 'E_ENUM'),
            ('enum E { A; A; } fn main() -> unit {}', 'E_DUPLICATE'),
            ('enum E { A(x:unit); } fn main() -> unit {}', 'E_TYPE'),
            ('enum E { A(x:i64,x:str); } fn main() -> unit {}', 'E_DUPLICATE'),
            ('enum E { A; B; } fn main() -> unit { match E::A() { E::A() => {} } }', 'E_MATCH_EXHAUSTIVE'),
            ('enum E { A; } fn main() -> unit { match E::A() { E::A() => {} E::A() => {} } }', 'E_MATCH_DUPLICATE'),
            ('enum E { A(x:i64); } fn main() -> unit { match E::A(1) { E::A() => {} } }', 'E_ARITY'),
            ('enum E { A(x:i64); } fn main() -> unit { match E::A(1) { E::A(x) => { x = 2; } } }', 'E_MUTABILITY'),
            ('enum E { A; } fn main() -> unit { let e: E = E(); }', 'E_CONSTRUCTOR'),
            ('enum E { A; } fn main() -> unit { match 1 { E::A() => {} } }', 'E_MATCH_TYPE'),
            ('enum E { A; } enum F { A; } fn main() -> unit { let e:E = F::A(); }', 'E_TYPE'),
            ('enum E { A; } enum F { A; } fn main() -> unit { match E::A() { F::A() => {} } }', 'E_MATCH_VARIANT'),
            ('enum E { A; B; } fn main() -> i64 { match E::A() { E::A() => {return 1;} E::B() => {} } }', 'E_RETURN'),
            ('enum E { A(x:i64); } fn main() -> unit { match E::A(1) { E::A(x) => {} } assert(x == 1); }', 'E_NAME'),
            ('enum E { A; } fn main() -> unit { match E::A() { E::A() => {print(1);} } }', 'E_EFFECT'),
            ('enum E { A; } server fn remote() -> unit {} client fn main() -> unit { match E::A() { E::A() => {remote();} } }', 'E_REALM'),
            ('struct Private {} pub enum E { A(x:Private); } fn main() -> unit {}', 'E_VISIBILITY'),
        ]
        for source,code in cases:
            with self.subTest(code=code,source=source):
                self.source('module rejected; '+source)
                self.assertEqual(self.cli('check',ok=False)['code'],code)

    def test_strict_codec_and_special_field_names(self):
        invalid=[{'case':'Missing','fields':{}},{'case':'Set','fields':{'value':42}},
                 {'case':'Reset','fields':{'extra':True}}, {'case':'Set','fields':{}},
                 {'case':'Reset'}, {'case':'Reset','fields':{},'other':True}]
        checks='\n'.join('assert(!is_ok(decode_json<E>('+json.dumps(json.dumps(v))+')));' for v in invalid)
        self.source('''module codec; enum E { Reset; Set(value:i64); }
enum Odd { Pair(case:str, fields:str, __proto__:str, constructor:i64); }
fn main() -> unit {}
test fn codec() -> unit {
 let odd:Odd = Odd::Pair("tag","payload","own",42);
 assert(unwrap(decode_json<Odd>(encode_json(odd))) == odd);
 assert(unwrap(decode_json<E>("{\\"case\\":\\"Set\\",\\"fields\\":{\\"value\\":\\"9223372036854775807\\"}}")) == E::Set(9223372036854775807));
'''+checks+'''\nassert(!is_ok(decode_json<E>("{\\"case\\":\\"Reset\\",\\"case\\":\\"Reset\\",\\"fields\\":{}}")));
}''')
        self.cli('test')
        self.cli('test','--target','web')

    def test_imported_cases_visibility_and_nominal_identity(self):
        (self.root/'model.nex').write_text('module model; pub enum E { A(value:i64); B; } enum Hidden { X; }')
        self.source('''module app; import "./model.nex" as m;
fn value(e:m::E) -> i64 { match e { m::E::A(n) => {return n;} m::E::B() => {return 0;} } }
fn main() -> unit !{io} { print(value(m::E::A(42))); }
test fn works() -> unit { assert(value(m::E::A(42)) == 42); }''')
        self.agree('42\n')
        revision=self.cli('check')['revision'];(self.root/'model.nex').unlink()
        self.assertEqual(self.cli('run','--revision',revision)['stdout'],'42\n')
        (self.root/'model.nex').write_text('module model; enum Hidden { X; }')
        self.source('module app; import "./model.nex" as m; fn main() -> unit { m::Hidden::X(); }')
        self.assertEqual(self.cli('check',ok=False)['code'],'E_VISIBILITY')

    def test_enum_json_depth_boundary_and_formal_verifier_limit(self):
        self.source('''module limits;
enum Link { Nil; Next(next:list<Link>); }
fn nested(n:i64) -> Link { var value:Link = Link::Nil(); var i:i64 = 0; while i < n { value = Link::Next([value]); i = i + 1; } return value; }
fn scalar() -> i64 { match Link::Nil() { Link::Nil() => {return 42;} Link::Next(_) => {return 0;} } }
fn main() -> unit { encode_json(nested(22)); }
test fn allowed() -> unit { let value:Link = nested(21); assert(unwrap(decode_json<Link>(encode_json(value))) == value); }
''')
        self.cli('test');self.cli('test','--target','web')
        self.assertEqual(self.cli('eval',ok=False)['code'],'E_JSON')
        run=self.cli('run',ok=False,machine=False)
        self.assertIn('E_JSON',run.stdout+run.stderr)
        contract=self.root/'scalar.json';self.cli('contract','--symbol','scalar','-o',contract)
        proof=self.cli('verify','--contracts',contract,ok=False)
        self.assertFalse(proof['ok']);self.assertEqual(proof['functions'][0]['status'],'unsupported')

    def test_actual_language_05_migration_retains_source_and_ids(self):
        self.source('module old; fn enum(x:i64) -> i64 { return x; } fn match(x:i64) -> i64 { return enum(x); } fn main() -> unit { let match:i64 = match(42); assert(match == 42); }')
        old_compiler=harness.REPO/'build/sdk-0.15.0/bin/nex'
        if sys.platform=='darwin' and old_compiler.exists():
            result=subprocess.run([str(old_compiler),'check','--json'],cwd=self.root,capture_output=True,text=True,check=True)
            old=json.loads(result.stdout)['revision'];old_graph=json.loads(subprocess.check_output([str(old_compiler),'graph','--json'],cwd=self.root))
        else:
            fixture=self.historical_store('0.5');old=fixture['revision'];old_graph=fixture['graph']
        self.file.unlink()
        self.assertEqual(self.cli('eval','--revision',old,ok=False)['code'],'E_LANGUAGE_VERSION')
        current=self.cli('migrate')
        self.assertEqual(current['language'],'0.18');self.assertNotEqual(old,current['revision'])
        self.assertEqual({r['language'] for r in self.cli('history')['revisions']},{'0.5','0.18'})
        self.assertEqual(self.cli('run','--revision','HEAD')['exit_code'],0)
        destination=self.root/'legacy';self.cli('export','--revision',old,'--directory',destination)
        self.assertEqual(json.loads((destination/'nex.json').read_text())['language'],'0.5')
        graph=self.cli('graph');self.assertEqual({n['name']:n['id'] for n in graph['nodes']},{n['name']:n['id'] for n in old_graph['nodes']})

    def test_case_ids_bindings_and_native_cache_survive_reordered_cases(self):
        model=self.root/'model.nex';model.write_text('module model; pub enum E { A(value:i64); B; } pub fn value() -> E { return E::A(42); }')
        self.source('''module app; import "./model.nex" as m;
fn number(e:m::E) -> i64 { match e { m::E::A(value) => {return value;} m::E::B() => {return 0;} } }
fn main() -> unit !{io} { print(number(m::value())); }''')
        self.cli('check');old=self.cli('operations','--symbol','number','--limit','1000')['nodes']
        first=self.cli('build');self.assertEqual(first['compiled_modules'],2)
        self.assertEqual(self.cli('build')['compiled_modules'],0)
        model.write_text(model.read_text().replace('A(value:i64); B;','B; A(value:i64);'))
        self.cli('check');new=self.cli('operations','--symbol','number','--limit','1000')['nodes']
        before={n['path']:n for n in old};after={n['path']:n for n in new}
        cases=[p for p,n in before.items() if n['kind']=='pattern.case'];self.assertEqual(len(cases),2)
        for path in cases:self.assertEqual(before[path]['id'],after[path]['id'])
        pattern=next(n for n in new if n['kind']=='pattern.binding')
        reference=next(n for n in new if n['kind']=='expression.name' and n['definition'].get('text')=='value')
        self.assertEqual(reference['references'][0]['id'],pattern['id'])
        changed=self.cli('build');self.assertEqual(changed['compiled_modules'],2)
        self.assertEqual(subprocess.check_output([changed['executable']],text=True),'42\n')
        self.assertEqual(self.cli('eval')['stdout'],'42\n')


if __name__ == '__main__': unittest.main()
