// Matching checked030 application owner. Source state never crosses the host
// boundary; only copied wire events, views and commands do.
import {CellHeap, type HeapLimits, type HeapStats, type RootFrame} from './nex-managed-heap.ts';
import type {Value} from './nex-managed-runtime.ts';
import {invokeApplication, type Step, type Item} from './nex-managed-task-runtime.ts';
import {NexError, type Value as HostValue} from './nex-runtime.ts';
import type {Options} from './nex-task-runtime.ts';
export type ApplicationOptions = Pick<Options, 'steps' | 'timeoutMs' | 'workers' | 'signal' | 'complete'>;
export type ApplicationDefinition<E extends HostValue, Snapshot> = Readonly<{
  initial(): Step<Value>;
  update(state: Value, event: E): Step<Value>;
  copyEvent(event: E): E;
  accept(value: Item): Readonly<{state: Value; snapshot: Snapshot}>;
}>;
type Job<E, Snapshot> = {event?: E; resolve(value: Snapshot): void; reject(error: unknown): void};
export type ApplicationStatistics = Readonly<{phase: 'starting' | 'ready' | 'closing' | 'closed'; pending: number; active: boolean; completed: number; heap: HeapStats}>;
export class Application<E extends HostValue, Snapshot> {
  readonly ready: Promise<Snapshot>;
  readonly #heap: CellHeap;
  readonly #root: RootFrame;
  readonly #definition: ApplicationDefinition<E, Snapshot>;
  readonly #limits: HeapLimits;
  readonly #options: ApplicationOptions;
  readonly #jobs: Job<E, Snapshot>[] = [];
  readonly #closed: Promise<void>;
  #resolveClosed!: () => void;
  #phase: ApplicationStatistics['phase'] = 'starting';
  #state: Value | undefined;
  #running = false;
  #scheduled = false;
  #abort: AbortController | undefined;
  #completed = 0;
  #failure: unknown;
  readonly #onAbort = () => { void this.close(); };
  constructor(definition: ApplicationDefinition<E, Snapshot>, limits: HeapLimits, options: ApplicationOptions = {}) {
    if (typeof options !== 'object' || options === null) throw new NexError('E_RANGE', 'application options must be an object');
    const signal = options.signal;
    if (signal !== undefined && (signal === null || typeof signal.aborted !== 'boolean' ||
        typeof signal.addEventListener !== 'function' || typeof signal.removeEventListener !== 'function'))
      throw new NexError('E_RANGE', 'application signal must support AbortSignal');
    if (options.complete !== undefined && typeof options.complete !== 'function') throw new NexError('E_RANGE', 'application completion hook must be callable');
    this.#definition = definition; this.#limits = Object.freeze({...limits}); this.#options = {steps: options.steps, timeoutMs: options.timeoutMs, workers: options.workers, signal: options.signal, complete: options.complete};
    this.#heap = new CellHeap(limits); this.#root = this.#heap.frame(); this.#root.track(() => this.#state);
    this.#closed = new Promise(resolve => { this.#resolveClosed = resolve; });
    this.ready = this.#enqueue();
    // Closing before initialization remains observable through ready, without an
    // unhandled rejection when a host only awaits the lifecycle close promise.
    void this.ready.catch(() => {});
    options.signal?.addEventListener('abort', this.#onAbort);
    if (options.signal?.aborted) this.#onAbort();
  }
  statistics(): ApplicationStatistics {
    return Object.freeze({phase: this.#phase, pending: this.#jobs.length, active: this.#running,
      completed: this.#completed, heap: Object.freeze(this.#heap.stats())});
  }
  dispatch(event: E): Promise<Snapshot> {
    if (this.#phase === 'closing' || this.#phase === 'closed') return Promise.reject(this.#failure ?? new NexError('E_CELL_CLOSED', 'application is closed'));
    let copied: E;
    try { copied = this.#definition.copyEvent(event); }
    catch (error) { return Promise.reject(error); }
    if (this.#jobs.length >= 256) return Promise.reject(new NexError('E_LIMIT', 'application event queue exceeds256'));
    return this.#enqueue(copied);
  }
  close(): Promise<void> {
    if (this.#phase !== 'closed' && this.#phase !== 'closing') {
      this.#phase = 'closing'; this.#failure ??= new NexError('E_CANCELLED', 'application was closed');
      this.#abort?.abort();
      for (const job of this.#jobs.splice(0)) job.reject(this.#failure);
      if (!this.#running) this.#finishClose();
    }
    return this.#closed;
  }
  #isClosing(): boolean { return this.#phase === 'closing' || this.#phase === 'closed'; }
  #enqueue(event?: E): Promise<Snapshot> {
    const result = new Promise<Snapshot>((resolve, reject) => { this.#jobs.push({event, resolve, reject}); });
    this.#schedule(); return result;
  }
  #schedule(): void {
    if (this.#scheduled || this.#running || this.#phase === 'closed') return;
    this.#scheduled = true;
    queueMicrotask(() => { this.#scheduled = false; void this.#pump(); });
  }
  async #pump(): Promise<void> {
    if (this.#running || this.#phase === 'closed') return;
    if (this.#phase === 'closing') { this.#finishClose(); return; }
    const job = this.#jobs.shift(); if (!job) return;
    this.#running = true; this.#abort = new AbortController();
    try {
      const state = this.#state;
      const snapshot = await invokeApplication(() => job.event === undefined ? this.#definition.initial() :
        this.#definition.update(state!, job.event), this.#heap, this.#limits, value => {
          if (this.#isClosing()) throw this.#failure;
          const next = this.#definition.accept(value);
          this.#state = next.state;
          return next.snapshot;
        }, {...this.#options, signal: this.#abort.signal});
      if (this.#isClosing()) throw this.#failure;
      ++this.#completed; this.#phase = 'ready'; job.resolve(snapshot);
    } catch (error) {
      this.#failure = error; job.reject(error);
      void this.close();
    } finally {
      this.#running = false; this.#abort = undefined;
      if (this.#isClosing()) this.#finishClose();
      else this.#schedule();
    }
  }
  #finishClose(): void {
    if (this.#running || this.#phase === 'closed') return;
    this.#options.signal?.removeEventListener('abort', this.#onAbort);
    this.#state = undefined; this.#root.close(); this.#heap.collect(); this.#heap.close();
    this.#phase = 'closed'; this.#resolveClosed();
  }
}
