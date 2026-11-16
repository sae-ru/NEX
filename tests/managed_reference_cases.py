"""One hand-written source corpus for reference/native/private TypeScript."""
import json
import re


def source_cases(root):
    source = (root/'tests/managed_references.cpp').read_text()
    pattern = r'runs\(R"nex\((.*?)\)nex",("(?:[^"\\]|\\.)*"(?:\s*"(?:[^"\\]|\\.)*")*)(?:,\{([^}]*)\})?\);'
    cases = []
    for index,match in enumerate(re.finditer(pattern,source,re.S)):
        expected = ''.join(json.loads(part) for part in re.findall(r'"(?:[^"\\]|\\.)*"',match[2]))
        limits = [int(value) for value in match[3].split(',')] if match[3] else [1048576,4194304,16777216]
        cases.append({'name':'core-'+str(index+1),'source':match[1],'output':expected,'limits':limits})
    assert len(cases)==9,('core reference source extraction changed',len(cases))
    cases += [
        {'name':'bool-float-bytes','source':'fn main()->unit!{state,io}{let flag:cell<bool>=cell_new(false);cell_write(flag,true);print(cell_read(flag));let real:cell<f64>=cell_new(1.25);cell_write(real,cell_read(real)+0.5);assert(cell_read(real)==1.75);let octets:cell<bytes>=cell_new(utf8_bytes("Я🌍"));let old:bytes=cell_read(octets);cell_write(octets,utf8_bytes("new"));assert(unwrap(decode_utf8(old))=="Я🌍");print("scalar-octets-ok");}','output':'true\nscalar-octets-ok\n'},
        {'name':'uncaught-cell','source':'fn main()->unit!{state,throw}{let value:cell<i64>=cell_new(1);throw(value);}','error':'E_SOURCE_EXCEPTION'},
        {'name':'overflow-cleanup','source':'struct Node{next:list<cell<Node>>;}fn main()->unit!{state,io}{let value:cell<Node>=cell_new(Node([]));cell_write(value,Node([value]));try{let bad:i64=9223372036854775807+1;}finally{print("wrong-finalizer");}}','error':'E_OVERFLOW'},
        {'name':'limit-cleanup','source':'fn main()->unit!{state}{let a:cell<i64>=cell_new(1);let b:cell<i64>=cell_new(2);let c:cell<i64>=cell_new(3);}','limits':[2,8,16],'error':'E_CELL_LIMIT'},
    ]
    cases += [
        {'name':'operand-root','limits':[1,8,16],'output':'42\n7\n','source':r'''
fn first()->cell<i64>!{state}{return cell_new(41);}
fn second()->i64!{state}{cell_collect();return 1;}
fn sum(value:cell<i64>,extra:i64)->i64!{state}{return cell_read(value)+extra;}
fn main()->unit!{state,io}{print(sum(first(),second()));cell_collect();let next:cell<i64>=cell_new(7);print(cell_read(next));}
'''},
        {'name':'closure-operand-root','limits':[1,12,16],'output':'42\n','source':r'''
fn callback()->fn(i64)->i64!{state}!{state}{let value:cell<i64>=cell_new(42);return fn(extra:i64)->i64!{state}{return cell_read(value)+extra;};}
fn extra()->i64!{state}{cell_collect();return 0;}
fn main()->unit!{state,io}{print(callback()(extra()));}
'''},
        {'name':'consumed-operand-retirement','limits':[1,8,16],'output':'3\n','source':r'''
fn main()->unit!{state,io}{print(cell_read(cell_new(1))+cell_read(cell_new(2)));}
'''},
        {'name':'return-through-finally','limits':[1,8,16],'output':'42\n','source':r'''
fn value()->cell<i64>!{state}{try{return cell_new(42);}finally{cell_collect();}}
fn main()->unit!{state,io}{print(cell_read(value()));}
'''},
        {'name':'replaced-return-retirement','limits':[2,16,32],'output':'2\n3\n','source':r'''
fn value()->cell<i64>!{state}{try{try{return cell_new(1);}finally{return cell_new(2);}}finally{cell_collect();}}
fn main()->unit!{state,io}{let selected:cell<i64>=value();print(cell_read(selected));let next:cell<i64>=cell_new(3);print(cell_read(next));}
'''},
        {'name':'handler-filter-root','limits':[1,12,24],'output':'42\n7\n','source':r'''
fn raise()->unit!{state,throw}{throw(cell_new(42));}
fn no(value:cell<i64>)->bool!{state}{cell_collect();return cell_read(value)==0;}
fn main()->unit!{state,io,throw}{try{raise();}catch(value:cell<i64>)if no(value){assert(false);}catch(value:cell<i64>){cell_collect();print(cell_read(value));}cell_collect();let next:cell<i64>=cell_new(7);print(cell_read(next));}
'''},
        {'name':'handler-retirement-loop','limits':[1,12,24],'output':'64\n','source':r'''
fn raise(value:i64)->unit!{state,throw}{throw(cell_new(value));}
fn main()->unit!{state,io,throw}{var i:i64=0;while i<64{try{raise(i);}catch(value:cell<i64>){cell_collect();assert(cell_read(value)==i);}i=i+1;}cell_collect();print(i);}
'''},
        {'name':'rethrow-flight-root','limits':[1,12,24],'output':'43\n','source':r'''
fn raise()->unit!{state,throw}{throw(cell_new(42));}
fn relay()->unit!{state,throw}{try{try{raise();}catch(value:cell<i64>){cell_write(value,43);throw;}}finally{cell_collect();}}
fn main()->unit!{state,io,throw}{try{relay();}catch(value:cell<i64>){cell_collect();print(cell_read(value));}}
'''},
        {'name':'replacement-source-error','limits':[2,12,24],'output':'2\n7\n','source':r'''
fn replace()->unit!{state,throw}{try{throw(cell_new(1));}finally{throw(cell_new(2));}}
fn main()->unit!{state,io,throw}{try{replace();}catch(value:cell<i64>){cell_collect();print(cell_read(value));}cell_collect();let next:cell<i64>=cell_new(7);print(cell_read(next));}
'''},
        {'name':'fatal-replaces-source-error','limits':[1,12,24],'error':'E_OVERFLOW','source':r'''
fn main()->unit!{state,throw}{try{throw(cell_new(1));}finally{cell_collect();let bad:i64=9223372036854775807+1;}}
'''},
        {'name':'legacy-filter','output':'E\nЯ🌍\n','source':r'''
fn no(code:str)->bool!{state}{cell_collect();return code=="other";}
fn main()->unit!{state,io,throw}{try{throw("E","Я🌍");}catch(code,message)if no(code){assert(false);}catch(code,message){cell_collect();print(code);print(message);}}
'''},
        {'name':'pattern-guard-roots','limits':[2,24,48],'output':'42\n42\n','source':r'''
enum Item{Empty;Some(value:cell<i64>);}
fn make()->Item!{state}{return Item::Some(cell_new(42));}
fn yes(value:cell<i64>)->bool!{state}{cell_collect();return cell_read(value)==42;}
fn main()->unit!{state,io}{let selected:i64=match make(){Item::Empty()=>0,Item::Some(value)if yes(value)=>cell_read(value),Item::Some(value)=>0};print(selected);match make(){Item::Empty()=>{assert(false);}Item::Some(value)if yes(value)=>{print(cell_read(value));}Item::Some(value)=>{assert(false);}}}
'''},
        {'name':'list-builder-roots','limits':[32,128,256],'output':'16\n15\n','source':r'''
fn main()->unit!{state,io}{let values:list<cell<i64>>=list(16,fn(i:i64)->cell<i64>!{state}{cell_collect();return cell_new(i);});cell_collect();print(len(values));print(cell_read(values[15]));}
'''},
        {'name':'text-byte-builders','output':'0123\nABCD\n','source':r'''
fn main()->unit!{state,io}{let value:cell<str>=cell_new(str(4,fn(i:i64)->str!{state}{cell_collect();return str(i);}));print(cell_read(value));let octets:cell<bytes>=cell_new(bytes(4,fn(i:i64)->i64!{state}{cell_collect();return i+65;}));print(unwrap(decode_utf8(cell_read(octets))));}
'''},
        {'name':'str-allocation-identity','limits':[8,3,32],'error':'E_CELL_LIMIT','source':r'''
fn main()->unit!{state}{let original:cell<str>=cell_new("same");let cloned:cell<str>=cell_new(str(cell_read(original)));}
'''},
        {'name':'bytes-set-allocation-identity','limits':[8,3,32],'error':'E_CELL_LIMIT','source':r'''
fn main()->unit!{state}{let original:cell<bytes>=cell_new(utf8_bytes("a"));let cloned:cell<bytes>=cell_new(set(cell_read(original),0,97));}
'''},
        {'name':'failure-message-allocation','limits':[8,6,32],'error':'E_CELL_LIMIT','source':r'''
fn main()->unit!{state}{let message:cell<str>=cell_new("m");let error:cell<result<i64>>=cell_new(err<i64>("E",cell_read(message)));let cloned:cell<str>=cell_new(error_message(cell_read(error)));}
'''},
        {'name':'result-propagation-root','limits':[1,16,32],'output':'42\n','source':r'''
fn failed()->result<cell<i64>>!{state}{try{let value:i64=err<i64>("E","missing")?;return ok(cell_new(value));}finally{cell_collect();}}
fn main()->unit!{state,io}{assert(!is_ok(failed()));let value:cell<i64>=cell_new(42);print(cell_read(value));}
'''},
        {'name':'json-boxed-values','output':'true\n','source':r'''
struct Box{value:list<i64>;text:str;}
fn main()->unit!{state,io}{let value:cell<Box>=cell_new(Box([1,2],"Я🌍"));let encoded:str=encode_json(cell_read(value));let decoded:Box=unwrap(decode_json<Box>(encoded));cell_collect();assert(decoded==cell_read(value));let binary:bytes=utf8_bytes("abc");assert(unwrap(decode_base64(encode_base64(binary)))==binary);print(true);}
'''},
        {'name':'typed-payload-shapes','output':'typed-payloads-ok\n','source':r'''
struct Box{value:cell<i64>;}
enum Item{Empty;Some(value:cell<i64>);}
fn main()->unit!{state,io,throw}{
 let stored:cell<i64>=cell_new(42);
 try{throw(false);}catch(value:bool){assert(!value);}
 try{throw(7);}catch(value:i64){assert(value==7);}
 try{throw(1.25);}catch(value:f64){assert(value==1.25);}
 try{throw("Я🌍");}catch(value:str){cell_collect();assert(value=="Я🌍");}
 try{throw(utf8_bytes("abc"));}catch(value:bytes){cell_collect();assert(unwrap(decode_utf8(value))=="abc");}
 try{throw([stored]);}catch(value:list<cell<i64>>){cell_collect();assert(value[0]==stored);}
 try{throw(Box(stored));}catch(value:Box){cell_collect();assert(value.value==stored);}
 try{throw(Item::Some(stored));}catch(value:Item){cell_collect();match value{Item::Empty()=>{assert(false);}Item::Some(alias)=>{assert(alias==stored);}}}
 try{throw(ok(stored));}catch(value:result<cell<i64>>){cell_collect();assert(unwrap(value)==stored);}
 try{throw(fn()->i64!{state}{cell_collect();return cell_read(stored);});}catch(value:fn()->i64!{state}){assert(value()==42);}
 print("typed-payloads-ok");
}
'''},
    ]
    # These graphs are never adopted by a cell registry. Their source handles
    # must retire correctly through the ordinary runtime on every exit path.
    deep_prefix=r'''
struct Deep{next:list<Deep>;}
'''
    deep_body=r'''
var value:Deep=Deep([]);var i:i64=0;
while i<65536{value=Deep([value]);i=i+1;}
'''
    cases += [
        {'name':'deep-ordinary-retirement','output':'65536\nretired\n','source':deep_prefix+r'''
fn build()->unit!{io}{'''+deep_body+r'''print(i);}
fn main()->unit!{io}{build();print("retired");}
'''},
        {'name':'deep-source-unwind','output':'42\n','source':deep_prefix+r'''
fn build()->unit!{throw}{'''+deep_body+r'''throw(42);}
fn main()->unit!{io,throw}{try{build();}catch(value:i64){print(value);}}
'''},
        {'name':'deep-fatal-unwind','error':'E_OVERFLOW','source':deep_prefix+r'''
fn build()->unit{'''+deep_body+r'''let bad:i64=9223372036854775807+1;}
fn main()->unit{build();}
'''},
    ]
    return cases


def host_cases():
    return [
        {'name':'host-i64','source':'fn main()->i64!{state}{let value:cell<i64>=cell_new(9223372036854775807);return cell_read(value);}','value':9223372036854775807},
        {'name':'host-snapshot','source':'struct Box{value:list<i64>;text:str;}fn main()->Box!{state}{let value:cell<Box>=cell_new(Box([1,2],"Я🌍"));let saved:Box=cell_read(value);cell_write(value,Box([3],"new"));return saved;}','value':{'value':[1,2],'text':'Я🌍'}},
    ]
