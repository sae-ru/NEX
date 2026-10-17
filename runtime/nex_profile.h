#pragma once
#include <cstddef>
#include <cstdint>

// Hooks are absent from ordinary builds and from the reference interpreter.
extern "C" {
void nex_profile_enter(const char *name,const char *file,int64_t line,const char *content);
void nex_profile_leave();
void nex_profile_unwind();
void nex_profile_allocation(const void *pointer,size_t size,int pool);
void nex_profile_free(const void *pointer);
}
namespace nexrt {
inline void profileAllocate(const void *pointer,size_t size,int pool){
#ifdef NEX_PROFILE_ENABLED
  nex_profile_allocation(pointer,size,pool);
#else
  (void)pointer;(void)size;(void)pool;
#endif
}
inline void profileFree(const void *pointer){
#ifdef NEX_PROFILE_ENABLED
  nex_profile_free(pointer);
#else
  (void)pointer;
#endif
}
inline void profileUnwind(){
#ifdef NEX_PROFILE_ENABLED
  nex_profile_unwind();
#endif
}
}
