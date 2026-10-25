'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const {execFileSync} = require('node:child_process');
const {pathToFileURL, fileURLToPath} = require('node:url');
const {LanguageClient} = require('./lsp-client');

// Locations may encode a comma while Node leaves it literal. Compare the exact
// local file identity, retaining every range and rejecting other URI components.
function fileIdentity(uri) {
  assert.equal(typeof uri, 'string');
  assert.equal(/[\u0000-\u0020\u007f]/.test(uri), false);
  const url = new URL(uri);
  assert.equal(url.protocol, 'file:');
  assert.equal(url.host, '');
  assert.equal(url.search, '');
  assert.equal(url.hash, '');
  return pathToFileURL(fileURLToPath(url)).href;
}
const locationIdentity = value => ({...value, uri:fileIdentity(value.uri)});

async function accept(compiler, output) {
  fs.mkdirSync(output);
  const project = fs.realpathSync(output);
  const language = JSON.parse(execFileSync(compiler, ['describe', '--json'], {
    cwd: project, encoding: 'utf8', timeout: 30000, maxBuffer: 4 * 1024 * 1024,
  })).version;
  assert.equal(typeof language, 'string');
  assert.ok(language.length);
  const source = path.join(project, 'main with spaces.nex'), model = path.join(project, 'model 🧠.nex');
  const main = 'module editor_client;\nimport "./model 🧠.nex" as m;\nfn main()->i64{return m::answer(21);}\n';
  const library = 'module model;\npub fn answer(n:i64)->i64{return n*2;}\n';
  fs.writeFileSync(path.join(project, 'nex.json'), JSON.stringify({schema:'nex.project/1',language,entry:path.basename(source)}));
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
    assert.equal(definition.length, 1); assert.equal(fileIdentity(definition[0].uri), modelURI);
    assert.deepEqual(definition[0].range, {start:{line:1,character:7},end:{line:1,character:13}});
    assert.equal((await client.request('textDocument/hover',query)).contents.value, 'pub shared fn model::answer(n: i64) -> i64');
    report.checks.push('actual Node stdio client and checked cross-module definition/hover/outline');
    const references = await client.request('textDocument/references', {...query,context:{includeDeclaration:false}});
    assert.deepEqual(references.map(locationIdentity), [{uri:sourceURI,range:{start:query.position,end:{line:2,character:query.position.character+6}}}]);
    const withDeclaration = await client.request('textDocument/references', {...query,context:{includeDeclaration:true}});
    assert.equal(withDeclaration.length, 2); assert.ok(withDeclaration.some(value => fileIdentity(value.uri) === modelURI));
    report.reference_checks = true;
    report.checks.push('exact cross-module references and explicit declaration inclusion');

    const invalid = 'module editor_client;\r\nfn main()->i64{let text:str="Я🧠";return missing;}\r\n';
    client.notify('textDocument/didChange', {textDocument:{uri:sourceURI,version:2},contentChanges:[{text:invalid}]});
    const errors = await diagnostics(2);
    assert.equal(errors.length, 1); assert.equal(errors[0].code, 'E_NAME');
    assert.deepEqual(errors[0].range.start, {line:1,character:invalid.split('\r\n')[1].indexOf('missing')});
    client.notify('textDocument/didChange', {textDocument:{uri:sourceURI,version:3},contentChanges:[{text:main}]});
    assert.deepEqual(await diagnostics(3), []);
    assert.equal((await client.request('textDocument/hover',query)).contents.value, 'pub shared fn model::answer(n: i64) -> i64');
    report.checks.push('unsaved Unicode/CRLF diagnostic and repair using matching document versions');
    const typedLibrary = "module model;pub trait Content{type Item;fn get(value:Self)->Content::Item<Self>;}pub struct Box<T>{value:T;}fn extract<T>(value:Box<T>)->T{return value.value;}pub impl boxed<T>:Content for Box<T>{type Item=T;get=extract<T>;}";
    const typedMain = "module editor_types;import \"./model 🧠.nex\" as m;fn main()->i64{let value:m::Box<i64>=m::Box<i64>(42);return m::Content<m::Box<i64>>::get(value);}";
    client.notify('textDocument/didOpen', {textDocument:{uri:modelURI,languageId:'nex',version:1,text:typedLibrary}});
    client.notify('textDocument/didChange', {textDocument:{uri:sourceURI,version:4},contentChanges:[{text:typedMain}]});
    assert.deepEqual(await diagnostics(4), []);
    const typedQuery = (uri,text,at) => ({textDocument:{uri},position:{line:0,character:at}});
    const alias = await client.request('textDocument/references', {...typedQuery(sourceURI,typedMain,typedMain.indexOf('m;')),context:{includeDeclaration:true}});
    assert.equal(alias.length,5); assert.ok(alias.every(row => fileIdentity(row.uri) === sourceURI));
    const parameter = await client.request('textDocument/references', {...typedQuery(modelURI,typedLibrary,typedLibrary.indexOf('T>{')),context:{includeDeclaration:true}});
    assert.equal(parameter.length,2);
    const contract = await client.request('textDocument/definition', typedQuery(sourceURI,typedMain,typedMain.indexOf('get(value)')));
    assert.deepEqual(contract.map(locationIdentity),[{uri:modelURI,range:{start:{line:0,character:typedLibrary.indexOf('get(value')},end:{line:0,character:typedLibrary.indexOf('get(value')+3}}}]);
    for (const [uri,text,at,expected] of [
      [sourceURI,typedMain,typedMain.indexOf('m;'),'import m = model ("./model 🧠.nex")'],
      [modelURI,typedLibrary,typedLibrary.indexOf('T>{'),'type parameter model::Box::T'],
      [modelURI,typedLibrary,typedLibrary.indexOf('Item;'),'associated type model::Content::Item<Self>'],
      [sourceURI,typedMain,typedMain.indexOf('get(value)'),'shared fn model::Content::get(value: Self) -> model::Content::Item<Self>'],
      [sourceURI,typedMain,typedMain.indexOf('i64>=m::Box'),'type i64']]) {
      assert.deepEqual((await client.request('textDocument/hover',typedQuery(uri,text,at))).contents,{kind:'plaintext',value:expected});
    }
    assert.deepEqual(await client.request('textDocument/definition',typedQuery(sourceURI,typedMain,typedMain.indexOf('i64>=m::Box'))),[]);
    report.identifier_checks = true;
    report.checks.push('exact identifier hover and builtin types without an invented physical definition');
    report.type_reference_checks = true;
    report.checks.push('type parameter scopes, alias identities and exact trait contract definitions');
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
