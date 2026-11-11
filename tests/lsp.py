"""Actual compiler/stdio LSP, unsaved projects and persistent-history isolation."""
from host_fixture import python_executable
from sqlite_fixture import connection as sqlite_connection
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import queue
import signal
import sqlite3
import subprocess
import sys
import threading
import time
import unittest
import support as harness


class Client:
    def __init__(self, cwd, command=None):
        self.process = subprocess.Popen(command or [harness.NEX, 'lsp'], cwd=cwd,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        self.queue = queue.Queue()
        self.saved = []
        self.ident = 0
        def read():
            try:
                while True:
                    headers = {}
                    while True:
                        line = self.process.stdout.readline()
                        if not line:
                            return
                        if line == b'\r\n':
                            break
                        key, value = line.decode('ascii').split(':', 1)
                        headers[key.lower()] = value.strip()
                    body = self.process.stdout.read(int(headers['content-length']))
                    self.queue.put(json.loads(body))
            except Exception as error:
                self.queue.put(error)
        self.reader = threading.Thread(target=read, daemon=True)
        self.reader.start()

    def send(self, method, params=None, request=False, fragments=False):
        value = {'jsonrpc': '2.0', 'method': method}
        if params is not None:
            value['params'] = params
        if request:
            self.ident += 1
            value['id'] = self.ident
        raw = json.dumps(value, ensure_ascii=False).encode()
        frame = ('Content-Length: ' + str(len(raw)) + '\r\n\r\n').encode() + raw
        chunks = [frame[i:i+3] for i in range(0,len(frame),3)] if fragments else [frame]
        for chunk in chunks:
            self.process.stdin.write(chunk)
            self.process.stdin.flush()
        return value.get('id')

    def take(self, predicate, timeout=15):
        end = time.monotonic() + timeout
        for index, message in enumerate(self.saved):
            if predicate(message):
                return self.saved.pop(index)
        while time.monotonic() < end:
            message = self.queue.get(timeout=max(0.01,end-time.monotonic()))
            if isinstance(message, Exception):
                raise message
            if predicate(message):
                return message
            self.saved.append(message)
        raise AssertionError('No matching LSP response')

    def response(self, ident):
        return self.take(lambda value:value.get('id') == ident and 'method' not in value)

    def request(self, method, params=None):
        response = self.response(self.send(method, params, request=True))
        if 'error' in response:
            raise AssertionError(response)
        return response['result']

    def initialize(self):
        ident = self.send('initialize', {'processId': os.getpid(), 'capabilities': {}}, request=True, fragments=True)
        result = self.response(ident)['result']
        self.send('initialized', {})
        return result

    def open(self, path, text, version=1):
        self.send('textDocument/didOpen', {'textDocument': {'uri':path.as_uri(),'languageId':'nex','version':version,'text':text}})

    def change(self, path, text, version):
        self.send('textDocument/didChange', {'textDocument':{'uri':path.as_uri(),'version':version},'contentChanges':[{'text':text}]})

    def diagnostics(self, path, version=None):
        return self.take(lambda value:value.get('method') == 'textDocument/publishDiagnostics' and
            value['params']['uri'] == path.as_uri() and (version is None or value['params'].get('version') == version))['params']['diagnostics']

    def close(self, clean=True):
        try:
            if self.process.poll() is None and clean:
                self.request('shutdown')
                self.send('exit')
                self.process.wait(timeout=10)
                if self.process.returncode != 0:
                    raise AssertionError(self.process.stderr.read().decode())
        finally:
            if self.process.poll() is None:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=10)
            for stream in [self.process.stdin,self.process.stdout,self.process.stderr]:
                stream.close()


class LanguageServer(harness.ToolchainCase):
    def setUp(self):
        super().setUp()
        (self.root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':harness.CURRENT_LANGUAGE,'entry':'main.nex'}), newline="\n")
        self.source('module app; fn twice(n:i64)->i64{return n*2;} fn main()->i64{return twice(21);}')
        self.clients=[]

    def tearDown(self):
        for client in self.clients:
            client.close()
        super().tearDown()

    def client(self, command=None):
        client=Client(self.root,command)
        self.clients.append(client)
        return client

    def overlay(self, files):
        path=self.root/'overlay.json'
        path.write_text(json.dumps({'schema':'nex.overlay/1','files':{str(k.resolve()):v for k,v in files.items()}}), newline="\n")
        return path

    def rows(self):
        path=self.root/'.nex/graph.db'
        if not path.exists():
            return None
        with sqlite_connection(path) as connection:
            names=[row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
            return {name:sorted(connection.execute('SELECT * FROM "'+name+'"').fetchall(),key=repr) for name in names}

    def test_analysis_unsaved_import_and_existing_history_are_preserved(self):
        self.cli('check',self.file)
        before=self.rows()
        physical=self.file.read_bytes()
        helper=self.root/'new file 🧠.nex'
        main='module app; import "./new file 🧠.nex" as m; fn main()->i64{return m::answer();}'
        analysis=self.cli('analyze',self.file,'--overlay',self.overlay({self.file:main,helper:'module model; pub fn answer()->i64{return 42;}'}))
        self.assertTrue(analysis['ok'])
        self.assertEqual(analysis['schema'],'nex.analysis/1')
        self.assertFalse(analysis['graph_written'])
        self.assertFalse(analysis['executed'])
        self.assertEqual(self.rows(),before)
        self.assertEqual(self.file.read_bytes(),physical)
        self.assertFalse(helper.exists())
        self.assertEqual({s['name'] for s in analysis['symbols']},{'main','answer'})
        target=next(e['definition'] for e in analysis['expressions'] if e['definition'])
        self.assertEqual(target['file'],helper.name)

    def test_analysis_uses_same_realm_effect_version_and_lock_checker(self):
        invalid='module app; fn main()->unit {print(42);}'
        result=self.cli('analyze',self.file,'--overlay',self.overlay({self.file:invalid}),ok=False)
        self.assertEqual(result['code'],'E_EFFECT')
        self.assertEqual(result['frontend']['source']['sha256'],hashlib.sha256(invalid.encode()).hexdigest())
        self.assertFalse((self.root/'.nex').exists())
        manifest=self.root/'nex.json'
        value=json.loads(manifest.read_text());value['language']='0.15';manifest.write_text(json.dumps(value), newline="\n")
        self.assertEqual(self.cli('analyze',self.file,ok=False)['code'],'E_LANGUAGE_VERSION')
        self.assertFalse((self.root/'.nex').exists())
        value['language']=harness.CURRENT_LANGUAGE
        value['libraries']={'dep':'library'}
        manifest.write_text(json.dumps(value), newline="\n")
        library=self.root/'library';library.mkdir()
        (library/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':harness.CURRENT_LANGUAGE,'entry':'model.nex'}), newline="\n")
        dependency=library/'model.nex';dependency.write_text('module dep;pub fn answer()->i64{return 1;}', newline="\n")
        self.source('module app;import "dep/model.nex" as d;fn main()->i64{return d::answer();}')
        self.cli('lock',self.file)
        before=self.rows()
        result=self.cli('analyze',self.file,'--overlay',self.overlay({dependency:'module dep;pub fn answer()->i64{return 2;}'}),ok=False)
        self.assertEqual(result['code'],'E_LOCK')
        self.assertEqual(self.rows(),before)

    def test_analysis_rejects_overlay_directory_escape_and_unbounded_inputs(self):
        outside=self.root/'outside';outside.mkdir();(self.root/'link').symlink_to(outside,target_is_directory=True)
        path=self.root/'overlay.json'
        for files in [{'main.nex':'module app;'}, {str(self.root/'link/main.nex'):'module app;'},
                      {str(self.file):'x'*(1048576+1)}]:
            path.write_text(json.dumps({'schema':'nex.overlay/1','files':files}), newline="\n")
            self.assertEqual(self.cli('analyze',self.file,'--overlay',path,ok=False)['code'],'E_OVERLAY')
        self.assertFalse((self.root/'.nex').exists())

    def test_analysis_generic_traits_closures_patterns_and_std_sources(self):
        for relative in ['examples/traits/main.nex','examples/generics/main.nex','examples/enums/main.nex','examples/functions/main.nex']:
            source=harness.REPO/relative
            self.assertTrue(source.is_file(),relative)
            # Analyze actual checked project sources; no graph synchronization.
            result=self.cli('analyze',source)
            self.assertTrue(result['ok'])
            self.assertTrue(result['symbols'])
        self.assertFalse((self.root/'.nex').exists())

    def test_exact_references_preserve_v1_and_distinguish_writes_and_function_values(self):
        text=('module refs;\nfn twice(n:i64)->i64{return n+n;}\n'
              'fn main()->i64{var n:i64=20;n=n+1;let f:fn(i64)->i64=twice;return f(n)+twice(n);}')
        self.source(text)
        legacy=self.cli('analyze',self.file)
        indexed=self.cli('analyze',self.file,'--references')
        self.assertEqual(indexed['schema'],'nex.analysis/2')
        without={k:v for k,v in indexed.items() if k!='occurrences'};without['schema']='nex.analysis/1'
        self.assertEqual(legacy,without)
        rows=indexed['occurrences'];raw=text.encode()
        def refs(name,at):
            declaration=text.index(name,at)
            return [row for row in rows if row['definition']['range']=={'begin':declaration,'end':declaration+len(name)}]
        parameter=refs('n',text.index('n:i64'))
        local=refs('n',text.index('n:i64',text.index('fn main')))
        callable=refs('f',text.index('let f'))
        function=refs('twice',text.index('fn twice'))
        self.assertEqual(sorted(row['role'] for row in parameter),['declaration','read','read'])
        self.assertEqual(sorted(row['role'] for row in local),['declaration','read','read','read','write'])
        self.assertEqual(sorted(row['role'] for row in callable),['call','declaration'])
        self.assertEqual(sorted(row['role'] for row in function),['call','declaration','read'])
        for row in rows:
            value=raw[row['range']['begin']:row['range']['end']].decode()
            self.assertRegex(value,r'^[A-Za-z_][A-Za-z_0-9]*$')
        client=self.client();client.initialize();client.open(self.file,text)
        at=text.index('n:i64',text.index('fn main'))
        prefix=text[:at];query={'textDocument':{'uri':self.file.as_uri()},'position':{'line':prefix.count('\n'),'character':len(prefix.rsplit('\n',1)[-1])},'context':{'includeDeclaration':False}}
        usages=client.request('textDocument/references',query);self.assertEqual(len(usages),4)
        for usage in usages:
            self.assertEqual(usage['range']['end']['character']-usage['range']['start']['character'],1)
        self.assertFalse((self.root/'.nex').exists())

    def test_reference_closure_capture_and_pattern_binders_have_physical_identity(self):
        text=('module refs;enum Maybe{Some(value:i64);None;}\n'
              'fn apply(x:i64)->i64{let value:i64=3;let call:fn(i64)->i64='
              'fn(value:i64)->i64{return value+x;};return call(value); }\n'
              'fn choose(m:Maybe)->i64{return match m {Maybe::Some(value)=>value,Maybe::None()=>0};}\n'
              'fn main()->i64{return apply(1)+choose(Maybe::Some(2));}')
        self.source(text);data=self.cli('analyze',self.file,'--references');rows=data['occurrences']
        x=text.index('x:i64');self.assertEqual(len([o for o in rows if o['definition']['range']=={'begin':x,'end':x+1}]),2)
        for start in [text.index('let value')+4,text.index('fn(value')+3,text.index('Some(value)=>')+5]:
            selected=[o for o in rows if o['definition']['range']=={'begin':start,'end':start+5}]
            self.assertEqual(sorted(o['role'] for o in selected),['declaration','read'])
        for relative in ['examples/traits/main.nex','examples/generics/main.nex','examples/enums/main.nex','examples/functions/main.nex']:
            index=self.cli('analyze',harness.REPO/relative,'--references')
            self.assertEqual(index['schema'],'nex.analysis/2')
            self.assertTrue(index['occurrences'])
        self.assertFalse((self.root/'.nex').exists())

    def test_fields_patterns_and_wildcards_do_not_merge_unrelated_bindings(self):
        text=('module refs;struct Left{value:i64;}struct Right{value:i64;}\n'
              'fn main()->i64{let a:Left=Left(20);let b:Right=Right(2);let _:i64=22;'
              'return match a {Left(value)=>value+b.value+a.value+(match 1 {_=>_})};}\n'
              'test fn correct()->unit{assert(main()==64);}')
        self.source(text);data=self.cli('analyze',self.file,'--references');rows=data['occurrences']
        left=text.index('value:i64');right=text.index('value:i64',left+1)
        for offset in [left,right]:
            selected=[row for row in rows if row['definition']['range']=={'begin':offset,'end':offset+5}]
            self.assertEqual(sorted(row['role'] for row in selected),['declaration','read'])
        owner=text.index('Left{')
        selected=[row for row in rows if row['definition']['range']=={'begin':owner,'end':owner+4}]
        self.assertEqual(sorted(row['role'] for row in selected),['call','declaration','pattern','read'])
        underscore=text.index('_:i64');wildcard=text.index('_=>')
        selected=[row for row in rows if row['definition']['range']=={'begin':underscore,'end':underscore+1}]
        self.assertEqual(sorted(row['role'] for row in selected),['declaration','read'])
        self.assertFalse(any(row['range']=={'begin':wildcard,'end':wildcard+1} for row in rows))
        legacy=self.cli('analyze',self.file)
        use=text.rindex('_}')
        expression=next(row for row in legacy['expressions'] if row['range']=={'begin':use,'end':use+1})
        self.assertEqual(expression['definition']['range'],{'begin':underscore,'end':underscore+1})
        self.assertFalse((self.root/'.nex').exists())
        self.cli('test',self.file)
        self.cli('test',self.file,'--target','web')

    def test_cross_module_references_aliases_open_entries_and_unicode_crlf(self):
        helper=self.root/'model 🧠.nex';library='module model;\npub fn answer(n:i64)->i64{return n;}\n';helper.write_text(library, newline="\n")
        main=('module app;\r\nimport "./model 🧠.nex" as a;\r\nimport "./model 🧠.nex" as b;\r\n'
              'fn main()->i64{let s:str="Я🧠";return a::answer(1)+b::answer(2);}')
        self.source(main);physical=self.file.read_bytes();client=self.client();self.assertTrue(client.initialize()['capabilities']['referencesProvider'])
        client.open(self.file,main);client.open(helper,library);self.assertEqual(client.diagnostics(self.file,1),[])
        query={'textDocument':{'uri':helper.resolve().as_uri()},'position':{'line':1,'character':8},'context':{'includeDeclaration':False}}
        refs=client.request('textDocument/references',query)
        starts=[main.split('\r\n')[3].index('answer'),main.split('\r\n')[3].rindex('answer')]
        self.assertEqual(refs,[{'uri':self.file.resolve().as_uri(),'range':{'start':{'line':3,'character':start+1},'end':{'line':3,'character':start+7}}} for start in starts])
        query['context']['includeDeclaration']=True
        with_declaration=client.request('textDocument/references',query);self.assertEqual(len(with_declaration),3)
        orphan=self.root/'orphan.nex';orphan_text='module orphan;import "./model 🧠.nex" as m;fn read()->i64{return m::answer(3);}'
        orphan.write_text(orphan_text, newline="\n");client.open(orphan,orphan_text)
        expanded=client.request('textDocument/references',query);self.assertEqual(len(expanded),4)
        self.assertEqual(len([row for row in expanded if row['uri']==helper.resolve().as_uri()]),1)
        client.send('textDocument/didClose',{'textDocument':{'uri':orphan.as_uri()}})
        self.assertEqual(len(client.request('textDocument/references',query)),3)
        for context in [None,{}, {'includeDeclaration':1},{'includeDeclaration':'yes'}]:
            response=client.response(client.send('textDocument/references',{**query,'context':context},request=True))
            self.assertEqual(response['error']['code'],-32602)
        self.assertEqual(self.file.read_bytes(),physical);self.assertEqual(helper.read_text(),library);self.assertFalse((self.root/'.nex').exists())

    def test_reference_caps_conflicting_captures_and_cancel_are_explicit(self):
        spec=importlib.util.spec_from_file_location('nex_lsp_refs',harness.REPO/'editor/lsp/server.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        server=module.Server(harness.NEX,output=io.BytesIO());text='n '*10002
        file={'key':'main.nex','path':str(self.file),'text':text,'hash':'a'*64}
        declaration={'file':'main.nex','range':{'begin':0,'end':1}}
        occurrences=[{'file':'main.nex','range':{'begin':i*2,'end':i*2+1},'definition':declaration,'role':'declaration' if i==0 else 'read'} for i in range(10002)]
        cache={'epoch':0,'indices':[{'files':[file],'occurrences':occurrences}],'documents':{}}
        params={'textDocument':{'uri':self.file.as_uri()},'position':{'line':0,'character':0},'context':{'includeDeclaration':False}}
        try:
            with self.assertRaises(module.RPCError) as failure:server.query('textDocument/references',params,cache)
            self.assertEqual(failure.exception.code,-32803)
            cache['indices'][0]['occurrences']=occurrences[:3]
            cache['indices'].append({'files':[{**file,'hash':'b'*64,'text':'n '}],'occurrences':[]})
            with self.assertRaises(module.RPCError) as failure:server.query('textDocument/references',params,cache)
            self.assertEqual(failure.exception.code,-32801)
            with self.assertRaises(module.RPCError) as failure:server.query('textDocument/definition',params,cache)
            self.assertEqual(failure.exception.code,-32801)
            cache['indices'].pop()
            changed={'file':'main.nex','range':{'begin':0,'end':1},'definition':{'file':'main.nex','range':{'begin':2,'end':3}},'role':'read'}
            cache['indices'].append({'files':[file],'occurrences':[changed]})
            with self.assertRaises(module.RPCError) as failure:server.query('textDocument/references',params,cache)
            self.assertEqual(failure.exception.code,-32801)
            with self.assertRaises(module.RPCError) as failure:server.query('textDocument/definition',params,cache)
            self.assertEqual(failure.exception.code,-32801)
            cache['indices'].pop()
            long_path=self.root/('я'*120)/('я'*120)/'module.nex'
            other={**file,'key':'other.nex','path':str(long_path),'text':'n '*10000}
            huge=[{'file':'other.nex','range':{'begin':i*2,'end':i*2+1},'definition':declaration,'role':'read'} for i in range(10000)]
            cache['indices'][0]={'files':[file,other],'occurrences':[occurrences[0],*huge]}
            with self.assertRaises(module.RPCError) as failure:server.query('textDocument/references',params,cache)
            self.assertEqual(failure.exception.code,-32803);self.assertIn('8 MiB',str(failure.exception))
            cache['indices'][0]={'files':[file],'occurrences':occurrences[:3]}
            cancel=threading.Event();cancel.set()
            with self.assertRaises(module.RPCError) as failure:server.query('textDocument/references',params,cache,cancel)
            self.assertEqual(failure.exception.code,-32800)
            with self.assertRaises(module.RPCError) as failure:server.query('textDocument/definition',params,cache,cancel)
            self.assertEqual(failure.exception.code,-32800)
            unicode='Я🧠\r\nn n';offsets=[len(unicode[:i].encode()) for i in [0,1,2,3,4,5,6,7]]
            positions=module.range_positions(unicode,offsets,lambda:None)
            self.assertEqual(positions,{offset:module.position(unicode,offset) for offset in offsets})
        finally:server.close()

    def selected_references(self, index, text, declaration, name, file='main.nex'):
        at=len(text[:declaration].encode())
        target={'file':file,'range':{'begin':at,'end':at+len(name.encode())}}
        return [row for row in index['occurrences'] if row['definition']==target]

    def test_type_parameters_have_lexical_scopes_and_nominal_types_have_annotations(self):
        text=('module types;struct Box<T>{value:T;}\n'
              'fn id<T>(value:T)->T{return value;}\n'
              'fn unused<T>(value:T)->T{return value;}\n'
              'fn main()->i64{let value:Box<i64>=Box<i64>(21);return id<Box<i64>>(value).value*2;}\n'
              'test fn correct()->unit{assert(main()==42);}')
        self.source(text);index=self.cli('analyze',self.file,'--references')
        legacy=self.cli('analyze',self.file);projected={k:v for k,v in index.items() if k!='occurrences'};projected['schema']='nex.analysis/1'
        self.assertEqual(legacy,projected)
        for start,count in [(text.index('T>'),2),(text.index('T>',text.index('fn id')),3),(text.index('T>',text.index('fn unused')),3)]:
            rows=self.selected_references(index,text,start,'T');self.assertEqual(len(rows),count)
            self.assertEqual(sum(row['role']=='declaration' for row in rows),1)
        rows=self.selected_references(index,text,text.index('Box<T>'),'Box')
        self.assertEqual(sorted(row['role'] for row in rows),['call','declaration','read','read'])
        self.assertFalse((self.root/'.nex').exists())
        self.cli('test',self.file);self.cli('test',self.file,'--target','web')

    def test_trait_members_implementation_bindings_and_actual_functions_are_distinct(self):
        text=('module contract;\ntrait Content{type Item;fn get(value:Self)->Content::Item<Self>;}\n'
              'struct Box<T>{value:T;}\nfn extract<T>(value:Box<T>)->T{return value.value;}\n'
              'impl boxed<T>:Content for Box<T>{type Item=T;get=extract<T>;}\n'
              'fn read<T:Content>(value:T)->Content::Item<T>{return Content<T>::get(value);}\n'
              'fn main()->i64{return read(Box<i64>(42));}\n'
              'test fn correct()->unit{assert(main()==42);let get:fn(Box<i64>)->i64=Content<Box<i64>>::get;assert(get(Box<i64>(7))==7);}')
        self.source(text);index=self.cli('analyze',self.file,'--references')
        method=text.index('get(');rows=self.selected_references(index,text,method,'get')
        self.assertEqual(sorted(row['role'] for row in rows),['call','declaration','read','read'])
        associated=text.index('Item;');rows=self.selected_references(index,text,associated,'Item')
        self.assertEqual(sorted(row['role'] for row in rows),['declaration','read','read','read'])
        function=text.index('extract<T>');rows=self.selected_references(index,text,function,'extract')
        self.assertEqual(sorted(row['role'] for row in rows),['declaration','read'])
        trait=text.index('Content{');rows=self.selected_references(index,text,trait,'Content')
        self.assertTrue(all(text.encode()[row['range']['begin']:row['range']['end']].decode() in ('Content','Self') for row in rows))
        implicit=[row for row in rows if text.encode()[row['range']['begin']:row['range']['end']]==b'Self']
        self.assertEqual(len(implicit),2);self.assertFalse(any(row['role']=='declaration' for row in implicit))
        self.assertFalse((self.root/'.nex').exists())
        self.cli('test',self.file);self.cli('test',self.file,'--target','web')

    def test_import_alias_type_and_variant_components_have_separate_definitions(self):
        library=('module model;pub enum Maybe<T>{Some(value:T);None;}\n'
                 'pub fn echo<T>(value:T)->T{return value;}')
        helper=self.root/'model 🧠.nex';helper.write_text(library, newline="\n")
        text=('module types;\r\nimport "./model 🧠.nex" as m;\r\n'
              'fn read(x:m::Maybe<i64>)->i64{return match x{m::Maybe::Some(n)=>n,m::Maybe::None()=>0};}\r\n'
              'fn main()->i64{let s:str="Я🧠";return read(m::Maybe<i64>::Some(m::echo<i64>(42)));}')
        self.source(text);index=self.cli('analyze',self.file,'--references')
        alias=text.index('m;');rows=self.selected_references(index,text,alias,'m')
        self.assertEqual(len(rows),6);self.assertEqual(sum(row['role']=='declaration' for row in rows),1)
        variant=library.index('Some(');rows=self.selected_references(index,library,variant,'Some',helper.name)
        self.assertEqual(sorted(row['role'] for row in rows),['call','declaration','pattern'])
        enum=library.index('Maybe<T>');rows=self.selected_references(index,library,enum,'Maybe',helper.name)
        self.assertEqual(sorted(row['role'] for row in rows),['declaration','read','read','read','read'])
        client=self.client();client.initialize();client.open(self.file,text);self.assertEqual(client.diagnostics(self.file,1),[])
        def query(at):
            prefix=text[:at];return {'textDocument':{'uri':self.file.as_uri()},'position':{'line':prefix.count('\n'),'character':len(prefix.rsplit('\n',1)[-1].encode('utf-16-le'))//2}}
        targets=[(text.index('m::Maybe'),self.file.resolve().as_uri(),text,alias,'m'),
                 (text.index('Maybe<i64>'),helper.resolve().as_uri(),library,enum,'Maybe'),
                 (text.rindex('Some('),helper.resolve().as_uri(),library,variant,'Some')]
        for at,uri,source,begin,name in targets:
            prefix=source[:begin];start={'line':prefix.count('\n'),'character':len(prefix.rsplit('\n',1)[-1].encode('utf-16-le'))//2}
            self.assertEqual(client.request('textDocument/definition',query(at)),[{'uri':uri,'range':{'start':start,'end':{**start,'character':start['character']+len(name)}}}])
        self.assertEqual(len(client.request('textDocument/references',{**query(text.index('m::Maybe')),'context':{'includeDeclaration':True}})),6)
        self.assertEqual(client.request('textDocument/hover',query(text.index('Maybe<i64>')))['contents']['value'],'pub enum model::Maybe<T>')
        self.assertFalse((self.root/'.nex').exists());self.assertEqual(self.file.read_bytes(),text.encode())
        # Visibility and import errors are still compiler errors, with no partial index.
        helper.write_text(library.replace('pub enum','enum'), newline="\n")
        error=self.cli('analyze',self.file,'--references',ok=False);self.assertIn('E_VISIBILITY',json.dumps(error))
        self.assertFalse((self.root/'.nex').exists())

    def test_module_prefix_cannot_invent_a_trait_qualifier_reference(self):
        library='module catalog::Nested;pub fn answer()->i64{return 42;}'
        (self.root/'nested.nex').write_text(library, newline="\n")
        text=('module catalog;import "./nested.nex" as n;'
              'trait Nested{fn value(x:Self)->Self;}'
              'fn main()->i64{return n::answer();}')
        self.source(text);index=self.cli('analyze',self.file,'--references')
        alias=text.index('n;');rows=self.selected_references(index,text,alias,'n')
        self.assertEqual(sorted(row['role'] for row in rows),['declaration','read'])
        use=text.index('n::answer');at={'begin':use,'end':use+1}
        selected=[row for row in index['occurrences'] if row['file']=='main.nex' and row['range']==at]
        self.assertEqual(len(selected),1)
        trait=text.index('Nested{');rows=self.selected_references(index,text,trait,'Nested')
        self.assertEqual(len(rows),3) # Declaration and the two implicit Self uses.
        self.assertFalse((self.root/'.nex').exists())

    def test_constructor_parameter_and_explicit_self_references_use_real_tokens(self):
        text=('module kinds;trait Mapper<Self<_>>{fn map<A,B>(values:Self<A>,apply:fn(A)->B)->Self<B>;}\n'
              'fn map_list<A,B>(values:list<A>,apply:fn(A)->B)->list<B>{let out:list<B>=[];return out;}\n'
              'impl list_mapper:Mapper for list{map=map_list;}\n'
              'fn convert<F<_>:Mapper,A,B>(values:F<A>,apply:fn(A)->B)->F<B>{return Mapper<F>::map<A,B>(values,apply); }\n'
              'fn main()->i64{return 42;}')
        self.source(text);index=self.cli('analyze',self.file,'--references')
        self_rows=self.selected_references(index,text,text.index('Self<_>'),'Self')
        self.assertEqual(sorted(row['role'] for row in self_rows),['declaration','read','read'])
        constructor=self.selected_references(index,text,text.index('F<_>'),'F')
        self.assertEqual(sorted(row['role'] for row in constructor),['declaration','read','read','read'])
        a=text.index('A,B>(values:Self');rows=self.selected_references(index,text,a,'A')
        self.assertEqual(sorted(row['role'] for row in rows),['declaration','read','read'])
        self.assertFalse(any(text.encode()[row['range']['begin']:row['range']['end']]==b'_' for row in index['occurrences']))
        self.assertFalse((self.root/'.nex').exists())

    def test_reference_grouping_matches_complete_utf16_results_across_many_files(self):
        spec=importlib.util.spec_from_file_location('nex_lsp_type_scale',harness.REPO/'editor/lsp/server.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        server=module.Server(harness.NEX,output=io.BytesIO());files=[];occurrences=[];target={'file':'0000.nex','range':{'begin':0,'end':1}}
        for number in range(512):
            key=f'{number:04d}.nex';text='T \r\n"🧠" T';begin=len(text[:text.rindex('T')].encode())
            files.append({'key':key,'path':str(self.root/key),'text':text,'hash':str(number)})
            occurrences.append({'file':key,'range':{'begin':begin,'end':begin+1},'definition':target,'role':'read'})
        occurrences.append({'file':'0000.nex','range':target['range'],'definition':target,'role':'declaration'})
        index={'files':files,'occurrences':occurrences};cache={'epoch':0,'indices':[index,index],'documents':{}}
        params={'textDocument':{'uri':(self.root/'0000.nex').as_uri()},'position':{'line':0,'character':0},'context':{'includeDeclaration':False}}
        try:
            result=server.query('textDocument/references',params,cache)
            self.assertEqual(len(result),512)
            self.assertTrue(all(row['range']=={'start':{'line':1,'character':5},'end':{'line':1,'character':6}} for row in result))
            cancel=threading.Event();calls=0;original=module.range_positions
            def interrupt(text,offsets,check):
                nonlocal calls
                calls+=1
                if calls==3:cancel.set()
                return original(text,offsets,check)
            module.range_positions=interrupt
            with self.assertRaises(module.RPCError) as failure:server.query('textDocument/references',params,cache,cancel)
            self.assertEqual(failure.exception.code,-32800)
        finally:server.close()

    def test_details_preserve_both_legacy_projections_and_classify_exact_words(self):
        text=('module hover;fn id<T:wire>(value:T)->T{return value;} '
              'fn main()->i64{return id<i64>(42);}')
        self.source(text);legacy=self.cli('analyze',self.file);refs=self.cli('analyze',self.file,'--references');details=self.cli('analyze',self.file,'--details')
        self.assertEqual(details['schema'],'nex.analysis/3')
        normalize=lambda value:{k:v for k,v in value.items() if k not in ('schema','occurrences','identifiers')}
        self.assertEqual(normalize(legacy),normalize(refs));self.assertEqual(normalize(refs),normalize(details))
        self.assertEqual(refs['occurrences'],details['occurrences'])
        names={row['range']['begin']:row for row in details['identifiers']}
        self.assertEqual(names[text.index('T:wire')]['kind'],'type_parameter')
        self.assertEqual(names[text.index('T:wire')]['detail'],'type parameter hover::id::T: wire')
        self.assertEqual(names[text.index('wire>')]['detail'],'constraint wire');self.assertIsNone(names[text.index('wire>')]['definition'])
        primitive=names[text.index('i64>(42)')];self.assertEqual(primitive['kind'],'builtin_type');self.assertEqual(primitive['detail'],'type i64');self.assertIsNone(primitive['definition'])
        self.assertEqual(names[text.index('module')]['kind'],'syntax');self.assertIsNone(names[text.index('module')]['detail'])
        self.assertEqual(names[text.index('id<T:wire>')]['detail'],'shared fn hover::id<T: wire>(value: T) -> T')
        duplicate=self.cli('analyze',self.file,'--details','--references',ok=False);self.assertEqual(duplicate['code'],'E_OPTION')
        self.assertFalse((self.root/'.nex').exists())

    def test_actual_hover_and_definition_fix_069_primitive_and_generic_counterexample(self):
        text='module hover; fn id<T>(value:T)->T{return value;} fn main()->i64{return id<i64>(42);}'
        self.source(text);client=self.client();client.initialize();client.open(self.file,text);self.assertEqual(client.diagnostics(self.file,1),[])
        def query(at):return {'textDocument':{'uri':self.file.as_uri()},'position':{'line':0,'character':at}}
        at=text.index('i64>(42)');self.assertEqual(client.request('textDocument/definition',query(at)),[])
        self.assertEqual(client.request('textDocument/hover',query(at)),{'contents':{'kind':'plaintext','value':'type i64'},'range':{'start':{'line':0,'character':at},'end':{'line':0,'character':at+3}}})
        at=text.index('T>(value');self.assertEqual(client.request('textDocument/hover',query(at))['contents']['value'],'type parameter hover::id::T')
        use=text.index('T)->');definition=client.request('textDocument/definition',query(use));self.assertEqual(definition[0]['range']['start']['character'],at)
        self.assertIsNone(client.request('textDocument/hover',query(text.index('return value'))))
        self.assertEqual(client.request('textDocument/hover',query(text.index('id<i64>')))['contents']['value'],'shared fn hover::id<T>(value: T) -> T')
        self.assertFalse((self.root/'.nex').exists());self.assertEqual(self.file.read_text(),text)

    def test_identifier_details_cover_aliases_contracts_fields_and_unicode_crlf(self):
        library=('// Я🧠\r\nmodule model;pub trait Content{type Item;fn get(value:Self)->Content::Item<Self>;}'
                 'pub struct Box<T>{value:T;}fn extract<T>(value:Box<T>)->T{return value.value;}'
                 'pub impl boxed<T>:Content for Box<T>{type Item=T;get=extract<T>;}')
        helper=self.root/'model 🧠.nex';helper.write_bytes(library.encode())
        text=('module hover;\r\nimport "./model 🧠.nex" as m;\r\nfn main()->i64{let s:str="Я🧠";'
              'let value:m::Box<i64>=m::Box<i64>(42);return m::Content<m::Box<i64>>::get(value);}')
        self.source(text);data=self.cli('analyze',self.file,'--details');files={row['key']:row for row in data['files']}
        def record(source,key,word,at=0):
            begin=len(source[:source.index(word,at)].encode());return next(row for row in data['identifiers'] if row['file']==key and row['range']['begin']==begin)
        alias=record(text,'main.nex','m;',text.index(' as '));self.assertEqual(alias['kind'],'import_alias');self.assertIn('import m = model',alias['detail'])
        method=record(library,helper.name,'get(value');self.assertEqual(method['kind'],'trait_method');self.assertEqual(method['detail'],'shared fn model::Content::get(value: Self) -> model::Content::Item<Self>')
        associated=record(library,helper.name,'Item;');self.assertEqual(associated['detail'],'associated type model::Content::Item<Self>')
        self_use=record(library,helper.name,'Self)');self.assertEqual(self_use['kind'],'type_parameter');self.assertEqual(self_use['detail'],'type parameter model::Content::Self (trait self)')
        member_binding=record(library,helper.name,'get=extract');self.assertEqual(member_binding['detail'],method['detail']);self.assertEqual(member_binding['definition'],method['definition'])
        ordinary=record(library,helper.name,'extract<T>',library.index('fn extract'));self.assertEqual(ordinary['detail'],'shared fn model::extract<T>(value: model::Box<T>) -> T')
        field=record(library,helper.name,'value.value',library.index('fn extract'))
        self.assertEqual(field['kind'],'parameter')
        client=self.client();client.initialize();client.open(self.file,text);client.open(helper,library);self.assertEqual(client.diagnostics(self.file,1),[])
        at=text.index('get(value)');prefix=text[:at];query={'textDocument':{'uri':self.file.as_uri()},'position':{'line':prefix.count('\n'),'character':len(prefix.rsplit('\n',1)[-1].encode('utf-16-le'))//2}}
        self.assertEqual(client.request('textDocument/hover',query)['contents']['value'],method['detail'])
        target=client.request('textDocument/definition',query)[0];self.assertEqual(target['uri'],helper.resolve().as_uri());self.assertEqual(target['range']['start']['line'],1)
        self.assertFalse((self.root/'.nex').exists());self.assertEqual(self.file.read_bytes(),text.encode());self.assertEqual(helper.read_bytes(),library.encode())

    def test_higher_kind_and_ordinary_self_names_have_distinct_checked_descriptions(self):
        text=('module kinds;trait Mapper<Self<_>>{fn map<A,B>(values:Self<A>,apply:fn(A)->B)->Self<B>;} '
              'fn ordinary<Self>(value:Self)->Self{return value;} '
              'fn main()->i64{let yes:bool=true;let call:fn(i64)->i64=fn(value:i64)->i64{return value;};return call(42);}')
        self.source(text);data=self.cli('analyze',self.file,'--details');rows={row['range']['begin']:row for row in data['identifiers'] if row['file']=='main.nex'}
        first=text.index('Self<_>');second=text.index('Self>(value');self.assertEqual(rows[first]['detail'],'type parameter kinds::Mapper::Self<_> (trait self)');self.assertEqual(rows[second]['detail'],'type parameter kinds::ordinary::Self')
        self.assertNotEqual(rows[first]['definition'],rows[second]['definition']);self.assertEqual(rows[text.index('true;')]['detail'],'bool')
        self.assertIsNone(rows[text.rindex('return value')]['detail']);self.assertEqual(rows[text.rindex('return value')]['kind'],'syntax')
        self.assertFalse((self.root/'.nex').exists())

    def test_checked_identifier_conflicts_null_targets_and_cancellation_are_explicit(self):
        spec=importlib.util.spec_from_file_location('nex_lsp_details',harness.REPO/'editor/lsp/server.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        server=module.Server(harness.NEX,output=io.BytesIO());file={'key':'main.nex','path':str(self.file),'text':'T','hash':'a'*64};row={'file':'main.nex','range':{'begin':0,'end':1},'kind':'type_parameter','detail':'type parameter one::T','definition':{'file':'main.nex','range':{'begin':0,'end':1}}};index={'files':[file],'identifiers':[row],'occurrences':[],'symbols':[],'expressions':[]};cache={'epoch':0,'indices':[index],'documents':{}};query={'textDocument':{'uri':self.file.as_uri()},'position':{'line':0,'character':0}}
        try:
            self.assertEqual(server.query('textDocument/hover',query,cache)['contents']['value'],row['detail'])
            cache['indices'].append({**index,'identifiers':[{**row,'detail':'type parameter two::T'}]})
            for method in ['textDocument/hover','textDocument/definition']:
                with self.assertRaises(module.RPCError) as error:server.query(method,query,cache)
                self.assertEqual(error.exception.code,-32801)
            cache['indices'].pop();index['identifiers']=[{**row,'kind':'builtin_type','detail':'type i64','definition':None}]
            self.assertEqual(server.query('textDocument/definition',query,cache),[])
            cancel=threading.Event();cancel.set()
            with self.assertRaises(module.RPCError) as error:server.query('textDocument/hover',query,cache,cancel)
            self.assertEqual(error.exception.code,-32800)
            index['identifiers']=[{**row,'kind':'syntax','detail':None,'definition':None}];self.assertIsNone(server.query('textDocument/hover',query,cache))
        finally:server.close()

    def test_details_limit_fails_without_partial_output_or_legacy_contract_change(self):
        # The code is valid; the source declaration's signature exceeds the new
        # explicit per-identifier display bound, while legacy formats still work.
        params=[('p'+str(i)+'x'*280) for i in range(64)]
        text='module bounds;fn wide('+','.join(name+':i64' for name in params)+')->i64{return '+params[0]+';}fn main()->i64{return 42;}'
        self.source(text);self.assertTrue(self.cli('analyze',self.file)['ok']);self.assertTrue(self.cli('analyze',self.file,'--references')['ok'])
        result=self.cli('analyze',self.file,'--details',ok=False);self.assertEqual(result['code'],'E_ANALYSIS_LIMIT');self.assertIn('16 KiB',result['message'])
        self.assertNotIn('identifiers',result);self.assertFalse((self.root/'.nex').exists())

    def test_details_keep_template_signatures_and_concrete_field_value_types(self):
        text=('module details;struct Box<T>{value:T;}'
              'fn first<T>(box:Box<T>)->T{return box.value;}'
              'test fn proof()->unit!{io}{print(42);}'
              'fn main()->i64!{io}{let b:Box<i64>=Box<i64>(42);print(b.value);return first<i64>(b);}')
        self.source(text);data=self.cli('analyze',self.file,'--details');rows={row['range']['begin']:row for row in data['identifiers'] if row['file']=='main.nex'}
        self.assertEqual(rows[text.index('first<i64>')]['detail'],'shared fn details::first<T>(box: details::Box<T>) -> T')
        self.assertEqual(rows[text.index('box.value')+4]['detail'],'value: T')
        self.assertEqual(rows[text.index('b.value')+2]['detail'],'value: i64')
        self.assertEqual(rows[text.index('value:T')]['detail'],'value: T')
        self.assertEqual(rows[text.index('proof()')]['detail'],'shared test fn details::proof() -> unit !{io}')
        builtin=rows[text.index('print(b')];self.assertEqual(builtin['detail'],'builtin print; result unit');self.assertIsNone(builtin['definition'])
        self.assertFalse((self.root/'.nex').exists())

    def test_details_total_json_bound_is_separate_from_source_and_legacy_limits(self):
        name='f'+'x'*250
        text='module bounds;fn '+name+'(n:i64)->i64{return n;}fn main()->i64{'+(name+'(42);')*22000+'return 42;}'
        self.source(text);self.assertTrue(self.cli('analyze',self.file)['ok']);self.assertTrue(self.cli('analyze',self.file,'--references')['ok'])
        value=self.cli('analyze',self.file,'--details',ok=False);self.assertEqual(value['code'],'E_ANALYSIS_LIMIT');self.assertIn('8 MiB',value['message']);self.assertNotIn('identifiers',value)
        self.assertFalse((self.root/'.nex').exists())

    def test_completion_returns_local_values(self):
        text='module app;\nfn main()->unit !{io}{let value:i64=1;print(value);}\n'
        line=text.splitlines()[1];start=line.rindex('value')
        client=self.client();client.initialize();client.open(self.file,text)
        result=client.request('textDocument/completion', {'textDocument': {'uri': self.file.as_uri()},
            'position': {'line':1,'character':start+3}})
        items=[item for item in result['items'] if item['label']=='value']
        self.assertEqual(len(items),1)
        self.assertEqual(items[0]['kind'],6)

    def test_completion_returns_checked_declarations(self):
        text='module app;\nstruct Point { x: i64; }\nfn helper(x: i64) -> i64 { return x + 1; }\nfn main() -> unit !{io} { print(helper(1)); }\n'
        line=text.splitlines()[3];start=line.index('helper')
        client=self.client();capabilities=client.initialize()['capabilities']
        self.assertIn('completionProvider',capabilities)
        client.open(self.file,text)
        result=client.request('textDocument/completion', {'textDocument': {'uri': self.file.as_uri()},
            'position': {'line':3,'character':start+2}})
        labels={item['label'] for item in result['items']}
        self.assertIn('helper',labels)
        self.assertEqual(result['items'][0]['kind'],3)
        all_items=client.request('textDocument/completion', {'textDocument': {'uri': self.file.as_uri()},
            'position': {'line':3,'character':start}})
        self.assertTrue({'helper','main','Point'} <= {item['label'] for item in all_items['items']})

    def test_prepare_rename_and_rename_edits(self):
        text='module app;\nfn helper()->i64{return 1;}\nfn main()->i64{return helper();}\n'
        line=text.splitlines()[2];position={'line':2,'character':line.index('helper')}
        client=self.client();capabilities=client.initialize()['capabilities']
        self.assertTrue(capabilities['renameProvider']['prepareProvider'])
        client.open(self.file,text)
        prepare=client.request('textDocument/prepareRename', {'textDocument': {'uri': self.file.as_uri()}, 'position': position})
        self.assertEqual(prepare['placeholder'],'helper')
        renamed=client.request('textDocument/rename', {'textDocument': {'uri': self.file.as_uri()}, 'position': position, 'newName':'renamed'})
        edits=[edit for edits in renamed['changes'].values() for edit in edits]
        self.assertEqual(len(edits),2)
        self.assertTrue(all(edit['newText']=='renamed' for edit in edits))
        invalid=client.response(client.send('textDocument/rename', {'textDocument': {'uri': self.file.as_uri()}, 'position': position, 'newName':'bad-name'}, request=True))
        self.assertEqual(invalid['error']['code'],-32602)

    def test_formatting_returns_full_replace_without_writing(self):
        text='module app;\nfn main()->unit{print(1);}\n'
        physical=self.file.read_bytes()
        client=self.client();capabilities=client.initialize()['capabilities']
        self.assertTrue(capabilities['documentFormattingProvider'])
        client.open(self.file,text)
        result=client.request('textDocument/formatting', {'textDocument': {'uri': self.file.as_uri()},
            'options': {'tabSize': 2, 'insertSpaces': True}})
        self.assertEqual(len(result),1)
        self.assertIn('fn main() -> unit {',result[0]['newText'])
        self.assertEqual(result[0]['range']['start'],{'line':0,'character':0})
        self.assertEqual(self.file.read_bytes(),physical)
        client.change(self.file,result[0]['newText'],2)
        self.assertEqual(client.request('textDocument/formatting', {'textDocument': {'uri':self.file.as_uri()},
            'options': {'tabSize': 2, 'insertSpaces': True}}), [])
        self.assertEqual(self.file.read_bytes(),physical)
        client.close()

    def test_lifecycle_fragmented_messages_and_method_errors(self):
        client=self.client()
        first=client.response(client.send('textDocument/hover',{},request=True))
        self.assertEqual(first['error']['code'],-32002)
        capabilities=client.initialize()['capabilities']
        self.assertEqual(capabilities['positionEncoding'],'utf-16')
        self.assertEqual(capabilities['textDocumentSync']['change'],1)
        self.assertTrue(capabilities['definitionProvider'])
        self.assertEqual(client.response(client.send('nex/unknown',{},request=True))['error']['code'],-32601)
        self.assertEqual(client.response(client.send('initialize',{},request=True))['error']['code'],-32600)
        client.send('$/cancelRequest',{'id':[]})
        bad=client.response(client.send('textDocument/hover',{'textDocument':{'uri':'file://['},'position':{'line':0,'character':0}},request=True))
        self.assertEqual(bad['error']['code'],-32602)
        self.assertEqual(client.response(client.send('still-responding',{},request=True))['error']['code'],-32601)

    def test_unsaved_diagnostics_utf16_crlf_and_repair_never_write_sources(self):
        physical=self.file.read_bytes()
        client=self.client();client.initialize()
        bad='module app;\r\nfn main()->i64 {let text:str="Я🧠";return missing;}\r\n'
        client.open(self.file,bad,3)
        diagnostics=client.diagnostics(self.file,3)
        self.assertEqual(len(diagnostics),1)
        self.assertEqual(diagnostics[0]['code'],'E_NAME')
        expected=bad.split('\r\n')[1].index('missing')+1  # one astral scalar adds one UTF-16 unit
        self.assertEqual(diagnostics[0]['range']['start'],{'line':1,'character':expected})
        fixed=bad.replace('missing','42')
        client.change(self.file,fixed,4)
        self.assertEqual(client.diagnostics(self.file,4),[])
        self.assertEqual(self.file.read_bytes(),physical)
        self.assertFalse((self.root/'.nex').exists())

    def test_definitions_symbols_types_and_local_binding(self):
        text='module app;\nfn twice(n:i64)->i64 {let x:i64=n+1;return x*2;}\nfn main()->i64{return twice(20);}\n'
        client=self.client();client.initialize();client.open(self.file,text)
        self.assertEqual(client.diagnostics(self.file,1),[])
        params={'textDocument':{'uri':self.file.as_uri()}}
        symbols=client.request('textDocument/documentSymbol',params)
        self.assertEqual([s['name'] for s in symbols],['twice','main'])
        query={**params,'position':{'line':2,'character':22}}
        definition=client.request('textDocument/definition',query)
        self.assertEqual(definition[0]['range'],{'start':{'line':1,'character':3},'end':{'line':1,'character':8}})
        query['position']={'line':1,'character':43}
        local=client.request('textDocument/definition',query)
        self.assertEqual(local[0]['range']['start'],{'line':1,'character':26})
        self.assertEqual(client.request('textDocument/hover',query)['contents']['value'],'x: i64')
        self.assertFalse((self.root/'.nex').exists())

    def test_imported_document_unsaved_and_old_versions_are_ignored(self):
        helper=self.root/'helper.nex';helper.write_text('module model;pub fn answer()->i64{return 1;}', newline="\n")
        text='module app;import "./helper.nex" as m;fn main()->i64{return m::answer();}'
        self.file.write_text(text, newline="\n")
        client=self.client();client.initialize();client.open(self.file,text)
        client.open(helper,'module model;pub fn answer()->i64{return true;}',2)
        self.assertEqual(client.diagnostics(helper,2)[0]['code'],'E_TYPE')
        client.change(helper,'module model;pub fn answer()->i64{return 42;}',3)
        self.assertEqual(client.diagnostics(helper,3),[])
        client.change(helper,'this old edit is invalid',2)
        symbols=client.request('textDocument/documentSymbol',{'textDocument':{'uri':helper.as_uri()}})
        self.assertEqual(symbols[0]['name'],'answer')
        self.assertEqual(helper.read_text(),'module model;pub fn answer()->i64{return 1;}')

    def test_new_file_and_cancellation_do_not_block_protocol(self):
        wrapper=self.root/'slow compiler'
        wrapper=python_executable(wrapper,'#!'+sys.executable+'\nimport os,time\ntime.sleep(0.5)\nos.execv('+repr(harness.NEX)+', ['+repr(harness.NEX)+']+__import__("sys").argv[1:])\n',harness.native_fixture_compiler())
        wrapper.chmod(0o700)
        client=self.client([sys.executable,str(harness.REPO/'editor/lsp/server.py'),'--compiler',str(wrapper)])
        client.initialize();client.open(self.file,self.file.read_text())
        request=client.send('textDocument/hover',{'textDocument':{'uri':self.file.as_uri()},'position':{'line':0,'character':16}},request=True)
        client.send('$/cancelRequest',{'id':request})
        started=time.monotonic()
        self.assertEqual(client.response(client.send('unknown',{},request=True))['error']['code'],-32601)
        self.assertLess(time.monotonic()-started,0.4)
        self.assertEqual(client.response(request)['error']['code'],-32800)
        client.change(self.file,'module app; fn main()->i64{return 42;}',5)
        client.change(self.file,'module app; fn main()->i64{return 43;}',6)
        self.assertEqual(client.diagnostics(self.file,6),[])

    def test_unicode_position_and_changed_physical_diagnostic_guard(self):
        spec=importlib.util.spec_from_file_location('nex_lsp',harness.REPO/'editor/lsp/server.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        self.assertEqual(module.byte_offset('a🧠b',{'line':0,'character':3}),5)
        with self.assertRaises(module.RPCError):module.byte_offset('a🧠b',{'line':0,'character':2})
        server=module.Server(harness.NEX)
        try:
            _, diagnostic=server.diagnostic({'file':'main.nex','code':'E_TYPE','message':'old error','frontend':{
                'source':{'utf8':True,'sha256':'0'*64},'location':{'byte_begin':20,'byte_end':24}}},self.root,self.file,{})
            self.assertEqual(diagnostic['range']['start'],{'line':0,'character':0})
        finally:server.close()

    def test_exit_without_shutdown_and_malformed_frame_are_terminal(self):
        for raw in [b'Content-Length: 56\r\nContent-Length: 56\r\n\r\n',
                    b'Content-Length: 0\r\n\r\n']:
            process=subprocess.run([harness.NEX,'lsp'],input=raw,cwd=self.root,capture_output=True,timeout=10)
            self.assertEqual(process.returncode,1)
            self.assertEqual(process.stdout,b'')
        client=self.client();client.send('exit');self.assertEqual(client.process.wait(timeout=10),1)

    def test_timer_scheduling_and_shutdown_cannot_race(self):
        spec=importlib.util.spec_from_file_location('nex_lsp_shutdown',harness.REPO/'editor/lsp/server.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        server=module.Server(harness.NEX,output=io.BytesIO())
        entered=threading.Event();release=threading.Event();closed=threading.Event();errors=[]
        original=server.executor.submit
        def delayed(*args,**kwargs):
            entered.set()
            if not release.wait(5):raise AssertionError('test scheduling barrier timed out')
            return original(*args,**kwargs)
        server.executor.submit=delayed
        def schedule():
            try:server.background()
            except Exception as error:errors.append(str(error))
        def close():
            try:server.close()
            except Exception as error:errors.append(str(error))
            finally:closed.set()
        scheduling=threading.Thread(target=schedule);closing=threading.Thread(target=close)
        scheduling.start()
        try:
            self.assertTrue(entered.wait(5))
            closing.start()
            closed.wait(0.15)
        finally:
            release.set();scheduling.join(5)
            if closing.ident is not None:closing.join(5)
            else:server.close()
        self.assertFalse(scheduling.is_alive());self.assertFalse(closing.is_alive())
        self.assertEqual(errors,[])

    def test_invalid_requests_and_non_utf8_frames_receive_standard_errors(self):
        client=self.client();client.initialize()
        for raw,code in [(b'{}',-32600),(b'[]',-32600),('{"jsonrpc":"2.0","method":"a"}'.encode('utf-16'),-32700)]:
            client.process.stdin.write(('Content-Length: '+str(len(raw))+'\r\n\r\n').encode()+raw)
            client.process.stdin.flush()
            response=client.take(lambda m:m.get('id') is None and 'error' in m)
            self.assertEqual(response['error']['code'],code)
        self.assertEqual(client.request('textDocument/documentSymbol',{'textDocument':{'uri':self.file.as_uri()}}),[])

    def test_standalone_installed_style_acceptance_uses_actual_compiler(self):
        output=self.root/'lsp-acceptance'
        result=subprocess.run([sys.executable,str(harness.REPO/'editor/lsp/acceptance.py'),harness.NEX,'--output',str(output)],
                              cwd=self.root,capture_output=True,text=True,timeout=45)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        report=json.loads(result.stdout)
        self.assertTrue(report['ok']);self.assertTrue(report['source_and_graph_unchanged'])
        self.assertTrue(report['type_reference_checks']);self.assertTrue(report['identifier_checks']);self.assertTrue(report['resource_checks']);self.assertEqual(report['messages_sent'],35);self.assertEqual(report['stderr'],'')


if __name__=='__main__':
    unittest.main(verbosity=2)
