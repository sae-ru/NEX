"""TypeScript semantics, client reachability and generated application contracts."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest
import support as harness


class Web(harness.ToolchainCase):
    def test_cli_typescript_tests_in_literal_and_physical_backslash_paths(self):
        root = self.root / 'project "quoted" \\ % 🧠'
        root.mkdir()
        source = root / 'main.nex'
        source.write_text('''module path_semantics;
fn main() -> unit !{io} { print("A🧠\\u0000"); print(9007199254740993 + 1); }
test fn value_test() -> unit !{io} { main(); assert(slice("A🧠B", 1, 1) == "🧠"); }
server fn secret() -> str { return "SERVER_PATH_SECRET"; }
''')
        revision = self.cli("check", cwd=root)["revision"]
        self.assertEqual(self.cli("run", cwd=root)["stdout"], self.cli("eval", cwd=root)["stdout"])
        self.assertEqual(self.cli("run", "--build-directory", root / 'native-temp-case', cwd=root,
                                  env={"TMPDIR": str(root)})["stdout"], self.cli("eval", cwd=root)["stdout"])
        alias = self.root / 'physical-alias'
        alias.symlink_to(root, target_is_directory=True)
        for directory in (root, alias):
            result = self.cli("test", "--target", "web", cwd=directory, env={"TMPDIR": str(root)})
            self.assertTrue(result["tests"][0]["web"])
        generated = list((root / '.nex/build').glob('*/typescript/program.ts'))
        self.assertEqual(len(generated), 1)
        self.assertNotIn("SERVER_PATH_SECRET", generated[0].read_text())
        self.assertTrue((generated[0].parent / 'nex-map.json').is_file())
        source.unlink()
        self.assertTrue(self.cli("test", "--revision", revision, "--target", "web", cwd=root)["tests"][0]["web"])

    def run_web(self, *, entry="main", revision=None):
        destination = self.root / "typescript"
        options = ["emit", "--kind", "typescript", "--entry", entry, "--directory", destination]
        if revision:
            options += ["--revision", revision]
        self.cli(*options)
        (destination / "package.json").write_text('{"type":"module"}')
        driver = destination / "driver.ts"
        driver.write_text('''import { entry } from './program.ts';
import { str, NexError } from './nex-runtime.ts';
let output = '';
console.log = value => { output += String(value) + '\\n'; };
let result;
try {
  const value = entry();
  result = { ok: true, stdout: output, value: value === undefined ? null : str(value) };
} catch (error) {
  if (!(error instanceof NexError)) throw error;
  result = { ok: false, stdout: output, code: error.code, site: error.site };
}
process.stdout.write(JSON.stringify(result));
''')
        result = subprocess.run([os.environ.get("NEX_NODE", "node"), "--experimental-strip-types", "--no-warnings", str(driver)],
                                cwd=self.root, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_observable_semantics_agree_with_interpreter_and_native(self):
        self.source('''module web_semantics;
struct Record { __proto__: i64; constructor: str; nested: list<list<str>>; }
fn effect(n: i64) -> bool !{io} { print(n); return true; }
fn rec(n: i64) -> i64 { if n == 0 { return 1; } return n * rec(n - 1); }
fn main() -> unit !{io} {
  assert(9007199254740993 + 1 == 9007199254740994);
  assert(-9223372036854775808 % -1 == 0);
  assert(-7 / 3 == -2); assert(-7 % 3 == -1); assert(7 % -3 == 1);
  assert(rec(10) == 3628800);
  let x: i64 = 4;
  if true { let x: i64 = x + 1; print(x); }
  print(x);
  let source: str = "A🦊Яe\\u0301\\u0000";
  assert(len(source) == 6); assert(source[1] == "🦊");
  assert(slice(source, 1, 2) == "🦊Я"); assert(slice(source, 6, 0) == "");
  assert(contains(source, "e\\u0301"));
  let original: list<i64> = [1, 2];
  let changed: list<i64> = push(set(original, 0, 8), 3);
  assert(original == [1, 2]); assert(changed == [8, 2, 3]);
  assert(original + changed == [1, 2, 8, 2, 3]);
  let value: Record = Record(9223372036854775807, "line\\n\\t\\u0000\\b", [[source], []]);
  assert(value.__proto__ == 9223372036854775807);
  assert(value == Record(value.__proto__, value.constructor, value.nested));
  print(value); print(str(value)); print(source);
  assert(!(false && effect(99))); assert(true || effect(98));
  assert(effect(1) && effect(2));
  var i: i64 = 0; var total: i64 = 0;
  while i < 10 { total = total + i; i = i + 1; }
  print(total);
}
test fn values_test() -> unit !{io} { main(); }
''')
        expected = self.cli("eval")["stdout"]
        self.assertEqual(self.cli("run", "--profile", "release")["stdout"], expected)
        self.assertEqual(self.run_web()["stdout"], expected)
        tests = self.cli("test", "--target", "web")["tests"]
        self.assertTrue(all(t["web"] and not t["native"] for t in tests))

    def test_checked_failures_preserve_output_and_source_locations(self):
        for expression, code in [
            ('9223372036854775807 + 1', 'E_OVERFLOW'),
            ('-(-9223372036854775808)', 'E_OVERFLOW'),
            ('-9223372036854775808 / -1', 'E_OVERFLOW'),
            ('3037000500 * 3037000500', 'E_OVERFLOW'),
            ('0 - -9223372036854775808', 'E_OVERFLOW'),
            ('1 / 0', 'E_DIV_ZERO'), ('1 % 0', 'E_DIV_ZERO'),
            ('[1][-1]', 'E_BOUNDS'), ('[1][1]', 'E_BOUNDS'),
            ('"🦊"[1]', 'E_BOUNDS'), ('set([1], 2, 3)', 'E_BOUNDS'),
            ('slice("a", 9223372036854775807, 1)', 'E_BOUNDS'),
        ]:
            with self.subTest(expression=expression):
                self.source('module traps; fn main() -> unit !{io} { print("before"); print(' + expression + '); }')
                expected = self.cli("eval", ok=False)
                actual = self.run_web()
                self.assertEqual(actual["code"], code)
                self.assertEqual(actual["code"], expected["code"])
                self.assertEqual(actual["stdout"], expected["stdout"])
                self.assertEqual(actual["site"], [expected["file"], expected["line"], expected["column"], expected["operation_site"]])
                self.assertRegex(expected["operation_id"], r"^[a-f0-9]{32}$")
        self.source('module traps; fn main() -> unit { assert(false); }')
        self.assertEqual(self.run_web()["code"], "E_ASSERT")

    def test_only_reachable_client_and_shared_definitions_are_emitted(self):
        self.source('''module realms;
server fn secret() -> str { return "SERVER_SECRET_MUST_NOT_SHIP"; }
client fn unused() -> str { return "UNUSED_CLIENT_DEFINITION"; }
fn shared_value() -> str { return "shared"; }
client fn main() -> unit !{io} { print(shared_value()); }
server test fn server_test() -> unit { assert(secret() == "SERVER_SECRET_MUST_NOT_SHIP"); }
client test fn client_test() -> unit { assert(shared_value() == "shared"); }
''')
        self.assertEqual(self.run_web()["stdout"], "shared\n")
        emitted = (self.root / "typescript/program.ts").read_text()
        self.assertNotIn("SERVER_SECRET_MUST_NOT_SHIP", emitted)
        self.assertNotIn("UNUSED_CLIENT_DEFINITION", emitted)
        self.assertEqual(self.cli("emit", "--kind", "typescript", "--entry", "secret", ok=False)["code"], "E_REALM")
        tests = self.cli("test", "--target", "web")["tests"]
        self.assertTrue(next(t for t in tests if t["name"] == "realms::server_test")["skipped"])
        self.assertTrue(next(t for t in tests if t["name"] == "realms::client_test")["web"])

    def test_typescript_uses_archived_sources_after_deletion(self):
        (self.root / "values.nex").write_text('module values; pub fn answer() -> i64 { return 42; }')
        self.source('module app; import "./values.nex" as v; fn main() -> unit !{io} { print(v::answer()); }')
        revision = self.cli("check")["revision"]
        self.file.unlink(); (self.root / "values.nex").unlink()
        self.assertEqual(self.run_web(revision=revision)["stdout"], "42\n")

    def test_browser_boundary_rejects_unpaired_surrogates_and_freezes_values(self):
        self.source('module runtime; fn main() -> unit {}')
        self.run_web()
        directory = self.root / "typescript"
        driver = directory / "runtime-check.ts"
        driver.write_text('''import * as nex from './nex-runtime.ts';
import assert from 'node:assert/strict';
for (const invalid of ['\\ud800', '\\udc00', '\\ud800x']) {
  assert.throws(() => nex.string(invalid), error => error.code === 'E_UTF8');
}
assert.equal(nex.string('🦊'), '🦊');
const original = nex.list([1n, 2n]);
assert.throws(() => { original[0] = 7n; }, TypeError);
const value = nex.record('A', [['__proto__', original]]);
assert.throws(() => { value.__proto__ = []; }, TypeError);
assert.equal(nex.equal(value, nex.record('B', [['__proto__', original]])), false);
assert.equal(nex.representation(value), '{"__proto__":[1,2]}');
''')
        result = subprocess.run([os.environ.get("NEX_NODE", "node"), "--experimental-strip-types", "--no-warnings", str(driver)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def app_source(self):
        return (harness.REPO / "examples/web/main.nex").read_text()

    def test_application_generation_and_reachable_metadata(self):
        self.source(self.app_source() + '\nserver fn secret() -> str { return "API_SECRET_NOT_IN_CLIENT"; }\n')
        output = self.root / "web output"
        generated = self.cli("web", "--directory", output)
        self.assertEqual(generated["schema"], "nex.web/1")
        self.assertEqual(generated["language"], "0.18")
        self.assertEqual(set(generated["files"]), {
            "README.md", "index.html", "package.json", "package-lock.json", "tsconfig.json", "vite.config.js", "playwright.config.js",
            "nex-map.json", "src/program.ts", "src/nex-runtime.ts", "src/nex-bytes.ts", "src/renderer.tsx", "src/urls.ts", "src/net.ts", "src/app.tsx", "src/app.css", "src/vite-env.d.ts", "tests/smoke.spec.js", "public/THIRD_PARTY_NOTICES.txt"})
        self.assertEqual((output / "src/nex-bytes.ts").read_text(), (harness.REPO / "web/nex-bytes.ts").read_text())
        for file in generated["files"]:
            self.assertNotIn("API_SECRET_NOT_IN_CLIENT", (output / file).read_text())
        mappings = json.loads((output / "nex-map.json").read_text())
        self.assertIn("tasks::update", {f["name"] for f in mappings["functions"]})
        self.assertNotIn("tasks::secret", {f["name"] for f in mappings["functions"]})
        self.assertEqual(self.cli("web", "--directory", output, ok=False)["code"], "E_EXISTS")
        tests = self.cli("test", "--target", "web")["tests"]
        self.assertEqual(len(tests), 2)
        self.assertTrue(all(t["web"] for t in tests))

    def test_application_contract_rejects_wrong_state_and_effects(self):
        original = self.app_source()
        for invalid in [
            original.replace('client fn title() -> str', 'server fn title() -> str').replace('web::text(title())', 'web::text("Tasks")'),
            original.replace('client fn title() -> str', 'client fn title() -> str !{io}').replace('web::text(title())', 'web::text("Tasks")'),
            original.replace('client fn update(state: State, event: web::Event) -> State', 'client fn update(state: State, event: web::Event, extra: i64) -> State').split('client test fn')[0],
        ]:
            with self.subTest(source=invalid[:40]):
                self.source(invalid)
                self.assertEqual(self.cli("web", "--directory", self.root / "output", ok=False)["code"], "E_WEB_SIGNATURE")
                self.assertFalse((self.root / "output").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
