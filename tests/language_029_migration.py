"""Explicit 0.28 -> 0.29 migration and retained 0.28 gate."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

NEX=Path(sys.argv.pop(1)).resolve()

def run(root,*args,ok=True):
    result=subprocess.run([str(NEX),*args],cwd=root,capture_output=True,text=True,timeout=240)
    value=json.loads(result.stdout) if result.stdout.strip().startswith('{') else None
    if ok:assert result.returncode==0,(args,result.stdout,result.stderr)
    else:assert result.returncode!=0,(args,result.stdout,result.stderr)
    return value

class Language029Migration(unittest.TestCase):
    def test_029_context_patch_restore_export_and_import_use_archived_language(self):
        with tempfile.TemporaryDirectory(prefix='nex 029 graph ') as temporary:
            root=Path(temporary)
            manifest={'schema':'nex.project/1','language':'0.29','entry':'main.nex'}
            (root/'nex.json').write_text(json.dumps(manifest)+'\n')
            original='''module app;
struct Pair<A,B>{first:A;second:B;}
fn forward<F<_>,T>(value:F<T>)->F<T>{return value;}
fn value()->i64{return 42;}
fn main()->unit!{io}{let p:Pair<i64,str>=forward<Pair<i64,_>,str>(Pair<i64,str>(value(),"x"));print(p.first);}
'''
            (root/'main.nex').write_text(original)
            checked=run(root,'check','--json');first=checked['revision']
            context=run(root,'context','--symbol','value','--json')
            self.assertEqual(context['language'],'0.29');self.assertEqual(context['revision'],first)
            declared=run(root,'context','--entity','type','--symbol','Pair','--json')
            self.assertEqual(declared['language'],'0.29')
            graph=run(root,'graph','--json');self.assertEqual(graph['language'],'0.29')
            patch=root/'patch.json';patch.write_text(json.dumps({'expected_revision':first,
                'replacements':[{'name':'main','source':'fn main()->unit!{io}{let p:Pair<i64,str>=forward<Pair<i64,_>,str>(Pair<i64,str>(43,"x"));print(p.first);}'}]}))
            changed=run(root,'apply','--patch',str(patch),'--json')['revision'];self.assertNotEqual(changed,first)
            self.assertEqual((root/'main.nex').read_text(),original)
            self.assertEqual(run(root,'eval','--revision','HEAD','--json')['stdout'],'43\n')
            exported=root/'exported';run(root,'export','--directory',str(exported),'--json')
            self.assertEqual(json.loads((exported/'nex.lock.json').read_text())['language'],'0.29')
            self.assertEqual(run(exported,'check','--json')['revision'],changed)
            restored=run(root,'restore','--revision',first,'--expected-revision',changed,'--json')
            self.assertEqual(restored['revision'],first)
            self.assertEqual(run(root,'eval','--revision','HEAD','--json')['stdout'],'42\n')
            imported=root/'imported';imported.mkdir();(imported/'nex.json').write_text(json.dumps(manifest)+'\n')
            graph_path=root/'graph.json';graph_path.write_text(json.dumps(graph)+'\n')
            self.assertEqual(run(imported,'import',str(graph_path),'--json')['revision'],first)
            self.assertEqual(run(imported,'context','--symbol','value','--json')['revision'],first)
            self.assertEqual(run(root,'context','--symbol','value','--revision',changed,'--json')['revision'],changed)

    def test_028_project_migrates_to_029_and_gate_changes(self):
        with tempfile.TemporaryDirectory(prefix='nex 029 migration ') as temporary:
            root=Path(temporary)
            (root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.28','entry':'main.nex'})+'\n')
            (root/'main.nex').write_text('module app;\nstruct Pair<A,B>{first:A;second:B;}\nfn main()->unit !{io}{print(42);}\n')
            old=run(root,'check','--json');self.assertTrue(old['ok'])
            plan=run(root,'migrate','--language-version','0.29','--kind','plan','--json')
            self.assertEqual(plan['origin_language'],'0.28');self.assertEqual(plan['target_language'],'0.29')
            applied=run(root,'migrate','--language-version','0.29','--json')
            self.assertTrue(applied['ok']);self.assertEqual(applied['language'],'0.29');self.assertTrue(applied['changed'])
            (root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.29','entry':'main.nex'})+'\n')
            checked=run(root,'check','--json');self.assertTrue(checked['ok'])
            (root/'main.nex').write_text('module app;\nstruct Pair<A,B>{first:A;second:B;}\nfn forward<F<_>,T>(value:F<T>)->F<T>{return value;}\nfn main()->unit !{io}{let p:Pair<i64,str>=forward<Pair<i64,_>,str>(Pair<i64,str>(1,"x"));print(p.first);}\n')
            run(root,'check','--json')
            bad=run(root,'migrate','--language-version','0.31','--kind','plan','--json',ok=False)
            self.assertEqual(bad['code'],'E_OPTION')

if __name__=='__main__':unittest.main()
