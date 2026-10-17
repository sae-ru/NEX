#pragma once
#include "nex/language.h"

namespace nex {
struct NativeUnit {
  std::string unit, module, contract;
  std::set<std::string> functions;
  bool wire = false, storage = false;
};
struct NativePlan {
  std::vector<NativeUnit> units;
  llvm::json::Value dependencies = nullptr;
};
// Plan from an already checked graph. Body identities are local to a unit;
// external calls depend on contracts, and type dependencies include layouts.
NativePlan planNative(const Program &program, const std::string &entry);
std::set<std::string> nativeFunctionBridges(const Program &program,const std::set<std::string> &reachable);
}
