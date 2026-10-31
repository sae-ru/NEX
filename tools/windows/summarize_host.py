"""Keep a compact receipt for a frozen local Windows compiler and its runs."""
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import re
import subprocess
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def relative(path):return Path(path).resolve().relative_to(ROOT).as_posix()
def text(path):
    data=Path(path).read_bytes()
    return data.decode('utf-16' if data.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8-sig',errors='replace')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('compiler','cpu','storage','typescript','closure','ctest','ctest-log','last-test','build-log','probe-log','verification-log','contracts-log','example','context','output'):
        parser.add_argument('--'+name,required=True,type=Path)
    args=parser.parse_args()
    cpu,storage,ts=(read(getattr(args,key)) for key in ('cpu','storage','typescript'))
    compiler=sha(args.compiler)
    for report in (cpu,storage,ts):
        assert report['ok'] and report['producer_sha256']==compiler
        assert report['requires_WSL'] is False
    context=read(args.context)
    assert not context['is_app_container'] and not context['is_elevated']
    probe=text(args.probe_log)
    assert 'RESULT passed=8 failed=0' in probe
    cases=ET.parse(args.ctest).getroot().findall('.//testcase')
    grouped={'passed':[],'failed':[],'skipped':[]}
    for case in cases:
        skipped=case.find('skipped')
        unavailable=skipped is not None and skipped.attrib.get('message') in ('Unable to find executable','Fixture dependency failed')
        state='failed' if case.find('failure') is not None or case.find('error') is not None or unavailable else 'skipped' if skipped is not None else 'failed' if case.attrib.get('status')=='notrun' else 'passed'
        grouped[state].append(case.attrib['name'])
    last=text(args.last_test)
    skips=[]
    for block in re.split(r'\n(?=\d+/\d+ Testing:)',last):
        counts=re.findall(r'^(?:OK|FAILED)\s*\([^\r\n)]*\bskipped=(\d+)\)',block,re.M)
        if counts:
            label=re.search(r'Test: ([^\r\n]+)',block)
            guards=[]
            for filename in re.findall(r'"([^"\n]+\.py)"',block.split('Output:',1)[0]):
                path=Path(filename)
                if not path.is_file() or not path.resolve().is_relative_to(ROOT):continue
                source=path.read_text(encoding='utf-8')
                for node in ast.walk(ast.parse(source)):
                    if isinstance(node,ast.Call) and getattr(node.func,'attr','') in ('skipTest','skip','skipUnless','skipIf'):
                        guards.append({'source':relative(path),'line':node.lineno,'expression':ast.get_source_segment(source,node)[:800]})
            skips.append({'group':label.group(1) if label else 'unknown','internal_unittest_skips':sum(map(int,counts)),'declared_guards_not_inferred_as_fired':guards})
    build=text(args.build_log)
    verification=text(args.verification_log)
    contracts=text(args.contracts_log)
    paths=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard'],cwd=ROOT,text=True).splitlines()
    pins={name:sha(ROOT/name) for name in paths if (name.startswith(('src/','include/','runtime/','tools/windows/')) or name in ('CMakeLists.txt','llm/language-pack.json','tests/windows_host_runtime.cpp','nex.cmd') or name.startswith('examples/windows-host/')) and (ROOT/name).is_file()}
    artifacts={key:{'path':relative(getattr(args,key)),'sha256':sha(getattr(args,key))} for key in ('cpu','storage','typescript','closure','ctest','ctest_log','last_test','build_log','probe_log','verification_log','contracts_log','example','context')}
    receipt={
        'schema':'nex.windows-host-evidence/1','verified_at_utc':datetime.now(timezone.utc).isoformat(),
        'status':'local_native_windows_compiler_accepted_portable_sdk_and_full_regression_not_accepted',
        'source_parent_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'source_pins_sha256':pins,'language':'0.27','toolchain':'0.152.1 development','native_task_ABI':7,
        'compiler':{'path':relative(args.compiler),'sha256':compiler,'index':cpu['index'],'doctor':cpu['doctor'],
                    'requires_WSL':False,'requires_MSYS_runtime':False,'execution_context':context},
        'accepted_target_toolchain':cpu['toolchain'],
        'compiled_default_toolchain':{'path':relative(args.compiler.parent/'toolchain.json'),'sha256':sha(args.compiler.parent/'toolchain.json'),'configuration':read(args.compiler.parent/'toolchain.json')},
        'host':{'windows_version':platform.win32_ver(),'machine':platform.machine()},
        'acceptance':{
            'cpu_tasks_files':{'status':'passed','cases':len(cpu['cases']),'native_PE_runs':sum('artifact' in c for c in cpu['cases']),
                               'byte_preserving_stdout':['CR','LF','NUL','UTF-8'],'cases_detail':cpu['cases']},
            'sqlite':{'status':'passed','cases':len(storage['cases'])},
            'typescript':{'status':'passed','cases':len(ts['cases']),'node_version':ts['node_version']},
            'windows_host_runtime':{'status':'passed','checks':8,'physical_completion':'retained job member process handles waited after termination; notification count checked against TotalProcesses; bounded10s failure is explicit','stdout':probe},
            'verification':{'status':'passed' if re.search(r'Ran 11 tests.*\bOK\b',verification,re.S) else 'failed','stdout':verification},
            'runtime_contracts':{'status':'failed','stdout':contracts},
            'all_target_build':{'status':'failed' if 'FAILED:' in build else 'passed','failed_steps':re.findall(r'^FAILED:.*',build,re.M)},
            'full_native_ctest':{'status':'failed' if grouped['failed'] else 'passed','total_groups':len(cases),'groups':grouped,'not_run_groups':[c.attrib['name'] for c in cases if c.attrib.get('status')=='notrun'],'raw_junit_summary':ET.parse(args.ctest).getroot().attrib,'internal_skips':skips,'internal_skip_total':sum(s['internal_unittest_skips'] for s in skips),'parallel':4,'PYTHONUTF8':'1','NEX_TSC':'web/node_modules/typescript/bin/tsc','private_probe_compilation_failures_are_not_skipped':True},
            'snapshot_example':read(args.example)},
        'dependency_lock_sha256':sha(ROOT/'tools/windows/host-dependencies.lock.json'),
        'dll_closure':read(args.closure),'artifacts':artifacts,
        'previous_target_only_evidence':'docs/evidence/windows-native-2026-10-31.json',
        'windows_security_report':{'reported_prefix':'nex-windows-','exact_executable':'unknown','matching_Defender_AppLocker_CodeIntegrity_event':'not found in inspected logs','query':read(ROOT/'build/local/windows-security-query.json'),'query_sha256':sha(ROOT/'build/local/windows-security-query.json'),'new_native_compiler_and_example':'executed successfully in ordinary user context','protection_exclusions_added':False},
        'pending':['portable Windows SDK installation/relocation and notices acceptance','Windows source FFI/task foreign/providers acceptance','CUDA invoked from NEX with physical completion and resource receipts','Windows debugger/profiler and HTTP/network hosting','Windows full regression and POSIX-only probe ports','actual Windows ARM64 hardware execution','DirectX/DirectML/NPU provider contracts and execution']}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_bytes((json.dumps(receipt,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
    print(json.dumps({'output':str(args.output),'compiler_sha256':compiler,'ctest_groups':len(cases),'failed_groups':len(grouped['failed'])}))


if __name__=='__main__':main()
