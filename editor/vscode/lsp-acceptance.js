'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const {pathToFileURL} = require('node:url');
const {LanguageClient} = require('./lsp-client');

async function accept(compiler, output) {
  fs.mkdirSync(output);
  const project = fs.realpathSync(output);
  const source = path.join(project, 'main with spaces.nex'), model = path.join(project, 'model 🧠.nex');
  const main = 'module editor_client;\nimport "./model 🧠.nex" as m;\nfn main()->i64{return m::answer(21);}\n';
  const library = 'module model;\npub fn answer(n:i64)->i64{return n*2;}\n';
  fs.writeFileSync(path.join(project, 'nex.json'), JSON.stringify({schema:'nex.project/1',language:'0.16',entry:path.basename(source)}));
  fs.writeFileSync(source, main); fs.writeFileSync(model, library);
  const sourceURI = pathToFileURL(source).href, modelURI = pathToFileURL(model).href;
  const notifications = [], waiting = new Set();
  const client = new LanguageClient(compiler, project);
  const report = {schema:'nex.editor-lsp-client-acceptance/1',ok:false,compiler_sha256:crypto.createHash('sha256').update(fs.readFileSync(compiler)).digest('hex'),checks:[]};
  const wake = (method, params) => {
    const event = {method,params};
    for (const item of waiting) if (item.match(event)) {waiting.delete(item); clearTimeout(item.timer); item.resolve(event); return;}
    notifications.push(event);
  };
  client.on('notification', wake);
  client.on('failure', error => {for (const item of waiting) {clearTimeout(item.timer); item.reject(error);} waiting.clear();});
  function notification(match) {
    const index = notifications.findIndex(match);
    if (index >= 0) return Promise.resolve(notifications.splice(index, 1)[0]);
    return new Promise((resolve,reject) => {
      const item = {match,resolve,reject};
      item.timer = setTimeout(() => {waiting.delete(item); reject(new Error('NEX editor diagnostic timed out.'));}, 35000);
      waiting.add(item);
    });
  }
  const diagnostics = version => notification(value => value.method === 'textDocument/publishDiagnostics' &&
    value.params.uri === sourceURI && value.params.version === version).then(value => value.params.diagnostics);
  try {
    report.server = await client.start(pathToFileURL(project).href);
    client.notify('textDocument/didOpen', {textDocument:{uri:sourceURI,languageId:'nex',version:1,text:main}});
    assert.deepEqual(await diagnostics(1), []);
    const document = {textDocument:{uri:sourceURI}};
    const symbols = await client.request('textDocument/documentSymbol', document);
    assert.deepEqual(symbols.map(value => value.name), ['main']);
    const query = {...document,position:{line:2,character:main.split('\n')[2].indexOf('answer')}};
    const definition = await client.request('textDocument/definition', query);
    assert.equal(definition.length, 1); assert.equal(definition[0].uri, modelURI);
    assert.deepEqual(definition[0].range, {start:{line:1,character:7},end:{line:1,character:13}});
    assert.equal((await client.request('textDocument/hover',query)).contents.value, 'i64');
    report.checks.push('actual Node stdio client and checked cross-module definition/hover/outline');
    const invalid = 'module editor_client;\r\nfn main()->i64{let text:str="Я🧠";return missing;}\r\n';
    client.notify('textDocument/didChange', {textDocument:{uri:sourceURI,version:2},contentChanges:[{text:invalid}]});
    const errors = await diagnostics(2);
    assert.equal(errors.length, 1); assert.equal(errors[0].code, 'E_NAME');
    assert.deepEqual(errors[0].range.start, {line:1,character:invalid.split('\r\n')[1].indexOf('missing')});
    client.notify('textDocument/didChange', {textDocument:{uri:sourceURI,version:3},contentChanges:[{text:main}]});
    assert.deepEqual(await diagnostics(3), []);
    assert.equal((await client.request('textDocument/hover',query)).contents.value, 'i64');
    report.checks.push('unsaved Unicode/CRLF diagnostic and repair using matching document versions');
    await client.dispose();
    assert.equal(client.child.exitCode, 0); assert.equal(client.stderr, '');
    assert.equal(fs.readFileSync(source,'utf8'), main); assert.equal(fs.readFileSync(model,'utf8'), library);
    assert.equal(fs.existsSync(path.join(project,'.nex')), false);
    report.checks.push('clean protocol shutdown with source and graph untouched');
    report.ok = true; report.requests = client.nextId; report.source_and_graph_unchanged = true;
  } finally {
    await client.dispose();
    for (const item of waiting) clearTimeout(item.timer);
    fs.writeFileSync(path.join(project,'report.json'), JSON.stringify(report,null,2)+'\n');
  }
  return report;
}

if (require.main === module) {
  if (process.argv.length !== 4) throw new Error('Usage: node lsp-acceptance.js /absolute/compiler NEW_OUTPUT');
  accept(path.resolve(process.argv[2]),path.resolve(process.argv[3])).then(value => process.stdout.write(JSON.stringify(value)+'\n'))
    .catch(error => {console.error(error.stack); process.exitCode = 1;});
}
module.exports = {accept};
