"""Separate native compilation checked against real compiler calls and behavior."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

LIVE = "--live" in sys.argv
if LIVE: sys.argv.remove("--live")

import support as harness


class Incremental(harness.ToolchainCase):
    def setUp(self):
        super().setUp()
        self.left = self.root / 'left.nex'
        self.right = self.root / 'right.nex'
        self.left.write_text('module inc::left; pub fn value(n: i64) -> i64 { return n + 1; }')
        self.right.write_text('module inc::right; pub fn value(n: i64) -> i64 { return n + 10; }')
        self.source('''module inc::app;
import "./left.nex" as left;
import "./right.nex" as right;
fn main() -> unit !{io} { print(left::value(5)); print(right::value(5)); }
test fn smoke() -> unit !{io} { assert(len(str(left::value(5))) > 0); assert(right::value(5) == 15); }
''')
        self.log = self.root / 'compiler-log.jsonl'
        self.identity = self.root / 'compiler-identity.txt'
        self.identity.write_text('')
        self.fake_target = self.root / 'compiler-target.txt'
        real = self.cli('doctor')['native_compiler']
        self.wrapper = self.root / 'compiler spy'
        self.wrapper.write_text('''#!/usr/bin/env python3
import json, os, pathlib, re, sys
entry = {"arguments": sys.argv[1:], "definitions": []}
if "-c" in sys.argv:
    for argument in sys.argv[1:]:
        if argument.endswith(".ll"):
            entry["definitions"] = re.findall(r"^define[^\\n]*?@([^ (]+)", pathlib.Path(argument).read_text(), re.M)
with open(LOG, "a") as output: output.write(json.dumps(entry) + "\\n")
if "-emit-llvm" in sys.argv and pathlib.Path(TARGET).is_file():
    print('target triple = "' + pathlib.Path(TARGET).read_text() + '"')
    sys.exit(0)
if "--version" in sys.argv and pathlib.Path(IDENTITY).read_text():
    print(pathlib.Path(IDENTITY).read_text(), flush=True)
os.execv(REAL, [REAL, *sys.argv[1:]])
'''.replace('LOG', repr(str(self.log))).replace('IDENTITY', repr(str(self.identity))).replace('TARGET', repr(str(self.fake_target))).replace('REAL', repr(real)))
        self.wrapper.chmod(0o755)
        self.env = {'NEX_CLANG': str(self.wrapper)}

    def build(self, *arguments, **options):
        self.log.write_text('')
        result = self.cli('build', *arguments, env={**self.env, **options.pop('env', {})}, **options)
        calls = [json.loads(line) for line in self.log.read_text().splitlines()]
        native = [call for call in calls if '-c' in call['arguments'] and any(a.endswith('.ll') for a in call['arguments'])]
        self.assertEqual(len(native), result['compiled_functions'], calls)
        self.last_compiled = [name for call in native for name in call['definitions'] if name.startswith('nex_')]
        return result, json.loads(Path(result['compilation']).read_text())

    def assert_behavior(self, built, expected):
        process = subprocess.run([built['executable']], capture_output=True, text=True, timeout=10)
        self.assertEqual((process.returncode, process.stdout), (0, expected), process.stderr)
        self.assertEqual(self.cli('eval')['stdout'], expected)

    def test_body_edits_reuse_independent_modules_and_match_clean_build(self):
        first, report = self.build()
        self.assertEqual((first['compiled_modules'], first['reused_modules']), (3, 0))
        self.assert_behavior(first, '6\n15\n')
        warm, _ = self.build()
        self.assertTrue(warm['cached'])
        self.assertEqual((warm['compiled_modules'], warm['reused_modules']), (0, 3))
        before = {u['module']: u['input_key'] for u in report['units']}
        self.left.write_text(self.left.read_text().replace('n + 1;', 'n + 2;'))
        changed, report = self.build()
        self.assertEqual((changed['compiled_modules'], changed['reused_modules']), (1, 2))
        self.assertEqual(self.last_compiled, ['nex_3_inc_4_left_5_value'])
        after = {u['module']: u['input_key'] for u in report['units']}
        self.assertEqual(before['inc::app'], after['inc::app'])
        self.assertEqual(before['inc::right'], after['inc::right'])
        self.assertNotEqual(before['inc::left'], after['inc::left'])
        self.assert_behavior(changed, '7\n15\n')
        self.cli('test', env=self.env)
        self.cli('test', '--target', 'web')
        clean = self.root / 'clean'
        clean.mkdir()
        for path in (self.file, self.left, self.right): shutil.copyfile(path, clean / path.name)
        fresh, _ = self.build(cwd=clean)
        self.assertEqual((fresh['compiled_modules'], fresh['reused_modules']), (3, 0))
        self.assert_behavior(fresh, '7\n15\n')

    def test_same_file_body_edits_reuse_function_objects_and_keep_exact_sources(self):
        self.source('module single;\nfn first(x:f64)->f64{return x+1e0;}\nfn stable(x:f64)->f64{return x*2e0;}\nfn main()->unit!{io}{print(first(2e0));print(stable(3e0));}\n')
        first, before = self.build()
        self.assertEqual(before['granularity'], 'function')
        self.assertEqual((first['compiled_modules'],first['compiled_functions']), (1,3))
        self.assert_behavior(first, '3e0\n6e0\n')
        old_manifest=json.loads(Path(first['debug_manifest']).read_text())
        old_source=Path(old_manifest['sources'][0]['projection'])
        original=old_source.read_text()
        warm,_=self.build()
        self.assertTrue(warm['cached'])
        self.assertEqual((warm['compiled_functions'],warm['reused_functions']), (0,3))
        # The extra byte changes later absolute offsets, but no emitted line/column.
        self.source(self.file.read_text().replace('x+1e0','x+10e0'))
        changed,after=self.build()
        self.assertEqual((changed['compiled_functions'],changed['reused_functions']), (1,2))
        self.assertEqual((changed['compiled_modules'],changed['reused_modules']), (1,0))
        self.assertEqual(self.last_compiled,['nex_6_single_5_first'])
        self.assert_behavior(changed,'1.2e1\n6e0\n')
        keys=lambda report:{u['identity']:u['input_key'] for u in report['units']}
        a,b=keys(before),keys(after)
        self.assertEqual(a['single::stable'],b['single::stable'])
        self.assertEqual(a['single::main'],b['single::main'])
        new_manifest=json.loads(Path(changed['debug_manifest']).read_text())
        self.assertEqual(old_manifest['source_map'][0][0],new_manifest['source_map'][0][0])
        self.assertNotEqual(old_manifest['source_map'][0][1],new_manifest['source_map'][0][1])
        self.assertEqual(old_source.read_text(),original)
        self.assertEqual(Path(new_manifest['sources'][0]['projection']).read_text(),self.file.read_text())
        # Actual source coordinates are inputs even when canonical code is equal.
        self.source(self.file.read_text().replace('\nfn stable','\n\nfn stable'))
        moved,_=self.build()
        self.assertEqual((moved['compiled_functions'],moved['reused_functions']), (2,1))
        self.assert_behavior(moved,'1.2e1\n6e0\n')
        self.assertEqual(self.cli('run','--revision',first['revision'])['stdout'],'3e0\n6e0\n')
        self.file.unlink()
        archived,_=self.build('--revision',first['revision'])
        self.assertEqual((archived['compiled_functions'],archived['reused_functions']), (0,3))
        self.assertEqual(subprocess.check_output([archived['executable']],text=True),'3e0\n6e0\n')

    def test_same_file_callee_contract_and_invalid_unused_body_cannot_hide_in_cache(self):
        self.source('module contracts;\nfn first()->i64{return 1;}\nfn stable()->i64{return 7;}\nfn main()->unit!{io}{print(first());print(stable());}\n')
        self.build()
        self.source(self.file.read_text().replace('first()->i64{return 1;}','first()->bool{return true;}'))
        changed,_=self.build()
        self.assertEqual((changed['compiled_functions'],changed['reused_functions']), (2,1))
        self.assert_behavior(changed,'true\n7\n')
        head=self.cli('history')['head']
        self.source(self.file.read_text()+'fn invalid()->f64{return "wrong";}')
        self.assertEqual(self.cli('build',ok=False)['code'],'E_TYPE')
        self.assertEqual(self.cli('history')['head'],head)

    def test_cached_libraries_and_tests_cannot_bypass_application_entry_rules(self):
        self.source('''module entrances;
fn with_arg(value:i64)->i64{return value+1;}
fn text()->str{return "NEX";}
client fn ui()->unit{}
fn generic<T>(value:T)->T{return value;}
fn main()->unit!{io}{print(with_arg(1));}
test fn scenario()->unit{assert(with_arg(1)==2);}
''')
        self.build()
        self.assertTrue(self.build()[0]['cached'])
        for name in ['with_arg','text']:
            self.cli('build','--entry',name,'--library',env=self.env)
            self.assertTrue(self.cli('build','--entry',name,'--library',env=self.env)['cached'])
        self.cli('test','--symbol','scenario',env=self.env)
        for name,code in [('with_arg','E_ENTRY'),('text','E_ENTRY'),('ui','E_REALM'),
                          ('generic','E_GENERIC_ENTRY'),('scenario','E_ENTRY')]:
            with self.subTest(entry=name):
                self.log.write_text('')
                rejected=self.cli('build','--entry',name,env=self.env,ok=False)
                self.assertEqual(rejected['code'],code)
                calls=[json.loads(line) for line in self.log.read_text().splitlines()]
                self.assertFalse(any('-c' in call['arguments'] for call in calls),calls)
        valid,_=self.build()
        self.assertTrue(valid['cached'])
        self.assert_behavior(valid,'2\n')

    def test_sibling_edit_reuses_generic_instances_and_snapshot_closure_objects(self):
        self.source('module callbacks;\nfn first()->i64{return 1;}\nfn identity<T>(value:T)->T{return value;}\nfn make(offset:i64)->(fn(i64)->i64){return fn(value:i64)->i64{return value+offset;};}\nfn main()->unit!{io}{print(first());print(identity(42));print(identity("ok"));print(make(2)(3));}\n')
        initial,before=self.build()
        self.source(self.file.read_text().replace('return 1;','return 100;'))
        updated,after=self.build()
        self.assertEqual(updated['compiled_functions'],1)
        self.assertEqual(updated['reused_functions'],initial['compiled_functions']-1)
        self.assertEqual(self.last_compiled,['nex_9_callbacks_5_first'])
        self.assert_behavior(updated,'100\n42\nok\n5\n')
        for unit in after['units']:
            if unit['identity']!='callbacks::first': self.assertTrue(unit['reused'],unit['identity'])

    def test_interface_effect_changes_invalidate_unchanged_consumers(self):
        self.left.write_text('module inc::left; pub fn value(n: i64) -> i64 { return n + 1; }')
        first, before = self.build()
        original = self.file.read_bytes()
        self.left.write_text('module inc::left; pub fn value(n: i64) -> i64 !{io} { print(99); return n + 1; }')
        changed, after = self.build()
        self.assertEqual(self.file.read_bytes(), original)
        self.assertEqual((changed['compiled_modules'], changed['reused_modules']), (2, 1))
        self.assertIn('nex_3_inc_3_app_4_main', self.last_compiled)
        self.assertNotIn('nex_3_inc_5_right_5_value', self.last_compiled)
        self.assert_behavior(changed, '99\n6\n15\n')
        functions = {f['name']: f for f in after['dependencies']['functions']}
        self.assertEqual(functions['inc::left::value']['callers'], ['inc::app::main'])
        units = {u['unit']: u for u in after['dependencies']['units']}
        self.assertIn('main.nex', units['left.nex']['consumers'])
        self.left.write_text('module inc::left; pub fn value(n: i64) -> bool { return n > 0; }')
        typed, _ = self.build()
        self.assertEqual(self.file.read_bytes(), original)
        self.assertEqual((typed['compiled_modules'], typed['reused_modules']), (2, 1))
        self.assert_behavior(typed, 'true\n15\n')
        self.cli('test', '--target', 'web')
        # Rejected signatures are checked even with a previously warm cache.
        self.left.write_text('module inc::left; pub fn value(n: bool) -> i64 { return 1; }')
        self.assertEqual(self.cli('build', env=self.env, ok=False)['code'], 'E_TYPE')

    def test_parameter_rename_does_not_invalidate_callers(self):
        self.build()
        self.left.write_text('module inc::left; pub fn value(argument: i64) -> i64 { return argument + 1; }')
        changed, _ = self.build()
        self.assertEqual((changed['compiled_modules'], changed['reused_modules']), (1, 2))
        self.assert_behavior(changed, '6\n15\n')

    def test_nested_record_layout_and_wire_schema_dependencies(self):
        models = self.root / 'models.nex'
        models.write_text('''module inc::models;
pub struct Pair { left: i64; right: i64; }
pub struct Envelope { pairs: list<Pair>; }
''')
        self.left.write_text('''module inc::left;
import "./models.nex" as model;
pub fn value(n: i64) -> str {
  let pair: model::Pair = model::Pair(2, 9);
  let envelope: model::Envelope = model::Envelope([pair]);
  let parsed: result<model::Envelope> = decode_json<model::Envelope>(encode_json(envelope));
  assert(is_ok(parsed));
  return str(pair.left) + ":" + encode_json(unwrap(parsed));
}
''')
        first, _ = self.build()
        self.assert_behavior(first, '2:{"pairs":[{"left":"2","right":"9"}]}\n15\n')
        models.write_text(models.read_text().replace('left: i64; right: i64;', 'right: i64; left: i64;'))
        changed, report = self.build()
        self.assertEqual((changed['compiled_modules'], changed['reused_modules']), (1, 2))
        self.assertEqual(self.last_compiled, ['nex_3_inc_4_left_5_value'])
        self.assert_behavior(changed, '9:{"pairs":[{"right":"2","left":"9"}]}\n15\n')
        provider = next(u for u in report['dependencies']['units'] if u['unit'] == 'models.nex')
        self.assertFalse(provider['emitted'])
        self.assertEqual(provider['consumers'], ['left.nex'])
        self.cli('test', '--target', 'web')

    def test_profiles_compiler_identity_and_runtime_inputs(self):
        self.build()
        for profile in ('release', 'profile'):
            built, _ = self.build('--profile', profile)
            self.assertEqual((built['compiled_modules'], built['reused_modules']), (3, 0))
            self.assert_behavior(built, '6\n15\n')
        warm, _ = self.build()
        self.assertEqual(warm['compiled_modules'], 0)
        self.identity.write_text('NEX test compiler identity 2')
        changed, _ = self.build()
        self.assertEqual((changed['compiled_modules'], changed['reused_modules']), (3, 0))
        resources = self.root / 'resources'
        for directory in ('runtime', 'debug', 'lib'): shutil.copytree(harness.REPO / directory, resources / directory)
        (resources / 'runtime/runtime.cpp').write_text((resources / 'runtime/runtime.cpp').read_text() + '\n// changed matching runtime input\n')
        changed, _ = self.build(env={'NEX_RESOURCE_DIR': str(resources)})
        self.assertEqual((changed['compiled_modules'], changed['reused_modules']), (3, 0))
        self.assert_behavior(changed, '6\n15\n')
        self.assertEqual(self.cli('build', '--target', 'unsupported-triple', env=self.env, ok=False)['code'], 'E_TARGET')
        self.fake_target.write_text('wasm32-unknown-unknown')
        self.assertEqual(self.cli('build', env=self.env, ok=False)['code'], 'E_TARGET')

    def test_pinned_library_body_updates_and_archived_reuse(self):
        package = self.root / 'package'
        package.mkdir()
        library = package / 'numbers.nex'
        library.write_text('module inc::numbers; pub fn add(n: i64) -> i64 { return n + 1; }')
        (self.root / 'nex.json').write_text(json.dumps({'language': '0.23', 'entry': 'main.nex', 'libraries': {'numbers': 'package'}}))
        self.left.write_text('module inc::left; import "numbers/numbers.nex" as numbers; pub fn value(n: i64) -> i64 { return numbers::add(n); }')
        self.cli('lock')
        first, _ = self.build()
        revision = first['revision']
        library.write_text(library.read_text().replace('n + 1;', 'n + 3;'))
        self.assertEqual(self.cli('build', env=self.env, ok=False)['code'], 'E_LOCK')
        self.cli('lock')
        changed, _ = self.build()
        self.assertEqual((changed['compiled_modules'], changed['reused_modules']), (1, 3))
        self.assertEqual(self.last_compiled, ['nex_3_inc_7_numbers_3_add'])
        self.assert_behavior(changed, '8\n15\n')
        shutil.rmtree(Path(first['executable']).parent)
        for path in (self.file, self.left, self.right, library): path.unlink()
        archived, _ = self.build('--revision', revision)
        self.assertEqual((archived['compiled_modules'], archived['reused_modules']), (0, 4))
        process = subprocess.run([archived['executable']], capture_output=True, text=True, timeout=10)
        self.assertEqual((process.returncode, process.stdout), (0, '6\n15\n'))

    def test_corruption_repairs_only_needed_objects_and_build_artifacts(self):
        first, report = self.build()
        left = next(u for u in report['units'] if u['module'] == 'inc::left')
        cache = Path(left['cache_record']).parent.parent
        object_file = cache / 'native-objects' / left['artifact_key'] / 'program.o'
        object_file.write_bytes(object_file.read_bytes() + b'corruption')
        restored, report = self.build()
        self.assertFalse(restored['cached'])
        self.assertEqual((restored['compiled_modules'], restored['reused_modules']), (1, 2))
        self.assert_behavior(restored, '6\n15\n')
        left = next(u for u in report['units'] if u['module'] == 'inc::left')
        Path(left['cache_record']).write_text('{"invalid":true}')
        restored, report = self.build()
        self.assertEqual((restored['compiled_modules'], restored['reused_modules']), (1, 2))
        Path(report['units'][0]['object']).write_bytes(b'bad local object')
        restored, _ = self.build()
        self.assertEqual((restored['compiled_modules'], restored['reused_modules']), (0, 3))
        Path(restored['llvm']).write_text('bad aggregate LLVM')
        restored, _ = self.build()
        self.assertFalse(restored['cached'])
        self.assertEqual((restored['compiled_modules'], restored['reused_modules']), (0, 3))
        self.assertIn('define', Path(restored['llvm']).read_text())
        self.assert_behavior(restored, '6\n15\n')

    def test_concurrent_builds_share_verified_units_with_unicode_paths(self):
        common_dir = self.root / 'lib Юникод%'
        common_dir.mkdir()
        (common_dir / 'common.nex').write_text('module inc::common; pub fn add(n: i64) -> i64 { return n + 5; }')
        revisions = []
        for name, number in (('one', 1), ('two', 2)):
            path = self.root / (name + '.nex')
            path.write_text('module inc::%s; import "./lib Юникод%%/common.nex" as common; fn main() -> unit !{io} { print(common::add(%d)); }' % (name, number))
            revisions.append(self.cli('check', path)['revision'])
        children = [subprocess.Popen([harness.NEX, 'build', '--revision', revision, '--json'], cwd=self.root,
                                     env={**os.environ, **self.env}, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    for revision in revisions]
        results = []
        try:
            for child in children:
                output, errors = child.communicate(timeout=45)
                self.assertEqual(child.returncode, 0, output + errors)
                results.append(json.loads(output))
        finally:
            for child in children:
                if child.poll() is None:
                    child.kill(); child.communicate(timeout=5)
        common_keys = []
        for index, result in enumerate(results):
            process = subprocess.run([result['executable']], capture_output=True, text=True, timeout=10)
            self.assertEqual((process.returncode, process.stdout), (0, str(index + 6) + '\n'))
            report = json.loads(Path(result['compilation']).read_text())
            common_keys.append(next(u['input_key'] for u in report['units'] if u['module'] == 'inc::common'))
        self.assertEqual(common_keys[0], common_keys[1])
        for revision in revisions:
            warm, _ = self.build('--revision', revision)
            self.assertEqual((warm['compiled_modules'], warm['reused_modules']), (0, 2))


if LIVE:
    class LiveFunctionCache(harness.ToolchainCase):
        def test_reused_dwarf_maps_both_revisions_after_original_source_deletion(self):
            self.source('''module frozen_cache;
fn first()->f64{return 1e0;}
fn observe(value:f64)->f64{
  let local:f64=value+0.25;
  return local; // CACHE_STOP
}
fn main()->unit!{io}{print(first());print(observe(1.25));}
''')
            first=self.cli('build')
            self.source(self.file.read_text().replace('return 1e0','return 100e0'))
            second=self.cli('build')
            self.assertEqual((second['compiled_functions'],second['reused_functions']),(1,2))
            self.file.unlink()
            from debugging import DAP
            for built in (first,second):
                with self.subTest(revision=built['revision']):
                    session=self.cli('debug','--revision',built['revision'],'--kind','nex-dap')
                    manifest=json.loads(Path(session['manifest']).read_text())
                    projected=manifest['sources'][0]['projection']
                    line=next(i+1 for i,s in enumerate(Path(projected).read_text().splitlines()) if 'CACHE_STOP' in s)
                    self.assertEqual(session['launch']['sourceMap'],manifest['source_map'])
                    # Standalone LLDB obtains the mapping from nex-load-debug;
                    # DAP separately receives its native sourceMap property.
                    result=self.cli('debug','--revision',built['revision'],'--',
                        '--no-lldbinit','--batch','-o','settings set target.disable-aslr false',
                        '-o','breakpoint set --file '+json.dumps(projected)+' --line '+str(line),
                        '-o','run','-o','nex-eval local','-o','continue',machine=False,timeout=60)
                    observations=[json.loads(s) for s in result.stdout.splitlines() if s.startswith('{')]
                    self.assertEqual(observations[0]['value'],1.5,result.stdout+result.stderr)
                    self.assertEqual(observations[0]['revision'],built['revision'])
                    client=DAP(session['adapter_command'],self.root)
                    try:
                        client.request('initialize',{'adapterID':'nex','pathFormat':'path','linesStartAt1':True})
                        launch=client.send('launch',dict(session['launch'],disableASLR=False))
                        client.event('initialized')
                        placed=client.request('setBreakpoints',{'source':{'path':projected},'breakpoints':[{'line':line}]})
                        self.assertTrue(placed['breakpoints'][0]['verified'])
                        client.request('configurationDone');client.response(launch)
                        stopped=client.event('stopped')
                        frame=client.request('stackTrace',{'threadId':stopped['threadId']})['stackFrames'][0]
                        self.assertEqual(Path(frame['source']['path']),Path(projected))
                        value=client.request('evaluate',{'expression':'local','frameId':frame['id'],'context':'watch'})
                        self.assertEqual(value['nex']['value'],1.5)
                        raw=client.request('evaluate',{'expression':'`nex-frame local','frameId':frame['id'],'context':'repl'})
                        captured=self.root/('frame-'+built['revision']+'.json')
                        captured.write_text(json.dumps(json.loads(raw['result'])))
                        client.request('continue',{'threadId':stopped['threadId']})
                        self.assertEqual(client.event('exited')['exitCode'],0)
                        self.assertEqual(self.cli('inspect',captured,'--manifest',session['manifest'],'--expression','local')['value'],1.5)
                    finally:
                        client.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
