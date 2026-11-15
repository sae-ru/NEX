#pragma once
// Compiler-private sequential cell helpers; not a public FFI or module ABI.
#include "nex_host.h"
extern "C" {
void nex_cell_context_limits(int64_t cells,int64_t nodes,int64_t edges,int64_t line);
nexrt::Handle *nex_cell_new_i64(int64_t value,int64_t tag,int64_t line);
nexrt::Handle *nex_cell_new_heap(nexrt::Handle *value,int64_t line);
int64_t nex_cell_read_i64(nexrt::Handle *cell,int64_t tag,int64_t line);
nexrt::Handle *nex_cell_read_heap(nexrt::Handle *cell,int64_t line);
void nex_cell_write_i64(nexrt::Handle *cell,int64_t value,int64_t tag,int64_t line);
void nex_cell_write_heap(nexrt::Handle *cell,nexrt::Handle *value,int64_t line);
void nex_cell_collect(int64_t line);
}
