"""Execute a producer artifact with native Windows Python; relay exact bytes."""
import os
from pathlib import Path
import re
import subprocess
import sys

if os.name != 'nt':
    raise SystemExit('run_pe.py requires native Windows Python')
match = re.fullmatch(r'/mnt/([a-z])/(.+)', sys.argv[1])
if not match:
    raise SystemExit('expected an artifact on a mounted Windows drive')
executable = Path(match[1].upper() + ':/' + match[2]).resolve(strict=True)
if executable.suffix.lower() != '.exe':
    raise SystemExit('expected a Windows PE executable')
result = subprocess.run([str(executable), *sys.argv[2:]], stdout=sys.stdout.buffer,
                        stderr=sys.stderr.buffer, timeout=120)
raise SystemExit(result.returncode)
