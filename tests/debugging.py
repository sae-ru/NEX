"""DWARF, artifact integrity, and opt-in real LLDB/DAP interaction checks."""
import json
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import time
import unittest

LIVE = "--live" in sys.argv
if LIVE:
    sys.argv.remove("--live")
import support as harness


class Debugging(harness.ToolchainCase):
    def setUp(self):
        super().setUp()
        for file in (harness.REPO / "examples/debugging").glob("*.nex"):
            shutil.copyfile(file, self.root / file.name)

    @unittest.skipUnless(sys.platform == 'darwin', 'Darwin LLDB image-path workaround')
    def test_backslash_debug_cache_preserves_identity_and_reuses_owned_directory(self):
        project = self.root / 'project "quoted" \\ % 🧠'
        project.mkdir()
        (project / 'main.nex').write_text('''module debug_paths;
fn observe(value:i64)->unit !{io}{
 print(value);
}
fn main()->unit !{io}{observe(42);}
''')
        first = self.cli('debug', cwd=project)
        program = Path(first['launch']['program'])
        cache = program.parent.parent
        self.assertTrue(cache.name.startswith('nex-debug-'))
        self.addCleanup(shutil.rmtree, cache)
        self.assertNotIn('\\', str(program))
        self.assertEqual(cache.stat().st_mode & 0o777, 0o700)
        manifest = json.loads(Path(first['manifest']).read_text())
        self.assertEqual(manifest['program'], str(program))
        self.assertEqual(manifest['build_key'], first['build_key'])
        self.assertEqual(Path(manifest['sources'][0]['original']).read_bytes(),
                         Path(manifest['sources'][0]['projection']).read_bytes())
        second = self.cli('debug', '--kind', 'nex-dap', cwd=project)
        self.assertEqual(second['manifest'], first['manifest'])
        self.assertEqual(second['nex_adapter']['launch']['program'], str(program))
        self.assertEqual(self.cli('run', cwd=project)['stdout'], '42\n')
        if LIVE:
            stopped = self.cli('debug', '--', '--no-lldbinit', '--batch',
                               '-o', 'settings set target.disable-aslr false',
                               '-o', 'breakpoint set --file source.nex --line 3',
                               '-o', 'run', '-o', 'nex-eval value + 0', '-o', 'continue',
                               cwd=project, machine=False, timeout=60)
            self.assertIn('"value": "42"', stopped.stdout)
            self.assertIn('exited with status = 0', stopped.stdout)

        # A pointer alone cannot adopt a directory belonging to another project.
        (cache / 'owner.json').write_text('"another project"\n')
        third = self.cli('debug', cwd=project)
        repaired = Path(third['launch']['program']).parent.parent
        self.addCleanup(shutil.rmtree, repaired)
        self.assertNotEqual(repaired, cache)
        self.assertEqual((cache / 'owner.json').read_text(), '"another project"\n')
        self.assertEqual(third['revision'], first['revision'])

    def test_dwarf_types_parameters_scopes_and_semantic_agreement(self):
        built = self.cli("build")
        self.assertEqual(self.cli("run")["stdout"], self.cli("eval")["stdout"])
        self.cli("test")
        self.cli("test", "--target", "web")
        manifest = json.loads(Path(built["debug_manifest"]).read_text())
        self.assertEqual(manifest["runtime_view"], "nex.runtime-view/3")
        self.assertIn("debugging::model::Person", manifest["heap_types"])
        self.assertIn("list<str>", manifest["heap_types"])
        for source in manifest["sources"]:
            self.assertEqual(Path(source["projection"]).read_text(), Path(source["original"]).read_text())
        tools = Path(self.cli("doctor")["native_compiler"]).parent
        dwarf = str(tools / "llvm-dwarfdump")
        symbols = built["executable"] + ".dSYM" if sys.platform == "darwin" else built["executable"]
        verified = subprocess.run([dwarf, "--verify", symbols], capture_output=True, text=True, timeout=20)
        self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)
        information = subprocess.check_output([dwarf, "--debug-info", symbols], text=True, timeout=20)
        for name in ("enabled", "label", "person", "items", "reply", "failure", "empty", "next"):
            self.assertIn('("' + name + '")', information)
        self.assertIn("DW_TAG_lexical_block", information)
        self.assertIn("DW_TAG_formal_parameter", information)
        self.assertIn("DW_TAG_typedef", information)
        self.assertGreaterEqual(information.count('("total")'), 2)
        for profile in ("profile", "release"):
            self.assertEqual(self.cli("run", "--profile", profile)["stdout"], self.cli("eval")["stdout"])

    def test_debug_artifact_cache_repairs_corrupt_inputs(self):
        built = self.cli("build")
        self.assertTrue(self.cli("build")["cached"])
        manifest_file = Path(built["debug_manifest"])
        manifest = json.loads(manifest_file.read_text())
        paths = [manifest_file, Path(manifest["formatter"]), Path(manifest["dap_adapter"]), Path(manifest["sources"][0]["projection"])]
        if sys.platform == "darwin":
            paths.append(Path(built["executable"] + ".dSYM/Contents/Resources/DWARF/app"))
        for file in paths:
            original = file.read_bytes()
            file.write_bytes(b"corrupt debug artifact\n")
            restored = self.cli("build")
            self.assertFalse(restored["cached"], file)
            if file.suffix in (".json", ".py", ".nex"):
                self.assertEqual(file.read_bytes(), original, file)
            else:
                # Relinking may produce a new Mach-O UUID; verify the repaired
                # DWARF rather than requiring byte-identical linker output.
                tools = Path(self.cli("doctor")["native_compiler"]).parent
                checked = subprocess.run([str(tools / "llvm-dwarfdump"), "--verify", str(file)], capture_output=True, text=True)
                self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
            self.assertTrue(self.cli("build")["cached"])

    def test_machine_debug_session_and_frozen_sources(self):
        session = self.cli("debug", "--kind", "dap")
        self.assertEqual(session["schema"], "nex.debug-session/1")
        self.assertEqual(session["launch"]["type"], "lldb-dap")
        self.assertEqual(session["launch"]["request"], "launch")
        self.assertIn("nex-load-debug", session["launch"]["initCommands"][1])
        self.assertEqual(self.cli("debug")["launch"], session["launch"])
        self.file.unlink()
        (self.root / "model.nex").unlink()
        archived = self.cli("debug", "--revision", "HEAD")
        self.assertEqual(archived["revision"], session["revision"])
        self.assertTrue(Path(archived["launch"]["program"]).is_file())
        manifest = json.loads(Path(archived["manifest"]).read_text())
        for source in manifest["sources"]:
            self.assertTrue(Path(source["projection"]).is_file())
        self.assertEqual(self.cli("debug", "--revision", "HEAD", "--kind", "unknown", ok=False)["code"], "E_OPTION")


class DAP:
    def __init__(self, executable, directory):
        self.log = (directory / "dap-stderr.txt").open("wb")
        self.process = subprocess.Popen(executable if isinstance(executable, list) else [executable], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.log)
        self.messages = queue.Queue()
        self.pending = []
        self.sequence = 0
        def read():
            try:
                while True:
                    headers = {}
                    while True:
                        line = self.process.stdout.readline()
                        if not line:
                            return
                        if line == b"\r\n":
                            break
                        key, value = line.decode().split(":", 1)
                        headers[key.lower()] = value.strip()
                    size = int(headers["content-length"])
                    body = self.process.stdout.read(size)
                    if len(body) != size:
                        raise RuntimeError("truncated DAP body")
                    self.messages.put(json.loads(body))
            except Exception as error:
                self.messages.put(error)
            finally:
                self.messages.put(None)
        threading.Thread(target=read, daemon=True).start()

    def send(self, command, arguments=None):
        self.sequence += 1
        body = json.dumps({"seq": self.sequence, "type": "request", "command": command,
                           "arguments": arguments or {}}).encode()
        self.process.stdin.write(("Content-Length: %d\r\n\r\n" % len(body)).encode() + body)
        self.process.stdin.flush()
        return self.sequence

    def wait(self, predicate, timeout=20):
        deadline = time.monotonic() + timeout
        while True:
            for index, message in enumerate(self.pending):
                if predicate(message):
                    return self.pending.pop(index)
            message = self.messages.get(timeout=max(.01, deadline - time.monotonic()))
            if message is None or isinstance(message, Exception):
                raise RuntimeError("DAP stopped: " + str(message))
            self.pending.append(message)

    def response(self, sequence):
        response = self.wait(lambda m: m.get("type") == "response" and m.get("request_seq") == sequence)
        if not response.get("success"):
            raise RuntimeError(str(response))
        return response.get("body", {})

    def request(self, command, arguments=None):
        return self.response(self.send(command, arguments))

    def event(self, event):
        return self.wait(lambda m: m.get("type") == "event" and m.get("event") == event).get("body", {})

    def close(self):
        try:
            if self.process.poll() is None:
                self.request("disconnect", {"terminateDebuggee": True})
                self.process.wait(timeout=5)
        finally:
            if self.process.poll() is None:
                self.process.kill()
                self.process.wait(timeout=5)
            self.process.stdin.close()
            self.process.stdout.close()
            self.log.close()


if LIVE:
    class Live(Debugging):
        # Only the following two interactions are additional live cases.
        test_dwarf_types_parameters_scopes_and_semantic_agreement = None
        test_debug_artifact_cache_repairs_corrupt_inputs = None
        test_machine_debug_session_and_frozen_sources = None

        def test_lldb_stop_step_shadow_mutation_and_archive(self):
            session = self.cli("debug")
            manifest = json.loads(Path(session["manifest"]).read_text())
            projected = next(s["projection"] for s in manifest["sources"] if Path(s["original"]).name == "main.nex")
            imported = next(s["projection"] for s in manifest["sources"] if Path(s["original"]).name == "model.nex")
            report = self.root / "lldb-report.json"
            script = self.root / "verify_lldb.py"
            script.write_text('''import json, lldb
def __lldb_init_module(debugger, context):
    target = debugger.GetSelectedTarget()
    interpreter = debugger.GetCommandInterpreter()
    snapshots = []
    def snapshot():
        result = lldb.SBCommandReturnObject()
        interpreter.HandleCommand("nex-values", result)
        assert result.Succeeded(), result.GetError()
        value = json.loads(result.GetOutput())
        snapshots.append(value)
        return value
    process = None
    try:
        debugger.SetAsync(False)
        debugger.HandleCommand("settings set target.disable-aslr false")
        target.BreakpointCreateByName("nex_9_debugging_3_app_7_inspect")
        for line in (8, 12, 14, 16): target.BreakpointCreateByLocation(PROJECTED, line)
        target.BreakpointCreateByLocation(IMPORTED, 11)
        process = target.LaunchSimple(None, None, None)
        assert process.GetState() == lldb.eStateStopped
        snapshot()
        process.Continue()
        snapshot()
        process.Continue()
        snapshot()
        process.Continue()
        snapshot()
        thread = process.GetSelectedThread()
        thread.StepOver()
        assert thread.GetSelectedFrame().GetLineEntry().GetLine() == 15
        process.Continue()
        helper = snapshot()
        assert process.GetSelectedThread().GetNumFrames() >= 3
        process.Continue()
        snapshot()
        process.Continue()
        assert process.GetState() == lldb.eStateExited and process.GetExitStatus() == 0
        with open(REPORT, "w") as output: json.dump(snapshots, output)
    finally:
        if process and process.GetState() not in (lldb.eStateExited, lldb.eStateInvalid): process.Kill()
'''.replace("PROJECTED", repr(projected)).replace("IMPORTED", repr(imported)).replace("REPORT", repr(str(report))))
            self.file.unlink()
            (self.root / "model.nex").unlink()
            output = self.cli("debug", "--revision", "HEAD", "--", "--no-lldbinit", "--batch", "-o",
                              "command script import " + json.dumps(str(script)), machine=False)
            self.assertTrue(report.is_file(), output.stdout + output.stderr)
            entry, declaration, inner, outer, helper, updated = json.loads(report.read_text())
            self.assertEqual(inner["function"], "debugging::app::inspect")
            self.assertEqual(helper["function"], "debugging::model::increment")
            values = lambda snapshot, name: [v["value"] for v in snapshot["variables"] if v["name"] == name]
            self.assertEqual(values(entry, "n"), ["40"])
            self.assertEqual(values(entry, "enabled"), ["true"])
            self.assertEqual(values(entry, "total"), [])
            self.assertTrue(values(declaration, "reply"))
            self.assertEqual(values(declaration, "failure"), [])
            self.assertEqual(values(inner, "total"), ["40", "42"])
            self.assertEqual(values(outer, "total"), ["40"])
            self.assertEqual(values(updated, "total"), ["43"])
            self.assertEqual(values(inner, "enabled"), ["true"])
            self.assertEqual(values(inner, "items"), ["[40, 41]"])
            self.assertEqual(values(inner, "empty"), ["[]"])
            self.assertIn("Ада", values(inner, "label")[0])
            self.assertIn("\\0🌍", values(inner, "label")[0])
            self.assertIn('tags = ["nex", "debug"]', values(inner, "person")[0])
            self.assertIn('err("EXAMPLE",', values(inner, "failure")[0])
            self.assertIn("ok(", values(inner, "reply")[0])

        def test_string_previews_preserve_nul_literal_escapes_and_utf8_boundaries(self):
            small="A\0🌍"
            escaped="literal\\u0000\0🌍"
            cut="a"*4093+"🌍suffix"
            self.source('module string_preview; fn stop(small:str,escaped:str,cut:str) -> unit !{io} { print(small);print(escaped);print(cut); } fn main() -> unit !{io} { stop('+','.join(json.dumps(x,ensure_ascii=False) for x in (small,escaped,cut))+'); }')
            self.cli('check');symbol=self.cli('context','--symbol','stop')['native_symbol']
            self.cli('debug')
            report=self.root/'string-values.json';script=self.root/'string_capture.py'
            script.write_text('''import json, lldb
def __lldb_init_module(debugger, context):
    debugger.SetAsync(False)
    debugger.HandleCommand("settings set target.disable-aslr false")
    target=debugger.GetSelectedTarget();target.BreakpointCreateByName(SYMBOL)
    process=target.LaunchSimple(None,None,None)
    try:
        assert process.GetState()==lldb.eStateStopped
        result=lldb.SBCommandReturnObject();debugger.GetCommandInterpreter().HandleCommand("nex-values",result)
        assert result.Succeeded(),result.GetError()
        with open(REPORT,"w") as out:out.write(result.GetOutput())
        process.Continue();assert process.GetState()==lldb.eStateExited and process.GetExitStatus()==0
    finally:
        if process.GetState() not in (lldb.eStateExited,lldb.eStateInvalid):process.Kill()
'''.replace('SYMBOL',repr(symbol)).replace('REPORT',repr(str(report))))
            output=self.cli('debug','--','--no-lldbinit','--batch','-o','command script import '+json.dumps(str(script)),machine=False)
            self.assertTrue(report.is_file(),output.stdout+output.stderr)
            values={v['name']:v['value'] for v in json.loads(report.read_text())['variables']}
            self.assertEqual(values['small'],'"A\\0🌍"')
            self.assertEqual(values['escaped'],'"literal\\\\u0000\\0🌍"')
            self.assertEqual(values['cut'],'"'+'a'*4093+'…"')

        def test_dap_breakpoint_stack_variables_children_and_resume(self):
            adapter = shutil.which("lldb-dap")
            if not adapter and sys.platform == "darwin":
                adapter = subprocess.check_output(["xcrun", "--find", "lldb-dap"], text=True).strip()
            self.assertTrue(adapter, "lldb-dap is needed for --live")
            session = self.cli("debug", "--kind", "dap")
            manifest = json.loads(Path(session["manifest"]).read_text())
            source = next(s["projection"] for s in manifest["sources"] if Path(s["original"]).name == "main.nex")
            client = DAP(adapter, self.root)
            try:
                client.request("initialize", {"adapterID": "nex", "pathFormat": "path", "linesStartAt1": True, "columnsStartAt1": True,
                                              "supportsVariableType": True, "supportsVariablePaging": True})
                launch = dict(session["launch"], disableASLR=False)
                pending = client.send("launch", launch)
                client.event("initialized")
                breakpoints = client.request("setBreakpoints", {"source": {"path": source}, "breakpoints": [{"line": 12}]})
                self.assertTrue(breakpoints["breakpoints"][0]["verified"])
                client.request("configurationDone")
                client.response(pending)
                stop = client.event("stopped")
                self.assertEqual(stop["reason"], "breakpoint")
                stack = client.request("stackTrace", {"threadId": stop["threadId"]})["stackFrames"]
                self.assertEqual(stack[0]["line"], 12)
                self.assertGreaterEqual(len(stack), 3)
                scopes = client.request("scopes", {"frameId": stack[0]["id"]})["scopes"]
                variables = []
                for scope in scopes:
                    if not scope.get("expensive"):
                        variables += client.request("variables", {"variablesReference": scope["variablesReference"]})["variables"]
                self.assertTrue(any(v["name"].startswith("total") and v["value"] == "42" for v in variables), variables)
                person = next(v for v in variables if v["name"] == "person")
                self.assertIn("Ада", person["value"])
                children = client.request("variables", {"variablesReference": person["variablesReference"]})["variables"]
                self.assertEqual([v["name"] for v in children], ["id", "name", "tags"])
                self.assertEqual(children[0]["value"], "7")
                inspection = client.request("evaluate", {"expression": "`nex-values", "context": "repl", "frameId": stack[0]["id"]})
                self.assertIn('"function": "debugging::app::inspect"', inspection["result"])
                client.request("continue", {"threadId": stop["threadId"]})
                self.assertEqual(client.event("exited")["exitCode"], 0)
            finally:
                client.close()

        def test_preview_budget_for_shared_nested_collections(self):
            lines = ['module preview_budget;', 'fn main() -> i64 !{io} {', 'let level0: list<i64> = [1, 2];']
            type_name = 'list<i64>'
            for level in range(1, 7):
                type_name = 'list<' + type_name + '>'
                lines.append('let level%d: %s = [%s];' % (level, type_name, ', '.join(['level%d' % (level - 1)] * 32)))
            lines += ['print(len(level6));', 'return 0;', '}']
            self.source('\n'.join(lines))
            (self.root / 'model.nex').unlink()
            result = self.cli('debug', '--', '--no-lldbinit', '--batch', '-o', 'settings set target.disable-aslr false',
                              '-o', 'breakpoint set --file source.nex --line %d' % (len(lines) - 2), '-o', 'run',
                              '-o', 'nex-values', '-o', 'continue', machine=False, timeout=30)
            snapshots = [json.loads(line) for line in result.stdout.splitlines() if line.startswith('{"schema": "nex.debug-values/1"')]
            self.assertEqual(len(snapshots), 1, result.stdout + result.stderr)
            nested = next(v for v in snapshots[0]['variables'] if v['name'] == 'level6')
            self.assertLessEqual(len(nested['value']), 4096)
            self.assertIn('…', nested['value'])
            self.assertIn('exited with status = 0', result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
