// Compiler-private source errors; payload data never enters the public details.
import * as nex from './nex-runtime.ts';
import * as task from './nex-task-runtime.ts';
export type Details = Readonly<{code: string; message: string; site: nex.Site}>;
export type PayloadKind = 'i64' | 'bool' | 'f64' | 'str' | 'bytes' | 'list' | 'record' | 'enum' | 'result' | 'function' | 'task_scope' | 'task' | 'channel';
export type TransferContract = Readonly<{key: string; kind: PayloadKind; nominal: string}>;
type TypedPayload = Readonly<{key: string; value: unknown}>;
const sources = new WeakMap<object, Details>();
const payloads = new WeakMap<Details, TypedPayload>();
class SourceException {
  readonly payload: Details;
  constructor(payload: Details) { this.payload = payload; sources.set(this, payload); Object.freeze(this); }
}
function validKey(key: string): boolean { return typeof key === 'string' && /^[0-9a-f]{64}$/.test(key); }
function typeFailure(site: nex.Site): never { throw new nex.NexError('E_SOURCE_TYPE', 'source error payload does not match the checked handler', site); }
function checkedValue(value: unknown, kind: PayloadKind, nominal: string, site: nex.Site): unknown {
  switch (kind) {
    case 'i64': if (typeof value === 'bigint') return nex.checked(value, site); break;
    case 'bool': if (typeof value === 'boolean') return value; break;
    case 'f64': if (typeof value === 'number') return nex.finiteFloat(value, site); break;
    case 'str': if (typeof value === 'string') return nex.string(value, site); break;
    case 'bytes': if (value instanceof nex.ByteBuffer) return value; break;
    case 'list': if (Array.isArray(value) && Object.isFrozen(value)) return value; break;
    case 'function': if (typeof value === 'function' && nex.captureValues(value as nex.Callable) !== undefined) return value; break;
    case 'task_scope': case 'task': case 'channel': if (task.isCapability(value, kind)) return value; break;
    case 'record': case 'enum': case 'result': {
      if (typeof value !== 'object' || value === null || !Object.isFrozen(value)) break;
      // Read data properties, never a source/host getter or string conversion.
      const type = Object.getOwnPropertyDescriptor(value, nex.TYPE);
      const variant = Object.getOwnPropertyDescriptor(value, nex.CASE);
      if (type === undefined || !('value' in type) || typeof type.value !== 'string') break;
      if (kind === 'result') {
        if (variant === undefined && (type.value === 'nex.result.ok' || type.value === 'nex.result.error')) return value;
      } else if (nominal.length > 0 && type.value === nominal) {
        if (kind === 'record' && variant === undefined) return value;
        if (kind === 'enum' && variant !== undefined && 'value' in variant && typeof variant.value === 'string') return value;
      }
      break;
    }
  }
  return typeFailure(site);
}
function metadata(code: string, message: string, site: nex.Site): Details {
  const origin = Object.freeze([...site]) as nex.Site;
  return Object.freeze({code: nex.string(code, origin), message: nex.string(message, origin), site: origin});
}
export function raise(code: string, message: string, site: nex.Site): never {
  throw new SourceException(metadata(code, message, site));
}
export function raiseTyped(key: string, name: string, value: unknown, kind: PayloadKind, nominal: string, site: nex.Site): never {
  const detail = metadata(name, 'typed source error', site);
  if (!validKey(key)) return typeFailure(detail.site);
  const owned = checkedValue(value, kind, nominal, detail.site);
  payloads.set(detail, Object.freeze({key, value: owned}));
  throw new SourceException(detail);
}
export function details(error: unknown): Details | undefined {
  return typeof error === 'object' && error !== null ? sources.get(error) : undefined;
}
export function matches(detail: Details, expected: string): boolean {
  return validKey(expected) && payloads.get(detail)?.key === expected;
}
export function readTyped<T extends nex.Value>(detail: Details, expected: string, kind: PayloadKind, nominal: string, site: nex.Site): T {
  const payload = payloads.get(detail);
  if (!validKey(expected) || payload === undefined || payload.key !== expected) return typeFailure(site);
  return checkedValue(payload.value, kind, nominal, site) as T;
}
// Compiler-known keys select the existing keyed accessor. There is deliberately
// no operation which returns an unknown packet's key/value or calls host code
// with its payload. Copy data properties once; never retain host contract objects.
export function checkedTransferContracts(input: ReadonlyArray<TransferContract>): ReadonlyArray<TransferContract> {
  const site: nex.Site = ['<source-error-contract>', 1, 1];
  if (!Array.isArray(input) || input.length > 4096) return typeFailure(site);
  const result = new Map<string, TransferContract>();
  const kinds: ReadonlyArray<string> = ['i64','bool','f64','str','bytes','list','record','enum','result','function','task_scope','task','channel'];
  for (let i = 0; i < input.length; ++i) {
    const element = Object.getOwnPropertyDescriptor(input, String(i));
    if (!element || !('value' in element) || typeof element.value !== 'object' || element.value === null) return typeFailure(site);
    const fields = ['key','kind','nominal'].map(name => Object.getOwnPropertyDescriptor(element.value, name));
    if (fields.some(field => !field || !('value' in field) || typeof field.value !== 'string')) return typeFailure(site);
    const [key, kind, nominal] = fields.map(field => field!.value as string);
    if (!validKey(key) || !kinds.includes(kind) || nominal.length > 65536 || (kind !== 'record' && kind !== 'enum' && nominal !== '')) return typeFailure(site);
    const previous = result.get(key);
    if (previous && (previous.kind !== kind || previous.nominal !== nominal)) return typeFailure(site);
    result.set(key, Object.freeze({key, kind: kind as PayloadKind, nominal}));
  }
  return Object.freeze([...result.values()]);
}
export function transferContract(detail: Details, known: ReadonlyArray<TransferContract>): TransferContract | undefined {
  const payload = payloads.get(detail);
  if (!payload) return undefined; // Retained legacy source errors have no value.
  const contract = known.find(candidate => candidate.key === payload.key);
  if (!contract) return typeFailure(detail.site);
  return contract;
}
