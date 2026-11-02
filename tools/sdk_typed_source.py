"""Installed027 typed CLI delivery and genuine026 graph migration/recovery."""
import collections
import hashlib
import json
from pathlib import Path
import sqlite3
import sys


def check_installed_typed_source(cli, run, root, resources, compiler):
    from sdk_acceptance import require
    root,resources,compiler=Path(root),Path(resources),Path(compiler)
    sha=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()
    descriptor=cli('describe','--field','source_exceptions')
    language=descriptor.get('language');require(language in ('0.27','0.28'),'SDK needs a known typed source language')
    require(descriptor.get('language')==language and descriptor['value'].get('typed_payloads') is True
            and descriptor['value'].get('finally') is True,'SDK lacks public027 typed source errors')
    destination=root/'typed-source-errors';destination.mkdir()
    test=resources/'tests/source_exceptions_public.py'
    run([sys.executable,'-B',test,compiler,'--output',destination/'execution'],timeout=900)
    execution_file=destination/'execution/report.json'
    execution=json.loads(execution_file.read_text())
    require(execution.get('ok') is True and execution.get('language')==language
            and execution.get('compiler_sha256')==sha(compiler),'SDK typed CLI used another compiler')
    typed=[row for row in execution['passed'] if row.get('ordinary_typed_CLI')]
    flags=('ordinary_typed_CLI','native_debug_release','typescript','checked_map',
           'actual_scalar_Wasm','effect_and_binding_rejections')
    require(len(typed)==1 and all(typed[0].get(key) is True for key in flags),
            'SDK lacks actual typed CLI/native/TypeScript/Wasm execution and rejected programs')
    checked=json.loads((destination/'execution/typed-check.stdout').read_text())
    mapping=json.loads((destination/'execution/typed-typescript/nex-map.json').read_text())
    require(mapping['schema']=='nex.typescript-map/2' and mapping['language']==language
            and mapping['revision']==checked['revision'],'installed typed map lost checked identity')

    metadata_file=resources/'tests/fixtures/language-0.26-typed-origin.json'
    sql_file=metadata_file.with_suffix('.sql');metadata=json.loads(metadata_file.read_text())
    require(sha(sql_file)==metadata['sql_sha256'] and metadata['language']=='0.26'
            and metadata['retagged_source'] is False,'SDK changed its genuine026 origin')
    origin=destination/'origin';origin.mkdir();(origin/'.nex').mkdir()
    physical=json.dumps({'schema':'nex.project/1','language':'0.26','entry':'main.nex'})+'\n'
    (origin/'nex.json').write_text(physical);(origin/'main.nex').write_text(metadata['source'])
    with sqlite3.connect(origin/'.nex/graph.db') as db:db.executescript(sql_file.read_text())
    def state(project):
        with sqlite3.connect(project/'.nex/graph.db') as db:
            db.execute('PRAGMA query_only=ON')
            schema=list(db.execute('SELECT * FROM sqlite_master ORDER BY name'))
            tables={name:collections.Counter(tuple(row) for row in db.execute('SELECT * FROM "'+name+'"'))
                    for name, in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        return schema,tables
    before=state(origin);require(len(before[1])==16,'genuine026 graph table set differs')
    require(cli('check',cwd=origin,expected_success=False).get('code')=='E_LANGUAGE_VERSION'
            and state(origin)==before,'SDK implicitly reinterpreted a026 project')
    plan=cli('migrate','--kind','plan',cwd=origin)
    require(plan.get('origin_verified') is True and plan.get('origin_language')=='0.26'
            and plan.get('target_language')==language and state(origin)==before,
            'SDK migration plan changed its origin')
    source='''module installed_typed_migration;
struct Failure{value:i64;}
fn main()->unit !{task,io}{
 try{task_yield();throw(Failure(42));}
 catch(error:Failure){task_yield();print(error.value);}
 finally{task_yield();}
}
'''
    candidate=plan['candidate']
    candidate['sources']={'schema':'nex.sources/1','entry':'main.nex','files':{'main.nex':source}}
    reviewed=destination/'reviewed.json';reviewed.write_text(json.dumps(candidate))
    rejected=cli('migrate','--candidate',reviewed,'--expected-revision','0'*64,
                 cwd=origin,expected_success=False)
    require(rejected.get('code')=='E_CONFLICT' and state(origin)==before,
            'SDK accepted a stale migration HEAD or changed its graph')
    migrated=cli('migrate','--candidate',reviewed,'--expected-revision',metadata['head'],cwd=origin)
    after=state(origin)
    require(migrated.get('language')==language and migrated['revision']!=metadata['head']
            and before[0]==after[0] and set(before[1])==set(after[1])
            and all(not (rows-after[1][name]) for name,rows in before[1].items() if name!='head'),
            'SDK migration lost original schema, rows, namespace or local IDs')
    require((origin/'nex.json').read_text()==physical and (origin/'main.nex').read_text()==metadata['source'],
            'SDK migration silently rewrote physical sources')
    snapshot=destination/'snapshot'
    cli('snapshot','--directory',snapshot,cwd=origin)
    require(state(origin)==after,'SDK snapshot changed its graph')
    recovered=destination/'recovered'
    cli('recover',snapshot,'--directory',recovered,cwd=destination)
    require(state(recovered)==after and not (recovered/'main.nex').exists(),
            'SDK recovery changed graph history or required original source files')
    require(cli('eval','--revision','HEAD',cwd=recovered)['stdout']=='42\n'
            and cli('run','--revision','HEAD','--profile','release',cwd=recovered,timeout=300)['stdout']=='42\n',
            'SDK recovered typed task execution differs')
    materialized=destination/'materialized'
    cli('export','--revision','HEAD','--directory',materialized,cwd=recovered)
    require(json.loads((materialized/'nex.json').read_text())['language']==language
            and cli('check',cwd=materialized)['revision']==migrated['revision'],
            'SDK explicit physical export lost its migrated identity')
    return {'schema':'nex.installed-typed-source/1','ok':True,'language':language,
            'compiler_sha256':sha(compiler),'helper_sha256':sha(__file__),
            'test_source_sha256':sha(test),'origin_metadata_sha256':sha(metadata_file),
            'origin_sql_sha256':sha(sql_file),'execution_report_sha256':sha(execution_file),
            'execution':execution,'revision':checked['revision'],'migration_revision':migrated['revision'],
            'reference_native_typescript':True,'checked_map':True,'scalar_Wasm':True,
            'wrong_type_guard_finally_suspension':True,'effect_and_immutable_binding_rejections':True,
            'genuine026_origin_verified':True,'stale_HEAD_rejected':True,
            'all16_tables_schema_rows_namespace_IDs_preserved':True,
            'physical_source_manifest_unchanged':True,'source_absent_snapshot_recovery':True,
            'recovered_reference_native_execution':True,'explicit_physical_export':True}
