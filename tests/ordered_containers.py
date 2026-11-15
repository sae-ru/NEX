"""Persistent AVL containers: independent deterministic oracle and backend agreement."""
import hashlib
import json
from pathlib import Path
import shutil
import unittest
import support as h
import standard_library as helpers


PREFIX='''module ordered_cases;
import "std/ordered_map.nex" as maps;
import "std/ordered_set.nex" as sets;
fn compare(a:i64,b:i64)->i64 {if a<b{return -1;}if a>b{return 1;}return 0;}
'''


def corpus():
    # This fixed operation schedule is deliberately reproducible. Expected keys
    # and values come from Python dict/sorted, not from a second AVL algorithm.
    operations=[(True,(index*17)%61,index) for index in range(80)]
    operations += [(False,(index*19)%79,0) for index in range(75)]
    operations += [(True,index,-index) for index in range(-12,13)]
    operations += [(False,index,0) for index in range(-12,80)]
    model={};keys=[];values=[]
    for insert,key,value in operations:
        if insert:model[key]=value
        else:model.pop(key,None)
        ordered=sorted(model);keys.append(ordered);values.append([model[k] for k in ordered])
    def literal(value):return json.dumps(value,separators=(',',':'))
    schedule='['+','.join(f'Operation({str(insert).lower()},{key},{value})' for insert,key,value in operations)+']'
    return PREFIX+'''
struct Operation {insert:bool;key:i64;value:i64;}
struct Key {group:i64;label:str;}
fn group(a:Key,b:Key)->i64{return compare(a.group,b.group);}
fn floating(a:f64,b:f64)->i64{if a<b{return -1;}if a>b{return 1;}return 0;}
fn rotations()->unit {
 let orders:list<list<i64>>=[[3,2,1],[1,2,3],[3,1,2],[1,3,2]];
 var index:i64=0;
 while index<len(orders) {
  var table:maps::Map<i64,i64>=maps::empty(compare);var step:i64=0;
  while step<3 {table=maps::put(table,orders[index][step],step);assert(maps::validate(table));step=step+1;}
  assert(maps::keys(table)==[1,2,3] && maps::height(table)==2);
  let old:maps::Map<i64,i64>=table;
  table=maps::remove(table,2);assert(maps::keys(table)==[1,3] && maps::validate(table));
  table=maps::remove(table,1);assert(maps::keys(table)==[3] && maps::validate(table));
  table=maps::remove(table,3);assert(maps::is_empty(table) && maps::height(table)==0 && maps::validate(table));
  assert(maps::keys(old)==[1,2,3]);index=index+1;
 }
}
fn comparators()->unit {
 let low:i64=-9223372036854775808;let high:i64=9223372036854775807;
 var numbers:maps::Map<i64,str>=maps::empty(compare);
 numbers=maps::put(maps::put(numbers,high,"high"),low,"low");
 assert(maps::keys(numbers)==[low,high] && maps::validate(numbers));
 var direction:i64=-1;
 let reverse:fn(i64,i64)->i64=fn(a:i64,b:i64)->i64{return direction*compare(a,b);};
 direction=1;
 let reversed:maps::Map<i64,i64>=maps::put(maps::put(maps::empty(reverse),1,10),2,20);
 assert(maps::keys(reversed)==[2,1] && maps::validate(reversed));
 var labels:maps::Map<Key,list<str>>=maps::empty(group);
 labels=maps::put(labels,Key(1,"first"),["Я","🌍"]);
 let old:maps::Map<Key,list<str>>=labels;
 labels=maps::put(labels,Key(1,"replacement"),["new"]);
 assert(maps::size(labels)==1 && maps::keys(labels)[0].label=="first");
 assert(unwrap(maps::get(labels,Key(1,"lookup")))==["new"]);
 assert(unwrap(maps::get(old,Key(1,"lookup")))==["Я","🌍"]);
 assert(maps::entries(labels)[0].value==["new"] && maps::validate(labels));
 labels=maps::remove(labels,Key(1,"different"));assert(maps::is_empty(labels));
 var floats:maps::Map<f64,bool>=maps::empty(floating);
 floats=maps::put(maps::put(maps::put(floats,1.5,true),-0.0,false),0.0,true);
 assert(maps::size(floats)==2 && maps::keys(floats)==[0.0,1.5] && maps::validate(floats));
}
fn set_algebra()->unit {
 let left:sets::Set<Key>=sets::add(sets::add(sets::empty(group),Key(1,"left")),Key(2,"two"));
 let exact:fn(Key,Key)->i64=fn(a:Key,b:Key)->i64{
  let order:i64=compare(a.group,b.group);if order!=0{return order;}return compare(len(a.label),len(b.label));
 };
 let right:sets::Set<Key>=sets::add(sets::add(sets::empty(exact),Key(1,"r")),Key(1,"longer"));
 assert(sets::size(right)==2);
 let united:sets::Set<Key>=sets::union(left,right);
 let common:sets::Set<Key>=sets::intersection(left,right);
 let apart:sets::Set<Key>=sets::difference(left,right);
 assert(sets::size(united)==2 && sets::items(united)[0].label=="left");
 assert(sets::items(common)==[Key(1,"left")] && sets::items(apart)==[Key(2,"two")]);
 assert(sets::validate(united) && sets::validate(common) && sets::validate(apart));
 assert(sets::items(left)==[Key(1,"left"),Key(2,"two")]);
 assert(sets::is_empty(sets::remove(sets::remove(left,Key(1,"a")),Key(2,"b"))));
 assert(!sets::has(left,Key(3,"missing")) && sets::height(left)==2);
}
fn representations()->unit {
 let one:maps::Node<i64,i64>=maps::Node(1,10,[],[],1,1);
 assert(!maps::validate(maps::Map([one,one],compare)));
 assert(!maps::validate(maps::Map([maps::Node(1,10,[],[],1,9223372036854775807)],compare)));
 assert(!maps::validate(maps::Map([maps::Node(1,10,[],[],1,-1)],compare)));
 assert(!maps::validate(maps::Map([maps::Node(1,10,[],[],0,1)],compare)));
 assert(!maps::validate(maps::Map([maps::Node(1,10,[],[one],2,2)],compare)));
 var root:list<maps::Node<i64,i64>>=[];var index:i64=0;
 while index<92 {root=[maps::Node(index,index,root,[],index+1,index+1)];index=index+1;}
 assert(!maps::validate(maps::Map(root,compare)));
}
fn bulk()->unit {
 var ascending:maps::Map<i64,i64>=maps::empty(compare);
 var descending:maps::Map<i64,i64>=maps::empty(compare);var index:i64=0;
 while index<512 {
  ascending=maps::put(ascending,index,index);descending=maps::put(descending,511-index,511-index);index=index+1;
 }
 let expected:list<i64>=list(512,fn(i:i64)->i64{return i;});
 assert(maps::keys(ascending)==expected && maps::keys(descending)==expected);
 assert(maps::height(ascending)<=12 && maps::height(descending)<=12);
 assert(maps::validate(ascending) && maps::validate(descending));
 let old:maps::Map<i64,i64>=descending;index=0;
 while index<512 {
  descending=maps::remove(descending,index);
  if index%32==0 {assert(maps::validate(descending));}index=index+1;
 }
 assert(maps::is_empty(descending) && maps::validate(descending) && maps::size(old)==512 && maps::keys(old)==expected);
}
fn trace()->unit {
 let operations:list<Operation>='''+schedule+''';
 let keys:list<list<i64>>='''+literal(keys)+''';
 let values:list<list<i64>>='''+literal(values)+''';
 var table:maps::Map<i64,i64>=maps::empty(compare);var index:i64=0;
 while index<len(operations) {
  let before:maps::Map<i64,i64>=table;let old_keys:list<i64>=maps::keys(before);
  let old_values:list<i64>=maps::values(before);let op:Operation=operations[index];
  if op.insert {table=maps::put(table,op.key,op.value);}else{table=maps::remove(table,op.key);}
  assert(maps::keys(table)==keys[index] && maps::values(table)==values[index]);
  assert(maps::keys(before)==old_keys && maps::values(before)==old_values);
  assert(maps::size(table)==len(keys[index]) && maps::validate(table));
  let entries:list<maps::Entry<i64,i64>>=maps::entries(table);var item:i64=0;
  while item<len(entries) {
   assert(entries[item].key==keys[index][item] && entries[item].value==values[index][item]);
   assert(maps::has(table,entries[item].key) && unwrap(maps::get(table,entries[item].key))==entries[item].value);item=item+1;
  }
  assert(!maps::has(table,9999) && error_code(maps::get(table,9999))=="E_NOT_FOUND");index=index+1;
 }
 assert(maps::is_empty(table));
}
fn main()->unit!{io}{rotations();comparators();set_algebra();representations();bulk();trace();print("ordered-oracle-ok");}
'''


class OrderedContainers(h.ToolchainCase):
    run_child=helpers.StandardLibrary.run_child
    strict_ts=helpers.StandardLibrary.strict_ts
    typescript=helpers.StandardLibrary.typescript

    def test_deterministic_oracle_native_reference_strict_typescript(self):
        compiler_pin=hashlib.sha256(Path(h.NEX).read_bytes()).hexdigest()
        self.source(corpus());checked=self.cli('check')
        reference=self.cli('eval','--steps','30000000',timeout=180)
        self.assertEqual(reference['stdout'],'ordered-oracle-ok\n')
        native={}
        for profile in ('debug','release'):
            native[profile]=self.cli('run','--profile',profile,timeout=240)
            self.assertEqual(native[profile]['stdout'],'ordered-oracle-ok\n')
        typescript=self.typescript();self.assertEqual(typescript,'ordered-oracle-ok\n')
        self.assertEqual(hashlib.sha256(Path(h.NEX).read_bytes()).hexdigest(),compiler_pin)
        print(json.dumps({'schema':'nex.ordered-containers-agreement/1','ok':True,
            'compiler_sha256':compiler_pin,
            'program_sha256':hashlib.sha256(self.file.read_bytes()).hexdigest(),
            'revision':checked['revision'],'reference':reference,'native':native,
            'typescript':{'strict':True,'executed':True,'stdout':typescript},
            'deterministic_trace_operations':272,'bulk_entries':512,'insertion_rotation_orders':4,
            'complete_SDK_workflow_claimed':False}))

    def test_explicit_029_example(self):
        for name in ('nex.json','main.nex','nex.lock.json'):
            shutil.copy2(h.REPO/'examples/ordered-containers'/name,self.root/name)
        before=(self.root/'nex.lock.json').read_bytes()
        self.cli('check')
        self.assertEqual(self.cli('eval')['stdout'],'ordered-containers-ok\n')
        self.assertEqual((self.root/'nex.lock.json').read_bytes(),before)

    def test_callback_effects_and_signature_are_checked(self):
        for comparator,code in (('fn noisy(a:i64,b:i64)->i64!{io}{print(a);return b;}','E_EFFECT'),
                                ('fn noisy(a:i64,b:i64)->bool{return a<b;}','E_TYPE')):
            with self.subTest(comparator=comparator):
                self.source(PREFIX+comparator+'\nfn main()->unit{let table:maps::Map<i64,str>=maps::empty(noisy);}\n')
                rejected=self.cli('check',ok=False)
                self.assertEqual(rejected['code'],code)

    def test_compiled_pins_and_public_API(self):
        descriptor=self.cli('describe','--field','standard_library')['value']['modules']
        for name in ('ordered_map','ordered_set'):
            path=h.REPO/f'lib/{name}.nex';module=descriptor[name]
            self.assertEqual(module['sha256'],hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual(module['representation'],'persistent AVL tree')
            self.assertFalse(module['mutation'])


if __name__=='__main__':unittest.main()
