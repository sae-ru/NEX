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
type Context = {heap: CellHeap; roots: Roots[]; scopes: RootFrame[]; flight: Map<Completion, RootFrame>; output: string};
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
export function print(text: string): void { context().output += text + '\n'; }
export type Execution = Readonly<{
  kind: 'return' | 'trap'; value_json?: string; output: string;
  code?: string; message?: string; line?: number; file?: string;
  beforeCollection: HeapStats; afterCollection: HeapStats; afterClose: HeapStats;
}>;
export function run(body: () => HeapValue | void, limits: HeapLimits, render: (value: HeapValue | void) => string): Execution {
  const previous = active, ctx: Context = {heap: new CellHeap(limits), roots: [], scopes: [], flight: new Map(), output: ''};
  active = ctx; let value_json: string | undefined, failure: {code: string; message: string; line: number; file: string} | undefined;
  try {
    try { scope(() => { const value = body(); value_json = render(value); }); }
    catch (error) {
      if (error instanceof SourceCompletion) {
        const owner = acquire(error);
        try { failure = {code: 'E_SOURCE_EXCEPTION', message: error.detail.code + ': ' + error.detail.message, line: error.detail.site[1], file: error.detail.site[0]}; }
        finally { owner.close(); }
      } else if (error instanceof NexError) failure = {code: error.code, message: error.message, line: error.site?.[1] ?? 0, file: error.site?.[0] ?? ''};
      else throw error;
    }
    if (ctx.flight.size) throw new NexError('E_INTERNAL', 'managed execution retained an abandoned completion');
    const beforeCollection = ctx.heap.stats(); ctx.heap.collect(); const afterCollection = ctx.heap.stats();
    if (afterCollection.nodes !== 0 || afterCollection.cells !== 0) throw new NexError('E_INTERNAL', 'managed execution retained source roots');
    ctx.heap.close();
    return {kind: failure === undefined ? 'return' : 'trap', value_json, ...failure, output: ctx.output,
      beforeCollection, afterCollection, afterClose: ctx.heap.stats()};
  } finally {
    unwind(ctx, 0); for (const frame of ctx.flight.values()) frame.close(); ctx.flight.clear();
    ctx.heap.close(); active = previous;
  }
}
