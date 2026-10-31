"""Native server capabilities, durable UTF-8 data and transaction isolation."""
from sqlite_fixture import connection as sqlite_connection
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import unittest
import support as harness


class Storage(harness.ToolchainCase):
    def test_storage_persists_across_interpreted_and_native_processes(self):
        self.source('''module data;
server fn write() -> unit !{db} {
  assert(is_ok(store_put("item", "Я🦊\\u0000text")));
  assert(unwrap(store_keys("it")) == ["item"]);
}
server fn main() -> unit !{db,io} { print(unwrap(store_get("item"))); }
server test fn operations() -> unit !{db} {
  store_remove("scratch");
  assert(error_code(store_get("scratch")) == "NOT_FOUND");
  assert(unwrap(store_put("scratch", "value")));
  assert(unwrap(store_get("scratch")) == "value");
  assert(unwrap(store_remove("scratch")));
  assert(!unwrap(store_remove("scratch")));
}
''')
        env = {"NEX_DATABASE": str(self.root / "database.sqlite"), "NEX_STORAGE_OWNER": "alice"}
        self.cli("eval", "--entry", "write", env=env)
        built = self.cli("build", env=env)
        standalone = subprocess.run([built["executable"]], env={"PATH": "/usr/bin:/bin", **env}, capture_output=True, text=True)
        self.assertEqual(standalone.returncode, 0, standalone.stderr)
        self.assertEqual(standalone.stdout, "Я🦊\0text\n")
        self.cli("test", env=env)
        other = self.cli("eval", env={**env, "NEX_STORAGE_OWNER": "bob"}, ok=False)
        self.assertEqual(other["code"], "E_RESULT")
        self.assertIn("NOT_FOUND", other["message"])

    def test_missing_capabilities_and_invalid_values_are_results(self):
        self.source('''module capabilities;
server fn main() -> unit !{db,io} {
  assert(error_code(store_get("key")) == "CAPABILITY");
  assert(error_code(read_env("NEX_NEVER_DEFINED_TEST_VARIABLE_9536321")) == "NOT_FOUND");
  assert(error_code(read_env("bad=name")) == "VALIDATION");
  assert(error_code(read_env("bad\\u0000name")) == "VALIDATION");
  print(unwrap(read_env("NEX_CAPABILITY_TEST")));
}
test fn valid_shared_code() -> unit { assert(true); }
''')
        env = {"NEX_DATABASE": "", "NEX_CAPABILITY_TEST": "host 🦊"}
        self.assertEqual(self.cli("eval", env=env)["stdout"], "host 🦊\n")
        self.assertEqual(self.cli("run", env=env)["stdout"], "host 🦊\n")
        self.cli("test", "--target", "web", env=env)
        self.assertEqual(self.cli("emit", "--entry", "main", "--kind", "typescript", ok=False)["code"], "E_REALM")

    def test_storage_limits_and_literal_prefixes(self):
        self.source('''module limits;
server fn main() -> unit !{db} {
  assert(error_code(store_put("", "x")) == "VALIDATION");
  assert(error_code(store_get("bad\\u0000key")) == "VALIDATION");
  assert(unwrap(store_put("percent%_", "one")));
  assert(unwrap(store_put("percentXY", "two")));
  assert(unwrap(store_keys("percent%")) == ["percent%_"]);
  assert(unwrap(store_put("数学🦊", "three")));
  assert(unwrap(store_keys("数学")) == ["数学🦊"]);
}
''')
        env = {"NEX_DATABASE": str(self.root / "limits.sqlite")}
        self.cli("eval", env=env);self.cli("run", env=env)

    def test_invalid_database_resources_and_schema_are_rejected(self):
        self.source('module invalid_database; server fn main() -> unit !{db} { assert(!is_ok(store_get("x"))); }')
        for path in (':memory:', 'file:memory?mode=memory'):
            self.cli('eval', env={'NEX_DATABASE': path})
            self.cli('run', env={'NEX_DATABASE': path})
        path = self.root / 'incorrect.sqlite'
        with sqlite_connection(path) as db:
            db.execute('CREATE TABLE nex_kv(owner TEXT COLLATE NOCASE NOT NULL,key TEXT NOT NULL,value BLOB NOT NULL,PRIMARY KEY(owner,key))')
        self.source('module invalid_schema; server fn main() -> unit !{db} { assert(error_code(store_get("x")) == "E_STORE_SCHEMA"); }')
        self.cli('eval', env={'NEX_DATABASE': str(path)})
        self.cli('run', env={'NEX_DATABASE': str(path)})

    def test_server_realm_and_effect_requirements(self):
        for definition, code in [
            ('fn main() -> unit !{db} { store_get("x"); }', 'E_REALM'),
            ('client fn main() -> unit !{db} { store_get("x"); }', 'E_REALM'),
            ('server fn main() -> unit { store_get("x"); }', 'E_EFFECT'),
            ('server fn main() -> unit { read_env("x"); }', 'E_EFFECT'),
        ]:
            self.source('module effects; ' + definition)
            self.assertEqual(self.cli("check", ok=False)["code"], code)

    def test_only_needed_runtime_components_link_sqlite(self):
        self.source('module pure; fn main() -> unit {}')
        pure = self.cli("build")
        self.source('module stored; server fn main() -> unit !{db} { store_get("x"); }')
        stored = self.cli("build")
        if shutil.which('otool'):
            pure_deps = subprocess.check_output(['otool', '-L', pure['executable']], text=True)
            stored_deps = subprocess.check_output(['otool', '-L', stored['executable']], text=True)
            self.assertNotIn('sqlite3', pure_deps)
            self.assertIn('sqlite3', stored_deps)

    def test_native_transactions_rollback_and_concurrent_principals(self):
        self.source('''module storage;
server fn mutate(mode: str) -> result<str> !{db} {
  let saved: result<str> = store_get("counter");
  var count: i64 = 0;
  if is_ok(saved) { count = unwrap(decode_json<i64>(unwrap(saved))); }
  let written: result<bool> = store_put("counter", encode_json(count + 1));
  if !is_ok(written) { return err(error_code(written), error_message(written)); }
  if mode == "1" { assert(false); }
  if mode == "2" { store_put("", "invalid mutation"); }
  if mode == "3" { while true { count = count + 1; } }
  return ok(str(count + 1));
}
''')
        built = self.cli("build", "--library", "--entry", "mutate", "--profile", "release")
        doctor = self.cli("doctor")
        target = self.root / "storage-scope-test"
        compiled = subprocess.run([doctor['native_compiler'], '-std=c++20', '-pthread', '-I', str(harness.REPO / 'runtime'),
                                   str(harness.REPO / 'tests/storage_scope.cpp'), built['executable'], doctor['native_sqlite_library'],
                                   '-o', str(target)], capture_output=True, text=True)
        self.assertEqual(compiled.returncode, 0, compiled.stderr)
        result = subprocess.run([str(target), str(self.root / 'concurrent.sqlite')], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=2)
