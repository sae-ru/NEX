"""Native failures, archived graph mappings, cache reuse and hostile log input."""
import copy
import json
import shutil
import subprocess
import unittest
from pathlib import Path
import support as harness


class NativeDiagnostics(harness.ToolchainCase):
    def native_failure(self, *args):
        result = self.cli('run', *args, ok=False, timeout=150)
        self.assertIn('exit_code',result)
        self.assertEqual(result['exit_code'], 70, result)
        records = result['native_diagnostics']['diagnostics']
        self.assertEqual(len(records), 1, result)
        self.assertEqual(records[0]['status'], 'mapped', records)
        return result, records[0]

    def diagnose(self, build, log, **kwargs):
        path = self.root / 'native.log'
        path.write_text(log, newline="\n")
        return self.cli('diagnose', '--manifest', build['debug_manifest'], '--log', path, **kwargs)

    def test_runtime_failures_map_to_the_same_operations_as_the_interpreter(self):
        self.source('''module failures;
fn div()->i64{return 10/0;}
fn add()->i64{return 9223372036854775807+1;}
fn neg()->i64{let n:i64=-9223372036854775808;return -n;}
fn floating()->f64{return 1e308*1e308;}
fn index()->i64{return [1,2][2];}
fn scalar()->str{return "Я🧠"[2];}
fn result()->i64{return unwrap(err<i64>("CUSTOM","problem"));}
fn assertion()->unit{assert(false);}
fn main()->unit{assert(true);}
''')
        for entry, code in [('div','E_DIV_ZERO'), ('add','E_OVERFLOW'), ('neg','E_OVERFLOW'),
                            ('index','E_BOUNDS'), ('assertion','E_ASSERT')]:
            # Native application entries return i64/unit. Other value kinds use wrappers below.
            expected = self.cli('eval','--entry',entry,ok=False)
            for profile in ('debug','release'):
                with self.subTest(entry=entry,profile=profile):
                    result, mapped = self.native_failure('--entry',entry,'--profile',profile)
                    self.assertEqual(mapped['report']['code'],code)
                    self.assertEqual(mapped['operation_id'],expected['operation_id'])
                    self.assertEqual(mapped['operation_site'],expected['operation_site'])
                    self.assertEqual(mapped['source_hash'],expected['source_hash'])
        self.source(self.file.read_text()+'''fn real()->unit{let value:f64=floating();}
fn text()->unit{let value:str=scalar();}
fn recover()->unit{let value:i64=result();}
''')
        for entry, code in [('real','E_FLOAT'),('text','E_BOUNDS'),('recover','E_RESULT')]:
            with self.subTest(entry=entry):
                _, mapped = self.native_failure('--entry',entry)
                self.assertEqual(mapped['report']['code'],code)
                self.assertEqual(mapped['operation_site'],self.cli('eval','--entry',entry,ok=False)['operation_site'])

    def test_nested_calls_ltr_short_circuit_and_profile_preserve_the_actual_failure(self):
        self.source('''module order;
fn crash()->i64{return 7/0;}
fn mark(n:i64)->i64!{io}{print(n);return n;}
fn sum(a:i64,b:i64,c:i64)->i64{return a+b+c;}
fn main()->unit!{io}{assert(!(false&&(crash()==1)));assert(true||(crash()==1));print(sum(mark(1),crash(),mark(2)));}
''')
        expected=self.cli('eval',ok=False)
        for profile in ('debug','release','profile'):
            result, mapped=self.native_failure('--profile',profile)
            self.assertEqual(result['stdout'],'1\n')
            self.assertEqual(mapped['symbol'],'order::crash')
            self.assertEqual(mapped['operation_id'],expected['operation_id'])

    def test_generic_closure_failures_keep_derived_operation_identity(self):
        self.source('''module closures;
fn make<T:integer>(value:T)->(fn(T)->T){return fn(other:T)->T{return value/other;};}
fn main()->unit!{io}{let callback:fn(i64)->i64=make(42);print(callback(0));}
''')
        expected=self.cli('eval',ok=False)
        _, mapped=self.native_failure()
        self.assertEqual(mapped['operation_id'],expected['operation_id'])
        self.assertEqual(mapped['report']['source']['kind'],'expression.binary')

    def test_reused_functions_receive_current_application_identity(self):
        source='''module reuse;
fn sibling()->i64{return 1;}
fn broken()->i64{return 8/0;}
fn main()->unit!{io}{print(sibling());print(broken());}
'''
        self.source(source)
        first, before=self.native_failure()
        self.source(source.replace('return 1;','return 2;'))
        second, after=self.native_failure()
        built=self.cli('build')
        compilation=json.loads(Path(built['compilation']).read_text())
        self.assertEqual(compilation['compiled_functions'],1)
        self.assertEqual(compilation['reused_functions'],2)
        self.assertEqual(before['operation_id'],after['operation_id'])
        self.assertEqual(before['report']['source'],after['report']['source'])
        self.assertNotEqual(before['revision'],after['revision'])
        self.assertNotEqual(before['build_key'],after['build_key'])
        self.assertEqual(second['stdout'],'2\n')
        stale=self.diagnose(built,first['stderr'])['diagnostics'][0]
        self.assertEqual(stale['status'],'unmapped')
        self.assertNotIn('operation_id',stale)

    def test_comment_edits_and_line_moves_do_not_misattribute_old_reports(self):
        source='module moved;\nfn main()->i64{//first\nreturn 1/0;}\n'
        self.source(source); first, before=self.native_failure()
        self.source(source.replace('//first','//later'))
        _, after=self.native_failure();built=self.cli('build')
        self.assertEqual(before['revision'],after['revision'])
        self.assertEqual(before['operation_site'],after['operation_site'])
        self.assertNotEqual(before['source_hash'],after['source_hash'])
        self.assertEqual(self.diagnose(built,first['stderr'])['diagnostics'][0]['status'],'unmapped')
        self.source('// new line\n'+self.file.read_text());_, moved=self.native_failure()
        self.assertEqual(moved['operation_id'],after['operation_id'])
        self.assertEqual(moved['location']['line'],after['location']['line']+1)

    def test_standalone_and_new_store_map_after_source_deletion(self):
        self.source('module archived;fn main()->i64{return 9/0;}')
        _, before=self.native_failure();built=self.cli('build')
        archive=self.root/'graph.json';archive.write_text(json.dumps(self.cli('graph')), newline="\n")
        standalone=self.root/'standalone';shutil.copy2(built['executable'],standalone)
        self.file.unlink()
        child=subprocess.run([standalone],capture_output=True,text=True,timeout=30)
        self.assertEqual(child.returncode,70)
        other=self.root/'restored';other.mkdir();(other/'nex.json').write_text('{"language":"0.24","entry":"main.nex"}', newline="\n");self.cli('import',archive,cwd=other)
        log=self.root/'standalone.log';log.write_text(child.stderr, newline="\n")
        mapped=self.cli('diagnose','--revision','HEAD','--manifest',built['debug_manifest'],'--log',log,cwd=other)['diagnostics'][0]
        self.assertEqual(mapped['status'],'mapped')
        self.assertEqual(mapped['operation_site'],before['operation_site'])
        self.assertNotEqual(mapped['operation_id'],before['operation_id'])
        self.assertFalse((other/'main.nex').exists())

    def test_forged_and_malformed_records_never_get_local_ids(self):
        self.source('module forged;fn main()->i64{return 9/0;}')
        result, mapped=self.native_failure();built=self.cli('build');raw=mapped['report']
        cases=[]
        for section,key,value in [('application','revision','0'*64),('application','build_key','0'*64),
                                  ('source','compiler_build','0'*64),('source','function_source_hash','0'*64),
                                  ('source','byte_begin',9000),('source','kind','expression.string'),
                                  ('application','language','0.14')]:
            entry=copy.deepcopy(raw);entry[section][key]=value;cases.append(entry)
        log=''.join('NEX_NATIVE_TRAP '+json.dumps(entry)+'\n' for entry in cases)
        decoded=self.diagnose(built,log)['diagnostics']
        self.assertEqual(len(decoded),len(cases))
        for entry in decoded:
            self.assertEqual(entry['status'],'unmapped')
            self.assertNotIn('operation_id',entry)
        bounded=self.diagnose(built,'NEX_NATIVE_TRAP {\nNEX_NATIVE_TRAP '+('x'*70000)+'\nNEX_NATIVE_TRAP '+('['*2000)+(']'*2000)+'\n'+result['stderr']*40)
        self.assertEqual((bounded['total'],bounded['omitted'],bounded['ignored'],len(bounded['diagnostics'])),(40,8,3,32))
        self.assertTrue(all(entry['status']=='mapped' for entry in bounded['diagnostics']))

    def test_log_and_manifest_input_are_bounded_regular_utf8_files(self):
        self.source('module files;fn main()->i64{return 0;}');built=self.cli('build')
        log=self.root/'input.log';log.write_text('', newline="\n")
        alias=self.root/'alias';alias.symlink_to(log)
        for path in (alias,self.root):
            error=self.cli('diagnose','--manifest',built['debug_manifest'],'--log',path,ok=False)
            self.assertEqual(error['code'],'E_DIAGNOSTIC_LIMIT')
        log.write_bytes(b'\xff')
        self.assertEqual(self.cli('diagnose','--manifest',built['debug_manifest'],'--log',log,ok=False)['code'],'E_JSON')
        log.write_bytes(b'x'*(4*1048576+1))
        self.assertEqual(self.cli('diagnose','--manifest',built['debug_manifest'],'--log',log,ok=False)['code'],'E_DIAGNOSTIC_LIMIT')

    def test_file_failure_unwrap_keeps_its_source_operation(self):
        data=self.root/'data';data.mkdir();env={'NEX_FILES_ROOT':str(data)}
        self.source('module file_trap;server fn main()->unit!{fs}{let text:str=unwrap(file_read_text("missing"));}')
        expected=self.cli('eval',env=env,ok=False)
        for profile in ('debug','release'):
            with self.subTest(profile=profile):
                native=self.cli('run','--profile',profile,env=env,ok=False)
                self.assertEqual(native.get('exit_code'),70,native)
                mapped=native['native_diagnostics']['diagnostics'][0]
                self.assertEqual(mapped['status'],'mapped')
                self.assertEqual(mapped['report']['code'],'E_RESULT')
                self.assertEqual(mapped['operation_id'],expected['operation_id'])

    def test_external_grant_failure_maps_to_its_checked_native_wrapper(self):
        self.source('module foreigns;server extern fn call()->i64!{ffi}=foreign("test","call","'+'0'*64+'");server fn main()->i64!{ffi}{return call();}')
        _, mapped=self.native_failure()
        self.assertEqual(mapped['symbol'],'foreigns::call')
        self.assertEqual(mapped['report']['code'],'E_FFI_GRANT')
        self.assertEqual(mapped['report']['source']['kind'],'block')

    def test_http_traps_and_budget_failures_keep_request_ids_in_operator_logs(self):
        import server_http as http
        self.source('''module requests;
import "std/http.nex" as http;
server fn handle(request:http::Request)->http::Response{
 if request.path=="/api/trap"{assert(false);}
 if request.path=="/api/loop"{while true{}}
 return http::json_response(200,"true");
}''')
        auth=self.root/'auth.json';token=self.cli('token','--user','alice','--auth',auth)['token']
        assets=self.root/'assets';assets.mkdir();(assets/'index.html').write_text('NEX', newline="\n")
        built=self.cli('build','--target','server','--profile','release',timeout=180)
        process=http.HTTP.launch(self,built['executable'],auth,budget=100)
        requests=[]
        try:
            for path,status,code in [('/api/trap',500,'E_ASSERT'),('/api/loop',429,'E_LIMIT')]:
                actual,body,headers=http.HTTP.request(self,path,token=token)
                self.assertEqual(actual,status)
                self.assertEqual(body['error'],{'code':code,'message':'request failed'})
                self.assertEqual(set(body),{'error','request_id'})
                self.assertEqual(headers['X-Request-Id'],body['request_id']);requests.append(body['request_id'])
            self.assertEqual(http.HTTP.request(self,'/health')[0],200)
        finally:
            process.terminate();stdout,stderr=process.communicate(timeout=20)
        self.assertEqual(process.returncode,0,stdout+stderr)
        mapped=self.diagnose(built,stderr)['diagnostics']
        self.assertEqual(len(mapped),2)
        self.assertEqual([entry['report']['request_id'] for entry in mapped],requests)
        self.assertEqual([entry['report']['code'] for entry in mapped],['E_ASSERT','E_LIMIT'])
        self.assertTrue(all(entry['status']=='mapped' for entry in mapped))

    def test_unicode_and_multiline_user_errors_produce_one_bounded_json_record(self):
        message='Я🧠\n'*900
        self.source('module text;fn main()->i64{return unwrap(err<i64>("CUSTOM",'+json.dumps(message,ensure_ascii=False)+'));}')
        result, mapped=self.native_failure()
        raw=mapped['report']
        self.assertTrue(raw['message_truncated'])
        self.assertLessEqual(len(raw['message'].encode()),4096)
        self.assertTrue(('CUSTOM: '+message).startswith(raw['message']))
        marked=[line for line in result['stderr'].splitlines() if line.startswith('NEX_NATIVE_TRAP ')]
        self.assertEqual(len(marked),1)
        self.assertEqual(json.loads(marked[0].removeprefix('NEX_NATIVE_TRAP ')),raw)


if __name__=='__main__':unittest.main()
