'use strict';
const fs = require('node:fs/promises');
const path = require('node:path');
const {programArguments} = require('./session');

function identifier(value) {return typeof value === 'string' && /^[A-Za-z_][A-Za-z_0-9]{0,63}$/.test(value);}

// UI choices select metadata only. The existing launch provider asks the
// configured compiler for fresh checked plans and the native debug descriptor.
function createProjectDebugCommand(vscode, options = {}) {
  return async () => {
    try {
      if (!vscode.workspace.isTrusted) throw new Error('Trust the workspace before debugging a NEX project.');
      const folders = (vscode.workspace.workspaceFolders || []).filter(folder => folder.uri.scheme === 'file');
      if (!folders.length) throw new Error('Open a physical NEX project folder.');
      let folder = folders[0];
      if (folders.length > 1) {
        const selected = await vscode.window.showQuickPick(folders.map(folder => ({label: folder.name, description: folder.uri.fsPath, folder})), {placeHolder: 'Select the NEX project folder'});
        if (!selected) return false;folder = selected.folder;
      }
      const manifest = path.join(folder.uri.fsPath, 'nex.build.json');
      const info = await (options.stat || fs.stat)(manifest);
      if (!info.isFile() || info.size > 262144) throw new Error('nex.build.json must be a project manifest of at most 256 KiB.');
      const text = await (options.readFile || fs.readFile)(manifest, 'utf8');
      if (Buffer.byteLength(text, 'utf8') > 262144) throw new Error('nex.build.json exceeds 256 KiB.');
      const metadata = JSON.parse(text);
      if (!metadata || metadata.schema !== 'nex.project-build/1' || !metadata.components || !metadata.configurations ||
          typeof metadata.components !== 'object' || Array.isArray(metadata.components) ||
          typeof metadata.configurations !== 'object' || Array.isArray(metadata.configurations) ||
          Object.keys(metadata.components).length > 128 || Object.keys(metadata.configurations).length > 32) throw new Error('Select a valid NEX architecture manifest.');
      const components = Object.entries(metadata.components).filter(([name, value]) => identifier(name) && ['executable', 'server'].includes(value?.kind)).map(([label, value]) => ({label, description: value.kind}));
      if (!components.length) throw new Error('The project has no native executable/server component to debug.');
      const component = components.length === 1 ? components[0] : await vscode.window.showQuickPick(components, {placeHolder: 'Select the native NEX component'});
      if (!component) return false;
      const configurations = Object.entries(metadata.configurations).filter(([name]) => identifier(name)).map(([label, value]) => ({label,
        description: [value?.profile, value?.target].filter(value => typeof value === 'string').map(value => value.slice(0, 128)).join(' / ')}));
      configurations.sort((a, b) => Number(b.label === metadata.default_configuration) - Number(a.label === metadata.default_configuration) || a.label.localeCompare(b.label));
      if (!configurations.length) throw new Error('The project has no named build configuration.');
      const configuration = configurations.length === 1 ? configurations[0] : await vscode.window.showQuickPick(configurations, {placeHolder: 'Select the NEX build configuration'});
      if (!configuration) return false;
      let runtime = {args: []};
      if (metadata.components[component.label].kind === 'server') {
        const input = await vscode.window.showInputBox({title: 'NEX server launch',
          prompt: 'Runtime settings as JSON: args array and optional foreign catalogue path',
          value: '{"args":["--auth","private/auth.json","--database","private/debug.sqlite","--port","0","--timeout-ms","60000"]}',
          ignoreFocusOut: true});
        if (input === undefined) return false;
        if (Buffer.byteLength(input, 'utf8') > 65536) throw new Error('Server runtime settings exceed64 KiB.');
        try {runtime = JSON.parse(input);} catch (_) {throw new Error('Server runtime settings must be a JSON object with args and optional foreign.');}
        if (!runtime || typeof runtime !== 'object' || Array.isArray(runtime) || Object.keys(runtime).some(key => !['args', 'foreign'].includes(key)) ||
            (runtime.foreign !== undefined && (typeof runtime.foreign !== 'string' || !runtime.foreign || runtime.foreign.includes('\0') || Buffer.byteLength(runtime.foreign, 'utf8') > 4096))) throw new Error('Invalid server runtime settings.');
        runtime = {...runtime, args: programArguments(runtime.args)};
      }
      if (!vscode.workspace.isTrusted) throw new Error('Workspace trust changed before NEX project debugging.');
      return await vscode.debug.startDebugging(folder, {type: 'nex', request: 'launch', name: 'Debug NEX project', cwd: folder.uri.fsPath,
        project: {manifest: 'nex.build.json', component: component.label, configuration: configuration.label}, stopOnEntry: false, ...runtime});
    } catch (error) {void vscode.window.showErrorMessage(error.message);return false;}
  };
}

module.exports = {createProjectDebugCommand};
