"""Collector boundary/accounting controls: synthetic provider, no real inference."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path=[x for x in sys.path if Path(x or '.').resolve()!=Path(__file__).resolve().parent]
spec=importlib.util.spec_from_file_location('nex_collection',ROOT/'experiments/quality/llm-campaign-v1/collector.py')
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)


class Collection(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='nex-collector-control-');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);(self.root/'resources').mkdir();(self.root/'starts').mkdir()
        c.a.save(self.root/'resources/documents.json',{'llm/BOOTSTRAP.md':'synthetic bootstrap','docs/language.md':'A🌍B'})
        c.a.save(self.root/'resources/descriptor.json',{'types':['i64'],'big':{'child':'x'*13000}})
        self.slot={'id':'synthetic-trial','task':'bounded-total','language':'python','repeat':0}
        for lang in c.LANGUAGES:c.a.materialize('bounded-total',lang,self.root/'starts'/('bounded-total-'+lang))
        self.frozen={'root':str(self.root),'order':[self.slot],'compiler':'/synthetic/nex','cpp':'/synthetic/clang++',
                     'resources':str(ROOT),'compiler_index':{'fields':['types','big']},'model_revision':'a'*64,
                     'tasks':['bounded-total'],'repeats':1,'kind':'synthetic_control'}
        c.a.save(self.root/'freeze.json',self.frozen)
        self.verify=patch.object(c,'verify',side_effect=lambda root,**kw:self.frozen);self.verify.start();self.addCleanup(self.verify.stop)

    def broker(self,language='python'):
        out=self.root/('broker-'+language);out.mkdir()
        return c.Broker(self.frozen,out,{**self.slot,'language':language})

    def good_check(self,broker,output,*,visible):
        output=Path(output);output.mkdir()
        files=broker.files();item=c.a.catalogue()[broker.task]
        report={'functional_passed':True,'accepted':False,'commands':[],'observations':[{'step':'synthetic','values':[0]}],
                'errors':[],'candidate_digest':c.a.source_digest(files)}
        c.a.save(output/'report.json',report)
        c.a.save(output/'acceptance.json',{'schema':'nex.llm-acceptance/1','trial_id':broker.slot['id'],
            'contract_sha256':item['contract_sha256'],'passed':False,
            'checks':[{'name':'functional-visible-and-held-out','exit_code':0},
                      {'name':'independent-source-contract-review','exit_code':1}]})
        return report

    def provider(self,answers,usage=True):
        owner=self
        class Fake:
            def __init__(self):self.number=0;self.prompts=[]
            def chat(self,instance,system,prompt,output,**kwargs):
                owner.assertEqual(kwargs['sampling'],c.SAMPLING);owner.assertIn(kwargs['max_tokens'],[2048,4096])
                self.prompts.append(json.loads(prompt));output.mkdir()
                text=answers[self.number];self.number+=1
                text=text(prompt)if callable(text)else text
                record={'id':'synthetic-call-'+str(self.number),'usage':{'input_tokens':100,'cached_input_tokens':None,'output_tokens':20}if usage else None,
                        'confirmed_cost':None,'error':None,'transport_finished':True}
                request=json.dumps({'system':system,'prompt':prompt}).encode();response=text.encode()
                (output/'request.json').write_bytes(request);(output/'response.json').write_bytes(response)
                record.update(request_sha256=hashlib.sha256(request).hexdigest(),response_sha256=hashlib.sha256(response).hexdigest())
                c.a.save(output/'call.json',record)
                return text,record
        return Fake()

    def test_broker_denies_host_paths_receipts_and_stale_partial_edits(self):
        broker=self.broker();original=broker.files()
        for path in ['../fixtures.py',str(ROOT/'experiments/quality/llm-campaign-v1/fixtures.py'),
                     'source-review.json','task.json','docs/language.md']:
            with self.subTest(path=path),self.assertRaises(ValueError):broker.action({'action':'read','path':path,'offset':0,'limit':20})
        valid={'sha256':c.a.sha(original['candidate.py']),'content':'def total(n): return 42\n'}
        with self.assertRaises(ValueError):broker.action({'action':'edit','files':{'candidate.py':valid,'../outside':valid}})
        self.assertEqual(broker.files(),original)
        with self.assertRaises(ValueError):broker.action({'action':'edit','files':{'candidate.py':{**valid,'sha256':'0'*64}}})
        broker.action({'action':'edit','files':{'candidate.py':valid}})
        self.assertEqual(broker.files()['candidate.py'],valid['content'].encode())
        with self.assertRaises(ValueError):broker.action({'action':'check','shell':'true'})

    def test_bounded_nex_docs_discovery_and_source_text_only(self):
        broker=self.broker('nex')
        row=broker.action({'action':'read','path':'docs/language.md','offset':1,'limit':1})
        self.assertEqual(row['text'],'🌍')
        self.assertEqual(broker.action({'action':'describe','field':'types'})['value'],['i64'])
        with self.assertRaises(ValueError):broker.action({'action':'describe','field':'big'})
        with self.assertRaises(ValueError):broker.action({'action':'describe','field':'../fixtures'})
        row=broker.action({'action':'symbol','name':'total'})
        self.assertEqual(row['matches'][0]['file'],'candidate.nex');self.assertEqual(row['kind'],'bounded_source_text_matches')
        with self.assertRaises(ValueError):broker.action({'action':'read','path':'docs/language.md','offset':True,'limit':1})

    def test_visible_feedback_never_runs_a_held_out_check(self):
        broker=self.broker();calls=[]
        def check(output,*,visible):calls.append(visible);return self.good_check(broker,output,visible=visible)
        with patch.object(broker,'run_check',side_effect=check):
            reply=broker.action({'action':'check'})
        self.assertEqual(calls,[True]);self.assertTrue(reply['functional_passed'])
        self.assertNotIn('acceptance',reply);self.assertNotIn('candidate_digest',reply)
        with patch.object(broker,'run_check',return_value={'errors':[{'step':'infrastructure','reason':'synthetic host failure'}]}):
            with self.assertRaises(RuntimeError):broker.action({'action':'check'})

    def test_actual_action_loop_keeps_bad_answers_repairs_and_review_boundary(self):
        def edit(prompt):
            packet=json.loads(prompt);entry=packet['files']['candidate.py']
            return json.dumps({'action':'edit','files':{'candidate.py':{'sha256':entry['sha256'],'content':'def total(n: int) -> int:\n    return sum(range(n+1))\n'}}})
        client=self.provider(['not JSON',edit,'{"action":"check"}','{"action":"submit"}'])
        checks=[]
        def check(broker,output,*,visible):checks.append(visible);return self.good_check(broker,output,visible=visible)
        with patch.object(c.Broker,'run_check',new=check):
            result=c.collect_trial(self.root,self.frozen,self.slot,client,'nex-cost-synthetic')
        self.assertEqual(checks,[True,False]);self.assertEqual(len(result['calls']),4)
        self.assertTrue(result['source_review_pending']);self.assertIsNone(result['status'])
        self.assertEqual(result['phase'],'awaiting_source_review')
        self.assertNotIn('held_out',json.dumps(client.prompts[0]['task']).replace('held_out_cases_status',''))
        self.assertIn('error',client.prompts[1]['history'][0]['tool_reply'])
        self.assertEqual(len(client.prompts[3]['history']),3)
        self.assertEqual(client.prompts[3]['history'][0]['assistant'],'not JSON')
        self.assertEqual(client.prompts[3]['history'][1]['tool_reply']['updated'],
            c.a.inventory({'candidate.py':b'def total(n: int) -> int:\n    return sum(range(n+1))\n'}))
        trial=self.root/'trials'/self.slot['id']
        self.assertFalse((trial/'acceptance.json').exists())
        reviews=self.root/'host-reviews';reviews.mkdir()
        item=c.a.catalogue()[self.slot['task']]
        review={'schema':'nex.llm-source-review/1','candidate_digest':result['candidate_digest'],
                'contract_sha256':item['contract_sha256'],'passed':True,'reviewer':'synthetic independent host',
                'rules':item['contract']['acceptance_rules'],'findings':[]}
        c.a.save(reviews/(self.slot['id']+'.json'),review)
        self.assertEqual(c.finalize(self.root,reviews)['source_reviews_finalized'],1)
        state=c.a.decode((trial/'state.json').read_bytes());self.assertEqual(state['status'],'accepted')
        summary=c.ledger(self.root)
        totals=summary['results']['qwen38-27b-q8']['python']
        self.assertEqual(totals['known_total_tokens'],480);self.assertEqual(totals['calls'],4)
        self.assertFalse(summary['matrix_complete']);self.assertFalse(summary['eligible_for_comparison_review'])
        (trial/'candidate/candidate.py').write_text('def total(n): return 999\n')
        with self.assertRaisesRegex(ValueError,'candidate changed'):c.ledger(self.root)

    def test_unknown_usage_and_request_budget_fail_without_dropping_calls(self):
        client=self.provider(['{"action":"submit"}'],usage=False)
        result=c.collect_trial(self.root,self.frozen,self.slot,client,'nex-cost-synthetic')
        self.assertEqual(result['status'],'failed');self.assertEqual(len(result['calls']),1)
        self.assertIsNone(result['calls'][0]['usage']);self.assertFalse(result['source_review_pending'])
        slot={**self.slot,'id':'synthetic-budget','repeat':0};client=self.provider(['{}','{}'])
        with patch.dict(c.LIMITS,{'model_requests':2}):result=c.collect_trial(self.root,self.frozen,slot,client,'nex-cost-synthetic')
        self.assertEqual(result['status'],'budget_exhausted');self.assertEqual(len(result['calls']),2)
        self.assertFalse(c.a.decode((self.root/'trials/synthetic-budget/acceptance.json').read_bytes())['passed'])

    def test_pending_interrupted_call_is_not_lost(self):
        client=self.provider([])
        def interrupted(instance,system,prompt,output,**kwargs):
            output.mkdir();c.a.save(output/'call.json',{'id':'synthetic-interrupted','usage':None,'confirmed_cost':None})
            raise KeyboardInterrupt()
        client.chat=interrupted
        with self.assertRaises(KeyboardInterrupt):c.collect_trial(self.root,self.frozen,self.slot,client,'nex-cost-synthetic')
        state=c.a.decode((self.root/'trials'/self.slot['id']/'state.json').read_bytes())
        self.assertEqual(state['status'],'failed');self.assertEqual(state['stop_reason'],'host_interruption')
        self.assertEqual(state['calls'][0]['id'],'synthetic-interrupted');self.assertIsNone(state['calls'][0]['usage'])

    def test_fresh_local_source_review_is_counted_and_can_reject_behavioral_success(self):
        rules=c.a.catalogue()['bounded-total']['contract']['acceptance_rules']
        review=json.dumps({'rules':[{'rule':rule,'passed':False,'evidence':'synthetic source violates the rule'}for rule in rules]})
        client=self.provider(['{"action":"submit"}',review])
        self.frozen['source_review_mode']='independent_local_call'
        def check(broker,output,*,visible):return self.good_check(broker,output,visible=visible)
        with patch.object(c.Broker,'run_check',new=check):state=c.collect_trial(self.root,self.frozen,self.slot,client,'nex-cost-synthetic')
        self.assertEqual(state['status'],'failed');self.assertEqual(len(state['calls']),2)
        self.assertEqual(state['stop_reason'],'independent_source_review_rejected')
        self.assertNotIn('latest_tool_reply',client.prompts[1]);self.assertNotIn('task',client.prompts[1]['files'])
        self.assertEqual([x['rule']for x in json.loads(review)['rules']],client.prompts[1]['rules'])
        receipt=c.a.decode((self.root/'trials'/self.slot['id']/'acceptance.json').read_bytes())
        self.assertFalse(receipt['passed'])
        summary=c.ledger(self.root)
        self.assertEqual(summary['results']['qwen38-27b-q8']['python']['calls'],2)
        self.assertEqual(summary['results']['qwen38-27b-q8']['python']['known_total_tokens'],240)

    def test_embedded_template_parser_skips_arrays_and_rejects_missing_template(self):
        string=lambda s:struct.pack('<Q',len(s.encode()))+s.encode()
        prefix=b'GGUF'+struct.pack('<IQQ',3,0,2)
        token_array=string('tokenizer.tokens')+struct.pack('<IIQ',9,8,2)+string('one')+string('two')
        chat=string('tokenizer.chat_template')+struct.pack('<I',8)+string('synthetic {{messages}}')
        path=self.root/'small.gguf';path.write_bytes(prefix+token_array+chat)
        self.assertEqual(c.template(path),'synthetic {{messages}}')
        path.write_bytes(b'GGUF'+struct.pack('<IQQ',3,0,0))
        with self.assertRaisesRegex(ValueError,'no chat template'):c.template(path)

    def test_existing_loaded_user_model_stops_before_any_owned_load(self):
        self.frozen.update(lms='/synthetic/lms',host={'runtime':'synthetic-runtime'})
        class Fake:
            def models(self):return {'models':[{'loaded_instances':[{'id':'user-owned'}]}]}
        with patch.object(c,'selected_runtime'),patch.object(c.p,'Client',return_value=Fake()),patch.object(c.subprocess,'run')as command:
            with self.assertRaisesRegex(ValueError,'idle service'):c.run(self.root)
        command.assert_not_called();self.assertFalse((self.root/'execution.json').exists())

    def test_runtime_internal_aliases_are_pinned_and_external_aliases_rejected(self):
        home=self.root/'lm';runtime=home/'llama.cpp-mac-arm64-apple-metal-advsimd-2.60.0';runtime.mkdir(parents=True)
        (runtime/'libactual.dylib').write_bytes(b'synthetic runtime')
        (runtime/'libalias.dylib').symlink_to('libactual.dylib')
        defaults=home/'.internal/user-concrete-model-default-config/qwen/qwen3.8-27b.json'
        defaults.parent.mkdir(parents=True);defaults.write_text('{"preset":"","operation":{"fields":[]}}')
        hub=home/'hub/models/qwen/qwen3.8-27b/model.yaml';hub.parent.mkdir(parents=True);hub.write_text('model: qwen/qwen3.8-27b\n')
        artifacts={'root':str(self.root),'primary_gguf':'synthetic.gguf'}
        with patch.object(c.r,'verify_weights',return_value=(artifacts,b'')),patch.object(c,'template',return_value='synthetic template'):
            facts=c.host_facts('/synthetic/weights',home,runtime)
            alias=next(x for x in facts['files']if x['path'].endswith('libalias.dylib'))
            self.assertTrue(alias['symlink']);self.assertEqual(alias['resolved'],str((runtime/'libactual.dylib').resolve()))
            (runtime/'liboutside.dylib').symlink_to(defaults)
            with self.assertRaisesRegex(ValueError,'aliases must stay inside'):c.host_facts('/synthetic/weights',home,runtime)

    def test_doc_search_is_literal_bounded_and_returns_scalar_offsets(self):
        broker=self.broker('nex');broker.docs['docs/language.md']='🌍 start\nWhile x\nwhile y\n'+('while z\n'*12)
        reply=broker.action({'action':'search','path':'docs/language.md','query':'WHILE'})
        self.assertEqual(reply['total_matches'],14);self.assertEqual(len(reply['matches']),8)
        offset=reply['matches'][0]['offset'];self.assertEqual(offset,len('🌍 start\n'))
        page=broker.action({'action':'read','path':'docs/language.md','offset':offset,'limit':7})
        self.assertEqual(page['text'],'While x')
        for path in ['../fixtures.py','terminal/report.json','host-reviews/source-review.json']:
            with self.assertRaises(ValueError):broker.action({'action':'search','path':path,'query':'secret'})

    def test_one_data_envelope_keeps_action_validation_strict(self):
        request={'action':'read','path':'reference.md','offset':0,'limit':10}
        raw=json.dumps(request)
        for text in [raw,'<tool_call>\n'+raw+'\n</tool_call>','```json\n'+raw+'\n```']:
            self.assertEqual(c.model_object(text),request)
        for text in ['prefix '+raw,raw+' trailing','<tool_call>'+raw+'</tool_call></tool_call>',
                     '<tool_call>'+raw+'</tool_call><tool_call>'+raw+'</tool_call>',
                     '```python\n'+raw+'\n```','[]','{"action":"submit","action":"check"}']:
            with self.subTest(text=text),self.assertRaises(ValueError):c.model_object(text)
        broker=self.broker()
        with self.assertRaises(ValueError):
            broker.action(c.model_object('<tool_call>{"action":"shell","command":"true"}</tool_call>'))

    def test_json_compiler_error_is_visible_without_embedded_host_source(self):
        broker=self.broker('nex')
        def check(output,*,visible):
            self.assertTrue(visible);output=Path(output);output.mkdir()
            c.a.save(output/'check.stdout',{'schema':'nex.diagnostic/1','ok':False,'code':'E_PARSE',
                'message':"expected expression, found '='",'line':5,'reported_source':'HOST_ONLY_ORACLE'})
            (output/'check.stderr').write_bytes(b'')
            return {'functional_passed':False,'errors':[{'step':'source-check','reason':'candidate rejected'}],
                'observations':[],'commands':[{'name':'source-check','exit_code':1,'stopped':None,
                    'stdout':'check.stdout','stderr':'check.stderr'}]}
        with patch.object(broker,'run_check',side_effect=check):reply=broker.action({'action':'check'})
        error=reply['diagnostics'][0]['stdout_diagnostic']
        self.assertEqual(error['code'],'E_PARSE');self.assertEqual(error['line'],5)
        self.assertEqual(error['message'],"expected expression, found '='")
        self.assertNotIn('HOST_ONLY_ORACLE',json.dumps(reply))

    def test_non_json_candidate_output_is_a_task_failure_not_host_failure(self):
        broker=self.broker()
        def command(argv,cwd,env,output,name,**kwargs):
            (output/(name+'.stdout')).write_bytes(b'unexpected candidate text\n{"result":1}\n')
            (output/(name+'.stderr')).write_bytes(b'')
            return {'name':name,'exit_code':0,'stopped':None,'stdout':name+'.stdout','stderr':name+'.stderr'}
        with patch.object(c.a,'command',side_effect=command):
            report=c.a.check(broker.work,broker.task,broker.language,self.root/'invalid-output',visible_only=True)
        self.assertFalse(report['functional_passed']);self.assertFalse(report['accepted'])
        self.assertEqual(report['errors'][0]['step'],'execute')
        self.assertEqual(report['errors'][0]['reason'],'invalid candidate observation JSON')
        self.assertFalse(any(x['step']=='infrastructure'for x in report['errors']))



_v2spec=importlib.util.spec_from_file_location('nex_collection_v2',ROOT/'experiments/quality/llm-campaign-v2/collector.py')
v2=importlib.util.module_from_spec(_v2spec);_v2spec.loader.exec_module(v2)

class Version2Collection(unittest.TestCase):
    provider=Collection.provider
    good_check=Collection.good_check

    def test_reference_edit_check_submit_and_independent_review_share_one_ledger(self):
        with tempfile.TemporaryDirectory(prefix='nex-collector-v2-') as temporary:
            self.root=Path(temporary);resources=self.root/'resources';resources.mkdir()
            docs={name:(ROOT/name).read_text(encoding='utf-8') for name in v2.engine.DOCS}
            v2.acceptance.save(resources/'documents.json',docs)
            v2.acceptance.save(resources/'descriptor.json',{'project_languages':['0.28','0.29','0.30']})
            quick=docs['llm/QUICK_REFERENCE.md']
            compiled={'identity':{'compiler_build':'synthetic-v2'},
                'guides':{'quick':{'text':quick,'hash':hashlib.sha256(quick.encode()).hexdigest()},
                          'stdlib':{'text':docs['docs/stdlib.md'],'hash':'synthetic-stdlib'}},
                'explanations':{'E_PARSE':{'code':'E_PARSE','context_specific':False,'action':'synthetic instruction'}}}
            v2.acceptance.save(resources/'compiled-references.json',compiled)
            v2.acceptance.materialize('bounded-total','nex',self.root/'starts/bounded-total-nex')
            slot={'id':'synthetic-v2-trial','task':'bounded-total','language':'nex','repeat':0}
            frozen={'root':str(self.root),'order':[slot],'compiler':'/synthetic/nex','cpp':'/synthetic/clang++',
                'resources':str(ROOT),'compiler_index':{'fields':['project_languages']},'model_revision':'a'*64,
                'tasks':['bounded-total'],'repeats':1,'kind':'synthetic_control',
                'study_protocol_version':2,'source_language':'0.30','source_review_mode':'independent_local_call'}
            v2.acceptance.save(self.root/'freeze.json',frozen)
            rules=v2.acceptance.catalogue()['bounded-total']['contract']['acceptance_rules']
            review=json.dumps({'rules':[{'rule':rule,'passed':True,'evidence':'synthetic independent source evidence'}for rule in rules]})
            def edit(prompt):
                packet=json.loads(prompt);entry=packet['files']['candidate.nex']
                solution=v2.acceptance.fixtures.files('bounded-total','nex','solution')['candidate.nex'].decode()
                return json.dumps({'action':'edit','files':{'candidate.nex':{'sha256':entry['sha256'],'content':solution}}})
            client=self.provider(['{"action":"guide","kind":"quick"}',
                '{"action":"explain","code":"E_PARSE"}',edit,'{"action":"check"}','{"action":"submit"}',review])
            def check(broker,output,*,visible):return self.good_check(broker,output,visible=visible)
            with patch.object(v2.engine,'verify',return_value=frozen),patch.object(v2.Broker,'run_check',new=check):
                state=v2.engine.collect_trial(self.root,frozen,slot,client,'nex-cost-synthetic-v2')
                self.assertEqual(state['status'],'accepted');self.assertEqual(len(state['calls']),6)
                summary=v2.engine.ledger(self.root)
            totals=summary['results']['qwen38-27b-q8']['nex']
            self.assertEqual(totals['calls'],6);self.assertEqual(totals['known_total_tokens'],720)
            self.assertEqual(client.prompts[1]['history'][0]['tool_reply']['text'],quick)
            self.assertEqual(client.prompts[2]['history'][1]['tool_reply']['code'],'E_PARSE')
            self.assertNotIn('history',client.prompts[-1]);self.assertNotIn('language_reference',client.prompts[-1])
            self.assertFalse(summary['matrix_complete']);self.assertFalse(summary['eligible_for_comparison_review'])
            self.assertIn('llm/DETAILED_CODING_RULES.md',client.prompts[0]['available_documents'])

    def test_new_freeze_pins_both_engines_documents_and_compiled_references(self):
        with tempfile.TemporaryDirectory(prefix='nex-freeze-v2-') as temporary:
            root=Path(temporary);compiler=root/'nex';compiler.write_bytes(b'synthetic compiler')
            cpp=root/'clang++';cpp.write_bytes(b'synthetic native compiler')
            lm=root/'lm';(lm/'bin').mkdir(parents=True);(lm/'bin/lms').write_bytes(b'synthetic lms')
            weights=root/'weights.json';v2.acceptance.save(weights,{'files':[{'path':'synthetic-Q8_0.gguf','sha256':'a'*64}]})
            identity={'language':'0.28','compiler_build':'synthetic-build','descriptor_hash':'synthetic-descriptor','fields':[]}
            descriptor={'project_languages':['0.28','0.29','0.30']}
            def info(argv,**kwargs):
                if 'doctor' in argv:return json.dumps({'version':'0.280.1'}).encode()
                return json.dumps(identity if '--kind' in argv else descriptor).encode()
            compiled={'compiler_sha256':v2.engine.sha(compiler),'identity':identity,
                'guides':{kind:{'text':(ROOT/name).read_text(encoding='utf-8')}for kind,name in
                    [('quick','llm/QUICK_REFERENCE.md'),('stdlib','docs/stdlib.md')]},'explanations':{}}
            output=root/'new-freeze'
            with patch.object(v2.engine,'host_facts',return_value={'runtime':'synthetic','files':[]}), \
                 patch.object(v2.engine,'selected_runtime',return_value='synthetic runtime listing'), \
                 patch.object(v2.engine.subprocess,'check_output',side_effect=info), \
                 patch.object(v2.engine.r,'verify_weights',return_value=None), \
                 patch.object(v2.references,'snapshot',return_value=compiled):
                frozen=v2.freeze(output,compiler=compiler,cpp=cpp,weights=weights,lm_home=lm,runtime=root/'runtime')
                self.assertEqual(v2.verify(output,deep=True),frozen)
            self.assertEqual(frozen['study_protocol_version'],2);self.assertEqual(frozen['source_language'],'0.30')
            self.assertEqual(frozen['schema'],'nex.local-collection/2')
            with self.assertRaisesRegex(ValueError,'unsupported collection freeze'):c.verify(output)
            self.assertEqual(frozen['limits'],c.LIMITS);self.assertEqual(len(frozen['order']),60)
            self.assertTrue(all(slot['id'].startswith('v2-')for slot in frozen['order']))
            names={Path(row['path']).resolve() for row in frozen['pinned_files']}
            for path in [ROOT/'experiments/quality/llm-campaign-v1/collector.py',
                         ROOT/'experiments/quality/llm-campaign-v2/collector.py',
                         ROOT/'experiments/quality/llm-campaign-v2/acceptance.py',
                         ROOT/'llm/DETAILED_CODING_RULES.md',output/'resources/compiled-references.json']:
                self.assertIn(path.resolve(),names)
            self.assertEqual(json.loads((output/'resources/documents.json').read_text())['llm/SYSTEM_PROMPT.md'],
                (ROOT/'llm/SYSTEM_PROMPT.md').read_text())

    def test_historical_freeze_is_refused_and_common_contract_fits_one_read(self):
        self.assertLessEqual(len((ROOT/'llm/SYSTEM_PROMPT.md').read_bytes()),4096)
        self.assertGreater(len((ROOT/'llm/DETAILED_CODING_RULES.md').read_bytes()),4096)
        with tempfile.TemporaryDirectory(prefix='nex-historical-freeze-') as temporary:
            historical_root=Path(temporary)
            c.a.save(historical_root/'freeze.json',{'schema':'nex.local-collection/1','study_protocol_version':1,'source_language':'0.28'})
            with self.assertRaisesRegex(ValueError,'historical'):v2.verify(historical_root)
        historical=json.loads((ROOT/'experiments/quality/llm-campaign-v1/tasks.json').read_text())
        current=json.loads((ROOT/'experiments/quality/llm-campaign-v2/tasks.json').read_text())
        self.assertEqual(historical['tasks'],current['tasks']);self.assertEqual(current['language'],'0.30')


if __name__=='__main__':unittest.main(verbosity=2)
