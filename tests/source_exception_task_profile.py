"""Real emitted native task profiling, including caught/uncaught source and control outcomes."""
import argparse, hashlib, json, os, subprocess, sys, tempfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('emitter');p.add_argument('reference');p.add_argument('compiler');p.add_argument('--output');p.add_argument('--existing-execution');a=p.parse_args()
source=Path(__file__).resolve().parents[1]
out=Path(a.output or os.environ.get('NEX_EXCEPTION_TASK_PROFILE_OUTPUT') or tempfile.mkdtemp(prefix='nex-source-task-profile-')).resolve();out.mkdir(parents=True,exist_ok=True)
names=['task-future-repeated','task-uncaught-root','task-uncaught-drain','task-rethrow-future','sequential-uncaught-nul','task-body-error-cancels-children','task-source-code-looks-fatal','task-assert-is-fatal','profile-data-cancel-code']
execution=Path(a.existing_execution).resolve() if a.existing_execution else out/'execution'
cmd=[sys.executable,'-B',str(source/'tests/source_exception_task_native.py'),a.emitter,a.reference,a.compiler,'--profile','--output',str(execution)]
for name in names:cmd += ['--case',name]
if not a.existing_execution:
    result=subprocess.run(cmd,text=True,capture_output=True,timeout=1800);(out/'driver.stdout').write_text(result.stdout, newline="\n");(out/'driver.stderr').write_text(result.stderr, newline="\n");assert result.returncode==0,(result.returncode,result.stdout[-1000:],result.stderr[-4000:])
native=json.loads((execution/'report.json').read_text());assert native['ok'] and native['comparisons']==18 and native['source_programs']==9
report={'ok':False,'cases':[],'execution':str(execution),'execution_report_sha256':hashlib.sha256((execution/'report.json').read_bytes()).hexdigest(),'verified_existing_execution':bool(a.existing_execution),'profile_api':'emitSourceExceptionTasksPrototypeNativeProfile','raw_runtime_schema':'nex.profile-runtime/2','public_profile_CLI_support':False,'archived':False,'security_checks_deferred_by_user':True}
def save():(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n', newline="\n")
save()
for item in native['cases']:
    f=execution/item['name']/('O'+item['optimization'])/'profile.json';raw=json.loads(f.read_text());assert hashlib.sha256(f.read_bytes()).hexdigest()==item['profile_sha256']
    assert raw['schema']=='nex.profile-runtime/2' and raw['kind']=='native_tasks' and not raw['incomplete']
    assert raw['build']['schema']=='nex.private-source-profile-build/1' and raw['build']['archived'] is False and 'revision' not in raw['build']
    for key in ['dropped_events','dropped_functions','dropped_frames','dropped_allocations','untracked_frees','dropped_tasks','invalid_transitions','clock_failures']:assert raw[key]==0,(item['name'],key,raw[key])
    assert all(raw['completeness'][key] for key in ['aggregates','timeline','memory','cpu','elapsed','lifetime'])
    assert raw['tasks'] and all(t['terminal'] and not t['active_invocations'] for t in raw['tasks'])
    assert all(i['outcome'] in ['completed','aborted'] for i in raw['invocations'])
    assert all(fn['calls']==fn['completed']+fn['aborted'] for fn in raw['functions'])
    assert len(raw['memory'])==2 and all(pool['live']==pool['live_shallow_bytes']==0 and pool['allocations']==pool['frees'] for pool in raw['memory'])
    root=min(raw['tasks'],key=lambda t:t['id']);expected='completed' if item['expected']['kind']=='return' else 'aborted';assert root['outcome']==expected,(item['name'],root,expected)
    aborted=sum(t['outcome']=='aborted' for t in raw['tasks'])
    if item['name'] in ['task-future-repeated','profile-data-cancel-code']:assert aborted>=1 and all(t['outcome']!='cancelled' for t in raw['tasks']),(item['name'],raw['tasks'])
    if item['expected']['kind']!='return':assert aborted>=1 and any(i['outcome']=='aborted' for i in raw['invocations'])
    report['cases'].append({'name':item['name'],'optimization':item['optimization'],'profile_sha256':item['profile_sha256'],'source_sha256':item['source_sha256'],'root_outcome':root['outcome'],'aborted_tasks':aborted,'tasks':len(raw['tasks']),'invocations':len(raw['invocations']),'passed':True});save()
report.update(ok=True,comparisons=len(report['cases']),source_programs=9);save();print(json.dumps({'ok':True,'comparisons':18,'report':str(out/'report.json')}))
