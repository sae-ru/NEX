"""Source identifier rename that preserves the checked graph-local ID."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

NEX=Path(sys.argv.pop(1)).resolve();RUNNER=Path(__file__).resolve().parents[1]/'tools/nex_rename.py'

def run(root,*args,ok=True):
    result=subprocess.run([sys.executable,'-B',str(RUNNER),'--compiler',str(NEX),'--project',str(root),*args],cwd=root,capture_output=True,text=True,timeout=180)
    if ok:assert result.returncode==0,(result.stdout,result.stderr)
    else:assert result.returncode!=0
    return json.loads(result.stdout) if result.stdout.strip() and result.stdout.lstrip().startswith('{') else None

def nex(root,*args):
    result=subprocess.run([str(NEX),*args],cwd=root,capture_output=True,text=True,timeout=180);assert result.returncode==0,(result.stdout,result.stderr);return json.loads(result.stdout)

class SourceRename(unittest.TestCase):
    def project(self):
        temporary=tempfile.TemporaryDirectory(prefix='nex source rename ');root=Path(temporary.name)
        (root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.28','entry':'main.nex'})+'\n')
        (root/'main.nex').write_text('''module app;
// old comment must not change
fn old(x:i64)->i64{return x+1;}
fn main()->unit !{io}{print("old");print(old(old(40)));}
''')
        return temporary,root

    def identity(self,root,symbol):
        check=nex(root,'check','--json');nodes=nex(root,'identities','--entity','function','--symbol',symbol,'--json')
        return check['revision'],nodes['nodes'][0]['id']

    def test_source_and_identity_rename_skips_comments_and_strings(self):
        temporary,root=self.project()
        with temporary:
            head,before=self.identity(root,'old')
            planned=run(root,'--from','app::old','--to','app::new','--dry-run')
            self.assertTrue(planned['dry_run']);self.assertIn('fn old',(root/'main.nex').read_text())
            result=run(root,'--from','app::old','--to','app::new')
            self.assertEqual(result['moved'][0]['id'],before)
            text=(root/'main.nex').read_text()
            self.assertIn('fn new',text);self.assertIn('new(new(40))',text)
            self.assertIn('// old comment must not change',text);self.assertIn('"old"',text)
            self.assertNotEqual(result['revision'],head)
            _,after=self.identity(root,'new');self.assertEqual(after,before)
            run(root,'--from','old','--to','app::other',ok=False)

if __name__=='__main__':unittest.main()
