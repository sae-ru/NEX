#pragma once
#include "nex/language.h"
#include <filesystem>
namespace nex {
class Store {
  struct Impl; std::unique_ptr<Impl> impl;
public:
  explicit Store(const std::filesystem::path &directory);
  ~Store();
  std::string save(const Program &program, const std::string &expected = "",bool makeHead=true);
  llvm::json::Value graph(const Program &program);
  llvm::json::Value operations(const Program &program,const std::string &symbol="",const std::string &selector="",unsigned offset=0,unsigned limit=100,bool context=false);
  llvm::json::Value history();
  std::string source(const std::string &revision);
  std::string headRevision();
  std::string revisionLanguage(const std::string &revision);
  llvm::json::Value bundle(const std::string &revision);
  void recordTask(const std::string &id,const std::string &task,const std::string &taskHash,const std::string &status,const std::string &report,const std::string &reportHash);
  llvm::json::Value taskHistory(const std::string &task,unsigned limit=50);
};
std::filesystem::path projectRoot(std::filesystem::path start);
}
