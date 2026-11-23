#!/usr/bin/env python3
"""Run the checked three-backend agreement corpus with retained results."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command,cwd,timeout):
    started=time.monotonic()
    failure={}
    try:
        child=subprocess.run(list(map(str,command)),cwd=cwd,capture_output=True,timeout=timeout)
        code=child.returncode
        stderr=child.stderr.decode('utf-8',errors='replace')
        try:
            stdout=child.stdout.decode('utf-8')
        except UnicodeDecodeError as error:
            stdout=child.stdout.decode('utf-8',errors='replace')
            failure={'driver_error':'invalid_stdout_utf8','byte_offset':error.start,
                     'stdout_sha256':hashlib.sha256(child.stdout).hexdigest(),'process_exit_code':code}
            code=-1
    except subprocess.TimeoutExpired as error:
        stdout=(error.stdout or b'').decode(errors='replace')
        stderr=(error.stderr or b'').decode(errors='replace')+'\nagreement command timed out'
        code=-1
        failure={'driver_error':'timeout'}
    return {'command':[str(item) for item in command],'exit_code':code,'stdout':stdout,'stderr':stderr,
        'seconds':round(time.monotonic()-started,4),**failure}


def payload(result):
    for text in (result['stdout'],result['stderr']):
        text=text.strip()
        if not text.startswith('{'):continue
        try:return json.loads(text)
        except json.JSONDecodeError:continue
    return None


def code_of(result,data):
    if result.get('driver_error'):return ''
    if data and isinstance(data,dict):
        if isinstance(data.get('code'),str):return data['code']
        diagnostics=data.get('native_diagnostics')
        if isinstance(diagnostics,dict):
            for entry in diagnostics.get('diagnostics') or []:
                if not isinstance(entry,dict):continue
                if isinstance(entry.get('code'),str):return entry['code']
                report=entry.get('report')
                if isinstance(report,dict) and isinstance(report.get('code'),str):return report['code']
    for text in (result['stderr'],result['stdout']):
        for token in text.replace(':',' ').replace(',',' ').split():
            if token.startswith('E_') and token[2:].replace('_','').isalnum():return token
    return ''


def prepare(case,root,destination):
    source=(root/case['source']).resolve(strict=True)
    destination.mkdir(parents=True)
    (destination/'main.nex').write_bytes(source.read_bytes())
    (destination/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':case.get('language','0.28'),'entry':'main.nex'})+'\n')
    return destination


def strict_typescript(folder,env,timeout):
    selected=env.get('NEX_TSC','')
    if not selected:
        return {'ok':False,'error':'NEX_TSC is required for strict TypeScript agreement'}
    tsc=Path(selected).resolve(strict=True)
    pin=json.loads((ROOT/'web/package.json').read_bytes())['devDependencies']['typescript']
    package=tsc.parent.parent/'package.json'
    if not package.is_file() or json.loads(package.read_bytes()).get('version')!=pin:
        return {'ok':False,'error':'selected TypeScript compiler does not match the repository pin '+pin}
    result=run([env.get('NEX_NODE','node'),tsc,'--noEmit','--strict','--target','ES2022','--module','ESNext',
        '--moduleResolution','bundler','--allowImportingTsExtensions','--lib','ES2022,DOM',folder/'program.ts'],folder,timeout)
    result['ok']=result['exit_code']==0
    return result


def typescript(case,project,env,timeout):
    folder=project/'typescript'
    result=run([env['NEX_COMPILER'],'emit','--kind','typescript','--entry',case.get('entry','main'),'--directory',folder],project,timeout)
    if result['exit_code']!=0:
        return {'ok':False,'emit':result,'error':'TypeScript emission failed'}
    (folder/'package.json').write_text('{"type":"module"}\n')
    if case['kind']=='trap':
        driver=("import {entry} from './program.ts';import {NexError} from './nex-runtime.ts';\n"
            "try{entry();process.stdout.write('unexpected-success');}catch(e){if(!(e instanceof NexError))throw e;process.stdout.write(e.code);}\n")
    else:
        driver="import {entry} from './program.ts';\nentry();\n"
    (folder/'driver.mjs').write_text(driver)
    executed=run([env.get('NEX_NODE','node'),'--experimental-strip-types','driver.mjs'],folder,timeout)
    observed=executed['stdout']
    if case['kind']=='valid':
        ok=executed['exit_code']==0 and observed==case['expected_stdout']
    elif case['kind']=='trap':
        ok=executed['exit_code']==0 and observed==case['expected_code']
    else:
        ok=True
    strict=strict_typescript(folder,env,timeout)
    return {'ok':ok and strict.get('ok',False),'emit':result,'execute':executed,'stdout':executed['stdout'],
        'strict_typescript':strict,'observed_code':observed if case['kind']=='trap' else None}


def run_case(case,root,output,env,timeout):
    case_dir=output/case['name']
    if case_dir.exists():shutil.rmtree(case_dir)
    project=prepare(case,root,case_dir/'project')
    entry=case.get('entry','main')
    checks=[]
    started=time.monotonic()
    checked=run([env['NEX_COMPILER'],'check','--json'],project,timeout)
    data=payload(checked)
    observed=code_of(checked,data)
    if case['kind']=='rejected':
        checks.append({'backend':'check','ok':checked['exit_code']!=0 and observed==case['expected_check_code'],
            'expected_code':case['expected_check_code'],'observed_code':observed,'result':checked})
    else:
        if checked['exit_code']!=0 or not data or data.get('ok') is not True:
            checks.append({'backend':'check','ok':False,'observed_code':observed,'result':checked})
        else:
            checks.append({'backend':'check','ok':True,'result':checked})
        if case['kind']=='valid':
            expected=case['expected_stdout']
            reference=run([env['NEX_COMPILER'],'eval','--entry',entry,'--json'],project,timeout)
            reference_data=payload(reference)
            checks.append({'backend':'reference','ok':reference['exit_code']==0 and reference_data is not None
                and reference_data.get('stdout')==expected,'expected_stdout':expected,
                'observed_stdout':reference_data.get('stdout') if reference_data else None,'result':reference})
            for profile in ('debug','release'):
                native=run([env['NEX_COMPILER'],'run','--entry',entry,'--profile',profile,'--json'],project,timeout)
                native_data=payload(native)
                checks.append({'backend':'native-'+profile,'ok':native['exit_code']==0 and native_data is not None
                    and native_data.get('stdout')==expected,'observed_stdout':native_data.get('stdout') if native_data else None,
                    'result':native})
        else:
            expected=case['expected_code']
            reference=run([env['NEX_COMPILER'],'eval','--entry',entry,'--json'],project,timeout)
            reference_code=code_of(reference,payload(reference))
            checks.append({'backend':'reference','ok':reference['exit_code']!=0 and reference_code==expected,
                'expected_code':expected,'observed_code':reference_code,'result':reference})
            for profile in ('debug','release'):
                native=run([env['NEX_COMPILER'],'run','--entry',entry,'--profile',profile,'--json'],project,timeout)
                native_code=code_of(native,payload(native))
                checks.append({'backend':'native-'+profile,'ok':native['exit_code']!=0 and native_code==expected,
                    'expected_code':expected,'observed_code':native_code,'result':native})
    if case['kind']!='rejected' and not env.get('NEX_SKIP_TYPESCRIPT'):
        ts=typescript(case,project,env,timeout)
        checks.append({'backend':'typescript','ok':ts.get('ok') is True,'details':ts})
    elif case['kind']!='rejected':
        checks.append({'backend':'typescript','ok':True,'skipped':True})
    failures=[check['backend'] for check in checks if not check.get('ok')]
    return {'name':case['name'],'kind':case['kind'],'language':case['language'],'ok':not failures,'failures':failures,
        'seconds':round(time.monotonic()-started,4),'checks':checks,
        'source_sha256':sha(project/'main.nex')}


def select_cases(manifest, requested_language, names):
    # Explicit case languages pin version-specific expectations. The selected
    # project language only changes the default for otherwise portable inputs.
    language=requested_language or manifest.get('language','0.28')
    cases=[dict(case,language=case.get('language',language)) for case in
           (*manifest['cases'], *manifest.get('additional_cases',{}).get(language,[]))]
    registered=[case['name'] for case in cases]
    if len(registered)!=len(set(registered)):
        raise ValueError('duplicate agreement case names')
    if names:
        selected=set(names)
        missing=selected-set(registered)
        if missing:raise ValueError('unknown agreement case(s): '+', '.join(sorted(missing)))
        cases=[case for case in cases if case['name'] in selected]
    if not cases:raise ValueError('empty agreement corpus')
    return cases


def coverage(cases):
    counts={key:0 for key in ('check','reference','native-debug','native-release',
                              'typescript','typescript_executed','typescript_strict')}
    counts['executable_cases']=sum(case['kind']!='rejected' for case in cases)
    for case in cases:
        for check in case['checks']:
            if check.get('skipped'):continue
            counts[check['backend']]+=int(check['ok'])
            if check['backend']=='typescript':
                details=check['details']
                counts['typescript_executed']+=int('execute' in details)
                counts['typescript_strict']+=int(details.get('strict_typescript',{}).get('ok') is True)
    return counts


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler',required=True,type=Path)
    parser.add_argument('--root',type=Path,default=ROOT/'tests/agreement')
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--case',action='append',default=[])
    parser.add_argument('--timeout',type=int,default=180)
    parser.add_argument('--no-typescript',action='store_true')
    parser.add_argument('--require-complete',action='store_true',
        help='require every case and all executable backends, including strict TypeScript')
    parser.add_argument('--language-version',help='project language for portable cases, e.g. 0.30')
    args=parser.parse_args()
    if args.require_complete and (args.case or args.no_typescript or os.environ.get('NEX_SKIP_TYPESCRIPT')):
        parser.error('--require-complete requires all cases and TypeScript execution')
    compiler=args.compiler.resolve(strict=True)
    root=args.root.resolve(strict=True)
    output=args.output.resolve()
    output.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((root/'cases.json').read_bytes())
    if manifest.get('schema')!='nex.agreement/1':raise SystemExit('unsupported agreement manifest')
    try:cases=select_cases(manifest,args.language_version,args.case)
    except ValueError as error:parser.error(str(error))
    env={**os.environ,'NEX_COMPILER':str(compiler)}
    if args.no_typescript:env['NEX_SKIP_TYPESCRIPT']='1'
    skip_typescript=bool(env.get('NEX_SKIP_TYPESCRIPT'))
    if not skip_typescript and not env.get('NEX_TSC'):
        raise SystemExit('NEX_TSC is required; pass --no-typescript only for an explicitly reduced run')
    if args.language_version:
        supported=json.loads(subprocess.check_output(
            [compiler,'describe','--field','project_languages','--json']))['value']
        if args.language_version not in supported:parser.error('unsupported language version '+args.language_version)
    identity=json.loads(subprocess.check_output([compiler,'describe','--kind','index','--json']))
    report={'schema':'nex.agreement-run/1','ok':False,'compiler':str(compiler),'compiler_sha256':sha(compiler),
        'compiler_build':identity.get('compiler_build'),'language':identity.get('language'),
        'requested_language':args.language_version,'project_languages':sorted({case['language'] for case in cases}),
        'typescript_requested':not skip_typescript,'manifest_sha256':sha(root/'cases.json'),
        'cases':[],'failures':[]}
    for case in cases:
        result=run_case(case,root,output,env,args.timeout)
        report['cases'].append(result)
        if not result['ok']:report['failures'].append({'case':result['name'],'backends':result['failures']})
        print(json.dumps({'case':result['name'],'ok':result['ok'],'failures':result['failures'],
            'seconds':result['seconds']}),flush=True)
    measured=coverage(report['cases'])
    report['coverage']=measured
    executable=measured['executable_cases']
    report['typescript_executed']=executable>0 and measured['typescript_executed']==executable
    report['complete']=not args.case and executable>0 and measured['check']==len(cases) and all(
        measured[key]==executable for key in ('reference','native-debug','native-release','typescript',
                                              'typescript_executed','typescript_strict'))
    if args.require_complete and not report['complete']:
        report['failures'].append({'coverage':measured,'expected_cases':len(cases),'expected_executable':executable})
    report['ok']=not report['failures']
    report['registered_cases']=len(report['cases'])
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'ok':report['ok'],'cases':report['registered_cases'],'failures':report['failures'],
        'report':str(output/'report.json')}))
    return 0 if report['ok'] else 1


if __name__=='__main__':raise SystemExit(main())
