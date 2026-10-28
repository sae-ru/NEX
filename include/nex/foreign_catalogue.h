#pragma once
#include "nex/language.h"
#include <filesystem>

namespace nex {
struct ForeignCatalogueGrant {
  std::string pin;
  std::set<std::string> exports;
  std::map<std::string,std::string> signatures;
};
struct ForeignCatalogueSnapshot {
  std::string hash,platform;
  llvm::json::Value manifest=nullptr,identity=nullptr;
  std::map<std::string,ForeignCatalogueGrant> grants;
  // Relative to the capture directory, with binary bytes retained verbatim.
  std::map<std::string,std::string> files;
};
// Reads grants and verifies all inventory bytes. Never initializes native code.
ForeignCatalogueSnapshot inspectForeignCatalogue(const std::string &configuration);
llvm::json::Value describeForeignCatalogue(const ForeignCatalogueSnapshot &snapshot);
void checkForeignBinding(const ForeignCatalogueSnapshot &snapshot,const Program &program,const Function &function);
void saveForeignCatalogue(const ForeignCatalogueSnapshot &snapshot,const std::filesystem::path &directory);
void verifyForeignCatalogue(const ForeignCatalogueSnapshot &snapshot,const std::filesystem::path &directory);
}
