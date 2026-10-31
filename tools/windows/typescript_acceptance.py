"""Compare the maintained CPU/task fixtures with emitted TypeScript on Windows."""
import argparse
import json
from pathlib import Path
import subprocess
from acceptance import linux_path

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
    parser.add_argument('--distro',default='Ubuntu-22.04')
    parser.add_argument('--projects',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    cases=[('core','main',None,'Я\0🧠\n42\n'),
           *[('core',name,code,'') for name,code in [('overflow_add','E_OVERFLOW'),('overflow_sub','E_OVERFLOW'),('overflow_mul','E_OVERFLOW'),('overflow_div','E_OVERFLOW'),('divide_zero','E_DIV_ZERO'),('bad_index','E_BOUNDS')]],
           ('tasks','main',None,'42\n42\n'),('typed','main',None,'Я\0🧠\nfinished\n'),('typed','cancel','E_CANCELLED','')]
    report={'schema':'nex.windows-typescript-acceptance/1','ok':False,
            'producer_environment':'WSL','TypeScript_execution_environment':'native Windows Node',
            'cases':[],'commands':[]}
    def save(): (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    def run(label,argv):
        result=subprocess.run(list(map(str,argv)),capture_output=True,timeout=120)
        (out/(label+'.stdout')).write_bytes(result.stdout);(out/(label+'.stderr')).write_bytes(result.stderr)
        report['commands'].append({'argv':list(map(str,argv)),'exit_code':result.returncode});save()
        assert result.returncode==0,(label,result.stdout,result.stderr)
        return result.stdout
    report['node_version']=run('node-version',['node','--version']).decode().strip()
    try:
        for module,entry,error,stdout in cases:
            label=module+'-'+entry;folder=out/label
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
