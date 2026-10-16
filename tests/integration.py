"""Observable language, native/interpreter, graph and LLM protocol checks."""
import json
import os
from pathlib import Path
import random
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest

import support as harness
NEX = harness.NEX
REPO = harness.REPO


class Toolchain(harness.ToolchainCase):
    def test_starter_and_real_native_binary(self):
        self.cli("init", ".")
        self.cli("check")
        interpreted = self.cli("eval")
        native = self.cli("run")
        self.assertEqual(interpreted["stdout"], "55\n")
        self.assertEqual(native["stdout"], interpreted["stdout"])
        tests = self.cli("test")
        self.assertTrue(tests["tests"][0]["native"])
        output = self.root / "standalone program"
        self.cli("build", "-o", output, "--profile", "release")
        child = subprocess.run([str(output)], capture_output=True, text=True, timeout=10,
                               cwd="/", env={"PATH": "/usr/bin:/bin"})
        self.assertEqual((child.returncode, child.stdout), (0, "55\n"))
        self.cli("init", ".", ok=False)

    def test_control_flow_scopes_recursion_and_short_circuit(self):
        self.source("""module semantics;
fn fib(n: i64) -> i64 {
  if n <= 1 { return n; } else { return fib(n - 1) + fib(n - 2); }
}
fn side() -> bool !{io} { print(999); return true; }
fn nothing() -> unit { return assert(true); }
fn main() -> i64 !{io} {
  var x: i64 = 1;
  var i: i64 = 0;
  while i < 4 { let x: i64 = i * 2; print(x); i = i + 1; }
  print(x);
  print(false && side());
  print(true || side());
  print(true && (false || true));
  print(!false);
  print(fib(10));
  print(-7 / 3);
  print(-7 % 3);
  print(-9223372036854775808 % -1);
  nothing();
  return 0;
}
test fn branches() -> unit {
  assert(fib(8) == 21);
  assert((false && (1 / 0 == 0)) == false);
  assert(true || (1 / 0 == 0));
}
""")
        expected = "0\n2\n4\n6\n1\nfalse\ntrue\ntrue\ntrue\n55\n-2\n-1\n0\n"
        self.assertEqual(self.cli("eval")["stdout"], expected)
        for profile in ("debug", "release"):
            self.assertEqual(self.cli("run", "--profile", profile)["stdout"], expected)
        self.cli("test")

    def test_rejections_are_structured_and_do_not_change_head(self):
        valid = "module bad; fn main() -> i64 { return 0; }"
        head = self.cli("check", self.source(valid))["revision"]
        cases = [
            ("fn main() -> i64 { return true; }", "E_TYPE"),
            ("fn main() -> i64 { let x: i64 = 1; x = 2; return x; }", "E_MUTABILITY"),
            ("fn main() -> i64 { print(1); return 0; }", "E_EFFECT"),
            ("fn main() -> i64 { if true { return 1; } }", "E_RETURN"),
            ("fn main() -> i64 { return 0; print(1); }", "E_UNREACHABLE"),
            ("fn main() -> i64 { return missing(); }", "E_NAME"),
            ("fn main() -> i64 { return 9223372036854775808; }", "E_RANGE"),
            ("fn main(x: unit) -> i64 { return 0; }", "E_TYPE"),
            ("fn main() -> i64 { let x: i64 = 1; let x: i64 = 2; return x; }", "E_DUPLICATE"),
            ("fn main() -> i64 !{network} { return 0; }", "E_EFFECT"),
            ("server fn secret() -> i64 { return 1; } fn main() -> i64 { return secret(); }", "E_REALM"),
            ("test fn wrong() -> i64 { return 1; }", "E_TEST"),
        ]
        for body, code in cases:
            with self.subTest(code=code, body=body):
                result = self.cli("check", self.source("module bad; " + body), ok=False)
                self.assertEqual(result["schema"], "nex.diagnostic/1")
                self.assertEqual(result["code"], code)
                self.assertIn("column", result)
                self.assertEqual(self.cli("history")["head"], head)

    def test_checked_arithmetic_errors_match_native_profiles(self):
        cases = [
            ("9223372036854775807 + 1", "E_OVERFLOW"),
            ("-9223372036854775808 - 1", "E_OVERFLOW"),
            ("9223372036854775807 * 2", "E_OVERFLOW"),
            ("-(-9223372036854775808)", "E_OVERFLOW"),
            ("-9223372036854775808 / -1", "E_OVERFLOW"),
            ("1 / 0", "E_DIV_ZERO"),
            ("1 % 0", "E_DIV_ZERO"),
        ]
        for expression, code in cases:
            with self.subTest(expression=expression):
                self.source("module traps; fn main() -> i64 { return " + expression + "; }")
                self.assertEqual(self.cli("eval", ok=False)["code"], code)
                for profile in ("debug", "release"):
                    actual = self.cli("run", "--profile", profile, ok=False)
                    self.assertEqual(actual["exit_code"], 70)
                    self.assertIn(code, actual["stderr"])

    def test_generated_arithmetic_matches_python_oracle(self):
        rng = random.Random(4120)
        checks = []
        for _ in range(80):
            a, b, c = (rng.randint(-1000, 1000) for _ in range(3))
            expected = a * b + c
            checks.append("assert((%s) * (%s) + (%s) == (%s));" % (a, b, c, expected))
        self.source("module generated; fn main() -> unit {} test fn random_arithmetic() -> unit {" + "\n".join(checks) + "}")
        self.cli("test", "--profile", "release")

    def test_output_before_runtime_error_is_preserved(self):
        self.source("module output; fn main() -> i64 !{io} { print(7); return 1 / 0; }")
        interpreted = self.cli("eval", ok=False)
        native = self.cli("run", ok=False)
        self.assertEqual(interpreted["stdout"], "7\n")
        self.assertEqual(native["stdout"], interpreted["stdout"])

    def test_revision_identity_and_node_identity(self):
        first = "module identity; fn a() -> i64 { return 1; } fn main() -> i64 { return a(); }"
        rev1 = self.cli("check", self.source(first))["revision"]
        graph1 = self.cli("graph")
        reordered = "// comment\nmodule identity;\nfn main() -> i64 { return a(); }\nfn a() -> i64 { return 1; }"
        self.assertEqual(self.cli("check", self.source(reordered))["revision"], rev1)
        self.cli("check", self.source(first.replace("return 1", "return 2")))
        graph2 = self.cli("graph")
        self.assertNotEqual(graph1["revision"], graph2["revision"])
        ids1 = {n["name"]: n["id"] for n in graph1["nodes"]}
        self.assertEqual(ids1, {n["name"]: n["id"] for n in graph2["nodes"]})
        self.assertEqual(graph1["nodes"][1]["dependencies"][0]["name"], "identity::a")
        literal = 'module spelling; fn text() -> str { return "🦊"; } fn main() -> unit {}'
        raw = self.cli("check", self.source(literal))["revision"]
        escaped = self.cli("check", self.source(literal.replace("🦊", "\\uD83E\\uDD8A")))["revision"]
        self.assertEqual(raw, escaped)

    def test_llm_context_patch_conflict_export_and_import(self):
        self.cli("init", ".")
        self.cli("check")
        before = (self.root / "src/main.nex").read_text()
        context = self.cli("context", "--symbol", "sum")
        self.assertEqual(context["callers"], ["app::main", "app::sum_test"])
        patch = self.root / "patch.json"
        patch.write_text(json.dumps({"expected_revision": context["revision"], "replacements": [
            {"name": "sum", "source": "fn sum(n: i64) -> i64 { return n * (n + 1) / 2; }"}
        ]}))
        applied = self.cli("apply", "--patch", patch)
        self.assertNotEqual(applied["revision"], context["revision"])
        self.assertFalse(applied["materialized"])
        self.assertEqual((self.root / "src/main.nex").read_text(), before)
        self.cli("test", "--revision", "HEAD")
        self.assertEqual(self.cli("apply", "--patch", patch, ok=False)["code"], "E_CONFLICT")
        graph = self.cli("graph")
        self.cli("export", "--revision", "HEAD", "-o", self.root / "export.nex")
        self.assertIn("return n *", (self.root / "export.nex").read_text())
        graphfile = self.root / "graph.json"
        graphfile.write_text(json.dumps(graph))
        self.assertEqual(self.cli("import", graphfile)["revision"], applied["revision"])
        graph["source"] = graph["source"].replace("return n *", "return (n + 1) *")
        graphfile.write_text(json.dumps(graph))
        self.assertEqual(self.cli("import", graphfile, ok=False)["code"], "E_BUNDLE")

    def test_cache_target_and_ir_artifacts(self):
        self.source("module cache; fn main() -> i64 { return 0; }")
        first = self.cli("build")
        second = self.cli("build")
        self.assertFalse(first["cached"])
        self.assertTrue(second["cached"])
        self.assertEqual(first["build_key"], second["build_key"])
        with Path(first["executable"]).open("ab") as artifact:
            artifact.write(b"corrupted cache artifact")
        self.assertFalse(self.cli("build")["cached"])
        release = self.cli("build", "--profile", "release")
        self.assertNotEqual(first["build_key"], release["build_key"])
        self.assertIn("func.func", Path(first["mlir"]).read_text())
        self.assertIn("define", Path(first["llvm"]).read_text())
        self.assertEqual(self.cli("build", "--target", "unsupported-triple", ok=False)["code"], "E_TARGET")
        self.file.write_text("// new source line\n" + self.file.read_text())
        changed = self.cli("build")
        self.assertEqual(first["revision"], changed["revision"])
        self.assertNotEqual(first["build_key"], changed["build_key"])

    def test_step_limit_and_input_validation(self):
        self.source("module endless; fn main() -> i64 { while true {} return 0; }")
        self.assertEqual(self.cli("eval", "--steps", "100", ok=False)["code"], "E_LIMIT")
        self.assertEqual(self.cli("eval", "--steps", "-1", ok=False)["code"], "E_OPTION")
        self.assertEqual(self.cli("eval", "--steps", "10x", ok=False)["code"], "E_OPTION")
        self.assertEqual(self.cli("check", "--imaginary", ok=False)["code"], "E_OPTION")
        self.assertEqual(self.cli("no-such-command", ok=False)["code"], "E_COMMAND")

    @unittest.skipUnless(shutil.which("lldb"), "LLDB is not installed")
    def test_debug_symbols_resolve_nex_source(self):
        self.source("module debug; fn main() -> i64 { return 0; }")
        self.cli("check")
        symbol = self.cli("context", "--symbol", "main")["native_symbol"]
        result = self.cli("debug", "--", "-b", "-o",
                          "image lookup --verbose --name " + symbol, machine=False)
        self.assertIn("source.nex", result.stdout)
        self.assertIn("CompileUnit", result.stdout)

    def test_pack_and_discovery_match_executable_example(self):
        descriptor = self.cli("describe")
        self.assertEqual(descriptor["version"], "0.5")
        pack = json.loads((REPO / "llm/language-pack.json").read_text())
        self.assertEqual(pack["language_version"], descriptor["version"])
        self.assertIn("web_ui", descriptor["features"])
        self.assertIn("native_http", descriptor["features"])
        self.assertIn("web_request_commands", descriptor["features"])
        self.assertIn("generated_client_helpers", descriptor["api_features"])
        self.assertIn("lldb_dap_launch", descriptor["debug_features"])
        for field in ("specification", "grammar", "llm_prompt", "web_guide", "server_guide", "api_guide", "debug_guide"):
            self.assertTrue((REPO / descriptor[field]).is_file())
        for kind in ("prompt", "language", "grammar", "protocol", "web", "server", "api", "debug"):
            guide = self.cli("guide", "--kind", kind)
            self.assertEqual(guide["language"], descriptor["version"])
            self.assertEqual(len(guide["hash"]), 64)
            self.assertGreater(len(guide["text"]), 100)
        self.source((REPO / "examples/arithmetic.nex").read_text())
        self.cli("test")
        self.assertEqual(self.cli("run")["stdout"], "55\n3628800\n")

    def test_unicode_lists_and_structures_in_both_backends(self):
        self.source((REPO / "examples/data.nex").read_text())
        expected = ('Привет, Саша 🦊!\n'
                    '{"id":7,"name":"Саша 🦊","active":true,"tags":["nex","web"]}\n'
                    '["Саша 🦊","Ada"]\n["Lin","Ada"]\n3\n🦊\n🦊Я\n')
        self.assertEqual(self.cli("eval")["stdout"], expected)
        for profile in ("debug", "release"):
            self.assertEqual(self.cli("run", "--profile", profile)["stdout"], expected)
            self.cli("test", "--profile", profile)
        context = self.cli("context", "--symbol", "greeting")
        self.assertEqual([s["name"] for s in context["structures"]], ["data::User"])
        self.assertIn("tags: list<str>", context["structures"][0]["source"])
        graph = self.cli("graph")
        self.assertEqual(graph["structures"][0]["name"], "data::User")
        graphfile = self.root / "graph.json"
        graphfile.write_text(json.dumps(graph))
        self.cli("import", graphfile)

    def test_ownership_aliases_scopes_and_early_returns(self):
        self.source('''module ownership;
struct Row { label: str; values: list<i64>; }
struct Tree { value: str; children: list<Tree>; }
fn identity(s: str) -> str { return s; }
fn select(n: i64) -> str {
  let outer: str = "outer";
  var i: i64 = 0;
  while i < 3 {
    let inner: str = identity("inner");
    if n == i { return inner + outer; }
    i = i + 1;
  }
  return outer;
}
fn collection() -> list<Row> {
  let a: Row = Row("a", [1, 2]);
  return [a, a];
}
fn tree(n: i64) -> Tree {
  if n == 0 { return Tree("leaf", []); }
  return Tree("branch", [tree(n - 1)]);
}
fn main() -> unit {}
test fn ownership_test() -> unit {
  var words: list<str> = ["original"];
  let alias: list<str> = words;
  words = set(words, 0, "changed");
  assert(alias[0] == "original");
  assert(words[0] == "changed");
  words = words;
  assert(words[0] == "changed");
  assert(collection()[1].values[1] == 2);
  assert(select(0) == "innerouter");
  assert(select(2) == "innerouter");
  assert(select(9) == "outer");
  var i: i64 = 0;
  while i < 500 {
    let temporary: Row = Row(identity("row"), [i, i + 1]);
    let alias: Row = temporary;
    assert(alias.values[0] == i);
    if i % 2 == 0 { let nested: str = alias.label + str(i); assert(len(nested) > 3); }
    identity("discarded");
    i = i + 1;
  }
  let root: Tree = tree(20);
  assert(root.children[0].value == "branch");
  assert([1, 2] + [3] == [1, 2, 3]);
  assert(["x"] != ["y"]);
  assert(Row("a", [1]) != Row("b", [1]));
}
''')
        for profile in ("debug", "release"):
            self.cli("test", "--profile", profile)

    def test_data_type_and_literal_rejections(self):
        cases = [
            ('fn main() -> unit { let x: list<i64> = [1, true]; }', 'E_TYPE'),
            ('fn main() -> unit { let x: list<unit> = []; }', 'E_TYPE'),
            ('fn main() -> Missing { return 1; }', 'E_TYPE'),
            ('struct A { a: i64; a: str; } fn main() -> unit {}', 'E_DUPLICATE'),
            ('struct A { a: i64; } fn main() -> unit { A(); }', 'E_ARITY'),
            ('struct A { a: i64; } fn main() -> i64 { return A(1).b; }', 'E_FIELD'),
            ('struct A { a: i64; } struct B { a: i64; } fn main() -> bool { return A(1) == B(1); }', 'E_TYPE'),
            ('fn main() -> unit { []; }', 'E_INFER'),
            ('fn main() -> i64 { return len(1); }', 'E_TYPE'),
            ('fn main() -> i64 { return [1][true]; }', 'E_TYPE'),
            ('fn main() -> unit { let xs: list<i64> = [1]; xs[0] = 2; }', 'E_PARSE'),
            ('fn main() -> unit { let x: str = "\\q"; }', 'E_STRING'),
            ('fn main() -> unit { let x: str = "\\uD800"; }', 'E_STRING'),
            ('fn main() -> unit { let x: str = "\\uDC00"; }', 'E_STRING'),
            ('fn main() -> unit { let x: str = "\\uD800\\u0041"; }', 'E_STRING'),
            ('fn main() -> unit { let x: str = "\\u123"; }', 'E_STRING'),
            ('fn main() -> unit { let x: str = "line\nbreak"; }', 'E_STRING'),
            ('fn main() -> unit { let x: str = "unfinished; }', 'E_STRING'),
        ]
        for body, code in cases:
            with self.subTest(body=body):
                result = self.cli("check", self.source("module invalid_data; " + body), ok=False)
                self.assertEqual(result["code"], code)
        self.file.write_bytes(b'module invalid; fn main() -> unit { "\xff"; }')
        self.assertEqual(self.cli("check", ok=False)["code"], "E_UTF8")
        self.file.write_bytes(b'// comment\n// invalid: \xff\nmodule invalid; fn main() -> unit {}')
        diagnostic = self.cli("check", ok=False)
        self.assertEqual(diagnostic["code"], "E_UTF8")
        self.assertEqual((diagnostic["line"], diagnostic["column"]), (2, 13))

    def test_bounds_errors_match_in_debug_and_release(self):
        for expression in ('[1][-1]', '[1][1]', '"🦊"[1]',
                           'set([1], 1, 2)', 'set(["a"], -1, "b")',
                           'slice("A🦊Я", 1, 3)',
                           'slice("a", 9223372036854775807, 1)'):
            with self.subTest(expression=expression):
                self.source('module bounds; fn main() -> unit !{io} { print(' + expression + '); }')
                self.assertEqual(self.cli("eval", ok=False)["code"], "E_BOUNDS")
                for profile in ("debug", "release"):
                    native = self.cli("run", "--profile", profile, ok=False)
                    self.assertEqual(native["exit_code"], 70)
                    self.assertIn("E_BOUNDS", native["stderr"])

    def test_eval_returns_structured_values_and_preserves_embedded_zero(self):
        self.source('''module values;
struct Response { message: str; numbers: list<i64>; ok: bool; }
fn response() -> Response { return Response("A🦊\\u0000Я", [1, -2], true); }
fn main() -> unit !{io} { print(response().message); }
''')
        value = self.cli("eval", "--entry", "response")["value"]
        self.assertEqual(value, {"message": "A🦊\0Я", "numbers": [1, -2], "ok": True})
        self.assertEqual(self.cli("run")["stdout"], "A🦊\0Я\n")

    def test_unicode_oracle_with_escaped_literals(self):
        strings = ["", "ASCII", "🦊", "Яа", "e\u0301", "A\0B", "𐐀🌍Яz", "\\uD800", '\\"/\b\f\n\r\t']
        checks = []
        for text in strings:
            literal = json.dumps(text, ensure_ascii=True)
            checks.append("assert(len(%s) == %d);" % (literal, len(text)))
            for i, char in enumerate(text):
                checks.append("assert(%s[%d] == %s);" % (literal, i, json.dumps(char, ensure_ascii=True)))
        self.source("module unicode_oracle; fn main() -> unit {} test fn unicode_test() -> unit {" + "\n".join(checks) + "}")
        self.cli("test", "--profile", "release")

    def test_schema_and_language_migration_preserve_history(self):
        directory = self.root / ".nex"
        directory.mkdir()
        old = "a" * 64
        source = "// retained\0comment\nmodule legacy; fn main() -> i64 { return 0; }"
        with sqlite3.connect(directory / "graph.db") as db:
            db.executescript('''CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
              INSERT INTO metadata VALUES('schema','1');
              CREATE TABLE revisions(hash TEXT PRIMARY KEY,module TEXT NOT NULL,source TEXT NOT NULL,path TEXT NOT NULL,created TEXT DEFAULT 'legacy');
              CREATE TABLE head(id INTEGER PRIMARY KEY,revision TEXT NOT NULL);''')
            db.execute("INSERT INTO revisions(hash,module,source,path) VALUES(?,?,?,?)", (old, "legacy", source, str(self.file)))
            db.execute("INSERT INTO head VALUES(1,?)", (old,))
        self.assertEqual(self.cli("graph", ok=False)["code"], "E_LANGUAGE_VERSION")
        migrated = self.cli("migrate")
        self.assertEqual(migrated["language"], "0.5")
        self.assertEqual(migrated["declared_original_revision"], old)
        self.assertNotEqual(migrated["revision"], old)
        history = self.cli("history")
        self.assertEqual({r["language"] for r in history["revisions"]}, {"0.1", "0.5"})
        self.cli("export", "--revision", old, "-o", self.root / "legacy.nex")
        self.assertEqual((self.root / "legacy.nex").read_text(), source)
        self.cli("run", "--revision", "HEAD")
        legacy_graph = self.root / "legacy.json"
        legacy_graph.write_text(json.dumps({"schema": "nex.graph/1", "language": "0.1", "source": source, "revision": old}))
        self.assertEqual(self.cli("import", legacy_graph, ok=False)["code"], "E_LANGUAGE_VERSION")
        self.assertEqual(self.cli("migrate", legacy_graph)["revision"], migrated["revision"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
