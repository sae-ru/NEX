"""Bounded native runtime benchmark command and baseline comparison."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

COMPILER=Path(sys.argv.pop(1)).resolve()
SOURCE='''module bench_case;
fn main() -> i64 !{io} {
  var i: i64 = 0;
  var total: i64 = 0;
  while i < 10000 { total = total + i; i = i + 1; }
  print(total);
  return 0;
}
'''


def run(args,cwd,timeout=300):
    return subprocess.run(list(map(str,[COMPILER]+args)),cwd=cwd,capture_output=True,text=True,timeout=timeout)


class Bench(unittest.TestCase):
    def test_runtime_samples_baseline_output_and_rejections(self):
        with tempfile.TemporaryDirectory(prefix='nex bench ') as temporary:
            root=Path(temporary)
            (root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.28','entry':'main.nex'})+'\n')
            (root/'main.nex').write_text(SOURCE)
            result=run(['bench','--repetitions','2','--warmup','0','--json'],root)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            report=json.loads(result.stdout)
            self.assertEqual(report['schema'],'nex.bench/1')
            self.assertEqual(report['mode'],'runtime')
            self.assertEqual(report['profile'],'release')
            self.assertEqual(report['repetitions'],2)
            self.assertEqual(report['warmup'],0)
            self.assertEqual(report['exit_codes'],[0,0])
            self.assertEqual(len(report['samples_seconds']),2)
            self.assertGreater(report['median_seconds'],0)
            self.assertLessEqual(report['min_seconds'],report['median_seconds'])
            self.assertLessEqual(report['median_seconds'],report['max_seconds'])
            self.assertEqual(report['stdout_bytes'],len(b'49995000\n'))
            self.assertEqual(len(report['stdout_sha256']),64)
            self.assertTrue(report['build_key'])
            self.assertTrue(report['source_revision'])
            self.assertEqual(report['toolchain'],json.loads(subprocess.check_output([COMPILER,'describe','--kind','index','--json'],text=True))['toolchain'])
            output=root/'report.json'
            written=run(['bench','--repetitions','1','--warmup','0','--output',output],root)
            self.assertEqual(written.returncode,0,written.stdout+written.stderr)
            self.assertTrue(output.is_file())
            baseline=json.loads(output.read_text())
            compared=run(['bench','--repetitions','2','--warmup','0','--baseline',output,'--json'],root)
            self.assertEqual(compared.returncode,0,compared.stdout+compared.stderr)
            comparison=json.loads(compared.stdout)
            self.assertIn('baseline',comparison)
            self.assertAlmostEqual(comparison['baseline']['delta_seconds'],
                comparison['median_seconds']-baseline['median_seconds'],places=12)
            for args in (['bench','--kind','build','--json'],['bench','--repetitions','0','--json']):
                rejected=run(args,root)
                self.assertNotEqual(rejected.returncode,0)
                diagnostic=json.loads(rejected.stdout)
                self.assertEqual(diagnostic['code'],'E_OPTION')


if __name__=='__main__':unittest.main()
