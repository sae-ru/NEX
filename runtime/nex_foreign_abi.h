#pragma once
#include <cstdint>
namespace nexrt {struct Handle;}
extern "C" nexrt::Handle *nex_foreign_invoke(const char *binding,int64_t bindingSize,
                                            nexrt::Handle *arguments,int64_t line);
