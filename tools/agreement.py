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
    try:
        child=subprocess.run(list(map(str,command)),cwd=cwd,capture_output=True,text=True,timeout=timeout)
        code,stdout,stderr=child.returncode,child.stdout,child.stderr
    except subprocess.TimeoutExpired as error:
        code,stdout,stderr=-1,error.stdout or '',(error.stderr or '')+'\nagreement command timed out'
    return {'command':[str(item) for item in command],'exit_code':code,'stdout':stdout,'stderr':stderr,
        'seconds':round(time.monotonic()-started,4)}


def payload(result):
    for text in (result['stdout'],result['stderr']):
        text=text.strip()
        if not text.startswith('{'):continue
        try:return json.loads(text)
        except json.JSONDecodeError:continue
    return None


def code_of(result,data):
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
    pin=json.loads((ROOT/'web/package.json').read_text())['devDependencies']['typescript']
    package=tsc.parent.parent/'package.json'
    if not package.is_file() or json.loads(package.read_text()).get('version')!=pin:
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
    observed=executed['stdout'].strip()
    if case['kind']=='valid':
        expected=case['expected_stdout'].rstrip('\n').split('\n') if case['expected_stdout'] else []
        actual=executed['stdout'].rstrip('\n').split('\n') if executed['stdout'] else []
        ok=executed['exit_code']==0 and actual==expected
    elif case['kind']=='trap':
        ok=observed==case['expected_code']
    else:
        ok=True
    strict=strict_typescript(folder,env,timeout)
    return {'ok':ok and strict.get('ok',False),'execute':executed,'stdout':executed['stdout'],
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
    return {'name':case['name'],'kind':case['kind'],'ok':not failures,'failures':failures,
        'seconds':round(time.monotonic()-started,4),'checks':checks,
        'source_sha256':sha(project/'main.nex')}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler',required=True,type=Path)
    parser.add_argument('--root',type=Path,default=ROOT/'tests/agreement')
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--case',action='append',default=[])
    parser.add_argument('--timeout',type=int,default=180)
    parser.add_argument('--no-typescript',action='store_true')
    args=parser.parse_args()
    compiler=args.compiler.resolve(strict=True)
    root=args.root.resolve(strict=True)
    output=args.output.resolve()
    output.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((root/'cases.json').read_text())
    if manifest.get('schema')!='nex.agreement/1':raise SystemExit('unsupported agreement manifest')
    cases=manifest['cases']
    if args.case:
        selected=set(args.case);cases=[case for case in cases if case['name'] in selected]
        missing=selected-{case['name'] for case in cases}
        if missing:raise SystemExit('unknown agreement case(s): '+', '.join(sorted(missing)))
    env={**os.environ,'NEX_COMPILER':str(compiler)}
    if args.no_typescript:env['NEX_SKIP_TYPESCRIPT']='1'
    if 'NEX_SKIP_TYPESCRIPT' not in env and not env.get('NEX_TSC'):
        raise SystemExit('NEX_TSC is required; pass --no-typescript only for an explicitly reduced run')
    identity=json.loads(subprocess.check_output([compiler,'describe','--kind','index','--json'],text=True))
    report={'schema':'nex.agreement-run/1','ok':False,'compiler':str(compiler),'compiler_sha256':sha(compiler),
        'compiler_build':identity.get('compiler_build'),'language':identity.get('language'),
        'typescript_executed':not args.no_typescript,'manifest_sha256':sha(root/'cases.json'),
        'cases':[],'failures':[]}
    for case in cases:
        result=run_case(case,root,output,env,args.timeout)
        report['cases'].append(result)
        if not result['ok']:report['failures'].append({'case':result['name'],'backends':result['failures']})
        print(json.dumps({'case':result['name'],'ok':result['ok'],'failures':result['failures'],
            'seconds':result['seconds']}),flush=True)
    report['ok']=not report['failures']
    report['registered_cases']=len(report['cases'])
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'ok':report['ok'],'cases':report['registered_cases'],'failures':report['failures'],
        'report':str(output/'report.json')}))
    return 0 if report['ok'] else 1


if __name__=='__main__':raise SystemExit(main())
