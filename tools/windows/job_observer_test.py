"""Real Windows Job Object lifetime and outside-canary calibration."""
from pathlib import Path
import ctypes as C
from ctypes import wintypes as W
import argparse, hashlib, json, os, shutil, subprocess, sys, tempfile, time, traceback

parser=argparse.ArgumentParser(description="Calibrate a native Windows job observer using only generated peers.")
parser.add_argument('--observer',type=Path,required=True)
parser.add_argument('--output',type=Path,help='New directory retaining all evidence; otherwise successful temporary evidence is removed.')
parser.add_argument('--peer-python',type=Path,
                    help='Ordinary Python executable for generated peers; defaults to this interpreter. Store app execution may reject assignment.')
args=parser.parse_args()
if os.name!='nt':parser.error('native Windows is required')
ROOT=args.output.resolve() if args.output else Path(tempfile.mkdtemp(prefix='NEX job objects, % 🧠 '))
if args.output:ROOT.mkdir(parents=True,exist_ok=False)
PYTHON = (args.peer_python or Path(sys.executable)).resolve(strict=True)
started = time.monotonic()
report = {'schema':'nex.windows-private-job-calibration/1','ok':False,'state':'preflight',
          'controller_pid':os.getpid(),'cases':[], 'existing_apps_queried_or_modified':False,
          'global_process_enumeration_used':False,'whole_debugger_or_SDK_accepted':False}
def save():
    report['seconds'] = time.monotonic()-started
    p=ROOT/'calibration.tmp';p.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    p.replace(ROOT/'calibration.json')
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
canary=None
try:
    helper=args.observer.resolve(strict=True)
    env={key:value for key,value in os.environ.items() if key.upper() in
         ('SYSTEMROOT','WINDIR','COMSPEC','SYSTEMDRIVE','USERPROFILE','LOCALAPPDATA','PROCESSOR_ARCHITECTURE','NUMBER_OF_PROCESSORS','PATH')}
    tmp=ROOT/'tmp';tmp.mkdir()
    env.update(TEMP=str(tmp),TMP=str(tmp),PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1')
    report.update(helper_exe_sha256=sha(helper),test_source_sha256=sha(__file__))
    report.update(controller_python=sys.version, controller_executable=sys.executable,
                  peer_python=str(PYTHON))
    peer=ROOT/'peer.py'
    peer.write_text('''from pathlib import Path
import json,os,subprocess,sys,time
mode,marker=sys.argv[1:3];marker=Path(marker)
if mode=='canary':
 marker.write_text(json.dumps({'pid':os.getpid()}))
 until=time.monotonic()+60
 while not marker.with_suffix('.stop').exists():
  if time.monotonic()>until:sys.exit(19)
  time.sleep(.02)
 sys.exit(0)
if mode in ['short-child','long-child']:
 marker.write_text(json.dumps({'pid':os.getpid(),'arguments':sys.argv[3:]}),encoding='utf-8')
 time.sleep(.15 if mode=='short-child'else 60);print('child completed');sys.exit(0)
if mode in ['healthy','orphan','wait-parent']:
 child=subprocess.Popen([sys.executable,'-B',__file__,'short-child'if mode=='healthy'else'long-child',str(marker),'x y','λ 🧠','ends\\\\','a"b'])
 until=time.monotonic()+5
 while not marker.exists():
  assert time.monotonic()<until;time.sleep(.01)
 marker.with_suffix('.parent').write_text(json.dumps({'pid':os.getpid(),'child_pid':child.pid}))
 if mode=='healthy':sys.exit(child.wait(timeout=10))
 if mode=='orphan':sys.exit(0)
 time.sleep(60)
if mode=='write-marker':marker.write_text('must not execute')
if mode=='fail-root':sys.exit(7)
''',encoding='utf-8')
    def wait_file(path,timeout=8):
        until=time.monotonic()+timeout
        while not path.is_file():
            assert time.monotonic()<until, 'own peer marker timed out'
            time.sleep(.01)
    marker=ROOT/'outside-canary.json'
    with (ROOT/'canary.stdout').open('wb') as out,(ROOT/'canary.stderr').open('wb') as err:
        canary=subprocess.Popen([str(PYTHON),'-u','-B',str(peer),'canary',str(marker)],env=env,stdout=out,stderr=err)
    wait_file(marker);assert canary.poll() is None
    report['outside_canary_pid']=canary.pid
    cases=ROOT/'cases, % 🧠';cases.mkdir()
    for label,mode,budget,expected in [('healthy','healthy',10000,0),('parent-zero-live-child','orphan',1500,124),
                                       ('nonzero-root','fail-root',10000,7),('assignment-refused','write-marker',10000,125)]:
        report['state']=label;save();prefix=cases/label;peer_marker=cases/(label+'.peer')
        command=[helper,prefix,str(budget),str(canary.pid),*(['--reject-assignment']if label=='assignment-refused'else[]),
                 '--',PYTHON,'-u','-B',peer,mode,peer_marker]
        p=subprocess.run(list(map(str,command)),env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20)
        (cases/(label+'.helper.stdout')).write_bytes(p.stdout);(cases/(label+'.helper.stderr')).write_bytes(p.stderr)
        result=json.loads(Path(str(prefix)+'.json').read_text(encoding='utf-8'))
        assert p.returncode==expected,(label,p.returncode,result,p.stderr)
        assert result['outside_canary_alive_before'] and result['outside_canary_alive_after'] and canary.poll() is None
        assert result['final_job_accounting_observed'] and result['active_job_processes']==0
        assert not result['parent_PID_ownership_used'] and result['assignment_at_creation'] and result['stdio_handles_only']
        assert all(row['kernel_membership_verified']and row['exited']for row in result['processes'])
        assert all(row['pid']!=canary.pid for row in result['processes'])
        if label=='assignment-refused':
            assert not result['created_root'] and not result['root_resumed'] and not peer_marker.exists()
            assert not result['probe_completed'] and result['error']
        else:
            assert result['probe_completed']and result['root_job_verified_before_resume']and result['root_resumed']
            assert result['root_exit_code']==(7 if label=='nonzero-root'else 0)
        if label=='healthy':
            ids=json.loads(peer_marker.with_suffix('.parent').read_text());peer_ids={ids['pid'],ids['child_pid']};observed_ids={row['pid']for row in result['processes']};assert peer_ids<=observed_ids and result['total_job_processes']==len(result['processes']);console=Path(os.environ['SystemRoot'])/'System32/conhost.exe';assert all(Path(row['image'])==console for row in result['processes']if row['pid']not in peer_ids)
            assert all(row['exit_code']==0 for row in result['processes'])
            assert json.loads(peer_marker.read_text(encoding='utf-8'))['arguments']==['x y','λ 🧠','ends\\','a"b']
        if label=='parent-zero-live-child':
            assert result['timed_out']and result['private_job_termination_requested']
            ids=json.loads(peer_marker.with_suffix('.parent').read_text());assert result['root_pid']==ids['pid'];child=next(row for row in result['processes']if row['pid']==ids['child_pid']);assert child['exit_code']==238 and result['total_job_processes']==len(result['processes'])
        report['cases'].append({'label':label,'passed':True,'helper_exit_code':p.returncode,'observation':result});save()

    # Abruptly stop only the helper process created here. Its private job must
    # retire its two own peers while the separate outside-job canary survives.
    report['state']='observer-abrupt-exit';save();prefix=cases/'observer-abrupt-exit';peer_marker=cases/'abrupt.peer'
    command=list(map(str,[helper,prefix,'10000',str(canary.pid),'--',PYTHON,'-u','-B',peer,'wait-parent',peer_marker]))
    kernel=C.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD];kernel.OpenProcess.restype=W.HANDLE
    kernel.WaitForSingleObject.argtypes=[W.HANDLE,W.DWORD];kernel.WaitForSingleObject.restype=W.DWORD
    kernel.GetExitCodeProcess.argtypes=[W.HANDLE,C.POINTER(W.DWORD)];kernel.GetExitCodeProcess.restype=W.BOOL
    kernel.CloseHandle.argtypes=[W.HANDLE]
    held=[]
    with (cases/'abrupt.helper.stdout').open('wb')as out,(cases/'abrupt.helper.stderr').open('wb')as err:
        observer=subprocess.Popen(command,env=env,stdout=out,stderr=err)
        try:
            wait_file(peer_marker.with_suffix('.parent'))
            ids=json.loads(peer_marker.with_suffix('.parent').read_text())
            for pid in [ids['pid'],ids['child_pid']]:
                # Read-only handles to the IDs reported by these own peers;
                # never used to terminate anything or discover a process tree.
                handle=kernel.OpenProcess(0x101000,False,pid);assert handle;held.append((pid,handle))
            observer.terminate();observer.wait(timeout=5)
            exits=[]
            for pid,handle in held:
                assert kernel.WaitForSingleObject(handle,5000)==0
                code=W.DWORD();assert kernel.GetExitCodeProcess(handle,C.byref(code));assert code.value!=259
                exits.append({'pid':pid,'exit_code':code.value})
            assert canary.poll() is None
            report['cases'].append({'label':'observer-abrupt-exit','passed':True,'observer_exit':observer.returncode,
                                    'own_peer_exits':exits,'outside_canary_still_alive':True})
        finally:
            if observer.poll() is None:observer.terminate();observer.wait(timeout=5)
            for pid,handle in held:kernel.CloseHandle(handle)
    assert len(report['cases'])==5
    # Exercise admission of a long workflow without waiting for that budget.
    # Peer lifetimes and every original timeout/canary check stay unchanged.
    features=json.loads(subprocess.check_output([str(helper),'--describe'],env=env,timeout=10))
    assert features['maximum_timeout_ms']==10800000
    report['workflow_budget_cases']=[]
    for budget in [3600001,10800000]:
        label='workflow-budget-'+str(budget);prefix=cases/label;peer_marker=cases/(label+'.peer')
        command=[helper,prefix,str(budget),str(canary.pid),'--',PYTHON,'-u','-B',peer,'healthy',peer_marker]
        completed=subprocess.run(list(map(str,command)),env=env,capture_output=True,timeout=20)
        result=json.loads(Path(str(prefix)+'.json').read_text(encoding='utf-8'))
        assert completed.returncode==0 and result['root_exit_code']==0 and not result['timed_out']
        assert result['root_job_verified_before_resume'] and result['final_job_accounting_observed'] and result['active_job_processes']==0
        assert all(row['kernel_membership_verified'] and row['exited'] for row in result['processes'])
        assert result['outside_canary_alive_after'] and canary.poll()is None
        report['workflow_budget_cases'].append({'budget_ms':budget,'passed':True,'observation':result})
    for budget in ['0','10800001','-1','18446744073709551615']:
        prefix=cases/('rejected-budget-'+budget);peer_marker=prefix.with_suffix('.peer')
        command=[helper,prefix,budget,str(canary.pid),'--',PYTHON,'-u','-B',peer,'write-marker',peer_marker]
        completed=subprocess.run(list(map(str,command)),env=env,capture_output=True,timeout=10)
        assert completed.returncode==126 and not peer_marker.exists()and not Path(str(prefix)+'.json').exists()
        assert canary.poll()is None
        report['workflow_budget_cases'].append({'rejected_budget_ms':budget,'program_not_created':True,'passed':True})
    # Exercise the maintained wrapper through this actual Python interpreter,
    # preserving both a normal and a nonzero root result and a job timeout.
    from job_observer import observe
    report['wrapper_cases'] = []
    for label, mode, expected, budget in [
            ('wrapper-zero', 'healthy', 0, 10),
            ('wrapper-seven', 'fail-root', 7, 10),
            ('wrapper-timeout', 'orphan', 0, 1.5),
            ('wrapper-workflow-budget', 'healthy', 0, 7200)]:
        result = observe([str(PYTHON), '-u', '-B', str(peer), mode,
                          str(cases/(label+'.peer'))], ROOT/label, env,
                         observer=helper, timeout=budget)
        assert result['parent_exit_code'] == expected, result
        assert result['timed_out'] is (label == 'wrapper-timeout'), result
        assert result['kernel_job_membership_verified'], result
        assert result['active_job_processes'] == 0, result
        assert canary.poll() is None
        report['wrapper_cases'].append(dict(label=label, passed=True, observation=result))
    report['wrapper_budget_rejections']=[]
    for rejected in [0,10800.001,float('nan')]:
        destination=ROOT/('wrapper-reject-'+str(rejected))
        try:observe([str(PYTHON),'-u','-B',str(peer),'write-marker',str(destination)+'.peer'],destination,env,observer=helper,timeout=rejected)
        except ValueError:pass
        else:raise AssertionError('out-of-range wrapper budget accepted')
        assert not destination.exists()and not Path(str(destination)+'.peer').exists()and canary.poll()is None
        report['wrapper_budget_rejections'].append({'budget':repr(rejected),'program_not_created':True,'passed':True})
    marker.with_suffix('.stop').write_text('stop');assert canary.wait(timeout=5)==0
    report.update(ok=True,state='passed',outside_canary_cooperative_exit=canary.returncode)
except BaseException as error:
    report.update(state='failed',error=repr(error),traceback=traceback.format_exc())
finally:
    if canary is not None and canary.poll()is None:
        (ROOT/'outside-canary.stop').write_text('stop')
        try:canary.wait(timeout=5)
        except subprocess.TimeoutExpired:
            # Popen owns this exact separately-created canary handle.
            canary.terminate();canary.wait(timeout=5)
    save()
print(json.dumps({**{key:report.get(key)for key in ['ok','state','error','seconds']},'evidence':str(ROOT),
    'cases':report['cases'],'workflow_budget_cases':report.get('workflow_budget_cases',[]),
    'wrapper_cases':report.get('wrapper_cases',[]),'wrapper_budget_rejections':report.get('wrapper_budget_rejections',[])}))
if report['ok']and not args.output:shutil.rmtree(ROOT)
raise SystemExit(0 if report['ok']else 1)
