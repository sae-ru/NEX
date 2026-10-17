"""Persistent operation identities, semantic sites and real lowering/diagnostics."""
import copy,json,os,shutil,sqlite3,subprocess,sys,unittest
from pathlib import Path
LIVE='--live' in sys.argv
if LIVE:sys.argv.remove('--live')
import support as harness

SOURCE='''module ops;
fn pick(a: i64, b: i64) -> i64 {
  let left: i64 = a + 1;
  let right: i64 = b + 2;
  return left + right;
}
fn main() -> unit !{io} { print(pick(2, 3)); }
'''

class Operations(harness.ToolchainCase):
    def setUp(self):
        super().setUp();self.source(SOURCE);self.revision=self.cli('check')['revision']
    def nodes(self,symbol='pick',**kwargs):
        return self.cli('operations','--symbol',symbol,'--limit','1000',**kwargs)['nodes']
    def bypath(self,symbol='pick',**kwargs):
        return {n['path']:n for n in self.nodes(symbol,**kwargs)}
    def edit(self,source):
        self.file.write_text(source);return self.cli('check')['revision']

    def test_complete_tree_typed_definitions_and_binding_call_edges(self):
        graph=self.cli('graph');nodes=graph['operation_graph']['nodes'];byid={n['id']:n for n in nodes}
        self.assertEqual(len(byid),len(nodes));self.assertEqual(len({n['site'] for n in nodes}),len(nodes))
        self.assertEqual(graph['schema'],'nex.graph/2')
        self.assertTrue({'block','parameter','statement.let','expression.binary','expression.name'} <= {n['kind'] for n in nodes})
        for n in nodes:
            for r in n['references']:
                if r['role']=='binding':self.assertIn(byid[r['id']]['kind'],['parameter','statement.let','statement.var'])
                else:self.assertIn(r['id'],{f['id'] for f in graph['nodes']})
        pick=self.bypath();self.assertEqual(pick['body/statement/0/expression/0/argument/0']['references'][0]['id'],pick['parameter/0']['id'])
        self.assertEqual(pick['body/statement/2/expression/0/argument/0']['references'][0]['id'],pick['body/statement/0']['id'])

    def test_edited_contents_keep_logical_ids_and_change_content_and_site(self):
        old=self.bypath();main=self.bypath('main')
        self.edit(SOURCE.replace('a + 1','a + 9'));new=self.bypath()
        self.assertEqual({p:n['id'] for p,n in old.items()},{p:n['id'] for p,n in new.items()})
        self.assertNotEqual(old['body/statement/0']['hash'],new['body/statement/0']['hash'])
        self.assertEqual(old['body/statement/1']['hash'],new['body/statement/1']['hash'])
        self.assertNotEqual(old['body/statement/1']['site'],new['body/statement/1']['site'])
        self.assertEqual(main,self.bypath('main'))

    def test_insertions_reordering_and_parameter_roles_preserve_unique_nodes(self):
        old=self.bypath()
        self.edit(SOURCE.replace('  let left: i64 = a + 1;\n  let right: i64 = b + 2;',
            '  let spare: i64 = 0;\n  let right: i64 = b + 2;\n  let left: i64 = a + 1;'))
        new=self.bypath()
        self.assertEqual(old['body/statement/0']['id'],new['body/statement/2']['id'])
        self.assertEqual(old['body/statement/1']['id'],new['body/statement/1']['id'])
        self.assertEqual(old['body/statement/2']['id'],new['body/statement/3']['id'])
        self.assertNotIn(new['body/statement/0']['id'],{n['id'] for n in old.values()})
        self.edit(self.file.read_text().replace('a: i64, b: i64','b: i64, a: i64'))
        reordered=self.bypath()
        self.assertEqual(old['parameter/0']['id'],reordered['parameter/1']['id'])
        self.assertEqual(old['parameter/1']['id'],reordered['parameter/0']['id'])

    def test_ambiguous_duplicates_are_not_guessed_and_old_revisions_remain(self):
        source='module ops; fn main() -> i64 { assert(true); assert(true); return 0; }'
        revision=self.edit(source);old=self.bypath('main')
        self.edit(source.replace('{ assert','{ let marker: i64 = 1; assert',1));new=self.bypath('main')
        oldcalls={old['body/statement/'+str(i)]['id'] for i in [0,1]}
        self.assertFalse(oldcalls & {new['body/statement/'+str(i)]['id'] for i in [1,2]})
        self.assertEqual(old['body/statement/2']['id'],new['body/statement/3']['id'])
        selected=next(iter(oldcalls))
        self.assertEqual(self.cli('context','--operation',selected,ok=False)['code'],'E_OPERATION')
        archived=self.cli('context','--operation',selected,'--revision',revision)
        self.assertEqual(archived['nodes'][0]['id'],selected)
        head=self.cli('history')['head'];self.cli('operations','--symbol','main','--revision',revision)
        self.assertEqual(self.cli('history')['head'],head)
        self.edit(source);self.assertEqual(old,self.bypath('main'))

    def test_lexical_shadow_initializers_and_assignments_refer_to_actual_bindings(self):
        self.edit('''module ops; fn main() -> unit {
          var x: i64 = 1;
          if true { let x: i64 = x + 1; assert(x == 2); }
          x = x + 1; assert(x == 2);
        } test fn shadow_test() -> unit { main(); }''')
        nodes=self.bypath('main');outer=nodes['body/statement/0']['id'];inner=nodes['body/statement/1/body/statement/0']['id']
        uses=[n['references'][0]['id'] for n in nodes.values() if n['kind']=='expression.name']
        self.assertEqual(uses.count(outer),3);self.assertEqual(uses.count(inner),1)
        self.assertEqual(nodes['body/statement/2']['references'][0]['id'],outer)
        self.cli('test');self.assertEqual(self.cli('run')['exit_code'],0)

    def test_database_v2_upgrade_backfill_and_rejected_patch_are_history_preserving(self):
        before=self.cli('graph');database=self.root/'.nex/graph.db'
        with sqlite3.connect(database) as db:
            sources=db.execute('SELECT hash,source,language FROM revisions').fetchall()
            db.executescript("DROP TABLE operation_functions; DROP TABLE operation_versions; DROP TABLE operation_ids; UPDATE metadata SET value='2' WHERE key='schema';")
        self.file.unlink();after=self.cli('graph')
        self.assertEqual([(n['id'],n['hash']) for n in before['nodes']],[(n['id'],n['hash']) for n in after['nodes']])
        with sqlite3.connect(database) as db:
            self.assertEqual(db.execute("SELECT value FROM metadata WHERE key='schema'").fetchone()[0],'3')
            self.assertEqual(db.execute('SELECT hash,source,language FROM revisions').fetchall(),sources)
            counts=[db.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ['operation_ids','operation_versions']]
        patch=self.root/'patch.json';patch.write_text(json.dumps({'expected_revision':'0'*64,'replacements':[{'name':'ops::pick','source':'fn pick(a: i64, b: i64) -> i64 { return 0; }'}]}))
        self.assertEqual(self.cli('apply','--patch',patch,ok=False)['code'],'E_CONFLICT')
        with sqlite3.connect(database) as db:self.assertEqual(counts,[db.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ['operation_ids','operation_versions']])
        self.assertEqual(self.cli('history')['head'],self.revision)

    def test_import_rechecks_sources_and_does_not_trust_foreign_derived_ids(self):
        before=self.cli('graph');foreign=copy.deepcopy(before)
        for n in foreign['operation_graph']['nodes']:n['id']='0'*32
        graph=self.root/'foreign.json';graph.write_text(json.dumps(foreign));directory=self.root/'other';directory.mkdir()
        self.cli('import',graph,cwd=directory);after=self.cli('graph',cwd=directory)
        first={n['site']:n['id'] for n in before['operation_graph']['nodes']};second={n['site']:n['id'] for n in after['operation_graph']['nodes']}
        self.assertEqual(first.keys(),second.keys());self.assertTrue(all(first[k]!=second[k] and second[k]!='0'*32 for k in first))
        self.assertEqual(before['revision'],after['revision'])

    def test_interpreter_native_typescript_sites_and_exact_source_hashes_agree(self):
        self.edit('''module ops; fn divide(n: i64) -> i64 { return 10 / n; }
        server fn hidden() -> str { return "SERVER_ONLY_OPERATION_SENTINEL"; }
        fn main() -> unit !{io} { print("before"); print(divide(0)); }''')
        error=self.cli('eval',ok=False);self.assertEqual(error['code'],'E_DIV_ZERO');self.assertEqual(error['stdout'],'before\n')
        context=self.cli('context','--operation',error['operation_id'])
        node=context['nodes'][0];self.assertEqual(node['site'],error['operation_site']);self.assertEqual(node['definition']['text'],'/')
        self.assertEqual(node['function'],'ops::divide');self.assertEqual(context['source_hash'],error['source_hash'])
        native=self.cli('run',ok=False);self.assertIn('E_DIV_ZERO',native['stderr']);self.assertEqual(native['stdout'],'before\n')
        built=self.cli('build');self.assertIn('nex.site.'+node['site'],Path(built['mlir']).read_text())
        manifest=json.loads(Path(built['debug_manifest']).read_text());self.assertEqual(manifest['source_hash'],error['source_hash'])
        sites=[o['site'] for f in manifest['functions'] for o in f['operation_sites']];self.assertIn(node['site'],sites)
        directory=self.root/'ts';self.cli('emit','--kind','typescript','--directory',directory)
        mapping=json.loads((directory/'nex-map.json').read_text());self.assertNotIn('SERVER_ONLY_OPERATION_SENTINEL',json.dumps(mapping))
        self.assertNotIn('ops::hidden',{f['name'] for f in mapping['functions']})
        (directory/'package.json').write_text('{"type":"module"}')
        (directory/'driver.ts').write_text("import {entry} from './program.ts';try{entry()}catch(e){process.stdout.write(JSON.stringify({code:e.code,site:e.site}));}")
        result=subprocess.run([os.environ.get('NEX_NODE','node'),'--experimental-strip-types','--no-warnings',str(directory/'driver.ts')],text=True,capture_output=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr);record=json.loads(result.stdout.removeprefix('before\n'))
        self.assertEqual(record['code'],'E_DIV_ZERO');self.assertEqual(record['site'][3],node['site'])
        before=error['source_hash'];self.file.write_text('// moved source\n'+self.file.read_text())
        moved=self.cli('eval',ok=False);self.assertEqual(moved['operation_id'],error['operation_id']);self.assertEqual(moved['operation_site'],node['site'])
        self.assertNotEqual(moved['source_hash'],before);self.assertEqual(self.cli('context','--site',node['site'])['source_hash'],before)

    def test_paged_queries_and_context_are_explicit_about_omitted_children(self):
        full=self.nodes();page=self.cli('operations','--symbol','pick','--offset','2','--limit','1')
        self.assertEqual(page['total'],len(full));self.assertEqual(page['nodes'],full[2:3]);self.assertTrue(page['truncated'])
        context=self.cli('context','--site',full[-1]['site']);self.assertEqual(context['nodes'][0]['id'],full[-1]['id']);self.assertTrue(context['ancestors'])
        for args in [('--limit','0'),('--limit','1001'),('--offset','-1')]:
            self.assertEqual(self.cli('operations','--symbol','pick',*args,ok=False)['code'],'E_OPTION')
        self.assertEqual(self.cli('context','--operation','f'*32,ok=False)['code'],'E_OPERATION')
        self.edit('module ops; fn main() -> unit { let items: list<i64> = ['+','.join(map(str,range(105)))+']; }')
        node=next(n for n in self.nodes('main') if n['kind']=='expression.list')
        self.assertEqual(node['child_count'],105);self.assertEqual(len(node['children']),100);self.assertTrue(node['children_truncated'])
        self.edit('module ops; fn main() -> unit { let text: str = "'+'x'*10000+'"; }')
        literal=next(n for n in self.nodes('main') if n['kind']=='expression.string')
        self.assertTrue(literal['definition_omitted']);self.assertIsNone(literal['definition']);self.assertGreater(literal['definition_bytes'],8192)
        exported=next(n for n in self.cli('graph')['operation_graph']['nodes'] if n['id']==literal['id'])
        self.assertEqual(exported['definition']['text'],'x'*10000)

    def test_inferred_and_explicit_generic_metadata_have_identical_semantic_identity(self):
        source='module ops; fn main() -> unit { let value: result<i64> = err("E", "message"); }'
        revision=self.edit(source);before=self.nodes('main')
        self.assertEqual(self.edit(source.replace('err(','err<i64>(')),revision)
        self.assertEqual(before,self.nodes('main'))
        live=self.cli('graph','--revision','')['operation_graph']['nodes']
        self.assertEqual([(n['id'],n['hash'],n['site']) for n in before],[(n['id'],n['hash'],n['site']) for n in live])

    def test_imported_operations_keep_identity_when_the_entry_module_changes(self):
        (self.root/'library.nex').write_text('module math; pub fn answer() -> i64 { return 42; }')
        source='module first; import "./library.nex" as math; fn main() -> i64 { return math::answer(); }'
        self.edit(source);before=self.nodes('math::answer')
        self.edit(source.replace('module first;','module second;'))
        self.assertEqual(before,self.nodes('math::answer'))

    def test_large_unchanged_function_keeps_ids_after_another_function_changes(self):
        source='module ops; fn wide() -> i64 {'+''.join('let value%d: i64 = %d;'%(i,i) for i in range(2000))+'return value1999;} fn main() -> i64 { return 0; }'
        self.edit(source)
        before=self.cli('operations','--symbol','wide','--offset','3990','--limit','20')
        self.edit(source.replace('fn main() -> i64 { return 0; }','fn main() -> i64 { return 1; }'))
        after=self.cli('operations','--symbol','wide','--offset','3990','--limit','20')
        self.assertEqual(before['nodes'],after['nodes']);self.assertGreater(after['total'],4000)

if LIVE:
    class LiveOperations(harness.ToolchainCase):
        def example(self):
            for name in ['main.nex','model.nex']:shutil.copyfile(harness.REPO/'examples/debugging'/name,self.root/name)
            session=self.cli('debug','--kind','nex-dap');manifest=json.loads(Path(session['manifest']).read_text())
            source=next(s['projection'] for s in manifest['sources'] if Path(s['original']).name=='main.nex')
            return session,source

        def test_actual_lldb_sites_resolve_to_archived_persistent_operations(self):
            session,source=self.example();script=self.root/'sites.py';report=self.root/'sites.json'
            script.write_text('''import json,lldb
def __lldb_init_module(debugger, _):
    debugger.SetAsync(False);debugger.HandleCommand('settings set target.disable-aslr false')
    target=debugger.GetSelectedTarget();target.BreakpointCreateByLocation(SOURCE,12)
    process=target.LaunchSimple(None,None,None)
    try:
        assert process.GetState()==lldb.eStateStopped
        stop=process.GetStopID();r=lldb.SBCommandReturnObject()
        debugger.GetCommandInterpreter().HandleCommand('nex-operation',r)
        assert r.Succeeded(),r.GetError()
        value=json.loads(r.GetOutput());assert value['candidates']
        assert process.GetState()==lldb.eStateStopped and process.GetStopID()==stop
        with open(REPORT,'w') as output:json.dump(value,output)
        process.Continue();assert process.GetState()==lldb.eStateExited and process.GetExitStatus()==0
    finally:
        if process.GetState() not in (lldb.eStateExited,lldb.eStateInvalid):process.Kill()
'''.replace('SOURCE',repr(source)).replace('REPORT',repr(str(report))))
            self.file.unlink();(self.root/'model.nex').unlink()
            result=self.cli('debug','--revision','HEAD','--','--no-lldbinit','--batch','-o','command script import '+json.dumps(str(script)),machine=False)
            self.assertTrue(report.is_file(),result.stdout+result.stderr);snapshot=json.loads(report.read_text())
            self.assertEqual(snapshot['line'],12);self.assertEqual(snapshot['function'],'debugging::app::inspect')
            for candidate in snapshot['candidates']:
                node=self.cli('context','--site',candidate['site'],'--revision',snapshot['revision'])['nodes'][0]
                self.assertEqual(node['path'],candidate['path']);self.assertEqual(node['location']['line'],12)
                if snapshot['selection']=='source_column':self.assertEqual(node['location']['column'],snapshot['column'])

        def test_actual_dap_reports_site_candidates_without_inferior_execution(self):
            from debugging import DAP
            session,source=self.example();client=DAP(session['adapter_command'],self.root)
            try:
                client.request('initialize',{'adapterID':'nex','pathFormat':'path','linesStartAt1':True})
                pending=client.send('launch',dict(session['launch'],disableASLR=False));client.event('initialized')
                client.request('setBreakpoints',{'source':{'path':source},'breakpoints':[{'line':12}]})
                client.request('configurationDone');client.response(pending);stop=client.event('stopped')
                frame=client.request('stackTrace',{'threadId':stop['threadId']})['stackFrames'][0]['id']
                report=client.request('evaluate',{'expression':chr(96)+'nex-operation','context':'repl','frameId':frame})['result']
                begin=report.index('{"schema": "nex.debug-operation/1"')
                snapshot=json.JSONDecoder().raw_decode(report[begin:])[0]
                self.assertTrue(snapshot['candidates']);self.assertEqual(snapshot['line'],12)
                for candidate in snapshot['candidates']:self.assertEqual(self.cli('context','--site',candidate['site'])['nodes'][0]['site'],candidate['site'])
                value=client.request('evaluate',{'expression':'total','context':'watch','frameId':frame})
                self.assertEqual(value['nex']['stop'],snapshot['stop']);self.assertEqual(value['result'],'42')
                client.request('continue',{'threadId':stop['threadId']});self.assertEqual(client.event('exited')['exitCode'],0)
            finally:client.close()

if __name__=='__main__':unittest.main(verbosity=2)
