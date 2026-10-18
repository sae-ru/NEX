#pragma once
#include "nex_host.h"
// Internal generated-code boundary, not a stable external FFI.
extern "C" {
nexrt::Handle *nex_file_open_read(nexrt::Handle*,int64_t);
nexrt::Handle *nex_file_open_write(nexrt::Handle*,int64_t);
nexrt::Handle *nex_file_open_append(nexrt::Handle*,int64_t);
nexrt::Handle *nex_file_read(nexrt::Handle*,int64_t,int64_t);
nexrt::Handle *nex_file_write(nexrt::Handle*,nexrt::Handle*,int64_t);
nexrt::Handle *nex_file_seek(nexrt::Handle*,int64_t,int64_t);
nexrt::Handle *nex_file_size(nexrt::Handle*,int64_t);
nexrt::Handle *nex_file_flush(nexrt::Handle*,int64_t);
int64_t nex_file_close(nexrt::Handle*,int64_t);
int64_t nex_file_is_open(nexrt::Handle*,int64_t);
}
