// Compiler-private source exceptions. Public024 emission does not import this module.
import * as nex from './nex-runtime.ts';
export type Details = Readonly<{code: string; message: string; site: nex.Site}>;
// Only this class enters a source catch. NexError, host failures and Result
// propagation retain their existing, independently owned boundary semantics.
class SourceException {
  readonly payload: Details;
  constructor(payload: Details) { this.payload = payload; Object.freeze(this); }
}
export function raise(code: string, message: string, site: nex.Site): never {
  const origin = Object.freeze([...site]) as nex.Site;
  const payload: Details = Object.freeze({code: nex.string(code, origin), message: nex.string(message, origin), site: origin});
  throw new SourceException(payload);
}
export function details(error: unknown): Details | undefined {
  return error instanceof SourceException ? error.payload : undefined;
}
