"""Retained task cohorts and the process-level missing-owner-runtime guard."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('probe', type=Path)
args = parser.parse_args()
probe = args.probe.resolve(strict=True)
ordinary = subprocess.run([str(probe)], capture_output=True, text=True, timeout=30)
assert ordinary.returncode == 0 and not ordinary.stderr, (ordinary.returncode, ordinary.stdout, ordinary.stderr)
report = json.loads(ordinary.stdout)
assert report['ok'] and report['descriptor_abi'] == 7 and report['cross_cohort_rejections'] == 20
missing = subprocess.run([str(probe), '--missing-reference-runtime'], capture_output=True, text=True, timeout=10)
assert missing.returncode == 70 and not missing.stdout, (missing.returncode, missing.stdout, missing.stderr)
assert 'E_TASK_STATE' in missing.stderr and 'requires its matching cell runtime' in missing.stderr, missing.stderr
assert 'E_INTERNAL_LEAK' not in missing.stderr
report['missing_reference_runtime'] = {'exit_code': missing.returncode, 'code': 'E_TASK_STATE',
                                      'stderr_sha256': hashlib.sha256(missing.stderr.encode()).hexdigest()}
print(json.dumps(report))
