"""Owned SDK fixtures exercise archive integrity and extraction boundaries."""
import ast
import copy
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import re
import shlex
import shutil
import socket
import subprocess
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location('sdk_archive', Path(__file__).resolve().parents[1]/'tools/sdk_archive.py')
archive = importlib.util.module_from_spec(spec); spec.loader.exec_module(archive)
spec = importlib.util.spec_from_file_location('sdk_acceptance', Path(__file__).resolve().parents[1]/'tools/sdk_acceptance.py')
acceptance = importlib.util.module_from_spec(spec); spec.loader.exec_module(acceptance)


class WindowsDebuggerPatchBytes(unittest.TestCase):
    def setUp(self):
        spec=importlib.util.spec_from_file_location('windows_debugger_build',Path(__file__).resolve().parents[1]/'tools/windows/build_debugger.py')
        self.builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.builder)
        temporary=tempfile.TemporaryDirectory(prefix='nex debugger patch % ');self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name);self.source=self.root/'source';self.source.mkdir()
        self.patch_root=self.root/'patches';self.patch_root.mkdir()
        self.before=b'alpha\nbeta\n';self.after=b'alpha\ngamma\n'
        self.target=self.source/'sample.cpp';self.target.write_bytes(self.before)
        self.patch=self.patch_root/'fix.patch'
        self.patch.write_bytes(b'--- a/sample.cpp\n+++ b/sample.cpp\n@@ -1,2 +1,2 @@\n alpha\n-beta\n+gamma\n')
        self.record={'patch':'fix.patch','patch_sha256':self.builder.sha(self.patch),'source_file':'sample.cpp',
                     'original_sha256':self.builder.sha(self.target),'patched_sha256':hashlib.sha256(self.after).hexdigest()}
        subprocess.run(['git','init','--quiet',str(self.source)],check=True,capture_output=True)
        subprocess.run(['git','-C',str(self.source),'config','core.autocrlf','true'],check=True,capture_output=True)
        subprocess.run(['git','-C',str(self.source),'config','core.eol','crlf'],check=True,capture_output=True)
        subprocess.run(['git','-C',str(self.source),'add','sample.cpp'],check=True,capture_output=True)

    def prepare(self):
        with mock.patch.object(self.builder,'HERE',self.patch_root):
            return self.builder.prepare_source_patch(self.source,self.record,'fixture')

    def test_real_git_preserves_pinned_LF_bytes_despite_CRLF_configuration(self):
        self.assertTrue(self.prepare()['applied']);self.assertEqual(self.target.read_bytes(),self.after)
        self.assertFalse(self.prepare()['applied']);self.assertEqual(self.target.read_bytes(),self.after)
        self.assertEqual(subprocess.check_output(['git','-C',str(self.source),'config','core.autocrlf'],text=True).strip(),'true')
        self.assertEqual(subprocess.check_output(['git','-C',str(self.source),'config','core.eol'],text=True).strip(),'crlf')

    def test_changed_source_is_rejected_without_rewriting(self):
        altered=self.before+b'unknown change\n';self.target.write_bytes(altered)
        with self.assertRaisesRegex(ValueError,'source checksum differs'):self.prepare()
        self.assertEqual(self.target.read_bytes(),altered)

    def test_preexisting_CRLF_is_not_silently_relabelled_as_a_pinned_source(self):
        altered=self.after.replace(b'\n',b'\r\n');self.target.write_bytes(altered)
        with self.assertRaisesRegex(ValueError,'source checksum differs'):self.prepare()
        self.assertEqual(self.target.read_bytes(),altered)

    def test_changed_patch_is_rejected_before_source_mutation(self):
        self.patch.write_bytes(self.patch.read_bytes()+b'unknown\n')
        with self.assertRaisesRegex(ValueError,'patch checksum differs'):self.prepare()
        self.assertEqual(self.target.read_bytes(),self.before)


class MacFloatHeaderCompatibility(unittest.TestCase):
    def setUp(self):
        spec=importlib.util.spec_from_file_location('mac_float_bundle',Path(__file__).resolve().parents[1]/'tools/sdk_bundle.py')
        self.bundle=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.bundle)
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup);self.root=Path(temporary.name)

    def test_partial_requests_are_forwarded_outside_the_guard_and_original_bytes_retained(self):
        original=b'// retained license\n#ifndef _LIBCPP_FLOAT_H\n#define _LIBCPP_FLOAT_H\n#include_next <float.h>\n#endif // _LIBCPP_FLOAT_H\n'
        path=self.root/'float.h';path.write_bytes(original);pin=hashlib.sha256(original).hexdigest()
        with mock.patch.object(self.bundle,'MACOS_FLOAT_HEADER_SHA256',pin):report=self.bundle.patch_macos_float_header(path)
        data=path.read_bytes();prefix=(b'// NEX LLVM22 compatibility: Apple math.h may request only INFINITY/NAN.\n'
            b'#if defined(__need_infinity_nan)\n#  include_next <float.h>\n#else\n')
        self.assertEqual(data.replace(prefix,b'',1).removesuffix(b'#endif // __need_infinity_nan\n'),original)
        self.assertLess(data.index(b'defined(__need_infinity_nan)'),data.index(b'#ifndef _LIBCPP_FLOAT_H'))
        self.assertEqual(report['source_sha256'],pin);self.assertEqual(report['patched_sha256'],hashlib.sha256(data).hexdigest())

    def test_unknown_or_changed_upstream_header_is_never_rewritten(self):
        path=self.root/'float.h';original=b'unknown libc++ header\n';path.write_bytes(original)
        with self.assertRaisesRegex(ValueError,'unqualified macOS libc'):self.bundle.patch_macos_float_header(path)
        self.assertEqual(path.read_bytes(),original)

    def test_wrong_guard_structure_is_rejected_even_after_a_digest_match(self):
        for data in [b'no guard\n',b'#ifndef _LIBCPP_FLOAT_H\n#endif // _LIBCPP_FLOAT_H\nextra\n']:
            path=self.root/'float.h';path.write_bytes(data)
            with mock.patch.object(self.bundle,'MACOS_FLOAT_HEADER_SHA256',hashlib.sha256(data).hexdigest()):
                with self.assertRaisesRegex(ValueError,'guard structure'):self.bundle.patch_macos_float_header(path)
            self.assertEqual(path.read_bytes(),data)

    def test_new_toolchains_without_the_libcxx_shim_need_no_patch(self):
        self.assertIsNone(self.bundle.patch_macos_float_header(self.root/'absent.h'))


class OwnedMetalEvidence(unittest.TestCase):
    def report(self):
        names=['README.md','prepare.py','verify.py','faults.py','logs.py','check_sources.py','module.cpp','worker.mm','protocol.h','main.nex.in']
        pins={name:hashlib.sha256(name.encode()).hexdigest() for name in names}
        root=Path(__file__).resolve().parents[1]/'experiments/owned-metal'
        spec=importlib.util.spec_from_file_location('metal_evidence_fixtures',root/'verify.py')
        verify=importlib.util.module_from_spec(spec);spec.loader.exec_module(verify)
        spec=importlib.util.spec_from_file_location('metal_evidence_faults',root/'faults.py')
        faults=importlib.util.module_from_spec(spec);spec.loader.exec_module(faults)
        cases=[group+'-'+name for group,values in [('normal',verify.CASES),('error',verify.ERROR_CASES),('fault',faults.CASES)] for name in values]
        preparation={'schema':'nex.owned-metal-preparation/1','ok':True,'source_checked':True,'source_language':'0.28','compiler_sha256':'a'*64,
            'native_provider_built':False,'driver_initialized':False,'hardware_executed':False,
            'source_input_sha256':{name:pins[name] for name in ['worker.mm','module.cpp','protocol.h','main.nex.in']},
            'signature_sha256':{name:'b'*64 for name in ['open','upload','dispatch','download','name','kernel_ns','busy']}}
        source={'schema':'nex.owned-metal-source-check/1','ok':True,'source_language':'0.28','compiler_sha256':'a'*64,
            'native_provider_built':False,'driver_initialized':False,'hardware_executed':False,'accepted_programs':27,'rejected_programs':1,
            'fixture_sha256':{name:pins[name] for name in ['verify.py','faults.py','main.nex.in']},
            'checks':[{'name':name,'exit_code':0} for name in cases]+[{'name':'missing-source-error-effect','exit_code':1,'diagnostic':'E_EFFECT'}]}
        metal={'installed_provider_source_checked':True,'verification_harness_installed':True,'fault_harness_installed':True,'log_harness_installed':True,
            'preparation':preparation,'source_report':source,'tool_sha256':pins}
        return {'compiler_sha256':'a'*64,'language':'0.28','evidence':{'owned_device_contract':{'metal':metal}}}

    def test_complete_installed_source_report_retains_no_hardware_claim(self):
        acceptance.validate_owned_metal_evidence(self.report())

    def test_missing_tools_wrong_compiler_or_hardware_claims_are_rejected(self):
        original=self.report()
        for mutate in [lambda d:d['evidence']['owned_device_contract'].pop('metal'),
                       lambda d:d['evidence']['owned_device_contract']['metal'].update(log_harness_installed=False),
                       lambda d:d['evidence']['owned_device_contract']['metal']['tool_sha256'].pop('worker.mm'),
                       lambda d:d['evidence']['owned_device_contract']['metal']['preparation'].update(compiler_sha256='c'*64),
                       lambda d:d['evidence']['owned_device_contract']['metal']['preparation'].update(source_language='0.27'),
                       lambda d:d['evidence']['owned_device_contract']['metal']['preparation'].update(hardware_executed=True),
                       lambda d:d['evidence']['owned_device_contract']['metal']['preparation']['signature_sha256'].pop('busy'),
                       lambda d:d['evidence']['owned_device_contract']['metal']['preparation']['source_input_sha256'].update(**{'worker.mm':'d'*64})]:
            changed=copy.deepcopy(original);mutate(changed)
            with self.assertRaisesRegex(RuntimeError,'Metal'):acceptance.validate_owned_metal_evidence(changed)

    def test_all_named_sources_and_the_effect_rejection_are_required(self):
        original=self.report()
        mutations=[lambda s:s['checks'].pop(),lambda s:s['checks'][0].update(name='unrelated-program'),
                   lambda s:s['checks'][-1].update(exit_code=0),lambda s:s['checks'][-1].update(exit_code=True),
                   lambda s:s['checks'][-1].update(diagnostic='E_PARSE'),lambda s:s.update(accepted_programs=True),
                   lambda s:s.update(compiler_sha256='d'*64),lambda s:s.update(native_provider_built=True),
                   lambda s:s['fixture_sha256'].update(**{'verify.py':'d'*64})]
        for mutate in mutations:
            changed=copy.deepcopy(original);mutate(changed['evidence']['owned_device_contract']['metal']['source_report'])
            with self.assertRaisesRegex(RuntimeError,'Metal source-fixture'):acceptance.validate_owned_metal_evidence(changed)

    def test_new_toolchain_requires_metal_before_other_legacy_evidence(self):
        current={'schema':'nex.sdk-acceptance/1','ok':True,'version':'0.163.0','doctor':{'version':'0.163.0'},
            'phases':[{'name':name,'status':'passed'} for name in acceptance.acceptance_phases('0.163.0')],
            'commands':[{'status':'passed','exit_code':0}]}
        with self.assertRaisesRegex(RuntimeError,'installed Metal provider'):acceptance.validate_completed_report(current)


class RetainedHostPaths(unittest.TestCase):
    def test_native_and_portable_spellings_bind_the_same_existing_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()/'retained SDK % 🧠'
            path = root/'.nex/build'/('a'*64)/acceptance.sdk_host.executable_name('app')
            path.parent.mkdir(parents=True)
            path.write_bytes(b'actual retained bytes')
            check = acceptance.sdk_host.same_existing_path
            self.assertTrue(check(str(path), path))
            self.assertTrue(check(path.as_posix(), path))
            self.assertTrue(check(str(path.parent), path.parent))
            if os.name == 'nt':
                mixed = str(root) + '/.nex/build/' + path.parent.name + '\\' + path.name
                self.assertNotEqual(mixed, str(path))
                self.assertTrue(check(mixed, path))

    def test_matching_bytes_or_physical_identity_do_not_waive_namespace(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            expected = root/'original';expected.write_bytes(b'same bytes')
            copy = root/'copy';copy.write_bytes(expected.read_bytes())
            alias = root/'outside hardlink';os.link(expected, alias)
            self.assertTrue(alias.samefile(expected))
            for recorded in (str(copy),str(alias),expected.name,'',None,42,str(expected)+'\0'):
                with self.subTest(recorded=recorded):
                    self.assertFalse(acceptance.sdk_host.same_existing_path(recorded,expected))
            missing = root/'missing'
            self.assertFalse(acceptance.sdk_host.same_existing_path(str(missing),missing))

    @unittest.skipIf(os.name == 'nt', 'POSIX backslashes are literal filename characters')
    def test_posix_backslashes_are_not_normalized_to_separators(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            literal = root/'nested\\image';literal.write_bytes(b'literal name')
            separated = root/'nested/image';separated.parent.mkdir();separated.write_bytes(b'literal name')
            check = acceptance.sdk_host.same_existing_path
            self.assertTrue(check(str(literal),literal))
            self.assertFalse(check(str(literal),separated))


@unittest.skipUnless(sys.platform == 'linux', 'actual Linux link-library packaging')
class LinuxLinkLibraries(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='NEX link library % 🧠 ')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.inputs = self.root/'original inputs';self.inputs.mkdir()
        self.output = self.root/'SDK';self.output.mkdir()
        self.compiler = shutil.which('cc')
        self.archiver = shutil.which('ar')
        self.assertIsNotNone(self.compiler)
        self.assertIsNotNone(self.archiver)
        self.environment = {k:v for k,v in os.environ.items() if k not in ('LD_LIBRARY_PATH','LD_PRELOAD')}
        spec = importlib.util.spec_from_file_location('linux_link_bundle',
            Path(__file__).resolve().parents[1]/'tools/sdk_bundle.py')
        self.bundle_module = importlib.util.module_from_spec(spec);spec.loader.exec_module(self.bundle_module)
        notice = self.root/'notices.json'
        notice.write_text(json.dumps({'schema':'nex.sdk-notices/1','components':[
            {'name':'NEX-owned-link-fixture','version':'1','url':'https://github.com/sae-ru/NEX',
             'roots':[str(self.inputs)],'license_files':[str(Path(__file__).resolve().parents[1]/'LICENSE')]}]}))
        self.bundle = self.bundle_module.LinuxBundle(self.root,self.output,notice)
        self.bundle.environment = self.environment
        self.source = self.inputs/'answer.c';self.source.write_text('int answer(void){return 42;}\n')
        self.object = self.inputs/'answer object.o'
        self.run_command([self.compiler,'-fPIC','-c',self.source,'-o',self.object])
        self.main = self.root/'main.c'
        self.main.write_text('#include <stdio.h>\nint answer(void);int main(void){printf("%d\\n",answer());return 0;}\n')

    def run_command(self, command):
        result = subprocess.run(list(map(str,command)),env=self.environment,capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        return result.stdout

    def test_regular_archive_links_after_original_objects_and_archive_are_deleted(self):
        original = self.inputs/'libanswer.a'
        self.run_command([self.archiver,'crs',original,self.object])
        raw = original.read_bytes()
        copied = self.bundle.copy_link_library(original,self.archiver)
        self.assertEqual(copied.read_bytes(),raw)
        self.assertEqual(self.bundle.origins[copied.relative_to(self.output).as_posix()]['source_sha256'],
                         hashlib.sha256(raw).hexdigest())
        self.assertEqual(len(self.bundle.copy_notices('licenses')),1)
        relative = copied.relative_to(self.output)
        shutil.rmtree(self.inputs)
        moved = self.root/'moved SDK % 🧠';self.output.rename(moved)
        executable = moved/'bin/app';executable.parent.mkdir()
        self.run_command([self.compiler,self.main,moved/relative,'-o',executable])
        self.assertEqual(self.run_command([executable]),'42\n')

    def test_shared_library_keeps_its_SONAME_alias_after_source_removal_and_move(self):
        original = self.inputs/'libanswer.so.1.2'
        self.run_command([self.compiler,'-shared',self.object,'-Wl,-soname,libanswer.so.1','-o',original])
        copied = self.bundle.copy_link_library(original,self.archiver)
        alias = copied.with_name('libanswer.so.1')
        self.assertTrue(alias.is_symlink())
        self.assertEqual(alias.resolve(),copied)
        executable = self.output/'bin/app';executable.parent.mkdir()
        self.run_command([self.compiler,self.main,copied,'-Wl,-rpath,$ORIGIN/../lib/nex/host','-o',executable])
        shutil.rmtree(self.inputs)
        moved = self.root/'moved shared SDK % 🧠';self.output.rename(moved)
        self.assertEqual(self.run_command([moved/'bin/app']),'42\n')

    def test_thin_and_malformed_archives_are_rejected_before_copy(self):
        thin = self.inputs/'thin.a'
        self.run_command([self.archiver,'crsT',thin,self.object])
        self.assertEqual(thin.read_bytes()[:8],b'!<thin>\n')
        with self.assertRaisesRegex(ValueError,'regular archive'):
            self.bundle.copy_link_library(thin,self.archiver)
        self.assertFalse((self.output/'lib/nex/host'/thin.name).exists())
        malformed = self.inputs/'malformed.a';malformed.write_bytes(b'!<arch>\n'+b'garbage'*16)
        with self.assertRaisesRegex(RuntimeError,'command failed'):
            self.bundle.copy_link_library(malformed,self.archiver)
        self.assertFalse((self.output/'lib/nex/host'/malformed.name).exists())


class WindowsOpenSSLPrefix(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.prefix = Path(self.directory.name)/'selected OpenSSL'
        self.doctor = {}
        for field, relative in [('native_openssl_include', 'include'),
                                ('native_openssl_ssl', 'lib/libssl.a'),
                                ('native_openssl_crypto', 'lib/libcrypto.a')]:
            path = self.prefix/relative
            if field.endswith('include'):
                path.mkdir(parents=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'fixture static library')
            self.doctor[field] = str(path)
        for name in ['openssl.exe', 'libssl-3-x64.dll', 'libcrypto-3-x64.dll']:
            path = self.prefix/'bin'/name
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(b'fixture executable')
        (self.prefix/'lib/ossl-modules').mkdir()
        spec = importlib.util.spec_from_file_location('openssl_prefix_bundle',
            Path(__file__).resolve().parents[1]/'tools/sdk_bundle.py')
        bundle = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bundle)
        self.bundle = bundle.WindowsBundle.__new__(bundle.WindowsBundle)
        self.configuration = self.prefix/'etc/ssl/openssl.cnf'

    def configure(self):
        self.configuration.parent.mkdir(parents=True, exist_ok=True)
        self.configuration.write_text('[req]\ndistinguished_name = req_dn\n[req_dn]\n')

    def test_missing_configuration_is_rejected_before_selecting_DLLs(self):
        with self.assertRaisesRegex(ValueError, 'install_ssldirs'):
            self.bundle.select_openssl_prefix(self.prefix, self.doctor)
        self.assertFalse(hasattr(self.bundle, 'pe_selected_imports'))

    def test_empty_configuration_is_rejected(self):
        self.configure()
        self.configuration.write_bytes(b'')
        with self.assertRaisesRegex(ValueError, 'openssl.cnf'):
            self.bundle.select_openssl_prefix(self.prefix, self.doctor)

    def test_complete_cohort_selects_its_own_DLLs(self):
        self.configure()
        self.assertEqual(self.bundle.select_openssl_prefix(self.prefix, self.doctor),
                         self.prefix.resolve())
        self.assertEqual(self.bundle.pe_selected_imports,
                         {name: self.prefix.resolve()/'bin'/name for name in
                          ['libssl-3-x64.dll', 'libcrypto-3-x64.dll']})

    def test_configuration_does_not_permit_a_different_native_library(self):
        self.configure()
        different = self.prefix/'lib/different-crypto.a'
        different.write_bytes(b'different library')
        self.doctor['native_openssl_crypto'] = str(different)
        with self.assertRaisesRegex(ValueError, 'must match'):
            self.bundle.select_openssl_prefix(self.prefix, self.doctor)
        self.assertFalse(hasattr(self.bundle, 'pe_selected_imports'))


class DebuggerFatalDiagnostics(unittest.TestCase):
    def test_zero_parent_with_actual_fatal_stderr_fails_both_recording_runners(self):
        # Reproduce the observed Windows contract: parent0, completed stdout,
        # and a child's fatal report on inherited stderr. Keep the raw logs.
        from types import SimpleNamespace
        data=b'lldb-server exiting...\nPLEASE submit a bug report to  and include the crash backtrace.\nException Code: 0xC0000005\n'
        peer=[sys.executable,'-c','import sys;sys.stdout.write("completed\\n");sys.stderr.buffer.write('+repr(data)+')']
        for installed in (False,True):
            with self.subTest(installed=installed),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);logs=root/'logs';logs.mkdir();report={'commands':[]}
                source=Path(__file__).resolve().parents[1]/('tools/sdk_acceptance.py' if installed else 'tests/source_exception_http.py')
                tree=ast.parse(source.read_text());run=next(node for node in ast.walk(tree) if isinstance(node,ast.FunctionDef) and node.name=='run')
                def save():
                    (root/'report.json').write_text(json.dumps(report))
                def launch(command,**kwargs):
                    return subprocess.Popen(peer,**kwargs)
                context={'Path':Path,'root':root,'out':root,'logs':logs,'report':report,'save':save,
                    'sdk_host':acceptance.sdk_host,'require':acceptance.require,
                    'debugger_crash_diagnostic':acceptance.sdk_host.debugger_crash_diagnostic,
                    'environment':os.environ.copy(),'compiler':root/'nex','resources':root/'resources',
                    'extra_notices':[],'subprocess':SimpleNamespace(Popen=launch,TimeoutExpired=subprocess.TimeoutExpired),
                    'run_native':lambda command,**kwargs:subprocess.run(peer,**kwargs)}
                exec(compile(ast.Module(body=[run],type_ignores=[]),str(source),'exec'),context)
                with self.assertRaises((AssertionError,RuntimeError)):
                    if installed:context['run'](['lldb'],timeout=10)
                    else:context['run']('zero-parent',['lldb'],timeout=10)
                row=json.loads((root/'report.json').read_text())['commands'][-1]
                self.assertEqual(row['exit_code' if installed else 'exit'],0)
                self.assertEqual(row['fatal_debugger_diagnostic'],'PLEASE submit a bug report')
                self.assertEqual((Path(row['stderr']) if installed else root/'zero-parent.stderr').read_bytes(),data)
                if installed:self.assertEqual(row['status'],'failed')

    def test_bytes_text_and_native_debugger_names_preserve_fatal_reports(self):
        for command in (['/usr/bin/lldb'],[r'F:\private\lldb.exe'],['lldb-dap'],['lldb-server.exe']):
            for data in (b'\xffException Code: 0xC0000005\n','LLVM ERROR: failure\n'):
                with self.subTest(command=command,data=data):
                    self.assertIsNotNone(acceptance.sdk_host.debugger_crash_diagnostic(command,data))

    def test_ordinary_errors_and_non_debugger_program_output_are_not_fatal_reports(self):
        check=acceptance.sdk_host.debugger_crash_diagnostic
        self.assertIsNone(check(['lldb'],'error: invalid command'))
        self.assertIsNone(check(['lldb'],None))
        self.assertIsNone(check(['nex'],'PLEASE submit a bug report'))
        self.assertIsNone(check([],b'LLVM ERROR: failure'))


class StreamHostPlatformEvidence(unittest.TestCase):
    def report(self):
        contract=acceptance._stream_host_contract()
        fields=('ok','typed_open_no_raw_file_ids','original_grants','physical_quota_retention',
                'single_CPU_worker_progress','cancel_physical_drain','immutable_input_snapshots',
                'large_file_streaming','protocol_rejections')
        pins={'tools/task_file_stream_host_acceptance.cpp','tests/host_test.h',
              *('runtime/'+name for name in (*contract.HEADERS,*contract.SOURCES))}
        host={'schema':'nex.installed-task-stream-host/1',**{name:True for name in fields},
              'cases':26,'case_names':list(contract.cases_for_platform('Windows')),
              'source_support':False,'actual_partial_write':False,'host_platform':'Windows',
              'portable_corpus_complete':False,'pending_cases':[contract.PARTIAL_WRITE_CASE],
              'probe_sha256':'a'*64,'installed_sources':{name:'b'*64 for name in pins}}
        return {'host':'x86_64-w64-windows-gnu','doctor':{'host':'x86_64-w64-windows-gnu'},
                'evidence':{'structured_task_file_writes':{'private_stream_host':host}}}

    def test_Windows_records_pending_partial_write_without_claiming_27_executions(self):
        report=self.report();acceptance.validate_installed_stream_host(report,(0,162,0))
        host=report['evidence']['structured_task_file_writes']['private_stream_host']
        for key,value in [('actual_partial_write',True),('portable_corpus_complete',True),
                          ('pending_cases',[]),('cases',27),('case_names',host['case_names'][:-1])]:
            damaged=copy.deepcopy(report)
            damaged['evidence']['structured_task_file_writes']['private_stream_host'][key]=value
            with self.subTest(field=key),self.assertRaises(RuntimeError):
                acceptance.validate_installed_stream_host(damaged,(0,162,0))

    def test_Windows_scope_cannot_replace_other_platform_or_historical_proofs(self):
        report=self.report()
        with self.assertRaises(RuntimeError):acceptance.validate_installed_stream_host(report,(0,161,0))
        for host in ('aarch64-unknown-linux-gnu','arm64-apple-darwin27.0.0'):
            damaged=copy.deepcopy(report);damaged['host']=host;damaged['doctor']['host']=host
            with self.subTest(host=host),self.assertRaises(RuntimeError):
                acceptance.validate_installed_stream_host(damaged,(0,162,0))
        report['doctor']['host']='aarch64-unknown-linux-gnu'
        with self.assertRaises(RuntimeError):acceptance.validate_installed_stream_host(report,(0,162,0))

    def test_physical_output_requires_exact_platform_cases_and_rejects_missing_or_duplicate_execution(self):
        contract=acceptance._stream_host_contract()
        def output(names):
            return '\n'.join(['PASS '+name for name in names]+[json.dumps({'ok':True,
                'host_stream_cases':len(names),'public_source_support':False,'maximum_chunk_bytes':1048576,
                'one_shot_typed_open':True,'physical_drain':True})])
        names=contract.cases_for_platform('Windows')
        self.assertEqual(contract.parse_host_output(output(names),'Windows')[0],list(names))
        for damaged in (names[:-1],names+(names[0],),contract.CASES):
            with self.subTest(cases=len(damaged)),self.assertRaises(RuntimeError):
                contract.parse_host_output(output(damaged),'Windows')
        for system in ('Darwin','Linux'):
            with self.subTest(system=system),self.assertRaises(RuntimeError):
                contract.parse_host_output(output(names),system)
            contract.parse_host_output(output(contract.CASES),system)


class ServerDebugEvidence(unittest.TestCase):
    def report(self, *, available=True, live=False):
        server = {'descriptor': True, 'actual_shared_provider': True,
                  'editor_preparation': available, 'backend_available': available,
                  **{name: live for name in ('live_worker_stop', 'source_deleted',
                                             'request_completed', 'graceful_exit')}}
        report = {'resource_hashes': {'editor/vscode/session.js': 'a'*64},
                  'evidence': {'live_debugger': live, 'server_debug': server}, 'commands': []}
        if not available:
            server['editor_backend_refusal'] = {
                'schema': 'nex.sdk-editor-backend-refusal/1', 'exit_code': 1,
                'message': acceptance.EDITOR_BACKEND_UNAVAILABLE,
                'backend_command': 'lldb-dap', 'backend_present': False, 'python_present': True,
                'editor_source_sha256': 'a'*64, 'stdout_empty': True,
                'stderr': '/evidence/editor.stderr', 'stderr_sha256': 'b'*64}
            report['commands'].append({'stderr': '/evidence/editor.stderr', 'status': 'passed', 'exit_code': 1})
        return report

    def test_existing_successful_editor_and_live_receipts_remain_required(self):
        for live in (False, True):
            report = self.report(live=live)
            del report['evidence']['server_debug']['backend_available']
            acceptance.validate_server_debug_evidence(report)
        report['evidence']['server_debug']['live_worker_stop'] = False
        with self.assertRaisesRegex(RuntimeError, 'actual source-deleted HTTP'):
            acceptance.validate_server_debug_evidence(report)

    def test_explicit_offline_refusal_requires_current_report_opt_in(self):
        report = self.report(available=False)
        with self.assertRaisesRegex(RuntimeError, 'server/editor debug preparation'):
            acceptance.validate_server_debug_evidence(report)
        acceptance.validate_server_debug_evidence(report, allow_offline_refusal=True)
        report['evidence']['live_debugger'] = True
        with self.assertRaisesRegex(RuntimeError, 'server/editor debug preparation'):
            acceptance.validate_server_debug_evidence(report, allow_offline_refusal=True)

    def test_refusal_cannot_hide_an_unrelated_command_failure_or_missing_prerequisite(self):
        report = self.report(available=False)
        mutations = (
            lambda r: r['evidence']['server_debug']['editor_backend_refusal'].update(message='build failed'),
            lambda r: r['evidence']['server_debug']['editor_backend_refusal'].update(python_present=False),
            lambda r: r['evidence']['server_debug']['editor_backend_refusal'].update(backend_present=True),
            lambda r: r['evidence']['server_debug']['editor_backend_refusal'].update(editor_source_sha256='c'*64),
            lambda r: r['evidence']['server_debug']['editor_backend_refusal'].update(stdout_empty=False),
            lambda r: r['commands'][0].update(exit_code=7),
            lambda r: r['commands'][0].update(status='failed'),
            lambda r: r['commands'].append(copy.deepcopy(r['commands'][0])),
        )
        for mutate in mutations:
            damaged = copy.deepcopy(report); mutate(damaged)
            with self.subTest(mutation=mutate), self.assertRaises(RuntimeError):
                acceptance.validate_server_debug_evidence(damaged, allow_offline_refusal=True)

    def test_offline_receipt_cannot_claim_live_execution_or_successful_editor_preparation(self):
        report = self.report(available=False)
        for name in ('live_worker_stop', 'source_deleted', 'request_completed', 'graceful_exit', 'editor_preparation'):
            damaged = copy.deepcopy(report); damaged['evidence']['server_debug'][name] = True
            with self.subTest(field=name), self.assertRaises(RuntimeError):
                acceptance.validate_server_debug_evidence(damaged, allow_offline_refusal=True)
        del report['evidence']['server_debug']['editor_backend_refusal']
        with self.assertRaisesRegex(RuntimeError, 'actual unavailable-backend'):
            acceptance.validate_server_debug_evidence(report, allow_offline_refusal=True)


class ProjectEditorEvidence(unittest.TestCase):
    def report(self, *, available):
        report=ServerDebugEvidence().report(available=available)
        server=report['evidence']['server_debug'];record={key:copy.deepcopy(server[key])for key in
            ('editor_preparation','backend_available','editor_backend_refusal')if key in server}
        if not available:
            record['editor_backend_refusal']['stderr']='/evidence/project-editor.stderr'
            report['commands'].append({'stderr':'/evidence/project-editor.stderr','status':'passed','exit_code':1})
        report['evidence']['editor']={'project_session_preparation':available,
            'project_actual_binary_dependencies':True,'project_session':record}
        return report

    def test_legacy_success_stays_valid_and_new_result_cannot_contradict_its_flags(self):
        report=self.report(available=True)
        acceptance.validate_project_editor_evidence(report)
        legacy=copy.deepcopy(report);del legacy['evidence']['editor']['project_session']
        acceptance.validate_project_editor_evidence(legacy)
        report['evidence']['editor']['project_session_preparation']=False
        with self.assertRaises(RuntimeError):acceptance.validate_project_editor_evidence(report)

    def test_actual_offline_refusal_stays_distinct_from_successful_preparation_or_live_debugging(self):
        report=self.report(available=False)
        acceptance.validate_project_editor_evidence(report)
        for mutate in (
            lambda r:r['evidence'].update(live_debugger=True),
            lambda r:r['evidence']['editor'].update(project_actual_binary_dependencies=False),
            lambda r:r['evidence']['editor'].pop('project_session'),
            lambda r:r['commands'][-1].update(exit_code=7),
            lambda r:r['evidence']['editor']['project_session'].pop('editor_backend_refusal')):
            damaged=copy.deepcopy(report);mutate(damaged)
            with self.subTest(mutation=mutate),self.assertRaises(RuntimeError):
                acceptance.validate_project_editor_evidence(damaged)

    def test_shared_project_cannot_reuse_the_server_editor_refusal(self):
        report=self.report(available=False)
        report['evidence']['editor']['project_session']['editor_backend_refusal']=copy.deepcopy(
            report['evidence']['server_debug']['editor_backend_refusal'])
        with self.assertRaisesRegex(RuntimeError,'cannot reuse the server'):
            acceptance.validate_project_editor_evidence(report)


class SDKClientLifecycle(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='nex DAP peer ')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.peer = self.root/'peer.py'
        self.peer.write_text('''import json,sys
mode=sys.argv[1];stream=sys.stdin.buffer;crlf=bytes([13,10])
while True:
 headers={}
 while True:
  line=stream.readline()
  if not line:sys.exit(0)
  if line==crlf:break
  key,value=line.decode().split(':',1);headers[key.lower()]=value.strip()
 request=json.loads(stream.read(int(headers['content-length'])))
 if request['command']=='disconnect':
  if mode.startswith('fatal'):
   sys.stderr.write('PLEASE submit a bug report\\nException Code: 0xC0000005\\n');sys.exit(0)
  sys.exit(0 if mode=='clean' else 7)
 if request['command']=='launch':
  if mode=='eof':sys.exit(9)
  continue
 body=json.dumps({'type':'response','request_seq':request['seq'],'command':request['command'],'success':True}).encode()
 sys.stdout.buffer.write(('Content-Length: %d'%len(body)).encode()+crlf+crlf+body);sys.stdout.buffer.flush()
''',encoding='utf-8')

    def client(self, mode):
        return acceptance.DAP([sys.executable,'-u','-B',str(self.peer),mode],self.root,
                              dict(os.environ,PYTHONDONTWRITEBYTECODE='1'))

    def assert_closed(self, client):
        self.assertIsNotNone(client.process.poll())
        self.assertFalse(client.reader.is_alive())
        self.assertTrue(client.process.stdin.closed)
        self.assertTrue(client.process.stdout.closed)
        self.assertTrue(client.log.closed)

    def test_real_peer_graceful_shutdown_releases_owned_process_and_reader(self):
        before=acceptance.DAP.successful_shutdowns;client=self.client('clean')
        try:client.request('initialize')
        finally:client.close()
        self.assert_closed(client)
        self.assertEqual(client.process.returncode,0)
        self.assertEqual(acceptance.DAP.successful_shutdowns,before+1)

    def test_timeout_keeps_request_failure_when_shutdown_also_fails(self):
        before=acceptance.DAP.successful_shutdowns;client=self.client('bad-shutdown')
        with self.assertRaisesRegex(RuntimeError,'DAP timeout.*request launch') as caught:
            try:
                client.request('initialize');client.send('launch')
                client.wait(lambda message:message.get('event')=='initialized',timeout=.1)
            finally:client.close()
        self.assertIn('adapter PID',str(caught.exception))
        self.assertIn(str(self.root/'dap-stderr.log'),str(caught.exception))
        self.assertEqual(client.shutdown_error,'DAP adapter failed during shutdown: exit 7')
        self.assertIn(client.shutdown_error,(self.root/'dap-stderr.log').read_text())
        self.assertEqual(acceptance.DAP.successful_shutdowns,before)
        self.assert_closed(client)

    def test_EOF_keeps_expected_event_and_original_failure_on_cleanup(self):
        client=self.client('eof')
        with self.assertRaisesRegex(RuntimeError,'DAP stream stopped.*event initialized'):
            try:
                client.request('initialize');client.send('launch');client.event('initialized')
            finally:client.close()
        self.assertEqual(client.process.returncode,9)
        self.assert_closed(client)

    def test_shutdown_failure_without_prior_error_remains_a_failure(self):
        client=self.client('bad-shutdown');client.request('initialize')
        with self.assertRaisesRegex(RuntimeError,'shutdown: exit 7'):client.close()
        self.assert_closed(client)

    def test_fatal_child_report_fails_even_when_the_adapter_exits_zero(self):
        before=acceptance.DAP.successful_shutdowns;client=self.client('fatal')
        client.request('initialize')
        with self.assertRaisesRegex(RuntimeError,'fatal debugger diagnostic'):client.close()
        self.assert_closed(client)
        self.assertEqual(client.process.returncode,0)
        self.assertEqual(acceptance.DAP.successful_shutdowns,before)
        self.assertIn('Exception Code: 0xC0000005',(self.root/'dap-stderr.log').read_text())

    def test_primary_request_error_survives_a_zero_exit_with_fatal_stderr(self):
        before=acceptance.DAP.successful_shutdowns;client=self.client('fatal-timeout')
        with self.assertRaisesRegex(RuntimeError,'DAP timeout.*request launch'):
            try:
                client.request('initialize');client.send('launch')
                client.wait(lambda message:message.get('event')=='initialized',timeout=.1)
            finally:client.close()
        self.assert_closed(client)
        self.assertEqual(client.process.returncode,0)
        self.assertEqual(acceptance.DAP.successful_shutdowns,before)
        self.assertIn('fatal debugger diagnostic',client.shutdown_error)
        self.assertIn('DAP cleanup:',(self.root/'dap-stderr.log').read_text())


class CommandTimeoutEvidence(unittest.TestCase):
    def runner(self, root):
        # Compile the actual nested logger without starting its native HTTP
        # builder. Its process transport is a real controlled stdio peer.
        source = Path(__file__).with_name('source_exception_http.py')
        tree = ast.parse(source.read_text(), filename=str(source))
        functions = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == 'run']
        self.assertEqual(len(functions), 1)
        report, saved = {'commands': []}, []
        namespace = {'run_native': subprocess.run, 'subprocess': subprocess, 'out': root,
                     'debugger_crash_diagnostic': acceptance.sdk_host.debugger_crash_diagnostic,
                     'report': report, 'save': lambda: saved.append(copy.deepcopy(report))}
        exec(compile(ast.Module(body=functions, type_ignores=[]), str(source), 'exec'), namespace)
        return namespace['run'], report, saved

    def test_real_timed_out_peer_retains_partial_streams_and_primary_timeout(self):
        with tempfile.TemporaryDirectory(prefix='nex HTTP command evidence ') as temporary:
            root = Path(temporary); run, report, saved = self.runner(root)
            command = [sys.executable, '-u', '-B', '-c',
                       'import os,time;os.write(1,b"partial LLDB \\xd0\\xaf\\n");'
                       'os.write(2,b"partial diagnostic \\xe2\\x82");time.sleep(60)']
            with self.assertRaises(subprocess.TimeoutExpired) as caught: run('peer', command, timeout=2)
            self.assertEqual(caught.exception.timeout, 2)
            self.assertEqual((root/'peer.stdout').read_text(encoding='utf-8'), 'partial LLDB Я\n')
            self.assertEqual((root/'peer.stderr').read_text(encoding='utf-8'), 'partial diagnostic \ufffd')
            self.assertEqual(report['commands'][0]['exit'], None)
            self.assertTrue(report['commands'][0]['timed_out'])
            self.assertEqual(report['commands'][0]['timeout_seconds'], 2)
            self.assertEqual(saved, [report])

    def test_real_failed_peer_still_fails_and_retains_its_output(self):
        with tempfile.TemporaryDirectory(prefix='nex HTTP command failure ') as temporary:
            root = Path(temporary); run, report, saved = self.runner(root)
            command = [sys.executable, '-B', '-c', 'import sys;sys.stderr.write("peer failed");sys.exit(7)']
            with self.assertRaises(AssertionError): run('peer', command)
            self.assertEqual((root/'peer.stderr').read_text(), 'peer failed')
            self.assertEqual(report['commands'][0]['exit'], 7)
            self.assertEqual(saved, [report])

    def test_real_successful_peer_keeps_UTF8_text_and_universal_newlines(self):
        with tempfile.TemporaryDirectory(prefix='nex HTTP text peer ') as temporary:
            root = Path(temporary); run, report, saved = self.runner(root)
            command = [sys.executable, '-B', '-c',
                       'import os;os.write(1,b"value \\xc3\\xa9\\r\\nnext\\r");'
                       'os.write(2,b"note \\xce\\xa9\\r\\n")']
            result = run('peer', command)
            self.assertEqual(result.stdout, 'value é\nnext\n')
            self.assertEqual(result.stderr, 'note Ω\n')
            self.assertEqual((root/'peer.stdout').read_bytes(), 'value é\nnext\n'.encode())
            self.assertEqual(report['commands'][0]['exit'], 0)
            self.assertEqual(saved, [report])


class FailedFixtureOwnership(unittest.TestCase):
    def exercise(self, outcome):
        spec = importlib.util.spec_from_file_location(
            'failure_fixture_support', Path(__file__).with_name('support.py'))
        support = importlib.util.module_from_spec(spec)
        with mock.patch.object(sys, 'argv', [__file__, sys.executable]):
            spec.loader.exec_module(support)
        observed = {}

        class NestedProject(support.ToolchainCase):
            __module__ = 'fixture_failure_peer'
            __qualname__ = 'NestedProject'
            def runTest(self):
                parent = self.root; observed['original_parent'] = parent
                self.root = parent/'project % 🧠'; self.root.mkdir()
                (self.root/'main.nex').write_text('fixture only', encoding='utf-8')
                moved = parent/'moved replay'; moved.mkdir()
                (moved/'receipt.json').write_text('{"preserve":"replay"}', encoding='utf-8')
                (parent/'sibling.json').write_text('external package evidence', encoding='utf-8')
                shutil.rmtree(self.root)
                if outcome == 'failure': self.fail('primary assertion remains visible')
                if outcome == 'error': raise RuntimeError('primary exception remains visible')

        with tempfile.TemporaryDirectory(prefix='nex fixture ownership ') as temporary:
            destination = Path(temporary)/'retained'; result = unittest.TestResult()
            with mock.patch.dict(os.environ, {'NEX_TEST_FAILURE_ROOT': str(destination)}), \
                 contextlib.redirect_stderr(io.StringIO()):
                unittest.TestSuite([NestedProject()]).run(result)
            self.assertFalse(observed['original_parent'].exists())
            if outcome == 'passed':
                self.assertTrue(result.wasSuccessful()); self.assertFalse(destination.exists())
                return
            self.assertEqual(len(result.failures), 1 if outcome == 'failure' else 0)
            self.assertEqual(len(result.errors), 1 if outcome == 'error' else 0)
            primary = (result.failures if outcome == 'failure' else result.errors)[0][1]
            self.assertIn('primary assertion' if outcome == 'failure' else 'primary exception', primary)
            roots = list(destination.iterdir()); self.assertEqual(len(roots), 1)
            self.assertEqual((roots[0]/'moved replay/receipt.json').read_text(), '{"preserve":"replay"}')
            self.assertEqual((roots[0]/'sibling.json').read_text(), 'external package evidence')

    def test_assertion_after_deleted_nested_root_keeps_parent_and_primary_failure(self):
        self.exercise('failure')

    def test_exception_after_deleted_nested_root_keeps_parent_and_primary_error(self):
        self.exercise('error')

    def test_passing_fixture_still_removes_parent_without_retaining_files(self):
        self.exercise('passed')


class LinuxVerifierBudgets(unittest.TestCase):
    """Real short-lived peers test orchestration budgets, not SDK acceptance."""

    def exercise(self, workflow_exit=0, slow_tool=False):
        spec = importlib.util.spec_from_file_location(
            'linux_bundle_budget_fixture', Path(__file__).resolve().parents[1]/'tools/linux/bundle.py')
        bundle = importlib.util.module_from_spec(spec); spec.loader.exec_module(bundle)
        real_run, real_exists = subprocess.run, Path.exists
        with tempfile.TemporaryDirectory(prefix='nex Linux verifier budget ') as temporary:
            root = Path(temporary); sdk = root/'SDK'; output = root/'evidence'; output.mkdir()
            (sdk/'bin').mkdir(parents=True); (sdk/'bin/nex').write_text('controlled fixture')
            (sdk/'share/nex').mkdir(parents=True)
            (sdk/'share/nex/sdk-bundle.json').write_text(json.dumps({'files': {}}))
            server = root/'server'; server.write_text('controlled fixture')
            accepted = {'compiler_sha256': archive.digest(sdk/'bin/nex'), 'seconds': 1,
                        'evidence': {'authenticated_storage': {'executable': str(server)}}}
            peer = root/'peer.py'; marker = root/'completed'
            peer.write_text('import json,pathlib,sys,time\n'
                            'time.sleep(float(sys.argv[1]))\n'
                            'pathlib.Path(sys.argv[2]).write_text("finished")\n'
                            'if int(sys.argv[3]):sys.stderr.write("controlled workflow failure");sys.exit(int(sys.argv[3]))\n'
                            'p=pathlib.Path(sys.argv[4]);p.parent.mkdir(parents=True,exist_ok=True)\n'
                            'p.write_text(sys.argv[5])\n')

            def controlled_run(arguments, **options):
                # Scale orchestration seconds to milliseconds, so the real
                # one-second peer outlives a tool budget without a ten-minute test.
                options['timeout'] /= 1000
                if arguments[0] == 'python3' or (slow_tool and arguments[:2] == ['ldconfig', '-p']):
                    return real_run([sys.executable, '-B', str(peer), '1', str(marker),
                                     str(workflow_exit), str(output/'workflow/report.json'),
                                     json.dumps(accepted)], **options)
                return subprocess.CompletedProcess(arguments, 0, '', '')

            def fixture_exists(path):
                return False if str(path) in ('/src', '/opt/z3', '/usr/lib/llvm-22') else real_exists(path)

            with mock.patch.object(bundle.subprocess, 'run', side_effect=controlled_run), \
                 mock.patch.object(bundle.shutil, 'which', return_value=None), \
                 mock.patch.object(Path, 'exists', fixture_exists), \
                 mock.patch.object(bundle.sdk_acceptance, 'validate_completed_report') as validate:
                if slow_tool:
                    with self.assertRaises(subprocess.TimeoutExpired): bundle.verify(sdk, output)
                    self.assertFalse(marker.exists()); validate.assert_not_called()
                elif workflow_exit:
                    with self.assertRaisesRegex(RuntimeError, 'controlled workflow failure'):
                        bundle.verify(sdk, output)
                    self.assertTrue(marker.exists()); validate.assert_not_called()
                else:
                    self.assertTrue(bundle.verify(sdk, output)['ok'])
                    self.assertTrue(marker.exists()); validate.assert_called_once_with(accepted)
            report = json.loads((output/'verification.json').read_text())
            self.assertEqual(report['ok'], not slow_tool and workflow_exit == 0)

    def test_complete_workflow_outlives_individual_tool_budget(self):
        self.exercise()

    def test_individual_tool_remains_bounded(self):
        self.exercise(slow_tool=True)

    def test_workflow_failure_is_not_accepted_with_longer_aggregate_budget(self):
        self.exercise(workflow_exit=7)


class DistributionWorkflow(unittest.TestCase):
    def tcp_report(self, profile='full'):
        # Synthetic receipt shapes exercise the validator, not platform execution.
        report={'schema':'nex.sdk-acceptance/1','ok':True,'version':'0.162.0','language':'0.28',
                'host':'x86_64-w64-windows-gnu','doctor':{'version':'0.162.0','host':'x86_64-w64-windows-gnu'},
                'network_profile':profile,'network_scope':acceptance.network_scope(profile),
                'compiler_sha256':'f'*64,'resource_hashes':{'tools/tcp_provider/verify.py':'a'*64,
                                                         'tools/tcp_provider/verify_delivery.py':'b'*64}}
        source={'schema':'nex.task-tcp-source-conformance/1','verification_source_sha256':'a'*64,
                'required_cases':list(acceptance.TCP_SOURCE_CASES),
                'selected_cases':list(acceptance.tcp_source_cases(profile)),
                'full_conformance':profile=='full','case_count':36,'cases':[]}
        for name in acceptance.tcp_source_cases(profile):
            for mode in ('eval','debug','release'):
                row={'name':name,'mode':mode,'passed':True,
                     'expected_error':{'cancel':'E_CANCELLED','parent-deadline':'E_TIMEOUT'}.get(name),
                     'peer_connections':0 if name in ('invalid','denied','ipv6-policy-denied') else 1,
                     'retired':[{'opened':1,'closed':1,'live':0}]}
                if name=='ipv6-policy-denied':
                    row['policy_control']={'schema':'nex.windows-ipv6-denial/1','native_socket':True,'system':'nt',
                        'family':'AF_INET6','address':'::1','port':12345,'winerror':10013,'errno':13,
                        'network_policy_changed':False}
                source['cases'].append(row)
        delivery={'schema':'nex.tcp-provider-delivery/1','verification_source_sha256':'b'*64,
                  'client_server_pruning':True,'source_deleted_package':True,'relocated_package':True,
                  'package_execution_network_connections':1,'target_rejections':22,'authority_rejections':18,
                  'rejections':[{'case':'target-'+str(i)} for i in range(22)]}
        codes={'no-grant':'E_FFI_GRANT','no-export':'E_FFI_GRANT','wrong-pin':'E_FFI_HASH',
               'wrong-signature':'E_FFI_SIGNATURE','changed-module':'E_FFI_HASH','changed-target-file':'E_FFI_HASH'}
        delivery['rejections'] += [{'case':name,'mode':mode,'network_connections':0,'code':code}
                                  for name,code in codes.items() for mode in ('eval','debug','release')]
        for proof in (source,delivery):
            proof.update(ok=True,state='passed',language=report['language'],toolchain=report['version'],
                         compiler_sha256=report['compiler_sha256'],source_projection=False)
        report['evidence']={'structured_task_tcp':{'source':source,'delivery':delivery}}
        return report

    def test_network_profiles_keep_full_TCP_and_require_explicit_limited_validation(self):
        full=self.tcp_report();acceptance.validate_task_tcp_evidence(full)
        limited=self.tcp_report('windows-ipv6-denied')
        with self.assertRaisesRegex(RuntimeError,'explicitly expected profile'):
            acceptance.validate_task_tcp_evidence(limited)
        with self.assertRaisesRegex(RuntimeError,'explicitly expected profile'):
            acceptance.validate_completed_report(limited)
        acceptance.validate_task_tcp_evidence(limited,expected_network_profile='windows-ipv6-denied')
        self.assertEqual(len(acceptance.acceptance_phases('0.162.0')),41)
        self.assertEqual(set(acceptance.tcp_source_cases('full'))-{'ipv6'},
                         set(acceptance.tcp_source_cases('windows-ipv6-denied'))-{'ipv6-policy-denied'})
        for field in ('network_profile','network_scope'):
            forged=copy.deepcopy(limited)
            if field=='network_profile':
                del forged['network_profile'];del forged['network_scope']
            else:
                forged['network_profile']='full';forged['network_scope']=acceptance.network_scope('full')
            with self.subTest(forgery=field),self.assertRaises(RuntimeError):
                acceptance.validate_task_tcp_evidence(forged)

    def test_limited_network_profile_rejects_missing_cases_false_controls_and_scope_claims(self):
        original=self.tcp_report('windows-ipv6-denied')
        mutations=[lambda d:d.update(host='arm64-apple-darwin'),
                   lambda d:d.update(version='0.159.0'),
                   lambda d:d['network_scope'].update(positive_TCP_IPv6_accepted=True),
                   lambda d:d['network_scope'].update(positive_TCP_IPv6_accepted=0),
                   lambda d:d['evidence']['structured_task_tcp']['source']['cases'].pop(),
                   lambda d:d['evidence']['structured_task_tcp']['source'].update(full_conformance=True),
                   lambda d:d['evidence']['structured_task_tcp']['source'].update(selected_cases=['ipv6-policy-denied'])]
        for mutate in mutations:
            changed=copy.deepcopy(original);mutate(changed)
            with self.subTest(mutation=mutate),self.assertRaises(RuntimeError):
                acceptance.validate_task_tcp_evidence(changed,expected_network_profile='windows-ipv6-denied')
        for key,value in [('native_socket',False),('system','posix'),('family','AF_INET'),('address','127.0.0.1'),
                          ('port',True),('winerror',10061),('errno',110),('network_policy_changed',True)]:
            changed=copy.deepcopy(original)
            row=next(r for r in changed['evidence']['structured_task_tcp']['source']['cases'] if r['name']=='ipv6-policy-denied')
            row['policy_control'][key]=value
            with self.subTest(control=key),self.assertRaisesRegex(RuntimeError,'native Windows socket control'):
                acceptance.validate_task_tcp_evidence(changed,expected_network_profile='windows-ipv6-denied')

    def test_native_IPv6_control_never_confuses_a_successful_connection_with_policy_denial(self):
        spec=importlib.util.spec_from_file_location('tcp_source_policy_probe',
            Path(__file__).resolve().parents[1]/'tools/tcp_provider/verify.py')
        tcp=importlib.util.module_from_spec(spec);spec.loader.exec_module(tcp)
        with socket.socket(socket.AF_INET6) as server:
            server.bind(('::1',0));server.listen(1)
            endpoint={'address':'::1','port':server.getsockname()[1]}
            # Both host policies have an observable expected result. No mock
            # socket or environment flag can manufacture the runtime control.
            try:control=tcp.prove_ipv6_policy_denial(endpoint)
            except RuntimeError as error:self.assertIn('connection succeeded',str(error))
            else:
                self.assertEqual(os.name,'nt');self.assertEqual(control['winerror'],10013)

    def test_limited_network_CLI_rejects_other_hosts_before_touching_SDK(self):
        with tempfile.TemporaryDirectory(prefix='nex SDK network profile ') as directory:
            error=io.StringIO()
            with mock.patch.object(acceptance.sdk_host,'WINDOWS',False), \
                 mock.patch.object(sys,'argv',[acceptance.__file__,str(Path(directory)/'absent'),
                    '--output',str(Path(directory)/'evidence'),'--network-profile','windows-ipv6-denied']), \
                 contextlib.redirect_stderr(error),self.assertRaises(SystemExit) as raised:
                acceptance.main()
            self.assertEqual(raised.exception.code,2)
            self.assertIn('requires native Windows execution',error.getvalue())
            self.assertEqual(list(Path(directory).iterdir()),[])

    def test_sdk_commands_reject_old_python_before_touching_paths(self):
        tools = Path(__file__).resolve().parents[1]/'tools'
        spec = importlib.util.spec_from_file_location('python_floor_bundle', tools/'sdk_bundle.py')
        bundle = importlib.util.module_from_spec(spec); spec.loader.exec_module(bundle)
        with tempfile.TemporaryDirectory(prefix='nex Python floor % 🧠 ') as directory:
            missing = Path(directory)/'missing SDK'
            for module, arguments in ((bundle, ['--sdk', str(missing), '--notices', str(missing),
                                                '--output', str(Path(directory)/'bundle')]),
                                      (acceptance, [str(missing), '--output', str(Path(directory)/'acceptance')])):
                with self.subTest(command=module.__name__):
                    error = io.StringIO()
                    with mock.patch.object(sys, 'argv', [module.__file__, *arguments]), \
                         mock.patch.object(sys, 'version_info', (3, 9, 99)), \
                         contextlib.redirect_stderr(error), self.assertRaises(SystemExit) as raised:
                        module.main()
                    self.assertEqual(raised.exception.code, 2)
                    self.assertIn('Python 3.10+ is required', error.getvalue())
                    self.assertNotIn('Traceback', error.getvalue())
                    self.assertEqual(list(Path(directory).iterdir()), [])
                    # This tests the dispatch boundary only; installed SDK execution
                    # is qualified separately with real supported interpreters.
                    for version in ((3, 10, 0), (3, 14, 9)):
                        with mock.patch.object(sys, 'argv', [module.__file__, '--help']), \
                             mock.patch.object(sys, 'version_info', version), \
                             contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as raised:
                            module.main()
                        self.assertEqual(raised.exception.code, 0)

    def test_typed027_requires_its_own_phase_and_keeps_retained_ABIs(self):
        self.assertEqual(len(acceptance.acceptance_phases('0.136.1')),39)
        self.assertEqual(len(acceptance.acceptance_phases('0.150.0')),39)
        self.assertEqual(len(acceptance.acceptance_phases('0.151.0')),40)
        self.assertIn('typed-source-errors',acceptance.acceptance_phases('0.151.0'))
        for language,abi,families in [('0.24',5,(8,9,10)),('0.25',6,(11,12,13)),
                                      ('0.26',6,(11,12,13)),('0.27',7,(14,15,16)),('0.28',7,(14,15,16))]:
            self.assertEqual(acceptance.source_task_abi(language),abi)
            self.assertEqual([acceptance.task_provider_schema({'language':language},kind)
                              for kind in ('normal','profile','debug')],
                             ['nex.native-task-provider/'+str(n) for n in families])
        for language in ('0.29','0.027',None):
            with self.assertRaises(RuntimeError):acceptance.source_task_abi(language)
            with self.assertRaises(RuntimeError):acceptance.task_provider_schema({'language':language},'normal')
        with self.assertRaisesRegex(RuntimeError,'actual027 typed source'):
            acceptance.validate_typed_source_evidence({'language':'0.27','compiler_sha256':'a'*64})

    def test_typed027_receipt_rejects_missing_execution_migration_and_identity(self):
        flags=('reference_native_typescript','checked_map','scalar_Wasm',
               'wrong_type_guard_finally_suspension','effect_and_immutable_binding_rejections',
               'genuine026_origin_verified','stale_HEAD_rejected',
               'all16_tables_schema_rows_namespace_IDs_preserved','physical_source_manifest_unchanged',
               'source_absent_snapshot_recovery','recovered_reference_native_execution','explicit_physical_export')
        proof=dict.fromkeys(flags,True)
        proof.update(schema='nex.installed-typed-source/1',ok=True,language='0.27',compiler_sha256='a'*64,
                     revision='b'*64,migration_revision='c'*64,execution_report_sha256='d'*64,
                     execution={'ok':True,'language':'0.27','compiler_sha256':'a'*64,'passed':[dict.fromkeys(
                         ('ordinary_typed_CLI','native_debug_release','typescript','checked_map','actual_scalar_Wasm',
                          'effect_and_binding_rejections'),True)]})
        resources={}
        for key,path in [('helper_sha256','tools/sdk_typed_source.py'),
                         ('test_source_sha256','tests/source_exceptions_public.py'),
                         ('origin_metadata_sha256','tests/fixtures/language-0.26-typed-origin.json'),
                         ('origin_sql_sha256','tests/fixtures/language-0.26-typed-origin.sql')]:
            resources[path]='e'*64;proof[key]='e'*64
        report={'language':'0.27','compiler_sha256':'a'*64,'resource_hashes':resources,
                'evidence':{'typed_source_errors':proof}}
        acceptance.validate_typed_source_evidence(report)
        for field in flags:
            changed=copy.deepcopy(report);changed['evidence']['typed_source_errors'][field]=False
            with self.subTest(field=field),self.assertRaises(RuntimeError):
                acceptance.validate_typed_source_evidence(changed)
        for key,value in [('language','0.26'),('compiler_sha256','f'*64),('origin_sql_sha256','f'*64),
                          ('execution',{}),('migration_revision','not-a-revision')]:
            changed=copy.deepcopy(report);changed['evidence']['typed_source_errors'][key]=value
            with self.subTest(field=key),self.assertRaises(RuntimeError):
                acceptance.validate_typed_source_evidence(changed)

    def test_discovered027_inventory_includes_real_typed_helper_and_origin_bytes(self):
        names=['docs/language.md','tools/sdk_typed_source.py','tests/source_exceptions_public.py',
               'tests/fixtures/language-0.26-typed-origin.json','tests/fixtures/language-0.26-typed-origin.sql']
        with tempfile.TemporaryDirectory(prefix='nex typed inventory % 🧠 ') as temporary:
            root=Path(temporary)
            for index,name in enumerate(names):
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text('owned SDK text '+str(index)+' Я🧠',encoding='utf-8', newline="\n")
            recorded=acceptance.language_resource_inventory(root,[names[0]],'0.27')
            self.assertEqual(set(recorded),set(names))
            for name in names:
                self.assertEqual(recorded[name],hashlib.sha256((root/name).read_bytes()).hexdigest())
            retained=acceptance.language_resource_inventory(root,[names[0]],'0.26')
            self.assertEqual(retained,{names[0]:recorded[names[0]]})
            changed=root/names[-1];changed.write_text('changed origin bytes',encoding='utf-8', newline="\n")
            current=acceptance.language_resource_inventory(root,[names[0]],'0.27')
            self.assertEqual([name for name in names if current[name]!=recorded[name]],[names[-1]])
            changed.unlink()
            with self.assertRaisesRegex(RuntimeError,'missing/escaped language resource'):
                acceptance.language_resource_inventory(root,[names[0]],'0.27')

    def test_language_resource_inventory_keeps_path_and_UTF8_guards(self):
        with tempfile.TemporaryDirectory(prefix='nex inventory guards ') as temporary:
            root=Path(temporary)/'sdk';root.mkdir()
            outside=Path(temporary)/'outside.txt';outside.write_text('outside', newline="\n")
            with self.assertRaisesRegex(RuntimeError,'missing/escaped language resource'):
                acceptance.language_resource_inventory(root,['../outside.txt'],'0.26')
            (root/'alias.txt').symlink_to(outside)
            with self.assertRaisesRegex(RuntimeError,'missing/escaped language resource'):
                acceptance.language_resource_inventory(root,['alias.txt'],'0.26')
            (root/'invalid.txt').write_bytes(b'\xff')
            with self.assertRaises(UnicodeDecodeError):
                acceptance.language_resource_inventory(root,['invalid.txt'],'0.26')

    @unittest.skipUnless(sys.platform.startswith('linux'), 'actual ELF loader context')
    def test_ELF_inherited_RPATH_context_relocates_and_rejects_inconsistent_roots(self):
        compiler = shutil.which('cc')
        if not compiler or not all(shutil.which(name) for name in ('readelf', 'ldd', 'patchelf')):
            self.skipTest('ELF compiler, loader inspection and patchelf are required')
        tools = Path(__file__).resolve().parents[1]/'tools'
        spec = importlib.util.spec_from_file_location('elf_loader_context_bundle', tools/'sdk_bundle.py')
        bundle = importlib.util.module_from_spec(spec); spec.loader.exec_module(bundle)
        environment = {k:v for k,v in os.environ.items() if k not in ('LD_LIBRARY_PATH', 'LD_PRELOAD')}
        def run(args):
            result = subprocess.run(list(map(str,args)), capture_output=True, text=True, env=environment, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            return result.stdout
        with tempfile.TemporaryDirectory(prefix='nex ELF context % 🧠 ') as temporary:
            root=Path(temporary);inputs=root/'inputs';mid=inputs/'middle';leaf=inputs/'leaf';other=inputs/'other'
            for path in (mid,leaf,other):path.mkdir(parents=True)
            (inputs/'leaf.c').write_text('int leaf(void){return VALUE;}\n', newline="\n")
            (inputs/'middle.c').write_text('int leaf(void);int middle(void){return leaf()+1;}\n', newline="\n")
            (inputs/'top.c').write_text('int middle(void);int top(void){return middle()+1;}\n', newline="\n")
            (inputs/'app.c').write_text('#include <stdio.h>\nint top(void);int main(void){printf("%d\\n",top());return 0;}\n', newline="\n")
            leafname='libnex_context_leaf.so.1';midname='libnex_context_middle.so.1';topname='libnex_context_top.so.1'
            for folder,value in ((leaf,40),(other,140)):
                run([compiler,'-shared','-fPIC','-DVALUE='+str(value),inputs/'leaf.c','-Wl,-soname,'+leafname,'-o',folder/leafname])
            run([compiler,'-shared','-fPIC',inputs/'middle.c','-L'+str(leaf),'-l:'+leafname,'-Wl,-soname,'+midname,'-o',mid/midname])
            run([compiler,'-shared','-fPIC',inputs/'top.c','-L'+str(mid),'-l:'+midname,'-Wl,-soname,'+topname,'-o',mid/topname])
            def application(name,leafroot,legacy):
                path=inputs/name
                run([compiler,inputs/'app.c','-L'+str(mid),'-l:'+topname,
                     '-Wl,-rpath-link,'+str(mid)+':'+str(leafroot),
                     '-Wl,'+('--disable-new-dtags' if legacy else '--enable-new-dtags'),
                     '-Wl,-rpath,'+str(mid)+':'+str(leafroot),'-o',path])
                return path
            app=application('app',leaf,True);conflict=application('conflict',other,True)
            self.assertEqual(run([app]),'42\n');self.assertEqual(run([conflict]),'142\n')
            self.assertIn(str(leaf/leafname),run(['ldd',app]))
            self.assertIn(leafname+' => not found',run(['ldd',mid/midname]))
            license_file=root/'LICENSE';license_file.write_text('''MIT License

Copyright (c) 2026 NEX contributors (owned ELF test fixtures)

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
''', newline="\n")
            notices=root/'notices.json';notices.write_text(json.dumps({'schema':'nex.sdk-notices/1','components':[
                {'name':'owned-ELF-fixtures','version':'1','url':'https://github.com/sae-ru/NEX',
                 'roots':[str(inputs)],'license_files':[str(license_file)]}]}), newline="\n")
            def collector(output):
                output.mkdir();b=bundle.LinuxBundle(root,output,notices)
                b.environment=environment
                return b
            output=root/'package';b=collector(output);destination=output/'bin/app'
            b.external(app,destination);b.destinations[app]=destination
            b.collect_elf(app,destination)
            # A cached top image must recheck the entire transitive closure in
            # another root; its immediate middle dependency has unchanged bytes.
            conflicting=collector(root/'conflicting-package')
            conflicting.collect_elf(app,root/'conflicting-package/bin/app')
            with self.assertRaisesRegex(ValueError,'inconsistent loader contexts'):
                conflicting.collect_elf(conflict,root/'conflicting-package/bin/conflict')
            b.relocate_elf('patchelf');used=b.copy_notices('licenses')
            self.assertEqual(len(used),1)
            for image in b.images.values():
                if image['destination'].exists():
                    self.assertNotIn(str(inputs),run(['patchelf','--print-rpath',image['destination']]))
            # RUNPATH is not inherited. Neither notice roots nor the filename's
            # directory silently grant an alternative dependency search path.
            rejected=application('non-inherited',leaf,False)
            self.assertIn(midname+' => not found',run(['ldd',rejected]))
            negative=collector(root/'negative')
            with self.assertRaisesRegex(ValueError,'unresolved ELF dependency '+midname):
                negative.collect_elf(rejected,root/'negative/bin/app')
            shutil.rmtree(inputs)
            moved=root/'moved % 🧠';output.rename(moved)
            self.assertEqual(run([moved/'bin/app']),'42\n')
            listing=run(['ldd',moved/'bin/app'])
            for name in (leafname,midname,topname):
                match=re.search(r'^\s*'+re.escape(name)+r'\s*=>\s*(.*?)\s+\(0x',listing,re.M)
                self.assertIsNotNone(match,listing)
                self.assertIn(moved,Path(match[1]).resolve().parents)

    def test_C_and_CPP_macro_paths_preserve_actual_UTF8_and_controls(self):
        compiler=shutil.which('clang')
        if not compiler or os.name!='posix':
            self.skipTest('a POSIX Clang host is required for the actual path probe')
        tools=Path(__file__).resolve().parents[1]/'tools'
        previous=list(sys.path)
        try:
            sys.path.insert(0,str(tools))
            spec=importlib.util.spec_from_file_location('sdk_resource_path_literals',tools/'sdk_source_resources.py')
            literals=importlib.util.module_from_spec(spec);spec.loader.exec_module(literals)
        finally:
            sys.path[:]=previous
        with tempfile.TemporaryDirectory(prefix='nex-C-paths-') as directory:
            root=Path(directory)
            marker=root/'marker, % 🧠7 "quote" \\ slash\n\tend'
            source=root/'probe.c'
            source.write_text('#include <stdio.h>\nint main(void){FILE *f=fopen(MARKER,"wb");if(!f)return 1;int ok=fputs("42",f)>=0;return fclose(f)==0&&ok?0:2;}\n', newline="\n")
            for language,standard in (('c','c11'),('c++','c++20')):
                with self.subTest(language=language):
                    executable=root/('probe-'+standard)
                    built=subprocess.run([compiler,'-x',language,'-std='+standard,
                        '-DMARKER='+literals.c_string_literal(marker),str(source),'-o',str(executable)],
                        capture_output=True,text=True,timeout=30)
                    self.assertEqual(built.returncode,0,built.stderr)
                    subprocess.run([str(executable)],check=True,timeout=10)
                    self.assertEqual(marker.read_bytes(),b'42')
                    marker.unlink()

    def test_explicit_wasm_linker_is_captured_without_a_compiled_default(self):
        spec=importlib.util.spec_from_file_location('wasm_bundle_selection',Path(__file__).resolve().parents[1]/'tools/sdk_bundle.py')
        bundle=importlib.util.module_from_spec(spec);spec.loader.exec_module(bundle)
        doctor={'wasm_linker':'','other':'preserved'}
        self.assertEqual(bundle.selected_wasm_linker(doctor,{}),doctor)
        for value in ('','/missing/nex-test-wasm-ld'):
            with self.subTest(value=value),self.assertRaisesRegex(ValueError,'executable LLVM 22.1'):
                bundle.selected_wasm_linker(doctor,{'NEX_WASM_LD':value})
        with tempfile.TemporaryDirectory(prefix='nex-wasm-version-') as directory:
            wrong=Path(directory)/'wasm-ld'
            from host_fixture import python_executable
            wrong=python_executable(wrong, '#!'+sys.executable+'\nprint("LLD 21.1.0")\n', shutil.which('clang++'))
            with self.assertRaisesRegex(ValueError,'LLVM 22.1.x'):
                bundle.selected_wasm_linker(doctor,{**os.environ,'NEX_WASM_LD':str(wrong)})
            malformed=Path(directory)/('malformed-wasm-ld.exe' if os.name=='nt' else 'malformed-wasm-ld')
            malformed.write_bytes(b'not a native executable\n');malformed.chmod(0o700)
            with self.assertRaisesRegex(ValueError,'runnable wasm-ld from LLVM 22.1.x'):
                bundle.selected_wasm_linker(doctor,{**os.environ,'NEX_WASM_LD':str(malformed)})
        actual=os.environ.get('NEX_WASM_LD') or shutil.which('wasm-ld')
        if actual is None:
            self.skipTest('actual LLVM22.1 wasm-ld was not selected for the packaging regression')
        selected=bundle.selected_wasm_linker(doctor,{**os.environ,'NEX_WASM_LD':actual})
        self.assertEqual(selected['wasm_linker'],str(Path(actual).absolute()))
        self.assertEqual(selected['other'],'preserved')
        self.assertEqual(doctor,{'wasm_linker':'','other':'preserved'})

    def test_debug_completion_keeps_exact_darwin_root_symbols(self):
        spec=importlib.util.spec_from_file_location('debug_completion',Path(__file__).resolve().parents[1]/'tools/core_capsule.py')
        capsule=importlib.util.module_from_spec(spec);spec.loader.exec_module(capsule)
        inputs=[{'kind':kind,'path':path} for kind,path in (
            ('abi','library-abi.json'),('task_provider','task-provider.json'),
            ('debug_catalog','task-debug-catalog.json'),('debug_sources','task-debug-sources.json'),
            ('debug_source_bundle','debugger/components/app/source-bundle.json'),
            ('debug_source_projection','debugger/source-cache/'+'a'*64+'/source.nex'),
            ('debug_manifest','debug.json'),('debug_formatter','debugger/lldb_nex.py'),('debug_adapter','debugger/nex_dap.py'))]
        metadata={'completion_schema':'nex.native-completion/7','completion_mode':'static-application',
            'compiler_target':'aarch64-unknown-linux-gnu','completion_inputs':copy.deepcopy(inputs)}
        self.assertEqual(capsule.completion_inputs(metadata),[row['path'] for row in inputs])
        metadata['compiler_target']='arm64-apple-darwin27.0.0'
        with self.assertRaises(ValueError):capsule.completion_inputs(metadata)
        symbols=[{'kind':'root_symbols','path':path} for path in (
            'debug-symbols.complete','app.dSYM/Contents/Info.plist','app.dSYM/Contents/Resources/DWARF/app')]
        metadata['completion_inputs']+=symbols
        self.assertEqual(len(capsule.completion_inputs(metadata)),12)
        for mutate in (lambda d:d['completion_inputs'].pop(),
                       lambda d:d['completion_inputs'][-1].update(path='../app'),
                       lambda d:d.update(completion_mode='static-archive'),
                       lambda d:d.update(compiler_target='aarch64-unknown-linux-gnu')):
            changed=copy.deepcopy(metadata);mutate(changed)
            with self.subTest(mutate=mutate),self.assertRaises(ValueError):capsule.completion_inputs(changed)

    def test_debugger_script_paths_preserve_unicode_and_argument_boundaries(self):
        for path in ['/SDK, % 🧠/record.py', '/SDK "quoted"/record.py', '/SDK \\ slash/record.py']:
            command = acceptance.lldb_script_import(Path(path))
            self.assertEqual(shlex.split(command), ['command', 'script', 'import', str(Path(path))])
        self.assertIn('🧠', acceptance.lldb_script_import(Path('/SDK 🧠/record.py')))

    def report(self):
        return {'schema': 'nex.sdk-acceptance/1', 'ok': True,
                'phases': [{'name': name, 'status': 'passed'} for name in acceptance.ACCEPTANCE_PHASES],
                'commands': [{'status': 'passed', 'exit_code': 0}, {'status': 'passed', 'exit_code': 70}]}

    def test_public_task_foreign_resources_require_installed_source_and_history_evidence(self):
        current=self.report()
        current.update(version='0.130.0',language='0.22',doctor={'version':'0.130.0'})
        with self.assertRaisesRegex(RuntimeError,'public source task/FFI'):
            acceptance.validate_completed_report(current)
        fields=('native_reference','destruction_before_unload','checked_exit70_cleanup','source_task_FFI',
                'scope_channel_result_transfer','physical_quota_settled','source_deleted_task_replay')
        producers=[{'language':language,**{name:True for name in fields}} for language in ('C11','CPP20')]
        current['evidence']={'source_resources':{'ok':True,'producers':producers}}
        with self.assertRaisesRegex(RuntimeError,'genuine021 public task/FFI migration'):
            acceptance.validate_completed_report(current)
        migration_fields=('origin_verified','all16_tables_schema_rows_ids_preserved','native_reference','actual_retained_tests')
        current['evidence']['source_resources']['task_foreign_migration']={
            name:{'original_revisions':3,**{field:True for field in migration_fields}}
            for name in ('resources','nominal','callable','imports','tasks')}
        current['evidence']['model_contract']={'preparer_source_checked':True,'preparer_source_language':'0.22'}
        # The new source gate passes; older physical task/request requirements
        # remain mandatory and are checked next, rather than bypassed.
        with self.assertRaisesRegex(RuntimeError,'task/request resource ownership'):
            acceptance.validate_completed_report(current)
        for index in (0,1):
            for name in fields:
                for value in (None,False,'true',1):
                    damaged=copy.deepcopy(current)
                    damaged['evidence']['source_resources']['producers'][index][name]=value
                    with self.subTest(producer=index,field=name,value=value),self.assertRaisesRegex(RuntimeError,'public source task/FFI'):
                        acceptance.validate_completed_report(damaged)
        for producers in ([],[current['evidence']['source_resources']['producers'][0]]*2,[None,None],{}):
            damaged=copy.deepcopy(current);damaged['evidence']['source_resources']['producers']=producers
            with self.subTest(producers=producers),self.assertRaisesRegex(RuntimeError,'public source task/FFI'):
                acceptance.validate_completed_report(damaged)
        for value in (None,0,[],{}):
            damaged=copy.deepcopy(current);damaged['evidence']['source_resources']['producers'][0]['language']=value
            with self.subTest(language=value),self.assertRaisesRegex(RuntimeError,'public source task/FFI'):
                acceptance.validate_completed_report(damaged)
        for name in migration_fields:
            for value in (None,False,'true',1):
                damaged=copy.deepcopy(current);damaged['evidence']['source_resources']['task_foreign_migration']['tasks'][name]=value
                with self.subTest(field=name,value=value),self.assertRaisesRegex(RuntimeError,'genuine021 public task/FFI migration'):
                    acceptance.validate_completed_report(damaged)
        for count in (0,2,4,True,'3'):
            damaged=copy.deepcopy(current);damaged['evidence']['source_resources']['task_foreign_migration']['tasks']['original_revisions']=count
            with self.subTest(revisions=count),self.assertRaisesRegex(RuntimeError,'genuine021 public task/FFI migration'):
                acceptance.validate_completed_report(damaged)
        for replacement in ({},None,{'tasks':{}},dict(current['evidence']['source_resources']['task_foreign_migration'],extra={})):
            damaged=copy.deepcopy(current);damaged['evidence']['source_resources']['task_foreign_migration']=replacement
            with self.subTest(migration=replacement),self.assertRaisesRegex(RuntimeError,'genuine021 public task/FFI migration'):
                acceptance.validate_completed_report(damaged)
        for field,value in [('language','0.21'),('version','0.129.0')]:
            damaged=copy.deepcopy(current);damaged[field]=value
            with self.subTest(field=field),self.assertRaisesRegex(RuntimeError,'version identities differ'):
                acceptance.validate_completed_report(damaged)
        damaged=copy.deepcopy(current);del damaged['doctor']
        with self.assertRaisesRegex(RuntimeError,'version identities differ'):
            acceptance.validate_completed_report(damaged)
        damaged=copy.deepcopy(current);damaged['doctor']['version']='0.129.0'
        with self.assertRaisesRegex(RuntimeError,'version identities differ'):
            acceptance.validate_completed_report(damaged)

    def test_current_SDK_requires_actual_provider_source_check_beyond_help(self):
        current=self.report();current.update(version='0.130.0',language='0.22',doctor={'version':'0.130.0'})
        producer_fields=('native_reference','destruction_before_unload','checked_exit70_cleanup','source_task_FFI',
                         'scope_channel_result_transfer','physical_quota_settled','source_deleted_task_replay')
        migration_fields=('origin_verified','all16_tables_schema_rows_ids_preserved','native_reference','actual_retained_tests')
        current['evidence']={'source_resources':{'ok':True,
            'producers':[{'language':language,**{field:True for field in producer_fields}} for language in ('C11','CPP20')],
            'task_foreign_migration':{name:{'original_revisions':3,**{field:True for field in migration_fields}}
                                     for name in ('resources','nominal','callable','imports','tasks')}}}
        for evidence in [{},{'preparer_installed':True},{'preparer_source_checked':False,'preparer_source_language':'0.22'},
                         {'preparer_source_checked':'true','preparer_source_language':'0.22'},
                         {'preparer_source_checked':1,'preparer_source_language':'0.22'},
                         {'preparer_source_checked':True,'preparer_source_language':'0.21'}]:
            current['evidence']['model_contract']=evidence
            with self.subTest(evidence=evidence),self.assertRaisesRegex(RuntimeError,'model provider source preparation'):
                acceptance.validate_completed_report(current)
        current['evidence']['model_contract']={'preparer_source_checked':True,'preparer_source_language':'0.22'}
        with self.assertRaisesRegex(RuntimeError,'task/request resource ownership'):
            acceptance.validate_completed_report(current)

    def test_task_request_resources_require_installed_physical_completion_evidence(self):
        current=self.report();current['doctor']={'version':'0.129.0'}
        with self.assertRaisesRegex(RuntimeError,'task/request resource ownership'):
            acceptance.validate_completed_report(current)
        fields=('ok','native_per_task_ownership','future_publication_waits_physical_settlement','caller_borrow_survives_group',
                'explicit_request_return_preserves_identity','sibling_authority_refused','single_source_worker_progress_during_cleanup',
                'cancel_deadline_physical_fence','combined_256_task_scope_depth','ancestor_spawn_preserves_lifetime','unpublished_creation_physical_fence')
        evidence={**{name:True for name in fields},'primitive_cases':17,'native_cases':13,
                  'source_value_transport':False,'installed_reference_private_host_gate':False}
        current['evidence']={'source_resources':{'request_resources':evidence}}
        for name in fields:
            for value in (None,False,'true',1):
                damaged=copy.deepcopy(current);damaged['evidence']['source_resources']['request_resources'][name]=value
                with self.subTest(name=name,value=value), self.assertRaisesRegex(RuntimeError,'task/request resource ownership'):
                    acceptance.validate_completed_report(damaged)
        for name in ('source_value_transport','installed_reference_private_host_gate'):
            damaged=copy.deepcopy(current);damaged['evidence']['source_resources']['request_resources'][name]=True
            with self.subTest(claim=name), self.assertRaisesRegex(RuntimeError,'task/request resource ownership'):
                acceptance.validate_completed_report(damaged)
        for name in ('primitive_cases','native_cases'):
            damaged=copy.deepcopy(current);damaged['evidence']['source_resources']['request_resources'][name]=0
            with self.subTest(count=name), self.assertRaisesRegex(RuntimeError,'task/request resource ownership'):
                acceptance.validate_completed_report(damaged)
        with self.assertRaisesRegex(RuntimeError,'task value retirement'):
            acceptance.validate_completed_report(current)

    def http_report(self):
        current=self.report();current.update(version='0.134.4',language='0.24',doctor={'version':'0.134.4'},compiler_sha256='f'*64,
            required_phases=list(acceptance.ACCEPTANCE_PHASES_024_HTTP),
            resource_hashes={'tests/task_http_server.py':'a'*64})
        current['phases']=[{'name':name,'status':'passed'} for name in acceptance.ACCEPTANCE_PHASES_024_HTTP]
        delivery={'schema':'nex.task-http-server/1','ok':True,'state':'passed','language':'0.24','compiler_sha256':'f'*64,
            'helper_sha256':'a'*64,'async_network_DB_claimed':False,'full_objective_complete':False,'checks':148,
            'profiles':2,'concurrent_requests_each':8,'compiled_limit_ceiling_rejections':14,
            **{k:True for k in ('source_absent_execution','request_identity_preserved','TLS_verified','compiler_unchanged',
                'task_whole_file_and_stream_IO','grant_denial_and_path_containment','trap_budget_deadline_disconnect_cleanup','public_HTTP_task_target')},
            'servers':[{'number':i,'exit_code':0,'TLS':i in (2,9)} for i in range(1,15)],
            'images':[{'profile':p,'sha256':'c'*64,'metadata_sha256':'d'*64,'task_limits':{'steps':100000000,'timeout_ms':5000,'workers':4}} for p in ('debug','release')],
            'cancel_observations':[{'profile':p,'code':'E_CANCELLED','opened_file_and_marker_before_disconnect':True,'sole_HTTP_worker_released_before_deadline':True} for p in ('debug','release')],
            'requests':[]}
        for i in range(26):
            text='A🌍\0β' if i<2 else None;identifier=str(i+1)
            delivery['requests'].append({'path':'/api/echo','status':200,'TLS':i<2,'input_body':text,'request_id':identifier,
                'response':{'user':'alice','request_id':identifier,'body':text or '','answer':'42'}})
        delivery['requests'] += [{'path':'/api/read','status':200,'TLS':False,'response':'value'} for _ in range(8)]
        for status,code,count,path in [(401,'UNAUTHORIZED',2,'/api/echo'),(429,'E_LIMIT',2,'/api/limit'),(500,'E_DIV_ZERO',4,'/api/trap'),(504,'E_TIMEOUT',2,'/api/deadline')]:
            delivery['requests'] += [{'path':path,'status':status,'TLS':status==500 and i<2,'response':{'error':{'code':code}}} for i in range(count)]
        delivery['requests'] += [{'path':path,'status':403,'TLS':False,'response':code} for path,code in [('/api/traversal','VALIDATION'),('/api/read','CAPABILITY'),('/api/write','CAPABILITY')] for _ in range(2)]
        current['evidence']={'structured_task_http':{'installed_helper':True,'helper_sha256':'a'*64,'delivery_report_sha256':'b'*64,'delivery':delivery}}
        return current

    def test_sdk1344_requires_complete_HTTP_phase_and_preserves_older_receipts(self):
        for version,count in [('0.132.6',34),('0.133.5',35),('0.134.0',36),('0.134.2',36),('0.134.3',36),('0.134.4',37),('0.135.0',37),('0.135.1',38)]:
            self.assertEqual(len(acceptance.acceptance_phases(version)),count)
        tcp=self.http_report();tcp.update(version='0.135.1',doctor={'version':'0.135.1'},required_phases=list(acceptance.ACCEPTANCE_PHASES_024_TCP))
        tcp['phases']=[{'name':name,'status':'passed'} for name in acceptance.ACCEPTANCE_PHASES_024_TCP]
        with self.assertRaisesRegex(RuntimeError,'SDK TCP evidence'):
            acceptance.validate_completed_report(tcp)
        tcp['phases']=[row for row in tcp['phases'] if row['name']!='structured-task-tcp']
        with self.assertRaisesRegex(RuntimeError,'complete workflow'):
            acceptance.validate_completed_report(tcp)
        current=self.http_report()
        acceptance.validate_task_http_evidence(current)
        # This synthetic shape passes only the HTTP gate; it cannot bypass
        # real stream/migration and all other installed SDK requirements.
        with self.assertRaisesRegex(RuntimeError,'public024 CLI stream execution'):
            acceptance.validate_completed_report(current)
        for mutate in (lambda d:d.update(phases=d['phases'][:-1]),
                       lambda d:d.update(required_phases=list(acceptance.ACCEPTANCE_PHASES_024)),
                       lambda d:d['evidence'].clear()):
            bad=copy.deepcopy(current);mutate(bad)
            with self.assertRaises(RuntimeError):acceptance.validate_completed_report(bad)

    def test_task_HTTP_gate_rejects_missing_or_forged_runtime_outcomes(self):
        current=self.http_report()
        changes=[
            lambda d:d['resource_hashes'].clear(),
            lambda d:d.update(compiler_sha256='0'*64),
            lambda d:d['evidence']['structured_task_http'].update(delivery=None),
            lambda d:d['evidence']['structured_task_http'].update(installed_helper=1),
            lambda d:d['evidence']['structured_task_http']['delivery'].update(ok=1),
            lambda d:d['evidence']['structured_task_http']['delivery'].update(profiles=True),
            lambda d:d['evidence']['structured_task_http']['delivery'].update(TLS_verified=False),
            lambda d:d['evidence']['structured_task_http']['delivery'].update(async_network_DB_claimed=True),
            lambda d:d['evidence']['structured_task_http']['delivery']['servers'][0].update(exit_code=False),
            lambda d:d['evidence']['structured_task_http']['delivery']['images'][0].update(metadata_sha256='?'),
            lambda d:d['evidence']['structured_task_http']['delivery'].update(cancel_observations=None),
            lambda d:d['evidence']['structured_task_http']['delivery']['cancel_observations'][0].update(code='E_LIMIT'),
            lambda d:d['evidence']['structured_task_http']['delivery']['requests'].pop(),
            lambda d:d['evidence']['structured_task_http']['delivery']['requests'][0].update(TLS='true'),
            lambda d:d['evidence']['structured_task_http']['delivery']['requests'][0]['response'].update(user='injected'),
            lambda d:d['evidence']['structured_task_http']['delivery']['requests'][0]['response'].update(body='lost NUL'),
            lambda d:d['evidence']['structured_task_http']['delivery']['requests'][-1].update(response='other'),
        ]
        for i,mutate in enumerate(changes):
            bad=copy.deepcopy(current);mutate(bad)
            with self.subTest(mutation=i),self.assertRaises(RuntimeError):acceptance.validate_task_http_evidence(bad)

    def test_sdk134_requires_public_streams_and_every_genuine_history(self):
        self.assertEqual(len(acceptance.acceptance_phases('0.134.0')),36)
        self.assertEqual(len(acceptance.acceptance_phases('0.133.5')),35)
        current=self.report();current.update(version='0.134.0',language='0.24',doctor={'version':'0.134.0'},compiler_sha256='a'*64)
        current['phases']=[{'name':name,'status':'passed'} for name in acceptance.ACCEPTANCE_PHASES_024]
        with self.assertRaisesRegex(RuntimeError,'public024 CLI stream execution'):
            acceptance.validate_completed_report(current)
        names=['aliases','write_append','future_owner','scoped_cleanup','source_cancel']
        delivery={'ok':True,'language':'0.24','compiler_sha256':'a'*64,'native_reference_pairs':5,'rejected_programs':3,
                  'old_metadata_rejected_before_store':True,'cases':[{'name':name,'native_reference':True,'source_absent_native':True} for name in names]}
        evidence={'delivery':delivery,'original_SDK_execution_claimed':False,
                  'delivery_report_sha256':'b'*64,'history_report_sha256':'c'*64}
        current['evidence']={'structured_task_file_streams':evidence}
        with self.assertRaisesRegex(RuntimeError,'all genuine023 public024 migrations'):
            acceptance.validate_completed_report(current)
        fields=('all16_tables_schema_rows_ids_preserved','physical_sources_manifest_lock_preserved',
                'idempotent','materialized_current_project_checked','source_absent_native','native_reference')
        history={'ok':True,'language':'0.24','compiler_sha256':'a'*64,'genuine023_histories':9,'genuine023_revisions':27,
                 'native_reference_pairs':27,'rejected_migrations':9,
                 'cases':[{'origin_revision':format(i,'064x'),'revision':format(i+100,'064x'),**{field:True for field in fields}} for i in range(27)]}
        evidence['histories']=history
        # Passing this structural gate must still reach the separate real host,
        # write-history and other workflow gates, not declare an SDK accepted.
        with self.assertRaisesRegex(RuntimeError,'installed private stream host'):
            acceptance.validate_completed_report(current)
        for field in fields:
            bad=copy.deepcopy(current);bad['evidence']['structured_task_file_streams']['histories']['cases'][0][field]=False
            with self.subTest(field=field),self.assertRaisesRegex(RuntimeError,'all genuine023 public024 migrations'):
                acceptance.validate_completed_report(bad)
        for field,value in [('native_reference_pairs',True),('cases',history['cases'][:-1]),('compiler_sha256','d'*64)]:
            bad=copy.deepcopy(current);bad['evidence']['structured_task_file_streams']['histories'][field]=value
            with self.subTest(field=field),self.assertRaisesRegex(RuntimeError,'all genuine023 public024 migrations'):
                acceptance.validate_completed_report(bad)

    def test_sdk1332_requires_actual_installed_stream_host_execution(self):
        contract=acceptance._stream_host_contract();CASES,HEADERS,SOURCES=contract.CASES,contract.HEADERS,contract.SOURCES
        current=self.report();current.update(version='0.133.2',language='0.23',doctor={'version':'0.133.2'})
        current['phases']=[{'name':name,'status':'passed'} for name in acceptance.ACCEPTANCE_PHASES_023]
        with self.assertRaisesRegex(RuntimeError,'installed private stream host'):
            acceptance.validate_completed_report(current)
        fields=('ok','actual_partial_write','typed_open_no_raw_file_ids','original_grants','physical_quota_retention',
                'single_CPU_worker_progress','cancel_physical_drain','immutable_input_snapshots','large_file_streaming','protocol_rejections')
        pins={'tools/task_file_stream_host_acceptance.cpp',*('runtime/'+n for n in (*HEADERS,*SOURCES))}
        host={'schema':'nex.installed-task-stream-host/1',**{k:True for k in fields},'source_support':False,'cases':27,
              'case_names':list(CASES),'probe_sha256':'a'*64,'installed_sources':{n:'b'*64 for n in pins}}
        current['evidence']={'structured_task_file_writes':{'private_stream_host':host}}
        with self.assertRaisesRegex(RuntimeError,'extended genuine022 history'):
            acceptance.validate_completed_report(current)
        for field in fields:
            for value in (None,False,1,'true'):
                bad=copy.deepcopy(current);bad['evidence']['structured_task_file_writes']['private_stream_host'][field]=value
                with self.subTest(field=field,value=value),self.assertRaisesRegex(RuntimeError,'installed private stream host'):
                    acceptance.validate_completed_report(bad)
        for field,value in [('cases',True),('cases',26),('source_support',True),('source_support',None),('case_names',list(CASES)[:-1]),
                            ('case_names',[CASES[0]]*27),('probe_sha256','bad'),('installed_sources',{})]:
            bad=copy.deepcopy(current);bad['evidence']['structured_task_file_writes']['private_stream_host'][field]=value
            with self.subTest(field=field),self.assertRaisesRegex(RuntimeError,'installed private stream host'):
                acceptance.validate_completed_report(bad)

    def test_sdk154_stream_host_requires_the_installed_compatibility_header(self):
        contract=acceptance._stream_host_contract()
        fields=('ok','actual_partial_write','typed_open_no_raw_file_ids','original_grants','physical_quota_retention',
                'single_CPU_worker_progress','cancel_physical_drain','immutable_input_snapshots','large_file_streaming','protocol_rejections')
        pins={'tools/task_file_stream_host_acceptance.cpp',
              *('runtime/'+n for n in (*contract.HEADERS,*contract.SOURCES))}
        host={'schema':'nex.installed-task-stream-host/1',**{k:True for k in fields},'source_support':False,
              'cases':27,'case_names':list(contract.CASES),'probe_sha256':'a'*64,
              'installed_sources':{name:'b'*64 for name in pins}}
        report={'evidence':{'structured_task_file_writes':{'private_stream_host':host}}}
        acceptance.validate_installed_stream_host(report,(0,153,0))
        with self.assertRaisesRegex(RuntimeError,'installed private stream host'):
            acceptance.validate_installed_stream_host(report,(0,154,0))
        host['installed_sources']['tests/host_test.h']='c'*64
        acceptance.validate_installed_stream_host(report,(0,154,0))
        for value in ('not-a-hash','d'*63,None):
            changed=copy.deepcopy(report)
            changed['evidence']['structured_task_file_writes']['private_stream_host']['installed_sources']['tests/host_test.h']=value
            with self.subTest(value=value),self.assertRaisesRegex(RuntimeError,'installed private stream host'):
                acceptance.validate_installed_stream_host(changed,(0,154,0))
        changed=copy.deepcopy(report)
        changed['evidence']['structured_task_file_writes']['private_stream_host']['installed_sources']['unreviewed.hpp']='e'*64
        with self.assertRaisesRegex(RuntimeError,'installed private stream host'):
            acceptance.validate_installed_stream_host(changed,(0,154,0))

    def test_sdk1331_requires_extended_genuine_history_before_other_acceptance(self):
        current=self.report();current.update(version='0.133.1',language='0.23',doctor={'version':'0.133.1'},compiler_sha256='a'*64)
        current['phases']=[{'name':name,'status':'passed'} for name in acceptance.ACCEPTANCE_PHASES_023]
        with self.assertRaisesRegex(RuntimeError,'extended genuine022 history'):
            acceptance.validate_completed_report(current)
        for value in (None,False,[],"bad"):
            damaged=copy.deepcopy(current);damaged['evidence']={'structured_task_file_writes':value}
            with self.subTest(parent=value),self.assertRaisesRegex(RuntimeError,'extended genuine022 history'):
                acceptance.validate_completed_report(damaged)
        fields=('ok','all16_tables_schema_rows_ids_preserved','native_reference','retained_web_tests')
        migration_fields=('all16_tables_schema_rows_ids_preserved','native_reference','retained_web_tests',
                          'implicit_HEAD_upgrade_rejected','physical_manifest_unchanged','idempotent')
        origin_sdk='a75421b899a7e47d617a8ef6257123f75db4ee4f9869fe2aa11c3be6b87bb1a8'
        history={'schema':'nex.public-task-write-histories/1','compiler_sha256':'a'*64,'language':'0.23','origin_SDK_sha256':origin_sdk,
            **{field:True for field in fields},'genuine022_histories':6,'genuine022_revisions':18,
            'origins':[{'name':name,'revisions':3,'sql_sha256':'b'*64,'origin_SDK_sha256':origin_sdk} for name in ('resources','nominal','callable','imports','tasks','model-compute-device-imports')],
            'migrations':[{'origin_revision':format(i,'064x'),'revision':format(i+18,'064x'),**{field:True for field in migration_fields}} for i in range(18)]}
        current['evidence']={'structured_task_file_writes':{'extended_histories':history}}
        with self.assertRaisesRegex(RuntimeError,'public023 task file-write delivery'):
            acceptance.validate_completed_report(current)
        for field in fields:
            for value in (None,False,1,'true'):
                damaged=copy.deepcopy(current);damaged['evidence']['structured_task_file_writes']['extended_histories'][field]=value
                with self.subTest(field=field,value=value),self.assertRaisesRegex(RuntimeError,'extended genuine022 history'):
                    acceptance.validate_completed_report(damaged)
        for field,value in [('genuine022_revisions',True),('genuine022_revisions',17),('genuine022_histories',5),('compiler_sha256','c'*64),
                            ('language','0.22'),('origins',history['origins'][:5]),('migrations',history['migrations'][:17])]:
            damaged=copy.deepcopy(current);damaged['evidence']['structured_task_file_writes']['extended_histories'][field]=value
            with self.subTest(field=field),self.assertRaisesRegex(RuntimeError,'extended genuine022 history'):
                acceptance.validate_completed_report(damaged)
        for field in migration_fields:
            damaged=copy.deepcopy(current);damaged['evidence']['structured_task_file_writes']['extended_histories']['migrations'][0][field]=False
            with self.subTest(migration_field=field),self.assertRaisesRegex(RuntimeError,'extended genuine022 history'):
                acceptance.validate_completed_report(damaged)

    def test_sdk133_requires_actual_public_write_delivery_and_genuine022_history(self):
        current=self.report();current.update(version='0.133.0',language='0.23',doctor={'version':'0.133.0'},compiler_sha256='a'*64)
        current['phases']=[{'name':name,'status':'passed'} for name in acceptance.ACCEPTANCE_PHASES_023]
        with self.assertRaisesRegex(RuntimeError,'public023 task file-write delivery'):
            acceptance.validate_completed_report(current)
        fields=('ok','all16_tables_schema_rows_ids_preserved','native_reference','static_shared_binary_edges','mixed_static_shared',
                'explicit_write_grant_denied','source_deleted_package','source_deleted_replay','browser_exclusion')
        migration_fields=('origin_verified','all16_tables_schema_rows_ids_preserved','physical_projection_unchanged','implicit_upgrade_rejected','native_reference')
        project_fields=('actual_binary_edges','native_reference','write_grant_denied','source_deleted_package','source_deleted_replay')
        writes={'schema':'nex.public-task-write-delivery/1','language':'0.23','compiler_sha256':'a'*64,**{key:True for key in fields},
                'genuine022_migrations':3,'migrations':[{'origin_revision':format(i,'064x'),'revision':format(i+3,'064x'),**{key:True for key in migration_fields}} for i in range(3)],
                'projects':[{'mode':mode,**{key:True for key in project_fields}} for mode in ('static','shared','mixed')]}
        current['evidence']={'structured_task_file_writes':writes}
        for field in fields:
            for value in [None,False,1,'true']:
                damaged=copy.deepcopy(current);damaged['evidence']['structured_task_file_writes'][field]=value
                with self.subTest(field=field,value=value),self.assertRaisesRegex(RuntimeError,'public023 task file-write delivery'):
                    acceptance.validate_completed_report(damaged)
        for field,value in [('genuine022_migrations',True),('genuine022_migrations',2),('compiler_sha256','b'*64),('language','0.22'),('projects',writes['projects'][:2]),('migrations',writes['migrations'][:2])]:
            damaged=copy.deepcopy(current);damaged['evidence']['structured_task_file_writes'][field]=value
            with self.subTest(field=field),self.assertRaisesRegex(RuntimeError,'public023 task file-write delivery'):
                acceptance.validate_completed_report(damaged)
        for group,fields in [('migrations',migration_fields),('projects',project_fields)]:
            for field in fields:
                damaged=copy.deepcopy(current);damaged['evidence']['structured_task_file_writes'][group][0][field]=False
                with self.subTest(group=group,field=field),self.assertRaisesRegex(RuntimeError,'public023 task file-write delivery'):
                    acceptance.validate_completed_report(damaged)
        damaged=copy.deepcopy(current);damaged['evidence']['structured_task_file_writes']['migrations'][0]['revision']='bad'
        with self.assertRaisesRegex(RuntimeError,'public023 task file-write delivery'):
            acceptance.validate_completed_report(damaged)
        # Public writers do not waive the existing HEAD integrity gate.
        with self.assertRaisesRegex(RuntimeError,'retained HEAD language guard'):
            acceptance.validate_completed_report(current)

    def test_sdk1326_requires_actual_retained_HEAD_language_guard(self):
        current=self.report();current.update(version='0.132.6',language='0.22',doctor={'version':'0.132.6'})
        with self.assertRaisesRegex(RuntimeError,'retained HEAD language guard'):
            acceptance.validate_completed_report(current)
        guard={'schema':'nex.head-language-guard/1','actual_cli':True,'compiler_language':'0.22',
            'origin_language':'0.19','fixtures':['history','tasks'],'command':'check','code':'E_LANGUAGE_VERSION',
            'all16_tables_schema_rows_ids_preserved':True,'physical_projection_restored':True}
        current['evidence']={'task_file_migration':{'head_language_guard':guard,
            'stores':{name:{'implicit_HEAD_language_change_rejected':True} for name in ('history','tasks')}}}
        for field in ('actual_cli','all16_tables_schema_rows_ids_preserved','physical_projection_restored'):
            for value in (None,False,1,'true'):
                damaged=copy.deepcopy(current);damaged['evidence']['task_file_migration']['head_language_guard'][field]=value
                with self.subTest(field=field,value=value),self.assertRaisesRegex(RuntimeError,'retained HEAD language guard'):
                    acceptance.validate_completed_report(damaged)
        for field,value in [('schema','other'),('compiler_language','0.19'),('origin_language','0.22'),
                            ('fixtures',['history']),('command','describe'),('code','E_OPTION')]:
            damaged=copy.deepcopy(current);damaged['evidence']['task_file_migration']['head_language_guard'][field]=value
            with self.subTest(field=field),self.assertRaisesRegex(RuntimeError,'retained HEAD language guard'):
                acceptance.validate_completed_report(damaged)
        for name in ('history','tasks'):
            damaged=copy.deepcopy(current);damaged['evidence']['task_file_migration']['stores'][name]['implicit_HEAD_language_change_rejected']=False
            with self.subTest(fixture=name),self.assertRaisesRegex(RuntimeError,'retained HEAD language guard'):
                acceptance.validate_completed_report(damaged)
        for field in ('head_language_guard','stores'):
            damaged=copy.deepcopy(current);damaged['evidence']['task_file_migration'][field]=None
            with self.subTest(field=field),self.assertRaisesRegex(RuntimeError,'retained HEAD language guard'):
                acceptance.validate_completed_report(damaged)
        # New evidence does not waive any existing delivery requirements.
        with self.assertRaisesRegex(RuntimeError,'installed owned device log harness'):
            acceptance.validate_completed_report(current)

    def test_sdk1323_requires_the_installed_owned_log_harness(self):
        current=self.report();current.update(version='0.132.3',language='0.22',doctor={'version':'0.132.3'})
        for value in [None,False,1,'true']:
            damaged=copy.deepcopy(current);damaged['evidence']={'owned_device_contract':{'log_harness_installed':value}}
            with self.subTest(value=value),self.assertRaisesRegex(RuntimeError,'installed owned device log harness'):
                acceptance.validate_completed_report(damaged)
        current['evidence']={'owned_device_contract':{'log_harness_installed':True}}
        with self.assertRaisesRegex(RuntimeError,'installed owned device fault harness'):
            acceptance.validate_completed_report(current)

    def test_sdk1322_requires_the_installed_owned_fault_harness(self):
        current=self.report();current.update(version='0.132.2',language='0.22',doctor={'version':'0.132.2'})
        for value in [None,False,1,'true']:
            damaged=copy.deepcopy(current);damaged['evidence']={'owned_device_contract':{'fault_harness_installed':value}}
            with self.subTest(value=value),self.assertRaisesRegex(RuntimeError,'installed owned device fault harness'):
                acceptance.validate_completed_report(damaged)
        current['evidence']={'owned_device_contract':{'fault_harness_installed':True}}
        with self.assertRaisesRegex(RuntimeError,'owned device contract evidence'):
            acceptance.validate_completed_report(current)

    def test_sdk132_requires_checked_owned_provider_without_claiming_hardware(self):
        current=self.report();current.update(version='0.132.0',language='0.22',doctor={'version':'0.132.0'},compiler_sha256='a'*64)
        fields=('descriptor','native_reference','typescript_reference','installed_provider_source_checked')
        prepared={'schema':'nex.owned-opencl-preparation/1','ok':True,'source_checked':True,
            'source_language':'0.22','compiler_sha256':'a'*64,'native_provider_built':False,'driver_initialized':False,'hardware_executed':False,
            'signature_sha256':{name:'b'*64 for name in ('open','upload','dispatch','download','name','kernel_ns','busy')}}
        current['evidence']={'owned_device_contract':{**{name:True for name in fields},'preparation':prepared}}
        for field in fields:
            damaged=copy.deepcopy(current);damaged['evidence']['owned_device_contract'][field]=False
            with self.subTest(field=field),self.assertRaisesRegex(RuntimeError,'owned device contract evidence'):
                acceptance.validate_completed_report(damaged)
        for field,value in [('ok',1),('source_checked',False),('compiler_sha256','c'*64),('source_language','0.21'),
                ('native_provider_built',True),('driver_initialized',True),('hardware_executed',True),('signature_sha256',{})]:
            damaged=copy.deepcopy(current);damaged['evidence']['owned_device_contract']['preparation'][field]=value
            with self.subTest(field=field),self.assertRaisesRegex(RuntimeError,'owned device preparation evidence'):
                acceptance.validate_completed_report(damaged)
        with self.assertRaisesRegex(RuntimeError,'dependent resource FFI evidence'):
            acceptance.validate_completed_report(current)

    def test_sdk131_requires_actual_installed_dependent_resource_execution(self):
        current=self.report();current.update(version='0.131.0',language='0.22',doctor={'version':'0.131.0'},compiler_sha256='a'*64)
        fields=('ok','native_reference','genuine_previous_C_prefix','hidden_parent_scope_future_channel_closure',
                'physical_parent_quota','cancel_deadline_borrow_fence','source_deleted_replay','client_exclusion')
        current['evidence']={'dependent_resource_ffi':{**{key:True for key in fields},'source_checks':37,
            'source_report':{'schema':'nex.dependent-resource-source/1','ok':True,'source_parent_FFI':True,'compiler_sha256':'a'*64,
                             'checks':[{}]*37,'actual_producers':['C11','CPP20'],'actual_GPU_NPU_resources':False}}}
        for field in fields:
            for value in [None,False,1,'true']:
                damaged=copy.deepcopy(current);damaged['evidence']['dependent_resource_ffi'][field]=value
                with self.subTest(field=field,value=value),self.assertRaisesRegex(RuntimeError,'dependent resource FFI evidence'):
                    acceptance.validate_completed_report(damaged)
        for count in [None,'37',True,36,38]:
            damaged=copy.deepcopy(current);damaged['evidence']['dependent_resource_ffi']['source_checks']=count
            with self.subTest(count=count),self.assertRaisesRegex(RuntimeError,'dependent resource FFI evidence'):
                acceptance.validate_completed_report(damaged)
        for field,value in [('ok',1),('checks',[{}]*36),('source_parent_FFI',False),('compiler_sha256','b'*64),
                            ('actual_producers',['C11']),('actual_GPU_NPU_resources',True)]:
            damaged=copy.deepcopy(current);damaged['evidence']['dependent_resource_ffi']['source_report'][field]=value
            with self.subTest(field=field),self.assertRaisesRegex(RuntimeError,'actual dependent resource source report'):
                acceptance.validate_completed_report(damaged)
        with self.assertRaisesRegex(RuntimeError,'public source task/FFI resource transport'):
            acceptance.validate_completed_report(current)

    def test_sdk164_requires_six_distinct_genuine_parent_prefix_cases(self):
        fixture=Path(__file__).parent/'fixtures/dependent-resource-source-0.164.json'
        origin=json.loads(fixture.with_suffix('.origin.json').read_bytes())
        self.assertEqual(hashlib.sha256(fixture.read_bytes()).hexdigest(),origin['fixture_sha256'])
        proof=json.loads(fixture.read_bytes())
        options=dict(compiler_sha256=origin['compiler_sha256'],toolchain='0.164.0',language='0.28')
        self.assertEqual(acceptance.validate_dependent_resource_source_report(proof,**options),43)
        self.assertEqual(acceptance.dependent_resource_source_check_count('0.163.0'),37)
        parent=[i for i,row in enumerate(proof['checks']) if 'genuine_previous_parent_header' in row]
        self.assertEqual(len(parent),6)
        mutations=[]
        missing=copy.deepcopy(proof);missing['checks'].pop(parent[-1]);mutations.append(missing)
        duplicate=copy.deepcopy(proof);duplicate['checks'][parent[-1]]=copy.deepcopy(duplicate['checks'][parent[-2]]);mutations.append(duplicate)
        stripped=copy.deepcopy(proof);stripped['checks']=[r for r in stripped['checks'] if 'genuine_previous_parent_header' not in r];mutations.append(stripped)
        for field,value in [('genuine_previous_parent_header','0'*64),('previous_parent_table_bytes',296),
                ('previous_parent_table_bytes',312),('previous_parent_table_bytes',True),('native_and_independent_AST',False),
                ('child_before_parent_destruction',False),('dialect','C23'),('case','unknown')]:
            damaged=copy.deepcopy(proof);damaged['checks'][parent[0]][field]=value;mutations.append(damaged)
        for field,value in [('compiler_sha256','0'*64),('language','0.27'),('actual_producers',['C11']),('actual_GPU_NPU_resources',True)]:
            damaged=copy.deepcopy(proof);damaged[field]=value;mutations.append(damaged)
        for index,damaged in enumerate(mutations):
            with self.subTest(mutation=index),self.assertRaises(RuntimeError):
                acceptance.validate_dependent_resource_source_report(damaged,**options)

    def test_task_value_retirement_requires_actual_installed_cleanup_evidence(self):
        current=self.report();current['doctor']={'version':'0.128.0'}
        with self.assertRaisesRegex(RuntimeError,'task value retirement'):
            acceptance.validate_completed_report(current)
        fields=('ok','destructors_outside_scheduler_mutex','cancelled_event_cleanup','task_scope_publication_fence',
                'buffer_storage_quota_fence','nested_reentrant_cleanup','root_results_remain_joinable','iterative_256_scope_retirement','api_cleanup_isolation','stolen_completion_fence')
        current['evidence']={'source_resources':{'task_value_retirement':{**{name:True for name in fields},'cases':15}}}
        for name in fields:
            for value in (False,None,'true'):
                damaged=copy.deepcopy(current);damaged['evidence']['source_resources']['task_value_retirement'][name]=value
                with self.subTest(name=name,value=value),self.assertRaisesRegex(RuntimeError,'task value retirement'):
                    acceptance.validate_completed_report(damaged)
        for count in (0,14,16,True,'15'):
            damaged=copy.deepcopy(current);damaged['evidence']['source_resources']['task_value_retirement']['cases']=count
            with self.subTest(count=count),self.assertRaisesRegex(RuntimeError,'task value retirement'):
                acceptance.validate_completed_report(damaged)
        with self.assertRaisesRegex(RuntimeError,'logical resource region'):
            acceptance.validate_completed_report(current)

    def test_current_resource_region_delivery_requires_physical_scope_evidence(self):
        current=self.report();current['doctor']={'version':'0.126.0'}
        with self.assertRaisesRegex(RuntimeError,'logical resource region'):
            acceptance.validate_completed_report(current)
        fields=('ok','native_scope_ownership','scope_exit_waits_physical_cleanup','only_source_worker_remains_available',
                'native_256_scope_depth','ancestor_promotion','root_group_retirement','prepared_access_survives_64_resumes','unpublished_factory_fence')
        current['evidence']={'source_resources':{'resource_regions':{**{name:True for name in fields},'cases':18}}}
        for name in fields:
            for value in (False,None,'true'):
                damaged=copy.deepcopy(current);damaged['evidence']['source_resources']['resource_regions'][name]=value
                with self.subTest(name=name,value=value),self.assertRaisesRegex(RuntimeError,'logical resource region'):
                    acceptance.validate_completed_report(damaged)
        for count in (0,17,19,True,'18'):
            damaged=copy.deepcopy(current);damaged['evidence']['source_resources']['resource_regions']['cases']=count
            with self.subTest(count=count),self.assertRaisesRegex(RuntimeError,'logical resource region'):
                acceptance.validate_completed_report(damaged)
        with self.assertRaisesRegex(RuntimeError,'physical resource executor'):
            acceptance.validate_completed_report(current)

    def test_current_executor_delivery_cannot_be_omitted_from_a_green_report(self):
        current=self.report();current['doctor']={'version':'0.125.0'}
        with self.assertRaisesRegex(RuntimeError,'physical resource executor'):
            acceptance.validate_completed_report(current)
        fields=('ok','owning_thread_factory_cleanup','physical_fence_and_quota_retention',
                'queued_running_cancellation','actual_module_destructor_unload','module_exceptions_destroyed_before_unload')
        current['evidence']={'source_resources':{'resource_executor':{**{name:True for name in fields},'cases':22}}}
        for name in fields:
            for value in (False,None,'true'):
                damaged=copy.deepcopy(current);damaged['evidence']['source_resources']['resource_executor'][name]=value
                with self.subTest(name=name,value=value),self.assertRaisesRegex(RuntimeError,'physical resource executor'):
                    acceptance.validate_completed_report(damaged)
        for count in (0,20,22,True,'21'):
            damaged=copy.deepcopy(current);damaged['evidence']['source_resources']['resource_executor']['cases']=count
            with self.subTest(count=count),self.assertRaisesRegex(RuntimeError,'physical resource executor'):
                acceptance.validate_completed_report(damaged)
        # A complete executor receipt still owes the earlier opaque-resource and
        # genuine-history evidence; it must not bypass any existing delivery gate.
        with self.assertRaisesRegex(RuntimeError,'opaque resource'):
            acceptance.validate_completed_report(current)

    def test_distribution_requires_current_complete_workflow(self):
        acceptance.validate_completed_report(self.report())
        old = self.report()
        old['phases'] = [phase for phase in old['phases'] if phase['name'] in (
            'discovery', 'new-project', 'reviewed-failure', 'graph-repair-import',
            'backend-agreement', 'binary-values', 'text-files', 'profile',
            'archive-debug-replay-export', 'scalar-proof', 'authenticated-storage', 'browser')]
        self.assertEqual(len(old['phases']), 12)
        with self.assertRaisesRegex(RuntimeError, 'complete workflow'):acceptance.validate_completed_report(old)
        for name in ('editor-tools', 'traits', 'graph-snapshot-recovery', 'graph-queries',
                     'structured-task-file-reads', 'structured-task-profile', 'structured-task-debug', 'static-task-providers',
                     'shared-task-providers','task-provider-profiling','task-provider-debugging'):
            missing = self.report();missing['phases'] = [p for p in missing['phases'] if p['name'] != name]
            with self.subTest(missing=name), self.assertRaises(RuntimeError):acceptance.validate_completed_report(missing)

    def test_compute_sdk121_requires_checked_delivery(self):
        report=self.report();report['doctor']={'version':'0.121.0'}
        keys=('descriptor','native_reference','typescript_reference','source_deleted_replay','standalone','cpu_device_reported')
        report['evidence']={'compute_contract':{key:True for key in keys}}
        for key in keys:
            for value in (False,None,1,'true'):
                changed=copy.deepcopy(report);changed['evidence']['compute_contract'][key]=value
                with self.subTest(key=key,value=value),self.assertRaisesRegex(RuntimeError,'compute contract delivery'):
                    acceptance.validate_completed_report(changed)

    def test_model_sdk122_requires_checked_delivery(self):
        report=self.report();report['doctor']={'version':'0.122.0'}
        keys=('descriptor','native_reference','typescript_reference','source_deleted_replay',
              'standalone','managed_memory_balanced','preparer_installed')
        report['evidence']={'model_contract':{key:True for key in keys}}
        for key in keys:
            for value in (False,None,1,'true'):
                changed=copy.deepcopy(report);changed['evidence']['model_contract'][key]=value
                with self.subTest(key=key,value=value),self.assertRaisesRegex(RuntimeError,'model contract delivery'):
                    acceptance.validate_completed_report(changed)

    def test_provider_debug_sdk119_requires_owned_delivery_and_actual_protocol(self):
        report={'schema':'nex.sdk-acceptance/1','ok':True,'doctor':{'version':'0.119.0'},
            'phases':[{'name':name,'status':'passed'} for name in acceptance.ACCEPTANCE_PHASES],
            'commands':[{'status':'passed','exit_code':0}]}
        delivery=('descriptor','native_reference','static_and_shared_artifacts','original_registry_symbols',
            'closed_owned_images','source_union','retained_completion7','raw_package_provenance','source_deleted_capture','source_deleted_replay')
        for key in delivery:
            for value in (False,None,'true',1):
                changed=copy.deepcopy(report);changed['evidence']={'task_provider_debugging':{name:True for name in delivery}}
                changed['evidence']['task_provider_debugging'][key]=value
                with self.subTest(key=key,value=value),self.assertRaisesRegex(RuntimeError,'provider debugger delivery'):
                    acceptance.validate_completed_report(changed)
        report['evidence']={'task_provider_debugging':{name:True for name in delivery},'live_debugger':True}
        live=('provider_locals','component_pure_watch','next_in_out','stale_references','retained_live_debug','package_live_debug','replay_live_debug')
        for key in live:
            for value in (False,None,'true',1):
                changed=copy.deepcopy(report);changed['evidence']['task_provider_debugging'].update({name:True for name in live})
                changed['evidence']['task_provider_debugging'][key]=value
                with self.subTest(key=key,value=value),self.assertRaisesRegex(RuntimeError,'provider debugger execution'):
                    acceptance.validate_completed_report(changed)
        report['evidence']['task_provider_debugging'].update({name:True for name in live})
        with self.assertRaisesRegex(RuntimeError,'provider profiling delivery'):
            acceptance.validate_completed_report(report)


    def test_static_provider_sdk116_requires_actual_archives_and_source_deleted_delivery(self):
        current = self.report();current['doctor']={'version':'0.116.0'}
        fields = ('descriptor','actual_static_archives','descriptor_accessors','consumer_ownership',
                  'native_reference','unused_read_excluded','root_file_grant','root_limits','warm_cache',
                  'retained_completion','source_deleted_replay','standalone_without_resources','source_deleted_package')
        with self.assertRaisesRegex(RuntimeError,'static task provider delivery'):
            acceptance.validate_completed_report(current)
        current['evidence']={'static_task_providers':{name:True for name in fields}}
        for name in fields:
            for value in (False,None,'true'):
                changed=copy.deepcopy(current);changed['evidence']['static_task_providers'][name]=value
                with self.subTest(delivery=name,value=value),self.assertRaisesRegex(RuntimeError,'static task provider delivery'):
                    acceptance.validate_completed_report(changed)
        # New provider evidence cannot waive genuine debugger/profile/read gates.
        with self.assertRaisesRegex(RuntimeError,'task debugger delivery'):
            acceptance.validate_completed_report(current)

    def test_shared_provider_sdk117_requires_loaded_closure_and_raw_retained_provenance(self):
        current=self.report();current['doctor']={'version':'0.117.0'}
        fields=('descriptor','actual_shared_images','defined_descriptor_accessors','consumer_ownership',
                'actual_loaded_closure','one_runtime','native_reference','unused_read_excluded','root_file_grant',
                'root_limits','warm_cache','retained_completion5','raw_package_provenance','source_deleted_replay',
                'copied_closure_without_resources','source_deleted_package')
        with self.assertRaisesRegex(RuntimeError,'shared task provider delivery'):
            acceptance.validate_completed_report(current)
        current['evidence']={'shared_task_providers':{name:True for name in fields}}
        for name in fields:
            for value in (False,None,'true'):
                changed=copy.deepcopy(current);changed['evidence']['shared_task_providers'][name]=value
                with self.subTest(delivery=name,value=value),self.assertRaisesRegex(RuntimeError,'shared task provider delivery'):
                    acceptance.validate_completed_report(changed)
        # The separate mode never waives static123 or older delivery contracts.
        with self.assertRaisesRegex(RuntimeError,'static task provider delivery'):
            acceptance.validate_completed_report(current)

    def test_provider_profile_sdk118_requires_actual_source_catalog_and_owned_delivery(self):
        current=self.report();current['doctor']={'version':'0.118.0'}
        fields=('descriptor','native_reference','exact_source_calls','zero_provider_generic','physical_owners',
                'defined_registry_accessors','one_runtime','managed_cleanup','event_only_completeness','root_limits',
                'unused_read_excluded','warm_cache','measured_retained_completion6','raw_package_provenance',
                'source_deleted_replay','copied_profile_without_resources','source_deleted_package_profile')
        with self.assertRaisesRegex(RuntimeError,'task provider profiling delivery'):
            acceptance.validate_completed_report(current)
        current['evidence']={'task_provider_profiling':{name:True for name in fields}}
        for name in fields:
            for value in (False,None,'true',1):
                changed=copy.deepcopy(current);changed['evidence']['task_provider_profiling'][name]=value
                with self.subTest(field=name,value=value),self.assertRaisesRegex(RuntimeError,'task provider profiling delivery'):
                    acceptance.validate_completed_report(changed)
        # New instrumented metadata cannot waive old unprofiled shared delivery.
        with self.assertRaisesRegex(RuntimeError,'shared task provider delivery'):
            acceptance.validate_completed_report(current)

    def test_captured_task_artifacts_use_their_checked_command_not_another_cwd(self):
        linkages={'app':{'schema':'nex.project-task-linkage/2','component':'app'},
                  'leaf':{'schema':'nex.project-task-linkage/2','component':'leaf'}}
        def command(cwd,key):
            cwd=Path(cwd).absolute().as_posix()
            return {'exit_code':0,'timed_out':False,'interrupted':0,'output_limit':False,
                'command':['/sdk/nex','project','nex.build.json','--kind','build','--component','app','--json'],
                'elapsed_ns':1,'timeout_seconds':60,'stdout':'logs/build-native/build/stdout','stderr':'logs/build-native/build/stderr',
                'response':{'ok':True,'plan':{'components':[{'name':name,'task_linkage':value} for name,value in linkages.items()]},
                    'artifacts':[{'component':name,'kind':'executable' if name=='app' else 'shared_library',
                        'build_key':key,'artifact':cwd+'/.nex/build/'+key+('/app' if name=='app' else '/libnex_leaf_'+key+'.so')}
                        for name in linkages]}}
        original=acceptance.captured_task_build_artifacts(command('/original-cwd','a'*64),linkages)
        captured_command=command('/capture/workspace','b'*64)
        captured=acceptance.captured_task_build_artifacts(captured_command,linkages)
        self.assertEqual(captured['app']['build_key'],'b'*64)
        self.assertNotEqual(captured['app']['artifact'],original['app']['artifact'])
        native=copy.deepcopy(captured_command)
        for row in native['response']['artifacts']:row['artifact']=str(Path(row['artifact']))
        selected=acceptance.captured_task_build_artifacts(native,linkages)
        self.assertEqual(Path(selected['app']['artifact']),Path(captured['app']['artifact']))
        for mutate in (
            lambda c:c.update(exit_code=70),
            lambda c:c.update(timed_out=True),
            lambda c:c.update(interrupted=15),
            lambda c:c['response']['artifacts'].append(copy.deepcopy(c['response']['artifacts'][0])),
            lambda c:c['response']['artifacts'][0].update(build_key='c'*64),
            lambda c:c['response']['artifacts'][0].update(artifact='relative/app'),
            lambda c:c['response']['artifacts'][0].update(artifact=c['response']['artifacts'][0]['artifact']+'\0'),
            lambda c:c['response']['artifacts'][0].update(component='foreign'),
            lambda c:c['response']['plan']['components'][0]['task_linkage'].update(component='foreign')):
            damaged=copy.deepcopy(captured_command);mutate(damaged)
            with self.subTest(mutate=mutate),self.assertRaises(RuntimeError):
                acceptance.captured_task_build_artifacts(damaged,linkages)
        for field in ('exit_code','interrupted'):
            for value in (False,True,0.0,1.0,-1,15,None,'0'):
                damaged=copy.deepcopy(captured_command);damaged[field]=value
                with self.subTest(field=field,value=value,type=type(value).__name__),self.assertRaises(RuntimeError):
                    acceptance.captured_task_build_artifacts(damaged,linkages)
            damaged=copy.deepcopy(captured_command);del damaged[field]
            with self.subTest(missing=field),self.assertRaises(RuntimeError):
                acceptance.captured_task_build_artifacts(damaged,linkages)
        for field in ('timed_out','output_limit'):
            for value in (0,0.0,True,None,'false'):
                damaged=copy.deepcopy(captured_command);damaged[field]=value
                with self.subTest(field=field,value=value,type=type(value).__name__),self.assertRaises(RuntimeError):
                    acceptance.captured_task_build_artifacts(damaged,linkages)

    def test_profile_retention_binds_measured_command_and_rejects_cross_action_pins(self):
        # Opaque digest labels are compiler-issued pins in this transport test;
        # SHA256 is independent evidence, never a stand-in for BLAKE3 validation.
        with tempfile.TemporaryDirectory(prefix='sdk profile retention ') as temporary:
            root=Path(temporary).resolve();receipt=root/'receipt';receipt.mkdir()
            def fixture(label,digit):
                key=digit*64;original=root/label/'.nex/build'/key;original.mkdir(parents=True)
                app=acceptance.sdk_host.executable_name('app')
                artifact={'component':'app','kind':'executable','build_key':key,'artifact':str(original/app)}
                component={'component':'app','kind':'executable',
                    'retained_build':'artifacts/measure-provider/components/app/retained-build/retained.json'}
                provider={'schema':'nex.native-task-provider/3','component':'app','mode':'static',
                    'profiling':{'catalog_file':'task-profile-catalog.json','catalog_hash':'c'*64}}
                catalog={'schema':'nex.task-profile-catalog/1','registry_abi':1,'mode':'static'}
                inputs=['library-abi.json','task-provider.json','task-profile-catalog.json',
                    'libraries/0.a','libraries/0.task-provider.json','libraries/0.task-profile-catalog.json']
                metadata={'key':key,'compiler_build':'f'*64,'completion_schema':'nex.native-completion/6',
                    'task_provider':provider,'task_provider_hash':digit*64}
                names=[app,'program.mlir','program.ll','compilation.json','build.json','source-bundle.json',
                    *inputs,'complete','debug.json']
                payload={name:(label+':'+name).encode() for name in names}
                leaf={**provider,'component':'leaf'}
                dependency={'hash':digit*64,'task_provider_hash':digit*64,'task_profile_catalog_hash':digit*64,'task_provider':leaf}
                payload.update({'build.json':json.dumps(metadata).encode(),'task-provider.json':json.dumps(provider).encode(),
                    'task-profile-catalog.json':json.dumps(catalog).encode(),
                    'library-abi.json':json.dumps({'static_libraries':[dependency]}).encode(),
                    'libraries/0.task-provider.json':json.dumps(leaf).encode(),
                    'complete':(digit*64+'\n').encode()})
                record={'schema':'nex.retained-native-task-build/3','compiler_build':'f'*64,'build_key':key,
                    'original_directory':str(original),'metadata_rewritten':False,'hash_algorithm':'BLAKE3',
                    'completion_schema':'nex.native-completion/6','files':[]}
                check={'id':'measure-provider','artifacts':{}}
                for name in names:
                    copied=receipt/'artifacts/measure-provider/components/app/retained-build'/name
                    copied.parent.mkdir(parents=True,exist_ok=True);copied.write_bytes(payload[name]);(original/name).parent.mkdir(parents=True,exist_ok=True);(original/name).write_bytes(payload[name])
                    row={'original':str(original)+'/'+name,'retained':copied.relative_to(receipt).as_posix(),
                        'hash':digit*64,'bytes':len(payload[name])};record['files'].append(row)
                    check['artifacts'][copied.relative_to(receipt/'artifacts/measure-provider').as_posix()]={'hash':row['hash'],'bytes':row['bytes']}
                path=receipt/component['retained_build'];path.write_text(json.dumps(record), newline="\n")
                check['artifacts'][path.relative_to(receipt/'artifacts/measure-provider').as_posix()]={'hash':'f'*64,'bytes':path.stat().st_size}
                return artifact,component,check,record,inputs,path
            artifact,component,check,record,inputs,path=fixture('capture','a')
            proof=acceptance.retained_task_profile_build(receipt,check,artifact,component,'f'*64,lambda unused:inputs)
            self.assertEqual(proof['build_key'],'a'*64)
            # A previous build from another CWD cannot authenticate this capture.
            foreign=copy.deepcopy(artifact);foreign.update(build_key='b'*64,artifact=str(root/'other/.nex/build'/('b'*64)/'app'))
            with self.assertRaises(RuntimeError):acceptance.retained_task_profile_build(receipt,check,foreign,component,'f'*64,lambda unused:inputs)
            for mutate in (
                lambda r:r.update(build_key='b'*64),
                lambda r:r['files'][0].update(original=str(root/'foreign/app')),
                lambda r:r['files'][0].update(retained='../escape'),
                lambda r:r['files'][0].update(hash='b'*64),
                lambda r:r['files'][0].update(bytes=True),
                lambda r:r['files'].reverse()):
                damaged=copy.deepcopy(record);mutate(damaged);path.write_text(json.dumps(damaged), newline="\n")
                check['artifacts'][path.relative_to(receipt/'artifacts/measure-provider').as_posix()]['bytes']=path.stat().st_size
                with self.subTest(mutate=mutate),self.assertRaises(RuntimeError):
                    acceptance.retained_task_profile_build(receipt,check,artifact,component,'f'*64,lambda unused:inputs)
            # Even an internally indexed catalog row must match the ABI's
            # static frontier raw catalog pin, in addition to archive/sidecar.
            damaged=copy.deepcopy(record);damaged_check=copy.deepcopy(check)
            catalog_row=next(row for row in damaged['files'] if Path(row['original']).as_posix().endswith('/libraries/0.task-profile-catalog.json'))
            catalog_row['hash']='b'*64
            damaged_check['artifacts'][catalog_row['retained'].split('artifacts/measure-provider/',1)[1]]['hash']='b'*64
            path.write_text(json.dumps(damaged), newline="\n")
            record_key=path.relative_to(receipt/'artifacts/measure-provider').as_posix()
            damaged_check['artifacts'][record_key]['bytes']=path.stat().st_size
            with self.assertRaisesRegex(RuntimeError,'triple pins'):
                acceptance.retained_task_profile_build(receipt,damaged_check,artifact,component,'f'*64,lambda unused:inputs)
            path.write_text(json.dumps(record), newline="\n")
            record_key=path.relative_to(receipt/'artifacts/measure-provider').as_posix()
            check['artifacts'][record_key]['bytes']=path.stat().st_size
            for corrupt in ({'hash':'f'*64,'bytes':True},{'hash':'0','bytes':path.stat().st_size},{}):
                baseline=copy.deepcopy(check);baseline['artifacts'][record_key]=corrupt
                with self.subTest(record_pin=corrupt),self.assertRaises(RuntimeError):
                    acceptance.retained_task_profile_build(receipt,baseline,artifact,component,'f'*64,lambda unused:inputs)
            target=receipt/record['files'][0]['retained'];target.unlink();target.symlink_to(artifact['artifact'])
            with self.assertRaisesRegex(RuntimeError,'symlink'):
                acceptance.retained_task_profile_build(receipt,check,artifact,component,'f'*64,lambda unused:inputs)

    def test_package_task_provenance_binds_own_originals_not_capture_pins(self):
        # Data-only transport fixtures use opaque compiler pins. They deliberately
        # have equal component names and different CWDs/keys/bytes. No synthetic
        # digest in this test is evidence of independent BLAKE3 computation.
        with tempfile.TemporaryDirectory(prefix='sdk package provenance ') as temporary:
            base=Path(temporary)
            def fixture(label,letter):
                project=base/(label+'-cwd');key=letter*64;leaf_key=letter*63+'1'
                original=project/'.nex/build'/key;original.mkdir(parents=True)
                package=base/(label+'-package');package.mkdir()
                runtime_key=letter*63+'2'
                def write_json(path,value):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value)+'\n', newline="\n")
                def image(identity,payload):return {'key':identity,'hash':letter*64,'sha256':hashlib.sha256(payload).hexdigest(),
                    'uuid':letter*32,'runtime_key':runtime_key,'runtime_hash':'f'*64}
                app_image=image(key,(label+'-app-original').encode());leaf_image=image(leaf_key,(label+'-leaf-original').encode())
                def provider(component,kind,identity):return {'schema':'nex.native-task-provider/2','mode':'shared-fixed',
                    'component':component,'owner_image':component,'artifact_kind':kind,'image':identity}
                own=provider('app','application',app_image);leaf=provider('leaf','shared-image',leaf_image)
                write_json(original/'task-provider.json',own)
                image_name='libnex_leaf_'+leaf_key+'.so';sidecar='images/'+image_name+'.task-provider.json'
                write_json(original/sidecar,leaf)
                pin=lambda name:hashlib.sha256((original/name).read_bytes()).hexdigest()
                links={'schema':'nex.native-image-inputs/2','images':[
                    {'kind':'runtime','path':str(original/'images'/('libnex_runtime_'+runtime_key+'.so'))},
                    {'kind':'library','path':str(original/'images'/image_name),**{k:leaf_image[k] for k in ('key','hash','sha256','uuid')}}],
                    'task_providers':[{'image':'images/'+image_name,'path':sidecar,'component':'leaf','hash':pin(sidecar)}]}
                write_json(original/'image-inputs.json',links)
                metadata={'key':key,'completion_schema':'nex.native-completion/5','compiler_build':'c'*64,
                    'task_provider':own,'task_provider_hash':pin('task-provider.json')}
                write_json(original/'build.json',metadata);(original/'complete').write_text(letter*64+'\n', newline="\n")
                result={'build_key':key,'compiler_build':'c'*64,'entry':'bin/app','files':{}}
                for path,data in [('bin/app',(label+'-app-relocated').encode()),('lib/'+image_name,(label+'-leaf-relocated').encode())]:
                    target=package/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
                    result['files'][path]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
                rows=[]
                for index,(kind,name,component,identity,output) in enumerate([
                    ('application_provider','task-provider.json','app',app_image,'bin/app'),
                    ('owned_provider',sidecar,'leaf',leaf_image,'lib/'+image_name),
                    ('image_inputs','image-inputs.json',None,None,None),('build','build.json',None,None,None),
                    ('complete','complete',None,None,None)]):
                    path='provenance/task/%03d-'%index+Path(name).name;raw=(original/name).read_bytes()
                    target=package/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
                    raw_sha=hashlib.sha256(raw).hexdigest();result['files'][path]={'bytes':len(raw),'sha256':raw_sha}
                    rows.append({'kind':kind,'path':path,'input_hash':pin(name),'input_sha256':raw_sha,'bytes':len(raw),
                        'component':component,'input_image_key':None if identity is None else identity['key'],
                        'input_image_sha256':None if identity is None else identity['sha256'],
                        'input_uuid':None if identity is None else identity['uuid'],'output_image':output,
                        'output_image_sha256':None if output is None else result['files'][output]['sha256']})
                result['task_provenance']={'schema':'nex.application-task-provenance/1','metadata_rewritten':False,
                    'hash_algorithm':'BLAKE3','files':rows}
                return project,package,result
            capture_project,capture_package,capture=fixture('capture','a')
            package_project,package_root,packaged=fixture('package','b')
            capture_proof=acceptance.package_task_provenance(capture_package,capture,capture_project)
            proof=acceptance.package_task_provenance(package_root,packaged,package_project)
            self.assertNotEqual(proof['build_key'],capture_proof['build_key'])
            self.assertTrue(all('package-cwd' in Path(row['original']).parts for row in proof['files']))
            with self.assertRaises(RuntimeError):acceptance.package_task_provenance(package_root,packaged,capture_project)
            for mutate in (
                lambda p:p['task_provenance']['files'][0].update(input_hash=capture['task_provenance']['files'][0]['input_hash']),
                lambda p:p['task_provenance']['files'][1].update(input_image_key='a'*64),
                lambda p:p['task_provenance']['files'][0].update(output_image_sha256='0'*64),
                lambda p:p['task_provenance']['files'][0].update(path='../outside'),
                lambda p:p['task_provenance']['files'][3].update(component='app')):
                damaged=copy.deepcopy(packaged);mutate(damaged)
                with self.subTest(mutate=mutate),self.assertRaises(RuntimeError):
                    acceptance.package_task_provenance(package_root,damaged,package_project)

    def test_profile_package_preserves_catalog_image_association_across_action_keys(self):
        with tempfile.TemporaryDirectory(prefix='sdk profile package ') as temporary:
            root=Path(temporary)
            def fixture(label,digit):
                project=root/(label+'-cwd');key=digit*64;original=project/'.nex/build'/key;original.mkdir(parents=True)
                package=root/(label+'-package');package.mkdir()
                executable=acceptance.sdk_host.executable_name('app');entry='bin/'+executable
                original_app=(label+' original app').encode();(original/executable).write_bytes(original_app)
                provider={'schema':'nex.native-task-provider/3','component':'app','mode':'static',
                    'profiling':{'schema':'nex.native-task-profile/1','catalog_hash':digit*64}}
                catalog={'schema':'nex.task-profile-catalog/1','registry_abi':1,'owner_image':'app'}
                (original/'task-provider.json').write_text(json.dumps(provider), newline="\n")
                (original/'task-profile-catalog.json').write_text(json.dumps(catalog), newline="\n")
                # These are opaque matching-compiler BLAKE3 labels. This fixture
                # independently hashes bytes with SHA256 only for transport.
                pin=lambda name:hashlib.sha256((original/name).read_bytes()).hexdigest()
                metadata={'key':key,'compiler_build':'f'*64,'profile':'profile','completion_schema':'nex.native-completion/6',
                    'completion_mode':'static-application','task_provider':provider,'task_provider_hash':pin('task-provider.json')}
                (original/'build.json').write_text(json.dumps(metadata), newline="\n");(original/'complete').write_text(digit*64+'\n', newline="\n")
                output=package/entry;output.parent.mkdir();output.write_bytes((label+' relocated app').encode())
                output_sha=hashlib.sha256(output.read_bytes()).hexdigest()
                meta={'build_key':key,'compiler_build':'f'*64,'entry':entry,
                    'files':{entry:{'sha256':output_sha,'bytes':output.stat().st_size}}}
                rows=[]
                for index,(kind,name) in enumerate([('application_provider','task-provider.json'),
                        ('application_profile_catalog','task-profile-catalog.json'),('build','build.json'),('complete','complete')]):
                    raw=(original/name).read_bytes();path='provenance/task/%03d-'%index+name
                    target=package/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
                    sha=hashlib.sha256(raw).hexdigest();meta['files'][path]={'sha256':sha,'bytes':len(raw)}
                    associated=index<2
                    rows.append({'kind':kind,'path':path,'input_hash':pin(name),'input_sha256':sha,'bytes':len(raw),
                        'component':'app' if associated else None,'input_image_key':key if associated else None,
                        'input_image_sha256':hashlib.sha256(original_app).hexdigest() if associated else None,
                        'input_uuid':digit*32 if associated else None,'output_image':entry if associated else None,
                        'output_image_sha256':output_sha if associated else None})
                meta['task_profile_provenance']={'schema':'nex.application-task-profile-provenance/1',
                    'metadata_rewritten':False,'hash_algorithm':'BLAKE3','files':rows}
                return project,package,meta
            capture,capture_package,captured=fixture('capture','a')
            project,package,meta=fixture('package','b')
            first=acceptance.package_task_profile_provenance(capture_package,captured,capture)
            proof=acceptance.package_task_profile_provenance(package,meta,project)
            self.assertNotEqual(first['build_key'],proof['build_key'])
            self.assertTrue(all('package-cwd' in Path(row['original']).parts for row in proof['files']))
            with self.assertRaises(RuntimeError):acceptance.package_task_profile_provenance(package,meta,capture)
            for mutate in (
                lambda p:p['task_profile_provenance']['files'][0].update(input_hash=captured['task_profile_provenance']['files'][0]['input_hash']),
                lambda p:p['task_profile_provenance']['files'][1].update(input_image_key='a'*64),
                lambda p:p['task_profile_provenance']['files'][1].update(component='foreign'),
                lambda p:p['task_profile_provenance']['files'][1].update(output_image_sha256='0'*64),
                lambda p:p['task_profile_provenance']['files'][1].update(bytes=True),
                lambda p:p['task_profile_provenance']['files'].reverse(),
                lambda p:p['task_profile_provenance']['files'][2].update(component='app'),
                lambda p:p['task_profile_provenance']['files'][0].update(path='../escape')):
                damaged=copy.deepcopy(meta);mutate(damaged)
                with self.subTest(mutate=mutate),self.assertRaises(RuntimeError):
                    acceptance.package_task_profile_provenance(package,damaged,project)

    def test_task_debug_sdk_requires_actual_delivery_and_live_execution(self):
        current = self.report(); current['doctor'] = {'version':'0.115.0'}
        fields = ('descriptor', 'actual_image_identity', 'source_deleted_archive',
                  'source_only_project', 'standalone_without_resources')
        with self.assertRaisesRegex(RuntimeError, 'task debugger delivery'):
            acceptance.validate_completed_report(current)
        current['evidence'] = {'structured_task_debug':{name:True for name in fields}}
        for name in fields:
            for value in (False, None, 'true'):
                changed=copy.deepcopy(current);changed['evidence']['structured_task_debug'][name]=value
                with self.subTest(delivery=name,value=value), self.assertRaisesRegex(RuntimeError, 'task debugger delivery'):
                    acceptance.validate_completed_report(changed)
        current['evidence']['live_debugger']=True
        with self.assertRaisesRegex(RuntimeError, 'task debugger execution'):
            acceptance.validate_completed_report(current)
        live=('logical_stack','initialized_locals','pure_watch','logical_step','stale_references_rejected','graceful_exit')
        current['evidence']['structured_task_debug'].update({name:True for name in live})
        for name in live:
            for value in (False, None, 'true'):
                changed=copy.deepcopy(current);changed['evidence']['structured_task_debug'][name]=value
                with self.subTest(execution=name,value=value), self.assertRaisesRegex(RuntimeError, 'task debugger execution'):
                    acceptance.validate_completed_report(changed)
        # Debugger delivery cannot waive profiling/read/migration checks.
        with self.assertRaisesRegex(RuntimeError, 'task profile delivery'):
            acceptance.validate_completed_report(current)

    def test_task_profile_sdk_requires_measured_and_source_deleted_delivery(self):
        current = self.report(); current['doctor'] = {'version': '0.114.0'}
        fields = ('native_reference', 'exact_source_calls', 'managed_cleanup',
                  'event_only_truncation', 'archived_source_deleted',
                  'standalone_without_resources', 'source_only_project', 'source_deleted_replay')
        with self.assertRaisesRegex(RuntimeError, 'task profile delivery'):
            acceptance.validate_completed_report(current)
        current['evidence'] = {'structured_task_profile': {name: True for name in fields}}
        for name in fields:
            for value in (False, None, 'true'):
                changed = copy.deepcopy(current)
                changed['evidence']['structured_task_profile'][name] = value
                with self.subTest(delivery=name, value=value), self.assertRaisesRegex(RuntimeError, 'task profile delivery'):
                    acceptance.validate_completed_report(changed)
        # Profile evidence does not waive existing file-read/migration gates.
        with self.assertRaisesRegex(RuntimeError, 'public task file-read delivery'):
            acceptance.validate_completed_report(current)

    def test_public_task_read_sdk_requires_delivery_and_genuine019_migration_evidence(self):
        current = self.report(); current['doctor'] = {'version':'0.110.0'}
        with self.assertRaisesRegex(RuntimeError, 'public task file-read delivery'):
            acceptance.validate_completed_report(current)
        fields = ('native_reference', 'standalone_without_resources', 'source_only_project',
                  'source_deleted_package', 'source_deleted_replay')
        current['evidence'] = {'structured_task_file_reads':{name:True for name in fields}}
        with self.assertRaisesRegex(RuntimeError, 'genuine019 migration'):
            acceptance.validate_completed_report(current)
        current['evidence']['task_file_migration'] = {'ok':True,'genuine019':True,'history_preserved':True}
        for name in fields:
            changed = copy.deepcopy(current); changed['evidence']['structured_task_file_reads'][name] = False
            with self.subTest(delivery=name), self.assertRaisesRegex(RuntimeError, 'public task file-read delivery'):
                acceptance.validate_completed_report(changed)
        for name in ('ok', 'genuine019', 'history_preserved'):
            changed = copy.deepcopy(current); changed['evidence']['task_file_migration'][name] = False
            with self.subTest(migration=name), self.assertRaisesRegex(RuntimeError, 'genuine019 migration'):
                acceptance.validate_completed_report(changed)
        # New public evidence never waives the pre-existing delivery gates.
        with self.assertRaisesRegex(RuntimeError, 'ordered CPU mapping'):
            acceptance.validate_completed_report(current)

    def test_failed_duplicate_reordered_and_incomplete_workflows_are_rejected(self):
        cases=[]
        changed=self.report();changed['ok']=False;cases.append(changed)
        changed=self.report();changed['schema']='other';cases.append(changed)
        changed=self.report();changed['phases'][1]=dict(changed['phases'][0]);cases.append(changed)
        changed=self.report();changed['phases'].reverse();cases.append(changed)
        changed=self.report();changed['phases'][-1]['status']='running';cases.append(changed)
        changed=self.report();changed['commands'][0]['status']='failed';cases.append(changed)
        changed=self.report();changed['commands']=[];cases.append(changed)
        for changed in cases:
            with self.subTest(report=changed), self.assertRaises(RuntimeError):acceptance.validate_completed_report(changed)

    def test_current_capsule_sdk_requires_installed_helper_and_actual_live_relocation(self):
        current = self.report();current['doctor'] = {'version': '0.59.0'}
        with self.assertRaisesRegex(RuntimeError, 'capsule helper'):acceptance.validate_completed_report(current)
        current['evidence'] = {'core_reports': {'capsule_helper_input_rejected': True}}
        acceptance.validate_completed_report(current)
        current['evidence']['live_debugger'] = True
        with self.assertRaisesRegex(RuntimeError, 'moved core capsule'):acceptance.validate_completed_report(current)
        core = current['evidence']['core_reports']
        core.update(actual_capsule_read=True, original_executable_absent=True,
                    capsule_report={'capsule': {'inventory_checked': True},
                                    'watch': {'value': 'Я🧠2'}, 'inferior_execution': False})
        acceptance.validate_completed_report(current)
        for key in ('actual_capsule_read', 'original_executable_absent'):
            changed = copy.deepcopy(current);changed['evidence']['core_reports'][key] = False
            with self.subTest(field=key), self.assertRaises(RuntimeError):acceptance.validate_completed_report(changed)


    def test_current_wasm_sdk_requires_independent_checked_compute_evidence(self):
        current=self.report();current['doctor']={'version':'0.60.0'}
        current['evidence']={'core_reports':{'capsule_helper_input_rejected':True}}
        with self.assertRaisesRegex(RuntimeError,'scalar Wasm evidence'):acceptance.validate_completed_report(current)
        fields=('exact_bigint','checked_overflow','input_rejection','resource_stop','post_trap_recovery',
                'module_integrity','source_deleted','independent_runtime','cache_integrity','server_exclusion')
        current['evidence']['wasm_compute']={name:True for name in fields}
        acceptance.validate_completed_report(current)
        for name in fields:
            changed=copy.deepcopy(current);changed['evidence']['wasm_compute'][name]=False
            with self.subTest(field=name),self.assertRaises(RuntimeError):acceptance.validate_completed_report(changed)


ENTRY = 'bin/nex.exe' if os.name == 'nt' else 'bin/nex'

class Archives(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='nex archive, % 🧠 ')
        self.root = Path(self.temp.name)
        self.sdk = self.root/'SDK'
        for name, value in [(ENTRY, b'owned executable'), ('include/header.h', b'owned header'),
                            ('notes, 🧠.txt', b'UTF-8 paths')]:
            path = self.sdk/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(value)
            path.chmod(0o755 if name == ENTRY else 0o644)
        (self.sdk/'bin/compiler').symlink_to(Path(ENTRY).name)
        self.manifest = {'schema': 'nex.sdk-bundle/1', 'ok': True, 'acceptance_passed': False,
                         'toolchain': '0.33.0', 'language': '0.14', 'platform': 'macos', 'files': {}}
        for path in self.sdk.rglob('*'):
            if path.is_file() or path.is_symlink():
                name = path.relative_to(self.sdk).as_posix()
                self.manifest['files'][name] = ({'symlink': path.readlink().as_posix()} if path.is_symlink() else
                    {'sha256': archive.digest(path), 'bytes': path.stat().st_size,
                     'executable': bool(path.stat().st_mode & 0o111)})
        self.save()

    def tearDown(self):
        self.temp.cleanup()

    def save(self, value=None):
        path = self.sdk/archive.MANIFEST; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.manifest if value is None else value, ensure_ascii=False), newline="\n")

    def test_inventory_roundtrip_ignores_only_regular_python_caches(self):
        cache = self.sdk/'tools/__pycache__/module.cpython-39.pyc'
        cache.parent.mkdir(parents=True); cache.write_bytes(b'not a distribution input')
        result = archive.create(self.sdk, self.root/'sdk.tar.gz', 'nex-sdk-test')
        self.assertEqual(result['excluded_python_cache_files'], [cache.relative_to(self.sdk).as_posix()])
        restored = archive.restore(result['path'], self.root/'restored', result['sha256'])
        self.assertEqual((restored/ENTRY).read_bytes(), b'owned executable')
        self.assertEqual((restored/'notes, 🧠.txt').read_bytes(), b'UTF-8 paths')
        self.assertEqual(str((restored/'bin/compiler').readlink()), Path(ENTRY).name)
        self.assertFalse((restored/'tools/__pycache__').exists())
        self.assertEqual(archive.inventory(restored)[0], self.manifest)
        (self.sdk/'unexpected').write_text('must not ship', newline="\n")
        with self.assertRaisesRegex(ValueError, 'unmanifested'):
            archive.inventory(self.sdk)

    def test_normalized_archive_is_identical_after_mtime_changes(self):
        first = archive.create(self.sdk, self.root/'first.tar.gz', 'nex-sdk-test')
        for path in self.sdk.rglob('*'):
            if not path.is_symlink(): os.utime(path, (123456789, 123456789))
        second = archive.create(self.sdk, self.root/'second.tar.gz', 'nex-sdk-test')
        self.assertEqual(first['sha256'], second['sha256'])
        with tarfile.open(first['path']) as package:
            for item in package:
                self.assertEqual((item.uid, item.gid, item.mtime, item.uname, item.gname), (0, 0, 0, '', ''))
                self.assertFalse(item.mode & 0o7000)

    def test_hash_modes_sizes_and_duplicate_manifest_keys_fail(self):
        for key, value in [('sha256', '0'*64), ('bytes', 1), ('executable', False), ('bytes', True)]:
            manifest = copy.deepcopy(self.manifest); manifest['files'][ENTRY][key] = value; self.save(manifest)
            with self.subTest(key=key, value=value), self.assertRaises(ValueError): archive.inventory(self.sdk)
        self.save()
        path = self.sdk/archive.MANIFEST
        path.write_text(path.read_text().replace('"ok": true', '"ok": false, "ok": true'), newline="\n")
        with self.assertRaisesRegex(ValueError, 'duplicate'): archive.inventory(self.sdk)

    def test_paths_privilege_bits_and_links_cannot_escape_inventory(self):
        for name in ['../outside', '/outside', 'bin/./nex', 'bin//nex', 'bin\\nex']:
            manifest = copy.deepcopy(self.manifest); manifest['files'][name] = manifest['files'].pop(ENTRY); self.save(manifest)
            with self.subTest(name=name), self.assertRaises(ValueError): archive.inventory(self.sdk)
        self.save()
        path = self.sdk/ENTRY; path.chmod(0o4755)
        # Some temporary filesystems discard setuid on chmod. The tar test
        # below checks privileged metadata independently of that host policy.
        if path.stat().st_mode & 0o4000:
            with self.assertRaisesRegex(ValueError, 'privilege'): archive.inventory(self.sdk)
        path.chmod(0o755)
        alias = self.sdk/'bin/compiler'; alias.unlink(); alias.symlink_to('../../outside')
        manifest = copy.deepcopy(self.manifest); manifest['files']['bin/compiler']['symlink'] = '../../outside'; self.save(manifest)
        with self.assertRaises(ValueError): archive.inventory(self.sdk)

    def test_manifest_symlink_ancestor_is_rejected_before_read(self):
        (self.sdk/archive.MANIFEST).unlink(); (self.sdk/'share/nex').rmdir(); (self.sdk/'share').rmdir()
        (self.sdk/'share').symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'manifest has a symlink ancestor'):
            archive.inventory(self.sdk)

    def malicious(self, rows):
        path = self.root/'malicious.tar.gz'
        with tarfile.open(path, 'w:gz') as package:
            for name, kind, target in rows:
                item = tarfile.TarInfo(name); item.type = kind
                if kind == tarfile.SYMTYPE: item.linkname = target
                data = b'{}' if kind == tarfile.REGTYPE else b''
                item.size = len(data); package.addfile(item, io.BytesIO(data) if data else None)
        return path

    def test_archive_structural_attacks_fail_before_destination_creation(self):
        baseline = [('SDK', tarfile.DIRTYPE, ''), ('SDK/share', tarfile.DIRTYPE, ''),
                    ('SDK/share/nex', tarfile.DIRTYPE, ''), ('SDK/'+archive.MANIFEST, tarfile.REGTYPE, '')]
        attacks = [[('../outside', tarfile.REGTYPE, '')], [('/outside', tarfile.REGTYPE, '')],
                   [('SDK/link', tarfile.SYMTYPE, '../../outside')],
                   [('SDK/share', tarfile.REGTYPE, '')], [('SDK/hard', tarfile.LNKTYPE, '')],
                   [('SDK/link', tarfile.SYMTYPE, 'share'), ('SDK/link/payload', tarfile.REGTYPE, '')],
                   [('SDK/a', tarfile.SYMTYPE, 'b'), ('SDK/b', tarfile.SYMTYPE, 'a')],
                   [('SDK/link', tarfile.SYMTYPE, 'missing')]]
        for index, extra in enumerate(attacks):
            path = self.malicious(baseline+extra); destination = self.root/('extract-'+str(index))
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                archive.restore(path, destination, archive.digest(path))
            self.assertFalse(destination.exists())
            self.assertFalse((self.root/'outside').exists())

    def test_archive_checksum_and_existing_destinations_are_preserved(self):
        result = archive.create(self.sdk, self.root/'sdk.tar.gz', 'SDK')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            archive.restore(result['path'], self.root/'new', '0'*64)
        destination = self.root/'existing'; destination.mkdir(); (destination/'keep').write_text('keep', newline="\n")
        with self.assertRaisesRegex(ValueError, 'must be new'):
            archive.restore(result['path'], destination, result['sha256'])
        self.assertEqual((destination/'keep').read_text(), 'keep')
        with self.assertRaises(FileExistsError): archive.create(self.sdk, self.root/'sdk.tar.gz', 'SDK')

    def test_privileged_archive_header_is_rejected_before_extraction(self):
        original = archive.create(self.sdk, self.root/'sdk.tar.gz', 'SDK')
        changed = self.root/'privileged.tar.gz'
        with tarfile.open(original['path']) as source, tarfile.open(changed, 'w:gz') as output:
            for item in source:
                data = source.extractfile(item) if item.isfile() else None
                if item.name == 'SDK/'+ENTRY: item.mode |= 0o4000
                output.addfile(item, data)
        with self.assertRaisesRegex(ValueError, 'unsafe SDK archive metadata'):
            archive.restore(changed, self.root/'restored', archive.digest(changed))
        self.assertFalse((self.root/'restored').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
