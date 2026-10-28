"""Installed-only private native logical-resource lifecycle acceptance."""
from pathlib import Path
import platform
from sdk_task_file_migration import _require,_sha

def check_installed_resource_regions(run,root,resources,driver):
    root,resources=Path(root),Path(resources);out=root/'resource-regions';out.mkdir()
    runtime=resources/'runtime';binary=out/'resource-regions'
    sources=[resources/'tools/resource_regions_acceptance.cpp',*[runtime/name for name in
      ('nex_external_resource.cpp','nex_resource_executor.cpp','nex_resource_region.cpp',
       'runtime.cpp','nex_files.cpp','nex_task_external.cpp')]]
    args=[driver,'-std=c++20','-pthread','-DNEX_STRUCTURED_WORKERS','-DNEX_ASYNC_TASKS',
          '-I'+str(runtime),*sources,'-o',binary]
    if platform.system()=='Linux':args.append('-ldl')
    run(args,cwd=out,timeout=300);output=run([binary],cwd=out,timeout=90)
    cases=[line for line in output.splitlines() if line.startswith('PASS ')]
    _require(len(cases)==len(set(cases))==18 and output.rstrip().endswith('RESOURCE REGION CASES 18'),
             'installed logical resource region cases did not complete')
    return {'ok':True,'cases':18,'native_scope_ownership':True,'scope_exit_waits_physical_cleanup':True,
            'only_source_worker_remains_available':True,'native_256_scope_depth':True,
            'ancestor_promotion':True,'root_group_retirement':True,'prepared_access_survives_64_resumes':True,
            'unpublished_factory_fence':True,'source_task_bridge':False,'reference_scheduler':False,
            'actual_GPU_NPU_resources':False,'probe_sha256':_sha(binary.read_bytes()),
            'installed_sources':{str(p.relative_to(resources)):_sha(p.read_bytes()) for p in sources}}
