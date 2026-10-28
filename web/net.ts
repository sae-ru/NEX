import type { Command } from './program.ts';
import { NexError, string as nexString, parseJSON, decodeJSON, isOk, unwrap, TYPE } from './nex-runtime.ts';
import type { Schema, Value, RecordValue } from './nex-runtime.ts';

type Delivery = (action: string, id: string, status: number, body: string, code: string, message: string) => void;
type Pending = { command: Command; controller: AbortController; timer: ReturnType<typeof setTimeout> };
type Prepared = { command: Command; body: string; schema?: Schema };
const byteLimit = 1024 * 1024;
const encoder = new TextEncoder();
function invalid(message: string): never { throw new NexError('E_REQUEST', message); }
// Deployment configuration belongs to the trusted host, never to a Command.
// Accept one canonical HTTPS origin; paths, credentials and opaque origins fail.
export function apiOrigin(value: string): string {
  try {
    const url = new URL(value);
    if (value.length > 300 || !/^https:\/\/[a-z0-9.-]+(?::[1-9][0-9]{0,4})?$/.test(value) ||
        url.origin !== value || url.username || url.password || url.port === '0' ||
        url.hostname.length > 253 || !url.hostname.split('.').every(label =>
          /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/.test(label))) invalid('Invalid HTTPS API origin');
    return value;
  } catch { invalid('Invalid HTTPS API origin'); }
}

export function configuredAPIOrigin(document: Pick<Document, 'querySelectorAll'>): string | undefined {
  const entries = document.querySelectorAll('meta[name="nex-api-origin"]');
  if (!entries.length) return undefined;
  if (entries.length !== 1) invalid('API origin must be configured once');
  return apiOrigin(entries[0].getAttribute('content') ?? '');
}
function text(value: unknown): asserts value is string {
  if (typeof value !== 'string') invalid('Command fields must be strings');
  nexString(value);
}
function object(value: unknown): value is Record<string, unknown> { return value !== null && typeof value === 'object' && !Array.isArray(value); }
function wireSchema(text: string): Schema {
  if (encoder.encode(text).length > 262144) invalid('Endpoint schema exceeds 256 KiB');
  const value = parseJSON(text);
  if (!object(value) || !object(value.records) || !((value.schema === 'nex.wire/1' && Object.keys(value).sort().join(',') === 'records,root,schema') || (value.schema === 'nex.wire/2' && Object.keys(value).sort().join(',') === 'enums,records,root,schema' && object(value.enums)))) invalid('Invalid endpoint wire schema');
  const records = value.records, enums = value.schema === 'nex.wire/2' ? value.enums as Record<string, unknown> : {};
  if (Object.keys(records).length + Object.keys(enums).length > 1024) invalid('Endpoint schema has too many nominal types');
  let nodes = 0;
  function descriptor(type: unknown, depth: number): void {
    if (++nodes > 10000 || depth > 64) invalid('Endpoint schema exceeds structural limits');
    if (type === 'i64' || type === 'str' || type === 'bool') return;
    if (!object(type) || Object.keys(type).length !== 1) invalid('Invalid endpoint type');
    if ('list' in type) descriptor(type.list, depth + 1);
    else if ('result' in type) descriptor(type.result, depth + 1);
    else if ('enum' in type) { if (typeof type.enum !== 'string' || !Object.prototype.hasOwnProperty.call(enums, type.enum)) invalid('Unknown endpoint enum'); }
    else if (typeof type.record !== 'string' || !Object.prototype.hasOwnProperty.call(records, type.record)) invalid('Unknown endpoint record');
  }
  function fieldsCheck(fields: unknown): void {
    if (!Array.isArray(fields) || fields.length > 1024) invalid('Invalid endpoint fields');
    const names = new Set<string>();
    for (const field of fields) {
      if (!object(field) || Object.keys(field).sort().join(',') !== 'name,type' || typeof field.name !== 'string' || !/^[A-Za-z_][A-Za-z0-9_]*(?![\s\S])/.test(field.name) || names.has(field.name)) invalid('Invalid endpoint field');
      names.add(field.name); descriptor(field.type, 0);
    }
  }
  for (const fields of Object.values(records)) fieldsCheck(fields);
  for (const variants of Object.values(enums)) {
    if (!Array.isArray(variants) || variants.length < 1 || variants.length > 1024) invalid('Invalid endpoint variants');
    const names = new Set<string>();
    for (const variant of variants) {
      if (!object(variant) || Object.keys(variant).sort().join(',') !== 'fields,name' || typeof variant.name !== 'string' || !/^[A-Za-z_][A-Za-z0-9_]*(?![\s\S])/.test(variant.name) || names.has(variant.name)) invalid('Invalid endpoint variant');
      names.add(variant.name); fieldsCheck(variant.fields);
    }
  }
  descriptor(value.root, 0); return value as Schema;
}
type TypedPayload = RecordValue & { readonly [TYPE]: 'std::net::TypedPayload'; readonly body: string; readonly schema: string };
const payloadSchema: Schema = { schema: 'nex.wire/1', root: { record: 'std::net::TypedPayload' }, records: { 'std::net::TypedPayload': [{ name: 'body', type: 'str' }, { name: 'schema', type: 'str' }] } };

// A runner belongs to one mounted application. It retains only pending/queued work.
export class RequestRunner {
  private pending = new Map<string, Pending>();
  private queued = new Set<string>();
  private closed = false;
  private base: URL;
  private deliver: Delivery;
  private fetcher: typeof fetch;
  private mode: RequestMode;
  constructor(deliver: Delivery, base = globalThis.location?.href ?? 'http://localhost/', fetcher: typeof fetch = globalThis.fetch.bind(globalThis), origin?: string) {
    this.base = new URL(origin === undefined ? base : apiOrigin(origin));
    this.mode = origin === undefined ? 'same-origin' : 'cors';
    this.deliver = deliver; this.fetcher = fetcher;
  }

  private prepare(commands: ReadonlyArray<Command>): Map<string, Prepared> {
    if (!Array.isArray(commands) || commands.length > 64) invalid('At most 64 commands are allowed per event');
    // Validate the entire batch before sending, aborting or changing anything.
    const active = new Set(this.pending.keys()), started = new Set<string>();
    const prepared = new Map<string, Prepared>();
    for (const command of commands) {
      if (!command || typeof command !== 'object') invalid('Invalid command');
      for (const field of ['kind', 'id', 'method', 'path', 'body', 'token', 'action'] as const) text(command[field]);
      if (command.kind === 'cancel_all') { active.clear(); continue; }
      if (!command.id || encoder.encode(command.id).length > 128 || /[\u0000-\u001f\u007f]/.test(command.id)) invalid('Invalid request identifier');
      if (command.kind === 'cancel') { active.delete(command.id); continue; }
      if (command.kind !== 'request' && command.kind !== 'typed_request') invalid('Unsupported command kind');
      if (this.pending.has(command.id) || this.queued.has(command.id) || started.has(command.id)) invalid('Request identifier is already in use');
      if (!['GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'].includes(command.method)) invalid('Unsupported request method');
      if (!command.action || encoder.encode(command.action).length > 128) invalid('Invalid response action');
      if (!command.path.startsWith('/api/') || /[\\\u0000-\u0020\u007f]/.test(command.path) || encoder.encode(command.path).length > 2048) invalid('Requests require an /api/ path on the configured origin');
      if (!['http:', 'https:'].includes(this.base.protocol)) invalid('Requests require an HTTP(S) application origin');
      const url = new URL(command.path, this.base);
      if (url.origin !== this.base.origin || !url.pathname.startsWith('/api/') || url.hash || url.username || url.password) invalid('Requests require a same-origin /api/ path');
      if (command.token && !/^[\x21-\x7e]{1,4096}(?![\s\S])/.test(command.token)) invalid('Invalid bearer credential');
      if (typeof command.timeout_ms !== 'bigint' || command.timeout_ms < 1n || command.timeout_ms > 60000n) invalid('Request timeout must be 1..60000 milliseconds');
      if (encoder.encode(command.body).length > byteLimit) invalid('Request body exceeds 1 MiB');
      let body = command.body, schema: Schema | undefined;
      if (command.kind === 'typed_request') {
        const payload = decodeJSON<TypedPayload>(command.body, payloadSchema);
        if (!isOk(payload)) invalid('Invalid typed request payload');
        body = unwrap(payload).body;
        try { schema = wireSchema(unwrap(payload).schema); } catch { invalid('Invalid endpoint wire schema'); }
      }
      if ((command.method === 'GET' || command.method === 'HEAD') && body) invalid('GET/HEAD cannot have a body');
      prepared.set(command.id, { command, body, schema });
      started.add(command.id); active.add(command.id);
      if (active.size > 32) invalid('At most 32 requests may be pending');
    }
    return prepared;
  }
  validate(commands: ReadonlyArray<Command>): void { if (!this.closed) this.prepare(commands); }
  run(commands: ReadonlyArray<Command>): void {
    if (this.closed) return;
    const prepared = this.prepare(commands);
    for (const command of commands) {
      if (command.kind === 'cancel_all') {
        for (const pending of [...this.pending.values()]) this.finish(pending, 0, '', 'E_CANCELED', 'Request canceled');
      } else if (command.kind === 'cancel') {
        const pending = this.pending.get(command.id);
        if (pending) this.finish(pending, 0, '', 'E_CANCELED', 'Request canceled');
      } else this.start(prepared.get(command.id)!);
    }
  }

  private finish(pending: Pending, status: number, body: string, code = '', message = ''): void {
    const command = pending.command;
    if (this.closed || this.pending.get(command.id) !== pending) return;
    this.pending.delete(command.id); clearTimeout(pending.timer);
    if (code) pending.controller.abort();
    this.queued.add(command.id);
    queueMicrotask(() => {
      this.queued.delete(command.id);
      if (!this.closed) this.deliver(command.action, command.id, status, body, code, message);
    });
  }

  private start(prepared: Prepared): void {
    const { command, body: requestBody, schema } = prepared;
    const controller = new AbortController();
    const pending: Pending = { command, controller, timer: setTimeout(() => {
      this.finish(pending, 0, '', 'E_TIMEOUT', 'Request timed out; mutation outcome may be unknown');
    }, Number(command.timeout_ms)) };
    this.pending.set(command.id, pending);
    void (async () => {
      let status = 0;
      try {
        const response = await this.fetcher(new URL(command.path, this.base), {
          method: command.method, body: command.method === 'GET' || command.method === 'HEAD' ? undefined : requestBody,
          headers: { Accept: 'application/json', 'Content-Type': 'application/json', ...(command.token ? { Authorization: 'Bearer ' + command.token } : {}) },
          credentials: 'omit', mode: this.mode, redirect: 'error', cache: 'no-store', referrerPolicy: 'same-origin', signal: controller.signal,
        });
        status = response.status;
        const length = response.headers.get('Content-Length');
        if (length && /^[0-9]+(?![\s\S])/.test(length) && BigInt(length) > BigInt(byteLimit)) {
          this.finish(pending, status, '', 'E_LIMIT', 'Response body exceeds 1 MiB'); return;
        }
        const reader = response.body?.getReader();
        const decoder = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true });
        let size = 0, body = '';
        try {
          if (reader) while (true) {
            const chunk = await reader.read();
            if (chunk.done) break;
            size += chunk.value.byteLength;
            if (size > byteLimit) { this.finish(pending, status, '', 'E_LIMIT', 'Response body exceeds 1 MiB'); return; }
            try { body += decoder.decode(chunk.value, { stream: true }); }
            catch { this.finish(pending, status, '', 'E_UTF8', 'Response is not valid UTF-8'); return; }
          }
          try { body += decoder.decode(); }
          catch { this.finish(pending, status, '', 'E_UTF8', 'Response is not valid UTF-8'); return; }
        } finally { reader?.releaseLock(); }
        if (schema && status >= 200 && status < 300 && !isOk(decodeJSON<Value>(body, schema))) {
          this.finish(pending, status, '', 'E_JSON', 'Response does not match the endpoint contract'); return;
        }
        this.finish(pending, status, body);
      } catch {
        this.finish(pending, status, '', 'E_NETWORK', 'Request failed; mutation outcome may be unknown');
      }
    })();
  }

  close(): void {
    this.closed = true;
    for (const pending of this.pending.values()) { clearTimeout(pending.timer); pending.controller.abort(); }
    this.pending.clear(); this.queued.clear();
  }
}
