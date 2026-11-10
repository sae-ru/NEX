"""Real configured label selection plus negative fixture/metadata controls."""
import argparse
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

parser=argparse.ArgumentParser();parser.add_argument('--build',type=Path,required=True);parser.add_argument('--ctest',required=True);parser.add_argument('--cmake',required=True)
args=parser.parse_args();ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('nex_tier_inventory',ROOT/'tools/ctest_tiers.py')
tool=importlib.util.module_from_spec(spec);spec.loader.exec_module(tool)
POLICY=tool.policy((ROOT/'cmake/test-tiers.json').read_bytes())


class Tiers(unittest.TestCase):
    def test_actual_core_filter_has_exact_declared_groups_and_no_fixture_injection(self):
        full=json.loads(subprocess.check_output([args.ctest,'--test-dir',str(args.build),'--show-only=json-v1'],timeout=20))
        selected=json.loads(subprocess.check_output([args.ctest,'--test-dir',str(args.build),'--show-only=json-v1','-L','^core$'],timeout=20))
        result=tool.inspect(POLICY,full);expected=set(result['tiers']['core']['selected_groups'])
        self.assertEqual({test['name']for test in selected['tests']},expected)
        self.assertFalse(result['tiers']['core']['fixture_groups_added']);self.assertGreaterEqual(len(expected),8)
        self.assertLessEqual(len(expected),16);self.assertEqual(result['unlabelled_groups'],[])

    def test_unclassified_unlabelled_disabled_and_browser_core_commands_reject(self):
        value={'schema':'nex.ctest-tiers/1','labels':{x:x for x in tool.LABELS},'tests':{'quick':['core'],'long':['extended','browser']}}
        registry={'tests':[{'name':'quick','command':['python','quick.py'],'properties':[{'name':'LABELS','value':['core']}]},
                           {'name':'long','command':['python','long.py'],'properties':[{'name':'LABELS','value':['extended','browser']}]}]}
        self.assertTrue(tool.inspect(value,registry)['ok'])
        for mutate in [lambda x:x['tests'][0].update(name='unlisted'),
                       lambda x:x['tests'][0].update(properties=[]),
                       lambda x:x['tests'][0]['properties'].append({'name':'DISABLED','value':True}),
                       lambda x:x['tests'][0].update(command=['node','quick.js'])]:
            changed=copy.deepcopy(registry);mutate(changed)
            with self.assertRaises(ValueError):tool.inspect(value,changed)
        registry['tests'][0]['properties'].append({'name':'FIXTURES_REQUIRED','value':['prepare']})
        registry['tests'][1]['properties'].append({'name':'FIXTURES_SETUP','value':['prepare']})
        with self.assertRaisesRegex(ValueError,'fixture'):tool.inspect(value,registry)

    def test_ambiguous_policy_and_mixed_core_labels_reject(self):
        for raw in [b'{"schema":1,"schema":2}',b'{"x":NaN}',b'\xff']:
            with self.assertRaises(ValueError):tool.policy(raw)
        changed=copy.deepcopy(POLICY);name=next(k for k,v in changed['tests'].items()if v==['core'])
        changed['tests'][name].append('browser')
        with self.assertRaises(ValueError):tool.policy(json.dumps(changed).encode())

    def test_configure_rejects_a_new_unclassified_test(self):
        with tempfile.TemporaryDirectory(prefix='nex-tier-unknown-')as temporary:
            root=Path(temporary);source=root/'source';source.mkdir()
            def quoted(path):return json.dumps(Path(path).as_posix()).replace('$','\\$')
            (source/'CMakeLists.txt').write_text('cmake_minimum_required(VERSION 3.25)\nproject(TierFixture NONE)\nenable_testing()\n'
                +'set(Python3_EXECUTABLE '+quoted(sys.executable)+')\n'
                +'add_test(NAME unclassified_future_group COMMAND '+quoted(sys.executable)+' -c "pass")\n'
                +'include('+quoted(ROOT/'cmake/TestTiers.cmake')+')\n')
            result=subprocess.run([args.cmake,'-S',str(source),'-B',str(root/'build')],capture_output=True,timeout=20)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('Classify CTest',result.stderr.decode());self.assertIn('unclassified_future_group',result.stderr.decode())


if __name__=='__main__':unittest.main(argv=[__file__,'-v'])
