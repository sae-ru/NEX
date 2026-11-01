#!/usr/bin/env python3
"""Ordinary private native/reference semantic comparisons; no public025 claim."""
from host_fixture import run_native
from host_fixture import exit_code, probe_dll_inputs
import os
import argparse,json,os,pathlib,platform,re,subprocess,tempfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('probe');p.add_argument('compiler');p.add_argument('--output');a=p.parse_args()
out=pathlib.Path(a.output or os.environ.get('NEX_EXCEPTION_NATIVE_OUTPUT') or tempfile.mkdtemp(prefix='nex-exception-native-')).resolve();out.mkdir(parents=True,exist_ok=True)
probe=str(pathlib.Path(a.probe).resolve());compiler=a.compiler

def run(cmd,**kw):
 r=run_native(cmd,text=True,capture_output=True,timeout=120,**kw)
 if r.returncode:raise RuntimeError(str(cmd)+'\n'+r.stdout+'\n'+r.stderr)
 return r
layout=out/'host.ll';run([compiler,'-x','c','-S','-emit-llvm',os.devnull,'-o',str(layout)])
text=layout.read_text();triple=re.search(r'target triple = "(.*?)"',text)[1];datalayout=re.search(r'target datalayout = "(.*?)"',text)[1]
cases=[
 ('catch', 'fn main()->i64{try{throw("USER","data");}catch(code,message){assert(code=="USER"&&message=="data");return 42;}}'),
 ('nul', 'fn main()->i64{try{throw("U\\u0000SER","start\\u0000end");}catch(code,message){assert(len(code)==5&&len(message)==9);return 42;}}'),
 ('direct', 'fn leaf()->i64 !{throw}{throw("USER","leaf");}fn main()->i64{try{return leaf();}catch(code,message){return len(code)+len(message)+34;}}'),
 ('generic', 'fn leaf<T:integer>(v:T)->T !{throw}{throw("GENERIC",str(v));}fn main()->i64{try{return leaf(99);}catch(code,message){assert(message=="99");return 42;}}'),
 ('rethrow', 'fn main()->i64{try{try{throw("FIRST","data");}catch(code,message){throw;}}catch(code,message){assert(code=="FIRST"&&message=="data");return 42;}}'),
 ('replace', 'fn main()->i64{try{try{throw("FIRST","data");}catch(code,message){throw("SECOND",message+"!");}}catch(code,message){assert(code=="SECOND"&&message=="data!");return 42;}}'),
 ('lambda', 'fn main()->i64{let cb:fn()->i64 !{throw}=fn()->i64 !{throw}{throw("LAMBDA","x");};try{return cb();}catch(code,message){assert(code=="LAMBDA");return 42;}}'),
 ('named-bridge', 'fn leaf(v:i64)->str !{throw}{if v==0{throw("NAMED","x");}return str(v);}fn main()->i64{let cb:fn(i64)->str !{throw}=leaf;try{assert(cb(7)=="7");let v:str=cb(0);return len(v);}catch(code,message){return 42;}}'),
 ('outer-assignment', 'fn main()->i64{var values:list<str>=["old"];try{values=["new","kept"];let temp:list<str>=["discard"];throw("USER","x");}catch(code,message){assert(values[0]=="new"&&values[1]=="kept");}return 42;}'),
 ('catch-capture', 'fn main()->i64{var cb:fn()->str=fn()->str{return "old";};try{throw("USER","captured");}catch(code,message){cb=fn()->str{return code+":"+message;};}assert(cb()=="USER:captured");return 42;}'),
 ('try-capture', 'fn main()->i64{var cb:fn()->str=fn()->str{return "old";};try{let value:str="retained";cb=fn()->str{return value;};throw("USER","x");}catch(code,message){}assert(cb()=="retained");return 42;}'),
 ('partial-list', 'fn fail()->str !{throw}{throw("LIST","x");}fn main()->i64{try{let values:list<str>=["allocated",fail()];return len(values);}catch(code,message){return 42;}}'),
 ('partial-argument', 'fn fail()->str !{throw}{throw("ARG","x");}fn join(a:str,b:str)->str{return a+b;}fn main()->i64{try{let v:str=join("allocated",fail());return len(v);}catch(code,message){return 42;}}'),
 ('partial-error', 'fn fail()->str !{throw}{throw("SECOND","payload");}fn main()->i64{try{throw("temporary",fail());}catch(code,message){assert(code=="SECOND");return 42;}}'),
 ('match', 'fn main()->i64{try{match ok(1){ok(v)=>{let temp:list<str>=["a","b"];throw("MATCH",str(v));}err(code,message)=>{throw(code,message);}}}catch(code,message){assert(code=="MATCH"&&message=="1");return 42;}}'),
 ('result', 'fn early()->result<i64>{try{let n:i64=err<i64>("RESULT","unchanged")?;return ok(n);}catch(code,message){return ok(0);}}fn main()->i64{let v:result<i64>=early();assert(!is_ok(v)&&error_code(v)=="RESULT");return 42;}'),
 ('nested-return', 'fn value()->list<str>{try{try{return ["kept","return"];}catch(code,message){return ["inner"];}}catch(code,message){return ["outer"];}}fn main()->i64{let v:list<str>=value();assert(v[0]=="kept"&&v[1]=="return");return 42;}'),
 ('success', 'fn maybe(v:i64)->str !{throw}{if v==0{throw("ZERO","x");}return str(v);}fn main()->i64{var output:str="old";try{output=maybe(42);}catch(code,message){return 0;}assert(output=="42");return 42;}'),
 ('loop', 'fn main()->i64{var count:i64=0;var text:str="old";while count<1000{try{let v:list<str>=["loop"];text=v[0];throw("ITER",str(count));}catch(code,message){assert(code=="ITER");}count=count+1;}assert(text=="loop");return 42;}'),
 ('recursive', 'fn depth(n:i64)->i64 !{throw}{let temp:list<str>=[str(n)];if n==0{throw("DEEP",temp[0]);}return depth(n-1);}fn main()->i64{try{return depth(40);}catch(code,message){assert(code=="DEEP"&&message=="0");return 42;}}'),
 ('shadow', 'fn main()->i64{let code:str="outer";try{let code:str="inner";throw("USER",code);}catch(code,message){assert(code=="USER"&&message=="inner");}assert(code=="outer");return 42;}'),
 ('nonthrowing-try', 'fn main()->i64{try{let text:str="normal";assert(text=="normal");}catch(code,message){return 0;}return 42;}'),
 ('unit', 'fn leaf()->unit !{throw}{throw("UNIT","x");}fn main()->unit{try{leaf();}catch(code,message){assert(code=="UNIT");}}'),
 ('float-bool', 'fn number()->f64 !{throw}{throw("FLOAT","x");}fn flag()->bool !{throw}{throw("BOOL","x");}fn main()->i64{try{let n:f64=number();return 0;}catch(code,message){assert(code=="FLOAT");}try{let b:bool=flag();return 0;}catch(code,message){assert(code=="BOOL");}return 42;}'),
 ('uncaught-order', 'fn part(v:str)->str !{io}{print(v);return v;}fn main()->unit !{io,throw}{throw(part("code"),part("message"));}'),
 ('uncaught-rethrow', 'fn leaf()->i64 !{throw}{\nthrow("ORIGINAL","payload");\n}\nfn main()->i64 !{throw}{\ntry{return leaf();}catch(code,message){\nthrow;\n}\n}'),
 ('uncaught-nul', 'fn main()->unit !{throw}{throw("A\\u0000B","C\\u0000D");}'),
 ('assert-trap', 'fn main()->i64{try{let v:list<str>=["alive"];assert(false);return 1;}catch(code,message){return 0;}}'),
 ('divide-trap', 'fn main()->i64{try{let n:i64=1/0;return n;}catch(code,message){return 0;}}'),
 ('overflow-trap', 'fn main()->i64{try{let n:i64=9223372036854775807+1;return n;}catch(code,message){return 0;}}'),
 ('catch-outer-rethrow', 'fn main()->i64{try{throw("OUTER","first");}catch(code,message){try{try{throw("INNER","second");}catch(code,message){throw;}}catch(code,message){assert(code=="INNER");}try{throw;}catch(code,message){assert(code=="OUTER"&&message=="first");return 42;}}}'),
 ('short-circuit', 'fn fail()->bool !{throw}{throw("BAD","not called");}fn main()->i64{try{assert(!(false&&fail()));assert(true||fail());}catch(code,message){return 0;}return 42;}'),
 ('call-argument-order', 'fn part(v:str)->str !{io}{print(v);return v;}fn fail()->str !{throw}{throw("STOP","second");}fn join(a:str,b:str,c:str)->str{return a+b+c;}fn main()->i64 !{io}{try{let value:str=join(part("first"),fail(),part("third"));return 0;}catch(code,message){assert(code=="STOP");return 42;}}'),
 ('aggregate-immutable', 'struct Pair{left:list<str>;right:str;}fn main()->i64{var result:Pair=Pair(["old"],"initial");try{let values:list<str>=["snapshot"];result=Pair(values,"retained");throw("USER","x");}catch(code,message){assert(result.left[0]=="snapshot"&&result.right=="retained");}return 42;}'),
 ('unicode', 'fn main()->i64{try{throw("Я🧠","λ\\u0000🙂");}catch(code,message){assert(len(code)==2&&len(message)==3);assert(code[1]=="🧠"&&message[2]=="🙂");return 42;}}'),
]
report={'ok':False,'public_language':'0.24','private_language':'0.25-prototype','platform':platform.platform(),'cases':[],'ordinary_functional_only':True,'public_build_supported':False,'security_checks_deferred_by_user':True}
(out/'report.json').write_text(json.dumps(report,indent=2)+'\n', newline="\n")
for name,source in cases:
 d=out/(('case-'+name) if os.name=='nt' and name.upper()=='NUL' else name);d.mkdir(exist_ok=True)
 # Explicit project boundary: neither the probe nor later CLI helpers may select an ancestor graph.
 (d/'nex.json').write_text(json.dumps({'language':'0.24','entry':'main.nex'}), newline="\n")
 f=d/'main.nex';f.write_text('module native_exception;\n'+source.replace('\\\\u','\\u')+'\n', newline="\n")
 reference=json.loads(run([probe,'reference',str(f)]).stdout);(d/'reference.json').write_text(json.dumps(reference,indent=2)+'\n', newline="\n")
 for optimization in ['0','2']:
  e=d/('O'+optimization);e.mkdir(exist_ok=True)
  run([probe,'emit',str(f),str(e),triple,datalayout,str(optimization=='2').lower()])
  library=e/('program.dylib' if platform.system()=='Darwin' else 'program.so')
  flags=['-dynamiclib','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else (['-shared',*probe_dll_inputs(probe,out)] if os.name=='nt' else ['-shared','-fPIC'])
  run([compiler,'-O'+optimization,*flags,str(e/'program.ll'),'-o',str(library)])
  result=run_native([probe,'run',str(library)],text=True,capture_output=True,timeout=30)
  (e/'stdout.txt').write_text(result.stdout, newline="\n");(e/'stderr.txt').write_text(result.stderr, newline="\n")
  if reference['kind']=='return':
   assert result.returncode==exit_code(reference['value']),(name,optimization,result.returncode,result.stderr)
   assert result.stdout==reference['output'],(name,'output',result.stdout,reference)
   assert not result.stderr,(name,'stderr',result.stderr)
  elif reference['kind']=='exception':
   assert result.returncode==70,(name,result.returncode,result.stderr)
   record=next(json.loads(l.split(' ',1)[1]) for l in result.stderr.splitlines() if l.startswith('NEX_SOURCE_EXCEPTION '))
   for k in ['code','message','line']:assert record[k]==reference[k],(name,k,record,reference)
   assert result.stdout==reference['output'],(name,'output',result.stdout,reference)
   assert record['source'] is not None,(name,'source metadata absent')
  else:
   assert result.returncode==70 and reference['code'] in result.stderr,(name,result.returncode,result.stderr,reference)
   assert 'NEX_SOURCE_EXCEPTION' not in result.stderr,(name,'trap caught as source error')
  report['cases'].append({'name':name,'optimization':'O'+optimization,'reference':reference['kind'],'exit_code':result.returncode,'passed':True})
  (out/'report.json').write_text(json.dumps(report,indent=2)+'\n', newline="\n")
d=out/'parallel-stage';d.mkdir(exist_ok=True);(d/'nex.json').write_text(json.dumps({'language':'0.24','entry':'main.nex'}), newline="\n")
f=d/'main.nex';f.write_text('module parallel_stage;fn main()->i64{let values:list<i64>=parallel_map([1],fn(v:i64)->i64{return v;},2);return values[0];}', newline="\n")
rejected=run_native([probe,'emit',str(f),str(d),triple,datalayout,'false'],text=True,capture_output=True,timeout=30)
(d/'stderr.txt').write_text(rejected.stderr, newline="\n")
assert rejected.returncode==1 and 'E_EXCEPTION_STAGE' in rejected.stderr,('parallel-stage',rejected.returncode,rejected.stderr)
report['rejections']=[{'name':'parallel-stage','code':'E_EXCEPTION_STAGE','passed':True}]
report['ok']=True;report['comparisons']=len(report['cases']);(out/'report.json').write_text(json.dumps(report,indent=2)+'\n', newline="\n");print(json.dumps({'ok':True,'comparisons':len(report['cases']),'report':str(out/'report.json')}))
