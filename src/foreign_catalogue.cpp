#include "nex/foreign_catalogue.h"
#include "nex_foreign.h"
#include <algorithm>
#include <filesystem>

namespace nex {
namespace {
namespace fs=std::filesystem;
using Object=llvm::json::Object;
using Array=llvm::json::Array;
constexpr size_t maximumBytes=128*1048576,maximumFiles=8190;
fs::path member(const fs::path &root,const std::string &name){
  if(fs::is_symlink(root))throw Error("E_TASK_INTEGRITY","symlink in captured foreign directory");
  auto path=root;
  for(const auto &part:fs::path(name)){
    if(part==".."||part=="."||part.empty()||part.is_absolute())throw Error("E_TASK_INTEGRITY","invalid captured foreign path");
    path/=part;
    if(fs::is_symlink(path))throw Error("E_TASK_INTEGRITY","symlink in captured foreign input");
  }
  return path;
}
}
ForeignCatalogueSnapshot inspectForeignCatalogue(const std::string &configuration){
  try{
    auto libraries=nexrt::loadForeignLibraries(configuration);
    ForeignCatalogueSnapshot result;result.platform=nexrt::foreignPlatform();
    Object grants;size_t bytes=0;
    for(const auto &[name,grant]:libraries->operatorGrants()){
      // The same pin can be granted under several logical names. Still verify
      // each operator-selected directory, then deduplicate the retained bytes.
      bool duplicate=result.files.contains("bundles/"+grant.manifestSha256+"/manifest.json");
      auto bundle=nexrt::inspectForeignBundle(grant,duplicate?maximumBytes:maximumBytes-bytes);
      Array exports;for(const auto &name:grant.exports)exports.push_back(name);
      grants[name]=Object{{"directory","bundles/"+grant.manifestSha256},{"manifest_sha256",grant.manifestSha256},{"exports",std::move(exports)}};
      result.grants.emplace(name,ForeignCatalogueGrant{grant.manifestSha256,grant.exports,std::move(bundle.exports)});
      if(!duplicate)for(auto &[path,data]:bundle.files){
        if(data.size()>maximumBytes-bytes||result.files.size()>=maximumFiles)throw Error("E_TASK_FOREIGN_LIMIT","foreign input capture exceeds task limits");
        bytes+=data.size();result.files.emplace("bundles/"+grant.manifestSha256+"/"+path,std::move(data));
      }
    }
    result.manifest=Object{{"schema","nex.foreign-host/1"},{"module_limit",int64_t(libraries->moduleLimit())},{"resource_limit",int64_t(libraries->resourceLimit())},{"resource_bytes",int64_t(libraries->resourceBytesLimit())},{"libraries",std::move(grants)}};
    result.identity=Object{{"schema","nex.foreign-catalogue/1"},{"platform",result.platform},{"catalogue",result.manifest}};
    result.hash=hash(json(result.identity,false));return result;
  }catch(const nexrt::DataError &error){throw Error(error.code,error.what());}
}
llvm::json::Value describeForeignCatalogue(const ForeignCatalogueSnapshot &snapshot){
  Object libraries;size_t bytes=0;
  for(const auto &[name,grant]:snapshot.grants){Array exports;for(const auto &name:grant.exports)exports.push_back(name);
    libraries[name]=Object{{"manifest_sha256",grant.pin},{"exports",std::move(exports)}};
  }
  for(const auto &[name,data]:snapshot.files){(void)name;bytes+=data.size();}
  return Object{{"schema","nex.foreign-catalogue-report/1"},{"hash",snapshot.hash},{"platform",snapshot.platform},
    {"normalized_catalogue",snapshot.manifest},{"libraries",std::move(libraries)},
    {"files",int64_t(snapshot.files.size())},{"bytes",int64_t(bytes)},{"module_initialization",false}};
}
void checkForeignBinding(const ForeignCatalogueSnapshot &snapshot,const Program &program,const Function &function){
  if(!function.foreign)return;
  const auto &binding=*function.foreign;auto grant=snapshot.grants.find(binding.library);
  if(grant==snapshot.grants.end()||!grant->second.exports.contains(binding.symbol)||grant->second.pin!=binding.manifest)
    throw Error("E_TASK_FOREIGN_BINDING","reachable external binding is outside the reviewed operator grant: "+function.name,function.span);
  auto expected=grant->second.signatures.find(binding.symbol);
  auto signature=nexrt::ForeignSignature(json(foreignSignature(program,function),false));
  if(expected==grant->second.signatures.end()||expected->second!=nexrt::foreignSignatureDigest(signature))
    throw Error("E_TASK_FOREIGN_BINDING","reachable external signature differs from the reviewed bundle: "+function.name,function.span);
}
void saveForeignCatalogue(const ForeignCatalogueSnapshot &snapshot,const fs::path &directory){
  writeFile(member(directory,"host.json").string(),json(snapshot.manifest)+"\n");
  writeFile(member(directory,"identity.json").string(),json(snapshot.identity)+"\n");
  for(const auto &[name,data]:snapshot.files)writeFile(member(directory,name).string(),data);
}
void verifyForeignCatalogue(const ForeignCatalogueSnapshot &snapshot,const fs::path &directory){
  auto verify=[&](const std::string &name,const std::string &expected){
    auto path=member(directory,name);
    if(!fs::is_regular_file(path)||fs::file_size(path)!=expected.size()||readFile(path.string())!=expected)
      throw Error("E_TASK_INTEGRITY","captured foreign input differs from current operator trust: "+name);
  };
  verify("host.json",json(snapshot.manifest)+"\n");verify("identity.json",json(snapshot.identity)+"\n");
  for(const auto &[name,data]:snapshot.files)verify(name,data);
}
}
