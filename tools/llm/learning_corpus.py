"""Validate frozen current learning inputs with the actual compiler and backends."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import language_pack as pack_tool

ROOT=Path(__file__).resolve().parents[2]
RUNNER='''import * as program from './program.ts';
import * as task from './nex-task-runtime.ts';
const logs=[];console.log=value=>logs.push(String(value));let statistics,result;
try{if(@ASYNC@)await task.runTypedSourceErrors(task.call(()=>program.entry()),program.sourceErrorContracts,{complete:s=>{statistics=s;}});else program.entry();result={ok:true};}
catch(error){result={ok:false,code:error.code,message:error.message};}
if(@ASYNC@&&(!statistics?.completed||statistics.activeCalls||statistics.retainedFrames))throw new Error('learning task cleanup failed');
process.stdout.write(JSON.stringify({...result,stdout:logs.join('\\n')+(logs.length?'\\n':'')})+'\\n');
'''


def terminate(child):
    if os.name=='nt':
        if child.poll()is None:subprocess.run([str(Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/taskkill.exe'),'/PID',str(child.pid),'/T','/F'],capture_output=True,timeout=15)
    else:
        try:os.killpg(child.pid,signal.SIGTERM)
        except ProcessLookupError:pass
    try:return child.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        if os.name=='nt':child.kill()
        else:
            try:os.killpg(child.pid,signal.SIGKILL)
            except ProcessLookupError:pass
        return child.communicate(timeout=10)


def contained(root,relative):
    if not isinstance(relative,str)or not relative or Path(relative).is_absolute():raise ValueError('expected a relative resource path')
    path=(root/relative).resolve();path.relative_to(root)
    return path


def read_inputs(resources,spec):
    if spec.get('schema')!='nex.learning-spec/1'or spec.get('path_base')!='resource_root':raise ValueError('unsupported learning specification')
    examples=spec.get('examples');ids=set();all_files={};cases=[]
    if not isinstance(examples,list)or not examples:raise ValueError('no learning examples')
    for example in examples:
        name=example.get('id','')
        if not name or name in ids or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-'for c in name):raise ValueError('invalid or duplicate case id')
        ids.add(name);files={}
        if example.get('kind')=='valid':
            project=contained(resources,example['project']);manifest=pack_tool.parse((project/'nex.json').read_bytes())
            if manifest.get('language')!=spec['language']:raise ValueError('example manifest has a different language: '+name)
            for p in sorted(project.rglob('*')):
                relative=p.relative_to(project)
                if any(x in {'.git','.nex','build','node_modules','__pycache__'}for x in relative.parts):continue
                if p.is_symlink():raise ValueError('learning input symlink: '+name)
                if p.is_file():files[relative.as_posix()]=p.read_bytes()
            if manifest.get('entry')not in files or not isinstance(example.get('expected_stdout'),str)or type(example.get('expected_tests'))is not int or example['expected_tests']<1:raise ValueError('incomplete positive case: '+name)
            for relative,raw in files.items():all_files[project.joinpath(relative).relative_to(resources).as_posix()]=hashlib.sha256(raw).hexdigest()
        elif example.get('kind')=='rejected':
            p=contained(resources,example['source']);files={'main.nex':p.read_bytes(),'nex.json':(json.dumps({'schema':'nex.project/1','language':spec['language'],'entry':'main.nex'})+'\n').encode()}
            all_files[p.relative_to(resources).as_posix()]=hashlib.sha256(files['main.nex']).hexdigest()
            if not isinstance(example.get('expected_check_code'),str):raise ValueError('missing rejection code')
        else:raise ValueError('unknown learning case kind')
        cases.append((example,files))
    return cases,all_files


def tests_passed(value,count,backend):
    rows=value.get('tests',[])
    return value.get('ok')is True and len(rows)==count and all(x.get('ok')is True and not x.get('skipped',False)and x.get('native')is(backend=='native')and x.get('web')is(backend=='typescript')for x in rows)


def validate(compiler,resources,output,node,tsc):
    compiler=compiler.resolve();resources=resources.resolve();output=output.resolve();output.mkdir(parents=True,exist_ok=False)
    spec_path=resources/'llm/corpus-spec.json';spec_raw=spec_path.read_bytes();spec=pack_tool.parse(spec_raw);proof,_=pack_tool.discover(compiler,resources)
    if not proof['ok']:raise ValueError('language pack contract does not match compiler')
    if spec['language']!=proof['language']:raise ValueError('learning specification does not match compiler language')
    cases,pins=read_inputs(resources,spec)
    if not node or not Path(node).is_file()or not tsc or not Path(tsc).is_file():raise ValueError('complete corpus validation requires Node and the matching TypeScript compiler; set NEX_NODE/NEX_TSC')
    workspace=Path(tempfile.mkdtemp(prefix='nex-learning-'))
    if any((p/'nex.json').exists()for p in [workspace,*workspace.parents]):raise ValueError('learning workspace must be outside existing NEX projects')
    commands=[];errors=[];rows=[];start=time.monotonic()
    env={k:v for k,v in os.environ.items()if not k.startswith(('NEX_','PYTHON','LD_','DYLD_'))}
    env.update(NEX_RESOURCE_DIR=str(resources),NEX_NODE=str(node),NEX_TSC=str(tsc),PYTHONDONTWRITEBYTECODE='1')
    if os.environ.get('NEX_NPM_CACHE'):env['NEX_NPM_CACHE']=os.environ['NEX_NPM_CACHE']
    report={'schema':'nex.learning-validation/1','ok':False,'language':proof['language'],'toolchain':proof['toolchain'],'compiler_sha256':proof['compiler_sha256'],'compiler_build':proof['compiler_build'],'descriptor_hash':proof['descriptor_hash'],'manifest_sha256':proof['manifest_sha256'],'spec_sha256':hashlib.sha256(spec_raw).hexdigest(),'inputs':pins,'workspace':str(workspace),'commands':commands,'cases':rows,'errors':errors,'physical_GPU_or_browser_execution_claimed':False,'SDK_qualification_claimed':False}
    def run(name,args,cwd,expected=0):
        child=subprocess.Popen(list(map(str,args)),cwd=cwd,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=os.name!='nt',creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name=='nt'else 0)
        timeout=False
        try:
            try:stdout,stderr=child.communicate(timeout=180)
            except subprocess.TimeoutExpired:timeout=True;stdout,stderr=terminate(child)
        except BaseException:terminate(child);raise
        number=len(commands);stem=f'{number:03d}-{name}'
        (output/(stem+'.stdout')).write_bytes(stdout);(output/(stem+'.stderr')).write_bytes(stderr)
        commands.append({'name':name,'argv':list(map(str,args)),'cwd':str(cwd),'exit_code':child.returncode,'timed_out':timeout,'stdout_sha256':hashlib.sha256(stdout).hexdigest(),'stderr_sha256':hashlib.sha256(stderr).hexdigest(),'stdout_file':stem+'.stdout','stderr_file':stem+'.stderr'})
        if timeout or child.returncode!=expected:errors.append({'step':name,'reason':'unexpected process outcome'});return None
        try:return pack_tool.parse(stdout)
        except (ValueError,UnicodeError):errors.append({'step':name,'reason':'invalid JSON output'});return None
    def accept(name,value,check):
        if value is None:return False
        if not check(value):errors.append({'step':name,'reason':'observable result differs'});return False
        return True
    prepared=[]
    try:
        # Check every source before paying for native or TypeScript execution.
        for example,files in cases:
            name=example['id'];project=workspace/name;project.mkdir()
            for relative,raw in files.items():
                p=contained(project.resolve(),relative);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
                snapshot=output/'inputs'/name/relative;snapshot.parent.mkdir(parents=True,exist_ok=True);snapshot.write_bytes(raw)
            rejected=example['kind']=='rejected';step=name+'-frontend';value=run(step,[compiler,'check','--json'],project,1 if rejected else 0)
            passed=accept(step,value,lambda v:v.get('ok')is False and v.get('code')==example['expected_check_code'])if rejected else accept(step,value,lambda v:v.get('ok')is True)
            rows.append({'id':name,'kind':example['kind'],'frontend_passed':passed,'observations':[]});prepared.append((example,project,rows[-1]))
        if not errors:
            for example,project,row in prepared:
                if example['kind']=='rejected':continue
                name=example['id'];expected=example['expected_stdout'];count=example['expected_tests']
                for suffix,flags,check in [
                    ('reference-main',['eval'],lambda v:v.get('ok')is True and v.get('stdout')==expected),
                    ('reference-tests',['test','--interpreter-only'],lambda v:tests_passed(v,count,'reference')),
                    ('native-tests',['test','--profile','release','--build-directory',workspace/'native-cache'],lambda v:tests_passed(v,count,'native')),
                    ('release-main',['run','--profile','release','--build-directory',workspace/'native-cache'],lambda v:v.get('ok')is True and v.get('exit_code')==0 and v.get('stdout')==expected),
                    ('typescript-tests',['test','--target','web'],lambda v:tests_passed(v,count,'typescript'))]:
                    step=name+'-'+suffix;value=run(step,[compiler,*flags,'--json'],project);passed=accept(step,value,check);row['observations'].append({'backend':suffix,'passed':passed})
                directory=project/'typescript-main';step=name+'-typescript-emit';emitted=run(step,[compiler,'emit','--kind','typescript','--directory',directory,'--json'],project)
                if accept(step,emitted,lambda v:v.get('ok')is True):
                    mapping=pack_tool.parse((directory/'nex-map.json').read_bytes());asynchronous=mapping['execution']=='task-generator';runner=directory/'run-main.mjs';runner.write_text(RUNNER.replace('@ASYNC@',json.dumps(asynchronous)))
                    step=name+'-typescript-main';value=run(step,[node,'--experimental-strip-types',runner],project)
                    passed=accept(step,value,lambda v:v.get('ok')is True and v.get('stdout')==expected);row['observations'].append({'backend':'typescript-main','passed':passed,'asynchronous':asynchronous})
                print(json.dumps({'case':name,'passed':all(x['passed']for x in row['observations'])and len(row['observations'])==6}),flush=True)
        if spec_path.read_bytes()!=spec_raw or pack_tool.sha(compiler)!=proof['compiler_sha256']:errors.append({'step':'final-input-check','reason':'compiler or specification changed'})
        if pack_tool.sha(resources/'llm/language-pack.json')!=proof['manifest_sha256']:errors.append({'step':'final-input-check','reason':'language pack changed'})
        if any(pack_tool.sha(resources/path)!=pin for path,pin in pins.items()):errors.append({'step':'final-input-check','reason':'source inputs changed'})
        report.update(ok=not errors,wall_ms=round((time.monotonic()-start)*1000),validated_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),valid_projects=sum(x['kind']=='valid'for x in rows),rejected_programs=sum(x['kind']=='rejected'for x in rows))
    finally:
        if report['ok']:shutil.rmtree(workspace);report['successful_workspace_removed']=True
        else:report['failed_workspace_retained']=True
        (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    return report,spec


def labels(report,spec,report_sha256):
    if not report['ok']:raise ValueError('failed corpus validation cannot publish passed labels')
    rows=[]
    for example in spec['examples']:
        row=dict(example)
        if row['kind']=='valid':
            prefix=row['project']+'/';row['files_sha256']={key[len(prefix):]:value for key,value in report['inputs'].items()if key.startswith(prefix)}
            row['source_sha256']=row['files_sha256']['main.nex']
        else:row['source_sha256']=report['inputs'][row['source']]
        rows.append(row)
    validation={key:report[key]for key in ['compiler_sha256','compiler_build','descriptor_hash','manifest_sha256','spec_sha256','validated_utc','valid_projects','rejected_programs']}
    validation.update(report_sha256=report_sha256,checks=['frontend','reference_main','reference_tests','native_release_tests','typescript_tests','native_release_main','typescript_main'],GPU_or_browser_execution_claimed=False,labelled_counterexamples_rechecked=True)
    return {'schema':'nex.learning-corpus/2','language':report['language'],'toolchain':report['toolchain'],'validation_status':'passed','capability_authority':spec['capability_authority'],'path_base':'repository_root','definition':'llm/corpus-spec.json','historical_record':spec['historical_record'],'historical_record_sha256':spec['historical_record_sha256'],'examples':rows,'validation':validation}


def publish(report,spec,destination,resources,report_path):
    resources=resources.resolve()
    if not report['ok']:raise ValueError('failed validation cannot publish current labels')
    expected={x['id']:x for x in spec['examples']};observed={x['id']:x for x in report['cases']}
    if len(observed)!=len(report['cases'])or set(observed)!=set(expected):raise ValueError('incomplete validated case set')
    backends={'reference-main','reference-tests','native-tests','release-main','typescript-tests','typescript-main'}
    for name,row in observed.items():
        if not row['frontend_passed']:raise ValueError('unaccepted frontend')
        values=row['observations']
        if expected[name]['kind']=='valid'and(len(values)!=len(backends)or{x['backend']for x in values}!=backends or not all(x['passed']for x in values)):raise ValueError('incomplete backend validation')
    history=contained(resources,spec['historical_record'])
    if pack_tool.sha(history)!=spec['historical_record_sha256']:raise ValueError('historical corpus record changed')
    if pack_tool.sha(resources/'llm/corpus-spec.json')!=report['spec_sha256']or pack_tool.sha(resources/'llm/language-pack.json')!=report['manifest_sha256']:raise ValueError('manifest or definition changed after validation')
    if any(pack_tool.sha(resources/path)!=pin for path,pin in report['inputs'].items()):raise ValueError('learning inputs changed after validation')
    content=json.dumps(labels(report,spec,pack_tool.sha(report_path)),ensure_ascii=False,indent=2)+'\n'
    destination=destination.resolve();temporary=destination.with_name(destination.name+'.tmp');temporary.write_text(content);temporary.replace(destination)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--compiler',required=True,type=Path);parser.add_argument('--resources',type=Path,default=ROOT);parser.add_argument('--output',required=True,type=Path);parser.add_argument('--publish',type=Path);args=parser.parse_args()
    try:
        node=os.environ.get('NEX_NODE')or shutil.which('node');tsc=os.environ.get('NEX_TSC')or str(args.resources/'web/node_modules/typescript/bin/tsc')
        report,spec=validate(args.compiler,args.resources,args.output,node,tsc)
        if report['ok']and args.publish:publish(report,spec,args.publish,args.resources,args.output/'report.json')
        print(json.dumps({'schema':report['schema'],'ok':report['ok'],'valid_projects':report.get('valid_projects',0),'rejected_programs':report.get('rejected_programs',0),'errors':report['errors'],'report':str(args.output/'report.json')},ensure_ascii=False));raise SystemExit(0 if report['ok']else 1)
    except (OSError,ValueError,subprocess.SubprocessError)as error:
        print(json.dumps({'schema':'nex.learning-validation/1','ok':False,'error':str(error)}));raise SystemExit(2)
