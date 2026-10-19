'use strict';
const vscode = require('vscode');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

function deferred(name, milliseconds = 90000) {
  let resolve, reject;
  const promise = new Promise((yes, no) => {resolve = yes; reject = no;});
  const timer = setTimeout(() => reject(new Error(`Timed out waiting for ${name}`)), milliseconds);
  // A session can fail before this particular event is awaited.
  promise.catch(() => {});
  return {promise, resolve, reject, cancel() {clearTimeout(timer);}};
}

async function run() {
  const folder = vscode.workspace.workspaceFolders?.[0];
  assert.ok(folder, 'controlled test workspace is required');
  assert.equal(vscode.workspace.isTrusted, true);
  const extension = vscode.extensions.getExtension('sae-ru.nex-language-tools');
  assert.ok(extension, 'installed VSIX was not found');
  // The installed package is tested, not the development source tree.
  assert.ok(path.resolve(extension.extensionPath).startsWith(path.resolve(process.env.NEX_EDITOR_EXTENSIONS) + path.sep));
  await extension.activate();
  await vscode.workspace.getConfiguration('nex', folder.uri).update('compilerPath', process.env.NEX_EDITOR_COMPILER, vscode.ConfigurationTarget.Workspace);
  const source = vscode.Uri.joinPath(folder.uri, 'main with spaces.nex');
  const document = await vscode.workspace.openTextDocument(source);
  assert.equal(document.languageId, 'nex');
  await vscode.window.showTextDocument(document);
  const line = document.getText().split('\n').findIndex(text => text.includes('print(total + 2)'));
  assert.ok(line >= 0);
  vscode.debug.addBreakpoints([new vscode.SourceBreakpoint(new vscode.Location(source, new vscode.Position(line, 0)))]);
  const stopped = deferred('native breakpoint'), terminated = deferred('native termination');
  const output = [], breakpointResponses = [];
  let current;
  const tracker = vscode.debug.registerDebugAdapterTrackerFactory('nex', {
    createDebugAdapterTracker(session) {
      current = session;
      return {onDidSendMessage(message) {
        if (message.type === 'event' && message.event === 'stopped') stopped.resolve(message.body);
        if (message.type === 'event' && message.event === 'terminated') {
          terminated.resolve(message.body);
          stopped.reject(new Error('Native program terminated before the requested breakpoint.'));
        }
        if (message.type === 'event' && message.event === 'output') output.push(message.body);
        if (message.type === 'response' && message.command === 'setBreakpoints') breakpointResponses.push(message);
      }};
    }
  });
  try {
    assert.equal(await vscode.debug.startDebugging(folder, {type: 'nex', request: 'launch', name: 'NEX installed VSIX acceptance',
      source: source.fsPath, cwd: folder.uri.fsPath, stopOnEntry: false}), true);
    const stop = await stopped.promise;
    assert.equal(stop.reason, 'breakpoint');
    assert.ok(breakpointResponses.some(response => response.success && response.body.breakpoints.some(value => value.verified)), 'source breakpoint was not verified');
    const trace = await current.customRequest('stackTrace', {threadId: stop.threadId, startFrame: 0, levels: 10});
    const frame = trace.stackFrames[0]; assert.ok(frame);
    assert.equal(path.basename(frame.source.path), 'main with spaces.nex');
    const value = await current.customRequest('evaluate', {expression: 'total + 2', frameId: frame.id, context: 'watch'});
    assert.equal(value.nex.value, '42'); assert.equal(value.nex.type, 'i64');
    const trait = await current.customRequest('evaluate', {expression: 'Readable<Box<i64>>::get(Box<i64>(40)) + 2', frameId: frame.id, context: 'watch'});
    assert.equal(trait.nex.value, '42');
    const scopes = await current.customRequest('scopes', {frameId: frame.id});
    assert.ok(scopes.scopes.length > 0);
    await current.customRequest('continue', {threadId: stop.threadId});
    await terminated.promise;
    assert.ok(output.some(row => row.category === 'stdout' && row.output.includes('42')));
    fs.writeFileSync(process.env.NEX_EDITOR_REPORT, JSON.stringify({ok: true, editor_version: vscode.version,
      editor_architecture: process.arch, installed_extension_path: extension.extensionPath,
      installed_extension_version: extension.packageJSON.version, physical_source_breakpoint: true,
      native_stack_scopes: true, pure_watch: value.nex, trait_watch: trait.nex,
      native_output: output.filter(row => row.category === 'stdout').map(row => row.output).join(''),
      native_resume_and_termination: true, controlled_test_profile: true, user_profile_modified: false}, null, 2) + '\n');
  } finally {
    stopped.cancel(); terminated.cancel(); tracker.dispose();
    if (current) await vscode.debug.stopDebugging(current);
    vscode.debug.removeBreakpoints(vscode.debug.breakpoints);
  }
}
module.exports = {run};
