"""Run only the installed Workboard sub-workflow; never claim complete SDK acceptance."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('compiler',type=Path)
p.add_argument('--resources',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
p.add_argument('--browser',action='store_true')
a=p.parse_args();compiler=a.compiler.resolve(strict=True);resources=a.resources.resolve(strict=True)
root=a.output.resolve();root.mkdir(parents=True,exist_ok=False)
spec=importlib.util.spec_from_file_location('nex_sdk_workboard_focus',resources/'tools/sdk_acceptance.py')
acceptance=importlib.util.module_from_spec(spec);spec.loader.exec_module(acceptance)
environment={**os.environ,'NEX_RESOURCE_DIR':str(resources),'PYTHONDONTWRITEBYTECODE':'1'}
commands=[]
def run(command,cwd=root,expected_success=True,timeout=180):
    result=subprocess.run(list(map(str,command)),cwd=cwd,env=environment,
                          capture_output=True,text=True,timeout=timeout)
    commands.append({'command':list(map(str,command)),'cwd':str(cwd),'exit_code':result.returncode,
                     'stdout':result.stdout,'stderr':result.stderr})
    (root/'commands.json').write_text(json.dumps(commands,ensure_ascii=False,indent=2)+'\n')
    if (result.returncode==0)!=expected_success:raise RuntimeError('unexpected result; inspect '+str(root/'commands.json'))
    return result.stdout
def cli(*args,cwd=root,expected_success=True,timeout=180):
    return json.loads(run([compiler,*args,'--json'],cwd,expected_success,timeout))
value=acceptance.sdk_workboard.exercise(cli=cli,run=run,compiler=compiler,resources=resources,root=root,browser=a.browser)
report={'compiler_sha256':value['compiler_sha256'],'resource_hashes':value['resource_sha256'],
        'evidence':{'browser_build':a.browser,'workboard':value},'complete_SDK_workflow_claimed':False}
acceptance.sdk_workboard.validate(report)
(root/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'ok':True,'browser_build':a.browser,'HTTP_requests':24,'complete_SDK_workflow_claimed':False}))
