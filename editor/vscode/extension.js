'use strict';

const {randomUUID} = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const {prepareSession} = require('./session');
const {createLanguageIntegration} = require('./language');
let languageIntegration;

function createIntegration(vscode, prepare = prepareSession, onPrepared = () => {}) {
  const pending = new Map();
  const provider = {
    async resolveDebugConfigurationWithSubstitutedVariables(folder, config) {
      try {
        if (!vscode.workspace.isTrusted) throw new Error('Trust the workspace before compiling and debugging NEX.');
        if (folder && folder.uri.scheme !== 'file') throw new Error('NEX requires a physical project directory.');
        const compiler = vscode.workspace.getConfiguration('nex', folder?.uri).get('compilerPath', 'nex');
        const prepared = await prepare(config, {folder: folder?.uri.fsPath, compiler});
        if (!vscode.workspace.isTrusted) throw new Error('Workspace trust changed during NEX compilation.');
        onPrepared(prepared);
        const now = Date.now();
        for (const [key, value] of pending) if (now - value.created > 300000) pending.delete(key);
        if (pending.size >= 32) pending.delete(pending.keys().next().value);
        const token = randomUUID();
        pending.set(token, {...prepared, created: now});
        return {...prepared.launch, _nexSession: token};
      } catch (error) {
        void vscode.window.showErrorMessage(error.message);
        return undefined;
      }
    }
  };
  const factory = {
    createDebugAdapterDescriptor(session) {
      if (!vscode.workspace.isTrusted) throw new Error('Workspace trust is required for the NEX debugger.');
      const token = session.configuration._nexSession;
      const prepared = pending.get(token);
      pending.delete(token);
      if (!prepared || Date.now() - prepared.created > 300000) throw new Error('Start a fresh NEX launch to prepare its matching adapter.');
      return new vscode.DebugAdapterExecutable(prepared.command[0], prepared.command.slice(1), {cwd: prepared.launch.cwd});
    }
  };
  return {provider, factory, dispose() {pending.clear();}};
}

function activate(context) {
  const vscode = require('vscode');
  const frozen = new Set();
  const key = value => {try {return fs.realpathSync(value);} catch (_) {return path.resolve(value);}};
  const integration = createIntegration(vscode, prepareSession, prepared => {
    for (const source of prepared.frozenSourcePaths || []) frozen.add(key(source));
    while (frozen.size > 8192) frozen.delete(frozen.values().next().value);
  });
  languageIntegration = createLanguageIntegration(vscode, {isFrozenDocument: uri => frozen.has(key(uri.fsPath))});
  languageIntegration.register();
  context.subscriptions.push(vscode.debug.registerDebugConfigurationProvider('nex', integration.provider),
    vscode.debug.registerDebugAdapterDescriptorFactory('nex', integration.factory), integration, languageIntegration);
}

async function deactivate() {await languageIntegration?.dispose(); languageIntegration = undefined;}

module.exports = {activate, deactivate, createIntegration};
