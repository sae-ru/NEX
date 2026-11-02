#include "Plugins/Process/Utility/RegisterInfoPOSIX_arm64.h"
#include "lldb/Utility/ArchSpec.h"
#include <cstdint>
#include <cstring>
#include <iostream>

int main() {
  using Info = RegisterInfoPOSIX_arm64;
  const lldb_private::ArchSpec arch("aarch64-unknown-linux");
  unsigned checks = 0, profiles = 0;
  for (uint32_t mask : {0u, 16u, 20u, 1u, 32u, 33u, 2u, 34u, 35u}) {
    Info info(arch, lldb_private::Flags(mask));
    const auto count = info.GetRegisterCount();
    const bool has_sme = (mask & Info::eRegsetMaskSSVE) != 0;
    std::cout << "profile " << mask << std::endl;
    for (uint32_t vq : {1u, 2u, 4u, 1u, 256u}) {
      info.ConfigureVectorLengthZA(vq);
      if (info.GetRegisterCount() != count) return 10;
      ++checks;
      unsigned za = 0;
      for (unsigned i = 0; i < count; ++i) {
        const auto &reg = info.GetRegisterInfo()[i];
        if (reg.name && std::strcmp(reg.name, "za") == 0) {
          ++za;
          if (!has_sme || reg.byte_size != (vq * 16) * (vq * 16)) return 11;
          ++checks;
        }
      }
      if (za != unsigned(has_sme)) return 12;
      ++checks;
    }
    ++profiles;
  }
  std::cout << "{\"ok\":true,\"profiles\":" << profiles
            << ",\"checks\":" << checks << "}\n";
}
