"""Actual NEX callable objects through the compiler-private CPU worker bridge."""
from host_fixture import run_native
import json,os,subprocess,sys,unittest
from pathlib import Path
PROBE=str(Path(sys.argv.pop(2)).resolve())
import support as harness

class CompiledWorkers(harness.ToolchainCase):
    def test_actual_nex_closures_keep_tags_captures_errors_and_owned_cleanup(self):
        (self.root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':self.cli('describe')['version'],'entry':'component/main.nex'}), newline="\n")
        # The private staging API uses the source directory's parent as project
        # root, matching the component layout used by actual project builds.
        (self.root/'component').mkdir();self.file=self.root/'component/main.nex'
        self.source('''module compiled_bridge;
pub struct Bundle {
 decorate:fn(i64)->str;
 floating:fn(f64)->f64;
 negate:fn(bool)->bool;
 identity:fn(str)->str;
 nested:fn(i64)->(fn(i64)->i64);
 checked:fn(i64)->i64;
 propagate:fn(i64)->result<str>;
}
pub fn make()->Bundle {
 let prefix:str="Я🧠:";
 return Bundle(
  fn(x:i64)->str{let held:list<str>=[prefix,"temporary"];assert(len(held)==2);return prefix+str(x);},
  fn(x:f64)->f64{return x+0.5;},
  fn(x:bool)->bool{return !x;},
  fn(x:str)->str{return x;},
  fn(x:i64)->(fn(i64)->i64){return fn(y:i64)->i64{return x+y;};},
  fn(x:i64)->i64{return 10/(x-2);},
  fn(x:i64)->result<str>{let held:list<str>=[prefix,"temporary"];
   assert(len(held)==2);if(x==1){return ok("unnamed"+err<str>("WORKER","ошибка 🧠")?);}
   return ok(prefix+str(x));}
 );
}
''')
        staged=run_native([PROBE,str(self.file),str(self.root/'cache'),json.dumps({'entry':'make','library':True,'code_only':True,'pic':True,'defer':True})],cwd=self.root,capture_output=True,text=True,timeout=180)
        self.assertEqual(staged.returncode,0,staged.stdout+staged.stderr);built=json.loads(staged.stdout)
        meta=json.loads(Path(built['metadata']).read_text());self.assertTrue(meta['deferred_link']);self.assertEqual(meta['kind'],'object_archive')
        compiler=self.cli('doctor')['native_compiler'];output=self.root/'compiled-worker-test'
        command=[compiler,'-std=c++20','-g','-pthread','-DNEX_STRUCTURED_WORKERS','-DNEX_PROFILE_ENABLED','-I',str(harness.REPO/'runtime'),str(harness.REPO/'tests/compiled_workers.cpp'),str(harness.REPO/'runtime/runtime.cpp'),str(harness.REPO/'runtime/nex_files.cpp'),*[str(harness.REPO/'runtime'/name) for name in ('nex_resource_region.cpp','nex_external_resource.cpp','nex_resource_executor.cpp')],built['artifact'],'-o',str(output)]
        sanitizer=os.environ.get('NEX_TEST_COMPILED_WORKER_SANITIZER','')
        self.assertIn(sanitizer,('','address,undefined','thread'))
        if sanitizer:command[1:1]=['-fsanitize='+sanitizer,'-fno-omit-frame-pointer','-O1']
        compiled=run_native(command,cwd=self.root,capture_output=True,text=True,timeout=180)
        self.assertEqual(compiled.returncode,0,compiled.stdout+compiled.stderr)
        observed=run_native([str(output)],cwd=self.root,capture_output=True,text=True,timeout=30)
        self.assertEqual(observed.returncode,0,observed.stdout+observed.stderr);report=json.loads(observed.stdout)
        self.assertTrue(report['ok']);self.assertEqual(report['cases'],7);self.assertTrue(report['actual_nex_closure_bodies'])
        self.assertEqual(report['simultaneous_workers'],4);self.assertEqual(report['live_handles'],0);self.assertEqual(report['live_objects'],0)

if __name__=='__main__':unittest.main()
