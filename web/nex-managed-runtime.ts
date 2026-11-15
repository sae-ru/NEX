// Checked private source values. Public browser modules keep nex-runtime.ts.
import * as base from './nex-runtime.ts';
import * as execution from './nex-managed-context.ts';
import {Cell as CellIdentity, HeapNode, type HeapValue, type HeapLimits} from './nex-managed-heap.ts';
export {NexError, type Site} from './nex-runtime.ts';
export {scope, expression, root, beginStatement, endStatement, condition, functionBody,
  returned, handle, finalize, details, matches, rethrow} from './nex-managed-context.ts';
export type {Execution} from './nex-managed-context.ts';
export type Value = HeapValue;
declare const textBrand: unique symbol, bytesBrand: unique symbol, listBrand: unique symbol,
  resultBrand: unique symbol, closureBrand: unique symbol, cellBrand: unique symbol;
export const TYPE: unique symbol = Symbol('NEX.private.managed.type');
export type Text = HeapNode & {readonly [textBrand]: true};
export type ByteBuffer = HeapNode & {readonly [bytesBrand]: true};
export type List<T extends Value> = HeapNode & {readonly [listBrand]: T};
export type Result<T extends Value> = HeapNode & {readonly [resultBrand]: T};
export type RecordValue = HeapNode & {readonly [TYPE]: string};
export type Closure<A extends Value[], R extends Value | void> = HeapNode & {readonly [closureBrand]: (...args: A) => R};
export type Cell<T extends Value> = CellIdentity & {readonly [cellBrand]: T};
type Builder = {items: Value[]; active: boolean};
type Metadata = Readonly<{text?: string; bytes?: base.ByteBuffer; nominal?: string; tag?: string;
  names?: ReadonlyArray<string>; callable?: unknown; builder?: Builder}>;
const metadata = new WeakMap<HeapNode, Metadata>();
function meta(node: HeapNode): Metadata {
  const result = metadata.get(node); if (result === undefined) throw new base.NexError('E_RUNTIME', 'managed value metadata is missing');
  return result;
}
function make<T extends HeapNode>(kind: HeapNode['kind'], values: ReadonlyArray<Value>, data: Metadata = {}): T {
  const node = new HeapNode(kind, values); metadata.set(node, Object.freeze(data)); return node as T;
}
export function text(value: string, site?: base.Site): Text { return make('string', [], {text: base.string(value, site)}); }
function raw(value: Text): string { return meta(value).text!; }
function octets(value: ByteBuffer): base.ByteBuffer { return meta(value).bytes!; }
function bytesValue(value: base.ByteBuffer): ByteBuffer { return make('bytes', [], {bytes: value}); }
export function textConcat(a: Text, b: Text): Text { return text(raw(a) + raw(b)); }
export function textEqual(a: Text, b: string): boolean { return raw(a) === b; }
export function list<T extends Value>(items: ReadonlyArray<T>): List<T> { return make('list', items); }
export function record<T extends RecordValue>(name: string, fields: ReadonlyArray<readonly [string, Value]>): T {
  return make('record', fields.map(field => field[1]), {nominal: name, names: Object.freeze(fields.map(field => field[0]))});
}
export function enumeration<T extends RecordValue>(name: string, tag: string, fields: ReadonlyArray<readonly [string, Value]>): T {
  return make('enum', fields.map(field => field[1]), {nominal: name, tag, names: Object.freeze(fields.map(field => field[0]))});
}
export function field<T extends Value>(value: HeapNode, offset: number): T { return value.values[offset] as T; }
export function caseName(value: HeapNode): string { return meta(value).tag!; }
export function captured<A extends Value[], R extends Value | void>(values: ReadonlyArray<Value>, callback: (...args: A) => R): Closure<A, R> {
  return make('closure', values, {callable: callback});
}
export function invoke<A extends Value[], R extends Value | void>(value: Closure<A, R>, args: A): R {
  const callback = meta(value).callable! as (...args: A) => R; return callback(...args);
}
export function cellNew<T extends Value>(value: T): Cell<T> { return execution.heap().create(value) as Cell<T>; }
export function cellRead<T extends Value>(value: Cell<T>): T { return execution.heap().read(value) as T; }
export function cellWrite<T extends Value>(value: Cell<T>, next: T): void { execution.heap().write(value, next); }
export function cellCollect(): void { execution.heap().collect(); }
export function ok<T extends Value>(value: T): Result<T> { return make('success', [value]); }
export function err<T extends Value>(code: Text, message: Text): Result<T> {
  return make('failure', [text(raw(message))], {text: raw(code)});
}
function failure<T extends Value>(code: string, message: string): Result<T> { return make('failure', [text(message)], {text: code}); }
export function isOk<T extends Value>(value: Result<T>): boolean { return value.kind === 'success'; }
export function unwrap<T extends Value>(value: Result<T>, site?: base.Site): T {
  if (!isOk(value)) throw new base.NexError('E_RESULT', meta(value).text + ': ' + raw(value.values[0] as Text), site);
  return value.values[0] as T;
}
export function errorCode<T extends Value>(value: Result<T>): Text { return text(isOk(value) ? '' : meta(value).text!); }
export function errorMessage<T extends Value>(value: Result<T>): Text { return text(isOk(value) ? '' : raw(value.values[0] as Text)); }
export function propagate<T extends Value>(value: Result<T>): T { if (!isOk(value)) execution.returned(value); return value.values[0] as T; }
export function index<T extends Value>(value: List<T>, at: bigint, site?: base.Site): T {
  if (at < 0n || at >= BigInt(value.values.length)) throw new base.NexError('E_BOUNDS', 'index is outside collection bounds', site);
  return value.values[Number(at)] as T;
}
export function length(value: Text | ByteBuffer | List<Value>): bigint {
  if (value.kind === 'string') return BigInt(Array.from(raw(value as Text)).length);
  if (value.kind === 'bytes') return octets(value as ByteBuffer).length;
  return BigInt(value.values.length);
}
export function character(value: Text, at: bigint, site?: base.Site): Text { return text(base.character(raw(value), at, site)); }
export function slice(value: Text, start: bigint, count: bigint, site?: base.Site): Text { return text(base.slice(raw(value), start, count, site)); }
export function contains(value: Text, part: Text): boolean { return raw(value).includes(raw(part)); }
export function concat<T extends Value>(a: List<T>, b: List<T>): List<T> { return list([...a.values, ...b.values] as T[]); }
export function push<T extends Value>(value: List<T>, item: T): List<T> { return list([...value.values, item] as T[]); }
export function set<T extends Value>(value: List<T>, at: bigint, item: T, site?: base.Site): List<T> {
  index(value, at, site); const items = [...value.values] as T[]; items[Number(at)] = item; return list(items);
}
export function bytesFromIntegers(value: List<bigint>): Result<ByteBuffer> {
  const result = base.bytesFromIntegers(value.values as ReadonlyArray<bigint>);
  return base.isOk(result) ? ok(bytesValue(base.unwrap(result))) : failure(base.errorCode(result), base.errorMessage(result));
}
export function utf8Bytes(value: Text, site?: base.Site): ByteBuffer { return bytesValue(base.utf8Bytes(raw(value), site)); }
export function decodeUTF8(value: ByteBuffer): Result<Text> {
  const result = base.decodeUTF8(octets(value));
  return base.isOk(result) ? ok(text(base.unwrap(result))) : failure(base.errorCode(result), base.errorMessage(result));
}
export function encodeBase64(value: ByteBuffer): Text { return text(base.encodeBase64(octets(value))); }
export function decodeBase64(value: Text): Result<ByteBuffer> {
  const result = base.decodeBase64(raw(value));
  return base.isOk(result) ? ok(bytesValue(base.unwrap(result))) : failure(base.errorCode(result), base.errorMessage(result));
}
export function bytesIndex(value: ByteBuffer, at: bigint, site?: base.Site): bigint { return base.bytesIndex(octets(value), at, site); }
export function bytesPush(value: ByteBuffer, item: bigint, site?: base.Site): ByteBuffer { return bytesValue(base.bytesPush(octets(value), item, site)); }
export function bytesSet(value: ByteBuffer, at: bigint, item: bigint, site?: base.Site): ByteBuffer { return bytesValue(base.bytesSet(octets(value), at, item, site)); }
export function bytesSlice(value: ByteBuffer, start: bigint, count: bigint, site?: base.Site): ByteBuffer { return bytesValue(base.bytesSlice(octets(value), start, count, site)); }
export function bytesConcat(a: ByteBuffer, b: ByteBuffer, site?: base.Site): ByteBuffer { return bytesValue(base.bytesConcat(octets(a), octets(b), site)); }
export function asInteger(value: number): Result<bigint> {
  const result = base.asInteger(value); return base.isOk(result) ? ok(base.unwrap(result)) : failure(base.errorCode(result), base.errorMessage(result));
}
export {add, sub, mul, div, rem, neg, assert, checked, floatAdd, floatSub, floatMul,
  floatDiv, floatRem, floatNeg, asFloat, invalidEnum} from './nex-runtime.ts';
export function equal(a: Value, b: Value): boolean {
  if (a === b) return true;
  if (!(a instanceof HeapNode) || !(b instanceof HeapNode) || a.kind !== b.kind) return false;
  if (a.kind === 'closure') return false;
  const x = meta(a), y = meta(b);
  if (a.kind === 'bytes') return x.bytes!.equals(y.bytes!);
  if (x.text !== y.text || x.nominal !== y.nominal || x.tag !== y.tag || a.values.length !== b.values.length) return false;
  if (x.names?.length !== y.names?.length || x.names?.some((name, i) => name !== y.names![i])) return false;
  return a.values.every((value, i) => equal(value, b.values[i]));
}
function quoted(value: string): string { return '"' + value.replace(/["\\\u0000-\u001f]/g, c => c === '"' || c === '\\' ? '\\' + c : '\\u' + c.charCodeAt(0).toString(16).padStart(4, '0')) + '"'; }
export function representation(value: Value | void): string {
  if (value === undefined) return 'null';
  if (typeof value === 'number') return base.formatFloat(value);
  if (typeof value === 'boolean' || typeof value === 'bigint') return String(value);
  if (value instanceof CellIdentity) return quoted('<cell>');
  const data = meta(value);
  switch (value.kind) {
    case 'string': return quoted(data.text!);
    case 'bytes': return quoted(data.bytes!.base64());
    case 'closure': return quoted('<function>');
    case 'success': return '{"ok":' + representation(value.values[0]) + '}';
    case 'failure': return '{"error":{"code":' + quoted(data.text!) + ',"message":' + representation(value.values[0]) + '}}';
    case 'list': return '[' + value.values.map(representation).join(',') + ']';
    case 'record': case 'enum': {
      const fields = '{' + value.values.map((value, i) => quoted(data.names![i]) + ':' + representation(value)).join(',') + '}';
      return value.kind === 'enum' ? '{"case":' + quoted(data.tag!) + ',"fields":' + fields + '}' : fields;
    }
  }
}
function printable(value: Value): string {
  if (value instanceof CellIdentity) return '<cell>';
  if (value instanceof HeapNode && value.kind === 'string') return raw(value as Text);
  if (value instanceof HeapNode && value.kind === 'closure') return '<function>';
  return representation(value);
}
export function str(value: Value): Text { return text(printable(value)); }
export function print(value: Value): void { execution.print(printable(value)); }
export function listBuilderStart<T extends Value>(): List<T> {
  const builder: Builder = {items: [], active: true};
  execution.rootValues(() => builder.active ? builder.items : []);
  return make('list', [], {builder});
}
function builder(value: HeapNode): Builder {
  const state = meta(value).builder;
  if (state === undefined || !state.active) throw new base.NexError('E_RUNTIME', 'cannot append to a published list');
  return state;
}
export function listBuilderAppend<T extends Value>(value: List<T>, item: T): void { builder(value).items.push(item); }
export function listBuilderFinish<T extends Value>(value: List<T>): List<T> {
  const state = builder(value), result = HeapNode.publish('list', state.items) as List<T>;
  metadata.set(result, Object.freeze({})); state.active = false; return result;
}
export function textBuilderJoin(value: List<Text>): Text {
  const state = builder(value), result = text((state.items as Text[]).map(raw).join('')); state.active = false; return result;
}
export function bytesBuilderFinish(value: List<bigint>, site?: base.Site): ByteBuffer {
  const state = builder(value), result = bytesValue(base.bytesBuilderFinish(state.items as bigint[], site)); state.active = false; return result;
}
// Conversion uses the ordinary checked JSON implementation, with an equally
// bounded private traversal before creating host objects. No cell/closure enters
// the JSON boundary. Text and actual Data slots retain their private identities.
function hostValue(value: Value, depth = 0, budget = {nodes: 0}): base.Value {
  if (depth > 64 || ++budget.nodes > 100000) throw new base.NexError('E_JSON', 'JSON value exceeds depth/node limit');
  if (typeof value !== 'object') return value;
  if (value instanceof CellIdentity) throw new base.NexError('E_JSON', 'cell values cannot cross the JSON boundary');
  if (value.values.length > 10000) throw new base.NexError('E_JSON', 'JSON collection exceeds item limit');
  const data = meta(value), child = (v: Value): base.Value => hostValue(v, depth + 1, budget);
  switch (value.kind) {
    case 'string': return data.text!;
    case 'bytes': return data.bytes!;
    case 'closure': throw new base.NexError('E_JSON', 'function values cannot cross the JSON boundary');
    case 'list': return base.list(value.values.map(child));
    case 'success': return base.ok(child(value.values[0]));
    case 'failure': return base.err(data.text!, raw(value.values[0] as Text));
    case 'record': case 'enum': {
      const fields = value.values.map((v, i): readonly [string, base.Value] => [data.names![i], child(v)]);
      return value.kind === 'enum' ? base.enumeration(data.nominal!, data.tag!, fields) : base.record(data.nominal!, fields);
    }
  }
}
function sourceValue(value: base.Value): Value {
  if (typeof value === 'string') return text(value);
  if (typeof value !== 'object') {
    if (typeof value === 'function') throw new base.NexError('E_JSON', 'function values cannot cross the JSON boundary');
    return value;
  }
  if (value instanceof base.ByteBuffer) return bytesValue(value);
  if (Array.isArray(value)) return list(value.map(sourceValue));
  const recordValue = value as base.RecordValue;
  if (recordValue[base.TYPE] === 'nex.result.ok') return ok(sourceValue(base.unwrap(recordValue as base.Result<base.Value>)));
  if (recordValue[base.TYPE] === 'nex.result.error') return failure(base.errorCode(recordValue as base.Result<base.Value>), base.errorMessage(recordValue as base.Result<base.Value>));
  const fields = Object.keys(recordValue).map((name): readonly [string, Value] => [name, sourceValue(recordValue[name])]);
  return recordValue[base.CASE] === undefined ? record(recordValue[base.TYPE], fields) : enumeration(recordValue[base.TYPE], recordValue[base.CASE]!, fields);
}
export function encodeJSON(value: Value, site?: base.Site): Text {
  try { return text(base.encodeJSON(hostValue(value), site)); }
  catch (error) { if (error instanceof base.NexError && error.site === undefined && site) throw new base.NexError(error.code, error.message, site); throw error; }
}
export function decodeJSON<T extends Value>(value: Text, schema: base.Schema): Result<T> {
  return sourceValue(base.decodeJSON(raw(value), schema)) as Result<T>;
}
export type PayloadKind = 'i64' | 'bool' | 'f64' | 'str' | 'bytes' | 'list' | 'record' | 'enum' | 'result' | 'function' | 'cell';
const payloadNodeKinds: Partial<Record<PayloadKind, HeapNode['kind']>> = {str: 'string', bytes: 'bytes', list: 'list', record: 'record', enum: 'enum', function: 'closure'};
function checkedPayload(value: Value, kind: PayloadKind, nominal: string, site: base.Site): void {
  if (kind === 'cell' && value instanceof CellIdentity) return;
  if (kind === 'i64' && typeof value === 'bigint') { base.checked(value, site); return; }
  if (kind === 'bool' && typeof value === 'boolean') return;
  if (kind === 'f64' && typeof value === 'number') { base.finiteFloat(value, site); return; }
  if (value instanceof HeapNode) {
    const expected = payloadNodeKinds[kind];
    if ((kind === 'result' && (value.kind === 'success' || value.kind === 'failure')) ||
        (value.kind === expected && ((kind !== 'record' && kind !== 'enum') || meta(value).nominal === nominal))) return;
  }
  throw new base.NexError('E_SOURCE_TYPE', 'source error payload does not match the checked handler', site);
}
export function raise(code: Text, message: Text, site: base.Site): never { return execution.raiseLegacy(raw(code), raw(message), site); }
export function raiseTyped(key: string, name: string, value: Value, kind: PayloadKind, nominal: string, site: base.Site): never {
  checkedPayload(value, kind, nominal, site); return execution.raiseValue(key, name, value, site);
}
export function readTyped<T extends Value>(detail: execution.SourceDetails, key: string, kind: PayloadKind, nominal: string, site: base.Site): T {
  const value = execution.payload(detail, key, site); checkedPayload(value, kind, nominal, site); return value as T;
}
export function run(body: () => Value | void, limits: HeapLimits): execution.Execution { return execution.run(body, limits, representation); }
