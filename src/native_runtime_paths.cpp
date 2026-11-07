#include "nex/native_toolchain.h"
#include "llvm/BinaryFormat/ELF.h"
#include "llvm/Object/ELF.h"
#include "llvm/Support/Error.h"
#include "llvm/TargetParser/Triple.h"
#include <algorithm>
#include <cstdint>
#include <filesystem>
#include <map>
#include <optional>
#include <set>

namespace nex {
namespace {
namespace fs=std::filesystem;
[[noreturn]] void invalid(const std::string &message){throw Error("E_TARGET_LIBRARY",message);}

template<class ELFT> std::string soname(llvm::StringRef bytes,const fs::path &path){
  auto parsed=llvm::object::ELFFile<ELFT>::create(bytes);
  if(!parsed)invalid("cannot read selected ELF library "+path.string()+": "+llvm::toString(parsed.takeError()));
  auto entries=parsed->dynamicEntries();
  if(!entries)invalid("cannot read selected ELF dynamic table "+path.string()+": "+llvm::toString(entries.takeError()));
  std::optional<uint64_t> address,size,name;
  for(const auto &entry:*entries){
    if(entry.d_tag==llvm::ELF::DT_NULL)break;
    auto assign=[&](std::optional<uint64_t> &field){
      const uint64_t value=entry.d_un.d_val;
      if(field&&*field!=value)invalid("conflicting selected ELF dynamic entries: "+path.string());
      field=value;
    };
    if(entry.d_tag==llvm::ELF::DT_STRTAB)assign(address);
    if(entry.d_tag==llvm::ELF::DT_STRSZ)assign(size);
    if(entry.d_tag==llvm::ELF::DT_SONAME)assign(name);
  }
  // Without SONAME, an absolute linker input remains an absolute DT_NEEDED.
  if(!name)return {};
  if(!address||!size||*name>=*size)invalid("invalid selected ELF SONAME table: "+path.string());
  auto mapped=parsed->toMappedAddr(*address,[](const llvm::Twine &message){return llvm::object::createError(message);});
  if(!mapped)invalid("cannot map selected ELF string table "+path.string()+": "+llvm::toString(mapped.takeError()));
  const auto begin=reinterpret_cast<uintptr_t>(parsed->base());
  const auto pointer=reinterpret_cast<uintptr_t>(*mapped);
  if(pointer<begin||pointer-begin>parsed->getBufSize()||*size>parsed->getBufSize()-(pointer-begin))
    invalid("selected ELF string table is outside its file: "+path.string());
  llvm::StringRef text(reinterpret_cast<const char*>(*mapped)+*name,*size-*name);
  const auto end=text.find('\0');
  if(end==llvm::StringRef::npos||end==0||end>4096)invalid("invalid selected ELF SONAME: "+path.string());
  const auto result=text.take_front(end);
  if(result.contains('/')||result=="."||result=="..")
    invalid("selected ELF SONAME must be a filename: "+path.string());
  return result.str();
}

struct Library {fs::path path;std::string name,imageHash;};
std::optional<Library> library(const std::string &input){
  const fs::path path=fs::weakly_canonical(input);
  const auto bytes=readFile(path.string());
  // Archives add no runtime search directory. In particular, an unrelated
  // shared library beside a selected static archive must not shadow a DSO.
  if(bytes.starts_with("!<arch>\n")||bytes.starts_with("!<thin>\n"))return std::nullopt;
  if(bytes.size()<6||bytes.compare(0,4,"\177ELF")!=0)
    invalid("selected Linux runtime library must be an ELF image or archive: "+path.string());
  const auto elfClass=static_cast<unsigned char>(bytes[llvm::ELF::EI_CLASS]);
  const auto data=static_cast<unsigned char>(bytes[llvm::ELF::EI_DATA]);
  std::string name;
  using namespace llvm::object;
  if(elfClass==llvm::ELF::ELFCLASS32&&data==llvm::ELF::ELFDATA2LSB)name=soname<ELF32LE>(bytes,path);
  else if(elfClass==llvm::ELF::ELFCLASS32&&data==llvm::ELF::ELFDATA2MSB)name=soname<ELF32BE>(bytes,path);
  else if(elfClass==llvm::ELF::ELFCLASS64&&data==llvm::ELF::ELFDATA2LSB)name=soname<ELF64LE>(bytes,path);
  else if(elfClass==llvm::ELF::ELFCLASS64&&data==llvm::ELF::ELFDATA2MSB)name=soname<ELF64BE>(bytes,path);
  else invalid("unsupported selected ELF class/encoding: "+path.string());
  return Library{path,std::move(name),hash(bytes)};
}
}

std::vector<std::string> nativeRuntimeSearchPaths(const NativeToolchain &tools,bool storage,bool foreign,bool server){
  const llvm::Triple target(tools.target);
  if(!target.isOSDarwin()&&!target.isOSLinux())return {};
  std::vector<std::string> inputs;
  if(storage)inputs.push_back(tools.sqliteLibrary);
  if(server)inputs.push_back(tools.opensslSSL);
  if(foreign||server)inputs.push_back(tools.opensslCrypto);
  std::set<std::string> directories;
  std::vector<Library> libraries;
  for(const auto &input:inputs){
    if(input.empty())invalid("missing selected runtime library");
    if(target.isOSDarwin())directories.insert(fs::path(input).parent_path().string());
    else if(auto selected=library(input)){
      const auto directory=selected->path.parent_path().string();
      if(directory.find(':')!=std::string::npos)invalid("ELF library directories cannot contain ':' (runtime search-path separator): "+directory);
      directories.insert(directory);libraries.push_back(std::move(*selected));
    }
  }
  std::vector<std::string> paths(directories.begin(),directories.end());
  if(target.isOSDarwin())return paths;
  std::map<std::string,size_t> indices;
  for(size_t i=0;i<paths.size();++i)indices.emplace(paths[i],i);
  std::vector<std::set<size_t>> edges(paths.size());
  for(const auto &selected:libraries){
    if(selected.name.empty())continue;
    const auto own=indices.at(selected.path.parent_path().string());
    const auto alias=selected.path.parent_path()/selected.name;
    std::error_code error;
    if(!fs::is_regular_file(alias,error)||error||hash(readFile(alias.string()))!=selected.imageHash)
      invalid("selected ELF SONAME alias must contain its configured library image: "+alias.string()+" -> "+selected.path.string());
    for(size_t other=0;other<paths.size();++other){
      if(other==own)continue;
      const auto candidate=fs::path(paths[other])/selected.name;
      const bool present=fs::exists(candidate,error);
      if(error)invalid("cannot inspect selected ELF runtime directory: "+candidate.string()+": "+error.message());
      // Even a byte-identical copy has separate path/provenance. Prefer the
      // explicitly selected directory rather than silently switching roots.
      if(present)edges[own].insert(other);
    }
  }
  std::vector<std::string> ordered;
  std::set<size_t> remaining;
  for(size_t i=0;i<paths.size();++i)remaining.insert(i);
  while(!remaining.empty()){
    auto ready=remaining.end();
    for(auto candidate=remaining.begin();candidate!=remaining.end();++candidate){
      const bool blocked=std::any_of(remaining.begin(),remaining.end(),[&](size_t before){return edges[before].contains(*candidate);});
      if(!blocked){ready=candidate;break;}
    }
    if(ready==remaining.end()){
      std::string message="selected ELF libraries have conflicting SONAME search requirements; use consistent runtime directories:";
      for(auto index:remaining)message+=" "+paths[index];
      invalid(message);
    }
    ordered.push_back(paths[*ready]);remaining.erase(ready);
  }
  return ordered;
}
}
