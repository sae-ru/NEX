"""Compile and execute the private stream bridge from installed SDK files only."""
import json
import hashlib
from pathlib import Path
import platform

def _require(condition,message):
 if not condition:raise RuntimeError(message)
def _sha(data):return hashlib.sha256(data).hexdigest()

CASES=(
 'open_on_worker_uses_captured_root_without_TLS','streamed_file_exceeds_whole_file_limit',
 'shared_cursor_aliases_and_absolute_seek','concurrent_reads_share_one_serialized_cursor',
 'write_snapshots_visible_input_and_flushes','append_uses_kernel_end_even_after_seek',
 'actual_partial_write_count_in_separate_child','modes_ranges_and_existing_error_priority',
 'read_only_grant_cannot_open_a_writer','invalid_paths_and_nonregular_files_do_not_open',
 'preparation_does_not_create_or_truncate','prepared_open_is_one_shot_and_has_no_raw_file_id',
 'unpublished_open_retains_real_quota_until_discard','closed_file_pins_quota_until_actual_worker_retirement',
 'close_after_IO_suppresses_data_with_typed_closed_result','request_scope_revocation_prevents_open_admission',
 'preopen_cancel_preserves_old_file','postopen_cancel_discards_owner_without_rollback',
 'postwrite_cancel_keeps_bytes_and_withholds_result','stream_reply_bounds_and_scalar_contracts_are_checked',
 'stream_one_shot_and_unknown_error_rejection','open_wakeup_cannot_fabricate_file_authority',
 'transport_backpressure_retains_exact_payload_credits','captured_root_survives_pathname_replacement',
 'post_IO_deadlines_retain_fatal_priority_and_retire_unpublished_files',
 'one_CPU_task_progresses_during_stream_IO','one_CPU_task_cancel_waits_stream_retirement')
HEADERS=('nex_task_file_stream.h','nex_files.h','nex_file_resource.h','nex_resource.h','nex_task_external.h','nex_tasks.h')
SOURCES=('runtime.cpp','nex_files.cpp','nex_external_resource.cpp','nex_resource_region.cpp','nex_resource_executor.cpp','nex_task_external.cpp')
PARTIAL_WRITE_CASE='actual_partial_write_count_in_separate_child'

def cases_for_platform(system):
 _require(system in ('Darwin','Linux','Windows'),'unsupported installed stream host platform')
 # The C++ fixture uses a child-only POSIX RLIMIT_FSIZE for this physical
 # partial-write proof. Its Windows build explicitly excludes that scenario.
 return tuple(name for name in CASES if system!='Windows' or name!=PARTIAL_WRITE_CASE)

def parse_host_output(output,system):
 names=[line[5:] for line in output.splitlines() if line.startswith('PASS ')]
 raw=json.loads(output.splitlines()[-1]);expected=cases_for_platform(system)
 _require(len(names)==len(set(names))==len(expected) and set(names)==set(expected) and raw.get('ok') is True and
          type(raw.get('host_stream_cases')) is int and raw['host_stream_cases']==len(expected) and
          raw.get('public_source_support') is False and raw.get('maximum_chunk_bytes')==1048576 and
          raw.get('one_shot_typed_open') is True and raw.get('physical_drain') is True,
          'installed task stream host did not execute its physical platform cases')
 return names,raw

def check_installed_task_streams(run,root,resources,driver):
 root,resources=Path(root),Path(resources);out=root/'private-task-file-streams';out.mkdir()
 runtime=resources/'runtime';source=resources/'tools/task_file_stream_host_acceptance.cpp';binary=out/'file-stream-host'
 sources=[source,*[runtime/name for name in SOURCES]]
 command=[driver,'-std=c++20','-pthread','-DNEX_STRUCTURED_WORKERS','-DNEX_ASYNC_TASKS','-I'+str(runtime),'-I'+str(resources/'tests'),*sources,'-o',binary]
 if platform.system()=='Linux':command.append('-ldl')
 run(command,cwd=out,timeout=300);output=run([binary],cwd=out,timeout=120)
 system=platform.system();names,raw=parse_host_output(output,system);partial=PARTIAL_WRITE_CASE in names
 return {'schema':'nex.installed-task-stream-host/1','ok':True,'cases':len(names),'case_names':names,'source_support':False,
   'host_platform':system,'portable_corpus_complete':partial,'pending_cases':[] if partial else [PARTIAL_WRITE_CASE],
   'actual_partial_write':partial,'typed_open_no_raw_file_ids':True,'original_grants':True,'physical_quota_retention':True,
   'single_CPU_worker_progress':True,'cancel_physical_drain':True,'immutable_input_snapshots':True,'large_file_streaming':True,
   'protocol_rejections':True,'probe_sha256':_sha(binary.read_bytes()),'raw_report':raw,
   'installed_sources':{str(p.relative_to(resources)):_sha(p.read_bytes()) for p in [*sources,*[runtime/name for name in HEADERS],resources/'tests/host_test.h']}}
