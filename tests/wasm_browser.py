"""Opt-in actual three-engine execution of an already-built scalar module."""
import argparse,functools,hashlib,http.server,json,os,pathlib,shutil,subprocess,threading,time
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('module',type=pathlib.Path);parser.add_argument('--playwright-module',required=True,type=pathlib.Path)
parser.add_argument('--browsers-path',required=True,type=pathlib.Path);parser.add_argument('--output',required=True,type=pathlib.Path)
args=parser.parse_args();repo=pathlib.Path(__file__).resolve().parents[1]
module=args.module.resolve();output=args.output.resolve();output.mkdir();site=output/'site';site.mkdir()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
files={name:sha(module/name) for name in ['module.wasm','module.mjs','module.json','THIRD_PARTY_NOTICES.txt']}
for name in files:shutil.copyfile(module/name,site/name)
shutil.copyfile(repo/'examples/wasm/index.html',site/'index.html')
package=args.playwright_module.resolve();expected=json.loads((repo/'web/package.json').read_text())['devDependencies']['@playwright/test']
assert json.loads((package.parent/'package.json').read_text())['version']==expected
class Handler(http.server.SimpleHTTPRequestHandler):
 def log_message(self,*arguments):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(site)))
server.daemon_threads=True;thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();started=time.monotonic()
try:
 command=[os.environ.get('NEX_NODE','node'),str(repo/'tests/wasm-browser.mjs'),
  'http://127.0.0.1:'+str(server.server_port),str(package),str(output/'engines.json')]
 environment={**os.environ,'PLAYWRIGHT_BROWSERS_PATH':str(args.browsers_path.resolve())}
 with (output/'browser.log').open('w') as log:process=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,env=environment,timeout=300)
 assert process.returncode==0,'actual browser check failed; inspect '+str(output/'browser.log')
 report=json.loads((output/'engines.json').read_text());assert report['ok'] and len(report['engines'])==3
 assert files=={name:sha(module/name) for name in files}
 report.update(module_files=files,inputs_unchanged=True,playwright_version=expected,
  seconds=round(time.monotonic()-started,3),scope='actual desktop browser compute example only; not physical device or complete SDK acceptance')
 (output/'verification.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
finally:server.shutdown();thread.join(5);server.server_close()
