// Matching checked030 bridge: boxed values and explicit roots on the existing
// cooperative task scheduler. Ordinary task/typed-source APIs stay unchanged.
import * as task from './nex-task-runtime.ts';
import * as base from './nex-runtime.ts';
import * as nex from './nex-managed-runtime.ts';
import * as execution from './nex-managed-context.ts';
import {HeapNode, type HeapLimits, type RootFrame} from './nex-managed-heap.ts';
export type Item = nex.Value | void;
export type Request = task.Request;
export type Step<T extends Item> = Generator<Request, T, Item>;
declare const outcome: unique symbol;
export type Call<T extends Item> = {readonly [outcome]?: T};
export {enterTyped, leave, finalizerEnabled} from './nex-task-runtime.ts';
// Representation crossings are confined to this matching-runtime bridge. The
// driver admits boxed graphs through children/capability checks, not JS casts.
function bridge<T>(value: unknown): T { return value as T; }
function pinned<T extends Item>(factory: () => Step<T>, values: ReadonlyArray<nex.Value>, frame: RootFrame): task.Step<base.Value | void> {
  let iterator: Step<T>;
  try { for (const value of values) frame.keep(value); iterator = factory(); }
  catch (error) { frame.close(); throw error; }
  const step = (body: () => IteratorResult<Request, T>): IteratorResult<Request, T> => {
    try { const result = body(); if (result.done) frame.close(); return result; }
    catch (error) { frame.close(); throw error; }
  };
  const result: Step<T> = {
    next: (value?: Item) => step(() => iterator.next(value)),
    throw: (error: unknown) => step(() => iterator.throw(error)),
    return: (value: T) => { try { return step(() => iterator.return(value)); } finally { frame.close(); } },
    [Symbol.iterator]() { return this; },
  };
  return bridge(result);
}
export function call<T extends Item>(factory: () => Step<T>, inputs: ReadonlyArray<nex.Value> = []): Call<T> {
  const heap = execution.taskOwner(), copied = Object.freeze([...inputs]);
  return bridge(task.call(() => pinned(factory, copied, heap.frame()), bridge(copied)));
}
export function* invoke<T extends Item>(value: Call<T>, site?: base.Site): Step<T> {
  return yield* bridge<Step<T>>(task.invoke(bridge<task.Call<base.Value | void>>(value), site));
}
export function* checkpoint(site?: base.Site): Step<void> { yield* bridge<Step<void>>(task.checkpoint(site)); }
export function request(operation: string, values: ReadonlyArray<nex.Value>, site?: base.Site): Request {
  return task.request(operation, bridge(values), site);
}
async function execute<T extends Item>(body: () => Step<T>, limits: HeapLimits, options: task.Options,
    render: (value: Item) => string, print?: (text: string) => void): Promise<execution.Execution> {
  const session = new execution.TaskSession(limits, print);
  const policy: task.ManagedDevelopmentValues = {
    children(value, site) {
      if (value instanceof HeapNode && ['task_scope', 'task', 'channel'].includes(value.kind) &&
          !task.isCapability(value, value.kind as 'task_scope' | 'task' | 'channel'))
        throw new base.NexError('E_TASK_VALUE', 'managed task capability lacks its scheduler owner', site);
      return bridge(nex.taskChildren(value, session));
    },
    capability: kind => bridge(nex.taskCapability(kind)),
    callback: (value, arguments_) => bridge(nex.invoke(bridge<nex.Closure<nex.Value[], Call<Item>>>(value), bridge(arguments_))),
    channelResult: (present, value) => bridge(present ? nex.ok(bridge<nex.Value>(value)) : nex.err(nex.text('E_CHANNEL_CLOSED'), nex.text('channel is closed'))),
    failed: value => value instanceof HeapNode && value.kind === 'failure',
    source: error => execution.details(error) !== undefined,
    payload: error => bridge(session.payload(error)),
    releaseSource: error => session.release(error), retainSource: error => session.retain(error),
    keepResult: value => session.keepResult(bridge<Item>(value)),
    attachRoots: read => { const frame = session.owner.heap.frame(); frame.trackValues(() => bridge(read().filter(value => value !== undefined))); return () => frame.close(); },
    turn: (job, action) => session.turn(job, action),
  };
  let value: Item = undefined, error: unknown, failed = false;
  try {
    const root = session.turn(0, () => call(body));
    value = bridge(await task.runManagedDevelopment(bridge<task.Call<base.Value | void>>(root), policy, options));
  } catch (caught) { error = caught; failed = true; }
  return session.finish(value, error, failed, render);
}

// Private envelope remains available to the independent development corpus.
export async function run<T extends Item>(body: () => Step<T>, limits: HeapLimits, options: task.Options = {}): Promise<execution.Execution> {
  return execute(body, limits, options, nex.representation);
}
// Public030 async host boundary: input conversion happens in the generated root
// scope; copy the checked immutable result before the invocation heap closes.
export async function invokeValue<T extends base.Value | void>(body: () => Step<Item>, limits: HeapLimits,
    schema?: base.Schema, options: task.Options = {}): Promise<T> {
  let result: base.Value | void = undefined;
  const outcome = await execute(body, limits, options, value => {
    result = nex.exportValue(value, schema); return 'null';
  }, text => console.log(text));
  if (outcome.kind === 'trap') throw new base.NexError(outcome.code!, outcome.message!, outcome.site);
  return result as T;
}
