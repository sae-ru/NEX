#!/usr/bin/env python3
"""Real025 normal-CLI HTTP exception boundaries and server cleanup."""
from host_fixture import stop_server
import argparse
import hashlib
import http.client
import json
import os
from pathlib import Path
import queue
import re
import signal
import subprocess
import tempfile
import threading

parser=argparse.ArgumentParser()
parser.add_argument('nex')
parser.add_argument('--output')
args=parser.parse_args()
nex=str(Path(args.nex).resolve())
out=Path(args.output or os.environ.get('NEX_PUBLIC025_HTTP_OUTPUT') or tempfile.mkdtemp(prefix='nex-public025-http-')).resolve()
out.mkdir(parents=True,exist_ok=True)
digest=hashlib.sha256(Path(nex).read_bytes()).hexdigest()
report={'ok':False,'compiler_sha256':digest,'images':[],'requests':[],'servers':[],'file_grants':[],'rejected_options':[]}
auth=out/'auth.json'
auth.write_text(json.dumps({'schema':'nex.auth/1','tokens':[{
    'user':'alice','sha256':hashlib.sha256(b'fixture-alice').hexdigest()}]}), newline="\n")
payload='λ\0🙂'
files=out/'files';files.mkdir();(files/'input').write_text('abcdef', newline="\n")

def save():
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n', newline="\n")

def cli(project,label,arguments):
    result=subprocess.run([nex,*map(str,arguments),'--json'],cwd=project,
                          capture_output=True,text=True,timeout=600)
    (out/(label+'.stdout')).write_text(result.stdout, newline="\n")
    (out/(label+'.stderr')).write_text(result.stderr, newline="\n")
    assert result.returncode==0,(label,result.stdout,result.stderr)
    return json.loads(result.stdout)

try:
    for tasks in [False,True]:
        mode='task' if tasks else 'sync'
        project=out/mode;project.mkdir()
        (project/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.27','entry':'main.nex'}), newline="\n")
        text='''module public_http;
import "std/http.nex" as http;
server fn fail(value:str)->http::Response !{throw}{throw("USER",value);}
server fn handle(req:http::Request)->http::Response !{EFFECTS}{
 YIELD
 if req.path=="/api/write"{
  let written:result<bool>=file_write_text("output",req.body);
  if is_ok(written){return http::json_response(200,encode_json("written"));}
  return http::json_response(200,encode_json(error_code(written)));
 }
 if req.path=="/api/file" || req.path=="/api/file-error"{
  let owner:file=unwrap(file_open_read("input"));
  assert(unwrap(file_read(owner,6))==utf8_bytes("abcdef"));
  if req.path=="/api/file-error"{return fail(req.body);}
  assert(file_close(owner));
 }
 if req.path=="/api/trap"{assert(false);}
 if req.path=="/api/uncaught"{return fail(req.body);}
 if req.path=="/api/rethrow"{try{return fail(req.body);}catch(code,message){throw;}}
 try{return fail(req.body);}catch(code,message){return http::json_response(200,encode_json([code,message,req.user,req.request_id]));}
}
'''.replace('EFFECTS','task,fs,throw' if tasks else 'fs,throw').replace('YIELD','task_yield();' if tasks else '')
        (project/'main.nex').write_text(text, newline="\n")
        for profile in ['debug','release']:
            label=mode+'-'+profile
            built=cli(project,label,['build','--target','server','--profile',profile,
                                     '--build-directory',out/'cache'])
            image=Path(built['executable'])
            metadata=json.loads((image.parent/'build.json').read_text())
            assert metadata['runtime_requirements']['tasks']==tasks
            assert metadata['task_execution_abi']==(0x4e45585400000007 if tasks else 0)
            report['images'].append({'mode':mode,'profile':profile,'path':str(image),'build_key':built['key'] if 'key' in built else metadata['key']})
            env={**os.environ,'NEX_RESOURCE_DIR':str(out/'absent-resources'),
                 'NEX_FILES_ROOT':str(out/'unconfigured-ambient-root')}
            process=subprocess.Popen([str(image),'--auth',str(auth),'--database',str(out/(label+'.sqlite')),
                                      '--port','0','--workers','4','--files-root',str(files)],cwd=out,env=env,
                                     stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            lines=queue.Queue()
            reader=threading.Thread(target=lambda:lines.put(process.stdout.readline()),daemon=True)
            reader.start();first=''
            try:
                first=lines.get(timeout=20)
                match=re.fullmatch(r'NEX server http://127\.0\.0\.1:([0-9]+)\n',first)
                assert match,(label,first)
                port=int(match[1])
                # Replacing the selected pathname must not retarget the pinned
                # capability retained by this live HTTP process or its tasks.
                pinned=out/(label+'-pinned-files');files.rename(pinned)
                files.mkdir();(files/'input').write_text('wrong replacement', newline="\n")
                for path in ['/api/caught','/api/uncaught','/api/caught','/api/rethrow','/api/trap','/api/file-error','/api/file','/api/write','/api/caught']:
                    connection=http.client.HTTPConnection('127.0.0.1',port,timeout=5)
                    try:
                        connection.request('POST',path,body=payload.encode(),headers={'Authorization':'Bearer fixture-alice'})
                        response=connection.getresponse();body=json.loads(response.read())
                        status=response.status;request_id=response.getheader('X-Request-Id')
                    finally:
                        connection.close()
                    assert request_id
                    expected=200 if path in ['/api/caught','/api/file','/api/write'] else 500
                    assert status==expected,(label,path,status,body)
                    if path=='/api/write':
                        assert body=='CAPABILITY' and not (files/'output').exists(),(label,body)
                    elif status==200:
                        assert body==['USER',payload,'alice',request_id],(label,body)
                    else:
                        expected_code='E_ASSERT' if path=='/api/trap' else 'E_SOURCE_EXCEPTION'
                        assert body['error']['code']==expected_code,(label,body)
                    report['requests'].append({'image':label,'path':path,'status':status,'body':body,'request_id':request_id})
                    save()
            finally:
                if process.poll() is None:stop_server(process)
                try:stdout,stderr=process.communicate(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill();stdout,stderr=process.communicate();raise
                reader.join(timeout=2)
                (out/(label+'-server.stdout')).write_text(first+stdout, newline="\n")
                (out/(label+'-server.stderr')).write_text(stderr, newline="\n")
                report['servers'].append({'image':label,'exit':process.returncode});save()
                assert process.returncode==0 and 'E_INTERNAL_LEAK' not in stderr,(label,process.returncode,stderr)
                pinned=out/(label+'-pinned-files')
                if pinned.exists():
                    assert (pinned/'input').read_text()=='abcdef'
                    assert not (pinned/'output').exists()
                    assert (files/'input').read_text()=='wrong replacement'
                    (files/'input').unlink();files.rmdir();pinned.rename(files)
                    report['images'][-1]['physical_root_replacement']=True;save()
            errors=[json.loads(line.split(' ',1)[1]) for line in stderr.splitlines() if line.startswith('NEX_SOURCE_EXCEPTION ')]
            assert len(errors)==3,(label,stderr)
            for error in errors:
                assert error['code']=='USER' and error['message']==payload and error['line']==3
                assert error['source']['kind']=='statement.throw'
                assert error['source']['compiler_build']==metadata['compiler_build']
            expected_ids={row['request_id'] for row in report['requests'] if row['image']==label and row['path'] in ['/api/uncaught','/api/rethrow','/api/file-error']}
            assert {error['request_id'] for error in errors}==expected_ids
            assert len({row['request_id'] for row in report['requests'] if row['image']==label})==9
            assert (files/'input').read_text()=='abcdef'
            # Validate the operator grant on the actual image, including an
            # explicit deny and explicit write permission. Ambient environment
            # points elsewhere so it cannot accidentally satisfy the grant.
            for flag in ['0','1']:
                grant_label=label+'-write-'+flag
                command=[str(image),'--auth',str(auth),'--database',str(out/(grant_label+'.sqlite')),
                         '--port','0','--files-root',str(files),'--files-write',flag]
                child=subprocess.Popen(command,cwd=out,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
                first='';events=queue.Queue()
                watcher=threading.Thread(target=lambda:events.put(child.stdout.readline()),daemon=True);watcher.start()
                try:
                    first=events.get(timeout=20)
                    match=re.fullmatch(r'NEX server http://127\.0\.0\.1:([0-9]+)\n',first);assert match,(grant_label,first)
                    connection=http.client.HTTPConnection('127.0.0.1',int(match[1]),timeout=5)
                    try:
                        connection.request('POST','/api/write',body=payload.encode(),headers={'Authorization':'Bearer fixture-alice'})
                        response=connection.getresponse();body=json.loads(response.read());assert response.status==200,(grant_label,body)
                    finally:connection.close()
                    assert body==('written' if flag=='1' else 'CAPABILITY'),(grant_label,body)
                    if flag=='1':assert (files/'output').read_text()==payload
                    else:assert not (files/'output').exists()
                    report['file_grants'].append({'image':label,'write':flag,'result':body});save()
                finally:
                    if child.poll() is None:stop_server(child)
                    try:stdout,stderr=child.communicate(timeout=15)
                    except subprocess.TimeoutExpired:child.kill();stdout,stderr=child.communicate();raise
                    watcher.join(timeout=2)
                    (out/(grant_label+'-server.stdout')).write_text(first+stdout, newline="\n")
                    (out/(grant_label+'-server.stderr')).write_text(stderr, newline="\n")
                    assert child.returncode==0 and 'E_INTERNAL_LEAK' not in stderr,(grant_label,child.returncode,stderr)
                if (files/'output').exists():(files/'output').unlink()
            invalid=[['--files-write','1'],['--files-root','relative'],
                     ['--files-root',str(files),'--files-root',str(files)],
                     ['--files-root',str(files),'--files-write','2'],
                     ['--files-root',str(files),'--files-write','0','--files-write','1'],
                     ['--files-root',str(files/'input')]]
            for index,options in enumerate(invalid):
                rejected=subprocess.run([str(image),'--auth',str(auth),'--database',str(out/(label+'-invalid.sqlite')),
                                         '--port','0',*options],cwd=out,env=env,capture_output=True,text=True,timeout=20)
                assert rejected.returncode!=0 and 'NEX server http://' not in rejected.stdout,(label,options,rejected.stdout,rejected.stderr)
                report['rejected_options'].append({'image':label,'options':options,'exit':rejected.returncode,'stderr':rejected.stderr})
            save()
    # A server without reachable file operations has no filesystem adapter.
    # Use the same cache as file-enabled images to cover compile-flag identity.
    project=out/'no-files';project.mkdir()
    (project/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.27','entry':'main.nex'}), newline="\n")
    (project/'main.nex').write_text('module no_files;import "std/http.nex" as http;server fn handle(req:http::Request)->http::Response{return http::json_response(200,"42");}', newline="\n")
    built=cli(project,'no-files',['build','--target','server','--profile','debug','--build-directory',out/'cache'])
    rejected=subprocess.run([built['executable'],'--auth',str(auth),'--database',str(out/'no-files.sqlite'),
                             '--port','0','--files-root',str(files)],cwd=out,capture_output=True,text=True,timeout=20)
    assert rejected.returncode!=0 and 'server image has no filesystem adapter' in rejected.stderr
    assert 'NEX server http://' not in rejected.stdout
    report['adapter_rejection']={'exit':rejected.returncode,'stderr':rejected.stderr,'executable':built['executable']}
    assert hashlib.sha256(Path(nex).read_bytes()).hexdigest()==digest
    report['ok']=True
finally:
    save()
print(json.dumps({'ok':report['ok'],'report':str(out/'report.json')}))
