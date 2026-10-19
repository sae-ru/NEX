// Scalar Wasm ABI 1. The generated descriptor contains only reachable code maps.
const freeze = value => {
  if (value && typeof value === 'object') {
    for (const child of Object.values(value)) freeze(child);
    Object.freeze(value);
  }
  return value;
};
export const descriptor = freeze(__NEX_WASM_DESCRIPTOR__);
const errors = new Map([
  [1, ['E_OVERFLOW', 'i64 arithmetic overflow']],
  [2, ['E_DIV_ZERO', 'division by zero']],
  [3, ['E_ASSERT', 'assertion failed']],
  [4, ['E_WASM_BUDGET', 'Wasm polling budget exhausted']],
  [5, ['E_WASM_DEPTH', 'Wasm call depth exceeds 64']],
  [6, ['E_MATCH', 'no matching arm']],
]);
function failure(code, message, context = {}) {
  const error = new Error(message);
  error.name = 'NexWasmError'; error.code = code;
  Object.assign(error, context);
  return error;
}
function budget(value) {
  if (!Number.isInteger(value) || value < 1 || value > 10000000)
    throw failure('E_WASM_INPUT', 'budget must be an integer from 1 through 10000000');
  return value;
}
function bytes(input) {
  let view;
  if (input instanceof ArrayBuffer) view = new Uint8Array(input);
  else if (ArrayBuffer.isView(input) && input.buffer instanceof ArrayBuffer)
    view = new Uint8Array(input.buffer, input.byteOffset, input.byteLength);
  else throw failure('E_WASM_MODULE', 'expected unshared Wasm bytes');
  if (view.length < 8 || view.length > 8388608)
    throw failure('E_WASM_MODULE', 'Wasm module size is outside the supported bounds');
  return view.slice();
}
export async function createNexWasm(input, options = {}) {
  if (!options || typeof options !== 'object' || Array.isArray(options))
    throw failure('E_WASM_INPUT', 'options must be an object');
  const defaultBudget = budget(options.budget ?? 1000000);
  const data = bytes(input);
  if (!globalThis.crypto?.subtle)
    throw failure('E_WASM_ENV', 'Web Crypto requires a secure browser context or current Node.js');
  const digest = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', data)),
    value => value.toString(16).padStart(2, '0')).join('');
  if (digest !== descriptor.module_sha256)
    throw failure('E_WASM_MODULE', 'Wasm bytes differ from the generated descriptor');
  let compiled;
  try { compiled = await WebAssembly.compile(data); }
  catch { throw failure('E_WASM_MODULE', 'invalid Wasm module'); }
  const exports = WebAssembly.Module.exports(compiled);
  const actual = exports.map(item => item.name).sort();
  if (WebAssembly.Module.imports(compiled).length ||
      JSON.stringify(actual) !== JSON.stringify([...descriptor.exports].sort()) ||
      exports.some(item => item.kind !== (item.name === 'memory' ? 'memory' : 'function')))
    throw failure('E_WASM_MODULE', 'unexpected Wasm imports or exports');
  let instance = null, busy = false;
  const sites = new Map(descriptor.functions.flatMap(fn => fn.operations.map(op => [op.site,
    freeze({ ...op, function: fn.symbol, function_hash: fn.function_hash, source_hash: fn.source_hash })])));
  function call(arguments_, settings = {}) {
    if (!settings || typeof settings !== 'object' || Array.isArray(settings))
      throw failure('E_WASM_INPUT', 'call settings must be an object');
    const ticks = budget(settings.budget ?? defaultBudget);
    if (!Array.isArray(arguments_) || arguments_.length !== descriptor.parameters.length)
      throw failure('E_WASM_INPUT', 'argument count differs from the checked signature');
    const args = Array.from(arguments_, (value, index) => {
      if (descriptor.parameters[index] === 'i64') {
        if (typeof value !== 'bigint' || value < -9223372036854775808n || value > 9223372036854775807n)
          throw failure('E_WASM_INPUT', 'i64 arguments require an in-range BigInt');
        return value;
      }
      if (typeof value !== 'boolean') throw failure('E_WASM_INPUT', 'bool arguments require booleans');
      return value ? 1 : 0;
    });
    if (busy) throw failure('E_WASM_BUSY', 'a Wasm instance cannot be entered recursively');
    busy = true;
    try {
      instance ??= new WebAssembly.Instance(compiled, {});
      instance.exports.nex_wasm_reset(ticks);
      const result = instance.exports[descriptor.native_symbol](...args);
      if (descriptor.result === 'bool') {
        if (result !== 0 && result !== 1) throw failure('E_WASM_RESULT', 'invalid bool result');
        return result === 1;
      }
      return descriptor.result === 'unit' ? undefined : result;
    } catch (cause) {
      let code = 0, line = 0, site = null;
      try {
        code = instance?.exports.nex_wasm_error_code() ?? 0;
        const rawLine = instance?.exports.nex_wasm_error_line() ?? 0n;
        if (rawLine > 0n && rawLine <= 2147483647n) line = Number(rawLine);
        const pointer = instance?.exports.nex_wasm_error_site() >>> 0;
        const memory = instance && new Uint8Array(instance.exports.memory.buffer);
        if (pointer && memory && pointer + 65 <= memory.length && memory[pointer + 64] === 0) {
          const key = String.fromCharCode(...memory.subarray(pointer, pointer + 64));
          if (/^[a-f0-9]{64}$/.test(key)) site = sites.get(key) ?? null;
        }
      } catch { code = 0; line = 0; site = null; }
      // A trap may leave the linear stack pointer changed. Never reuse it.
      instance = null;
      if (errors.has(code)) {
        const [name, message] = errors.get(code);
        throw failure(name, message, { line, site });
      }
      if (cause?.name === 'NexWasmError') throw cause;
      throw failure('E_WASM_TRAP', 'unexpected Wasm trap; source attribution is unavailable');
    } finally { busy = false; }
  }
  return Object.freeze({ descriptor, call });
}
