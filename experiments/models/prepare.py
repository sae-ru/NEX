#!/usr/bin/env python3
"""Prepare a new pinned ONNX model provider; never initialize its runtime/device."""
import argparse,base64,hashlib,json,math,os,platform,shutil,struct,subprocess
from pathlib import Path

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def identifier(value,n):return isinstance(value,str) and 0<len(value)<=n and '\0' not in value
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--sdk',type=Path,required=True);p.add_argument('--model',type=Path,required=True);p.add_argument('--spec',type=Path,required=True);p.add_argument('--ort-library',type=Path,required=True);p.add_argument('--include',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--enable-zhouyi',action='store_true');p.add_argument('--operator-path',type=Path);p.add_argument('--precision',choices=['match-cpu','vendor']);p.add_argument('--example',type=Path);p.add_argument('--expect-npu-unsupported',action='store_true',help='negative acceptance expectation only; does not change provider placement or fallback policy');p.add_argument('--cxx',default='g++');a=p.parse_args()
 if platform.system()!='Linux' or platform.machine() not in ['aarch64','arm64']:p.error('current native provider requires Linux ARM64; other hosts remain pending')
 if a.expect_npu_unsupported and (not a.enable_zhouyi or not a.example):p.error('negative NPU example requires --enable-zhouyi and --example')
 if a.enable_zhouyi and not a.operator_path:p.error('Zhouyi binding needs an explicit installed operator directory')
 origin=Path(__file__).resolve().parent;sdk=a.sdk.resolve(strict=True);resources=sdk/'share/nex';compiler=sdk/'bin/nex';library=a.ort_library.resolve(strict=True);model=a.model.resolve(strict=True);headers=a.include.resolve(strict=True)
 if not library.is_file() or not model.is_file() or not 0<model.stat().st_size<=33554432 or a.spec.stat().st_size>65536:p.error('bounded existing model/runtime/spec files required')
 spec=json.loads(a.spec.read_text());allowed={'schema','id','sha256','inputs','outputs','precision'}
 if set(spec)-allowed or spec.get('schema')!='nex.model-artifact/1' or not identifier(spec.get('id'),128) or spec.get('sha256')!=sha(model):p.error('spec schema/id/model SHA256 mismatch')
 precision=a.precision or spec.get('precision','match-cpu')
 if precision not in ['match-cpu','vendor']:p.error('unknown explicit precision policy')
 spec['precision']=precision;total=0;dtype={'f32':('F32',4),'u8':('U8',1),'i8':('I8',1),'i32':('I32',4)}
 for direction in ['inputs','outputs']:
  ports=spec.get(direction);names=set()
  if not isinstance(ports,list) or not 1<=len(ports)<=16:p.error('requires1..16 ports per direction')
  for port in ports:
   if not isinstance(port,dict) or set(port)!={'name','dtype','shape'} or not identifier(port['name'],128) or port['name'] in names or port['dtype'] not in dtype:p.error('invalid or duplicate named port')
   names.add(port['name']);shape=port['shape']
   if not isinstance(shape,list) or not 1<=len(shape)<=4:p.error('port rank must be1..4')
   n=1
   for d in shape:
    if type(d)!=int or d<1 or d>262144 or n>262144//d:p.error('port exceeds262144 elements')
    n*=d
   total+=n*dtype[port['dtype']][1]
 if total>786432:p.error('combined model input/output exceeds786432 bytes')
 operator=str(a.operator_path.resolve(strict=True)) if a.operator_path else ''
 if operator and not Path(operator).is_dir():p.error('operator path must be a directory')
 root=a.output.absolute();root.mkdir(exist_ok=False);commands=[];env={**os.environ,'NEX_RESOURCE_DIR':str(resources)}
 def command(args):
  q=subprocess.run(list(map(str,args)),cwd=root,env=env,capture_output=True,text=True,timeout=300);index=len(commands);(root/('prepare-'+str(index)+'.stdout')).write_text(q.stdout);(root/('prepare-'+str(index)+'.stderr')).write_text(q.stderr);commands.append({'command':list(map(str,args)),'exit_code':q.returncode});assert q.returncode==0,(q.stdout[-3000:],q.stderr[-3000:]);return q.stdout
 def cli(*args):return json.loads(command([compiler,*args,'--json']))
 descriptor=cli('describe');assert descriptor['version']=='0.20' and descriptor['foreign_boundary']['source_support']
 if 'model' in descriptor:assert descriptor['model']['source_support'] and descriptor['model']['import']=='std/model.nex' and descriptor['model']['contract_version']==1
 (root/'stdlib').mkdir();shutil.copy2(origin.parents[1]/'lib/model.nex',root/'stdlib/model.nex');shutil.copy2(origin.parents[1]/'lib/compute.nex',root/'stdlib/compute.nex');(root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.20','entry':'main.nex','libraries':{'std':'./stdlib'}},indent=2)+'\n')
 for name in ['common.h','model-worker.cpp','model-module.cpp','model-broker.inc']:shutil.copy2(origin/name,root/name)
 configuration={**spec,'runtime':str(library),'runtime_sha256_at_preparation':sha(library),'zhouyi':a.enable_zhouyi,'operator_path':operator}
 (root/'model-config.inc').write_text('static constexpr const char modelConfiguration[]='+json.dumps(json.dumps(configuration,ensure_ascii=True,separators=(',',':')))+';\n')
 (root/'operator-spec.json').write_bytes(a.spec.read_bytes())
 def port(value):return 'm::Port('+json.dumps(value['name'],ensure_ascii=False)+',m::DType::'+dtype[value['dtype']][0]+'(),'+json.dumps(value['shape'])+')'
 definition='m::Model('+json.dumps(spec['id'],ensure_ascii=False)+','+json.dumps(spec['sha256'])+',m::Precision::'+('MatchCPU' if precision=='match-cpu' else 'Vendor')+'(),['+','.join(port(v) for v in spec['inputs'])+'],['+','.join(port(v) for v in spec['outputs'])+'])'
 example='server fn main()->unit!{io}{print(encode_json(definition()));}\n'
 if a.example:
  case=json.loads(a.example.read_text());assert set(case)=={'inputs','expected'} and len(case['inputs'])==len(spec['inputs']) and len(case['expected'])==len(spec['outputs'])
  def octets(values,port):
   fmt={'f32':'f','i32':'i','u8':'B','i8':'b'}[port['dtype']];raw=struct.pack('<'+fmt*len(values),*values);assert len(raw)==math.prod(port['shape'])*dtype[port['dtype']][1];return base64.b64encode(raw).decode('ascii')
  inputs=['unwrap(m::tensor('+json.dumps(v['name'],ensure_ascii=False)+',m::DType::'+dtype[v['dtype']][0]+'(),'+json.dumps(v['shape'])+',unwrap(decode_base64('+json.dumps(octets(values,v))+'))))' for v,values in zip(spec['inputs'],case['inputs'])]
  expected=[json.dumps(octets(values,v)) for v,values in zip(spec['outputs'],case['expected'])]
  example='fn inputs()->list<m::Tensor>{return ['+','.join(inputs)+'];}\nserver fn checks(kind:c::Kind)->unit!{ffi}{let out:m::Response=unwrap(run(inputs(),kind,c::Fallback::Deny()));assert(out.device.kind==kind);assert(!out.fallback_used);'
  for i,raw in enumerate(expected):example+='assert(out.outputs['+str(i)+'].data==unwrap(decode_base64('+raw+')));'
  example+='}\n'
  first_size=math.prod(spec['inputs'][0]['shape'])*dtype[spec['inputs'][0]['dtype']][1]
  bad_size=base64.b64encode(bytes(1 if first_size!=1 else 2)).decode('ascii')
  example+='fn raw_inputs(first:bytes)->list<bytes>{let values:list<m::Tensor>=inputs();var data:list<bytes>=[first];var i:i64=1;while i<len(values){data=push(data,values[i].data);i=i+1;}return data;}\nserver fn reject_inputs()->unit!{ffi}{let values:list<m::Tensor>=inputs();assert(error_code(model_run(raw_inputs(values[0].data),2))=="E_MODEL_DEVICE");assert(error_code(model_run([],0))=="E_MODEL_PORT");assert(error_code(model_run(raw_inputs(unwrap(decode_base64('+json.dumps(bad_size)+'))),0))=="E_MODEL_SIZE");'
  if spec['inputs'][0]['dtype']=='f32':
   nonfinite=base64.b64encode(bytes([0,0,128,127])+bytes(first_size-4)).decode('ascii')
   example+='assert(error_code(model_run(raw_inputs(unwrap(decode_base64('+json.dumps(nonfinite)+'))),0))=="E_MODEL_NONFINITE");'
  example+='}\nserver test fn raw_rejections()->unit!{ffi}{reject_inputs();}\n'
  if a.expect_npu_unsupported:
   assert a.enable_zhouyi
   example+='server fn denied()->unit!{ffi}{assert(error_code(run(inputs(),c::Kind::NPU(),c::Fallback::Deny()))=="E_MODEL_UNSUPPORTED");}\nserver fn fallback()->unit!{ffi}{let out:m::Response=unwrap(run(inputs(),c::Kind::NPU(),c::Fallback::CPU()));assert(out.device.kind==c::Kind::CPU());assert(out.fallback_used);assert(out.fallback_reason!="");'
   for i,raw in enumerate(expected):example+='assert(out.outputs['+str(i)+'].data==unwrap(decode_base64('+raw+')));'
   example+='}\nserver fn main()->unit!{ffi,io}{reject_inputs();checks(c::Kind::CPU());denied();fallback();print('+json.dumps('NEX MODEL '+spec['id']+' OK',ensure_ascii=False)+');}\nserver test fn cpu_case()->unit!{ffi}{checks(c::Kind::CPU());}\nserver test fn denied_case()->unit!{ffi}{denied();}\nserver test fn fallback_case()->unit!{ffi}{fallback();}\n'
  else:
   example+='server fn main()->unit!{ffi,io}{reject_inputs();checks(c::Kind::CPU());'+('checks(c::Kind::NPU());' if a.enable_zhouyi else '')+'print('+json.dumps('NEX MODEL '+spec['id']+' OK',ensure_ascii=False)+');}\nserver test fn cpu_case()->unit!{ffi}{checks(c::Kind::CPU());}\n'
   if a.enable_zhouyi:example+='server test fn npu_case()->unit!{ffi}{checks(c::Kind::NPU());}\n'
  (root/'example.json').write_bytes(a.example.read_bytes())
 template=(origin/'main.nex.in').read_text().replace('@MODEL@',definition).replace('@DEVICES@','[cpu(),npu()]' if a.enable_zhouyi else '[cpu()]').replace('@EXAMPLE@',example)
 provenance='prepared runtime SHA256:'+sha(library)+'; precision:'+precision+'; model:'+spec['sha256']
 template=template.replace('@PROVENANCE@',json.dumps(provenance));(root/'main.nex').write_text(template.replace('@PIN@','0'*64));signature=cli('ffi','--symbol','model_run');digest=hashlib.sha256(json.dumps(signature,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
 bundle=root/'bundle';bundle.mkdir();shutil.copy2(model,bundle/'model.onnx');(bundle/'model.json').write_text(json.dumps(spec,indent=2)+'\n');flags=[a.cxx,'-std=c++20','-O2','-Wall','-Wextra','-I'+str(resources/'runtime'),'-I'+str(headers)]
 command([*flags,root/'model-worker.cpp','-o',bundle/'model-worker','-ldl','-pthread']);command([*flags,'-shared','-fPIC','-fvisibility=hidden','-DNEX_MODEL_SIGNATURE="'+digest+'"',root/'model-module.cpp','-o',bundle/'module.so','-ldl','-pthread'])
 notice='NEX-owned experimental model provider and test graphs. Runtime/driver/operator dependencies remain installed platform inputs.\n'
 for license in [headers/'ONNX-LICENSE',headers/'OPENCL-LICENSE',resources/'runtime/third_party/JSON-LICENSE.MIT']:notice+='\n'+license.read_text()
 (bundle/'NOTICE').write_text(notice);manifest={'schema':'nex.foreign-bundle/1','platform':'linux-arm64','entry':'module.so','files':[{'path':n,'sha256':sha(bundle/n)} for n in ['module.so','model-worker','model.onnx','model.json','NOTICE']],'exports':{'model_run':digest},'notices':['NOTICE']};(bundle/'manifest.json').write_text(json.dumps(manifest,sort_keys=True,indent=2)+'\n');pin=sha(bundle/'manifest.json');(root/'main.nex').write_text(template.replace('@PIN@',pin));(root/'host.json').write_text(json.dumps({'schema':'nex.foreign-host/1','module_limit':64,'libraries':{'model':{'directory':'bundle','manifest_sha256':pin,'exports':['model_run']}}},indent=2)+'\n');cli('check');catalogue=cli('foreign',root/'host.json')
 report={'schema':'nex.model-preparation/1','ok':True,'hardware_executed':False,'commands':commands,'compiler_sha256':sha(compiler),'model_sha256':sha(model),'manifest_sha256':pin,'precision':precision,'native_zhouyi_binding':a.enable_zhouyi,'acceptance_expects_NPU_unsupported':a.expect_npu_unsupported,'runtime':str(library),'runtime_sha256_at_preparation':sha(library),'runtime_immutable_pin':False,'operator_path':operator,'catalogue':catalogue,'sources':{n:sha(root/n) for n in ['common.h','model-worker.cpp','model-module.cpp','model-broker.inc','stdlib/model.nex','model-config.inc']}};(root/'preparation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='catalogue'}))
if __name__=='__main__':main()
