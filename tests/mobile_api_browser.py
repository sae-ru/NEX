"""Opt-in separately hosted client -> real HTTPS NEX API in three browsers.

The temporary TLS certificate is accepted only in the test browser context;
this verifies CORS/fetch/application semantics, not production PKI deployment.
"""
import argparse
import functools
import http.server
import importlib.util
import json
import os
from pathlib import Path
import queue
import re
import shutil
import signal
import subprocess
import threading

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('compiler',type=Path)
parser.add_argument('project',type=Path,help='built fullstack client web project with locked dependencies')
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--browsers-path',type=Path)
args=parser.parse_args()
repo=Path(__file__).resolve().parents[1];compiler=args.compiler.resolve();project=args.project.resolve();root=args.output.absolute()
if os.path.lexists(root):raise SystemExit('requires a new output directory')
root.mkdir(mode=0o700)
(root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.21','entry':'source/server.nex'})+'\n')
spec=importlib.util.spec_from_file_location('mobile',repo/'tools/mobile_project.py');mobile=importlib.util.module_from_spec(spec);spec.loader.exec_module(mobile)
env=dict(os.environ)
if args.browsers_path:env['PLAYWRIGHT_BROWSERS_PATH']=str(args.browsers_path.resolve())
def cli(*arguments):
    result=subprocess.run([str(compiler),*map(str,arguments),'--json'],cwd=root,capture_output=True,text=True,timeout=240,env=env)
    assert result.returncode==0,result.stdout+result.stderr
    return json.loads(result.stdout)
shutil.copytree(repo/'examples/fullstack',root/'source')
built=cli('build',root/'source/server.nex','--target','server','--profile','release')
auth=root/'auth.json';tokens={engine:{who:cli('token','--user',engine+'-'+who,'--auth',auth)['token'] for who in ('alice','bob')} for engine in ('chromium','firefox','webkit')}
subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-sha256','-days','1','-subj','/CN=localhost',
                '-addext','subjectAltName=IP:127.0.0.1,DNS:localhost','-keyout',str(root/'key.pem'),'-out',str(root/'cert.pem')],capture_output=True,check=True)
(root/'key.pem').chmod(0o600)
shutil.copytree(project/'dist',root/'www')
class Static(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*arguments):pass
static=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Static,directory=str(root/'www')))
thread=threading.Thread(target=static.serve_forever,daemon=True);thread.start()
client='http://127.0.0.1:'+str(static.server_port)
script=project/'tests/mobile-api-browser.mjs';shutil.copyfile(repo/'tests/mobile-api-browser.mjs',script)
server=None;address=None;phases=[]
try:
    for phase in ('initial','restart'):
        command=[built['executable'],'--auth',str(auth),'--database',str(root/'data.sqlite'),'--cert',str(root/'cert.pem'),'--key',str(root/'key.pem'),
                 '--port','0' if address is None else address.rsplit(':',1)[1],'--cors-origin',client]
        server=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env)
        lines=queue.Queue();threading.Thread(target=lambda:lines.put(server.stdout.readline()),daemon=True).start()
        match=re.fullmatch(r'NEX server (https://127\.0\.0\.1:[0-9]+)\n',lines.get(timeout=15));assert match,'server did not start'
        address=match.group(1)
        if phase=='initial':receipt=mobile.configure_api(root/'www/index.html',address)
        for asset in (root/'www').rglob('*'):
            if asset.is_file():assert all(token.encode() not in asset.read_bytes() for roles in tokens.values() for token in roles.values())
        config=root/(phase+'-private.json');config.write_text(json.dumps({'client':client,'api':address,'tokens':tokens,'phase':phase,'result':str(root/(phase+'-result.json'))}));config.chmod(0o600)
        try:
            result=subprocess.run([env.get('NEX_NODE','node'),str(script),str(config)],cwd=project,env=env,capture_output=True,text=True,timeout=150)
            (root/(phase+'-browser.log')).write_text(result.stdout+result.stderr)
            assert result.returncode==0,result.stdout+result.stderr
            phases.append(json.loads((root/(phase+'-result.json')).read_text()))
        finally:
            server.send_signal(signal.SIGTERM);out,err=server.communicate(timeout=15);exit_code=server.returncode;server=None
            (root/(phase+'-server.log')).write_text(out+err)
            assert exit_code==0 and 'E_INTERNAL_LEAK' not in err and 'libc++abi' not in err
    report={'ok':True,'scope':'cross-origin HTTPS fetch/CORS/application semantics; ephemeral certificate trusted by test browser context',
            'compiler_sha256':mobile.sha(compiler),'server_sha256':mobile.sha(built['executable']),'host_configuration':receipt,'phases':phases}
    (root/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'ok':True,'browsers':3,'phases':2,'report':str(root/'verification.json')}))
finally:
    if server is not None:server.terminate();server.communicate(timeout=15)
    static.shutdown();static.server_close();thread.join(timeout=5)
