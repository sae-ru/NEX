"""Source030 blocking storage stays on the task/HTTP invocation owner."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import unittest
import support as harness
import server_http

SOURCE='''module task_storage;
server fn read()->str!{db}{return unwrap(store_get("value"));}
server fn main()->unit!{db,task,throw,io}{
 let value:str=with_tasks(2,server fn(scope:task_scope)->str!{db,task,throw}{
  let child:task<str>=task_spawn(scope,server fn()->str!{db,task}{
   task_yield();assert(unwrap(store_put("value","Я🙂\\u0000")));
   assert(unwrap(store_keys(""))==["value"]);
   let kept:str=read();assert(unwrap(store_remove("value")));return kept;
  });return task_wait(child);
 });assert(error_code(store_get("value"))=="NOT_FOUND");print(value);
}
'''
HTTP='''module task_storage_http;
import "std/http.nex" as http;
struct Input{value:str;}
struct Fault{message:str;}
server fn handle(req:http::Request)->http::Response!{db,task,throw}{
 if req.method=="GET"{
  let value:result<str>=store_get("value");
  if is_ok(value){return http::json_response(200,encode_json(unwrap(value)));}
  return http::json_response(200,encode_json("missing"));
 }
 let input:Input=unwrap(decode_json<Input>(req.body));
 let value:str=with_tasks(1,server fn(scope:task_scope)->str!{db,task,throw}{
  let child:task<str>=task_spawn(scope,server fn()->str!{db,task,throw}{
   task_yield();assert(unwrap(store_put("value",input.value)));
   if req.path=="/api/throw"{throw(Fault(input.value));}
   if req.path=="/api/control"{while true{task_yield();}}
   return unwrap(store_get("value"));
  });return task_wait(child);
 });
 if req.path=="/api/rollback"{return http::json_response(409,encode_json(value));}
 return http::json_response(200,encode_json(value));
}
'''

class Storage(harness.ToolchainCase):
    launch=server_http.HTTP.launch
    stop=server_http.HTTP.stop
    request=server_http.HTTP.request

    def program(self,source,language='0.30'):
        (self.root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':language,'entry':'main.nex'})+'\n')
        self.source(source)

    def test_reference_and_native_storage_without_cells_use_owner_ABI8(self):
        self.program(SOURCE)
        for mode in ['reference','debug','release']:
            env={'NEX_DATABASE':str(self.root/(mode+'.sqlite')),'NEX_STORAGE_OWNER':'fixture'}
            if mode=='reference':observed=self.cli('eval',env=env)['stdout']
            else:
                built=self.cli('build','--profile',mode,timeout=300)
                metadata=json.loads(Path(built['metadata']).read_bytes())
                self.assertEqual(metadata['task_execution_abi'],0x4e45585400000008)
                result=subprocess.run([built['executable']],cwd=self.root,env={**os.environ,**env},capture_output=True,text=True,timeout=30)
                self.assertEqual(result.returncode,0,result.stderr);self.assertNotIn('E_INTERNAL_LEAK',result.stderr)
                observed=result.stdout
                cli_run=self.cli('run','--profile',mode,env=env,timeout=300)
                self.assertEqual(cli_run['stdout'],observed)
                self.assertEqual(cli_run['task_execution']['executor_workers'],1)
            self.assertEqual(observed,'Я🙂\0\n')

    def test_callback_requires_complete_caller_effects(self):
        self.program(SOURCE.replace('main()->unit!{db,task,throw,io}','main()->unit!{task,throw,io}'))
        self.assertEqual(self.cli('check',ok=False)['code'],'E_EFFECT')

    def test_retained029_callbacks_do_not_gain_storage(self):
        self.program(SOURCE,language='0.29')
        self.assertEqual(self.cli('check',ok=False)['code'],'E_EFFECT')

    def test_retained029_native_task_entry_still_rejects_db(self):
        self.program('module old;server fn main()->unit!{db,task}{task_yield();let value:result<str>=store_get("value");}',language='0.29')
        self.cli('check')
        self.assertEqual(self.cli('build',ok=False)['code'],'E_TASK_UNIMPLEMENTED')

    def test_HTTP_child_storage_keeps_transaction_on_success_error_and_control_exit(self):
        self.program(HTTP)
        (self.root/'assets').mkdir();(self.root/'assets/index.html').write_text('<h1>Storage</h1>')
        auth=self.root/'auth.json';token='task-storage-fixture'
        auth.write_text(json.dumps({'schema':'nex.auth/1','tokens':[{'user':'fixture','sha256':hashlib.sha256(token.encode()).hexdigest()}]}))
        for profile in ['debug','release']:
            built=self.cli('build','--target','server','--profile',profile,timeout=300)
            self.assertEqual(json.loads(Path(built['metadata']).read_bytes())['task_execution_abi'],0x4e45585400000008)
            process=self.launch(built['executable'],auth,env={'NEX_DATABASE':str(self.root/'wrong-ambient.sqlite'),'NEX_STORAGE_OWNER':'wrong'})
            try:
                committed='committed-'+profile
                status,value,_=self.request('/api/save',token=token,method='POST',body={'value':committed})
                self.assertEqual((status,value),(200,committed))
                for path,expected in [('/api/rollback',409),('/api/throw',500),('/api/control',429)]:
                    status,_,_=self.request(path,token=token,method='POST',body={'value':'uncommitted'})
                    self.assertEqual(status,expected,(path,status))
                    status,value,_=self.request('/api/read',token=token)
                    self.assertEqual((status,value),(200,committed),(path,value))
            finally:self.stop(process)
        self.assertFalse((self.root/'wrong-ambient.sqlite').exists())

if __name__=='__main__':unittest.main()
