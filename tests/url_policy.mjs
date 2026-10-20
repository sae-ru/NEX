import assert from 'node:assert/strict';
import {pathToFileURL} from 'node:url';
const {safeViewURL, sameApplicationOrigin} = await import(pathToFileURL(process.argv[2]));
const mobile = new URL('capacitor://localhost/start');
const web = new URL('https://example.test/start');
for (const value of ['/', '/active?filter=a#end', './item', '../item', '?a=1', '#end', 'assets/main.png', '']) {
  assert.equal(safeViewURL(value, 'href', mobile), value);
  assert.equal(safeViewURL(value, 'src', mobile), value);
  assert.equal(safeViewURL(value, 'href', web), value);
}
for (const base of [mobile, web, new URL('file:///tmp/index.html'), new URL('capacitor://evil/index'),
                    new URL('capacitor://user@localhost/'), new URL('capacitor://localhost:8080/')]) {
  for (const value of ['javascript:alert(1)', 'data:text/html,a', 'file:///tmp/private', 'blob:https://example.test/id',
                       'capacitor://localhost/active', 'capacitor://evil/active', ' \n/active', '/ac\tive']) {
    assert.throws(() => safeViewURL(value, 'href', base), e => e.code === 'E_UI');
  }
}
for (const value of ['//localhost/active', '//evil/active', '\\active'])
  assert.throws(() => safeViewURL(value, 'href', mobile), e => e.code === 'E_UI');
for (const value of ['/', './item', 'asset.png']) {
  assert.throws(() => safeViewURL(value, 'href', new URL('file:///private/index.html')), e => e.code === 'E_UI');
  assert.throws(() => safeViewURL(value, 'href', new URL('capacitor://evil/')), e => e.code === 'E_UI');
}
for (const value of ['https://example.test/path', 'http://example.test/path', 'mailto:a@example.test', 'tel:123'])
  assert.equal(safeViewURL(value, 'href', mobile), value);
assert.throws(() => safeViewURL('mailto:a@example.test', 'src', mobile), e => e.code === 'E_UI');
assert(sameApplicationOrigin(new URL('/active', mobile), mobile));
assert(sameApplicationOrigin(new URL('/active', web), web));
for (const value of ['capacitor://evil/', 'file:///private', 'mailto:a@example.test', 'data:text/html,x',
                     'https://localhost/', 'capacitor://localhost:8080/', 'capacitor://a@localhost/'])
  assert.equal(sameApplicationOrigin(new URL(value), mobile), false, value);
assert.equal(sameApplicationOrigin(new URL('file:///a'), new URL('file:///b')), false);
console.log('URL policy passed: relative local mobile routes/assets; HTTP behavior; opaque-origin isolation; rejected schemes/authorities');
const {RequestRunner} = await import(new URL('../web/net.ts', import.meta.url));
let fetches = 0;
const request = {kind:'request',id:'one',method:'GET',path:'/api/tasks',body:'',token:'',action:'response',timeout_ms:1000n};
for (const base of ['capacitor://localhost/', 'file:///tmp/app.html', 'data:text/plain,x']) {
  const runner = new RequestRunner(() => assert.fail('unexpected delivery'), base, async () => {fetches++;throw Error('unexpected fetch');});
  runner.run([]);
  assert.throws(() => runner.run([request]), error => error.code === 'E_REQUEST');
}
assert.equal(fetches,0);
console.log('Network policy passed: offline origins cannot send API requests');
