"""Bounded GPU lists: source semantics, exact wire bounds and immutable values."""
import json
import os
import subprocess
import sys
import unittest
import cuda_values as fixed


def packed(items, width=1, capacity=4):
    words = [w for item in items for w in (item if isinstance(item, list) else [item])]
    assert len(words) == len(items)*width and len(items) <= capacity
    return [len(items), *words, *([0]*((capacity-len(items))*width))]


def fixtures():
    L=packed
    return [
      ('ops', '''pub fn transform(xs:list<i64>,i:i64)->list<i64>{let saved:list<i64>=xs;var changed:list<i64>=xs;changed=set(changed,i,9);assert(xs==saved);return push(changed,7)+[8];}
test fn oracle()->unit{assert(transform([1,2],1)==[1,9,7,8]);}''',
       lambda ids: [([L([1,2]),[1]],L([1,9,7,8]),0),([L([1,2,3]),[1]],[0]*5,10),([L([1,2,3,4]),[1]],[0]*5,10),([L([1]),[-1]],[0]*5,9),([L([1]),[9223372036854775807]],[0]*5,9),([L([]),[0]],[0]*5,9),([[-1,0,0,0,0],[0]],[0]*5,6),([[5,0,0,0,0],[0]],[0]*5,6),([[1,1,0,3,0],[0]],[0]*5,6)]),
      ('snapshots', '''pub fn transform(xs:list<i64>)->list<i64>{var a:list<i64>=xs;let saved:list<i64>=a;a=set(a,0,7);assert(xs==saved);assert(a!=saved);return saved;}
test fn oracle()->unit{assert(transform([1,2])==[1,2]);}''',
       lambda ids: [([L([1,2])],L([1,2]),0),([L([1,2,3,4])],L([1,2,3,4]),0)]),
      ('sum', '''fn sum(xs:list<f64>)->f64{var i:i64=0;var total:f64=0.0;while i<len(xs){total=total+xs[i];i=i+1;}return total;}
pub fn transform(xs:list<f64>)->f64{return sum(xs);}
test fn oracle()->unit{assert(transform([1.5,2.5,-0.0])==4.0);assert(transform([])==0.0);}''',
       lambda ids: [([L([fixed.fword(1.5),fixed.fword(2.5),fixed.fword(-0.0)])],[fixed.fword(4)],0),([L([])],[0],0),([L([0x7ff8000000000001])],[0],7),([[0,0x7ff8000000000001,0,0,0]],[0],6)]),
      ('floating', '''pub fn transform(xs:list<f64>)->list<f64>{assert(xs==[-0.0,2.0]);return set(xs,1,3.5);}
test fn oracle()->unit{assert(transform([0.0,2.0])==[0.0,3.5]);}''',
       lambda ids: [([L([fixed.fword(-0.0),fixed.fword(2)])],L([0,fixed.fword(3.5)]),0),([L([fixed.fword(0.0),fixed.fword(2)])],L([0,fixed.fword(3.5)]),0)]),
      ('nested', '''pub fn transform(xs:list<list<i64>>)->i64{return match xs{[[a,b],[]] if a>0=>a+b,[]=>0,[[_,_],[]] if false=>1/0,_=>len(xs)};}
test fn oracle()->unit{assert(transform([[40,2],[]])==42);assert(transform([[-1,2],[]])==2);assert(transform([])==0);}''',
       lambda ids: [([L([L([40,2]),L([])],5)],[42],0),([L([L([-1,2]),L([])],5)],[2],0),([L([],5)],[0],0),([L([[-1,0,0,0,0]],5)],[0],6),([L([[0,1,0,0,0]],5)],[0],6)]),
      ('record', '''pub struct Pair{n:i64;b:bool;}
pub fn transform(xs:list<Pair>)->result<list<Pair>>{let saved:list<Pair>=xs;let out:list<Pair>=set(xs,0,Pair(xs[0].n+1,false));assert(xs==saved);return ok(out);}
test fn oracle()->unit{assert(transform([Pair(41,true)])==ok([Pair(42,false)]));}''',
       lambda ids: [([L([[41,1]],2)],[1,*L([[42,0]],2)],0),([L([[41,2]],2)],[0]*10,6),([L([],2)],[0]*10,9)]),
      ('text', '''pub fn transform(xs:list<str>)->list<str>{assert(len("🌍")==1);return push(xs,"🌍");}
test fn oracle()->unit{assert(transform([""])==["","🌍"]);}''',
       lambda ids: [([L([0])],L([0,ids('🌍')]),0),([L([999])],[0]*5,6),([L([0,0,0,0])],[0]*5,10)]),
      ('order_set', '''pub fn transform(xs:list<i64>,i:i64,d:i64)->list<i64>{return set(xs,i,1/d);}
test fn oracle()->unit{assert(transform([1],0,1)==[1]);}''',
       lambda ids: [([L([1]),[-1],[0]],[0]*5,2),([L([1]),[-1],[1]],[0]*5,9)]),
      ('order_push', '''pub fn transform(xs:list<i64>,d:i64)->list<i64>{return push(xs,1/d);}
test fn oracle()->unit{assert(transform([],1)==[1]);}''',
       lambda ids: [([L([1,2,3,4]),[0]],[0]*5,2),([L([1,2,3,4]),[1]],[0]*5,10)]),
      ('order_concat', '''pub fn transform(xs:list<i64>,d:i64)->list<i64>{return xs+[1/d];}
test fn oracle()->unit{assert(transform([2],1)==[2,1]);}''',
       lambda ids: [([L([1,2,3,4]),[0]],[0]*5,2),([L([1,2,3,4]),[1]],[0]*5,10)]),
      ('enum', '''pub enum Item{Some(xs:list<bool>);Empty;}
pub fn transform(v:Item)->Item{return match v{Item::Some([true,x])=>Item::Some([x,false]),Item::Some(xs)=>Item::Some(push(xs,true)),Item::Empty()=>Item::Some([])};}
test fn oracle()->unit{assert(transform(Item::Some([true,true]))==Item::Some([true,false]));assert(transform(Item::Empty())==Item::Some([]));}''',
       lambda ids: [([[0,*L([1,1])]],[0,*L([1,0])],0),([[1,0,0,0,0,0]],[0,*L([])],0),([[0,*L([2])]],[0]*6,6),([[1,0,0,0,0,1]],[0]*6,6)])]


class CudaLists(fixed.CudaValues):
    cases=staticmethod(fixtures)
    emission_schema='nex.cuda-emission/3'
    value_schema='nex.cuda-values/2'
    emit_args=('--list-capacity','4')

    def test_public_preparation_and_limits(self):
        self.source('module gpu;fn transform(xs:list<list<i64>>)->list<list<i64>>{return xs;}fn main()->unit{}')
        self.assertEqual(self.cli('describe')['gpu_codegen']['cuda'],json.loads((fixed.harness.REPO/'llm/language-pack.json').read_text())['gpu_codegen']['cuda'])
        self.cli('check');r=self.cli('emit','--kind','cuda','--entry','transform')
        self.assertEqual(r['value_abi']['parameter_words'],[1057])
        out=self.root/'prepared'
        p=subprocess.run([sys.executable,'-B',str(fixed.harness.REPO/'experiments/owned-cuda-codegen/prepare.py'),'--compiler',fixed.harness.NEX,'--resources',str(fixed.harness.REPO),'--source-project',str(self.root),'--symbol','transform','--source-only','--list-capacity','4','--output',str(out)],capture_output=True,text=True,timeout=90)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        r=json.loads((out/'preparation/report.json').read_bytes());self.assertEqual(r['value_abi']['parameter_words'],[21]);self.assertEqual(r['maximum_batch_lanes'],32768//21)
        header=(out/'preparation/inputs/generated_kernel.h').read_text();self.assertIn('#define GENERATED_LIST_VALUES 1',header)
        status=self.root/'status.cpp';status.write_text('#include '+json.dumps(str(out/'preparation/inputs/module.cpp'))+'\nint main(){if(std::string(laneError(9))!="E_BOUNDS"||laneMessage(9,1)!="index is outside collection bounds"||std::string(laneError(10))!="E_LIMIT"||laneMessage(10,1)!="device list exceeds declared capacity")return 1;for(auto c:{7u,8u,11u,0xffffffffu}){bool bad=false;try{(void)laneError(c);}catch(const Error&e){bad=e.code=="E_DEVICE_ABI";}if(!bad)return 2;}return 0;}\n')
        doctor=self.cli('doctor');exe=self.root/('status.exe'if os.name=='nt'else'status');flags=['-std=c++20','-O1','-Wall','-Wextra','-Werror','-I'+str(fixed.harness.REPO/'runtime'),'-I'+str(out/'preparation/inputs')]
        if os.name=='nt':flags+=['--target='+doctor['host'],'--sysroot='+doctor['native_sysroot']]
        elif sys.platform!='darwin':flags+=['-ldl']
        p=subprocess.run([doctor['native_compiler'],*flags,str(status),'-o',str(exe)],capture_output=True,text=True,timeout=90);self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        p=subprocess.run([str(exe)],capture_output=True,text=True,timeout=20);self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        for value in ['0','1025','-1','1.5','99999999999999999999','']:
            self.assertEqual(self.cli('emit','--kind','cuda','--entry','transform','--list-capacity',value,ok=False)['code'],'E_OPTION')
        self.assertEqual(self.cli('emit','--kind','metal','--entry','transform','--list-capacity','4',ok=False)['code'],'E_OPTION')
        self.assertEqual(self.cli('emit','--kind','cuda','--entry','transform','--list-capacity','1024',ok=False)['code'],'E_GPU_LIMIT')
        self.source('module gpu;fn transform(xs:list<i64>)->list<i64>{return xs+[1,2,3];}fn main()->unit{}');self.cli('check')
        self.assertEqual(self.cli('emit','--kind','cuda','--entry','transform','--list-capacity','2',ok=False)['code'],'E_GPU_LIMIT')
        self.assertEqual(self.cli('emit','--kind','cuda','--entry','transform','--list-capacity','3')['value_abi']['result_words'],4)
        self.source('module gpu;fn transform(xs:list<i64>)->i64{return match xs{[a,b,c]=>a+b+c,_=>0};}fn main()->unit{}');self.cli('check')
        self.assertEqual(self.cli('emit','--kind','cuda','--entry','transform','--list-capacity','2',ok=False)['code'],'E_GPU_LIMIT')


if __name__=='__main__':
    unittest.main(argv=[__file__,'-v'])
