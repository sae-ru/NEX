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
// Rich locations are an additive internal runtime ABI. Legacy exported helpers
// and the original Trap layout remain available to trusted C/C++ hosts.
// Compiler-private 64-bit descriptor layout, mirrored by MLIR constant globals.
// Function hashes are shared by all sites in that function. Serialization is cold.
struct NativeFunctionSite {const char *functionHash,*sourceHash,*compilerBuild;};
struct NativeSite {const NativeFunctionSite *function;const char *site,*kind;int64_t begin,end;};
static_assert(sizeof(NativeFunctionSite)==24&&sizeof(NativeSite)==40);
struct SourceLocation {
  int64_t line=0;const NativeSite *site=nullptr;
  SourceLocation(int64_t line=0,const NativeSite *site=nullptr):line(line),site(site){}
  operator int64_t()const{return line;}
};
struct LocatedTrap : Trap {
  std::string source;
  LocatedTrap(const Trap &trap,std::string source);
};
[[noreturn]] void propagateTrap(const Trap &trap,SourceLocation location);
void printNativeTrap(const char *code,const char *message,int64_t line,const std::string &source,const char *request=nullptr)noexcept;
// Trusted runtime boundary. Resource/handle pointers are never NEX source values.
class RequestScope {
  friend struct ParallelAccess;
  struct Control;
  struct Impl;std::shared_ptr<Impl> impl;
  RequestScope(std::shared_ptr<Control> control,const std::atomic<bool> *workerStop);
  void checkExecution(int64_t line,bool forceCancellation,bool consumeStep);
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
  ResourceDomain &bindResources(const ResourceDomain &capability);
};
Handle *makeHandle(const Value &value);
Value readHandle(const Handle *handle);
[[noreturn]] void runtimeFail(const char *code,const char *message,int64_t line);
[[noreturn]] void runtimeFail(const char *code,const char *message,SourceLocation location);
bool inRequestScope();
void pollHostOperation(int64_t line);
void registerRuntimeCleanup(void (*cleanup)() noexcept);
void cleanupRuntimeResources();
template<class F> auto hostOperation(SourceLocation line,F operation)->decltype(operation()){
  try{return operation();}
  catch(const Trap &trap){propagateTrap(trap,line);}
  catch(const DataError &e){runtimeFail(e.code.c_str(),e.what(),line);}
  catch(const std::bad_alloc &){runtimeFail("E_MEMORY","allocation failed",line);}
  catch(const std::exception &){runtimeFail("E_RUNTIME","host value operation failed",line);}
}
template<class F> Handle *hostValue(SourceLocation line,F operation){
  return hostOperation(line,[&]{return makeHandle(operation());});
}
}
extern "C" {
// Compiler-private owned-function boundary. It preserves caller values, moves
// the kept result to the parent owner and cleans all other function temporaries.
// A trusted application or RequestScope must enclose every boundary.
int64_t nex_owned_enter();
int64_t nex_owned_enter_at(const nexrt::NativeSite *site);
void nex_owned_leave(int64_t token,nexrt::Handle *kept);
void nex_owned_leave_at(int64_t token,nexrt::Handle *kept,const nexrt::NativeSite *site);
void nex_release(nexrt::Handle *handle);
void nex_runtime_finish();
// Compiler-generated application thunk: i64(argc, argv), returning process code.
int64_t nex_application_run(void *entry,int64_t argc,const char *const *argv);
void nex_poll(int64_t line);
}
