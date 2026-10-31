"""Observable scalar Wasm027 execution, checked arithmetic and retained026 control."""
from pathlib import Path
import argparse,ast,hashlib,json,os,shutil,subprocess,tempfile,time
parser=argparse.ArgumentParser();parser.add_argument('probe',type=Path);parser.add_argument('--source-root',type=Path,default=Path(__file__).resolve().parents[1]);parser.add_argument('--resources',type=Path);parser.add_argument('--output',type=Path)
args=parser.parse_args();probe=args.probe.resolve();W=args.source_root.resolve();O=args.output.resolve() if args.output else Path(tempfile.mkdtemp(prefix='nex-typed-scalar-wasm-'));O.mkdir(parents=True,exist_ok=args.output is None)
env={**os.environ,'NEX_RESOURCE_DIR':str(args.resources.resolve() if args.resources else W)}
report={'ok':False,'scope':'explicit027 scalar Wasm with retained026 and independent reference checks','ordinary_CLI_acceptance_tested':False,'cases':[],'commands':[]}
def save():(O/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n', newline="\n")
def run(label,argv,code=0):
 r=subprocess.run(list(map(str,argv)),env=env,text=True,capture_output=True,timeout=180);(O/(label+'.stdout')).write_text(r.stdout, newline="\n");(O/(label+'.stderr')).write_text(r.stderr, newline="\n");report['commands'].append({'label':label,'exit':r.returncode});save();assert r.returncode==code,(label,r.stdout[-3500:],r.stderr[-3000:]);return r
def build(label,probe,source,language,profile='release',entry='compute',error=None):
 value=json.loads(run(label,[probe,source,language,entry,profile,O/(label+'-cache'),'build'],1 if error else 0).stdout)
 if error:assert value['code']==error,(label,value)
 else:
  assert not value['cached'];metadata=json.loads(Path(value['descriptor']).read_text()) if 'descriptor' in value else json.loads((Path(value['directory'])/'module.json').read_text());assert metadata['language']==language
 return value
tree=ast.parse((W/'tests/wasm.py').read_text());original=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='SOURCE' for t in n.targets))
cases=[([0,9007199254740993,7],9007199254741000,None),([0,9223372036854775807,1],None,'E_OVERFLOW'),([1,-9223372036854775808,1],None,'E_OVERFLOW'),([2,3,-7],-21,None),([2,9223372036854775807,2],None,'E_OVERFLOW'),([3,-7,3],-2,None),([3,-9223372036854775808,-1],None,'E_OVERFLOW'),([3,1,0],None,'E_DIV_ZERO'),([4,-9223372036854775808,-1],0,None),([4,-7,3],-1,None),([5,-9223372036854775808,0],None,'E_OVERFLOW'),([6,7,7],0,None),([6,1,2],None,'E_ASSERT'),([7,0,0],None,'E_DIV_ZERO'),([8,42,0],42,None),([9,-3,7],-21,None),([10,9223372036854775807,0],9223372036854775807,None),([11,15,0],15,None)]
checks=''.join('assert(compute('+','.join(map(str,args))+')=='+str(value)+');' for args,value,error in cases if error is None)
root=O/'project';root.mkdir();source=root/'main.nex';source.write_text(original+'\nfn main()->unit !{io}{'+checks+'print(42);}\n', newline="\n")
kept=build('retained026-control',probe,source,'0.26')
source027=root/'typed.nex';source027.write_text(source.read_text()+'\nfn unused_typed_error()->unit !{throw}{throw(42);}\n', newline="\n")
observed=json.loads(run('reference027',[probe,source027,'0.27','main','release',O/'reference','reference']).stdout);assert observed['stdout']=='42\n'
def node(label,result,entry='compute'):
 driver=O/(label+'.mjs');driver.write_text('import assert from "node:assert/strict";import fs from "node:fs";import {createNexWasm,descriptor} from '+json.dumps(Path(result['wrapper']).as_uri())+';const instance=await createNexWasm(fs.readFileSync('+json.dumps(result['module'])+'));\n'+('''const cases=CASES;let passed=0;
for(const row of cases){const args=row.args.map(BigInt);if(row.code){assert.throws(()=>instance.call(args),e=>e.code===row.code);}else assert.equal(instance.call(args),BigInt(row.value));++passed;}
assert.throws(()=>instance.call([0,1,2]),e=>e.code==='E_WASM_INPUT');
process.stdout.write(JSON.stringify({ok:true,cases:passed+1,language:descriptor.language})+'\\n');
'''.replace('CASES',json.dumps([{'args':list(map(str,args)),'value':str(value) if value is not None else None,'code':error} for args,value,error in cases])) if entry=='compute' else '''assert.equal(instance.call([true]),false);assert.equal(instance.call([false]),true);process.stdout.write(JSON.stringify({ok:true,cases:2})+'\\n');'''), newline="\n")
 value=json.loads(run(label,[os.environ.get('NEX_NODE','node'),driver]).stdout);assert value['ok'];report['cases'].append({'label':label,'actual_Node_Wasm_checks':value['cases'],'passed':True});save();return value['cases']
count=node('retained026',kept)
for profile in ['debug','release']:
 built=build('typed027-'+profile,probe,source027,'0.27',profile);count+=node('typed027-'+profile,built)
 assert b'WASM_SERVER_SECRET_EXCLUDED_060' not in Path(built['module']).read_bytes()
 assert b'unused_typed_error' not in Path(built['module']).read_bytes()
boolean=build('typed027-bool',probe,source027,'0.27','release','invert');count+=node('typed027-bool',boolean,'invert')
for label,text,error in [('caught-typed','fn compute()->i64{try{throw(42);}catch(e:i64){return e;}catch(c,m){return 0;}}','E_EXCEPTION_BACKEND'),('uncaught-typed','fn compute()->i64 !{throw}{throw(42);}','E_WASM_REALM'),('finally','fn compute()->i64{try{return 42;}finally{}}','E_WASM_TYPE'),('float','fn compute()->f64{return 1.5;}','E_WASM_TYPE')]:
 bad=root/(label+'.nex');bad.write_text("module negative;"+text, newline="\n");build(label,probe,bad,'0.27',error=error);report['cases'].append({'rejection':label,'code':error,'passed':True});save()
report.update(ok=True,actual_Wasm_Node_checks=count,source_language027_selected_explicitly=True,reference027_assertions_passed=True,source_errors_and_finally_still_rejected=True,goal_complete=False);save();print(json.dumps({'ok':True,'actual_Wasm_Node_checks':count,'rejected_cases':4,'report':str(O/'report.json')}),flush=True)

if not args.output:shutil.rmtree(O)
