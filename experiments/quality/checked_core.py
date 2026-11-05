"""Actual checked-i64/native throughput probe; retain inputs and every result."""
import argparse, datetime, hashlib, json, os, platform, resource, shutil, signal, statistics, subprocess, sys, threading, time, traceback
from pathlib import Path

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--compiler',type=Path,required=True)
parser.add_argument('--resources',type=Path)
parser.add_argument('--language',choices=('0.18','0.24','0.28'),default='0.28',
                    help='Corpus language; default 0.28, must match actual compiler discovery')
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--count',type=int,default=10000000)
parser.add_argument('--rounds',type=int,default=10)
parser.add_argument('--repeats',type=int,default=5)
settings=parser.parse_args()
assert 0<=settings.count<=10000000 and 1<=settings.rounds<=1000 and 3<=settings.repeats<=31
nex=settings.compiler.resolve();out=settings.output.resolve()
assert nex.is_file() and not out.exists()
out.mkdir();project=out/'project';project.mkdir()
compiler_digest=hashlib.sha256(nex.read_bytes()).hexdigest()
started = time.monotonic()
report = {'schema': 'nex.checked-core-comparison/2', 'ok': False, 'state': 'running',
          'phase': 'prepare', 'toolchain': None, 'language': settings.language, 'commands': [],
          'full_objective_complete': False, 'runtime_cpp_parity_established': False,
          'model_cost_measured': False, 'isolated_host': False,
          'scope': 'One positive bounded checked-i64 modular recurrence. Host isolation is not established; process wall latency includes startup. No cross-platform/application/general-language parity claim.'}
env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}
linux=sys.platform.startswith('linux')
usage_launcher=None
report['resource_measurement']={'linux':'C fork/exec/wait4 launcher excludes Python driver peak',
    'darwin':'direct wait4; maximum RSS is already in bytes',
    'scope':'command and waited descendants: CPU sum and largest process RSS, not concurrent memory sum',
    'linux_bootstrap_RSS_valid':False}
if settings.resources is not None:env['NEX_RESOURCE_DIR']=str(settings.resources.resolve())
else:env.pop('NEX_RESOURCE_DIR',None)

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def guard():
    assert digest(nex)==compiler_digest,'compiler changed during measurement'

def save():
    report.update(updated=datetime.datetime.now(datetime.timezone.utc).isoformat(), seconds=round(time.monotonic()-started, 3))
    temporary=out/'report.json.tmp'
    temporary.write_text(json.dumps(report, indent=2) + '\n')
    temporary.replace(out/'report.json')

def command(label, args, inputs=None, timeout=120):
    report['phase'] = label
    save()
    index = len(report['commands'])
    prefix = '%03d-%s' % (index, label)
    local = dict(env)
    if inputs is not None:
        local['NEX_BENCH_SEED'] = json.dumps(str(inputs[0]))
        local['NEX_BENCH_COUNT'] = json.dumps(str(inputs[1]))
        local['NEX_BENCH_ROUNDS'] = json.dumps(str(inputs[2]))
    usage_path=out/(prefix+'.usage.json')
    arguments=list(map(str,args))
    launched=[str(usage_launcher),str(usage_path),*arguments] if usage_launcher else arguments
    row={'name':label,'command':arguments,'inputs':inputs,'status':'running',
         'stdout':prefix+'.stdout','stderr':prefix+'.stderr',
         'maximum_rss_valid':not linux or usage_launcher is not None,
         'resource_backend':'C-fork-exec-wait4' if usage_launcher else 'direct-wait4'}
    if usage_launcher:row.update(launcher_command=launched,usage=usage_path.name)
    report['commands'].append(row);save()
    with (out / (prefix + '.stdout')).open('wb') as stdout, (out / (prefix + '.stderr')).open('wb') as stderr:
        start=time.monotonic()
        p = subprocess.Popen(launched, cwd=project, env=local, stdout=stdout, stderr=stderr,start_new_session=True)
        row['pid']=p.pid;save();done=threading.Event()
        def terminate():
            if done.is_set():return
            try:os.killpg(p.pid,signal.SIGKILL)
            except ProcessLookupError:pass
        timer = threading.Timer(timeout, terminate)
        timer.daemon = True
        timer.start()
        try:
            _, status, usage = os.wait4(p.pid, 0)
            p.returncode = os.waitstatus_to_exitcode(status)
        except BaseException as error:
            terminate()
            try:os.wait4(p.pid,0)
            except ChildProcessError:pass
            row.update(status='interrupted',error=repr(error));save()
            raise
        finally:
            done.set()
            timer.cancel()
    row.update({'exit_code': p.returncode,
           'seconds': time.monotonic()-start, 'user_seconds': usage.ru_utime, 'system_seconds': usage.ru_stime,
           'maximum_rss_bytes': usage.ru_maxrss if sys.platform == 'darwin' else usage.ru_maxrss * 1024,
           'status':'passed' if p.returncode==0 else 'failed'})
    if usage_launcher:
        if usage_path.is_file():
            measured=json.loads(usage_path.read_text())
            assert measured['exit_code']==p.returncode,'resource launcher exit differs from command'
            row.update({key:measured[key] for key in ('user_seconds','system_seconds','maximum_rss_bytes')})
            row['measured_pid']=measured['child_pid']
        else:row['maximum_rss_valid']=False
    save()
    assert p.returncode == 0, (label, p.returncode, (out / row['stderr']).read_text()[-2000:])
    return (out / row['stdout']).read_text(), row

def core_oracle(seed, count):
    state, checksum = seed, 0
    for _ in range(count):
        state = (state * 48271) % 2147483647
        checksum = (checksum + state) % 1000000007
    return checksum

def oracle(seed, count, rounds=3):
    total = 0
    for _ in range(rounds):
        total = (total + core_oracle(seed,count)) % 1000000007
        seed = seed % 2147483646 + 1
    return total

nex_text = '''module checked_core;
fn core(seed:i64,count:i64)->i64 {
  assert(seed>0 && seed<2147483647 && count>=0 && count<=10000000);
  var state:i64=seed;
  var checksum:i64=0;
  var index:i64=0;
  while(index<count) {
    state=(state*48271)%2147483647;
    checksum=(checksum+state)%1000000007;
    index=index+1;
  }
  return checksum;
}
fn batch(seed:i64,count:i64,rounds:i64)->i64 {
  assert(rounds>0 && rounds<=1000);
  var total:i64=0;
  var current:i64=seed;
  var round:i64=0;
  while(round<rounds) {
    total=(total+core(current,count))%1000000007;
    current=current%2147483646+1;
    round=round+1;
  }
  return total;
}
test fn edges()->unit {
  assert(batch(1,1,2)==144813);
  assert(core(1,0)==0);
  assert(core(1,1)==48271);
  assert(core(1,2)==182654065);
}
server fn main()->i64 !{io} {
  let seed:i64=unwrap(decode_json<i64>(unwrap(read_env("NEX_BENCH_SEED"))));
  let count:i64=unwrap(decode_json<i64>(unwrap(read_env("NEX_BENCH_COUNT"))));
  let rounds:i64=unwrap(decode_json<i64>(unwrap(read_env("NEX_BENCH_ROUNDS"))));
  print(batch(seed,count,rounds));
  return 0;
}
'''
cpp_text = r'''#include <charconv>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <string_view>
using I = std::int64_t;
[[noreturn]] void fail() { std::exit(70); }
I input(const char* name) {
  const char* raw=std::getenv(name); if(!raw) fail();
  std::string_view s(raw); if(s.size()<3 || s.front()!='"' || s.back()!='"') fail();
  s.remove_prefix(1); s.remove_suffix(1); I value;
  auto [end,ec]=std::from_chars(s.data(),s.data()+s.size(),value);
  if(ec!=std::errc{} || end!=s.data()+s.size()) fail(); return value;
}
inline I add(I a,I b) { I r; if(__builtin_add_overflow(a,b,&r)) fail(); return r; }
inline I mul(I a,I b) { I r; if(__builtin_mul_overflow(a,b,&r)) fail(); return r; }
inline I rem(I a,I b) { if(b==0 || (a==INT64_MIN && b==-1)) fail(); return a%b; }
__attribute__((noinline)) I core(I seed,I count) {
  if(!(seed>0 && seed<2147483647 && count>=0 && count<=10000000)) fail();
  I state=seed,checksum=0,index=0;
  while(index<count) {
    state=rem(mul(state,48271),2147483647);
    checksum=rem(add(checksum,state),1000000007);
    index=add(index,1);
  }
  return checksum;
}
I batch(I seed,I count,I rounds) {
  if(!(rounds>0 && rounds<=1000)) fail();
  I total=0,round=0;
  while(round<rounds) {
    total=rem(add(total,core(seed,count)),1000000007);
    seed=add(rem(seed,2147483646),1);
    round=add(round,1);
  }
  return total;
}
int main() { std::cout<<batch(input("NEX_BENCH_SEED"),input("NEX_BENCH_COUNT"),input("NEX_BENCH_ROUNDS"))<<'\n'; }
'''
python_text = """import json,os
seed=int(json.loads(os.environ['NEX_BENCH_SEED']))
count=int(json.loads(os.environ['NEX_BENCH_COUNT']))
rounds=int(json.loads(os.environ['NEX_BENCH_ROUNDS']))
assert 0<seed<2147483647 and 0<=count<=10000000 and 0<rounds<=1000
def core(seed,count):
 state,checksum,index=seed,0,0
 while index<count:
  state=(state*48271)%2147483647
  checksum=(checksum+state)%1000000007
  index=index+1
 return checksum
total=0
for _ in range(rounds):
 total=(total+core(seed,count))%1000000007
 seed=seed%2147483646+1
print(total)
"""

try:
    guard()
    (project / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1', 'language': settings.language, 'entry': 'main.nex'}) + '\n')
    (project / 'main.nex').write_text(nex_text)
    (out / 'baseline.cpp').write_text(cpp_text)
    (out / 'baseline.py').write_text(python_text)
    report['input_domain'] = {'seed': [1,2147483646], 'count': [0,10000000], 'rounds':[1,1000],
        'largest_multiply': 2147483646*48271, 'largest_add': 1000000006+2147483646,
        'overflow_possible_within_domain': False,
        'semantics': 'All integer operands stay nonnegative and within i64; Python arbitrary integers and floor remainder agree on this domain. C++ uses explicit checked add/multiply/remainder. NEX also includes its existing runtime polling, ownership and instrumentation costs; C++ baseline has no cancellation/step-budget runtime.'}
    capabilities, _ = command('capabilities',[nex,'describe','--json'])
    descriptor=json.loads(capabilities)
    assert descriptor['version']==settings.language,'explicit corpus language must match actual compiler discovery'
    actual, _ = command('doctor', [nex,'doctor','--json'])
    doctor = json.loads(actual)
    assert doctor['language']==settings.language,'doctor differs from the explicitly selected corpus language'
    report['discovered_language']=descriptor['version']
    report['host_load_average_before']=list(os.getloadavg())
    report['toolchain']=doctor.get('toolchain',doctor.get('version'))
    report['probe_sha256']=digest(Path(__file__).resolve())
    clang = Path(doctor['native_compiler'])
    assert clang.is_file()
    version, _ = command('clang-version', [clang,'--version'])
    report['compilers'] = {'nex_sha256': digest(nex), 'clang': str(clang), 'clang_version': version,
                           'python': sys.executable, 'python_version': sys.version, 'machine': platform.machine()}
    if linux:
        source=out/'usage-launcher.c'
        shutil.copyfile(Path(__file__).with_name('usage_launcher.c'),source)
        executable=out/'usage-launcher'
        command('rss-launcher-build',[clang,'-x','c','-std=c11','-O2','-g0','-nostdlib++',source,'-o',executable])
        usage_launcher=executable
        _,control=command('rss-launcher-control',['/bin/true'])
        report['resource_launcher']={'source_sha256':digest(source),'executable_sha256':digest(executable),
            'parent_peak_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
            'small_child_peak_bytes':control['maximum_rss_bytes']}
    checked, _ = command('check', [nex,'check','--json'])
    report['revision'] = json.loads(checked)['revision']
    command('native-tests', [nex,'test','--profile','release','--json'], timeout=300)
    command('typescript-tests', [nex,'test','--target','web','--json'], timeout=300)
    built, _ = command('release-build', [nex,'build','--profile','release','--json'], timeout=300)
    build = json.loads(built)
    binary = Path(build['executable'])
    cpp = out / 'baseline'
    command('cpp-build', [clang,'-std=c++20','-O2','-g0',out/'baseline.cpp','-o',cpp])
    programs = {'nex': [binary], 'cpp_checked': [cpp], 'python': [sys.executable,out/'baseline.py']}
    cases = [(1,0),(1,1),(1,2),(1234567,1000),(2147483646,3000)]
    for seed, count in cases:
        expected = str(oracle(seed,count,3)) + '\n'
        observed, _ = command('reference-%d-%d'%(seed,count), [nex,'eval','--steps','1000000','--json'], (seed,count,3))
        assert json.loads(observed)['stdout'] == expected
        for language, args in programs.items():
            observed, _ = command('agreement-'+language, args, (seed,count,3))
            assert observed == expected, (language,seed,count,observed,expected)
    seed, count, repeats = 1234567, settings.count, settings.repeats
    rounds = settings.rounds
    expected = str(oracle(seed,count,rounds)) + '\n'
    samples = {name: [] for name in programs}
    for language,args in programs.items():
        observed, _ = command('warmup-'+language, args, (seed,count,rounds))
        assert observed == expected
    order = list(programs)
    for iteration in range(repeats):
        for language in order[iteration%3:]+order[:iteration%3]:
            observed, row = command('measure-'+language, programs[language], (seed,count,rounds))
            assert observed == expected
            assert row['maximum_rss_valid'],'measurement lacks independent child RSS'
            samples[language].append({k:row[k] for k in ['seconds','user_seconds','system_seconds','maximum_rss_bytes']})
    summary = {name:{'samples':values,'median_wall_seconds':statistics.median(v['seconds'] for v in values),
                     'median_user_seconds':statistics.median(v['user_seconds'] for v in values),
                     'maximum_rss_bytes':max(v['maximum_rss_bytes'] for v in values)} for name,values in samples.items()}
    report.update(ok=True,state='passed',phase='complete',agreement_cases=len(cases),
                  host_load_average_after=list(os.getloadavg()),
                  measured_seed=seed,measured_iterations=count,measured_rounds=rounds,total_recurrence_steps=count*rounds,repetitions=repeats,measurements=summary,
                  nex_over_cpp_checked_wall_ratio=summary['nex']['median_wall_seconds']/summary['cpp_checked']['median_wall_seconds'],
                  binary_bytes={'nex':binary.stat().st_size,'cpp_checked':cpp.stat().st_size},
                  source_digests={str(p.relative_to(out)):digest(p) for p in [project/'main.nex',project/'nex.json',out/'baseline.cpp',out/'baseline.py']},
                  executable_digests={'nex':digest(binary),'cpp_checked':digest(cpp)})
    guard()
except BaseException as error:
    report.update(state='failed',error=repr(error))
    traceback.print_exc()
finally:
    save()
    print(json.dumps({k:v for k,v in report.items() if k!='commands'}))
raise SystemExit(0 if report['ok'] else 1)
