'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const {prepareSession} = require('./session');
const {createIntegration} = require('./extension');
const {createProjectDebugCommand} = require('./project-command');

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
  assert.equal(prepared.launch.sourceMap, undefined);
  assert.deepEqual(prepared.launch.preRunCommands, ['settings set target.source-map "/frozen" "/original"']);
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
  assert.equal(matched.launch.sourceMap, undefined);
  assert.deepEqual(matched.launch.preRunCommands, ['settings set target.source-map "/anchor/source.nex" "/project with spaces/library.nex" "/frozen" "/original"']);
  files.set(original, Buffer.from('changed source'));
  const changed = await prepareSession(configuration, options);
  assert.deepEqual(changed.launch.preRunCommands, ['settings set target.source-map "/frozen" "/original"']);
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

test('compiler pre-run commands survive source-map configuration and malformed maps are rejected', async () => {
  const response = descriptor();response.launch.preRunCommands = ['settings set target.disable-aslr false'];
  const options = {readFile: emptyManifest, execute: async () => ({stdout: JSON.stringify(response)})};
  const prepared = await prepareSession({...configuration, preRunCommands: ['untrusted command'], sourceMap: [['ignored', 'user map']]}, options);
  assert.deepEqual(prepared.launch.preRunCommands, ['settings set target.source-map "/frozen" "/original"', 'settings set target.disable-aslr false']);
  for (const value of ['bad', [null], [['a']], [['a', 'b\0c']], [['a', 4]]]) {
    response.launch.sourceMap = value;
    await assert.rejects(prepareSession(configuration, options), /invalid frozen source maps/);
  }
  response.launch.sourceMap = [];
  for (const value of ['bad', [null], ['bad\0command']]) {
    response.launch.preRunCommands = value;
    await assert.rejects(prepareSession(configuration, options), /invalid pre-run commands/);
  }
});

function projectFixture() {
  const root = '/project with spaces', source = root + '/app/main.nex', projection = '/frozen app/source.nex';
  const selection = {manifest: 'architecture $(literal).json', component: 'app', configuration: 'debug'};
  const config = {type: 'nex', request: 'launch', cwd: root, project: selection, args: ['two words', '$(literal)']};
  const plan = {schema: 'nex.project-plan/1', ok: true, source_checked: true, graph_store_opened: false, external_tools_invoked: false,
    root, manifest: path.join(root, selection.manifest), selected_component: 'app', configuration: {name: 'debug'},
    plan_hash: 'a'.repeat(64), architecture_hash: 'b'.repeat(64),
    components: [{name: 'core', kind: 'shared_library', entry: 'core/value.nex'}, {name: 'app', kind: 'executable', entry: 'app/main.nex', native_toolchain: {host_compatible: true}}]};
  const observation = descriptor();observation.launch.cwd = root;
  const response = {schema: 'nex.project-session/1', ok: true, action: 'debug', component: 'app', graph_store_opened: false,
    plan_hash: plan.plan_hash, plan, observation,
    artifacts: [{component: 'app', kind: 'executable', host_compatible: true, artifact: observation.launch.program, build_key: observation.build_key}]};
  const files = new Map([[observation.manifest, JSON.stringify({schema: 'nex.debug/1', revision: observation.revision, build_key: observation.build_key,
    sources: [{original: source, projection, debug_path: '/anchor/app.nex'}]})], [source, Buffer.from('exact app 🧠')], [projection, Buffer.from('exact app 🧠')]]);
  const calls = [];
  const options = {compiler: '/sdk with spaces/bin/nex', realpath: async name => name, readFile: async name => files.get(name),
    execute: async (compiler, args, processOptions) => {calls.push({compiler, args, processOptions});return {stdout: JSON.stringify(args[args.indexOf('--kind') + 1] === 'debug' ? response : plan)};}};
  return {root, source, config, plan, response, files, calls, options};
}

test('project launch uses only its actual architecture session and checks plans around compilation', async () => {
  const f = projectFixture();
  const result = await prepareSession(f.config, f.options);
  assert.deepEqual(f.calls.map(c => c.args[c.args.indexOf('--kind') + 1]), ['plan', 'debug', 'plan']);
  for (const call of f.calls) {
    assert.equal(call.compiler, f.options.compiler);assert.equal(call.processOptions.shell, false);assert.equal(call.processOptions.cwd, f.root);
    assert.deepEqual(call.args.slice(0, 2), ['project', path.join(f.root, f.config.project.manifest)]);
    assert.deepEqual(call.args.slice(4, 8), ['--component', 'app', '--configuration', 'debug']);
    assert.equal(call.args.includes('--revision'), false);
  }
  assert.deepEqual(f.calls[1].args.slice(-3), ['--adapter', 'nex-dap', '--json']);
  assert.deepEqual(result.command, f.response.observation.adapter_command);
  assert.equal(result.launch.program, f.response.artifacts[0].artifact);
  assert.equal(result.project.architectureHash, f.plan.architecture_hash);
  assert.equal(result.project.planHash, f.plan.plan_hash);
  assert.deepEqual(result.launch.args, ['--nex-grant', 'exact-manifest', 'two words', '$(literal)']);
  assert.ok(result.originalSourceMappings.some(row => row[1] === f.source));
});

test('malformed project selections reject before any compiler call', async () => {
  const f = projectFixture();
  for (const project of [null, [], {}, {...f.config.project, component: 'bad;name'}, {...f.config.project, configuration: ''},
    {...f.config.project, manifest: 'bad\0manifest'}, {...f.config.project, adapter_command: ['untrusted']}]) {
    await assert.rejects(prepareSession({...f.config, project}, f.options));
  }
  await assert.rejects(prepareSession({...f.config, source: 'main.nex'}, f.options), /either/);
  await assert.rejects(prepareSession({...f.config, args: 'shell string'}, f.options));
  assert.equal(f.calls.length, 0);
});

test('non-executable and foreign-host plans do not invoke project debug', async () => {
  for (const kind of ['source', 'static_library', 'shared_library', 'server', 'web']) {
    const f = projectFixture();f.plan.components[1].kind = kind;
    await assert.rejects(prepareSession(f.config, f.options), /native executable/);assert.equal(f.calls.length, 1);
  }
  const f = projectFixture();f.plan.components[1].native_toolchain.host_compatible = false;
  await assert.rejects(prepareSession(f.config, f.options), /matching native host/);assert.equal(f.calls.length, 1);
});

test('a different project artifact, configuration or architecture cannot supply the adapter', async () => {
  for (const mutate of [f => {f.response.schema = 'other';}, f => {f.response.component = 'core';}, f => {f.response.plan_hash = 'c'.repeat(64);},
    f => {f.response.artifacts[0].artifact = '/other/app';}, f => {f.response.artifacts[0].build_key = 'different';},
    f => {f.response.observation.launch.cwd = '/different';}, f => {f.response.graph_store_opened = true;},
    f => {f.response.observation.adapter_command = ['untrusted\0adapter'];}]) {
    const f = projectFixture();mutate(f);await assert.rejects(prepareSession(f.config, f.options));
  }
});

test('source and architecture changes during project preparation require a fresh launch', async () => {
  const f = projectFixture(), original = f.options.execute;
  f.options.execute = async (...args) => {const value = await original(...args);if (f.calls.length === 3) return {stdout: JSON.stringify({...f.plan, plan_hash: 'c'.repeat(64)})};return value;};
  await assert.rejects(prepareSession(f.config, f.options), /changed after compilation/);
  for (const retarget of [false, true]) {
    const f = projectFixture(), execute = f.options.execute;let changed = false;
    f.options.realpath = async name => changed && retarget && name === f.source ? '/other/entry.nex' : name;
    f.options.execute = async (...args) => {const value = await execute(...args);if (f.calls.length === 3) {changed = true;f.files.set(f.source, Buffer.from('changed source'));}return value;};
    await assert.rejects(prepareSession(f.config, f.options), /selected source changed after compilation/);
  }
});

test('retargeted architecture aliases and structured project errors do not register a launch', async () => {
  const f = projectFixture(), execute = f.options.execute;let changed = false;
  f.options.realpath = async name => changed && name === f.plan.manifest ? '/other/architecture.json' : name;
  f.options.execute = async (...args) => {const value = await execute(...args);if (f.calls.length === 2) changed = true;return value;};
  await assert.rejects(prepareSession(f.config, f.options), /manifest or project root changed/);
  const g = projectFixture();g.options.execute = async () => {throw Object.assign(new Error('exit 1'), {stdout: JSON.stringify({code: 'E_PROJECT_BOUNDARY', message: 'undeclared component edge'})});};
  await assert.rejects(prepareSession(g.config, g.options), /E_PROJECT_BOUNDARY: undeclared component edge/);
});

test('project aliases map provider source breakpoints through the editor workspace spelling', async () => {
  const f = projectFixture(), alias = '/workspace alias';f.config.cwd = alias;
  f.options.realpath = async name => name === alias || name.startsWith(alias + '/') ? f.root + name.slice(alias.length) : name;
  const provider = f.root + '/core/value.nex', projection = '/frozen core/source.nex';
  const manifest = JSON.parse(f.files.get(f.response.observation.manifest));manifest.sources.push({original: provider, projection, debug_path: '/anchor/core.nex'});
  f.files.set(f.response.observation.manifest, JSON.stringify(manifest));f.files.set(projection, Buffer.from('core source'));
  f.files.set(alias + '/app/main.nex', f.files.get(f.source));f.files.set(alias + '/core/value.nex', Buffer.from('core source'));
  const result = await prepareSession(f.config, f.options);
  assert.ok(result.originalSourceMappings.some(row => row[1] === alias + '/core/value.nex'));
  assert.ok(result.originalSourceMappings.some(row => row[1] === alias + '/app/main.nex'));
});

test('dirty compiled project documents prevent launch registration without saving buffers', async () => {
  const vscode = host();vscode.workspace.textDocuments = [{isDirty: true, uri: {scheme: 'file', fsPath: '/project/app/main.nex'}}];
  const prepared = {project: {component: 'app'}, launch: descriptor().launch, command: descriptor().adapter_command,
    originalSourceMappings: [['/anchor/main.nex', '/project/app/main.nex']]};
  const integration = createIntegration(vscode, async () => prepared);
  assert.equal(await integration.provider.resolveDebugConfigurationWithSubstitutedVariables(undefined, {}), undefined);
  assert.match(vscode.errors[0], /Save the project sources/);
  vscode.workspace.textDocuments[0].uri.fsPath = '/unrelated/project.nex';
  const selected = await integration.provider.resolveDebugConfigurationWithSubstitutedVariables(undefined, {});
  assert.ok(selected._nexSession);
  integration.dispose();
});

function projectCommandHost() {
  const vscode = host(), launches = [], choices = [];
  vscode.workspace.workspaceFolders = [{name: 'Project', uri: {scheme: 'file', fsPath: '/project with spaces'}}];
  vscode.debug = {startDebugging: async (...args) => {launches.push(args);return true;}};
  vscode.window.showQuickPick = async items => {choices.push(items);return items[0];};
  const metadata = {schema: 'nex.project-build/1', default_configuration: 'release',
    components: {app: {kind: 'executable'}, core: {kind: 'shared_library'}}, configurations: {debug: {profile: 'debug'}, release: {profile: 'release'}}};
  let reads = 0;
  const options = {stat: async () => ({isFile: () => true, size: 100}), readFile: async () => {reads++;return JSON.stringify(metadata);}};
  return {vscode, launches, choices, metadata, options, get reads() {return reads;}};
}

test('project command chooses declared configurations and delegates to the fresh launch provider', async () => {
  const h = projectCommandHost();assert.equal(await createProjectDebugCommand(h.vscode, h.options)(), true);
  assert.equal(h.launches.length, 1);assert.equal(h.choices.length, 1);
  assert.deepEqual(h.launches[0][1].project, {manifest: 'nex.build.json', component: 'app', configuration: 'release'});
  assert.equal(h.launches[0][1].source, undefined);assert.equal(h.launches[0][1].cwd, '/project with spaces');
});

test('project command respects cancellation and trust changes without starting a debug session', async () => {
  let h = projectCommandHost();h.vscode.workspace.isTrusted = false;
  assert.equal(await createProjectDebugCommand(h.vscode, h.options)(), false);assert.equal(h.reads, 0);assert.equal(h.launches.length, 0);
  h = projectCommandHost();h.vscode.window.showQuickPick = async () => undefined;
  assert.equal(await createProjectDebugCommand(h.vscode, h.options)(), false);assert.equal(h.launches.length, 0);
  h = projectCommandHost();h.vscode.window.showQuickPick = async items => {h.vscode.workspace.isTrusted = false;return items[0];};
  assert.equal(await createProjectDebugCommand(h.vscode, h.options)(), false);assert.equal(h.launches.length, 0);
});

test('project command rejects oversized manifests and unavailable components', async () => {
  let h = projectCommandHost();h.options.stat = async () => ({isFile: () => true, size: 262145});
  assert.equal(await createProjectDebugCommand(h.vscode, h.options)(), false);assert.equal(h.reads, 0);
  h = projectCommandHost();h.metadata.components.app.kind = 'server';
  assert.equal(await createProjectDebugCommand(h.vscode, h.options)(), false);assert.equal(h.launches.length, 0);
});
