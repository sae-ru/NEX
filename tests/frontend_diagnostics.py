"""Captured compiler inputs, rejected candidates and frame-bound watch errors."""
import base64
import copy
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import unittest
import support as harness
import expressions as expression_harness

SOURCE='module frontend;\nfn value()->i64{return 42;}\nfn main()->unit!{io}{print(value());}\n'

class FrontendDiagnostics(harness.ToolchainCase):
    def ready(self):
        (self.root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.19','entry':'main.nex'}))
        self.source(SOURCE);return self.cli('check')['revision']

    def rows(self):
        with sqlite3.connect(self.root/'.nex/graph.db') as db:
            names=[n for n, in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")]
            return {n:sorted(db.execute('SELECT * FROM "'+n.replace('"','""')+'"').fetchall(),key=repr) for n in names}

    def frontend(self,error,phase,kind='project',complete=None):
        self.assertEqual(error['schema'],'nex.diagnostic/1');value=error['frontend']
        self.assertEqual(value['schema'],'nex.frontend-diagnostic/1');self.assertEqual(value['phase'],phase)
        self.assertEqual(value['input_kind'],kind);self.assertEqual(len(value['id']),64)
        self.assertEqual(len(value['source_inputs_hash']),64);self.assertEqual(value['language'],'0.19')
        if complete is not None:self.assertEqual(value['source_inputs_complete'],complete)
        self.assertNotIn('operation_id',value);self.assertNotIn('revision',value)
        return value

    def preview(self,context):
        preview=context['preview'];data=preview['data']
        raw=data.encode() if preview['encoding']=='utf-8' else base64.b64decode(data,validate=True)
        self.assertEqual(len(raw),preview['byte_end']-preview['byte_begin']);self.assertLessEqual(len(raw),4096)
        return raw

    def patch(self,revision,source,operation=False):
        value={'expected_revision':revision,'replacements':[{'name':'value','source':source}]}
        if operation:
            page=self.cli('operations','--symbol','value')
            node=next(n for n in page['nodes'] if n['kind']=='expression.integer')
            value['expected_source_hash']=page['source_hash'];value['replacements']=[{'operation_id':node['id'],'source':source}]
        path=self.root/'patch.json';path.write_text(json.dumps(value));return path

    def test_parse_error_captures_actual_file_and_partial_closure(self):
        self.ready();before=self.rows();text='module broken;\nfn main()->unit{return }'
        self.source(text);error=self.cli('check',ok=False);context=self.frontend(error,'parse',complete=False)
        self.assertEqual(context['input_files'],1);self.assertEqual(self.preview(context),text.encode())
        self.assertEqual(context['source']['key']['data'],'main.nex');self.assertEqual(self.rows(),before)

    def test_dependency_parse_error_captures_all_inputs_read_before_failure(self):
        self.ready();self.source('module app;import "./library.nex" as lib;fn main()->unit{}')
        library=self.root/'library.nex';library.write_text('module library;pub fn bad()->i64{return }')
        first=self.frontend(self.cli('check',ok=False),'parse',complete=False)
        self.assertEqual(first['input_files'],2);self.assertEqual(first['source']['key']['data'],'library.nex')
        self.assertEqual(self.preview(first),library.read_bytes())
        self.file.write_text('// changed context\n'+self.file.read_text())
        second=self.frontend(self.cli('check',ok=False),'parse',complete=False)
        self.assertEqual(first['source']['hash'],second['source']['hash']);self.assertNotEqual(first['source_inputs_hash'],second['source_inputs_hash'])

    def test_binding_error_has_complete_source_closure_and_no_new_graph_rows(self):
        self.ready();before=self.rows();self.source('module app;import "./library.nex" as lib;fn main()->unit{lib::missing();}')
        (self.root/'library.nex').write_text('module library;pub fn value()->i64{return 42;}')
        context=self.frontend(self.cli('check',ok=False),'bind',complete=True)
        self.assertEqual(context['input_files'],2);self.assertIn(b'lib::missing()',self.preview(context));self.assertEqual(self.rows(),before)

    def test_checker_error_uses_uncommitted_candidate_instead_of_physical_source(self):
        revision=self.ready();before=self.rows();original=self.file.read_bytes()
        path=self.patch(revision,'fn value()->i64{return "bad";}');error=self.cli('apply','--patch',path,ok=False)
        first=self.frontend(error,'check',complete=True);self.assertIn(b'return "bad"',self.preview(first))
        self.assertEqual(self.file.read_bytes(),original);self.assertNotIn(b'"bad"',original)
        self.assertNotIn('revision',error);self.assertNotIn('operation_id',error);self.assertEqual(self.rows(),before)
        path=self.patch(revision,'fn value()->i64{return true;}')
        second=self.frontend(self.cli('apply','--patch',path,ok=False),'check',complete=True)
        self.assertNotEqual(first['source']['hash'],second['source']['hash']);self.assertNotEqual(first['id'],second['id'])
        self.assertEqual(self.rows(),before)

    def test_operation_type_error_refers_to_assembled_candidate(self):
        revision=self.ready();before=self.rows();path=self.patch(revision,'"bad"',True)
        context=self.frontend(self.cli('apply','--patch',path,ok=False),'check',complete=True)
        self.assertIn(b'"bad"',self.preview(context));self.assertEqual(context['source']['key']['data'],'main.nex')
        self.assertEqual(self.file.read_text(),SOURCE);self.assertEqual(self.rows(),before)

    def test_operation_parse_error_keeps_fragment_scope(self):
        revision=self.ready();before=self.rows();path=self.patch(revision,'1 +',True)
        context=self.frontend(self.cli('apply','--patch',path,ok=False),'parse','expression',True)
        self.assertEqual(self.preview(context),b'(\n1 +\n)');self.assertEqual(context['entry']['data'],'<operation-patch>')
        self.assertEqual(self.rows(),before)

    def test_declaration_parse_error_shows_actual_synthetic_unit(self):
        revision=self.ready();path=self.patch(revision,'fn value()->i64{return }')
        context=self.frontend(self.cli('apply','--patch',path,ok=False),'parse','unit',True)
        self.assertTrue(self.preview(context).startswith(b'module fragment;\n'));self.assertEqual(context['entry']['data'],'<patch>')

    def test_translated_patch_budget_error_retains_context_with_current_error_identity(self):
        revision=self.ready();before=self.rows();fragment='1+'*50010+'1';path=self.patch(revision,fragment,True)
        error=self.cli('apply','--patch',path,ok=False);self.assertEqual(error['code'],'E_PATCH_LIMIT')
        context=self.frontend(error,'parse','expression',True);self.assertEqual(context['source']['bytes'],len(fragment)+4)
        self.assertLessEqual(len(self.preview(context)),4096);self.assertEqual(self.rows(),before)

    def test_invalid_utf8_source_is_lossless_base64_and_json_safe(self):
        self.ready();before=self.rows()
        for invalid in [b'\xff',b'\xc0\x80',b'\xed\xa0\x80',b'\xf4\x90\x80\x80',b'\xe2\x82']:
            raw=b'module bad;\n'+invalid;self.file.write_bytes(raw)
            error=self.cli('check',ok=False);self.assertEqual(error['code'],'E_UTF8')
            context=self.frontend(error,'parse',complete=False)
            self.assertFalse(context['source']['utf8']);self.assertEqual(context['preview']['encoding'],'base64')
            self.assertEqual(self.preview(context),raw);self.assertEqual(error['line'],2);self.assertEqual(error['column'],1)
            self.assertEqual(self.rows(),before)

    def test_large_unicode_context_is_bounded_and_scalar_aligned(self):
        self.ready();text='module large;\n// '+('Я🧠'*2000)+'\nfn main()->i64{return "bad";}'
        self.source(text);context=self.frontend(self.cli('check',ok=False),'check',complete=True)
        preview=context['preview'];raw=self.preview(context);raw.decode('utf-8')
        self.assertEqual(raw,text.encode()[preview['byte_begin']:preview['byte_end']]);self.assertTrue(preview['truncated_before'])
        self.assertTrue(preview['focus_fully_visible']);self.assertEqual(context['source']['bytes'],len(text.encode()))

    def test_valid_utf8_source_with_unsupported_token_keeps_encoding_distinct(self):
        self.ready();text='module raw;fn main()->unit{let x:i64=1 é;}';self.source(text)
        error=self.cli('check',ok=False);self.assertEqual(error['code'],'E_LEX')
        context=self.frontend(error,'parse',complete=False)
        self.assertTrue(context['source']['utf8']);self.assertEqual(self.preview(context),text.encode())

    def test_incomplete_large_diagnostic_span_is_explicit(self):
        self.ready();name='missing_'+'a'*6000;self.source('module large;fn main()->unit{'+name+'();}')
        context=self.frontend(self.cli('check',ok=False),'check',complete=True)
        self.assertFalse(context['preview']['focus_fully_visible']);self.assertTrue(context['preview']['truncated_after'])
        self.assertGreater(context['location']['byte_end'],context['preview']['byte_end'])

    def test_missing_import_has_partial_context_of_the_importing_source(self):
        self.ready();text='module app;import "./missing.nex" as m;fn main()->unit{}';self.source(text)
        context=self.frontend(self.cli('check',ok=False),'load',complete=False)
        self.assertEqual(context['input_files'],1);self.assertEqual(self.preview(context),text.encode())

    def test_missing_entry_does_not_fabricate_source_or_range(self):
        self.ready();self.file.unlink();context=self.frontend(self.cli('check',ok=False),'load',complete=False)
        self.assertEqual(context['input_files'],0);self.assertIsNone(context['source']);self.assertIsNone(context['location']);self.assertIsNone(context['preview'])

    def test_identity_is_repeatable_portable_and_changes_with_exact_source(self):
        self.ready();text='module stable;fn main()->i64{return true;}';self.source(text)
        first=self.frontend(self.cli('check',ok=False),'check',complete=True)
        repeat=self.frontend(self.cli('check',ok=False),'check',complete=True);self.assertEqual(first['id'],repeat['id'])
        moved=self.root/'moved';moved.mkdir()
        for name in ['nex.json','main.nex']:shutil.copy2(self.root/name,moved/name)
        portable=self.frontend(self.cli('check',cwd=moved,ok=False),'check',complete=True)
        self.assertEqual(first['id'],portable['id']);self.assertEqual(first['source_inputs_hash'],portable['source_inputs_hash'])
        self.file.write_text('// exact bytes changed\n'+text)
        changed=self.frontend(self.cli('check',ok=False),'check',complete=True);self.assertNotEqual(first['id'],changed['id'])

    def test_frozen_import_error_never_rereads_physical_source(self):
        revision=self.ready();before=self.rows();self.file.unlink()
        bad='module frozen;fn main()->i64{return "bad";}'
        graph={'schema':'nex.graph/2','language':'0.19','revision':'0'*64,'source':bad,
            'bundle':{'schema':'nex.sources/1','entry':'main.nex','files':{'main.nex':bad}}}
        path=self.root/'candidate.json';path.write_text(json.dumps(graph))
        context=self.frontend(self.cli('import',path,ok=False),'check',complete=True)
        self.assertEqual(self.preview(context),bad.encode());self.assertEqual(self.rows(),before);self.assertEqual(self.cli('history')['head'],revision)

    def test_unicode_source_key_and_preview_remain_exact(self):
        self.ready();name='математика🧠.nex';self.source('module app;import "./'+name+'" as m;fn main()->i64{return m::value();}')
        text='module library;pub fn value()->i64{return "bad";}';(self.root/name).write_text(text)
        context=self.frontend(self.cli('check',ok=False),'check',complete=True)
        self.assertEqual(context['source']['key']['encoding'],'utf-8');self.assertEqual(context['source']['key']['data'],name)
        self.assertEqual(self.preview(context),text.encode())

    def test_metadata_and_runtime_errors_keep_their_existing_distinctions(self):
        self.ready();manifest=self.root/'nex.json';value=json.loads(manifest.read_text());value['language']='0.14';manifest.write_text(json.dumps(value))
        error=self.cli('check',ok=False);self.assertEqual(error['code'],'E_LANGUAGE_VERSION');self.assertNotIn('frontend',error)
        value['language']='0.19';manifest.write_text(json.dumps(value));self.source('module runtime;fn main()->unit{assert(false);}')
        error=self.cli('eval',ok=False);self.assertEqual(error['code'],'E_ASSERT');self.assertNotIn('frontend',error)
        self.assertEqual(len(error['operation_site']),64);self.assertIn('operation_id',error)

    def test_watch_static_errors_bind_expression_and_frame_without_mutation(self):
        case=expression_harness.Expressions();case.setUp()
        try:
            before=copy.deepcopy(case.frame)
            first=self.frontend(case.inspect('n + true',ok=False),'check','expression',True)
            self.assertEqual(self.preview(first),b'n + true');self.assertEqual(case.frame,before)
            repeat=self.frontend(case.inspect('n + true',ok=False),'check','expression',True)
            self.assertEqual(first['id'],repeat['id'])
            changed=copy.deepcopy(case.frame);next(v for v in changed['bindings'] if v['name']=='n')['value']='41'
            second=self.frontend(case.inspect('n + true',changed,ok=False),'check','expression',True)
            self.assertEqual(first['source_inputs_hash'],second['source_inputs_hash']);self.assertNotEqual(first['watch']['frame_hash'],second['watch']['frame_hash']);self.assertNotEqual(first['id'],second['id'])
            syntax=self.frontend(case.inspect('n +',ok=False),'parse','expression',True);self.assertIn('watch',syntax)
            invalid=copy.deepcopy(case.frame);invalid['build_key']='0'*64
            self.assertNotIn('frontend',case.inspect('n',invalid,ok=False))
        finally:case.tearDown()

    def test_non_utf8_source_key_is_rejected_without_json_abort(self):
        if sys.platform=='darwin':self.skipTest('macOS filesystem requires UTF-8 names')
        self.ready();before=self.rows();path=os.fsencode(self.root)+b'/bad\xff.nex'
        with open(path,'wb') as output:output.write(SOURCE.encode())
        result=subprocess.run([os.fsencode(harness.NEX),b'check',path,b'--json'],cwd=self.root,capture_output=True,timeout=20)
        self.assertNotEqual(result.returncode,0);error=json.loads(result.stdout.decode('utf-8'));self.assertEqual(error['code'],'E_IMPORT_PATH')
        context=self.frontend(error,'load',complete=False);self.assertEqual(context['entry']['encoding'],'base64');self.assertEqual(self.rows(),before)

    def test_discovery_and_model_pack_expose_frontend_contract(self):
        descriptor=self.cli('describe');pack=json.loads((harness.REPO/'llm/language-pack.json').read_text())
        self.assertIn('captured_source_inputs',descriptor['frontend_diagnostic_features'])
        self.assertEqual(descriptor['frontend_diagnostic_limits'],{'preview_bytes':4096,'label_bytes':1024})
        self.assertEqual(descriptor['frontend_diagnostic_schema'],pack['documents']['frontend_diagnostic_schema'])
        self.assertEqual(self.cli('guide','--kind','frontend')['text'],(harness.REPO/'docs/frontend-diagnostics.md').read_text())

if __name__=='__main__':unittest.main()
