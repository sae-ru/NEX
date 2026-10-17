"""Separate native compilation checked against real compiler calls and behavior."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest

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
        self.assertEqual(len(native), result['compiled_modules'], calls)
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
        (self.root / 'nex.json').write_text(json.dumps({'language': '0.6', 'entry': 'main.nex', 'libraries': {'numbers': 'package'}}))
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


if __name__ == '__main__':
    unittest.main(verbosity=2)
