"""Pure request descriptions, checked adapter signatures and transport outcomes."""
import os
from pathlib import Path
import shutil
import subprocess
import unittest
import support as harness


class Commands(harness.ToolchainCase):
    def prepare(self):
        for name in ('client.nex', 'model.nex'):
            shutil.copyfile(harness.REPO / 'examples/fullstack' / name, self.root / name)
        self.file = self.root / 'client.nex'
        return self.file

    def test_pure_command_transitions_and_client_reachability(self):
        self.prepare()
        self.cli('test', self.file, '--target', 'web')
        original = self.file.read_text()
        self.file.write_text(original.replace('client fn', 'shared fn').replace('client test fn', 'shared test fn'), newline="\n")
        self.cli('test', self.file)
        self.file.write_text(original, newline="\n")
        output = self.root / 'generated'
        self.cli('web', self.file, '--directory', output)
        source = (output / 'src/program.ts').read_text()
        self.assertIn('as commands', source)
        self.assertNotIn('SERVER_ONLY_FULLSTACK_SENTINEL', source)
        self.assertNotIn('runtime-token', source)  # test literals are unreachable
        shutil.copyfile(harness.REPO / 'tests/net-runner.ts', output / 'src/check.ts')
        checked = subprocess.run([os.environ.get('NEX_NODE', 'node'), '--experimental-strip-types', '--no-warnings', str(output / 'src/check.ts')],
                                 capture_output=True, text=True, timeout=30)
        self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

    def test_command_contract_rejects_wrong_state_effects_and_library_shape(self):
        self.prepare()
        original = self.file.read_text().split('client test fn')[0]
        for invalid in [
            original.replace('commands(before: State, after: State, event: web::Event)', 'commands(before: i64, after: State, event: web::Event)').replace('before.pending', 'after.pending'),
            original.replace('client fn commands', 'server fn commands'),
            original.replace('-> list<net::Command> {', '-> list<net::Command> !{io} {'),
        ]:
            self.file.write_text(invalid, newline="\n")
            self.assertEqual(self.cli('web', self.file, '--directory', self.root / 'output', ok=False)['code'], 'E_WEB_SIGNATURE')
        self.file.write_text(original, newline="\n")
        library = self.root / 'custom-net.nex'
        source = (harness.REPO / 'lib/net.nex').read_text().replace('import "./web.nex"', 'import "std/web.nex"')
        library.write_text(source.replace('timeout_ms: i64;', 'timeout_ms: i64; extra: str;').replace('action, timeout_ms)', 'action, timeout_ms, "")').replace('"", 0)', '"", 0, "")'), newline="\n")
        self.file.write_text(original.replace('"std/net.nex"', '"./custom-net.nex"'), newline="\n")
        self.assertEqual(self.cli('web', self.file, '--directory', self.root / 'output', ok=False)['code'], 'E_WEB_SIGNATURE')


if __name__ == '__main__':
    unittest.main(verbosity=2)
