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
    (project / 'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.21','entry':source.name}))
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
        assert hover['contents']['value']=='shared fn editor_sdk::twice(n: i64) -> i64',hover
        report['checks'].append('actual stdio lifecycle, declarations, checked hover and definition')
        reference_query={**query,'position':{'line':2,'character':22},'context':{'includeDeclaration':False}}
        references=request('textDocument/references',reference_query)
        assert references==[{'uri':source.as_uri(),'range':{'start':{'line':2,'character':22},'end':{'line':2,'character':27}}}],references
        reference_query['context']['includeDeclaration']=True
        references=request('textDocument/references',reference_query)
        assert len(references)==2 and references[0]['range']==defined[0]['range'],references
        report['checks'].append('exact semantic references with explicit declaration inclusion')
        report['reference_checks']=True

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
        defined = request('textDocument/definition',{**query,'position':{'line':0,'character':len(main[:main.index('m::answer')+3].encode('utf-16-le'))//2}})
        assert len(defined)==1 and defined[0]['uri']==helper.as_uri(),defined
        references=request('textDocument/references',{**query,'position':{'line':0,'character':len(main[:main.index('m::answer')+3].encode('utf-16-le'))//2},'context':{'includeDeclaration':True}})
        assert len(references)==2 and {row['uri'] for row in references}=={source.as_uri(),helper.as_uri()},references
        typed_library = 'module model;pub trait Content{type Item;fn get(value:Self)->Content::Item<Self>;}pub struct Box<T>{value:T;}fn extract<T>(value:Box<T>)->T{return value.value;}pub impl boxed<T>:Content for Box<T>{type Item=T;get=extract<T>;}'
        typed_main = 'module editor_types;import "./new module 🧠.nex" as m;fn main()->i64{let value:m::Box<i64>=m::Box<i64>(42);return m::Content<m::Box<i64>>::get(value);}'
        send('textDocument/didChange',{'textDocument':{'uri':helper.as_uri(),'version':2},'contentChanges':[{'text':typed_library}]})
        send('textDocument/didChange',{'textDocument':{'uri':source.as_uri(),'version':4},'contentChanges':[{'text':typed_main}]})
        assert diagnostics(4)==[] and diagnostics(2,helper)==[]
        def typed_query(text, path, at):
            return {'textDocument':{'uri':path.as_uri()},'position':{'line':0,'character':len(text[:at].encode('utf-16-le'))//2}}
        alias = request('textDocument/references',{**typed_query(typed_main,source,typed_main.index('m;')),'context':{'includeDeclaration':True}})
        assert len(alias)==5 and all(row['uri']==source.as_uri() for row in alias),alias
        parameter = request('textDocument/references',{**typed_query(typed_library,helper,typed_library.index('T>{')),'context':{'includeDeclaration':True}})
        assert len(parameter)==2,parameter
        for text,path,at,target in [(typed_main,source,typed_main.index('get(value)'),typed_library.index('get(value')),
                                    (typed_library,helper,typed_library.index('Item<Self>'),typed_library.index('Item;')),
                                    (typed_library,helper,typed_library.index('get=extract'),typed_library.index('get(value'))]:
            result=request('textDocument/definition',typed_query(text,path,at))
            assert result==[{'uri':helper.as_uri(),'range':{'start':{'line':0,'character':target},'end':{'line':0,'character':target+(4 if text[at:].startswith('Item') else 3)}}}],result
        for text,path,at,expected in [
                (typed_main,source,typed_main.index('m;'),'import m = model ("./new module 🧠.nex")'),
                (typed_library,helper,typed_library.index('T>{'),'type parameter model::Box::T'),
                (typed_library,helper,typed_library.index('Item;'),'associated type model::Content::Item<Self>'),
                (typed_main,source,typed_main.index('get(value)'),'shared fn model::Content::get(value: Self) -> model::Content::Item<Self>'),
                (typed_main,source,typed_main.index('i64>=m::Box'),'type i64')]:
            value=request('textDocument/hover',typed_query(text,path,at))
            assert value['contents']=={'kind':'plaintext','value':expected},value
        assert request('textDocument/definition',typed_query(typed_main,source,typed_main.index('i64>=m::Box')))==[]
        report['identifier_checks']=True
        report['checks'].append('exact alias, generic, associated-member, method and builtin-type descriptions; no invented builtin definition')
        report['type_reference_checks']=True
        report['checks'].append('checked type parameters, import aliases, trait member contracts and implementation bindings')
        resource_library='module model;pub server resource resource<T>;'
        resource_main='module editor_resources;import "./new module 🧠.nex" as m;server fn alive(value:m::resource<i64>)->bool!{ffi}{return resource_is_open(value);}fn main()->i64{return 42;}'
        send('textDocument/didChange',{'textDocument':{'uri':helper.as_uri(),'version':3},'contentChanges':[{'text':resource_library}]})
        send('textDocument/didChange',{'textDocument':{'uri':source.as_uri(),'version':5},'contentChanges':[{'text':resource_main}]})
        assert diagnostics(5)==[] and diagnostics(3,helper)==[]
        symbols=request('textDocument/documentSymbol',{'textDocument':{'uri':helper.as_uri()}})
        at=resource_library.index('resource<T>')
        assert len(symbols)==1 and symbols[0]['kind']==5 and symbols[0]['selectionRange']=={'start':{'line':0,'character':at},'end':{'line':0,'character':at+8}},symbols
        use=typed_query(resource_main,source,resource_main.index('resource<i64>'))
        hover=request('textDocument/hover',use)
        assert hover['contents']=={'kind':'plaintext','value':'pub server resource model::resource<T>'},hover
        definitions=request('textDocument/definition',use)
        assert definitions==[{'uri':helper.as_uri(),'range':symbols[0]['selectionRange']}],definitions
        references=request('textDocument/references',{**use,'context':{'includeDeclaration':True}})
        assert len(references)==2 and {r['uri'] for r in references}=={source.as_uri(),helper.as_uri()},references
        report['checks'].append('opaque generic resource symbols, exact contextual name token, cross-file hover/definition/references')
        report['resource_checks']=True
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
