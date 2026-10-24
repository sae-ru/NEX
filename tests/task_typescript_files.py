"""020/retained019 TS task execution and server-file reachability boundary."""
import argparse,hashlib,json,os,shutil,subprocess,tempfile
from pathlib import Path

parser=argparse.ArgumentParser();parser.add_argument('probe');parser.add_argument('--output')
args=parser.parse_args();probe=Path(args.probe).resolve();source=Path(__file__).resolve().parents[1]
out=Path(args.output).resolve() if args.output else Path(tempfile.mkdtemp(prefix='nex-ts-file-boundary-'))
if args.output:out.mkdir(exist_ok=False)
node=os.environ.get('NEX_NODE','node');records=[]
def command(argv,expected=0):
    result=subprocess.run(list(map(str,argv)),capture_output=True,text=True,timeout=90)
    assert result.returncode==expected,(argv,result.returncode,result.stdout,result.stderr)
    return result.stdout
def emit(path,name,mode='emit',entry='main',error=None):
    folder=out/name;value=json.loads(command([probe,path,folder,mode,entry],1 if error else 0))
    if error:
        assert not value['ok'] and value['code']==error and not folder.exists(),value
        records.append({'name':name,'rejected':error});return value,None
    assert value['ok'],value
    mapping=json.loads((folder/'nex-map.json').read_text())
    assert mapping['schema']=='nex.typescript-map/1' and mapping['language']==value['language'] and mapping['revision']==value['revision']
    if value['asynchronous']:
        assert (folder/'nex-task-runtime.ts').read_bytes()==(source/'web/nex-task-runtime.ts').read_bytes()
    else:assert not (folder/'nex-task-runtime.ts').exists()
    for filename in ['program.ts','nex-map.json']:
        text=(folder/filename).read_text()
        assert 'UNREACHABLE_ASYNC_FILE_SECRET' not in text and 'SERVER_PRIVATE_PATH' not in text and 'server_file_read' not in text
    (folder/'package.json').write_text('{"type":"module"}\n')
    if value['asynchronous']:
        runner="import * as task from './nex-task-runtime.ts';import {entry} from './program.ts';process.stdout.write(String(await task.run(task.call(()=>entry())))+'\\n');\n"
    else:runner="import {entry} from './program.ts';process.stdout.write(String(entry())+'\\n');\n"
    (folder/'run.mjs').write_text(runner)
    assert command([node,'--experimental-strip-types','--no-warnings',folder/'run.mjs'])=='42\n'
    command([node,Path(os.environ['NEX_TSC']).resolve(),'--noEmit','--strict','--target','ES2022','--module','ESNext','--moduleResolution','bundler','--allowImportingTsExtensions','--lib','ES2022,DOM',folder/'program.ts'])
    records.append({'name':name,'language':value['language'],'asynchronous':value['asynchronous'],'revision':value['revision']})
    return value,folder
try:
    secret='server fn server_file_read()->result<str> !{task,fs}{return file_read_text("SERVER_PRIVATE_PATH/UNREACHABLE_ASYNC_FILE_SECRET");}\n'
    path=out/'task.nex';path.write_text('module ts_file_boundary;fn main()->i64 !{task}{task_yield();return 42;}\n'+secret)
    current,_=emit(path,'current020');old,_=emit(path,'retained019','retained019')
    assert current['language']=='0.22' and old['language']=='0.19' and current['asynchronous'] and old['asynchronous']
    assert current['revision']!=old['revision'] and current['source_hash']==old['source_hash']
    emit(path,'server020',entry='server_file_read',error='E_REALM')
    emit(path,'server019','retained019',entry='server_file_read',error='E_REALM')
    path=out/'pure.nex';path.write_text('module ts_file_boundary;fn main()->i64{return 42;}\n'+secret)
    pure,_=emit(path,'pure020');assert not pure['asynchronous'] and pure['language']=='0.22'
    for realm in ['shared','client']:
        path=out/(realm+'.nex');path.write_text('module bad_file_realm;'+realm+' fn main()->result<str> !{task,fs}{return file_read_text("bad");}\n')
        emit(path,realm+'-fs',error='E_REALM')
    report={'ok':True,'cases':len(records),'standaloneTaskExecutionAndBrowserBoundary':True,'sourceFilesystemInTypeScript':False,'records':records,
      'sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [probe,source/'src/typescript.cpp',source/'web/nex-task-runtime.ts',Path(__file__)]}}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
except BaseException:
    print('TypeScript file boundary fixtures retained at '+str(out));raise
else:
    if not args.output:shutil.rmtree(out)
