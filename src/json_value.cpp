#include "nex/language.h"
#include "llvm/Support/FormatVariadic.h"

namespace nex {
// Kept in its own RTTI-free translation unit for retained LLVM archives that
// omit format_adapter typeinfo. No other language code shares this TU.
std::string json(const llvm::json::Value &v, bool pretty) {
  return pretty ? llvm::formatv("{0:2}", v).str() : llvm::formatv("{0}", v).str();
}
}
