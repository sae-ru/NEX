"""Explicit graph-local identity-preserving rename for checked functions and types."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

NEX=Path(sys.argv.pop(1)).resolve()
TOOL=Path(__file__).resolve().parent.parent/'tools'/'nex_rename.py'

def run(root,*args,ok=True):
    result=subprocess.run([str(NEX),*args],cwd=root,capture_output=True,text=True,timeout=180)
    value=json.loads(result.stdout) if result.stdout.strip() else None
    if ok:assert result.returncode==0,(args,result.stdout,result.stderr)
    else:assert result.returncode!=0,(args,result.stdout,result.stderr)
    return value

class IdentityRename(unittest.TestCase):
    def project(self,source):
        temporary=tempfile.TemporaryDirectory(prefix='nex identity rename ')
        root=Path(temporary.name)
        (root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.28','entry':'main.nex'})+'\n')
        (root/'main.nex').write_text(source)
        return temporary,root

    def checked(self,root,kind,symbol):
        check=run(root,'check','--json');nodes=run(root,'identities','--entity',kind,'--symbol',symbol,'--json')
        self.assertTrue(nodes['nodes']);return check['revision'],nodes['nodes'][0]['id']

    def rename(self,root,old,new,head,ok=True):
        return run(root,'identities','--kind','rename','--symbol',old,'--to',new,'--expected-revision',head,'--json',ok=ok)

    def test_function_and_type_identities_survive_source_rename(self):
        temporary,root=self.project('''module app;
pub struct Old{v:i64;}
fn old(x:i64)->i64{return x+1;}
fn main()->unit !{io}{print(old(Old(1).v));}
''')
        with temporary:
            head,function_id=self.checked(root,'function','old')
            _,type_id=self.checked(root,'type','Old')
            (root/'main.nex').write_text((root/'main.nex').read_text().replace('Old','New').replace('old','new'))
            result=self.rename(root,'app::old','app::new',head)
            self.assertEqual(result['schema'],'nex.identities-rename/1')
            self.assertEqual(result['moved'][0]['id'],function_id)
            result=self.rename(root,'app::Old','app::New',head)
            self.assertEqual(result['moved'][0]['id'],type_id)
            run(root,'check','--json')
            _,new_function=self.checked(root,'function','new')
            _,new_type=self.checked(root,'type','New')
            self.assertEqual(new_function,function_id)
            self.assertEqual(new_type,type_id)
            self.rename(root,'app::old','app::other',head,ok=False)

    def test_cross_module_move_preserves_function_identity(self):
        temporary,root=self.project('''module app;
fn old(x:i64)->i64{return x+1;}
fn main()->unit !{io}{print(old(41));}
''')
        with temporary:
            head,function_id=self.checked(root,'function','old')
            (root/'main.nex').write_text('''module lib;
fn new(x:i64)->i64{return x+1;}
fn main()->unit !{io}{print(new(41));}
''')
            result=self.rename(root,'app::old','lib::new',head)
            self.assertEqual(result['moved'][0]['symbol'],'lib::new')
            self.assertEqual(result['moved'][0]['id'],function_id)
            run(root,'check','--json')
            _,moved=self.checked(root,'function','new')
            self.assertEqual(moved,function_id)

    def test_conflict_and_stale_head_are_rejected(self):
        temporary,root=self.project('''module app;
fn old(x:i64)->i64{return x;}
fn other(x:i64)->i64{return x;}
fn main()->unit !{io}{print(old(1)+other(1));}
''')
        with temporary:
            head,_=self.checked(root,'function','old')
            before=(root/'main.nex').read_text()
            conflict=self.rename(root,'app::old','app::other',head,ok=False)
            self.assertEqual(conflict['code'],'E_IDENTITY')
            stale=self.rename(root,'app::old','app::new','0'*64,ok=False)
            self.assertEqual(stale['code'],'E_CONFLICT')
            self.assertEqual((root/'main.nex').read_text(),before)

class RenameTool(unittest.TestCase):
    def invoke(self,root,*args):
        return subprocess.run([sys.executable,str(TOOL),'--compiler',str(NEX),'--project',str(root),*args],capture_output=True,text=True,timeout=180)

    def test_failed_rename_restores_original_source(self):
        with tempfile.TemporaryDirectory(prefix='nex rename rollback ') as temporary:
            root=Path(temporary)
            (root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.28','entry':'main.nex'})+chr(10))
            original='''module app;
fn old(x:i64)->i64{return x+1;}
fn new(x:i64)->i64{return x+2;}
fn main()->unit !{io}{print(old(1)+new(2));}
'''
            (root/'main.nex').write_text(original)
            result=self.invoke(root,'--from','app::old','--to','changed::new')
            self.assertNotEqual(result.returncode,0)
            self.assertIn('E_DUPLICATE',result.stdout+result.stderr)
            self.assertEqual((root/'main.nex').read_text(),original)

    def test_rename_does_not_touch_same_name_in_another_module(self):
        with tempfile.TemporaryDirectory(prefix='nex rename modules ') as temporary:
            root=Path(temporary)
            (root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.28','entry':'main.nex'})+chr(10))
            (root/'left.nex').write_text('module left;'+chr(10)+'pub fn old(x:i64)->i64{return x+1;}'+chr(10))
            (root/'right.nex').write_text('module right;'+chr(10)+'pub fn old(x:i64)->i64{return x+2;}'+chr(10))
            (root/'main.nex').write_text('module app;'+chr(10)+'import "./left.nex" as left;'+chr(10)+'import "./right.nex" as right;'+chr(10)+'fn main()->unit !{io}{print(left::old(1)+right::old(2));}'+chr(10))
            right=(root/'right.nex').read_text()
            result=self.invoke(root,'--from','left::old','--to','left::renamed')
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertEqual((root/'right.nex').read_text(),right)
            self.assertIn('renamed',(root/'left.nex').read_text())
            main=(root/'main.nex').read_text()
            self.assertIn('left::renamed',main)
            self.assertIn('right::old',main)
            run(root,'check','--json')

if __name__=='__main__':unittest.main()
