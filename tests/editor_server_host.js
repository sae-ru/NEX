'use strict';
const vscode = require('vscode');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');

function deferred(name) {
  let resolve, reject;
  const promise = new Promise((yes, no) => {resolve=yes;reject=no;});promise.catch(()=>{});
  const timer=setTimeout(()=>reject(new Error('Timed out waiting for '+name)),120000);
  return {promise,resolve,reject,cancel(){clearTimeout(timer);}};
}

async function run() {
  const folder=vscode.workspace.workspaceFolders?.[0];assert.ok(folder);assert.equal(vscode.workspace.isTrusted,true);
  const extension=vscode.extensions.getExtension('sae-ru.nex-language-tools');assert.ok(extension);
  assert.equal(extension.packageJSON.version,'0.7.0');
  assert.ok(path.resolve(extension.extensionPath).startsWith(path.resolve(process.env.NEX_EDITOR_EXTENSIONS)+path.sep));
  await extension.activate();
  await vscode.workspace.getConfiguration('nex',folder.uri).update('compilerPath',process.env.NEX_EDITOR_COMPILER,vscode.ConfigurationTarget.Workspace);
  const source=vscode.Uri.joinPath(folder.uri,'core/main.nex');
  const document=await vscode.workspace.openTextDocument(source);await vscode.window.showTextDocument(document);
  const line=document.getText().split('\n').findIndex(text=>text.includes('return prefix+body;'));assert.ok(line>=0);
  const breakpoint=new vscode.SourceBreakpoint(new vscode.Location(source,new vscode.Position(line,0)));vscode.debug.addBreakpoints([breakpoint]);
  const stopped=deferred('server provider breakpoint'),listening=deferred('server listener'),terminated=deferred('server termination');
  const output=[];let current,pid,exitCode,chooser;
  const tracker=vscode.debug.registerDebugAdapterTrackerFactory('nex',{createDebugAdapterTracker(session){
    current=session;return {onDidSendMessage(message){
      if(message.type!=='event')return;
      if(message.event==='process')pid=message.body.systemProcessId;
      if(message.event==='stopped')stopped.resolve(message.body);
      if(message.event==='exited')exitCode=message.body.exitCode;
      if(message.event==='terminated'){
        terminated.resolve(message.body);stopped.reject(new Error('Server terminated before its breakpoint.'));
        listening.reject(new Error('Server terminated before listening.'));
      }
      if(message.event==='output'){
        output.push(message.body);
        const match=output.map(row=>row.output).join('').match(/NEX server http:\/\/127\.0\.0\.1:([0-9]+)/);
        if(match)listening.resolve(Number(match[1]));
      }
    }};
  }});
  try {
    chooser=setInterval(()=>{void vscode.commands.executeCommand('workbench.action.acceptSelectedQuickOpenItem');},100);
    assert.equal(await vscode.commands.executeCommand('nex.debugProject'),true);clearInterval(chooser);chooser=undefined;
    const port=await listening.promise;
    const token=fs.readFileSync(process.env.NEX_EDITOR_SERVER_TOKEN_FILE,'utf8').trim();assert.ok(token);
    const request=new Promise((resolve,reject)=>{
      const call=http.request({host:'127.0.0.1',port,path:'/api/debug',method:'POST',
        headers:{Authorization:'Bearer '+token,'Content-Type':'text/plain','Content-Length':7}},response=>{
          let body='';response.setEncoding('utf8');response.on('data',part=>{body+=part;});
          response.on('end',()=>{try{resolve({status:response.statusCode,body:JSON.parse(body)});}catch(error){reject(error);}});
        });
      call.setTimeout(90000,()=>call.destroy(new Error('HTTP debug request timed out')));call.on('error',reject);call.end('payload');
    });request.catch(()=>{});
    const stop=await stopped.promise;assert.equal(stop.reason,'breakpoint');
    const placed=await current.customRequest('setBreakpoints',{source:{path:source.fsPath},breakpoints:[{line:line+1}]});assert.equal(placed.breakpoints[0].verified,true);
    const frame=(await current.customRequest('stackTrace',{threadId:stop.threadId})).stackFrames[0];
    assert.ok(frame.name.includes('render'));assert.equal(fs.realpathSync(frame.source.path),fs.realpathSync(source.fsPath));
    const watch=await current.customRequest('evaluate',{expression:'prefix+body',frameId:frame.id,context:'watch'});
    assert.equal(watch.nex.value,'Я🧠:payload');assert.equal(watch.nex.type,'str');
    const compilation=JSON.parse(fs.readFileSync(path.join(path.dirname(current.configuration.program),'compilation.json'),'utf8'));
    assert.equal(compilation.owned_images.length,2);assert.ok(compilation.units.every(unit=>!unit.identity.startsWith('debug_core::')));
    await current.customRequest('evaluate',{expression:'`process handle -s false -n false -p true SIGTERM',context:'repl'});
    vscode.debug.removeBreakpoints([breakpoint]);await current.customRequest('setBreakpoints',{source:{path:source.fsPath},breakpoints:[]});
    await current.customRequest('continue',{threadId:stop.threadId});
    assert.deepEqual(await request,{status:200,body:'Я🧠:payload'});
    assert.ok(Number.isInteger(pid)&&pid>0);process.kill(pid,'SIGTERM');await terminated.promise;assert.equal(exitCode,0);
    assert.equal(fs.existsSync(path.join(folder.uri.fsPath,'.nex/graph.db')),false);
    assert.ok(!output.some(row=>row.output.includes('E_INTERNAL_LEAK')));
    fs.writeFileSync(process.env.NEX_EDITOR_REPORT,JSON.stringify({ok:true,actual_installed_vsix:true,extension_version:extension.packageJSON.version,
      compiler:process.env.NEX_EDITOR_COMPILER,editor_version:vscode.version,server_project_command_executed:true,runtime_input_exercised:true,
      actual_shared_provider:true,original_provider_breakpoint:true,watch:watch.nex,request_completed:true,native_exit:exitCode,
      graph_not_created:true,controlled_test_profile:true,user_profile_modified:false},null,2)+'\n');
  } finally {
    if(chooser)clearInterval(chooser);stopped.cancel();listening.cancel();terminated.cancel();tracker.dispose();
    if(current)await vscode.debug.stopDebugging(current);vscode.debug.removeBreakpoints([breakpoint]);
  }
}
module.exports={run};
