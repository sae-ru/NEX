"""Exact Java long domain: JDK observations, checked NEX and actual backends."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import unittest
import support as h
import standard_library as helpers
from java_long_cases import cases, mathematical, source

FIXTURE = h.REPO/'tests/fixtures/java-long'
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()


class JavaLong(h.ToolchainCase):
    run_child = helpers.StandardLibrary.run_child
    strict_ts = helpers.StandardLibrary.strict_ts
    typescript = helpers.StandardLibrary.typescript

    def test_compiled_catalogue_matches_public_source(self):
        cap = self.cli('describe', '--field', 'standard_library.modules.java_long')['value']
        path = h.REPO/cap['resource']
        self.assertEqual(sha(path), cap['sha256'])
        self.assertEqual(set(re.findall(r'\bpub\s+fn\s+(\w+)', path.read_text())), set(cap['functions']))
        self.assertEqual(len(cap['functions']), 21)
        self.assertEqual(cap['import'], 'std/java_long.nex')
        self.assertFalse(cap['native_primitive_type'])

    def test_live_and_frozen_JDK_match_independent_model(self):
        fixture = json.loads((FIXTURE/'oracle.json').read_text())
        self.assertEqual(fixture['oracle_source_sha256'], sha(FIXTURE/'Oracle.java'))
        self.assertEqual(fixture['inputs'], cases())
        self.assertEqual(fixture['outputs'], list(map(mathematical, cases())))
        home = os.environ.get('NEX_JAVA_HOME')
        if home:
            tools = Path(home)/'bin';suffix = '.exe' if os.name == 'nt' else ''
            self.run_child([tools/('javac'+suffix), '-d', self.root, FIXTURE/'Oracle.java'])
            raw = ''.join(' '.join(map(str, row))+'\n' for row in cases())
            result = subprocess.run([str(tools/('java'+suffix)), '-cp', str(self.root), 'Oracle'],
                                    input=raw, capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.splitlines(), fixture['outputs'])
            print(json.dumps({'live_JDK': True, 'cases': len(cases()),
                              'version': self.run_child([tools/('java'+suffix), '--version'])}))

    def test_latest_source_backends_and_checked_arithmetic(self):
        (self.root/'nex.json').write_text('{"schema":"nex.project/1","language":"0.30","entry":"main.nex"}\n')
        fixture = json.loads((FIXTURE/'oracle.json').read_text());pin = sha(h.NEX)
        self.source(source(fixture['outputs']));checked = self.cli('check')
        reference = self.cli('eval', '--steps', '10000000', timeout=180)
        self.assertEqual(reference['stdout'], 'java-long-oracle-ok\n')
        native = {}
        for profile in ('debug', 'release'):
            native[profile] = self.cli('run', '--profile', profile, timeout=240)
            self.assertEqual(native[profile]['stdout'], reference['stdout'])
        self.assertEqual(self.typescript(), reference['stdout'])
        self.assertEqual(self.cli('eval', '--entry', 'checked_overflow', ok=False)['code'], 'E_OVERFLOW')
        for profile in ('debug', 'release'):
            self.assertIn('E_OVERFLOW', self.cli('run', '--entry', 'checked_overflow', '--profile', profile,
                                               ok=False, timeout=240)['stderr'])
        self.assertEqual(self.typescript('checked_overflow', failure='E_OVERFLOW'), 'E_OVERFLOW')
        self.assertEqual(sha(h.NEX), pin)
        report = {'schema': 'nex.java-long-agreement/1', 'ok': True, 'language': '0.30',
                  'compiler_sha256': pin, 'revision': checked['revision'],
                  'program_sha256': sha(self.file), 'cases': len(cases()),
                  'oracle_sha256': sha(FIXTURE/'oracle.json'), 'reference': reference,
                  'native': native, 'strict_executed_typescript': True,
                  'ordinary_checked_overflow_preserved': True}
        destination = os.environ.get('NEX_JAVA_LONG_REPORT')
        if destination: Path(destination).write_text(json.dumps(report, indent=2)+'\n')
        print(json.dumps(report))

    def test_nominal_types_effects_and_wire(self):
        (self.root/'nex.json').write_text('{"schema":"nex.project/1","language":"0.30","entry":"main.nex"}\n')
        for body, code in [
            ('longs::add(1,longs::from_i64(2));', 'E_TYPE'),
            ('longs::add(ints::from_i64(1),longs::from_i64(2));', 'E_TYPE'),
            ('longs::from_int(longs::from_i64(1));', 'E_TYPE'),
            ('longs::divide(longs::from_i64(1),longs::from_i64(0));', 'E_EFFECT')]:
            with self.subTest(body=body):
                self.source('module rejected;import "std/java_long.nex" as longs;import "std/java_int.nex" as ints;fn main()->unit{'+body+'}')
                self.assertEqual(self.cli('check', ok=False)['code'], code)
        self.source('''module long_wire;import "std/java_long.nex" as longs;
fn main()->unit!{io}{
 let minimum:longs::Int64=longs::from_i64(-9223372036854775808);
 let maximum:longs::Int64=longs::from_i64(9223372036854775807);
 assert(unwrap(decode_json<longs::Int64>(encode_json(minimum)))==minimum);
 assert(unwrap(decode_json<longs::Int64>(encode_json(maximum)))==maximum);
 print(encode_json(minimum));print(encode_json(maximum));
}''')
        expected = '{"value":"-9223372036854775808"}\n{"value":"9223372036854775807"}\n'
        self.assertEqual(self.cli('eval')['stdout'], expected)
        self.assertEqual(self.cli('run', '--profile', 'release', timeout=240)['stdout'], expected)
        self.assertEqual(self.typescript(), expected)


if __name__ == '__main__': unittest.main()
