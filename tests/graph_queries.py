"""Bounded discovery of checked archived source and directed dependencies."""
import hashlib
import json
import sqlite3
from pathlib import Path
import unittest
import support as harness

LIBRARY = '''module library;
pub struct Box<T>{value:T;}
pub fn leaf()->i64{return 42;}
pub fn middle(value:Box<i64>)->i64{return leaf()+value.value;}
pub fn echo<T>(value:T)->T{return value;}
pub fn cycle_a(n:i64)->i64{if n==0{return 1;}return cycle_b(n-1);}
pub fn cycle_b(n:i64)->i64{if n==0{return 2;}return cycle_a(n-1);}
pub fn never_execute()->i64{assert(false);return 0;}
'''
MAIN = '''module app;import "./library.nex" as lib;
fn choose()->i64{return lib::middle(lib::Box(lib::echo(0)));}
fn marker()->str{return "needle🌍 .*";}
fn main()->i64{return choose();}
'''


class GraphQueries(harness.ToolchainCase):
    def project(self, source=MAIN, library=LIBRARY, directory=None):
        directory = directory or self.root
        directory.mkdir(exist_ok=True)
        (directory/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.18','entry':'main.nex'}))
        (directory/'main.nex').write_text(source)
        (directory/'library.nex').write_text(library)
        revision = self.cli('check',cwd=directory)['revision']
        return directory, revision

    def rows(self, directory=None):
        with sqlite3.connect((directory or self.root)/'.nex/graph.db') as db:
            names = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
            return {n:sorted(db.execute('SELECT * FROM "'+n+'"').fetchall(),key=repr) for n in names}

    def search(self, query, *args, **kw):
        return self.cli('search','--query',query,*args,**kw)

    def subgraph(self, name, *args, **kw):
        return self.cli('subgraph','--symbol',name,*args,**kw)

    def symbols(self, response):
        return {n['symbol'] for n in response['nodes']}

    def test_literal_discovery_names_sources_and_fields(self):
        self.project()
        one = self.search('leaf','--field','symbol')
        self.assertEqual(one['schema'],'nex.graph-search/1')
        self.assertEqual(self.symbols(one),{'library::leaf'})
        self.assertEqual(one['nodes'][0]['matched_fields'],['symbol'])
        self.assertIsNone(one['nodes'][0]['preview'])
        self.assertEqual(self.symbols(self.search('needle🌍','--field','source')),{'app::marker'})
        self.assertEqual(self.symbols(self.search('.*','--field','source')),{'app::marker'})
        self.assertFalse(self.search('LEAF','--field','symbol')['nodes'])
        self.assertFalse(self.search('needle🌍','--field','symbol')['nodes'])
        self.assertEqual(self.symbols(self.search('library.nex','--field','any')),self.symbols(self.search('library','--field','any')))
        module = self.search('library','--entity','module')
        self.assertEqual(self.symbols(module),{'library'})
        self.assertFalse(module['nodes'][0]['editable'])

    def test_source_window_is_byte_exact_utf8_and_definition_relative(self):
        value = 'λ🌍'*900+'needle🌍'+'x'*3000
        source = 'module window;fn value()->str{return '+json.dumps(value,ensure_ascii=False)+';}fn main()->unit{}'
        self.project(source)
        node = self.search('needle🌍','--field','source')['nodes'][0]
        preview = node['preview'];raw = self.cli('context','--symbol','value')['source'].encode()
        self.assertEqual(preview['relative_to'],'declaration_source')
        self.assertLessEqual(len(preview['text'].encode()),2048)
        self.assertEqual(preview['text'].encode(),raw[preview['byte_begin']:preview['byte_end']])
        self.assertEqual(raw[preview['match']['byte_begin']:preview['match']['byte_end']].decode(),'needle🌍')
        self.assertEqual(preview['source_bytes'],len(raw))
        self.assertTrue(preview['truncated_before'] and preview['truncated_after'])
        self.assertRegex(preview['source_hash'],r'^[0-9a-f]{64}$')

    def test_pages_are_deterministic_and_query_identity_excludes_page_ranges(self):
        _, revision = self.project()
        full = self.search('library','--limit','1000')
        rows = [];offset=0
        while True:
            page = self.search('library','--revision',revision,'--offset',str(offset),'--limit','2')
            self.assertEqual(page['query_hash'],full['query_hash'])
            rows += page['nodes'];offset=page['page']['next_offset']
            if offset is None:break
        self.assertEqual(rows,full['nodes'])
        self.assertEqual([(n['kind'],n['symbol']) for n in rows],sorted((n['kind'],n['symbol']) for n in rows))
        missing = self.search('library','--offset','10000000')
        self.assertFalse(missing['nodes']);self.assertIsNone(missing['page']['next_offset'])
        self.assertNotEqual(full['query_hash'],self.search('library','--entity','function')['query_hash'])
        other=self.root/'other';self.project(directory=other)
        moved=self.search('library',cwd=other)
        self.assertEqual(moved['revision'],revision)
        self.assertNotEqual(moved['query_hash'],full['query_hash'])

    def test_byte_budget_returns_progressing_cursor_instead_of_growing_output(self):
        body='module many;'+''.join('fn item'+str(i)+'()->str{return "needle'+('🌍'*800)+'";}' for i in range(40))+'fn main()->unit{}'
        _,revision=self.project(body);all_rows=[];offset=0;bounded=False
        while True:
            result=self.search('needle','--field','source','--limit','1000','--offset',str(offset),'--revision',revision)
            self.assertLessEqual(len(json.dumps(result,ensure_ascii=False).encode()),262144)
            self.assertTrue(result['nodes']);bounded |= result['page']['byte_limited'];all_rows += result['nodes']
            cursor=result['page']['next_offset']
            if cursor is None:break
            self.assertGreater(cursor,offset);offset=cursor
        self.assertTrue(bounded);self.assertEqual(len(all_rows),40)
        self.assertEqual(len({n['id'] for n in all_rows}),40)

    def test_queries_do_not_sync_physical_source_or_move_head_and_journal(self):
        _,revision=self.project();before=self.rows();original=(self.root/'main.nex').read_text()
        (self.root/'main.nex').write_text('invalid physical source')
        (self.root/'nex.json').write_text('{"language":"0.14","entry":"main.nex"}')
        self.assertEqual(self.search('choose')['revision'],revision)
        self.assertEqual(self.subgraph('choose')['revision'],revision)
        (self.root/'main.nex').unlink();(self.root/'library.nex').unlink()
        self.assertEqual(self.search('leaf')['revision'],revision)
        self.assertEqual(self.subgraph('library::middle')['revision'],revision)
        self.assertEqual(self.rows(),before)
        self.assertIn('choose',original)

    def test_archived_results_retain_old_dependencies_and_sources(self):
        _,old=self.project();original=self.subgraph('choose','--depth','3')
        (self.root/'main.nex').write_text(MAIN.replace('return lib::middle(lib::Box(lib::echo(0)));','return 7;'))
        current=self.cli('check')['revision'];self.assertNotEqual(old,current)
        latest=self.subgraph('choose','--depth','3')
        self.assertNotIn('library::middle',self.symbols(latest))
        self.assertEqual(self.subgraph('choose','--depth','3','--revision',old),original)
        self.assertEqual(self.cli('history')['head'],current)

    def test_dependency_radius_minimum_distances_and_explicit_boundary(self):
        self.project()
        zero=self.subgraph('choose','--depth','0')
        self.assertEqual(self.symbols(zero),{'app::choose'});self.assertTrue(zero['depth_limited'])
        one=self.subgraph('choose','--depth','1')
        self.assertIn('library::middle',self.symbols(one));self.assertNotIn('library::leaf',self.symbols(one))
        self.assertTrue(one['depth_limited'])
        all_nodes=self.subgraph('choose','--depth','8')
        distances={n['symbol']:n['distance'] for n in all_nodes['nodes']}
        self.assertEqual(distances['app::choose'],0);self.assertEqual(distances['library::middle'],1)
        self.assertEqual(distances['library::leaf'],2);self.assertFalse(all_nodes['depth_limited'])
        self.assertTrue(any(n['kind']=='type' for n in all_nodes['nodes']))
        self.assertEqual(all_nodes,self.subgraph('app::choose','--depth','8'))

    def test_reverse_and_bidirectional_walk_preserve_original_edge_direction(self):
        self.project();reverse=self.subgraph('library::leaf','--direction','dependents','--depth','2')
        self.assertTrue({'library::leaf','library::middle','app::choose'}.issubset(self.symbols(reverse)))
        pairs={(e['source']['symbol'],e['target']['symbol']) for e in reverse['edges']}
        self.assertIn(('library::middle','library::leaf'),pairs)
        self.assertNotIn(('library::leaf','library::middle'),pairs)
        both=self.subgraph('library::middle','--direction','both','--depth','1')
        self.assertTrue({'library::leaf','app::choose'}.issubset(self.symbols(both)))
        self.assertEqual(both['selection']['direction'],'both')

    def test_recursion_terminates_with_one_node_per_identity(self):
        self.project();cycle=self.subgraph('library::cycle_a','--depth','8')
        self.assertEqual(self.symbols(cycle),{'library::cycle_a','library::cycle_b'})
        self.assertEqual(len(cycle['nodes']),2);self.assertEqual(cycle['edge_page']['total'],2)
        self.assertFalse(cycle['depth_limited'])

    def test_independent_node_and_edge_pages_reference_checked_graph_ids(self):
        _,revision=self.project();full=self.subgraph('library','--entity','module','--depth','2','--limit','1000','--edge-limit','1000')
        expected={(n['kind'],n['symbol']):n for n in self.cli('identities','--limit','1000')['nodes'] if n['kind']!='operation'}
        for n in full['nodes']:
            self.assertEqual(n['id'],expected[(n['kind'],n['symbol'])]['id'])
            self.assertEqual(n['context_hash'],expected[(n['kind'],n['symbol'])]['context_hash'])
        nodes=[];edges=[];no=eo=0
        while no is not None or eo is not None:
            page=self.subgraph('library','--entity','module','--depth','2','--revision',revision,'--offset',str(no if no is not None else 10000000),'--edge-offset',str(eo if eo is not None else 10000000),'--limit','2','--edge-limit','3')
            self.assertEqual(page['query_hash'],full['query_hash']);nodes+=page['nodes'];edges+=page['edges']
            no=page['node_page']['next_offset'];eo=page['edge_page']['next_offset']
        self.assertEqual(nodes,full['nodes']);self.assertEqual(edges,full['edges'])
        ids={n['id'] for n in full['nodes']}
        self.assertTrue(all(e['source']['id'] in ids and e['target']['id'] in ids for e in edges))

    def test_derived_instances_are_discoverable_and_not_editable(self):
        self.project();functions=self.search('echo','--entity','function')
        source=next(n for n in functions['nodes'] if n['symbol']=='library::echo')
        derived=next(n for n in functions['nodes'] if n['symbol']=='library::echo<i64>')
        self.assertTrue(source['editable']);self.assertFalse(source['derived'])
        self.assertFalse(derived['editable']);self.assertTrue(derived['derived'])
        types=self.search('Box','--entity','type')
        self.assertTrue(any(n['derived'] and not n['editable'] for n in types['nodes']))
        sub=self.subgraph('library::echo<i64>')
        self.assertIn('library::echo',self.symbols(sub))

    def test_closure_helpers_remain_explicit_derived_readonly_nodes(self):
        source='module captures;fn make(n:i64)->(fn()->i64){return fn()->i64{return n;};}fn main()->i64{return make(42)();}'
        self.project(source)
        nodes=self.search('::','--entity','function','--field','symbol')['nodes']
        helpers=[n for n in nodes if n['derived']]
        self.assertTrue(helpers)
        self.assertTrue(all(not n['editable'] for n in helpers))
        selected=self.subgraph(helpers[0]['symbol'],'--depth','0')
        self.assertEqual(selected['root']['id'],helpers[0]['id'])

    def test_subgraph_byte_budgets_page_nodes_and_edges_independently(self):
        names=['wide_'+str(i)+'_'+('n'*1000) for i in range(80)]
        self.project('module wide;'+''.join('fn '+n+'()->i64{return 42;}' for n in names)+'fn main()->unit{}')
        nodes=[];edges=[];no=eo=0;nb=eb=False
        while no is not None or eo is not None:
            result=self.subgraph('wide','--entity','module','--depth','1','--limit','1000','--edge-limit','1000','--offset',str(no if no is not None else 10000000),'--edge-offset',str(eo if eo is not None else 10000000))
            self.assertLessEqual(len(json.dumps(result,ensure_ascii=False).encode()),262144)
            nb |= result['node_page']['byte_limited'];eb |= result['edge_page']['byte_limited']
            nodes+=result['nodes'];edges+=result['edges']
            nn=result['node_page']['next_offset'];en=result['edge_page']['next_offset']
            if nn is not None:self.assertGreater(nn,no)
            if en is not None:self.assertGreater(en,eo)
            no=nn;eo=en
        self.assertTrue(nb and eb)
        self.assertEqual(len(nodes),82);self.assertEqual(len({n['id'] for n in nodes}),82)
        self.assertEqual(len(edges),81)
        self.assertEqual({e['target']['symbol'] for e in edges},{'wide::'+n for n in names+['main']})

    def test_endpoint_handler_and_model_dependencies(self):
        source='''module api_query;import "std/api.nex" as api;
pub struct Reply{value:i64;}
server fn serve(context:api::Context)->result<Reply>{return ok(Reply(42));}
endpoint read("GET","/api/items")=serve;
fn main()->unit{}
'''
        self.project(source)
        match=self.search('read','--entity','endpoint');self.assertEqual(self.symbols(match),{'api_query::read'})
        sub=self.subgraph('read','--entity','endpoint','--depth','2')
        self.assertTrue({'api_query::read','api_query::serve','api_query::Reply'}.issubset(self.symbols(sub)))
        self.assertTrue(match['nodes'][0]['editable'])

    def test_invalid_requests_fail_before_creating_store(self):
        self.file.write_text('module no_store;fn main()->unit{}')
        cases=[('search',),('search','--query',''),('search','--query','x','--field','regex'),('search','--query','x','--entity','operation'),('search','--query','x','--limit','0'),('search','--query','x','--limit','1001'),('search','--query','x','--offset','-1'),('search','--query','x','--offset',''),('search','--query','x','--revision',''),('search','--query','x','--revision','unknown'),('search','--query','x','--depth','2'),('search',str(self.file),'--query','x'),('search','--query','x','--interpreter-only'),('search','--query','x','--','argument'),('subgraph','--symbol','x','--entity','all'),('subgraph','--symbol','x','--depth','9'),('subgraph','--symbol','x','--depth','-1'),('subgraph','--symbol','x','--edge-limit','0'),('subgraph','--symbol','x','--direction','sideways'),('subgraph','--symbol','x','--query','x'),('search','--query','x'*1025),('search','--query','\udcff'),('subgraph','--symbol','x'*8193)]
        for args in cases:
            with self.subTest(args=args):
                error=self.cli(*args,ok=False)
                self.assertIn(error['code'],{'E_OPTION','E_QUERY_OPTION'})
                self.assertFalse((self.root/'.nex').exists())

    def test_unknown_roots_and_tampered_graph_edges_fail_without_repairing_rows(self):
        self.project();before=self.rows()
        self.assertEqual(self.subgraph('absent',ok=False)['code'],'E_QUERY_SYMBOL')
        self.assertEqual(self.rows(),before)
        with sqlite3.connect(self.root/'.nex/graph.db') as db:
            db.execute('DELETE FROM graph_edges WHERE rowid=(SELECT rowid FROM graph_edges LIMIT 1)')
        tampered=self.rows()
        self.assertEqual(self.search('leaf',ok=False)['code'],'E_STORE')
        self.assertEqual(self.subgraph('choose',ok=False)['code'],'E_STORE')
        self.assertEqual(self.rows(),tampered)

    def test_output_file_and_followup_context_keep_complete_identity(self):
        self.project();out=self.root/'selection.json';response=self.search('choose','--output',out)
        selected=json.loads(out.read_text());self.assertTrue(response['ok'])
        self.assertEqual(response['query_hash'],selected['query_hash'])
        node=selected['nodes'][0];context=self.cli('context','--revision',selected['revision'],'--symbol',node['symbol'])
        self.assertEqual(context['revision'],selected['revision'])
        self.assertIn('fn choose',context['source'])

    def test_descriptor_guide_and_pack_agree(self):
        desc=self.cli('describe');pack=json.loads((harness.REPO/'llm/language-pack.json').read_text())
        self.assertIn('literal_source_search',desc['graph_query_features'])
        self.assertEqual(desc['graph_query_limits']['preview_bytes'],2048)
        self.assertEqual(desc['graph_query_schema'],pack['documents']['graph_query_schema'])
        self.assertEqual(self.cli('guide','--kind','query')['text'],(harness.REPO/'docs/queries.md').read_text())


if __name__=='__main__':unittest.main()
