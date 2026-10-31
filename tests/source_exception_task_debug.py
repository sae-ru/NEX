"""Live generated native checkpoint/pause/watch/resume; private source has no archive identity."""
import argparse, hashlib, json, os, subprocess, sys, tempfile
from pathlib import Path
DEBUG_CASES=[
('debug-catch-shadow',r'''
fn main()->i64 !{task}{
 var code:i64=17;
 var outer:str="old";
 try{
  outer="kept";
  task_yield();
  throw("USER","λ\u0000🙂");
 }catch(code,message){
  task_yield(); // STOP:catch_before
  let n:i64=len(message);
  assert(n==3); // STOP:catch_after
 }
 assert(code==17); // STOP:outside
 return 42;
}
''',{'catch_before':[{'values':{'code':'USER','message':'λ\0🙂','outer':'kept'},'absent':['n'],'types':{'code':'str'}}],
     'catch_after':[{'values':{'code':'USER','message':'λ\0🙂','outer':'kept','n':3}}],
     'outside':[{'values':{'code':17,'outer':'kept'},'absent':['message','n'],'types':{'code':'i64'}}]},1000000),
('debug-call-rethrow',r'''
fn leaf(v:i64)->i64 !{task,throw}{
 task_yield(); // STOP:leaf
 throw("LEAF",str(v));
}
fn main()->i64 !{task}{
 var outer:i64=7;
 try{
  try{let result:i64=leaf(outer);return result;}
  catch(code,message){
   task_yield(); // STOP:inner
   throw;
  }
 }catch(code,message){
  assert(code=="LEAF"); // STOP:outer
  assert(message=="7");return 42;
 }
}
''',{'leaf':[{'values':{'v':7},'min_frames':2,'function':'leaf','caller_values':{'outer':7}}],
     'inner':[{'values':{'code':'LEAF','message':'7','outer':7}}],
     'outer':[{'values':{'code':'LEAF','message':'7','outer':7}}]},1000000),
('debug-future-handler',r'''
fn failed()->i64 !{task,throw}{task_yield();throw("FUTURE","payload");}
fn main()->i64 !{task,throw}{
 return with_tasks(2,fn(scope:task_scope)->i64 !{task}{
  let t:task<i64>=task_spawn(scope,failed);
  try{return task_wait(t);}
  catch(code,message){
   task_yield(); // STOP:future
   assert(code=="FUTURE"&&message=="payload");return 42;
  }
 });
}
''',{'future':[{'values':{'code':'FUTURE','message':'payload','t':{'opaque':True}},'types':{'t':'task<i64>'},'min_frames':2}]},1000000),
('debug-loop-handler',r'''
fn main()->i64 !{task}{
 var i:i64=0;
 while i<3{
  try{task_yield();throw("LOOP",str(i));}
  catch(code,message){
   assert(code=="LOOP"); // STOP:loop
  }
  i=i+1;
 }
 return 42;
}
''',{'loop':[{'values':{'i':0,'code':'LOOP','message':'0'}},{'values':{'i':1,'code':'LOOP','message':'1'}},{'values':{'i':2,'code':'LOOP','message':'2'}}]},1000000),
('debug-runtime-trap',r'''
fn main()->i64 !{task}{
 try{
  let protected:str="owned";
  task_yield(); // STOP:trap_before
  assert(false);
 }catch(code,message){return 0;}
 return 42;
}
''',{'trap_before':[{'values':{'protected':'owned'},'absent':['code','message']}]},1000000),
('debug-control-limit',r'''
fn main()->i64 !{task}{
 try{while true{
  task_yield(); // STOP:limit_before
 }}catch(code,message){return 0;}
 return 42;
}
''',{'limit_before':[{'values':{},'absent':['code','message']}]},2000),
('debug-uncaught-rethrow',r'''
fn leaf()->i64 !{task,throw}{
 task_yield();throw("ORIGIN","λ\u0000🙂");
}
fn main()->i64 !{task,throw}{
 try{return leaf();}
 catch(code,message){
  task_yield(); // STOP:rethrow
  throw;
 }
}
''',{'rethrow':[{'values':{'code':'ORIGIN','message':'λ\0🙂'}}]},1000000),
]
def main():
    p=argparse.ArgumentParser();p.add_argument('emitter');p.add_argument('reference');p.add_argument('compiler');p.add_argument('--output');p.add_argument('--existing-execution');a=p.parse_args()
    source=Path(__file__).resolve().parents[1];out=Path(a.output or os.environ.get('NEX_EXCEPTION_TASK_DEBUG_OUTPUT') or tempfile.mkdtemp(prefix='nex-source-debug-')).resolve();out.mkdir(parents=True,exist_ok=True)
    execution=Path(a.existing_execution).resolve() if a.existing_execution else out/'execution'
    cmd=[sys.executable,'-B',str(source/'tests/source_exception_task_native.py'),a.emitter,a.reference,a.compiler,'--debug','--output',str(execution)]
    for name,_,_,_ in DEBUG_CASES:cmd += ['--case',name]
    if not a.existing_execution:
        r=subprocess.run(cmd,text=True,capture_output=True,timeout=1800);(out/'driver.stdout').write_text(r.stdout, newline="\n");(out/'driver.stderr').write_text(r.stderr, newline="\n");assert r.returncode==0,(r.returncode,r.stdout[-1000:],r.stderr[-4000:])
    native=json.loads((execution/'report.json').read_text());assert native['ok'] and native['comparisons']==14 and native['source_programs']==7
    definitions={n:e for n,_,e,_ in DEBUG_CASES};report={'ok':False,'cases':[],'execution':str(execution),'execution_report_sha256':hashlib.sha256((execution/'report.json').read_bytes()).hexdigest(),'verified_existing_execution':bool(a.existing_execution),'actual_native_pause_watch_resume':True,'nonowning':True,'LLDB_DAP_acceptance_claimed':False,'public_debug_CLI_support':False,'archived':False,'security_checks_deferred_by_user':True}
    def save():(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n', newline="\n")
    save()
    for item in native['cases']:
        d=execution/item['name'];e=d/('O'+item['optimization']);f=e/'observations.jsonl';assert hashlib.sha256(f.read_bytes()).hexdigest()==item['debug_observations_sha256']
        observations=[json.loads(line) for line in f.read_text().splitlines()];assert all('debug_error' not in v for v in observations)
        plans=definitions[item['name']];total=sum(map(len,plans.values()));stats=item['debug_statistics'];assert stats['pauses']==stats['resumes']==total and stats['live_frames']==0 and stats['nonowning'] and len(observations)==total
        text=(d/'main.nex').read_text();metadata=json.loads((e/'metadata.json').read_text())['operations']
        for tag,visits in plans.items():
            line=next(i for i,t in enumerate(text.splitlines(),1) if '// STOP:'+tag in t);actual=[v for v in observations if v['line']==line];assert len(actual)==len(visits),(item['name'],tag,actual)
            for value,want in zip(actual,visits):
                assert value['frames']>=want.get('min_frames',1) and value['task_id'] and value['frame_id']
                if 'function' in want:assert value['function']==want['function']
                assert len(value['stack'])==value['frames'] and value['stack'][0]['frame_id']==value['frame_id']
                if 'caller_values' in want:
                    caller=value['stack'][1];assert caller['function']=='main'
                    for key,expected in want['caller_values'].items():assert caller['values'][key]==expected
                for key,expected in want['values'].items():assert value['values'].get(key)==expected,(item['name'],tag,key,value,expected)
                for key in want.get('absent',[]):assert key not in value['values'],(item['name'],tag,'out of scope',key,value)
                for key,expected in want.get('types',{}).items():assert value['types'][key]==expected
                assert any(op['site']==value['site'] and op['function_hash']==value['function_hash'] and op['function_source_hash']==value['source_hash'] for op in metadata),(item['name'],'debug site provenance',value)
        report['cases'].append({'name':item['name'],'optimization':item['optimization'],'source_sha256':item['source_sha256'],'observations_sha256':item['debug_observations_sha256'],'pauses':total,'retained_frames':0,'passed':True});save()
    report.update(ok=True,comparisons=len(report['cases']),source_programs=7,pauses=sum(v['pauses'] for v in report['cases']));save();print(json.dumps({'ok':True,'comparisons':14,'pauses':report['pauses'],'report':str(out/'report.json')}))
if __name__=='__main__':main()
