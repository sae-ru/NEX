"""Version-selected installed Workboard consumption for the complete SDK workflow."""
import hashlib
import json
from pathlib import Path
import re
import sys

EXAMPLE_FILES=('client.nex','server.nex','model.nex','nex.json','README.md','.gitignore')
RESOURCES=('tools/sdk_workboard.py','tests/workboard_application.py','tests/workboard_controller.mjs',
           'tests/host_fixture.py','docs/task-storage.md',
           'runtime/nex_store.cpp','runtime/store_runtime.cpp','runtime/nex_io.h','runtime/http_main.cpp',
           'runtime/nex_task_application.cpp','runtime/nex_task_application.h','runtime/nex_task_session.cpp',
           'runtime/nex_task_frame.cpp','runtime/nex_task_frame.h','runtime/nex_tasks_impl.h',
           'runtime/nex_cells.cpp','runtime/nex_cells.h','lib/http.nex','lib/net.nex','lib/web.nex','lib/worker.nex',
           *(('examples/workboard/'+name) for name in EXAMPLE_FILES))
COMMANDS=('check-client','check-server','source-tests','server-tests-debug','server-debug',
          'server-tests-release','server-release','client-tests-web','web-build','controller')
FLOW=(('GET','/api/items','alice',200),('POST','/api/items','alice',201),
      ('POST','/api/items','alice',201),('PUT','/api/items','alice',200),
      ('POST','/api/export','alice',200),('POST','/api/items','alice',201),
      ('POST','/api/restore','alice',200),('GET','/api/items','bob',200),
      ('POST','/api/items','bob',201),('POST','/api/export','bob',200),
      ('GET','/api/items','alice',200),('GET','/api/items','bob',200))

def require(value,message):
    if not value:raise RuntimeError('installed Workboard: '+message)

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def digest(value):return type(value) is str and re.fullmatch('[0-9a-f]{64}',value) is not None
def resource_names(resources):
    for name in RESOURCES:
        path=resources/name
        require(path.is_file() and not path.is_symlink(),'missing SDK resource '+name)
    return list(RESOURCES)

def exercise(*,cli,run,compiler,resources,root,browser):
    identity=cli('describe','--kind','index')
    capability=cli('describe','--field','task_storage')['value']
    require(capability==read(resources/'llm/language-pack.json')['task_storage'] and
            capability.get('source_support') is True and capability.get('source_language')=='0.30' and
            capability.get('async_database') is False,'storage capability/manifest differs')
    pins={name:sha(resources/name) for name in resource_names(resources)}
    directory=root/'workboard-application'
    summary=json.loads(run([sys.executable,'-B',resources/'tests/workboard_application.py',compiler,
                           '--resources',resources,'--output',directory,
                           '--web-mode','build' if browser else 'generate'],timeout=900))
    require(summary.get('ok') is True and summary.get('profiles')==2 and summary.get('requests')==24,
            'application command did not complete')
    path=directory/'report.json';proof=read(path)
    exports=[]
    for profile in ('debug','release'):
        exported=directory/(profile+'-files')/'tasks-616c696365.json'
        exports.append({'profile':profile,'sha256':sha(exported),'snapshot':read(exported)})
    value={'schema':'nex.sdk-workboard/1','ok':True,'compiler_sha256':sha(compiler),
           'compiler_build':identity['compiler_build'],'descriptor_hash':identity['descriptor_hash'],
           'resource_sha256':pins,'application_report_sha256':sha(path),'application':proof,
           'browser_build':browser,'exports':exports,'complete_SDK_workflow_claimed':False}
    validate({'compiler_sha256':value['compiler_sha256'],'resource_hashes':pins,
              'evidence':{'browser_build':browser,'workboard':value}})
    require(all(sha(resources/name)==pin for name,pin in pins.items()),'SDK resources changed during execution')
    return value

def validate(report):
    value=report.get('evidence',{}).get('workboard',{})
    require(isinstance(value,dict) and value.get('schema')=='nex.sdk-workboard/1' and value.get('ok') is True,
            'application phase is missing')
    require(digest(value.get('compiler_sha256')) and value['compiler_sha256']==report.get('compiler_sha256') and
            all(digest(value.get(k)) for k in ('compiler_build','descriptor_hash','application_report_sha256')),
            'compiler/report identity differs')
    pins=value.get('resource_sha256',{})
    require(isinstance(pins,dict) and set(pins)==set(RESOURCES) and
            all(digest(v) and report.get('resource_hashes',{}).get(k)==v for k,v in pins.items()),
            'resource identities differ')
    browser=report.get('evidence',{}).get('browser_build')
    require(type(browser) is bool and value.get('browser_build') is browser,'browser scope differs')
    proof=value.get('application',{})
    require(isinstance(proof,dict) and proof.get('schema')=='nex.workboard-application/1' and proof.get('ok') is True and
            proof.get('compiler_sha256')==value['compiler_sha256'] and proof.get('source_language')=='0.30' and
            proof.get('harness_sha256')==pins['tests/workboard_application.py'],'application identity differs')
    require(proof.get('source_files')=={name:pins['examples/workboard/'+name] for name in EXAMPLE_FILES},
            'copied application inputs differ')
    require(proof.get('browser_UI_qualified') is False and proof.get('portable_SDK_qualified') is False and
            proof.get('complete_objective') is False and value.get('complete_SDK_workflow_claimed') is False,
            'sub-workflow overstates its scope')
    commands=proof.get('commands',[]);labels=list(COMMANDS)
    if not browser:labels[labels.index('web-build')]='web-generate'
    require(isinstance(commands,list) and [c.get('label') for c in commands]==labels and
            all(c.get('status')=='passed' and type(c.get('exit_code')) is int and c['exit_code']==0 for c in commands),
            'application command coverage differs')
    web=proof.get('web',{})
    require(isinstance(web,dict) and web.get('production_build') is browser and digest(web.get('revision')) and
            (digest(web.get('build_key')) if browser else web.get('build_key') is None),
            'generated/production web scope differs')
    require(isinstance(web.get('files'),dict) and web['files'] and all(digest(v) for v in web['files'].values()) and
            set(web.get('generated_files',{}))=={'nex-map.json','src/program.ts','src/worker-program.ts','tsconfig.json'} and
            all(digest(v) for v in web['generated_files'].values()),'web artifacts are missing')
    controller=proof.get('controller',{})
    require(isinstance(controller,dict) and all(controller.get(k) is True for k in
            ('ok','persistent_state','immutable_published_views','transient_commands_once','file_commands',
             'signed_out_late_response_ignored','closed')) and
            controller.get('summary')=={'total':1,'done':1,'Unicode_scalars':3},'controller/Worker evidence differs')
    images=proof.get('images',[]);servers=proof.get('servers',[]);requests=proof.get('requests',[])
    require(isinstance(images,list) and len(images)==2 and [r.get('profile') for r in images]==['debug','release'] and
            all(type(r.get('task_ABI')) is int and r['task_ABI']==0x4e45585400000008 and
                all(digest(r.get(k)) for k in ('sha256','metadata_sha256','export_sha256')) and
                all(r.get(k) is True for k in ('restart_persistence','file_export_restore','ordinary_two_user_flow'))
                for r in images),'native image/ABI/persistence evidence differs')
    require(isinstance(servers,list) and len(servers)==4 and [s.get('server') for s in servers]==[1,2,3,4] and
            [s.get('profile') for s in servers]==['debug','debug','release','release'] and
            all(type(s.get('exit_code')) is int and s['exit_code']==0 and s.get('source_copy_absent') is True for s in servers),
            'server lifetime evidence differs')
    require(isinstance(requests,list) and len(requests)==24,'request count differs')
    exports=value.get('exports',[])
    require(isinstance(exports,list) and [r.get('profile') for r in exports]==['debug','release'],
            'file export coverage differs')
    empty={'next_id':'1','items':[]}
    first={'next_id':'2','items':[{'id':'1','text':'Я🙂\0','done':False}]}
    changed={'next_id':'3','items':[{'id':'1','text':'Я🙂\0','done':True},{'id':'2','text':'Second','done':False}]}
    bob={'next_id':'2','items':[{'id':'1','text':'Bob','done':False}]}
    for index,profile in enumerate(('debug','release')):
        rows=requests[index*12:(index+1)*12]
        require([(r.get('method'),r.get('path'),r.get('user'),r.get('status')) for r in rows]==list(FLOW) and
                all(r.get('profile')==profile for r in rows) and
                [r.get('server') for r in rows]==[index*2+1]*10+[index*2+2]*2,
                'ordinary request flow/profile differs')
        snapshots=[r.get('response',{}).get('snapshot') for r in rows]
        require(snapshots[0]==empty and snapshots[1]==first and snapshots[3]==changed and
                snapshots[4]==snapshots[6]==snapshots[10]==changed and snapshots[7]==empty and
                snapshots[8]==snapshots[9]==snapshots[11]==bob and
                snapshots[2]=={'next_id':'3','items':[{**first['items'][0]},changed['items'][1]]} and
                snapshots[5]=={'next_id':'4','items':[*changed['items'],{'id':'3','text':'After export','done':False}]},
                'database/file/restart response values differ')
        require(exports[index].get('snapshot')==changed and exports[index].get('sha256')==images[index]['export_sha256'],
                'exported file differs from the restored database')
