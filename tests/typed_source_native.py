from host_fixture import run_native
from host_fixture import exit_code, probe_dll_inputs
import os
import argparse,json,os,platform,re,subprocess,tempfile,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('probe');p.add_argument('--source-root',type=Path,default=Path(__file__).resolve().parents[1]);p.add_argument('--output',type=Path);p.add_argument('--compiler',default=os.environ.get('NEX_CLANG','clang++'));a=p.parse_args()
root=a.source_root.resolve();out=a.output.resolve() if a.output else Path(tempfile.mkdtemp(prefix='nex-typed-source-native-'));out.mkdir(parents=True,exist_ok=a.output is None);probe=str(Path(a.probe).resolve());started=time.monotonic();records=[]
report={'ok':False,'candidate_language':'0.27','public027_enabled':False,'actual_native_execution':True,'cases':records}
def save():report['seconds']=round(time.monotonic()-started,3);(out/'report.json').write_text(json.dumps(report,indent=2)+'\n', newline="\n")
def run(cmd,timeout=120):
 r=run_native(list(map(str,cmd)),text=True,capture_output=True,timeout=timeout)
 if r.returncode:raise AssertionError((list(map(str,cmd)),r.returncode,r.stdout,r.stderr))
 return r
host=out/'host.ll';run([a.compiler,'-x','c','-S','-emit-llvm',os.devnull,'-o',host]);t=host.read_text();triple=re.search(r'target triple = "(.*?)"',t)[1];layout=re.search(r'target datalayout = "(.*?)"',t)[1]
fixtures=re.findall(r'value\(R"\((.*?)\)"(?:,"(.*?)")?\);',(root/'tests/typed_source.cpp').read_text(),re.S);assert len(fixtures)==31
fixtures=[(f'reference-{i:02d}',text,False) for i,(text,_) in enumerate(fixtures)]
fixtures += [
 ('uncaught-int','fn main()->unit !{throw}{throw(42);}',False),
 ('uncaught-record','struct Fault{code:i64;text:str;}fn main()->unit !{throw}{throw(Fault(42,"hidden"));}',False),
 ('rethrow-site','fn main()->unit !{throw}{\ntry{throw(42);}\ncatch(error:i64){throw;}\n}',False),
 ('declined-site','fn main()->unit !{throw}{\ntry{throw(42);}\ncatch(error:i64) if false{}\n}',False),
 ('overflow','fn main()->i64{try{return 9223372036854775807+1;}catch(error:i64){return 0;}catch(c,m){return 1;}}',False),
 ('modules','module app;import "./library.nex" as lib;fn main()->i64{try{lib::fail();return 0;}catch(error:lib::Fault){return error.number;}catch(c,m){return 1;}}',True),
 ('heap-loop','fn main()->i64{var count:i64=0;var result:list<str>=["old"];while count<1000{try{throw(["retained","λ"]);}catch(error:list<str>) if false{assert(false);}catch(error:list<str>){result=error;}count=count+1;}assert(result[0]=="retained"&&result[1]=="λ");return 42;}',False),
 ('nested-finally','fn main()->i64 !{io}{try{try{throw([42]);}finally{try{throw("cleanup");}catch(e:str){print(e);}}}catch(e:list<i64>){return e[0];}}',False),
]
save()
for name,text,project in fixtures:
 d=out/name;d.mkdir();f=d/'main.nex';f.write_text(text if project else 'module typed;\n'+text, newline="\n")
 if project:(d/'library.nex').write_text('module errors;pub struct Fault{number:i64;}pub fn fail()->unit !{throw}{throw(Fault(42));}', newline="\n")
 expected=json.loads(run([probe,'reference',f]).stdout);(d/'reference.json').write_text(json.dumps(expected,indent=2)+'\n', newline="\n")
 for optimization in ['0','2']:
  e=d/('O'+optimization);e.mkdir();run([probe,'emit',f,e,triple,layout,str(optimization=='2').lower()]);lib=e/('program.dylib' if platform.system()=='Darwin' else 'program.so');flags=['-dynamiclib','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else (['-shared',*probe_dll_inputs(probe,out)] if os.name=='nt' else ['-shared','-fPIC']);run([a.compiler,'-O'+optimization,*flags,e/'program.ll','-o',lib])
  actual=run_native([probe,'run',str(lib)],text=True,capture_output=True,timeout=60);(e/'stdout.txt').write_text(actual.stdout, newline="\n");(e/'stderr.txt').write_text(actual.stderr, newline="\n")
  if expected['kind']=='return':
   assert actual.returncode==exit_code(expected['value']),(name,optimization,actual.returncode,actual.stderr)
   assert actual.stdout==expected['output'] and not actual.stderr,(name,actual.stdout,actual.stderr,expected)
  elif expected['kind']=='exception':
   assert actual.returncode==70,(name,actual.returncode,actual.stderr)
   row=next(json.loads(line.split(' ',1)[1]) for line in actual.stderr.splitlines() if line.startswith('NEX_SOURCE_EXCEPTION '))
   for key in ['code','message','line']:assert row[key]==expected[key],(name,key,row,expected)
   assert row['source'] is not None and actual.stdout==expected['output'],(name,row,expected)
   assert 'hidden' not in actual.stderr,(name,'payload entered public diagnostic')
  else:assert actual.returncode==70 and expected['code'] in actual.stderr and 'NEX_SOURCE_EXCEPTION' not in actual.stderr,(name,actual.returncode,actual.stderr,expected)
  records.append({'name':name,'optimization':'O'+optimization,'kind':expected['kind'],'passed':True});save()
report.update(ok=True,comparisons=len(records),physical_Data_retirement_checked_by_host=True,heap_loop_iterations=1000);save();print(json.dumps({'ok':True,'comparisons':len(records),'report':str(out/'report.json')}))
