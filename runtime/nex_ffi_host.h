#pragma once
#include "nex_ffi.h"
#include "nex_value.h"
#include <functional>
#include <span>
namespace nexrt {
namespace foreign_detail { class TypedContext; class TaskCodec; }
class ForeignSignature {
public:
  struct Layout;
  explicit ForeignSignature(const std::string &json);
  const std::string &canonical()const;
  bool hasResources()const;
private:
  std::shared_ptr<const Layout> layout;
  friend class foreign_detail::TypedContext;
  friend class foreign_detail::TaskCodec;
};
struct ForeignCallLimits {
  uint64_t references=4096;
  uint64_t copiedBytes=1048576;
  uint64_t operations=65536;
};
// Trusted host entry. Arguments are copied before polling or entering C code.
// All C tokens expire on return; only the returned managed Value escapes.
Value invokeForeign(nex_ffi_callback_v1 callback,std::span<const Value> arguments,
                    void *user=nullptr,std::function<void()> poll={},
                    ForeignCallLimits limits={});
Value invokeForeignTyped(nex_ffi_callback_v1 callback,std::span<const Value> arguments,
                         const ForeignSignature &signature,void *user=nullptr,
                         std::function<void()> poll={},ForeignCallLimits limits={});
}
