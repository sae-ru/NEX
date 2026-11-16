// Private sequential execution/root ownership for the managed source backend.
import {CellHeap, type HeapValue, type HeapLimits, type HeapStats, type RootFrame} from './nex-managed-heap.ts';
import {NexError, type Site} from './nex-runtime.ts';
export type SourceDetails = Readonly<{code: string; message: string; site: Site}>;
class SourceCompletion {
  readonly detail: SourceDetails;
  readonly key: string | undefined;
  readonly value: HeapValue | undefined;
  constructor(detail: SourceDetails, key?: string, value?: HeapValue) {
    this.detail = detail; this.key = key; this.value = value; Object.freeze(this);
  }
}
class ReturnCompletion {
  readonly value: HeapValue | undefined;
  constructor(value?: HeapValue) { this.value = value; Object.freeze(this); }
}
type Completion = SourceCompletion | ReturnCompletion;
const sourceDetails = new WeakMap<SourceDetails, SourceCompletion>();
type Roots = {frame: RootFrame; kind: 'scope' | 'expression' | 'statement'};
type Context = {heap: CellHeap; roots: Roots[]; scopes: RootFrame[]; flight: Map<Completion, RootFrame>; output: {text: string; print?: (text: string) => void}};
let active: Context | undefined;
function context(): Context {
  if (active === undefined) throw new NexError('E_CELL_CONTEXT', 'managed source execution has no active context');
  return active;
}
function keep(frame: RootFrame | undefined, value: HeapValue | void): void { if (value !== undefined) frame?.keep(value); }
function unwind(ctx: Context, depth: number): void { while (ctx.roots.length > depth) ctx.roots.pop()!.frame.close(); }
function push(ctx: Context, kind: Roots['kind']): RootFrame {
  const frame = ctx.heap.frame(); ctx.roots.push({frame, kind}); return frame;
}
function completion(value: unknown): value is Completion { return value instanceof SourceCompletion || value instanceof ReturnCompletion; }
function retainFlight(error: Completion): void {
  const ctx = context(); if (ctx.flight.has(error)) return;
  const root = ctx.heap.frame(); keep(root, error.value); ctx.flight.set(error, root);
}
// Acquire the next owner before retiring the transport owner. The held packet
// may survive source frame cleanup, guards and user finalizers.
function acquire(error: Completion): RootFrame {
  const ctx = context(), root = ctx.heap.frame(); keep(root, error.value);
  ctx.flight.get(error)?.close(); ctx.flight.delete(error); return root;
}
export function heap(): CellHeap { return context().heap; }
export function root(read: () => HeapValue | undefined): void {
  const frame = context().scopes.at(-1);
  if (frame === undefined) throw new NexError('E_CELL_CONTEXT', 'managed binding has no lexical root scope');
  frame.track(read);
}
export function rootValues(read: () => ReadonlyArray<HeapValue>): void {
  const frame = context().scopes.at(-1);
  if (frame === undefined) throw new NexError('E_CELL_CONTEXT', 'managed builder has no lexical root scope');
  frame.trackValues(read);
}
export function scope<T extends HeapValue | void>(body: () => T): T {
  const ctx = context(), depth = ctx.roots.length, parent = ctx.roots.at(-1)?.frame;
  const frame = push(ctx, 'scope'); ctx.scopes.push(frame);
  try { const value = body(); keep(parent, value); return value; }
  finally { unwind(ctx, depth); ctx.scopes.pop(); }
}
export function expression<T extends HeapValue | void>(site: Site, body: () => T): T {
  const ctx = context(), depth = ctx.roots.length, parent = ctx.roots.at(-1)?.frame;
  push(ctx, 'expression');
  try { const value = body(); keep(parent, value); return value; }
  catch (error) {
    if (error instanceof NexError && error.site === undefined) throw new NexError(error.code, error.message, site);
    throw error;
  } finally { unwind(ctx, depth); }
}
export function beginStatement(): void { push(context(), 'statement'); }
export function endStatement(): void {
  const ctx = context(), roots = ctx.roots.at(-1);
  if (roots?.kind !== 'statement') throw new NexError('E_CELL_CONTEXT', 'managed statement roots are unbalanced');
  ctx.roots.pop(); roots.frame.close();
}
export function condition(body: () => boolean): boolean {
  const ctx = context(), depth = ctx.roots.length; push(ctx, 'statement');
  try { return body(); } finally { unwind(ctx, depth); }
}
export function returned(value: HeapValue | void = undefined): never {
  const error = new ReturnCompletion(value as HeapValue | undefined); retainFlight(error); throw error;
}
export function functionBody<T extends HeapValue | void>(inputs: ReadonlyArray<HeapValue>, body: () => void): T {
  const ctx = context(), depth = ctx.roots.length, parent = ctx.roots.at(-1)?.frame;
  const frame = push(ctx, 'scope'); ctx.scopes.push(frame);
  try {
    for (const input of inputs) frame.keep(input);
    try { body(); return undefined as T; }
    catch (error) {
      if (!(error instanceof ReturnCompletion)) throw error;
      const owner = acquire(error);
      try { keep(parent, error.value); return error.value as T; }
      finally { owner.close(); }
    }
  } finally { unwind(ctx, depth); ctx.scopes.pop(); }
}
function throwSource(code: string, message: string, site: Site, key?: string, value?: HeapValue): never {
  const detail = Object.freeze({code, message, site: Object.freeze([...site]) as Site});
  const error = new SourceCompletion(detail, key, value); sourceDetails.set(detail, error);
  retainFlight(error); throw error;
}
export function raiseLegacy(code: string, message: string, site: Site): never { return throwSource(code, message, site); }
export function raiseValue(key: string, name: string, value: HeapValue, site: Site): never {
  if (!/^[0-9a-f]{64}$/.test(key)) throw new NexError('E_SOURCE_TYPE', 'source error type key must be a complete SHA256 digest', site);
  return throwSource(name, 'typed source error', site, key, value);
}
export function details(error: unknown): SourceDetails | undefined { return error instanceof SourceCompletion ? error.detail : undefined; }
export function matches(detail: SourceDetails, key: string): boolean { return sourceDetails.get(detail)?.key === key && /^[0-9a-f]{64}$/.test(key); }
export function payload(detail: SourceDetails, key: string, site: Site): HeapValue {
  const packet = sourceDetails.get(detail);
  if (!matches(detail, key) || packet?.value === undefined) throw new NexError('E_SOURCE_TYPE', 'source error payload type does not match the checked handler', site);
  return packet.value;
}
export function rethrow(error: unknown): never {
  if (!completion(error)) throw new NexError('E_INTERNAL', 'managed rethrow lost its source completion');
  retainFlight(error); throw error;
}
export function handle(body: () => void, handler: (error: unknown) => boolean): void {
  try { body(); }
  catch (error) {
    if (!(error instanceof SourceCompletion)) throw error;
    const owner = acquire(error);
    try { if (!handler(error)) rethrow(error); }
    finally { owner.close(); }
  }
}
export function finalize(body: () => void, finalizer: () => void): void {
  let pending: Completion | undefined, owner: RootFrame | undefined;
  try {
    try { body(); }
    catch (error) {
      // Fatal traps bypass user finalizers. Compiler root cleanup still runs in
      // each enclosing scope's finally clause.
      if (!completion(error)) throw error;
      pending = error; owner = acquire(error);
    }
    finalizer();
    if (pending !== undefined) rethrow(pending);
  } finally { owner?.close(); }
}
// Generator roots belong to one scheduler lane. The scheduler activates that
// lane only during a synchronous resume; no ambient context spans an await.
export function* scopeTask<Y, N, T extends HeapValue | void>(body: () => Generator<Y, T, N>): Generator<Y, T, N> {
  const ctx = context(), depth = ctx.roots.length, parent = ctx.roots.at(-1)?.frame;
  const frame = push(ctx, 'scope'); ctx.scopes.push(frame);
  try { const value = yield* body(); keep(parent, value); return value; }
  finally { unwind(ctx, depth); ctx.scopes.pop(); }
}
export function* expressionTask<Y, N, T extends HeapValue | void>(site: Site, body: () => Generator<Y, T, N>): Generator<Y, T, N> {
  const ctx = context(), depth = ctx.roots.length, parent = ctx.roots.at(-1)?.frame;
  push(ctx, 'expression');
  try { const value = yield* body(); keep(parent, value); return value; }
  catch (error) {
    if (error instanceof NexError && error.site === undefined) throw new NexError(error.code, error.message, site);
    throw error;
  } finally { unwind(ctx, depth); }
}
export function* conditionTask<Y, N>(body: () => Generator<Y, boolean, N>): Generator<Y, boolean, N> {
  const ctx = context(), depth = ctx.roots.length; push(ctx, 'statement');
  try { return yield* body(); } finally { unwind(ctx, depth); }
}
export function* functionTaskBody<Y, N, T extends HeapValue | void>(inputs: ReadonlyArray<HeapValue>, body: () => Generator<Y, void, N>): Generator<Y, T, N> {
  const ctx = context(), depth = ctx.roots.length, parent = ctx.roots.at(-1)?.frame;
  const frame = push(ctx, 'scope'); ctx.scopes.push(frame);
  try {
    for (const input of inputs) frame.keep(input);
    try { yield* body(); return undefined as T; }
    catch (error) {
      if (!(error instanceof ReturnCompletion)) throw error;
      const owner = acquire(error);
      try { keep(parent, error.value); return error.value as T; }
      finally { owner.close(); }
    }
  } finally { unwind(ctx, depth); ctx.scopes.pop(); }
}
export function* handleTask<Y, N>(body: () => Generator<Y, void, N>, handler: (error: unknown) => Generator<Y, boolean, N>): Generator<Y, void, N> {
  try { yield* body(); }
  catch (error) {
    if (!(error instanceof SourceCompletion)) throw error;
    const owner = acquire(error);
    try { if (!(yield* handler(error))) rethrow(error); }
    finally { owner.close(); }
  }
}
export function* finalizeTask<Y, N>(body: () => Generator<Y, void, N>, finalizer: () => Generator<Y, void, N>): Generator<Y, void, N> {
  let pending: Completion | undefined, owner: RootFrame | undefined;
  try {
    try { yield* body(); }
    catch (error) { if (!completion(error)) throw error; pending = error; owner = acquire(error); }
    yield* finalizer();
    if (pending !== undefined) rethrow(pending);
  } finally { owner?.close(); }
}
export class TaskSession {
  readonly owner: Context;
  readonly lanes = new Map<number, Context>();
  private readonly result: RootFrame;
  private closed = false;
  private readonly ownsHeap: boolean;
  constructor(limits: HeapLimits, print?: (text: string) => void, borrowed?: CellHeap) {
    this.ownsHeap = borrowed === undefined;
    this.owner = {heap: borrowed ?? new CellHeap(limits), roots: [], scopes: [], flight: new Map(), output: {text: '', print}};
    this.result = this.owner.heap.frame();
  }
  turn<T>(job: number, body: () => T): T {
    if (this.closed) throw new NexError('E_CELL_CONTEXT', 'managed task session is closed');
    let lane = this.lanes.get(job);
    if (lane === undefined) { lane = {...this.owner, roots: [], scopes: []}; this.lanes.set(job, lane); }
    const previous = active; active = lane;
    try { return body(); } finally { active = previous; }
  }
  payload(error: unknown): HeapValue | undefined { return error instanceof SourceCompletion ? error.value : undefined; }
  release(error: unknown): void {
    if (!completion(error)) return;
    this.owner.flight.get(error)?.close(); this.owner.flight.delete(error);
  }
  retain(error: unknown): void {
    if (!completion(error) || this.owner.flight.has(error)) return;
    const frame = this.owner.heap.frame(); keep(frame, error.value); this.owner.flight.set(error, frame);
  }
  keepResult(value: HeapValue | void): void { keep(this.result, value); }
  finish(value: HeapValue | void, error: unknown, failed: boolean, render: (value: HeapValue | void) => string): Execution {
    if (!this.ownsHeap) throw new NexError('E_INTERNAL', 'borrowed task session requires an application result owner');
    try {
      let value_json: string | undefined, failure: {code: string; message: string; line: number; file: string; site?: Site} | undefined;
      if (!failed) value_json = render(value);
      else if (error instanceof SourceCompletion) {
        failure = {code: 'E_SOURCE_EXCEPTION', message: error.detail.code + ': ' + error.detail.message, line: error.detail.site[1], file: error.detail.site[0], site: error.detail.site};
        this.release(error);
      } else if (error instanceof NexError) failure = {code: error.code, message: error.message, line: error.site?.[1] ?? 0, file: error.site?.[0] ?? '', site: error.site};
      else throw error;
      this.result.close();
      if (this.owner.flight.size || [...this.lanes.values()].some(lane => lane.roots.length || lane.scopes.length))
        throw new NexError('E_INTERNAL', 'managed tasks retained source frames or completions');
      const beforeCollection = this.owner.heap.stats(); this.owner.heap.collect(); const afterCollection = this.owner.heap.stats();
      if (afterCollection.cells || afterCollection.nodes) throw new NexError('E_INTERNAL', 'managed tasks retained heap roots');
      this.owner.heap.close();
      return {kind: failure === undefined ? 'return' : 'trap', value_json, ...failure, output: this.owner.output.text,
        beforeCollection, afterCollection, afterClose: this.owner.heap.stats()};
    } finally { this.close(); }
  }
  finishBorrowed<T>(value: HeapValue | void, error: unknown, failed: boolean, accept: (value: HeapValue | void) => T): T {
    if (this.ownsHeap) throw new NexError('E_INTERNAL', 'application task session requires a borrowed heap');
    try {
      if (failed) {
        if (error instanceof SourceCompletion) {
          this.release(error);
          throw new NexError('E_SOURCE_EXCEPTION', error.detail.code + ': ' + error.detail.message, error.detail.site);
        }
        throw error;
      }
      // The application adopts state/copies outputs before invocation roots end.
      const result = accept(value);
      this.result.close();
      if (this.owner.flight.size || [...this.lanes.values()].some(lane => lane.roots.length || lane.scopes.length))
        throw new NexError('E_INTERNAL', 'application task retained source frames or completions');
      return result;
    } finally {
      this.close();
      this.owner.heap.collect();
    }
  }
  close(): void {
    if (this.closed) return;
    for (const lane of this.lanes.values()) { unwind(lane, 0); lane.scopes.length = 0; }
    for (const frame of this.owner.flight.values()) frame.close(); this.owner.flight.clear();
    this.result.close(); if (this.ownsHeap) this.owner.heap.close(); this.lanes.clear(); this.closed = true;
  }
}
export function taskOwner(): CellHeap { return context().heap; }
export function print(text: string): void { const ctx = context(); ctx.output.text += text + '\n'; ctx.output.print?.(text); }
export type Execution = Readonly<{
  kind: 'return' | 'trap'; value_json?: string; output: string;
  code?: string; message?: string; line?: number; file?: string;
  site?: Site;
  beforeCollection: HeapStats; afterCollection: HeapStats; afterClose: HeapStats;
}>;
export function run(body: () => HeapValue | void, limits: HeapLimits, render: (value: HeapValue | void) => string, print?: (text: string) => void): Execution {
  const previous = active, ctx: Context = {heap: new CellHeap(limits), roots: [], scopes: [], flight: new Map(), output: {text: '', print}};
  active = ctx; let value_json: string | undefined, failure: {code: string; message: string; line: number; file: string; site?: Site} | undefined;
  try {
    try { scope(() => { const value = body(); value_json = render(value); }); }
    catch (error) {
      if (error instanceof SourceCompletion) {
        const owner = acquire(error);
        try { failure = {code: 'E_SOURCE_EXCEPTION', message: error.detail.code + ': ' + error.detail.message, line: error.detail.site[1], file: error.detail.site[0], site: error.detail.site}; }
        finally { owner.close(); }
      } else if (error instanceof NexError) failure = {code: error.code, message: error.message, line: error.site?.[1] ?? 0, file: error.site?.[0] ?? '', site: error.site === undefined ? undefined : Object.freeze([...error.site]) as Site};
      else throw error;
    }
    if (ctx.flight.size) throw new NexError('E_INTERNAL', 'managed execution retained an abandoned completion');
    const beforeCollection = ctx.heap.stats(); ctx.heap.collect(); const afterCollection = ctx.heap.stats();
    if (afterCollection.nodes !== 0 || afterCollection.cells !== 0) throw new NexError('E_INTERNAL', 'managed execution retained source roots');
    ctx.heap.close();
    return {kind: failure === undefined ? 'return' : 'trap', value_json, ...failure, output: ctx.output.text,
      beforeCollection, afterCollection, afterClose: ctx.heap.stats()};
  } finally {
    unwind(ctx, 0); for (const frame of ctx.flight.values()) frame.close(); ctx.flight.clear();
    ctx.heap.close(); active = previous;
  }
}
