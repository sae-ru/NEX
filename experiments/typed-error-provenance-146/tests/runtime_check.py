from pathlib import Path
import json,subprocess,os
D=Path(__file__).resolve().parents[1];out=D/'runtime-evidence-v3';out.mkdir(exist_ok=False);(out/'input').write_bytes(b'abc')
old=json.loads((D/'evidence-v1/report.json').read_text());cases=[(r['name'],(D/'evidence-v1'/(r['name']+'.nex')).read_text(),r['expected']=='E_TASK_LIFETIME') for r in old['cases']]
cases += [
 ('unobserved-inner-channel','''module runtime;fn main()->unit !{task,throw}{with_tasks(1,fn(s:task_scope)->unit !{task}{task_spawn(s,fn()->unit !{task,throw}{throw(channel_new<i64>(s,1));});});}''',True),
 ('observed-inner-channel','''module runtime;fn main()->i64 !{task,throw}{return with_tasks(1,fn(s:task_scope)->i64 !{task,throw}{let failed:task<i64>=task_spawn(s,fn()->i64 !{task,throw}{throw(channel_new<i64>(s,1));});try{task_wait(failed);}catch(q:channel<i64>){assert(task_send(q,42));return unwrap(task_recv(q));}return 0;});}''',False),
 ('same-scope-value','''module runtime;fn main()->i64 !{task,throw}{return with_tasks(1,fn(s:task_scope)->i64 !{task}{try{throw(s);}catch(owner:task_scope){let q:channel<i64>=channel_new<i64>(owner,1);assert(task_send(q,42));return unwrap(task_recv(q));}});}''',False),
 ('owned-file-error','''module runtime;server fn main()->i64 !{task,fs,throw}{try{with_tasks(1,server fn(s:task_scope)->unit !{task,fs,throw}{let f:file=unwrap(file_open_read("input"));throw(f);});}catch(f:file){assert(len(unwrap(file_read(f,1)))==1);assert(file_close(f));return 42;}catch(c,m){return 0;}return 0;}''',False),
 ('unobserved-file-error','''module runtime;server fn main()->i64 !{task,fs,throw}{try{with_tasks(1,server fn(s:task_scope)->unit !{task,fs}{task_spawn(s,server fn()->unit !{task,fs,throw}{let f:file=unwrap(file_open_read("input"));throw(f);});});}catch(f:file){assert(len(unwrap(file_read(f,1)))==1);assert(file_close(f));return 42;}catch(c,m){return 0;}return 0;}''',False),
]
cases += [
 ('bounded-type-join',(D/'tests/bounded-types.nex').read_text(),False),
 ('aliased-owned-file-error','module runtime;struct Problem{first:file;second:file;}server fn main()->i64 !{task,fs,throw}{try{with_tasks(1,server fn(s:task_scope)->unit !{task,fs,throw}{let f:file=unwrap(file_open_read("input"));throw(Problem(f,f));});}catch(e:Problem){assert(file_is_open(e.first));assert(file_close(e.first));assert(!file_is_open(e.second));return 42;}catch(c,m){return 0;}return 0;}',False),
]
rows=[]
for name,text,reject in cases:
 f=out/(name+'.nex');f.write_text(text);values=[]
 for mode in ['ast','ir']:
  r=subprocess.run([D/'probe',f,mode],cwd=out,env={**os.environ,'NEX_FILES_ROOT':str(out)},text=True,capture_output=True,timeout=60);(out/(name+'-'+mode+'.stdout')).write_text(r.stdout);(out/(name+'-'+mode+'.stderr')).write_text(r.stderr)
  try:v=json.loads(r.stdout)
  except ValueError:v={'kind':'process_failure','code':r.returncode,'stderr':r.stderr}
  if reject:okay=v.get('kind')=='trap' and v.get('code')=='E_TASK_SCOPE'
  elif name=='retained145-uncaught':okay=v.get('kind')=='exception' and v.get('typed') is True
  elif name.startswith('retained145-fatal'):okay=v.get('kind')=='trap' and v.get('code')==('E_ASSERT' if name.endswith('fatal-filter') else 'E_OVERFLOW')
  else:okay=v.get('kind')=='return' and v.get('value') in (None,42)
  rows.append({'name':name,'mode':mode,'passed':okay and r.returncode==0,'observed':v});values.append(v)
 if values[0]!=values[1]:rows.append({'name':name,'mode':'comparison','passed':False,'observed':values})
report={'ok':all(r['passed'] for r in rows),'programs':len(cases),'executions':len(rows),'cases':rows,'scope':'isolated reference/TaskIR prototype; native/TS transfer protocol remains pending','public027_enabled':False};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({**{k:report[k] for k in ['ok','programs','executions','scope']},'failures':[r for r in rows if not r['passed']]}));raise SystemExit(not report['ok'])
