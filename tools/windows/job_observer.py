"""Observe only a newly-created native Windows process and its private job.

Build job_observer.cpp first and calibrate it with job_observer_test.py.
No PID tree is scanned. The helper assigns its root at creation, verifies job
membership before resume, and may terminate only that private job on timeout.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time


def observe(command, root, environment, *, observer, timeout=180):
    if os.name != 'nt':
        raise RuntimeError('job observation requires native Windows')
    if not command or not Path(command[0]).is_absolute():
        raise ValueError('an absolute program path is required')
    if not 0 < timeout <= 3600:
        raise ValueError('observer timeout must be in (0, 3600] seconds')
    helper = Path(observer).resolve(strict=True)
    root = Path(root).resolve(); root.mkdir(parents=True, exist_ok=False)
    prefix = root/'owned'
    argv = [str(helper), str(prefix), str(max(1, int(timeout*1000))), '0', '--', *map(str, command)]
    started = time.monotonic()
    try:
        completed = subprocess.run(argv, cwd=root, env=environment, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout+20,
            creationflags=subprocess.CREATE_NO_WINDOW)
    except subprocess.TimeoutExpired as error:
        # subprocess reaps only its exact helper handle. The helper's private
        # KILL_ON_JOB_CLOSE job supplies descendant cleanup; no PID fallback.
        (root/'observer.stdout').write_bytes(error.stdout or b'')
        (root/'observer.stderr').write_bytes(error.stderr or b'')
        raise
    (root/'observer.stdout').write_bytes(completed.stdout)
    (root/'observer.stderr').write_bytes(completed.stderr)
    receipt = Path(str(prefix)+'.json')
    if not receipt.is_file():
        raise RuntimeError('job observer did not publish its report: '+str(root))
    value = json.loads(receipt.read_text(encoding='utf-8'))
    required = ('probe_completed', 'created_root', 'root_job_verified_before_resume',
                'root_resumed', 'assignment_at_creation', 'stdio_handles_only',
                'final_job_accounting_observed')
    if (value.get('schema') != 'nex.windows-job-observation/1' or
            any(value.get(name) is not True for name in required) or
            value.get('parent_PID_ownership_used') is not False or
            type(value.get('active_job_processes')) is not int or
            value.get('active_job_processes') != 0 or value.get('error')):
        raise RuntimeError('job observer failed; inspect '+str(receipt))
    root_code = value.get('root_exit_code')
    if type(root_code) is not int or not 0 <= root_code <= 0xffffffff:
        raise RuntimeError('job observer lacks the actual root exit code')
    timed_out = value.get('timed_out')
    if (type(timed_out) is not bool or
            value.get('private_job_termination_requested') is not timed_out or
            completed.returncode & 0xffffffff != (124 if timed_out else root_code)):
        raise RuntimeError('job observer status contradicts its actual process result')
    processes = value.get('processes', [])
    if (type(value.get('total_job_processes')) is not int or
            value['total_job_processes'] < len(processes) or not processes or
            any(row.get('kernel_membership_verified') is not True or
            row.get('exited') is not True or type(row.get('exit_code')) is not int
            for row in processes)):
        raise RuntimeError('job observer has an unretired or unverified captured member')
    roots = [row for row in processes if row.get('pid') == value['root_pid']]
    if len(roots) != 1 or roots[0]['exit_code'] != root_code:
        raise RuntimeError('job observer lost its held root process result')
    stdout = Path(str(prefix)+'.stdout').read_bytes()
    stderr = Path(str(prefix)+'.stderr').read_bytes()
    (root/'stdout').write_bytes(stdout); (root/'stderr').write_bytes(stderr)
    children = [dict(row, exit_hex='0x%08X'%row['exit_code'])
                for row in processes if row['pid'] != value['root_pid']]
    return {'schema':'nex.controlled-job-process-observation/1',
        'command':list(map(str,command)), 'parent_pid':value['root_pid'],
        'parent_exit_code':root_code, 'timed_out':timed_out,
        'seconds':time.monotonic()-started, 'children':children,
        'kernel_job_membership_verified':True, 'active_job_processes':0,
        'all_child_exit_codes_claimed':False,
        'total_job_processes':value['total_job_processes'], 'captured_job_processes':len(processes),
        'crash_diagnostic':b'PLEASE submit a bug report' in stderr or b'Exception Code:' in stderr,
        'inferior_reported_zero':b'exited with status = 0' in stdout,
        'job_receipt':str(receipt)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--observer', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=float, default=180)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    value = observe(command, args.output, os.environ.copy(), observer=args.observer, timeout=args.timeout)
    (args.output/'report.json').write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(value))
    raise SystemExit(124 if value['timed_out'] else value['parent_exit_code'])


if __name__ == '__main__':
    main()
