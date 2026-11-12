"""Partial type-lambda applications in checked source."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

COMPILER=Path(sys.argv.pop(1)).resolve()
SOURCE='''module lambdas;
struct Pair<A,B>{first:A;second:B;}
struct Wrapped<F<_>,T>{value:F<T>;}
fn forward<F<_>,T>(value:F<T>)->F<T>{return value;}
fn hold<F<_>,T>(value:F<T>)->Wrapped<F,T>{return Wrapped<F,T>(value);}
fn main()->unit !{io}{
 let pair:Pair<i64,str>=forward<Pair<i64,_>,str>(Pair<i64,str>(1,"x"));
 let held:Wrapped<Pair<i64,_>,str>=hold<Pair<i64,_>,str>(pair);
 print(held.value.second);
}
test fn values()->unit{
 assert(forward<Pair<i64,_>,str>(Pair<i64,str>(1,"x")).second=="x");
 assert(hold<Pair<i64,_>,str>(Pair<i64,str>(2,"y")).value.first==2);
}
'''

def run(args,cwd,environment=None):
    return subprocess.run(list(map(str,[COMPILER]+args)),cwd=cwd,capture_output=True,text=True,timeout=240,
        env={**os.environ,**(environment or {})})

class TypeLambdas(unittest.TestCase):
    def project(self,root,source):
        (root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.28','entry':'main.nex'})+'\n')
        (root/'main.nex').write_text(source)

    def test_partial_application_reference_native_and_optional_web(self):
        with tempfile.TemporaryDirectory(prefix='nex type lambdas ') as temporary:
            root=Path(temporary);self.project(root,SOURCE)
            checked=run(['check','--json'],root);self.assertEqual(checked.returncode,0,checked.stdout+checked.stderr)
            evaluated=run(['eval','--entry','main','--json'],root);self.assertEqual(evaluated.returncode,0,evaluated.stdout+evaluated.stderr)
            self.assertEqual(json.loads(evaluated.stdout)['stdout'],'x\n')
            native=run(['test','--json'],root);self.assertEqual(native.returncode,0,native.stdout+native.stderr)
            native=json.loads(native.stdout);self.assertTrue(native['ok']);self.assertTrue(all(t['native'] for t in native['tests']))
            ran=run(['run','--profile','release','--json'],root);self.assertEqual(ran.returncode,0,ran.stdout+ran.stderr)
            self.assertEqual(json.loads(ran.stdout)['stdout'],'x\n')
            tsc=os.environ.get('NEX_TSC')
            if tsc:
                web=run(['test','--target','web','--json'],root,{'NEX_TSC':tsc});self.assertEqual(web.returncode,0,web.stdout+web.stderr)
                web=json.loads(web.stdout);self.assertTrue(web['ok']);self.assertTrue(all(t['web'] for t in web['tests']))
            descriptor=json.loads(run(['describe','--field','generic_features','--json'],root).stdout)['value']
            self.assertIn('partial_type_lambdas',descriptor)

    def test_unknown_value_type_is_still_rejected(self):
        with tempfile.TemporaryDirectory(prefix='nex type lambdas reject ') as temporary:
            root=Path(temporary)
            self.project(root,'''module bad;
struct Pair<A,B>{first:A;second:B;}
fn forward<F<_>,T>(value:F<T>)->F<T>{return value;}
fn main()->unit !{io}{print("x");}
fn bad(value:Pair<i64,_>)->unit{}
''')
            result=run(['check','--json'],root);self.assertNotEqual(result.returncode,0)
            self.assertIn(json.loads(result.stdout)['code'],{'E_GENERIC_ARITY','E_TYPE','E_GENERIC_KIND'})

if __name__=='__main__':unittest.main()
