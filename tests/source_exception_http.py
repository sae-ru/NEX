"""Ordinary private exception HTTP/HTTPS execution; no security campaign."""
from host_fixture import stop_server
from host_fixture import run_native
import os
import argparse,concurrent.futures,contextlib,hashlib,http.client,json,os,platform,queue,re,signal,socket,ssl,subprocess,tempfile,threading,time
from pathlib import Path
from source_exception_host import MODULE,DECLARATIONS
from source_exception_profile_support import FLAGS as PROFILE_FLAGS,EXTRA_RUNTIME
import source_exception_module_debug_support as debug_support

PURE=r'''module private_http;
import "std/http.nex" as http;
server fn handle(req:http::Request)->http::Response !{task,throw}{
 if req.path=="/api/uncaught"{task_yield();throw("PURE","λ\u0000🙂");}
 try{task_yield();throw("PURE",req.body);}catch(code,message){return http::text_response(200,req.user+":"+code+":"+message);}
}
'''
HOST=r'''module private_http;
import "std/http.nex" as http;
DECLARATIONS
server fn leaf()->i64 !{task,fs,ffi,throw}{
 let f:file=unwrap(file_open_read("input"));
 let c:Counter=create(42);task_yield();
 assert(unwrap(file_read(f,6))==utf8_bytes("abcdef")&&read(c)==42);
 throw("HOST","λ\u0000🙂");
}
server fn handle(req:http::Request)->http::Response !{task,fs,ffi,throw}{
 if req.path=="/api/recover"{try{return http::text_response(200,str(leaf()));}catch(code,message){return http::text_response(200,req.user+":"+code+":"+message+":"+req.body);}}
 if req.path=="/api/rethrow"{try{return http::text_response(200,str(leaf()));}catch(code,message){task_yield();throw;}}
 if req.path=="/api/uncaught"{return http::text_response(200,str(leaf()));}
 if req.path=="/api/label"{throw("E_TIMEOUT","literal user code");}
 if req.path=="/api/trap"{try{let f:file=unwrap(file_open_read("input"));let c:Counter=create(42);task_yield();assert(false);}catch(code,message){return http::text_response(200,"caught runtime");}}
 if req.path=="/api/future"{try{let n:i64=with_tasks(1,server fn(s:task_scope)->i64 !{task,fs,ffi,throw}{let t:task<i64>=task_spawn(s,leaf);return task_wait(t);});return http::text_response(200,str(n));}catch(code,message){return http::text_response(200,req.user+":future:"+code+":"+message);}}
 if req.path=="/api/promote"{let f:file=with_tasks(1,server fn(s:task_scope)->file !{task,fs,throw}{let t:task<file>=task_spawn(s,server fn()->file !{task,fs}{try{throw("MAKE","retry");}catch(code,message){return unwrap(file_open_read("input"));}});return task_wait(t);});let c:Counter=create(42);let data:bytes=unwrap(file_read(f,6));assert(read(c)==42);file_close(f);return http::text_response(200,req.user+":"+unwrap(decode_utf8(data)));}
 if req.path=="/api/result"{let r:result<i64>=ordinary();try{throw(error_code(r),error_message(r));}catch(code,message){return http::text_response(200,req.user+":"+code+":"+message);}}
 if req.path=="/api/cancel"||req.path=="/api/limit"||req.path=="/api/deadline"{try{let f:file=unwrap(file_open_read("input"));let c:Counter=create(42);assert(unwrap(file_write_text("started","yes")));while true{assert(file_is_open(f)&&resource_is_open(c));task_yield();}}catch(code,message){return http::text_response(200,"caught control");}}
 return http::text_response(200,req.user+":"+req.body);
}
'''

def main(native_builder=None,context_factory=None,output_env='NEX_EXCEPTION_HTTP_OUTPUT',topologies=None,extra_paths=None,finalize=True,server_observer=None,profiling=False,debugging=False):
    p=argparse.ArgumentParser();p.add_argument('emitter');p.add_argument('reference');p.add_argument('compiler');p.add_argument('--output',default=os.environ.get(output_env));p.add_argument('--runtime-cache');p.add_argument('--openssl-include');p.add_argument('--ssl-library');p.add_argument('--crypto-library');p.add_argument('--sqlite-library',default='-lsqlite3');p.add_argument('--module-probe');p.add_argument('--debug-compiler');p.add_argument('--case',action='append');a=p.parse_args()
    source=Path(__file__).resolve().parents[1];runtime=source/'runtime';out=Path(a.output or tempfile.mkdtemp(prefix='nex-private-http-')).resolve();out.mkdir(parents=True,exist_ok=True)
    emitter=Path(a.emitter).resolve();reference=Path(a.reference).resolve();compiler=Path(a.compiler).absolute();cache=Path(a.runtime_cache).resolve() if a.runtime_cache else out;cache.mkdir(parents=True,exist_ok=True)
    openssl=Path('/opt/homebrew/opt/openssl@3');include=a.openssl_include or (str(openssl/'include') if platform.system()=='Darwin' else '/usr/include');crypto=a.crypto_library or (str(openssl/'lib/libcrypto.dylib') if platform.system()=='Darwin' else '-lcrypto');ssl_library=a.ssl_library or (str(openssl/'lib/libssl.dylib') if platform.system()=='Darwin' else '-lssl')
    report={'ok':False,'commands':[],'images':[],'references':[],'requests':[],'servers':[],'disconnects':[],'signature_rejections':[],'ordinary_functional_only':True,'security_checks_deferred_by_user':True,'public_language':'0.24','private_identity':'0.25-prototype','public_source_support':False,'HTTP':True,'HTTPS':True,'new_publication_claimed':False,'full_objective_complete':False}
    def save():(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n', newline="\n")
    def run(label,argv,env=None,allowed=(0,),timeout=300):
        r=run_native(list(map(str,argv)),cwd=out,text=True,capture_output=True,env=env,timeout=timeout);(out/(label+'.stdout')).write_text(r.stdout, newline="\n");(out/(label+'.stderr')).write_text(r.stderr, newline="\n");report['commands'].append({'label':label,'argv':list(map(str,argv)),'exit':r.returncode});save();assert r.returncode in allowed,(label,r.returncode,r.stdout[-1800:],r.stderr[-3000:]);return r
    save();run('target',[compiler,'-x','c','-S','-emit-llvm',os.devnull,'-o',out/'target.ll']);target=(out/'target.ll').read_text();triple=re.search(r'target triple = "([^"]+)"',target)[1];layout=re.search(r'target datalayout = "([^"]+)"',target)[1]
    flags=['-std=c++20','-O1','-g','-fPIC','-DNEX_STRUCTURED_WORKERS','-DNEX_ASYNC_TASKS','-DNEX_FOREIGN_ENABLED','-DNEX_SOURCE_EXCEPTION_HTTP','-I'+str(runtime),'-I'+include]
    assert not (profiling and debugging)
    if debugging:flags += [*debug_support.FLAGS,'-DNEX_TASK_DEBUG_COMPLETION_ENABLED']
    if profiling:flags += [*PROFILE_FLAGS,'-DNEX_PRIVATE_TASK_PROFILE_HTTP']
    headers={str(v.relative_to(runtime)):hashlib.sha256(v.read_bytes()).hexdigest() for v in sorted(runtime.rglob('*')) if v.is_file() and v.suffix in ['.h','.hpp']};compiler_digest=hashlib.sha256(compiler.read_bytes()).hexdigest();objects=[]
    names=['runtime.cpp','nex_files.cpp','files_runtime.cpp','nex_task_frame.cpp','nex_task_external.cpp','nex_task_application.cpp','foreign_runtime.cpp','nex_foreign.cpp','nex_ffi_loader.cpp','nex_ffi.cpp','nex_ffi_types.cpp','nex_ffi_resources.cpp','nex_external_resource.cpp','nex_resource_region.cpp','nex_resource_executor.cpp','nex_json.cpp','wire_runtime.cpp','nex_store.cpp','store_runtime.cpp','http_main.cpp']
    if profiling:names += EXTRA_RUNTIME
    if debugging:names += debug_support.EXTRA_RUNTIME
    for name in names:
        compile_flags=[flag for flag in flags if not (os.name=='nt' and name=='nex_profile.cpp' and flag=='-DNEX_SHARED_PROFILE_RUNTIME')]
        obj=cache/(name+'.o');obj.parent.mkdir(parents=True,exist_ok=True);stamp=obj.with_suffix('.recipe.json');recipe={'compiler':compiler_digest,'flags':compile_flags,'headers':headers,'source':hashlib.sha256((runtime/name).read_bytes()).hexdigest()}
        if not (obj.exists() and stamp.exists() and json.loads(stamp.read_text())==recipe):run('compile-'+name.replace('/','_'),[compiler,*compile_flags,'-c',runtime/name,'-o',obj]);stamp.write_text(json.dumps(recipe,sort_keys=True)+'\n', newline="\n")
        objects.append(obj)
    def default_context(directory,text):
        directory.mkdir();(directory/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.24','entry':'server.nex'}), newline="\n");file=directory/'server.nex';file.write_text(text, newline="\n");library=directory/'http.nex';library.write_text((source/'lib/http.nex').read_text(), newline="\n");result=directory/'source-context.json';result.write_text(json.dumps({'schema':'nex.private-task-source/2','file':str(file),'source':text,'entry_unit':'server.nex','units':[{'unit':'@std/http.nex','file':str(library),'source':library.read_text()},{'unit':'server.nex','file':str(file),'source':text}]},ensure_ascii=False)+'\n', newline="\n");return result
    def context(directory,text):
        return context_factory(directory,text,source,default_context) if context_factory else default_context(directory,text)
    negative_sources={
        'no-task':PURE.replace('!{task,throw}','!{throw}').replace('task_yield();',''),
        'wrong-request':'module private_http;import "std/http.nex" as http;server fn handle(req:str)->http::Response !{task}{return http::text_response(200,req);}',
        'wrong-result':'module private_http;import "std/http.nex" as http;server fn handle(req:http::Request)->str !{task}{return req.body;}',
        'wrong-realm':'module private_http;import "std/http.nex" as http;fn handle(req:http::Request)->http::Response !{task}{return http::text_response(200,req.body);}',
        'wrong-layout':PURE,
    }
    for name,text in negative_sources.items():
        directory=out/('reject-'+name);ctx=context(directory,text)
        if name=='wrong-layout':
            value=json.loads(ctx.read_text());library=next(v for v in value['units'] if v['unit']=='@std/http.nex');library['source']=library['source'].replace('  method: str;\n  path: str;','  path: str;\n  method: str;');(directory/'http.nex').write_text(library['source'], newline="\n");ctx.write_text(json.dumps(value,ensure_ascii=False)+'\n', newline="\n")
        rejected=run('reject-'+name,[emitter,'emit-context',ctx,directory/'emission',triple,layout,'false','http'],allowed=(1,));assert 'E_HTTP_SIGNATURE' in rejected.stderr,(name,rejected.stderr);report['signature_rejections'].append({'name':name,'code':'E_HTTP_SIGNATURE','passed':True});save()
    signatures=context(out/'signatures',HOST.replace('DECLARATIONS',DECLARATIONS.replace('@PIN@','0'*64)));sigs=json.loads(run('signatures',[emitter,'signatures-context',signatures]).stdout)
    bundle=out/'bundle';bundle.mkdir();rows=[]
    for name,op in [('create',1),('read',2),('add',3),('ordinary',4),('bad',5)]:
        signature=hashlib.sha256(json.dumps(sigs[name],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest();rows.append('{sizeof(nex_ffi_export_v1),0,'+json.dumps(name)+','+json.dumps(signature)+',callback,(void*)'+str(op)+'}')
    (out/'module.c').write_text(MODULE.replace('EXPORTS',','.join(rows)), newline="\n");run('module',[compiler,'-x','c','-std=c11','-shared','-fPIC','-fvisibility=hidden','-I'+str(runtime),out/'module.c','-o',bundle/'module']);(bundle/'NOTICE').write_text('NEX ordinary private HTTP fixture\n', newline="\n")
    manifest={'schema':'nex.foreign-bundle/1','platform':('windows' if os.name=='nt' else 'macos' if platform.system()=='Darwin' else 'linux')+'-'+({'arm64':'arm64','aarch64':'arm64','x86_64':'x86_64','amd64':'x86_64'}[platform.machine().lower()]),'entry':'module','files':[{'path':name,'sha256':hashlib.sha256((bundle/name).read_bytes()).hexdigest()} for name in ['module','NOTICE']],'exports':{name:hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest() for name,value in sigs.items()},'notices':['NOTICE']};(bundle/'manifest.json').write_text(json.dumps(manifest)+'\n', newline="\n");pin=hashlib.sha256((bundle/'manifest.json').read_bytes()).hexdigest();catalog=out/'host.json';catalog.write_text(json.dumps({'schema':'nex.foreign-host/1','module_limit':64,'libraries':{'host':{'directory':'bundle','manifest_sha256':pin,'exports':list(sigs)}}})+'\n', newline="\n")
    tokens={user:'fixture-'+user for user in ['alice','bob']};auth=out/'auth.json';auth.write_text(json.dumps({'schema':'nex.auth/1','tokens':[{'user':user,'sha256':hashlib.sha256(token.encode()).hexdigest()} for user,token in tokens.items()]}), newline="\n");run('TLS-certificate',['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',out/'key.pem','-out',out/'cert.pem','-days','1','-subj','/CN=localhost','-addext','subjectAltName=IP:127.0.0.1'])
    @contextlib.contextmanager
    def absent_sources(directory):
        hidden=[]
        try:
            context_file=directory/'source-context.json';saved=json.loads(context_file.read_text());paths=[context_file,*[Path(unit['file']) for unit in saved['units']]]
            for original in paths:
                temporary=original.with_name(original.name+'.hidden');assert original.is_file() and not temporary.exists();original.rename(temporary);hidden.append((original,temporary))
            assert all(not original.exists() for original,_ in hidden)
            yield
        finally:
            for original,temporary in hidden:
                if temporary.exists():temporary.rename(original)
    launch=0
    @contextlib.contextmanager
    def server(binary,foreign,tls=False,extra=()):
        nonlocal launch
        with absent_sources(binary.parent.parent):
            launch+=1;directory=out/('server-'+str(launch));directory.mkdir();files=directory/'files';files.mkdir();(files/'input').write_text('abcdef', newline="\n");events=directory/'events';env={**os.environ,'NEX_FILES_ROOT':str(files),'NEX_FILES_WRITE':'1','NEX_PRIVATE_HOST_EVENTS':str(events),'NEX_RESOURCE_DIR':str(out/'missing-sdk')};argv=[binary,'--auth',auth,'--database',directory/'database.sqlite','--port','0','--workers','4',*extra]
            if foreign:argv+=['--foreign',catalog]
            if tls:argv+=['--cert',out/'cert.pem','--key',out/'key.pem']
            if profiling:env['NEX_PROFILE_OUTPUT']=str(directory/'profile.json')
            first_request=len(report['requests'])
            process=subprocess.Popen(list(map(str,argv)),cwd=directory,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            lines=queue.Queue();stdout_chunks=[];stderr_chunks=[]
            def drain_stdout():
                first=True
                for chunk in process.stdout:
                    if first:lines.put(chunk);first=False
                    else:stdout_chunks.append(chunk)
                if first:lines.put('')
            reader=threading.Thread(target=drain_stdout,daemon=True)
            error_reader=threading.Thread(target=lambda:stderr_chunks.append(process.stderr.read()),daemon=True)
            reader.start();error_reader.start();line=''
            try:
                line=lines.get(timeout=20);match=re.fullmatch(r'NEX server (https?)://127\.0\.0\.1:([0-9]+)\n',line);assert match and match[1]==('https' if tls else 'http'),line;yield int(match[2]),files,events
            finally:
                if process.poll() is None:stop_server(process)
                try:process.wait(timeout=20)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=20);raise
                reader.join(timeout=2);error_reader.join(timeout=2)
                assert not reader.is_alive() and not error_reader.is_alive(),'server output readers did not join'
                stdout=''.join(stdout_chunks);stderr=''.join(stderr_chunks)
                (directory/'stdout').write_text(line+stdout, newline="\n");(directory/'stderr').write_text(stderr, newline="\n");assert process.returncode==0,(argv,process.returncode,stderr)
                observed=events.read_text() if events.exists() else '';assert observed.count('F')==observed.count('X'),observed
                row={'launch':launch,'argv':list(map(str,argv)),'TLS':tls,'exit':process.returncode,'factories':observed.count('F'),'finalizers':observed.count('X'),'stderr':stderr,'selected_sources_absent':True,'passed':True}
                if profiling:row.update(profile_file=str(directory/'profile.json'),completed_requests=len(report['requests'])-first_request)
                if server_observer:server_observer(binary,row)
                report['servers'].append(row);save()
    def request(port,path,user='alice',body='A🌍\0β',tls=False):
        connection=http.client.HTTPSConnection('127.0.0.1',port,context=ssl.create_default_context(cafile=str(out/'cert.pem')),timeout=10) if tls else http.client.HTTPConnection('127.0.0.1',port,timeout=10)
        try:connection.request('POST',path,body=body.encode(),headers={'Authorization':'Bearer '+tokens[user]});response=connection.getresponse();value=response.read().decode();result={'status':response.status,'body':value,'content_type':response.getheader('Content-Type'),'request_id':response.getheader('X-Request-Id')}
        finally:connection.close()
        report['requests'].append({'path':path,'user':user,'TLS':tls,'result':result});return result
    programs=[(name if not topologies else name+'-'+topology,text,foreign) for name,text,foreign in [('pure',PURE,False),('host',HOST.replace('DECLARATIONS',DECLARATIONS.replace('@PIN@',pin)),True)] for topology in (topologies or [''])]
    programs=[row for row in programs if not a.case or row[0] in a.case]
    builder_state={'source':source,'runtime':runtime,'out':out,'compiler':compiler,'flags':flags,'objects':objects,'triple':triple,'layout':layout,'crypto':crypto,'ssl':ssl_library,'sqlite':a.sqlite_library,'run':run,'report':report,'save':save,'module_probe':Path(a.module_probe).resolve() if a.module_probe else None,'cache':cache,'profiling':profiling,'debugging':debugging,'debug_compiler':Path(a.debug_compiler).resolve() if a.debug_compiler else None,'emitter':emitter}
    for name,text,foreign in programs:
        directory=out/name;ctx=context(directory,text);paths=['/api/recover','/api/uncaught'] if not foreign else ['/api/echo','/api/recover','/api/future','/api/promote','/api/result','/api/uncaught','/api/rethrow','/api/label','/api/trap']
        if foreign:paths+=extra_paths or []
        expected={}
        for i,path in enumerate(paths):
            actual=None
            for mode in ['http-reference','http-task-ir']:
                files=directory/(str(i)+'-'+mode);files.mkdir();(files/'input').write_text('abcdef', newline="\n");input_file=files/'request.json';input_file.write_text(json.dumps({'method':'POST','path':path,'query':'','body':'A🌍\0β','user':'alice','request_id':'1'}), newline="\n");events=files/'events';env={**os.environ,'NEX_FILES_ROOT':str(files),'NEX_FILES_WRITE':'1','NEX_PRIVATE_HOST_EVENTS':str(events)};value=json.loads(run(name+'-'+str(i)+'-'+mode,[reference,mode,ctx,input_file,'1000000',catalog if foreign else '-'],env).stdout);assert value['managed_live']==value['external_capacity']==0
                if actual is None:actual=value
                else:assert actual==value,(path,actual,value)
            expected[path]=actual;report['references'].append({'program':name,'path':path,'outcome':actual});save()
        for optimization in ['0','2']:
            label=name+'-O'+optimization;e=directory/('O'+optimization);e.mkdir()
            if native_builder:
                meta,binary=native_builder(builder_state,name,directory,ctx,e,optimization)
                assert meta['descriptor_abi']==0x4e45585400002502
            else:
                run(label+'-emit',[emitter,'emit-context',ctx,e,triple,layout,str(optimization=='2').lower(),'http']);meta=json.loads((e/'metadata.json').read_text());assert meta['descriptor_abi']==(0x4e45585400002502 if foreign else 0x4e45585400002501);ir=(e/'program.ll').read_text();assert not re.search(r'^define[^\n]*@main\(',ir,re.M) and '@nex_task_application_execute' not in ir
                bridge=e/'bridge.cpp';bridge.write_text('#include "nex_task_application.h"\nextern "C" const nexrt::TaskCodeDescriptor *'+meta['descriptor_symbol']+'();\nextern "C" const nexrt::TaskExecutionLimits *nex_server_task_limits(){static const nexrt::TaskExecutionLimits limits{100000000,5000,4};return &limits;}\nextern "C" nexrt::Handle *nex_server_task_dispatch(nexrt::Handle *value,unsigned workers){return nexrt::executeConfiguredSourceExceptionTaskHttpRequest(*'+meta['descriptor_symbol']+'(),value,workers);}\n', newline="\n");binary=e/('server.exe' if os.name=='nt' else 'server');run(label+'-link',[compiler,*flags,'-O'+optimization,e/'program.ll',bridge,*objects,ssl_library,crypto,a.sqlite_library,'-pthread',*(['-ldl'] if platform.system()!='Darwin' else []),'-o',binary])
            for tls in [False,True]:
                first=len(report['requests'])
                with server(binary,foreign,tls) as (port,files,events):
                    for path in paths:
                        response=request(port,path,tls=tls);oracle=expected[path]
                        if oracle['kind']=='return':assert all(response[k]==oracle[k] for k in ['status','body','content_type']),(path,response,oracle)
                        else:assert response['status']==500 and json.loads(response['body'])['error']['code']==('E_SOURCE_EXCEPTION' if oracle['kind']=='exception' else oracle['code']),(path,response,oracle)
                        observed=events.read_text() if events.exists() else '';assert observed.count('F')==observed.count('X'),(path,observed)
                    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                        replies=list(pool.map(lambda user:request(port,'/api/recover',user,tls=tls),['alice','bob']*4))
                    assert all(v['status']==200 and v['body'].startswith(user+':') for user,v in zip(['alice','bob']*4,replies))
                logs=[json.loads(line.split(' ',1)[1]) for line in report['servers'][-1]['stderr'].splitlines() if line.startswith('NEX_SOURCE_EXCEPTION ')]
                for path,oracle in expected.items():
                    if oracle['kind']!='exception':continue
                    response=next(v['result'] for v in report['requests'][first:] if v['path']==path and v['user']=='alice');record=next(v for v in logs if v['request_id']==response['request_id']);assert all(record[k]==oracle[k] for k in ['code','message','line']);original=next(v for v in meta['operations'] if v['site']==record['source']['operation_site'] and v['function_hash']==record['source']['function_hash']);assert original['kind']=='statement.throw' and original['line']==oracle['line'] and original['function_source_hash']==record['source']['function_source_hash']
            if foreign:
                with server(binary,True,extra=['--timeout-ms','150']) as (port,files,events):
                    response=request(port,'/api/deadline');assert response['status']==504 and json.loads(response['body'])['error']['code']=='E_TIMEOUT'
                with server(binary,True,extra=['--budget','1000']) as (port,files,events):
                    response=request(port,'/api/limit');assert response['status']==429 and json.loads(response['body'])['error']['code']=='E_LIMIT'
                with server(binary,True) as (port,files,events):
                    client=socket.create_connection(('127.0.0.1',port),timeout=5);client.sendall(('POST /api/cancel HTTP/1.1\r\nHost: localhost\r\nAuthorization: Bearer '+tokens['alice']+'\r\nContent-Length: 0\r\n\r\n').encode());deadline=time.monotonic()+5
                    while not (files/'started').exists() and time.monotonic()<deadline:time.sleep(.01)
                    assert (files/'started').exists();client.close();deadline=time.monotonic()+5
                    while time.monotonic()<deadline:
                        observed=events.read_text() if events.exists() else ''
                        if observed.count('F')==observed.count('X') and observed.count('F')>0:break
                        time.sleep(.01)
                    else:raise AssertionError('disconnect did not settle foreign owners')
                    assert request(port,'/api/recover')['status']==200
                    report['disconnects'].append({'optimization':optimization,'started_marker':True,'factories_before_recovery':observed.count('F'),'finalizers_before_recovery':observed.count('X'),'next_request_succeeded':True});save()
                assert 'E_CANCELLED' in report['servers'][-1]['stderr']
            report['images'].append({'program':name,'optimization':optimization,'descriptor_abi':meta['descriptor_abi'],'source_sha256':hashlib.sha256((directory/'server.nex').read_bytes()).hexdigest(),'image_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'passed':True});save()
    report.update(ok=finalize,source_programs=len(programs),native_images=len(report['images']),reference_comparisons=len(report['references']),HTTP_requests=len(report['requests']),HTTP_server_launches=len(report['servers']),compiled_native_execution=True,source_and_runtime_errors_separate=True,source_free_execution=True);save()
    if finalize:print(json.dumps({'ok':True,'images':len(report['images']),'references':len(report['references']),'requests':len(report['requests']),'report':str(out/'report.json')}))
    return {**builder_state,'reference':reference,'catalogue':catalog,'pin':pin,'server':server,'request':request}

if __name__=='__main__':main()
