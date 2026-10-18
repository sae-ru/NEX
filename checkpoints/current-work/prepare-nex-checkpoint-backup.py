import datetime,hashlib,json,os,pathlib,re,subprocess,tarfile,io
root=pathlib.Path.cwd();stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S')
directory=root/'build'/('github-nex-checkpoint-'+stamp);directory.mkdir();(directory/'objects').mkdir()
env=dict(os.environ,GIT_INDEX_FILE=str(directory/'index'),GIT_OBJECT_DIRECTORY=str(directory/'objects'),GIT_ALTERNATE_OBJECT_DIRECTORIES=str(root/'.git/objects'))
def git(*args):return subprocess.check_output(['git',*args],env=env)
index_hash=hashlib.sha256((root/'.git/index').read_bytes()).hexdigest()
pointer=root/'build/github-bytes-values-current.json'
if not pointer.exists():pointer=root/'build/github-bytes-runtime-current.json'
previous_dir=pathlib.Path(json.loads(pointer.read_text())['directory'])
previous=json.loads((previous_dir/'metadata.json').read_text());previous_verify=json.loads((previous_dir/'verification.json').read_text());assert previous_verify['ok'];assert previous_verify['tree']==previous['expected_tree']
git('read-tree','HEAD');git('add','--all','--','.')
files={}
for entry in git('ls-files','-s','-z').split(b'\0'):
 if entry:
  record,path=entry.split(b'\t',1);mode,sha,stage=record.decode().split();assert stage=='0';files[path.decode()]={'mode':mode,'sha':sha}
patterns=[rb'github_pat_[A-Za-z0-9_]{25,}',rb'gh[pousr]_[A-Za-z0-9]{30,}',rb'AKIA[0-9A-Z]{16}',rb'-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----']
entries=[]
for name,record in files.items():
 data=git('cat-file','blob',record['sha']);assert not any(re.search(p,data) for p in patterns),'credential scan: '+name
 if previous['files_manifest'].get(name)!=record:entries.append({'path':name,'mode':record['mode'],'type':'blob','content':data.decode()})
for name in previous['files_manifest'].keys()-files.keys():entries.append({'path':name,'sha':None,'mode':previous['files_manifest'][name]['mode'],'type':'blob'})
tree=git('write-tree').decode().strip();source=root/'build'/('source-checkpoint-'+stamp+'-'+tree[:8]);assert not source.exists();source.mkdir()
archive=git('archive',tree)
with tarfile.open(fileobj=io.BytesIO(archive)) as t:
 for member in t.getmembers():
  assert member.isdir() or member.isfile();p=pathlib.PurePosixPath(member.name);assert not p.is_absolute() and '..' not in p.parts
 t.extractall(source)
for name,record in files.items():
 p=source/name;data=p.read_bytes();assert hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()==record['sha'];assert ('100755' if p.stat().st_mode&0o111 else '100644')==record['mode']
payload=json.dumps(entries,ensure_ascii=True,separators=(',',':'));(directory/'payload.json').write_text(payload)
toolchain=re.search(r'project\(NEX VERSION ([0-9.]+)',(root/'CMakeLists.txt').read_text()).group(1)
language=re.search(r'languageVersion = "([0-9.]+)"',(root/'include/nex/language.h').read_text()).group(1)
meta={'backup_note':os.environ['NEX_BACKUP_NOTE'],'repository':'sae-ru/NEX','branch':'backup/nex-'+stamp,'parent':previous_verify['commit'],'base_tree':previous['expected_tree'],'expected_tree':tree,'files_manifest':files,'changed_files':len(entries),'payload_length':len(payload),'directory':str(directory),'source_directory':str(source),'normal_index_sha256':index_hash,'source_language':language,'toolchain':toolchain,'credential_scan':'clear','accepted_release':False,'full_objective_complete':False}
(directory/'metadata.json').write_text(json.dumps(meta,indent=2)+'\n');(root/'build/github-bytes-values-current.json').write_text(json.dumps({'directory':str(directory)})+'\n');assert hashlib.sha256((root/'.git/index').read_bytes()).hexdigest()==index_hash
print(json.dumps({k:v for k,v in meta.items() if k!='files_manifest'}))
