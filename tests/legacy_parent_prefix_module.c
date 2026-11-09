/* Compile the genuine dependent-resource producer against the frozen 0.163
   table. Including that header first deliberately hides every later slot. */
#include "fixtures/ffi-parent-prefix-0.163/nex_ffi.h"
#ifdef NEX_FFI_V1_TRAP_SIZE
#error This producer must not see the appended trap slot
#endif
#if defined(__cplusplus)
static_assert(sizeof(nex_ffi_api_v1)==304);
#else
_Static_assert(sizeof(nex_ffi_api_v1)==304,"legacy parent table width changed");
#endif
#include "dependent_resource_module.c"
