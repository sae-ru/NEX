"""Opt-in genuine core frames must belong to the loaded NEX manifest image."""
import json
from pathlib import Path
import sys
import unittest

LIVE = '--live' in sys.argv
if LIVE:
    sys.argv.remove('--live')
import support as harness

SOURCE = '''module image_binding;
fn observe(value:i64,text:str,items:list<i64>)->unit !{io}{
 let answer:i64=value+items[1];
 print(answer); // IMAGE_STOP
}
fn main()->unit !{io}{observe(40,"Я🧠",[1,2,3]);}
'''


class DebugImage(harness.ToolchainCase):
    @unittest.skipUnless(LIVE, 'use --live for actual LLDB core image identity')
    def test_same_named_frame_in_another_image_cannot_use_the_selected_manifest(self):
        self.source(SOURCE)
        original = self.cli('debug', '--kind', 'nex-dap')
        core = self.root / 'process.core'
        captured = self.cli('debug', '--', '--no-lldbinit', '--batch',
            '-o', 'settings set target.disable-aslr false',
            '-o', 'breakpoint set --file source.nex --line 4', '-o', 'run',
            '-o', 'process save-core --style modified-memory ' + json.dumps(str(core)),
            '-o', 'continue', machine=False, timeout=90)
        self.assertIn('exited with status = 0', captured.stdout)
        self.assertTrue(core.is_file())
        self.assertLess(core.stat().st_size, 16 * 1024 * 1024)

        # Run all commands even when one reports an error, so values and
        # operation reports cannot silently retain weaker image checks.
        probe = self.root / 'probe.py'
        commands = ['nex-values', 'nex-operation', 'nex-eval text + str(items[1])']
        probe.write_text('''import json,lldb
COMMANDS=''' + repr(commands) + '''
def __lldb_init_module(debugger, context):
    process=debugger.GetSelectedTarget().GetProcess()
    before=[process.GetProcessID(),process.GetStopID(),process.GetSelectedThread().GetThreadID()]
    records=[]
    for command in COMMANDS:
        result=lldb.SBCommandReturnObject()
        debugger.GetCommandInterpreter().HandleCommand(command,result)
        records.append({'command':command,'success':result.Succeeded(),'output':result.GetOutput(),'error':result.GetError()})
    after=[process.GetProcessID(),process.GetStopID(),process.GetSelectedThread().GetThreadID()]
    print('NEX_IMAGE_PROBE '+json.dumps({'records':records,'before':before,'after':after},ensure_ascii=False))
''')

        def inspect(*args):
            process = self.cli('debug', *args, '--', '--no-lldbinit', '--batch',
                '--core', core, '-o', 'command script import ' + json.dumps(str(probe)),
                machine=False, timeout=90)
            records = [json.loads(line[len('NEX_IMAGE_PROBE '):])
                for line in process.stdout.splitlines() if line.startswith('NEX_IMAGE_PROBE ')]
            self.assertEqual(len(records), 1, process.stdout + process.stderr)
            self.assertEqual(records[0]['before'], records[0]['after'])
            return records[0]['records']

        self.file.unlink()
        matching = inspect('--revision', original['revision'])
        self.assertTrue(all(r['success'] for r in matching), matching)
        values, operation, watch = [json.loads(r['output']) for r in matching]
        self.assertEqual(values['revision'], original['revision'])
        self.assertEqual(operation['revision'], original['revision'])
        self.assertEqual(watch['value'], 'Я🧠2')
        self.assertEqual(watch['revision'], original['revision'])
        self.assertFalse(self.file.exists())

        self.source(SOURCE.replace('observe(40,"Я🧠",[1,2,3])',
            'observe(100,"Different",[10,20,30])'))
        other = self.cli('debug', '--kind', 'nex-dap')
        self.assertNotEqual(other['revision'], original['revision'])
        self.assertNotEqual(other['launch']['program'], original['launch']['program'])
        mismatched = inspect()
        for record in mismatched:
            self.assertFalse(record['success'], 'accepted a frame from another image: ' + str(record))
            self.assertIn('image', record['error'])
            self.assertFalse(record['output'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
