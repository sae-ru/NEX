#include "nex_value.h"
#ifdef _WIN32
#define NEX_OWNER_EXPORT __declspec(dllexport)
#else
#define NEX_OWNER_EXPORT __attribute__((visibility("default")))
#endif
extern "C" NEX_OWNER_EXPORT void nex_owner_module_make(nexrt::Value *output,const nexrt::Value *leaf,size_t depth){
  auto value=*leaf;
  for(size_t i=0;i<depth;++i){auto data=nexrt::Data::make(nexrt::Data::List);data->values.push_back(std::move(value));value=nexrt::Value(std::move(data));}
  *output=std::move(value);
}
extern "C" NEX_OWNER_EXPORT int64_t nex_owner_module_live(){return nexrt::liveObjects.load();}
