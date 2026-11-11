// NEX value semantics shared by generated TypeScript and browser applications.
import {ByteBuffer, ByteError} from './nex-bytes.ts';
export {ByteBuffer};
export const TYPE: unique symbol = Symbol('NEX.type');
export const CASE: unique symbol = Symbol('NEX.case');
export type Callable = (...arguments_: never[]) => Value | void;
export type Value = bigint | number | boolean | string | ByteBuffer | ReadonlyArray<Value> | RecordValue | Callable;
export interface RecordValue {
  readonly [TYPE]: string;
  readonly [CASE]?: string;
  readonly [key: string]: Value;
}
type ErrorValue = RecordValue & { readonly [TYPE]: 'nex.error'; readonly code: string; readonly message: string };
type Success<T extends Value> = RecordValue & { readonly [TYPE]: 'nex.result.ok'; readonly ok: T };
type Failure = RecordValue & { readonly [TYPE]: 'nex.result.error'; readonly error: ErrorValue };
export type Result<T extends Value> = Success<T> | Failure;
export function ok<T extends Value>(value: T): Result<T> { return record<Success<T>>('nex.result.ok', [['ok', value]]); }
export function err<T extends Value>(code: string, message: string): Result<T> {
  return record<Failure>('nex.result.error', [['error', record<ErrorValue>('nex.error', [['code', code], ['message', message]])]]);
}
export function isOk<T extends Value>(value: Result<T>): boolean { return value[TYPE] === 'nex.result.ok'; }
export function unwrap<T extends Value>(value: Result<T>, site?: Site): T {
  if (value[TYPE] === 'nex.result.error') fail('E_RESULT', value.error.code + ': ' + value.error.message, site);
  return value.ok;
}
export function errorCode<T extends Value>(value: Result<T>): string { return value[TYPE] === 'nex.result.error' ? value.error.code : ''; }
export function errorMessage<T extends Value>(value: Result<T>): string { return value[TYPE] === 'nex.result.error' ? value.error.message : ''; }
// Private non-value sentinel: only an emitted function boundary handles it.
class ResultPropagation {
  readonly failure: Failure;
  constructor(failure: Failure) { this.failure = failure; }
}
export function propagate<T extends Value>(value: Result<T>): T {
  if (value[TYPE] === 'nex.result.error') throw new ResultPropagation(value);
  return value.ok;
}
export function resultScope<T extends Value>(body: () => Result<T>): Result<T> {
  try { return body(); }
  catch (error) { if (error instanceof ResultPropagation) return error.failure; throw error; }
}
// Generated resumable functions use the same source return boundary.
export function propagatedFailure(error: unknown): Failure | undefined {
  return error instanceof ResultPropagation ? error.failure : undefined;
}
export type Site = readonly [file: string, line: number, column: number, operationSite?: string];
export class NexError extends Error {
  readonly code: string;
  readonly site?: Site;
  constructor(code: string, message: string, site?: Site) {
    super(message); this.name = 'NexError'; this.code = code; this.site = site;
  }
}
function fail(code: string, message: string, site?: Site): never { throw new NexError(code, message, site); }
// The synchronous TypeScript backend evaluates ordered CPU maps serially. It
// provides the same pure value/error contract, not browser worker parallelism.
const callableCaptures = new WeakMap<Callable, ReadonlyArray<Value>>();
const privateTaskValues = new WeakMap<object, 'task_scope' | 'task' | 'channel'>();
// These annotations classify values for ordinary equality/printing/map guards;
// they never grant authority in the private task scheduler's separate owner map.
export function annotateTaskValue(value: RecordValue, kind: 'task_scope' | 'task' | 'channel'): void { privateTaskValues.set(value, kind); }
export function captureValues(callback: Callable): ReadonlyArray<Value> | undefined { return callableCaptures.get(callback); }
export function captured<F extends Callable>(values: ReadonlyArray<Value>, callback: F): F {
  callableCaptures.set(callback, Object.freeze([...values])); return callback;
}
type ParallelControl = { steps: number; depth: number; deadline: number };
let parallelControl: ParallelControl | undefined;
export function parallelPoll(site?: Site): void {
  if (!parallelControl) return;
  if (++parallelControl.steps > 1000000) fail('E_LIMIT', 'parallel execution budget exceeded', site);
  if (performance.now() >= parallelControl.deadline) fail('E_TIMEOUT', 'parallel execution deadline exceeded', site);
}
export function parallelEnter(site?: Site): void {
  if (!parallelControl) return;
  if (parallelControl.depth >= 256) fail('E_LIMIT', 'parallel callback call depth exceeds 256', site);
  parallelPoll(site); ++parallelControl.depth;
}
export function parallelLeave(): void { if (parallelControl) --parallelControl.depth; }
function parallelValue(value: Value, site?: Site): void {
  const pending: Value[] = [value], seen = new Set<object>(); let members = 1;
  while (pending.length) {
    const next = pending.pop()!;
    if (next === null || next === undefined) fail('E_PARALLEL_VALUE', 'parallel value is not a NEX value', site);
    if (typeof next !== 'object' && typeof next !== 'function') continue;
    if (privateTaskValues.has(next)) fail('E_PARALLEL_VALUE', 'parallel value cannot contain task authority', site);
    if (seen.has(next)) continue; seen.add(next);
    if (seen.size > 262144) fail('E_LIMIT', 'parallel value graph exceeds its object limit', site);
    if (seen.size % 64 === 0) parallelPoll(site);
    let children: ReadonlyArray<Value>;
    if (typeof next === 'function') {
      const captures = callableCaptures.get(next);
      if (!captures) fail('E_PARALLEL_VALUE', 'parallel callback has no checked capture metadata', site);
      children = captures;
    } else if (next instanceof ByteBuffer) children = [];
    else children = Array.isArray(next) ? next : Object.values(next);
    if (children.length > 262144 - members) fail('E_LIMIT', 'parallel value graph exceeds its member limit', site);
    members += children.length; for (const child of children) pending.push(child);
  }
}
export function validateParallelValue(value: Value, site?: Site): void { parallelValue(value, site); }
export function parallelMap<T extends Value, U extends Value>(items: ReadonlyArray<T>, callback: (item: T) => U, workers: bigint, site?: Site): ReadonlyArray<U> {
  if (workers < 1n || workers > 16n) fail('E_RANGE', 'parallel worker count must be in 1..16', site);
  if (items.length > 65536) fail('E_LIMIT', 'parallel input exceeds 65536 items', site);
  const previous = parallelControl;
  if (!parallelControl) parallelControl = {steps: 0, depth: 0, deadline: performance.now() + 5000};
  try {
    parallelPoll(site); parallelValue(items, site); parallelValue(callback, site);
    const output: U[] = []; let failure: NexError | undefined;
    for (const item of items) {
      try { parallelPoll(site); const value = callback(item); parallelValue(value, site); output.push(value); }
      catch (error) {
        if (!(error instanceof NexError) || ['E_LIMIT', 'E_TIMEOUT', 'E_CANCELLED', 'E_MEMORY'].includes(error.code)) throw error;
        if (!failure) failure = error;
      }
    }
    parallelPoll(site); if (failure) throw failure; return list(output);
  } finally { parallelControl = previous; }
}
const MIN = -9223372036854775808n, MAX = 9223372036854775807n;
export function checked(value: bigint, site?: Site): bigint {
  if (value < MIN || value > MAX) fail('E_OVERFLOW', 'i64 arithmetic overflow', site);
  return value;
}
export function add(a: bigint, b: bigint, site?: Site): bigint { return checked(a + b, site); }
export function sub(a: bigint, b: bigint, site?: Site): bigint { return checked(a - b, site); }
export function mul(a: bigint, b: bigint, site?: Site): bigint { return checked(a * b, site); }
export function neg(a: bigint, site?: Site): bigint { return checked(-a, site); }
export function div(a: bigint, b: bigint, site?: Site): bigint {
  if (b === 0n) fail('E_DIV_ZERO', 'division by zero', site);
  return checked(a / b, site);
}
export function rem(a: bigint, b: bigint, site?: Site): bigint {
  if (b === 0n) fail('E_DIV_ZERO', 'division by zero', site);
  return a % b;
}
// Finite binary64 helpers for the upcoming source-language milestone. Keep
// per-operation rounding visible; never combine expressions under fast-math.
export function finiteFloat(value: number, site?: Site): number {
  if (!Number.isFinite(value)) fail('E_FLOAT', 'non-finite f64 result', site);
  return value === 0 ? 0 : value;
}
export function floatAdd(a: number, b: number, site?: Site): number { return finiteFloat(finiteFloat(a, site) + finiteFloat(b, site), site); }
export function floatSub(a: number, b: number, site?: Site): number { return finiteFloat(finiteFloat(a, site) - finiteFloat(b, site), site); }
export function floatMul(a: number, b: number, site?: Site): number { return finiteFloat(finiteFloat(a, site) * finiteFloat(b, site), site); }
export function floatDiv(a: number, b: number, site?: Site): number {
  a = finiteFloat(a, site); b = finiteFloat(b, site);
  if (b === 0) fail('E_DIV_ZERO', 'division by zero', site);
  return finiteFloat(a / b, site);
}
export function floatRem(a: number, b: number, site?: Site): number {
  a = finiteFloat(a, site); b = finiteFloat(b, site);
  if (b === 0) fail('E_DIV_ZERO', 'division by zero', site);
  return finiteFloat(a % b, site);
}
export function floatNeg(value: number, site?: Site): number { return finiteFloat(-finiteFloat(value, site), site); }
export function asFloat(value: bigint): number { return finiteFloat(Number(checked(value))); }
export function asInteger(value: number): Result<bigint> {
  value = finiteFloat(value);
  if (value < -9223372036854775808 || value >= 9223372036854775808) return err('E_RANGE', 'f64 value is outside i64 range');
  return ok(BigInt(Math.trunc(value)));
}
export function formatFloat(value: number): string { return finiteFloat(value).toExponential().replace('e+', 'e'); }
export function assert(value: boolean, site?: Site): void { if (!value) fail('E_ASSERT', 'assertion failed', site); }
export function string(value: string, site?: Site): string {
  for (let i = 0; i < value.length; ++i) {
    const c = value.charCodeAt(i);
    if (c >= 0xd800 && c <= 0xdbff) {
      const low = value.charCodeAt(++i);
      if (!(low >= 0xdc00 && low <= 0xdfff)) fail('E_UTF8', 'unpaired UTF-16 surrogate at browser boundary', site);
    } else if (c >= 0xdc00 && c <= 0xdfff) fail('E_UTF8', 'unpaired UTF-16 surrogate at browser boundary', site);
  }
  return value;
}
function byteOperation<T>(operation: () => T, site?: Site): T {
  try { return operation(); }
  catch (error) { if (error instanceof ByteError) fail(error.code, error.message, site); throw error; }
}
export function bytesFromIntegers(values: ReadonlyArray<bigint>): Result<ByteBuffer> {
  try { return ok(ByteBuffer.fromIntegers(values)); }
  catch (error) { if (error instanceof ByteError && error.code === 'E_RANGE') return err(error.code, error.message); throw error; }
}
export function utf8Bytes(text: string, site?: Site): ByteBuffer { return ByteBuffer.copy(new TextEncoder().encode(string(text, site))); }
export function decodeUTF8(value: ByteBuffer): Result<string> {
  const data = value.toUint8Array();
  try { return ok(new TextDecoder('utf-8', {fatal: true, ignoreBOM: true}).decode(data)); }
  catch (error) { if (!(error instanceof TypeError)) throw error; }
  // Keep the host decoder's fast path for valid input; classify a rejection
  // because it collapses malformed sequences and invalid Unicode scalars.
  for (let i = 0; i < data.length;) {
    const first = data[i];
    const count = first < 0x80 ? 1 : first >= 0xc2 && first <= 0xdf ? 2 : first >= 0xe0 && first <= 0xef ? 3 : first >= 0xf0 && first <= 0xf4 ? 4 : 0;
    if (!count || count > data.length - i) return err('E_UTF8', 'invalid UTF-8 string');
    let code = first & (count === 1 ? 0x7f : count === 2 ? 0x1f : count === 3 ? 0x0f : 0x07);
    for (let j = 1; j < count; ++j) {
      const next = data[i + j];
      if ((next & 0xc0) !== 0x80) return err('E_UTF8', 'invalid UTF-8 string');
      code = (code << 6) | (next & 0x3f);
    }
    if ((count === 2 && code < 0x80) || (count === 3 && code < 0x800) || (count === 4 && code < 0x10000) || code > 0x10ffff || (code >= 0xd800 && code <= 0xdfff)) return err('E_UTF8', 'invalid Unicode scalar');
    i += count;
  }
  return err('E_UTF8', 'invalid UTF-8 string');
}
export function encodeBase64(value: ByteBuffer): string { return value.base64(); }
export function decodeBase64(text: string): Result<ByteBuffer> {
  try { return ok(ByteBuffer.fromBase64(text)); }
  catch (error) { if (error instanceof ByteError && error.code === 'E_BASE64') return err(error.code, error.message); throw error; }
}
export function bytesIndex(value: ByteBuffer, at: bigint, site?: Site): bigint { return byteOperation(() => value.at(at), site); }
export function bytesPush(value: ByteBuffer, item: bigint, site?: Site): ByteBuffer { return byteOperation(() => value.append(item), site); }
export function bytesSet(value: ByteBuffer, at: bigint, item: bigint, site?: Site): ByteBuffer { return byteOperation(() => value.set(at, item), site); }
export function bytesSlice(value: ByteBuffer, start: bigint, count: bigint, site?: Site): ByteBuffer { return byteOperation(() => value.slice(start, count), site); }
export function bytesConcat(left: ByteBuffer, right: ByteBuffer, site?: Site): ByteBuffer { return byteOperation(() => left.concat(right), site); }
export function list<T extends Value>(items: ReadonlyArray<T>): ReadonlyArray<T> { return Object.freeze([...items]); }
// Compiler-only construction primitives. Source callbacks never receive the
// unpublished buffer. Publication freezes that same array without a full copy.
export function listBuilderStart<T extends Value>(): ReadonlyArray<T> { return []; }
export function listBuilderAppend<T extends Value>(items: ReadonlyArray<T>, value: T): void {
  if (Object.isFrozen(items)) fail('E_RUNTIME', 'cannot append to a published list');
  (items as T[]).push(value);
}
export function listBuilderFinish<T extends Value>(items: ReadonlyArray<T>): ReadonlyArray<T> { return Object.freeze(items); }
// One linear pass; the published string is ordinary immutable NEX text.
export function textBuilderJoin(items: ReadonlyArray<string>): string { return items.join(''); }
export function record<T extends RecordValue>(name: string, fields: ReadonlyArray<readonly [string, Value]>): T {
  const result = Object.create(null) as Record<string | symbol, Value>;
  Object.defineProperty(result, TYPE, { value: name });
  for (const [key, value] of fields) Object.defineProperty(result, key, { value, enumerable: true });
  // The NEX checker established the nominal type and field layout before emission.
  return Object.freeze(result) as unknown as T;
}
export function enumeration<T extends RecordValue>(name: string, tag: string, fields: ReadonlyArray<readonly [string, Value]>): T {
  const result = Object.create(null) as Record<string | symbol, Value>;
  Object.defineProperty(result, TYPE, { value: name }); Object.defineProperty(result, CASE, { value: tag });
  for (const [key, value] of fields) Object.defineProperty(result, key, { value, enumerable: true });
  return Object.freeze(result) as unknown as T;
}
export function invalidEnum(site?: Site): never { return fail('E_ENUM', 'invalid enum discriminant', site); }
export function concat<T extends Value>(a: ReadonlyArray<T>, b: ReadonlyArray<T>): ReadonlyArray<T> { return list([...a, ...b]); }
export function push<T extends Value>(items: ReadonlyArray<T>, value: T): ReadonlyArray<T> { return list([...items, value]); }
function bounds(index: bigint, size: number, site?: Site): number {
  if (index < 0n || index >= BigInt(size)) fail('E_BOUNDS', 'index is outside collection bounds', site);
  return Number(index);
}
export function index<T extends Value>(items: ReadonlyArray<T>, at: bigint, site?: Site): T { return items[bounds(at, items.length, site)]; }
export function set<T extends Value>(items: ReadonlyArray<T>, at: bigint, value: T, site?: Site): ReadonlyArray<T> {
  const i = bounds(at, items.length, site), copy = [...items]; copy[i] = value; return list(copy);
}
export function character(text: string, at: bigint, site?: Site): string { const chars = Array.from(text); return chars[bounds(at, chars.length, site)]; }
export function length(value: string | ByteBuffer | ReadonlyArray<Value>): bigint { return BigInt(typeof value === 'string' ? Array.from(value).length : value.length); }
export function slice(text: string, start: bigint, count: bigint, site?: Site): string {
  const chars = Array.from(text), size = BigInt(chars.length);
  if (start < 0n || count < 0n || start > size || count > size - start) fail('E_BOUNDS', 'slice is outside string bounds', site);
  return chars.slice(Number(start), Number(start + count)).join('');
}
export function contains(text: string, part: string): boolean { return text.includes(part); }
function isList(value: Value): value is ReadonlyArray<Value> { return Array.isArray(value); }
export function equal(a: Value, b: Value): boolean {
  if (a === b) return true;
  if (typeof a !== 'object' || typeof b !== 'object') return false;
  if (privateTaskValues.has(a) || privateTaskValues.has(b)) return false;
  if (a instanceof ByteBuffer || b instanceof ByteBuffer) return a instanceof ByteBuffer && b instanceof ByteBuffer && a.equals(b);
  if (isList(a)) return isList(b) && a.length === b.length && a.every((item, i) => equal(item, b[i]));
  if (isList(b) || a[TYPE] !== b[TYPE] || a[CASE] !== b[CASE]) return false;
  const names = Object.keys(a), other = Object.keys(b);
  return names.length === other.length && names.every((name, i) => name === other[i] && equal(a[name], b[name]));
}
function quoted(value: string): string {
  return '"' + value.replace(/["\\\u0000-\u001f]/g, c => c === '"' || c === '\\' ? '\\' + c : '\\u' + c.charCodeAt(0).toString(16).padStart(4, '0')) + '"';
}
export function representation(value: Value): string {
  if (typeof value === 'number') return formatFloat(value);
  if (typeof value === 'function') return quoted('<function>');
  if (typeof value === 'string') return quoted(value);
  if (typeof value !== 'object') return String(value);
  const taskKind = privateTaskValues.get(value);
  if (taskKind !== undefined) return quoted('<' + taskKind + '>');
  if (value instanceof ByteBuffer) return quoted(value.base64());
  if (isList(value)) return '[' + value.map(representation).join(',') + ']';
  const fields = '{' + Object.keys(value).map(key => quoted(key) + ':' + representation(value[key])).join(',') + '}';
  return value[CASE] === undefined ? fields : '{"case":' + quoted(value[CASE]) + ',"fields":' + fields + '}';
}
export function str(value: Value): string { return typeof value === 'string' ? value : typeof value === 'function' ? '<function>' : representation(value); }
export function print(value: Value): void { console.log(str(value)); }

type Descriptor = 'i64' | 'f64' | 'bool' | 'str' | 'bytes' | { list: Descriptor } | { result: Descriptor } | { record: string } | { enum: string };
export type Schema = { schema: 'nex.wire/1' | 'nex.wire/2'; root: Descriptor; records: Record<string, ReadonlyArray<{ name: string; type: Descriptor }>>; enums?: Record<string, ReadonlyArray<{ name: string; fields: ReadonlyArray<{name: string; type: Descriptor}> }>> };
const JSON_BYTES = 1024 * 1024, JSON_DEPTH = 64, JSON_ITEMS = 10000, JSON_NODES = 100000;
function invalidJSON(message: string): never { throw new NexError('E_JSON', message); }
function utf8Size(text: string): number { return new TextEncoder().encode(text).length; }
export function encodeJSON(value: Value, site?: Site): string {
  let nodes = 0;
  function encode(value: Value, depth: number): string {
    if (typeof value === 'function') invalidJSON('function values cannot cross the JSON boundary');
    if (depth > JSON_DEPTH || ++nodes > JSON_NODES) invalidJSON('JSON value exceeds depth/node limit');
    if (typeof value === 'bigint') return quoted(String(value));
    if (typeof value === 'boolean') return String(value);
    if (typeof value === 'number') return formatFloat(value);
    if (typeof value === 'string') return quoted(value);
    if (value instanceof ByteBuffer) {
      if (value.length > BigInt(Math.floor((JSON_BYTES - 2) / 4) * 3)) invalidJSON('JSON value exceeds byte limit');
      return quoted(value.base64());
    }
    if (!isList(value)) {
      if (value[TYPE] === 'nex.result.ok') return '{"ok":' + encode(value.ok, depth + 1) + '}';
      if (value[TYPE] === 'nex.result.error') {
        const error = value.error as ErrorValue;
        return '{"error":{"code":' + quoted(error.code) + ',"message":' + quoted(error.message) + '}}';
      }
    }
    if (!isList(value) && value[CASE] !== undefined) {
      if (depth + 1 > JSON_DEPTH) invalidJSON('JSON enum wrapper exceeds depth limit');
      const names = Object.keys(value); if (names.length > JSON_ITEMS) invalidJSON('JSON enum exceeds item limit');
      const fields = '{' + names.map(name => quoted(name) + ':' + encode(value[name], depth + 2)).join(',') + '}';
      return '{"case":' + quoted(value[CASE]) + ',"fields":' + fields + '}';
    }
    const names = Object.keys(value);
    if (names.length > JSON_ITEMS) invalidJSON('JSON collection exceeds item limit');
    const result = isList(value) ? '[' + value.map(item => encode(item, depth + 1)).join(',') + ']'
      : '{' + names.map(name => quoted(name) + ':' + encode(value[name], depth + 1)).join(',') + '}';
    if (utf8Size(result) > JSON_BYTES) invalidJSON('JSON value exceeds byte limit');
    return result;
  }
  try {
    const text = encode(value, 0); if (utf8Size(text) > JSON_BYTES) invalidJSON('JSON value exceeds byte limit'); return text;
  } catch (error) { if (error instanceof NexError && !error.site && site) throw new NexError(error.code, error.message, site); throw error; }
}
export function parseJSON(text: string): unknown {
  string(text); if (utf8Size(text) > JSON_BYTES) invalidJSON('JSON input exceeds byte limit');
  // Match the native wire parser's optional leading UTF-8 byte-order mark.
  // Count it against the byte limit, and preserve BOMs inside string values.
  if (text.startsWith('\ufeff')) text = text.slice(1);
  try {
  // JSON.parse validates syntax; this bounded lexical pass also rejects duplicate keys.
  const stack: Array<{ object: boolean; key: boolean; names: Set<string> }> = [];
  let events = 0;
  for (let i = 0; i < text.length; ++i) {
    const c = text[i];
    if (c === '{' || c === '[') {
      stack.push({ object: c === '{', key: c === '{', names: new Set() });
      if (stack.length - 1 > JSON_DEPTH || ++events > JSON_NODES * 3) invalidJSON('JSON input exceeds depth/node limit');
    } else if (c === '}' || c === ']') stack.pop();
    else if (c === ',' && stack.length && stack[stack.length - 1].object) stack[stack.length - 1].key = true;
    else if (c === '"') {
      const start = i++;
      while (i < text.length && text[i] !== '"') { if (text[i] === '\\') ++i; ++i; }
      if (i >= text.length) invalidJSON('unterminated JSON string');
      if (++events > JSON_NODES * 3) invalidJSON('JSON input exceeds depth/node limit');
      const decoded = string(JSON.parse(text.slice(start, i + 1)) as string);
      const frame = stack[stack.length - 1];
      if (frame?.object && frame.key) {
        const key = decoded;
        if (frame.names.has(key)) invalidJSON('duplicate JSON object key'); frame.names.add(key); frame.key = false;
      }
    }
  }
  return JSON.parse(text);
  } catch { return invalidJSON('invalid JSON text or wire schema'); }
}
function object(value: unknown): value is Record<string, unknown> { return value !== null && typeof value === 'object' && !Array.isArray(value); }
const has = (value: object, key: string) => Object.prototype.hasOwnProperty.call(value, key);
export function decodeJSON<T extends Value>(text: string, schema: Schema): Result<T> {
  let nodes = 0;
  function decode(value: unknown, type: Descriptor, depth: number): Value {
    if (depth > JSON_DEPTH || ++nodes > JSON_NODES) invalidJSON('JSON value exceeds depth/node limit');
    if (type === 'i64') {
      if (typeof value !== 'string' || !/^(0|-?[1-9][0-9]*)(?![\s\S])/.test(value)) invalidJSON('i64 requires a canonical decimal JSON string');
      if (value.length > 20) invalidJSON('JSON integer is outside i64 range');
      const number = BigInt(value); if (number < MIN || number > MAX) invalidJSON('JSON integer is outside i64 range'); return number;
    }
    if (type === 'bool') { if (typeof value !== 'boolean') invalidJSON('expected JSON boolean'); return value; }
    if (type === 'f64') { if (typeof value !== 'number' || !Number.isFinite(value)) invalidJSON('f64 requires a finite JSON number'); return finiteFloat(value); }
    if (type === 'str') { if (typeof value !== 'string') invalidJSON('expected JSON string'); return string(value); }
    if (type === 'bytes') {
      if (typeof value !== 'string') invalidJSON('bytes require a canonical base64 JSON string');
      try { return ByteBuffer.fromBase64(value); }
      catch (error) { if (error instanceof ByteError) invalidJSON('bytes require a canonical base64 JSON string'); throw error; }
    }
    if (typeof type === 'string') return invalidJSON('unsupported wire type');
    if ('list' in type) {
      if (!Array.isArray(value) || value.length > JSON_ITEMS) invalidJSON('expected JSON array within item limit');
      return list(value.map(item => decode(item, type.list, depth + 1)));
    }
    if ('result' in type) {
      if (!object(value) || Object.keys(value).length !== 1) invalidJSON('expected tagged JSON result');
      if (has(value, 'ok')) return ok(decode(value.ok, type.result, depth + 1));
      if (!has(value, 'error')) invalidJSON('expected ok or error result');
      const error = value.error;
      if (!object(error) || Object.keys(error).length !== 2 || !has(error, 'code') || !has(error, 'message') || typeof error.code !== 'string' || typeof error.message !== 'string') invalidJSON('invalid JSON error');
      return err(string(error.code), string(error.message));
    }
    if ('enum' in type) {
      if (schema.schema !== 'nex.wire/2' || !object(value) || Object.keys(value).length !== 2 || !has(value, 'case') || !has(value, 'fields') || typeof value.case !== 'string' || !object(value.fields)) invalidJSON('expected tagged JSON enum');
      const variant = schema.enums?.[type.enum]?.find(variant => variant.name === value.case);
      if (!variant) invalidJSON('unknown JSON enum variant'); const payload = value.fields;
      if (Object.keys(payload).length !== variant.fields.length || Object.keys(payload).length > JSON_ITEMS) invalidJSON('JSON enum has missing or unknown fields');
      return enumeration(type.enum, value.case, variant.fields.map(field => { if (!has(payload, field.name)) invalidJSON('JSON enum has missing or unknown fields'); return [field.name, decode(payload[field.name], field.type, depth + 2)] as const; }));
    }
    const fields = schema.records[type.record];
    if (!object(value) || Object.keys(value).length !== fields.length) invalidJSON('JSON record has missing or unknown fields');
    return record(type.record, fields.map(field => {
      if (!has(value, field.name)) invalidJSON('JSON record has missing or unknown fields');
      return [field.name, decode(value[field.name], field.type, depth + 1)] as const;
    }));
  }
  try {
    if (schema.schema !== 'nex.wire/1' && schema.schema !== 'nex.wire/2') invalidJSON('unsupported wire schema');
    return ok(decode(parseJSON(text), schema.root, 0) as T);
  } catch (error) {
    return err('E_JSON', error instanceof NexError && error.code === 'E_JSON' ? error.message : 'invalid JSON text or wire schema');
  }
}
