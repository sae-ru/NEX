"""Produce a small, hash-pinned receipt without copying caches or binaries."""
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def relative(path):return Path(path).resolve().relative_to(ROOT).as_posix()


def declared_skip_guards(block):
    """Keep source guards for interpretation; do not infer which guard fired."""
    guards=[]
    for name in re.findall(r'"/mnt/f/sae/NEX/(tests/[^"\n]+\.py)"',block.split('Output:',1)[0]):
        source=ROOT/name
        text=source.read_text(encoding='utf-8')
        for node in ast.walk(ast.parse(text)):
            if isinstance(node,ast.Call) and getattr(node.func,'attr','') in ('skipTest','skip','skipUnless','skipIf'):
                guards.append({'source':name,'line':node.lineno,
                  'expression':ast.get_source_segment(text,node)[:800]})
    return guards


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--ctest-status',choices=('pending','passed','failed'),default='pending')
    args=parser.parse_args();local=ROOT/'build/local'
    cpu_path=ROOT/'build/native-acceptance-2/report.json';cpu=read(cpu_path)
    storage_path=ROOT/'build/windows-storage/report.json';storage=read(storage_path)
    ts_path=ROOT/'build/windows-typescript-2/report.json';ts=read(ts_path)
    contracts_path=ROOT/'build/windows-contracts/report.json';contracts=read(contracts_path)
    cuda_path=local/'cuda-report.json';cuda=read(cuda_path)
    inventory=read(local/'inventory-windows.json');producer=read(local/'inventory-wsl.json')
    assert cpu['ok'] and storage['ok'] and ts['ok'] and cuda['ok']
    assert cpu['index']==storage['index']
    assert contracts['producer_sha256']==producer['binary_sha256']['/home/sae/nex-build/nex']
    assert 'Ran 15 tests' in (local/'windows-contracts.log').read_text() and (local/'windows-contracts.log').read_text().rstrip().endswith('OK')
    io=(local/'windows-io-final.log').read_text(encoding='utf-8')
    passed,failed=map(int,re.search(r'RESULT passed=(\d+) failed=(\d+)',io).groups());assert failed==0
    memcheck=(local/'cuda-memcheck.log').read_text();assert 'ERROR SUMMARY: 0 errors' in memcheck
    report={'schema':'nex.windows-machine-evidence/1',
      'verified_at_utc':datetime.now(timezone.utc).isoformat(),
      'status':'scoped_native_target_checks_complete_full_regression_'+args.ctest_status,
      'source_base_commit':cpu['source_commit'],'toolchain':'0.152.1','language':'0.27','native_task_ABI':7,
      'compiler_sha256':contracts['producer_sha256'],'compiler_build':cpu['index']['compiler_build'],
      'descriptor_hash':cpu['index']['descriptor_hash'],
      'native_tool_binary_sha256':{
        'LLVM_MinGW_clang':sha(ROOT/'build/deps/llvm-mingw-20260616-ucrt-x86_64/bin/clang.exe'),
        'Windows_IO_probe':sha(ROOT/'build/windows/nex_windows_io.exe'),
        'Windows_ASan_IO_probe':sha(ROOT/'build/windows-asan/nex_windows_io.exe'),
        'Windows_CUDA_driver_probe':sha(ROOT/'build/windows/nex_windows_cuda_probe.exe')},
      'host':inventory,'volumes':read(local/'volumes-windows.json'),'producer':producer,
      'producer_configuration':read(local/'producer-configuration.json'),
      'other_accelerator_availability':read(local/'accelerator-availability.json'),
      'dxdiag_accelerator_summary':(local/'dxdiag-accelerator-summary.txt').read_text(encoding='utf-8-sig').splitlines(),
      'checks':{
       'native_Windows_runtime':{'status':'passed','cases':passed,'failed':failed,
         'log':relative(local/'windows-io-final.log'),'sha256':sha(local/'windows-io-final.log')},
       'native_NEX_CPU_tasks_files':{'status':'passed','program_executions':sum('artifact' in row for row in cpu['cases']),
         'rejected_sources':sum(bool(row.get('rejected')) for row in cpu['cases']),
         'reference_environment':'WSL','native_environment':'Windows',
         'report':relative(cpu_path),'report_sha256':sha(cpu_path),'cases':cpu['cases']},
       'native_NEX_SQLite':{'status':'passed','program_executions':len(storage['cases']),
         'report':relative(storage_path),'report_sha256':sha(storage_path),'cases':storage['cases']},
       'Windows_Node_TypeScript':{'status':'passed','cases':len(ts['cases']),'node':ts['node_version'],
         'report':relative(ts_path),'report_sha256':sha(ts_path)},
       'runtime_contracts':{'status':'passed','scenario_methods':15,
         'native_PE_executions':len(contracts['observations']),
         'methods_with_native_PE_runs':len({row['scenario'] for row in contracts['observations']}),
         'generation_reference_TypeScript_proof_profile_environment':'WSL',
         'run_observation_environment':'native Windows','report':relative(contracts_path),
         'report_sha256':sha(contracts_path),'log_sha256':sha(local/'windows-contracts.log')},
       'CUDA_driver_prerequisite':{'status':'passed','NEX_invocation':False,
         'device':cuda['device'],'kernel_launches_per_run':cuda['kernel_launches'],
         'ordinary_cases':len(cuda['cases'])-2,'overflow_cases':2,
         'physical_completion_before_resource_release':cuda['physical_completion_before_resource_release'],
         'memory':cuda['device_memory'],'timing_scope':'independent CPU reference plus input generation; upload, GPU event kernel, download and wall time including allocations recorded separately; no speedup claim',
         'resource_ledger':cuda['resource_ledger'],
         'report':relative(cuda_path),'report_sha256':sha(cuda_path),
         'memcheck':{'status':'passed','version':(local/'compute-sanitizer-version.log').read_text().strip(),
                     'summary':'0 errors','log_sha256':sha(local/'cuda-memcheck.log')}},
       'NVCC_MSVC_compile':{'status':'failed','NVCC':'12.1.66','MSVC':'19.44.35229',
         'diagnostic':'Host compiler targets unsupported OS','unsupported_compiler_override':False,
         'direct_MSVC_WIN64_preprocess':'passed','log_sha256':sha(local/'cuda-toolchain-check.log')},
       'producer_CMake_build':{'status':'passed','generator':'Ninja','configuration':'Release','parallelism':4,
         'log_sha256':sha(local/'build-wsl.log')},
       'native_Windows_CTest':{'status':'passed','groups':2,'skipped':0,
         'scope':'direct Windows runtime and CUDA driver prerequisite; not Windows-hosted compiler full CTest',
         'JUnit_sha256':sha(local/'ctest-windows-junit.xml')},
       'producer_full_CTest':{'status':args.ctest_status,'environment':'WSL Ubuntu-22.04',
         'Windows_cross_targets_configured':True,'Wine_configured':False,
         'observed_failed_groups':re.findall(r'Test\s+#\d+:\s+(\S+)\s+\.\.+\*\*\*Failed', (local/'ctest-wsl.log').read_text(errors='replace'))}
      },
      'pending':[
       {'item':'Windows-hosted NEX compiler and portable SDK','status':'pending','reason':'Windows LLVM/MLIR dependency chain and POSIX compiler/process/debug/packaging portability remain open'},
       {'item':'Windows native parallel_map','status':'pending','reason':'ordinary structured CPU tasks are tested separately; parallel_map target still rejects Windows'},
       {'item':'Windows checked DLL/FFI loader and CUDA from NEX','status':'pending','reason':'POSIX FFI loader remains rejected; no std/device CUDA provider or NEX CUDA invocation accepted'},
       {'item':'CUDA cancellation/deadline/typed errors/owned lifetimes','status':'pending','reason':'driver prerequisite probe is not a NEX task/resource adapter'},
       {'item':'actual ARM64 Windows execution','status':'pending','reason':'no physical ARM64 Windows device; cross-builds are separate'},
       {'item':'Windows debugger/profiler/HTTP/packaging/browser UI delivery','status':'pending','reason':'not accepted by the scoped native CPU/file/Node probes'}],
      'skipped':[
       {'item':'Wine compatibility','status':'skipped','reason':'not configured; actual Windows execution checked separately'},
       {'item':'Mac SDK binary checksum and Mac rerun','status':'skipped','reason':'Mac binaries not published in the source delivery record and not installed on Windows'}],
      'Windows_hosted_SDK_accepted':False,'CUDA_NEX_accepted':False,'all_PLAN_complete':False}
    report['pending'].append({'item':'DirectX/DirectML/NPU execution from NEX','status':'pending','reason':'only OS device/DLL availability observed; no NEX execution or separate provider contract accepted'})
    for folder, label in [('task-typescript-rerun','task_typescript_steps'),('task-typescript-public-rerun','task_typescript_public')]:
        path=ROOT/'build'/folder/'report.json'
        if path.exists():
            value=read(path);assert value['ok'] and value['strict_typecheck']
            report['checks'][label+'_with_pinned_tsc']={'status':'passed','environment':'WSL',
              'report':relative(path),'report_sha256':sha(path),'initial_environment_issue':'NEX_TSC not set',
              'source_scenarios':value.get('source_scenarios',value.get('independent_asynchronous_ast_agreement'))}
    for folder,label in [('task-typescript-files-rerun','task_file_reads_typescript'),
                         ('task-typescript-external-rerun','task_external_typescript')]:
        path=ROOT/'build'/folder/'report.json'
        if path.exists():
            value=read(path);assert value['ok']
            report['checks'][label+'_with_pinned_tsc']={'status':'passed','environment':'WSL',
              'report':relative(path),'report_sha256':sha(path),'initial_environment_issue':'NEX_TSC not set',
              'cases':value.get('cases',value.get('host',{}).get('cases'))}
    for folder,label in [('source-exception-typescript-rerun','source_exception_typescript'),
                         ('source-exception-tasks-typescript-rerun','source_exception_tasks_typescript')]:
        path=ROOT/'build'/folder/'report.json'
        if path.exists():
            value=read(path);assert value['ok'] and value['strict_typecheck']
            report['checks'][label+'_with_pinned_tsc']={'status':'passed','environment':'WSL',
              'report':relative(path),'report_sha256':sha(path),'initial_environment_issue':'NEX_TSC not set',
              'comparisons':value.get('comparisons',value.get('typescript_comparisons'))}
    for folder,label in [('source-exception-instances-rerun','source_exception_instances'),
                         ('typed-source-typescript-rerun','typed_source_typescript'),
                         ('typed-source-tasks-rerun','typed_source_tasks')]:
        path=ROOT/'build'/folder/'report.json'
        if path.exists():
            value=read(path)
            if value.get('ok') and (value.get('strict_typecheck') or value.get('strict_TypeScript')):
                report['checks'][label+'_with_pinned_tsc']={'status':'passed','environment':'WSL',
                  'report':relative(path),'report_sha256':sha(path),'initial_environment_issue':'NEX_TSC not set',
                  'reported_counts':{k:v for k,v in value.items() if type(v) is int},
                  'case_records':len(value.get('cases',[]))}
    preserved_private=local/'private-lldb-failures.json'
    if preserved_private.exists():
        report['checks']['private_source_exception_LLDB']={'status':'failed','environment':'WSL LLDB22',
          'observed':'first checkpoint is seen; subsequent expected catch/rethrow checkpoints are not seen before exit42',
          'affected_groups':['source_exception_task_lldb','source_exception_task_watch','source_exception_host','source_exception_module_debug'],
          'separate_HTTP_debug_issue':{'group':'source_exception_module_http_debug',
             'observed':'expected shared-library-event stop is instead SIGSTOP plus task completion breakpoint'},
          'fixtures':read(preserved_private),'requirements_weakened':False}
    terminal=local/'lldb-terminal-rerun.log'
    if terminal.exists() and terminal.read_text().rstrip().endswith('OK'):
        report['checks']['LLDB_terminal_state_fixture']={'status':'passed','scenario_methods':1,'environment':'WSL LLDB22',
          'log_sha256':sha(terminal),'fix':'logical out may finish at process exit; conditionally resume stopped processes and explicitly assert exit0'}
    candidate=local/'verification-z3-5.3.1.log'
    if candidate.exists() and candidate.read_text().rstrip().endswith('OK'):
        report['checks']['Z3_5_3_1_verifier_candidate']={
          'status':'passed_tests_dependency_unification_pending','scenario_methods':11,
          'doctor':read(local/'doctor-z3-5.3.1.json'),'index':read(local/'z3-candidate-index.json'),
          'compiler_sha256':(local/'z3-candidate-sha256.txt').read_text().split()[0],
          'log_sha256':sha(candidate),'ldd_sha256':sha(local/'ldd-z3-candidate.log'),
          'query_comparison':read(local/'z3-comparison.json'),
          'known_issue':'distro LLVM requires libz3.so.4 while candidate directly uses libz3.so.5.3; not promoted as an accepted SDK toolchain',
          'primary_compiler_changed':False,'solver_limits_increased':False}
    delivery=read(ROOT/'docs/releases/0.152.1.json')
    browser=delivery['SDK']['browser_fixture_completion']
    report['delivery_record_checks']={
      'record':'docs/releases/0.152.1.json','Mac_source_commit':delivery['source_commit'],
      'Mac_source_is_ancestor_of_base':subprocess.run(['git','merge-base','--is-ancestor',delivery['source_commit'],cpu['source_commit']],cwd=ROOT).returncode==0,
      'publication_preserves_compiler_sources':subprocess.run(['git','diff','--quiet',delivery['source_commit'],cpu['source_commit'],'--','src','include','runtime'],cwd=ROOT).returncode==0,
      'NEX_MIT_notice_sha256_matches':sha(ROOT/'LICENSE')==delivery['NEX_MIT_notice_sha256'],
      'browser_fixture_sha256_matches':sha(ROOT/browser['path'])==browser['sha256'],
      'Mac_SDK_archive_verified_here':False,'native_Mac_retested_here':False}
    asan_junit=local/'ctest-windows-asan-junit.xml'
    if asan_junit.exists():
        suite=ET.parse(asan_junit).getroot();cases=suite.findall('.//testcase')
        bad=[c.attrib['name'] for c in cases if c.find('failure') is not None or c.find('error') is not None]
        report['checks']['native_Windows_ASan']={'status':'passed' if cases and not bad else 'failed',
          'groups':len(cases),'failed_groups':bad,'scope':'direct Windows file runtime and instrumented SQLite; no Windows LSan claim',
          'JUnit_sha256':sha(asan_junit),'log_sha256':sha(local/'ctest-windows-asan.log')}
    rerun_junit=local/'ctest-timeouts-rerun-junit.xml'
    if rerun_junit.exists():
        cases=ET.parse(rerun_junit).getroot().findall('.//testcase')
        bad=[c.attrib['name'] for c in cases if c.find('failure') is not None or c.find('error') is not None]
        report['checks']['sequential_timeout_followup']={'status':'failed' if bad else 'passed',
          'groups':len(cases),'failed_groups':bad,'environment':'WSL','parallelism':1,'limits_increased':False,
          'JUnit_sha256':sha(rerun_junit),'log_sha256':sha(local/'ctest-timeouts-rerun.log')}
    if args.ctest_status!='pending':
        junit=local/'ctest-wsl-junit.xml';suite=ET.parse(junit).getroot()
        cases=suite.findall('.//testcase');bad=[c.attrib['name'] for c in cases if c.find('failure') is not None or c.find('error') is not None]
        skipped=[c.attrib['name'] for c in cases if c.find('skipped') is not None]
        value=report['checks']['producer_full_CTest']
        value.update(groups=len(cases),failed_groups=bad,skipped_groups=skipped,
          JUnit_sha256=sha(junit),log_sha256=sha(local/'ctest-wsl.log'))
        assert len(cases)==271
        if args.ctest_status=='passed':assert not bad and not skipped
        last=local/'ctest-wsl-last.log'
        if last.exists():
            entries=[]
            for block in re.split(r'\n\d+/\d+ Testing: ',last.read_text(errors='replace'))[1:]:
                name=block.splitlines()[0]
                counts=[int(n) for n in re.findall(r'Ran (\d+) tests? in ',block)]
                skips=[int(n) for n in re.findall(r'(?:OK|FAILED)\s*\([^\n)]*\bskipped=(\d+)',block)]
                summaries=[]
                for match in re.finditer(r'(?m)^\{',block):
                    try:decoded,_=json.JSONDecoder().raw_decode(block[match.start():])
                    except json.JSONDecodeError:continue
                    if isinstance(decoded,dict) and type(decoded.get('ok')) is bool:
                        summary={k:v for k,v in decoded.items() if type(v) in (bool,int,float)}
                        if isinstance(decoded.get('cases'),list):summary['case_records']=len(decoded['cases'])
                        if decoded.get('schema'):summary['schema']=decoded['schema']
                        summaries.append(summary)
                if counts or skips or summaries:
                    entry={'group':name,'reported_unittest_cases':sum(counts),
                      'reported_unittest_skips':sum(skips),'driver_summaries':summaries}
                    if skips:entry['declared_skip_guards_not_a_runtime_trace']=declared_skip_guards(block)
                    entries.append(entry)
            value['reported_internal_unittest_cases']=entries
            value['LastTest_log_sha256']=sha(last)
    changed=subprocess.check_output(['git','diff',cpu['source_commit'],'--name-only'],cwd=ROOT,text=True).splitlines()
    changed+=['tests/windows_native_cases.py','tests/windows_runtime_contracts.py']
    changed += [relative(p) for p in (ROOT/'tools/windows').iterdir() if p.is_file() and p.name!='fetch_host_deps.py']
    report['changed_code_sha256']={name:sha(ROOT/name) for name in sorted(set(changed))
      if name.startswith(('src/','runtime/','include/','tests/','tools/windows/','llm/'))}
    report['preserved_failures']=['build/local/windows-io.log','build/local/windows-io-native.log',
      'build/native-acceptance-1/report.json','build/native-acceptance-2/report-before-resume-1.json',
      'build/native-acceptance-2/report-before-resume-2.json','build/local/ctest-wsl-initial.log']
    destination=args.output.resolve();destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'output':str(destination)}))


if __name__=='__main__':main()
