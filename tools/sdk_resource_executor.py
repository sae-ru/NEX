"""Exercise the actual private host executor using only installed SDK files."""
from pathlib import Path
import platform
from sdk_task_file_migration import _require,_sha

def check_installed_resource_executor(run,root,resources,driver):
    root,resources=Path(root),Path(resources)
    out=root/'resource-executor';out.mkdir()
    runtime=resources/'runtime';tools=resources/'tools'
    module=out/'executor-module.so';probe=out/'resource-executor'
    run([driver,'-std=c++20','-pthread','-shared','-fPIC','-I'+str(runtime),
         tools/'resource_executor_module.cpp','-o',module],cwd=out)
    args=[driver,'-std=c++20','-pthread','-I'+str(runtime),'-I'+str(resources/'tests'),
          tools/'resource_executor_acceptance.cpp',runtime/'nex_resource_executor.cpp',
          runtime/'nex_external_resource.cpp',runtime/'nex_resource_region.cpp','-o',probe]
    if platform.system()=='Linux':args.append('-ldl')
    run(args,cwd=out)
    output=run([probe,module],cwd=out,timeout=90)
    cases=[line for line in output.splitlines() if line.startswith('PASS ')]
    _require(len(cases)==len(set(cases))==21 and output.rstrip().endswith('RESOURCE EXECUTOR CASES 21'),
             'installed resource executor did not finish all physical lifetime cases')
    return {'ok':True,'cases':len(cases),'owning_thread_factory_cleanup':True,
            'physical_fence_and_quota_retention':True,'queued_running_cancellation':True,
            'actual_module_destructor_unload':True,'module_exceptions_destroyed_before_unload':True,
            'source_task_bridge':False,'actual_GPU_NPU_resources':False,
            'module_sha256':_sha(module.read_bytes()),'probe_sha256':_sha(probe.read_bytes()),
            'installed_sources':{str(p.relative_to(resources)):_sha(p.read_bytes()) for p in
              (runtime/'nex_resource_executor.h',runtime/'nex_resource_executor.cpp',runtime/'nex_resource_region.h',runtime/'nex_resource_region.cpp',
               runtime/'nex_resource.h',runtime/'nex_external_resource.h',runtime/'nex_external_resource.cpp',
               tools/'resource_executor_acceptance.cpp',tools/'resource_executor_module.cpp',resources/'tests/host_test.h')}}
