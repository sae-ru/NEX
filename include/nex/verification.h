#pragma once
#include "nex/language.h"
namespace nex {
struct VerificationOptions {
  std::string symbol,directory;
  unsigned solverTimeoutMs=2000,resourceLimit=1000000,totalTimeoutSeconds=30;
};
std::string verifierVersion();
std::string verificationIntentHash(const llvm::json::Value &contract);
llvm::json::Value contractTemplate(const Program &program,const std::string &symbol);
llvm::json::Value verifyContracts(const Program &program,const llvm::json::Value &contract,const llvm::json::Value &graph,const VerificationOptions &options);
}
