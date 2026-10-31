"""Opt-in real-engine responsiveness of a private production generator module."""
import argparse,functools,hashlib,http.server,json,os,shutil,subprocess,threading,time
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('module',type=Path);parser.add_argument('tools',type=Path);parser.add_argument('--browsers-path',required=True,type=Path);parser.add_argument('--output',required=True,type=Path)
args=parser.parse_args();source=Path(__file__).resolve().parents[1];out=args.output.resolve();out.mkdir(exist_ok=False)
module=args.module.resolve();tools=args.tools.resolve();node=os.environ.get('NEX_NODE','node');env={**os.environ,'PLAYWRIGHT_BROWSERS_PATH':str(args.browsers_path.resolve()),'PYTHONDONTWRITEBYTECODE':'1'}
started=time.monotonic();files={}
for name in ['program.ts','nex-runtime.ts','nex-bytes.ts','nex-task-runtime.ts','nex-source-exception-runtime.ts']:
 data=(module/name).read_bytes();(out/name).write_bytes(data);files[name]=hashlib.sha256(data).hexdigest()
(out/'package.json').write_text('{"type":"module"}\n', newline="\n")
(out/'index.html').write_text('''<!doctype html><html><head><meta charset="utf-8"><link rel="icon" href="data:,"><title>NEX private task probe</title></head><body><button id="start">Start</button><button id="stop">Stop</button><output role="status" id="status">Ready</output><script type="module" src="/browser.ts"></script></body></html>''', newline="\n")
(out/'browser.ts').write_text('''import * as task from './nex-task-runtime.ts';
import {entry} from './program.ts';
const state={started:false,done:false,ticks:0,polls:0,frames:0,stopClicks:0,code:'',statistics:undefined as task.Statistics|undefined};
(globalThis as typeof globalThis & {__nexTaskBrowserState:typeof state}).__nexTaskBrowserState=state;
const controller=new AbortController();
document.getElementById('stop')!.onclick=()=>{++state.stopClicks;controller.abort();};
document.getElementById('start')!.onclick=()=>{
 if(state.started)return;state.started=true;document.getElementById('status')!.textContent='Running';
 const clock=setInterval(()=>{++state.ticks;},1);
 const frame=()=>{if(!state.done){++state.frames;requestAnimationFrame(frame);}};requestAnimationFrame(frame);
 task.run(task.call(()=>entry()),{steps:100000000,signal:controller.signal,observe:(_job,r)=>{if(r.operation==='$poll')++state.polls;},complete:s=>{state.statistics=s;}})
 .then(()=>{state.code='UNEXPECTED_RETURN';}).catch(error=>{state.code=error.code??'HOST_ERROR';})
 .finally(()=>{clearInterval(clock);state.done=true;document.getElementById('status')!.textContent=state.code;});
};
''', newline="\n")
(out/'vite.config.mjs').write_text("export default {build:{target:'esnext',minify:false,sourcemap:true,modulePreload:false}};\n", newline="\n")
build=subprocess.run([node,str(tools/'vite/bin/vite.js'),'build',str(out),'--config',str(out/'vite.config.mjs')],text=True,capture_output=True,env=env,timeout=180)
(out/'build.stdout').write_text(build.stdout, newline="\n");(out/'build.stderr').write_text(build.stderr, newline="\n");assert build.returncode==0,build.stdout+build.stderr
for p in (out/'dist').rglob('*'):
 if p.is_file() and p.suffix in ('.js','.map','.html'):assert b'UNREACHABLE_SERVER_TASK_SECRET' not in p.read_bytes(),p
class Handler(http.server.SimpleHTTPRequestHandler):
 def log_message(self,*_):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(out/'dist')))
thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
try:
 result=subprocess.run([node,str(source/'tests/task_typescript_browser.mjs'),str(tools/'playwright/index.mjs'),'http://127.0.0.1:'+str(server.server_port)+'/'],text=True,capture_output=True,env=env,timeout=180)
 (out/'browser.stdout').write_text(result.stdout, newline="\n");(out/'browser.stderr').write_text(result.stderr, newline="\n");assert result.returncode==0,result.stdout+result.stderr
 report=json.loads(result.stdout);assert report['ok'] and report['production_browser_engines']==3
 report.update(source_module_sha256=files,unreachable_server_literal_excluded=True,public_source_tasks=False,nex_ui_adapter_tasks=False,seconds=round(time.monotonic()-started,3))
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n', newline="\n");print(json.dumps(report))
finally:server.shutdown();server.server_close();thread.join()
