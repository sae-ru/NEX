// Checked resumable TypeScript backend. No serialized AST/IR or native scheduler.
import * as nex from './nex-runtime.ts';
type Item = nex.Value | void;
declare const outcome: unique symbol;
export interface Call<T extends Item> extends nex.RecordValue { readonly [outcome]?: T }
export interface Scope extends nex.RecordValue {}
export interface Future<T extends Item> extends nex.RecordValue { readonly [outcome]?: T }
export interface Channel<T extends nex.Value> extends nex.RecordValue { readonly [outcome]?: T }
declare const pendingType: unique symbol;
declare const hostWaitType: unique symbol;
export interface Pending<T extends nex.Value> { readonly [pendingType]: T }
type HostWait = Readonly<{ [hostWaitType]: true }>;
export type Step<T extends Item> = Generator<Request | HostWait, T, Item>;
export type Request = Readonly<{ operation: string; arguments: ReadonlyArray<nex.Value>; site?: nex.Site }>;
// Private trusted-host bridge. settled must mean physical quiescence, including
// operation-owned buffers/readers. cancel is a request, never proof of settlement.
// start may throw only before physical work exists. Once work has started, the
// trusted adapter must return its settlement Promise even on eventual failure.
export type HostOperation = Readonly<{ settled: Promise<unknown>; cancel: () => void }>;
export const hostQuotas = Object.freeze({pending: 64, payloadBytes: 1048576, reservedBytes: 8388608});
type HostStamp = { owner: WeakRef<Driver>; job: number; index: number; generation: number };
const hostTickets = new WeakMap<object, HostStamp>();
const hostWaits = new WeakMap<object, HostStamp>();
type Invocation = { factory: () => Step<Item>; inputs: ReadonlyArray<nex.Value> };
const invocations = new WeakMap<object, Invocation>();
const requests = new WeakSet<object>();
const requestArity = new Map([['$poll',0],['task_yield',0],['with_tasks',2],['task_spawn',2],['task_wait',1],['channel_new',2],['task_send',2],['task_recv',1],['task_close',1],['task_cancel',1],['current_task_scope',0]]);
type Cap = { owner: WeakRef<Driver>; scope: number; index: number; kind: 'task_scope' | 'task' | 'channel' };
const capabilities = new WeakMap<object, Cap>();
let active: { driver: Driver; job: number } | undefined;
const none = -1;
function fail(code: string, message: string, site?: nex.Site): never { throw new nex.NexError(code, message, site); }
function context(): { driver: Driver; job: number } {
  if (!active) fail('E_TASK_STATE', 'task code requires an active generator resume'); return active;
}
// payloadBytes reserves retained raw capacity, not total memory allocated by
// trusted host code. Adapters must copy small views or charge their full backing
// storage. Admission also charges a bounded copied NEX value against this cap.
export function hostPending<T extends nex.Value>(start: () => HostOperation, admit: (raw: unknown) => T, payloadBytes: number, site?: nex.Site): Pending<T> {
  const {driver, job} = context(); return driver.reserveHost(job, start, admit, payloadBytes, site);
}
export function* hostAwait<T extends nex.Value>(ticket: Pending<T>): Step<T> {
  const {driver, job} = context(); return (yield driver.awaitHost(job, ticket)) as T;
}
export function call<T extends Item>(factory: () => Step<T>, inputs: ReadonlyArray<nex.Value> = []): Call<T> {
  const value = nex.record<Call<T>>('nex.private.invocation', []);
  invocations.set(value, {factory, inputs: Object.freeze([...inputs])}); return value;
}
function take<T extends Item>(value: Call<T>, site?: nex.Site): Step<T> {
  const invocation = value && invocations.get(value);
  if (!invocation) fail('E_TASK_STATE', 'invalid or consumed task invocation', site);
  invocations.delete(value); return invocation.factory() as Step<T>;
}
export function* invoke<T extends Item>(value: Call<T>, site?: nex.Site): Step<T> { return yield* take(value, site); }
export function request(operation: string, arguments_: ReadonlyArray<nex.Value>, site?: nex.Site): Request {
  if (!Array.isArray(arguments_) || requestArity.get(operation) !== arguments_.length) fail('E_TASK_STATE', 'unknown task request or incorrect argument count', site);
  const value = Object.freeze({operation, arguments: Object.freeze([...arguments_]), site}); requests.add(value); return value;
}
export function enter(site?: nex.Site): void {
  const {driver, job} = context(); driver.charge(site);
  if (driver.jobs[job].calls >= 256) fail('E_LIMIT', 'task call depth exceeds256', site);
  ++driver.jobs[job].calls;
}
export function leave(): void {
  const {driver, job} = context(); if (driver.jobs[job].calls < 1) fail('E_TASK_STATE', 'unbalanced generator call depth'); --driver.jobs[job].calls;
}
export function* checkpoint(site?: nex.Site): Step<void> {
  const {driver, job} = context(); driver.charge(site);
  if (++driver.jobs[job].polls >= 64) { driver.jobs[job].polls = 0; yield request('$poll', [], site); }
}
export function* parallelMap<T extends nex.Value, U extends nex.Value>(items: ReadonlyArray<T>, callback: (item: T) => Call<U>, workers: bigint, site?: nex.Site): Step<ReadonlyArray<U>> {
  if (workers < 1n || workers > 16n) fail('E_RANGE', 'parallel worker count must be in1..16', site);
  if (items.length > 65536) fail('E_LIMIT', 'parallel input exceeds65536 items', site);
  nex.validateParallelValue(items, site); nex.validateParallelValue(callback, site);
  const result: U[] = []; let failure: nex.NexError | undefined;
  for (const item of items) {
    yield* checkpoint(site);
    try { const value = yield* invoke(callback(item), site); nex.validateParallelValue(value, site); result.push(value); }
    catch (error) {
      if (!(error instanceof nex.NexError) || resource(error)) throw error;
      if (!failure) failure = error;
    }
  }
  if (failure) throw failure; return nex.list(result);
}
type State = 'ready' | 'future' | 'send' | 'receive' | 'external' | 'drain' | 'finishing' | 'done';
// Fixed reserved channel/ready slots have constant-time FIFO operations and
// release a consumed reference immediately. Waiter indices grow only as needed.
class Ring<T> {
  private storage: (T | undefined)[];
  private start=0;
  private count=0;
  constructor(capacity: number) { this.storage=new Array<T | undefined>(capacity); }
  get length(): number { return this.count; }
  push(value: T): void {
    if(this.count>=this.storage.length)fail('E_TASK_STATE','bounded task queue overflow');
    this.storage[(this.start+this.count)%this.storage.length]=value;++this.count;
  }
  shift(): T | undefined {
    if(!this.count)return undefined;
    const value=this.storage[this.start];this.storage[this.start]=undefined;
    this.start=(this.start+1)%this.storage.length;--this.count;return value;
  }
  clear(): void { this.storage.length=0;this.start=this.count=0; }
}
class Waiters {
  private storage: (number | undefined)[]=[];
  private start=0;
  get length(): number { return this.storage.length-this.start; }
  push(value: number): void { this.storage.push(value); }
  shift(): number | undefined {
    if(!this.length)return undefined;
    const value=this.storage[this.start];this.storage[this.start++]=undefined;
    if(this.start===this.storage.length){this.storage.length=0;this.start=0;}
    else if(this.start>4096&&this.start*2>=this.storage.length){this.storage=this.storage.slice(this.start);this.start=0;}
    return value;
  }
}
type Activation = { iterator: Step<Item>; scope: number; parent: number; site?: nex.Site; result?: Item; sourceFailure?: object };
type Job = {
  state: State; stack: Activation[]; member: number; current: number; parent: number; spawnDepth: number;
  calls: number; polls: number; cancelled: boolean; queued: boolean; observed: boolean; target: number;
  response?: Item; responseSource?: object; pending?: nex.Value; result?: Item; failure?: Error; sourceFailure?: object; owned: number[]; external: Set<number>; capability?: WeakRef<Future<Item>>;
};
type Region = {
  parent: number; owner: number; depth: number; closing: boolean; closed: boolean; abort: boolean;
  members: number[]; children: number[]; pipes: number[]; external: Set<number>; failure?: Error; sourceFailure?: object; capability?: WeakRef<Scope>;
};
type External = {
  stamp: HostStamp; scope: number; bytes: number; site?: nex.Site;
  state: 'reserved' | 'queued' | 'running' | 'settled' | 'retired'; claimed: boolean;
  start?: () => HostOperation; admit?: (raw: unknown) => nex.Value; cancel?: () => void;
  cancelRequested: boolean; cancelCalled: boolean; raw?: unknown; rejected?: boolean; failure?: nex.NexError;
};
type Pipe = { scope: number; capacity: number; closed: boolean; buffer: Ring<nex.Value>; senders: Waiters; receivers: Waiters; capability?: WeakRef<Channel<nex.Value>> };
export type ExecutionLimits = Readonly<{ steps: number; timeoutMs: number; workers: number }>;
export type Options = { steps?: number; timeoutMs?: number; workers?: number; signal?: AbortSignal; observe?: (job: number, request: Request) => void; complete?: (statistics: Statistics) => void };
export type Statistics = { steps: number; tasks: number; scopes: number; channels: number; completed: boolean; retainedFrames: number; activeCalls: number; limits: ExecutionLimits; actualWorkers: 1; externalPending: number; externalReservedBytes: number; externalMailbox: number; externalStarted: number; externalSettled: number; externalPeakPending: number; externalPeakBytes: number };
function validatedOptions(options: Options): Readonly<Options & ExecutionLimits> {
  if (typeof options !== 'object' || options === null) fail('E_RANGE', 'task options must be an object');
  const steps = options.steps === undefined ? 1000000 : options.steps;
  const timeoutMs = options.timeoutMs === undefined ? 5000 : options.timeoutMs;
  const workers = options.workers === undefined ? 16 : options.workers;
  if (!Number.isSafeInteger(steps) || steps < 1) fail('E_RANGE', 'task budget must be in1..9007199254740991');
  if (!Number.isSafeInteger(timeoutMs) || timeoutMs < 1 || timeoutMs > 3600000) fail('E_RANGE', 'task timeoutMs must be in1..3600000');
  if (!Number.isSafeInteger(workers) || workers < 1 || workers > 16) fail('E_RANGE', 'task workers must be in1..16');
  return Object.freeze({...options, steps, timeoutMs, workers});
}
function resource(error: Error): boolean { return error instanceof nex.NexError && ['E_LIMIT', 'E_MEMORY', 'E_TIMEOUT', 'E_CANCELLED'].includes(error.code); }
function fatalResource(error: unknown): error is nex.NexError { return error instanceof nex.NexError && ['E_LIMIT', 'E_MEMORY', 'E_TIMEOUT'].includes(error.code); }
function prefer(selected: Error | undefined, candidate: Error | undefined): Error | undefined {
  return candidate && (!selected || (!resource(selected) && resource(candidate))) ? candidate : selected;
}
function asError(error: unknown): Error { return error instanceof Error ? error : new Error('non-error thrown by task host'); }
function failed(value: Item): boolean { return typeof value === 'object' && value !== null && (value as nex.RecordValue)[nex.TYPE] === 'nex.result.error'; }
class Driver {
  readonly jobs: Job[] = [];
  readonly regions: Region[] = [];
  readonly pipes: Pipe[] = [];
  readonly ready = new Ring<number>(4096);
  readonly external = new Array<External | undefined>(hostQuotas.pending);
  readonly generations = new Array<number>(hostQuotas.pending).fill(0);
  readonly mailbox = new Ring<HostStamp>(hostQuotas.pending);
  private starts: External[] = [];
  private cancels: External[] = [];
  private wake?: () => void;
  private wakeVersion = 0;
  private externalCount = 0;
  private externalBytes = 0;
  private externalStarted = 0;
  private externalSettled = 0;
  private externalPeakCount = 0;
  private externalPeakBytes = 0;
  readonly options: Readonly<Options & ExecutionLimits>;
  readonly limit: number;
  readonly deadline: number;
  private expired?: nex.NexError;
  private hostFailure?: nex.NexError;
  used = 0; slots = 0; closed = false;
  private rootDone(): boolean { return this.jobs[0].state === 'done'; }
  private readonly sourceClassifier?: (error: unknown) => boolean;
  constructor(options: Options, sourceClassifier?: (error: unknown) => boolean) {
    this.sourceClassifier = sourceClassifier;
    this.options = validatedOptions(options); this.limit = this.options.steps;
    this.deadline = performance.now() + this.options.timeoutMs;
  }
  private sourceError(error: unknown): object | undefined {
    return typeof error === 'object' && error !== null && this.sourceClassifier?.(error) ? error : undefined;
  }
  private checkSourceControl(site?: nex.Site): void {
    this.checkDeadline(site);
    if (this.options.signal?.aborted) fail('E_CANCELLED', 'task execution was cancelled', site);
  }
  checkDeadline(site?: nex.Site): void {
    if (!this.expired && performance.now() >= this.deadline) this.expired = new nex.NexError('E_TIMEOUT', 'shared generator task deadline exceeded', site);
    if (this.expired) throw this.expired;
  }
  charge(site?: nex.Site): void { this.checkDeadline(site); if (this.used >= this.limit) fail('E_LIMIT', 'shared generator task budget exceeded', site); ++this.used; }
  notify(): void { ++this.wakeVersion; const wake = this.wake; this.wake = undefined; wake?.(); }
  outside<T>(callback: () => T): T { const previous = active; active = undefined; try { return callback(); } finally { active = previous; } }
  reserveHost<T extends nex.Value>(job: number, start: () => HostOperation, admit: (raw: unknown) => T, bytes: number, site?: nex.Site): Pending<T> {
    this.charge(site);
    if (this.closed || this.jobs[job].state !== 'ready') fail('E_TASK_STATE', 'host ticket requires a live generator resume', site);
    if (typeof start !== 'function' || typeof admit !== 'function' || !Number.isSafeInteger(bytes) || bytes < 1 || bytes > hostQuotas.payloadBytes) fail('E_RANGE', 'invalid bounded host operation', site);
    if (this.externalCount >= hostQuotas.pending || bytes > hostQuotas.reservedBytes - this.externalBytes) fail('E_LIMIT', 'external operation reservation quota exceeded', site);
    const index = this.external.findIndex(value => value === undefined), generation = ++this.generations[index];
    if (!Number.isSafeInteger(generation)) fail('E_LIMIT', 'external ticket generation exhausted', site);
    const stamp = {owner: new WeakRef(this), job, index, generation}, scope = this.jobs[job].current;
    this.external[index] = {stamp, scope, bytes, site, state: 'reserved', claimed: false, start, admit, cancelRequested: false, cancelCalled: false};
    this.jobs[job].external.add(index); if (scope !== none) this.regions[scope].external.add(index);
    ++this.externalCount; this.externalBytes += bytes;
    this.externalPeakCount = Math.max(this.externalPeakCount, this.externalCount); this.externalPeakBytes = Math.max(this.externalPeakBytes, this.externalBytes);
    const ticket = Object.freeze(Object.create(null)) as Pending<T>; hostTickets.set(ticket, stamp); return ticket;
  }
  hostRecord(stamp: HostStamp, job: number): External {
    const value = this.external[stamp.index];
    if (this.closed || stamp.owner.deref() !== this || stamp.job !== job || !value || value.stamp.generation !== stamp.generation || value.stamp !== stamp) fail('E_TASK_STATE', 'foreign, stale or consumed host ticket');
    if (value.scope !== none) this.access(value.scope, this.jobs[job].current, value.site);
    return value;
  }
  awaitHost<T extends nex.Value>(job: number, ticket: Pending<T>): HostWait {
    const stamp = ticket && typeof ticket === 'object' ? hostTickets.get(ticket) : undefined;
    if (!stamp) fail('E_TASK_STATE', 'expected a branded host ticket');
    const value = this.hostRecord(stamp, job);
    if (value.claimed || value.state !== 'reserved') fail('E_TASK_STATE', 'host ticket may be awaited once', value.site);
    value.claimed = true; const wait = Object.freeze(Object.create(null)) as HostWait; hostWaits.set(wait, stamp); return wait;
  }
  retireHost(value: External): void {
    if (value.state === 'retired') return;
    value.state = 'retired'; const {index, job} = value.stamp;
    this.external[index] = undefined; this.jobs[job].external.delete(index);
    if (value.scope !== none) this.regions[value.scope].external.delete(index);
    --this.externalCount; this.externalBytes -= value.bytes;
    value.raw = value.start = value.admit = value.cancel = value.failure = undefined;
  }
  cancelHost(value: External): void {
    value.cancelRequested = true;
    if (value.state === 'reserved' || value.state === 'queued') this.retireHost(value);
    else if (value.state === 'running' && value.cancel && !value.cancelCalled) { value.cancelCalled = true; this.cancels.push(value); }
  }
  publishHost(value: External, raw: unknown, rejected: boolean, failure?: nex.NexError): void {
    if (this.closed || this.external[value.stamp.index] !== value || value.state !== 'running') return;
    value.state = 'settled'; value.raw = raw; value.rejected = rejected; value.failure = failure; ++this.externalSettled;
    this.mailbox.push(value.stamp); this.notify();
  }
  rejectHost(value: External, error: unknown): void {
    // Retain only a checked fatal code, never an arbitrary host exception or its
    // payload. Physical failure cannot be hidden by cleanup-request cancellation.
    const failure = fatalResource(error) ? new nex.NexError(error.code, 'trusted host resource failure', value.site) : undefined;
    this.publishHost(value, undefined, true, failure);
  }
  stopHost(failure: nex.NexError): void {
    const selected = fatalResource(this.jobs[0].failure) ? this.jobs[0].failure : this.hostFailure ?? failure;
    this.hostFailure = selected;
    for (let i = 0; i < this.jobs.length; ++i) {
      const job = this.jobs[i];
      if (job.state === 'done') continue;
      const next = fatalResource(job.failure) ? job.failure : selected;
      if (job.state === 'finishing') { job.failure = next; job.result = undefined; }
      else this.finish(i, next);
    }
  }
  dispatchHost(job: number, stamp: HostStamp): void {
    const value = this.hostRecord(stamp, job); this.charge(value.site);
    if (value.state !== 'reserved' || !value.claimed) fail('E_TASK_STATE', 'host wait was already dispatched', value.site);
    value.state = 'queued'; this.jobs[job].state = 'external'; this.jobs[job].target = stamp.index; this.starts.push(value);
  }
  flushHost(): void {
    // Complete state transitions before invoking any trusted host callback, and
    // clear the active generator context. Callbacks never resume source frames.
    const cancels = this.cancels; this.cancels = [];
    for (const value of cancels) { try { if (value.cancel) this.outside(value.cancel); } catch { /* still retain the physical settlement lease */ } }
    const starts = this.starts; this.starts = [];
    for (const value of starts) {
      if (value.state !== 'queued') continue;
      if (this.jobs[value.stamp.job].cancelled) { this.cancelHost(value); continue; }
      value.state = 'running'; ++this.externalStarted;
      try {
        const operation = this.outside(value.start!); value.start = undefined;
        if (!operation || !(operation.settled instanceof Promise)) fail('E_HOST', 'host start must supply a settlement Promise', value.site);
        const protocolFailure = typeof operation.cancel !== 'function';
        if (!protocolFailure) value.cancel = operation.cancel;
        // A malformed cancellation hook cannot make an existing operation
        // physically quiescent. Retain even this rejected protocol until settled.
        Promise.prototype.then.call(operation.settled, (raw: unknown) => this.publishHost(value, raw, protocolFailure), (error: unknown) => this.rejectHost(value, error));
        if (value.cancelRequested || this.jobs[value.stamp.job].cancelled) this.cancelHost(value);
      } catch (error) { value.start = undefined; this.rejectHost(value, error); }
    }
  }
  copyHost(root: unknown, budget: number, site?: nex.Site): nex.Value {
    let bytes = 0, nodes = 0; const path = new Set<object>();
    const spend = (count: number) => { if (count > budget - bytes) fail('E_LIMIT', 'host completion exceeds reserved payload capacity', site); bytes += count; };
    const text = (value: string): string => { spend(value.length * 2); return nex.string(value, site); };
    const copy = (value: unknown, depth: number): nex.Value => {
      this.charge(site); spend(8); if (++nodes > 65536 || depth > 64) fail('E_LIMIT', 'host completion graph exceeds its bound', site);
      if (typeof value === 'bigint') return nex.checked(value, site);
      if (typeof value === 'number') return nex.finiteFloat(value, site);
      if (typeof value === 'boolean') return value;
      if (typeof value === 'string') return text(value);
      if (!value || typeof value !== 'object' || capabilities.has(value) || invocations.has(value) || hostTickets.has(value) || hostWaits.has(value)) fail('E_TASK_VALUE', 'host completion is not capability-free NEX data', site);
      if (value instanceof nex.ByteBuffer) { spend(Number(value.length)); return nex.ByteBuffer.copy(value.toUint8Array()); }
      if (path.has(value)) fail('E_TASK_VALUE', 'cyclic host completion', site); path.add(value);
      try {
        if (Array.isArray(value)) {
          if (value.length > 65536) fail('E_LIMIT', 'host list exceeds its bound', site);
          const items: nex.Value[] = [];
          for (let i = 0; i < value.length; ++i) { const field = Object.getOwnPropertyDescriptor(value, String(i)); if (!field || !('value' in field)) fail('E_TASK_VALUE', 'host list contains holes or accessors', site); items.push(copy(field.value, depth + 1)); }
          if (Reflect.ownKeys(value).length !== value.length + 1) fail('E_TASK_VALUE', 'host list has non-value properties', site);
          return nex.list(items);
        }
        if (Object.getPrototypeOf(value) !== null) fail('E_TASK_VALUE', 'host object lacks NEX record layout', site);
        const type = Object.getOwnPropertyDescriptor(value, nex.TYPE), variant = Object.getOwnPropertyDescriptor(value, nex.CASE);
        if (!type || !('value' in type) || typeof type.value !== 'string' || !type.value || type.value.startsWith('nex.private.') || (variant && (!('value' in variant) || typeof variant.value !== 'string'))) fail('E_TASK_VALUE', 'invalid host record metadata', site);
        const name = text(type.value), tag = variant ? text(variant.value) : undefined, fields: [string, nex.Value][] = [];
        for (const key of Reflect.ownKeys(value)) {
          if (key === nex.TYPE || key === nex.CASE) continue;
          if (typeof key !== 'string') fail('E_TASK_VALUE', 'host record has unknown metadata', site);
          const field = Object.getOwnPropertyDescriptor(value, key)!;
          if (!('value' in field) || !field.enumerable) fail('E_TASK_VALUE', 'host record contains an accessor', site);
          fields.push([text(key), copy(field.value, depth + 1)]);
        }
        return tag === undefined ? nex.record(name, fields) : nex.enumeration(name, tag, fields);
      } finally { path.delete(value); }
    };
    return copy(root, 0);
  }
  acceptHost(): void {
    while (this.mailbox.length) {
      const stamp = this.mailbox.shift()!, value = this.external[stamp.index];
      if (!value || value.stamp !== stamp || value.state !== 'settled') continue;
      const job = this.jobs[stamp.job];
      if (value.failure) { this.stopHost(value.failure); this.retireHost(value); continue; }
      try {
        if (!value.cancelRequested && !job.cancelled && job.state === 'external' && !this.expired) {
          this.checkDeadline(value.site);
          if (value.rejected) fail('E_HOST', 'trusted host operation rejected', value.site);
          let admitted: unknown;
          try { admitted = this.outside(() => value.admit!(value.raw)); }
          catch (error) {
            if (fatalResource(error)) throw new nex.NexError(error.code, 'trusted host resource failure', value.site);
            fail('E_HOST_VALUE', 'trusted host completion failed admission', value.site);
          }
          if (!job.cancelled) {
            const owned = this.copyHost(admitted, value.bytes, value.site); this.checkDeadline(value.site);
            if (!job.cancelled) { this.retireHost(value); this.answer(stamp.job, owned); continue; }
          }
        }
      } catch (error) {
        const failure = asError(error);
        // An admitted host completion can exhaust validation/copy resources or
        // its decoder's explicit resource budget. Keep that known fatal outcome
        // sticky across a later ordinary callback result or cancellation drain.
        if (fatalResource(failure)) this.stopHost(failure); else this.finish(stamp.job, failure);
      }
      this.retireHost(value);
    }
  }
  externalProgress(): boolean { return this.external.some(value => value && value.state !== 'reserved'); }
  stop(failure: Error): void {
    // A root deadline ends the entire execution, even if the timed-out child
    // was unobserved or its enclosing callback returned an error result.
    for (let i = 0; i < this.jobs.length; ++i) {
      const job = this.jobs[i];
      if (job.state === 'finishing') job.failure = prefer(job.failure, failure);
      else if (job.state !== 'done') this.finish(i, failure);
    }
  }
  within(ancestor: number, scope: number): boolean {
    for (let s = scope; s !== none; s = this.regions[s].parent) if (s === ancestor) return true; return false;
  }
  access(scope: number, current: number, site?: nex.Site): void {
    if (scope < 0 || scope >= this.regions.length || this.regions[scope].closed || !this.within(scope, current)) fail('E_TASK_SCOPE', 'task scope is foreign or has ended', site);
  }
  cap(value: nex.Value, kind: Cap['kind'], current: number, site?: nex.Site): number {
    if (typeof value !== 'object' || value === null) fail('E_TASK_VALUE', 'expected an owned task capability', site);
    const cap = capabilities.get(value);
    if (!cap || cap.kind !== kind) fail('E_TASK_VALUE', 'expected a branded task capability', site);
    if (this.closed || cap.owner.deref() !== this) fail('E_TASK_SCOPE', 'task capability belongs to a foreign or ended scheduler', site);
    this.access(cap.scope, current, site);
    const canonical = kind === 'task_scope' ? this.regions[cap.index]?.capability?.deref() : kind === 'task' ? this.jobs[cap.index]?.capability?.deref() : this.pipes[cap.index]?.capability?.deref();
    if (canonical !== value) fail('E_TASK_SCOPE', 'task capability identity differs', site); return cap.index;
  }
  value(kind: Cap['kind'], index: number): nex.RecordValue {
    const state = kind === 'task_scope' ? this.regions[index] : kind === 'task' ? this.jobs[index] : this.pipes[index];
    const previous = state.capability?.deref(); if (previous) return previous;
    const value = nex.record<nex.RecordValue>('nex.private.' + kind, []);
    const scope = kind === 'task_scope' ? index : kind === 'task' ? this.jobs[index].member : this.pipes[index].scope;
    capabilities.set(value, {owner: new WeakRef(this), kind, index, scope}); nex.annotateTaskValue(value, kind);
    state.capability = new WeakRef(value); return value;
  }
  snapshot(root: Item, target: number, current: number, site?: nex.Site): void {
    const work: Item[] = [root], seen = new Set<object>(); let members = 1;
    while (work.length) {
      const next = work.pop(); this.charge(site);
      if (next === undefined) continue;
      if (typeof next === 'number') { if (!Number.isFinite(next)) fail('E_FLOAT', 'non-finite task value', site); continue; }
      if (typeof next !== 'object' && typeof next !== 'function') continue;
      if (next === null) fail('E_TASK_VALUE', 'null is not a task value', site);
      if (hostTickets.has(next) || hostWaits.has(next)) fail('E_TASK_VALUE', 'host tickets are not source values', site);
      if (seen.has(next)) continue; seen.add(next);
      if (seen.size > 262144) fail('E_LIMIT', 'task snapshot graph exceeds262144 nodes', site);
      const cap = capabilities.get(next);
      if (cap) { this.cap(next as nex.Value, cap.kind, current, site); if (target === none || !this.within(cap.scope, target)) fail('E_TASK_SCOPE', 'task capability escapes its owner scope', site); }
      let children: ReadonlyArray<nex.Value>;
      if (typeof next === 'function') {
        const captures = nex.captureValues(next); if (!captures) fail('E_TASK_VALUE', 'task callable lacks checked capture metadata', site); children = captures;
      } else if (next instanceof nex.ByteBuffer) children = [];
      else children = Array.isArray(next) ? next : Object.values(next);
      if (children.length > 262144 - members) fail('E_LIMIT', 'task snapshot graph exceeds262144 members', site);
      members += children.length; for (const child of children) work.push(child);
    }
  }
  enqueue(index: number): void { const job = this.jobs[index]; if (job.state === 'ready' && !job.queued) { this.ready.push(index); job.queued = true; } }
  answer(index: number, value?: Item): void { const job = this.jobs[index]; job.response = value; job.responseSource = job.pending = undefined; job.target = none; job.state = 'ready'; this.enqueue(index); }
  makeJob(iterator: Step<Item>, member = none, parent = none): number {
    if (this.jobs.length >= 4096) fail('E_LIMIT', 'task slots exceed4096');
    const spawnDepth = parent === none ? 1 : this.jobs[parent].spawnDepth + 1;
    if (spawnDepth > 256) fail('E_LIMIT', 'task nesting exceeds256');
    const index = this.jobs.length;
    this.jobs.push({state: 'ready', stack: [{iterator, scope: none, parent: none}], member, current: member, parent, spawnDepth, calls: 0, polls: 0, cancelled: false, queued: false, observed: false, target: none, owned: [], external: new Set()});
    if (member !== none) this.regions[member].members.push(index); this.enqueue(index); return index;
  }
  callback(value: nex.Value, arguments_: ReadonlyArray<nex.Value>, site?: nex.Site): Step<Item> {
    if (typeof value !== 'function' || !nex.captureValues(value)) fail('E_FUNCTION', 'task callback is not a checked callable', site);
    const invoke = value as (...args: nex.Value[]) => Call<Item>;
    return (function* (): Step<Item> { return yield* take(invoke(...arguments_), site); })();
  }
  cancelRegion(scope: number): void { for (const job of this.jobs) if (job.state !== 'done' && this.within(scope, job.member)) job.cancelled = true; }
  cancelJob(index: number): boolean {
    const selected = this.jobs[index]; if (selected.state === 'done' || selected.state === 'finishing') return false;
    for (let i = 0; i < this.jobs.length; ++i) for (let parent = i; parent !== none; parent = this.jobs[parent].parent) if (parent === index) { this.jobs[i].cancelled = true; break; }
    return true;
  }
  answerSource(index: number, error: object): void {
    const job = this.jobs[index]; job.response = undefined; job.responseSource = error;
    job.pending = undefined; job.target = none; job.state = 'ready'; this.enqueue(index);
  }
  finish(index: number, failure?: Error, result?: Item, sourceFailure?: object): void {
    const job = this.jobs[index]; if (job.state === 'done' || job.state === 'finishing') return;
    job.state = 'finishing'; job.failure = failure; job.sourceFailure = sourceFailure; job.result = result; job.pending = job.response = job.responseSource = undefined;
    const previous = active; active = {driver: this, job: index};
    try { for (let i = job.stack.length; i-- > 0;) {
      try { job.stack[i].iterator.return(undefined); } catch (error) { job.failure = prefer(job.failure, asError(error)); }
    } } finally { active = previous; }
    job.stack.length = 0;
    for (const index of [...job.external]) this.cancelHost(this.external[index]!);
    for (const scope of job.owned) if (!this.regions[scope].closed) { this.regions[scope].closing = true; this.regions[scope].abort = !!job.failure || !!job.sourceFailure; if (this.regions[scope].abort) this.cancelRegion(scope); }
  }
  cycle(waiter: number, target: number, scope = false): boolean {
    const work = [scope ? 4096 + target : target], seen = new Set<number>();
    while (work.length) {
      const node = work.pop()!; if (node === waiter) return true; if (seen.has(node)) continue; seen.add(node);
      if (node >= 4096) { const region = this.regions[node - 4096]; if (region.closed) continue; for (const i of region.members) if (this.jobs[i].state !== 'done') work.push(i); for (const s of region.children) if (!this.regions[s].closed) work.push(4096 + s); }
      else { const job = this.jobs[node]; if (job.state === 'future') work.push(job.target); else if (job.state === 'drain') work.push(4096 + job.target); }
    }
    return false;
  }
  first(queue: Waiters, state: State, pipe: number): number {
    while (queue.length) { const i = queue.shift()!, job = this.jobs[i]; if (!job.cancelled && job.state === state && job.target === pipe) return i; } return none;
  }
  closePipe(index: number): boolean {
    const pipe = this.pipes[index]; if (pipe.closed) return false; pipe.closed = true;
    for (let i = this.first(pipe.senders, 'send', index); i !== none; i = this.first(pipe.senders, 'send', index)) this.answer(i, false);
    for (let i = this.first(pipe.receivers, 'receive', index); i !== none; i = this.first(pipe.receivers, 'receive', index)) this.answer(i, pipe.buffer.length ? nex.ok(pipe.buffer.shift()!) : nex.err('E_CHANNEL_CLOSED', 'channel is closed'));
    return true;
  }
  settle(): boolean {
    let any = false, changed = true;
    while (changed) {
      changed = false;
      for (let i = 0; i < this.jobs.length; ++i) { const job = this.jobs[i]; if (job.cancelled && job.state !== 'done' && job.state !== 'finishing') { this.finish(i, new nex.NexError('E_CANCELLED', 'task was cancelled')); changed = true; } }
      for (let s = this.regions.length; s-- > 0;) {
        const region = this.regions[s]; if (!region.closing || region.closed || region.external.size) continue;
        if (this.sourceClassifier && !region.abort) for (const member of region.members) { const job = this.jobs[member];
          if (job.state === 'done' && !job.observed && !job.cancelled && job.sourceFailure) {
            region.sourceFailure = job.sourceFailure; region.abort = true; this.cancelRegion(s); changed = true; break;
          }
        }
        if (region.members.some(i => this.jobs[i].state !== 'done') || region.children.some(i => !this.regions[i].closed)) continue;
        for (const i of region.members) { const job = this.jobs[i]; if ((!region.abort && !job.observed && !job.cancelled) || (region.sourceFailure && job.failure && (!(job.failure instanceof nex.NexError) || job.failure.code !== 'E_CANCELLED'))) region.failure = prefer(region.failure, job.failure); job.observed = true; job.result = job.sourceFailure = undefined; job.capability = undefined; }
        for (const p of region.pipes) { this.closePipe(p); this.slots -= this.pipes[p].capacity; this.pipes[p].capacity = 0; this.pipes[p].buffer.clear(); this.pipes[p].capability = undefined; }
        region.closed = true; region.capability = undefined; const owner = this.jobs[region.owner]; if (owner.state === 'finishing') { owner.failure = prefer(owner.failure, region.failure); owner.sourceFailure ??= region.sourceFailure; } changed = true;
      }
      for (let i = 0; i < this.jobs.length; ++i) {
        const job = this.jobs[i];
        if (job.state === 'finishing' && !job.external.size && job.owned.every(s => this.regions[s].closed)) { if (job.failure || job.sourceFailure) job.result = undefined; job.state = 'done'; changed = true; }
        else if (job.state === 'future' && this.jobs[job.target].state === 'done') { const target = this.jobs[job.target]; target.observed = true; if (target.failure) this.finish(i, target.failure); else if (target.sourceFailure) this.answerSource(i, target.sourceFailure); else this.answer(i, target.result); changed = true; }
        else if (job.state === 'drain' && this.regions[job.target].closed) {
          const region = this.regions[job.target]; if (region.failure) this.finish(i, region.failure);
          else { const activation = job.stack.pop()!; job.current = activation.parent; const source = activation.sourceFailure ?? region.sourceFailure; if (source) this.answerSource(i, source); else this.answer(i, activation.result); } changed = true;
        }
      }
      any ||= changed;
    }
    return any;
  }
  dispatch(index: number, r: Request): void {
    const job = this.jobs[index], args = r.arguments; this.charge(r.site);
    if (r.operation === '$poll' || r.operation === 'task_yield') { this.answer(index); return; }
    if (r.operation === 'with_tasks') {
      const workers = args[0]; if (typeof workers !== 'bigint' || workers < 1n || workers > 16n) fail('E_RANGE', 'with_tasks requires1..16 workers', r.site);
      if (this.regions.length >= 1024) fail('E_LIMIT', 'scope count exceeds1024', r.site);
      const parent = job.current, depth = parent === none ? 1 : this.regions[parent].depth + 1;
      if (depth > 256 || job.calls >= 256) fail('E_LIMIT', 'scope/call nesting exceeds256', r.site);
      const scope = this.regions.length;
      this.regions.push({parent, owner: index, depth, closing: false, closed: false, abort: false, members: [], children: [], pipes: [], external: new Set()});
      if (parent !== none) this.regions[parent].children.push(scope); job.owned.push(scope); job.current = scope;
      this.snapshot(args[1], scope, scope, r.site);
      job.stack.push({iterator: this.callback(args[1], [this.value('task_scope', scope)], r.site), scope, parent, site: r.site}); this.enqueue(index); return;
    }
    if (r.operation === 'current_task_scope') { this.access(job.current, job.current, r.site); this.answer(index, this.value('task_scope', job.current)); return; }
    if (r.operation === 'task_spawn') {
      const scope = this.cap(args[0], 'task_scope', job.current, r.site); this.snapshot(args[1], scope, job.current, r.site);
      const child = this.makeJob(this.callback(args[1], [], r.site), scope, index); this.answer(index, this.value('task', child)); return;
    }
    if (r.operation === 'task_wait' || r.operation === 'task_cancel') {
      const target = this.cap(args[0], 'task', job.current, r.site);
      if (r.operation === 'task_cancel') { this.answer(index, this.cancelJob(target)); return; }
      if (this.cycle(index, target)) fail('E_TASK_CYCLE', 'cyclic task wait', r.site); job.target = target; job.state = 'future'; return;
    }
    if (r.operation === 'channel_new') {
      const scope = this.cap(args[0], 'task_scope', job.current, r.site), count = args[1];
      if (typeof count !== 'bigint' || count < 0n || count > 65536n) fail('E_RANGE', 'channel capacity must be0..65536', r.site);
      if (this.pipes.length >= 1024 || Number(count) > 65536 - this.slots) fail('E_LIMIT', 'channel/slot quota exceeded', r.site);
      const p = this.pipes.length; this.pipes.push({scope, capacity: Number(count), closed: false, buffer: new Ring<nex.Value>(Number(count)), senders: new Waiters(), receivers: new Waiters()}); this.slots += Number(count); this.regions[scope].pipes.push(p); this.answer(index, this.value('channel', p)); return;
    }
    const p = this.cap(args[0], 'channel', job.current, r.site), pipe = this.pipes[p];
    if (r.operation === 'task_close') { this.answer(index, this.closePipe(p)); return; }
    if (r.operation === 'task_send') {
      const value = args[1]; this.snapshot(value, pipe.scope, job.current, r.site);
      if (pipe.closed) { this.answer(index, false); return; }
      const receiver = this.first(pipe.receivers, 'receive', p);
      if (receiver !== none) { this.answer(receiver, nex.ok(value)); this.answer(index, true); return; }
      if (pipe.buffer.length < pipe.capacity) { pipe.buffer.push(value); this.answer(index, true); return; }
      job.pending = value; job.target = p; job.state = 'send'; pipe.senders.push(index); return;
    }
    if (r.operation === 'task_recv') {
      if (pipe.buffer.length) { const value = pipe.buffer.shift()!, sender = this.first(pipe.senders, 'send', p); if (sender !== none) { pipe.buffer.push(this.jobs[sender].pending!); this.answer(sender, true); } this.answer(index, nex.ok(value)); return; }
      const sender = this.first(pipe.senders, 'send', p);
      if (sender !== none) { const value = this.jobs[sender].pending!; this.answer(sender, true); this.answer(index, nex.ok(value)); return; }
      if (pipe.closed) { this.answer(index, nex.err('E_CHANNEL_CLOSED', 'channel is closed')); return; }
      job.target = p; job.state = 'receive'; pipe.receivers.push(index); return;
    }
    fail('E_TASK_STATE', 'unknown task request', r.site);
  }
  turn(index: number): void {
    const previous = active; active = {driver: this, job: index}; const job = this.jobs[index];
    try {
      const activation = job.stack[job.stack.length - 1], input = job.response, source = job.responseSource; job.response = job.responseSource = undefined;
      const result = source === undefined ? activation.iterator.next(input) : activation.iterator.throw(source);
      if (result.done) {
        this.snapshot(result.value, activation.scope === none ? job.member : activation.parent, job.current, activation.site);
        if (activation.scope === none) { this.finish(index, undefined, result.value); return; }
        const region = this.regions[activation.scope], abort = failed(result.value);
        for (const external of [...region.external]) { const value = this.external[external]!; if (value.stamp.job === index && value.state === 'reserved') this.retireHost(value); }
        if (!abort && this.cycle(index, activation.scope, true)) fail('E_TASK_CYCLE', 'cyclic task scope drain', activation.site);
        activation.result = result.value; region.closing = true; region.abort = abort; if (abort) this.cancelRegion(activation.scope); job.target = activation.scope; job.state = 'drain'; return;
      }
      const r = result.value, host = hostWaits.get(r);
      if (host) { hostWaits.delete(r); if (job.cancelled) this.finish(index, new nex.NexError('E_CANCELLED', 'task was cancelled')); else this.dispatchHost(index, host); return; }
      if (!requests.has(r)) fail('E_TASK_STATE', 'unbranded or reused task request'); requests.delete(r);
      const sourceRequest = r as Request;
      this.options.observe?.(index, sourceRequest);
      if (job.cancelled) this.finish(index, new nex.NexError('E_CANCELLED', 'task was cancelled', sourceRequest.site)); else this.dispatch(index, sourceRequest);
    } catch (error) {
      const source = this.sourceError(error);
      if (!source) this.finish(index, asError(error));
      else {
        try { this.checkSourceControl(); }
        catch (control) { this.finish(index, asError(control)); return; }
        const activation = job.stack[job.stack.length - 1];
        if (activation.scope === none) this.finish(index, undefined, undefined, source);
        else {
          const region = this.regions[activation.scope]; activation.sourceFailure = source;
          region.sourceFailure = source; region.closing = region.abort = true;
          this.cancelRegion(activation.scope); job.target = activation.scope; job.state = 'drain';
        }
      }
    }
    finally { active = previous; }
  }
  async drive<T extends Item>(root: Call<T>): Promise<T> {
    const rootInvocation = invocations.get(root); if (!rootInvocation) fail('E_TASK_STATE', 'root invocation is missing');
    for (const input of rootInvocation.inputs) this.snapshot(input, none, none); this.makeJob(take(root));
    const cancel = () => { for (const job of this.jobs) job.cancelled = true; this.notify(); };
    this.options.signal?.addEventListener('abort', cancel); if (this.options.signal?.aborted) cancel();
    const channel = new MessageChannel(); let deadlineTimer: ReturnType<typeof setTimeout> | undefined;
    channel.port1.onmessage = () => this.notify();
    const armDeadline = () => {
      if (deadlineTimer !== undefined || this.expired) return;
      deadlineTimer = setTimeout(() => {
        deadlineTimer = undefined;
        try { this.checkDeadline(); } catch { this.notify(); }
        if (!this.expired) armDeadline();
      }, Math.max(1, Math.ceil(this.deadline - performance.now())));
    };
    const wait = (turn: boolean) => {
      if (!turn) armDeadline();
      const version = this.wakeVersion;
      return new Promise<void>(resolve => {
        this.wake = resolve;
        if (turn) channel.port2.postMessage(null);
        // Register before inspecting the mailbox. Promise callbacks only enqueue
        // and notify, so immediate completion cannot fall through this boundary.
        if (this.wakeVersion !== version || this.mailbox.length) { this.wake = undefined; resolve(); }
      });
    };
    const drain = async () => {
      while (!this.rootDone()) {
        this.settle(); this.flushHost(); this.acceptHost(); this.settle();
        if (!this.rootDone()) {
          if (!this.externalProgress()) fail('E_TASK_STATE', 'unfinished task drain lacks a physical host operation');
          await wait(false);
        }
      }
    };
    try {
      while (!this.rootDone()) {
        if (this.expired) this.stop(this.expired);
        this.settle(); this.flushHost(); this.acceptHost(); this.settle(); if (this.rootDone()) break;
        if (!this.expired) { try { this.checkDeadline(); } catch (error) { this.stop(asError(error)); continue; } }
        let ran = false;
        while (this.ready.length) {
          const index = this.ready.shift()!, job = this.jobs[index]; job.queued = false;
          if (job.state !== 'ready' || job.cancelled) continue; this.turn(index); ran = true; break;
        }
        this.flushHost();
        if (!ran && !this.settle()) {
          if (!this.externalProgress()) fail('E_TASK_DEADLOCK', 'tasks are parked with no possible progress');
          await wait(false);
        } else if (!this.rootDone()) await wait(true);
      }
      if (this.jobs[0].failure) throw this.jobs[0].failure;
      if (this.jobs[0].sourceFailure) { this.checkSourceControl(); throw this.jobs[0].sourceFailure; }
      return this.jobs[0].result as T;
    } catch (error) {
      if (!this.sourceError(error)) this.stop(asError(error)); await drain(); throw this.jobs[0].failure ?? error;
    } finally {
      this.closed = true; this.options.signal?.removeEventListener('abort', cancel); channel.port1.close(); channel.port2.close();
      if (deadlineTimer !== undefined) clearTimeout(deadlineTimer); this.wake = undefined;
      for (let i = 0; i < this.jobs.length; ++i) { const previous = active; active = {driver: this, job: i}; try { this.finish(i, new nex.NexError('E_CANCELLED', 'task scheduler ended')); } finally { active = previous; } }
      this.settle();
      const limits = Object.freeze({steps: this.options.steps, timeoutMs: this.options.timeoutMs, workers: this.options.workers});
      // This cooperative host has one serial executor. workers is a validated
      // execution ceiling, not a claim that worker threads were created.
      const statistics: Statistics = {steps: this.used, tasks: this.jobs.length, scopes: this.regions.length, channels: this.pipes.length, completed: this.jobs[0].state === 'done', retainedFrames: this.jobs.reduce((n, job) => n + job.stack.length, 0), activeCalls: this.jobs.reduce((n, job) => n + job.calls, 0), limits, actualWorkers: 1, externalPending: this.externalCount, externalReservedBytes: this.externalBytes, externalMailbox: this.mailbox.length, externalStarted: this.externalStarted, externalSettled: this.externalSettled, externalPeakPending: this.externalPeakCount, externalPeakBytes: this.externalPeakBytes};
      this.pipes.length = this.regions.length = this.jobs.length = 0;this.ready.clear();
      this.options.complete?.(Object.freeze(statistics));
    }
  }
}
export async function run<T extends Item>(root: Call<T>, options: Options = {}): Promise<T> { return await new Driver(options).drive(root); }

// Language025 selects a branded classifier per driver; host errors and traps
// retain their ordinary cancellation path. No ambient scheduler mode is changed.
export async function runSourceErrors<T extends Item>(root: Call<T>, sourceClassifier: (error: unknown) => boolean, options: Options = {}): Promise<T> {
  if (typeof sourceClassifier !== 'function') fail('E_TASK_STATE', 'source-error classifier is required');
  return await new Driver(options, sourceClassifier).drive(root);
}
// Retained entry for explicitly private025 experiments.
export async function runSourceExceptionPrototype<T extends Item>(root: Call<T>, sourceClassifier: (error: unknown) => boolean, options: Options = {}): Promise<T> {
  return await runSourceErrors(root, sourceClassifier, options);
}
