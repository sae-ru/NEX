"""Installed025 source-error execution; standard-library-only SDK helper."""
import hashlib
import json
import os
from pathlib import Path
import shutil


SOURCE = r'''module installed_errors;
fn fail()->i64 !{throw}{
 let held:list<str>=["owned","λ\u0000🙂"];assert(len(held)==2);
 throw("APP\u0000CODE","λ\u0000🙂");
}
fn recovered()->i64 !{task}{
 try {
  return with_tasks(1,fn(scope:task_scope)->i64 !{task,throw}{
   let child:task<i64>=task_spawn(scope,fn()->i64 !{task,throw}{task_yield();return fail();});
   return task_wait(child);
  });
 }catch(code,message){assert(code=="APP\u0000CODE" && message=="λ\u0000🙂");return 42;}
}
fn uncaught()->i64 !{throw}{return fail();}
fn rethrown()->i64 !{throw}{try{return fail();}catch(code,message){throw;}}
fn fatal()->i64{try{return 1/0;}catch(code,message){return 0;}}
fn main()->unit !{io,task}{print(recovered());}
test fn recovered_test()->unit !{task}{assert(recovered()==42);}
'''


def check_installed_source_exceptions(cli, run, root, resources):
    def require(value, message):
        if not value:
            raise RuntimeError(message)

    root, resources = Path(root), Path(resources)
    doctor = cli('doctor')
    language=doctor.get('language')
    require(language in {'0.25','0.26'} and
            Path(doctor.get('runtime', '')).resolve() == (resources/'runtime/runtime.cpp').resolve(),
            'source-error gate did not select the requested SDK resources')
    discovery = cli('describe', '--field', 'source_exceptions')
    feature = discovery['value']
    require(feature.get('source_language') == language and feature.get('frontend') is True
            and feature.get('reference') is True, 'SDK does not advertise ordinary025 source errors')
    project = root/'source-exceptions'
    project.mkdir()
    (project/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':language,'entry':'main.nex'})+'\n')
    source = project/'main.nex'
    source.write_text(SOURCE)
    checked = cli('check', cwd=project)
    throw_sites = [row['site'] for row in cli('operations','--symbol','fail',cwd=project)['nodes']
                   if row['kind']=='statement.throw']
    require(len(throw_sites)==1,'SDK lost the source throw operation')
    reference = cli('eval', cwd=project)
    require(reference.get('stdout') == '42\n', 'source-error reference recovery differs')
    for profile in ('debug', 'release'):
        native = cli('run', '--profile', profile, cwd=project, timeout=240)
        require(native.get('stdout') == '42\n' and native.get('exit_code') == 0,
                'source-error native recovery differs: '+profile)
    cli('test', cwd=project, timeout=240)
    cli('test', '--target', 'web', cwd=project, timeout=240)

    def pools(profile):
        memory = profile.get('memory')
        return (isinstance(memory, list) and bool(memory)
                and all(row.get('live') == 0 and row.get('allocations') == row.get('frees') for row in memory))

    measured = cli('profile', '--scenario', 'installed source recovery', cwd=project, timeout=240)
    profile = json.loads(Path(measured['output']).read_text())
    require(profile.get('ok') is True and profile.get('exit_code') == 0 and pools(profile),
            'caught source exception retained owned values')
    require(any(row.get('aborted', 0) > 0 for row in profile.get('functions', [])),
            'source-error profile lost the aborted callee')
    native_sources = []
    for entry, code in [('uncaught','E_SOURCE_EXCEPTION'), ('rethrown','E_SOURCE_EXCEPTION'), ('fatal','E_DIV_ZERO')]:
        reference = cli('eval', '--entry', entry, cwd=project, expected_success=False)
        require(reference.get('code') == code, 'reference exception/trap boundary differs: '+entry)
        native = cli('run', '--entry', entry, cwd=project, expected_success=False, timeout=240)
        diagnostics = native.get('native_diagnostics', {}).get('diagnostics', [])
        require(native.get('exit_code') == 70,'native error exit differs: '+entry)
        if code=='E_SOURCE_EXCEPTION':
            records=[json.loads(line[len('NEX_SOURCE_EXCEPTION '):]) for line in native.get('stderr','').splitlines()
                     if line.startswith('NEX_SOURCE_EXCEPTION ')]
            require(len(records)==1,'native source-error record missing: '+entry)
            record=records[0];site=record.get('source',{})
            require(record.get('code')==reference.get('source_exception',{}).get('code')=='APP\0CODE'
                    and record.get('message')==reference['source_exception'].get('message')=='λ\0🙂'
                    and record.get('line')==reference.get('line') and site.get('kind')=='statement.throw'
                    and site.get('compiler_build')==discovery['compiler_build']
                    and site.get('operation_site')==throw_sites[0],
                    'native source error lost its payload or original checked site: '+entry)
            native_sources.append(site)
        else:
            require(len(diagnostics)==1 and diagnostics[0].get('report',{}).get('code')==code,
                    'native checked trap entered the source-error channel')
    require(native_sources[0]==native_sources[1],'native rethrow changed the original source site')
    failed = cli('profile', '--entry', 'uncaught', '--scenario', 'installed uncaught source error',
                 cwd=project, expected_success=False, timeout=240)
    failed_profile = json.loads(Path(failed['output']).read_text())
    require(failed_profile.get('ok') is False and failed_profile.get('exit_code') == 70 and pools(failed_profile),
            'uncaught source exception retained owned values')

    node = os.environ.get('NEX_NODE') or shutil.which('node')
    require(node, 'source-error SDK acceptance requires Node')
    errors = []
    for entry in ('uncaught', 'rethrown'):
        folder = project/('typescript-'+entry)
        cli('emit', '--kind', 'typescript', '--entry', entry, '--directory', folder, cwd=project)
        driver = folder/'source-error.ts'
        driver.write_text(r'''import assert from 'node:assert/strict';
import { entry } from './program.ts';
import { details } from './nex-source-exception-runtime.ts';
let payload;
try { entry(); } catch (error) { payload = details(error); }
assert(payload);assert.equal(payload.code,'APP\u0000CODE');assert.equal(payload.message,'λ\u0000🙂');
process.stdout.write(JSON.stringify({code:payload.code,message:payload.message,site:payload.site}));
''')
        errors.append(json.loads(run([node, '--experimental-strip-types', '--no-warnings', driver], cwd=folder)))
    require(errors[0] == errors[1], 'TypeScript rethrow changed its original payload or source site')
    invalid = project/'missing-effect.nex'
    invalid.write_text('module missing_effect;fn main()->unit{throw("USER","missing throw effect");}\n')
    require(cli('check', invalid, cwd=project, expected_success=False).get('code') == 'E_EFFECT',
            'source throw escaped effect checking')
    handlers={}
    if language=='0.26':
        from sdk_source_handlers import check_installed_source_handlers
        handlers=check_installed_source_handlers(cli,root,resources)
    return {'schema':'nex.installed-source-exceptions/1','ok':True,'language':language,'handler_filters':handlers,
            'revision':checked['revision'],'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
            'helper_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'native_profiles':['debug','release'],'reference':True,'typescript':True,
            'joined_child_payload':True,'uncaught_source_error':True,'rethrow_site_preserved':True,
            'native_source_transport':'NEX_SOURCE_EXCEPTION',
            'checked_trap_not_caught':True,'effect_rejection':True,
            'caught_profile_cleanup':True,'uncaught_profile_cleanup':True,
            'resource_helper_sha256':hashlib.sha256((resources/'web/nex-source-exception-runtime.ts').read_bytes()).hexdigest()}


def main():
    import argparse
    import subprocess
    import traceback
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sdk',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    sdk=args.sdk.resolve();compiler=sdk/'bin/nex';resources=sdk/'share/nex'
    if not compiler.is_file() or not (resources/'web/nex-source-exception-runtime.ts').is_file():
        parser.error('a025 installed SDK with source-error resources is required')
    root=args.output.resolve();root.mkdir(parents=True,exist_ok=False)
    logs=root/'logs';logs.mkdir()
    report={'schema':'nex.source-exception-sdk-gate/1','ok':False,'sdk':str(sdk),'commands':[],
            'compiler_sha256':hashlib.sha256(compiler.read_bytes()).hexdigest(),'full_SDK_accepted':False}
    environment={**os.environ,'NEX_RESOURCE_DIR':str(resources)}

    def run(command,cwd=root,expected_success=True,timeout=180):
        result=subprocess.run(list(map(str,command)),cwd=cwd,env=environment,capture_output=True,text=True,timeout=timeout)
        number=len(report['commands']);out=logs/(str(number)+'.stdout');err=logs/(str(number)+'.stderr')
        out.write_text(result.stdout);err.write_text(result.stderr)
        report['commands'].append({'argv':list(map(str,command)),'cwd':str(cwd),'exit_code':result.returncode,
                                   'expected_success':expected_success,'stdout':str(out),'stderr':str(err)})
        if (result.returncode==0)!=expected_success:
            raise RuntimeError('unexpected command result: '+str(command)+'; inspect '+str(err))
        return result.stdout

    def cli(*arguments,**options):
        return json.loads(run([compiler,*arguments,'--json'],**options))

    try:
        report['evidence']=check_installed_source_exceptions(cli,run,root,resources)
        report['ok']=True
    except BaseException as error:
        report.update(error=repr(error),traceback=traceback.format_exc())
    finally:
        (root/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'ok':report['ok'],'report':str(root/'report.json'),'full_SDK_accepted':False}))
    raise SystemExit(0 if report['ok'] else 1)


if __name__=='__main__':
    main()
