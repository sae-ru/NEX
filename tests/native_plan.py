"""Checked local/qualified/generic names and precise native-plan contracts."""
import json,os,subprocess,sys,unittest
from pathlib import Path
PROBE=str(Path(sys.argv.pop(2)).resolve())
import support as harness

class NativePlan(harness.ToolchainCase):
    def setUp(self):
        super().setUp()
        (self.root/'left.nex').write_text('''module left;
pub struct Box{text:str;}
pub fn value()->str{return "left";}
pub fn make()->Box{return Box(value());}
''', newline="\n")
        (self.root/'right.nex').write_text('''module right;
pub struct Box{flag:bool;}
pub fn value()->bool{return true;}
pub fn make()->Box{return Box(value());}
''', newline="\n")
        self.source('''module app;
import "./left.nex" as left;import "./right.nex" as right;
struct Box{number:i64;}
fn value()->i64{return 17;}
fn identity<T>(v:T)->T{return v;}
fn plus(n:i64)->i64{return n+value();}
fn calculate()->i64{
 let a:left::Box=identity(left::make());let b:right::Box=identity(right::make());let local:Box=Box(value());
 assert(a.text=="left" && b.flag && local.number==17);
 let f:fn(i64)->i64=plus;return f(25);
}
fn main()->unit!{io}{print(calculate());}
test fn checked()->unit{assert(calculate()==42);}
''')

    def plan(self,ok=True,**options):
        p=subprocess.run([PROBE,str(self.file),json.dumps(options)],env=os.environ.copy(),cwd=self.root,capture_output=True,text=True,timeout=60)
        self.assertEqual(p.returncode==0,ok,p.stdout+p.stderr)
        return json.loads(p.stdout)

    def test_qualified_and_local_entries_preserve_distinct_module_layouts(self):
        plan=self.plan()
        self.assertEqual(plan,self.plan(entry='app::main'))
        units={u['identity']:u for u in plan['units']}
        self.assertTrue({'left::value','right::value','app::value','app::calculate'}<=units.keys())
        self.assertEqual(self.cli('eval')['stdout'],'42\n')
        self.cli('test')
        contracts=[json.loads(u['contract']) for u in plan['units']]
        layouts={v['name'] for c in contracts for v in c['type_layouts']}
        self.assertTrue({'left::Box','right::Box','app::Box'}<=layouts)

    def test_generic_local_name_with_qualified_argument_matches_exact_entry(self):
        generic='identity<left::Box>'
        a=self.plan(entry=generic,exports=['value'])
        self.assertEqual(a,self.plan(entry='app::'+generic,exports=['app::value']))
        self.assertEqual({u['identity'] for u in a['units']},{'app::'+generic,'app::value'})
        contract=json.loads(next(u['contract'] for u in a['units'] if u['identity']=='app::'+generic))
        self.assertTrue(any(v['name']=='left::Box' for v in contract['type_layouts']))

    def test_callable_bridges_and_dependency_edges_keep_checked_identities(self):
        a=self.plan();b=self.plan(all_callable=True)
        self.assertEqual(a['dependencies'],b['dependencies'])
        self.assertEqual([u['identity'] for u in a['units']],sorted(u['identity'] for u in a['units']))
        selected={u['identity']:json.loads(u['contract'])['closure_bridges'] for u in a['units']}
        self.assertEqual(selected['app::plus'],['app::plus'])
        for unit in b['units']:
            self.assertEqual(json.loads(unit['contract'])['closure_bridges'],[unit['identity']])
        functions={v['name']:v for v in a['dependencies']['functions']}
        self.assertIn('app::value',functions['app::plus']['callees'])
        self.assertIn('app::plus',functions['app::value']['callers'])

    def test_unknown_entries_and_cross_module_local_aliases_retain_diagnostics(self):
        for name in ['absent','left::absent','make']:
            error=self.plan(ok=False,entry=name)
            self.assertEqual(error['code'],'E_NAME')
            self.assertIn("unknown function '"+name+"'",error['message'])

if __name__=='__main__':unittest.main()
