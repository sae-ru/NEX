"""Exact syntax intervals and atomic graph edits that preserve surrounding code."""
import copy
import json
import os
import hashlib
from pathlib import Path
import sqlite3
import unittest
import support as harness


class OperationPatches(harness.ToolchainCase):
    def ready(self, source):
        self.source(source)
        return self.cli('check')['revision']

    def nodes(self, symbol='main'):
        return self.cli('operations','--symbol',symbol,'--limit','1000')['nodes']

    def target(self, symbol='main', *, kind=None, text=None, number=None):
        matches=[node for node in self.nodes(symbol)
                 if (kind is None or node['kind']==kind)
                 and (text is None or node['definition'].get('text')==text)
                 and (number is None or node['definition'].get('number')==str(number))]
        self.assertEqual(len(matches),1,matches)
        return matches[0]

    def rows(self):
        with sqlite3.connect(self.root/'.nex/graph.db') as db:
            return {name:sorted(db.execute('SELECT * FROM "'+name+'"').fetchall(),key=repr)
                    for name, in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}

    def apply(self, replacements, *, source_hash=True, revision=None, ok=True):
        context=self.cli('operations','--symbol','main','--limit','1')
        patch={'expected_revision':revision or context['revision'],'replacements':replacements}
        if source_hash is not False:patch['expected_source_hash']=context['source_hash'] if source_hash is True else source_hash
        path=self.root/'patch.json';path.write_text(json.dumps(patch))
        return self.cli('apply','--patch',path,ok=ok)

    def op(self, node, source):
        return {'operation_id':node['id'],'source':source}

    def test_lexical_ranges_cover_complete_expressions_but_keep_diagnostic_points(self):
        expression='(inc(2) + [5,6][1]) * -3'
        source='module ranges;fn inc(n:i64)->i64{return n+1;}fn main()->unit!{io}{print('+expression+');}'
        self.ready(source)
        node=self.target(kind='expression.binary',text='*')
        point=node['location'];span=node['source_range'];raw=source.encode()
        self.assertEqual(raw[point['byte_begin']:point['byte_end']],b'*')
        self.assertEqual(raw[span['byte_begin']:span['byte_end']].decode(),expression)
        self.assertTrue(span['editable'])
        context=self.cli('context','--operation',node['id'])
        self.assertEqual(context['nodes'][0]['source_preview'],expression)
        self.assertFalse(context['nodes'][0]['source_truncated'])
        self.assertEqual(context['nodes'][0]['source_bytes'],len(expression.encode()))
        self.assertNotIn('source_preview',node)

    def test_expression_replacement_preserves_precedence_and_comment_boundaries(self):
        source='module edits;fn compute()->i64{return 2*3;}fn main()->unit!{io}{print(compute());}test fn wanted()->unit{assert(compute()==9);}'
        self.ready(source);node=self.target('compute',kind='expression.integer',number=2)
        changed=self.apply([self.op(node,'1+2 // comment')])
        self.assertTrue(changed['ok'])
        self.assertEqual(self.cli('eval','--revision','HEAD')['stdout'],'9\n')
        self.assertEqual(self.cli('run','--revision','HEAD')['stdout'],'9\n')
        self.assertTrue(self.cli('test','--revision','HEAD')['ok'])
        self.assertTrue(self.cli('test','--revision','HEAD','--target','web')['ok'])
        self.assertEqual(self.file.read_text(),source)

    def test_declaration_suffix_comment_does_not_swallow_adjacent_function(self):
        self.ready('module edits;fn a()->i64{return 1;} fn b()->i64{return 2;}\nfn main()->unit!{io}{print(a());print(b());}')
        before=self.nodes('b')[0]['function_id']
        self.apply([{'name':'edits::a','source':'fn a()->i64{return 3;}// trailing comment'}])
        self.assertEqual(self.nodes('b')[0]['function_id'],before)
        self.assertEqual(self.cli('run','--revision','HEAD')['stdout'],'3\n2\n')

    def test_rejected_stale_missing_unknown_and_overlapping_edits_are_atomic(self):
        self.ready('module atomic;fn main()->i64{return 1+2;}')
        expression=self.target(kind='expression.binary',text='+')
        leaf=self.target(kind='expression.integer',number=1)
        baseline=self.rows()
        checks=[([self.op(leaf,'3')],{'source_hash':False},'E_PATCH_SOURCE'),
                ([self.op(leaf,'3')],{'source_hash':'0'*64},'E_SOURCE_CONFLICT'),
                ([{'operation_id':'0'*32,'source':'3'}],{},'E_OPERATION'),
                ([self.op(expression,'4'),self.op(leaf,'5')],{},'E_PATCH_OVERLAP'),
                ([self.op(leaf,'3'),self.op(leaf,'4')],{},'E_JSON'),
                ([self.op(leaf,'3);print(99);(4')],{},'E_PARSE'),
                ([self.op(leaf,'true')],{},'E_TYPE')]
        for replacements,options,code in checks:
            with self.subTest(code=code):
                error=self.apply(replacements,ok=False,**options)
                self.assertEqual(error['code'],code,error)
                self.assertEqual(self.rows(),baseline)
        body=next(node for node in self.nodes() if node['path']=='body')
        self.assertIsNone(body['source_range'])
        self.assertEqual(self.apply([self.op(body,'{}')],ok=False)['code'],'E_PATCH_TARGET')
        self.assertEqual(self.rows(),baseline)

    def test_statement_and_expression_edits_share_one_checked_transaction(self):
        self.ready('module mixed;fn value()->i64{return 1;}fn main()->unit!{io}{print(value()+2);}')
        returned=self.target('value',kind='statement.return')
        number=self.target(kind='expression.integer',number=2)
        self.apply([self.op(returned,'return 4;'),self.op(number,'5')])
        self.assertEqual(self.cli('eval','--revision','HEAD')['stdout'],'9\n')
        self.assertEqual(self.cli('run','--revision','HEAD')['stdout'],'9\n')
        self.assertEqual(self.apply([self.op(returned,'return 1;return 2;')],ok=False)['code'],'E_PARSE')

    def test_context_preview_is_bounded_and_utf8_aligned(self):
        text='🧠'*1500
        self.ready('module unicode;fn main()->unit!{io}{print('+json.dumps(text,ensure_ascii=False)+');}')
        node=self.target(kind='expression.string')
        context=self.cli('context','--operation',node['id'])['nodes'][0]
        self.assertTrue(context['source_truncated'])
        self.assertLessEqual(len(context['source_preview'].encode()),4096)
        self.assertEqual(context['source_bytes'],len(json.dumps(text,ensure_ascii=False).encode()))
        self.assertEqual(context['source_preview'].encode().decode(),context['source_preview'])

    def test_type_and_operation_edits_across_modules_preserve_history(self):
        model='module model;pub struct Row{value:i64;}pub fn make()->Row{return Row(41);}'
        (self.root/'model.nex').write_text(model)
        original=self.ready('module app;import "./model.nex" as m;fn main()->unit!{io}{print(m::make().value);}')
        number=self.target('model::make',kind='expression.integer',number=41)
        baseline=self.rows()
        self.apply([self.op(number,'"after"')],ok=False)
        self.assertEqual(self.rows(),baseline)
        self.apply([{'kind':'type','name':'model::Row','source':'pub struct Row{value:str;}'},
                    self.op(number,'"after"')])
        self.assertEqual(self.cli('eval','--revision','HEAD')['stdout'],'after\n')
        self.assertEqual(self.cli('run','--revision','HEAD')['stdout'],'after\n')
        self.assertEqual(self.cli('run','--revision',original)['stdout'],'41\n')
        self.assertEqual((self.root/'model.nex').read_text(),model)
        self.assertEqual(self.apply([self.op(number,'42')],revision=original,ok=False)['code'],'E_CONFLICT')

    def test_generic_source_operations_regenerate_instances_and_reject_derived_edits(self):
        self.ready('module generic;fn add_one<T:integer>(x:T)->T{return x+x;}fn main()->unit!{io}{print(add_one(3));}test fn value()->unit{assert(add_one(4)==8);}')
        operator=self.target('add_one',kind='expression.binary',text='+')
        self.assertTrue(operator['source_range']['editable'])
        instance=self.target('generic::add_one<i64>',kind='expression.binary',text='+')
        self.assertFalse(instance['source_range']['editable'])
        before=self.rows()
        self.assertEqual(self.apply([self.op(instance,'x')],ok=False)['code'],'E_PATCH_SPECIALIZATION')
        self.assertEqual(self.rows(),before)
        self.apply([self.op(operator,'x')])
        self.assertEqual(self.cli('run','--revision','HEAD')['stdout'],'3\n')
        # The old assertion is intentionally retained; a successful edit is not a test waiver.
        self.assertFalse(self.cli('test','--revision','HEAD',ok=False)['ok'])
        self.assertFalse(self.cli('test','--revision','HEAD','--target','web',ok=False)['ok'])

    def test_closure_operations_are_derived_and_owner_lambda_is_editable(self):
        self.ready('module closures;fn main()->unit!{io}{let n:i64=5;let f:fn(i64)->i64=fn(x:i64)->i64{return x+n;};print(f(2));}')
        lam=self.target(kind='expression.lambda')
        lifted=self.target(lam['definition']['text'],kind='expression.binary',text='+')
        self.assertFalse(lifted['source_range']['editable'])
        before=self.rows()
        self.assertEqual(self.apply([self.op(lifted,'x')],ok=False)['code'],'E_PATCH_CLOSURE')
        self.assertEqual(self.rows(),before)
        self.apply([self.op(lam,'fn(x:i64)->i64{return x*n;}')])
        self.assertEqual(self.cli('eval','--revision','HEAD')['stdout'],'10\n')
        self.assertEqual(self.cli('run','--revision','HEAD')['stdout'],'10\n')

    def test_nested_pattern_binding_guard_and_uses_rename_atomically(self):
        self.ready('module patterns;enum Maybe<T>{None;Some(value:T);}fn read(v:Maybe<list<i64>>)->i64{return match v{Maybe::Some([x]) if x>0=>x,_=>0};}fn main()->unit!{io}{print(read(Maybe::Some([42])));}')
        nodes=self.nodes('read');binding=next(n for n in nodes if n['kind']=='pattern.binding')
        uses=[n for n in nodes if n['kind']=='expression.name' and n['definition']['text']=='x']
        self.assertEqual(len(uses),2)
        self.apply([self.op(binding,'y // pattern comment'),*[self.op(n,'y') for n in uses]])
        self.assertEqual(self.cli('eval','--revision','HEAD')['stdout'],'42\n')
        self.assertEqual(self.cli('run','--revision','HEAD')['stdout'],'42\n')
        binding=next(n for n in self.nodes('read') if n['kind']=='pattern.binding')
        before=self.rows();self.apply([self.op(binding,'_')],ok=False);self.assertEqual(self.rows(),before)

    def test_declaration_operation_overlap_and_strict_fields_leave_no_rows(self):
        self.ready('module strict;fn main()->i64{return 7;}')
        leaf=self.target(kind='expression.integer',number=7);before=self.rows()
        invalid=[([{'name':'main','source':'fn main()->i64{return 8;}'},self.op(leaf,'9')],'E_PATCH_OVERLAP'),
                 ([{'kind':'function','operation_id':leaf['id'],'source':'9'}],'E_JSON'),
                 ([{'name':'main','operation_id':leaf['id'],'source':'9'}],'E_JSON'),
                 ([{'operation_id':leaf['site'],'source':'9'}],'E_JSON'),
                 ([{'operation_id':leaf['id'],'source':'9','byte_begin':0}],'E_JSON')]
        for replacements,code in invalid:
            with self.subTest(replacements=replacements):
                self.assertEqual(self.apply(replacements,ok=False)['code'],code)
                self.assertEqual(self.rows(),before)

    def test_patch_file_bounds_and_special_files_are_rejected_without_blocking(self):
        self.ready('module limits;fn main()->i64{return 7;}')
        before=self.rows();path=self.root/'input.json'
        for payload,code in [('['*65+']'*65,'E_PATCH_LIMIT'),(' '*4194305,'E_PATCH_LIMIT'),
                             ('{"replacements":['+','.join('{}' for _ in range(1001))+'],"expected_revision":"'+'0'*64+'"}','E_PATCH_LIMIT')]:
            path.write_text(payload)
            self.assertEqual(self.cli('apply','--patch',path,ok=False)['code'],code)
        path.write_bytes(b'\xff')
        self.assertEqual(self.cli('apply','--patch',path,ok=False)['code'],'E_JSON')
        link=self.root/'link.json';link.symlink_to(path)
        self.assertEqual(self.cli('apply','--patch',link,ok=False)['code'],'E_PATCH_LIMIT')
        fifo=self.root/'fifo';os.mkfifo(fifo)
        self.assertEqual(self.cli('apply','--patch',fifo,ok=False,timeout=3)['code'],'E_PATCH_LIMIT')
        self.assertEqual(self.rows(),before)

    def test_deep_fragments_fail_with_diagnostics_and_preserve_head(self):
        self.ready('module depth;fn main()->i64{return 7;}')
        leaf=self.target(kind='expression.integer',number=7)
        statement=self.target(kind='statement.return');before=self.rows()
        fragments=[(leaf,'('*2000+'1'+')'*2000),
                   (leaf,'+'.join('1' for _ in range(2000))),
                   (statement,'if true{'*2000+'return 1;'+'}'*2000),
                   (statement,'if true{return 1;}else '*2000+'return 2;')]
        for node,source in fragments:
            self.assertEqual(self.apply([self.op(node,source)],ok=False)['code'],'E_PARSE_LIMIT')
            self.assertEqual(self.rows(),before)
        combined='1'
        for _ in range(80):combined='('+combined+')'+'+1'*100
        self.assertEqual(self.apply([self.op(leaf,combined)],ok=False)['code'],'E_PARSE_LIMIT')
        self.assertEqual(self.rows(),before)
        self.source('module depth;fn main()->i64{return '+combined+';}')
        self.assertEqual(self.cli('check',ok=False)['code'],'E_PARSE_LIMIT')
        self.assertEqual(self.rows(),before)
        self.assertEqual(self.apply([self.op(leaf,'1+'*50000+'1')],ok=False)['code'],'E_PATCH_LIMIT')
        self.assertEqual(self.rows(),before)

    def test_replacement_preserves_effect_order_short_circuit_and_minimum_literal_range(self):
        source='module order;fn mark(x:i64)->i64!{io}{print(x);return x;}fn main()->unit!{io}{print(mark(2)+mark(3));assert(true||mark(0)==0);print(-9223372036854775808);}'
        self.ready(source)
        calls=[n for n in self.nodes() if n['kind']=='expression.call' and n['definition']['text']=='order::mark']
        self.assertEqual(len(calls),3)
        minimum=self.target(kind='expression.integer',number=-9223372036854775808)
        span=minimum['source_range'];self.assertEqual(source.encode()[span['byte_begin']:span['byte_end']],b'-9223372036854775808')
        self.apply([self.op(calls[1],'mark(4)+mark(5)')])
        self.assertEqual(self.cli('eval','--revision','HEAD')['stdout'],'2\n4\n5\n11\n-9223372036854775808\n')
        self.assertEqual(self.cli('run','--revision','HEAD')['stdout'],'2\n4\n5\n11\n-9223372036854775808\n')

    def test_actual_047_store_keeps_revision_sites_locations_ids_and_old_source(self):
        fixture=harness.REPO/'tests/fixtures/operation-0.47'
        metadata=json.loads(Path(str(fixture)+'.json').read_text())
        sql=Path(str(fixture)+'.sql').read_bytes()
        self.assertEqual(hashlib.sha256(sql).hexdigest(),metadata['sql_sha256'])
        self.source(metadata['source']);(self.root/'.nex').mkdir()
        with sqlite3.connect(self.root/'.nex/graph.db') as db:db.executescript(sql.decode())
        before=self.rows();current=self.cli('graph')
        old=metadata['graph'];self.assertEqual(current['revision'],old['revision'])
        self.assertEqual(current['nodes'],old['nodes'])
        self.assertEqual(len(current['operation_graph']['nodes']),len(old['operation_graph']['nodes']))
        for new,prior in zip(current['operation_graph']['nodes'],old['operation_graph']['nodes']):
            for key,value in prior.items():self.assertEqual(new[key],value,key)
        self.assertEqual(self.rows(),before)
        self.file.unlink()
        self.assertEqual(self.cli('eval','--revision','HEAD')['stdout'],'42\n🧠\n')
        self.assertTrue(self.cli('test','--revision','HEAD','--target','web')['ok'])
        self.assertEqual(self.cli('run','--revision','HEAD')['stdout'],'42\n🧠\n')
        number=self.target('main',kind='expression.integer',number=40)
        self.apply([self.op(number,'41')])
        self.assertEqual(self.cli('run','--revision','HEAD')['stdout'],'43\n🧠\n')
        self.assertEqual(self.cli('eval','--revision',metadata['revision'])['stdout'],'42\n🧠\n')

    def test_simple_enum_pattern_roots_can_change_together(self):
        self.ready('module cases;enum Choice{First(value:i64);Second(value:i64);}fn read(v:Choice)->i64{match v{Choice::First(x)=>{return x;}Choice::Second(y)=>{return y+1;}}}fn main()->unit!{io}{print(read(Choice::First(40)));print(read(Choice::Second(40)));}test fn wanted()->unit{assert(read(Choice::First(40))==41);assert(read(Choice::Second(40))==40);}')
        cases=[n for n in self.nodes('read') if n['kind']=='pattern.case']
        first=next(n for n in cases if n['definition']['variant']=='cases::Choice::First')
        second=next(n for n in cases if n['definition']['variant']=='cases::Choice::Second')
        self.assertTrue(first['source_range']['editable'])
        self.apply([self.op(first,'Choice::Second(x)'),self.op(second,'Choice::First(y)')])
        self.assertEqual(self.cli('run','--revision','HEAD')['stdout'],'41\n40\n')
        self.assertTrue(self.cli('test','--revision','HEAD')['ok'])
        self.assertTrue(self.cli('test','--revision','HEAD','--target','web')['ok'])

    def test_whole_candidate_rejects_undeclared_effects_and_realm_crossings(self):
        self.ready('module gates;fn mark()->i64!{io}{print(1);return 1;}server fn hidden()->i64{return 1;}fn pure()->i64{return 0;}client fn visible()->i64{return 0;}fn main()->i64{return pure();}')
        pure=self.target('pure',kind='expression.integer',number=0)
        client=self.target('visible',kind='expression.integer',number=0)
        before=self.rows()
        for node,source,code in [(pure,'mark()','E_EFFECT'),(pure,'hidden()','E_REALM'),(client,'hidden()','E_REALM')]:
            self.assertEqual(self.apply([self.op(node,source)],ok=False)['code'],code)
            self.assertEqual(self.rows(),before)

    def test_exact_source_guard_distinguishes_formatting_with_same_semantic_revision(self):
        original='module layout;fn main()->i64{return 7;}'
        revision=self.ready(original)
        leaf=self.target(kind='expression.integer',number=7)
        archived=self.cli('operations','--symbol','main')['source_hash']
        projection='module layout;\n// 🧠 layout only\nfn main() -> i64 {\n return 7;\n}\n'
        self.source(projection)
        live=self.cli('graph','--revision','')
        self.assertEqual(live['revision'],revision)
        live_hash=live['operation_graph']['source_hash']
        self.assertNotEqual(live_hash,archived)
        before=self.rows()
        self.assertEqual(self.apply([self.op(leaf,'8')],source_hash=live_hash,ok=False)['code'],'E_SOURCE_CONFLICT')
        self.assertEqual(self.rows(),before)
        self.apply([self.op(leaf,'8')],source_hash=archived)
        self.assertEqual(self.cli('eval','--revision','HEAD')['value'],8)
        self.assertEqual(self.cli('eval','--revision',revision)['value'],7)
        self.assertEqual(self.file.read_text(),projection)


if __name__=='__main__':unittest.main()
