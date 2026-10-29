"""Installed026 filtered handlers and genuine025 history; no source fallback."""
import ast
import hashlib
import json
from pathlib import Path
import sqlite3


def check_installed_source_handlers(cli, root, resources):
    root,resources=Path(root),Path(resources)
    def require(value,message):
        if not value:raise RuntimeError(message)
    def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
    feature=cli('describe','--field','source_exceptions')['value']
    require(feature.get('source_language')=='0.26' and feature.get('handler_filters') is True,
            'SDK lacks checked026 handler filters')
    fixture=resources/'tests/exception_handlers.py'
    tree=ast.parse(fixture.read_text())
    sources=[ast.literal_eval(node.value) for node in tree.body if isinstance(node,ast.Assign)
             and any(isinstance(target,ast.Name) and target.id=='SOURCE' for target in node.targets)]
    require(len(sources)==1 and isinstance(sources[0],str),'SDK handler source corpus is not a literal')
    project=root/'source-handler-filters';project.mkdir()
    (project/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.26','entry':'main.nex'}))
    (project/'main.nex').write_text(sources[0])
    checked=cli('check',cwd=project)
    require(cli('eval',cwd=project).get('stdout')=='42\n','SDK handler reference execution differs')
    counts=[]
    for profile in ('debug','release'):
        tested=cli('test','--profile',profile,cwd=project,timeout=300)
        require(tested.get('ok') and len(tested.get('tests',[]))==7,'SDK native handler cases differ')
        counts.append(len(tested['tests']))
    tested=cli('test','--target','web',cwd=project,timeout=300)
    require(tested.get('ok') and len(tested.get('tests',[]))==7,'SDK TypeScript handler cases differ')
    counts.append(len(tested['tests']))
    measured=cli('profile','--scenario','installed handler filters',cwd=project,timeout=300)
    memory=json.loads(Path(measured['output']).read_text()).get('memory',[])
    require(memory and all(p.get('live')==0 and p.get('allocations')==p.get('frees') for p in memory),
            'SDK handler filters retained owned values')

    metadata_file=resources/'tests/fixtures/language-0.25-handler-origin.json'
    sql_file=resources/'tests/fixtures/language-0.25-handler-origin.sql'
    metadata=json.loads(metadata_file.read_text());sql=sql_file.read_bytes()
    require(sha(sql_file)==metadata['sql_sha256'] and metadata['producer']['language']=='0.25'
            and metadata.get('retagged_source') is False,'SDK genuine025 fixture identity differs')
    origin=root/'handler-origin025';(origin/'.nex').mkdir(parents=True)
    (origin/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.25','entry':'main.nex'}))
    (origin/'main.nex').write_text(metadata['source'])
    graph=origin/'.nex/graph.db'
    with sqlite3.connect(str(graph)) as connection:connection.executescript(sql.decode())
    def snapshot():
        with sqlite3.connect(str(graph)) as connection:
            schema=list(connection.execute('SELECT * FROM sqlite_master ORDER BY name'))
            names=[r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
            return schema,{name:list(connection.execute('SELECT * FROM "'+name+'"')) for name in names}
    before=snapshot();plan=cli('migrate','--kind','plan',cwd=origin)
    require(plan.get('origin_verified') and plan.get('origin_language')=='0.25' and
            plan.get('target_language')=='0.26' and plan.get('target_valid') is False and snapshot()==before,
            'SDK did not preserve genuine025 before the reviewed keyword repair')
    candidate=plan['candidate'];candidate['sources']['files']['main.nex']=metadata['source'].replace('finally','finished')
    path=origin/'reviewed.json';path.write_text(json.dumps(candidate))
    changed=cli('migrate','--candidate',path,'--expected-revision',metadata['head'],cwd=origin)
    after=snapshot()
    require(before[0]==after[0] and set(before[1])==set(after[1]) and len(before[1])==16,
            'SDK handler migration changed the original graph schema')
    require(all(set(rows)<=set(after[1][name]) for name,rows in before[1].items() if name!='head')
            and len(after[1]['revisions'])==3,'SDK handler migration lost original rows or IDs')
    require(cli('eval','--revision',changed['revision'],cwd=origin).get('stdout')==metadata['actual_origin_eval_stdout']
            and (origin/'main.nex').read_text()==metadata['source']
            and json.loads((origin/'nex.json').read_text())['language']=='0.25',
            'SDK migration changed physical source or target behavior')
    return {'ok':True,'language':'0.26','reference':True,'native_debug_release':True,'typescript':True,
            'cases_per_engine':counts,'owned_cleanup':True,'genuine025_origin_verified':True,
            'all16_tables_rows_schema_IDs_preserved':True,'reviewed_keyword_repair':True,
            'physical_source_manifest_unchanged':True,'revision':checked['revision'],
            'helper_sha256':sha(Path(__file__)),'test_source_sha256':sha(fixture),
            'origin_metadata_sha256':sha(metadata_file),'origin_sql_sha256':sha(sql_file)}
