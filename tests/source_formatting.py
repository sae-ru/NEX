"""Formatting behavior, retained graph state and execution agreement."""
import json
import os
from pathlib import Path
import subprocess
import unittest
import support as h


class Formatting(h.ToolchainCase):
    def preview(self,source):
        self.file.write_bytes(source.encode('utf-8'))
        result=self.cli('fmt',self.file)
        self.assertEqual(self.file.read_bytes(),source.encode('utf-8'))
        return result['source']

    def test_fixed_style_and_idempotent_noop(self):
        source='module pretty;fn main()->unit!{io}{let x:list<i64>=[1,2];if x[0]<x[1]{print(-x[0]);}else{print(!false);}}'
        expected='''module pretty;
fn main() -> unit !{io} {
  let x: list<i64> = [1, 2];
  if x[0] < x[1] {
    print(-x[0]);
  } else {
    print(!false);
  }
}
'''
        self.assertEqual(self.preview(source),expected)
        before=self.file.stat().st_mtime_ns
        check=self.cli('fmt',self.file,'--check',ok=False)
        self.assertEqual(check['schema'],'nex.format/1');self.assertFalse(check['ok'])
        self.assertFalse(check['written']);self.assertEqual(self.file.stat().st_mtime_ns,before)
        write=self.cli('fmt',self.file,'--write');self.assertTrue(write['written'])
        self.assertEqual(self.file.read_text(),expected)
        before=self.file.stat().st_mtime_ns
        self.assertFalse(self.cli('fmt',self.file,'--write')['written'])
        self.assertEqual(self.file.stat().st_mtime_ns,before)
        self.assertFalse(self.cli('fmt',self.file,'--check')['changed'])
        self.assertFalse((self.root/'.nex').exists())
        self.assertEqual(list(self.root.glob('*.fmt-*')),[])
        formatted=self.preview('module pretty;fn main()->unit!{io}{if [true][0]{print([1][0]);}while [false][0]{}print(([2])[0]);}')
        self.assertIn('if [true][0] {',formatted)
        self.assertIn('while [false][0] {}',formatted)

    def test_unicode_comments_raw_literals_multiline_and_trailing_comment(self):
        source=('// Первый 🌍\r\n\r\nmodule pretty; // module note\r\n'
            'fn main( // parameters\r\n)->unit !{io, // effects\r\nthrow}{\r\n'
            'let text:str="//literal\\u0410\\n\\\"\\u0000";// keep trailing  \r\n'
            'let xs:list<i64>=[\r\n 1, // first\r\n 2\r\n];\r\n'
            'print(text); // print\r\n} // 最後')
        formatted=self.preview(source)
        self.assertIn('"//literal\\u0410\\n\\\"\\u0000"',formatted)
        comments=['// Первый 🌍','// module note','// parameters','// effects',
            '// keep trailing  ','// first','// print','// 最後']
        cursor=0
        for comment in comments:
            cursor=formatted.index(comment,cursor)+len(comment)
        self.assertNotIn('\r',formatted);self.assertTrue(formatted.endswith('// 最後\n'))
        self.assertEqual(self.preview(formatted),formatted)

    def test_comments_between_syntax_elements(self):
        # Named, deterministic trivia positions; no random/source execution.
        pieces=['module','pretty',';','fn','main','(',')','->','unit','!','{','io','}',
            '{','let','xs',':','list','<','i64','>','=','[','1',',','2',']',';',
            'print','(','xs','[','0',']',')',';','}']
        for boundary in [1,3,5,7,9,10,12,13,14,17,19,20,21,23,25,27,30,32,35,36]:
            with self.subTest(boundary=boundary):
                source=' '.join(pieces[:boundary])+' // position '+str(boundary)+'\n'+' '.join(pieces[boundary:])
                formatted=self.preview(source)
                self.assertIn('// position '+str(boundary)+'\n',formatted)
                self.assertEqual(self.preview(formatted),formatted)

    def test_types_comparisons_traits_and_current_sources(self):
        source='''module types;
pub trait Map<Self<_>>{type Item:wire;fn get(x:Self<i64>)->i64;}
struct Box<T>{value:T;}
fn id<T>(x:T)->T{return x;}
fn main()->unit!{io,throw}{
let xs:list<list<i64>>=[[1,2]];
let f:fn(i64)->list<i64>=fn(x:i64)->list<i64>{return [x];};
let b:Box<i64>=Box<i64>(f(xs[0][0])[0]);
assert(b.value>=1 && b.value<=2 && b.value>0 && b.value<3);
print(id<i64>(b.value));
try{throw("X","message");}catch(code,message){print(code);}finally{print("done");}
}
'''
        formatted=self.preview(source)
        for fragment in ['Map<Self<_>>','list<list<i64>> =','list<i64> = fn(',
                         'Box<i64> = Box<i64>(', 'b.value >= 1', 'b.value < 3']:
            self.assertIn(fragment,formatted)
        for relative in ['lib/text.nex','lib/list.nex','lib/math.nex','examples/stdlib/main.nex',
            'examples/finally/main.nex','examples/finally/tasks.nex','examples/traits/main.nex',
            'examples/traits/mapping.nex','examples/traits/api/helpers/contracts.nex',
            'examples/source-contracts/main.nex','examples/llm-quick/src/main.nex']:
            with self.subTest(source=relative):
                original=(h.REPO/relative).read_text()
                self.assertEqual(self.preview(self.preview(original)),self.preview(original))

    def test_syntax_only_and_invalid_sources_are_not_written(self):
        formatted=self.preview('module missing;import "./absent.nex" as absent;fn main()->i64{return undefined;}')
        self.assertIn('return undefined;',formatted)
        for raw in [b'module bad;fn main()->unit{',b'module bad;\xff',
                    b'module bad;fn main()->str{return "unfinished;}']:
            self.file.write_bytes(raw)
            result=self.cli('fmt',self.file,'--write',ok=False)
            self.assertFalse(result['ok']);self.assertNotEqual(result['code'],'E_INTERNAL')
            self.assertEqual(self.file.read_bytes(),raw)
        self.file.write_text(formatted)
        for args in [[],[self.file,'--check','--write'],[self.file,'--write','--write'],
                     [self.file,'--revision','HEAD'],[self.file,'--output','out.nex']]:
            self.assertEqual(self.cli('fmt',*args,ok=False)['code'],'E_OPTION')
        self.assertEqual(self.file.read_text(),formatted)
        self.assertFalse((self.root/'.nex').exists())

    def test_execution_and_existing_graph_are_preserved(self):
        self.source('''module agreement;
fn twice(x:i64)->i64 requires(x>=0) ensures(value=>value==x*2){return x*2;}
fn main()->unit!{io,throw}{
 let xs:list<i64>=[1,2];let f:fn(i64)->i64=fn(x:i64)->i64{return x+xs[0];};
 print("Я🌍\\u0000");print(f(twice(xs[1])));print(false && 1/0==0);
 try{throw("EXPECTED","message");}catch(code,message){print(code);}finally{print("finally");}
}
''')
        checked=self.cli('check');revision=checked['revision']
        graph=h.database_rows(self.root/'.nex/graph.db')
        original=self.file.read_text()
        expected=self.cli('eval')['stdout']
        # Capture graph again after ordinary eval's independent synchronization.
        graph=h.database_rows(self.root/'.nex/graph.db')
        self.cli('fmt',self.file,'--check',ok=False)
        self.assertEqual(h.database_rows(self.root/'.nex/graph.db'),graph)
        self.cli('fmt',self.file,'--write')
        self.assertNotEqual(self.file.read_text(),original)
        self.assertEqual(h.database_rows(self.root/'.nex/graph.db'),graph)
        self.assertEqual(self.cli('check')['revision'],revision)
        self.assertEqual(self.cli('eval')['stdout'],expected)
        for profile in ['debug','release']:
            result=self.cli('run','--profile',profile)
            self.assertEqual(result['stdout'],expected)
        folder=self.root/'typescript'
        self.cli('emit','--kind','typescript','--directory',folder)
        (folder/'package.json').write_text('{"type":"module"}\n')
        driver=folder/'driver.mjs';driver.write_text("import {entry} from './program.ts';entry();\n")
        selected=os.environ.get('NEX_TSC');self.assertTrue(selected,'Use pinned NEX_TSC')
        tsc=Path(selected).resolve(strict=True)
        self.assertEqual(json.loads((tsc.parent.parent/'package.json').read_text())['version'],
            json.loads((h.REPO/'web/package.json').read_text())['devDependencies']['typescript'])
        for command in [
            [os.environ.get('NEX_NODE','node'),tsc,'--noEmit','--strict','--target','ES2022','--module','ESNext',
             '--moduleResolution','bundler','--allowImportingTsExtensions','--lib','ES2022,DOM',folder/'program.ts'],
            [os.environ.get('NEX_NODE','node'),'--experimental-strip-types',driver]]:
            result=subprocess.run(list(map(str,command)),capture_output=True,text=True,timeout=120)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            if command[-1]==driver:self.assertEqual(result.stdout,expected)

    def test_discovery_manifest_and_guide(self):
        capability=self.cli('describe','--field','source_formatting')['value']
        pack=json.loads((h.REPO/'llm/language-pack.json').read_text())
        self.assertEqual(capability,pack['source_formatting'])
        guide=self.cli('guide','--kind','format')
        self.assertIn('nex fmt',json.dumps(guide))


if __name__=='__main__':unittest.main()
