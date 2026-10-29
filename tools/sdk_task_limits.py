"""Installed task limits and source-deleted launch controls."""
import json
from pathlib import Path
import shutil

def check_installed_task_limits(cli,run,last_command,root,resources,environment):
    from sdk_acceptance import require
    language=cli('describe','--kind','index')['language']
    unavailable=environment['NEX_RESOURCE_DIR']
    # Run a real task application with the installed headers/runtime. This
    # phase executes with the original compiler source path unavailable.
    task_project = root / 'structured-task-limits'
    task_project.mkdir()
    (task_project / 'nex.json').write_text(json.dumps({'schema':'nex.project/1',
        'language':language,'entry':'main.nex'}))
    program='module installed_task_limits;\nfn solve()->i64 !{task}{return with_tasks(2,fn(scope:task_scope)->i64 !{task}{\n let child:task<i64>=task_spawn(scope,fn()->i64 !{task}{task_yield();return 42;});\n return task_wait(child);\n});}\nfn main()->i64 !{io,task}{print(solve());return 0;}\ntest fn checks()->unit !{task}{assert(solve()==42);}\n'
    if language in ('0.25','0.26'):
        program='module installed_task_limits;\nfn solve()->i64 !{task,throw}{return with_tasks(2,fn(scope:task_scope)->i64 !{task,throw}{\n let child:task<i64>=task_spawn(scope,fn()->i64 !{task}{task_yield();return 42;});\n return task_wait(child);\n});}\nfn main()->i64 !{io,task,throw}{print(solve());return 0;}\ntest fn checks()->unit !{task,throw}{assert(solve()==42);}\n'
    (task_project/'main.nex').write_text(program)
    caps={'steps':2000000,'timeout_ms':10000,'workers':2}
    controls=['--task-steps','2000000','--task-timeout-ms','10000','--task-workers','2']
    task_revision=cli('check',cwd=task_project)['revision']
    evaluated=cli('eval',*controls,cwd=task_project)
    require(evaluated['stdout']=='42\n' and evaluated['task_execution']['effective']==caps and
            evaluated['task_execution']['executor_workers']==1,'installed reference task limits differ')
    for profile in ('debug','release'):
        observed=cli('run','--profile',profile,*controls,cwd=task_project)
        require(observed['stdout']=='42\n' and observed['task_execution']['effective']==caps and
                observed['task_execution']['executor_workers']==2,'installed native task limits differ')
    for target in ('native','web'):
        observed=cli('test','--target',target,*controls,cwd=task_project)
        require(all(t['task_execution']['effective']==caps and
                    t['task_execution']['executor_workers']==(2 if target=='native' else 1)
                    for t in observed['tests']),'installed task test limits differ')
    built=cli('build','--profile','release',*controls,cwd=task_project)
    require(built['task_limits']==caps,'installed build lost task limits')
    standalone=root/'task-limits-standalone'
    shutil.copyfile(built['executable'],standalone);standalone.chmod(0o755)
    (task_project/'main.nex').unlink()
    try:
        environment['NEX_RESOURCE_DIR']=str(root/'absent-resources')
        require(run([standalone,'--nex-task-steps','100000','--nex-task-timeout-ms','1000',
                     '--nex-task-workers','1'])=='42\n','copied task application lost embedded/lowered limits')
        run([standalone,'--nex-task-workers','3'],expected_success=False)
        require('E_OPTION' in Path(last_command()['stderr']).read_text(),
                'copied task application raised embedded worker ceiling')
        run([standalone,'--nex-task-steps','1'],expected_success=False)
        require('E_LIMIT' in Path(last_command()['stderr']).read_text(),
                'copied task application ignored its lowered budget')
    finally:
        environment['NEX_RESOURCE_DIR']=unavailable
    require(cli('run','--revision',task_revision,*controls,cwd=task_project)['stdout']=='42\n',
            'installed task archive lost runtime controls after source deletion')
    return {'revision':task_revision,'limits':caps,
        'native_profiles':['debug','release'],'reference_workers':1,'typescript_workers':1,
        'native_pool_workers':2,'source_deleted':True,'standalone_without_resources':str(standalone),
        'launcher_lowered_limits':True,'launcher_raise_rejected':True,'lowered_budget_enforced':True,
        'identical_step_thresholds':False}
