from pathlib import Path
import hashlib,json
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def trace_receipt(path, expected_kernels, expected_overflow):
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    created = [x for x in rows if x['event'] == 'session_created']
    destroyed = [x for x in rows if x['event'] == 'session_destroyed']
    assert len(created) == len(destroyed) == 1 and all((x['device_type'] & 4 and (not x['device_type'] & 2) and (x['persistent'] is True) for x in created))
    assert not any((x['event'] in ['unsettled', 'failed_session_drained'] for x in rows))
    buffers = {(x['session'], x['buffer']) for x in rows if x['event'] == 'buffer_created'}
    released = {(x['session'], x['buffer']) for x in rows if x['event'] == 'buffer_released'}
    assert buffers == released
    physical = []
    for x in rows:
        if x['event'] == 'worker_diagnostics':
            for line in bytes.fromhex(x['hex']).decode('utf-8', errors='replace').splitlines():
                if line.startswith('NEXGPU_KERNEL '):
                    parts = line.split()
                    assert len(parts) == 5
                    physical.append(tuple(map(int, parts[1:])))
    assert len(physical) == expected_kernels and sum((x[3] for x in physical)) == expected_overflow, (path, physical)
    queued = [x for x in rows if x['event'] == 'kernel_queued']
    completed = [x for x in rows if x['event'] == 'kernel_completed']
    assert len(queued) == expected_kernels and len(completed) == expected_kernels - expected_overflow
    assert len(buffers) == 2 * expected_kernels + expected_kernels - expected_overflow
    exited = [x for x in rows if x['event'] == 'worker_exited']
    assert len(exited) == 1 and exited[0]['exit_code'] == 0 and (exited[0]['signal'] == 0)
    for x in queued:
        assert x['physical_enqueue_verified'] is True
    for x in rows:
        if x['event'] in ['buffer_released', 'session_destroyed', 'kernel_completed']:
            assert x['physical_completion_verified'] is True
    end = next((i for i, x in enumerate(rows) if x['event'] == 'session_destroyed'))
    assert all((i < end for i, x in enumerate(rows) if x['event'] == 'buffer_released'))
    return {'device': created[0]['device'], 'actual_kernel_events': physical, 'buffers': len(buffers), 'all_buffers_released': True, 'session_after_children': True, 'trace_sha256': sha(path)}

def pending_trace(path,cancel):
 result=trace_receipt(path,1,0);rows=[json.loads(x) for x in path.read_text().splitlines()];queued=next(x for x in rows if x['event']=='kernel_queued');complete=next(x for x in rows if x['event']=='kernel_completed')
 assert queued['controlled_user_event'] is True and queued['completion_pending'] is True and queued['execution_status'] in (1,2,3)
 elapsed=(complete['steady_ns']-queued['steady_ns'])/1e9;assert elapsed>=0.5
 if cancel:
  busy=[x for x in rows if x['event']=='kernel_busy_observed'];assert busy and queued['steady_ns']<=busy[0]['steady_ns']<complete['steady_ns']
 assert all(x['steady_ns']>=complete['steady_ns'] for x in rows if x['event'] in ('buffer_released','session_destroyed'))
 result.update(physical_pending_verified=True,enqueued_to_completion_seconds=elapsed,settlement_before_release=True);return result
