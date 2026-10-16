#pragma once
#include "nex/language.h"
#include <filesystem>
namespace nex {
class Store {
  struct Impl; std::unique_ptr<Impl> impl;
public:
  explicit Store(const std::filesystem::path &directory);
  ~Store();
  std::string save(const Program &program, const std::string &expected = "");
  llvm::json::Value graph(const Program &program);
  llvm::json::Value history();
  std::string source(const std::string &revision);
  std::string headRevision();
  std::string revisionLanguage(const std::string &revision);
  llvm::json::Value bundle(const std::string &revision);
};
std::filesystem::path projectRoot(std::filesystem::path start);
}
