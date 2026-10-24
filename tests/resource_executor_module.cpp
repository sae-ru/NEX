#include "nex_error.h"
#include <cstdlib>
#include <stdexcept>
namespace {
void (*event)(int)=nullptr;
struct ModuleError final:nexrt::DataError {
  ModuleError():DataError("E_DEVICE_TEST","module error"){}
  ~ModuleError()noexcept override{if(event)event(3);}
};
struct UnknownError final:std::runtime_error {
  UnknownError():std::runtime_error("private module exception"){}
  ~UnknownError()noexcept override{if(event)event(3);}
};
__attribute__((destructor)) void unload(){if(event)event(2);}
}
extern "C" {
void resource_executor_callback(void(*callback)(int)){event=callback;}
void *resource_fixture_create(void(*callback)(int)){event=callback;return std::malloc(8);}
void resource_fixture_destroy(void *p){if(event)event(1);std::free(p);}
void resource_executor_throw(int unknown){if(unknown)throw UnknownError{};throw ModuleError{};}
}
