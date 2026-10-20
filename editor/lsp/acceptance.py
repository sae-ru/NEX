"""Standalone installed-SDK language-server acceptance; no checkout imports."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import queue
import signal
import subprocess
import threading


def accept(compiler, output):
    output.mkdir()
    project = output / 'project with spaces 🧠'
    project.mkdir()
    source = project / 'main.nex'
    original = 'module editor_sdk;\nfn twice(n:i64)->i64{return n*2;}\nfn main()->i64{return twice(21);}\n'
    source.write_text(original, encoding='utf-8')
    (project / 'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.16','entry':source.name}))
    report = {'schema':'nex.lsp-acceptance/1','ok':False,'compiler_sha256':hashlib.sha256(compiler.read_bytes()).hexdigest(),
              'messages_sent':0,'checks':[],'source_and_graph_unchanged':False}
    process = subprocess.Popen([str(compiler),'lsp'],cwd=project,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
    incoming = queue.Queue()
    saved = []
    ident = 0
    def read():
        try:
            while True:
                header = {}
                while True:
                    row = process.stdout.readline()
                    if not row:
                        incoming.put(RuntimeError('LSP closed before its response'))
                        return
                    if row == b'\r\n':break
                    key,value = row.decode('ascii').split(':',1)
                    header[key.lower()] = value.strip()
                incoming.put(json.loads(process.stdout.read(int(header['content-length']))))
        except Exception as error:incoming.put(error)
    reader = threading.Thread(target=read,daemon=True)
    reader.start()
    def send(method, params=None, request=False):
        nonlocal ident
        message = {'jsonrpc':'2.0','method':method}
        if params is not None:message['params'] = params
        if request:
            ident += 1
            message['id'] = ident
        raw = json.dumps(message,ensure_ascii=False).encode('utf-8')
        process.stdin.write(('Content-Length: '+str(len(raw))+'\r\n\r\n').encode()+raw)
        process.stdin.flush()
        report['messages_sent'] += 1
        return message.get('id')
    def take(predicate):
        for i,message in enumerate(saved):
            if predicate(message):return saved.pop(i)
        for _ in range(256):
            message = incoming.get(timeout=40)
            if isinstance(message,Exception):raise message
            if predicate(message):return message
            saved.append(message)
        raise RuntimeError('LSP response limit exceeded')
    def request(method,params=None):
        number = send(method,params,True)
        response = take(lambda m:m.get('id')==number and 'method' not in m)
        assert 'error' not in response,response
        return response['result']
    def diagnostics(version,path=source):
        return take(lambda m:m.get('method')=='textDocument/publishDiagnostics' and m['params']['uri']==path.as_uri()
                    and m['params'].get('version')==version)['params']['diagnostics']
    try:
        capabilities = request('initialize',{'processId':os.getpid(),'capabilities':{}})['capabilities']
        assert capabilities['positionEncoding']=='utf-16' and capabilities['textDocumentSync']['change']==1
        send('initialized',{})
        send('textDocument/didOpen',{'textDocument':{'uri':source.as_uri(),'languageId':'nex','version':1,'text':original}})
        assert diagnostics(1)==[]
        query = {'textDocument':{'uri':source.as_uri()}}
        symbols = request('textDocument/documentSymbol',query)
        assert [s['name'] for s in symbols]==['twice','main'],symbols
        defined = request('textDocument/definition',{**query,'position':{'line':2,'character':22}})
        assert defined==[{'uri':source.as_uri(),'range':{'start':{'line':1,'character':3},'end':{'line':1,'character':8}}}],defined
        hover = request('textDocument/hover',{**query,'position':{'line':2,'character':22}})
        assert hover['contents']['value']=='i64',hover
        report['checks'].append('actual stdio lifecycle, declarations, checked hover and definition')
        invalid = 'module editor_sdk;\r\nfn main()->i64{let text:str="Я🧠";return absent;}\r\n'
        send('textDocument/didChange',{'textDocument':{'uri':source.as_uri(),'version':2},'contentChanges':[{'text':invalid}]})
        errors = diagnostics(2)
        assert len(errors)==1 and errors[0]['code']=='E_NAME',errors
        expected = invalid.split('\r\n')[1].index('absent')+1
        assert errors[0]['range']['start']=={'line':1,'character':expected},errors
        report['checks'].append('unsaved UTF-8/UTF-16 and CRLF diagnostic coordinates')
        helper = project / 'new module 🧠.nex'
        main = 'module editor_sdk;import "./new module 🧠.nex" as m;fn main()->i64{return m::answer();}'
        send('textDocument/didOpen',{'textDocument':{'uri':helper.as_uri(),'languageId':'nex','version':1,
            'text':'module model;pub fn answer()->i64{return 42;}'}})
        send('textDocument/didChange',{'textDocument':{'uri':source.as_uri(),'version':3},'contentChanges':[{'text':main}]})
        assert diagnostics(3)==[]
        assert diagnostics(1,helper)==[]
        defined = request('textDocument/definition',{**query,'position':{'line':0,'character':main.index('m::answer')+3}})
        assert len(defined)==1 and defined[0]['uri']==helper.as_uri(),defined
        send('textDocument/didClose',{'textDocument':{'uri':helper.as_uri()}})
        report['checks'].append('new unsaved imported module, overlay repair and cross-file definition')
        request('shutdown')
        send('exit')
        assert process.wait(timeout=10)==0
        assert source.read_text(encoding='utf-8')==original and not helper.exists() and not (project/'.nex').exists()
        report.update(ok=True,source_and_graph_unchanged=True,exit_code=process.returncode)
    finally:
        if process.poll() is None:
            os.killpg(process.pid,signal.SIGKILL)
            process.wait(timeout=10)
        report['stderr'] = process.stderr.read().decode('utf-8',errors='replace')
        for stream in [process.stdin,process.stdout,process.stderr]:stream.close()
        (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return report


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('compiler',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    result = accept(args.compiler.resolve(),args.output.resolve())
    print(json.dumps(result,ensure_ascii=False))
