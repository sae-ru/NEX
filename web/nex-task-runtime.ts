// Compiler-private generator backend. No serialized AST/IR or native scheduler.
import * as nex from './nex-runtime.ts';
type Item = nex.Value | void;
declare const outcome: unique symbol;
export interface Call<T extends Item> extends nex.RecordValue { readonly [outcome]?: T }
export interface Scope extends nex.RecordValue {}
export interface Future<T extends Item> extends nex.RecordValue { readonly [outcome]?: T }
export interface Channel<T extends nex.Value> extends nex.RecordValue { readonly [outcome]?: T }
export type Step<T extends Item> = Generator<Request, T, Item>;
export type Request = Readonly<{ operation: string; arguments: ReadonlyArray<nex.Value>; site?: nex.Site }>;
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
type State = 'ready' | 'future' | 'send' | 'receive' | 'drain' | 'finishing' | 'done';
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
type Activation = { iterator: Step<Item>; scope: number; parent: number; site?: nex.Site; result?: Item };
type Job = {
  state: State; stack: Activation[]; member: number; current: number; parent: number; spawnDepth: number;
  calls: number; polls: number; cancelled: boolean; queued: boolean; observed: boolean; target: number;
  response?: Item; pending?: nex.Value; result?: Item; failure?: Error; owned: number[]; capability?: WeakRef<Future<Item>>;
};
type Region = {
  parent: number; owner: number; depth: number; closing: boolean; closed: boolean; abort: boolean;
  members: number[]; children: number[]; pipes: number[]; failure?: Error; capability?: WeakRef<Scope>;
};
type Pipe = { scope: number; capacity: number; closed: boolean; buffer: Ring<nex.Value>; senders: Waiters; receivers: Waiters; capability?: WeakRef<Channel<nex.Value>> };
export type Options = { steps?: number; signal?: AbortSignal; observe?: (job: number, request: Request) => void; complete?: (statistics: Statistics) => void };
export type Statistics = { steps: number; tasks: number; scopes: number; channels: number; completed: boolean; retainedFrames: number; activeCalls: number };
function resource(error: Error): boolean { return error instanceof nex.NexError && ['E_LIMIT', 'E_MEMORY', 'E_TIMEOUT', 'E_CANCELLED'].includes(error.code); }
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
  readonly options: Options;
  readonly limit: number;
  used = 0; slots = 0; closed = false;
  private rootDone(): boolean { return this.jobs[0].state === 'done'; }
  constructor(options: Options) {
    this.options = options; this.limit = options.steps ?? 1000000;
    if (!Number.isSafeInteger(this.limit) || this.limit < 1) fail('E_RANGE', 'task budget must be a positive safe integer');
  }
  charge(site?: nex.Site): void { if (this.used >= this.limit) fail('E_LIMIT', 'shared generator task budget exceeded', site); ++this.used; }
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
  answer(index: number, value?: Item): void { const job = this.jobs[index]; job.response = value; job.pending = undefined; job.target = none; job.state = 'ready'; this.enqueue(index); }
  makeJob(iterator: Step<Item>, member = none, parent = none): number {
    if (this.jobs.length >= 4096) fail('E_LIMIT', 'task slots exceed4096');
    const spawnDepth = parent === none ? 1 : this.jobs[parent].spawnDepth + 1;
    if (spawnDepth > 256) fail('E_LIMIT', 'task nesting exceeds256');
    const index = this.jobs.length;
    this.jobs.push({state: 'ready', stack: [{iterator, scope: none, parent: none}], member, current: member, parent, spawnDepth, calls: 0, polls: 0, cancelled: false, queued: false, observed: false, target: none, owned: []});
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
  finish(index: number, failure?: Error, result?: Item): void {
    const job = this.jobs[index]; if (job.state === 'done' || job.state === 'finishing') return;
    job.state = 'finishing'; job.failure = failure; job.result = result; job.pending = job.response = undefined;
    const previous = active; active = {driver: this, job: index};
    try { for (let i = job.stack.length; i-- > 0;) {
      try { job.stack[i].iterator.return(undefined); } catch (error) { job.failure = prefer(job.failure, asError(error)); }
    } } finally { active = previous; }
    job.stack.length = 0;
    for (const scope of job.owned) if (!this.regions[scope].closed) { this.regions[scope].closing = true; this.regions[scope].abort = !!job.failure; if (job.failure) this.cancelRegion(scope); }
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
        const region = this.regions[s]; if (!region.closing || region.closed || region.members.some(i => this.jobs[i].state !== 'done') || region.children.some(i => !this.regions[i].closed)) continue;
        for (const i of region.members) { const job = this.jobs[i]; if (!region.abort && !job.observed && !job.cancelled) region.failure = prefer(region.failure, job.failure); job.observed = true; job.result = undefined; job.capability = undefined; }
        for (const p of region.pipes) { this.closePipe(p); this.slots -= this.pipes[p].capacity; this.pipes[p].capacity = 0; this.pipes[p].buffer.clear(); this.pipes[p].capability = undefined; }
        region.closed = true; region.capability = undefined; const owner = this.jobs[region.owner]; if (owner.state === 'finishing') owner.failure = prefer(owner.failure, region.failure); changed = true;
      }
      for (let i = 0; i < this.jobs.length; ++i) {
        const job = this.jobs[i];
        if (job.state === 'finishing' && job.owned.every(s => this.regions[s].closed)) { if (job.failure) job.result = undefined; job.state = 'done'; changed = true; }
        else if (job.state === 'future' && this.jobs[job.target].state === 'done') { const target = this.jobs[job.target]; target.observed = true; if (target.failure) this.finish(i, target.failure); else this.answer(i, target.result); changed = true; }
        else if (job.state === 'drain' && this.regions[job.target].closed) {
          const region = this.regions[job.target]; if (region.failure) this.finish(i, region.failure);
          else { const activation = job.stack.pop()!; job.current = activation.parent; this.answer(i, activation.result); } changed = true;
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
      this.regions.push({parent, owner: index, depth, closing: false, closed: false, abort: false, members: [], children: [], pipes: []});
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
      const activation = job.stack[job.stack.length - 1], input = job.response; job.response = undefined;
      const result = activation.iterator.next(input);
      if (result.done) {
        this.snapshot(result.value, activation.scope === none ? job.member : activation.parent, job.current, activation.site);
        if (activation.scope === none) { this.finish(index, undefined, result.value); return; }
        const region = this.regions[activation.scope], abort = failed(result.value);
        if (!abort && this.cycle(index, activation.scope, true)) fail('E_TASK_CYCLE', 'cyclic task scope drain', activation.site);
        activation.result = result.value; region.closing = true; region.abort = abort; if (abort) this.cancelRegion(activation.scope); job.target = activation.scope; job.state = 'drain'; return;
      }
      const r = result.value; if (!requests.has(r)) fail('E_TASK_STATE', 'unbranded or reused task request'); requests.delete(r);
      this.options.observe?.(index, r);
      if (job.cancelled) this.finish(index, new nex.NexError('E_CANCELLED', 'task was cancelled', r.site)); else this.dispatch(index, r);
    } catch (error) { this.finish(index, asError(error)); }
    finally { active = previous; }
  }
  async drive<T extends Item>(root: Call<T>): Promise<T> {
    const rootInvocation = invocations.get(root); if (!rootInvocation) fail('E_TASK_STATE', 'root invocation is missing');
    for (const input of rootInvocation.inputs) this.snapshot(input, none, none); this.makeJob(take(root));
    const cancel = () => { for (const job of this.jobs) job.cancelled = true; };
    this.options.signal?.addEventListener('abort', cancel); if (this.options.signal?.aborted) cancel();
    const channel = new MessageChannel(); let wake: (() => void) | undefined;
    channel.port1.onmessage = () => { const current = wake; wake = undefined; current?.(); };
    const tick = () => new Promise<void>(resolve => { wake = resolve; channel.port2.postMessage(null); });
    try {
      while (!this.rootDone()) {
        this.settle(); if (this.rootDone()) break;
        let ran = false;
        while (this.ready.length) {
          const index = this.ready.shift()!, job = this.jobs[index]; job.queued = false;
          if (job.state !== 'ready' || job.cancelled) continue; this.turn(index); ran = true; break;
        }
        if (!ran && !this.settle()) fail('E_TASK_DEADLOCK', 'tasks are parked with no possible progress');
        if (!this.rootDone()) await tick();
      }
      if (this.jobs[0].failure) throw this.jobs[0].failure; return this.jobs[0].result as T;
    } finally {
      this.closed = true; this.options.signal?.removeEventListener('abort', cancel); channel.port1.close(); channel.port2.close();
      for (let i = 0; i < this.jobs.length; ++i) { const previous = active; active = {driver: this, job: i}; try { this.finish(i, new nex.NexError('E_CANCELLED', 'task scheduler ended')); } finally { active = previous; } }
      const statistics: Statistics = {steps: this.used, tasks: this.jobs.length, scopes: this.regions.length, channels: this.pipes.length, completed: this.jobs[0].state === 'done', retainedFrames: this.jobs.reduce((n, job) => n + job.stack.length, 0), activeCalls: this.jobs.reduce((n, job) => n + job.calls, 0)};
      this.pipes.length = this.regions.length = this.jobs.length = 0;this.ready.clear();
      this.options.complete?.(Object.freeze(statistics));
    }
  }
}
export async function run<T extends Item>(root: Call<T>, options: Options = {}): Promise<T> { return await new Driver(options).drive(root); }
