"""Compare the maintained CPU/task fixtures with emitted TypeScript on Windows."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from acceptance import linux_path
from compiler_cohort import COHORT_HELPER_SHA256, compiler_cohort

SYNC = """import {entry} from './program.ts';
let stdout='';console.log=value=>{stdout+=String(value)+'\\n';};
let result;try{entry();result={ok:true};}catch(e){result={ok:false,code:e.code};}
process.stdout.write(JSON.stringify({...result,stdout}));
"""
ASYNC = """import * as task from './nex-task-runtime.ts';
import {entry,sourceErrorContracts} from './program.ts';
let stdout='',statistics;console.log=value=>{stdout+=String(value)+'\\n';};
let result;try{await task.runTypedSourceErrors(task.call(()=>entry()),sourceErrorContracts,{complete:s=>{statistics=s;}});result={ok:true};}
catch(e){result={ok:false,code:e.code};}
if(!statistics?.completed||statistics.activeCalls||statistics.retainedFrames)throw new Error('task cleanup failed');
process.stdout.write(JSON.stringify({...result,stdout,statistics}));
"""


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--producer',required=True)
    parser.add_argument('--producer-environment',choices=('windows','wsl'),default='wsl')
    parser.add_argument('--distro',default='Ubuntu-22.04')
    parser.add_argument('--projects',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    native=args.producer_environment=='windows'
    if native:args.producer=str(Path(args.producer).resolve())
    cases=[('core','main',None,'Я\0🧠\n42\n'),
           *[('core',name,code,'') for name,code in [('overflow_add','E_OVERFLOW'),('overflow_sub','E_OVERFLOW'),('overflow_mul','E_OVERFLOW'),('overflow_div','E_OVERFLOW'),('divide_zero','E_DIV_ZERO'),('bad_index','E_BOUNDS')]],
           ('tasks','main',None,'42\n42\n'),('typed','main',None,'Я\0🧠\nfinished\n'),('typed','cancel','E_CANCELLED','')]
    report={'schema':'nex.windows-typescript-acceptance/1','ok':False,
            'helper_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'cohort_helper_sha256':COHORT_HELPER_SHA256,
            'producer_environment':'native Windows' if native else 'WSL','requires_WSL':not native,'TypeScript_execution_environment':'native Windows Node',
            'cases':[],'commands':[]}
    if native:report['producer_sha256']=hashlib.sha256(Path(args.producer).read_bytes()).hexdigest()
    def save(): (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    def run(label,argv,cwd=None):
        result=subprocess.run(list(map(str,argv)),capture_output=True,timeout=120,cwd=cwd)
        (out/(label+'.stdout')).write_bytes(result.stdout);(out/(label+'.stderr')).write_bytes(result.stderr)
        report['commands'].append({'argv':list(map(str,argv)),'exit_code':result.returncode,'cwd':str(cwd) if cwd else None});save()
        assert result.returncode==0,(label,result.stdout,result.stderr)
        return result.stdout
    report['node_version']=run('node-version',['node','--version']).decode().strip()
    try:
        def discover(*arguments):
            if native:
                return json.loads(run('discovery-'+arguments[0], [args.producer,*arguments,'--json'],cwd=out))
            return json.loads(run('discovery-'+arguments[0], ['wsl.exe','-d',args.distro,'--cd',linux_path(out),'--',args.producer,*arguments,'--json']))
        report['doctor']=discover('doctor')
        report['index']=discover('describe','--kind','index')
        report['cohort']=compiler_cohort(report['doctor'],report['index'])
        for module,entry,error,stdout in cases:
            label=module+'-'+entry;folder=out/label
            manifest=json.loads((args.projects/module/'nex.json').read_text(encoding='utf-8'))
            if manifest.get('language')!=report['cohort']['language']:
                raise RuntimeError('project language differs from the selected compiler; regenerate acceptance projects without rewriting their history')
            if native:
                metadata=json.loads(run(label+'-emit',[args.producer,'emit','--kind','typescript','--entry',entry,'--directory',folder,'--json'],cwd=(args.projects/module).resolve()))
            else:
                metadata=json.loads(run(label+'-emit',['wsl.exe','-d',args.distro,'--cd',linux_path(args.projects/module),'--',args.producer,'emit','--kind','typescript','--entry',entry,'--directory',linux_path(folder),'--json']))
            (folder/'package.json').write_text('{"type":"module"}\n',encoding='utf-8')
            mapping=json.loads((folder/'nex-map.json').read_text(encoding='utf-8'))
            assert mapping['execution'] in ('synchronous','task-generator'),mapping['execution']
            (folder/'driver.ts').write_text(ASYNC if mapping['execution']=='task-generator' else SYNC,encoding='utf-8')
            value=json.loads(run(label+'-node',['node','--experimental-strip-types','--no-warnings',folder/'driver.ts']))
            assert value['stdout']==stdout,(label,value)
            assert value['ok']==(error is None),(label,value)
            if error:assert value['code']==error,(label,value)
            report['cases'].append({'module':module,'entry':entry,'status':'passed','emission':metadata,'execution':mapping['execution'],'observation':value});save()
        report['ok']=True
    except Exception as error:
        report['failure']=str(error);raise
    finally:save()
    print(json.dumps({'ok':True,'cases':len(report['cases']),'report':str(out/'report.json')}))


if __name__=='__main__':main()
