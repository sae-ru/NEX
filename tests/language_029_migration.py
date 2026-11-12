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
            bad=run(root,'migrate','--language-version','0.30','--kind','plan','--json',ok=False)
            self.assertEqual(bad['code'],'E_OPTION')

if __name__=='__main__':unittest.main()
