#!/usr/bin/env python3
"""Observable source-model contract tests; no accelerator/runtime is simulated."""
import argparse,base64,hashlib,json,os,random,shutil,struct,subprocess,time,tempfile
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--compiler',required=True,type=Path);p.add_argument('--resources',required=True,type=Path);p.add_argument('--output',type=Path);a=p.parse_args()
origin=Path(__file__).resolve().parent;out=a.output.absolute() if a.output else Path(tempfile.mkdtemp(prefix='nex-model-contract-'));
if a.output:out.mkdir(exist_ok=False)
compiler=a.compiler.resolve(strict=True);env={**os.environ,'NEX_RESOURCE_DIR':str(a.resources.resolve(strict=True)),'PYTHONDONTWRITEBYTECODE':'1'}
language=json.loads(subprocess.check_output([str(compiler),'describe','--json'],cwd=out,env=env,text=True))['version'];assert language=='0.25'
report={'schema':'nex.model-contract/1','ok':False,'hardware_executed':False,'commands':[],'cases':[],'compiler_sha256':hashlib.sha256(compiler.read_bytes()).hexdigest(),'library_sha256':hashlib.sha256((a.resources/'lib/model.nex').read_bytes()).hexdigest()};start=time.monotonic()
def save():report['seconds']=round(time.monotonic()-start,3);(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
def project(name,body):
 root=out/name;root.mkdir();(root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':language,'entry':'main.nex'})+'\n');(root/'main.nex').write_text('module model_contract;import "std/model.nex" as m;import "std/compute.nex" as c;\n'+body);return root
def cli(root,name,args,code=None):
 command=[str(compiler),*map(str,args),'--json'];r=subprocess.run(command,cwd=root,env=env,capture_output=True,text=True,timeout=300);(root/(name+'.stdout')).write_text(r.stdout);(root/(name+'.stderr')).write_text(r.stderr);report['commands'].append({'case':root.name,'name':name,'command':command,'exit_code':r.returncode});save();d=json.loads(r.stdout)
 if code:assert r.returncode!=0 and d.get('code')==code,(name,d)
 else:assert r.returncode==0,(name,r.stdout[-3000:],r.stderr[-3000:])
 return d
def agree(root,expected):
 assert cli(root,'reference',['eval'])['stdout']==expected
 for mode in ['debug','release']:assert cli(root,'native-'+mode,['run','--profile',mode])['stdout']==expected
 emitted=root/'ts';cli(root,'emit',['emit','--kind','typescript','--directory',emitted]);(emitted/'package.json').write_text('{"type":"module"}');(emitted/'run.ts').write_text("import {entry} from './program.ts';entry();")
 r=subprocess.run([env.get('NEX_NODE','node'),'--experimental-strip-types','--no-warnings',str(emitted/'run.ts')],env=env,capture_output=True,text=True,timeout=60);(root/'typescript.stdout').write_text(r.stdout);(root/'typescript.stderr').write_text(r.stderr);assert r.returncode==0 and r.stdout==expected,(r.returncode,r.stdout,r.stderr)
 cli(root,'native-tests',['test','--profile','release']);cli(root,'web-tests',['test','--target','web'])

sha='a'*64
setup='''
fn definition()->m::Model{return m::Model("identity","@SHA@",m::Precision::MatchCPU(),[m::Port("X",m::DType::F32(),[2])],[m::Port("Y",m::DType::F32(),[2])]);}
fn device(kind:c::Kind,id:str)->m::Device{return m::Device(kind,id,"controlled.test","1","source contract test; no hardware",[definition()]);}
fn job(kind:c::Kind,fallback:c::Fallback)->m::Request{return m::request("job",definition(),[unwrap(m::from_exact_i32("X",[2],[3,-7]))],c::Selection(kind,""),fallback);}
server fn echo(job:m::Request,d:m::Device)->result<m::Response>!{ffi}{return ok(m::Response(1,job.id,job.model.sha256,job.model.precision,[m::Tensor("Y",m::DType::F32(),[2],job.inputs[0].data)],d,false,""));}
server fn never(job:m::Request,d:m::Device)->result<m::Response>!{ffi}{assert(false);return err("E_TEST","must not invoke");}
'''.replace('@SHA@',sha)
try:
 discovery=project('discovery','fn main()->unit{}');descriptor=cli(discovery,'descriptor',['describe','--field','model'])['value'];pack=json.loads((a.resources/'llm/language-pack.json').read_text());assert descriptor==pack['model'] and descriptor['source_support'] and not descriptor['builtin_cpu_inference'];assert cli(discovery,'guide',['guide','--kind','model'])['text']==(a.resources/'docs/models.md').read_text();report['cases'].append({'name':'installed-contract-discovery'})
 rng=random.Random(133);values=[0,1,-1,16777216,-16777216]
 for e in range(24):values.extend([2**e,-(2**e),2**e-1,-(2**e-1)])
 values += [rng.randint(-16777216,16777216) for _ in range(256)]
 source='''fn checks()->unit{let values:list<i64>=@VALUES@;let x:m::Tensor=unwrap(m::from_exact_i32("x",[@N@],values));assert(unwrap(m::to_exact_i32(x))==values);assert(error_code(m::from_exact_i32("x",[1],[16777217]))=="E_MODEL_PRECISION");assert(error_code(m::from_exact_i32("x",[1],[-9223372036854775808]))=="E_MODEL_PRECISION");}
fn main()->unit!{io}{checks();print(encode_base64(unwrap(m::from_exact_i32("x",[@N@],@VALUES@)).data));}test fn roundtrip()->unit{checks();}'''.replace('@VALUES@',json.dumps(values)).replace('@N@',str(len(values)))
 root=project('exact-f32',source);expected=base64.b64encode(b''.join(struct.pack('<f',v) for v in values)).decode()+'\n';agree(root,expected);report['cases'].append({'name':'exact-f32','values_compared':len(values),'native_reference_typescript':True})
 root=project('shape-finite',setup+'''
fn checks()->unit{
 assert(error_code(m::tensor("x",m::DType::F32(),[1],unwrap(bytes([0,0,128,127]))))=="E_MODEL_NONFINITE");
 assert(error_code(m::tensor("x",m::DType::F32(),[1],unwrap(bytes([1,0,128,255]))))=="E_MODEL_NONFINITE");
 assert(error_code(m::tensor("x",m::DType::F32(),[1],unwrap(bytes([1,2,3]))))=="E_MODEL_SIZE");
 let half:m::Tensor=unwrap(m::tensor("x",m::DType::F32(),[1],unwrap(bytes([0,0,0,63]))));assert(error_code(m::to_exact_i32(half))=="E_MODEL_PRECISION");
 let zero:m::Tensor=unwrap(m::tensor("x",m::DType::F32(),[1],unwrap(bytes([0,0,0,128]))));assert(zero.data==unwrap(bytes([0,0,0,128])));assert(m::to_exact_i32(zero)==ok([0]));
 assert(error_code(m::elements([9223372036854775807,9223372036854775807]))=="E_MODEL_LIMIT");
 let d:m::Model=definition();assert(error_code(m::validate_model(m::Model(d.id,d.sha256,d.precision,[d.inputs[0],d.inputs[0]],d.outputs)))=="E_MODEL_PORT");
 assert(error_code(m::validate_model(m::Model(d.id,d.sha256,d.precision,[m::Port("X",m::DType::F32(),[196608])],[m::Port("Y",m::DType::U8(),[1])])))=="E_MODEL_LIMIT");
 assert(is_ok(m::validate_model(m::Model(d.id,d.sha256,d.precision,[m::Port("X",m::DType::U8(),[262144])],[m::Port("Y",m::DType::U8(),[262144])]))));
 assert(error_code(m::tensor("bad\\u0000name",m::DType::U8(),[1],unwrap(bytes([0]))))=="E_MODEL_PORT");
 assert(!m::is_sha256("A"));assert(!m::is_sha256("AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"));
}
fn main()->unit!{io}{checks();print("shape/finite OK");}test fn bounds()->unit{checks();}
''');agree(root,'shape/finite OK\n');report['cases'].append({'name':'shape-finite','native_reference_typescript':True})
 root=project('dispatch-fallback',setup+'''
server fn unsupported(job:m::Request,d:m::Device)->result<m::Response>!{ffi}{if d.kind==c::Kind::NPU(){return err("E_MODEL_UNSUPPORTED","runtime constraint");}return echo(job,d);}
server fn failed(job:m::Request,d:m::Device)->result<m::Response>!{ffi}{return err("E_TEST_FAULT","must not become fallback");}
server fn wrong(job:m::Request,d:m::Device)->result<m::Response>!{ffi}{return ok(m::Response(1,job.id,job.model.sha256,job.model.precision,[m::Tensor("wrong",m::DType::F32(),[2],job.inputs[0].data)],d,false,""));}
server fn wrong_precision(job:m::Request,d:m::Device)->result<m::Response>!{ffi}{return ok(m::Response(1,job.id,job.model.sha256,m::Precision::Vendor(),[m::Tensor("Y",m::DType::F32(),[2],job.inputs[0].data)],d,false,""));}
server fn precision_fault(job:m::Request,d:m::Device)->result<m::Response>!{ffi}{return err("E_MODEL_PRECISION","CPU comparison differs");}
server fn checks()->unit!{ffi}{
 let cpu:m::Device=device(c::Kind::CPU(),"cpu");let npu:m::Device=device(c::Kind::NPU(),"npu");
 let ctx:m::Context=unwrap(m::context([cpu,npu],echo));assert(!unwrap(m::execute(ctx,job(c::Kind::NPU(),c::Fallback::Deny()))).fallback_used);
 let empty:m::Context=unwrap(m::context([cpu],echo));assert(error_code(m::execute(empty,job(c::Kind::NPU(),c::Fallback::Deny())))=="E_MODEL_UNAVAILABLE");
 let fall:m::Response=unwrap(m::execute(empty,job(c::Kind::NPU(),c::Fallback::CPU())));assert(fall.fallback_used);assert(fall.device.kind==c::Kind::CPU());assert(fall.fallback_reason!="");assert(m::to_exact_i32(fall.outputs[0])==ok([3,-7]));
 let fallback:m::Response=unwrap(m::execute(unwrap(m::context([cpu,npu],unsupported)),job(c::Kind::NPU(),c::Fallback::CPU())));assert(fallback.fallback_used);
 assert(error_code(m::execute(unwrap(m::context([cpu,npu],failed)),job(c::Kind::NPU(),c::Fallback::CPU())))=="E_TEST_FAULT");
 assert(error_code(m::execute(unwrap(m::context([cpu,npu],wrong)),job(c::Kind::NPU(),c::Fallback::CPU())))=="E_MODEL_RESPONSE");
 assert(error_code(m::execute(unwrap(m::context([cpu,npu],wrong_precision)),job(c::Kind::NPU(),c::Fallback::CPU())))=="E_MODEL_RESPONSE");
 assert(error_code(m::execute(unwrap(m::context([cpu,npu],precision_fault)),job(c::Kind::NPU(),c::Fallback::CPU())))=="E_MODEL_PRECISION");
 let j:m::Request=job(c::Kind::NPU(),c::Fallback::CPU());let invalid:m::Request=m::Request(9,j.id,j.model,j.inputs,j.device,j.fallback);assert(error_code(m::execute(unwrap(m::context([],never)),invalid))=="E_MODEL_VERSION");
 assert(error_code(m::execute(m::Context([npu,npu],never),j))=="E_MODEL_DEVICE");
 assert(error_code(m::execute(ctx,m::on(j,c::Selection(c::Kind::NPU(),"missing"),c::Fallback::Deny())))=="E_MODEL_UNAVAILABLE");
 assert(error_code(m::execute(ctx,m::on(j,c::Selection(c::Kind::NPU(),"bad\\u0000id"),c::Fallback::CPU())))=="E_MODEL_ID");
 let other:m::Model=m::Model(j.model.id,j.model.sha256,m::Precision::Vendor(),j.model.inputs,j.model.outputs);
 assert(error_code(m::execute(ctx,m::request(j.id,other,j.inputs,j.device,c::Fallback::Deny())))=="E_MODEL_UNSUPPORTED");
}
server fn main()->unit!{ffi,io}{checks();print("dispatch/fallback OK");}server test fn dispatch()->unit!{ffi}{checks();}
''')
 for name,args in [('reference',['eval']),('debug',['run','--profile','debug']),('release',['run','--profile','release'])]:assert cli(root,name,args)['stdout']=='dispatch/fallback OK\n'
 cli(root,'tests',['test','--profile','release']);measured=cli(root,'profile',['profile','--entry','checks','--scenario','model response cleanup']);profile=json.loads(Path(measured['output']).read_text());assert all(v['live']==0 and v['allocations']==v['frees'] for v in profile['memory']);report['cases'].append({'name':'dispatch-fallback','managed_memory_balanced':True})
 root=project('wire-data',setup+'''
fn checks()->unit{
 let x:m::Tensor=unwrap(m::tensor("X",m::DType::F32(),[2],unwrap(bytes([0,0,0,128,1,0,0,0]))));
 assert(unwrap(decode_json<m::Tensor>(encode_json(x)))==x);
 assert(unwrap(decode_json<m::Model>(encode_json(definition())))==definition());
 let u:m::Tensor=unwrap(m::tensor("U",m::DType::U8(),[2],unwrap(bytes([0,255]))));assert(m::validate_tensor(u)==ok(u));
 let i:m::Tensor=unwrap(m::tensor("I",m::DType::I8(),[2],unwrap(bytes([128,127]))));assert(m::validate_tensor(i)==ok(i));
 let w:m::Tensor=unwrap(m::tensor("W",m::DType::I32(),[2],unwrap(bytes([0,0,0,128,255,255,255,127]))));assert(m::validate_tensor(w)==ok(w));
 assert(error_code(m::to_exact_i32(x))=="E_MODEL_PRECISION");
}
fn main()->unit!{io}{checks();print("wire data OK");}test fn data()->unit{checks();}
''');agree(root,'wire data OK\n');report['cases'].append({'name':'wire-data','native_reference_typescript':True,'negative_zero_and_subnormal_bytes':True,'all_four_dtypes':True})
 for name,body,code in [('wire','fn main()->unit{} fn encode(value:m::Context)->str{return encode_json(value);}','E_GENERIC_BOUND'),('realm','client fn main()->unit{let ctx:m::Context=unwrap(m::context([],never));}','E_REALM'),('effects','server fn main()->unit{let ctx:m::Context=unwrap(m::context([],never));let value:result<m::Response>=m::execute(ctx,job(c::Kind::CPU(),c::Fallback::Deny()));}','E_EFFECT')]:
  root=project('reject-'+name,setup+body);cli(root,'check',['check'],code);report['cases'].append({'name':'reject-'+name,'diagnostic':code})
 root=project('typed-bulk-signature','server extern fn model_run(values:list<bytes>,kind:i64)->result<list<bytes>> !{ffi}=foreign("model","model_run","'+('0'*64)+'");server fn main()->unit{}');contract=cli(root,'ffi',['ffi','--symbol','model_run']);assert {v['kind'] for v in contract['types']}=={'bytes','list','i64','result'};report['cases'].append({'name':'typed-bulk-signature'})
 report.update(ok=True,phase='complete',claims='source validation/dispatch and exact finite F32 byte helpers; no actual model execution or device claim');save();print(json.dumps({'ok':report['ok'],'report':str(out/'report.json'),'cases':len(report['cases']),'compiler_commands':len(report['commands'])}))
except BaseException:
 save();raise
