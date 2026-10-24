#include "nex_ffi_loader.h"
#include "nex_ffi_module.h"
#include "nex_ffi_resources.h"
#include "nex_json.h"
#include "third_party/json.hpp"
#include <openssl/evp.h>
#include <array>
#include <cerrno>
#include <chrono>
#include <condition_variable>
#include <cstring>
#include <filesystem>
#include <thread>
#include <fcntl.h>
#include <dlfcn.h>
#include <sys/stat.h>
#include <unistd.h>

namespace nexrt {
namespace {
namespace fs=std::filesystem;
using J=nlohmann::ordered_json;
using Poll=std::function<void()>;
[[noreturn]] void fail(const char *code,const char *message){throw DataError(code,message);}
void pollNow(const Poll &poll){if(poll)poll();}
struct FD {
  int fd=-1;
  explicit FD(int fd=-1):fd(fd){}
  FD(const FD&)=delete;FD &operator=(const FD&)=delete;
  FD(FD &&other)noexcept:fd(std::exchange(other.fd,-1)){}
  FD &operator=(FD &&other)noexcept{if(this!=&other){if(fd>=0)::close(fd);fd=std::exchange(other.fd,-1);}return *this;}
  ~FD(){if(fd>=0)::close(fd);}
};
struct Digest {
  std::unique_ptr<EVP_MD_CTX,decltype(&EVP_MD_CTX_free)> context{EVP_MD_CTX_new(),EVP_MD_CTX_free};
  Digest(){if(!context||EVP_DigestInit_ex2(context.get(),EVP_sha256(),nullptr)!=1)fail("E_FFI_HASH","SHA-256 initialization failed");}
  void add(const void *data,size_t size){if(EVP_DigestUpdate(context.get(),data,size)!=1)fail("E_FFI_HASH","SHA-256 update failed");}
  std::string finish(){std::array<unsigned char,EVP_MAX_MD_SIZE> bytes{};unsigned n=0;
    if(EVP_DigestFinal_ex(context.get(),bytes.data(),&n)!=1||n!=32)fail("E_FFI_HASH","SHA-256 finalization failed");
    constexpr char hex[]="0123456789abcdef";std::string result;result.reserve(64);for(unsigned i=0;i<n;++i){result+=hex[bytes[i]>>4];result+=hex[bytes[i]&15];}return result;
  }
};
std::string digest(std::string_view text){Digest d;d.add(text.data(),text.size());return d.finish();}
bool hash(const std::string &value){return value.size()==64&&std::all_of(value.begin(),value.end(),[](char c){return(c>='0'&&c<='9')||(c>='a'&&c<='f');});}
bool identifier(const std::string &value){auto letter=[](char c){return(c>='a'&&c<='z')||(c>='A'&&c<='Z')||c=='_';};
  return !value.empty()&&value.size()<=128&&letter(value.front())&&std::all_of(value.begin(),value.end(),[&](char c){return letter(c)||(c>='0'&&c<='9');});
}
void keys(const J &value,std::initializer_list<const char*> names){if(!value.is_object()||value.size()!=names.size())fail("E_FFI_MANIFEST","foreign bundle fields differ");for(auto name:names)if(!value.contains(name))fail("E_FFI_MANIFEST","missing foreign bundle field");}
std::string string(const J &value){if(!value.is_string())fail("E_FFI_MANIFEST","foreign bundle field must be text");return value.get<std::string>();}
std::vector<std::string> pathParts(const std::string &path){
  if(path.empty()||path.size()>4096||path.front()=='/'||path.back()=='/'||path.find_first_of(std::string("\\:\0",3))!=std::string::npos)fail("E_FFI_MANIFEST","invalid bundle relative path");
  try{unicodeOffsets(path,false);}catch(const DataError&){fail("E_FFI_MANIFEST","bundle path is not UTF-8");}
  std::vector<std::string> result;size_t begin=0;
  while(begin<path.size()){auto end=path.find('/',begin);if(end==std::string::npos)end=path.size();auto part=path.substr(begin,end-begin);
    if(part.empty()||part=="."||part==".."||part.size()>255||result.size()>=128)fail("E_FFI_MANIFEST","invalid bundle path component");result.push_back(std::move(part));begin=end+1;
  }return result;
}
FD parent(int root,const std::vector<std::string> &parts,const Poll &poll){FD dir(::fcntl(root,F_DUPFD_CLOEXEC,0));if(dir.fd<0)fail("E_FFI_IO","cannot duplicate bundle directory");
  for(size_t i=0;i+1<parts.size();++i){pollNow(poll);FD next(::openat(dir.fd,parts[i].c_str(),O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC));if(next.fd<0)fail("E_FFI_IO","bundle parent is unavailable or a symbolic link");dir=std::move(next);}return dir;
}
FD openFile(int root,const std::string &path,const Poll &poll){auto parts=pathParts(path);auto dir=parent(root,parts,poll);FD file(::openat(dir.fd,parts.back().c_str(),O_RDONLY|O_NOFOLLOW|O_NONBLOCK|O_CLOEXEC));
  if(file.fd<0)fail("E_FFI_IO","bundle file is unavailable or a symbolic link");struct stat st{};
  if(::fstat(file.fd,&st)||!S_ISREG(st.st_mode))fail("E_FFI_IO","bundle member must be a regular file");return file;
}
template<class Consume> size_t readFile(int fd,size_t limit,const Poll &poll,Consume consume){
  struct stat st{};if(::fstat(fd,&st)||st.st_size<0||uint64_t(st.st_size)>limit)fail("E_FFI_LIMIT","bundle member exceeds byte limit");
  std::array<char,65536> buffer{};size_t total=0;
  for(;;){pollNow(poll);auto n=::read(fd,buffer.data(),buffer.size());if(n<0){if(errno==EINTR)continue;fail("E_FFI_IO","bundle read failed");}if(!n)break;
    if(size_t(n)>limit-total)fail("E_FFI_LIMIT","bundle member exceeds byte limit");consume(buffer.data(),size_t(n));total+=size_t(n);
  }return total;
}
struct Manifest {FD root;std::string pin,entry,text;std::map<std::string,std::string> files,exports;};
std::shared_ptr<Manifest> readManifest(const ForeignLibraryGrant &grant,const Poll &poll){
  auto result=std::make_shared<Manifest>();result->pin=grant.manifestSha256;pollNow(poll);
  result->root=FD(::open(grant.directory.c_str(),O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC));if(result->root.fd<0)fail("E_FFI_IO","configured bundle directory is unavailable");
  auto file=openFile(result->root.fd,"manifest.json",poll);std::string text;
  readFile(file.fd,1048576,poll,[&](const char *data,size_t size){text.append(data,size);});
  if(digest(text)!=result->pin)fail("E_FFI_HASH","foreign bundle manifest hash differs");
  try{
    validateJSONText(text);auto doc=J::parse(text);keys(doc,{"schema","platform","entry","files","exports","notices"});
    if(doc.at("schema")!="nex.foreign-bundle/1")fail("E_FFI_MANIFEST","unsupported foreign bundle schema");
    if(string(doc.at("platform"))!=foreignPlatform())fail("E_FFI_PLATFORM","foreign bundle platform differs from the host");
    result->entry=string(doc.at("entry"));pathParts(result->entry);
    const auto &files=doc.at("files");if(!files.is_array()||files.empty()||files.size()>128)fail("E_FFI_MANIFEST","foreign bundle file count must be 1..128");
    for(const auto &member:files){keys(member,{"path","sha256"});auto path=string(member.at("path")),sha=string(member.at("sha256"));pathParts(path);
      if(path=="manifest.json"||!hash(sha)||!result->files.emplace(path,sha).second)fail("E_FFI_MANIFEST","duplicate file or invalid bundle hash");}
    for(const auto &[path,sha]:result->files){(void)sha;auto parts=pathParts(path);std::string prefix;for(size_t i=0;i+1<parts.size();++i){if(i)prefix+='/';prefix+=parts[i];if(result->files.contains(prefix))fail("E_FFI_MANIFEST","bundle file is also a parent directory");}}
    if(!result->files.contains(result->entry))fail("E_FFI_MANIFEST","bundle entry is missing from inventory");
    const auto &exports=doc.at("exports");if(!exports.is_object()||exports.empty()||exports.size()>1024)fail("E_FFI_MANIFEST","foreign bundle exports must contain 1..1024 items");
    for(auto item=exports.begin();item!=exports.end();++item){auto sha=string(item.value());if(!identifier(item.key())||!hash(sha))fail("E_FFI_MANIFEST","invalid foreign export name or signature hash");result->exports.emplace(item.key(),sha);}
    const auto &notices=doc.at("notices");if(!notices.is_array()||notices.empty()||notices.size()>128)fail("E_FFI_MANIFEST","foreign bundle requires notices");std::set<std::string> unique;
    for(const auto &notice:notices){auto path=string(notice);if(!result->files.contains(path)||!unique.insert(path).second)fail("E_FFI_MANIFEST","invalid or duplicate bundle notice");}
  }catch(const J::exception&){fail("E_FFI_MANIFEST","invalid foreign bundle JSON");}
  catch(const DataError &e){if(e.code=="E_JSON"||e.code=="E_UTF8"||e.code=="E_LIMIT")fail("E_FFI_MANIFEST","invalid foreign bundle JSON");throw;}
  result->text=std::move(text);pollNow(poll);return result;
}
struct Image {
  fs::path directory;void *handle=nullptr;
  std::shared_ptr<foreign_detail::ResourceRegistry> resourceTypes=std::make_shared<foreign_detail::ResourceRegistry>();
  std::map<std::string,nex_ffi_export_v1> exports;
  ~Image(){if(handle)::dlclose(handle);if(!directory.empty()){std::error_code e;fs::permissions(directory,fs::perms::owner_all,fs::perm_options::add,e);
    for(fs::recursive_directory_iterator it(directory,e),end;!e&&it!=end;it.increment(e))if(it->is_directory(e))fs::permissions(it->path(),fs::perms::owner_all,fs::perm_options::add,e);
    e.clear();fs::remove_all(directory,e);}}
};
bool ownedAddress(const void *address,const Image &image,const Manifest &manifest){Dl_info info{};if(!address||!::dladdr(address,&info)||!info.dli_fname)return false;
  std::error_code ec;auto file=fs::canonical(info.dli_fname,ec);if(ec)return false;
  for(const auto &[name,sha]:manifest.files){(void)sha;if(file==image.directory/name)return true;}return false;
}
bool entryAddress(const void *address,const Image &image,const Manifest &manifest){Dl_info info{};std::error_code ec;return address&&::dladdr(address,&info)&&info.dli_fname&&fs::canonical(info.dli_fname,ec)==image.directory/manifest.entry&&!ec;}
std::string bounded(const char *text,size_t maximum){if(!text)fail("E_FFI_ABI","null module metadata string");auto length=::strnlen(text,maximum+1);if(length>maximum)fail("E_FFI_ABI","module metadata string exceeds limit");return {text,length};}
std::shared_ptr<Image> loadImage(const Manifest &manifest,const Poll &poll){
  auto image=std::make_shared<Image>();auto pattern=(fs::temp_directory_path()/"nex-module-XXXXXX").string();
  pollNow(poll);if(!::mkdtemp(pattern.data()))fail("E_FFI_IO","cannot reserve a private module directory");image->directory=fs::canonical(pattern);
  size_t total=0;std::vector<fs::path> directories;
  for(const auto &[name,sha]:manifest.files){pollNow(poll);auto source=openFile(manifest.root.fd,name,poll);auto destination=image->directory/name;
    std::error_code ec;fs::create_directories(destination.parent_path(),ec);if(ec)fail("E_FFI_IO","cannot create module snapshot directories");
    FD output(::open(destination.c_str(),O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600));if(output.fd<0)fail("E_FFI_IO","cannot create module snapshot member");Digest d;
    auto size=readFile(source.fd,std::min<size_t>(64*1048576,256*1048576-total),poll,[&](const char *data,size_t size){
      d.add(data,size);for(size_t offset=0;offset<size;){pollNow(poll);auto n=::write(output.fd,data+offset,size-offset);if(n<0){if(errno==EINTR)continue;fail("E_FFI_IO","module snapshot write failed");}if(!n)fail("E_FFI_IO","module snapshot write made no progress");offset+=size_t(n);}
    });total+=size;if(d.finish()!=sha)fail("E_FFI_HASH","foreign bundle member hash differs");
    if(::fchmod(output.fd,0400))fail("E_FFI_IO","cannot seal module snapshot member");
  }
  std::error_code ec;for(fs::recursive_directory_iterator it(image->directory,ec),end;!ec&&it!=end;it.increment(ec))if(it->is_directory())directories.push_back(it->path());
  if(ec)fail("E_FFI_IO","cannot inspect module snapshot directories");std::sort(directories.rbegin(),directories.rend());
  for(const auto &dir:directories)if(::chmod(dir.c_str(),0500))fail("E_FFI_IO","cannot seal module snapshot directory");if(::chmod(image->directory.c_str(),0500))fail("E_FFI_IO","cannot seal module snapshot root");
  pollNow(poll);image->handle=::dlopen((image->directory/manifest.entry).c_str(),RTLD_NOW|RTLD_LOCAL);if(!image->handle)fail("E_FFI_LOAD","native module load failed");
  pollNow(poll);::dlerror();auto address=::dlsym(image->handle,"nex_ffi_module_entry");const char *failure=::dlerror();
  if(failure||!entryAddress(address,*image,manifest))fail("E_FFI_ABI","native module entry is absent or outside its entry image");
  auto entry=reinterpret_cast<nex_ffi_module_entry_fn>(address);const nex_ffi_module_v1 *table=nullptr;
  try{table=entry(NEX_FFI_ABI_V1,sizeof(nex_ffi_api_v1));}catch(...){fail("E_FFI_EXCEPTION","native module entry threw an exception");}pollNow(poll);
  if(!table||table->abi_version!=NEX_FFI_MODULE_ABI_V1||table->struct_size<sizeof(nex_ffi_module_v1)||table->export_count!=manifest.exports.size()||table->export_stride<sizeof(nex_ffi_export_v1)||table->export_stride>4096||table->export_stride%alignof(nex_ffi_export_v1)||!table->exports)fail("E_FFI_ABI","native module descriptor differs");
  for(uint64_t i=0;i<table->export_count;++i){pollNow(poll);auto &item=*reinterpret_cast<const nex_ffi_export_v1*>(reinterpret_cast<const char*>(table->exports)+i*table->export_stride);
    if(item.struct_size<sizeof(nex_ffi_export_v1)||item.struct_size>table->export_stride||item.reserved||!item.callback||!ownedAddress(reinterpret_cast<const void*>(item.callback),*image,manifest))fail("E_FFI_ABI","invalid module export descriptor");
    auto name=bounded(item.name,128),sha=bounded(item.signature_sha256,64);auto expected=manifest.exports.find(name);
    if(!identifier(name)||!hash(sha)||expected==manifest.exports.end()||expected->second!=sha||!image->exports.emplace(name,item).second)fail("E_FFI_ABI","native export name or signature differs from manifest");
  }pollNow(poll);return image;
}
struct ImageSlot {std::mutex mutex;std::condition_variable changed;bool loading=false;std::thread::id thread;std::weak_ptr<Image> value;};
std::shared_ptr<Image> imageFor(const Manifest &manifest,const Poll &poll){
  static std::mutex mutex;static std::map<std::string,std::shared_ptr<ImageSlot>> slots;
  std::shared_ptr<ImageSlot> slot;
  {std::lock_guard guard(mutex);std::erase_if(slots,[](const auto &item){std::lock_guard inner(item.second->mutex);return item.second.use_count()==1&&!item.second->loading&&item.second->value.expired();});auto &item=slots[manifest.pin];if(!item)item=std::make_shared<ImageSlot>();slot=item;}
  std::shared_ptr<Image> found;
  for(;;){pollNow(poll);std::unique_lock guard(slot->mutex);found=slot->value.lock();if(found){guard.unlock();pollNow(poll);return found;}
    if(!slot->loading){slot->loading=true;slot->thread=std::this_thread::get_id();break;}
    if(slot->thread==std::this_thread::get_id())fail("E_FFI_REENTRANT","recursive load of the same native module");slot->changed.wait_for(guard,std::chrono::milliseconds(10));
  }
  try{auto value=loadImage(manifest,poll);{std::lock_guard guard(slot->mutex);slot->value=value;slot->loading=false;}slot->changed.notify_all();return value;}
  catch(...){ {std::lock_guard guard(slot->mutex);slot->loading=false;}slot->changed.notify_all();throw;}
}
struct Module {std::shared_ptr<Image> image;};
struct AuthSlot {ResourceAccess access;std::mutex mutex;std::condition_variable changed;bool loading=false;std::thread::id thread;ResourceOwner<Module> owner;explicit AuthSlot(ResourceAccess access):access(std::move(access)){};};
ResourceOwner<Module> authorize(const std::shared_ptr<AuthSlot> &slot,const Manifest &manifest,const Poll &poll){
  ResourceOwner<Module> found;
  for(;;){pollNow(poll);std::unique_lock guard(slot->mutex);found=slot->owner;if(found.isOpen()){guard.unlock();pollNow(poll);return found;}
    if(!slot->loading){slot->loading=true;slot->thread=std::this_thread::get_id();break;}
    if(slot->thread==std::this_thread::get_id())fail("E_FFI_REENTRANT","recursive authorization of the same module");slot->changed.wait_for(guard,std::chrono::milliseconds(10));
  }
  try{auto owner=slot->access.make<Module>([&](const ResourcePermit &permit){permit.check();auto image=imageFor(manifest,poll);permit.check();return std::make_unique<Module>(Module{std::move(image)});});
    {std::lock_guard guard(slot->mutex);slot->owner=owner;slot->loading=false;}slot->changed.notify_all();pollNow(poll);return owner;
  }catch(...){ {std::lock_guard guard(slot->mutex);slot->loading=false;}slot->changed.notify_all();throw;}
}
}
std::string foreignPlatform(){
#if defined(__APPLE__)
  const char *os="macos";
#elif defined(__linux__)
  const char *os="linux";
#else
  fail("E_FFI_PLATFORM","native modules are unsupported on this host OS");
#endif
#if defined(__aarch64__) || defined(__arm64__)
  return std::string(os)+"-arm64";
#elif defined(__x86_64__)
  return std::string(os)+"-x86_64";
#else
  fail("E_FFI_PLATFORM","native modules are unsupported on this host architecture");
#endif
}
std::string foreignSignatureDigest(const ForeignSignature &signature){return digest(signature.canonical());}
ForeignBundleSnapshot inspectForeignBundle(const ForeignLibraryGrant &grant,size_t maximumBytes,Poll poll){
  if(!maximumBytes||maximumBytes>257*1048576)fail("E_FFI_LIMIT","invalid bundle capture byte limit");
  auto manifest=readManifest(grant,poll);
  ForeignBundleSnapshot result;result.manifest=manifest->text;result.entry=manifest->entry;result.exports=manifest->exports;
  if(result.manifest.size()>maximumBytes)fail("E_FFI_LIMIT","bundle capture exceeds byte limit");
  size_t total=result.manifest.size(),members=0;
  for(const auto &[name,sha]:manifest->files){
    auto file=openFile(manifest->root.fd,name,poll);std::string bytes;Digest d;
    auto limit=std::min({size_t(64*1048576),size_t(256*1048576)-members,maximumBytes-total});
    auto size=readFile(file.fd,limit,poll,[&](const char *data,size_t size){d.add(data,size);bytes.append(data,size);});
    if(d.finish()!=sha)fail("E_FFI_HASH","foreign bundle member hash differs");
    total+=size;members+=size;result.files.emplace(name,std::move(bytes));
  }
  for(const auto &name:grant.exports)if(!result.exports.contains(name))fail("E_FFI_SIGNATURE","granted export is absent from pinned bundle");
  result.files.emplace("manifest.json",result.manifest);pollNow(poll);return result;
}
struct ForeignFunction::Impl {ResourceOwner<Module> owner;ForeignSignature signature;nex_ffi_callback_v1 callback;void *user;std::shared_ptr<ResourceDomain> values;ResourceByteBudget bytes;std::shared_ptr<Manifest> manifest;};
struct ForeignLibraries::Impl {
  const std::map<std::string,ForeignLibraryGrant> grants;const size_t limit,valueLimit;ResourceDomain resources;std::shared_ptr<ResourceDomain> values;ResourceByteBudget bytes;std::mutex mutex;
  std::map<std::string,std::shared_ptr<Manifest>> manifests;
  std::map<std::pair<const void*,std::string>,std::shared_ptr<AuthSlot>> slots;
  Impl(std::map<std::string,ForeignLibraryGrant> grants,size_t limit,size_t valueLimit,uint64_t bytes):grants(std::move(grants)),limit(limit),valueLimit(valueLimit),resources(limit),values(std::make_shared<ResourceDomain>(valueLimit)),bytes(bytes){}
};
ForeignLibraries::ForeignLibraries(std::map<std::string,ForeignLibraryGrant> grants,size_t limit,size_t valueLimit,uint64_t bytes){
  if(grants.size()>128)fail("E_FFI_LIMIT","host library catalogue exceeds 128 grants");
  for(const auto &[name,grant]:grants){if(!identifier(name)||grant.directory.empty()||grant.directory.find('\0')!=std::string::npos||!hash(grant.manifestSha256)||grant.exports.empty()||grant.exports.size()>1024)fail("E_FFI_GRANT","invalid host library grant");for(const auto &name:grant.exports)if(!identifier(name))fail("E_FFI_GRANT","invalid host export grant");}
  if(!valueLimit||valueLimit>4096||!bytes||bytes>uint64_t(1024)*1024*1024)fail("E_FFI_LIMIT","invalid foreign resource capacity limits");
  impl=std::make_shared<Impl>(std::move(grants),limit,valueLimit,bytes);
}
ForeignLibraries::~ForeignLibraries(){revoke();}
void ForeignLibraries::revoke()noexcept{auto retained=impl;if(retained){retained->values->revoke();retained->resources.revoke();}}
std::vector<std::string> ForeignLibraries::grantedDirectories()const{auto retained=impl;std::vector<std::string> result;for(const auto &[name,grant]:retained->grants){(void)name;result.push_back(grant.directory);}return result;}
std::map<std::string,ForeignLibraryGrant> ForeignLibraries::operatorGrants()const{return impl->grants;}
size_t ForeignLibraries::moduleLimit()const noexcept{return impl->limit;}
size_t ForeignLibraries::resourceLimit()const noexcept{return impl->valueLimit;}
uint64_t ForeignLibraries::resourceBytesLimit()const noexcept{return impl->bytes.limit();}
uint64_t ForeignLibraries::resourceBytesUsed()const noexcept{return impl->bytes.used();}
ForeignFunction ForeignLibraries::bind(const std::string &library,const std::string &name,const ForeignSignature &signature,const std::string &expectedManifestSha256,Poll poll)const{
  auto retained=impl;auto *domain=&retained->resources;
  if(auto binder=resource_detail::requestBinder)if(auto joined=binder(*domain))domain=joined;
  return bindWithResourceScope(library,name,signature,expectedManifestSha256,domain->access(),std::move(poll));
}
ForeignFunction ForeignLibraries::bindWithResourceScope(const std::string &library,const std::string &name,const ForeignSignature &signature,const std::string &expectedManifestSha256,ResourceAccess scope,Poll poll)const{
  auto retained=impl;auto libraryName=library,exportName=name,expectedPin=expectedManifestSha256;auto contract=signature;
  const auto &grant=retained->grants;auto it=grant.find(libraryName);
  if(it==grant.end()||!it->second.exports.contains(exportName))fail("E_FFI_GRANT","host has not authorized this library/export");
  if(expectedPin!=it->second.manifestSha256)fail("E_FFI_HASH","requested bundle pin differs from host grant");
  auto access=scope.combine(retained->resources.access());
  auto checked=[access,poll=std::move(poll)]{access.check();pollNow(poll);access.check();};checked();
  std::shared_ptr<Manifest> manifest;{std::lock_guard guard(retained->mutex);auto cached=retained->manifests.find(libraryName);if(cached!=retained->manifests.end())manifest=cached->second;}
  if(!manifest){auto read=readManifest(it->second,checked);std::lock_guard guard(retained->mutex);manifest=retained->manifests.try_emplace(libraryName,std::move(read)).first->second;}
  auto exported=manifest->exports.find(exportName);if(exported==manifest->exports.end()||exported->second!=foreignSignatureDigest(contract))fail("E_FFI_SIGNATURE","requested signature differs from pinned export");
  std::shared_ptr<AuthSlot> slot;std::vector<std::shared_ptr<AuthSlot>> retired;
  {std::lock_guard guard(retained->mutex);for(auto pos=retained->slots.begin();pos!=retained->slots.end();){auto candidate=pos->second;std::lock_guard inner(candidate->mutex);
      bool expired=false;try{candidate->access.check();}catch(const DataError &){expired=true;}
      if(!candidate->loading&&(expired||(candidate->owner.identity()&&!candidate->owner.isOpen()))){retired.push_back(std::move(candidate));pos=retained->slots.erase(pos);}else ++pos;}
    auto &item=retained->slots[{access.scopeKey(),libraryName}];if(!item)item=std::make_shared<AuthSlot>(access);slot=item;}
  retired.clear();auto owner=authorize(slot,*manifest,checked);auto lease=owner.acquire();const auto &item=lease.value().image->exports.at(exportName);checked();
  return ForeignFunction(std::make_shared<ForeignFunction::Impl>(ForeignFunction::Impl{owner,std::move(contract),item.callback,item.user,retained->values,retained->bytes,manifest}));
}
bool ForeignFunction::isOpen()const noexcept{auto retained=impl;return retained&&retained->owner.isOpen();}
const ForeignSignature &ForeignFunction::signature()const{if(!impl)fail("E_RESOURCE_CLOSED","foreign function is unavailable");return impl->signature;}
Value ForeignFunction::invoke(std::span<const Value> arguments,Poll poll,ForeignCallLimits limits)const{
  return invokeWithResourceScope(arguments,{},std::move(poll),limits);
}
Value ForeignFunction::invokeWithResourceScope(std::span<const Value> arguments,ResourceAccess scope,Poll poll,ForeignCallLimits limits)const{
  auto retained=impl;if(!retained)fail("E_RESOURCE_CLOSED","foreign function is unavailable");auto lease=retained->owner.acquire();
  auto checked=[lease,poll=std::move(poll)]{lease.check();pollNow(poll);lease.check();};
  if(!retained->signature.hasResources())return invokeForeignTyped(retained->callback,arguments,retained->signature,retained->user,std::move(checked),limits);
  auto *domain=retained->values.get();if(auto binder=resource_detail::requestBinder)if(auto joined=binder(*domain))domain=joined;
  auto access=domain->access();if(scope.scopeKey())access=access.combine(scope);
  auto image=lease.value().image;auto manifest=retained->manifest;
  auto pin=std::make_shared<ResourceLease<Module>>(lease);
  auto resources=std::make_shared<foreign_detail::ResourceContext>(image->resourceTypes,access,retained->bytes,pin,
      [image,manifest](const void *address){return ownedAddress(address,*image,*manifest);});
  auto valuePoll=[checked=std::move(checked),access]{access.check();checked();access.check();};
  return foreign_detail::invokeForeignTypedResources(retained->callback,arguments,retained->signature,retained->user,std::move(valuePoll),limits,std::move(resources));
}
}
