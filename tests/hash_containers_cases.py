"""Deterministic dict/set oracles; no second trie implementation."""
import json


def literal(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def hash_bytes(value):
    result = 0
    for byte in value:
        result = (result * 257 + byte + 1) % (1 << 32)
    return result


def corpus():
    checks = []
    texts = ['', '\0', 'a\0b', 'λ🙂', 'e\u0301', '\ufeff', 'Я' * 64]
    for text in texts:
        checks.append(f'assert(hash::text({literal(text)})=={hash_bytes(text.encode())});')
    for value in [b'', bytes(range(256)), bytes([0, 255, 0, 128]), b'abc' * 100]:
        checks.append(f'assert(hash::binary(unwrap(bytes({literal(list(value))})))=={hash_bytes(value)});')
    trace = [(True, (index * 17) % 83 - 35, index) for index in range(125)]
    trace += [(False, (index * 19) % 91 - 40, 0) for index in range(85)]
    trace += [(True, value, index) for index, value in enumerate([-9223372036854775808, 9223372036854775807, -1, 0, 16, -16])]
    trace += [(False, value, 0) for value in [-9223372036854775808, 9223372036854775807, -1, 0, 16, -16]]
    model = {}
    keys, values = [], []
    for insert, key, value in trace:
        if insert:
            model[key] = value
        else:
            model.pop(key, None)
        # Signed remainder agrees with checked NEX, including negative hashes.
        reduced = lambda key: (abs(key) % 7) * (-1 if key < 0 else 1)
        order = lambda key: tuple((reduced(key) & ((1 << 64) - 1)) >> shift & 15 for shift in range(0, 64, 4))
        ordered = sorted(model, key=order)  # stable: retain bucket insertion order.
        keys.append(ordered)
        values.append([model[key] for key in ordered])
    schedule = '[' + ','.join(f'Operation({str(insert).lower()},{key},{value})' for insert, key, value in trace) + ']'
    source = '''module hash_cases;
import "std/hash.nex" as hash;
import "std/hash_map.nex" as maps;
import "std/hash_set.nex" as sets;
import "std/list.nex" as seq;
struct Operation{insert:bool;key:i64;value:i64;}
struct Key{group:i64;label:str;}
fn collision(value:i64)->i64{return value%7;}
fn constant(value:i64)->i64{return 0;}
fn key_hash(value:Key)->i64{return value.group;}
fn key_equal(a:Key,b:Key)->bool{return a.group==b.group;}
fn exact_hash(value:Key)->i64{return value.group*100+len(value.label);}
fn exact_equal(a:Key,b:Key)->bool{return a==b;}
fn hashes()->unit{
 assert(hash::integer(-9223372036854775808)==-9223372036854775808);
 assert(hash::integer(9223372036854775807)==9223372036854775807);
 assert(hash::boolean(false)==0&&hash::boolean(true)==1);
 HASH_CHECKS
}
fn longest_path()->unit{
 var table:maps::Map<i64,str>=maps::empty(hash::integer,hash::equal<i64>);
 assert(maps::size(table)==0&&maps::height(table)==0&&maps::validate(table));
 assert(maps::entries(table)==[]&&maps::keys(table)==[]&&maps::values(table)==[]);
 assert(error_code(maps::get(table,0))=="E_NOT_FOUND");
 table=maps::put(maps::put(table,0,"zero"),-9223372036854775808,"minimum");
 assert(maps::height(table)==17&&maps::validate(table));
 assert(maps::keys(table)==[0,-9223372036854775808]);
 let old:maps::Map<i64,str>=table;
 table=maps::remove(table,0);
 assert(maps::height(table)==1&&maps::keys(table)==[-9223372036854775808]&&maps::validate(table));
 assert(maps::size(old)==2&&unwrap(maps::get(old,0))=="zero");
 table=maps::remove(table,-9223372036854775808);assert(maps::is_empty(table)&&maps::validate(table));
 let boundaries:list<i64>=[-9223372036854775808,-9223372036854775807,-16,-1,0,1,15,16,9223372036854775806,9223372036854775807];
 var all:maps::Map<i64,i64>=maps::empty(hash::integer,hash::equal<i64>);var index:i64=0;
 while index<len(boundaries){all=maps::put(all,boundaries[index],index);assert(maps::validate(all));index=index+1;}
 index=0;while index<len(boundaries){assert(unwrap(maps::get(all,boundaries[index]))==index);index=index+1;}
 index=0;while index<len(boundaries){all=maps::remove(all,boundaries[index]);assert(maps::validate(all)&&maps::height(all)<=17);index=index+1;}
 assert(maps::is_empty(all));
}
fn representatives()->unit{
 var table:maps::Map<Key,list<str>>=maps::empty(key_hash,key_equal);
 table=maps::put(table,Key(1,"first"),["λ","🙂"]);
 let old:maps::Map<Key,list<str>>=table;
 table=maps::put(table,Key(1,"replacement"),["new"]);
 assert(maps::size(table)==1&&maps::keys(table)[0].label=="first"&&maps::validate(table));
 assert(unwrap(maps::get(table,Key(1,"lookup")))==["new"]);
 assert(unwrap(maps::get(old,Key(1,"old")))==["λ","🙂"]);
 table=maps::remove(table,Key(1,"other"));assert(maps::is_empty(table));
 var offset:i64=0;
 let captured:fn(i64)->i64=fn(value:i64)->i64{return value+offset;};offset=7;
 let snapshot:maps::Map<i64,bool>=maps::put(maps::empty(captured,hash::equal<i64>),1,true);
 assert(snapshot.root[0].items[0].hash==1&&maps::has(snapshot,1)&&maps::validate(snapshot));
}
fn bucket()->unit{
 var table:maps::Map<i64,i64>=maps::empty(constant,hash::equal<i64>);var index:i64=0;
 while index<24{table=maps::put(table,index,index*2);index=index+1;}
 assert(maps::size(table)==24&&maps::height(table)==1&&maps::validate(table));
 let old:maps::Map<i64,i64>=table;
 table=maps::put(maps::put(table,0,99),23,98);
 table=maps::remove(maps::remove(maps::remove(table,12),0),23);
 assert(maps::size(table)==21&&maps::validate(table)&&maps::size(old)==24);
 assert(unwrap(maps::get(old,0))==0&&!maps::has(table,12));
 assert(!maps::has(table,999)&&error_code(maps::get(table,999))=="E_NOT_FOUND");
 index=1;while index<23{table=maps::remove(table,index);index=index+1;}
 assert(maps::is_empty(table)&&maps::validate(table));
}
fn algebra()->unit{
 let left:sets::Set<Key>=sets::add(sets::add(sets::empty(key_hash,key_equal),Key(1,"left")),Key(2,"two"));
 let right:sets::Set<Key>=sets::add(sets::add(sets::empty(exact_hash,exact_equal),Key(1,"r")),Key(1,"longer"));
 assert(sets::size(right)==2);
 let united:sets::Set<Key>=sets::union(left,right);
 let common:sets::Set<Key>=sets::intersection(left,right);
 let apart:sets::Set<Key>=sets::difference(left,right);
 assert(sets::size(united)==2&&sets::items(united)[0].label=="left");
 assert(sets::items(common)==[Key(1,"left")]&&sets::items(apart)==[Key(2,"two")]);
 assert(sets::validate(united)&&sets::validate(common)&&sets::validate(apart));
 assert(sets::size(left)==2&&sets::size(right)==2);
 assert(sets::is_empty(sets::remove(sets::remove(left,Key(1,"a")),Key(2,"b")))) ;
}
fn bulk()->unit{
 var table:maps::Map<i64,i64>=maps::empty(hash::integer,hash::equal<i64>);var index:i64=0;
 while index<1024{table=maps::put(table,index,index*3);index=index+1;}
 assert(maps::size(table)==1024&&maps::height(table)<=17&&maps::validate(table));
 let original:maps::Map<i64,i64>=table;
 index=0;while index<1024{assert(unwrap(maps::get(table,index))==index*3);index=index+1;}
 let all:list<maps::Entry<i64,i64>>=maps::entries(table);
 assert(seq::sort(maps::keys(table))==list(1024,fn(index:i64)->i64{return index;}));
 index=0;while index<len(all){assert(all[index].value==all[index].key*3);index=index+1;}
 index=0;while index<1024{table=maps::remove(table,index);index=index+1;}
 assert(maps::is_empty(table)&&maps::size(original)==1024&&maps::validate(original));
}
fn representations()->unit{
 let one:maps::Node<i64,i64>=maps::Node([maps::Item(1,1,10)],[],[],1);
 assert(!maps::validate(maps::Map([one,one],hash::integer,hash::equal<i64>)));
 assert(!maps::validate(maps::Map([maps::Node([maps::Item(2,1,10)],[],[],1)],hash::integer,hash::equal<i64>)));
 assert(!maps::validate(maps::Map([maps::Node([maps::Item(1,1,10),maps::Item(1,1,11)],[],[],2)],hash::integer,hash::equal<i64>)));
 assert(!maps::validate(maps::Map([maps::Node<i64,i64>([],[],[],0)],hash::integer,hash::equal<i64>)));
 assert(!maps::validate(maps::Map([maps::Node([],[1,1],[one,one],2)],hash::integer,hash::equal<i64>)));
 assert(!maps::validate(maps::Map([maps::Node([],[2],[one],1)],hash::integer,hash::equal<i64>)));
 assert(!maps::validate(maps::Map([maps::Node([],[1],[one],2)],hash::integer,hash::equal<i64>)));
}
fn trace()->unit{
 let operations:list<Operation>=SCHEDULE;
 let keys:list<list<i64>>=EXPECTED_KEYS;
 let values:list<list<i64>>=EXPECTED_VALUES;
 var table:maps::Map<i64,i64>=maps::empty(collision,hash::equal<i64>);var index:i64=0;
 while index<len(operations){
  let before:maps::Map<i64,i64>=table;let old_keys:list<i64>=maps::keys(before);let old_values:list<i64>=maps::values(before);
  let operation:Operation=operations[index];
  if operation.insert{table=maps::put(table,operation.key,operation.value);}else{table=maps::remove(table,operation.key);}
  assert(maps::keys(before)==old_keys&&maps::values(before)==old_values);
  assert(maps::keys(table)==keys[index]&&maps::values(table)==values[index]&&maps::size(table)==len(keys[index]));
  assert(maps::validate(table)&&maps::height(table)<=17);
  let entries:list<maps::Entry<i64,i64>>=maps::entries(table);var item:i64=0;
  while item<len(entries){assert(entries[item].key==keys[index][item]&&entries[item].value==values[index][item]);assert(unwrap(maps::get(table,entries[item].key))==entries[item].value);item=item+1;}
  assert(!maps::has(table,9999));index=index+1;
 }
}
fn main()->unit!{io}{hashes();longest_path();representatives();bucket();algebra();bulk();representations();trace();print("hash-oracle-ok");}
'''
    source = source.replace('HASH_CHECKS', '\n '.join(checks)).replace('SCHEDULE', schedule)
    return source.replace('EXPECTED_KEYS', literal(keys)).replace('EXPECTED_VALUES', literal(values)), len(trace)
