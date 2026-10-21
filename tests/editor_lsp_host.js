'use strict';

const vscode = require('vscode');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

async function eventually(action, predicate, label) {
  const end = Date.now() + 30000;
  let last;
  while (Date.now() < end) {
    last = await action();
    if (predicate(last)) return last;
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error(`Timed out waiting for ${label}: ${JSON.stringify(last)}`);
}

async function replace(document, text) {
  const edit = new vscode.WorkspaceEdit();
  edit.replace(document.uri, new vscode.Range(document.positionAt(0), document.positionAt(document.getText().length)), text);
  assert.equal(await vscode.workspace.applyEdit(edit), true);
}

async function run() {
  const folder = vscode.workspace.workspaceFolders?.[0];
  assert.ok(folder && folder.uri.scheme === 'file');
  assert.equal(vscode.workspace.isTrusted, true);
  const extension = vscode.extensions.getExtension('sae-ru.nex-language-tools');
  assert.ok(extension && extension.extensionPath.startsWith(path.resolve(process.env.NEX_EDITOR_EXTENSIONS) + path.sep));
  assert.equal(extension.packageJSON.version, '0.6.0');
  await vscode.workspace.getConfiguration('nex', folder.uri).update('compilerPath', process.env.NEX_EDITOR_COMPILER, vscode.ConfigurationTarget.Workspace);
  await extension.activate();
  const source = vscode.Uri.joinPath(folder.uri, 'main with spaces.nex');
  const model = vscode.Uri.joinPath(folder.uri, 'model 🧠.nex');
  const original = fs.readFileSync(source.fsPath, 'utf8');
  const modelOriginal = fs.readFileSync(model.fsPath, 'utf8');
  const document = await vscode.workspace.openTextDocument(source);
  const originalEOL = document.eol;
  await vscode.window.showTextDocument(document);
  assert.equal(document.languageId, 'nex');
  assert.equal(vscode.window.activeTextEditor.document.uri.toString(), source.toString());
  const query = new vscode.Position(2, original.split('\n')[2].indexOf('answer'));
  const symbols = await eventually(() => vscode.commands.executeCommand('vscode.executeDocumentSymbolProvider', source),
    values => values?.some(value => value.name === 'main'), 'compiler document outline');
  const hover = await eventually(() => vscode.commands.executeCommand('vscode.executeHoverProvider', source, query),
    values => values?.some(value => value.contents.some(content => content.value?.includes('i64'))), 'checked type hover');
  const definitions = await eventually(() => vscode.commands.executeCommand('vscode.executeDefinitionProvider', source, query),
    values => values?.some(value => value.uri?.fsPath === model.fsPath), 'cross-module definition');
  const destination = definitions.find(value => value.uri?.fsPath === model.fsPath);
  assert.equal(destination.range.start.line, 1); assert.equal(destination.range.start.character, 7);
  const references = await eventually(() => vscode.commands.executeCommand('vscode.executeReferenceProvider', source, query),
    values => values?.some(value => value.uri?.fsPath === source.fsPath), 'exact source references');
  const use = references.find(value => value.uri?.fsPath === source.fsPath);
  assert.equal(use.range.start.line, 2); assert.equal(use.range.start.character, query.character);
  assert.equal(use.range.end.character, query.character + 6);
  // Edit only the imported buffer, then query the unchanged entry immediately.
  // The query must flush that buffer instead of reusing its earlier i64 index.
  const modelDocument = await vscode.workspace.openTextDocument(model);
  await replace(modelDocument, 'module model;\npub fn answer(n:i64)->i64{return true;}\n');
  const afterImportedEdit = await vscode.commands.executeCommand('vscode.executeHoverProvider', source, query);
  assert.equal((afterImportedEdit || []).some(value => value.contents.some(content => content.value?.includes('i64'))), false);
  await eventually(() => Promise.resolve(vscode.languages.getDiagnostics(model).filter(value => value.source === 'nex')),
    values => values.some(value => value.code === 'E_TYPE'), 'unsaved imported-buffer diagnostic');
  assert.equal(fs.readFileSync(model.fsPath, 'utf8'), modelOriginal);
  assert.equal(document.getText(), original);
  await replace(modelDocument, modelOriginal);
  await eventually(() => vscode.commands.executeCommand('vscode.executeHoverProvider', source, query),
    values => values?.some(value => value.contents.some(content => content.value?.includes('i64'))), 'imported-buffer repair');
  assert.equal(await modelDocument.save(), true);
  assert.equal(fs.readFileSync(model.fsPath, 'utf8'), modelOriginal);
  const typedLibrary = "module model;pub trait Content{type Item;fn get(value:Self)->Content::Item<Self>;}pub struct Box<T>{value:T;}fn extract<T>(value:Box<T>)->T{return value.value;}pub impl boxed<T>:Content for Box<T>{type Item=T;get=extract<T>;}";
  const typedMain = "module editor_types;import \"./model 🧠.nex\" as m;fn main()->i64{let value:m::Box<i64>=m::Box<i64>(42);return m::Content<m::Box<i64>>::get(value);}";
  await replace(modelDocument, typedLibrary);
  await replace(document, typedMain);
  const typedPosition = document.positionAt(typedMain.indexOf('get(value)'));
  const contract = await eventually(() => vscode.commands.executeCommand('vscode.executeDefinitionProvider', source, typedPosition),
    values => values?.some(value => value.uri?.fsPath === model.fsPath), 'typed trait method definition');
  const method = contract.find(value => value.uri?.fsPath === model.fsPath);
  assert.equal(method.range.start.character, typedLibrary.indexOf('get(value'));
  assert.equal(method.range.end.character, typedLibrary.indexOf('get(value') + 3);
  const aliases = await eventually(() => vscode.commands.executeCommand('vscode.executeReferenceProvider', source, document.positionAt(typedMain.indexOf('m;'))),
    values => values?.length === 5, 'import alias references');
  assert.ok(aliases.every(value => value.uri.fsPath === source.fsPath));
  const typeParameters = await eventually(() => vscode.commands.executeCommand('vscode.executeReferenceProvider', model, modelDocument.positionAt(typedLibrary.indexOf('T>{'))),
    values => values?.length === 2, 'lexical type parameter references');
  assert.ok(typeParameters.every(value => value.uri.fsPath === model.fsPath));
  for (const [uri,doc,text,at,expected] of [
    [source,document,typedMain,typedMain.indexOf('m;'),'import m = model ("./model 🧠.nex")'],
    [model,modelDocument,typedLibrary,typedLibrary.indexOf('T>{'),'type parameter model::Box::T'],
    [model,modelDocument,typedLibrary,typedLibrary.indexOf('Item;'),'associated type model::Content::Item<Self>'],
    [source,document,typedMain,typedMain.indexOf('get(value)'),'shared fn model::Content::get(value: Self) -> model::Content::Item<Self>'],
    [source,document,typedMain,typedMain.indexOf('i64>=m::Box'),'type i64']]) {
    const rendered = new vscode.MarkdownString(); rendered.appendCodeblock(expected, 'nex');
    const values = await eventually(() => vscode.commands.executeCommand('vscode.executeHoverProvider', uri, doc.positionAt(at)),
      rows => rows?.some(row => row.contents.some(content => content.value === rendered.value)), 'exact identifier hover: ' + expected);
    assert.ok(values.some(row => row.range?.start.isEqual(doc.positionAt(at))));
  }
  const primitiveDefinitions = await vscode.commands.executeCommand('vscode.executeDefinitionProvider', source, document.positionAt(typedMain.indexOf('i64>=m::Box')));
  assert.deepEqual(primitiveDefinitions, []);
  assert.equal(fs.readFileSync(source.fsPath, 'utf8'), original);
  assert.equal(fs.readFileSync(model.fsPath, 'utf8'), modelOriginal);
  assert.equal(fs.existsSync(path.join(folder.uri.fsPath, '.nex')), false);
  await replace(modelDocument, modelOriginal);
  await replace(document, original);
  const invalid = 'module ide_client;\r\nfn main()->i64{let text:str="Я🧠";return missing;}\r\n';
  await replace(document, invalid);
  const eolEditor = await vscode.window.showTextDocument(document);
  await eolEditor.edit(edit => edit.setEndOfLine(vscode.EndOfLine.CRLF));
  assert.equal(document.eol, vscode.EndOfLine.CRLF);
  assert.ok(document.getText().includes("\r\n"));
  assert.equal(document.isDirty, true);
  const invalidVersion = document.version;
  const errors = await eventually(() => Promise.resolve(vscode.languages.getDiagnostics(source).filter(value => value.source === 'nex')),
    values => values.some(value => value.code === 'E_NAME'), 'unsaved compiler diagnostic');
  const error = errors.find(value => value.code === 'E_NAME');
  assert.equal(error.range.start.line, 1);
  assert.equal(error.range.start.character, invalid.split('\r\n')[1].indexOf('missing'));
  assert.equal(fs.readFileSync(source.fsPath, 'utf8'), original);
  assert.equal(fs.existsSync(path.join(folder.uri.fsPath, '.nex')), false);
  await replace(document, original);
  await eolEditor.edit(edit => edit.setEndOfLine(originalEOL));
  assert.equal(document.getText(), original);
  assert.ok(document.version > invalidVersion);
  await eventually(() => Promise.resolve(vscode.languages.getDiagnostics(source).filter(value => value.source === 'nex')),
    values => values.length === 0, 'repaired diagnostic version');
  await eventually(() => vscode.commands.executeCommand('vscode.executeHoverProvider', source, query),
    values => values?.some(value => value.contents.some(content => content.value?.includes('i64'))), 'repaired checked hover');
  await vscode.commands.executeCommand('nex.restartLanguageServer');
  await eventually(() => vscode.commands.executeCommand('vscode.executeDocumentSymbolProvider', source),
    values => values?.some(value => value.name === 'main'), 'fresh server after restart');
  await vscode.workspace.getConfiguration('nex', folder.uri).update('languageServer.enabled', false, vscode.ConfigurationTarget.Workspace);
  await eventually(() => vscode.commands.executeCommand('vscode.executeHoverProvider', source, query), values => !values?.length,
    'disabled language client');
  await vscode.workspace.getConfiguration('nex', folder.uri).update('languageServer.enabled', true, vscode.ConfigurationTarget.Workspace);
  await eventually(() => vscode.commands.executeCommand('vscode.executeHoverProvider', source, query),
    values => values?.some(value => value.contents.some(content => content.value?.includes('i64'))), 're-enabled language client');
  assert.equal(fs.readFileSync(source.fsPath, 'utf8'), original);
  assert.equal(fs.readFileSync(model.fsPath, 'utf8'), modelOriginal);
  assert.equal(fs.existsSync(path.join(folder.uri.fsPath, '.nex')), false);
  await document.save(); // Save the restored original before closing the owned fixture.
  await vscode.commands.executeCommand('workbench.action.closeActiveEditor');
  assert.equal(fs.readFileSync(source.fsPath, 'utf8'), original);
  const report = {schema:'nex.editor-ide-acceptance/1',ok:true,editor:vscode.version,
    extension_version:extension.packageJSON.version,extension_path:extension.extensionPath,
    compiler_sha256:crypto.createHash('sha256').update(fs.readFileSync(process.env.NEX_EDITOR_COMPILER)).digest('hex'),
    actual_installed_vsix:true,checked_references:true,type_reference_checks:true,identifier_checks:true,imported_unsaved_context_checked:true,trusted_physical_workspace:true,controlled_test_profile:true,user_profile_modified:false,
    outline_symbols:symbols.map(value => value.name),checked_hover:true,cross_module_definition:true,
    unicode_crlf_unsaved_error:true,explicit_crlf_eol_asserted:true,repaired_document_version:true,restart_verified:true,disable_enable_verified:true,
    physical_sources_unchanged:true,graph_not_created:true,close_verified:true,
    source_sha256:crypto.createHash('sha256').update(original).digest('hex'),
    model_sha256:crypto.createHash('sha256').update(modelOriginal).digest('hex')};
  fs.writeFileSync(process.env.NEX_EDITOR_REPORT, JSON.stringify(report,null,2)+'\n');
}

module.exports = {run};
