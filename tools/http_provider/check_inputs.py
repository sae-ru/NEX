#!/usr/bin/env python3
"""Reject malformed operator policies and incompatible HTTP dependency records.

This check performs no module initialization or network IO. A dependency
inventory is operator-selected provenance, not a signature of a trusted build.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import platform
import tempfile
import shutil
import time

import prepare
from dependency_contract import validate_http


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--http-prefix', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    temporary = args.output is None
    out = args.output.absolute() if args.output else Path(tempfile.mkdtemp(prefix='nex-http-policy-'))
    if not temporary:
        out.mkdir(parents=True)
    report = {'schema': 'nex.http-input-conformance/1', 'ok': False, 'rejections': [],
              'network_executed': False, 'module_initialized': False}
    report['tool_inputs'] = {}
    for name in ('check_inputs.py', 'prepare.py', 'dependency_contract.py'):
        path = Path(__file__).parent / name
        shutil.copy2(path, out / ('input-' + name))
        report['tool_inputs'][name] = hashlib.sha256(path.read_bytes()).hexdigest()
    start = time.monotonic()

    def rejected(name, action, *, path=None, value=None):
        if path is not None:
            if path.is_symlink():
                write(out / (name + '-input.json'), {'symlink': os.readlink(path)})
            elif path.is_file():
                shutil.copy2(path, out / (name + '-input'))
            else:
                write(out / (name + '-input.json'), {'file_mode': path.lstat().st_mode})
        if value is not None:
            write(out / (name + '-input.json'), value)
        try:
            action()
        except (ValueError, OSError) as error:
            report['rejections'].append({'case': name, 'error': type(error).__name__})
        else:
            raise AssertionError('invalid HTTP input accepted: ' + name)

    try:
        target = out / 'policy.json'
        good = {'schema': 'nex.http-targets/1', 'resolvers': [{'address': '127.0.0.1', 'port': 5353}],
                'authorities': [{'name': 'backend', 'domain': 'example.test', 'subdomains': True,
                                 'schemes': ['http'], 'ports': [80], 'methods': ['GET', 'POST']}]}
        changes = [
            ('empty-resolvers', {'resolvers': []}),
            ('resolver-name', {'resolvers': [{'address': 'localhost', 'port': 53}]}),
            ('resolver-scope', {'resolvers': [{'address': 'fe80::1%en0', 'port': 53}]}),
            ('resolver-unspecified', {'resolvers': [{'address': '::', 'port': 53}]}),
            ('resolver-multicast', {'resolvers': [{'address': '224.0.0.1', 'port': 53}]}),
            ('resolver-broadcast', {'resolvers': [{'address': '255.255.255.255', 'port': 53}]}),
            ('resolver-port-bool', {'resolvers': [{'address': '127.0.0.1', 'port': True}]}),
            ('resolver-port-zero', {'resolvers': [{'address': '127.0.0.1', 'port': 0}]}),
            ('resolver-port-large', {'resolvers': [{'address': '127.0.0.1', 'port': 65536}]}),
            ('duplicate-resolver', {'resolvers': good['resolvers'] * 2}),
            ('too-many-resolvers', {'resolvers': [{'address': '127.0.0.1', 'port': 5353 + i} for i in range(5)]}),
            ('empty-authorities', {'authorities': []}),
            ('duplicate-authority', {'authorities': good['authorities'] * 2}),
            ('too-many-authorities', {'authorities': [dict(good['authorities'][0], name='a' + str(i)) for i in range(17)]}),
            ('capacity-bool', {'maximum_calls': True}), ('capacity-zero', {'maximum_calls': 0}),
            ('capacity-large', {'maximum_calls': 65}), ('unknown-field', {'credential': 'not-a-grant'})]
        for name, key, value in [
            ('authority-unicode', 'name', 'Я'), ('authority-path', 'name', '../bad'),
            ('domain-unicode', 'domain', 'пример.рф'), ('domain-empty', 'domain', ''),
            ('domain-long-label', 'domain', 'a' * 64 + '.test'), ('domain-double-dot', 'domain', 'a..test'),
            ('domain-broadcast', 'domain', '255.255.255.255'), ('domain-multicast', 'domain', 'ff02::1'),
            ('domain-unspecified', 'domain', '0.0.0.0'), ('subdomains-integer', 'subdomains', 1),
            ('cross-origin-integer', 'cross_origin_redirects', 1), ('scheme-file', 'schemes', ['file']),
            ('scheme-duplicate', 'schemes', ['http', 'http']), ('empty-methods', 'methods', []),
            ('method-CONNECT', 'methods', ['CONNECT']), ('method-mixed-connect', 'methods', ['Connect']),
            ('method-injection', 'methods', ['GET\r\n']), ('duplicate-method', 'methods', ['GET', 'GET']),
            ('port-bool', 'ports', [True]), ('port-zero', 'ports', [0]),
            ('duplicate-port', 'ports', [80, 80]), ('HTTPS-without-CA', 'schemes', ['https'])]:
            row = copy.deepcopy(good['authorities'][0])
            row[key] = value
            if name in ('domain-broadcast', 'domain-multicast', 'domain-unspecified'):
                row['subdomains'] = False
            changes.append((name, {'authorities': [row]}))
        for name, change in changes:
            write(target, {**good, **change})
            rejected(name, lambda: prepare.policy(target), path=target)
        for name, data in [('duplicate-JSON', b'{"schema":"nex.http-targets/1","schema":"nex.http-targets/1"}'),
                           ('invalid-UTF8', b'\xff'), ('oversized-JSON', b' ' * 1048577)]:
            target.write_bytes(data)
            rejected(name, lambda: prepare.policy(target), path=target)
        write(target, good)
        link = out / 'policy-link'
        link.symlink_to(target)
        rejected('symlink-policy', lambda: prepare.policy(link), path=link)
        fifo = out / 'policy-pipe'
        os.mkfifo(fifo)
        rejected('FIFO-policy', lambda: prepare.policy(fifo), path=fifo)
        ca = out / 'public-CA.pem'
        for name, data in [('CA-private-key', b'-----BEGIN CERTIFICATE-----\n-----BEGIN PRIVATE KEY-----'),
                           ('CA-invalid-UTF8', b'\xff'), ('CA-oversized', b' ' * 1048577)]:
            ca.write_bytes(data)
            write(target, {**good, 'ca_file': str(ca)})
            rejected(name, lambda: prepare.policy(target), path=target)
        row = copy.deepcopy(good['authorities'][0])
        row.update(domain='EXAMPLE.TEST.', subdomains=False)
        write(target, {**good, 'authorities': [row]})
        actual, ca = prepare.policy(target)
        assert actual['authorities'][0]['domain'] == 'example.test' and actual['maximum_calls'] == 16 and ca == b''
        if args.http_prefix:
            record = json.loads((args.http_prefix / 'share/http-source.json').read_text())
            validate_http(record, platform.system())
            for name, mutate in [
                ('archive-pin', lambda value: value['curl'].__setitem__('sha256', '0' * 64)),
                ('missing-curl-patch', lambda value: value.__setitem__('curl_source_patches', [])),
                ('modified-curl-patch', lambda value: value['curl_source_patches'][0]['document'].__setitem__('patched_sha256', '0' * 64)),
                ('cares-archive-pin', lambda value: value['cares'].__setitem__('archive_sha256', '0' * 64)),
                ('cares-library-cohort', lambda value: value['libraries'].__setitem__('libcares.a', '0' * 64)),
                ('missing-license', lambda value: value['licenses'].pop('share/licenses/curl/LICENSE.txt')),
                ('missing-headers', lambda value: value.__setitem__('headers', {})),
                ('wrong-PIC', lambda value: value.__setitem__('static_PIC', False)),
                ('unexpected-decompression', lambda value: value.__setitem__('automatic_decompression', True))]:
                modified = copy.deepcopy(record)
                mutate(modified)
                rejected(name, lambda: validate_http(modified, platform.system()), value=modified)
            report['actual_selected_dependency_cohort_accepted'] = True
        report.update(ok=True, target_rejections=len(report['rejections']))
    except BaseException as error:
        report['error'] = repr(error)
        raise
    finally:
        report['seconds'] = round(time.monotonic() - start, 3)
        (out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key: report.get(key) for key in ('ok', 'target_rejections', 'seconds')}))
    if temporary and report['ok']:
        shutil.rmtree(out)


if __name__ == '__main__':
    main()
