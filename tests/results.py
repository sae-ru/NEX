"""Recoverable values, strict wire codecs and generated request unwinding."""
import json
import hashlib
from pathlib import Path
import subprocess
import unittest
import support as harness


class Results(harness.ToolchainCase):
    def test_vendored_provenance_and_native_distribution_notices(self):
        vendor = harness.REPO / 'runtime/third_party'
        manifest = json.loads((vendor / 'manifest.json').read_text())
        for component in manifest['components']:
            self.assertEqual(hashlib.sha256((vendor / component['file']).read_bytes()).hexdigest(), component['sha256'])
            self.assertIn('Permission is hereby granted', (vendor / component['license']).read_text())
        self.source('module notices; fn main() -> unit !{io} { print(encode_json([1, 2])); }')
        target = self.root / 'distributed program'
        built = self.cli('build', '--profile', 'release', '-o', target)
        self.assertEqual(built['kind'], 'executable')
        notices = Path(built['notices'])
        expected = ('Dragonbox 1.1.3\n\n' + (vendor / 'dragonbox/LICENSE-Boost').read_text() + '\n\n'
                    + harness.windows_notices(built) + 'nlohmann/json 3.12.0\n\n' + (vendor / 'JSON-LICENSE.MIT').read_text() + '\n\n')
        self.assertEqual(notices.read_text(), expected)
        self.assertEqual(str(notices), str(target) + '.THIRD_PARTY_NOTICES.txt')
        metadata = json.loads(Path(built['metadata']).read_text())
        self.assertEqual(metadata['kind'], 'executable')
        self.assertEqual(metadata['runtime_components'], ['runtime.cpp', 'nex_json.cpp', 'wire_runtime.cpp'])
        self.assertTrue((Path(metadata['runtime_source_projection']) / 'third_party/JSON-LICENSE.MIT').is_file())
        dragonbox=json.loads((vendor/'dragonbox/manifest.json').read_text())
        self.assertEqual(dragonbox['commit'],'3053a74ac81099591a12a55341a203d9688fbb92')
        self.assertFalse(dragonbox['local_modifications'])
        for name,record in dragonbox['files'].items():
            original=(vendor/'dragonbox'/name).read_bytes()
            self.assertEqual(hashlib.sha256(original).hexdigest(),record['sha256'])
            self.assertEqual((Path(metadata['runtime_source_projection'])/'third_party/dragonbox'/name).read_bytes(),original)
        self.assertTrue(self.cli('build', '--profile', 'release')['cached'])
        Path(metadata['notices']).write_text('corrupted notice', newline="\n")
        rebuilt = self.cli('build', '--profile', 'release')
        self.assertFalse(rebuilt['cached'])
        self.assertEqual(Path(rebuilt['notices']).read_text(), expected)
        result = subprocess.run([str(target)], capture_output=True, text=True, timeout=10)
        self.assertEqual((result.returncode, result.stdout), (0, '["1","2"]\n'))

    def test_result_values_and_typed_wire_models_in_all_backends(self):
        self.source((harness.REPO / "examples/results.nex").read_text())
        expected = self.cli("eval")["stdout"]
        self.assertIn('"id":"9223372036854775807"', expected)
        for profile in ("debug", "release"):
            self.assertEqual(self.cli("run", "--profile", profile)["stdout"], expected)
            self.cli("test", "--profile", profile)
        self.cli("test", "--target", "web")

    def test_unwrap_failure_remains_an_explicit_trap(self):
        self.source('module failure; fn main() -> unit !{io} { print("before"); print(unwrap(err<i64>("DENIED", "no access"))); }')
        reference = self.cli("eval", ok=False)
        self.assertEqual(reference["code"], "E_RESULT")
        for profile in ("debug", "release"):
            actual = self.cli("run", "--profile", profile, ok=False)
            self.assertEqual(actual["exit_code"], 70)
            self.assertEqual(actual["stdout"], reference["stdout"])
            self.assertIn("E_RESULT", actual["stderr"])

    def test_invalid_wire_inputs_are_recoverable_and_agree(self):
        bad_integers = ["1", "true", "null", '""', '"-0"', '"01"', '"+1"', '" 1"',
                        '"9223372036854775808"', '"-9223372036854775809"', '"1e2"', '"١"']
        bad_integers += [json.dumps(value) for value in ('1\n','1\r','1\u2028','1\u2029','-1\n','1'*100)]
        bad_integers += ['"\\ud800"', '"\\udc00"']
        bad_records = ['{}', '{"id":"1"}', '{"id":"1","text":"x","extra":true}',
                       '{"id":"1","text":"x","id":"2"}',
                       '{"id":"1","\\u0074ext":"x","text":"y"}',
                       '{"id":"1","text":"\\ud800"}', '{"id":"1","text":"\\udc00"}',
                       '{"id":"1","text":false}', '{"id":"1","text":"x"} trailing',
                       '{"id":"1","text":"', 'null', '[]']
        bad_records.append('{"id":"1","text":"x","\\ud800":true}')
        body = []
        for i, (type_, text) in enumerate([(t, s) for t, values in [('i64', bad_integers), ('Row', bad_records)] for s in values]):
            body.append('let r%d: result<%s> = decode_json<%s>(%s); assert(!is_ok(r%d)); assert(error_code(r%d) == "E_JSON"); print(error_message(r%d));' % (i, type_, type_, json.dumps(text), i, i, i))
        self.source('module validation; struct Row { id: i64; text: str; } fn main() -> unit {} test fn invalid() -> unit !{io} {' + '\n'.join(body) + '}')
        self.cli("test", "--profile", "release")
        self.cli("test", "--target", "web")

    def test_type_rules_and_public_result_visibility(self):
        for source, code in [
            ('fn main() -> unit { let x: result<unit> = err("X", "Y"); }', 'E_TYPE'),
            ('fn main() -> unit { print(err("X", "Y")); }', 'E_INFER'),
            ('fn main() -> unit { let x: result<i64> = ok(true); }', 'E_TYPE'),
            ('fn main() -> unit { let x: result<i64> = decode_json("1"); }', 'E_INFER'),
            ('fn main() -> unit { let x: i64 = unwrap(1); }', 'E_TYPE'),
            ('struct Private { x: i64; } pub fn get() -> result<Private> { return ok(Private(1)); }', 'E_VISIBILITY'),
        ]:
            with self.subTest(source=source):
                self.source('module errors; ' + source)
                self.assertEqual(self.cli("check", ok=False)["code"], code)

    def test_imported_types_in_annotations_and_bounded_context(self):
        (self.root / "model.nex").write_text('module models; pub struct Row { id: i64; }', newline="\n")
        self.source('module app; import "./model.nex" as m; fn parse() -> result<m::Row> { return decode_json<m::Row>("{\\\"id\\\":\\\"7\\\"}"); } fn main() -> unit { assert(unwrap(parse()).id == 7); } test fn parse_test() -> unit { main(); }')
        self.cli("test")
        self.cli("test", "--target", "web")
        context = self.cli("context", "--symbol", "parse")
        self.assertEqual(context["structures"][0]["name"], "models::Row")

    def test_native_request_scopes_unwind_generated_frames_and_cleanup(self):
        self.source('''module scope;
struct Input { mode: i64; text: str; }
server fn handle(input: Input) -> result<str> {
  let values: list<str> = [input.text, "temporary"];
  var i: i64 = 0;
  while input.mode == 1 { i = i + 1; }
  if input.mode == 2 { return ok(str(9223372036854775807 + input.mode)); }
  if input.mode == 3 { assert(false); }
  if input.mode == 4 { return ok(unwrap(err<str>("X", "failure"))); }
  return ok(values[0] + ":" + str(input.mode));
}
''')
        built = self.cli("build", "--library", "--entry", "handle", "--profile", "release")
        self.assertEqual(built['kind'], 'static_library')
        self.assertTrue(built["executable"].endswith("libnex.a"))
        compiler = self.cli("doctor")["native_compiler"]
        target = self.root / "scope-test"
        compiled = subprocess.run([compiler, '-std=c++20', '-pthread', '-I', str(harness.REPO / 'runtime'),
                                   str(harness.REPO / 'tests/request_scope.cpp'), built['executable'], '-o', str(target)], capture_output=True, text=True)
        self.assertEqual(compiled.returncode, 0, compiled.stderr)
        result = subprocess.run([str(target)], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=2)
