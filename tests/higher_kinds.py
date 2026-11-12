"""Higher-order constructor kind signatures such as F<_<_>>."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

COMPILER=Path(sys.argv.pop(1)).resolve()
SOURCE='''module higher;
struct Wrap<F<_>>{value:F<i64>;}
struct H<F<_<_>>,G<_>>{value:F<G>;}
fn hold<F<_<_>>,G<_>>(value:F<G>)->F<G>{return value;}
fn main()->unit !{io}{
 let wrap:Wrap<list>=Wrap<list>([1,2,3]);
 let held:Wrap<list>=hold<Wrap,list>(wrap);
 let nested:H<Wrap,list>=H<Wrap,list>(wrap);
 print(len(held.value));
 print(len(nested.value.value));
}
test fn values()->unit{
 assert(len(hold<Wrap,list>(Wrap<list>([1,2])).value)==2);
}
'''

def run(args,cwd,environment=None):
    return subprocess.run(list(map(str,[COMPILER]+args)),cwd=cwd,capture_output=True,text=True,timeout=240,
        env={**os.environ,**(environment or {})})

class HigherKinds(unittest.TestCase):
    def project(self,root,source):
        (root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.28','entry':'main.nex'})+'\n')
        (root/'main.nex').write_text(source)

    def test_higher_order_kinds_reference_native_and_optional_web(self):
        with tempfile.TemporaryDirectory(prefix='nex higher kinds ') as temporary:
            root=Path(temporary);self.project(root,SOURCE)
            checked=run(['check','--json'],root);self.assertEqual(checked.returncode,0,checked.stdout+checked.stderr)
            evaluated=run(['eval','--entry','main','--json'],root);self.assertEqual(evaluated.returncode,0,evaluated.stdout+evaluated.stderr)
            self.assertEqual(json.loads(evaluated.stdout)['stdout'],'3\n3\n')
            native=run(['test','--json'],root);self.assertEqual(native.returncode,0,native.stdout+native.stderr)
            native=json.loads(native.stdout);self.assertTrue(native['ok']);self.assertTrue(all(t['native'] for t in native['tests']))
            ran=run(['run','--profile','release','--json'],root);self.assertEqual(ran.returncode,0,ran.stdout+ran.stderr)
            self.assertEqual(json.loads(ran.stdout)['stdout'],'3\n3\n')
            tsc=os.environ.get('NEX_TSC')
            if tsc:
                web=run(['test','--target','web','--json'],root,{'NEX_TSC':tsc});self.assertEqual(web.returncode,0,web.stdout+web.stderr)
                web=json.loads(web.stdout);self.assertTrue(web['ok']);self.assertTrue(all(t['web'] for t in web['tests']))
            descriptor=json.loads(run(['describe','--field','generic_features','--json'],root).stdout)['value']
            self.assertIn('higher_order_kind_signatures',descriptor)

    def test_value_constructor_is_rejected_for_higher_order_slot(self):
        with tempfile.TemporaryDirectory(prefix='nex higher kinds reject ') as temporary:
            root=Path(temporary)
            self.project(root,'''module badkind;
struct Box<T>{value:T;}
fn hold<F<_<_>>,G<_>>(value:F<G>)->F<G>{return value;}
fn main()->unit !{io}{
 let box:Box<list>=Box<list>([1]);
 let bad:Box<list>=hold<Box,list>(box);
 print(len(bad.value));
}
''')
            result=run(['check','--json'],root);self.assertNotEqual(result.returncode,0)
            self.assertEqual(json.loads(result.stdout)['code'],'E_GENERIC_KIND')

if __name__=='__main__':unittest.main()
