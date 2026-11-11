"""Actual standard helpers: independent oracles, backend agreement and pins."""
import copy
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import random
import re
import shutil
import subprocess
import unittest
import support as h

spec=importlib.util.spec_from_file_location('stdlib_sdk',h.REPO/'tools/sdk_stdlib.py')
sdk=importlib.util.module_from_spec(spec);spec.loader.exec_module(sdk)
SPACE=''.join(chr(x) for x in [*range(9,14),32,133,160,5760,*range(8192,8203),8232,8233,8239,8287,12288])
PREFIX='''module library_cases;
import "std/text.nex" as text;
import "std/list.nex" as seq;
import "std/math.nex" as math;
'''
def literal(value):return json.dumps(value,ensure_ascii=False,separators=(',',':'))


def corpus():
    checks=[];rng=random.Random(122)
    samples=[('','','X'),('a\0b','\0','🌍'),('aaaaa','aa','X'),('ababa','aba','!'),
        ('e\u0301🌍','','Я'),('Я🌍Я','Я',''),('abc','long needle','N')]
    alphabet=['a','b','Я','🌍','\0','\u0301']
    for _ in range(32):
        samples.append((''.join(rng.choices(alphabet,k=rng.randrange(25))),
            ''.join(rng.choices(alphabet,k=rng.randrange(7))),rng.choice(alphabet)))
    for value,needle,replacement in samples:
        checks += [f'assert(text::find({literal(value)},{literal(needle)})=={value.find(needle)});',
            f'assert(text::split({literal(value)},{literal(needle)})=={literal(value.split(needle) if needle else list(value))});',
            f'assert(text::replace({literal(value)},{literal(needle)},{literal(replacement)})=={literal(value.replace(needle,replacement))});']
    for character in SPACE+'\u001c\u001f\u200b\ufeff\0':
        value=character+' X\0Y '+character
        checks.append(f'assert(text::trim({literal(value)})=={literal(value.strip(SPACE))});')
    for _ in range(18):
        values=rng.choices(range(-20,21),k=rng.randrange(25))
        checks += [f'assert(seq::sort<i64>({literal(values)})=={literal(sorted(values))});',
            f'assert(seq::reverse<i64>({literal(values)})=={literal(list(reversed(values)))});',
            f'assert(seq::map<i64,i64>({literal(values)},fn(x:i64)->i64{{return x+1;}})=={literal([x+1 for x in values])});',
            f'assert(seq::filter<i64>({literal(values)},fn(x:i64)->bool{{return x%2==0;}})=={literal([x for x in values if x%2==0])});']
    for a in (-9223372036854775808,-9223372036854775807,-7,-1,0,1,7,9223372036854775807):
        for b in (-9223372036854775808,-7,-1,1,7,9223372036854775807):
            if (a,b)==(-9223372036854775808,-1):continue
            checks += [f'assert(math::floor_div({a},{b})=={a//b});',
                f'assert(math::ceil_div({a},{b})=={-((-a)//b)});']
    for a,b in [(0,0),(0,-9223372036854775808),(-9223372036854775808,-1),
        (-9223372036854775808,-9223372036854775808),(-9223372036854775808,6),
        (-48,18),(9223372036854775807,2),(0,17),(12,-18),(-1,-1)]:
        for name,result in [('gcd',math.gcd(a,b)),('lcm',math.lcm(a,b))]:
            call=f'math::{name}({a},{b})'
            checks.append(f'assert(unwrap({call})=={result});' if result<=9223372036854775807 else
                f'assert(!is_ok({call}) && error_code({call})=="E_MATH_OVERFLOW");')
    for base,exponent in [(0,0),(0,20),(-1,63),(-2,63),(2,62),(-9223372036854775808,1),(9223372036854775807,1)]:
        checks.append(f'assert(math::pow_i64({base},{exponent})=={base**exponent});')
    return PREFIX+'''
struct Item { key:i64; id:i64; }
fn binary(value:i64,count:i64)->str {
  var bits:i64=value;var left:i64=count;var result:str="";
  while left>0 { if bits%2==0 {result=result+"a";}else{result=result+"b";}bits=bits/2;left=left-1; }
  return result;
}
fn oracle(value:str,needle:str)->i64 {
  var index:i64=0;
  while index+len(needle)<=len(value) {
    if slice(value,index,len(needle))==needle {return index;}
    index=index+1;
  }
  return -1;
}
fn exhaustive()->unit {
  var length:i64=0;
  while length<=7 {
    var code:i64=0;
    while code<math::pow_i64(2,length) {
      let value:str=binary(code,length);var size:i64=0;
      while size<=5 {
        var pattern:i64=0;
        while pattern<math::pow_i64(2,size) {
          let needle:str=binary(pattern,size);
          assert(text::find(value,needle)==oracle(value,needle));pattern=pattern+1;
        }
        size=size+1;
      }
      code=code+1;
    }
    length=length+1;
  }
}
fn main()->unit !{io} {
  exhaustive();
  let input:list<Item>=[Item(2,0),Item(1,1),Item(2,2),Item(1,3)];
  let sorted:list<Item>=seq::sort_by(input,fn(a:Item,b:Item)->bool{return a.key<b.key;});
  assert(seq::map(sorted,fn(x:Item)->i64{return x.id;})==[1,3,0,2]);
  assert(input[0].id==0 && input[1].id==1);
  var captured:list<i64>=[1,2];let mapper:fn(i64)->list<str>=fn(x:i64)->list<str>{return [str(captured[0]+x)];};
  captured=set(captured,0,99);assert(seq::map([1,2],mapper)==[["2"],["3"]]);
  assert(seq::fold([3,1,2],"",fn(a:str,b:i64)->str{return a+str(b);})=="312");
  assert(seq::any([1,0],fn(x:i64)->bool{return 10/x>0;}));
  assert(!seq::all([0,1],fn(x:i64)->bool{return x!=0 && 10/(x-1)>0;}));
  assert(seq::find_index([3,0],fn(x:i64)->bool{return 10/x>0;})==0);
  assert(seq::find_index<i64>([],fn(x:i64)->bool{return 1/x>0;})== -1);
  assert(seq::sort<f64>([3.5,-2.0,0.0,-0.0])==[-2.0,0.0,0.0,3.5]);
'''+ '\n'.join(checks) + '\nprint("stdlib-corpus-ok");\n}\n',len(checks)


class StandardLibrary(h.ToolchainCase):
    def run_child(self,command,timeout=120):
        child=subprocess.run(list(map(str,command)),capture_output=True,text=True,timeout=timeout)
        self.assertEqual(child.returncode,0,child.stdout+child.stderr)
        return child.stdout

    def strict_ts(self,folder):
        selected=os.environ.get('NEX_TSC')
        if not selected:
            self.assertTrue(os.environ.get('NEX_NPM_CACHE'),'Select pinned NEX_TSC or populated offline NEX_NPM_CACHE')
            tool=self.root/'typescript-tool';tool.mkdir(exist_ok=True)
            for name in ('package.json','package-lock.json'):shutil.copy2(h.REPO/'web'/name,tool/name)
            self.run_child([os.environ.get('NEX_NPM','npm'),'ci','--ignore-scripts','--offline','--prefix',tool,
                '--cache',os.environ['NEX_NPM_CACHE']],180)
            selected=tool/'node_modules/typescript/bin/tsc'
        tsc=Path(selected).resolve(strict=True)
        pin=json.loads((h.REPO/'web/package.json').read_text())['devDependencies']['typescript']
        self.assertEqual(json.loads((tsc.parent.parent/'package.json').read_text())['version'],pin)
        self.run_child([os.environ.get('NEX_NODE','node'),tsc,'--noEmit','--strict','--target','ES2022',
            '--module','ESNext','--moduleResolution','bundler','--allowImportingTsExtensions','--lib','ES2022,DOM',folder/'program.ts'],180)

    def typescript(self,entry='main',failure=None):
        folder=self.root/('typescript-'+entry)
        self.cli('emit','--kind','typescript','--entry',entry,'--directory',folder)
        (folder/'package.json').write_text('{"type":"module"}\n')
        driver=folder/'driver.mjs'
        if failure:
            driver.write_text("import {entry} from './program.ts';import {NexError} from './nex-runtime.ts';\n"
                "try{entry();process.stdout.write('unexpected success');}catch(e){if(!(e instanceof NexError))throw e;process.stdout.write(e.code);}\n")
        else:driver.write_text("import {entry} from './program.ts';entry();\n")
        result=self.run_child([os.environ.get('NEX_NODE','node'),'--experimental-strip-types',driver])
        if failure:self.assertEqual(result,failure)
        else:self.strict_ts(folder)
        return result

    def test_compiled_catalogue_matches_actual_public_sources_and_guide(self):
        cap=self.cli('describe','--field','standard_library')['value']
        self.assertEqual(sdk.resource_pins(h.REPO,cap),{name:hashlib.sha256((h.REPO/name).read_bytes()).hexdigest() for name in sdk.FILES})
        total=0
        for module in cap['modules'].values():
            names=re.findall(r'\bpub\s+fn\s+(\w+)',(h.REPO/module['resource']).read_text())
            self.assertEqual(set(names),set(module['functions']));total+=len(names)
        self.assertEqual(total,62);self.assertFalse(cap['source_language_changed'])
        self.assertTrue(cap['modules']['list']['linear_bulk_construction'])
        self.assertEqual(self.cli('guide','--kind','stdlib')['text'],(h.REPO/'docs/stdlib.md').read_text())
        self.assertFalse((self.root/'.nex').exists())

    def test_actual_SDK_subworkflow_and_strict_typescript_with_receipt_controls(self):
        proof=sdk.exercise(cli=self.cli,run=self.run_child,compiler=Path(h.NEX),resources=h.REPO,root=self.root,browser=True)
        inventory={**proof['compiled_source_pins'],**{'examples/stdlib/'+name:digest for name,digest in proof['example_hashes'].items()}}
        report={'compiler_sha256':proof['compiler_sha256'],'language':h.CURRENT_LANGUAGE,'version':proof['toolchain'],
            'resource_hashes':inventory,'evidence':{'standard_library':proof,'browser_build':True,
                'scoped_discovery':{'descriptor_hash':proof['descriptor_hash']}}}
        sdk.validate(report)
        for key,value in [('compiler_sha256','0'*64),('compiled_source_pins',{}),('native',{}),
            ('example_hashes',{}),('lock_unchanged',False),('typescript',{'requested':True,'executed':False}),
            ('descriptor_hash','0'*64),('complete_SDK_workflow_claimed',True)]:
            bad=copy.deepcopy(report);bad['evidence']['standard_library'][key]=value
            with self.subTest(rejected=key),self.assertRaises(RuntimeError):sdk.validate(bad)
        bad=copy.deepcopy(report);del bad['evidence']['standard_library']
        with self.assertRaises(RuntimeError):sdk.validate(bad)
        bad=copy.deepcopy(report);bad['resource_hashes']['lib/text.nex']='0'*64
        with self.assertRaises(RuntimeError):sdk.validate(bad)
        self.strict_ts(self.root/'standard-library-typescript')
        print(json.dumps({'stdlib_SDK_subworkflow':proof,'strict_typescript':True,'receipt_rejection_controls':10,'complete_SDK_executed':False}))

    def test_independent_oracles_reference_native_profiles_and_typescript(self):
        program,count=corpus();self.source(program);self.cli('check')
        # v2 expands the original945-pair correctness matrix exactly17 times.
        # Scale that aggregate oracle budget; the separate1M adversarial guard
        # stays fixed and still rejects an independent naive implementation.
        self.assertEqual(self.cli('eval','--steps','170000000',timeout=180)['stdout'],'stdlib-corpus-ok\n')
        for profile in ('debug','release'):
            self.assertEqual(self.cli('run','--profile',profile,timeout=240)['stdout'],'stdlib-corpus-ok\n')
        self.assertEqual(self.typescript(),'stdlib-corpus-ok\n')
        print(json.dumps({'oracle_assertions':count,'exhaustive_binary_search_pairs':16065,
            'oracle_matrix_version':2,'aggregate_oracle_step_budget':170000000,'case_expansion_factor':17,
            'adversarial_step_budget_unchanged':1000000,
            'reference_native_debug_release_TypeScript':True,'UTF8_White_Space_codepoints':len(SPACE)}))

    def test_adversarial_search_step_budget_rejects_an_independent_naive_control(self):
        value='a'*8192;needle='a'*1024+'b'
        self.source(PREFIX+f'fn main()->unit {{assert(text::find({literal(value)},{literal(needle)})== -1);}}')
        self.cli('eval','--steps','1000000',timeout=120)
        self.source('''module naive_control;
fn find(data:bytes,needle:bytes)->i64 {
  var position:i64=0;
  while position<=len(data)-len(needle) {
    var index:i64=0;
    while index<len(needle) && data[position+index]==needle[index] {index=index+1;}
    if index==len(needle) {return position;}position=position+1;
  }
  return -1;
}
'''+f'fn main()->unit {{assert(find(utf8_bytes({literal(value)}),utf8_bytes({literal(needle)}))== -1);}}')
        self.assertEqual(self.cli('eval','--steps','1000000',ok=False,timeout=120)['code'],'E_LIMIT')

    def test_callback_type_effect_and_private_helpers_rejected_and_runtime_failures_agree(self):
        for expression,code in [('seq::sort(["a","b"])','E_GENERIC_BOUND'),
            ('seq::map([1],fn(x:i64)->i64 !{io}{print(x);return x;})','E_EFFECT'),
            ('seq::filter([1],fn(x:i64)->i64{return x;})','E_TYPE'),
            ('text::find_bytes(utf8_bytes("a"),utf8_bytes("b"),0)','E_VISIBILITY')]:
            self.source(PREFIX+'fn main()->unit { '+expression+'; }')
            self.assertEqual(self.cli('check',ok=False)['code'],code)
        self.source(PREFIX+'''
fn risky(x:i64)->i64 {if x==1 {return 10/(x-1);}assert(x<2);return x;}
fn map_order()->unit {let output:list<i64>=seq::map([1,2],risky);}
fn filter_order()->unit {let output:list<i64>=seq::filter([1,2],fn(x:i64)->bool{return risky(x)>0;});}
fn overflow_pow()->unit {let value:i64=math::pow_i64(2,63);}
fn min_identity()->unit {assert(math::pow_i64(-9223372036854775808,1)== -9223372036854775808);}
fn negative_exponent()->unit {let value:i64=math::pow_i64(2,-1);}
fn zero_division()->unit {let value:i64=math::floor_div(1,0);}
fn overflow_division()->unit {let value:i64=math::ceil_div(-9223372036854775808,-1);}
fn main()->unit {}
''')
        for entry,code in [('map_order','E_DIV_ZERO'),('filter_order','E_DIV_ZERO'),('overflow_pow','E_OVERFLOW'),
            ('negative_exponent','E_ASSERT'),('zero_division','E_DIV_ZERO'),('overflow_division','E_OVERFLOW')]:
            with self.subTest(entry=entry):
                self.assertEqual(self.cli('eval','--entry',entry,ok=False)['code'],code)
                native=self.cli('run','--entry',entry,'--profile','release',ok=False,timeout=240)
                self.assertEqual(native['exit_code'],70);self.assertIn(code,native['stderr'])
                self.typescript(entry,failure=code)

    def test_reviewed_dependency_update_preserves_old_revision_and_frozen_export(self):
        library=self.root/'std';library.mkdir()
        old='module std::text; pub fn starts_with(value:str,prefix:str)->bool{return false;}'
        (library/'text.nex').write_text(old)
        self.source('module locked;import "std/text.nex" as text;fn main()->unit !{io}{print(text::starts_with("abc","a"));}')
        manifest=self.root/'nex.json';value=json.loads(manifest.read_text());value['libraries']={'std':'std'};manifest.write_text(json.dumps(value))
        self.cli('lock');previous=self.cli('check')['revision'];lock=(self.root/'nex.lock.json').read_bytes()
        before=h.database_rows(self.root/'.nex/graph.db')
        before_graph=self.cli('graph')
        before_ids={node['name']:node['id'] for node in before_graph['nodes']}
        (library/'text.nex').write_bytes((h.REPO/'lib/text.nex').read_bytes())
        self.assertEqual(self.cli('check',ok=False)['code'],'E_LOCK')
        self.assertEqual((self.root/'nex.lock.json').read_bytes(),lock)
        self.assertEqual(h.database_rows(self.root/'.nex/graph.db'),before)
        self.assertEqual(self.cli('eval','--revision',previous)['stdout'],'false\n')
        self.cli('lock');self.assertNotEqual((self.root/'nex.lock.json').read_bytes(),lock)
        current=self.cli('check')['revision'];self.assertNotEqual(current,previous)
        self.assertEqual(self.cli('graph','--revision',previous),before_graph)
        current_ids={node['name']:node['id'] for node in self.cli('graph')['nodes']}
        self.assertTrue(all(current_ids[name]==identity for name,identity in before_ids.items()))
        self.assertEqual(self.cli('eval')['stdout'],'true\n')
        self.assertIn(previous,{row['revision'] for row in self.cli('history')['revisions']})
        destination=self.root/'frozen';self.cli('export','--revision',previous,'--directory',destination)
        self.assertEqual(self.cli('eval',cwd=destination)['stdout'],'false\n')


if __name__=='__main__':unittest.main(verbosity=2)
