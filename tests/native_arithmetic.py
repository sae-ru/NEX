"""Observable checked-i64 agreement, boundary failures and evaluation order."""
import json
import random
import unittest
import support as harness

LOW=-(1<<63)
HIGH=(1<<63)-1
FUNCTIONS='''module arithmetic;
fn add(a:i64,b:i64)->i64{return a+b;}
fn sub(a:i64,b:i64)->i64{return a-b;}
fn mul(a:i64,b:i64)->i64{return a*b;}
fn div(a:i64,b:i64)->i64{return a/b;}
fn mod(a:i64,b:i64)->i64{return a%b;}
fn neg(a:i64)->i64{return -a;}
'''


def quotient(a,b):
    magnitude=abs(a)//abs(b)
    return -magnitude if (a<0)!=(b<0) else magnitude


class NativeArithmetic(harness.ToolchainCase):
    def test_boundary_and_seeded_random_values_agree_across_backends(self):
        randomizer=random.Random(20261018)
        boundaries=[LOW,LOW+1,-(1<<32),-(1<<31),-2,-1,0,1,2,(1<<31)-1,1<<32,HIGH-1,HIGH]
        pairs=[(a,b) for a in boundaries for b in boundaries]
        pairs += [(randomizer.randint(LOW,HIGH),randomizer.randint(LOW,HIGH)) for _ in range(100)]
        pairs += [(randomizer.randint(-(1<<31),1<<31),randomizer.randint(-(1<<31),1<<31)) for _ in range(50)]
        cases=[]
        for operation in ('add','sub','mul','div','mod'):
            for a,b in pairs:
                if operation in ('div','mod') and not b:continue
                value={'add':lambda:a+b,'sub':lambda:a-b,'mul':lambda:a*b,
                       'div':lambda:quotient(a,b),'mod':lambda:a-quotient(a,b)*b}[operation]()
                if not LOW<=value<=HIGH:continue
                cases.append((operation+'('+str(a)+','+str(b)+')',value))
        cases += [('neg('+str(value)+')',-value) for value in boundaries if value!=LOW]
        assertions=''.join('assert('+call+'=='+str(value)+');' for call,value in cases)
        self.source(FUNCTIONS+'test fn matrix()->unit{'+assertions+'}\nfn main()->unit{'+assertions+'}')
        self.assertGreater(len(cases),1000)
        self.cli('test','--target','web',timeout=180)
        for profile in ('debug','release','profile'):
            with self.subTest(profile=profile):
                self.assertEqual(self.cli('run','--profile',profile,timeout=240)['exit_code'],0)

    def test_every_integer_failure_keeps_reference_code_and_operation(self):
        bad=[('add('+str(HIGH)+',1)','E_OVERFLOW'),('add('+str(LOW)+',-1)','E_OVERFLOW'),
             ('sub('+str(LOW)+',1)','E_OVERFLOW'),('sub('+str(HIGH)+',-1)','E_OVERFLOW'),
             ('mul('+str(HIGH)+',2)','E_OVERFLOW'),('mul('+str(LOW)+',-1)','E_OVERFLOW'),
             ('neg('+str(LOW)+')','E_OVERFLOW'),('div('+str(LOW)+',-1)','E_OVERFLOW'),
             ('div(1,0)','E_DIV_ZERO'),('mod('+str(LOW)+',0)','E_DIV_ZERO')]
        entries=''.join('fn failure_'+str(i)+'()->i64{return '+call+';}\n' for i,(call,_) in enumerate(bad))
        self.source(FUNCTIONS+entries+'fn main()->i64{return 0;}')
        for i,(_,code) in enumerate(bad):
            entry='failure_'+str(i);expected=self.cli('eval','--entry',entry,ok=False)
            self.assertEqual(expected['code'],code)
            for profile in ('debug','release'):
                with self.subTest(entry=entry,profile=profile):
                    native=self.cli('run','--entry',entry,'--profile',profile,ok=False,timeout=150)
                    self.assertEqual(native['exit_code'],70)
                    record=native['native_diagnostics']['diagnostics'][0]
                    self.assertEqual(record['status'],'mapped')
                    self.assertEqual(record['report']['code'],code)
                    self.assertEqual(record['operation_id'],expected['operation_id'])
                    self.assertEqual(record['operation_site'],expected['operation_site'])

    def test_loop_remainders_and_nested_side_effects_preserve_order(self):
        self.source(FUNCTIONS+'''fn mark(value:i64)->i64!{io}{print(value);return value;}
fn main()->unit!{io}{
 var index:i64=0;var value:i64=-9223372036854775808;
 while index<5{value=mod(value,-1);index=add(index,1);}
 assert(value==0);print(mul(mark(9223372036854775807),mark(2)));
}''')
        expected=self.cli('eval',ok=False)
        for profile in ('debug','release'):
            native=self.cli('run','--profile',profile,ok=False,timeout=150)
            self.assertEqual(native['stdout'],str(HIGH)+'\n2\n')
            record=native['native_diagnostics']['diagnostics'][0]
            self.assertEqual(record['operation_id'],expected['operation_id'])
            self.assertEqual(record['report']['code'],'E_OVERFLOW')


if __name__=='__main__':unittest.main()
