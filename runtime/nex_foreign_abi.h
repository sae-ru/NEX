#pragma once
#include <cstdint>
namespace nexrt {struct Handle;}
extern "C" void nex_foreign_configure(int64_t argc,const char *const *argv);
extern "C" nexrt::Handle *nex_foreign_invoke(const char *binding,int64_t bindingSize,
                                            nexrt::Handle *arguments,int64_t line);
extern "C" int64_t nex_resource_close(nexrt::Handle*,int64_t line);
extern "C" int64_t nex_resource_is_open(nexrt::Handle*,int64_t line);
