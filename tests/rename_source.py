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

    def test_cross_file_references_are_rewritten(self):
        temporary=tempfile.TemporaryDirectory(prefix='nex source rename cross ');root=Path(temporary.name)
        with temporary:
            (root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.28','entry':'main.nex'})+'\n')
            (root/'main.nex').write_text('module app;\nimport "./util.nex" as util;\nfn main()->unit !{io}{print(util::old(41));}\n')
            (root/'util.nex').write_text('module util;\npub fn old(x:i64)->i64{return x+1;}\n')
            nex(root,'check','--json')
            before=nex(root,'identities','--entity','function','--json')['nodes']
            before_id=next(node['id'] for node in before if node['symbol']=='util::old')
            result=run(root,'--from','util::old','--to','util::new')
            self.assertEqual(set(result['files']),{'main.nex','util.nex'})
            self.assertIn('util::new(41)',(root/'main.nex').read_text())
            self.assertIn('fn new',(root/'util.nex').read_text())
            after=nex(root,'identities','--entity','function','--json')['nodes']
            self.assertEqual(next(node['id'] for node in after if node['symbol']=='util::new'),before_id)
    def test_type_rename_preserves_declaration_identity(self):
        temporary,root=self.project()
        with temporary:
            (root/'main.nex').write_text('module app;\npub struct Old{v:i64;}\nfn main()->unit !{io}{print(Old(7).v);}\n')
            nex(root,'check','--json')
            before=nex(root,'identities','--entity','type','--json')['nodes'][0]
            result=run(root,'--from','app::Old','--to','app::New')
            self.assertEqual(result['moved'][0]['id'],before['id'])
            self.assertIn('struct New',(root/'main.nex').read_text())
            self.assertIn('New(7)',(root/'main.nex').read_text())
            after=nex(root,'identities','--entity','type','--json')['nodes'][0]
            self.assertEqual(after['symbol'],'app::New');self.assertEqual(after['id'],before['id'])
    def test_import_alias_rename_updates_only_alias_and_qualified_references(self):
        temporary=tempfile.TemporaryDirectory(prefix='nex alias rename ');root=Path(temporary.name)
        with temporary:
            (root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.28','entry':'main.nex'})+'\n')
            (root/'util.nex').write_text('module util;\npub fn helper()->i64{return 42;}\n')
            (root/'main.nex').write_text('module app;\nimport "./util.nex" as util;\nfn main()->i64{return util::helper();}\n')
            head=nex(root,'check','--json')['revision']
            planned=run(root,'--import-alias','util','--to','u','--dry-run')
            self.assertTrue(planned['dry_run']);self.assertIn('as util',(root/'main.nex').read_text())
            result=run(root,'--import-alias','util','--to','u')
            text=(root/'main.nex').read_text()
            self.assertIn('import "./util.nex" as u;',text);self.assertIn('u::helper()',text)
            self.assertEqual(result['revision'],head)
            nex(root,'check','--json')
    def test_cross_module_source_move_preserves_identity(self):
        temporary=tempfile.TemporaryDirectory(prefix='nex module rename ');root=Path(temporary.name)
        with temporary:
            (root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.28','entry':'main.nex'})+'\n')
            (root/'app.nex').write_text('module app;\npub fn old(x:i64)->i64{return x+1;}\n')
            (root/'main.nex').write_text('module root;\nimport "./app.nex" as app;\nfn main()->unit !{io}{print(app::old(41));}\n')
            nex(root,'check','--json')
            before=nex(root,'identities','--entity','function','--json')['nodes']
            before_id=next(node['id'] for node in before if node['symbol']=='app::old')
            result=run(root,'--from','app::old','--to','lib::new')
            self.assertEqual(set(result['files']),{'app.nex','main.nex'})
            self.assertIn('module lib;',(root/'app.nex').read_text())
            self.assertIn('fn new',(root/'app.nex').read_text())
            self.assertIn('app::new(41)',(root/'main.nex').read_text())
            after=nex(root,'identities','--entity','function','--json')['nodes']
            self.assertEqual(next(node['id'] for node in after if node['symbol']=='lib::new'),before_id)
if __name__=='__main__':unittest.main()
