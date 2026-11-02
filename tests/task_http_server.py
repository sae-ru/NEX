"""Real public task HTTP requests: control, identity, file authority and cleanup."""
from host_fixture import stop_server, run_native
import argparse,concurrent.futures,contextlib,hashlib,http.client,json,os,queue,re,signal,socket,ssl,subprocess,tempfile,threading,time,traceback
from pathlib import Path

parser=argparse.ArgumentParser();parser.add_argument('compiler',type=Path);parser.add_argument('--output',type=Path);args=parser.parse_args()
temporary=None
if args.output:root=args.output.resolve();root.mkdir()
else:temporary=tempfile.TemporaryDirectory(prefix='nex task HTTP server 🧠 ');root=Path(temporary.name).resolve()
compiler=args.compiler.resolve();start=time.monotonic();checks=0;launches=0
report={'schema':'nex.task-http-server/1','ok':False,'state':'starting','commands':[],'requests':[],
 'compiler':str(compiler),'compiler_sha256':hashlib.sha256(compiler.read_bytes()).hexdigest(),
 'helper_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'language':'0.28',
 'images':[],'cancel_observations':[],'public_HTTP_task_target':True,'async_network_DB_claimed':False,'full_objective_complete':False}
def save():report['seconds']=round(time.monotonic()-start,3);(root/'report.json').write_text(json.dumps(report,indent=2)+'\n', newline="\n")
def require(value,message):
 global checks
 checks+=1;assert value,message
def run(name,argv,expected=0,timeout=600):
 report['state']=name;save();p=run_native(list(map(str,argv)),cwd=root,capture_output=True,text=True,timeout=timeout)
 (root/(name+'.stdout')).write_text(p.stdout, newline="\n");(root/(name+'.stderr')).write_text(p.stderr, newline="\n")
 report['commands'].append({'name':name,'argv':list(map(str,argv)),'exit_code':p.returncode,'expected':expected});save()
 require(p.returncode==expected,(name,p.returncode,p.stdout[-2000:],p.stderr[-3000:]));return p
def cli(name,*argv,expected=0):return json.loads(run(name,[compiler,*argv,'--json'],expected).stdout)
SOURCE='''module task_http;
import "std/http.nex" as http;
struct Echo {user:str;request_id:str;body:str;answer:i64;}
server fn handle(req:http::Request)->http::Response !{task,fs,throw}{
 if req.path=="/api/trap" {task_yield();let zero:i64=0;return http::text_response(200,str(1/zero));}
 if req.path=="/api/limit" || req.path=="/api/deadline" {while true{task_yield();}}
 if req.path=="/api/cancel" {
  let kept:file=unwrap(file_open_read("input"));
  assert(unwrap(file_write_text("started", "yes")));
  while true{assert(file_is_open(kept));task_yield();}
 }
 if req.path=="/api/read" || req.path=="/api/traversal" {
  let path:str=match req.path {"/api/read"=>"input",_=>"../private-auth.json"};
  let value:result<str>=file_read_text(path);
  if !is_ok(value){return http::json_response(403,encode_json(error_code(value)));}
  return http::json_response(200,encode_json(unwrap(value)));
 }
 if req.path=="/api/write" {
  let written:result<bool>=file_write_text("saved-"+req.user,req.body);
  if !is_ok(written){return http::json_response(403,encode_json(error_code(written)));}
  return http::json_response(200,encode_json(unwrap(written)));
 }
 if req.path=="/api/stream" {
  let opened:result<file>=file_open_read("input");
  if !is_ok(opened){return http::json_response(403,encode_json(error_code(opened)));}
  let file:file=unwrap(opened);let value:bytes=unwrap(file_read(file,100));assert(file_close(file));
  return http::json_response(200,encode_json(unwrap(decode_utf8(value))));
 }
 let n:i64=with_tasks(2,fn(scope:task_scope)->i64 !{task,throw}{
  let left:task<i64>=task_spawn(scope,fn()->i64 !{task}{task_yield();return 20;});
  let right:task<i64>=task_spawn(scope,fn()->i64 !{task}{task_yield();return 22;});
  return task_wait(left)+task_wait(right);
 });
 return http::json_response(200,encode_json(Echo(req.user,req.request_id,req.body,n)));
}
server fn reference()->str !{task,fs,throw}{return handle(http::Request("POST","/api/echo","","A🌍\\u0000β","alice","1")).body;}
'''
@contextlib.contextmanager
def server(image,*options,grant='write',workers=4,tls=False):
 global launches
 launches+=1;number=launches
 argv=[image,'--auth',auth,'--database',root/('database-'+str(number)+'.sqlite'),'--port','0','--workers',str(workers),*options]
 if tls:argv+=['--cert',root/'cert.pem','--key',root/'private-key.pem']
 env={**os.environ,'NEX_RESOURCE_DIR':str(root/'absent-resources')}
 for key in ('NEX_FILES_ROOT','NEX_FILES_WRITE','NEX_FILES_LIMIT','NEX_TASK_STEPS','NEX_TASK_TIMEOUT_MS','NEX_TASK_WORKERS'):env.pop(key,None)
 if grant!='none':argv+=['--files-root',str(files)]
 if grant=='write':argv+=['--files-write','1']
 # Ambient task limit variables cannot change explicit compiled/runtime limits.
 env.update(NEX_TASK_STEPS='1',NEX_TASK_TIMEOUT_MS='1',NEX_TASK_WORKERS='1')
 process=subprocess.Popen(list(map(str,argv)),cwd=root,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
 lines=queue.Queue();thread=threading.Thread(target=lambda:lines.put(process.stdout.readline()),daemon=True);thread.start()
 report['state']='server-'+str(number);save();line=''
 try:
  line=lines.get(timeout=20);match=re.fullmatch(r'NEX server (https?)://127\.0\.0\.1:([0-9]+)\n',line)
  require(bool(match) and match.group(1)==('https' if tls else 'http'),('server failed to start',line));yield int(match.group(2))
 finally:
  if process.poll() is None:stop_server(process)
  try:stdout,stderr=process.communicate(timeout=15)
  except subprocess.TimeoutExpired:process.kill();stdout,stderr=process.communicate();raise
  thread.join(timeout=2);(root/('server-'+str(number)+'.stdout')).write_text(line+stdout, newline="\n");(root/('server-'+str(number)+'.stderr')).write_text(stderr, newline="\n")
  report.setdefault('servers',[]).append({'number':number,'argv':list(map(str,argv)),'exit_code':process.returncode,'grant':grant,'TLS':tls});save()
  require(process.returncode==0,('server cleanup failed',process.returncode,stderr));require('E_INTERNAL_LEAK' not in stderr and 'libc++abi' not in stderr,stderr)
def request(port,path,token=None,body=None,method='GET',timeout=5,tls=False):
 connection=http.client.HTTPSConnection('127.0.0.1',port,timeout=timeout,context=ssl.create_default_context(cafile=str(root/'cert.pem'))) if tls else http.client.HTTPConnection('127.0.0.1',port,timeout=timeout)
 headers={}
 if token:headers['Authorization']='Bearer '+token
 payload=None if body is None else body.encode();connection.request(method,path,body=payload,headers=headers)
 try:
  response=connection.getresponse();raw=response.read();value=json.loads(raw);head=dict(response.getheaders());status=response.status
 finally:connection.close()
 report['requests'].append({'path':path,'method':method,'TLS':tls,'input_body':body,'status':status,'response':value,'request_id':head.get('X-Request-Id')})
 return status,value,head
try:
 source=root/'server.nex';source.write_text(SOURCE, newline="\n");auth=root/'private-auth.json'
 (root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.28','entry':'server.nex'})+'\n', newline="\n")
 alice=cli('alice','token','--user','alice','--auth',auth)['token'];bob=cli('bob','token','--user','bob','--auth',auth)['token']
 files=root/'files';files.mkdir();(files/'input').write_text('input 🌍\0β', newline="\n")
 run('TLS-certificate',['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',root/'private-key.pem','-out',root/'cert.pem','-days','1','-subj','/CN=localhost','-addext','subjectAltName=IP:127.0.0.1'])
 reference=cli('reference','eval',source,'--entry','task_http::reference');oracle=json.loads(reference['value'])
 require(oracle=={'user':'alice','request_id':'1','body':'A🌍\0β','answer':'42'},oracle)
 limits=['--task-steps','100000000','--task-timeout-ms','5000','--task-workers','4']
 images=[]
 for profile in ['debug','release']:
  built=cli('build-'+profile,'build',source,'--target','server','--profile',profile,*limits)
  image=Path(built['executable']);metadata=json.loads((image.parent/'build.json').read_text())
  require(built['kind']=='http_server' and metadata['runtime_requirements']['tasks'],metadata)
  require(metadata['task_limits']=={'steps':100000000,'timeout_ms':5000,'workers':4},metadata['task_limits'])
  report['images'].append({'profile':profile,'path':str(image),'sha256':hashlib.sha256(image.read_bytes()).hexdigest(),
   'metadata_sha256':hashlib.sha256((image.parent/'build.json').read_bytes()).hexdigest(),'task_limits':metadata['task_limits']})
  llvm=Path(built['llvm']).read_text()
  require('__task_step' in llvm and not re.search(r'\bcall\b[^\n]*@nex_task_application_execute',llvm) and not re.search(r'^define[^\n]*@main\(',llvm,re.M),'HTTP emitted a standalone task process entry')
  images.append((profile,image))
 for profile,image in images:
  hidden=root/'server.hidden';source.rename(hidden)
  try:
   with server(image,'--nex-task-workers','2') as port:
    require(request(port,'/api/echo')[0]==401,'missing bearer was accepted')
    status,value,headers=request(port,'/api/echo',alice,'A🌍\0β',method='POST');require(status==200,value)
    require({**value,'request_id':'1'}==oracle,value);require(value['request_id']==headers['X-Request-Id'],headers)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
     jobs=[pool.submit(request,port,'/api/echo',alice if i%2==0 else bob,'body-'+str(i)) for i in range(8)]
     results=[job.result() for job in jobs]
    require(len({value['request_id'] for _,value,_ in results})==8,'request IDs crossed')
    for i,(status,value,headers) in enumerate(results):require(status==200 and value['user']==('alice' if i%2==0 else 'bob') and value['body']=='body-'+str(i) and value['answer']=='42' and value['request_id']==headers['X-Request-Id'],value)
    require(request(port,'/api/read',alice)[:2]==(200,'input 🌍\0β'),'task read differs')
    require(request(port,'/api/stream',alice)[:2]==(200,'input 🌍\0β'),'task stream differs')
    require(request(port,'/api/write',alice,'written 🌍\0β',method='POST')[:2]==(200,True),'task write differs')
    require((files/'saved-alice').read_bytes()=='written 🌍\0β'.encode(),'write payload differs')
    require(request(port,'/api/traversal',alice)[0]==403,'task path escaped grant')
    status,value,_=request(port,'/api/trap',alice);require(status==500 and value['error']['code']=='E_DIV_ZERO',value)
    require(request(port,'/api/echo',bob)[0]==200,'trap poisoned next request')
   with server(image,tls=True) as port:
    status,value,headers=request(port,'/api/echo',alice,'A🌍\0β',method='POST',tls=True)
    require(status==200 and {**value,'request_id':'1'}==oracle,value)
    require(value['request_id']==headers['X-Request-Id'],headers)
    status,value,_=request(port,'/api/trap',alice,tls=True);require(status==500 and value['error']['code']=='E_DIV_ZERO',value)
   with server(image,'--budget','100000000','--nex-task-steps','40') as port:
    status,value,_=request(port,'/api/limit',alice);require(status==429 and value['error']['code']=='E_LIMIT',value)
   with server(image,'--budget','100000000','--timeout-ms','60000','--nex-task-timeout-ms','20') as port:
    status,value,_=request(port,'/api/deadline',alice);require(status==504 and value['error']['code']=='E_TIMEOUT',value)
   with server(image,grant='none') as port:
    require(request(port,'/api/echo',alice)[0]==200,'unused fs effect demanded a root')
    require(request(port,'/api/read',alice)[:2]==(403,'CAPABILITY'),'missing read grant was accepted')
   with server(image,grant='read') as port:
    require(request(port,'/api/read',alice)[0]==200,'read grant failed')
    require(request(port,'/api/write',alice,'denied',method='POST')[:2]==(403,'CAPABILITY'),'read-only grant upgraded')
   # A disconnected active task must release the sole HTTP worker before its
   # five-second deadline, including an opened File and completed marker IO.
   marker=files/'started';marker.unlink(missing_ok=True)
   with server(image,'--budget','100000000',workers=1) as port:
    connection=socket.create_connection(('127.0.0.1',port),timeout=3)
    connection.sendall(('GET /api/cancel HTTP/1.1\r\nHost: localhost\r\nAuthorization: Bearer '+alice+'\r\n\r\n').encode())
    try:
     deadline=time.monotonic()+3
     while not marker.exists() and time.monotonic()<deadline:time.sleep(.01)
     require(marker.read_text()=='yes','task never admitted marker IO')
    finally:connection.close()
    require(request(port,'/api/echo',alice,timeout=2)[0]==200,'disconnect failed to release request worker')
   cancel_server=report['servers'][-1];diagnostic=(root/('server-'+str(cancel_server['number'])+'.stderr')).read_text()
   require('E_CANCELLED' in diagnostic,'disconnected task ended without its cancellation diagnostic')
   report['cancel_observations'].append({'profile':profile,'code':'E_CANCELLED','opened_file_and_marker_before_disconnect':True,'sole_HTTP_worker_released_before_deadline':True})
   invalid=[('--nex-task-workers','5'),('--nex-task-steps','100000001'),('--nex-task-timeout-ms','5001'),('--nex-task-workers','0'),('--nex-task-unknown','1'),('--nex-task-steps','1x'),('--nex-task-workers','1','--nex-task-workers','1')]
   for i,options in enumerate(invalid):
    failed=run('invalid-'+profile+'-'+str(i),[image,'--auth',auth,'--database',root/'bad.sqlite',*options],expected=1,timeout=5)
    require(not failed.stdout and 'NEX server:' in failed.stderr,'invalid task limit started a server')
  finally:hidden.rename(source)
 require(hashlib.sha256(compiler.read_bytes()).hexdigest()==report['compiler_sha256'],'compiler changed during HTTP acceptance')
 report.update(ok=True,state='passed',checks=checks,profiles=2,concurrent_requests_each=8,source_absent_execution=True,request_identity_preserved=True,TLS_verified=True,compiler_unchanged=True,
  task_whole_file_and_stream_IO=True,grant_denial_and_path_containment=True,trap_budget_deadline_disconnect_cleanup=True,compiled_limit_ceiling_rejections=14,servers=report['servers'])
except BaseException as error:report.update(state='failed',error=repr(error),traceback=traceback.format_exc());raise
finally:save()
print(json.dumps({k:report[k] for k in ['ok','checks','profiles','concurrent_requests_each','public_HTTP_task_target','async_network_DB_claimed']}))
