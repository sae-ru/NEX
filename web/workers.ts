import type { WorkerCommand } from './program.ts';
import { NexError, TYPE, string as checkedString, encodeJSON, decodeJSON, isOk, unwrap } from './nex-runtime.ts';
import type { Value } from './nex-runtime.ts';
import { inputSchema, outputSchema } from './worker-contract.ts';

type Delivery = (action: string, id: string, body: string, code: string, message: string) => void;
type Port = Pick<Worker, 'postMessage' | 'terminate' | 'onmessage' | 'onerror' | 'onmessageerror'>;
type Prepared = { kind: string; id: string; action: string; timeout: number; body: string };
type Pending = { command: Prepared; ticket: number; timer: ReturnType<typeof setTimeout>; port?: Port };
const encoder = new TextEncoder(), byteLimit = 1024 * 1024;
function invalid(message: string): never { throw new NexError('E_WORKER_COMMAND', message); }
function text(value: unknown): asserts value is string {
  if (typeof value !== 'string') invalid('Worker fields must be strings');
  try { checkedString(value); } catch { invalid('Worker fields require Unicode scalar strings'); }
}
function identifier(value: string): void {
  if (!value || encoder.encode(value).length > 128 || /[\u0000-\u001f\u007f]/.test(value)) invalid('Invalid worker identifier');
}

// One mounted application owns these jobs. Every running job has a dedicated
// worker; terminating it cannot interrupt another job's code or cleanup.
export class WorkerRunner {
  private pending = new Map<string, Pending>();
  private delivering = new Set<string>();
  private closed = false;
  private running = 0;
  private ticket = 0;
  private deliver: Delivery;
  private factory: () => Port;
  constructor(deliver: Delivery, factory: () => Port = () => new Worker(new URL('./worker-entry.ts', import.meta.url), { type: 'module' })) {
    this.deliver = deliver; this.factory = factory;
  }

  private prepare(commands: ReadonlyArray<WorkerCommand>): Prepared[] {
    if (!Array.isArray(commands) || commands.length > 64) invalid('At most 64 worker commands are allowed per event');
    const active = new Set(this.pending.keys()), started = new Set<string>();
    const prepared = commands.map(command => {
      if (!command || typeof command !== 'object') invalid('Invalid worker command');
      for (const field of ['kind', 'id', 'action'] as const) text(command[field]);
      const { kind, id, action } = command;
      if (kind === 'cancel_all') { active.clear(); return { kind, id, action, timeout: 0, body: '' }; }
      identifier(id);
      if (kind === 'cancel') { active.delete(id); return { kind, id, action, timeout: 0, body: '' }; }
      if (kind !== 'request') invalid('Unsupported worker command kind');
      if (this.pending.has(id) || this.delivering.has(id) || started.has(id)) invalid('Worker identifier is already in use');
      identifier(action);
      if (typeof command.timeout_ms !== 'bigint' || command.timeout_ms < 1n || command.timeout_ms > 60000n) invalid('Worker timeout must be 1..60000 milliseconds');
      if (!command.input || typeof command.input !== 'object' || command.input[TYPE] !== 'nex.result.ok') invalid('Worker request requires a successful typed input');
      let body: string;
      try {
        body = encodeJSON(unwrap(command.input));
        if (!isOk(decodeJSON<Value>(body, inputSchema))) invalid('Worker input does not match its handler');
      } catch { invalid('Worker input exceeds wire limits or does not match its handler'); }
      started.add(id); active.add(id);
      if (active.size > 32) invalid('At most 32 worker jobs may be pending');
      return { kind, id, action, timeout: Number(command.timeout_ms), body };
    });
    if (this.ticket > Number.MAX_SAFE_INTEGER - started.size) invalid('Worker ticket space exhausted');
    return prepared;
  }
  validate(commands: ReadonlyArray<WorkerCommand>): void { if (!this.closed) this.prepare(commands); }
  run(commands: ReadonlyArray<WorkerCommand>): void {
    if (this.closed) return;
    const prepared = this.prepare(commands);
    for (const command of prepared) {
      if (command.kind === 'cancel_all') {
        for (const job of [...this.pending.values()]) this.finish(job, '', 'E_CANCELED', 'Worker canceled');
      } else if (command.kind === 'cancel') {
        const job = this.pending.get(command.id);
        if (job) this.finish(job, '', 'E_CANCELED', 'Worker canceled');
      } else {
        if (this.ticket >= Number.MAX_SAFE_INTEGER) invalid('Worker ticket space exhausted');
        const job: Pending = { command, ticket: ++this.ticket, timer: setTimeout(() => this.finish(job, '', 'E_TIMEOUT', 'Worker timed out'), command.timeout) };
        this.pending.set(command.id, job);
      }
    }
    this.pump();
  }
  private pump(): void {
    if (this.closed) return;
    for (const job of this.pending.values()) {
      if (this.running >= 2) break;
      if (job.port) continue;
      try {
        const port = this.factory(); job.port = port; ++this.running;
        port.onmessage = event => {
          if (this.closed || this.pending.get(job.command.id) !== job) return;
          try {
            const data: unknown = event.data;
            if (!data || typeof data !== 'object' || Array.isArray(data) || Object.keys(data).sort().join(',') !== 'body,code,message,protocol,ticket') throw new Error();
            const item = data as Record<string, unknown>;
            if (item.protocol !== 'nex.worker/1' || item.ticket !== job.ticket || typeof item.body !== 'string' || typeof item.code !== 'string' || typeof item.message !== 'string') throw new Error();
            checkedString(item.body); checkedString(item.message);
            if (encoder.encode(item.body).length > byteLimit || encoder.encode(item.message).length > 1024 || (item.code && !/^[A-Z][A-Z0-9_]{0,63}$/.test(item.code))) throw new Error();
            if (!item.code && !isOk(decodeJSON<Value>(item.body, outputSchema))) throw new Error();
            this.finish(job, item.body, item.code, item.message);
          } catch { this.finish(job, '', 'E_WORKER_PROTOCOL', 'Invalid worker response'); }
        };
        port.onerror = event => { event.preventDefault(); this.finish(job, '', 'E_WORKER', 'Worker execution failed'); };
        port.onmessageerror = () => this.finish(job, '', 'E_WORKER_PROTOCOL', 'Worker message could not be decoded');
        port.postMessage({ protocol: 'nex.worker/1', ticket: job.ticket, body: job.command.body });
      } catch { this.finish(job, '', 'E_WORKER', 'Worker could not be started'); }
    }
  }
  private finish(job: Pending, body: string, code = '', message = ''): void {
    if (this.closed || this.pending.get(job.command.id) !== job) return;
    this.pending.delete(job.command.id); clearTimeout(job.timer);
    if (job.port) { job.port.onmessage = null; job.port.onerror = null; job.port.onmessageerror = null; job.port.terminate(); --this.running; }
    this.delivering.add(job.command.id);
    queueMicrotask(() => {
      this.delivering.delete(job.command.id);
      if (this.closed) return;
      try { this.deliver(job.command.action, job.command.id, body, code, message); }
      finally { this.pump(); }
    });
  }
  close(): void {
    this.closed = true;
    for (const job of this.pending.values()) { clearTimeout(job.timer); job.port?.terminate(); }
    this.pending.clear(); this.delivering.clear(); this.running = 0;
  }
}
