#!/usr/bin/env python3
"""Installed Linux SDK: authoring, native/web semantics, tasks, ELF and storage."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from compiler_cohort import COHORT_HELPER_SHA256, compiler_cohort


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sdk',type=Path)
    parser.add_argument('--source',type=Path,default=Path('/src'))
    parser.add_argument('--output-root',type=Path,default=Path('/build'))
    args=parser.parse_args()
    sdk=args.sdk.resolve();nex=sdk/'bin/nex';resources=sdk/'share/nex';source=args.source.resolve();output_root=args.output_root.resolve()
    output_root.mkdir(parents=True,exist_ok=True)
    report={'schema':'nex.linux-sdk-smoke/2','ok':False};output=output_root/'sdk-smoke.json'
    with tempfile.TemporaryDirectory(prefix='nex-linux-sdk-') as temporary:
        root=Path(temporary);env={**os.environ,'NEX_RESOURCE_DIR':str(resources)}
        def cli(*args,cwd=None):
            p=subprocess.run([str(nex),*map(str,args),'--json'],cwd=cwd or root,env=env,capture_output=True,text=True,timeout=180)
            value=json.loads(p.stdout);assert p.returncode==0,(args,p.stdout,p.stderr);return value
        try:
            descriptor=cli('describe');doctor=cli('doctor');assert 'linux' in doctor['host']
            index=cli('describe','--kind','index')
            cohort=compiler_cohort(doctor,index,languages=('0.23','0.24','0.25','0.26','0.27','0.28'))
            pack=json.loads((resources/'llm/language-pack.json').read_text())
            language=doctor['language']
            assert descriptor['version']==pack['language_version']==language
            assert cli('guide','--kind','linux')['text']
            report.update(language=language,toolchain=doctor['version'],cohort=cohort,compiler_sha256=hashlib.sha256(nex.read_bytes()).hexdigest(),helper_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),cohort_helper_sha256=COHORT_HELPER_SHA256)
            indexed=[*pack['documents'].values(),*pack['examples'].values()]
            for name in indexed:
                assert (resources/name).read_bytes()==(source/name).read_bytes(),name
            constrained=root/'constraints';constrained.mkdir();shutil.copyfile(resources/'examples/constraints.nex',constrained/'main.nex')
            (constrained/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':language,'entry':'main.nex'}))
            constrained_output=cli('eval',cwd=constrained)['stdout'];assert constrained_output=='NEX 🧠\n42\n[1,2,3]\n'
            assert cli('run',cwd=constrained)['stdout']==constrained_output;cli('test',cwd=constrained);cli('test','--target','web',cwd=constrained)
            report['constrained_backends']='native/interpreter/TypeScript passed'
            matched=root/'matching';matched.mkdir();shutil.copyfile(resources/'examples/matching.nex',matched/'main.nex')
            (matched/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':language,'entry':'main.nex'}))
            assert cli('eval',cwd=matched)['stdout']=='42\none:42\n7\n';assert cli('run',cwd=matched)['stdout']=='42\none:42\n7\n'
            cli('test',cwd=matched);cli('test','--target','web',cwd=matched);report['matching_backends']='native/interpreter/TypeScript passed'

            for name in ('main.nex','model.nex'):shutil.copyfile(resources/'examples/generics'/name,root/name)
            (root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':language,'entry':'main.nex'}))
            checked=cli('check');assert cli('context','--symbol','main')['symbol']=='generics::main'
            expected=cli('eval')['stdout'];cli('test');cli('test','--target','web')
            built=cli('build');assert built['host_compatible']
            metadata=json.loads(Path(built['metadata']).read_text());assert metadata['linker'].endswith('/ld.lld')
            subprocess.run(['llvm-dwarfdump','--verify',built['executable']],check=True,stdout=subprocess.DEVNULL)
            exported=output_root/'standalone-app';cli('build','--output',exported)
            independent=subprocess.run([str(exported)],env={**env,'NEX_RESOURCE_DIR':'/unavailable'},capture_output=True,text=True,timeout=20)
            assert (independent.returncode,independent.stdout)==(0,expected),independent.stderr
            dependencies=subprocess.check_output(['ldd',str(exported)],text=True)
            assert 'LLVM' not in dependencies and 'libz3' not in dependencies
            profile=cli('profile','--events','0','--scenario','installed Linux generic values');assert profile['exit_code']==0
            config=root/'native.json';config.write_text(json.dumps({'schema':'nex.toolchain/1','target':doctor['host'],'compiler':doctor['native_compiler']}))
            snapshot=cli('toolchain',config);assert snapshot['inputs']['schema']=='nex.toolchain-snapshot/2'
            task=cli('task',root/'main.nex','--kind','init')
            for check in task['checks']:check.update(toolchain='linux',toolchain_hash=snapshot['hash'])
            taskfile=root/'task.json';taskfile.write_text(json.dumps(task));catalog=root/'catalog.json';catalog.write_text(json.dumps({'linux':config.name}))
            acceptance=cli('task',taskfile,'--kind','run','--toolchains',catalog)
            for name in ('main.nex','model.nex'): (root/name).unlink()
            assert cli('run','--revision',checked['revision'])['stdout']==expected
            replay=cli('task',acceptance['output'],'--kind','replay','--toolchains',catalog)
            assert replay['task_hash']==acceptance['task_hash'] and replay['status']=='passed'
            evidence=output_root/'sdk-evidence';evidence.mkdir(exist_ok=True)
            saved=[]
            for result in (acceptance,replay):
                destination=evidence/result['run_id']
                shutil.copytree(Path(result['output']).parent,destination,ignore=shutil.ignore_patterns('workspaces'))
                saved.append(str(destination/'receipt.json'))
            (evidence/'native.json').write_text(json.dumps(snapshot['manifest']))
            (evidence/'catalog.json').write_text(json.dumps({'linux':'native.json'}))
            report.update(task_document=task,toolchain_manifest=snapshot['manifest'],toolchain_catalog={'linux':'native.json'},receipts=saved)
            shared=output_root/'sdk-shared-work';shared.mkdir(exist_ok=True)
            (shared/'main.nex').write_text('module shared_linux; fn main() -> unit !{io} { print(7); } test fn example() -> unit { assert(3 + 4 == 7); }')
            (shared/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':language,'entry':'main.nex'}))
            cli('check',cwd=shared);assert cli('run',cwd=shared)['stdout']=='7\n'
            shared_task=cli('task',shared/'main.nex','--kind','init',cwd=shared)
            shared_file=shared/'task.json';shared_file.write_text(json.dumps(shared_task))
            shared_run=cli('task',shared_file,'--kind','run',cwd=shared)
            shared_replay=cli('task',shared_run['output'],'--kind','replay',cwd=shared)
            assert shared_replay['status']=='passed'
            proof=root/'proof';shutil.copytree(resources/'examples/verification',proof)
            (proof/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':language,'entry':'main.nex'}))
            verified=cli('verify','--contracts',proof/'contracts.json',cwd=proof);assert verified['ok'] and verified['functions'] and all(f['status']=='proven' for f in verified['functions'])
            service=root/'service';service.mkdir()
            (service/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':language,'entry':'main.nex'}))
            (service/'main.nex').write_text('''module linux_sdk_server;
import "std/http.nex" as http;
server fn handle(request:http::Request) -> http::Response !{db} {
  if request.method == "POST" {
    let saved:result<bool> = store_put("value",request.body);
    return match saved {ok(_) => http::Response(200,request.user + ":" + request.body,"text/plain"),err(_,_) => http::Response(500,"storage failure","text/plain")};
  }
  let value:result<str> = store_get("value");
  return match value {ok(text) => http::Response(200,request.user + ":" + text,"text/plain"),err(_,_) => http::Response(404,"missing","text/plain")};
}
''')
            auth=service/'auth.json';tokens={user:cli('token','--user',user,'--auth',auth,cwd=service)['token'] for user in ('alice','bob')}
            server=cli('build','--target','server',cwd=service)
            def launch():
                p=subprocess.Popen([server['executable'],'--auth',str(auth),'--database',str(service/'data.sqlite'),'--port','0'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
                lines=queue.Queue();threading.Thread(target=lambda:lines.put(p.stdout.readline()),daemon=True).start()
                try:
                    line=lines.get(timeout=30);match=re.match(r'NEX server (http://127\.0\.0\.1:[0-9]+)',line);assert match,line
                    return p,match.group(1)
                except BaseException:
                    p.terminate();p.communicate(timeout=20);raise
            def stop(p):
                p.send_signal(signal.SIGTERM);stdout,stderr=p.communicate(timeout=20);assert p.returncode==0,stdout+stderr;assert 'E_INTERNAL_LEAK' not in stderr
            def request(base,user,body=None):
                headers={'Authorization':'Bearer '+tokens[user],'Content-Type':'text/plain; charset=utf-8'}
                req=urllib.request.Request(base+'/api/value',data=None if body is None else body.encode(),headers=headers)
                try:
                    with urllib.request.urlopen(req,timeout=15) as r:return r.status,r.read().decode()
                except urllib.error.HTTPError as e:return e.code,e.read().decode()
            p,base=launch()
            try:
                actual=request(base,'alice','Unicode 🧠');assert actual==(200,'alice:Unicode 🧠'),actual
                assert request(base,'bob')[0]==404
                assert request(base,'bob','separate')==(200,'bob:separate')
                assert request(base,'alice')==(200,'alice:Unicode 🧠')
            finally:stop(p)
            p,base=launch()
            try:
                assert request(base,'alice')==(200,'alice:Unicode 🧠')
                assert request(base,'bob')==(200,'bob:separate')
            finally:stop(p)
            report.update(ok=True,host=doctor['host'],llvm=doctor['llvm'],verifier=doctor['verifier_version'],resources=len(indexed),native_stdout=expected,standalone_dependencies=dependencies.splitlines(),linker=metadata['linker'],task_hash=acceptance['task_hash'],archived_replay=True,scalar_proof='proven',authenticated_storage='isolated and persistent across restart')
        finally:output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()
