from pathlib import Path
import ast,json,subprocess,os
D=Path(__file__).resolve().parents[1];W=Path(os.environ.get('NEX_DRAFT_SOURCE_ROOT',D.parents[1]));out=D/os.environ.get('NEX_DRAFT_EVIDENCE','evidence-v1');out.mkdir(exist_ok=False);cases=[]
def case(name,source,reject=False):cases.append((name,source,'E_TASK_LIFETIME' if reject else None))
case('local-channel',r'''fn main()->i64 !{task,throw}{return with_tasks(1,fn(s:task_scope)->i64 !{task}{try{throw(channel_new<i64>(s,1));}catch(q:channel<i64>){assert(task_send(q,42));return unwrap(task_recv(q));}});}''')
case('channel-scope-error',r'''fn main()->unit !{task,throw}{with_tasks(1,fn(s:task_scope)->unit !{task,throw}{throw(channel_new<i64>(s,1));});}''',True)
case('helper-error',r'''fn fail(q:channel<i64>)->unit !{throw}{throw(q);}fn main()->unit !{task,throw}{with_tasks(1,fn(s:task_scope)->unit !{task,throw}{fail(channel_new<i64>(s,1));});}''',True)
case('borrowed-outer',r'''fn main()->i64 !{task,throw}{return with_tasks(1,fn(outer:task_scope)->i64 !{task,throw}{let q:channel<i64>=channel_new<i64>(outer,1);try{with_tasks(1,fn(inner:task_scope)->unit !{throw}{throw(q);});}catch(e:channel<i64>){assert(task_send(e,42));return unwrap(task_recv(e));}catch(c,m){return 0;}return 0;});}''')
case('catch-return',r'''fn main()->unit !{task,throw}{with_tasks(1,fn(outer:task_scope)->unit !{task,throw}{let leaked:channel<i64>=with_tasks(1,fn(inner:task_scope)->channel<i64> !{task}{try{throw(channel_new<i64>(inner,1));}catch(q:channel<i64>){return q;}});});}''',True)
for field,reject in [('outer',False),('inner',True)]:
 case('projection-'+field,'''struct Pair{outer:channel<i64>;inner:channel<i64>;}fn main()->unit !{task,throw}{with_tasks(1,fn(outer:task_scope)->unit !{task,throw}{let safe:channel<i64>=channel_new<i64>(outer,1);let selected:channel<i64>=with_tasks(1,fn(inner:task_scope)->channel<i64> !{task}{try{throw(Pair(safe,channel_new<i64>(inner,1)));}catch(e:Pair){return e.FIELD;}});});}'''.replace('FIELD',field),reject)
case('local-closure',r'''fn main()->i64 !{task,throw}{return with_tasks(1,fn(s:task_scope)->i64 !{task}{let q:channel<i64>=channel_new<i64>(s,1);try{throw(fn()->i64 !{task}{assert(task_send(q,42));return unwrap(task_recv(q));});}catch(f:fn()->i64 !{task}){return f();}});}''')
case('closure-scope-error',r'''fn main()->unit !{task,throw}{with_tasks(1,fn(s:task_scope)->unit !{task,throw}{let q:channel<i64>=channel_new<i64>(s,1);throw(fn()->bool !{task}{return task_close(q);});});}''',True)
case('legacy-rethrow',r'''fn main()->unit !{task,throw}{with_tasks(1,fn(s:task_scope)->unit !{task,throw}{try{throw(channel_new<i64>(s,1));}catch(c,m){throw;}});}''',True)
case('filter-decline',r'''fn no()->bool{return false;}fn main()->unit !{task,throw}{with_tasks(1,fn(s:task_scope)->unit !{task,throw}{try{throw(channel_new<i64>(s,1));}catch(q:channel<i64>) if no(){return;}});}''',True)
case('predicate-replacement',r'''fn replace()->bool !{throw}{throw(42);}fn main()->i64 !{task,throw}{try{return with_tasks(1,fn(s:task_scope)->i64 !{task,throw}{try{throw(channel_new<i64>(s,1));}catch(q:channel<i64>) if replace(){return 0;}catch(i:i64){return 0;}});}catch(i:i64){return i;}catch(c,m){return 0;}}''')
case('finally-return-override',r'''fn main()->i64 !{task,throw}{return with_tasks(1,fn(s:task_scope)->i64 !{task,throw}{try{throw(channel_new<i64>(s,1));}finally{task_yield();return 42;}});}''')
case('finally-error-override',r'''fn main()->i64 !{task,throw}{try{return with_tasks(1,fn(s:task_scope)->i64 !{task,throw}{try{throw(channel_new<i64>(s,1));}finally{task_yield();throw(42);}});}catch(e:i64){return e;}catch(c,m){return 0;}}''')
case('finally-lexical-rethrow',r'''fn main()->unit !{task,throw}{with_tasks(1,fn(s:task_scope)->unit !{task,throw}{try{throw(channel_new<i64>(s,1));}catch(q:channel<i64>){try{throw(42);}finally{throw;}}});}''',True)
for owner,reject in [('outer',False),('inner',True)]:
 case('future-'+owner,'''fn main()->unit !{task,throw}{with_tasks(1,fn(outer:task_scope)->unit !{task,throw}{let selected:channel<i64>=with_tasks(1,fn(inner:task_scope)->channel<i64> !{task,throw}{let child:task<i64>=task_spawn(inner,fn()->i64 !{task,throw}{throw(channel_new<i64>(OWNER,1));});try{task_wait(child);}catch(q:channel<i64>){return q;}catch(c,m){return channel_new<i64>(outer,1);}return channel_new<i64>(outer,1);});});}'''.replace('OWNER',owner),reject)
case('wrong-type-clause-unreachable',r'''fn main()->unit !{task,throw}{with_tasks(1,fn(outer:task_scope)->unit !{task,throw}{let selected:channel<i64>=with_tasks(1,fn(inner:task_scope)->channel<i64> !{task}{try{throw(42);}catch(q:channel<i64>){return channel_new<i64>(inner,1);}catch(i:i64){return channel_new<i64>(outer,1);}});});}''')
case('handler-replacement',r'''fn main()->i64 !{task,throw}{try{return with_tasks(1,fn(s:task_scope)->i64 !{task,throw}{try{throw(channel_new<i64>(s,1));}catch(q:channel<i64>){throw(42);}catch(i:i64){return 0;}});}catch(i:i64){return i;}catch(c,m){return 0;}}''')
case('scope-value',r'''fn main()->unit !{task,throw}{with_tasks(1,fn(s:task_scope)->unit !{throw}{throw(s);});}''',True)
# Keep the full ordinary-data task corpus accepted by the source checker.
t=ast.parse((W/'tests/typed_source_tasks.py').read_text());node=next(n for n in t.body if isinstance(n,ast.Assign) and any(isinstance(x,ast.Name) and x.id=='cases' for x in n.targets))
for name,text in ast.literal_eval(node.value):case('retained145-'+name,text)
rows=[]
for name,text,expected in cases:
 f=out/(name+'.nex');f.write_text('module provenance;\n'+text);r=subprocess.run([D/'probe',f],text=True,capture_output=True);(out/(name+'.stdout')).write_text(r.stdout);(out/(name+'.stderr')).write_text(r.stderr)
 try:v=json.loads(r.stdout)
 except ValueError:v={'code':'PROCESS_FAILURE','stderr':r.stderr,'stdout':r.stdout}
 okay=r.returncode==0 and v.get('ok') is True if expected is None else r.returncode==1 and v.get('code')==expected
 rows.append({'name':name,'expected':expected or 'accepted','passed':okay,'observed':v})
report={'ok':all(r['passed'] for r in rows),'cases':rows,'count':len(rows),'accepted':sum(r['expected']=='accepted' for r in rows),'rejected':sum(r['expected']!='accepted' for r in rows),'scope':'isolated static provenance only; no runtime authority capability enabled'};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({**{k:report[k] for k in ['ok','count','accepted','rejected','scope']},'failures':[r for r in rows if not r['passed']]}))
raise SystemExit(not report['ok'])
