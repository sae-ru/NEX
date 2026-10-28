'use strict';
const vscode = require('vscode');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

function deferred(name) {
  let resolve, reject;
  const promise = new Promise((yes, no) => {resolve = yes;reject = no;});promise.catch(() => {});
  const timer = setTimeout(() => reject(new Error('Timed out waiting for ' + name)), 120000);
  return {promise, resolve, reject, cancel() {clearTimeout(timer);}};
}

async function run() {
  const folder = vscode.workspace.workspaceFolders?.[0];assert.ok(folder);assert.equal(vscode.workspace.isTrusted, true);
  const extension = vscode.extensions.getExtension('sae-ru.nex-language-tools');assert.ok(extension);
  assert.equal(extension.packageJSON.version, '0.7.0');
  assert.ok(path.resolve(extension.extensionPath).startsWith(path.resolve(process.env.NEX_EDITOR_EXTENSIONS) + path.sep));
  assert.ok(fs.existsSync(path.join(extension.extensionPath, 'project-command.js')));
  await extension.activate();
  await vscode.workspace.getConfiguration('nex', folder.uri).update('compilerPath', process.env.NEX_EDITOR_COMPILER, vscode.ConfigurationTarget.Workspace);
  const source = vscode.Uri.joinPath(folder.uri, 'core/value.nex');
  const document = await vscode.workspace.openTextDocument(source);await vscode.window.showTextDocument(document);
  const line = document.getText().split('\n').findIndex(row => row.includes('return fn('));assert.ok(line >= 0);
  const breakpoint = new vscode.SourceBreakpoint(new vscode.Location(source, new vscode.Position(line, 0)));
  vscode.debug.addBreakpoints([breakpoint]);
  const stopped = deferred('project provider breakpoint'), terminated = deferred('project termination');
  const output = [];let current, exitCode;
  const tracker = vscode.debug.registerDebugAdapterTrackerFactory('nex', {createDebugAdapterTracker(session) {
    current = session;
    return {onDidSendMessage(message) {
      if (message.type !== 'event') return;
      if (message.event === 'stopped') stopped.resolve(message.body);
      if (message.event === 'exited') exitCode = message.body.exitCode;
      if (message.event === 'terminated') {terminated.resolve(message.body);stopped.reject(new Error('Project exited before its provider breakpoint.'));}
      if (message.event === 'output') output.push(message.body);
    }};
  }});
  let chooser;
  try {
    const commands = await vscode.commands.getCommands(true);
    assert.ok(commands.includes('nex.debugProject'));assert.ok(commands.includes('workbench.action.acceptSelectedQuickOpenItem'));
    // Drive only this controlled test window's configuration picker. Calls
    // outside Quick Open are no-ops; no system keyboard event is sent.
    chooser = setInterval(() => {void vscode.commands.executeCommand('workbench.action.acceptSelectedQuickOpenItem');}, 100);
    assert.equal(await vscode.commands.executeCommand('nex.debugProject'), true);clearInterval(chooser);chooser = undefined;
    const stop = await stopped.promise;assert.equal(stop.reason, 'breakpoint');
    const placed = await current.customRequest('setBreakpoints', {source: {path: source.fsPath}, breakpoints: [{line: line + 1}]});
    assert.equal(placed.breakpoints[0].verified, true);
    const frame = (await current.customRequest('stackTrace', {threadId: stop.threadId})).stackFrames[0];
    assert.ok(frame.name.includes('make'));assert.equal(fs.realpathSync(frame.source.path), fs.realpathSync(source.fsPath));
    const value = await current.customRequest('evaluate', {expression: 'base+2', frameId: frame.id, context: 'watch'});
    assert.equal(value.nex.value, '42');assert.equal(value.nex.type, 'i64');
    const compilation = JSON.parse(fs.readFileSync(path.join(path.dirname(current.configuration.program), 'compilation.json'), 'utf8'));
    assert.equal(compilation.owned_images.length, 2);assert.ok(compilation.units.every(unit => unit.identity.startsWith('project_task::app::')));
    vscode.debug.removeBreakpoints([breakpoint]);
    await current.customRequest('setBreakpoints', {source: {path: source.fsPath}, breakpoints: []});
    await current.customRequest('continue', {threadId: stop.threadId});await terminated.promise;
    const stdout = output.filter(row => row.category === 'stdout').map(row => row.output).join('').replace(/\r\n/g, '\n');
    assert.equal(stdout, '42 🧠\n');assert.equal(exitCode, 0);assert.equal(fs.existsSync(path.join(folder.uri.fsPath, '.nex/graph.db')), false);
    fs.writeFileSync(process.env.NEX_EDITOR_REPORT, JSON.stringify({ok: true, actual_installed_vsix: true, extension_version: extension.packageJSON.version,
      compiler: process.env.NEX_EDITOR_COMPILER, editor_version: vscode.version, project_command_executed: true, configuration_picker_exercised: true,
      actual_shared_provider: true, original_provider_breakpoint: true, watch: value.nex, native_output: stdout, native_exit: exitCode,
      graph_not_created: true, controlled_test_profile: true, user_profile_modified: false}, null, 2) + '\n');
  } finally {
    if (chooser) clearInterval(chooser);stopped.cancel();terminated.cancel();tracker.dispose();
    if (current) await vscode.debug.stopDebugging(current);vscode.debug.removeBreakpoints([breakpoint]);
  }
}
module.exports = {run};
