#!/usr/bin/env python3
"""Build pinned static PIC HTTP/1.1+HTTP/2 dependencies for the selected SDK."""
import argparse
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import platform
import shutil
import subprocess
import tarfile
import urllib.request
from dependency_contract import RELEASES, CURL_PATCH, patch, validate_cares, validate_http

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,value):Path(p).write_text(json.dumps(value,indent=2)+'\n')
def extract(out,kind,archive):
 record=RELEASES[kind];target=out/(record['name']+'.tar.gz')
 if archive:
  if archive.stat().st_size!=record['bytes'] or sha(archive)!=record['sha256']:raise ValueError('archive identity differs: '+kind)
  shutil.copyfile(archive,target)
 else:
  with urllib.request.urlopen(urllib.request.Request(record['url'],headers={'User-Agent':'NEX-public-dependency-builder'}),timeout=60) as source,target.open('xb') as sink:
   total=0
   while True:
    data=source.read(65536)
    if not data:break
    total+=len(data)
    if total>record['bytes']:raise ValueError('archive exceeds pinned bytes')
    sink.write(data)
 if target.stat().st_size!=record['bytes'] or sha(target)!=record['sha256']:raise ValueError('release identity differs')
 files={};total=0
 with tarfile.open(target,'r:gz') as tar:
  for member in tar:
   path=PurePosixPath(member.name)
   if not path.parts or path.parts[0]!=record['name'] or path.is_absolute() or '..' in path.parts:raise ValueError('unsafe release path')
   destination=out/path
   if member.isdir():destination.mkdir(parents=True,exist_ok=True);continue
   if not member.isfile() or member.mode&0o7000:raise ValueError('unsupported source member')
   relative=str(path.relative_to(record['name']))
   if relative in files or len(files)>=20000:raise ValueError('duplicate/too many release files')
   total+=member.size
   if total>192*1024*1024:raise ValueError('source exceeds192MiB')
   destination.parent.mkdir(parents=True,exist_ok=True)
   with tar.extractfile(member) as source,destination.open('xb') as sink:shutil.copyfileobj(source,sink)
   destination.chmod(0o755 if member.mode&0o111 else 0o644);files[relative]={'sha256':sha(destination),'bytes':destination.stat().st_size}
 manifest=out/(kind+'-upstream-source.json');write(manifest,{'archive':record,'files':files});return out/record['name'],manifest,files
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--sdk',type=Path,required=True);parser.add_argument('--cares-prefix',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--curl-archive',type=Path);parser.add_argument('--nghttp2-archive',type=Path);parser.add_argument('--jobs',type=int,default=4);args=parser.parse_args()
 if not 1<=args.jobs<=8:parser.error('jobs must be1..8')
 out=args.output.absolute()
 if os.path.lexists(out):parser.error('output must be new')
 out.mkdir(parents=True);sdk=args.sdk.resolve(strict=True);cares=args.cares_prefix.resolve(strict=True);env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','NEX_RESOURCE_DIR':str(sdk/'share/nex')};report={'schema':'nex.http-dependencies-build/1','ok':False,'commands':[],'network_used':not(args.curl_archive and args.nghttp2_archive),'PGP_verified':False,'upstream_tests_run':False}
 def save():write(out/'report.json',report)
 def run(label,argv):
  row={'label':label,'argv':list(map(str,argv)),'state':'running'};report['commands'].append(row);save()
  with (out/(label+'.stdout')).open('w') as stdout,(out/(label+'.stderr')).open('w') as stderr:p=subprocess.run(row['argv'],cwd=out,env=env,stdout=stdout,stderr=stderr,timeout=1800)
  row.update(exit_code=p.returncode,state='passed' if p.returncode==0 else 'failed');save()
  if p.returncode:raise RuntimeError(label+' failed; inspect retained logs')
  return (out/(label+'.stdout')).read_text()
 try:
  doctor=json.loads(run('doctor',[sdk/'bin/nex','doctor','--json']));compiler=Path(doctor['native_compiler']);cc=compiler.with_name('clang')
  if not cc.is_file():raise ValueError('selected SDK requires a matching clang C compiler')
  ssl={k:str(Path(doctor[k]).resolve(strict=True)) for k in ['native_openssl_include','native_openssl_ssl','native_openssl_crypto']};ssl_hashes={k:sha(v) for k,v in ssl.items() if k!='native_openssl_include'}
  care=json.loads((cares/'share/cares-source.json').read_text())
  validate_cares(care,platform.system())
  if care['version']!='1.34.9' or not care['static_PIC'] or sha(cares/care['static_library'])!=care['static_library_sha256']:raise ValueError('c-ares static prefix identity differs')
  if platform.system()=='Darwin' and len(care.get('local_source_patches',[]))!=1:raise ValueError('macOS requires the recorded c-ares alignment patch')
  curl,curl_manifest,curl_files=extract(out,'curl',args.curl_archive);ng,ng_manifest,ng_files=extract(out,'nghttp2',args.nghttp2_archive)
  patchfile=Path(__file__).resolve().parent/'patches/curl-no-ambient-keylog-v1.json';patch_document=patch(patchfile,CURL_PATCH);target=curl/patch_document['path']
  if sha(target)!=patch_document['original_sha256']:raise ValueError('curl patch source differs')
  text=target.read_text()
  for old,new in patch_document['replacements']:
   if text.count(old)!=1:raise ValueError('curl source patch does not apply exactly')
   text=text.replace(old,new,1)
  target.write_text(text)
  if sha(target)!=patch_document['patched_sha256']:raise ValueError('curl patched source differs')
  effective=dict(curl_files);effective[patch_document['path']]={'sha256':sha(target),'bytes':target.stat().st_size};write(out/'curl-effective-source.json',{'archive':RELEASES['curl'],'local_patches':[{'sha256':sha(patchfile),'document':patch_document}],'files':effective})
  prefix=out/'prefix';(prefix/'lib').mkdir(parents=True);(prefix/'include').mkdir();(prefix/'share/licenses').mkdir(parents=True)
  shutil.copy2(cares/care['static_library'],prefix/'lib/libcares.a')
  for name,h in care['headers'].items():
   if Path(name).name!=name or sha(cares/'include'/name)!=h:raise ValueError('c-ares headers differ')
   shutil.copy2(cares/'include'/name,prefix/'include'/name)
  common=['-DCMAKE_C_COMPILER='+str(cc),'-DCMAKE_BUILD_TYPE=Release','-DCMAKE_POSITION_INDEPENDENT_CODE=ON','-DCMAKE_INSTALL_PREFIX='+str(prefix),'-DCMAKE_INSTALL_LIBDIR=lib','-DBUILD_SHARED_LIBS=OFF','-DBUILD_STATIC_LIBS=ON','-DBUILD_TESTING=OFF']
  run('nghttp2-configure',['cmake','-S',ng,'-B',out/'nghttp2-build',*common,'-DENABLE_LIB_ONLY=ON','-DENABLE_DOC=OFF','-DENABLE_FAILMALLOC=OFF']);run('nghttp2-build',['cmake','--build',out/'nghttp2-build','-j',str(args.jobs)]);run('nghttp2-install',['cmake','--install',out/'nghttp2-build'])
  flags=['-DBUILD_CURL_EXE=OFF','-DCURL_BUILD_EVERYTHING=OFF','-DENABLE_ARES=ON','-DCARES_INCLUDE_DIR='+str(prefix/'include'),'-DCARES_LIBRARY='+str(prefix/'lib/libcares.a'),'-DCARES_USE_STATIC_LIBS=ON','-DUSE_NGHTTP2=ON','-DNGHTTP2_INCLUDE_DIR='+str(prefix/'include'),'-DNGHTTP2_LIBRARY='+str(prefix/'lib/libnghttp2.a'),'-DNGHTTP2_USE_STATIC_LIBS=ON','-DCURL_USE_OPENSSL=ON','-DOPENSSL_INCLUDE_DIR='+ssl['native_openssl_include'],'-DOPENSSL_SSL_LIBRARY='+ssl['native_openssl_ssl'],'-DOPENSSL_CRYPTO_LIBRARY='+ssl['native_openssl_crypto'],'-DCURL_ZLIB=OFF','-DCURL_BROTLI=OFF','-DCURL_ZSTD=OFF','-DCURL_USE_LIBPSL=OFF','-DUSE_LIBIDN2=OFF','-DCURL_USE_LIBSSH2=OFF','-DCURL_USE_LIBSSH=OFF','-DCURL_USE_GSSAPI=OFF','-DCURL_USE_GSASL=OFF','-DCURL_USE_PKGCONFIG=OFF','-DCURL_USE_CMAKECONFIG=OFF','-DENABLE_UNIX_SOCKETS=OFF','-DCURL_CA_BUNDLE=none','-DCURL_CA_PATH=none','-DCURL_CA_FALLBACK=OFF']
  for protocol in ['DICT','DOH','FILE','FTP','GOPHER','IMAP','LDAP','LDAPS','MQTT','POP3','RTSP','SMB','SMTP','TELNET','TFTP','WEBSOCKETS','NETRC','ALTSVC','HSTS']:flags+=['-DCURL_DISABLE_'+protocol+'=ON']
  run('curl-configure',['cmake','-S',curl,'-B',out/'curl-build',*common,*flags]);run('curl-build',['cmake','--build',out/'curl-build','-j',str(args.jobs)]);run('curl-install',['cmake','--install',out/'curl-build'])
  for kind,source in [('curl',curl/'COPYING'),('nghttp2',ng/'COPYING'),('c-ares',cares/care['license'])]:
   folder=prefix/'share/licenses'/kind;folder.mkdir(exist_ok=True);shutil.copy2(source,folder/'LICENSE.txt')
  for k,h in ssl_hashes.items():
   if sha(ssl[k])!=h:raise ValueError('OpenSSL changed during build')
  record={'schema':'nex.http-dependencies/1','curl':RELEASES['curl'],'nghttp2':RELEASES['nghttp2'],'cares':care,'curl_source_patches':[{'sha256':sha(patchfile),'document':patch_document}],'openssl':ssl,'openssl_library_sha256':ssl_hashes,'source_manifest_sha256':{'curl_upstream':sha(curl_manifest),'curl_effective':sha(out/'curl-effective-source.json'),'nghttp2':sha(ng_manifest)},'static_PIC':True,'libraries':{p.name:sha(p) for p in (prefix/'lib').glob('*.a')},'headers':{p.relative_to(prefix/'include').as_posix():sha(p) for p in (prefix/'include').rglob('*.h')},'licenses':{p.relative_to(prefix).as_posix():sha(p) for p in (prefix/'share/licenses').rglob('*') if p.is_file()},'automatic_decompression':False,'build_configuration':{'C_compiler':str(cc),'CFLAGS':env.get('CFLAGS',''),'LDFLAGS':env.get('LDFLAGS',''),'common_CMake':common,'curl_CMake':flags}};validate_http(record,platform.system());write(prefix/'share/http-source.json',record);report.update(ok=True,prefix=str(prefix),record_sha256=sha(prefix/'share/http-source.json'),compiler_sha256=sha(sdk/'bin/nex'),actual_compiler_toolchain=doctor['version'],language=doctor['language'])
 except BaseException as error:report['error']=repr(error);raise
 finally:save()
 print(json.dumps({k:report.get(k) for k in ['ok','prefix','record_sha256','error']}))
if __name__=='__main__':main()
