"""Validate the recorded public HTTP dependency cohort and local patches.

An inventory is provenance, not a signature or an OS sandbox. Operators still
select and trust their dependency build. File hashes are rechecked by prepare.
"""
import hashlib
import json
from pathlib import Path
import re

RELEASES = {
    'curl': {'name': 'curl-8.23.0', 'version': '8.23.0', 'bytes': 4465093,
             'sha256': 'e3de77cfa6367083c776a26647fc9f633b538c06c3baa73d931a252ac8f72b49',
             'url': 'https://github.com/curl/curl/releases/download/curl-8_23_0/curl-8.23.0.tar.gz'},
    'nghttp2': {'name': 'nghttp2-1.70.0', 'version': '1.70.0', 'bytes': 3104002,
               'sha256': 'aa317e2cf9dca6afa0aed68f8fad6ff303ec6982e25a78c75c0b65e2b9b3ded5',
               'url': 'https://github.com/nghttp2/nghttp2/releases/download/v1.70.0/nghttp2-1.70.0.tar.gz'}
}
CARES_ARCHIVE = '9364b70a12eb59a06830fb488d9357f90100dff0d98b23ea3593a183d43e6f2f'
CURL_PATCH = 'a097ba0f9dfa3b4fd6b34ddda84c4d9d56e9b99dfb7f6d9719b087aec1898f0b'
CARES_MAC_PATCH = '908c595efdeba68c8abb40ef81c0fe3f36c07ef4c5b3c895dbf82bd99ddd0d24'
LICENSES = {
    'share/licenses/curl/LICENSE.txt': '82f2f4427d6545ee5aaac4f0b80428da6cc8ba41c2cf5da3a03680ec327b9681',
    'share/licenses/nghttp2/LICENSE.txt': '6b94f3abc1aabd0c72a7c7d92a77f79dda7c8a0cb3df839a97890b4116a2de2a',
    'share/licenses/c-ares/LICENSE.txt': '460f5e768fda3752ca2169a95df062578a10fb126bfd65f3b9b1a1bed2f84807'
}


def patch(path, expected):
    data = Path(path).read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError('HTTP dependency patch document identity differs')
    return json.loads(data)


def sha256(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


def validate_cares(record, host):
    if (record.get('schema') != 'nex.cares-install/1' or record.get('version') != '1.34.9'
            or record.get('archive_sha256') != CARES_ARCHIVE or record.get('static_PIC') is not True
            or record.get('static_library') != 'lib/libcares.a'
            or not sha256(record.get('static_library_sha256'))
            or record.get('license') != 'share/licenses/c-ares/LICENSE.txt'
            or record.get('license_sha256') != LICENSES['share/licenses/c-ares/LICENSE.txt']):
        raise ValueError('pinned c-ares source/library/license cohort differs')
    expected = []
    if host == 'Darwin':
        document = patch(Path(__file__).parent.parent / 'dns_provider/patches/c-ares-macos-unaligned-v1.json', CARES_MAC_PATCH)
        expected = [{'patch_sha256': CARES_MAC_PATCH, 'document': document}]
    if record.get('local_source_patches') != expected:
        raise ValueError('c-ares local patch cohort differs for selected host')


def validate_http(record, host):
    if record.get('schema') != 'nex.http-dependencies/1':
        raise ValueError('unsupported HTTP dependency inventory')
    if any(record.get(kind) != release for kind, release in RELEASES.items()):
        raise ValueError('HTTP release archive identity differs')
    validate_cares(record.get('cares', {}), host)
    document = patch(Path(__file__).parent / 'patches/curl-no-ambient-keylog-v1.json', CURL_PATCH)
    if record.get('curl_source_patches') != [{'sha256': CURL_PATCH, 'document': document}]:
        raise ValueError('curl ambient keylog patch cohort differs')
    if (record.get('static_PIC') is not True or record.get('automatic_decompression') is not False
            or record.get('licenses') != LICENSES):
        raise ValueError('HTTP static build/complete license cohort differs')
    libraries = record.get('libraries', {})
    if (set(libraries) != {'libcurl.a', 'libnghttp2.a', 'libcares.a'}
            or not all(sha256(value) for value in libraries.values())
            or libraries['libcares.a'] != record['cares']['static_library_sha256']):
        raise ValueError('HTTP static library cohort differs')
    headers = record.get('headers', {})
    if (not isinstance(headers, dict) or not {'curl/curl.h', 'nghttp2/nghttp2.h', 'ares.h'} <= set(headers)
            or not all(sha256(value) for value in headers.values())):
        raise ValueError('HTTP public header inventory differs')
    manifests = record.get('source_manifest_sha256', {})
    if (set(manifests) != {'curl_upstream', 'curl_effective', 'nghttp2'}
            or not all(sha256(value) for value in manifests.values())):
        raise ValueError('HTTP upstream/effective source manifests differ')
    ssl = record.get('openssl_library_sha256', {})
    if set(ssl) != {'native_openssl_ssl', 'native_openssl_crypto'} or not all(sha256(value) for value in ssl.values()):
        raise ValueError('HTTP selected OpenSSL identity differs')
