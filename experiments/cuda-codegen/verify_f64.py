"""Verify finite binary64 CUDA lowering on CPU and LLVM/NVPTX; no GPU claim."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import struct
import subprocess
import sys


def word(value):
    return struct.unpack('<q', struct.pack('<d', value))[0]


def floating(value):
    return struct.unpack('<d', struct.pack('<q', value))[0]


def literal(value):
    text = repr(value)
    return text if '.' in text or 'e' in text else text + '.0'


def fixtures():
    tiny = floating(1)
    maximum = floating(0x7fefffffffffffff)
    pairs = [(0.0, -0.0), (1.0, 0.0), (-1.0, -0.0), (0.1, 0.2), (1.0, 2**-53),
        (float(2**53), 1.0), (maximum, maximum), (maximum, -maximum), (-maximum, maximum), (maximum, 3*tiny),
        (maximum, tiny), (tiny, 2.0), (-tiny, 2.0),
        (tiny, tiny), (-7.0, 3.0), (7.0, -3.0), (-7.0, -3.0), (floating(0x10000000000000), 3*tiny)]
    result = []
    for name, operator in [('add','+'), ('sub','-'), ('mul','*'), ('div','/'), ('mod','%')]:
        rows = []
        selected = list(pairs)
        if operator == '%':
            rng = random.Random(0x4e455864)
            while len(selected) < 143:
                a, b = [struct.unpack('<d', rng.getrandbits(64).to_bytes(8, 'little'))[0] for _ in range(2)]
                if math.isfinite(a) and math.isfinite(b) and b != 0:
                    selected.append((a, b))
        for a, b in selected:
            if operator in ['/', '%'] and b == 0:
                value, error = 0, 2
            else:
                value = {'+': lambda:a+b, '-':lambda:a-b, '*':lambda:a*b, '/':lambda:a/b, '%':lambda:math.fmod(a,b)}[operator]()
                value, error = (word(0.0 if value == 0 else value), 0) if math.isfinite(value) else (0, 7)
            rows.append(([word(a), word(b)], value, error))
        result.append(('f64_'+name, 'pub fn transform(a:f64,b:f64)->f64{return a'+operator+'b;}', ['f64','f64'], 'f64', rows))
    finite = [0.0, -0.0, tiny, -tiny, -1.25, maximum, -maximum]
    identity = [([word(x)], word(0.0 if x == 0 else x), 0) for x in finite]
    identity += [([struct.unpack('<q', n.to_bytes(8,'little'))[0]], 0, 7) for n in [0x7ff0000000000000,0xfff0000000000000,0x7ff8000000000001,0x7ff0000000000001]]
    result.append(('f64_identity','pub fn transform(x:f64)->f64{return x;}',['f64'],'f64',identity))
    result.append(('f64_neg','pub fn transform(x:f64)->f64{return -x;}',['f64'],'f64',[([word(x)],word(0.0 if x==0 else -x),0)for x in finite]))
    result.append(('f64_compare','pub fn transform(a:f64,b:f64)->i64{var r:i64=0;if a==b{r=r+1;}if a!=b{r=r+2;}if a<b{r=r+4;}if a<=b{r=r+8;}if a>b{r=r+16;}if a>=b{r=r+32;}return r;}',['f64','f64'],'i64',
        [([word(a),word(b)],sum(n for n,c in [(1,a==b),(2,a!=b),(4,a<b),(8,a<=b),(16,a>b),(32,a>=b)]if c),0)for a,b in pairs]))
    result.append(('f64_no_FMA','pub fn transform(a:f64,b:f64,c:f64)->f64{return a*b+c;}',['f64']*3,'f64',
        [([word(a),word(b),word(c)],word(a*b+c),0)for a,b,c in [(1+2**-27,1-2**-27,-1.0),(0.1,0.2,-0.02)]]))
    result.append(('f64_from_i64','pub fn transform(x:i64)->f64{return as_f64(x);}',['i64'],'f64',
        [([x],word(float(x)),0)for x in [-(1<<63),(1<<63)-1,-(1<<53)-1,(1<<53)+1,(1<<53)+3,-1,0,1]]))
    result.append(('f64_generic','fn twice<T:number>(x:T)->T{return x+x;}pub fn transform(x:f64)->f64{return twice<f64>(x);}',['f64'],'f64',
        [([word(x)],word(0.0 if x+x==0 else x+x) if math.isfinite(x+x) else 0,0 if math.isfinite(x+x) else 7)for x in finite]))
    result.append(('f64_contract','pub fn transform(x:f64)->f64 requires(x>=0.0) ensures(r=>r>=x){return x+1.0;}',['f64'],'f64',
        [([word(x)],word(x+1.0) if x>=0 else 0,0 if x>=0 else 3)for x in [0.0,tiny,41.0,-1.0,maximum]]))
    result.append(('f64_match','pub fn transform(x:f64)->f64{return match x{n if n<0.0=>-n,n=>n+1.0};}',['f64'],'f64',
        [([word(x)],word(-x if x<0 else x+1.0),0)for x in finite]))
    result.append(('f64_lazy_match','fn fail()->f64{assert(false);return 0.0;}pub fn transform(x:bool)->f64{return match x{true=>1.0,false=>fail()};}',['bool'],'f64',[([1],word(1.0),0),([0],0,3),([2],0,6)]))
    for name, first, second, error in [('f64_div_first','return x/0.0;','assert(false);return x;',2),('f64_assert_first','assert(false);return x;','return x/0.0;',3)]:
        result.append((name,'fn first(x:f64)->f64{'+first+'}fn second(x:f64)->f64{'+second+'}pub fn transform(x:f64)->f64{return first(x)+second(x);}',['f64'],'f64',[([word(1.0)],0,error)]))
    nan = 0x7ff8000000000001
    result.append(('f64_input_order','pub fn transform(x:f64,b:bool)->bool{return b&&x>0.0;}',['f64','bool'],'bool',[([nan,2],0,7),([word(1.0),2],0,6),([word(1.0),1],1,0),([word(0.0),1],0,0)]))
    result.append(('f64_input_order_reverse','pub fn transform(b:bool,x:f64)->bool{return b&&x>0.0;}',['bool','f64'],'bool',[([2,nan],0,6),([1,nan],0,7),([1,word(1.0)],1,0)]))
    result.append(('f64_literal','pub fn transform()->f64{return 5e-324;}',[],'f64',[([],1,0)]))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['emitter','compiler','resources','frontend-archive','cxx','llvm-bin','output']:
        parser.add_argument('--'+name, required=True, type=Path)
    args = parser.parse_args()
    emitter, compiler, resources, frontend, cxx, llvm = [p.resolve(strict=True)for p in [args.emitter,args.compiler,args.resources,args.frontend_archive,args.cxx,args.llvm_bin]]
    out = args.output.resolve();out.mkdir(exist_ok=False)
    sha = lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
    source = Path(__file__).resolve().parent
    pins = {str(p):sha(p)for p in [emitter,compiler,frontend,Path(__file__).resolve(),source/'floating_runtime.h',source.parent.parent/'src/cuda_floating_runtime.h',source.parent.parent/'src/cuda.cpp',source/'clang_device.h']}
    env = {k:v for k,v in os.environ.items()if not k.startswith(('NEX_','PYTHON','CUDA_','LD_','DYLD_')) and k not in ['SDKROOT','CPATH','CPLUS_INCLUDE_PATH','C_INCLUDE_PATH','LIBRARY_PATH']}
    env.update({k:os.environ[k] for k in ['NEX_NODE','NEX_TSC','NEX_PYTHON'] if k in os.environ})
    env.update(NEX_RESOURCE_DIR=str(resources),PYTHONDONTWRITEBYTECODE='1')
    report = {'schema':'nex.experimental-cuda-source-controls/1','ok':False,'GPU_execution_claimed':False,'f64':True,'cases':[],'commands':[],
        'compiler_sha256':sha(compiler),'emitter_sha256':sha(emitter),'input_pins':pins,'PTX_variants':[]}
    def save(): (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    def run(label,argv,cwd=out,expected=0,timeout=600):
        assert all(sha(p)==h for p,h in pins.items())
        number=len(report['commands']);row={'label':label,'argv':list(map(str,argv))};report['commands'].append(row);save()
        v=subprocess.run(row['argv'],cwd=cwd,env=env,capture_output=True,timeout=timeout)
        (out/(str(number)+'-'+label+'.stdout')).write_bytes(v.stdout);(out/(str(number)+'-'+label+'.stderr')).write_bytes(v.stderr);row['exit_code']=v.returncode;save()
        assert v.returncode==expected,(label,v.stderr[-2000:],v.stdout[-2000:]);return v.stdout
    def manifest(p): (p/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.28','entry':'main.nex'})+'\n')
    try:
        resource = Path(run('clang-resource',[llvm/'clang++','--no-default-config','-print-resource-dir']).decode().strip()).resolve(strict=True)
        for name in ['clang++','opt','llc']:
            p=(llvm/name).resolve(strict=True);pins[str(p)]=sha(p);assert re.search(r'version\s+22\.1\.\d+',run(name+'-version',[p,'--version']).decode())
        references=out/'references';references.mkdir();manifest(references);imports=[];assertions=[];negatives=[]
        for index,(name,body,types,result_type,rows)in enumerate(fixtures()):
            project=out/name;project.mkdir();manifest(project)
            text='module cf64_'+str(index)+';'+body+'\nfn main()->unit{}\nserver fn unselected()->str{return "UNREACHABLE_F64_SECRET";}\n'
            (project/'main.nex').write_text(text);(references/('f'+str(index)+'.nex')).write_text(text);imports.append('import "./f'+str(index)+'.nex" as c'+str(index)+';')
            checked=json.loads(run(name+'-check',[compiler,'check','--json'],project));assert checked['ok']
            graph=json.loads(run(name+'-graph',[compiler,'graph','--json'],project));nodes={n['name']:n for n in graph['nodes']}
            for layout in ['rows','columns']:
                shader=project/(layout+'.cu');metadata=json.loads(run(name+'-'+layout,[emitter,project,'transform',layout,shader],project))
                assert metadata['parameter_types']==types and metadata['result_type']==result_type and metadata['floating_point']['rounding']=='nearest_ties_even'
                assert metadata['revision']==checked['revision']
                assert all(nodes[f['name']]['hash']==f['hash']for f in metadata['functions']) and metadata['shader_sha256']==sha(shader)
                assert 'UNREACHABLE_F64_SECRET'not in shader.read_text()
                count,arity=len(rows),len(types);matrix=[r[0]for r in rows];values=[v for row in matrix for v in row]if layout=='rows'else[matrix[lane][p]for p in range(arity)for lane in range(count)]
                literals=','.join('nex_bits(0x%016xULL)'%(v%(1<<64))for v in values)or'0LL'
                inputs=['input']if layout=='rows'else['input+'+str(p*count)for p in range(arity)];call=','.join([*inputs,'output','errors',str(count)+'U','65536U'])
                harness=project/(layout+'-host.cpp');harness.write_text('#include <iostream>\n#define __device__\n#define __global__\nstruct Index{unsigned int x;};Index blockIdx,blockDim,threadIdx;\n#include '+json.dumps(str(shader))+'\nint main(){long long input[]={'+literals+'};long long output['+str(count+3)+'];unsigned int errors['+str(count+3)+'];int modes[]={FE_TONEAREST,FE_UPWARD,FE_DOWNWARD,FE_TOWARDZERO};std::cout<<"[";for(unsigned m=0;m<4;++m){std::fesetenv(FE_DFL_ENV);if(std::fesetround(modes[m])||std::feraiseexcept(FE_INVALID|FE_INEXACT))return 11;auto flags=std::fetestexcept(FE_ALL_EXCEPT);for(unsigned i=0;i<'+str(count+3)+';++i){output[i]=123456789LL;errors[i]=98765U;}blockDim.x=128;for(unsigned lane=0;lane<'+str(count+256)+';++lane){blockIdx.x=lane/128;threadIdx.x=lane%128;nex_generated_cuda_map('+call+');if(std::fegetround()!=modes[m]||std::fetestexcept(FE_ALL_EXCEPT)!=flags)return 12;}if(m)std::cout<<",";std::cout<<"{\\\"values\\\":[";for(unsigned i=0;i<'+str(count+3)+';++i){if(i)std::cout<<",";std::cout<<output[i];}std::cout<<"],\\\"errors\\\":[";for(unsigned i=0;i<'+str(count+3)+';++i){if(i)std::cout<<",";std::cout<<errors[i];}std::cout<<"]}";}std::cout<<"]\\n";}\n')
                executable=project/(layout+'-host');run(name+'-host-build',[cxx,'-std=c++20','-O2','-frounding-math','-ffp-contract=off','-fsanitize=undefined','-fno-sanitize-recover=all',harness,'-o',executable])
                actual=json.loads(run(name+'-host-run',[executable]));assert len(actual)==4
                for mode in actual:
                    assert mode['values']==[r[1]for r in rows]+[123456789]*3,(name,layout,mode,rows)
                    assert mode['errors']==[r[2]for r in rows]+[98765]*3,(name,layout,mode,rows)
                for arch,feature,version in [('sm_52','ptx42','4.2'),('sm_86','ptx71','7.1')]:
                    for optimization in [0,2]:
                        label=name+'-'+layout+'-'+arch+'-O'+str(optimization);ir=project/(label+'.ll');ptx=project/(label+'.ptx')
                        run(label+'-frontend',[llvm/'clang++','--no-default-config','--target=x86_64-unknown-linux-gnu','-x','cuda','--cuda-device-only','--cuda-gpu-arch='+arch,'--cuda-feature=+'+feature,'-resource-dir',resource,'-nocudainc','-nocudalib','-nostdinc','-nostdinc++','-isystem',resource/'include','-std=c++20','-O'+str(optimization),'-S','-emit-llvm','-include',source/'clang_device.h',shader,'-o',ir],timeout=60)
                        run(label+'-IR-verify',[llvm/'opt','-passes=verify','-disable-output',ir],timeout=60)
                        run(label+'-PTX',[llvm/'llc','-march=nvptx64','-mcpu='+arch,'-mattr=+'+feature,'-O='+str(optimization),'-verify-machineinstrs',ir,'-o',ptx],timeout=60)
                        p=ptx.read_text();assert '.address_size 64'in p and re.search(r'\.version\s+'+re.escape(version)+r'\b',p)and re.search(r'\.target\s+'+arch+r'\b',p)and not re.search(r'\.extern\s+\.func',p)
                        entry=re.search(r'\.visible\s+\.entry\s+nex_generated_cuda_map\s*\((.*?)\)',p,re.S);assert entry
                        assert list(map(int,re.findall(r'\.param\s+\.[ub](\d+)\s',entry[1])))==[64]*(3 if layout=='rows'else arity+2)+[32,32]
                        if name=='f64_no_FMA':assert 'mul.rn.f64'in p and 'add.rn.f64'in p and not re.search(r'\bfma\.[^\n]*f64',p)
                        report['PTX_variants'].append({'name':name,'layout':layout,'arch':arch,'optimization':optimization,'IR_sha256':sha(ir),'PTX_sha256':sha(ptx),'IR_and_machine_verification_passed':True})
                report['cases'].append({'name':name,'layout':layout,'shader':str(shader.relative_to(out)),'shader_sha256':sha(shader),'metadata':metadata,'steps':65536,
                    'lanes':[{'arguments':list(map(str,r[0])),'value':str(r[1]),'error':r[2]}for r in rows],'host_UBSan_passed':True,'all_four_rounding_modes_and_exception_flags_preserved':True,'excess_lanes_untouched':True})
            for args_words,value,error in rows:
                if any((t=='f64'and not math.isfinite(floating(v)))or(t=='bool'and v not in [0,1])for t,v in zip(types,args_words)):continue
                words=[literal(floating(v))if t=='f64'else('true'if v else'false')if t=='bool'else str(v)for t,v in zip(types,args_words)]
                call='c'+str(index)+'::transform('+','.join(words)+')'
                if not error:
                    expect=literal(floating(value))if result_type=='f64'else('true'if value else'false')if result_type=='bool'else str(value)
                    assertions.append('assert('+call+'=='+expect+');')
                elif not any(n[0]==index for n in negatives):negatives.append((index,call,error))
        (references/'main.nex').write_text('module oracle;'+''.join(imports)+'fn agree()->unit{'+''.join(assertions)+'}fn main()->unit{agree();}test fn agreement()->unit{agree();}')
        for argv in [('eval',),('test','--profile','release'),('test','--target','web')]:assert json.loads(run('NEX-agreement',[compiler,*argv,'--json'],references))['ok']
        for index,call,error in negatives:
            root=out/('reference-error-'+str(index));root.mkdir();manifest(root);(root/'f.nex').write_bytes((references/('f'+str(index)+'.nex')).read_bytes());(root/'main.nex').write_text('module failure;import "./f.nex" as c'+str(index)+';fn main()->unit{'+call+';}')
            value=json.loads(run('NEX-trap',[compiler,'eval','--json'],root,expected=1));assert value['code']=={2:'E_DIV_ZERO',3:'E_ASSERT',7:'E_FLOAT'}[error]
        prepared=out/'owned-f64-source-preparation'
        run('owned-f64-preparation',[sys.executable,'-B',source.parent/'owned-cuda-codegen/prepare.py','--compiler',compiler,'--resources',resources,'--emitter',emitter,'--frontend-archive',frontend,'--source-project',out/'f64_add','--symbol','transform','--source-only','--output',prepared])
        proof=json.loads((prepared/'preparation/report.json').read_bytes())
        assert proof['all_f64_interface'] and proof['f64_transport']['implemented'] and len(proof['signature_sha256'])==11 and not proof['native_provider_built']
        assert all(sha(p)==h for p,h in pins.items())
        report.update(ok=True,source_fixtures=len(fixtures()),emitted_layout_cases=len(report['cases']),lane_results_checked=sum(len(c['lanes'])for c in report['cases']),
            actual_IR_PTX_variants=len(report['PTX_variants']),positive_NEX_assertions=len(assertions),NEX_reference_native_TypeScript_agreement=True,
            original_error_precedence_and_finite_float_traps_checked=True,owned_f64_transport_accepted=False,actual_NVRTC_or_GPU_execution=False)
    except BaseException as error:
        report['error']=repr(error);raise
    finally:save()
    print(json.dumps({k:report[k]for k in ['ok','source_fixtures','emitted_layout_cases','lane_results_checked','actual_IR_PTX_variants','positive_NEX_assertions','actual_NVRTC_or_GPU_execution']}))


if __name__=='__main__':main()
