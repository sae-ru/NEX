#pragma once
#include "nex_value.h"
#include <memory>
#include <functional>

namespace nexrt {
struct Handle;
struct Trap : std::runtime_error {
  std::string code; int64_t line;
  Trap(std::string code,std::string message,int64_t line):std::runtime_error(std::move(message)),code(std::move(code)),line(line){}
};
// Trusted runtime boundary. Resource/handle pointers are never NEX source values.
class RequestScope {
  struct Impl;std::unique_ptr<Impl> impl;
public:
  explicit RequestScope(uint64_t budget=1000000,uint64_t timeoutMs=5000);
  ~RequestScope();
  RequestScope(const RequestScope&)=delete;
  RequestScope &operator=(const RequestScope&)=delete;
  void cancel();
  void setCancellation(std::function<bool()> check);
  void poll(int64_t line=0,bool forceCancellation=true);
  void track(Handle*);
  void untrack(Handle*);
};
Handle *makeHandle(const Value &value);
Value readHandle(const Handle *handle);
[[noreturn]] void runtimeFail(const char *code,const char *message,int64_t line);
bool inRequestScope();
void pollHostOperation(int64_t line);
void registerRuntimeCleanup(void (*cleanup)() noexcept);
void cleanupRuntimeResources();
template<class F> Handle *hostValue(int64_t line,F operation){
  try{return makeHandle(operation());}
  catch(const Trap &){throw;}
  catch(const DataError &e){runtimeFail(e.code.c_str(),e.what(),line);}
  catch(const std::bad_alloc &){runtimeFail("E_MEMORY","allocation failed",line);}
  catch(const std::exception &){runtimeFail("E_RUNTIME","host value operation failed",line);}
}
}
extern "C" {
void nex_release(nexrt::Handle *handle);
void nex_runtime_finish();
void nex_poll(int64_t line);
}
