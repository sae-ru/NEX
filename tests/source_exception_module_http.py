from host_fixture import copy_link_image, native_task_definitions, needed_windows_dlls, shared_profile_objects
"""Ordinary HTTP execution across actual private static/shared code images."""
import os
import hashlib
import copy
import json
import platform
import re
import shutil
from pathlib import Path
import source_exception_http as http
from source_exception_profile_support import host_identity
import source_exception_module_debug_support as debug_support


def context(directory, text, source, default):
    # Keep the original signature diagnostics independent of module placement.
    if directory.name != 'signatures' and not directory.name.startswith(('pure-', 'host-')):
        return default(directory, text)
    directory.mkdir()
    foreign = directory.name == 'signatures' or directory.name.startswith('host-')
    if foreign:
        declarations = re.search(r'server resource Counter;.*?server extern fn bad[^\n]+\n', text, re.S)[0]
        leaf_body = text[text.index('server fn leaf()'):text.index('server fn handle(')]
        leaf = 'module leaf;\n' + declarations.replace('server resource Counter;', 'pub server resource Counter;') + leaf_body.replace('server fn leaf()', 'pub server fn leaf()') + r'''
pub server fn make(v:i64)->Counter !{task,ffi}{return create(v);}
pub server fn peek(v:Counter)->i64 !{task,ffi}{return read(v);}
pub server fn ordinary_error()->result<i64> !{task,ffi}{return ordinary();}
pub trait Render {server fn text(v:Self)->str !{task,throw};}
pub server fn render<T:Render>(v:T)->str !{task,throw}{
 let s:str=Render<T>::text(v);task_yield();
 if s=="GENERIC"{throw("TEMPLATE","λ\u0000🙂");}return s;
}
'''
        body = text[text.index('server fn handle('):].replace('server fn handle(', 'pub server fn run(')
        for old, new in [('Counter', 'leaf::Counter'), ('create(42)', 'leaf::make(42)'), ('read(c)', 'leaf::peek(c)'), ('ordinary()', 'leaf::ordinary_error()'), ('leaf()', 'leaf::leaf()'), ('task_spawn(s,leaf)', 'task_spawn(s,leaf::leaf)')]:
            body = body.replace(old, new)
        body = body.replace('return http::text_response(200,req.user+":"+req.body);', '''if req.path=="/api/generic-error"{return http::text_response(200,leaf::render(Payload(req.user,"GENERIC")));}
 return http::text_response(200,leaf::render(Payload(req.user,req.body)));''')
        mid = r'''module mid;
import "std/http.nex" as http;import "../leaf/main.nex" as leaf;
struct Payload {user:str;body:str;}
server fn render_payload(v:Payload)->str !{task,throw}{task_yield();if v.body=="GENERIC"{return v.body;}return v.user+":"+v.body;}
impl payloads:leaf::Render for Payload{text=render_payload;}
''' + body
        effects = 'task,fs,ffi,throw'
    else:
        leaf = r'''module leaf;
pub server fn fail(body:str)->str !{task,throw}{task_yield();throw("PURE",body);}
'''
        mid = r'''module mid;import "std/http.nex" as http;import "../leaf/main.nex" as leaf;
pub server fn run(req:http::Request)->http::Response !{task,throw}{
 if req.path=="/api/uncaught"{return http::text_response(200,leaf::fail("λ\u0000🙂"));}
 try{return http::text_response(200,leaf::fail(req.body));}catch(code,message){return http::text_response(200,req.user+":"+code+":"+message);}
}
'''
        effects = 'task,throw'
    app = 'module app;import "std/http.nex" as http;import "./mid/main.nex" as mid;\nserver fn handle(req:http::Request)->http::Response !{' + effects + '}{return mid::run(req);}\n'
    units = {'server.nex': app, 'leaf/main.nex': leaf, 'mid/main.nex': mid, '@std/http.nex': (source / 'lib/http.nex').read_text()}
    rows = []
    for unit, value in sorted(units.items()):
        file = directory / ('http.nex' if unit.startswith('@std/') else unit)
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(value, newline="\n")
        rows.append({'unit': unit, 'file': str(file), 'source': value})
    (directory / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1', 'language': '0.24', 'entry': 'server.nex'}), newline="\n")
    result = directory / 'source-context.json'
    result.write_text(json.dumps({'schema': 'nex.private-task-source/2', 'entry_unit': 'server.nex', 'file': str(directory / 'server.nex'), 'source': app, 'units': rows}, ensure_ascii=False) + '\n', newline="\n")
    return result


HOST = r'''#include "nex_host.h"
#include "nex_task_application.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#ifdef _WIN32
#include "host_images.h"
#else
#include <dirent.h>
#endif
#include "host_dlfcn.h"
#ifdef _WIN32
#include "host_images.h"
#elif defined(__APPLE__)
#include <mach-o/dyld.h>
#else
#include <link.h>
#endif
extern int nex_private_http_main(int,char **);
extern "C" const nexrt::TaskCodeDescriptor *ENTRY();
extern "C" const nexrt::TaskExecutionLimits *nex_server_task_limits(){static const nexrt::TaskExecutionLimits limits{100000000,5000,4};return &limits;}
extern "C" nexrt::Handle *nex_server_task_dispatch(nexrt::Handle *value,unsigned workers){return nexrt::executeConfiguredSourceExceptionTaskHttpRequest(*ENTRY(),value,workers);}
static const char *base(const char *p){auto *s=std::strrchr(p,'/');auto *w=std::strrchr(p,'\\');if(w&&(!s||w>s))s=w;return s?s+1:p;}
static long files(){
#ifdef _WIN32
 return static_cast<long>(nex_test::files().size());
#else
auto *d=opendir("/dev/fd");if(!d)std::abort();long n=0;while(auto *e=readdir(d))if(e->d_name[0]!='.')++n;closedir(d);return n;
#endif
}
static bool inspect(const char *symbol,const char *function,const char *expected){
 using Accessor=const nexrt::TaskCodeDescriptor *(*)();auto f=reinterpret_cast<Accessor>(dlsym(RTLD_DEFAULT,symbol));auto *c=f?f():nullptr;
 Dl_info data{},step{};bool ok=c&&c->abi==nexrt::taskCodeExceptionHostPrototypeABI&&dladdr(c,&data)&&dladdr(reinterpret_cast<const void*>(c->step),&step)&&!std::strcmp(base(data.dli_fname),expected)&&!std::strcmp(base(step.dli_fname),expected);
 std::fprintf(stderr,"NEX_PRIVATE_HTTP_ADDRESS {\"function\":\"%s\",\"expected\":\"%s\",\"data\":\"%s\",\"step\":\"%s\",\"ok\":%s}\n",function,expected,data.dli_fname?base(data.dli_fname):"",step.dli_fname?base(step.dli_fname):"",ok?"true":"false");return ok;
}
static void images(unsigned &runtime,unsigned &code){
#ifdef _WIN32
 runtime=nex_test::imageCount("libnex-private-runtime-http.dll");code=nex_test::imageCount("libimage-");
#elif defined(__APPLE__)
 for(uint32_t i=0;i<_dyld_image_count();++i){auto *name=base(_dyld_get_image_name(i));if(std::strstr(name,"libnex-private-runtime-http.dylib"))++runtime;if(!std::strncmp(name,"libimage-",9))++code;}
#else
 struct Counts{unsigned &runtime,&code;} counts{runtime,code};dl_iterate_phdr([](struct dl_phdr_info *image,size_t,void *p){auto &c=*static_cast<Counts*>(p);auto *name=base(image->dlpi_name);if(std::strstr(name,"libnex-private-runtime-http.so"))++c.runtime;if(!std::strncmp(name,"libimage-",9))++c.code;return 0;},&counts);
#endif
}
int main(int argc,char **argv){bool addresses=true;CHECKS
 auto before=nexrt::liveObjects.load();auto descriptors=files();
#ifdef _WIN32
 auto initialFiles=nex_test::files();std::fprintf(stderr,"NEX_PRIVATE_HANDLES_BEFORE ");for(auto h:initialFiles)std::fprintf(stderr,"%llu:%lu ",(unsigned long long)h,GetFileType(reinterpret_cast<HANDLE>(h)));for(auto h:initialFiles)if(GetFileType(reinterpret_cast<HANDLE>(h))==FILE_TYPE_DISK){wchar_t p[32768];auto n=GetFinalPathNameByHandleW(reinterpret_cast<HANDLE>(h),p,32768,0);if(n&&n<32768)std::fprintf(stderr,"DISK[%llu]=%s ",(unsigned long long)h,nexrt::platform::utf8(std::wstring(p,n)).c_str());}std::fprintf(stderr,"\n");
#endif
 auto result=nex_private_http_main(argc,argv);nex_runtime_finish();unsigned runtime=0,code=0;images(runtime,code);
#ifdef _WIN32
 auto finalFiles=nex_test::files();std::fprintf(stderr,"NEX_PRIVATE_HANDLES_AFTER ");for(auto h:finalFiles)std::fprintf(stderr,"%llu:%lu ",(unsigned long long)h,GetFileType(reinterpret_cast<HANDLE>(h)));std::fprintf(stderr,"\n");
#endif
 bool clean=addresses&&nexrt::liveObjects.load()==before&&files()==descriptors&&runtime==EXPECT_RUNTIME&&code==EXPECT_CODE;
 std::fprintf(stderr,"NEX_PRIVATE_HTTP_CLEANUP {\"ok\":%s,\"managed_live\":%llu,\"runtime_finish\":true,\"file_delta\":%ld,\"runtime_images\":%u,\"code_images\":%u}\n",clean?"true":"false",(unsigned long long)(nexrt::liveObjects.load()-before),files()-descriptors,runtime,code);return clean?result:71;
}
'''


def build(state, name, directory, ctx, out, optimization):
    run, report, compiler = state['run'], state['report'], state['compiler']
    probe = state['module_probe']
    assert probe and probe.is_file(), '--module-probe is required'
    foreign = name.startswith('host-')
    topology = name.split('-', 1)[1]
    links = {'static': {'std': 'static', 'leaf': 'static', 'mid': 'static'},
             'shared': {'std': 'shared', 'leaf': 'shared', 'mid': 'shared'},
             'mixed': {'std': 'shared', 'leaf': 'static', 'mid': 'shared'}}[topology]
    entries = {'std': 'std::http::text_response', 'leaf': 'leaf::leaf' if foreign else 'leaf::fail', 'mid': 'mid::run', 'app': 'app::handle'}
    components = {key: {'entry': entry, 'units': [{'std': '@std/http.nex', 'app': 'server.nex'}.get(key, key + '/main.nex')],
                        'exports': ['leaf::make', 'leaf::peek', 'leaf::ordinary_error'] if key == 'leaf' and foreign else [],
                        'dependencies': {'std': [], 'leaf': [], 'mid': ['std', 'leaf'], 'app': ['std', 'mid']}[key],
                        'linkage': 'application' if key == 'app' else links[key], 'instantiations': []} for key, entry in entries.items()}
    catalogue = json.loads(run(name + '-instances', [probe, 'instances', ctx]).stdout)
    if foreign:
        selected = [key for key, row in catalogue['instances'].items() if row['template'] == 'leaf::render' and row['arguments'] == ['mid::Payload']]
        assert len(selected) == 1, catalogue
        components['mid']['instantiations'] = selected
    profiled=state.get('profiling',False);debugged=state.get('debugging',False);version=6 if debugged else 5 if profiled else 4
    architecture = {'schema': 'nex.private-task-architecture/'+str(version), 'mode': 'mixed-fixed', 'application': 'app', 'host': 'http', 'components': components}
    if profiled:architecture['instrumentation']='profile'
    if debugged:architecture.update(instrumentation='debug',debug_timeout_ms=60000)
    arch = directory / 'architecture.json'
    arch.write_text(json.dumps(architecture) + '\n', newline="\n")
    plan = json.loads(run(name + '-plan', [probe, 'plan', ctx, arch]).stdout)
    (out / 'plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2) + '\n', newline="\n")
    assert plan['schema'] == 'nex.private-task-modules/'+str(version) and plan['host'] == 'http'
    assert plan['components']['app']['entry_kind'] == 'http'
    mac = platform.system() == 'Darwin'
    suffix = '.dll' if os.name=='nt' else '.dylib' if mac else '.so'
    shared = plan['runtime_linkage'] == 'shared'
    runtime_name = 'libnex-private-runtime-http' + suffix
    runtime_objects = [v for v in state['objects'] if v.name != 'http_main.cpp.o']
    label = name + '-O' + optimization
    if shared:
        if profiled:runtime_objects=shared_profile_objects(runtime_objects,state['flags'],compiler,state['runtime'],run)
        runtime = state['cache'] / runtime_name
        if not state.get('module_http_runtime_built'):
            run('http-runtime-shared', [compiler, '-dynamiclib' if mac else '-shared', *runtime_objects, state['ssl'], state['crypto'], state['sqlite'], '-pthread', *(['-Wl,-install_name,@rpath/' + runtime.name] if mac else ['-ldl', '-Wl,-soname,' + runtime.name]), '-o', runtime])
            state['module_http_runtime_built'] = True
        copy_link_image(runtime, out / runtime.name)
    wrapped = state['cache'] / 'http_main_wrapped.o'
    if not state.get('module_http_main_built'):
        run('http-main-wrapped', [compiler, *state['flags'], '-Dmain=nex_private_http_main', '-c', state['runtime'] / 'http_main.cpp', '-o', wrapped])
        state['module_http_main_built'] = True
    records, accessors, symbols, metadata = {}, {}, {}, None
    for component in plan['load_order']:
        module = out / component
        run(label + '-' + component + '-emit', [probe, 'emit', ctx, arch, component, module, state['triple'], state['layout'], str(optimization == '2').lower()])
        record = json.loads((module / 'module-record.json').read_text())
        assert record == plan['components'][component] and record['schema'] == 'nex.private-task-module/'+str(version)
        run(label + '-' + component + '-validate', [probe, 'validate', ctx, arch, component, module / 'module-record.json'])
        records[component] = record
        ir = (module / 'module.ll').read_text()
        assert not re.search(r'^define[^\n]*@main\(', ir, re.M)
        symbols[component] = re.findall(r'^define[^\n]*@([^\s(]+__task_step)\(', ir, re.M)
        assert len(symbols[component]) == len(record['definitions'])
        run(label + '-' + component + '-object', [compiler, '-c', '-fPIC', '-O' + optimization, module / 'module.ll', '-o', module / 'module.o'])
        metadata = json.loads((module / 'metadata.json').read_text())
        accessors.update({key: row['accessor'] for kind in ['exports', 'support_exports', 'instantiation_descriptors'] for key, row in record.get(kind, {}).items()})
        if component == 'app':
            assert metadata['descriptor_symbol'] == record['entry_descriptor']
            accessors[record['entry']] = record['entry_descriptor']
        if record['linkage'] == 'static':
            run(label + '-' + component + '-archive', [compiler.parent / 'llvm-ar', 'rcs', out / ('lib' + component + '.a'), module / 'module.o'])
    def filename(image):
        return ('server.exe' if os.name=='nt' else 'server') if image == 'app' else 'libimage-' + image + suffix
    checks = ['addresses=inspect(' + ','.join(map(json.dumps, [accessor, function, filename(plan['definition_owners'][function])])) + ')&&addresses;' for function, accessor in sorted(accessors.items())]
    host = HOST.replace('ENTRY', plan['components']['app']['entry_descriptor']).replace('CHECKS', '\n'.join(checks)).replace('EXPECT_RUNTIME', str(int(shared))).replace('EXPECT_CODE', str(len(plan['images']) - 1))
    if profiled:
        host=host_identity(plan)+host.replace('int main(int argc,char **argv){bool addresses=true;', 'int main(int argc,char **argv){nex_task_profile_prepare_application_v1();bool addresses=true;')
    if debugged:
        host=debug_support.host_identity(plan)+host.replace('100000000,5000,4','100000000,60000,4').replace('int main(int argc,char **argv){bool addresses=true;', 'int main(int argc,char **argv){nex_task_debug_prepare_application_v1();nex_private_module_debug_start();bool addresses=true;').replace('bool clean=addresses&&','bool clean=nex_private_module_debug_finish()&&addresses&&')
    (out / 'host.cpp').write_text(host, newline="\n")
    run(label + '-host', [compiler, *state['flags'], '-c', out / 'host.cpp', '-o', out / 'host.o'])
    images, physical = {}, {}
    for image in plan['image_load_order']:
        row = plan['images'][image]
        args = [compiler, *([] if image == 'app' else ['-dynamiclib' if mac else '-shared']), out / image / 'module.o']
        if image == 'app':
            args += [out / 'host.o', wrapped, '-Wl,-export_dynamic' if mac else '-Wl,--export-dynamic']
        for component in row['static_components']:
            archive = out / ('lib' + component + '.a')
            args += ['-Wl,-force_load,' + str(archive)] if mac else ['-Wl,--whole-archive,' + str(archive) + ',--no-whole-archive']
        args += (needed_windows_dlls([out/(filename(dependency)+'.a') for dependency in row['dependencies']],compiler) if os.name=='nt' else ['-Wl,-needed_library,' + str(out / filename(dependency)) for dependency in row['dependencies']] if mac else ['-Wl,--no-as-needed', *[out / filename(dependency) for dependency in row['dependencies']]])
        args += ['-L' + str(out), '-lnex-private-runtime-http'] if shared else [*runtime_objects, state['ssl'], state['crypto'], state['sqlite'], '-pthread', *([] if mac else ['-ldl'])]
        if shared and image == 'app':args += [state['ssl'], state['crypto'], state['sqlite'], '-pthread', *([] if mac else ['-ldl'])]
        if image != 'app':args += ['-Wl,-install_name,@rpath/' + filename(image)] if mac else ['-Wl,-soname,' + filename(image)]
        if shared:args += ['-Wl,-rpath,@loader_path'] if mac else ['-Wl,-rpath,$ORIGIN', '-Wl,-z,defs']
        binary = out / filename(image)
        run(label + '-link-' + image, [*args, '-o', binary])
        inventory = run(label + '-symbols-' + image, [compiler.parent / 'llvm-nm', '--defined-only', '--format=posix', binary]).stdout
        actual = native_task_definitions(inventory,binary,compiler)
        expected = {symbol for component in records if plan['component_images'][component] == image for symbol in symbols[component]}
        assert len(actual) == len(row['definitions']) and set(actual) == expected, (image, actual, expected)
        physical[image] = actual
        images[image] = {'file': binary.name, 'sha256': hashlib.sha256(binary.read_bytes()).hexdigest()}
    assert len(set(v for row in physical.values() for v in row)) == sum(map(len, physical.values()))
    case = {'program': name, 'optimization': optimization, 'topology': topology, 'images': images, 'physical_symbols': physical,
            'accessors': accessors, 'runtime_images': int(shared), 'code_images': len(plan['images']) - 1,
            'module_records': {key: hashlib.sha256((out / key / 'module-record.json').read_bytes()).hexdigest() for key in records},
            'source_hashes': {row['unit']: hashlib.sha256(row['source'].encode()).hexdigest() for row in json.loads(ctx.read_text())['units']}, 'passed': True}
    report.setdefault('module_images', []).append(case)
    state.setdefault('module_http_cases', {})[str(out / ('server.exe' if os.name=='nt' else 'server'))] = case
    state['save']()
    return {'descriptor_abi': 0x4e45585400002502, 'operations': metadata['operations']}, out / ('server.exe' if os.name=='nt' else 'server')


def observe(binary, row):
    cleanup = [json.loads(v.split(' ', 1)[1]) for v in row['stderr'].splitlines() if v.startswith('NEX_PRIVATE_HTTP_CLEANUP ')]
    addresses = [json.loads(v.split(' ', 1)[1]) for v in row['stderr'].splitlines() if v.startswith('NEX_PRIVATE_HTTP_ADDRESS ')]
    plan = json.loads((binary.parent / 'plan.json').read_text())
    assert len(cleanup) == 1 and cleanup[0] == {'ok': True, 'managed_live': 0, 'runtime_finish': True, 'file_delta': 0, 'runtime_images': int(plan['runtime_linkage'] == 'shared'), 'code_images': len(plan['images']) - 1}
    expected = {key for record in plan['components'].values() for kind in ['exports', 'support_exports', 'instantiation_descriptors'] for key in record.get(kind, {})} | {plan['components']['app']['entry']}
    assert len(addresses) == len(expected) and {v['function'] for v in addresses} == expected
    assert all(v['ok'] and v['data'] == v['step'] == v['expected'] for v in addresses)
    row.update(cleanup=cleanup[0], addresses=addresses)


def contracts(state):
    report, out, run, probe = [state[key] for key in ['report', 'out', 'run', 'module_probe']]
    report['module_contract_rejections'] = []
    base = out / 'pure-static'
    if not base.exists():return
    ctx, arch = base / 'source-context.json', base / 'architecture.json'
    original = json.loads(arch.read_text())
    negative = out / 'module-contracts'
    negative.mkdir()
    bad = {}
    for name, key, value in [('unknown-host', 'host', 'worker'), ('legacy-host-field', 'schema', 'nex.private-task-architecture/3'), ('HTTP-not-process-entry', 'host', 'application')]:
        changed = copy.deepcopy(original);changed[key] = value
        bad[name] = (changed, 'E_ENTRY' if name == 'HTTP-not-process-entry' else 'E_EXCEPTION_MODULE')
    changed = copy.deepcopy(original);changed.pop('host');bad['missing-host'] = (changed, 'E_EXCEPTION_MODULE')
    for name, (value, code) in bad.items():
        file = negative / (name + '.json');file.write_text(json.dumps(value), newline="\n")
        rejected = run('reject-module-' + name, [probe, 'plan', ctx, file], allowed=(1,))
        assert code in rejected.stderr
        report['module_contract_rejections'].append({'name': name, 'code': code, 'passed': True})
    source = json.loads(ctx.read_text())
    for name, body in [('no-task', 'server fn handle(req:http::Request)->http::Response{return http::text_response(200,req.body);}'),
                       ('wrong-request', 'server fn handle(req:str)->http::Response !{task}{return http::text_response(200,req);}'),
                       ('wrong-result', 'server fn handle(req:http::Request)->str !{task}{return req.body;}'),
                       ('wrong-realm', 'fn handle(req:http::Request)->http::Response !{task}{return http::text_response(200,req.body);}')]:
        changed = copy.deepcopy(source)
        entry = next(row for row in changed['units'] if row['unit'] == changed['entry_unit'])
        entry['source'] = 'module app;import "std/http.nex" as http;import "./mid/main.nex" as mid;\n' + body
        changed['source'] = entry['source']
        file = negative / (name + '.json');file.write_text(json.dumps(changed, ensure_ascii=False), newline="\n")
        rejected = run('reject-module-' + name, [probe, 'plan', file, arch], allowed=(1,))
        assert 'E_HTTP_SIGNATURE' in rejected.stderr
        report['module_contract_rejections'].append({'name': name, 'code': 'E_HTTP_SIGNATURE', 'passed': True})
    record = json.loads((base / 'O0/app/module-record.json').read_text())
    for field, value in [('entry_kind', 'application'), ('entry_descriptor', 'missing'), ('descriptor_abi', 0x4e45585400000005)]:
        changed = copy.deepcopy(record);changed[field] = value
        file = negative / ('record-' + field + '.json');file.write_text(json.dumps(changed), newline="\n")
        rejected = run('reject-module-record-' + field, [probe, 'validate', ctx, arch, 'app', file], allowed=(1,))
        assert 'E_EXCEPTION_MODULE' in rejected.stderr
        report['module_contract_rejections'].append({'name': 'record-' + field, 'code': 'E_EXCEPTION_MODULE', 'passed': True})
    # /4 can also name an ordinary process root; HTTP does not weaken that rule.
    changed = copy.deepcopy(source)
    entry = next(row for row in changed['units'] if row['unit'] == changed['entry_unit'])
    entry['source'] = 'module app;import "std/http.nex" as http;import "./mid/main.nex" as mid;fn main()->i64 !{task}{return 42;}'
    changed['source'] = entry['source']
    file = negative / 'application-context.json';file.write_text(json.dumps(changed), newline="\n")
    architecture = copy.deepcopy(original);architecture['host'] = 'application';architecture['components']['app']['entry'] = 'app::main'
    model = negative / 'application-architecture.json';model.write_text(json.dumps(architecture), newline="\n")
    plan = json.loads(run('module-application-host', [probe, 'plan', file, model]).stdout)
    assert plan['host'] == plan['components']['app']['entry_kind'] == 'application'
    assert 'entry_descriptor' not in plan['components']['app']
    report['application_host_checked'] = True
    state['save']()


def reuse_and_relocate(state):
    report, out, run, probe, compiler = [state[key] for key in ['report', 'out', 'run', 'module_probe', 'compiler']]
    report['provider_reuse'], report['relocated'] = [], []
    def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
    for name in ['pure-static', 'pure-shared', 'pure-mixed', 'host-shared']:
        directory = out / name
        if not directory.exists():continue
        ctx, arch, e = directory / 'source-context.json', directory / 'architecture.json', directory / 'O0'
        source = json.loads(ctx.read_text())
        root = directory / 'server.nex'
        saved_root = root.read_bytes()
        entry = next(v for v in source['units'] if v['unit'] == 'server.nex')
        entry['source'] = entry['source'].replace('return mid::run(req);', 'let r:http::Response=mid::run(req);return http::text_response(r.status,r.body+"!");')
        source['source'] = entry['source']
        changed = directory / 'changed-context.json';changed.write_text(json.dumps(source, ensure_ascii=False), newline="\n")
        plan = json.loads(run(name + '-reuse-plan', [probe, 'plan', changed, arch]).stdout)
        original = json.loads((e / 'plan.json').read_text())
        assert all(plan['components'][key] == original['components'][key] for key in ['std', 'leaf', 'mid'])
        assert plan['components']['app'] != original['components']['app']
        module = e / 'changed-app'
        run(name + '-reuse-emit', [probe, 'emit', changed, arch, 'app', module, state['triple'], state['layout'], 'false'])
        run(name + '-reuse-object', [compiler, '-c', '-fPIC', '-O0', module / 'module.ll', '-o', module / 'module.o'])
        providers = [e / key / 'module-record.json' for key in ['std', 'leaf', 'mid']] + list(e.glob('lib*.a')) + list(e.glob('lib*.so')) + list(e.glob('lib*.dylib')) + list(e.glob('lib*.dll'))
        hashes = {str(path.relative_to(e)): digest(path) for path in providers}
        argv = next(row['argv'] for row in report['commands'] if row['label'] == name + '-O0-link-app')
        argv = [str(module / 'module.o') if value == str(e / 'app/module.o') else value for value in argv]
        if state.get('debugging'):
            old=(e/'host.cpp').read_text();assert debug_support.host_identity(original) in old
            (module/'host.cpp').write_text(old.replace(debug_support.host_identity(original),debug_support.host_identity(plan),1), newline="\n")
            run(name+'-reuse-debug-host',[compiler,*state['flags'],'-c',module/'host.cpp','-o',module/'host.o'])
            argv=[str(module/'host.o') if value==str(e/'host.o') else value for value in argv]
        if state.get('profiling'):
            old=(e/'host.cpp').read_text();assert host_identity(original) in old
            (module/'host.cpp').write_text(old.replace(host_identity(original),host_identity(plan),1), newline="\n")
            run(name+'-reuse-profile-host',[compiler,*state['flags'],'-c',module/'host.cpp','-o',module/'host.o'])
            argv=[str(module/'host.o') if value==str(e/'host.o') else value for value in argv]
        server = e / ('server.exe' if os.name=='nt' else 'server');saved = e / 'original-server';server.rename(saved)
        plan_raw = (e / 'plan.json').read_bytes()
        try:
            root.write_text(entry['source'], newline="\n");(e / 'plan.json').write_text(json.dumps(plan), newline="\n")
            run(name + '-reuse-link', argv)
            rebuilt_hash = digest(server)
            with state['server'](server, name.startswith('host-')) as (port, files, events):
                response = state['request'](port, '/api/recover')
                expected = 'alice:HOST:λ\0🙂:A🌍\0β!' if name.startswith('host-') else 'alice:PURE:A🌍\0β!'
                assert response['status'] == 200 and response['body'] == expected, response
            assert hashes == {str(path.relative_to(e)): digest(path) for path in providers}
            report['provider_reuse'].append({'program': name, 'provider_records_identical': True, 'provider_artifacts_unchanged': True, 'providers': hashes, 'rebuilt_image_sha256': rebuilt_hash, 'consumer_record_changed': True, 'passed': True})
        finally:
            root.write_bytes(saved_root);(e / 'plan.json').write_bytes(plan_raw)
            if server.exists():server.rename(e / 'rebuilt-server')
            saved.rename(server)
        state['save']()
    for name in ['host-shared', 'host-mixed']:
        directory = out / name
        if not directory.exists():continue
        original = directory / 'O2'
        target = out / ('relocated-' + name);target.mkdir()
        copy_link_image(directory / 'source-context.json', target / 'source-context.json')
        e = target / 'O2';e.mkdir()
        for file in [original / ('server.exe' if os.name=='nt' else 'server'), original / 'plan.json', *original.glob('lib*.so'), *original.glob('lib*.dylib'), *original.glob('lib*.dll')]:shutil.copy2(file, e / file.name)
        hashes = {file.name: digest(file) for file in e.iterdir() if file.name != 'plan.json'}
        hidden = directory / 'O2.hidden';original.rename(hidden)
        try:
            with state['server'](e / ('server.exe' if os.name=='nt' else 'server'), True, tls=True) as (port, files, events):
                response = state['request'](port, '/api/recover', tls=True)
                assert response['status'] == 200 and response['body'] == 'alice:HOST:λ\0🙂:A🌍\0β'
                response = state['request'](port, '/api/generic-error', tls=True)
                assert response['status'] == 500 and json.loads(response['body'])['error']['code'] == 'E_SOURCE_EXCEPTION'
            assert all(digest(e / file) == digest(hidden / file) == sha for file, sha in hashes.items())
            report['relocated'].append({'program': name, 'images': hashes, 'original_images_and_sources_absent': True, 'passed': True})
        finally:hidden.rename(original)
        state['save']()


def main(profiling=False,finalize=True,observer=None,debugging=False):
    state = http.main(build, context, 'NEX_EXCEPTION_MODULE_HTTP_DEBUG_OUTPUT' if debugging else 'NEX_EXCEPTION_MODULE_HTTP_PROFILE_OUTPUT' if profiling else 'NEX_EXCEPTION_MODULE_HTTP_OUTPUT', ['static', 'shared', 'mixed'], ['/api/generic-error'], False, observer or observe,profiling,debugging)
    contracts(state)
    reuse_and_relocate(state)
    report = state['report']
    report.update(ok=finalize, HTTP_requests=len(report['requests']), HTTP_server_launches=len(report['servers']), private_modular_HTTP=True, actual_symbol_and_loader_ownership=True, joined_shutdown_cleanup=True)
    state['save']()
    if finalize:print(json.dumps({'ok': True, 'images': len(report['images']), 'requests': len(report['requests']), 'report': str(state['out'] / 'report.json')}))
    return state


if __name__ == '__main__':main()
