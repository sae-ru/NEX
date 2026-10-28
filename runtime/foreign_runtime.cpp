#include "nex_foreign_abi.h"
#include "nex_foreign.h"
#include "nex_host.h"
#include <cstring>
namespace {
thread_local std::unique_ptr<nexrt::ForeignScope> standaloneForeign;
void resetStandaloneForeign()noexcept{standaloneForeign.reset();nexrt::resetForeignScopes();}
}
static void impl_nex_foreign_configure(int64_t argc,const char *const *argv, nexrt::SourceLocation location){
  return nexrt::hostOperation(location,[&]() -> void {
  nexrt::hostOperation(location,[&]{
    if(argc<0||argc>65536||(!argv&&argc))throw nexrt::DataError("E_FFI_GRANT","invalid native argument vector");
    std::string path;
    for(int64_t i=1;i<argc;++i){if(!argv[i])throw nexrt::DataError("E_FFI_GRANT","invalid native argument vector");
      if(std::strcmp(argv[i],"--nex-foreign")!=0)continue;
      if(!path.empty()||i+1>=argc||!argv[i+1])throw nexrt::DataError("E_FFI_GRANT","--nex-foreign requires one operator catalogue");
      auto size=::strnlen(argv[++i],4097);if(!size||size>4096)throw nexrt::DataError("E_FFI_GRANT","invalid operator catalogue path");path.assign(argv[i],size);
    }
    if(path.empty())path=nexrt::packagedForeignCatalogue();
    if(!path.empty()){
      nexrt::registerRuntimeCleanup(resetStandaloneForeign);
      if(standaloneForeign)throw nexrt::DataError("E_FFI_SCOPE","native foreign configuration is already initialized");
      standaloneForeign=std::make_unique<nexrt::ForeignScope>(nexrt::loadForeignLibraries(path));
    }
  });
});
}
extern "C" void nex_foreign_configure(int64_t argc,const char *const *argv){return impl_nex_foreign_configure(argc, argv, nexrt::SourceLocation{});}
extern "C" void nex_foreign_configure_at(int64_t argc,const char *const *argv, const nexrt::NativeSite *nex_site){return impl_nex_foreign_configure(argc, argv, nexrt::SourceLocation{0,nex_site});}
static nexrt::Handle * impl_nex_foreign_invoke(const char *binding,int64_t size,
                                            nexrt::Handle *arguments,nexrt::SourceLocation line){
  return nexrt::hostOperation(line,[&]() -> nexrt::Handle * {
  return nexrt::hostValue(line,[&]{
    if(!nexrt::inRequestScope())nexrt::registerRuntimeCleanup(nexrt::resetForeignScopes);
    if(!binding||size<=0||size>1048576)throw nexrt::DataError("E_FFI_BINDING","invalid native foreign binding length");
    if(!arguments)throw nexrt::DataError("E_FFI_TYPE","native foreign argument pack is absent");
    auto values=nexrt::readHandle(arguments);
    if(!values.object||values.object->kind!=nexrt::Data::List)throw nexrt::DataError("E_FFI_TYPE","native foreign argument pack must be a list");
    auto result=nexrt::invokeScopedForeign(std::string(binding,size_t(size)),values.object->values,[line]{nexrt::pollHostOperation(line);});
    // The generated adapter extracts its checked scalar/heap result and releases
    // this internal box. Even unit results never become a source value.
    auto box=std::make_shared<nexrt::Data>(nexrt::Data::List);box->values.push_back(std::move(result));return nexrt::Value(std::move(box));
  });
});
}
extern "C" nexrt::Handle * nex_foreign_invoke(const char *binding,int64_t size,
                                            nexrt::Handle *arguments,int64_t line){return impl_nex_foreign_invoke(binding, size, arguments, line);}
extern "C" nexrt::Handle * nex_foreign_invoke_at(const char *binding,int64_t size,
                                            nexrt::Handle *arguments,int64_t line, const nexrt::NativeSite *nex_site){return impl_nex_foreign_invoke(binding, size, arguments, nexrt::SourceLocation{line,nex_site});}
