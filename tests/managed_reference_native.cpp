#include "host_test.h"
#include "nex/managed_references.h"
#include "nex/backend.h"
#include "nex_cell_host.h"
#ifndef _WIN32
#include <dlfcn.h>
#endif
#include <filesystem>
#include <iostream>

using namespace nex;
namespace {
unsigned destroyed=0,denied=0;
void *factory(void *){return new int(42);}
void destroy(void *value)noexcept;
void *otherFactory(void *){return new int(43);}
void destroy(void *value)noexcept{
  delete static_cast<int*>(value);++destroyed;
  try{(void)nexrt::managedReferenceContext(factory,nullptr,destroy);}catch(const nexrt::DataError &error){if(error.code=="E_CELL_CONTEXT")++denied;}
}
void *failedFactory(void *){throw std::bad_alloc();}
int64_t contextEntry(int64_t,const char *const*){
  try{(void)nexrt::managedReferenceContext(failedFactory,nullptr,destroy);}catch(const std::bad_alloc&){}
  auto first=nexrt::managedReferenceContext(factory,nullptr,destroy);
  if(first!=nexrt::managedReferenceContext(factory,nullptr,destroy))throw std::runtime_error("context owner was replaced");
  try{(void)nexrt::managedReferenceContext(otherFactory,nullptr,destroy);throw std::runtime_error("factory mismatch accepted");}catch(const nexrt::DataError &error){if(error.code!="E_CELL_CONTEXT")throw;}
  nex_runtime_finish();
  try{(void)nexrt::managedReferenceContext(factory,nullptr,destroy);throw std::runtime_error("ended context revived");}catch(const nexrt::DataError &error){if(error.code!="E_CELL_CONTEXT")throw;}
  return 0;
}
}
int main(int argc,char **argv){try{
  if(argc==2&&std::string(argv[1])=="context"){
    auto status=nex_application_run(reinterpret_cast<void*>(contextEntry),0,nullptr);
    if(status||destroyed!=1||denied!=1)throw std::runtime_error("reference context teardown/reentry differs");
    std::cout<<"{\"ok\":true,\"destroyed\":1,\"teardown_reentry_denied\":true}\n";return 0;
  }
  if(argc==3&&std::string(argv[1])=="run"){
    const auto baseline=nexrt::liveObjects.load();
    // Pull/export this exact cohort's cell helpers as well as its base runtime.
    if(nexrt::inRequestScope())nex_cell_collect(0);
    nex_runtime_finish();
    auto library=dlopen(argv[2],RTLD_NOW|RTLD_LOCAL);if(!library)throw std::runtime_error(dlerror());
    auto entry=reinterpret_cast<int(*)(int,const char *const*)>(dlsym(library,"main"));if(!entry)throw std::runtime_error(dlerror());
    auto status=entry(0,nullptr);
    if(nexrt::liveObjects.load()!=baseline)throw std::runtime_error("native reference context left live values");
    nex_runtime_finish();dlclose(library);return status;
  }
  const auto mode=argc>1?std::string(argv[1]):std::string{};
  if(!((mode=="reference"&&argc==6)||(mode=="emit"&&argc==10)))throw std::runtime_error("expected reference source cells nodes edges, or emit source out triple layout optimized cells nodes edges");
  const bool emit=mode=="emit";const auto start=emit?7:3;
  nexrt::CellHeapLimits limits{std::stoull(argv[start]),std::stoull(argv[start+1]),std::stoull(argv[start+2])};
  auto path=std::filesystem::absolute(argv[2]);auto p=parseManagedReferencesPrototype(readFile(path.string()),path.string());check(p);
  if(!emit){
    try{
      auto result=evaluateManagedReferencesPrototype(p,"main",4000000,limits);
      std::cout<<json(llvm::json::Object{{"kind","return"},{"value",std::move(result.evaluation.value)},{"output",result.evaluation.output},{"remaining_cells",int64_t(result.afterCollection.cells)},{"remaining_nodes",int64_t(result.afterCollection.nodes)}})<<'\n';
    }catch(const Error &error){std::cout<<json(llvm::json::Object{{"kind","trap"},{"code",error.code},{"message",error.message},{"output",error.output},{"line",int64_t(error.span.line)}})<<'\n';}
    return 0;
  }
  auto folder=std::filesystem::absolute(argv[3]);std::filesystem::create_directories(folder);
  auto mlir=emitManagedReferencesPrototypeMLIR(p,"main",std::string(argv[6])=="true",limits);
  writeFile((folder/"program.mlir").string(),mlir);
  writeFile((folder/"program.ll").string(),lowerMLIRToLLVM(mlir,path.string(),argv[4],argv[5]));return 0;
}catch(const Error &error){std::cerr<<error.code<<": "<<error.message<<" at "<<error.span.line<<":"<<error.span.column<<'\n';}
catch(const std::exception &error){std::cerr<<error.what()<<'\n';}return 1;}
