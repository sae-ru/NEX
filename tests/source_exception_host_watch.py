"""Actual private ABI2502 LLDB watch/capture after file/resource unwinding."""
import argparse,ast,hashlib,json,os,platform,shutil,subprocess
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('emitter');p.add_argument('compiler');p.add_argument('artifacts');a=p.parse_args()
    source=Path(__file__).resolve().parents[1];root=Path(a.artifacts).resolve();directory=root/'host-debug-unwind';file=directory/'main.nex'
    emitter=Path(a.emitter).resolve();compiler=Path(a.compiler).resolve();debugger=shutil.which('lldb');assert debugger
    tree=ast.parse((source/'tests/source_exception_task_lldb.py').read_text());assignment=next(n for n in tree.body if isinstance(n,ast.Assign) and any(getattr(t,'id','')=='LLDB_DRIVER' for t in n.targets));driver=ast.literal_eval(assignment.value)
    needle="str(config['limit'])+(' --nex-task-timeout-ms"
    assert driver.count(needle)==1
    driver=driver.replace(needle,"str(config['limit'])+' --nex-foreign '+json.dumps(config['catalog'])+(' --nex-task-timeout-ms")
    check="if isinstance(value,dict) and value.get('opaque'):assert 'opaque' in rows[name].get('unavailable','')"
    assert driver.count(check)==1
    driver=driver.replace(check,"if isinstance(value,dict) and value.get('identity_kind'):assert rows[name].get('preview','').startswith('<'+value['identity_kind']+' ') and rows[name]['preview'].endswith('>')\n            el"+check)
    marker="        assert values==request('values',task_id=identity),'watch changed inferior state'"
    assert driver.count(marker)==1
    driver=driver.replace(marker,'''        diagnostic=False
        for name,value in want['values'].items():
            if isinstance(value,dict) and value.get('identity_kind'):
                diagnostic=True;kind=value['identity_kind'];row=next(v for v in values['variables'] if v['name']==name);identity_text=row['preview'][len(kind)+2:-1];assert identity_text.isdecimal() and int(identity_text)>0
                if kind=='resource':watch(identity,name,error='E_DEBUG_UNAVAILABLE');watch(identity,name+'=='+name,error='E_DEBUG_UNAVAILABLE')
                else:watch(identity,name,{kind:identity_text});watch(identity,name+'=='+name,True)
                watch(identity,('file_is_open' if kind=='file' else 'resource_is_open')+'('+name+')',error='E_EFFECT')
        if diagnostic:
            expression='f==f';frame=json.loads(run('nex-frame '+expression));assert frame['schema']=='nex.private-task-debug-frame/1'
            file=Path(config['directory'])/('frame-'+str(len(report.get('captures',[])))+'.json');file.write_text(json.dumps(frame,ensure_ascii=False)+'\\n');report.setdefault('captures',[]).append({'file':str(file),'expression':expression,'value':True})
'''+marker)
    (root/'host_watch_driver.py').write_text(driver)
    file_identity={'identity_kind':'file'};resource_identity={'identity_kind':'resource'}
    wants={'owned':[{'values':{'f':file_identity,'c':resource_identity},'types':{'f':'file'},'caller_values':{'outer':41},'min_frames':2}],
           'catch':[{'values':{'code':'HOST','message':'λ\0🙂','outer':41},'absent':['f','c','recovered']}],
           'recovered':[{'values':{'code':'HOST','message':'λ\0🙂','outer':41,'recovered':42},'absent':['f','c']}]}
    plans={str(next(i for i,line in enumerate(file.read_text().splitlines(),1) if '// STOP:'+tag in line)):visits for tag,visits in wants.items()}
    report={'ok':False,'cases':[],'commands':[],'ordinary_functional_only':True,'security_checks_deferred_by_user':True,'private_host_abi':'0x4e45585400002502'}
    def save():(root/'host-watch-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    def run(label,argv,env=None):
        r=subprocess.run(list(map(str,argv)),cwd=directory,text=True,capture_output=True,env=env,timeout=180);(root/(label+'.stdout')).write_text(r.stdout);(root/(label+'.stderr')).write_text(r.stderr);report['commands'].append({'label':label,'argv':list(map(str,argv)),'exit':r.returncode});save();assert r.returncode==0,(label,r.returncode,r.stdout[-3000:],r.stderr[-2000:]);return r
    save()
    for optimization in ['0','2']:
        label='host-watch-O'+optimization;e=directory/('O'+optimization);binary=e/'program'
        if platform.system()=='Darwin':run(label+'-symbols',['dsymutil',binary])
        context=json.loads((e/'debug-context.json').read_text());assert context['descriptor_abi']==report['private_host_abi'] and context['archived'] is False and 'revision' not in context
        identity=run(label+'-identity',[emitter,'identity',binary]).stdout.strip().replace('-','').lower()
        context.update(program=str(binary),formatter=str(source/'debug/lldb_nex.py'),dap_adapter=str(source/'debug/nex_dap.py'));context['task_debug'].update(image_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),image_uuid=identity)
        manifest=e/'host-debug.json';manifest.write_text(json.dumps(context,ensure_ascii=False,indent=2)+'\n')
        options=e/'host-session.json';options.write_text(json.dumps({'source':str(file),'plans':plans,'limit':1000000,'report':str(e/'host-lldb-report.json'),'watch':True,'directory':str(e),'source_files':[str(file)],'catalog':str(root/'host.json')},ensure_ascii=False,indent=2)+'\n')
        files=e/'debug-files';files.mkdir();(files/'input').write_bytes(b'abcdef');events=files/'events';env={**os.environ,'NEX_FILES_ROOT':str(files),'NEX_FILES_WRITE':'1','NEX_PRIVATE_HOST_EVENTS':str(events)}
        argv=[debugger,'--no-lldbinit','--batch',binary]
        for command in ['settings set target.disable-aslr false','command script import '+json.dumps(str(source/'debug/lldb_nex.py')),'nex-load-private-task-debug '+json.dumps(str(manifest))+' --compiler '+json.dumps(str(compiler)),'command script import '+json.dumps(str(root/'host_watch_driver.py')),'nex-private-test-session '+str(options)]:argv+=['-o',command]
        executed=run(label+'-lldb',argv,env)
        observed=json.loads((e/'host-lldb-report.json').read_text());assert observed['ok'] and observed['all_stop'] and observed['exit']==42 and len(observed['observations'])==3 and observed['source_absent_during_watch']
        cleanup=json.loads(next(line.split(' ',1)[1] for line in executed.stdout.splitlines() if line.startswith('NEX_PRIVATE_HOST_CLEANUP ')));assert cleanup=={'ok':True,'live_frames':0,'managed_live':0}
        events_text=events.read_text();assert events_text.count('F')==events_text.count('X')==1
        assert len(observed['captures'])==3 and len(observed['watches'])>=10 and len(observed['watch_rejections'])>=6
        for i,capture in enumerate(observed['captures']):
            value=json.loads(run(label+'-offline-'+str(i),[compiler,'inspect-private-task',capture['file'],'--manifest',manifest,'--expression',capture['expression'],'--json']).stdout)
            assert value['ok'] and value['value']==capture['value'] and value['archived'] is False and 'revision' not in value
        report['cases'].append({'optimization':optimization,'owning_statement_pauses':3,'watches':len(observed['watches']),'captures':len(observed['captures']),'watch_rejections':len(observed['watch_rejections']),'source_absent_during_watch':True,'resource_factories':1,'resource_finalizers':1,'cleanup':cleanup,'passed':True});save()
    report.update(ok=True,LLDB_comparisons=2,statement_pauses=6,watches=sum(v['watches'] for v in report['cases']),captures=6,watch_rejections=sum(v['watch_rejections'] for v in report['cases']));save();print(json.dumps({'ok':True,'LLDB_comparisons':2,'report':str(root/'host-watch-report.json')}))

if __name__=='__main__':main()
