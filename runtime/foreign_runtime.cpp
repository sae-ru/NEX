#include "nex_foreign_abi.h"
#include "nex_foreign.h"
#include "nex_host.h"
extern "C" nexrt::Handle *nex_foreign_invoke(const char *binding,int64_t size,
                                            nexrt::Handle *arguments,int64_t line){
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
}
