"""Module visibility, hermetic revisions, dependency locks and relocation."""
import copy
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest
import support as harness


class Modules(harness.ToolchainCase):
    def test_language_04_result_bundle_migrates_explicitly_with_history(self):
        source='module old_results; fn endpoint(x: i64) -> i64 { return x; } fn main() -> unit { let endpoint: i64 = endpoint(42); assert(unwrap(ok(endpoint)) == 42); }'
        bundle={'schema':'nex.sources/1','entry':'main.nex','files':{'main.nex':source}}
        directory=self.root / '.nex';directory.mkdir();database=directory / 'graph.db';old='e'*64
        # Model the old, unjournaled schema directly. Rewriting HEAD after a
        # current check would instead create a corrupt schema4 database.
        with sqlite3.connect(database) as db:
            db.executescript('''CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
              INSERT INTO metadata VALUES('schema','2');
              CREATE TABLE revisions(hash TEXT PRIMARY KEY,module TEXT NOT NULL,source TEXT NOT NULL,path TEXT NOT NULL,created TEXT DEFAULT 'legacy',language TEXT NOT NULL);
              CREATE TABLE head(id INTEGER PRIMARY KEY,revision TEXT NOT NULL);''')
            db.execute('INSERT INTO revisions(hash,module,source,path,language) VALUES(?,?,?,?,?)',(old,'old_results',json.dumps(bundle),str(self.file),'0.4'))
            db.execute('INSERT INTO head VALUES(1,?)',(old,))
        self.assertEqual(self.cli('run','--revision',old,ok=False)['code'],'E_LANGUAGE_VERSION')
        self.assertEqual(self.cli('migrate')['language'],'0.18')
        self.assertEqual(self.cli('run','--revision','HEAD')['exit_code'],0)
        self.assertEqual({r['language'] for r in self.cli('history')['revisions']},{'0.4','0.18'})
        change,=self.cli('changes')['changes']
        self.assertEqual((change['action'],change['previous_revision']),('migrate',old))
        recovered=self.root / 'recovered'
        self.cli('export','--revision',old,'--directory',recovered)
        self.assertEqual(json.loads((recovered/'nex.json').read_text())['language'],'0.4')

    def test_language_03_bundle_migration_preserves_all_sources_and_history(self):
        root_source='module legacy_app; import "./format.nex" as f; fn main() -> unit !{io} { print(f::text()); }'
        library_source='module legacy_format; pub fn text() -> str { var result: str = "retained"; return result; }'
        bundle={'schema': 'nex.sources/1', 'entry': 'main.nex', 'files': {'main.nex': root_source, 'format.nex': library_source}}
        directory=self.root / '.nex';directory.mkdir();old='f'*64
        with sqlite3.connect(directory / 'graph.db') as db:
            db.executescript('''CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
              INSERT INTO metadata VALUES('schema','2');
              CREATE TABLE revisions(hash TEXT PRIMARY KEY,module TEXT NOT NULL,source TEXT NOT NULL,path TEXT NOT NULL,created TEXT DEFAULT 'legacy',language TEXT NOT NULL);
              CREATE TABLE head(id INTEGER PRIMARY KEY,revision TEXT NOT NULL);''')
            db.execute('INSERT INTO revisions(hash,module,source,path,language) VALUES(?,?,?,?,?)', (old, 'legacy_app', json.dumps(bundle), str(self.file), '0.3'))
            db.execute('INSERT INTO head VALUES(1,?)', (old,))
        self.assertEqual(self.cli('build', '--revision', old, ok=False)['code'], 'E_LANGUAGE_VERSION')
        migrated=self.cli('migrate')
        self.assertEqual(migrated['language'], '0.18')
        self.assertNotEqual(migrated['revision'], old)
        self.assertEqual({r['language'] for r in self.cli('history')['revisions']}, {'0.3', '0.18'})
        self.assertEqual(self.cli('run', '--revision', 'HEAD')['stdout'], 'retained\n')
        destination=self.root / 'recovered old project'
        self.cli('export', '--revision', old, '--directory', destination)
        self.assertEqual((destination / 'format.nex').read_text(), library_source)
        self.assertEqual((destination / 'main.nex').read_text(), root_source)

    def example(self):
        self.source((harness.REPO / "examples/modules/main.nex").read_text())
        (self.root / "model.nex").write_text((harness.REPO / "examples/modules/model.nex").read_text())

    def test_modules_standard_libraries_and_debug_origins(self):
        self.example()
        self.cli("check")
        expected = '{"name":"NEX","tags":["native","web"]}\nnative + web\n10\n'
        self.assertEqual(self.cli("eval")["stdout"], expected)
        self.assertEqual(self.cli("run")["stdout"], expected)
        tests = self.cli("test", "--profile", "release")["tests"]
        self.assertEqual({t["name"] for t in tests}, {
            "module_example::application_test", "std::math::math_test", "std::text::text_test"})
        graph = self.cli("graph")
        self.assertEqual(graph["schema"], "nex.graph/2")
        self.assertEqual({m["name"] for m in graph["modules"]}, {
            "module_example", "example::model", "std::math", "std::text"})
        context = self.cli("context", "--symbol", "example::model::create")
        self.assertEqual(context["file"], "model.nex")
        self.assertIn("pub fn create", context["source"])
        self.assertEqual(context["callees"][0]["name"], "example::model::normalize")
        self.assertEqual(context["structures"][0]["name"], "example::model::Item")
        if shutil.which("lldb"):
            session = self.cli("debug")
            manifest = json.loads(Path(session["manifest"]).read_text())
            imported = next(s for s in manifest["sources"]
                            if s["original"] == str((self.root / "model.nex").resolve()))
            debug = self.cli("debug", "--", "-b", "-o",
                             "image lookup --verbose --name " + context["native_symbol"], machine=False)
            self.assertIn(imported["debug_path"], debug.stdout)
            self.assertEqual(Path(imported["projection"]).read_text(),
                             (self.root / "model.nex").read_text())

    def test_saved_revision_does_not_reload_modified_or_missing_files(self):
        self.example()
        revision = self.cli("check")["revision"]
        (self.root / "model.nex").unlink()
        self.file.write_text("broken live source")
        result = self.cli("run", "--revision", revision)
        self.assertIn("native + web", result["stdout"])
        self.assertEqual(self.cli("context", "--symbol", "example::model::create")["revision"], revision)
        self.cli("check", ok=False)
        self.assertEqual(self.cli("history")["head"], revision)

    def test_exported_project_is_self_contained_and_relocatable(self):
        self.example()
        revision = self.cli("check")["revision"]
        destination = self.root / "relocated project"
        self.assertEqual(self.cli("export", "-o", self.root / "incomplete.nex", ok=False)["code"], "E_EXPORT")
        self.cli("export", "--directory", destination)
        self.file.unlink()
        (self.root / "model.nex").unlink()
        resources = self.root / "compiler resources"
        shutil.copytree(harness.REPO / "runtime", resources / "runtime")
        shutil.copytree(harness.REPO / "debug", resources / "debug")
        # The relocated manifest vendors std sources; no SDK lib/ exists here.
        env = {"NEX_RESOURCE_DIR": str(resources)}
        self.assertEqual(self.cli("check", cwd=destination, env=env)["revision"], revision)
        self.assertIn("native + web", self.cli("run", cwd=destination, env=env)["stdout"])
        self.cli("test", "--profile", "release", cwd=destination, env=env)
        manifest = json.loads((destination / "nex.json").read_text())
        self.assertEqual(manifest["libraries"]["std"], "_nex_deps/std")
        self.assertTrue((destination / "nex.lock.json").is_file())
        self.assertEqual(self.cli("export", "--directory", destination, ok=False)["code"], "E_EXISTS")

    def test_package_pinning_and_explicit_dependency_update(self):
        with tempfile.TemporaryDirectory(prefix="nex external library ") as library:
            package = Path(library)
            dependency = package / "numbers.nex"
            dependency.write_text("module vendor::numbers; pub fn value() -> i64 { return 1; }")
            (self.root / "nex.json").write_text(json.dumps({
                "entry": "main.nex", "libraries": {"numbers": library}}))
            self.source('module app; import "numbers/numbers.nex" as n; fn main() -> unit !{io} { print(n::value()); }')
            lock = self.cli("lock")
            self.assertEqual(set(lock["lock"]["dependencies"]), {"@pkg/numbers/numbers.nex"})
            revision = self.cli("check")["revision"]
            other = self.root / "other.nex"
            other.write_text("module other; fn main() -> unit {}")
            self.cli("check", other)
            self.assertEqual(set(self.cli("lock", other)["lock"]["dependencies"]), {"@pkg/numbers/numbers.nex"})
            dependency.write_text(dependency.read_text().replace("return 1", "return 2"))
            self.assertEqual(self.cli("check", ok=False)["code"], "E_LOCK")
            self.assertEqual(self.cli("run", "--revision", revision)["stdout"], "1\n")
            self.cli("lock")
            self.assertEqual(self.cli("run")["stdout"], "2\n")
            exported = self.root / "portable"
            self.cli("export", "--directory", exported)
            dependency.unlink()
            self.assertEqual(self.cli("run", cwd=exported)["stdout"], "2\n")

    def test_visibility_types_effects_and_realms_across_files(self):
        library = self.root / "library.nex"
        cases = [
            ('fn secret() -> i64 { return 1; }', 'lib::secret()', 'i64', 'E_VISIBILITY'),
            ('struct Hidden { value: i64; }', 'lib::Hidden(1)', 'i64', 'E_VISIBILITY'),
            ('pub fn visible() -> i64 { return 1; }', 'other::visible()', 'i64', 'E_IMPORT_ALIAS'),
            ('pub fn visible() -> i64 { return 1; }', 'lib::missing()', 'i64', 'E_NAME'),
            ('pub server fn visible() -> i64 { return 1; }', 'lib::visible()', 'i64', 'E_REALM'),
            ('pub fn visible() -> i64 !{io} { print(1); return 1; }', 'lib::visible()', 'i64', 'E_EFFECT'),
            ('struct Hidden { value: i64; } pub fn visible() -> Hidden { return Hidden(1); }', '0', 'i64', 'E_VISIBILITY'),
            ('struct Hidden { value: i64; } pub struct Public { value: Hidden; }', '0', 'i64', 'E_VISIBILITY'),
        ]
        for body, expression, result, error in cases:
            with self.subTest(body=body):
                library.write_text("module library; " + body)
                self.source('module app; import "./library.nex" as lib; fn main() -> ' + result + ' { return ' + expression + '; }')
                self.assertEqual(self.cli("check", ok=False)["code"], error)
        library.write_text('module library; fn secret() -> i64 { return 9; } pub fn visible() -> i64 { return secret(); }')
        self.source('module app; import "./library.nex" as lib; fn main() -> i64 { return lib::visible(); }')
        self.assertEqual(self.cli("eval")["value"], 9)

    def test_module_identity_aliases_and_nominal_types(self):
        (self.root / "left.nex").write_text("module left; pub struct Point { x: i64; } pub fn value() -> i64 { return 1; }")
        (self.root / "right.nex").write_text("module right; pub struct Point { x: i64; } pub fn value() -> i64 { return 2; }")
        self.source('''module app;
import "./left.nex" as a;
import "./left.nex" as duplicate;
import "./right.nex" as b;
fn main() -> unit !{io} { print(a::value()); print(b::value()); }
test fn aliases() -> unit { assert(a::Point(1) == duplicate::Point(1)); }
''')
        self.assertEqual(self.cli("run")["stdout"], "1\n2\n")
        self.cli("test")
        initial = self.cli("check")["revision"]
        self.file.write_text(self.file.read_text().replace("as a;", "as renamed;").replace("a::", "renamed::"))
        self.assertEqual(self.cli("check")["revision"], initial)
        self.source('module app; import "./left.nex" as a; import "./right.nex" as b; fn main() -> bool { return a::Point(1) == b::Point(1); }')
        self.assertEqual(self.cli("check", ok=False)["code"], "E_TYPE")

    def test_import_failures_and_file_diagnostics(self):
        self.source('module app; import "./missing.nex" as m; fn main() -> unit {}')
        self.assertEqual(self.cli("check", ok=False)["code"], "E_IMPORT_FILE")
        self.source('module app; import "../outside.nex" as m; fn main() -> unit {}')
        self.assertEqual(self.cli("check", ok=False)["code"], "E_IMPORT_PATH")
        self.source('module app; import "unknown/library.nex" as m; fn main() -> unit {}')
        self.assertEqual(self.cli("check", ok=False)["code"], "E_IMPORT_PACKAGE")
        library = self.root / "library.nex"
        library.write_text('module library; import "./main.nex" as app; pub fn value() -> i64 { return 1; }')
        self.source('module app; import "./library.nex" as m; fn main() -> unit {}')
        self.assertEqual(self.cli("check", ok=False)["code"], "E_IMPORT_CYCLE")
        library.write_text('module app; pub fn value() -> i64 { return 1; }')
        self.assertEqual(self.cli("check", ok=False)["code"], "E_MODULE_DUPLICATE")
        library.write_text('module library; pub fn value() -> i64 { return true; }')
        error = self.cli("check", ok=False)
        self.assertEqual(error["code"], "E_TYPE")
        self.assertEqual(error["file"], "library.nex")
        self.source('module app; import "./library.nex" as m; import "./library.nex" as m; fn main() -> unit {}')
        self.assertEqual(self.cli("check", ok=False)["code"], "E_IMPORT_ALIAS")

    def test_atomic_cross_module_patches_and_fragment_boundaries(self):
        library = self.root / "library.nex"
        library.write_text("module library; pub fn value() -> i64 { return 1; }")
        self.source('module app; import "./library.nex" as lib; fn get() -> i64 { return lib::value(); } fn main() -> unit !{io} { print(get()); }')
        revision = self.cli("check")["revision"]
        patch = self.root / "patch.json"
        patch.write_text(json.dumps({"expected_revision": revision, "replacements": [
            {"name": "library::value", "source": 'pub fn value() -> str { return "two"; }'},
            {"name": "app::get", "source": 'fn get() -> str { return lib::value(); }'}]}))
        applied = self.cli("apply", "--patch", patch)
        self.assertNotEqual(applied["revision"], revision)
        self.assertEqual(self.cli("run", "--revision", "HEAD")["stdout"], "two\n")
        self.assertIn("return 1", library.read_text())
        context = self.cli("context", "--symbol", "library::value")
        self.assertEqual(context["file"], "library.nex")
        for fragment in ('fn value() -> str { return "two"; }',
                         'pub fn value() -> str { return "two"; } struct Injected { x: i64; }'):
            patch.write_text(json.dumps({"expected_revision": applied["revision"], "replacements": [
                {"name": "library::value", "source": fragment}]}))
            result = self.cli("apply", "--patch", patch, ok=False)
            self.assertIn(result["code"], {"E_VISIBILITY", "E_PATCH"})
            self.assertEqual(self.cli("history")["head"], applied["revision"])

    def test_imported_bundle_integrity_and_unreachable_files(self):
        self.example()
        self.cli("check")
        graph = self.cli("graph")
        file = self.root / "graph.json"
        changed = copy.deepcopy(graph)
        changed["bundle"]["files"]["model.nex"] += "\nfn added() -> i64 { return 9; }\n"
        file.write_text(json.dumps(changed))
        self.assertEqual(self.cli("import", file, ok=False)["code"], "E_REVISION")
        changed = copy.deepcopy(graph)
        changed["bundle"]["files"]["unused.nex"] = "module unused;"
        file.write_text(json.dumps(changed))
        self.assertEqual(self.cli("import", file, ok=False)["code"], "E_BUNDLE")
        changed = copy.deepcopy(graph)
        changed["bundle"]["files"]["../escape.nex"] = "module escape;"
        file.write_text(json.dumps(changed))
        self.assertEqual(self.cli("import", file, ok=False)["code"], "E_IMPORT_PATH")
        file.write_text(json.dumps(graph))
        self.cli("import", file)

    def test_unicode_module_paths_and_stable_library_nodes(self):
        library = self.root / "数学.nex"
        library.write_text('module math; pub fn answer() -> i64 { return 42; }')
        self.source('module first; import "./数学.nex" as math; fn main() -> unit !{io} { print(math::answer()); }')
        self.cli("check")
        before = self.cli("graph")
        node = next(n for n in before["nodes"] if n["name"] == "math::answer")
        self.assertEqual(self.cli("run")["stdout"], "42\n")
        self.file.write_text(self.file.read_text().replace("module first;", "module second;"))
        self.cli("check")
        after = next(n for n in self.cli("graph")["nodes"] if n["name"] == "math::answer")
        self.assertEqual(node["id"], after["id"])
        self.assertEqual(node["hash"], after["hash"])

    def test_export_avoids_collisions_with_project_source_directories(self):
        directory = self.root / "_nex_deps/std"
        directory.mkdir(parents=True)
        (directory / "math.nex").write_text("module local_math; pub fn value() -> i64 { return 42; }")
        self.source('''module app;
import "./_nex_deps/std/math.nex" as local;
import "std/math.nex" as math;
fn main() -> unit !{io} { print(local::value()); print(math::max(1, 2)); }
''')
        revision = self.cli("check")["revision"]
        destination = self.root / "exported"
        self.cli("export", "--directory", destination)
        self.assertEqual(json.loads((destination / "nex.json").read_text())["libraries"]["std"], "_nex_deps_1/std")
        self.assertEqual(self.cli("check", cwd=destination)["revision"], revision)
        self.assertEqual(self.cli("run", cwd=destination)["stdout"], "42\n2\n")


if __name__ == "__main__":
    unittest.main(verbosity=2)
