"""Opt-in browser checks for the internal binary primitive; no source bytes type."""
import argparse
import functools
import hashlib
import http.server
import json
import os
from pathlib import Path
import subprocess
import threading

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('project',type=Path,help='Existing locked web project with TypeScript/Playwright installed')
parser.add_argument('--output',required=True,type=Path,help='New evidence directory')
parser.add_argument('--browsers-path',type=Path)
args=parser.parse_args();root=Path(__file__).resolve().parents[1];project=args.project.resolve();output=args.output.resolve()
if output.exists():parser.error('--output must be new; existing evidence is preserved')
tsc=project/'node_modules/typescript/bin/tsc';playwright=project/'node_modules/playwright/index.mjs'
if not tsc.is_file() or not playwright.is_file():parser.error('project needs installed locked TypeScript and Playwright')
output.mkdir(parents=True);public=output/'public';public.mkdir()
report={'ok':False,'source_bytes_exposed':False,'source_sha256':hashlib.sha256((root/'web/nex-bytes.ts').read_bytes()).hexdigest()}
with (output/'compile.log').open('w') as log:
    subprocess.run(['node',str(tsc),'--strict','--target','ES2020','--module','ESNext','--moduleResolution','Bundler',
        '--rootDir',str(root/'web'),'--outDir',str(public),str(root/'web/nex-bytes.ts')],stdout=log,stderr=subprocess.STDOUT,check=True)
(public/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>NEX byte runtime test</title>')
report['emitted_sha256']=hashlib.sha256((public/'nex-bytes.js').read_bytes()).hexdigest()

class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*args):pass

server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(public)))
thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
environment=dict(os.environ)
if args.browsers_path:environment['PLAYWRIGHT_BROWSERS_PATH']=str(args.browsers_path.resolve())
try:
    with (output/'browser.log').open('w') as log:
        subprocess.run(['node',str(root/'tests/bytes-browser-runner.mjs'),str(playwright),
            'http://127.0.0.1:'+str(server.server_address[1]),str(output/'browser-results.json')],
            env=environment,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
    browsers=json.loads((output/'browser-results.json').read_text());assert browsers['ok']
    report.update(ok=True,browsers=browsers['browsers'])
finally:
    server.shutdown();server.server_close();thread.join(timeout=5)
    (output/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
