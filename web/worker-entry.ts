import { execute } from './worker-program.ts';
import { NexError, decodeJSON, encodeJSON, unwrap } from './nex-runtime.ts';
import { inputSchema } from './worker-contract.ts';

const scope = globalThis as unknown as {
  onmessage: ((event: MessageEvent<unknown>) => void) | null;
  postMessage(value: unknown): void;
  close(): void;
};
let accepted = false;
scope.onmessage = async event => {
  if (accepted) return;
  accepted = true;
  const data = event.data as Record<string, unknown> | null;
  if (!data || typeof data !== 'object' || Array.isArray(data) || Object.keys(data).sort().join(',') !== 'body,protocol,ticket' || data.protocol !== 'nex.worker/1' || typeof data.ticket !== 'number' || !Number.isSafeInteger(data.ticket) || data.ticket < 1 || typeof data.body !== 'string') { scope.close(); return; }
  let body = '', code = '', message = '';
  try {
    const input = unwrap(decodeJSON<Parameters<typeof execute>[0]>(data.body, inputSchema));
    body = encodeJSON(await execute(input));
  } catch (error) {
    code = error instanceof NexError ? error.code : 'E_WORKER';
    message = error instanceof NexError ? error.message : 'Worker execution failed';
    if (new TextEncoder().encode(message).length > 1024) message = 'Worker execution failed';
  }
  scope.postMessage({ protocol: 'nex.worker/1', ticket: data.ticket, body, code, message });
  scope.close();
};
