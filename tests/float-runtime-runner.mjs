import * as nex from '../web/nex-runtime.ts';
import {readFileSync} from 'node:fs';
const schema = {schema: 'nex.wire/2', root: 'f64', records: {}, enums: {}};
function value(hex) { const buffer = Buffer.from(hex, 'hex'); return buffer.readDoubleBE(); }
function bits(number) { const buffer = Buffer.alloc(8); buffer.writeDoubleBE(number); return buffer.toString('hex'); }
function observed(number) {
  number = nex.finiteFloat(number);
  const wire = nex.encodeJSON(number), decoded = nex.decodeJSON(wire, schema);
  if (!nex.isOk(decoded)) throw new Error('f64 JSON roundtrip failed');
  return {ok: true, bits: bits(number), display: nex.representation(number), wire, json_bits: bits(nex.unwrap(decoded))};
}
function command(request) {
  try {
    const [operation, a, b] = request;
    if (operation === 'decode') { const result = nex.decodeJSON(a, schema); return nex.isOk(result) ? observed(nex.unwrap(result)) : {ok: false, code: nex.errorCode(result)}; }
    if (operation === 'from_integer') return observed(nex.asFloat(BigInt(a)));
    const left = value(a);
    if (operation === 'to_integer') { const result = nex.asInteger(left); return nex.isOk(result) ? {ok: true, integer: String(nex.unwrap(result))} : {ok: false, code: nex.errorCode(result)}; }
    if (operation === 'value') return observed(left);
    const operations = {add: nex.floatAdd, sub: nex.floatSub, mul: nex.floatMul, div: nex.floatDiv, rem: nex.floatRem};
    return observed(operations[operation](left, value(b)));
  } catch (error) {
    if (!(error instanceof nex.NexError)) throw error;
    return {ok: false, code: error.code};
  }
}
for (const line of readFileSync(0, 'utf8').trim().split('\n')) if (line) console.log(JSON.stringify(command(JSON.parse(line))));
