import {CellHeap, HeapNode, type HeapValue, type NodeKind} from './nex-managed-heap.ts';
import {NexError} from './nex-runtime.ts';
type Token = number | boolean | {ref: string} | {i64: string} | {f64: number};
type Command = {op: string; id?: string; from?: string; cell?: string; value?: Token; values?: Token[]; kind?: NodeKind; a?: string; b?: string; count?: number};
export type Trace = {limits?: number[]; commands: Command[]};
export function runTrace(document: Trace): unknown {
  const limits = document.limits;
  const heap = new CellHeap(limits === undefined ? undefined : {maximumCells: limits[0], maximumNodes: limits[1], maximumEdges: limits[2]});
  const frame = heap.frame(), values = new Map<string, HeapValue>(), tracked = new Set<string>();
  const bind = (name: string, value: HeapValue): void => {
    values.set(name, value);
    if (!tracked.has(name)) { tracked.add(name); frame.track(() => values.get(name)); }
  };
  const resolve = (token: Token): HeapValue => {
    if (typeof token === 'boolean') return token;
    if (typeof token === 'number') return BigInt(token);
    if ('ref' in token) return values.get(token.ref)!;
    if ('f64' in token) return token.f64;
    return BigInt(token.i64);
  };
  const events: Array<Record<string, unknown>> = [];
  for (const command of document.commands) {
    const c = command, event: Record<string, unknown> = {op: c.op};
    try {
      switch (c.op) {
        case 'node': bind(c.id!, new HeapNode(c.kind!, (c.values ?? []).map(resolve))); break;
        case 'literal': bind(c.id!, resolve(c.value!)); break;
        case 'create': bind(c.id!, heap.create(resolve(c.value!))); break;
        case 'alias': bind(c.id!, values.get(c.from!)!); break;
        case 'read': bind(c.id!, heap.read(values.get(c.cell!)!)); break;
        case 'write': heap.write(values.get(c.cell!)!, resolve(c.value!)); break;
        case 'drop': values.delete(c.id!); break;
        case 'same': event.same = values.get(c.a!) === values.get(c.b!); break;
        case 'collect': event.collection = heap.collect(); break;
        case 'chain': case 'deep': {
          let head: HeapValue = 0n;
          const local = heap.frame(); local.track(() => head);
          try {
            for (let i = 0; i < c.count!; ++i) {
              head = new HeapNode('list', [head]);
              if (c.op === 'chain') head = heap.create(head);
            }
            if (c.op === 'deep') head = heap.create(head);
            bind(c.id!, head);
          } finally { local.close(); }
          break;
        }
        case 'close': heap.close(); break;
        default: throw new Error('unknown managed heap trace operation');
      }
    } catch (error) {
      if (!(error instanceof NexError)) throw error;
      event.code = error.code;
    }
    event.stats = heap.stats(); events.push(event);
  }
  values.clear(); frame.close(); heap.close();
  return {events, final: heap.stats()};
}

function require(value: boolean, message: string): void { if (!value) throw new Error(message); }
function rejects(code: string, action: () => unknown): void {
  try { action(); } catch (error) { if (error instanceof NexError && error.code === code) return; throw error; }
  throw new Error('expected ' + code);
}
export function rootChecks(): number {
  let checked = 0;
  {
    const heap = new CellHeap({maximumCells: 1, maximumNodes: 8, maximumEdges: 16}), frame = heap.frame();
    const cell = frame.keep(heap.create(1n));
    rejects('E_CELL_LIMIT', () => heap.create(2n));
    frame.clearTemporaries(); const next = frame.keep(heap.create(2n));
    require(heap.read(next) === 2n && heap.stats().cells === 1, 'temporary root release did not free capacity');
    rejects('E_CELL_CLOSED', () => heap.read(cell));
    heap.close(); frame.close(); frame.close();
    rejects('E_CELL_CLOSED', () => frame.keep(1n)); ++checked;
  }
  {
    const heap = new CellHeap({maximumCells: 1, maximumNodes: 8, maximumEdges: 16});
    const cell = heap.create(1n);
    rejects('E_CELL_LIMIT', () => heap.create(cell));
    require(heap.read(cell) === 1n, 'an allocation operand was reclaimed');
    heap.close(); ++checked;
  }
  {
    const heap = new CellHeap({maximumCells: 8, maximumNodes: 3, maximumEdges: 16});
    const cell = heap.create(1n), other = heap.create(2n);
    heap.create(3n);
    // No explicit outside roots: the receiver and next payload are rooted by
    // write itself while a threshold/capacity collection runs.
    heap.write(cell, new HeapNode('record', [other]));
    require(heap.read(cell) instanceof HeapNode && heap.stats().cells === 2 && heap.stats().collections > 0, 'write lost its receiver or operand');
    heap.close(); ++checked;
  }
  {
    const heap = new CellHeap(), frame = heap.frame();
    let cell: HeapValue | undefined = heap.create(1n); frame.track(() => cell);
    heap.collect(); require(heap.stats().cells === 1, 'binding getter root was lost');
    cell = undefined; heap.collect(); require(heap.stats().nodes === 0, 'binding getter retained its former value');
    frame.close(); heap.close(); ++checked;
  }
  {
    const heap = new CellHeap(), frame = heap.frame();
    frame.track(() => { heap.create(1n); return undefined; });
    rejects('E_CELL_CONTEXT', () => heap.collect());
    require(heap.stats().nodes === 0 && heap.stats().collections === 0, 'failed root traversal changed the heap');
    frame.close(); heap.collect(); heap.close(); ++checked;
  }
  {
    const first = new CellHeap(), second = new CellHeap(), shared = new HeapNode('list', [1n]);
    first.create(shared); second.create(shared);
    second.collect(); require(second.stats().cells === 0 && second.stats().nodes === 1, 'another registry owner was ignored');
    first.close(); second.collect(); require(second.stats().nodes === 0, 'closed registry retained shared ordinary nodes');
    second.close(); ++checked;
  }
  {
    const first = new CellHeap(), second = new CellHeap(), cell = first.create(1n);
    rejects('E_CELL_HEAP', () => second.create(new HeapNode('list', [cell])));
    rejects('E_CELL_HEAP', () => second.read(cell));
    require(first.read(cell) === 1n, 'foreign heap rejection changed the cell');
    first.close(); second.close(); ++checked;
  }
  {
    const heap = new CellHeap();
    rejects('E_CELL_VALUE', () => heap.create('unboxed' as unknown as HeapValue));
    rejects('E_CELL_VALUE', () => heap.create({} as HeapValue));
    rejects('E_CELL_VALUE', () => heap.create(Infinity));
    rejects('E_CELL_VALUE', () => heap.create(9223372036854775808n));
    for (const n of [0, -1, 1.5, Infinity, Number.MAX_SAFE_INTEGER + 1])
      rejects('E_CELL_LIMIT', () => new CellHeap({maximumCells: n, maximumNodes: 8, maximumEdges: 16}));
    heap.close(); ++checked;
  }
  {
    const heap = new CellHeap(), frame = heap.frame(), buffer: HeapValue[] = [heap.create(1n)];
    frame.trackValues(() => buffer);
    heap.collect(); require(heap.stats().cells === 1, 'unpublished builder contents were not rooted');
    buffer.length = 0; heap.collect(); require(heap.stats().nodes === 0, 'cleared builder retained its former members');
    frame.close(); heap.close(); ++checked;
  }
  {
    const heap = new CellHeap({maximumCells: 1, maximumNodes: 8, maximumEdges: 16});
    const caller = heap.frame(), callee = heap.frame();
    try { caller.keep(callee.keep(heap.create(1n))); } finally { callee.close(); }
    rejects('E_CELL_LIMIT', () => heap.create(2n));
    caller.clearTemporaries(); const next = caller.keep(heap.create(2n));
    require(heap.read(next) === 2n, 'return-to-caller roots did not release after their use');
    caller.close(); heap.close(); ++checked;
  }
  return checked;
}
