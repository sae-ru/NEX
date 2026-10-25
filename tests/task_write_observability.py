"""Actual DAP stops and complete profiler reports for ABI4 write providers."""
import argparse,hashlib,json,os,sys,tempfile,time,traceback,unittest
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--compiler',type=Path,required=True);p.add_argument('--resources',type=Path);p.add_argument('--output',type=Path);a=p.parse_args()
temporary=tempfile.TemporaryDirectory(prefix='nex write observability ') if not a.output else None
O=(a.output or Path(temporary.name)/'evidence').resolve();O.mkdir();S=(a.resources or Path(__file__).resolve().parents[1]).resolve();compiler=a.compiler.resolve()
sys.path.insert(0,str(S/'tests'));sys.argv=[__file__,str(compiler)]
os.environ['NEX_RESOURCE_DIR']=str(S);os.environ['NEX_TASK_PROVIDER_DEBUG_OUTPUT']=str(O/'dap');os.environ['NEX_TASK_PROVIDER_PROFILE_OUTPUT']=str(O/'profile')
import task_provider_debugging as debug
import task_provider_profile as profile
TEXT='A🌍\0λ'
started=time.monotonic();report={'schema':'nex.public-write-observability/1','ok':False,'state':'starting','compiler_sha256':hashlib.sha256(compiler.read_bytes()).hexdigest(),'checks':[],'full_objective_complete':False}
def save():report['seconds']=round(time.monotonic()-started,3);(O/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
class WriterDAP(debug.TaskProviderDebugging):
 def test_actual_write_resume(self):
  self.mixed()
  source=debug.LEAF+'''\npub server fn save(path:str,text:str)->result<bool> !{task,fs}{
 let answer:bool=file_write_text(path,text)?;
 task_yield(); // actual-write-done
 return ok(answer);
}
'''
  (self.root/'leaf/value.nex').write_text(source)
  (self.root/'mid/value.nex').write_text(debug.MID+'\npub server fn save(path:str,text:str)->result<bool> !{task,fs}{return leaf::save(path,text);}\n')
  self.description['components']['leaf']['exports'].append('save');self.description['components']['mid']['exports'].append('save');self.save()
  self.file.write_text(r'''module debug_app;import "../mid/value.nex" as mid;
server fn main()->unit !{task,fs,io}{assert(unwrap(mid::save("written","A🌍\u0000λ")));print(42);}''')
  grant=self.root/'grant';grant.mkdir();(grant/'written').write_text('original')
  _,session,_,manifest=self.prepare()
  function=next(f for f in manifest['functions'] if f['name']=='debug_leaf::save')
  line=next(i+1 for i,text in enumerate(source.splitlines()) if '// actual-write-done' in text)
  old={key:os.environ.get(key) for key in ['NEX_FILES_ROOT','NEX_FILES_WRITE']}
  os.environ.update(NEX_FILES_ROOT=str(grant),NEX_FILES_WRITE='1')
  observations={}
  def body(adapter):
   selected=adapter.request('threads')['nex']['selected'];self.assertTrue(selected)
   stack=adapter.request('stackTrace',{'threadId':selected});self.assertEqual(stack['stackFrames'][0]['name'],'debug_leaf::save')
   frame=stack['stackFrames'][0]['id']
   before=adapter.request('evaluate',{'expression':'len(text)','frameId':frame,'context':'watch'})
   self.assertEqual(before['nex']['value'],'4');self.assertEqual((grant/'written').read_text(),'original')
   adapter.request('setFunctionBreakpoints',{'breakpoints':[]})
   points=adapter.request('setBreakpoints',{'source':{'path':function['task_debug']['file']},'breakpoints':[{'line':line}]})
   self.assertTrue(points['breakpoints'][0]['verified'])
   adapter.request('continue',{'threadId':selected});adapter.event('stopped')
   stack=adapter.request('stackTrace',{'threadId':selected});self.assertEqual(stack['stackFrames'][0]['name'],'debug_leaf::save')
   after=adapter.request('evaluate',{'expression':'answer','frameId':stack['stackFrames'][0]['id'],'context':'watch'})
   self.assertIs(after['nex']['value'],True);self.assertEqual((grant/'written').read_bytes(),TEXT.encode())
   self.assertEqual(after['nex']['source_identity']['component'],'leaf');self.assertEqual(after['nex']['source_identity']['owner_image'],'mid')
   adapter.request('setBreakpoints',{'source':{'path':function['task_debug']['file']},'breakpoints':[]})
   adapter.request('continue',{'threadId':selected});self.assertEqual(adapter.event('exited')['exitCode'],0)
   observations.update(before_value=before['nex']['value'],after_value=after['nex']['value'],source_identity=after['nex']['source_identity'])
  try:self.dap(session,'debug_leaf::save',body)
  finally:
   for key,value in old.items():
    if value is None:os.environ.pop(key,None)
    else:os.environ[key]=value
  report['checks'].append({'kind':'actual_DAP_write_resume','mixed_static_shared':True,'before_write_unchanged':True,'after_write_exact_unicode_NUL':True,'exit_code':0,**observations});save()
class WriterProfile(profile.TaskProviderProfiles):
 def test_actual_write_profiles(self):
  self.shared_graph()
  (self.root/'leaf/value.nex').write_text(profile.LEAF+'\npub server fn save(path:str,text:str)->result<bool> !{task,fs}{task_yield();return file_write_text(path,text);}\n')
  self.description['components']['leaf']['exports'].append('save')
  self.description['components']['app']['dependencies']={'leaf':'dynamic','unused':'dynamic'};self.save()
  self.file.write_text(r'''module profile_app;import "../leaf/value.nex" as leaf;
server fn main()->unit !{task,fs,io}{let result:result<bool>=leaf::save("written","A🌍\u0000λ");
 if error_code(result)=="CAPABILITY"{print("CAPABILITY");return;}assert(unwrap(result));print(42);}''')
  expected={name:0 for name in profile.COUNTS if not name.startswith('profile_mid::') and name!='profile_app::local'}
  expected.update({'profile_app::main':1,'profile_leaf::save':1})
  grant=self.root/'grant';grant.mkdir();(grant/'written').write_text('original')
  for allowed,stdout in [(False,'CAPABILITY\n'),(True,'42\n')]:
   result=self.project('profile','app','measured','--events','0',env={'NEX_FILES_ROOT':str(grant),'NEX_FILES_WRITE':'1' if allowed else '0'})
   saved=self.measured(result,expected,stdout,timeline=False)
   self.assertEqual((grant/'written').read_bytes(),TEXT.encode() if allowed else b'original')
   self.assertGreater(saved['dropped_events'],0)
   report['checks'].append({'kind':'actual_write_profile','write_grant':allowed,'all_invocations_terminal':True,'all_pools_empty':True,'exact_file_observed':True,'profile':result['observation']['output']});save()
try:
 for cls,name in [(WriterDAP,'test_actual_write_resume'),(WriterProfile,'test_actual_write_profiles')]:
  report['state']=name;save();case=cls(name);case.setUp()
  try:getattr(case,name)()
  finally:case.tearDown()
 report.update(ok=True,state='passed')
except BaseException as error:report.update(state='failed',error=repr(error),traceback=traceback.format_exc());traceback.print_exc()
finally:save();print(json.dumps({k:report.get(k) for k in ['ok','state','error']}))
if temporary:temporary.cleanup()
raise SystemExit(0 if report['ok'] else 1)
