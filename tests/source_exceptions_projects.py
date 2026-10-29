#!/usr/bin/env python3
"""Ordinary026 concrete source providers with real static/shared/mixed images."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import shutil
import sqlite3

parser=argparse.ArgumentParser()
parser.add_argument('nex')
parser.add_argument('--output')
parser.add_argument('--pure-only',action='store_true')
parser.add_argument('--debug-only',action='store_true')
args=parser.parse_args()
nex=str(Path(args.nex).resolve())
output_env='NEX_PUBLIC025_DEBUG_OUTPUT' if args.debug_only else 'NEX_PUBLIC025_PROJECT_OUTPUT'
out=Path(args.output or os.environ.get(output_env) or tempfile.mkdtemp(prefix='nex-public025-projects-')).resolve()
out.mkdir(parents=True,exist_ok=True)
report={'ok':False,'compiler_sha256':hashlib.sha256(Path(nex).read_bytes()).hexdigest(),
        'commands':[],'cases':[],'captures':[],'profiles':[]}
case_environment={}
LEAF=r'''module leaf;
pub struct Packet{values:list<str>;}
pub fn pure(value:str)->Packet !{throw}{
 let temporary:list<str>=["retained",value];
 if value=="raise"{throw("LEAF","λ\u0000🙂");}
 return Packet(temporary);
}
pub fn next(value:i64)->i64{return value+1;}
pub fn delayed(value:str)->Packet !{task,throw}{task_yield();return pure(value);}
pub server fn opened()->file !{task,fs}{return unwrap(file_open_read("input"));}
pub server fn fail_file()->unit !{task,fs,throw}{
 let owner:file=opened();assert(file_is_open(owner));throw("FILE","closed on unwind");
}
'''
MIDDLE=r'''module middle;
import "../leaf/main.nex" as leaf;
pub fn pure(value:str)->list<str> !{throw}{return leaf::pure(value).values;}
pub fn forward(value:str)->list<str> !{task,throw}{return leaf::delayed(value).values;}
pub fn next(value:i64)->i64 !{task}{task_yield();return leaf::next(value);}
pub fn reject(code:str)->bool !{task}{task_yield();return code=="OTHER";}
pub fn rethrow()->i64 !{task,throw}{
 try{let ignored:leaf::Packet=leaf::delayed("raise");return 0;}
 catch(code,message) if reject(code){assert(false);throw;}
}
pub server fn read()->str !{task,fs}{
 let owner:file=leaf::opened();let value:bytes=unwrap(file_read(owner,6));
 assert(file_close(owner));return unwrap(decode_utf8(value));
}
pub server fn fail_file()->unit !{task,fs,throw}{leaf::fail_file();}
'''
APP=r'''module app;
import "../middle/main.nex" as middle;
server fn main()->unit !{task,fs,io,throw}{
 try{let ignored:list<str>=middle::pure("raise");assert(false);}
 catch(code,message){assert(code=="LEAF"&&message=="λ\u0000🙂");}
 try{
  let ignored:i64=with_tasks(2,fn(scope:task_scope)->i64 !{task,throw}{
   let future:task<i64>=task_spawn(scope,fn()->i64 !{task,throw}{
    let value:list<str>=middle::forward("raise");return len(value);
   });
   return task_wait(future);
  });
  assert(false);
 }catch(code,message){assert(code=="LEAF"&&message=="λ\u0000🙂");}
 try{let ignored:i64=middle::rethrow();assert(false);}
 catch(code,message) if code=="LEAF"{assert(message=="λ\u0000🙂");}
 let value:list<str>=["owned",middle::forward("ok")[1]];
 assert(value==["owned","ok"]);assert(middle::next(41)==42);
 assert(middle::read()=="abcdef");
 try{middle::fail_file();assert(false);}
 catch(code,message){assert(code=="FILE"&&message=="closed on unwind");}
 print(42);
}
'''
def save():
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')

def cli(project,label,arguments,expected=0):
    result=subprocess.run([nex,*map(str,arguments),'--json'],cwd=project,
                          capture_output=True,text=True,timeout=900,env={**os.environ,**case_environment})
    (out/(label+'.stdout')).write_text(result.stdout)
    (out/(label+'.stderr')).write_text(result.stderr)
    report['commands'].append({'label':label,'arguments':list(map(str,arguments)),
                               'exit':result.returncode});save()
    assert result.returncode==expected,(label,result.stdout[-4000:],result.stderr[-4000:])
    return json.loads(result.stdout)

def debug(project,mode):
    description=cli(project,mode+'-debug',['project','--kind','debug','--component','app','--adapter','nex-dap'])
    session=description['observation'];manifest=json.loads(Path(session['manifest']).read_text())
    assert manifest['schema']=='nex.debug/3' and manifest['language']=='0.26'
    debugger=os.environ.get('NEX_LLDB') or shutil.which('lldb')
    assert debugger,'actual LLDB is required for source-provider debugger tests'
    commands=['settings set target.disable-aslr false',
              'command script import '+json.dumps(manifest['formatter']),
              'nex-load-debug '+json.dumps(session['manifest'])+' --compiler '+json.dumps(nex),
              'nex-task-break function leaf::pure','run','nex-task-stack','nex-task-values',
              'nex-frame value','nex-eval value','breakpoint disable','continue']
    argv=[debugger,'--no-lldbinit','--batch',session['launch']['program']]
    for command in commands:argv+=['-o',command]
    result=subprocess.run(argv,cwd=project,env={**os.environ,**case_environment},
                          capture_output=True,text=True,timeout=180)
    (out/(mode+'-lldb.stdout')).write_text(result.stdout)
    (out/(mode+'-lldb.stderr')).write_text(result.stderr)
    assert result.returncode==0,(mode,result.stdout[-3500:],result.stderr[-1500:])
    rows=[json.loads(line) for line in result.stdout.splitlines() if line.startswith('{')]
    stack=next(row for row in rows if row.get('schema')=='nex.task-debug-stack/1')
    assert [row['name'] for row in stack['frames']][:3]==['leaf::pure','middle::pure','app::main']
    frame=next(row for row in rows if row.get('schema')=='nex.debug-frame/4')
    expected={'static':'app','shared':'leaf','mixed':'middle'}[mode]
    assert frame['source_identity']['component']=='leaf' and frame['source_identity']['owner_image']==expected
    watch=next(row for row in rows if row.get('schema')=='nex.task-expression/2')
    assert watch['ok'] and watch['value']=='raise'
    assert '42\n' in result.stdout and 'exited with status = 0' in result.stdout
    report['cases'].append({'mode':mode,'real_LLDB':True,'pure_helper_frame':True,
                            'component':'leaf','physical_owner_image':expected,'watch':'raise'})
    save()

try:
    for mode in ([] if args.pure_only else ['static','shared','mixed']):
        project=out/mode;project.mkdir()
        files=out/(mode+'-files');files.mkdir();(files/'input').write_text('abcdef')
        case_environment={'NEX_FILES_ROOT':str(files)}
        for name,text in [('leaf',LEAF),('middle',MIDDLE),('app',APP)]:
            folder=project/name;folder.mkdir();(folder/'main.nex').write_text(text.replace(chr(92)*2+'u0000',chr(92)+'u0000'))
        (project/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.26','entry':'app/main.nex'}))
        leaf_shared=mode=='shared';middle_shared=mode!='static'
        architecture={'schema':'nex.project-build/1','default_configuration':'debug',
                      'configurations':{'debug':{'profile':'debug'},'release':{'profile':'release'},'measured':{'profile':'profile'}},
                      'components':{
            'leaf':{'kind':'shared_library' if leaf_shared else 'static_library','root':'leaf',
                    'entry':'leaf/main.nex','entry_function':'delayed','exports':['pure','next','delayed','opened','fail_file']},
            'middle':{'kind':'shared_library' if middle_shared else 'static_library','root':'middle',
                      'entry':'middle/main.nex','entry_function':'forward','exports':['pure','forward','next','rethrow','read','fail_file'],
                      'dependencies':{'leaf':'dynamic' if leaf_shared else 'static'}},
            'app':{'kind':'executable','root':'app','entry':'app/main.nex',
                   'dependencies':{'middle':'dynamic' if middle_shared else 'static'}}}}
        (project/'nex.build.json').write_text(json.dumps(architecture,indent=2))
        if args.debug_only:
            debug(project,mode)
            continue
        for profile in ['debug','release']:
            label=mode+'-'+profile
            plan=cli(project,label+'-plan',['project','--kind','plan','--component','app','--configuration',profile])
            assert plan['ok'] and plan['language']=='0.26' and not plan['graph_store_opened']
            expected='nex.project-static-task-linkage/4' if mode=='static' else 'nex.project-task-linkage/11'
            for row in plan['components']:
                linkage=row['task_linkage'];assert linkage['schema']==expected and linkage['execution_abi']==6
                assert all(i['calling_mode']=='task-code/6' for i in linkage['imports'])
                assert all(v['requirements']&~7967==0 for v in linkage['exports'].values())
            observation=cli(project,label+'-run',['project','--kind','run','--component','app','--configuration',profile])
            actual=observation['observation'];assert actual['exit_code']==0 and actual['stdout']=='42\n',actual
            assert not (project/'.nex/graph.db').exists()
            report['cases'].append({'mode':mode,'profile':profile,'passed':True});save()
        profiled=cli(project,mode+'-profile',['project','--kind','profile','--component','app',
                     '--configuration','measured','--profile-output',out/(mode+'-profile.json')])
        assert profiled['observation']['stdout']=='42\n'
        profile=json.loads((out/(mode+'-profile.json')).read_text())
        assert profile['ok'] and not profile['incomplete'] and profile['invalid_transitions']==0
        assert all(pool['live']==0 and pool['allocations']==pool['frees'] for pool in profile['memory'])
        functions={row['name']:row for row in profile['functions']}
        assert functions['leaf::pure']['calls']==4 and functions['leaf::opened']['calls']==2
        assert functions['middle::reject']['calls']==1
        assert functions['leaf::fail_file']['calls']==1 and functions['middle::forward']['calls']==2
        expected_owner={'static':'app','shared':'leaf','mixed':'middle'}[mode]
        assert functions['leaf::pure']['provider_component']=='leaf'
        assert functions['leaf::pure']['owner_image']==expected_owner
        report['profiles'].append({'mode':mode,'report':str(out/(mode+'-profile.json'))});save()
        task=cli(project,mode+'-task-init',['task','nex.build.json','--kind','init','--component','app','--configuration','debug'])
        task['checks'].append({'id':'run-native','kind':'run','target':'native','program':'app','entry':'app::main',
                               'configuration':'debug','expect':{'stdout':'42\n','exit_code':0}})
        task['requirements'][0]['checks'].append('run-native')
        taskfile=project/'task.json';taskfile.write_text(json.dumps(task,indent=2))
        checked=cli(project,mode+'-task-check',['task',taskfile,'--kind','check'])
        run=cli(project,mode+'-task-run',['task',taskfile,'--kind','run','--task-hash',checked['task_hash']])
        assert run['ok'] and all(row['status']=='passed' for row in run['checks'])
        receipt=Path(run['output']);saved=out/(mode+'-receipt');shutil.copytree(receipt.parent,saved)
        original=project.with_name(project.name+'-hidden');project.rename(original)
        try:
            replay=cli(original,mode+'-task-replay',['task',saved/receipt.name,'--kind','replay','--directory',out/(mode+'-replay')])
            assert replay['ok'] and all(row['status']=='passed' for row in replay['checks'])
        finally:
            original.rename(project)
        report['captures'].append({'mode':mode,'source_absent_replay':True,'receipt':str(saved/receipt.name)})
        assert (files/'input').read_text()=='abcdef'
        # Project plan/build/run/profile are graph-free. Acceptance-task run
        # deliberately persists its own history after those actions complete.
        with sqlite3.connect(str(project/'.nex/graph.db')) as database:
            database.execute('pragma query_only=on')
            assert database.execute('select status from task_runs').fetchall()==[('passed',)]
        save()
    for mode in ([] if args.debug_only else ['static','shared']):
        project=out/('pure-'+mode);project.mkdir()
        leaf=project/'leaf';leaf.mkdir();app=project/'app';app.mkdir()
        (leaf/'main.nex').write_text('module leaf;pub fn answer(fail:bool)->i64 !{throw}{if fail{throw("PURE","leaf");}return 42;}')
        (app/'main.nex').write_text('module app;import "../leaf/main.nex" as leaf;fn main()->unit !{task,io}{task_yield();try{let ignored:i64=leaf::answer(true);assert(false);}catch(c,m){assert(c=="PURE"&&m=="leaf");}try{print(leaf::answer(false));}catch(c,m){assert(false);}}')
        (project/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.26','entry':'app/main.nex'}))
        (project/'nex.build.json').write_text(json.dumps({'schema':'nex.project-build/1','default_configuration':'debug','configurations':{'debug':{'profile':'debug'}},'components':{
            'leaf':{'kind':'static_library' if mode=='static' else 'shared_library','root':'leaf','entry':'leaf/main.nex','entry_function':'answer'},
            'app':{'kind':'executable','root':'app','entry':'app/main.nex','dependencies':{'leaf':'static' if mode=='static' else 'dynamic'}}}}))
        observed=cli(project,'pure-'+mode+'-run',['project','--kind','run','--component','app'])
        assert observed['observation']['stdout']=='42\n' and observed['observation']['exit_code']==0
        report['cases'].append({'mode':mode,'pure_provider_without_task_effect':True,'passed':True});save()
    assert hashlib.sha256(Path(nex).read_bytes()).hexdigest()==report['compiler_sha256']
    report['ok']=True
finally:
    save()
print(json.dumps({'ok':report['ok'],'cases':len(report['cases']),'report':str(out/'report.json')}))
