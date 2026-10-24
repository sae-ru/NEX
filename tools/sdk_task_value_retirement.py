"""Installed-only native owned-value retirement and completion fences."""
from pathlib import Path
import platform
from sdk_task_file_migration import _require,_sha

def check_installed_task_value_retirement(run,root,resources,driver):
    root,resources=Path(root),Path(resources);out=root/'task-value-retirement';out.mkdir()
    runtime=resources/'runtime';binary=out/'task-value-retirement'
    sources=[resources/'tools/task_value_retirement_acceptance.cpp',*[runtime/name for name in
      ('runtime.cpp','nex_files.cpp','nex_external_resource.cpp','nex_resource_region.cpp',
       'nex_resource_executor.cpp','nex_task_external.cpp')]]
    args=[driver,'-std=c++20','-pthread','-DNEX_STRUCTURED_WORKERS','-DNEX_ASYNC_TASKS',
          '-I'+str(runtime),*sources,'-o',binary]
    if platform.system()=='Linux':args.append('-ldl')
    run(args,cwd=out,timeout=300);output=run([binary],cwd=out,timeout=90)
    cases=[line for line in output.splitlines() if line.startswith('PASS ')]
    _require(len(cases)==len(set(cases))==13 and output.rstrip().endswith('TASK VALUE RETIREMENT CASES 13'),
             'installed task value retirement cases did not complete')
    return {'ok':True,'cases':13,'destructors_outside_scheduler_mutex':True,
            'cancelled_event_cleanup':True,'task_scope_publication_fence':True,
            'buffer_storage_quota_fence':True,'nested_reentrant_cleanup':True,
            'root_results_remain_joinable':True,'iterative_256_scope_retirement':True,'source_resource_transport':False,
            'probe_sha256':_sha(binary.read_bytes()),
            'installed_sources':{str(p.relative_to(resources)):_sha(p.read_bytes()) for p in sources}}
