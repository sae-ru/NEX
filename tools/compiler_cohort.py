"""Keep platform helpers bound to one explicitly supported compiler cohort."""
import hashlib
from pathlib import Path
import re

COHORT_HELPER_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def require(value, message):
    if not value:
        raise RuntimeError(message)


def compiler_cohort(doctor, index, *, languages=('0.27', '0.28')):
    require(isinstance(doctor, dict) and doctor.get('schema') == 'nex.doctor/1',
            'compiler doctor schema is unsupported')
    require(isinstance(index, dict) and index.get('schema') == 'nex.discovery/1'
            and index.get('kind') == 'index', 'compiler discovery index is unsupported')
    language = index.get('language')
    require(isinstance(language, str) and language in languages,
            'unsupported source language for this platform helper: ' + str(language))
    require(doctor.get('language') == language and
            isinstance(index.get('toolchain'), str) and bool(index['toolchain']) and
            doctor.get('version') == index['toolchain'],
            'doctor and discovery select different compiler versions')
    for name in ('compiler_build', 'descriptor_hash'):
        require(isinstance(index.get(name), str) and re.fullmatch('[0-9a-f]{64}', index[name]),
                'compiler discovery lacks a valid ' + name)
    return {name: index[name] for name in ('toolchain', 'language', 'compiler_build', 'descriptor_hash')}


def compiler_field(cohort, envelope, field):
    require(isinstance(envelope, dict) and envelope.get('schema') == 'nex.discovery/1'
            and envelope.get('kind') == 'field' and envelope.get('field') == field,
            'unexpected compiler discovery field: ' + field)
    require(all(envelope.get(name) == value for name, value in cohort.items()),
            'compiler identity changed while discovering ' + field)
    require('value' in envelope, 'compiler discovery field lacks its value: ' + field)
    return envelope['value']


def typed_task_abi(cohort, envelope):
    value = compiler_field(cohort, envelope, 'source_exceptions.source_providers')
    require(isinstance(value, dict) and value.get('ordinary_CLI') is True and
            isinstance(value.get('source_languages'), list) and
            cohort['language'] in value['source_languages'] and
            value.get('descriptor_abi') == '0x4e45585400000007' and
            value.get('record_schema') == 'nex.native-task-provider/14' and
            value.get('profile_record_schema') == 'nex.native-task-provider/15' and
            value.get('debug_record_schema') == 'nex.native-task-provider/16',
            'platform helper requires the advertised typed source task ABI7 cohort')
    return 7
