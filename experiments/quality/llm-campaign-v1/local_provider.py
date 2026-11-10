"""Bounded LM Studio native API transport, restricted to numeric loopback.

No SDK, proxies, redirect following, downloads, model loading or cloud fallback.
Generation requires an already loaded, explicitly selected Qwen Q8_0 instance.
"""
import hashlib
import http.client
import json
from pathlib import Path
import time
from urllib.parse import urlsplit
import uuid

MAX_RESPONSE = 8 * 1024 * 1024
MAX_REQUEST = 2 * 1024 * 1024
MODEL = 'qwen/qwen3.8-27b'


def count(value):
    if type(value) is not int or not 0 <= value <= 10**12:
        raise ValueError('expected an observed nonnegative token count')
    return value


def usage(response):
    """Normalize observed native counters; never tokenize bytes or guess cache."""
    stats = response.get('stats')
    if not isinstance(stats, dict): return None
    if 'input_tokens' not in stats or 'total_output_tokens' not in stats: return None
    incoming = count(stats['input_tokens']); outgoing = count(stats['total_output_tokens'])
    reasoning = stats.get('reasoning_output_tokens')
    if reasoning is not None and count(reasoning) > outgoing:
        raise ValueError('reasoning subtotal exceeds total output')
    cached = stats.get('cached_input_tokens')
    if cached is not None and count(cached) > incoming:
        raise ValueError('cached input exceeds total input')
    return {'input_tokens': incoming, 'cached_input_tokens': cached, 'output_tokens': outgoing}


def decode(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value: raise ValueError('duplicate API JSON key')
            value[key] = item
        return value
    def invalid(value): raise ValueError('nonfinite API JSON')
    return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=invalid)


def authorized_instance(models, instance, context=16384):
    if not isinstance(instance, str) or not instance.startswith('nex-cost-'):
        raise ValueError('a separately owned nex-cost instance is required')
    matches = []
    if not isinstance(models, dict) or not isinstance(models.get('models'), list):
        raise ValueError('expected local model inventory')
    for model in models['models']:
        if not isinstance(model, dict): raise ValueError('invalid model inventory item')
        if model.get('key') not in (MODEL, MODEL + '@q8_0'): continue
        if model.get('type') != 'llm' or model.get('format') != 'gguf': continue
        quant = model.get('quantization')
        if not isinstance(quant, dict) or quant.get('name') != 'Q8_0': continue
        for loaded in model.get('loaded_instances', []):
            if not isinstance(loaded, dict): raise ValueError('invalid model instance')
            if loaded.get('id') == instance: matches.append((model, loaded))
    if len(matches) != 1: raise ValueError('selected local Qwen Q8_0 instance is not uniquely loaded')
    model, loaded = matches[0]
    config = loaded.get('config', {})
    if not isinstance(config, dict): raise ValueError('invalid loaded instance configuration')
    if (type(config.get('context_length')) is not int or type(config.get('parallel')) is not int
            or config['context_length'] != context or config['parallel'] != 1):
        raise ValueError('local instance context/parallel settings differ from the frozen profile')
    return {'model_key': model['key'], 'quantization': 'Q8_0', 'instance': instance,
            'config': config, 'architecture': model.get('architecture')}


class Client:
    def __init__(self, base_url, *, token=None, timeout=180):
        url = urlsplit(base_url)
        if (url.scheme != 'http' or url.hostname != '127.0.0.1' or url.username is not None
                or url.password is not None or url.path not in ('', '/') or url.query or url.fragment
                or not url.port or not 1 <= url.port <= 65535):
            raise ValueError('only an explicit http://127.0.0.1:PORT endpoint is permitted')
        self.host, self.port, self.timeout, self.token = url.hostname, url.port, timeout, token

    def request(self, method, path, payload=None, *, encoded=None):
        if (method, path) not in [('GET', '/api/v1/models'), ('POST', '/api/v1/chat')]:
            raise ValueError('endpoint is not permitted by the local-only collector')
        if encoded is not None and payload is not None: raise ValueError('request has two different bodies')
        raw = encoded if encoded is not None else None if payload is None else json.dumps(payload, ensure_ascii=False, allow_nan=False).encode('utf-8')
        if raw is not None and len(raw) > MAX_REQUEST: raise ValueError('request exceeds byte budget')
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
        if self.token: headers['Authorization'] = 'Bearer ' + self.token
        connection = http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)
        try:
            connection.request(method, path, body=raw, headers=headers)
            response = connection.getresponse()
            # http.client never consults proxy env vars or follows a redirect.
            body = response.read(MAX_RESPONSE + 1)
            if len(body) > MAX_RESPONSE: raise ValueError('response exceeds byte budget')
            headers = {key: response.getheader(key) for key in ['content-type', 'x-request-id', 'server']
                       if response.getheader(key) is not None}
            return response.status, body, headers
        finally:
            connection.close()

    def models(self):
        status, raw, _ = self.request('GET', '/api/v1/models')
        if status != 200: raise ValueError('local model inventory HTTP status ' + str(status))
        result = decode(raw)
        if not isinstance(result, dict) or not isinstance(result.get('models'), list):
            raise ValueError('invalid local model inventory')
        return result

    def chat(self, instance, system, prompt, output, *, max_tokens=4096, context=16384, sampling=None):
        """Retain even failed request evidence and unknown usage, never retry here."""
        selection = authorized_instance(self.models(), instance, context)
        if type(max_tokens) is not int or not 1 <= max_tokens <= 4096:
            raise ValueError('invalid bounded completion limit')
        if not isinstance(system, str) or not isinstance(prompt, str): raise ValueError('text-only input required')
        output = Path(output); output.mkdir(parents=True, exist_ok=False)
        payload = {'model': instance, 'system_prompt': system, 'input': prompt,
                   'integrations': [], 'stream': False, 'store': False,
                   'temperature': 0, 'top_p': 1, 'max_output_tokens': max_tokens,
                   'reasoning': 'off',
                   'context_length': context}
        if sampling is not None:
            if sampling != {'top_k': 40, 'min_p': 0, 'repeat_penalty': 1}:
                raise ValueError('unsupported frozen collection sampling settings')
            payload.update(sampling)
        request = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8') + b'\n'
        (output / 'request.json').write_bytes(request)
        started = time.monotonic()
        record = {'schema': 'nex.local-provider-call/1', 'id': 'host-' + uuid.uuid4().hex,
                  'provider': 'lmstudio-local', 'instance': instance, 'selection': selection,
                  'request_sha256': hashlib.sha256(request).hexdigest(),
                  'usage': None, 'confirmed_cost': None, 'error': None, 'transport_finished': False}
        def retain():
            temporary = output / 'call.json.tmp'
            temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            temporary.replace(output / 'call.json')
        retain()  # An abrupt process exit must leave the attempted call recorded.
        content = ''
        try:
            status, raw, headers = self.request('POST', '/api/v1/chat', encoded=request)
            (output / 'response.json').write_bytes(raw)
            record['http_status'] = status; record['response_sha256'] = hashlib.sha256(raw).hexdigest()
            record['response_headers'] = headers
            response = decode(raw)
            if not isinstance(response, dict): raise ValueError('expected API response object')
            record['usage'] = usage(response)
            record['returned_instance'] = response.get('model_instance_id')
            request_id = headers.get('x-request-id') or response.get('response_id')
            if request_id is not None:
                if not isinstance(request_id, str) or not 0 < len(request_id) <= 512 or '\0' in request_id:
                    raise ValueError('invalid provider request identifier')
                record['producer_trace_id'] = record['id']; record['id'] = request_id
            if status != 200: raise ValueError('local chat HTTP status ' + str(status))
            if response.get('model_instance_id') != instance: raise ValueError('response used another model instance')
            messages = response.get('output')
            if not isinstance(messages, list) or not messages: raise ValueError('missing local response output')
            chunks = []
            for item in messages:
                if not isinstance(item, dict) or item.get('type') not in ('message', 'reasoning'):
                    raise ValueError('unexpected server-executed integration/tool output')
                if not isinstance(item.get('content'), str): raise ValueError('invalid message text')
                if item['type'] == 'message': chunks.append(item['content'])
            content = '\n'.join(chunks)
            if not content: raise ValueError('response contains no final text')
            after = authorized_instance(self.models(), instance, context)
            if after != selection: raise ValueError('local model configuration changed during the call')
        except (OSError, ValueError, TypeError, http.client.HTTPException) as error:
            record['error'] = str(error)
        except BaseException as error:
            record['error'] = type(error).__name__; record['interrupted'] = True
            raise
        finally:
            record['wall_ms'] = round((time.monotonic() - started) * 1000)
            record['transport_finished'] = True
            retain()
        return content, record
