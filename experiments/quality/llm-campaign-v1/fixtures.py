"""Host-only starting snapshots and control solutions, never model context.

This is experiment infrastructure, not observed model output. Public candidates
receive only their own materialized starting bundle and neutral task contract.
"""
from pathlib import Path
import json
import random

CPP = '''#pragma once
#include <algorithm>
#include <atomic>
#include <cstdint>
#include <future>
#include <optional>
#include <string>
#include <thread>
#include <vector>
using i64 = std::int64_t;
'''
PY = 'from dataclasses import dataclass\nfrom typing import Generic, TypeVar, Optional\nT = TypeVar("T")\n'
TASKS = {}


def add(name, language, initial, solution, other=None):
    file = {'nex': 'candidate.nex', 'cpp': 'candidate.hpp', 'python': 'candidate.py'}[language]
    prefix = {'nex': 'module candidate;\n', 'cpp': CPP, 'python': PY}[language]
    start, correct = {file: prefix + initial.strip() + '\n'}, {file: prefix + solution.strip() + '\n'}
    if language == 'nex':
        manifest = json.dumps({'schema': 'nex.project/1', 'language': '0.28', 'entry': file}) + '\n'
        start['nex.json'] = correct['nex.json'] = manifest
    for path, values in (other or {}).items():
        start[path], correct[path] = values
    TASKS.setdefault(name, {})[language] = {'start': start, 'solution': correct}


add('bounded-total', 'nex',
    'fn total(n:i64)->i64 requires(n>=0&&n<=100) ensures(value=>value>=0){return n;}',
    '''fn total(n:i64)->i64 requires(n>=0&&n<=100) ensures(value=>value>=0){
 var i:i64=0;var sum:i64=0;
 while i<n invariant(i>=0&&i<=n) invariant(sum>=0) decreases(n-i){i=i+1;sum=sum+i;}
 return sum;
}''')
add('bounded-total', 'cpp', 'inline i64 total(i64 n){return n;}',
    'inline i64 total(i64 n){i64 value=0;for(i64 i=1;i<=n;++i)value+=i;return value;}')
add('bounded-total', 'python', 'def total(n: int) -> int:\n    return n',
    'def total(n: int) -> int:\n    return sum(range(1, n + 1))')

NEX_CHOICE = 'enum Choice{Some(value:i64);None;}\n'
CPP_SELECTION = 'struct Selection{bool ok;i64 value;std::string code,message;};\n'
PY_SELECTION = '@dataclass\nclass Selection:\n    ok: bool\n    value: int = 0\n    code: str = ""\n    message: str = ""\n'
add('recoverable-selection', 'nex', NEX_CHOICE +
    'fn double_selected(x:Choice)->result<i64>{return match x{Choice::Some(n)=>ok(n*2),Choice::None()=>ok(0)};}',
    NEX_CHOICE + '''fn select(x:Choice)->result<i64>{return match x{
 Choice::Some(n) if n>=0=>ok(n),Choice::Some(_)=>err<i64>("NEGATIVE","negative"),Choice::None()=>err<i64>("EMPTY","empty")};}
fn double_selected(x:Choice)->result<i64>{let n:i64=select(x)?;return ok(n*2);}''')
add('recoverable-selection', 'cpp', CPP_SELECTION +
    'inline Selection double_selected(std::optional<i64> n){return {true,n.value_or(0)*2,"",""};}',
    CPP_SELECTION + '''inline Selection double_selected(std::optional<i64> n){
 if(!n)return {false,0,"EMPTY","empty"};
 if(*n<0)return {false,0,"NEGATIVE","negative"};return {true,*n*2,"",""};}''')
add('recoverable-selection', 'python', PY_SELECTION +
    'def double_selected(n: Optional[int]) -> Selection:\n    return Selection(True, (n or 0) * 2)',
    PY_SELECTION + '''def double_selected(n: Optional[int]) -> Selection:
    if n is None:
        return Selection(False, code="EMPTY", message="empty")
    if n < 0:
        return Selection(False, code="NEGATIVE", message="negative")
    return Selection(True, n * 2)''')

add('unicode-window', 'nex', 'fn window(text:str,start:i64,count:i64)->str{return text;}',
    'fn window(text:str,start:i64,count:i64)->str{return slice(text,start,count);}')
add('unicode-window', 'cpp', 'inline std::string window(const std::string &s,i64 start,i64 count){return s;}',
    '''inline std::string window(const std::string &s,i64 start,i64 count){
 std::vector<std::size_t> offsets;
 for(std::size_t i=0;i<s.size();){offsets.push_back(i);auto c=static_cast<unsigned char>(s[i]);i+=c<0x80?1:c<0xe0?2:c<0xf0?3:4;}
 offsets.push_back(s.size());auto first=offsets.at(static_cast<std::size_t>(start));
 return s.substr(first,offsets.at(static_cast<std::size_t>(start+count))-first);
}''')
add('unicode-window', 'python', 'def window(text: str, start: int, count: int) -> str:\n    return text',
    'def window(text: str, start: int, count: int) -> str:\n    return text[start:start + count]')

NEX_UPDATE = 'struct Update{original:bytes;updated:bytes;decoded:result<str>;}\n'
CPP_UPDATE = 'struct Update{std::vector<i64> original,updated;bool decoded_ok;std::string decoded,error_code;};\n'
PY_UPDATE = '@dataclass\nclass Update:\n    original: bytes\n    updated: bytes\n    decoded: Optional[str]\n    error_code: str = ""\n'
add('immutable-byte-update', 'nex', NEX_UPDATE +
    'fn updated_copy(data:bytes,index:i64,value:i64)->Update{return Update(data,data,decode_utf8(data));}',
    NEX_UPDATE + 'fn updated_copy(data:bytes,index:i64,value:i64)->Update{let changed:bytes=set(data,index,value);return Update(data,changed,decode_utf8(changed));}')
CPP_UTF8 = '''inline bool valid_utf8(const std::vector<i64> &s){
 for(std::size_t i=0;i<s.size();){auto c=s[i++];if(c<0||c>255)return false;if(c<128)continue;
  int tail=0;std::uint32_t cp=0,minimum=0;
  if(c>=0xc2&&c<=0xdf){tail=1;cp=c&31;minimum=128;}
  else if(c>=0xe0&&c<=0xef){tail=2;cp=c&15;minimum=2048;}
  else if(c>=0xf0&&c<=0xf4){tail=3;cp=c&7;minimum=65536;}else return false;
  if(s.size()-i<static_cast<std::size_t>(tail))return false;
  for(int n=0;n<tail;++n){auto b=s[i++];if(b<128||b>191)return false;cp=(cp<<6)|(b&63);}
  if(cp<minimum||cp>0x10ffff||(cp>=0xd800&&cp<=0xdfff))return false;
 }return true;
}
'''
add('immutable-byte-update', 'cpp', CPP_UPDATE +
    'inline Update updated_copy(std::vector<i64> &data,i64 index,i64 value){return {data,data,true,"",""};}',
    CPP_UPDATE + CPP_UTF8 + '''inline Update updated_copy(std::vector<i64> &data,i64 index,i64 value){
 auto changed=data;changed.at(static_cast<std::size_t>(index))=value;bool valid=valid_utf8(changed);std::string text;
 if(valid)for(auto octet:changed)text.push_back(static_cast<char>(octet));
 return {data,changed,valid,text,valid?"":"E_UTF8"};
}''')
add('immutable-byte-update', 'python', PY_UPDATE +
    'def updated_copy(data: bytes, index: int, value: int) -> Update:\n    return Update(data, data, "")',
    PY_UPDATE + '''def updated_copy(data: bytes, index: int, value: int) -> Update:
    changed = bytearray(data)
    changed[index] = value
    result = bytes(changed)
    try:
        return Update(data, result, result.decode("utf-8", errors="strict"))
    except UnicodeDecodeError:
        return Update(data, result, None, "E_UTF8")''')

add('generic-projection', 'nex', 'struct Box<T>{value:T;}\nfn project(value:Box<i64>)->i64{return value.value;}',
    'struct Box<T>{value:T;}\nfn project<T>(value:Box<T>)->T{return value.value;}')
add('generic-projection', 'cpp', 'template<class T>struct Box{T value;};\ninline i64 project(const Box<i64>& b){return b.value;}',
    'template<class T>struct Box{T value;};\ntemplate<class T>T project(const Box<T>& b){return b.value;}')
PY_BOX = '@dataclass\nclass Box(Generic[T]):\n    value: T\n'
add('generic-projection', 'python', PY_BOX + 'def project(value: Box[int]) -> int:\n    return int(value.value)',
    PY_BOX + 'def project(value: Box[T]) -> T:\n    return value.value')

NEX_CONTENT = '''trait Content{type Item;fn get(value:Self)->Content::Item<Self>;}
struct Box<T>{value:T;}
fn extract<T>(value:Box<T>)->T{return value.value;}
impl boxed<T>:Content for Box<T>{type Item=T;get=extract<T>;}
'''
CPP_CONTENT = 'template<class T>struct Box{T value;T get()const{return value;}};\n'
PY_CONTENT = PY_BOX + '    def get(self) -> T:\n        return self.value\n'
add('associated-value-adapter', 'nex', NEX_CONTENT + 'fn read_content(value:Box<i64>)->i64{return Content<Box<i64>>::get(value);}',
    NEX_CONTENT + 'fn read_content<T:Content>(value:T)->Content::Item<T>{return Content<T>::get(value);}')
add('associated-value-adapter', 'cpp', CPP_CONTENT + 'inline i64 read_content(const Box<i64>& b){return b.get();}',
    CPP_CONTENT + 'template<class T>T read_content(const Box<T>& b){return b.get();}')
add('associated-value-adapter', 'python', PY_CONTENT + 'def read_content(value: Box[int]) -> int:\n    return int(value.get())',
    PY_CONTENT + 'def read_content(value: Box[T]) -> T:\n    return value.get()')

add('module-interface-change', 'nex', 'import "./operations.nex" as operations;\nfn answer(n:i64)->i64{return operations::answer(n);}',
    'import "./operations.nex" as operations;\nfn answer(n:i64,offset:i64)->i64{return operations::answer(n,offset);}',
    {'operations.nex': ('module operations;\npub fn answer(n:i64)->i64{return n*2;}\n',
                        'module operations;\npub fn answer(n:i64,offset:i64)->i64{return n*2+offset;}\n')})
add('module-interface-change', 'cpp', '#include "operations.hpp"\ninline i64 answer(i64 n){return operation::answer(n);}',
    '#include "operations.hpp"\ninline i64 answer(i64 n,i64 offset){return operation::answer(n,offset);}',
    {'operations.hpp': ('#pragma once\n#include <cstdint>\nnamespace operation{std::int64_t answer(std::int64_t n);}\n',
                        '#pragma once\n#include <cstdint>\nnamespace operation{std::int64_t answer(std::int64_t n,std::int64_t offset);}\n'),
     'operations.cpp': ('#include "operations.hpp"\nnamespace operation{std::int64_t answer(std::int64_t n){return n*2;}}\n',
                        '#include "operations.hpp"\nnamespace operation{std::int64_t answer(std::int64_t n,std::int64_t offset){return n*2+offset;}}\n')})
add('module-interface-change', 'python', 'import operations\ndef answer(n: int) -> int:\n    return operations.answer(n)',
    'import operations\ndef answer(n: int, offset: int) -> int:\n    return operations.answer(n, offset)',
    {'operations.py': ('def answer(n: int) -> int:\n    return n * 2\n',
                       'def answer(n: int, offset: int) -> int:\n    return n * 2 + offset\n')})

add('ordered-bounded-map', 'nex', 'fn squares(values:list<i64>,workers:i64)->list<i64>{return values;}',
    'fn square(x:i64)->i64{return x*x;}\nfn squares(values:list<i64>,workers:i64)->list<i64>{return parallel_map(values,square,workers);}')
add('ordered-bounded-map', 'cpp', 'inline std::vector<i64> squares(std::vector<i64>& values,i64 workers){return values;}',
    '''inline std::vector<i64> squares(std::vector<i64>& values,i64 workers){
 std::vector<i64> result(values.size());std::atomic<std::size_t> next{0};std::vector<std::thread> pool;
 auto count=std::min<std::size_t>(static_cast<std::size_t>(workers),values.size());
 for(std::size_t w=0;w<count;++w)pool.emplace_back([&]{for(;;){auto i=next.fetch_add(1);if(i>=values.size())break;result[i]=values[i]*values[i];}});
 for(auto &worker:pool)worker.join();return result;
}''')
add('ordered-bounded-map', 'python', 'def squares(values: list[int], workers: int) -> list[int]:\n    return values',
    '''from concurrent.futures import ThreadPoolExecutor
def squares(values: list[int], workers: int) -> list[int]:
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(lambda x: x * x, values))''')

NEX_READ = '''struct InputError{text:str;}
struct ReadTrace{ok:bool;value:i64;error_text:str;trace:list<str>;}
fn read_answer(text:str)->i64 !{throw}{if text=="42"{return 42;}throw(InputError(text));}
'''
CPP_READ = '''struct InputError{std::string text;};
struct ReadTrace{bool ok;i64 value;std::string error_text;std::vector<std::string> trace;};
inline i64 read_answer(const std::string &text){if(text=="42")return 42;throw InputError{text};}
'''
PY_READ = '''class InputError(Exception):
    def __init__(self, text: str):
        super().__init__(text)
        self.text = text
@dataclass
class ReadTrace:
    ok: bool
    value: int
    error_text: str
    trace: list[str]
def read_answer(text: str) -> int:
    if text == "42":
        return 42
    raise InputError(text)
'''
add('typed-error-finally', 'nex', NEX_READ + 'fn read_with_trace(text:str)->ReadTrace !{throw}{return ReadTrace(true,42,"",[]);}',
    NEX_READ + '''fn read_with_trace(text:str)->ReadTrace !{throw}{
 var success:bool=false;var value:i64=0;var detail:str="";var trace:list<str>=[];
 try{value=read_answer(text);success=true;}
 catch(error:InputError){detail=error.text;trace=push(trace,"caught");}
 finally{trace=push(trace,"finished");}
 return ReadTrace(success,value,detail,trace);
}''')
add('typed-error-finally', 'cpp', CPP_READ + 'inline ReadTrace read_with_trace(const std::string& text){return {true,42,"",{}};}',
    CPP_READ + '''inline ReadTrace read_with_trace(const std::string &text){
 ReadTrace result{false,0,"",{}};
 {struct Finalizer{std::vector<std::string>& trace;~Finalizer(){trace.push_back("finished");}} finally{result.trace};
  try{result.value=read_answer(text);result.ok=true;}
  catch(const InputError& error){result.error_text=error.text;result.trace.push_back("caught");}}
 return result;
}''')
add('typed-error-finally', 'python', PY_READ + 'def read_with_trace(text: str) -> ReadTrace:\n    return ReadTrace(True, 42, "", [])',
    PY_READ + '''def read_with_trace(text: str) -> ReadTrace:
    result = ReadTrace(False, 0, "", [])
    try:
        result.value = read_answer(text)
        result.ok = True
    except InputError as error:
        result.error_text = error.text
        result.trace.append("caught")
    finally:
        result.trace.append("finished")
    return result''')

NEX_JOIN = 'struct Joined{value:i64;trace:list<str>;}\n'
CPP_JOIN = 'struct Joined{i64 value;std::vector<std::string> trace;};\n'
PY_JOIN = '@dataclass\nclass Joined:\n    value: int\n    trace: list[str]\n'
add('joined-yielding-child', 'nex', NEX_JOIN + 'fn joined_answer(value:i64)->Joined !{task,throw}{return Joined(42,[]);}',
    NEX_JOIN + '''fn joined_answer(value:i64)->Joined !{task,throw}{
 let result:Joined=with_tasks(1,fn(scope:task_scope)->Joined !{task,throw}{
  let child:task<Joined>=task_spawn(scope,fn()->Joined !{task}{task_yield();return Joined(value,["child"]);});
  return task_wait(child);
 });return Joined(result.value,push(result.trace,"returned"));
}''')
add('joined-yielding-child', 'cpp', CPP_JOIN + 'inline Joined joined_answer(i64 value){return {42,{}};}',
    CPP_JOIN + '''inline Joined joined_answer(i64 value){
 auto child=std::async(std::launch::async,[value]{std::this_thread::yield();return Joined{value,{"child"}};});
 auto result=child.get();result.trace.push_back("returned");return result;
}''')
add('joined-yielding-child', 'python', PY_JOIN + 'def joined_answer(value: int) -> Joined:\n    return Joined(42, [])',
    PY_JOIN + '''from concurrent.futures import ThreadPoolExecutor
import time
def joined_answer(value: int) -> Joined:
    def child() -> Joined:
        time.sleep(0)  # scheduler yield; ordering is established by result()/join
        return Joined(value, ["child"])
    with ThreadPoolExecutor(max_workers=1) as scope:
        result = scope.submit(child).result()
    result.trace.append("returned")
    return result''')


def files(task, language, variant='start'):
    """Return fresh bytes; callers cannot mutate the host's control templates."""
    if variant not in ('start', 'solution'):
        raise ValueError('unknown fixture variant')
    return {name: text.encode('utf-8') for name, text in TASKS[task][language][variant].items()}


def held_out(task):
    """Fixed host-only cases; never adapt cases after viewing model answers."""
    rng = random.Random(0x4e4558)
    def case(value, expected):
        return {'input': value, 'expected': expected}
    if task == 'bounded-total':
        return [case({'n': n}, n * (n + 1) // 2) for n in [2, 37, 99]]
    if task == 'recoverable-selection':
        return [case({'choice': {'Some': n}}, {'ok': n * 2}) for n in [7, 999]] + [
            case({'choice': {'Some': -1000}}, {'error': {'code': 'NEGATIVE', 'message': 'negative'}})]
    if task == 'unicode-window':
        return [case({'text': s, 'start': start, 'count': count}, s[start:start + count])
                for s, start, count in [('é🌍A\0Z', 1, 3), ('A\r\n🧠B', 1, 3), ('x🧠', 2, 0)]]
    if task == 'immutable-byte-update':
        cases = []
        for octets, index, value in [([192, 175], 0, 192), ([237, 160, 128], 0, 237),
                                     ([244, 144, 128, 128], 0, 244), ([240, 159, 140, 141], 1, 65)]:
            changed = list(octets); changed[index] = value
            expected = {'original': octets, 'updated': changed}
            try: expected['decoded'] = bytes(changed).decode('utf-8', errors='strict')
            except UnicodeDecodeError: expected['decode_error'] = 'E_UTF8'
            cases.append(case({'octets': octets, 'index': index, 'value': value}, expected))
        return cases
    if task == 'generic-projection':
        return [case({'type': kind, 'value': value}, value)
                for kind, value in [('i64', -999), ('str', '\0🌍'), ('f64', -1.75), ('f64', 1e200)]]
    if task == 'associated-value-adapter':
        return [case({'type': kind, 'value': value}, {'direct': value, 'referenced': value})
                for kind, value in [('i64', -999), ('str', '\0🌍')]]
    if task == 'module-interface-change':
        return [case({'n': n, 'offset': offset}, n * 2 + offset)
                for n, offset in [(999, -999), (-1000, 1000), (7, 0)]]
    if task == 'ordered-bounded-map':
        values = [rng.randrange(-999, 1000) for _ in range(17)]
        return [case({'values': values, 'workers': workers}, [x * x for x in values]) for workers in [1, 4]]
    if task == 'typed-error-finally':
        return [case({'text': value}, {'error_text': value, 'trace': ['caught', 'finished']})
                for value in ['', '42\0', '042']]
    if task == 'joined-yielding-child':
        return [case({'value': n}, {'value': n, 'trace': ['child', 'returned']}) for n in [-1000, 777]]
    raise ValueError('unknown task')
