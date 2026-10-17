"""Endpoint semantics, graph transactions, generated SDKs, OpenAPI and live routing."""
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
    def example(self):
        for name in ('service.nex', 'model.nex'):
            shutil.copyfile(harness.REPO / 'examples/api' / name, self.root / name)
        self.file = self.root / 'service.nex'
        return self.file

    def simple(self):
        return 'module routes; import "std/api.nex" as api; pub struct Row { id: i64; } server fn handle(context: api::Context, input: Row) -> result<Row> { return ok(input); } endpoint create("POST", "/api/rows", 201) = handle;'

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
        (self.root/'nex.json').write_text(json.dumps({'entry':'service.nex','language':'0.9','libraries':{'std':'standard'}}))
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
        (self.root/'nex.json').write_text(json.dumps({'entry':'service.nex','language':'0.9','libraries':{'std':'standard','helpers':'helpers'}}))
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
