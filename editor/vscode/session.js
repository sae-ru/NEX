'use strict';

const {execFile} = require('node:child_process');
const path = require('node:path');
const {promisify} = require('node:util');
const fs = require('node:fs/promises');
const execute = promisify(execFile);

function string(value, name) {
  if (typeof value !== 'string' || !value || value.includes('\0')) throw new Error(`Invalid ${name}.`);
  return value;
}
function programArguments(value = []) {
  const scalarText = value => {for (const scalar of value) if (scalar.length === 1 && /[\uD800-\uDFFF]/.test(scalar)) return false;return true;};
  if (!Array.isArray(value) || value.length > 128 || value.some(arg => typeof arg !== 'string' || arg.includes('\0') || !scalarText(arg) || Buffer.byteLength(arg, 'utf8') > 4096) ||
      value.reduce((size, arg) => size + Buffer.byteLength(arg, 'utf8'), 0) > 65536) throw new Error('Program args require at most128 strings,4 KiB each and64 KiB total.');
  return [...value];
}

function lldbArgument(value) {
  // LLDB's command parser accepts quoted newlines and Unicode literally.
  // JSON escapes such as \uXXXX have different meanings to that parser.
  return '"' + value.replace(/\\/g, '\\\\').replace(/"/g, '\\"') + '"';
}

// Only a fresh, successful compiler response can select a frozen executable and
// adapter. No saved manifest or launch.json adapter command authorizes a process.
function launchSettings(configuration, options, sourceRequired) {
  if (configuration.request !== 'launch' || configuration.type !== 'nex') throw new Error('Only a NEX launch request is supported.');
  const base = path.resolve(options.folder || process.cwd());
  const cwd = path.resolve(base, configuration.cwd === undefined ? '.' : string(configuration.cwd, 'project directory'));
  const source = sourceRequired ? path.resolve(cwd, string(configuration.source, 'NEX source')) : undefined;
  if (sourceRequired && path.extname(source) !== '.nex') throw new Error('Select a .nex entry source.');
  const compiler = string(options.compiler === undefined ? 'nex' : options.compiler, 'compiler executable');
  const args = programArguments(configuration.args);
  const target = configuration.target === undefined ? 'native' : configuration.target;
  if (!['native', 'server'].includes(target)) throw new Error('Source debugging target must be native or server.');
  if (configuration.foreign !== undefined && Buffer.byteLength(string(configuration.foreign, 'operator foreign catalogue'), 'utf8') > 4096) throw new Error('Operator foreign catalogue path exceeds4 KiB.');
  if (configuration.foreign !== undefined) programArguments([configuration.foreign]);
  const foreign = configuration.foreign === undefined ? undefined : path.resolve(cwd, configuration.foreign);
  if ((foreign !== undefined || configuration.project !== undefined) && args.some(arg => ['--foreign', '--nex-foreign'].includes(arg))) {
    throw new Error('Use the foreign launch field for a reviewed operator catalogue.');
  }
  if (configuration.stopOnEntry !== undefined && typeof configuration.stopOnEntry !== 'boolean') throw new Error('stopOnEntry must be a boolean.');
  return {cwd, source, compiler, args, target, foreign};
}

async function prepareSourceSession(configuration, options = {}, freshObservation, physicalSourceBeforeCompilation, projectSpelling) {
  const {cwd, source, compiler, args, target, foreign} = launchSettings(configuration, options, true);
  if (foreign !== undefined) programArguments([target === 'server' ? '--foreign' : '--nex-foreign', foreign, ...args]);
  // The compiler records physical paths. Keep the editor's selected spelling
  // for breakpoints, while matching its identity before compilation (including
  // macOS /var aliases and symlinked workspace entries).
  let physicalSource;
  try { physicalSource = await (options.realpath || fs.realpath)(source); }
  catch (error) {
    if (error.code !== 'ENOENT' && error.code !== 'ENOTDIR') throw error;
    physicalSource = source; // Let the compiler diagnose a missing entry.
  }
  if (physicalSourceBeforeCompilation !== undefined) {
    if (physicalSource !== physicalSourceBeforeCompilation) throw new Error('The selected source changed after compilation. Start a fresh project launch.');
    physicalSource = physicalSourceBeforeCompilation;
  }
  let output;
  try {
    const result = freshObservation === undefined ? await (options.execute || execute)(compiler, ['debug', source, '--kind', 'nex-dap', '--json',
      ...(target === 'server' ? ['--target', 'server'] : []), ...(foreign === undefined ? [] : ['--foreign', foreign])],
      {cwd, encoding: 'utf8', maxBuffer: 8 * 1024 * 1024, timeout: 180000, windowsHide: true, shell: false})
      : {stdout: JSON.stringify(freshObservation)};
    output = result.stdout;
  } catch (error) {
    let detail = '';
    for (const text of [error.stdout, error.stderr]) {
      try { const diagnostic = JSON.parse(text); if (diagnostic.message) { detail = `${diagnostic.code || 'NEX'}: ${diagnostic.message}`; break; } } catch (_) {}
    }
    throw new Error(detail || `NEX debug preparation failed: ${String(error.message).slice(0, 2048)}`);
  }
  let session;
  try { session = JSON.parse(output); } catch (_) { throw new Error('NEX returned an invalid debug-session response.'); }
  if (session.schema !== 'nex.debug-session/1' || session.ok !== true || session.adapter !== 'nex-dap' ||
      session.nex_adapter?.schema !== 'nex.dap-adapter/1' || session.nex_adapter.available !== true) {
    throw new Error('NEX requires its matching native SDK, Python and an available lldb-dap backend.');
  }
  if (target === 'server' && (session.application_kind !== 'http_server' || session.host_compatible !== true)) {
    throw new Error('Server debugging requires a compiler with checked host HTTP-server sessions.');
  }
  const command = session.adapter_command;
  if (!Array.isArray(command) || !command.length || command.some(arg => typeof arg !== 'string' || !arg || arg.includes('\0'))) throw new Error('NEX returned an invalid adapter command.');
  const launch = session.launch;
  if (!launch || launch.type !== 'nex' || launch.request !== 'launch' || !path.isAbsolute(string(launch.program, 'frozen executable')) ||
      !path.isAbsolute(string(launch.cwd, 'frozen project directory')) || !Array.isArray(launch.initCommands) ||
      launch.initCommands.some(arg => typeof arg !== 'string')) throw new Error('NEX returned an invalid frozen launch configuration.');
  if (launch.args !== undefined && (!Array.isArray(launch.args) || launch.args.some(arg => typeof arg !== 'string'))) throw new Error('NEX returned invalid execution capability arguments.');
  if (launch.preRunCommands !== undefined && (!Array.isArray(launch.preRunCommands) || launch.preRunCommands.some(arg => typeof arg !== 'string' || arg.includes('\0')))) throw new Error('NEX returned invalid pre-run commands.');
  const manifestPath = string(session.manifest, 'debug manifest');
  if (!path.isAbsolute(manifestPath)) throw new Error('NEX returned a relative debug manifest.');
  const readFile = options.readFile || fs.readFile;
  const manifest = JSON.parse(await readFile(manifestPath, 'utf8'));
  if (manifest.schema !== 'nex.debug/1' || manifest.revision !== session.revision || manifest.build_key !== session.build_key || !Array.isArray(manifest.sources)) {
    throw new Error('NEX debug manifest differs from its fresh session.');
  }
  if (physicalSourceBeforeCompilation !== undefined && !manifest.sources.some(row => row.original === physicalSource)) throw new Error('The selected source identity differs from its captured project session.');
  const originals = [], frozenFallbacks = [];
  for (const row of manifest.sources) {
    if (!['original', 'projection', 'debug_path'].every(key => typeof row[key] === 'string' && !row[key].includes('\0') && path.isAbsolute(row[key]))) {
      throw new Error('NEX debug manifest contains an invalid source mapping.');
    }
    const selected = row.original === physicalSource;
    const relative = projectSpelling ? path.relative(projectSpelling.physical, row.original) : undefined;
    const inProject = relative !== undefined && relative !== '..' && !relative.startsWith('..' + path.sep) && !path.isAbsolute(relative);
    const destination = selected ? source : inProject ? path.resolve(projectSpelling.original, relative) : row.original;
    let same = false;
    // Read through the selected spelling again: a symlink may have changed
    // while the compiler was preparing its frozen source.
    try {same = (await readFile(destination)).equals(await readFile(row.projection));} catch (_) {}
    if (same) originals.push([row.debug_path, destination]);
    else {
      frozenFallbacks.push(row.original);
      if (selected) throw new Error('The selected source changed after compilation. Save it and start a fresh NEX launch.');
    }
  }
  if (launch.sourceMap !== undefined && (!Array.isArray(launch.sourceMap) || launch.sourceMap.some(row => !Array.isArray(row) || row.length !== 2 || row.some(item => typeof item !== 'string' || item.includes('\0'))))) {
    throw new Error('NEX returned invalid frozen source maps.');
  }
  const sourceMaps = [...originals, ...(launch.sourceMap || [])];
  const {sourceMap: unusedSourceMap, ...frozenLaunch} = launch;
  const preRunCommands = [];
  // lldb-dap inserts sourceMap strings into a command without quoting their
  // contents. Configure the same map after target creation using escaped LLDB
  // arguments, so original files containing quotes remain valid breakpoints.
  if (sourceMaps.length) preRunCommands.push('settings set target.source-map ' + sourceMaps.flat().map(lldbArgument).join(' '));
  preRunCommands.push(...(launch.preRunCommands || []));
  return {command: [...command], revision: session.revision, buildKey: session.build_key,
    originalSourceMappings: originals, frozenSourceFallbacks: frozenFallbacks,
    frozenSourcePaths: manifest.sources.map(row => row.projection),
    launch: {...frozenLaunch, name: configuration.name || 'NEX', stopOnEntry: configuration.stopOnEntry || false,
      preRunCommands,
      // Compiler-provided arguments carry explicit foreign execution grants.
      args: programArguments([...(launch.args || []), ...args])}};
}

function projectIdentifier(value, name) {
  if (typeof value !== 'string' || !/^[A-Za-z_][A-Za-z_0-9]{0,63}$/.test(value)) throw new Error(`Invalid project ${name}.`);
  return value;
}

function digest(value) {return typeof value === 'string' && /^[0-9a-f]{64}$/.test(value);}

async function physicalPath(name, options) {
  try {return await (options.realpath || fs.realpath)(name);}
  catch (error) {
    if (error.code !== 'ENOENT' && error.code !== 'ENOTDIR') throw error;
    return name; // Preserve a useful compiler diagnostic for missing inputs.
  }
}

function projectPlan(plan, selection) {
  if (!plan || plan.schema !== 'nex.project-plan/1' || plan.ok !== true || plan.source_checked !== true ||
      plan.graph_store_opened !== false || plan.external_tools_invoked !== false ||
      plan.selected_component !== selection.component || plan.configuration?.name !== selection.configuration ||
      !digest(plan.plan_hash) || !digest(plan.architecture_hash) ||
      !Array.isArray(plan.components) || plan.components.length > 128) throw new Error('NEX returned an invalid checked project plan.');
  if (!path.isAbsolute(string(plan.root, 'project root')) || !path.isAbsolute(string(plan.manifest, 'architecture manifest'))) throw new Error('NEX returned relative project paths.');
  const selected = plan.components.filter(row => row?.name === selection.component);
  if (selected.length !== 1 || !['executable', 'server'].includes(selected[0].kind)) throw new Error('Project editor debugging requires one native executable/server component.');
  if (selected[0].native_toolchain?.host_compatible === false) throw new Error('Project editor debugging requires a matching native host.');
  const entry = string(selected[0].entry, 'component entry');
  const relative = path.relative(plan.root, path.resolve(plan.root, entry));
  if (path.isAbsolute(entry) || relative === '..' || relative.startsWith('..' + path.sep) || path.extname(entry) !== '.nex') throw new Error('NEX returned an invalid component source entry.');
  return selected[0];
}

async function prepareProjectSession(configuration, options) {
  const {cwd, compiler, args, foreign} = launchSettings(configuration, options, false);
  if (configuration.source !== undefined) throw new Error('Choose either a source launch or a project launch.');
  if (configuration.target !== undefined) throw new Error('Project debugging selects its target through the architecture.');
  const selection = configuration.project;
  if (!selection || typeof selection !== 'object' || Array.isArray(selection) ||
      Object.keys(selection).some(key => !['manifest', 'component', 'configuration'].includes(key))) throw new Error('Invalid project launch selection.');
  const component = projectIdentifier(selection.component, 'component');
  const selectedConfiguration = projectIdentifier(selection.configuration, 'configuration');
  const manifest = path.resolve(cwd, string(selection.manifest, 'architecture manifest'));
  const physicalManifest = await physicalPath(manifest, options);
  const argumentsFor = kind => ['project', manifest, '--kind', kind, '--component', component, '--configuration', selectedConfiguration,
    ...(kind === 'debug' ? ['--adapter', 'nex-dap', ...(foreign === undefined ? [] : ['--foreign', foreign])] : []), '--json'];
  async function request(kind) {
    let output;
    try {output = (await (options.execute || execute)(compiler, argumentsFor(kind),
      {cwd, encoding: 'utf8', maxBuffer: 16 * 1024 * 1024, timeout: 180000, windowsHide: true, shell: false})).stdout;}
    catch (error) {
      for (const text of [error.stdout, error.stderr]) {
        try {const diagnostic = JSON.parse(text); if (diagnostic.message) throw Object.assign(new Error(`${diagnostic.code || 'NEX'}: ${diagnostic.message}`), {structured: true});}
        catch (parsed) {if (parsed.structured) throw parsed;}
      }
      throw new Error(`NEX project debug preparation failed: ${String(error.message).slice(0, 2048)}`);
    }
    try {return JSON.parse(output);} catch (_) {throw new Error('NEX returned an invalid project response.');}
  }
  async function checkPaths(plan) {
    if (await physicalPath(manifest, options) !== physicalManifest ||
        await physicalPath(plan.manifest, options) !== physicalManifest ||
        await physicalPath(plan.root, options) !== plan.root) throw new Error('The architecture manifest or project root changed during preparation.');
  }
  const before = await request('plan');
  const selected = projectPlan(before, selection);await checkPaths(before);
  if (foreign !== undefined) programArguments([selected.kind === 'server' ? '--foreign' : '--nex-foreign', foreign, ...args]);
  const physicalSourceBeforeCompilation = await physicalPath(path.resolve(before.root, selected.entry), options);
  const prepared = await request('debug');
  if (prepared?.schema !== 'nex.project-session/1' || prepared.ok !== true || prepared.action !== 'debug' ||
      prepared.component !== component || prepared.graph_store_opened !== false || prepared.plan_hash !== before.plan_hash ||
      prepared.plan?.plan_hash !== before.plan_hash || prepared.plan?.architecture_hash !== before.architecture_hash) throw new Error('The project inputs changed while compiling the debug session.');
  projectPlan(prepared.plan, selection);await checkPaths(prepared.plan);
  const artifacts = Array.isArray(prepared.artifacts) ? prepared.artifacts.filter(row => row?.component === component) : [];
  const session = prepared.observation;
  if (artifacts.length !== 1 || artifacts[0].kind !== selected.kind || artifacts[0].host_compatible !== true ||
      artifacts[0].artifact !== session?.launch?.program || artifacts[0].build_key !== session?.build_key ||
      session?.launch?.cwd !== before.root) throw new Error('NEX project session does not match its final native artifact.');
  const after = await request('plan');projectPlan(after, selection);await checkPaths(after);
  if (after.plan_hash !== before.plan_hash || after.architecture_hash !== before.architecture_hash) throw new Error('The project inputs changed after compilation. Start a fresh launch.');
  // Preserve the editor's physical workspace spelling, including /var aliases.
  let root = before.root;
  for (const start of [path.dirname(manifest), cwd]) {
    let candidate = start;
    for (let count = 0; count < 128; count++) {
      if (await physicalPath(candidate, options) === before.root) {root = candidate; break;}
      const parent = path.dirname(candidate);if (parent === candidate) break;candidate = parent;
    }
    if (root !== before.root) break;
  }
  const {project: ignoredProject, ...sourceConfiguration} = configuration;
  const result = await prepareSourceSession({...sourceConfiguration, target: selected.kind === 'server' ? 'server' : 'native', source: path.resolve(root, selected.entry)}, options, session, physicalSourceBeforeCompilation,
    {physical: before.root, original: root});
  return {...result, project: {manifest, component, configuration: selectedConfiguration,
    architectureHash: before.architecture_hash, planHash: before.plan_hash}};
}

async function prepareSession(configuration, options = {}) {
  return configuration.project === undefined ? prepareSourceSession(configuration, options) : prepareProjectSession(configuration, options);
}

module.exports = {prepareSession, programArguments};
