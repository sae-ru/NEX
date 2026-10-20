'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const {EventEmitter} = require('node:events');
const {PassThrough} = require('node:stream');
const {pathToFileURL, fileURLToPath} = require('node:url');
const {LanguageClient} = require('./lsp-client');
const {createLanguageIntegration} = require('./language');

function frame(value) {
  const body = Buffer.from(JSON.stringify({jsonrpc: '2.0', ...value}));
  return Buffer.concat([Buffer.from(`Content-Length: ${body.length}\r\n\r\n`), body]);
}
function processFixture() {
  const child = new EventEmitter();
  Object.assign(child, {stdin: new PassThrough(), stdout: new PassThrough(), stderr: new PassThrough(), exitCode: null, signalCode: null, messages: []});
  child.stdin.on('data', raw => {
    const message = JSON.parse(raw.subarray(raw.indexOf('\r\n\r\n') + 4).toString());
    child.messages.push(message);
    if (message.method === 'shutdown') child.stdout.write(frame({id: message.id, result: null}));
    if (message.method === 'exit') {child.exitCode = 0; queueMicrotask(() => child.emit('close', 0));}
  });
  child.kill = () => {child.signalCode = 'SIGTERM'; child.emit('close', null, 'SIGTERM');};
  return child;
}

test('LSP starts one literal executable and decodes fragmented UTF-8 responses', async () => {
  const child = processFixture(); let observed;
  const client = new LanguageClient('/sdk with $(literal)/nex', '/project with spaces', {spawn: (...args) => {observed = args; return child;}});
  try {
    const pending = client.request('echo', {text: 'Я🧠'});
    const raw = frame({id: 1, result: 'Я🧠'});
    for (const byte of raw) child.stdout.write(Buffer.from([byte]));
    assert.equal(await pending, 'Я🧠');
    assert.equal(observed[0], '/sdk with $(literal)/nex');
    assert.deepEqual(observed[1], ['lsp']); assert.equal(observed[2].shell, false);
    assert.equal(child.messages[0].params.text, 'Я🧠');
  } finally {await client.dispose();}
});

test('malformed LSP frames reject pending requests and cannot supply editor data', async () => {
  for (const raw of [Buffer.from('Content-Length: 0\r\n\r\n'), Buffer.from('Content-Length: 2\r\nContent-Length: 2\r\n\r\n{}'),
    Buffer.from('Content-Length: 2\r\n\r\n\xff\xff', 'binary'), Buffer.from('x'.repeat(8193))]) {
    const child = processFixture(), client = new LanguageClient('nex', '/project', {spawn: () => child});
    const pending = client.request('pending'); child.stdout.write(raw);
    await assert.rejects(pending); child.kill(); await client.dispose();
  }
});

test('cancellation forwards the exact request ID and ignores its late response', async () => {
  const child = processFixture(), client = new LanguageClient('nex', '/project', {spawn: () => child});
  let cancel;
  try {
    const token = {isCancellationRequested: false, onCancellationRequested(callback) {cancel = callback; return {dispose() {}};}};
    const pending = client.request('hover', {}, token); cancel();
    await assert.rejects(pending, error => error.code === -32800);
    assert.deepEqual(child.messages[1], {jsonrpc: '2.0', method: '$/cancelRequest', params: {id: 1}});
    child.stdout.write(frame({id: 1, result: 'obsolete'}));
    const next = client.request('next'); child.stdout.write(frame({id: 2, result: 'current'}));
    assert.equal(await next, 'current');
  } finally {await client.dispose();}
});

test('LSP initialization requires matching UTF-16/full-sync capabilities', async () => {
  const child = processFixture(), client = new LanguageClient('nex', '/project', {spawn: () => child});
  try {
    const pending = client.start('file:///project');
    child.stdout.write(frame({id: 1, result: {capabilities: {positionEncoding: 'utf-8'}}}));
    await assert.rejects(pending, /matching language-server/);
  } finally {await client.dispose();}
});

function host() {
  const messages = [], errors = [], logs = [], published = new Map();
  class URI {
    constructor(value) {this.value = value; this.scheme = new URL(value).protocol.slice(0, -1); this.fsPath = this.scheme === 'file' ? fileURLToPath(value) : '';}
    toString() {return this.value;}
    static file(value) {return new URI(pathToFileURL(value).href);}
    static parse(value) {return new URI(value);}
  }
  const document = {uri: URI.file('/project/main.nex'), languageId: 'nex', isClosed: false, isDirty: false, version: 1,
    text: 'module app; fn main()->i64{return 42;}', getText() {return this.text;}};
  const vscode = {Uri: URI, DiagnosticSeverity: {Error: 0, Warning: 1, Information: 2, Hint: 3}, SymbolKind: {Function: 11, Struct: 22, Enum: 9, Interface: 10, Class: 4, Variable: 12},
    Range: class {constructor(a,b,c,d) {this.start = {line:a,character:b}; this.end = {line:c,character:d};}},
    Diagnostic: class {constructor(range,message,severity) {Object.assign(this,{range,message,severity});}},
    MarkdownString: class {appendCodeblock(value) {this.value = value;}},
    Hover: class {constructor(contents,range) {Object.assign(this,{contents,range});}},
    Location: class {constructor(uri,range) {Object.assign(this,{uri,range});}},
    DocumentSymbol: class {constructor(name,detail,kind,range,selectionRange) {Object.assign(this,{name,detail,kind,range,selectionRange});}},
    workspace: {isTrusted: true, textDocuments: [document], enabled: true,
      getWorkspaceFolder: () => ({uri: URI.file('/project')}),
      getConfiguration() {return {get: (key,fallback) => key === 'compilerPath' ? '/sdk/bin/nex' : key === 'languageServer.enabled' ? vscode.workspace.enabled : fallback};}},
    window: {showErrorMessage: async text => errors.push(text), createOutputChannel: () => ({appendLine: text => logs.push(text), dispose() {}})},
    languages: {createDiagnosticCollection: () => ({set: (uri,values) => published.set(uri.toString(),values), delete: uri => published.delete(uri.toString()), dispose() {published.clear();}})}};
  const clients = [];
  const factory = (compiler,cwd) => {
    const client = new EventEmitter(); Object.assign(client, {compiler,cwd,disposed:false,
      async start(uri) {messages.push(['initialize',uri]);},
      notify(method,params) {messages.push([method,params]);},
      async request(method,params) {messages.push([method,params]); return client.answer?.(method,params);},
      async dispose() {client.disposed = true;}});
    clients.push(client); return client;
  };
  return {vscode, document, factory, clients, messages, errors, logs, published};
}
const span = {start: {line:0,character:3}, end: {line:0,character:7}};

test('untrusted, virtual and disabled language features never start a compiler', async () => {
  const h = host(), integration = createLanguageIntegration(h.vscode, {createClient:h.factory});
  try {
    h.vscode.workspace.isTrusted = false; await integration.sync(h.document);
    h.vscode.workspace.isTrusted = true; h.document.uri = h.vscode.Uri.parse('untitled:/main.nex'); await integration.sync(h.document);
    h.document.uri = h.vscode.Uri.file('/project/main.nex'); h.vscode.workspace.enabled = false; await integration.sync(h.document);
    assert.equal(h.clients.length,0);
  } finally {await integration.dispose();}
});

test('editor sends unsaved versions and flushes debounced edits before a query', async () => {
  const h = host(), integration = createLanguageIntegration(h.vscode, {createClient:h.factory,delay:5000});
  try {
    await integration.sync(h.document);
    assert.equal(h.messages[1][0],'textDocument/didOpen');
    h.document.version = 2; h.document.isDirty = true; h.document.text += '\n// Я🧠'; integration.change(h.document);
    h.clients[0].answer = () => ({contents:{kind:'plaintext',value:'i64'},range:span});
    const value = await integration.providers.hover.provideHover(h.document,{line:0,character:3});
    assert.equal(h.messages[2][0],'textDocument/didChange'); assert.equal(h.messages[2][1].textDocument.version,2);
    assert.equal(h.messages[2][1].contentChanges[0].text,h.document.text);
    assert.equal(value.contents.value,'i64'); assert.equal(value.contents.isTrusted,false);
    assert.equal(h.clients.length,1);
  } finally {await integration.dispose();}
});

test('stale diagnostics and responses cannot overwrite a newer editor version', async () => {
  const h = host(), integration = createLanguageIntegration(h.vscode, {createClient:h.factory});
  try {
    await integration.sync(h.document); const client = h.clients[0];
    const publish = version => client.emit('notification','textDocument/publishDiagnostics',{uri:h.document.uri.toString(),version,
      diagnostics:[{range:span,severity:1,code:'E_TYPE',message:'expected i64'}]});
    h.document.version = 2; h.document.isDirty = true; publish(1); assert.equal(h.published.size,0);
    publish(2); assert.equal(h.published.get(h.document.uri.toString())[0].code,'E_TYPE');
    let resolve; client.answer = () => new Promise(yes => {resolve = yes;});
    const pending = integration.providers.hover.provideHover(h.document,{line:0,character:3});
    while (!resolve) await new Promise(yes => setImmediate(yes));
    h.document.version = 3; resolve({contents:{kind:'plaintext',value:'obsolete'},range:span});
    assert.equal(await pending,undefined);
    integration.close(h.document); assert.equal(h.published.size,0); assert.equal(client.disposed,true);
  } finally {await integration.dispose();}
});

test('definitions and outline use physical URIs and checked source ranges', async () => {
  const h = host(), integration = createLanguageIntegration(h.vscode,{createClient:h.factory});
  try {
    await integration.sync(h.document);
    h.clients[0].answer = method => method === 'textDocument/definition' ? [{uri:'file:///project/model.nex',range:span}] :
      [{name:'main',detail:'shared fn main() -> i64',kind:12,range:span,selectionRange:span}];
    const locations = await integration.providers.definition.provideDefinition(h.document,{line:0,character:3});
    assert.equal(locations[0].uri.fsPath,'/project/model.nex'); assert.deepEqual(locations[0].range.start,span.start);
    const symbols = await integration.providers.symbols.provideDocumentSymbols(h.document);
    assert.equal(symbols[0].kind,h.vscode.SymbolKind.Function); assert.equal(symbols[0].name,'main');
  } finally {await integration.dispose();}
});

test('restart disposes the old process and ignores its later diagnostics', async () => {
  const h = host(), integration = createLanguageIntegration(h.vscode,{createClient:h.factory});
  try {
    await integration.sync(h.document); const old = h.clients[0]; await integration.restart();
    assert.equal(old.disposed,true); assert.equal(h.clients.length,2);
    old.emit('notification','textDocument/publishDiagnostics',{uri:h.document.uri.toString(),version:1,diagnostics:[{range:span,message:'obsolete'}]});
    assert.equal(h.published.size,0);
  } finally {await integration.dispose();}
});

test('rejected large or malformed editor text cannot reuse an older semantic index', async () => {
  const h = host(), integration = createLanguageIntegration(h.vscode,{createClient:h.factory});
  try {
    await integration.sync(h.document); const old = h.clients[0];
    h.document.version = 2; h.document.text = 'x'.repeat(1048577);
    assert.equal(await integration.providers.hover.provideHover(h.document,{line:0,character:3}),undefined);
    assert.equal(old.disposed,true);
    assert.equal(h.published.get(h.document.uri.toString())[0].code,'E_EDITOR_LIMIT');
    h.document.version = 3; h.document.text = '\ud800'; await integration.sync(h.document);
    assert.equal(h.clients.length,1);
    h.document.version = 4; h.document.text = 'module app;'; await integration.sync(h.document);
    assert.equal(h.clients.length,2); assert.equal(h.published.size,0);
  } finally {await integration.dispose();}
});

test('frozen debugger projections use the debugger rather than a live source index', async () => {
  const h = host(), integration = createLanguageIntegration(h.vscode,{createClient:h.factory,isFrozenDocument:uri => uri.fsPath.startsWith('/private/tmp/nex-debug-owned/')});
  try {
    h.document.uri=h.vscode.Uri.file('/project/.nex/build/frozen.nex');await integration.sync(h.document);
    h.document.uri=h.vscode.Uri.file('/private/tmp/nex-debug-owned/source.nex');await integration.sync(h.document);
    assert.equal(h.clients.length,0);
    h.document.uri=h.vscode.Uri.file('/project/main.nex');await integration.sync(h.document);assert.equal(h.clients.length,1);
  } finally {await integration.dispose();}
});
