import assert from 'node:assert/strict';
import { RequestRunner, apiOrigin, configuredAPIOrigin } from './net.ts';
import type { Command } from './program.ts';
import { makeResponseEvent } from './program.ts';
import { record } from './nex-runtime.ts';

function command(id: string, changes: Partial<Command> = {}): Command {
  return record<Command>('std::net::Command', Object.entries({ kind: 'request', id, method: 'GET', path: '/api/test', body: '', token: 'runtime-secret', action: 'response', timeout_ms: 1000n, ...changes }));
}
const pause = () => new Promise(resolve => setTimeout(resolve, 0));
async function until(predicate: () => boolean): Promise<void> {
  for (let i = 0; i < 200 && !predicate(); ++i) await pause();
  assert.ok(predicate(), 'asynchronous event was not delivered');
}
type Received = { id: string; status: string; body: { ok?: string; error?: { code: string; message: string } } };
let received: Received[] = [], calls: RequestInit[] = [];
const deliver = (action: string, id: string, status: number, body: string, code: string, message: string) => {
  received.push(JSON.parse(makeResponseEvent(action, id, status, body, code, message, '/').value));
};
let runner = new RequestRunner(deliver, 'https://app.test/', async (_url, options) => {
  calls.push(options!); return new Response('{"id":"9007199254740993"}', { status: 201 });
});
runner.run([command('success', { method: 'POST', body: '{"text":"🦊"}' })]);
await until(() => received.length === 1);
assert.equal(received[0].status, '201'); assert.equal(received[0].body.ok, '{"id":"9007199254740993"}');
assert.equal((calls[0].headers as Record<string, string>).Authorization, 'Bearer runtime-secret');
assert.equal(calls[0].credentials, 'omit'); assert.equal(calls[0].redirect, 'error'); assert.equal(calls[0].mode, 'same-origin');
assert.equal(calls[0].cache, 'no-store');
for (const change of [
  { path: 'https://other.test/api/tasks' }, { path: '//other.test/api/tasks' }, { path: '/api/../private' },
  { path: '/api/\\other' }, { path: '/api/test#fragment' }, { path: '/api/test\n' },
  { token: 'secret\nInjected: header' }, { token: 'secret\n' }, { timeout_ms: 0n }, { method: 'TRACE' }, { body: 'x' },
  { action: '' }, { body: '\ud800' }, { method: 'POST', body: 'x'.repeat(1048577) },
]) {
  assert.throws(() => runner.run([command('valid-first'), command('invalid-second', change)]), error => ['E_REQUEST', 'E_UTF8'].includes(error.code));
  assert.equal(calls.length, 1, 'invalid batch partially dispatched');
}
runner.close();

async function outcome(fetcher: typeof fetch, change: Partial<Command> = {}): Promise<Received> {
  received = [];
  runner = new RequestRunner(deliver, 'https://app.test/', fetcher);
  runner.run([command('case', change)]);
  await until(() => received.length === 1);
  runner.close(); return received[0];
}
assert.equal((await outcome(async () => new Response('denied', { status: 401 }))).status, '401');
assert.equal((await outcome(async () => { throw new Error('do not leak runtime-secret'); })).body.error?.code, 'E_NETWORK');
assert.equal((await outcome(async () => new Response(new Uint8Array([0xc0, 0x80])))).body.error?.code, 'E_UTF8');
assert.equal((await outcome(async () => new Response(new Uint8Array([0xf0, 0x9f])))).body.error?.code, 'E_UTF8');
assert.equal((await outcome(async () => new Response('x', { headers: { 'Content-Length': '1048577' } }))).body.error?.code, 'E_LIMIT');
assert.equal((await outcome(async () => new Response('x'.repeat(1048577)))).body.error?.code, 'E_LIMIT');
assert.equal((await outcome(async () => new Response('"'.repeat(600000)))).body.error?.code, 'E_LIMIT');
assert.equal((await outcome(async () => new Response(new ReadableStream({
  start(controller) { controller.enqueue(new Uint8Array([0xf0, 0x9f])); controller.enqueue(new Uint8Array([0xa6, 0x8a])); controller.close(); },
})))).body.ok, '🦊');

const schema = { schema: 'nex.wire/1', root: { result: { record: 'model::Row' } }, records: { 'model::Row': [{ name: 'id', type: 'i64' }] } };
const typed = { kind: 'typed_request', body: JSON.stringify({ body: '', schema: JSON.stringify(schema) }) };
assert.equal((await outcome(async () => new Response('{"ok":{"id":"9007199254740993"}}'), typed)).body.ok, '{"ok":{"id":"9007199254740993"}}');
for (const body of ['{"ok":{"id":1}}', '{"ok":{"id":"1","extra":true}}', '{"ok":{"id":"1","id":"2"}}', '{"ok":{"id":"9223372036854775808"}}']) {
  const response = await outcome(async () => new Response(body), typed);
  assert.equal(response.body.error?.code, 'E_JSON');
  assert.equal(response.body.ok, undefined, 'invalid endpoint data reached the application event');
}
let sent;
await outcome(async (_url, options) => { sent = options.body; return new Response('{"ok":{"id":"1"}}'); },
              { ...typed, method: 'POST', body: JSON.stringify({ body: '{"text":"🦊"}', schema: JSON.stringify(schema) }) });
assert.equal(sent, '{"text":"🦊"}', 'compiler schema leaked into the HTTP request body');
runner = new RequestRunner(deliver, 'https://app.test/', async () => { assert.fail('invalid schema caused a request'); });
assert.throws(() => runner.run([command('bad-schema', { kind: 'typed_request', body: JSON.stringify({body:'',schema:'{"schema":"nex.wire/1","root":{"record":"missing"},"records":{}}'}) })]), error => error.code === 'E_REQUEST');
runner.close();

const enumSchema = { schema: 'nex.wire/2', root: { result: { enum: 'model::Event' } }, records: {}, enums: {
  'model::Event': [{name:'Reset',fields:[]},{name:'Set',fields:[{name:'value',type:'i64'}]}],
}};
const enumTyped = { kind: 'typed_request', body: JSON.stringify({body:'',schema:JSON.stringify(enumSchema)}) };
assert.equal((await outcome(async () => new Response('{"ok":{"case":"Set","fields":{"value":"42"}}}'), enumTyped)).body.ok,
             '{"ok":{"case":"Set","fields":{"value":"42"}}}');
for (const body of ['{"ok":{"case":"Other","fields":{}}}', '{"ok":{"case":"Set","fields":{"value":42}}}',
                    '{"ok":{"case":"Reset","fields":{"extra":true}}}', '{"ok":{"case":"Reset","fields":{},"extra":true}}']) {
  const response=await outcome(async () => new Response(body),enumTyped);
  assert.equal(response.body.error?.code,'E_JSON'); assert.equal(response.body.ok,undefined);
}

const hanging: typeof fetch = async (_url, options) => new Promise((_resolve, reject) => {
  options!.signal!.addEventListener('abort', () => reject(new Error('aborted')), { once: true });
});
assert.equal((await outcome(hanging, { timeout_ms: 5n })).body.error?.code, 'E_TIMEOUT');
received = [];
runner = new RequestRunner(deliver, 'https://app.test/', hanging);
runner.run([command('cancel')]);
assert.throws(() => runner.run([command('cancel')]), error => error.code === 'E_REQUEST');
runner.run([command('cancel', { kind: 'cancel' })]);
await until(() => received.length === 1);
assert.equal(received[0].body.error?.code, 'E_CANCELED');
runner.run([command('one'), command('two')]);
runner.run([command('', { kind: 'cancel_all' })]);
await until(() => received.length === 3);
runner.run([command('unmount')]); runner.close();
await pause(); assert.equal(received.length, 3, 'unmounted application received a stale event');
received = [];
runner = new RequestRunner(deliver, 'https://app.test/', hanging);
runner.run(Array.from({ length: 32 }, (_, i) => command(String(i))));
assert.throws(() => runner.run([command('overflow')]), error => error.code === 'E_REQUEST');
runner.close();
console.log('Request transport boundaries, codecs, limits, cancellation and timeout passed');

// Trusted deployment selects the destination once; commands cannot override it.
for (const value of ['https://api.example.test', 'https://127.0.0.1:9443', 'https://localhost:9443'])
  assert.equal(apiOrigin(value), value);
for (const value of ['', 'http://api.test', 'https://user:pass@api.test', 'https://api.test/',
  'https://api.test/api', 'https://api.test?x', 'https://api.test#x', 'https://API.test',
  'https://api.test:0', 'https://api.test:443', 'https://api.test:65536', 'https://api.test:0443',
  'https://127.1', 'https://0x7f000001', 'https://api..test', 'https://-api.test', 'https://api.test\n',
  'capacitor://localhost', '//api.test', 'https://[::1]:9443']) {
  assert.throws(() => apiOrigin(value), error => error.code === 'E_REQUEST', value);
}
const meta = (values: string[]) => ({querySelectorAll: () => values.map(value => ({getAttribute: () => value}))}) as unknown as Pick<Document, 'querySelectorAll'>;
assert.equal(configuredAPIOrigin(meta([])), undefined);
assert.equal(configuredAPIOrigin(meta(['https://api.test'])), 'https://api.test');
assert.throws(() => configuredAPIOrigin(meta(['https://a.test','https://b.test'])), error => error.code === 'E_REQUEST');
assert.throws(() => configuredAPIOrigin(meta(['http://a.test'])), error => error.code === 'E_REQUEST');
for (const origin of ['capacitor://localhost/', 'https://localhost/']) {
  received = []; let destinations: string[] = []; calls = [];
  const remote = new RequestRunner(deliver, origin, async (url, options) => {
    destinations.push(String(url)); calls.push(options!); return new Response('Я🧠', {status:201});
  }, 'https://api.test:9443');
  remote.run([command('remote', {path:'/api/tasks?limit=3',method:'POST',body:'Я🧠'})]);
  await until(() => received.length === 1);
  assert.equal(destinations[0], 'https://api.test:9443/api/tasks?limit=3');
  assert.equal(received[0].body.ok, 'Я🧠');
  assert.equal(calls[0].mode, 'cors'); assert.equal(calls[0].credentials, 'omit'); assert.equal(calls[0].redirect, 'error');
  for (const path of ['https://other.test/api/x','//other.test/api/x','/api/../private','/api/x#fragment','/api/\\evil']) {
    assert.throws(() => remote.run([command('valid'),command('bad',{path})]), error => error.code === 'E_REQUEST');
    assert.equal(destinations.length,1);
  }
  remote.close();
}
console.log('Explicit HTTPS host configuration and mobile cross-origin request boundaries passed');
