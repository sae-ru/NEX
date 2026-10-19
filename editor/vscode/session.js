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

function lldbArgument(value) {
  // LLDB's command parser accepts quoted newlines and Unicode literally.
  // JSON escapes such as \uXXXX have different meanings to that parser.
  return '"' + value.replace(/\\/g, '\\\\').replace(/"/g, '\\"') + '"';
}

// Only a fresh, successful compiler response can select a frozen executable and
// adapter. No saved manifest or launch.json adapter command authorizes a process.
async function prepareSession(configuration, options = {}) {
  if (configuration.request !== 'launch' || configuration.type !== 'nex') throw new Error('Only a NEX launch request is supported.');
  const base = path.resolve(options.folder || process.cwd());
  const cwd = path.resolve(base, configuration.cwd === undefined ? '.' : string(configuration.cwd, 'project directory'));
  const source = path.resolve(cwd, string(configuration.source, 'NEX source'));
  if (path.extname(source) !== '.nex') throw new Error('Select a .nex entry source.');
  const compiler = string(options.compiler === undefined ? 'nex' : options.compiler, 'compiler executable');
  const args = configuration.args === undefined ? [] : configuration.args;
  if (!Array.isArray(args) || args.some(arg => typeof arg !== 'string' || arg.includes('\0'))) throw new Error('Program args must be strings.');
  if (configuration.stopOnEntry !== undefined && typeof configuration.stopOnEntry !== 'boolean') throw new Error('stopOnEntry must be a boolean.');
  // The compiler records physical paths. Keep the editor's selected spelling
  // for breakpoints, while matching its identity before compilation (including
  // macOS /var aliases and symlinked workspace entries).
  let physicalSource;
  try { physicalSource = await (options.realpath || fs.realpath)(source); }
  catch (error) {
    if (error.code !== 'ENOENT' && error.code !== 'ENOTDIR') throw error;
    physicalSource = source; // Let the compiler diagnose a missing entry.
  }
  let output;
  try {
    const result = await (options.execute || execute)(compiler, ['debug', source, '--kind', 'nex-dap', '--json'],
      {cwd, encoding: 'utf8', maxBuffer: 8 * 1024 * 1024, timeout: 180000, windowsHide: true, shell: false});
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
  const originals = [], frozenFallbacks = [];
  for (const row of manifest.sources) {
    if (!['original', 'projection', 'debug_path'].every(key => typeof row[key] === 'string' && !row[key].includes('\0') && path.isAbsolute(row[key]))) {
      throw new Error('NEX debug manifest contains an invalid source mapping.');
    }
    const selected = row.original === physicalSource;
    const destination = selected ? source : row.original;
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
    launch: {...frozenLaunch, name: configuration.name || 'NEX', stopOnEntry: configuration.stopOnEntry || false,
      preRunCommands,
      // Compiler-provided arguments carry explicit foreign execution grants.
      args: [...(launch.args || []), ...args]}};
}

module.exports = {prepareSession};
