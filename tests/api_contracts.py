"""Endpoint semantics, graph transactions, generated SDKs, OpenAPI and live routing."""
import base64
import json
from pathlib import Path
import queue
import random
import re
import shutil
import signal
import subprocess
import threading
import unittest
import urllib.error
import urllib.request
import support as harness


class API(harness.ToolchainCase):
    def test_binary_generic_models_openapi_sdk_and_live_validation(self):
        self.source('''module binary_api;import "std/api.nex" as api;
pub struct Blob<T:wire>{data:T;parts:list<bytes>;}
server fn handle(context:api::Context,input:Blob<bytes>)->result<Blob<bytes>>{
 if len(input.data)==1 && input.data[0]==255 {assert(false);}
 return ok(Blob<bytes>(input.data+utf8_bytes("!"),input.parts));
}
server fn sentinel()->str{return "BINARY_SERVER_ONLY_SENTINEL";}
endpoint echo_blob("POST","/api/blob")=handle;
''')
        generated = self.cli('api', self.file, '--directory', self.root/'generated')
        client = self.root/'generated/client'
        document = json.loads(Path(generated['openapi']).read_text())
        model = next(value for value in document['components']['schemas'].values()
                     if value.get('properties', {}).get('data', {}).get('x-nex-type') == 'bytes')
        binary = model['properties']['data']
        self.assertEqual(binary['type'], 'string')
        self.assertEqual(binary['contentEncoding'], 'base64')
        self.assertEqual(binary['contentMediaType'], 'application/octet-stream')
        self.assertEqual(model['properties']['parts']['items']['x-nex-type'], 'bytes')
        self.assertFalse(model['additionalProperties'])
        for source in client.rglob('*.nex'):
            self.assertNotIn('BINARY_SERVER_ONLY_SENTINEL', source.read_text())
            self.assertNotIn('server fn handle', source.read_text())
        consumer = self.root/'consumer.nex'
        consumer.write_text(r'''module binary_consumer;
import "./generated/client/api.nex" as sdk;
import "./generated/client/models/binary_api.nex" as model;
import "std/net.nex" as net;import "std/web.nex" as web;
fn main()->unit{}
test fn binary_helpers()->unit{
 let data:bytes=unwrap(bytes([0,255,128,65]));
 let value:model::Blob<bytes>=model::Blob<bytes>(data,[slice(data,1,2)]);
 let command:net::Command=sdk::request_echo_blob("1","token",value,"received",1000);
 let payload:net::TypedPayload=unwrap(decode_json<net::TypedPayload>(command.body));
 assert(unwrap(decode_json<model::Blob<bytes>>(payload.body))==value);
 let response:net::Response=net::Response("1",200,ok(encode_json(ok(value))));
 assert(unwrap(sdk::response_echo_blob(web::Event("received",encode_json(response),"/")))==value);
 let invalid:net::Response=net::Response("1",200,ok("{\"ok\":{\"data\":\"AB==\",\"parts\":[]}}"));
 assert(error_code(sdk::response_echo_blob(web::Event("received",encode_json(invalid),"/")))=="E_JSON");
}
''')
        self.cli('test', consumer)
        self.cli('test', consumer, '--profile', 'release')
        if shutil.which('node'):
            self.cli('test', consumer, '--target', 'web')
        built = self.cli('build', generated['server_entry'], '--target', 'server',
                         '--profile', 'release', timeout=180)
        auth = self.root/'auth.json'
        token = self.cli('token', '--user', 'alice', '--auth', auth)['token']
        process = subprocess.Popen([built['executable'], '--auth', str(auth), '--database',
            str(self.root/'data.sqlite'), '--port', '0'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            lines = queue.Queue()
            threading.Thread(target=lambda: lines.put(process.stdout.readline()), daemon=True).start()
            address = re.match(r'NEX server (http://127\.0\.0\.1:\d+)', lines.get(timeout=15)).group(1)
            def request(body):
                raw = body if isinstance(body, bytes) else json.dumps(body).encode()
                req = urllib.request.Request(address+'/api/blob', data=raw,
                    headers={'Authorization': 'Bearer '+token, 'Content-Type': 'application/json'})
                try:
                    response = urllib.request.urlopen(req, timeout=15)
                except urllib.error.HTTPError as error:
                    response = error
                with response:
                    return response.status, json.loads(response.read())
            raw = bytes(range(256))
            encode = lambda value: base64.b64encode(value).decode('ascii')
            value = {'data': encode(raw), 'parts': ['', encode(bytes([0, 255]))]}
            expected = {'ok': dict(value, data=encode(raw+b'!'))}
            self.assertEqual(request(value), (200, expected))
            for invalid in ['AA', 'AB==', '_w==', 'AA==\n', [0, 255], {'bytes': 'AA=='}]:
                with self.subTest(invalid=invalid):
                    self.assertEqual(request(dict(value, data=invalid))[0], 400)
            self.assertEqual(request(dict(value, parts=['AB==']))[0], 400)
            for _ in range(3):
                self.assertEqual(request({'data': '/w==', 'parts': []})[0], 500)
            self.assertEqual(request(value), (200, expected))
        finally:
            process.send_signal(signal.SIGTERM)
            output, errors = process.communicate(timeout=15)
            self.assertEqual(process.returncode, 0, output+errors)
            self.assertNotIn('E_INTERNAL_LEAK', errors)

    def test_floating_models_schema_and_generated_client_agree(self):
        self.source('''module numeric_api;import "std/api.nex" as api;
pub struct Sample{value:f64;}
server fn handle(context:api::Context,input:Sample)->result<Sample>{return ok(Sample(input.value*2e0));}
server fn sentinel()->str{return "FLOATING_SERVER_ONLY_SENTINEL";}
endpoint double_value("POST","/api/double")=handle;
''')
        generated=self.cli('api',self.file,'--directory',self.root/'generated')
        document=json.loads(Path(generated['openapi']).read_text())
        model=next(value for value in document['components']['schemas'].values() if value.get('properties',{}).get('value',{}).get('x-nex-type')=='f64')
        self.assertEqual(model['properties']['value']['type'],'number')
        self.assertEqual(model['properties']['value']['format'],'double')
        client=self.root/'generated/client'
        for source in client.rglob('*.nex'):self.assertNotIn('FLOATING_SERVER_ONLY_SENTINEL',source.read_text())
        app=client/'numeric.nex';app.write_text('''module numeric_sdk;import "./models/numeric_api.nex" as model;
fn main()->unit!{io}{print(encode_json(model::Sample(1.25)));}
test fn wire()->unit{assert(unwrap(decode_json<model::Sample>("{\\"value\\":1.25}")).value==1.25);}
''')
        self.assertEqual(self.cli('run',app,cwd=client)['stdout'],'{"value":1.25e0}\n')
        self.cli('test',app,cwd=client);self.cli('test',app,'--target','web',cwd=client)

    def example(self):
        for name in ('service.nex', 'model.nex'):
            shutil.copyfile(harness.REPO / 'examples/api' / name, self.root / name)
        self.file = self.root / 'service.nex'
        return self.file

    def simple(self):
        return 'module routes; import "std/api.nex" as api; pub struct Row { id: i64; } server fn handle(context: api::Context, input: Row) -> result<Row> { return ok(input); } endpoint create("POST", "/api/rows", 201) = handle;'

    def callback_library(self, extra, helpers=False):
        standard = self.root/'standard'; standard.mkdir()
        libraries = {'std': 'standard'}
        if helpers:
            directory = self.root/'helpers'; directory.mkdir()
            (directory/'types.nex').write_text('module callback_types;pub struct Token{id:i64;}')
            libraries['helpers'] = 'helpers'
        for name in ('api.nex', 'http.nex', 'web.nex', 'net.nex'):
            text = (harness.REPO/'lib'/name).read_text()
            if name == 'net.nex':
                text += extra
            (standard/name).write_text(text)
        (self.root/'nex.json').write_text(json.dumps({
            'entry': 'main.nex', 'language': self.cli('describe')['version'], 'libraries': libraries}))
        self.source(self.simple()+'\nimport "std/net.nex" as custom_net;\n')
        self.cli('api', self.file, '--directory', self.root/'generated')
        return self.root/'generated/client'

    def test_callback_library_projection_preserves_inline_closure_once(self):
        client = self.callback_library('''
pub fn capture(value:i64)->(fn(i64)->i64){return fn(extra:i64)->i64{return value+extra;};}
pub server fn unused_server()->str{return "CALLBACK_SERVER_SENTINEL";}
fn unused_private()->str{return "CALLBACK_PRIVATE_SENTINEL";}
''')
        for source in client.rglob('*.nex'):
            text = source.read_text()
            self.assertNotIn('CALLBACK_SERVER_SENTINEL', text)
            self.assertNotIn('CALLBACK_PRIVATE_SENTINEL', text)
            self.assertNotIn('$lambda_', text)
        manifest = json.loads((client/'nex.json').read_text())
        net = (client/manifest['libraries']['std']/'net.nex').read_text()
        self.assertEqual(net.count('fn capture('), 1)
        app = client/'callbacks.nex'
        app.write_text('module sdk_callbacks;import "std/net.nex" as net;'
            'fn main()->unit!{io}{print(net::capture(40)(2));}'
            'test fn cases()->unit{assert(net::capture(40)(2)==42);}')
        self.assertEqual(self.cli('eval', app, cwd=client)['stdout'], '42\n')
        self.assertEqual(self.cli('run', app, cwd=client)['stdout'], '42\n')
        self.cli('test', app, cwd=client)
        self.cli('test', app, '--target', 'web', cwd=client)

    def test_callback_only_nominal_types_keep_their_imports_and_definitions(self):
        client = self.callback_library('''
import "helpers/types.nex" as types;
pub fn consume(callback:fn(types::Token)->i64)->i64{return 42;}
''', helpers=True)
        manifest = json.loads((client/'nex.json').read_text())
        self.assertIn('helpers', manifest['libraries'])
        self.assertIn('pub struct Token', (client/manifest['libraries']['helpers']/'types.nex').read_text())
        app = client/'callback_types.nex'
        app.write_text('module sdk_callback_types;import "std/net.nex" as net;'
            'import "helpers/types.nex" as types;'
            'fn take(value:types::Token)->i64{return value.id;}'
            'test fn cases()->unit{assert(net::consume(take)==42);}')
        self.cli('test', app, cwd=client)
        self.cli('test', app, '--target', 'web', cwd=client)

    def test_phantom_callable_type_arguments_preserve_extracted_model_imports(self):
        (self.root/'types.nex').write_text('module callback_types;pub struct Token{id:i64;}')
        callback = 'fn(types::Token)->(fn()->types::Token)'
        self.source('module routes;import "std/api.nex" as api;import "./types.nex" as types;'
            'pub struct Tag<T>{id:i64;}'
            'server fn handle(context:api::Context,input:Tag<'+callback+'>)->result<Tag<'+callback+'>>{return ok(input);}'
            'endpoint create("POST","/api/tags",201)=handle;')
        self.cli('check')
        self.assertIn('callback_types::Token', {s['name'] for s in self.cli('context','--symbol','create')['structures']})
        self.cli('api', self.file, '--directory', self.root/'generated')
        client = self.root/'generated/client'
        self.assertTrue((client/'models/callback_types.nex').is_file())
        self.cli('check', client/'api.nex', cwd=client)
        app = client/'phantom.nex'
        app.write_text('module sdk_phantom;import "./models/routes.nex" as model;'
            'import "./models/callback_types.nex" as types;'
            'test fn cases()->unit{let tag:model::Tag<'+callback+'> = model::Tag(42);'
            'assert(encode_json(tag)=="{\\"id\\":\\"42\\"}");}')
        self.cli('test', app, cwd=client)
        self.cli('test', app, '--target', 'web', cwd=client)

    def test_endpoint_rejections_are_checked_before_graph_commit(self):
        valid = self.simple()
        head = self.cli('check', self.source(valid))['revision']
        for invalid, code in [
            (valid.replace('"POST"', '"TRACE"'), 'E_API_METHOD'),
            (valid.replace('/api/rows', '/api/../secret'), 'E_API_PATH'),
            (valid.replace('/api/rows', '/api/%2fsecret'), 'E_API_PATH'),
            (valid.replace(', 201)', ', 204)'), 'E_API_STATUS'),
            (valid.replace('server fn', 'shared fn'), 'E_API_SIGNATURE'),
            (valid.replace('"POST"', '"GET"'), 'E_API_SIGNATURE'),
            (valid.replace('pub struct', 'struct'), 'E_VISIBILITY'),
            (valid + 'endpoint duplicate("POST", "/api/rows") = handle;', 'E_API_ROUTE'),
            (valid + 'endpoint create("POST", "/api/other") = handle;', 'E_API_NAME'),
            (valid + 'client fn forbidden() -> result<Row> { return handle(api::Context("x", "y"), Row(1)); }', 'E_REALM'),
            (valid.replace('context: api::Context', 'context: i64'), 'E_API_SIGNATURE'),
            (valid.replace('pub struct Row { id: i64; }', 'pub struct Row { ' + ''.join('field%d: i64; ' % i for i in range(1025)) + ' }'), 'E_API_LIMIT'),
        ]:
            with self.subTest(code=code, source=invalid):
                self.source(invalid)
                self.assertEqual(self.cli('check', ok=False)['code'], code)
                self.assertEqual(self.cli('history')['head'], head)

    def test_endpoint_graph_identity_context_patch_and_frozen_generation(self):
        self.source(self.simple())
        revision = self.cli('check')['revision']
        first = self.cli('graph')['endpoints'][0]
        context = self.cli('context', '--symbol', 'create')
        self.assertEqual(context['kind'], 'endpoint')
        self.assertEqual(context['contract']['input']['root'], {'record': 'routes::Row'})
        self.assertEqual(context['handler']['name'], 'routes::handle')
        self.assertIn('routes::create', self.cli('context', '--symbol', 'handle')['callers'])
        patch = self.root / 'patch.json'
        patch.write_text(json.dumps({'expected_revision': revision, 'replacements': [{'name': 'create', 'source': 'endpoint create("POST", "/api/new", 202) = handle;'}]}))
        changed = self.cli('apply', '--patch', patch)['revision']
        self.assertNotEqual(changed, revision)
        second = self.cli('graph')['endpoints'][0]
        self.assertEqual(first['id'], second['id']); self.assertNotEqual(first['hash'], second['hash'])
        self.assertIn('/api/rows', self.file.read_text())
        self.file.unlink()
        output = self.root / 'frozen API'
        self.cli('api', '--revision', changed, '--directory', output)
        self.assertEqual(json.loads((output / 'api.json').read_text())['endpoints'][0]['path'], '/api/new')
        self.assertEqual(self.cli('api', '--revision', changed, '--directory', output, ok=False)['code'], 'E_EXISTS')
        self.assertEqual(self.cli('api', '--revision', revision)['endpoints'][0]['path'], '/api/rows')

    def test_generation_extracts_models_and_openapi_has_exact_i64_bounds(self):
        self.example()
        generated = self.cli('api', self.file, '--directory', self.root / 'generated')
        client = self.root / 'generated/client'
        for source in client.rglob('*.nex'):
            self.assertNotIn('SERVER_ONLY_TYPED_API_SENTINEL', source.read_text())
            self.assertNotIn('store_put(', source.read_text())
        self.assertNotIn('struct State', (client / 'models/api_example/model.nex').read_text())
        document = json.loads(Path(generated['openapi']).read_text())
        self.assertEqual(document['openapi'], '3.1.1')
        self.assertEqual(set(document['paths']['/api/tasks']), {'get', 'post', 'put', 'delete'})
        self.assertEqual(document['components']['securitySchemes']['bearerAuth']['scheme'], 'bearer')
        model = document['components']['schemas']['nex_11_api_example_5_model_4_Task']
        self.assertFalse(model['additionalProperties'])
        integer = model['properties']['id']['pattern']
        values = [0, 1, -1, -(2**63), 2**63-1, -(2**63)-1, 2**63, 10**19, -(10**19)]
        rng = random.Random(41)
        values += [rng.randrange(-(10**20), 10**20) for _ in range(500)]
        for value in values:
            self.assertEqual(bool(re.search(integer, str(value))), -(2**63) <= value < 2**63)
        for invalid in ('-0', '+1', '01', '-01', '1e2', '١', ' 1', '1\n', '1\r\n', '1\u2028', '\n1'):
            self.assertIsNone(re.search(integer, invalid))

    def test_generated_sdk_pure_helpers_agree_in_all_backends(self):
        self.example(); self.cli('api', self.file, '--directory', self.root / 'generated')
        self.source('''module consumer;
import "./generated/client/api.nex" as api;
import "./generated/client/models/api_example/model.nex" as model;
import "std/net.nex" as net;
import "std/web.nex" as web;
fn main() -> unit {}
test fn codecs() -> unit {
  let command: net::Command = api::request_create_task("1", "runtime-token", model::Create("Я🦊"), "received", 1000);
  assert(command.kind == "typed_request"); assert(command.method == "POST");
  let data: net::TypedPayload = unwrap(decode_json<net::TypedPayload>(command.body));
  assert(unwrap(decode_json<model::Create>(data.body)).text == "Я🦊");
  let task: model::Task = model::Task(9007199254740993, "🦊", false);
  let response: net::Response = net::Response("1", 201, ok(encode_json(ok(task))));
  assert(unwrap(api::response_create_task(web::Event("received", encode_json(response), "/"))) == task);
  let error: net::Response = net::Response("1", 422, ok(encode_json(err<model::Task>("DENIED", "No access"))));
  assert(error_code(api::response_create_task(web::Event("received", encode_json(error), "/"))) == "DENIED");
  let wrong: net::Response = net::Response("1", 200, ok(encode_json(ok(task))));
  assert(error_code(api::response_create_task(web::Event("received", encode_json(wrong), "/"))) == "E_API_PROTOCOL");
  let malformed: net::Response = net::Response("1", 201, ok("{\\\"ok\\\":{\\\"id\\\":1,\\\"text\\\":\\\"x\\\",\\\"complete\\\":false}}"));
  assert(error_code(api::response_create_task(web::Event("received", encode_json(malformed), "/"))) == "E_JSON");
}
''')
        self.cli('test', self.file, '--profile', 'release')
        self.cli('test', self.file, '--target', 'web')

    def test_imported_endpoints_and_transitive_models_generate_portably(self):
        (self.root/'domain').mkdir()
        (self.root/'domain/base.nex').write_text('module domain::base; pub struct Child { value: i64; }')
        (self.root/'domain/rows.nex').write_text('module domain::rows; import "./base.nex" as b; pub struct Row { children: list<b::Child>; }')
        (self.root/'impl.nex').write_text('module implementation; import "std/api.nex" as api; import "./domain/rows.nex" as m; pub server fn fetch(context: api::Context) -> result<m::Row> { return ok(m::Row([])); }')
        (self.root/'routes.nex').write_text('module routes; import "./impl.nex" as service; endpoint fetch_rows("GET", "/api/rows") = service::fetch;')
        self.source('module root_app; import "./routes.nex" as routes; fn main() -> unit {}')
        built=self.cli('api',self.file,'--directory',self.root/'generated')
        self.cli('check',built['server_entry'])
        self.cli('check',built['client_entry'])
        self.assertTrue((self.root/'generated/client/models/domain/base.nex').is_file())
        source=(self.root/'generated/client/models/domain/rows.nex').read_text()
        self.assertIn('import "./base.nex"',source)
        self.assertNotIn('server fn',source)

    def test_invalid_generated_candidate_leaves_no_partial_output(self):
        self.example()
        standard=self.root/'standard';standard.mkdir()
        for file in ('api.nex','http.nex','web.nex','net.nex'):
            text=(harness.REPO/'lib'/file).read_text()
            if file=='net.nex': text=text.replace('fn typed_request(', 'fn renamed_typed_request(')
            (standard/file).write_text(text)
        (self.root/'nex.json').write_text(json.dumps({'entry':'service.nex','language':'0.17','libraries':{'std':'standard'}}))
        self.file.write_text(self.file.read_text()+'\nimport "std/net.nex" as custom_net;\n')
        destination=self.root/'generated'
        self.assertEqual(self.cli('api',self.file,'--directory',destination,ok=False)['code'],'E_NAME')
        self.assertFalse(destination.exists())
        self.assertEqual(list(self.root.glob('generated.tmp.*')),[])

    def test_sdk_excludes_server_and_private_unused_standard_code(self):
        self.example();standard=self.root/'standard';standard.mkdir()
        helpers=self.root/'helpers';helpers.mkdir()
        (helpers/'tools.nex').write_text('module helpers::tools; pub fn data() -> str { return format(); } fn format() -> str { return "data"; } pub server fn hidden() -> str { return "SERVER_PKG_SECRET"; }')
        for name in ('api.nex','http.nex','web.nex','net.nex'):
            text=(harness.REPO/'lib'/name).read_text()
            if name=='net.nex': text+='''
import "helpers/tools.nex" as tools;
pub server fn server_secret() -> str { return "SERVER_STD_SECRET"; }
fn unused_secret() -> str { return "UNUSED_STD_SECRET"; }
struct PrivateStore { value: str; }
pub fn public_helper() -> str { return helper() + tools::data(); }
fn helper() -> str { return "public data"; }
'''
            (standard/name).write_text(text)
        (self.root/'nex.json').write_text(json.dumps({'entry':'service.nex','language':'0.17','libraries':{'std':'standard','helpers':'helpers'}}))
        self.file.write_text(self.file.read_text()+'\nimport "std/net.nex" as custom_net;\n')
        self.cli('api',self.file,'--directory',self.root/'generated')
        client=self.root/'generated/client'
        for source in client.rglob('*.nex'):
            self.assertNotIn('SERVER_STD_SECRET',source.read_text())
            self.assertNotIn('UNUSED_STD_SECRET',source.read_text())
            self.assertNotIn('SERVER_PKG_SECRET',source.read_text())
            self.assertNotIn('PrivateStore',source.read_text())
        manifest=json.loads((client/'nex.json').read_text())
        library=(client/manifest['libraries']['std']/'net.nex').read_text()
        self.assertIn('fn public_helper',library);self.assertIn('fn helper',library)
        self.assertIn('helpers',manifest['libraries'])
        self.assertIn('fn format',(client/manifest['libraries']['helpers']/'tools.nex').read_text())

    def test_enum_api_models_sdk_openapi_and_live_cleanup(self):
        self.source('''module enum_service; import "std/api.nex" as api;
pub enum Event { Reset; Set(value:i64); }
enum Hidden { Secret; }
server fn echo(context:api::Context,input:Event) -> result<Event> {
 match input { Event::Reset() => { return ok(Event::Reset()); } Event::Set(value) => { if value < 0 { assert(false); } return ok(Event::Set(value)); } }
}
endpoint echo_event("POST","/api/event") = echo;
fn server_only() -> str { return "ENUM_SERVER_ONLY_SENTINEL"; }
''')
        generated=self.cli('api',self.file,'--directory',self.root/'generated')
        client=self.root/'generated/client'
        model=client/'models/enum_service.nex'
        self.assertIn('pub enum Event',model.read_text());self.assertNotIn('Hidden',model.read_text())
        for path in client.rglob('*.nex'): self.assertNotIn('ENUM_SERVER_ONLY_SENTINEL',path.read_text())
        document=json.loads(Path(generated['openapi']).read_text())
        schema=next(value for value in document['components']['schemas'].values() if 'oneOf' in value and value['oneOf'][0].get('properties',{}).get('case'))
        self.assertEqual([v['properties']['case']['const'] for v in schema['oneOf']],['Reset','Set'])
        consumer=self.root/'consumer.nex';consumer.write_text('''module consumer;
import "./generated/client/api.nex" as sdk; import "./generated/client/models/enum_service.nex" as m;
import "std/net.nex" as net; import "std/web.nex" as web;
fn main() -> unit {}
test fn helpers() -> unit {
 let e:m::Event = m::Event::Set(42);
 let request:net::Command = sdk::request_echo_event("1","token",e,"received",1000);
 let payload:net::TypedPayload = unwrap(decode_json<net::TypedPayload>(request.body));
 assert(unwrap(decode_json<m::Event>(payload.body)) == e);
 let response:net::Response = net::Response("1",200,ok(encode_json(ok(e))));
 assert(unwrap(sdk::response_echo_event(web::Event("received",encode_json(response),"/"))) == e);
}''')
        self.cli('test',consumer);self.cli('test',consumer,'--target','web')
        built=self.cli('build',generated['server_entry'],'--target','server','--profile','release',timeout=180)
        auth=self.root/'auth.json';token=self.cli('token','--user','alice','--auth',auth)['token']
        process=subprocess.Popen([built['executable'],'--auth',str(auth),'--database',str(self.root/'data.sqlite'),'--port','0'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            lines=queue.Queue();threading.Thread(target=lambda:lines.put(process.stdout.readline()),daemon=True).start()
            address=re.match(r'NEX server (http://127\.0\.0\.1:\d+)',lines.get(timeout=15)).group(1)
            def request(body):
                raw=body if isinstance(body,bytes) else json.dumps(body).encode()
                req=urllib.request.Request(address+'/api/event',data=raw,headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
                try: response=urllib.request.urlopen(req,timeout=15)
                except urllib.error.HTTPError as error: response=error
                with response:return response.status,json.loads(response.read())
            event={'case':'Set','fields':{'value':'42'}}
            self.assertEqual(request(event),(200,{'ok':event}))
            for body in [{'case':'Unknown','fields':{}},{'case':'Set','fields':{'value':42}},b'{"case":"Reset","case":"Set","fields":{}}']:
                self.assertEqual(request(body)[0],400)
            for _ in range(3):self.assertEqual(request({'case':'Set','fields':{'value':'-1'}})[0],500)
            self.assertEqual(request(event),(200,{'ok':event}))
        finally:
            process.send_signal(signal.SIGTERM);output,errors=process.communicate(timeout=15)
            self.assertEqual(process.returncode,0,output+errors);self.assertNotIn('E_INTERNAL_LEAK',errors)

    def test_generated_server_auth_strict_inputs_transactions_and_context(self):
        self.example()
        self.file.write_text(self.file.read_text() + '''
endpoint identity("GET", "/api/me") = who;
endpoint fail_write("POST", "/api/fail") = fail;
endpoint probe_write("GET", "/api/probe") = probe;
server fn who(context: api::Context) -> result<api::Context> { return ok(context); }
server fn fail(context: api::Context, trap: bool) -> result<bool> !{db} {
  store_put("probe", "uncommitted"); if trap { assert(false); } return err("DENIED", "Rejected");
}
server fn probe(context: api::Context) -> result<str> !{db} { return store_get("probe"); }
''')
        generated = self.cli('api', self.file, '--directory', self.root / 'generated')
        built = self.cli('build', generated['server_entry'], '--target', 'server', '--profile', 'release', timeout=180)
        auth = self.root / 'auth.json'
        alice = self.cli('token', '--user', 'alice', '--auth', auth)['token']
        bob = self.cli('token', '--user', 'bob', '--auth', auth)['token']
        process = subprocess.Popen([built['executable'], '--auth', str(auth), '--database', str(self.root / 'data.sqlite'), '--port', '0'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            lines = queue.Queue();threading.Thread(target=lambda: lines.put(process.stdout.readline()), daemon=True).start()
            match = re.match(r'NEX server (http://127\.0\.0\.1:\d+)', lines.get(timeout=15)); self.assertIsNotNone(match)
            def request(method, path='/api/tasks', body=None, token=alice):
                headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'}
                data=body if isinstance(body,bytes) else None if body is None else json.dumps(body).encode()
                try: response=urllib.request.urlopen(urllib.request.Request(match.group(1)+path,data=data,headers=headers,method=method),timeout=15)
                except urllib.error.HTTPError as error: response=error
                with response: return response.status,json.loads(response.read())
            self.assertEqual(request('GET')[1],{'ok': []})
            status, created=request('POST',body={'text': 'durable 🦊'})
            self.assertEqual((status,created['ok']['id']),(201,'1'))
            self.assertEqual(request('GET',token=bob)[1],{'ok': []})
            self.assertEqual(request('GET','/api/me')[1]['ok']['user'],'alice')
            self.assertEqual(request('GET',token='invalid')[0],401)
            for body in ({'text':'x','user':'bob'},b'{"text":"x","text":"y"}'):
                self.assertEqual(request('POST',body=body)[0],400)
            self.assertEqual(request('GET','/api/tasks?user=bob')[0],400)
            self.assertEqual(request('PATCH',body={})[0],405)
            self.assertEqual(request('GET','/api/missing')[0],404)
            self.assertEqual(request('POST',body={'text':''})[0],422)
            self.assertEqual(request('PUT',body={**created['ok'],'text':'updated','complete':True})[1]['ok'][0]['text'],'updated')
            self.assertEqual(request('POST','/api/fail',False)[0],422)
            self.assertEqual(request('POST','/api/fail',True)[0],500)
            self.assertEqual(request('GET','/api/probe')[1]['error']['code'],'NOT_FOUND')
            self.assertEqual(request('DELETE',body={'id':'1'})[1],{'ok': []})
        finally:
            process.send_signal(signal.SIGTERM)
            output, errors=process.communicate(timeout=15)
            self.assertEqual(process.returncode,0,output+errors)
            self.assertNotIn('E_INTERNAL_LEAK',errors)


if __name__ == '__main__':
    unittest.main(verbosity=2)
