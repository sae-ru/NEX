"""Maintained native Windows cleanup regressions; no original-source ACL changes."""
from pathlib import Path
import argparse
import ctypes as C
from ctypes import wintypes as W
import hashlib,json,os,shutil,stat,sys,tempfile,time,traceback
from appcontainer import Profile, sha
parser=argparse.ArgumentParser(description='Exercise owned AppContainer cleanup after abrupt native exit, readonly files, reparse/hardlinks, replaced roots and bounded retries.')
parser.add_argument('--observer',required=True,type=Path)
parser.add_argument('--abrupt-probe',required=True,type=Path)
parser.add_argument('--output',type=Path,help='New retained evidence directory')
args=parser.parse_args()
if os.name!='nt':parser.error('native Windows is required')
OUT=args.output.resolve()if args.output else Path(tempfile.mkdtemp(prefix='nex-AppContainer-cleanup-'))
if args.output:OUT.mkdir(parents=True,exist_ok=False)
start=time.monotonic();profiles=[];saved_roots={};canary_temp=None;canary=None;manager=None
r={'schema':'nex.AppContainer-owned-cleanup-guards/1','ok':False,'state':'starting','controller_pid':os.getpid(),'cases':[],'profiles':[],'controls':[],'outside_profile_ACLs_changed':False,'python':sys.version,'output':str(OUT)}
def save():
 r['seconds']=time.monotonic()-start;(OUT/'report.json').write_text(json.dumps(r,indent=2)+'\n')
def fingerprint(p):
 h=manager._cleanup_open(p)
 try:
  identity,attrs=manager._cleanup_metadata(h);desc=C.c_void_p();error=manager.a.GetSecurityInfo(h,1,7,None,None,None,None,C.byref(desc));assert error==0,error
  try:
   text=W.LPWSTR();manager._check(manager.a.ConvertSecurityDescriptorToStringSecurityDescriptorW(desc,1,7,C.byref(text),None))
   try:sddl=text.value
   finally:manager.k.LocalFree(text)
  finally:manager.k.LocalFree(desc)
 finally:manager.k.CloseHandle(h)
 return {'identity':[identity[0],identity[1].hex()],'attributes':attrs,'SDDL':sddl,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()if p.is_file()else None}
def fresh(**kwargs):
 p=Profile(**kwargs);p.create();profiles.append(p);r['profiles'].append({'name':p.name,'SID':p.sid,'path':str(p.path)});save();return p
def gone(p):assert p.deleted and not p.path.exists()and not p.path.parent.exists()
try:
 r['helper_sha256']=sha(Path(__file__).with_name('appcontainer.py'));fixture=args.abrupt_probe.resolve(strict=True);fixture_sha=sha(fixture);inputs=OUT/'inputs';inputs.mkdir();shutil.copyfile(fixture,inputs/'probe.exe')
 helper=args.observer.resolve(strict=True);r['observer_sha256']=sha(helper);r['abrupt_probe_sha256']=fixture_sha
 env={k:v for k,v in os.environ.items()if not k.startswith(('NEX_','PYTHON'))};env.update(PYTHONUTF8='1',PATH='C:/Windows/System32;C:/Windows')
 manager=fresh();manager.a.ConvertSecurityDescriptorToStringSecurityDescriptorW.argtypes=[C.c_void_p,W.DWORD,W.DWORD,C.POINTER(W.LPWSTR),C.c_void_p];manager.a.ConvertSecurityDescriptorToStringSecurityDescriptorW.restype=W.BOOL
 tree=manager.copy_tree(inputs,max_files=2,max_bytes=32*1024**2);value=manager.run([str(tree/'probe.exe'),str(manager.temp/'abrupt-snapshot')],OUT/'native',manager.native_environment(env),observer=helper,timeout=30);r['cases']=[{'name':'abrupt-native-exit','observation':value}];save();assert value['parent_exit_code']==93 and value['active_job_processes']==0;manager.verify_copies();manager.close();gone(manager);r['controls'].append({'name':'abrupt-sealed-snapshot','ok':True,'stats':manager.cleanup_stats})
 canary_temp=tempfile.TemporaryDirectory(prefix='nex-cleanup-canary-',dir=manager.path.parent.parent);canary_root=Path(canary_temp.name);canary=canary_root/'keep.dat';canary.write_bytes(b'NEX outside-profile canary\x00\n');canary.chmod(stat.S_IREAD);before=fingerprint(canary);before_dir=fingerprint(canary_root)
 p=fresh();assert p.path.drive.casefold()==canary.drive.casefold();os.symlink(str(canary_root),p.work/'outside-directory',target_is_directory=True);os.link(canary,p.work/'outside-hardlink');own=p.work/'readonly.dat';own.write_bytes(b'owned');own.chmod(stat.S_IREAD);deep=p.work/'readonly-directory';deep.mkdir();(deep/'member').write_bytes(b'owned directory');deep.chmod(stat.S_IREAD)
 p.close();gone(p);assert fingerprint(canary)==before;assert fingerprint(canary_root)==before_dir;assert p.cleanup_stats['reparse_entries_unlinked']==1;assert p.cleanup_stats['hardlink_names_removed_without_ACL_or_attribute_changes']==1
 r['controls'].append({'name':'readonly-reparse-and-hardlink-no-outside-change','ok':True,'stats':p.cleanup_stats,'outside_canary':before})
 p=fresh();original=p.path;saved=p.path.parent/'AC-held';original.rename(saved);saved_roots[p.name]=saved;original.mkdir();sentinel=original/'kept';sentinel.write_bytes(b'replacement-root');root_before=fingerprint(original)
 try:p.close()
 except RuntimeError as error:assert 'root identity changed'in str(error)
 else:raise AssertionError('replaced root admitted for cleanup')
 assert fingerprint(original)==root_before and sentinel.read_bytes()==b'replacement-root';sentinel.unlink();original.rmdir();saved.rename(original);saved_roots.pop(p.name)
 original.rename(saved);saved_roots[p.name]=saved;os.symlink(str(canary_root),original,target_is_directory=True)
 try:p.close()
 except RuntimeError as error:assert 'root identity changed'in str(error)
 else:raise AssertionError('root reparse admitted for cleanup')
 assert fingerprint(canary)==before and fingerprint(canary_root)==before_dir;original.rmdir();saved.rename(original);saved_roots.pop(p.name);p.close();gone(p);r['controls'].append({'name':'replacement-and-reparse-roots-refused','ok':True})
 p=fresh(max_cleanup_entries=2)
 try:p.close()
 except RuntimeError as error:assert 'entry bound'in str(error)
 else:raise AssertionError('cleanup entry bound ignored')
 assert not p.deleted and p.path.exists();p.max_cleanup_entries=200000;p.close();gone(p);r['controls'].append({'name':'explicit-bound-retains-profile-then-reviewed-budget-retry','ok':True})
 assert all(p.deleted and not p.path.parent.exists()for p in profiles);assert fingerprint(canary)==before and fingerprint(canary_root)==before_dir;assert hashlib.sha256(fixture.read_bytes()).hexdigest()==fixture_sha
 r.update(ok=True,state='abrupt-alias-hardlink-readonly-root-identity-and-bound-guards-passed',all4_profiles_and_parents_absent=True,outside_canary_preserved=True)
except BaseException as error:
 r.update(state='failed',error=repr(error),traceback=traceback.format_exc());save()
finally:
 for p in reversed(profiles):
  if p.name in saved_roots:
   try:
    if p.path.is_symlink():p.path.rmdir()
    elif p.path.exists():
     entries=list(p.path.iterdir())
     assert all(x.name=='kept'and x.is_file()and not x.is_symlink()and x.read_bytes()==b'replacement-root'for x in entries)
     for x in entries:x.unlink()
     p.path.rmdir()
    saved_roots.pop(p.name).rename(p.path)
   except BaseException as error:r.setdefault('cleanup_errors',[]).append({'profile':p.name,'stage':'restore-own-root-fixture','error':repr(error)})
  if p.created and not p.deleted:
   try:
    if p.max_cleanup_entries==2:p.max_cleanup_entries=200000
    p.close()
   except BaseException as error:r.setdefault('cleanup_errors',[]).append({'profile':p.name,'stage':'owned-profile-close','error':repr(error)})
 if canary is not None and canary.exists():canary.chmod(stat.S_IREAD|stat.S_IWRITE)
 if canary_temp is not None:
  try:canary_temp.cleanup()
  except BaseException as error:r.setdefault('cleanup_errors',[]).append({'stage':'own-canary-close','error':repr(error)})
 r['profiles']=[{'name':p.name,'path':str(p.path),'deleted':p.deleted,'parent_absent':not p.path.parent.exists()}for p in profiles]
 if r.get('cleanup_errors')or not all(p.deleted and not p.path.parent.exists()for p in profiles):r.update(ok=False,state='failed-cleanup')
 save()
print(json.dumps({k:r.get(k)for k in ['ok','state','error','cleanup_errors','controls','output']}));raise SystemExit(0 if r['ok']else 1)
