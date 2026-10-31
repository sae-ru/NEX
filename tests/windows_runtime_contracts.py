"""Reuse the 15 contract scenarios with explicit PE builds/native Windows runs.

Run under the WSL producer. Set TMPDIR to a directory on /mnt/DRIVE and provide
NEX_WINDOWS_CONTRACT_TOOLCHAIN, NEX_WINDOWS_CONTRACT_RUNNER (a JSON argv array),
and NEX_WINDOWS_CONTRACT_REPORT. Reference/TypeScript, generation, proofs and
profiling still execute in WSL; every `run` observation executes a Windows PE.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import unittest

import runtime_contracts

TOOLCHAIN = os.environ['NEX_WINDOWS_CONTRACT_TOOLCHAIN']
RUNNER = json.loads(os.environ['NEX_WINDOWS_CONTRACT_RUNNER'])
REPORT = Path(os.environ['NEX_WINDOWS_CONTRACT_REPORT'])
observations = []
PRODUCER_SHA256 = hashlib.sha256(Path(runtime_contracts.harness.NEX).read_bytes()).hexdigest()


class WindowsRuntimeContracts(runtime_contracts.RuntimeContracts):
    def cli(self, *arguments, **kwargs):
        if arguments[0] != 'run':
            return super().cli(*arguments, **kwargs)
        options = dict(kwargs)
        success = options.pop('ok', True)
        built = super().cli('build', *arguments[1:], '--toolchain', TOOLCHAIN, **options)
        command = [*RUNNER, built['executable']]
        process = subprocess.run(command, capture_output=True, text=True,
                                 timeout=options.get('timeout', 240))
        record = {'scenario': self.id(), 'argv': command, 'producer_build': built,
                  'executable_sha256': hashlib.sha256(Path(built['executable']).read_bytes()).hexdigest(),
                  'exit_code': process.returncode, 'stdout': process.stdout,
                  'stderr': process.stderr, 'execution_environment': 'native Windows'}
        observations.append(record)
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps({'schema': 'nex.windows-runtime-contracts/1',
            'producer_environment': 'WSL', 'reference_TypeScript_proof_profile_environment': 'WSL',
            'native_execution_environment': 'Windows', 'Windows_hosted_compiler_accepted': False,
            'producer_sha256': PRODUCER_SHA256,
            'observations': observations}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline="\n")
        if success:
            self.assertEqual(process.returncode, 0, record)
        else:
            self.assertNotEqual(process.returncode, 0, record)
        return record


if __name__ == '__main__':
    unittest.main()
