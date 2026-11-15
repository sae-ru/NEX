// Private managed-reference foundation. Ordinary generated clients do not import
// this module. Source lowering must register every live binding/operand/packet;
// JavaScript reachability and nondeterministic host GC are not language roots.
import {NexError} from './nex-runtime.ts';

export type NodeKind = 'string' | 'bytes' | 'list' | 'record' | 'success' | 'failure' | 'enum' | 'closure';
export type HeapValue = bigint | number | boolean | HeapNode | Cell;
export type HeapLimits = Readonly<{maximumCells: number; maximumNodes: number; maximumEdges: number}>;
export type HeapStats = Readonly<{cells: number; nodes: number; edges: number; collections: number}>;
export type Collection = Readonly<{beforeCells: number; afterCells: number; reclaimedCells: number; reclaimedNodes: number}>;
export const defaultLimits: HeapLimits = Object.freeze({maximumCells: 1048576, maximumNodes: 4194304, maximumEdges: 16777216});

function fail(code: string, message: string): never { throw new NexError(code, message); }
const kinds = new Set<NodeKind>(['string', 'bytes', 'list', 'record', 'success', 'failure', 'enum', 'closure']);
const ordinaryNodes = new WeakSet<HeapNode>();
const ownedVector: unique symbol = Symbol('NEX.private.owned-vector');
type Owner = {closed: boolean};
type CellState = {owner: Owner; identity: bigint; values: HeapValue[]};
const cells = new WeakMap<Cell, CellState>();
// Another heap's registry is an external owner, as in the C++ kernel. Ordinary
// immutable nodes can be shared; cells still belong to exactly one heap.
const registryOwners = new WeakMap<object, number>();
type Node = HeapNode | Cell;
function isNode(value: HeapValue): value is Node { return typeof value === 'object' && value !== null; }
function validValue(value: HeapValue): void {
  if (typeof value === 'boolean') return;
  if (typeof value === 'bigint' && value >= -9223372036854775808n && value <= 9223372036854775807n) return;
  if (typeof value === 'number' && Number.isFinite(value)) return;
  if (isNode(value) && (ordinaryNodes.has(value as HeapNode) || cells.has(value as Cell))) return;
  fail('E_CELL_VALUE', 'managed payload is not a supported value');
}
function children(value: Node): ReadonlyArray<HeapValue> {
  const cell = cells.get(value as Cell);
  return cell === undefined ? (value as HeapNode).values : cell.values;
}

// Explicit node identity is necessary even for strings: two equal JS primitive
// strings cannot tell a shared source allocation from two different allocations.
// Text/bytes/nominal/callable metadata belongs to the future checked facade;
// only actual Data::values slots enter this graph (including scalar slots).
export class HeapNode {
  readonly kind: NodeKind;
  readonly values: ReadonlyArray<HeapValue>;
  constructor(kind: NodeKind, values: ReadonlyArray<HeapValue> = [], ownership?: typeof ownedVector) {
    if (!kinds.has(kind)) fail('E_CELL_VALUE', 'unsupported managed payload node kind');
    for (const value of values) validValue(value);
    this.kind = kind; this.values = ownership === ownedVector ? Object.freeze(values) : Object.freeze([...values]);
    ordinaryNodes.add(this); Object.freeze(this);
  }
  // The compiler owns the unpublished builder vector and gives it up here.
  // Freeze that vector in place rather than copy the completed list.
  static publish(kind: NodeKind, values: HeapValue[]): HeapNode { return new HeapNode(kind, values, ownedVector); }
}
export class Cell {
  declare private readonly cellBrand: void;
  private constructor() { fail('E_CELL_TYPE', 'cells are created by their owning heap'); }
}
type FrameState = {active: boolean; roots: Array<() => HeapValue | undefined>; vectors: Array<() => ReadonlyArray<HeapValue>>; temporaries: HeapValue[]};
export interface RootFrame {
  track(read: () => HeapValue | undefined): void;
  trackValues(read: () => ReadonlyArray<HeapValue>): void;
  keep<T extends HeapValue>(value: T): T;
  clearTemporaries(): void;
  close(): void;
}

export class CellHeap {
  readonly #limits: HeapLimits;
  readonly #owner: Owner = {closed: false};
  readonly #nodes = new Set<Node>();
  readonly #frames = new Set<FrameState>();
  readonly #operands: ReadonlyArray<HeapValue>[] = [];
  #cells = 0; #edges = 0; #collections = 0; #nextIdentity = 1n;
  #nextCollection: number;
  #collecting = false;
  constructor(limits: HeapLimits = defaultLimits) {
    for (const value of [limits.maximumCells, limits.maximumNodes, limits.maximumEdges])
      if (!Number.isSafeInteger(value) || value <= 0) fail('E_CELL_LIMIT', 'managed heap limits must be positive safe integers');
    this.#limits = Object.freeze({...limits});
    this.#nextCollection = Math.min(256, limits.maximumNodes);
  }
  #available(): void {
    if (this.#owner.closed) fail('E_CELL_CLOSED', 'managed heap is closed');
    if (this.#collecting) fail('E_CELL_CONTEXT', 'managed root traversal cannot reenter its heap');
  }
  #cell(value: HeapValue): CellState {
    const state = isNode(value) ? cells.get(value as Cell) : undefined;
    if (state === undefined) fail('E_CELL_TYPE', 'expected a managed cell');
    if (state.owner !== this.#owner) fail('E_CELL_HEAP', 'cell belongs to another heap');
    if (!this.#nodes.has(value as Cell) || state.values.length !== 1) fail('E_CELL_CLOSED', 'managed cell is no longer live');
    return state;
  }
  #payloadNode(value: Node): void {
    if (cells.has(value as Cell)) { this.#cell(value); return; }
    if (!ordinaryNodes.has(value as HeapNode)) fail('E_CELL_VALUE', 'unsupported managed payload node');
  }
  #operation<T>(operands: ReadonlyArray<HeapValue>, body: () => T): T {
    this.#available(); this.#operands.push(operands);
    try { return body(); } finally { this.#operands.pop(); }
  }
  frame(): RootFrame {
    this.#available();
    const state: FrameState = {active: true, roots: [], vectors: [], temporaries: []};
    this.#frames.add(state);
    const available = (): void => {
      this.#available();
      if (!state.active) fail('E_CELL_CLOSED', 'managed root frame is closed');
    };
    return Object.freeze({
      track: (read: () => HeapValue | undefined): void => { available(); state.roots.push(read); },
      trackValues: (read: () => ReadonlyArray<HeapValue>): void => { available(); state.vectors.push(read); },
      keep: <T extends HeapValue>(value: T): T => { available(); validValue(value); state.temporaries.push(value); return value; },
      clearTemporaries: (): void => { available(); state.temporaries.length = 0; },
      close: (): void => {
        if (!state.active) return;
        this.#available(); state.active = false; state.roots.length = 0; state.vectors.length = 0; state.temporaries.length = 0;
        this.#frames.delete(state);
      }
    });
  }
  #pending(root: HeapValue): Node[] {
    validValue(root);
    if (!isNode(root)) return [];
    const result: Node[] = [], visited = new Map<Node, boolean>();
    const stack: Array<{value: Node; next: number}> = [];
    let edges = 0;
    const enter = (value: Node): void => {
      this.#payloadNode(value);
      if (this.#nodes.has(value)) return;
      const seen = visited.get(value);
      if (seen !== undefined) {
        if (!seen) fail('E_CELL_GRAPH', 'immutable payload has a cycle outside managed cells');
        return;
      }
      visited.set(value, false);
      if (visited.size > this.#limits.maximumNodes) fail('E_CELL_LIMIT', 'managed payload node limit exceeded');
      stack.push({value, next: 0});
    };
    enter(root);
    while (stack.length) {
      const frame = stack[stack.length - 1], values = children(frame.value);
      if (frame.next < values.length) {
        if (edges++ >= this.#limits.maximumEdges) fail('E_CELL_LIMIT', 'managed payload edge limit exceeded');
        const value = values[frame.next++]; if (isNode(value)) enter(value);
      } else {
        visited.set(frame.value, true); result.push(frame.value); stack.pop();
      }
    }
    return result;
  }
  #append(value: Node): void {
    if (this.#nodes.has(value)) fail('E_CELL_GRAPH', 'managed node registered twice');
    this.#nodes.add(value); registryOwners.set(value, (registryOwners.get(value) ?? 0) + 1);
    this.#edges += children(value).length;
  }
  #remove(value: Node): void {
    this.#edges -= children(value).length; this.#nodes.delete(value);
    const owners = registryOwners.get(value)!;
    if (owners === 1) registryOwners.delete(value); else registryOwners.set(value, owners - 1);
  }
  #prepare(value: HeapValue, extra: number): Node[] {
    if (this.#nodes.size >= this.#nextCollection) this.collect();
    let additions = this.#pending(value);
    const fits = (): boolean => {
      if (extra > this.#limits.maximumNodes || additions.length > this.#limits.maximumNodes - extra ||
          this.#nodes.size > this.#limits.maximumNodes - extra - additions.length) return false;
      if (extra > this.#limits.maximumEdges || this.#edges > this.#limits.maximumEdges - extra) return false;
      let remaining = this.#limits.maximumEdges - extra - this.#edges;
      for (const node of additions) {
        if (children(node).length > remaining) return false;
        remaining -= children(node).length;
      }
      return true;
    };
    if (!fits()) {
      this.collect(); additions = this.#pending(value);
      if (!fits()) fail('E_CELL_LIMIT', 'managed heap node or edge limit exceeded');
    }
    return additions;
  }
  create(initial: HeapValue): Cell {
    return this.#operation([initial], () => {
      if (this.#cells >= this.#limits.maximumCells) this.collect();
      if (this.#cells >= this.#limits.maximumCells) fail('E_CELL_LIMIT', 'managed cell limit exceeded');
      if (this.#nextIdentity > 9223372036854775807n) fail('E_CELL_LIMIT', 'managed cell identities exhausted');
      const additions = this.#prepare(initial, 1);
      const created = Object.freeze(Object.create(Cell.prototype)) as Cell;
      cells.set(created, {owner: this.#owner, identity: this.#nextIdentity, values: [initial]});
      for (const node of additions) this.#append(node);
      this.#append(created); ++this.#cells; ++this.#nextIdentity; return created;
    });
  }
  read(value: HeapValue): HeapValue { this.#available(); return this.#cell(value).values[0]; }
  write(value: HeapValue, next: HeapValue): void {
    this.#operation([value, next], () => {
      const target = this.#cell(value), additions = this.#prepare(next, 0);
      for (const node of additions) this.#append(node);
      target.values[0] = next;
    });
  }
  collect(): Collection {
    this.#available(); this.#collecting = true;
    try {
      const beforeCells = this.#cells, marked = new Set<Node>(), work: HeapValue[] = [];
      for (const frame of this.#frames) {
        for (const read of frame.roots) { const value = read(); if (value !== undefined) { validValue(value); work.push(value); } }
        for (const read of frame.vectors) for (const value of read()) { validValue(value); work.push(value); }
        for (const value of frame.temporaries) work.push(value);
      }
      for (const operands of this.#operands) for (const value of operands) { validValue(value); work.push(value); }
      for (const node of this.#nodes) if (registryOwners.get(node)! > 1) work.push(node);
      // Traverse unregistered immutable root containers too: their children may
      // be registered cells even though the container never entered a payload.
      while (work.length) {
        const value = work.pop()!;
        if (!isNode(value) || marked.has(value)) continue;
        this.#payloadNode(value); marked.add(value);
        for (const child of children(value)) work.push(child);
      }
      let reclaimedCells = 0, reclaimedNodes = 0;
      for (const node of this.#nodes) if (!marked.has(node)) {
        const cell = cells.get(node as Cell);
        if (cell !== undefined) { this.#edges -= cell.values.length; cell.values.length = 0; --this.#cells; ++reclaimedCells; }
        this.#remove(node); ++reclaimedNodes;
      }
      ++this.#collections;
      this.#nextCollection = Math.min(this.#limits.maximumNodes, Math.max(256,
        this.#nodes.size > this.#limits.maximumNodes / 2 ? this.#limits.maximumNodes : this.#nodes.size * 2));
      return {beforeCells, afterCells: this.#cells, reclaimedCells, reclaimedNodes};
    } finally { this.#collecting = false; }
  }
  stats(): HeapStats { return {cells: this.#cells, nodes: this.#nodes.size, edges: this.#edges, collections: this.#collections}; }
  close(): void {
    if (this.#owner.closed) return;
    this.#available(); this.#owner.closed = true;
    for (const frame of this.#frames) { frame.active = false; frame.roots.length = 0; frame.vectors.length = 0; frame.temporaries.length = 0; }
    this.#frames.clear();
    for (const node of this.#nodes) { const cell = cells.get(node as Cell); if (cell !== undefined) cell.values.length = 0; }
    for (const node of this.#nodes) {
      const owners = registryOwners.get(node)!;
      if (owners === 1) registryOwners.delete(node); else registryOwners.set(node, owners - 1);
    }
    this.#nodes.clear(); this.#cells = 0; this.#edges = 0;
  }
}
