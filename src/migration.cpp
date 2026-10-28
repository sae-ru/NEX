#include "nex/migration.h"
#include <algorithm>

namespace nex {
bool versionedMigrationLanguage(const std::string &language,SourceLanguage target){
  return language=="0.18"||language=="0.19"||language=="0.20"||language=="0.21"||language=="0.22"||
    (language=="0.23"&&(target==SourceLanguage::TaskWrites023||target==SourceLanguage::TaskStreams024||target==SourceLanguage::SourceExceptions025))||
    (language=="0.24"&&(target==SourceLanguage::TaskStreams024||target==SourceLanguage::SourceExceptions025))||
    (language=="0.25"&&target==SourceLanguage::SourceExceptions025);
}
void validateMigrationLanguage(const std::string &language,SourceLanguage target){
  if(versionedMigrationLanguage(language,target))return;
  // Historical serializers before018 are not retained. Their existing recheck
  // path remains explicitly unverified; they cannot disguise a modern hash.
  for(unsigned i=1;i<=17;++i)if(language=="0."+std::to_string(i))return;
  throw Error("E_LANGUAGE_VERSION","unsupported migration origin language");
}
bool verifyMigrationOrigin(const llvm::json::Value &bundle,const std::filesystem::path &root,
    const std::string &language,const std::string &original,SourceLanguage target){
  validateMigrationLanguage(language,target);
  if(original.size()!=64||!std::all_of(original.begin(),original.end(),[](char c){return (c>='0'&&c<='9')||(c>='a'&&c<='f');}))
    throw Error("E_REVISION","migration origin requires a canonical revision hash");
  if(!versionedMigrationLanguage(language,target)){
    for(const auto *modern:{"0.18","0.19","0.20","0.21","0.22","0.23","0.24","0.25"}){
      bool matches=false;
      try{matches=revision(loadVersionedBundle(bundle,root.string(),modern))==original;}catch(const Error &){}
      if(matches)throw Error("E_REVISION","migration origin language contradicts its modern semantic revision");
    }
    return false;
  }
  try{
    auto old=loadVersionedBundle(bundle,root.string(),language);
    if(revision(old)!=original)throw Error("E_REVISION","origin source does not match its retained semantic revision");
  }catch(const Error &error){throw Error("E_REVISION",std::string("invalid archived migration origin: ")+error.what(),error.span);}
  return true;
}
Program preflightMigrationTarget(const llvm::json::Value &bundle,const std::filesystem::path &root,SourceLanguage target){
  Program language;language.sourceLanguage=target;
  return loadVersionedBundle(bundle,root.string(),programLanguage(language));
}
}
