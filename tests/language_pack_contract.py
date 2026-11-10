"""All shared capabilities agree, including previously unchecked fields and types."""
import copy
import importlib.util
from pathlib import Path
import unittest
import support as h
spec=importlib.util.spec_from_file_location('nex_language_pack',h.REPO/'tools/llm/language_pack.py');tool=importlib.util.module_from_spec(spec);spec.loader.exec_module(tool)


class LanguagePack(h.ToolchainCase):
    def test_every_declared_shared_field_is_required_and_exact(self):
        import json
        pack=json.loads((h.REPO/'llm/language-pack.json').read_bytes());descriptor=self.cli('describe');index=self.cli('describe','--kind','index')
        proof=tool.compare(pack,descriptor,index);self.assertTrue(proof['ok'],proof);self.assertGreater(proof['shared_field_count'],50)
        for key in proof['shared_fields']:
            changed=copy.deepcopy(pack);del changed[key];self.assertFalse(tool.compare(changed,descriptor,index)['ok'],key)
        for value in [False,1,'true',None]:
            changed=copy.deepcopy(pack);changed['runtime_diagnostic_messages']['embedded_NUL_preserved']=value
            rejected=tool.compare(changed,descriptor,index);self.assertFalse(rejected['ok'],rejected)
            self.assertTrue(any(x['path']=='runtime_diagnostic_messages.embedded_NUL_preserved'for x in rejected['errors']))
        changed=copy.deepcopy(pack);changed['language_version']='old';self.assertFalse(tool.compare(changed,descriptor,index)['ok'])
        changed=copy.deepcopy(pack);changed['unregistered_shared']=True;expanded=copy.deepcopy(descriptor);expanded['unregistered_shared']=True
        self.assertFalse(tool.compare(changed,expanded,index)['ok'])
        # Distinct envelope schemas and document indexes are intentional.
        changed=copy.deepcopy(pack);changed['documents']['local_note']='example.md';self.assertTrue(tool.compare(changed,descriptor,index)['ok'])
        self.assertFalse((self.root/'.nex').exists())

    def test_legacy_summary_is_marked_without_removing_its_values(self):
        full=self.cli('describe');index=self.cli('describe','--kind','index');legacy=self.cli('describe','--field','features')
        self.assertEqual(legacy['value'],full['features']);self.assertIn('functions',legacy['value'])
        self.assertFalse(legacy['value_complete']);self.assertEqual(legacy['value_scope'],'legacy_partial_summary')
        self.assertEqual(legacy['capability_index_command'],'nex describe --kind index --json')
        self.assertIn('features',index['legacy_fields']);self.assertTrue(set(index['recommended_fields'])<=set(index['fields']))
        self.assertIn('source_contracts',index['recommended_fields']);self.assertIn('generic_features',index['recommended_fields'])
        self.assertFalse(full['features_scope']['complete']);self.assertEqual(full['features_scope']['recommended_fields'],index['recommended_fields'])
        self.assertNotIn('value_scope',self.cli('describe','--field','types'))

    def test_ambiguous_json_is_rejected(self):
        for raw in [b'{"x":1,"x":2}',b'{"x":NaN}',b'{"x":Infinity}',b'\xff']:
            with self.assertRaises(ValueError):tool.parse(raw)


if __name__=='__main__':unittest.main(argv=[__file__,'-v'])
