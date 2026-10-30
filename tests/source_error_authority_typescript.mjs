import * as nex from './nex-runtime.ts';
import * as task from './nex-task-runtime.ts';
import * as source from './nex-source-exception-runtime.ts';

const site = ['authority.nex', 9, 3, 'origin'];
const channelKey = 'a'.repeat(64), scopeKey = 'b'.repeat(64), functionKey = 'c'.repeat(64), scalarKey = 'd'.repeat(64);
const contracts = source.checkedTransferContracts([
  {key: channelKey, kind: 'channel', nominal: ''}, {key: scopeKey, kind: 'task_scope', nominal: ''},
  {key: functionKey, kind: 'function', nominal: ''}, {key: scalarKey, kind: 'i64', nominal: ''},
]);
let cases = 0;
const require = (value, message) => { if (!value) throw Error(message); ++cases; };
const caught = action => { try { action(); } catch (error) { return error; } throw Error('expected failure'); };
const trap = (action, code = 'E_SOURCE_TYPE') => { const error = caught(action); require(error instanceof nex.NexError && error.code === code && !source.details(error), 'wrong fatal outcome'); };
const callback = (captures, factory) => nex.captured(captures, (...args) => task.call(() => factory(...args)));
const run = (factory, known = contracts, options = {}) => task.runTypedSourceErrors(task.call(factory), known, options);
const request = (operation, args) => task.request(operation, args, site);
async function rejects(factory, code, known = contracts) {
  let error, statistics;
  try { await run(factory, known, {complete: value => { statistics = value; }}); } catch (failure) { error = failure; }
  require(error instanceof nex.NexError && error.code === code && source.details(error) === undefined, 'unexpected task failure: ' + error);
  require(statistics?.completed && !statistics.activeCalls && !statistics.retainedFrames && !statistics.externalPending, 'task state retained');
}

require(Object.isFrozen(contracts) && contracts.every(Object.isFrozen), 'contracts are mutable');
const original = [{key: scalarKey, kind: 'i64', nominal: ''}];
const copied = source.checkedTransferContracts(original); original[0].key = channelKey;
require(copied[0].key === scalarKey, 'contracts retain mutable host objects');
for (const invalid of [null, {}, new Array(4097), [{key:'invalid',kind:'i64',nominal:''}], [{key:scalarKey,kind:'unknown',nominal:''}], [{key:scalarKey,kind:'i64',nominal:'hidden'}], [{key:scalarKey,kind:'i64',nominal:''},{key:scalarKey,kind:'str',nominal:''}]]) trap(() => source.checkedTransferContracts(invalid));
let getter = false;
const property = Object.defineProperty({}, 'key', {get(){ getter=true; throw Error('getter'); }});
trap(() => source.checkedTransferContracts([property])); require(!getter, 'contract getter executed');
const element = []; Object.defineProperty(element, '0', {get(){ getter=true; throw Error('element getter'); }});
trap(() => source.checkedTransferContracts(element)); require(!getter, 'element getter executed');

for (const kind of ['task_scope','task','channel']) trap(() => source.raiseTyped(channelKey, kind, nex.record('nex.private.'+kind, []), kind, '', site));
trap(() => source.raiseTyped(functionKey, 'callback', () => 42n, 'function', '', site));

let legacyFailure;
try { await task.runSourceErrors(task.call(function*(){ task.enterTyped(site); try { return 42n; } finally { task.leave(); } }), error => source.details(error) !== undefined); }
catch (error) { legacyFailure = error; }
require(legacyFailure?.code === 'E_TASK_STATE', 'new generators accepted an unvalidated legacy driver');
require(await run(function*(){ task.enterTyped(site); try { return 42n; } finally { task.leave(); } }) === 42n, 'checked driver rejected its generator');

const local = callback([], function*(scope) {
  const q = yield request('channel_new', [scope, 1n]);
  for (const [key, kind, value] of [[scopeKey, 'task_scope', scope], [channelKey, 'channel', q]]) {
    const error = caught(() => source.raiseTyped(key, kind, value, kind, '', site));
    const detail = source.details(error);
    require(source.readTyped(detail, key, kind, '', site) === value, 'capability identity changed');
    require(Object.keys(detail).sort().join(',') === 'code,message,site' && !JSON.stringify(error).includes('nex.private'), 'authority entered public metadata');
  }
  yield request('task_send', [q, 42n]); return nex.unwrap(yield request('task_recv', [q]));
});
require(await run(function*(){ return yield request('with_tasks', [1n, local]); }) === 42n, 'local source binding changed capability');

await rejects(function*(){ return yield request('with_tasks', [1n, callback([], function*(scope) {
  const q = yield request('channel_new', [scope, 1n]); source.raiseTyped(channelKey, 'channel', q, 'channel', '', site);
})]); }, 'E_TASK_SCOPE');
await rejects(function*(){ return yield request('with_tasks', [1n, callback([], function*(scope) {
  source.raiseTyped(scopeKey, 'scope', scope, 'task_scope', '', site);
})]); }, 'E_TASK_SCOPE');
await rejects(function*(){ return yield request('with_tasks', [1n, callback([], function*(scope) {
  const q = yield request('channel_new', [scope, 1n]);
  const closure = callback([q], function*(){ return yield request('task_close', [q]); });
  source.raiseTyped(functionKey, 'closure', closure, 'function', '', site);
})]); }, 'E_TASK_SCOPE');
await rejects(function*(){ return yield request('with_tasks', [1n, callback([], function*(scope) {
  const q = yield request('channel_new', [scope, 1n]);
  yield request('task_spawn', [scope, callback([q], function*(){ yield request('task_yield', []); source.raiseTyped(channelKey, 'channel', q, 'channel', '', site); })]);
  return 0n;
})]); }, 'E_TASK_SCOPE');

// An implicit inner close may forward an ancestor capability after its failed
// child finishes. Validate before clearing the child's canonical identities.
require(await run(function*(){ return yield request('with_tasks', [1n, callback([], function*(outer) {
  const q = yield request('channel_new', [outer, 1n]);
  try { yield request('with_tasks', [1n, callback([q], function*(inner) {
    yield request('task_spawn', [inner, callback([q], function*(){ source.raiseTyped(channelKey, 'channel', q, 'channel', '', site); })]); return 0n;
  })]); } catch (error) {
    const detail = source.details(error); if (!detail) throw error;
    const retained = source.readTyped(detail, channelKey, 'channel', '', site);
    require(retained === q, 'implicit source transfer changed identity');
    yield request('task_send', [retained, 42n]); return nex.unwrap(yield request('task_recv', [q]));
  }
  return 0n;
})]); }) === 42n, 'ancestor source transfer failed');

await rejects(function*(){ source.raiseTyped(scalarKey, 'scalar', 42n, 'i64', '', site); }, 'E_SOURCE_TYPE', []);
await rejects(function*(){ source.raiseTyped(scalarKey, 'scalar', 42n, 'i64', '', site); }, 'E_SOURCE_TYPE', [{key:scalarKey,kind:'str',nominal:''}]);
let sourceFailure;
try { await run(function*(){ source.raiseTyped(scalarKey, 'scalar', 42n, 'i64', '', site); }); } catch (error) { sourceFailure = error; }
require(source.readTyped(source.details(sourceFailure), scalarKey, 'i64', '', site) === 42n, 'known scalar was not forwarded');
let legacySource;
try { await run(function*(){ source.raise('LEGACY', 'value', site); }, []); } catch (error) { legacySource = error; }
require(source.details(legacySource)?.code === 'LEGACY', 'legacy source outcome changed');
process.stdout.write(JSON.stringify({ok:true,cases,unknown_keys_rejected:true,private_payload_metadata:true,scope_guards:true})+'\n');
