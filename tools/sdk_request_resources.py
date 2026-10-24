"""Installed-only request ancestry and native per-task resource completion."""
from pathlib import Path
import platform
from sdk_task_file_migration import _require,_sha

def check_installed_request_resources(run,root,resources,driver):
    root,resources=Path(root),Path(resources);out=root/'request-resource-ownership';out.mkdir()
    runtime=resources/'runtime';evidence={}
    common=[runtime/name for name in ('nex_external_resource.cpp','nex_resource_executor.cpp',
            'nex_resource_region.cpp','runtime.cpp','nex_files.cpp','nex_task_external.cpp')]
    for label,source,count,marker in (
        ('primitive','request_resource_regions_acceptance.cpp',17,'REQUEST RESOURCE REGION CASES 17'),
        ('native','native_request_resources_acceptance.cpp',13,'NATIVE REQUEST RESOURCE CASES 13')):
        binary=out/label;sources=[resources/'tools'/source,*common]
        args=[driver,'-std=c++20','-pthread','-DNEX_STRUCTURED_WORKERS','-DNEX_ASYNC_TASKS',
              '-I'+str(runtime),*sources,'-o',binary]
        if platform.system()=='Linux':args.append('-ldl')
        run(args,cwd=out,timeout=300);output=run([binary],cwd=out,timeout=120)
        cases=[line for line in output.splitlines() if line.startswith('PASS ')]
        _require(len(cases)==len(set(cases))==count and output.rstrip().endswith(marker),
                 'installed '+label+' request resource cases did not complete')
        evidence[label]={'ok':True,'cases':count,'binary_sha256':_sha(binary.read_bytes()),
                        'installed_sources':{str(p.relative_to(resources)):_sha(p.read_bytes()) for p in sources}}
    return {'ok':True,'primitive_cases':17,'native_cases':13,'native_per_task_ownership':True,
            'future_publication_waits_physical_settlement':True,'caller_borrow_survives_group':True,
            'explicit_request_return_preserves_identity':True,'sibling_authority_refused':True,
            'single_source_worker_progress_during_cleanup':True,'cancel_deadline_physical_fence':True,
            'combined_256_task_scope_depth':True,'ancestor_spawn_preserves_lifetime':True,
            'unpublished_creation_physical_fence':True,'source_value_transport':False,
            'installed_reference_private_host_gate':False,'evidence':evidence}
