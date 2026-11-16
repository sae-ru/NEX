"""Hand-written multi-unit reference programs shared by all three engines."""

def bundle(files):
    return {'schema':'nex.private-reference-sources/1','entry':'main.nex','files':files}


def module_cases():
    cases = [
        {'name':'module-alias-snapshot','output':'42\nold\nnew\n','bundle':bundle({
            'main.nex':'''module app;
import "./counter.nex" as counter;
fn main()->unit!{state,io}{
 let value:counter::Counter=counter::make();
 let alias:counter::Counter=value;let old:str=cell_read(value.label);
 counter::change(alias);cell_collect();
 print(cell_read(value.number));print(old);print(cell_read(value.label));
}
''',
            'counter.nex':'''module counter;
pub struct Counter{number:cell<i64>;label:cell<str>;}
pub fn make()->Counter!{state}{return Counter(cell_new(1),cell_new("old"));}
pub fn change(value:Counter)->unit!{state}{cell_write(value.number,42);cell_write(value.label,"new");}
'''})},
        {'name':'module-partial-type-identities','output':'42\nЯ🌍\n','bundle':bundle({
            'main.nex':'''module app;
import "./left.nex" as left;
import "./right.nex" as right;
fn forward<F<_>,T>(value:F<T>)->F<T>{return value;}
fn main()->unit!{state,io}{
 let value:cell<i64>=cell_new(41);
 let first:left::Pair<cell<i64>,str>=forward<left::Pair<cell<i64>,_>,str>(left::Pair(value,"Я🌍"));
 let second:right::Pair<str,cell<i64>>=forward<right::Pair<str,_>,cell<i64>>(right::Pair("other",value));
 cell_write(second.second,42);cell_collect();print(cell_read(first.first));print(first.second);
}
''',
            'left.nex':'module left;pub struct Pair<A,B>{first:A;second:B;}',
            'right.nex':'module right;pub struct Pair<A,B>{first:A;second:B;}'})},
        {'name':'module-trait-associated-methods','output':'42\n43\n','bundle':bundle({
            'main.nex':'''module app;
import "./traits.nex" as ops;
fn read<T:ops::Content>(value:T)->ops::Content::Item<T>!{state}{return ops::Content<T>::get(value);}
fn main()->unit!{state,io}{
 let value:cell<i64>=cell_new(41);
 let converted:cell<str>=ops::Mapper<cell>::map<i64,str>(value,fn(number:i64)->str{return str(number+1);});
 let getter:fn(cell<i64>)->i64!{state}=ops::Content<cell<i64>>::get;
 cell_write(value,43);cell_collect();print(cell_read(converted));print(getter(value));assert(read(value)==43);
}
''',
            'traits.nex':'''module traits;
pub trait Content{type Item;fn get(value:Self)->Content::Item<Self>!{state};}
fn extract<T>(value:cell<T>)->T!{state}{return cell_read(value);}
impl content<T>:Content for cell<T>{type Item=T;get=extract<T>;}
pub trait Mapper<Self<_>>{fn map<A,B>(value:Self<A>,apply:fn(A)->B)->Self<B>!{state};}
fn map_cell<A,B>(value:cell<A>,apply:fn(A)->B)->cell<B>!{state}{return cell_new(apply(cell_read(value)));}
impl mapper:Mapper for cell{map=map_cell;}
'''})},
        {'name':'module-source-error-finally','output':'caught\n42\n','bundle':bundle({
            'main.nex':'''module app;
import "./errors.nex" as errors;
fn main()->unit!{state,throw,io}{
 let value:cell<i64>=cell_new(0);
 try{errors::raise(value);}catch(packet:errors::Packet<cell<i64>>){cell_collect();assert(packet.value==value);print(packet.message);print(cell_read(packet.value));}
}
''',
            'errors.nex':'''module errors;
pub struct Packet<T>{value:T;message:str;}
pub fn raise(value:cell<i64>)->unit!{state,throw}{
 try{throw(Packet(value,"caught"));}finally{cell_collect();cell_write(value,42);}
}
'''})},
        {'name':'module-cycles-closure-return','output':'42\n42\n','bundle':bundle({
            'main.nex':'''module app;
import "./graph.nex" as graph;
fn main()->unit!{state,io}{
 let node:cell<graph::Node>=graph::cycle();
 let reader:fn()->i64!{state}=graph::reader(node);
 cell_collect();print(reader());cell_write(node,graph::Node(43,[]));cell_collect();print(reader());
}
''',
            'graph.nex':'''module graph;
pub struct Node{value:i64;next:list<cell<Node>>;}
pub fn cycle()->cell<Node>!{state}{let node:cell<Node>=cell_new(Node(42,[]));cell_write(node,Node(42,[node]));return node;}
pub fn reader(node:cell<Node>)->fn()->i64!{state}!{state}{
 let snapshot:Node=cell_read(node);return fn()->i64!{state}{cell_collect();assert(snapshot.next[0]==node);return snapshot.value;};
}
'''})},
        {'name':'module-defaults-contracts','output':'42\n','bundle':bundle({
            'main.nex':'''module app;
import "./values.nex" as values;
fn main()->unit!{state,io}{
 let value:cell<i64>=cell_new(41);let same:cell<i64>=values::keep(value);
 cell_write(same,42);cell_collect();print(cell_read(values::marker<cell<i64>>(value).value));
 let saved:values::Marker<cell<i64>>=values::Marker<cell<i64>>(same);assert(saved.value==value);
}
''',
            'values.nex':'''module values;
pub struct Marker<T,U=T>{value:T;}
pub fn marker<T,U=T>(value:T)->Marker<T,U>{return Marker<T,U>(value);}
pub fn keep<T>(value:T)->T requires(value==value) ensures(result=>result==value){return value;}
'''})},
        {'name':'module-client-reachability','output':'42\n','absent':'SERVER_MODULE_SENTINEL','bundle':bundle({
            'main.nex':'''module app;
import "./provider.nex" as provider;
import "./server.nex" as hidden;
fn main()->unit!{state,io}{let value:cell<i64>=provider::make();cell_collect();print(cell_read(value));}
''',
            'provider.nex':'module provider;pub fn make()->cell<i64>!{state}{return cell_new(42);}',
            'server.nex':'module hidden;pub server fn secret()->str{return "SERVER_MODULE_SENTINEL";}'})},
        {'name':'module-fatal-cleanup','error':'E_OVERFLOW','bundle':bundle({
            'main.nex':'''module app;
import "./failure.nex" as failure;
fn main()->unit!{state,io}{let value:cell<i64>=cell_new(1);try{failure::fail(value);}finally{print("wrong-finalizer");}}
''',
            'failure.nex':'''module failure;
pub fn fail(value:cell<i64>)->unit!{state}{cell_write(value,42);let overflow:i64=9223372036854775807+1;}
'''})},
        {'name':'module-uncaught-source-cleanup','error':'E_SOURCE_EXCEPTION','bundle':bundle({
            'main.nex':'''module app;
import "./errors.nex" as errors;
fn main()->unit!{state,throw}{errors::raise();}
''',
            'errors.nex':'''module errors;
pub struct Packet{value:cell<i64>;}
pub fn raise()->unit!{state,throw}{let value:cell<i64>=cell_new(42);throw(Packet(value));}
'''})},
    ]
    # The root source remains identical; changing only an imported body must
    # change that unit's map hash as well as the actual result.
    from copy import deepcopy
    changed=deepcopy(next(case for case in cases if case['name']=='module-client-reachability'))
    changed['name']='module-import-change';changed['output']='43\n'
    changed['bundle']['files']['provider.nex']=changed['bundle']['files']['provider.nex'].replace('cell_new(42)','cell_new(43)')
    return cases+[changed]
