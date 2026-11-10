"""Private executable observations for the ten public task contracts."""
import json


def text(value):
    return json.dumps(value, ensure_ascii=False)


def cpp_text(value):
    raw = value.encode('utf-8')
    return 'std::string("' + ''.join('\\%03o' % c for c in raw) + '",' + str(len(raw)) + ')'


CPP_JSON = r'''
#include <charconv>
#include <cmath>
#include <iostream>
#include <stdexcept>
#include <type_traits>
std::string j(const std::string &s){
 const char *hex="0123456789abcdef";std::string result="\"";
 for(unsigned char c:s){if(c=='"'||c=='\\'){result+='\\';result+=c;}
  else if(c<32){result+="\\u00";result+=hex[c>>4];result+=hex[c&15];}else result+=c;}
 return result+'"';
}
std::string j(i64 x){return std::to_string(x);}
std::string j(double x){if(!std::isfinite(x))throw std::runtime_error("nonfinite output");
 char buffer[128];auto r=std::to_chars(buffer,buffer+sizeof(buffer),x,std::chars_format::general);
 if(r.ec!=std::errc{})throw std::runtime_error("float output");return {buffer,r.ptr};}
template<class T>std::string j(const std::vector<T>& xs){std::string result="[";
 for(std::size_t i=0;i<xs.size();++i){if(i)result+=',';result+=j(xs[i]);}return result+"]";}
'''


def cpp_driver(task, cases):
    body = []
    for case in cases:
        x = case['input']; before = ''
        if task == 'bounded-total':
            code = f'auto r=total({x["n"]});'; result = 'j(r)'
        elif task == 'recoverable-selection':
            choice = x['choice']; arg = 'std::nullopt' if choice == 'None' else f'std::optional<i64>{{{choice["Some"]}}}'
            code = f'auto r=double_selected({arg});'
            result = '(r.ok?"{\\\"ok\\\":"+j(r.value)+"}":"{\\\"error\\\":{\\\"code\\\":"+j(r.code)+",\\\"message\\\":"+j(r.message)+"}}")'
        elif task == 'unicode-window':
            code = f'auto r=window({cpp_text(x["text"])},{x["start"]},{x["count"]});'; result = 'j(r)'
        elif task == 'immutable-byte-update':
            code = 'std::vector<i64> input{' + ','.join(map(str, x['octets'])) + '};'
            code += f'auto r=updated_copy(input,{x["index"]},{x["value"]});'
            result = '"{\\\"original\\\":"+j(r.original)+",\\\"updated\\\":"+j(r.updated)+(r.decoded_ok?",\\\"decoded\\\":"+j(r.decoded):",\\\"decode_error\\\":"+j(r.error_code))+"}"'
            before = '"\\\"input_after\\\":"+j(input)+","+'
        elif task in ('generic-projection', 'associated-value-adapter'):
            kind = x['type']; typ = {'i64': 'i64', 'str': 'std::string', 'f64': 'double'}[kind]
            literal = cpp_text(x['value']) if kind == 'str' else repr(x['value'])
            code = f'Box<{typ}> input{{{literal}}};'
            if task == 'generic-projection':
                code += f'auto r=project(input);static_assert(std::is_same_v<decltype(r),{typ}>);'
                result = 'j(r)'
            else:
                code += f'auto direct=read_content(input);auto reader=&Box<{typ}>::get;auto referenced=(input.*reader)();'
                result = '"{\\\"direct\\\":"+j(direct)+",\\\"referenced\\\":"+j(referenced)+"}"'
        elif task == 'module-interface-change':
            code = f'auto r=answer({x["n"]},{x["offset"]});'; result = 'j(r)'
        elif task == 'ordered-bounded-map':
            code = 'std::vector<i64> input{' + ','.join(map(str, x['values'])) + '};'
            code += f'auto r=squares(input,{x["workers"]});'; result = 'j(r)'
            before = '"\\\"input_after\\\":"+j(input)+","+'
        elif task == 'typed-error-finally':
            code = f'auto r=read_with_trace({cpp_text(x["text"])});'
            result = '(r.ok?"{\\\"ok\\\":"+j(r.value):"{\\\"error_text\\\":"+j(r.error_text))+",\\\"trace\\\":"+j(r.trace)+"}"'
        elif task == 'joined-yielding-child':
            code = f'auto r=joined_answer({x["value"]});'
            result = '"{\\\"value\\\":"+j(r.value)+",\\\"trace\\\":"+j(r.trace)+"}"'
        else:
            raise ValueError('unknown task')
        # One actual observation per case, never a model-authored pass marker.
        body.append('{' + code + 'std::cout<<std::string("{")+' + before + '"\\\"result\\\":"+(' + result + ')+"}\\n";}')
    return '#include "candidate.hpp"\n' + CPP_JSON + '\nint main(){\n' + '\n'.join(body) + '\n}\n'


NEX_OCTETS = '''fn campaign_octets(data:bytes)->list<i64>{
 var result:list<i64>=[];var i:i64=0;while i<len(data){result=push(result,data[i]);i=i+1;}return result;
}
'''
NEX_NUMBERS = '''fn campaign_number(value:i64)->str{return str(value);}
fn campaign_numbers(values:list<i64>)->str{
 var result:str="[";var i:i64=0;while i<len(values){if i>0{result=result+",";}result=result+str(values[i]);i=i+1;}return result+"]";
}
'''


def nex_driver(task, cases):
    body = []
    for i, case in enumerate(cases):
        x = case['input']; v = 'campaign_value_' + str(i); p = 'campaign_input_' + str(i)
        if task == 'bounded-total':
            expression = f'total({x["n"]})'
            codec = 'campaign_number'
        elif task == 'unicode-window':
            expression = f'window({text(x["text"])},{x["start"]},{x["count"]})'
            codec = 'encode_json'
        elif task == 'generic-projection':
            typ = x['type']; literal = text(x['value'])
            body.append(f'let {v}:{typ}=project(Box<{typ}>({literal}));')
            expression = v
            codec = 'campaign_number' if typ == 'i64' else 'encode_json'
        elif task == 'module-interface-change':
            expression = f'answer({x["n"]},{x["offset"]})'
            codec = 'campaign_number'
        elif task == 'recoverable-selection':
            choice = x['choice']; arg = 'Choice::None()' if choice == 'None' else f'Choice::Some({choice["Some"]})'
            body.append(f'let {v}:result<i64>=double_selected({arg});')
            success = text('{"result":{"ok":') + f'+campaign_number(unwrap({v}))+' + text('}}')
            failure = text('{"result":{"error":{"code":') + f'+encode_json(error_code({v}))+' + text(',"message":') + f'+encode_json(error_message({v}))+' + text('}}}')
            body.append(f'if is_ok({v}){{print({success});}}else{{print({failure});}}'); continue
        elif task == 'immutable-byte-update':
            body.append(f'let {p}:bytes=unwrap(bytes({text(x["octets"])}));let {v}:Update=updated_copy({p},{x["index"]},{x["value"]});')
            prefix = text('{"input_after":') + f'+campaign_numbers(campaign_octets({p}))+' + text(',"result":{"original":') + f'+campaign_numbers(campaign_octets({v}.original))+' + text(',"updated":') + f'+campaign_numbers(campaign_octets({v}.updated))+'
            success = prefix + text(',"decoded":') + f'+encode_json(unwrap({v}.decoded))+' + text('}}')
            failure = prefix + text(',"decode_error":') + f'+encode_json(error_code({v}.decoded))+' + text('}}')
            body.append(f'if is_ok({v}.decoded){{print({success});}}else{{print({failure});}}'); continue
        elif task == 'associated-value-adapter':
            typ = x['type']; direct = v + '_direct'; referenced = v + '_reference'; reader = v + '_reader'
            body.append(f'let {p}:Box<{typ}>=Box<{typ}>({text(x["value"])});let {direct}:{typ}=read_content({p});let {reader}:fn(Box<{typ}>)->{typ}=Content<Box<{typ}>>::get;let {referenced}:{typ}={reader}({p});')
            codec = 'campaign_number' if typ == 'i64' else 'encode_json'
            result = text('{"result":{"direct":') + f'+{codec}({direct})+' + text(',"referenced":') + f'+{codec}({referenced})+' + text('}}')
            body.append(f'print({result});'); continue
        elif task == 'ordered-bounded-map':
            body.append(f'let {p}:list<i64>={text(x["values"])};let {v}:list<i64>=squares({p},{x["workers"]});')
            result = text('{"input_after":') + f'+campaign_numbers({p})+' + text(',"result":') + f'+campaign_numbers({v})+' + text('}')
            body.append(f'print({result});'); continue
        elif task == 'typed-error-finally':
            body.append(f'let {v}:ReadTrace=read_with_trace({text(x["text"])});')
            trace = text(',"trace":') + f'+encode_json({v}.trace)+' + text('}}')
            success = text('{"result":{"ok":') + f'+campaign_number({v}.value)+' + trace
            failure = text('{"result":{"error_text":') + f'+encode_json({v}.error_text)+' + trace
            body.append(f'if {v}.ok{{print({success});}}else{{print({failure});}}'); continue
        elif task == 'joined-yielding-child':
            body.append(f'let {v}:Joined=joined_answer({x["value"]});')
            result = text('{"result":{"value":') + f'+campaign_number({v}.value)+' + text(',"trace":') + f'+encode_json({v}.trace)+' + text('}}')
            body.append(f'print({result});'); continue
        else:
            raise ValueError('unknown task')
        body.append('print(' + text('{"result":') + '+' + codec + '(' + expression + ')+' + text('}') + ');')
    effects = 'task,throw,io' if task == 'joined-yielding-child' else 'throw,io' if task == 'typed-error-finally' else 'io'
    helpers = '' if task == 'unicode-window' else NEX_NUMBERS
    return helpers + (NEX_OCTETS if task == 'immutable-byte-update' else '') + 'fn main()->unit !{' + effects + '}{\n' + '\n'.join(body) + '\n}\n'


def python_driver(task, cases):
    return '''import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import candidate as c
task = ''' + repr(task) + '\ncases = ' + repr(cases) + '''
for case in cases:
    x = case['input']
    extra = {}
    if task == 'bounded-total': r = c.total(x['n'])
    elif task == 'recoverable-selection':
        choice = x['choice']
        v = c.double_selected(None if choice == 'None' else choice['Some'])
        r = {'ok': v.value} if v.ok else {'error': {'code': v.code, 'message': v.message}}
    elif task == 'unicode-window': r = c.window(x['text'], x['start'], x['count'])
    elif task == 'immutable-byte-update':
        data = bytes(x['octets'])
        v = c.updated_copy(data, x['index'], x['value'])
        r = {'original': list(v.original), 'updated': list(v.updated)}
        r.update({'decoded': v.decoded} if v.decoded is not None else {'decode_error': v.error_code})
        extra['input_after'] = list(data)
    elif task == 'generic-projection':
        r = c.project(c.Box(x['value']))
        if type(r) is not type(x['value']): raise TypeError('projection changed payload type')
    elif task == 'associated-value-adapter':
        box = c.Box(x['value']); reader = c.Box.get
        r = {'direct': c.read_content(box), 'referenced': reader(box)}
    elif task == 'module-interface-change': r = c.answer(x['n'], x['offset'])
    elif task == 'ordered-bounded-map':
        data = list(x['values']); r = c.squares(data, x['workers']); extra['input_after'] = data
    elif task == 'typed-error-finally':
        v = c.read_with_trace(x['text'])
        r = {'ok': v.value} if v.ok else {'error_text': v.error_text}
        r['trace'] = v.trace
    elif task == 'joined-yielding-child':
        v = c.joined_answer(x['value']); r = {'value': v.value, 'trace': v.trace}
    else: raise ValueError('unknown task')
    print(json.dumps(dict(extra, result=r), ensure_ascii=False, allow_nan=False, separators=(',', ':')))
'''


def expected(task, cases):
    values = []
    for case in cases:
        value = {'result': case['expected']}
        if task == 'immutable-byte-update': value['input_after'] = case['input']['octets']
        if task == 'ordered-bounded-map': value['input_after'] = case['input']['values']
        values.append(value)
    return values
