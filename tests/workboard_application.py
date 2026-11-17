"""One actual030 application: persistent UI, Worker, task HTTP, SQLite and files.

Browser UI interaction is an additional explicit gate. This fixture builds the
production client, executes its generated controller and serves the native API.
"""
import argparse
import contextlib
import hashlib
import http.client
import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time

from host_fixture import stop_server

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('compiler',type=Path)
p.add_argument('--resources',type=Path,default=Path(__file__).resolve().parents[1])
p.add_argument('--output',type=Path)
p.add_argument('--output-parent',type=Path)
a=p.parse_args()
resources=a.resources.resolve();compiler=a.compiler.resolve()
out=a.output.resolve() if a.output else Path(tempfile.mkdtemp(prefix='nex-workboard-',dir=a.output_parent))
if a.output:out.mkdir(parents=True,exist_ok=False)
sha=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()
source=out/'source'
shutil.copytree(resources/'examples/workboard',source,ignore=shutil.ignore_patterns('.nex','var','node_modules'))
report={'schema':'nex.workboard-application/1','ok':False,'compiler_sha256':sha(compiler),
        'harness_sha256':sha(__file__),'source_language':'0.30','source_files':{
            str(path.relative_to(source)):sha(path) for path in source.rglob('*') if path.is_file()},
        'commands':[],'requests':[],'servers':[],'images':[],'browser_UI_qualified':False,
        'portable_SDK_qualified':False,'complete_objective':False}
started=time.monotonic()
def save():
    report['seconds']=round(time.monotonic()-started,3)
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
def run(label,argv,cwd=source):
    row={'label':label,'argv':list(map(str,argv)),'status':'running'};report['commands'].append(row);save()
    result=subprocess.run(row['argv'],cwd=cwd,capture_output=True,text=True,timeout=600)
    (out/(label+'.stdout')).write_text(result.stdout);(out/(label+'.stderr')).write_text(result.stderr)
    row.update(exit_code=result.returncode,status='passed' if result.returncode==0 else 'failed');save()
    assert result.returncode==0,(label,result.returncode,result.stdout[-3000:],result.stderr[-3000:])
    return result
def cli(label,*argv):return json.loads(run(label,[compiler,*argv,'--json']).stdout)
launches=0
@contextlib.contextmanager
def serve(image,database,files):
    global launches
    launches+=1;label='server-'+str(launches)
    command=[str(image),'--auth',str(auth),'--database',str(database),'--static',str(out/'dist'),
             '--files-root',str(files),'--files-write','1','--workers','4','--port','0']
    process=subprocess.Popen(command,cwd=out,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
                             env={**os.environ,'NEX_RESOURCE_DIR':str(out/'absent-compiler-resources')})
    lines=queue.Queue();reader=threading.Thread(target=lambda:lines.put(process.stdout.readline()),daemon=True);reader.start()
    line=''
    try:
        line=lines.get(timeout=20);match=re.fullmatch(r'NEX server http://127\.0\.0\.1:([0-9]+)\n',line)
        assert match,('server did not start',line)
        yield int(match[1])
    finally:
        if process.poll() is None:stop_server(process)
        try:stdout,stderr=process.communicate(timeout=20)
        except subprocess.TimeoutExpired:process.kill();stdout,stderr=process.communicate();raise
        reader.join(timeout=2)
        (out/(label+'.stdout')).write_text(line+stdout);(out/(label+'.stderr')).write_text(stderr)
        report['servers'].append({'argv':command,'exit_code':process.returncode,'source_copy_absent':not source.exists()});save()
        assert process.returncode==0 and 'E_INTERNAL_LEAK' not in stderr,(process.returncode,stderr)
def request(port,path,method='GET',body=None,user='alice',status=200):
    connection=http.client.HTTPConnection('127.0.0.1',port,timeout=15)
    try:
        connection.request(method,path,body=None if body is None else json.dumps(body,ensure_ascii=False).encode(),
                           headers={'Authorization':'Bearer '+tokens[user],'Content-Type':'application/json'})
        response=connection.getresponse();data=response.read();value=json.loads(data)
        report['requests'].append({'path':path,'method':method,'user':user,'status':response.status,'response':value});save()
        assert response.status==status,(response.status,value)
        return value
    finally:connection.close()
try:
    for entry in ['client','server']:
        cli('check-'+entry,'check',entry+'.nex')
    cli('source-tests','test','server.nex','--interpreter-only')
    for profile in ['debug','release']:
        cli('server-tests-'+profile,'test','server.nex','--profile',profile)
        built=cli('server-'+profile,'build','server.nex','--target','server','--profile',profile)
        metadata=json.loads(Path(built['metadata']).read_bytes())
        assert metadata['task_execution_abi']==0x4e45585400000008
        image=out/('workboard-'+profile+('.exe' if os.name=='nt' else ''))
        shutil.copy2(built['executable'],image)
        report['images'].append({'profile':profile,'path':str(image),'sha256':sha(image),'metadata_sha256':sha(built['metadata']),'task_ABI':metadata['task_execution_abi']});save()
    cli('client-tests-web','test','client.nex','--target','web')
    web=cli('web-build','build','client.nex','--target','web','--profile','release')
    generated=Path(web['directory']);shutil.copytree(web['dist'],out/'dist')
    report['web']={'revision':web['revision'],'build_key':web['build_key'],'dist':str(out/'dist'),
                   'files':{str(path.relative_to(out/'dist')):sha(path) for path in (out/'dist').rglob('*') if path.is_file()}}
    report['controller']=json.loads(run('controller',[os.environ.get('NEX_NODE','node'),'--no-warnings','--experimental-strip-types',
                                                     resources/'tests/workboard_controller.mjs',generated]).stdout)
    assert report['controller']['ok']
    # Source and compiler resources are not application runtime dependencies.
    source.rename(out/'retained-source')
    tokens={'alice':'workboard-alice-fixture','bob':'workboard-bob-fixture'}
    auth=out/'auth.json';auth.write_text(json.dumps({'schema':'nex.auth/1','tokens':[
        {'user':user,'sha256':hashlib.sha256(value.encode()).hexdigest()} for user,value in tokens.items()]}))
    for image in report['images']:
        profile=image['profile'];database=out/(profile+'.sqlite');files=out/(profile+'-files');files.mkdir()
        with serve(image['path'],database,files) as port:
            assert request(port,'/api/items')['snapshot']=={'next_id':'1','items':[]}
            first=request(port,'/api/items','POST',{'text':'Я🙂\0'},status=201)['snapshot']
            assert first=={'next_id':'2','items':[{'id':'1','text':'Я🙂\0','done':False}]}
            second=request(port,'/api/items','POST',{'text':'Second'},status=201)['snapshot']
            changed=request(port,'/api/items','PUT',{'id':'1','done':True})['snapshot']
            assert changed['items'][0]['done'] and len(changed['items'])==2
            exported=request(port,'/api/export','POST')
            saved=files/'tasks-616c696365.json'
            assert json.loads(saved.read_bytes())==changed and exported['snapshot']==changed
            assert len(request(port,'/api/items','POST',{'text':'After export'},status=201)['snapshot']['items'])==3
            assert request(port,'/api/restore','POST')['snapshot']==changed
            assert request(port,'/api/items',user='bob')['snapshot']=={'next_id':'1','items':[]}
            request(port,'/api/items','POST',{'text':'Bob'},user='bob',status=201)
            request(port,'/api/export','POST',user='bob')
            assert (files/'tasks-626f62.json').is_file() and json.loads(saved.read_bytes())==changed
        with serve(image['path'],database,files) as port:
            assert request(port,'/api/items')['snapshot']==changed
            assert request(port,'/api/items',user='bob')['snapshot']['items'][0]['text']=='Bob'
        image['export_sha256']=sha(saved);image['restart_persistence']=True
        image['file_export_restore']=True;image['ordinary_two_user_flow']=True;save()
    report['ok']=True
finally:save()
print(json.dumps({'ok':True,'report':str(out/'report.json'),'profiles':len(report['images']),'requests':len(report['requests']),
                  'browser_UI_qualified':False,'portable_SDK_qualified':False}))
