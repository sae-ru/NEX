'use strict';

const {spawn} = require('node:child_process');
const {EventEmitter} = require('node:events');
const {TextDecoder} = require('node:util');

const MESSAGE_LIMIT = 16 * 1024 * 1024;
const HEADER_LIMIT = 8192;

class LanguageClient extends EventEmitter {
  constructor(compiler, cwd, options = {}) {
    super();
    if (typeof compiler !== 'string' || !compiler.length || compiler.includes('\0')) throw new Error('Select a NEX compiler executable.');
    this.timeout = options.timeout ?? 45000;
    this.pending = new Map();
    this.nextId = 0;
    this.buffer = Buffer.alloc(0);
    this.length = null;
    this.closed = false;
    this.closing = false;
    this.stderr = '';
    this.exited = new Promise(resolve => {this.resolveExit = resolve;});
    this.child = (options.spawn || spawn)(compiler, ['lsp'], {cwd, shell: false, windowsHide: true, stdio: ['pipe', 'pipe', 'pipe']});
    this.child.stdout.on('data', data => this.receive(data));
    this.child.stderr.on('data', data => {this.stderr = (this.stderr + data.toString('utf8')).slice(-16384);});
    this.child.stdin.on('error', error => this.fail(error));
    this.child.on('error', error => this.fail(error));
    this.child.on('close', (code, signal) => {
      this.resolveExit();
      this.fail(new Error(`NEX language server closed (${signal || code})${this.stderr ? ': ' + this.stderr.trim() : ''}`));
    });
  }

  fail(error) {
    if (this.closed) return;
    this.closed = true;
    for (const item of this.pending.values()) {
      clearTimeout(item.timer);
      item.cancel?.dispose();
      item.reject(error);
    }
    this.pending.clear();
    this.child.stdin.end();
    if (!this.closing) this.emit('failure', error);
  }

  send(message) {
    if (this.closed) throw new Error('NEX language server is closed.');
    const raw = Buffer.from(JSON.stringify({jsonrpc: '2.0', ...message}), 'utf8');
    if (raw.length > MESSAGE_LIMIT || this.child.stdin.writableLength > 2 * MESSAGE_LIMIT) throw new Error('NEX language server message limit exceeded.');
    this.child.stdin.write(Buffer.concat([Buffer.from(`Content-Length: ${raw.length}\r\n\r\n`, 'ascii'), raw]));
  }

  notify(method, params) {
    this.send({method, ...(params === undefined ? {} : {params})});
  }

  request(method, params, token) {
    if (token?.isCancellationRequested) return Promise.reject(Object.assign(new Error('Request cancelled'), {code: -32800}));
    if (this.pending.size >= 128) return Promise.reject(new Error('Too many NEX language server requests.'));
    const id = ++this.nextId;
    return new Promise((resolve, reject) => {
      const item = {resolve, reject};
      const finish = error => {
        if (!this.pending.delete(id)) return;
        clearTimeout(item.timer);
        item.cancel?.dispose();
        try {this.notify('$/cancelRequest', {id});} catch (_) {}
        reject(error);
      };
      item.timer = setTimeout(() => finish(new Error('NEX language server request timed out.')), this.timeout);
      this.pending.set(id, item);
      if (token) item.cancel = token.onCancellationRequested(() => finish(Object.assign(new Error('Request cancelled'), {code: -32800})));
      try {this.send({id, method, ...(params === undefined ? {} : {params})});}
      catch (error) {finish(error);}
    });
  }

  receive(data) {
    if (this.closed) return;
    try {
      this.buffer = Buffer.concat([this.buffer, data]);
      for (;;) {
        if (this.length === null) {
          const end = this.buffer.indexOf('\r\n\r\n');
          if (end < 0) {
            if (this.buffer.length > HEADER_LIMIT) throw new Error('Oversized NEX LSP header.');
            return;
          }
          if (end + 4 > HEADER_LIMIT) throw new Error('Oversized NEX LSP header.');
          if (this.buffer.subarray(0, end).some(byte => byte > 127)) throw new Error('Non-ASCII NEX LSP header.');
          const headers = new Map();
          for (const line of this.buffer.subarray(0, end).toString('ascii').split('\r\n')) {
            const colon = line.indexOf(':');
            const key = line.slice(0, colon).toLowerCase(), value = line.slice(colon + 1).trim();
            if (colon <= 0 || headers.has(key)) throw new Error('Malformed NEX LSP header.');
            headers.set(key, value);
          }
          const length = headers.get('content-length');
          if (!/^\d+$/.test(length || '') || !Number.isSafeInteger(Number(length)) || Number(length) < 1 || Number(length) > MESSAGE_LIMIT) throw new Error('Invalid NEX LSP Content-Length.');
          this.length = Number(length);
          this.buffer = this.buffer.subarray(end + 4);
        }
        if (this.buffer.length < this.length) return;
        const raw = this.buffer.subarray(0, this.length);
        this.buffer = this.buffer.subarray(this.length);
        this.length = null;
        const message = JSON.parse(new TextDecoder('utf-8', {fatal: true}).decode(raw));
        if (!message || typeof message !== 'object' || Array.isArray(message) || message.jsonrpc !== '2.0') throw new Error('Invalid NEX LSP response.');
        if (typeof message.method === 'string') {
          if (Object.hasOwn(message, 'id')) this.send({id: message.id, error: {code: -32601, message: 'Client method is unsupported.'}});
          else this.emit('notification', message.method, message.params);
        } else {
          const item = this.pending.get(message.id);
          if (!item) continue; // Cancellation and timeouts can leave late responses.
          this.pending.delete(message.id);
          clearTimeout(item.timer);
          item.cancel?.dispose();
          if (message.error) item.reject(Object.assign(new Error(String(message.error.message)), {code: message.error.code}));
          else if (Object.hasOwn(message, 'result')) item.resolve(message.result);
          else item.reject(new Error('NEX LSP response omitted its result.'));
        }
      }
    } catch (error) {this.fail(error);}
  }

  async start(rootUri) {
    const initialized = await this.request('initialize', {
      processId: process.pid, rootUri,
      capabilities: {general: {positionEncodings: ['utf-16']}, textDocument: {publishDiagnostics: {versionSupport: true}}}
    });
    const caps = initialized?.capabilities;
    if (caps?.positionEncoding !== 'utf-16' || caps.textDocumentSync?.change !== 1 || !caps.hoverProvider || !caps.definitionProvider || !caps.documentSymbolProvider) {
      throw new Error('Select NEX 0.66 or newer with its matching language-server resources.');
    }
    this.notify('initialized', {});
    return initialized;
  }

  async dispose() {
    if (this.disposing) return this.disposing;
    this.closing = true;
    this.disposing = (async () => {
      try {
        if (!this.closed) {
          await Promise.race([this.request('shutdown'), new Promise(resolve => {const timer = setTimeout(resolve, 3000); timer.unref?.();})]);
          if (!this.closed) this.notify('exit');
        }
      } catch (_) {}
      this.child.stdin.end();
      await Promise.race([this.exited, new Promise(resolve => {const timer = setTimeout(resolve, 2000); timer.unref?.();})]);
      if (this.child.exitCode === null && this.child.signalCode === null) this.child.kill();
      this.fail(new Error('NEX language client disposed.'));
    })();
    return this.disposing;
  }
}

module.exports = {LanguageClient};
