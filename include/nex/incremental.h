#pragma once
#include "nex/language.h"

namespace nex {
struct NativeUnit {
  std::string identity, unit, module, contract, source;
  std::set<std::string> functions;
  bool wire = false, storage = false;
};
struct NativePlan {
  std::vector<NativeUnit> units;
  llvm::json::Value dependencies = nullptr;
};
// Plan one object per checked concrete function. Body identities are local;
// external calls depend on contracts, and type dependencies include layouts.
NativePlan planNative(const Program &program, const std::string &entry);
std::set<std::string> nativeFunctionBridges(const Program &program,const std::set<std::string> &reachable);
}
