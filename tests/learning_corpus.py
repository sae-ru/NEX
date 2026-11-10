"""Actual current learning corpus, backend observations and guarded publication."""
import copy
import json
import os
from pathlib import Path
import sys
import unittest
import support as h
sys.path.insert(0,str(h.REPO/'tools/llm'))
import learning_corpus as tool


class LearningCorpus(h.ToolchainCase):
    def test_actual_frontends_three_backends_and_preserved_counterexamples(self):
        output=Path(os.environ['NEX_LEARNING_OUTPUT'])if os.environ.get('NEX_LEARNING_OUTPUT')else self.root/'validation'
        node=os.environ.get('NEX_NODE')or __import__('shutil').which('node');tsc=os.environ.get('NEX_TSC')or str(h.REPO/'web/node_modules/typescript/bin/tsc')
        report,spec=tool.validate(Path(h.NEX),h.REPO,output,node,tsc)
        self.assertTrue(report['ok'],report['errors']);self.assertEqual(report['language'],h.CURRENT_LANGUAGE)
        self.assertEqual(report['valid_projects'],9);self.assertEqual(report['rejected_programs'],6)
        self.assertTrue(report['successful_workspace_removed']);self.assertFalse(Path(report['workspace']).exists())
        self.assertEqual(len(report['commands']),78)
        destination=output/'labels.json';tool.publish(report,spec,destination,h.REPO,output/'report.json')
        corpus=json.loads(destination.read_bytes());self.assertEqual(corpus['schema'],'nex.learning-corpus/2');self.assertEqual(corpus['validation_status'],'passed')
        self.assertEqual(corpus['validation']['report_sha256'],tool.pack_tool.sha(output/'report.json'))
        bad=copy.deepcopy(report);bad['ok']=False
        with self.assertRaises(ValueError):tool.publish(bad,spec,self.root/'must-not-publish.json',h.REPO,output/'report.json')
        self.assertFalse((self.root/'must-not-publish.json').exists())
        bad=copy.deepcopy(report);bad['cases'][0]['observations'].pop()
        with self.assertRaises(ValueError):tool.publish(bad,spec,self.root/'incomplete.json',h.REPO,output/'report.json')
        self.assertFalse((self.root/'incomplete.json').exists())
        if os.environ.get('NEX_LEARNING_OUTPUT'):print('Verified learning labels: '+str(destination))

    def test_input_definition_rejects_drift_and_escaping_paths(self):
        spec=json.loads((h.REPO/'llm/corpus-spec.json').read_bytes());cases,pins=tool.read_inputs(h.REPO,spec);self.assertEqual(len(cases),15)
        self.assertIn('examples/learn/modules/operations.nex',pins)
        for value in ['../outside','/absolute','']:
            with self.assertRaises(ValueError):tool.contained(h.REPO,value)
        for changed in [dict(spec,language='old'),dict(spec,examples=spec['examples']+[spec['examples'][0]])]:
            with self.assertRaises(ValueError):tool.read_inputs(h.REPO,changed)
        skipped={'ok':True,'tests':[{'skipped':True}]}
        self.assertFalse(tool.tests_passed(skipped,1,'typescript'))
        changed=copy.deepcopy(spec);changed['examples'][0]['expected_tests']=True
        with self.assertRaises(ValueError):tool.read_inputs(h.REPO,changed)


if __name__=='__main__':unittest.main(argv=[__file__,'-v'])
