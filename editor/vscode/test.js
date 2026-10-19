'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const {prepareSession} = require('./session');
const {createIntegration} = require('./extension');

function descriptor() {
  return {schema: 'nex.debug-session/1', ok: true, adapter: 'nex-dap', revision: 'frozen-revision', build_key: 'frozen-build',
    nex_adapter: {schema: 'nex.dap-adapter/1', available: true}, manifest: '/frozen debug/debug.json',
    adapter_command: ['python3', '/sdk with spaces/debugger/nex_dap.py', '--backend', '/llvm/bin/lldb-dap'],
    launch: {type: 'nex', request: 'launch', program: '/frozen source/app', cwd: '/project with spaces',
      initCommands: ['command script import "captured formatter.py"'], sourceMap: [['/frozen', '/original']], args: ['--nex-grant', 'exact-manifest']}};
}
const configuration = {type: 'nex', request: 'launch', name: 'Observe NEX', source: 'main $(literal).nex', cwd: '/project with spaces'};
const emptyManifest = async () => JSON.stringify({schema: 'nex.debug/1', revision: 'frozen-revision', build_key: 'frozen-build', sources: []});

test('fresh compiler preparation preserves the frozen launch and argument boundaries', async () => {
  let observed;
  const original = descriptor();
  const prepared = await prepareSession({...configuration, args: ['a b', '$(literal)'], stopOnEntry: true}, {
    compiler: '/sdk with spaces/bin/nex', readFile: emptyManifest, execute: async (...args) => { observed = args; return {stdout: JSON.stringify(original)}; }
  });
  assert.equal(observed[0], '/sdk with spaces/bin/nex');
  assert.deepEqual(observed[1], ['debug', path.resolve(configuration.cwd, configuration.source), '--kind', 'nex-dap', '--json']);
  assert.equal(observed[2].shell, false);
  assert.equal(observed[2].cwd, configuration.cwd);
  assert.deepEqual(prepared.command, original.adapter_command);
  assert.equal(prepared.launch.program, original.launch.program);
  assert.deepEqual(prepared.launch.initCommands, original.launch.initCommands);
  assert.deepEqual(prepared.launch.sourceMap, original.launch.sourceMap);
  assert.deepEqual(prepared.launch.args, ['--nex-grant', 'exact-manifest', 'a b', '$(literal)']);
  assert.equal(prepared.launch.stopOnEntry, true);
  assert.equal(prepared.revision, 'frozen-revision');
});

test('malformed source launches fail before invoking any executable', async () => {
  let calls = 0;
  const execute = async () => { calls++; throw new Error('must not run'); };
  for (const change of [{request: 'attach'}, {type: 'other'}, {source: '/a.json'}, {source: ''}, {cwd: 'bad\0path'}, {args: ['x\0y']}, {args: {}}, {stopOnEntry: 'false'}]) {
    await assert.rejects(prepareSession({...configuration, ...change}, {execute}));
  }
  await assert.rejects(prepareSession(configuration, {execute, compiler: ''}));
  assert.equal(calls, 0);
});

test('compiler failures surface structured diagnostics without a launch', async () => {
  await assert.rejects(prepareSession(configuration, {execute: async () => {
    throw Object.assign(new Error('exit 1'), {stdout: JSON.stringify({code: 'E_TYPE', message: 'expected i64'})});
  }}), /E_TYPE: expected i64/);
});

test('mismatched or unavailable compiler responses cannot supply an adapter', async () => {
  for (const mutate of [d => { d.schema = 'other'; }, d => { d.ok = false; }, d => { d.nex_adapter.available = false; },
    d => { d.adapter_command = ['']; }, d => { d.adapter_command = ['python3', 'x\0y']; },
    d => { d.launch.program = 'relative'; }, d => { d.launch.initCommands = 'not an array'; }, d => { d.launch.args = [1]; }]) {
    const response = descriptor(); mutate(response);
    await assert.rejects(prepareSession(configuration, {execute: async () => ({stdout: JSON.stringify(response)})}));
  }
  await assert.rejects(prepareSession(configuration, {execute: async () => ({stdout: 'not JSON'})}), /invalid debug-session/);
});

function host() {
  const errors = [];
  return {errors, workspace: {isTrusted: true, getConfiguration: () => ({get: () => '/configured/nex'})},
    window: {showErrorMessage: async message => errors.push(message)},
    DebugAdapterExecutable: class {constructor(command, args, options) {Object.assign(this, {command, args, options});}}};
}

test('restricted and virtual workspaces do not compile or launch', async () => {
  const vscode = host(); let calls = 0;
  const integration = createIntegration(vscode, async () => { calls++; });
  vscode.workspace.isTrusted = false;
  assert.equal(await integration.provider.resolveDebugConfigurationWithSubstitutedVariables(undefined, configuration), undefined);
  assert.throws(() => integration.factory.createDebugAdapterDescriptor({configuration: {_nexSession: 'forged'}}), /trust/);
  vscode.workspace.isTrusted = true;
  assert.equal(await integration.provider.resolveDebugConfigurationWithSubstitutedVariables({uri: {scheme: 'virtual'}}, configuration), undefined);
  assert.equal(calls, 0);
});

test('each registered launch consumes only its own freshly prepared command', async () => {
  const vscode = host();
  const prepared = {launch: descriptor().launch, command: descriptor().adapter_command};
  let options;
  const integration = createIntegration(vscode, async (_, value) => {options = value; return prepared;});
  const folder = {uri: {scheme: 'file', fsPath: '/workspace'}};
  const first = await integration.provider.resolveDebugConfigurationWithSubstitutedVariables(folder, configuration);
  const second = await integration.provider.resolveDebugConfigurationWithSubstitutedVariables(folder, configuration);
  assert.notEqual(first._nexSession, second._nexSession);
  assert.deepEqual(options, {folder: '/workspace', compiler: '/configured/nex'});
  const selected = integration.factory.createDebugAdapterDescriptor({configuration: second});
  assert.equal(selected.command, prepared.command[0]); assert.deepEqual(selected.args, prepared.command.slice(1));
  assert.equal(selected.options.cwd, prepared.launch.cwd);
  assert.throws(() => integration.factory.createDebugAdapterDescriptor({configuration: second}), /fresh NEX launch/);
  assert.throws(() => integration.factory.createDebugAdapterDescriptor({configuration: {_nexSession: 'forged'}}), /fresh NEX launch/);
  integration.dispose();
  assert.throws(() => integration.factory.createDebugAdapterDescriptor({configuration: first}), /fresh NEX launch/);
});

test('trust changes during compiler preparation prevent launch registration', async () => {
  const vscode = host();
  const integration = createIntegration(vscode, async () => {vscode.workspace.isTrusted = false; return {launch: descriptor().launch, command: descriptor().adapter_command};});
  assert.equal(await integration.provider.resolveDebugConfigurationWithSubstitutedVariables(undefined, configuration), undefined);
  assert.match(vscode.errors[0], /trust changed/);
});

test('original breakpoint files map only when they match the exact frozen source bytes', async () => {
  const response = descriptor(), original = '/project with spaces/library.nex', frozen = '/frozen/library/source.nex';
  const manifest = {schema: 'nex.debug/1', revision: response.revision, build_key: response.build_key,
    sources: [{original, projection: frozen, debug_path: '/anchor/source.nex'}]};
  const files = new Map([[response.manifest, JSON.stringify(manifest)], [original, Buffer.from('exact source 🧠')], [frozen, Buffer.from('exact source 🧠')]]);
  const options = {execute: async () => ({stdout: JSON.stringify(response)}), readFile: async name => files.get(name)};
  const matched = await prepareSession(configuration, options);
  assert.deepEqual(matched.launch.sourceMap, [['/anchor/source.nex', original], ...response.launch.sourceMap]);
  files.set(original, Buffer.from('changed source'));
  const changed = await prepareSession(configuration, options);
  assert.deepEqual(changed.launch.sourceMap, response.launch.sourceMap);
  assert.deepEqual(changed.frozenSourceFallbacks, [original]);
  await assert.rejects(prepareSession({...configuration, source: original}, options), /changed after compilation/);
  manifest.build_key = 'another build';files.set(response.manifest, JSON.stringify(manifest));
  await assert.rejects(prepareSession(configuration, options), /manifest differs/);
});

test('failed preparation resolves without waiting for notification dismissal', async () => {
  const vscode = host();vscode.window.showErrorMessage = () => new Promise(() => {});
  const integration = createIntegration(vscode, async () => {throw new Error('compile diagnostic');});
  assert.equal(await integration.provider.resolveDebugConfigurationWithSubstitutedVariables(undefined, configuration), undefined);
});

test('physical entry aliases retain editor breakpoints and reject a retargeted symlink', async () => {
  const fs = require('node:fs/promises'), os = require('node:os');
  const root = await fs.mkdtemp(path.join(os.tmpdir(), 'nex-editor-alias-'));
  try {
    const original = path.join(root, 'physical.nex'), selected = path.join(root, 'selected.nex');
    const changed = path.join(root, 'changed.nex'), projection = path.join(root, 'frozen.nex');
    await fs.writeFile(original, 'exact source 🧠');await fs.writeFile(projection, 'exact source 🧠');
    await fs.writeFile(changed, 'different source');await fs.symlink(original, selected);
    const response = descriptor();response.manifest = path.join(root, 'manifest.json');
    await fs.writeFile(response.manifest, JSON.stringify({schema: 'nex.debug/1', revision: response.revision,
      build_key: response.build_key, sources: [{original: await fs.realpath(original), projection, debug_path: '/anchor/entry.nex'}]}));
    const config = {...configuration, source: selected};
    const prepared = await prepareSession(config, {execute: async () => ({stdout: JSON.stringify(response)})});
    assert.deepEqual(prepared.originalSourceMappings, [['/anchor/entry.nex', selected]]);
    await assert.rejects(prepareSession(config, {execute: async () => {
      await fs.unlink(selected);await fs.symlink(changed, selected);
      return {stdout: JSON.stringify(response)};
    }}), /selected source changed after compilation/);
  } finally {await fs.rm(root, {recursive: true, force: true});}
});
