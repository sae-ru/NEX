#include "nex_foreign.h"
#include "nex_json.h"
#include "third_party/json.hpp"
#include <atomic>
#include <array>
#include <cerrno>
#include <filesystem>
#include <thread>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>
#if defined(NEX_FOREIGN_DEFAULT) && defined(__APPLE__)
#include <mach-o/dyld.h>
#endif
namespace nexrt {
std::string packagedForeignCatalogue(){
#ifdef NEX_FOREIGN_DEFAULT
  std::string executable;
#if defined(__APPLE__)
  uint32_t size=0;_NSGetExecutablePath(nullptr,&size);
  if(!size||size>1048576)throw DataError("E_FFI_IO","cannot locate packaged executable");
  std::vector<char> path(size);if(_NSGetExecutablePath(path.data(),&size))throw DataError("E_FFI_IO","cannot locate packaged executable");executable=path.data();
#elif defined(__linux__)
  std::vector<char> path(1048576);auto size=::readlink("/proc/self/exe",path.data(),path.size());
  if(size<=0||size_t(size)>=path.size())throw DataError("E_FFI_IO","cannot locate packaged executable");executable.assign(path.data(),size_t(size));
#else
  throw DataError("E_FFI_PLATFORM","packaged catalogue location is unsupported on this platform");
#endif
  std::error_code error;auto actual=std::filesystem::canonical(executable,error);
  if(error)throw DataError("E_FFI_IO","cannot resolve packaged executable");
  return (actual.parent_path()/NEX_FOREIGN_DEFAULT).lexically_normal().string();
#else
  return {};
#endif
}
namespace {
using J=nlohmann::ordered_json;
[[noreturn]] void invalid(const char *code,const char *message){throw DataError(code,message);}
bool hash(const std::string &v){return v.size()==64&&v.find_first_not_of("0123456789abcdef")==std::string::npos;}
bool identifier(const std::string &v){auto letter=[](char c){return(c>='a'&&c<='z')||(c>='A'&&c<='Z')||c=='_';};return !v.empty()&&v.size()<=128&&letter(v.front())&&std::all_of(v.begin(),v.end(),[&](char c){return letter(c)||(c>='0'&&c<='9');});}
void keys(const J &value,std::initializer_list<const char*> names,const char *code){if(!value.is_object()||value.size()!=names.size())invalid(code,"foreign object fields differ");for(auto name:names)if(!value.contains(name))invalid(code,"missing foreign object field");}
std::string string(const J &value,const char *code){if(!value.is_string())invalid(code,"foreign field must be text");return value.get<std::string>();}
uint64_t integer(const J &value,const char *code){if(!value.is_number_integer()||(!value.is_number_unsigned()&&value.get<int64_t>()<0))invalid(code,"foreign limit must be an unsigned integer");return value.get<uint64_t>();}
J parse(const std::string &text,const char *code){try{validateJSONText(text);return J::parse(text);}catch(const DataError&){invalid(code,"invalid or excessive foreign JSON");}catch(const J::exception&){invalid(code,"invalid foreign JSON");}}
struct Binding {
  std::string library,name,pin;ForeignSignature signature;
  Binding(std::string library,std::string name,std::string pin,ForeignSignature signature)
      :library(std::move(library)),name(std::move(name)),pin(std::move(pin)),signature(std::move(signature)){}
};
std::shared_ptr<Binding> binding(const std::string &text){
  auto v=parse(text,"E_FFI_BINDING");keys(v,{"schema","library","export","manifest_sha256","signature"},"E_FFI_BINDING");
  if(v.at("schema")!="nex.foreign-binding/1")invalid("E_FFI_BINDING","unsupported foreign binding schema");
  auto library=string(v.at("library"),"E_FFI_BINDING"),name=string(v.at("export"),"E_FFI_BINDING"),pin=string(v.at("manifest_sha256"),"E_FFI_BINDING");
  if(!identifier(library)||!identifier(name)||!hash(pin))invalid("E_FFI_BINDING","invalid foreign binding identity or pin");
  return std::make_shared<Binding>(std::move(library),std::move(name),std::move(pin),ForeignSignature(v.at("signature").dump()));
}
struct State {
  std::atomic<bool> active{true};const std::thread::id thread=std::this_thread::get_id();
  const std::shared_ptr<ForeignLibraries> libraries;const ForeignScopeLimits limits;
  ResourceDomain modules;
  ResourceDomain resources;
  std::mutex metadataMutex;
  uint64_t metadata=0;std::map<std::string,std::shared_ptr<Binding>> bindings;
  State(std::shared_ptr<ForeignLibraries> libraries,ForeignScopeLimits limits):libraries(std::move(libraries)),limits(limits),modules(this->libraries->moduleLimit()),resources(this->libraries->resourceLimit()){}
  void check()const{if(!active.load())invalid("E_FFI_SCOPE","foreign scope has ended");if(thread!=std::this_thread::get_id())invalid("E_FFI_THREAD","foreign context belongs to another thread");}
};
thread_local std::vector<std::weak_ptr<State>> contexts;
std::shared_ptr<State> current(){
  while(!contexts.empty()){auto state=contexts.back().lock();if(state&&state->active.load()){state->check();return state;}contexts.pop_back();}
  invalid("E_FFI_GRANT","foreign calls require an explicit host scope");
}
std::shared_ptr<Binding> resolve(const std::shared_ptr<State> &state,const std::string &text){
  if(text.size()>1048576)invalid("E_FFI_LIMIT","foreign binding exceeds 1 MiB");
  std::lock_guard lock(state->metadataMutex);
  if(auto found=state->bindings.find(text);found!=state->bindings.end())return found->second;
  if(state->bindings.size()>=state->limits.bindings||text.size()>state->limits.metadataBytes-state->metadata)
    invalid("E_FFI_LIMIT","foreign binding cache budget exceeded");
  auto selected=binding(text);state->bindings.emplace(text,selected);state->metadata+=text.size();return selected;
}
}
std::shared_ptr<ForeignLibraries> loadForeignLibraries(const std::string &configuration){
  if(configuration.empty()||configuration.size()>4096||configuration.find('\0')!=std::string::npos)invalid("E_FFI_GRANT","invalid foreign host configuration path");
  try{unicodeOffsets(configuration,false);}catch(const DataError&){invalid("E_FFI_GRANT","foreign host configuration path must be UTF-8");}
  std::error_code ec;auto absolute=std::filesystem::absolute(configuration,ec);if(ec)invalid("E_FFI_IO","cannot resolve foreign host configuration path");
  auto parent=std::filesystem::canonical(absolute.parent_path(),ec);if(ec)invalid("E_FFI_IO","foreign host configuration parent is unavailable");absolute=parent/absolute.filename();
  // Opening a caller-selected configuration does not execute any native code.
  struct File {int fd;~File(){if(fd>=0)::close(fd);}} file{::open(absolute.c_str(),O_RDONLY|O_NOFOLLOW|O_NONBLOCK|O_CLOEXEC)};
  if(file.fd<0)invalid("E_FFI_IO","foreign host configuration is unavailable");struct stat info{};
  if(::fstat(file.fd,&info)||!S_ISREG(info.st_mode))invalid("E_FFI_IO","foreign host configuration must be a regular file");
  if(info.st_size<0||uint64_t(info.st_size)>1048576)invalid("E_FFI_LIMIT","foreign host configuration exceeds 1 MiB");
  std::string text;std::array<char,65536> chunk{};
  for(;;){auto n=::read(file.fd,chunk.data(),chunk.size());if(n<0){if(errno==EINTR)continue;invalid("E_FFI_IO","cannot read foreign host configuration");}if(!n)break;if(uint64_t(n)>1048576-text.size())invalid("E_FFI_LIMIT","foreign host configuration exceeds 1 MiB");text.append(chunk.data(),size_t(n));}
  auto doc=parse(text,"E_FFI_GRANT");
  if(!doc.is_object()||!doc.contains("schema")||!doc.contains("libraries")||!doc.contains("module_limit"))invalid("E_FFI_GRANT","missing foreign host field");
  for(auto it=doc.begin();it!=doc.end();++it)if(it.key()!="schema"&&it.key()!="libraries"&&it.key()!="module_limit"&&it.key()!="resource_limit"&&it.key()!="resource_bytes")invalid("E_FFI_GRANT","unknown foreign host field");
  if(doc.at("schema")!="nex.foreign-host/1")invalid("E_FFI_GRANT","unsupported foreign host configuration");auto limit=integer(doc.at("module_limit"),"E_FFI_GRANT");
  if(!limit||limit>4096)invalid("E_FFI_GRANT","foreign module limit must be 1..4096");const auto &libraries=doc.at("libraries");
  if(!libraries.is_object()||libraries.size()>128)invalid("E_FFI_GRANT","foreign host catalogue exceeds 128 libraries");
  std::map<std::string,ForeignLibraryGrant> grants;
  for(auto item=libraries.begin();item!=libraries.end();++item){const auto &v=item.value();keys(v,{"directory","manifest_sha256","exports"},"E_FFI_GRANT");
    auto directory=string(v.at("directory"),"E_FFI_GRANT"),pin=string(v.at("manifest_sha256"),"E_FFI_GRANT");
    if(!identifier(item.key())||directory.empty()||directory.size()>4096||directory.find('\0')!=std::string::npos||!hash(pin))invalid("E_FFI_GRANT","invalid library grant");
    try{unicodeOffsets(directory,false);}catch(const DataError&){invalid("E_FFI_GRANT","foreign grant directory must be UTF-8");}
    const auto &exports=v.at("exports");if(!exports.is_array()||exports.empty()||exports.size()>1024)invalid("E_FFI_GRANT","foreign export grants must contain 1..1024 names");
    std::set<std::string> names;for(const auto &value:exports){auto name=string(value,"E_FFI_GRANT");if(!identifier(name)||!names.insert(name).second)invalid("E_FFI_GRANT","invalid or duplicate export grant");}
    auto path=std::filesystem::path(directory);if(path.is_relative())path=parent/path;
    if(path.string().size()>4096)invalid("E_FFI_GRANT","resolved grant directory exceeds path byte limit");
    grants.emplace(item.key(),ForeignLibraryGrant{path.string(),std::move(pin),std::move(names)});
  }
  auto resources=doc.contains("resource_limit")?integer(doc.at("resource_limit"),"E_FFI_GRANT"):64;
  auto bytes=doc.contains("resource_bytes")?integer(doc.at("resource_bytes"),"E_FFI_GRANT"):64*1048576;
  if(!resources||resources>4096||!bytes||bytes>uint64_t(1024)*1024*1024)invalid("E_FFI_GRANT","foreign resource limits exceed supported bounds");
  return std::make_shared<ForeignLibraries>(std::move(grants),size_t(limit),size_t(resources),bytes);
}
struct ForeignScope::Impl {std::shared_ptr<State> state;};
ForeignScope::ForeignScope(std::shared_ptr<ForeignLibraries> libraries,ForeignScopeLimits limits){
  if(!libraries)invalid("E_FFI_GRANT","foreign scope requires a host catalogue");
  if(!limits.bindings||limits.bindings>4096||!limits.metadataBytes||limits.metadataBytes>64*1048576)invalid("E_FFI_LIMIT","foreign metadata limits exceed supported bounds");
  if(!limits.call.references||limits.call.references>65536||!limits.call.copiedBytes||limits.call.copiedBytes>64*1048576||!limits.call.operations||limits.call.operations>1048576)invalid("E_FFI_LIMIT","foreign call limits exceed supported bounds");
  // Prune ended contexts even if a host never invokes a foreign function.
  std::erase_if(contexts,[](const auto &entry){auto state=entry.lock();return !state||!state->active.load();});
  if(contexts.size()>=64)invalid("E_FFI_LIMIT","foreign scope nesting exceeds 64");
  auto state=std::make_shared<State>(std::move(libraries),limits);auto value=std::make_unique<Impl>();value->state=state;contexts.push_back(state);impl=std::move(value);
}
ForeignScope::~ForeignScope(){if(impl){impl->state->active=false;impl->state->resources.revoke();impl->state->modules.revoke();}}
struct CapturedForeignScope::Impl {
  std::shared_ptr<State> state;
  ResourceAccess access;
};
CapturedForeignScope::CapturedForeignScope(std::shared_ptr<const Impl> value):impl(std::move(value)){}
CapturedForeignScope captureForeignScope(bool unavailableDeferred){
  std::shared_ptr<State> state;
  try{state=current();}catch(const DataError &error){if(unavailableDeferred&&error.code=="E_FFI_GRANT")return {};throw;}
  auto *domain=&state->modules;
  if(auto binder=resource_detail::requestBinder)if(auto joined=binder(*domain))domain=joined;
  return CapturedForeignScope(std::make_shared<CapturedForeignScope::Impl>(CapturedForeignScope::Impl{state,domain->access()}));
}
void CapturedForeignScope::check()const{
  if(!impl)invalid("E_FFI_GRANT","task foreign calls require a captured explicit host scope");
  if(!impl->state->active.load())invalid("E_FFI_SCOPE","captured foreign scope has ended");
  impl->access.check();
}
ForeignCallLimits CapturedForeignScope::callLimits()const{check();return impl->state->limits.call;}
ForeignSignature CapturedForeignScope::signature(const std::string &text)const{check();return resolve(impl->state,text)->signature;}
ForeignFunction CapturedForeignScope::bind(const std::string &text,std::function<void()> poll)const{
  check();auto retained=*this;
  auto checked=[retained,poll=std::move(poll)]{retained.check();if(poll)poll();retained.check();};
  auto selected=resolve(impl->state,text);
  return impl->state->libraries->bindWithResourceScope(selected->library,selected->name,selected->signature,selected->pin,impl->access,std::move(checked));
}
Value invokeScopedForeign(const std::string &description,std::span<const Value> arguments,std::function<void()> poll){
  auto state=current();if(description.size()>1048576)invalid("E_FFI_LIMIT","foreign binding exceeds 1 MiB");
  if(arguments.size()>4096)invalid("E_FFI_LIMIT","foreign argument pack exceeds 4096 values");auto text=description;
  // Inputs and callback storage must survive a poll destroying caller wrappers.
  std::vector<Value> retained(arguments.begin(),arguments.end());
  auto checked=[state,poll=std::move(poll)]{state->check();if(poll)poll();state->check();};
  auto selected=resolve(state,text);
  auto function=state->libraries->bind(selected->library,selected->name,selected->signature,selected->pin,checked);
  return function.invokeWithResourceScope(retained,state->resources.access(),checked,state->limits.call);
}
void resetForeignScopes()noexcept{
  while(!contexts.empty()){auto state=contexts.back().lock();contexts.pop_back();if(state){state->active=false;state->resources.revoke();state->modules.revoke();state->libraries->revoke();}}
}
}
