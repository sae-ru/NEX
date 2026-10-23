"""Finite numeric source semantics, exact boundaries, migration and watches."""
import copy
import json
import math
from pathlib import Path
import random
import struct
import subprocess
import sys
import unittest
LIVE='--live' in sys.argv
if LIVE:sys.argv.remove('--live')
import support as harness


def bits(value):return struct.pack('>d',value).hex()


class Numbers(harness.ToolchainCase):
    def backends(self):
        reference=self.cli('eval')['stdout']
        for profile in ('debug','release'):
            self.assertEqual(self.cli('run','--profile',profile)['stdout'],reference)
            self.cli('test','--profile',profile)
        self.cli('test','--target','web')
        return reference

    def test_generic_aggregate_callback_example_and_discovery(self):
        self.source((harness.REPO/'examples/numbers.nex').read_text())
        output=self.backends();self.assertIn('2.5e0\n',output)
        self.assertIn('"E_RANGE"',output)
        descriptor=self.cli('describe');self.assertEqual(descriptor['version'],'0.20')
        self.assertIn('f64',descriptor['types'])
        self.assertEqual(descriptor['generic_constraints']['number'],['i64','f64'])
        self.assertEqual(set(descriptor['generic_constraints']['implications']['integer']),{'number','add','ordered','wire'})
        self.assertEqual(descriptor['numeric_limits']['literal_bytes'],4096)

    def test_generated_arithmetic_results_have_independent_python_bits(self):
        randomizer=random.Random(110064);expressions=[];expected=[]
        pairs=[(0.1,0.2),(1.0,2**-53),(math.nextafter(1.0,2.0),2**-53),
               (sys.float_info.min,2.0),(5e-324,2.0),(-5.5,2.0)]
        pairs.extend((randomizer.uniform(-1000,1000),randomizer.uniform(0.1,1000)) for _ in range(12))
        operations=[('+',lambda a,b:a+b),('-',lambda a,b:a-b),('*',lambda a,b:a*b),('/',lambda a,b:a/b),('%',math.fmod)]
        for a,b in pairs:
            for symbol,operation in operations:
                expressions.append('('+repr(a)+symbol+repr(b)+')');value=operation(a,b);expected.append(bits(value or 0.0))
        self.source('module numeric_vectors;fn values()->list<f64>{return ['+','.join(expressions)+'];}'
            'fn main()->unit!{io}{print(encode_json(values()));}'
            'test fn same()->unit!{io}{print(encode_json(values()));}')
        observed=self.cli('eval','--entry','values')['value']
        self.assertEqual([bits(v) for v in observed],expected)
        output=self.backends();self.assertEqual([bits(v) for v in json.loads(output)],expected)

    def test_browser_numeric_state_keeps_checked_values_and_reachable_code(self):
        self.source((harness.REPO/'examples/numbers-web.nex').read_text())
        self.assertEqual(self.backends(),'7.5e-1\n')
        directory=self.root/'numeric-browser'
        generated=self.cli('web','--directory',directory)
        for name in generated['files']:
            self.assertNotIn('FINITE_NUMBERS_SERVER_SENTINEL',(directory/name).read_text())

    def test_literal_rounding_canonical_identity_and_scalar_eval(self):
        revisions=[]
        for spelling in ['0.1','1e-1','0.1000000000000000055511151231257827021181583404541015625']:
            self.source('module canonical_float;fn value()->f64{return '+spelling+';}fn main()->unit!{io}{print(value());}')
            revisions.append(self.cli('check')['revision'])
            self.assertEqual(bits(self.cli('eval','--entry','value')['value']),bits(0.1))
        self.assertEqual(len(set(revisions)),1)
        nodes=self.cli('operations','--symbol','value')['nodes']
        literal=next(n for n in nodes if n['kind']=='expression.floating')
        self.assertEqual(literal['definition']['literal'],'1e-1')
        self.source('module edge;fn main()->unit!{io}{print([1.7976931348623157e308,5e-324,1e-9999,-0.0]);}'
            'test fn edge()->unit{assert(5e-324>0e0);assert(1e-9999==0e0);assert(-0.0==0e0);}')
        self.assertEqual(self.backends(),'[1.7976931348623157e308,5e-324,0e0,0e0]\n')

    def test_mixed_types_unsound_bounds_bad_literals_and_patterns_are_rejected(self):
        cases=[
            ('let x:f64=1;','E_TYPE'),('let x:i64=1e0;','E_TYPE'),
            ('let x:f64=1e0+1;','E_TYPE'),('let x:f64=as_f64(1e0);','E_TYPE'),
            ('let x:result<i64>=as_i64(1);','E_TYPE'),
            ('let x:f64=1e309;','E_RANGE'),('let x:f64=1e+;','E_FLOAT_LITERAL'),
            ('let x:f64=1e'+'9'*4096+';','E_FLOAT_LITERAL'),
            ('let x:f64=match 1e0 {1=>1e0,_=>0e0};','E_MATCH_TYPE'),
            ('let x:f64=match 1e0 {1e0=>1e0,_=>0e0};','E_PARSE')]
        for body,code in cases:
            with self.subTest(body=body[:60]):
                self.source('module rejected;fn main()->unit{'+body+'}')
                self.assertEqual(self.cli('check',ok=False)['code'],code)
        for declaration in ['fn bad<T:number>(x:T)->T{return x+1;}',
                            'fn bad<T:number>(x:T)->T{return 1.0;}',
                            'fn bad<T:ordered>(x:T)->T{return x-x;}',
                            'fn bad<T:integer>(x:T)->T{return x;}fn use()->f64{return bad(1e0);}']:
            self.source('module rejected;'+declaration+'fn main()->unit{}')
            self.assertIn(self.cli('check',ok=False)['code'],['E_TYPE','E_GENERIC_BOUND'])

    def test_checked_traps_keep_left_to_right_effects_and_short_circuit(self):
        for expression,code in [('left()/right()','E_DIV_ZERO'),('left()%right()','E_DIV_ZERO'),('left()*2e0','E_FLOAT')]:
            self.source('module traps;fn left()->f64!{io}{print("left");return 1.7976931348623157e308;}'
                'fn right()->f64!{io}{print("right");return 0e0;}'
                'fn main()->unit!{io}{print('+expression+');}')
            reference=self.cli('eval',ok=False);self.assertEqual(reference['code'],code)
            self.assertEqual(reference['stdout'],'left\nright\n' if 'right' in expression else 'left\n')
            for profile in ('debug','release'):
                native=self.cli('run','--profile',profile,ok=False)
                self.assertEqual(native['stdout'],reference['stdout']);self.assertIn(code,native['stderr'])

    def test_actual_023_sql_migration_preserves_history_sources_and_operation_ids(self):
        fixture=json.loads((harness.REPO/'tests/fixtures/language-0.10.json').read_text())
        self.source(fixture['source']);self.historical_store('0.10');self.file.unlink()
        self.assertEqual(self.cli('graph',ok=False)['code'],'E_LANGUAGE_VERSION')
        migrated=self.cli('migrate');self.assertEqual(migrated['language'],'0.20')
        self.assertEqual({r['language'] for r in self.cli('history')['revisions']},{'0.10','0.20'})
        graph=self.cli('graph');self.assertEqual(graph['bundle'],fixture['graph']['bundle'])
        self.assertEqual({n['name']:n['id'] for n in graph['nodes']},{n['name']:n['id'] for n in fixture['graph']['nodes']})
        self.assertEqual({n['path']:n['id'] for n in self.cli('operations','--symbol','choose')['nodes']},
                         {n['path']:n['id'] for n in fixture['operations']})
        self.assertEqual(self.cli('run','--revision','HEAD')['stdout'],'42\n')
        old=self.root/'old';self.cli('export','--revision',fixture['revision'],'--directory',old)
        self.assertEqual((old/'main.nex').read_text(),fixture['source'])
        self.assertEqual(json.loads((old/'nex.json').read_text())['language'],'0.10')

    def test_legacy_intrinsic_collision_migration_is_atomic_and_explicitly_repairable(self):
        fixture=json.loads((harness.REPO/'tests/fixtures/language-0.10-intrinsic.json').read_text())
        self.source(fixture['source']);self.historical_store('0.10-intrinsic')
        self.cli('migrate',ok=False);history=self.cli('history')
        self.assertEqual(history['head'],fixture['revision']);self.assertEqual(len(history['revisions']),1)
        repaired=copy.deepcopy(fixture['graph']);source=fixture['source'].replace('as_f64','legacy_float')
        repaired['source']=source;repaired['bundle']['files']['main.nex']=source
        patch=self.root/'repair.json';patch.write_text(json.dumps(repaired));self.cli('migrate',patch)
        self.assertEqual(self.cli('run','--revision','HEAD')['stdout'],'42\n')
        old=self.root/'old';self.cli('export','--revision',fixture['revision'],'--directory',old)
        self.assertEqual((old/'main.nex').read_text(),fixture['source'])

    def test_native_float_abi_host_validation_and_request_cleanup(self):
        self.source('''module float_scope;
pub fn host(value:f64,mode:i64)->f64{
 let owned:list<str>=["owned","before floating operation"];
 if mode==1{return value/0e0;}
 if mode==2{return value*1.7976931348623157e308;}
 if mode==3{if value>0e0{return value;}return 0e0;}
 return value+as_f64(len(owned));
}
fn main()->unit{}
''')
        library=self.cli('build','--library','--entry','host','--profile','release')
        host=self.root/'host.cpp';host.write_text('''#include "nex_host.h"
#include <cassert>
#include <limits>
extern "C" double nex_11_float_scope_4_host(double,int64_t);
int main(){
 for(int mode=0;mode<5;++mode){
  bool trapped=false;
  {nexrt::RequestScope request;
   double input=mode==2?2.0:mode==4?std::numeric_limits<double>::infinity():1.25;
   try{double value=nex_11_float_scope_4_host(input,mode);assert(mode==0||mode==3);assert(value==(mode==0?3.25:1.25));}
   catch(const nexrt::Trap &error){trapped=true;assert(error.code==(mode==1?"E_DIV_ZERO":"E_FLOAT"));assert(error.line>0);}
  }
  assert(trapped==(mode==1||mode==2||mode==4));nex_runtime_finish();
 }
 std::fesetround(FE_UPWARD);std::feclearexcept(FE_ALL_EXCEPT);std::feraiseexcept(FE_INVALID);
 {nexrt::RequestScope request;assert(nex_11_float_scope_4_host(1.25,0)==3.25);}
 assert(std::fegetround()==FE_UPWARD&&std::fetestexcept(FE_ALL_EXCEPT)==FE_INVALID);
 std::fesetenv(FE_DFL_ENV);nex_runtime_finish();
}
''')
        target=self.root/'host';compiler=self.cli('doctor')['native_compiler']
        completed=subprocess.run([compiler,'-std=c++20','-I',str(harness.REPO/'runtime'),str(host),library['executable'],'-o',str(target)],capture_output=True,text=True)
        self.assertEqual(completed.returncode,0,completed.stdout+completed.stderr)
        completed=subprocess.run([str(target)],capture_output=True,text=True,timeout=30)
        self.assertEqual(completed.returncode,0,completed.stdout+completed.stderr)

    def test_numeric_context_flows_through_generic_calls_without_coercing_literals(self):
        self.source('''module numeric_context;
fn read<T:wire>()->T{return unwrap(decode_json<T>("1.25"));}
fn identity<T>(x:T)->T{return x;}
fn negative<T:number>(x:T)->T{return -identity(x);}
fn main()->unit!{io}{let x:f64=-read();let y:f64=read()-0.25;print([x,y,negative(1.25)]);}
test fn cases()->unit{assert(read()<2e0);assert(1e0<read());assert(negative(1.25)==-1.25);}
''')
        self.assertEqual(self.backends(),'[-1.25e0,1e0,-1.25e0]\n')


DEBUG_SOURCE='''module numeric_debug;
fn make(offset:f64)->fn(f64)->f64{return fn(value:f64)->f64{return value+offset;};}
fn observe(number:f64,values:list<f64>,callback:fn(f64)->f64)->unit!{io}{
 print(callback(number)); // FLOAT_STOP
 print(values);
}
fn main()->unit!{io}{observe(1.25,[5e-324,-2.5],make(0.25));}
'''


class NumericFrames(harness.ToolchainCase):
    def setUp(self):
        super().setUp();self.source(DEBUG_SOURCE);self.session=self.cli('debug')
        self.manifest=Path(self.session['manifest']);self.identity=json.loads(self.manifest.read_text())
        self.frame={'schema':'nex.debug-frame/1','language':'0.20','revision':self.identity['revision'],
            'build_key':self.identity['build_key'],'function':'numeric_debug::observe',
            'stop':{'process_id':'100','thread_id':'101','frame_id':0,'stop_id':'1'},
            'bindings':[{'name':'number','type':'f64','value':1.25},
                        {'name':'values','type':'list<f64>','value':[5e-324,-2.5]},
                        {'name':'callback','type':'fn(f64)->f64','unavailable':'not captured'}],
            'truncated':False}
        self.framefile=self.root/'frame.json'
        self.schema=self.inspect('callback',kind='plan')['variables'][0]['wire_schema']
        self.target=next(name for name,value in self.schema['targets'].items() if value['captures'])
        self.frame['bindings'][2]={'name':'callback','type':'fn(f64)->f64','value':{
            'function':self.target,'identity':'10001','captures':{'offset':0.25}}}

    def inspect(self,expression,frame=None,kind=None,**kwargs):
        self.framefile.write_text(json.dumps(self.frame if frame is None else frame))
        return self.cli('inspect',self.framefile,'--manifest',self.manifest,'--expression',expression,
                        *(['--kind',kind] if kind else []),**kwargs)


class NumericDebug(NumericFrames):
    def test_full_scalar_aggregate_closure_watches_are_finite_and_exact(self):
        self.assertEqual(self.inspect('callback(number)')['display'],'1.5e0')
        self.assertEqual(bits(self.inspect('values[0]')['value']),bits(5e-324))
        self.assertEqual(self.inspect('(fn(extra:f64)->f64{return extra+number;})(0.25)')['value'],1.5)
        self.assertEqual(self.inspect('callback')['value']['captures'],{'offset':0.25})
        for bad in ['1.25',True,None]:
            frame=copy.deepcopy(self.frame);frame['bindings'][0]['value']=bad
            self.assertEqual(self.inspect('number',frame,ok=False)['code'],'E_DEBUG_VALUE')
        self.file.unlink();self.assertEqual(self.inspect('callback(number)')['value'],1.5)

    def test_demand_reads_only_selected_float_payloads(self):
        frame=copy.deepcopy(self.frame);frame['schema']='nex.debug-frame/2';frame['captures']=[]
        for binding in frame['bindings']:binding.pop('value',None);binding['unavailable']='not captured'
        reads=[]
        for _ in range(12):
            result=self.inspect('callback(number)+values[0]',frame,kind='demand')
            if result['schema']=='nex.expression/1':break
            request=result['request'];reads.append(request);binding,path,kind=request['binding'],request['path'],request['kind']
            if binding=='number':value=1.25
            elif binding=='values':value={'length':'20000'} if kind=='shape' else 5e-324
            elif path==[]:value={'function':self.target,'identity':'10001'}
            else:self.assertEqual(path,['offset']);value=0.25
            frame['captures'].append(dict({key:request[key] for key in ['binding','path','kind']},value=value))
        else:self.fail('numeric demand did not converge')
        self.assertEqual(result['value'],1.5)
        self.assertFalse(any(r['binding']=='values' and r['kind']=='value' and r['path']!=[0] for r in reads))


if LIVE:
    class LiveNumbers(NumericFrames):
        def test_actual_lldb_dap_float_roots_captures_pages_and_offline_replay(self):
            session=self.cli('debug','--kind','nex-dap');projected=self.identity['sources'][0]['projection']
            line=next(i+1 for i,text in enumerate(DEBUG_SOURCE.splitlines()) if '// FLOAT_STOP' in text)
            report=self.root/'numeric-watch.json';script=self.root/'numeric_watch.py'
            script.write_text('''import json,lldb
def __lldb_init_module(debugger,_):
 debugger.SetAsync(False);debugger.HandleCommand('settings set target.disable-aslr false')
 target=debugger.GetSelectedTarget();target.BreakpointCreateByLocation(SOURCE,LINE)
 process=target.LaunchSimple(None,None,None)
 def command(text):
  result=lldb.SBCommandReturnObject();debugger.GetCommandInterpreter().HandleCommand(text,result)
  assert result.Succeeded(),(text,result.GetOutput(),result.GetError())
  return json.loads(result.GetOutput())
 try:
  assert process.GetState()==lldb.eStateStopped
  stop=process.GetStopID()
  values={'root':command('nex-eval number'),'tiny':command('nex-eval values[0]'),
   'negative':command('nex-eval values[1]'),
   'callback':command('nex-eval callback(number)'), 'whole':command('nex-eval callback'),
   'snapshot':command('nex-frame callback(number)+values[0]')}
  assert process.GetStopID()==stop
  with open(REPORT,'w') as output:json.dump(values,output)
  process.Continue();assert process.GetState()==lldb.eStateExited and process.GetExitStatus()==0
 finally:
  if process.GetState() not in (lldb.eStateExited,lldb.eStateInvalid):process.Kill()
'''.replace('SOURCE',repr(projected)).replace('LINE',str(line)).replace('REPORT',repr(str(report))))
            output=self.cli('debug','--','--no-lldbinit','--batch','-o','command script import '+json.dumps(str(script)),machine=False)
            self.assertTrue(report.is_file(),output.stdout+output.stderr);captured=json.loads(report.read_text())
            self.assertEqual(captured['root']['display'],'1.25e0')
            self.assertEqual(bits(captured['tiny']['value']),bits(5e-324))
            self.assertEqual(captured['negative']['value'],-2.5)
            self.assertEqual(captured['callback']['value'],1.5)
            self.assertEqual(captured['whole']['value']['captures'],{'offset':0.25})
            self.file.unlink();snapshot=self.root/'saved.json';snapshot.write_text(json.dumps(captured['snapshot']))
            self.assertEqual(self.cli('inspect',snapshot,'--manifest',self.manifest,'--expression','callback(number)+values[0]')['value'],1.5)
            from debugging import DAP
            client=DAP(session['adapter_command'],self.root)
            try:
                client.request('initialize',{'adapterID':'nex','pathFormat':'path','linesStartAt1':True,'supportsVariablePaging':True})
                pending=client.send('launch',dict(session['launch'],disableASLR=False));client.event('initialized')
                client.request('setBreakpoints',{'source':{'path':projected},'breakpoints':[{'line':line}]})
                client.request('configurationDone');client.response(pending)
                stopped=client.event('stopped');frame=client.request('stackTrace',{'threadId':stopped['threadId']})['stackFrames'][0]['id']
                def evaluate(expression):return client.request('evaluate',{'expression':expression,'frameId':frame,'context':'watch'})
                self.assertEqual(evaluate('callback(number)')['nex']['value'],1.5)
                value=evaluate('values');page=client.request('variables',{'variablesReference':value['variablesReference'],'start':0,'count':1})['variables']
                self.assertEqual(page[0]['value'],'5e-324')
                closure=evaluate('callback');children=client.request('variables',{'variablesReference':closure['variablesReference'],'start':1,'count':1})['variables']
                self.assertEqual(children[0]['value'],'2.5e-1')
                client.request('continue',{'threadId':stopped['threadId']});self.assertEqual(client.event('exited')['exitCode'],0)
            finally:client.close()


if __name__=='__main__':unittest.main(verbosity=2)
