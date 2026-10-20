'use strict';

const path = require('node:path');
const {LanguageClient} = require('./lsp-client');

function createLanguageIntegration(vscode, options = {}) {
  const clients = new Map(), timers = new Map(), subscriptions = [], localLimits = new Map();
  const diagnostics = vscode.languages.createDiagnosticCollection('nex');
  const output = vscode.window.createOutputChannel('NEX Language Tools');
  const selector = {language: 'nex', scheme: 'file'};
  const makeClient = options.createClient || ((compiler, cwd) => new LanguageClient(compiler, cwd));
  let disposed = false, generation = 0, disposal;

  function log(error) {if (!disposed) output.appendLine(String(error?.message || error));}
  function allowed(document) {
    const folder = vscode.workspace.getWorkspaceFolder(document.uri);
    return !disposed && vscode.workspace.isTrusted && document.languageId === 'nex' && document.uri.scheme === 'file' && document.uri.fsPath.endsWith('.nex') && !document.isClosed &&
      (!folder || folder.uri.scheme === 'file') && !document.uri.fsPath.split(path.sep).includes('.nex') && !options.isFrozenDocument?.(document.uri) &&
      vscode.workspace.getConfiguration('nex', document.uri).get('languageServer.enabled', true);
  }
  function refresh(uri) {
    const values = [...(localLimits.get(uri.toString()) || [])], seen = new Set();
    for (const entry of clients.values()) for (const value of entry.diagnostics.get(uri.toString()) || []) {
      const key = JSON.stringify([value.range, value.message, value.code, value.severity]);
      if (!seen.has(key)) {seen.add(key); values.push(value);}
    }
    if (values.length) diagnostics.set(uri, values);
    else diagnostics.delete(uri);
  }
  function clear(entry) {
    const uris = [...entry.diagnostics.keys()];
    entry.diagnostics.clear();
    for (const uri of uris) refresh(vscode.Uri.parse(uri));
  }
  function range(value) {
    const valid = p => p && Number.isInteger(p.line) && p.line >= 0 && p.line <= 2147483647 && Number.isInteger(p.character) && p.character >= 0 && p.character <= 2147483647;
    if (!value || !valid(value.start) || !valid(value.end) || value.start.line > value.end.line ||
        (value.start.line === value.end.line && value.start.character > value.end.character)) throw new Error('NEX returned an invalid text range.');
    return new vscode.Range(value.start.line, value.start.character, value.end.line, value.end.character);
  }
  function publish(entry, params) {
    if (disposed || entry.disposed || !vscode.workspace.isTrusted || !params || typeof params.uri !== 'string' || !Array.isArray(params.diagnostics)) return;
    const uri = vscode.Uri.parse(params.uri);
    if (uri.scheme !== 'file') return;
    const open = vscode.workspace.textDocuments.find(doc => doc.uri.toString() === params.uri && !doc.isClosed);
    if (open && (params.version === undefined ? open.isDirty : params.version !== open.version)) return;
    const values = params.diagnostics.map(item => {
      if (typeof item.message !== 'string') throw new Error('NEX returned an invalid diagnostic.');
      const severity = ({1: vscode.DiagnosticSeverity.Error, 2: vscode.DiagnosticSeverity.Warning,
        3: vscode.DiagnosticSeverity.Information, 4: vscode.DiagnosticSeverity.Hint})[item.severity] ?? vscode.DiagnosticSeverity.Error;
      const diagnostic = new vscode.Diagnostic(range(item.range), item.message, severity);
      diagnostic.source = 'nex';
      if (typeof item.code === 'string' || typeof item.code === 'number') diagnostic.code = item.code;
      return diagnostic;
    });
    entry.diagnostics.set(params.uri, values);
    refresh(uri);
  }
  function ensure(document) {
    if (!allowed(document)) return undefined;
    const folder = vscode.workspace.getWorkspaceFolder(document.uri);
    const cwd = folder?.uri.fsPath || path.dirname(document.uri.fsPath);
    let compiler = vscode.workspace.getConfiguration('nex', document.uri).get('compilerPath', 'nex');
    if (typeof compiler !== 'string' || !compiler || compiler.includes('\0')) throw new Error('Set nex.compilerPath to a NEX compiler executable.');
    if (!path.isAbsolute(compiler) && compiler.includes(path.sep)) compiler = path.resolve(cwd, compiler);
    const key = JSON.stringify([folder?.uri.toString() || cwd, compiler]);
    let entry = clients.get(key);
    if (!entry) {
      const client = makeClient(compiler, cwd);
      entry = {client, key, documents: new Map(), sent: new Map(), bytes: new Map(), diagnostics: new Map(), disposed: false, failed: false, context: 0};
      clients.set(key, entry);
      client.on('notification', (method, params) => {
        try {if (method === 'textDocument/publishDiagnostics') publish(entry, params);}
        catch (error) {log(error);}
      });
      const failed = error => {
        if (entry.failed || entry.disposed || disposed) return;
        entry.failed = true; clear(entry); log(error);
        void vscode.window.showErrorMessage('NEX language server stopped. Check nex.compilerPath and the NEX Language Tools output.');
      };
      client.on('failure', failed);
      entry.ready = Promise.resolve().then(() => client.start(folder?.uri.toString() || vscode.Uri.file(cwd).toString()))
        .catch(error => {failed(error); throw error;});
      entry.ready.catch(() => {});
    }
    entry.documents.set(document.uri.toString(), document);
    return entry;
  }
  function cancelTimer(uri) {const timer = timers.get(uri); if (timer) clearTimeout(timer); timers.delete(uri);}
  async function sync(document) {
    const uri = document.uri.toString();
    cancelTimer(uri);
    if (!allowed(document)) return undefined;
    const text = document.getText(), raw = Buffer.from(text, 'utf8');
    const limited = message => {
      close(document);
      const diagnostic = new vscode.Diagnostic(new vscode.Range(0, 0, 0, 0), message, vscode.DiagnosticSeverity.Error);
      diagnostic.source = 'nex'; diagnostic.code = 'E_EDITOR_LIMIT';
      localLimits.set(uri, [diagnostic]); refresh(document.uri);
      return undefined;
    };
    if (raw.length > 1048576 || raw.toString('utf8') !== text) return limited('NEX editor documents require Unicode scalar text of at most 1 MiB.');
    const entry = ensure(document);
    if (!entry) return undefined;
    await entry.ready;
    if (entry.disposed || !allowed(document) || !entry.documents.has(uri)) return undefined;
    if (document.getText() !== text) return sync(document);
    const total = raw.length + [...entry.bytes.entries()].reduce((sum, [name, bytes]) => sum + (name === uri ? 0 : bytes), 0);
    if (total > 8 * 1048576 || (!entry.sent.has(uri) && entry.sent.size >= 128)) return limited('NEX language server supports 128 open documents and 8 MiB of open source text per workspace.');
    if (localLimits.delete(uri)) refresh(document.uri);
    const version = document.version;
    if (!entry.sent.has(uri)) {entry.client.notify('textDocument/didOpen', {textDocument: {uri, languageId: 'nex', version, text}}); ++entry.context;}
    else if (entry.sent.get(uri) !== version) {entry.client.notify('textDocument/didChange', {textDocument: {uri, version}, contentChanges: [{text}]}); ++entry.context;}
    entry.sent.set(uri, version);
    entry.bytes.set(uri, raw.length);
    return entry;
  }
  async function query(method, document, position, token, extra = {}) {
    const version = document.version;
    try {
      if (token?.isCancellationRequested) return undefined;
      const entry = await sync(document);
      if (!entry || document.version !== version || token?.isCancellationRequested) return undefined;
      // Imported buffers can change while the selected file stays unchanged.
      // Flush the connection's whole editable context and bind the reply to it.
      const entries = await Promise.all([...entry.documents.values()].map(sync));
      if (entries.some(value => value !== entry) || entry.disposed || token?.isCancellationRequested) return undefined;
      const versions = new Map([...entry.documents].map(([uri, doc]) => [uri, doc.version]));
      const context = entry.context;
      if ([...entry.documents].some(([uri, doc]) => !allowed(doc) || entry.sent.get(uri) !== doc.version)) return undefined;
      const params = {...extra, textDocument: {uri: document.uri.toString()}};
      if (position) params.position = {line: position.line, character: position.character};
      const value = await entry.client.request(method, params, token);
      if (entry.disposed || entry.context !== context || !allowed(document) || document.version !== version || entry.documents.size !== versions.size ||
          [...entry.documents].some(([uri, doc]) => versions.get(uri) !== doc.version || !allowed(doc))) return undefined;
      return value;
    } catch (error) {
      if (![ -32800, -32801 ].includes(error.code)) log(error);
      return undefined;
    }
  }
  const providers = {
    hover: {async provideHover(document, position, token) {
      const value = await query('textDocument/hover', document, position, token);
      if (!value || value.contents?.kind !== 'plaintext' || typeof value.contents.value !== 'string') return undefined;
      const content = new vscode.MarkdownString(); content.appendCodeblock(value.contents.value, 'nex');
      content.isTrusted = false; content.supportHtml = false;
      return new vscode.Hover(content, value.range ? range(value.range) : undefined);
    }},
    definition: {async provideDefinition(document, position, token) {
      const values = await query('textDocument/definition', document, position, token);
      if (!Array.isArray(values)) return [];
      return values.map(value => {
        const uri = vscode.Uri.parse(value.uri);
        if (uri.scheme !== 'file') throw new Error('NEX returned a non-file definition.');
        return new vscode.Location(uri, range(value.range));
      });
    }},
    references: {async provideReferences(document, position, context, token) {
      const values = await query('textDocument/references', document, position, token,
        {context: {includeDeclaration: context.includeDeclaration}});
      if (!Array.isArray(values)) return [];
      if (values.length > 10000) throw new Error('NEX returned too many reference locations.');
      return values.map(value => {
        const uri = vscode.Uri.parse(value.uri);
        if (uri.scheme !== 'file') throw new Error('NEX returned a non-file reference.');
        return new vscode.Location(uri, range(value.range));
      });
    }},
    symbols: {async provideDocumentSymbols(document, token) {
      const values = await query('textDocument/documentSymbol', document, undefined, token);
      if (!Array.isArray(values)) return [];
      const kinds = {12: vscode.SymbolKind.Function, 23: vscode.SymbolKind.Struct, 10: vscode.SymbolKind.Enum,
        11: vscode.SymbolKind.Interface, 5: vscode.SymbolKind.Class};
      return values.map(value => new vscode.DocumentSymbol(value.name, value.detail || '', kinds[value.kind] ?? vscode.SymbolKind.Variable,
        range(value.range), range(value.selectionRange)));
    }}
  };
  function change(document) {
    if (!allowed(document)) return;
    const uri = document.uri.toString(); cancelTimer(uri);
    timers.set(uri, setTimeout(() => {timers.delete(uri); void sync(document).catch(log);}, options.delay ?? 120));
  }
  function stop(entry) {
    if (entry.disposed) return entry.stopping;
    entry.disposed = true; clear(entry); clients.delete(entry.key);
    entry.stopping = Promise.resolve(entry.client.dispose()).catch(log);
    return entry.stopping;
  }
  function close(document) {
    const uri = document.uri.toString(); cancelTimer(uri);
    if (localLimits.delete(uri)) refresh(document.uri);
    for (const entry of [...clients.values()]) if (entry.documents.delete(uri)) {
      ++entry.context;
      entry.bytes.delete(uri);
      if (entry.sent.delete(uri) && !entry.failed) {
        try {entry.client.notify('textDocument/didClose', {textDocument: {uri}});} catch (error) {log(error);}
      }
      entry.diagnostics.delete(uri); refresh(document.uri);
      if (!entry.documents.size) void stop(entry);
    }
  }
  function changedFile(uri, type) {
    if (!vscode.workspace.isTrusted || uri.scheme !== 'file' || uri.fsPath.split(path.sep).some(p => ['.git', '.nex', 'node_modules'].includes(p))) return;
    for (const entry of clients.values()) {
      ++entry.context;
      void entry.ready.then(() => {
        if (!entry.disposed && !entry.failed) entry.client.notify('workspace/didChangeWatchedFiles', {changes: [{uri: uri.toString(), type}]});
      }).catch(log);
    }
  }
  async function restart() {
    const current = ++generation;
    for (const uri of timers.keys()) cancelTimer(uri);
    const limits = [...localLimits.keys()]; localLimits.clear();
    for (const uri of limits) refresh(vscode.Uri.parse(uri));
    await Promise.all([...clients.values()].map(stop));
    if (!disposed && current === generation && vscode.workspace.isTrusted) await Promise.all(vscode.workspace.textDocuments.map(doc => sync(doc).catch(log)));
  }
  function register() {
    subscriptions.push(vscode.languages.registerHoverProvider(selector, providers.hover),
      vscode.languages.registerDefinitionProvider(selector, providers.definition),
      vscode.languages.registerReferenceProvider(selector, providers.references),
      vscode.languages.registerDocumentSymbolProvider(selector, providers.symbols),
      vscode.workspace.onDidOpenTextDocument(doc => {void sync(doc).catch(log);}),
      vscode.workspace.onDidChangeTextDocument(event => {if (event.contentChanges.length) change(event.document);}),
      vscode.workspace.onDidCloseTextDocument(close),
      vscode.workspace.onDidSaveTextDocument(doc => {void sync(doc).then(entry => {
        if (entry && !entry.disposed) entry.client.notify('textDocument/didSave', {textDocument: {uri: doc.uri.toString()}, text: doc.getText()});
        changedFile(doc.uri, 2);
      }).catch(log);}),
      vscode.workspace.onDidChangeConfiguration(event => {if (event.affectsConfiguration('nex')) void restart().catch(log);}),
      vscode.commands.registerCommand('nex.restartLanguageServer', restart));
    if (vscode.workspace.onDidGrantWorkspaceTrust) subscriptions.push(vscode.workspace.onDidGrantWorkspaceTrust(() => {void restart().catch(log);}));
    for (const pattern of ['**/*.nex', '**/nex.json', '**/nex.lock.json']) {
      const watcher = vscode.workspace.createFileSystemWatcher(pattern);
      subscriptions.push(watcher, watcher.onDidCreate(uri => changedFile(uri, 1)), watcher.onDidChange(uri => changedFile(uri, 2)), watcher.onDidDelete(uri => changedFile(uri, 3)));
    }
    for (const document of vscode.workspace.textDocuments) void sync(document).catch(log);
  }
  function dispose() {
    if (disposal) return disposal;
    disposed = true; ++generation;
    for (const uri of timers.keys()) cancelTimer(uri);
    for (const subscription of subscriptions) subscription.dispose();
    disposal = Promise.all([...clients.values()].map(stop)).then(() => {diagnostics.dispose(); output.dispose();});
    return disposal;
  }
  return {register, providers, sync, change, close, restart, dispose};
}

module.exports = {createLanguageIntegration};
