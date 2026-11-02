from host_fixture import run_native, probe_dll_inputs
"""Actual all-stop LLDB/DAP over unarchived compiled private source exceptions."""
import os
import argparse, ast, hashlib, json, os, platform, re, shutil, subprocess, sys, tempfile
from pathlib import Path

HOST = r'''
#include "nex_task_debug.h"
#include "nex_value.h"
#include <atomic>
#include <chrono>
#include <cstdio>
#include <map>
#include <mutex>
#include <thread>
extern "C" int nex_private_debug_entry(int,const char *const*);
extern "C" { std::atomic<uint64_t> nex_private_debug_pulse{0}; }
static std::atomic<bool> finished{false};
static std::mutex allocationsMutex;
static std::map<const void*,int> allocations;
extern "C" void nex_profile_unwind(){}
extern "C" void nex_profile_allocation(const void *p,size_t,int pool){std::lock_guard lock(allocationsMutex);if(!allocations.emplace(p,pool).second)std::abort();}
extern "C" void nex_profile_free(const void *p){std::lock_guard lock(allocationsMutex);if(allocations.erase(p)!=1)std::abort();}
int main(int argc,const char *const *argv){
  auto baseline=nexrt::liveObjects.load();
  std::thread pulse([]{while(!finished.load()){++nex_private_debug_pulse;std::this_thread::sleep_for(std::chrono::milliseconds(1));}});
  auto result=nex_private_debug_entry(argc,argv);finished=true;pulse.join();
  auto &catalog=nex_task_debug_catalog_v1;
  bool clean=nexrt::liveObjects.load()==baseline&&!catalog.live_frames&&!catalog.dropped_tasks&&!catalog.dropped_frames&&!catalog.invalid_transitions;
  auto tasks=reinterpret_cast<const nexrt::TaskDebugTaskRecord*>(catalog.tasks_address);
  for(size_t i=0;i<catalog.task_count;++i)clean&=(tasks[i].flags&nexrt::taskDebugTerminal)&&!tasks[i].frame_count;
  {std::lock_guard lock(allocationsMutex);clean&=allocations.empty();}
  std::fprintf(stderr,"NEX_PRIVATE_LLDB_CLEANUP {\"ok\":%s,\"live_frames\":%llu,\"managed_live\":%llu}\n",clean?"true":"false",(unsigned long long)catalog.live_frames,(unsigned long long)(nexrt::liveObjects.load()-baseline));
  return clean?result:71;
}
'''

LLDB_DRIVER = r'''
import base64,json,time,traceback,os
from pathlib import Path
import lldb
def session(debugger,command,result,internal_dict):
    config=json.loads(Path(command.strip()).read_text(encoding='utf-8'));report={'ok':False,'observations':[],'steps':[]}
    target=debugger.GetSelectedTarget();debugger.SetAsync(False)
    def run(text):
        response=lldb.SBCommandReturnObject();debugger.GetCommandInterpreter().HandleCommand(text,response)
        output=response.GetOutput() or '';error=response.GetError() or ''
        report.setdefault('commands',[]).append({'command':text,'output':output,'error':error,'ok':response.Succeeded()})
        assert response.Succeeded(),(text,output,error)
        return output
    def request(name,**args):
        payload=base64.b64encode(json.dumps({'command':name,'arguments':args}).encode()).decode()
        return json.loads(run('nex-task-request-encoded '+payload))
    def pulse(process):
        variable=target.FindFirstGlobalVariable('nex_private_debug_pulse');assert variable.IsValid()
        error=lldb.SBError();value=process.ReadUnsignedFromMemory(variable.GetLoadAddress(),8,error);assert error.Success();return value
    def preview(value):
        if isinstance(value,str):return '"'+'\\0'.join(json.dumps(p,ensure_ascii=False)[1:-1] for p in value.split('\0'))+'"'
        if value is True:return 'true'
        if value is False:return 'false'
        return str(value)
    def watch(identity,expression,expected=None,frame_index=0,error=None):
        payload=base64.b64encode(json.dumps({'expression':expression,'task_id':identity,'frame_index':frame_index}).encode()).decode()
        text='nex-eval-encoded '+payload
        if error:
            response=lldb.SBCommandReturnObject();debugger.GetCommandInterpreter().HandleCommand(text,response)
            assert not response.Succeeded() and error in (response.GetError() or ''),(text,response.GetOutput(),response.GetError())
            report.setdefault('watch_rejections',[]).append({'expression':expression,'error':response.GetError()});return
        value=json.loads(run(text));assert value['ok'] and value['schema']=='nex.private-task-expression/1' and value['archived'] is False and 'revision' not in value
        assert value['value']==expected,(expression,value,expected)
        report.setdefault('watches',[]).append({'expression':expression,'frame_index':frame_index,'result':value});return value
    def watches(identity,want,values):
        def wire(value):return str(value) if type(value) is int else value
        candidates=[(name,value) for name,value in want['values'].items() if type(value) in (int,bool,str)]
        for name,value in candidates:watch(identity,name,wire(value))
        lazy=watch(identity,'false && 1/0 == 0',False);assert not lazy['read_bindings']
        if isinstance(want['values'].get('message'),str):watch(identity,'len(message)',str(len(want['values']['message'])))
        if 'caller_values' in want:watch(identity,'outer+1',str(want['caller_values']['outer']+1),1)
        for expression,expected in want.get('watches',[]):watch(identity,expression,expected)
        for name,value in want['values'].items():
            if isinstance(value,dict) and value.get('opaque'):watch(identity,name,error='E_DEBUG_VALUE')
        if want.get('absent'):watch(identity,want['absent'][0],error='E_NAME')
        watch(identity,'1+true',error='E_TYPE');watch(identity,'print("watch")',error='E_EFFECT')
        if candidates:
            name,value=candidates[0];frame=json.loads(run('nex-frame '+name))
            assert frame['schema']=='nex.private-task-debug-frame/1' and frame['archived'] is False and 'revision' not in frame
            file=Path(config['directory'])/('frame-'+str(len(report.get('captures',[])))+'.json');file.write_text(json.dumps(frame,ensure_ascii=False)+'\n',encoding='utf-8')
            report.setdefault('captures',[]).append({'file':str(file),'expression':name,'value':wire(value)})
        assert values==request('values',task_id=identity),'watch changed inferior state'
    def check(values,want):
        rows={v['name']:v for v in values['variables']}
        for name,value in want.get('values',{}).items():
            assert name in rows,(name,rows)
            if isinstance(value,dict) and value.get('opaque'):assert 'opaque' in rows[name].get('unavailable','')
            else:assert rows[name].get('preview')==preview(value),(name,rows[name],value)
        for name in want.get('absent',[]):assert name not in rows,(name,rows)
        for name,kind in want.get('types',{}).items():assert rows[name]['type']==kind
    try:
        plans=config['plans'];counts={line:0 for line in plans}
        def arm():
            lines=[{'line':int(line)} for line,wants in plans.items() if counts[line]<len(wants)]
            response=request('breakpoints',source=config['source'],breakpoints=lines)
            assert all(v['verified'] for v in response['breakpoints']),response
        hidden=[]
        if config.get('watch'):
            for name in config['source_files']:
                original=Path(name);temporary=original.with_suffix('.hidden');assert not temporary.exists();original.rename(temporary);hidden.append((original,temporary))
            report['source_absent_during_watch']=all(not original.exists() for original,_ in hidden)
            report['hidden_sources']=config['source_files']
        if os.name=='nt':run('settings set target.error-path '+json.dumps(str(Path(config['directory'])/'inferior.stderr'),ensure_ascii=False))
        arm();run('run --nex-task-workers 2 --nex-task-steps '+str(config['limit'])+(' --nex-task-timeout-ms 800' if config.get('deadline') else ''))
        process=target.GetProcess()
        while process.GetState()==lldb.eStateStopped:
            tasks=request('tasks');assert not tasks.get('marker_error'),tasks
            identity=tasks['selected'];stack=request('stack',task_id=identity);frame=stack['frames'][0]
            if frame['phase']!='statement':
                # One source line can also resolve to call-entry/resume points.
                # The shared fixture expectations describe statement checkpoints.
                values=request('values',task_id=identity);before=pulse(process);time.sleep(.025)
                assert before==pulse(process) and values==request('values',task_id=identity)
                report.setdefault('auxiliary_stops',[]).append({'stack':stack,'values':values,'all_stop':True})
                request('continue');continue
            line=str(frame['line']);assert line in plans and counts[line]<len(plans[line]),(frame,plans,counts)
            want=plans[line][counts[line]];counts[line]+=1
            values=request('values',task_id=identity);check(values,want)
            assert len(stack['frames'])>=want.get('min_frames',1)
            if 'function' in want:assert frame['name'].split('::')[-1]==want['function']
            if 'caller_values' in want:check(request('values',task_id=identity,frame_index=1),{'values':want['caller_values']})
            before=pulse(process);time.sleep(.025);after=pulse(process)
            assert before==after and process.GetState()==lldb.eStateStopped,'other native thread advanced during all-stop'
            assert values==request('values',task_id=identity),'values changed while all native threads were stopped'
            report['observations'].append({'stack':stack,'values':values,'all_stop':True,'pulse_before':before,'pulse_after':after})
            if config.get('watch'):watches(identity,want,values)
            if config.get('deadline'):time.sleep(1.1)
            arm()
            if config.get('step'):
                # A source exception unwinds the leaf and logical step-out must
                # land in the retained caller, not in retired native storage.
                original=frame['id'];request('out',task_id=identity)
                assert process.GetState()==lldb.eStateStopped
                caller=request('stack',task_id=identity);assert caller['frames'][0]['id']!=original
                assert caller['frames'][0]['name'].split('::')[-1]=='main',caller
                report['steps'].append({'kind':'out','stack':caller})
                for i in range(16):
                    visible=request('values',task_id=identity)
                    names={v['name']:v for v in visible['variables']}
                    if 'code' in names and 'preview' in names['code']:
                        assert names['code']['preview']=='"LEAF"',names
                        report['steps'].append({'kind':'catch','values':visible});break
                    request('next',task_id=identity)
                    assert process.GetState()==lldb.eStateStopped
                else:raise AssertionError('logical next never reached initialized catch bindings')
            request('continue')
        assert process.GetState()==lldb.eStateExited,(process.GetState(),process.GetExitDescription())
        assert all(counts[line]==len(wants) for line,wants in plans.items()),counts
        for read in (process.GetSTDOUT,process.GetSTDERR):
            while True:
                chunk=read(1048576)
                if not chunk:break
                result.PutCString(chunk)
        if os.name=='nt':result.PutCString((Path(config['directory'])/'inferior.stderr').read_text(encoding='utf-8'))
        report.update(ok=True,exit=process.GetExitStatus(),counts=counts,all_stop=True)
    except Exception:
        report['failure']=traceback.format_exc();result.SetError(report['failure'])
    finally:
        if config.get('watch') and 'hidden' in locals():
            for original,temporary in hidden:
                if temporary.exists():temporary.rename(original)
        Path(config['report']).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if report['ok']:result.PutCString(json.dumps({'ok':True,'report':config['report']}))
def __lldb_init_module(debugger,internal_dict):
    debugger.HandleCommand('command script add -f '+__name__+'.session nex-private-test-session')
'''

WATCH_CASES=[
 ('watch-c-locale',r'''fn main()->i64 !{task,throw}{
 let text:str="Я🌍\u0000";
 try{task_yield();throw("LOCALE",text);}
 catch(code,message){
  assert(len(message)==3); // STOP:locale
  return 42;
 }
}''',{'locale':[{'values':{'text':'Я🌍\0','code':'LOCALE','message':'Я🌍\0'}}]},1000000),
('watch-aggregates',r'''
struct Box{label:str;nums:list<i64>;}
fn recover()->i64{try{throw("PURE","abc");}catch(code,message){return len(message);}}
fn main()->i64 !{task}{
 let native:i64=recover();
 let box:Box=Box("λ\u0000🙂",[1,2,3]);
 let items:list<i64>=[40,2];
 let number:result<i64>=ok(42);
 let binary:bytes=unwrap(bytes([65,0,255]));
 try{throw("AGG","λ\u0000🙂");}catch(code,message){
  task_yield(); // STOP:aggregates
  assert(native==3);return 42;
 }
}
''',{'aggregates':[{'values':{'native':3,'code':'AGG','message':'λ\0🙂'},'watches':[
 ('items[0]+items[1]','42'),('box.label','λ\0🙂'),('box.nums[1]','2'),('unwrap(number)','42'),('binary[2]','255'),('recover()+native','6'),
 ('(fn()->i64{try{throw("LOCAL","λ");}catch(code,message){return len(message);}})()','1'),('false && items[999]==0',False)]}]},1000000),
('watch-module-context',{
 'main.nex':r'''module module_watch;
import "./model.nex" as model;
fn main()->i64 !{task}{
 let native:i64=model::recover(41);
 try{return model::fail();}catch(code,message){
  task_yield(); // STOP:modules
  assert(code=="CROSS");return native;
 }
}
''',
 'model.nex':r'''module model;
pub fn recover(v:i64)->i64{try{throw("PURE",str(v));}catch(code,message){return v+1;}}
pub fn fail()->i64 !{task,throw}{task_yield();throw("CROSS","λ\u0000🙂");}
'''}, {'modules':[{'values':{'native':42,'code':'CROSS','message':'λ\0🙂'},'watches':[('model::recover(native)','43')]}]},1000000),
]

def main():
    p=argparse.ArgumentParser();p.add_argument('emitter');p.add_argument('reference');p.add_argument('compiler');p.add_argument('--output');p.add_argument('--case',action='append');p.add_argument('--watch-compiler');a=p.parse_args()
    source=Path(__file__).resolve().parents[1];runtime=source/'runtime'
    out=Path(a.output or os.environ.get('NEX_EXCEPTION_TASK_WATCH_OUTPUT' if a.watch_compiler else 'NEX_EXCEPTION_TASK_LLDB_OUTPUT') or tempfile.mkdtemp(prefix='nex-private-lldb-')).resolve();out.mkdir(parents=True,exist_ok=True)
    emitter=str(Path(a.emitter).resolve());reference=str(Path(a.reference).resolve());compiler=str(Path(a.compiler).absolute())
    report={'ok':False,'cases':[],'dap_cases':[],'typescript_cases':[],'commands':[],'archived':False,'public_debug_CLI_support':False,'checked_expression_support':bool(a.watch_compiler),'security_checks_deferred_by_user':True,'ordinary_functional_only':True}
    def save():(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n', newline="\n")
    def run(label,command,allowed=(0,),cwd=out,timeout=240,env=None):
        r=run_native(command,cwd=cwd,text=True,capture_output=True,timeout=timeout,
                     env=None if env is None else {**os.environ,**env})
        (out/(label+'.stdout')).write_text(r.stdout, newline="\n");(out/(label+'.stderr')).write_text(r.stderr, newline="\n")
        report['commands'].append({'label':label,'argv':list(map(str,command)),'exit':r.returncode});save()
        assert r.returncode in allowed,(label,r.returncode,r.stdout[-1500:],r.stderr[-4000:]);return r
    def dap_case(binary,manifest,directory,plans,optimization):
        # Reuse the real pipe/event harness; its ToolchainCase is not instantiated.
        previous=list(sys.argv)
        try:
            sys.argv=[sys.argv[0],emitter]
            from debugging import DAP
        finally:sys.argv=previous
        backend=shutil.which('lldb-dap')
        if not backend and platform.system()=='Darwin':backend=subprocess.check_output(['xcrun','--find','lldb-dap'],text=True).strip()
        assert backend,'actual lldb-dap required'
        trace=[]
        class Recorded(DAP):
            def send(self,command,arguments=None):
                trace.append({'request':command,'arguments':arguments});return super().send(command,arguments)
            def wait(self,predicate,timeout=30):
                value=super().wait(predicate,timeout);trace.append({'received':value});return value
        adapter=Recorded([sys.executable,str(source/'debug/nex_dap.py'),'--backend',backend],directory)
        try:
            adapter.request('initialize',{'clientID':'private-source-test','adapterID':'nex','linesStartAt1':True,'columnsStartAt1':True,'pathFormat':'path'})
            launch=adapter.send('launch',{'program':str(binary),'cwd':str(directory),'stopOnEntry':False,'nexTaskDebug':True,
                'args':['--nex-task-workers','2'],'initCommands':['settings set target.disable-aslr false',
                    'command script import '+json.dumps(str(source/'debug/lldb_nex.py')),
                    'nex-load-private-task-debug '+json.dumps(str(manifest))+(' --compiler '+json.dumps(str(Path(a.watch_compiler).resolve())) if a.watch_compiler else '')]})
            adapter.event('initialized')
            points=list(plans);selected_lines=points[:2]
            response=adapter.request('setBreakpoints',{'source':{'path':str(directory.parent/'main.nex')},'breakpoints':[{'line':int(v)} for v in selected_lines]})
            assert all(v['verified'] for v in response['breakpoints']),response
            adapter.request('configurationDone');adapter.response(launch)
            stop=adapter.event('stopped');assert stop['allThreadsStopped']
            tasks=adapter.request('threads');identity=tasks['nex']['selected'];assert identity
            stack=adapter.request('stackTrace',{'threadId':identity});assert [v['name'].split('::')[-1] for v in stack['stackFrames']]==['leaf','main']
            frame=stack['stackFrames'][0]['id'];scope=adapter.request('scopes',{'frameId':frame})['scopes'][0]['variablesReference']
            values=adapter.request('variables',{'variablesReference':scope})['variables'];assert next(v['value'] for v in values if v['name']=='v')=='7'
            if a.watch_compiler:
                watch=adapter.request('evaluate',{'expression':'v+1','frameId':frame,'context':'watch'});assert watch['nex']['value']=='8' and watch['nex']['archived'] is False
            parent=stack['stackFrames'][1]['id'];parent_scope=adapter.request('scopes',{'frameId':parent})['scopes'][0]['variablesReference']
            parent_values=adapter.request('variables',{'variablesReference':parent_scope})['variables'];assert next(v['value'] for v in parent_values if v['name']=='outer')=='7'
            adapter.request('setBreakpoints',{'source':{'path':str(directory.parent/'main.nex')},'breakpoints':[{'line':int(selected_lines[1])}]})
            adapter.request('continue',{'threadId':identity});stop=adapter.event('stopped');assert stop['allThreadsStopped']
            old=adapter.send('variables',{'variablesReference':scope});rejected=adapter.wait(lambda v:v.get('type')=='response' and v.get('request_seq')==old);assert not rejected['success']
            stack=adapter.request('stackTrace',{'threadId':identity});assert stack['stackFrames'][0]['name'].split('::')[-1]=='main'
            frame=stack['stackFrames'][0]['id'];scope=adapter.request('scopes',{'frameId':frame})['scopes'][0]['variablesReference']
            values=adapter.request('variables',{'variablesReference':scope})['variables'];values={v['name']:v['value'] for v in values};assert values['code']=='"LEAF"' and values['message']=='"7"' and values['outer']=='7',values
            if a.watch_compiler:
                watch=adapter.request('evaluate',{'expression':'code+":"+message','frameId':frame,'context':'watch'});assert watch['nex']['value']=='LEAF:7' and 'revision' not in watch['nex']
            adapter.request('setBreakpoints',{'source':{'path':str(directory.parent/'main.nex')},'breakpoints':[]})
            adapter.request('next',{'threadId':identity,'singleThread':True});stop=adapter.event('stopped');assert stop['allThreadsStopped']
            fresh=adapter.request('stackTrace',{'threadId':identity});assert fresh['stackFrames'][0]['id']!=frame
            adapter.request('continue',{'threadId':identity});exited=adapter.event('exited');assert exited['exitCode']==42,exited
        finally:
            try:adapter.close()
            finally:(directory/'dap-protocol.json').write_text(json.dumps({'trace':trace,'pending':adapter.pending},ensure_ascii=False,indent=2)+'\n', newline="\n")
        messages={item['seq']:item for item in [*[row['received'] for row in trace if 'received' in row],*adapter.pending] if 'seq' in item}
        output=''.join(item.get('body',{}).get('output','') for _,item in sorted(messages.items()) if item.get('event')=='output')
        cleanup=json.loads(next(line.split(' ',1)[1] for line in output.splitlines() if line.startswith('NEX_PRIVATE_LLDB_CLEANUP ')))
        assert cleanup=={'ok':True,'live_frames':0,'managed_live':0},output
        report['dap_cases'].append({'name':'debug-call-rethrow','optimization':optimization,'all_threads_stopped':True,'caller_and_catch_values':True,'stale_reference_rejected':True,'next_after_unwind':True,'checked_watches':bool(a.watch_compiler),'protocol_sha256':hashlib.sha256((directory/'dap-protocol.json').read_bytes()).hexdigest(),'passed':True});save()
    save();debugger=shutil.which('lldb');assert debugger,'actual LLDB required'
    run('target',[compiler,'-x','c','-S','-emit-llvm',os.devnull,'-o',out/'target.ll'])
    target=(out/'target.ll').read_text();triple=re.search(r'target triple = "([^"]+)"',target)[1];layout=re.search(r'target datalayout = "([^"]+)"',target)[1]
    flags=['-std=c++20','-O1','-g','-DNEX_PROFILE_ENABLED','-DNEX_STRUCTURED_WORKERS','-DNEX_ASYNC_TASKS','-DNEX_TASK_DEBUG_ENABLED','-I'+str(runtime)]
    objects=[]
    for name in ['runtime.cpp','nex_files.cpp','nex_task_frame.cpp','nex_task_external.cpp','nex_resource_region.cpp','nex_external_resource.cpp','nex_resource_executor.cpp','nex_task_application.cpp','nex_task_debug.cpp']:
        obj=out/(name+'.o');run('compile-'+name,[compiler,*flags,'-c',runtime/name,'-o',obj]);objects.append(obj)
    host=out/'host.cpp';host.write_text(HOST, newline="\n");run('compile-host',[compiler,*flags,'-c',host,'-o',out/'host.o']);objects.append(out/'host.o')
    driver=out/'lldb_session.py';driver.write_text(LLDB_DRIVER, newline="\n")
    tree=ast.parse((source/'tests/source_exception_task_debug.py').read_text());assignment=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='DEBUG_CASES' for t in n.targets))
    fixtures=ast.literal_eval(assignment.value)
    step=next(v for v in fixtures if v[0]=='debug-call-rethrow')
    fixtures += [('lldb-exception-step',step[1],{'leaf':step[2]['leaf']},1000000),('lldb-stopped-deadline','''fn main()->i64 !{task}{
 try{
  let owned:str="deadline";
  task_yield(); // STOP:deadline
  return 42;
 }catch(code,message){return 0;}
}''',{'deadline':[{'values':{'owned':'deadline'},'absent':['code','message']}]},1000000)]
    if a.watch_compiler:fixtures+=WATCH_CASES
    if a.case:fixtures=[v for v in fixtures if v[0] in a.case]
    for name,text,expectations,limit in fixtures:
        directory=out/name;directory.mkdir();(directory/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.24','entry':'main.nex'}), newline="\n");file=directory/'main.nex'
        context_input=None
        if isinstance(text,dict):
            for unit,content in text.items():(directory/unit).write_text(content, newline="\n")
            context_input=directory/'input-context.json';context_input.write_text(json.dumps({'schema':'nex.private-task-source/2','file':str(file),'source':text['main.nex'],'entry_unit':'main.nex','units':[{'unit':key,'file':str(directory/key),'source':value} for key,value in sorted(text.items())]},ensure_ascii=False)+'\n', newline="\n")
        else:file.write_text('module private_lldb;\n'+text+'\n', newline="\n")
        expected=json.loads(run(name+'-reference',[reference,'reference-context' if context_input else 'reference',context_input or file,str(limit)]).stdout);(directory/'reference.json').write_text(json.dumps(expected,ensure_ascii=False,indent=2)+'\n', newline="\n")
        if name.startswith('watch-'):
            ts=directory/'typescript';ts.mkdir();run(name+'-typescript-emit',[reference,'typescript-context' if context_input else 'typescript',context_input or file,ts])
            tree=ast.parse((source/'tests/source_exception_tasks_typescript.py').read_text());assignment=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='runner' for t in n.targets));runner=ast.literal_eval(assignment.value)
            script=ts/'run.mjs';script.write_text(runner.replace('STEPS',str(limit)), newline="\n");node=os.environ.get('NEX_NODE','node')
            actual=json.loads(run(name+'-typescript-execute',[node,'--experimental-strip-types','--disable-warning=ExperimentalWarning',script]).stdout)
            assert actual['kind']=='return' and actual['value']==str(expected['value']) and actual['output']==expected['output'],actual
            tsc=Path(os.environ['NEX_TSC']);pin=json.loads((source/'web/package.json').read_text())['devDependencies']['typescript'];assert json.loads((tsc.parent.parent/'package.json').read_text())['version']==pin
            run(name+'-typescript-check',[node,tsc,'--noEmit','--strict','--target','ES2022','--module','ESNext','--moduleResolution','bundler','--allowImportingTsExtensions','--lib','ES2022,DOM',ts/'program.ts'])
            report['typescript_cases'].append({'name':name,'actual':actual,'strict_typecheck':True,'typescript_version':pin,'module_context':bool(context_input),'passed':True});save()
        plans={str(next(i for i,line in enumerate(file.read_text().splitlines(),1) if '// STOP:'+tag in line)):visits for tag,visits in expectations.items()}
        for optimization in ['0','2']:
            label=name+'-O'+optimization;e=directory/('O'+optimization);e.mkdir()
            run(label+'-emit',[emitter,'emit-context' if context_input else 'emit',context_input or file,e,triple,layout,str(optimization=='2').lower(),'debug-lldb'])
            ir=(e/'program.ll').read_text();assert ir.count('@main(')==1;ir=ir.replace('@main(','@nex_private_debug_entry(');(e/'linked.ll').write_text(ir, newline="\n")
            binary=e/('program.exe' if os.name=='nt' else 'program');run(label+'-link',[compiler,'-O'+optimization,'-g',e/'linked.ll',*objects,'-pthread',*(['-Wl,--build-id'] if platform.system()!='Darwin' else []),'-o',binary])
            if platform.system()=='Darwin':run(label+'-symbols',[Path(compiler).parent/'dsymutil',binary])
            context=json.loads((e/'debug-context.json').read_text());assert context['archived'] is False and 'revision' not in context
            identity=run(label+'-identity',[emitter,'identity',binary]).stdout.strip().replace('-','').lower()
            context.update(program=str(binary),formatter=str(source/'debug/lldb_nex.py'),dap_adapter=str(source/'debug/nex_dap.py'))
            context['task_debug'].update(image_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),image_uuid=identity)
            manifest=e/'debug.json';manifest.write_text(json.dumps(context,ensure_ascii=False,indent=2)+'\n', newline="\n")
            options=e/'session.json';options.write_text(json.dumps({'source':str(file),'plans':plans,'limit':limit,'step':name=='lldb-exception-step','deadline':name=='lldb-stopped-deadline','report':str(e/'lldb-report.json'),'watch':bool(a.watch_compiler),'directory':str(e),'source_files':[str(directory/key) for key in text] if isinstance(text,dict) else [str(file)]},ensure_ascii=False,indent=2)+'\n', newline="\n")
            command=[debugger,'--no-lldbinit','--batch',binary]
            for line in ['settings set target.disable-aslr false','command script import '+json.dumps(str(source/'debug/lldb_nex.py')),'nex-load-private-task-debug '+json.dumps(str(manifest))+(' --compiler '+json.dumps(str(Path(a.watch_compiler).resolve())) if a.watch_compiler else ''),'command script import '+json.dumps(str(driver)),'nex-private-test-session '+str(options)]:command += ['-o',line]
            locale_env={'LC_ALL':'C','LANG':'C','PYTHONUTF8':'0','PYTHONCOERCECLOCALE':'0'} if name=='watch-c-locale' else None
            result=run(label+'-lldb',command,timeout=180,env=locale_env)
            observed=json.loads((e/'lldb-report.json').read_text());assert observed['ok'] and observed['all_stop'],observed
            expected_exit=(expected['value'] or 0)%256 if expected['kind']=='return' else 70
            if name=='lldb-stopped-deadline':expected_exit=70;assert 'E_TIMEOUT' in result.stdout and 'NEX_SOURCE_EXCEPTION ' not in result.stdout
            assert observed['exit']==expected_exit,(name,observed,expected)
            cleanup=next(line.split(' ',1)[1] for line in result.stdout.splitlines() if line.startswith('NEX_PRIVATE_LLDB_CLEANUP '));assert json.loads(cleanup)=={'ok':True,'live_frames':0,'managed_live':0}
            if expected['kind']=='exception':
                record=next(json.loads(line.split(' ',1)[1]) for line in result.stdout.splitlines() if line.startswith('NEX_SOURCE_EXCEPTION '));assert all(record[k]==expected[k] for k in ['code','message','line'])
                original=next(v for v in json.loads((e/'metadata.json').read_text())['operations'] if v['site']==record['source']['operation_site'] and v['function_hash']==record['source']['function_hash']);assert original['kind']=='statement.throw' and original['line']==expected['line']
            if a.watch_compiler:
                assert observed['source_absent_during_watch'] and observed['watches'] and observed['watch_rejections']
                for i,capture in enumerate(observed.get('captures',[])):
                    value=json.loads(run(label+'-offline-'+str(i),[a.watch_compiler,'inspect-private-task',capture['file'],'--manifest',manifest,'--expression',capture['expression'],'--json'],cwd=directory).stdout)
                    assert value['ok'] and value['value']==capture['value'] and value['archived'] is False and 'revision' not in value
            report['cases'].append({'name':name,'optimization':optimization,'source_sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'image_sha256':context['task_debug']['image_sha256'],'manifest_sha256':hashlib.sha256(manifest.read_bytes()).hexdigest(),'LLDB_report_sha256':hashlib.sha256((e/'lldb-report.json').read_bytes()).hexdigest(),'pauses':len(observed['observations']),'step_observations':len(observed['steps']),'expected_exit':expected_exit,'watches':len(observed.get('watches',[])),'captures':len(observed.get('captures',[])),'watch_rejections':len(observed.get('watch_rejections',[])),'passed':True});save()
            if name=='debug-call-rethrow':dap_case(binary,manifest,e,plans,optimization)
    report.update(ok=True,LLDB_comparisons=len(report['cases']),DAP_comparisons=len(report['dap_cases']),source_programs=len(fixtures),all_stop_pauses=sum(v['pauses'] for v in report['cases']),logical_step_cases=sum(bool(v['step_observations']) for v in report['cases']),deadline_cases=sum(v['name']=='lldb-stopped-deadline' for v in report['cases']))
    report.update(watches=sum(v['watches'] for v in report['cases']),captures=sum(v['captures'] for v in report['cases']),watch_rejections=sum(v['watch_rejections'] for v in report['cases']))
    save();print(json.dumps({'ok':True,'LLDB_comparisons':report['LLDB_comparisons'],'pauses':report['all_stop_pauses'],'report':str(out/'report.json')}))

if __name__=='__main__':main()
