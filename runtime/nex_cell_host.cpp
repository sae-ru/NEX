#include "nex_cell_host.h"
#include "nex_cells.h"
#include <limits>

namespace {
using namespace nexrt;
void *create(void *argument){return new CellHeap(argument?*static_cast<CellHeapLimits*>(argument):CellHeapLimits{});}
void destroy(void *value)noexcept{delete static_cast<CellHeap*>(value);}
Value checked(Value value,SourceLocation location){pollHostOperation(location);return value;}
CellHeap &heap(SourceLocation location){pollHostOperation(location);return *static_cast<CellHeap*>(managedReferenceContext(create,nullptr,destroy));}
void configure(int64_t cells,int64_t nodes,int64_t edges,SourceLocation location){
  pollHostOperation(location);
  for(auto value:{cells,nodes,edges})if(value<=0||uint64_t(value)>uint64_t(std::numeric_limits<size_t>::max()))throw DataError("E_CELL_LIMIT","native managed heap limits must be positive and representable");
  CellHeapLimits limits{size_t(cells),size_t(nodes),size_t(edges)};
  (void)managedReferenceContext(create,&limits,destroy,true);
  pollHostOperation(location);
}
Value scalar(int64_t value,int64_t tag){
  auto result=Value::taggedScalar(value,tag);
  if(result.tag==Value::Boolean&&(value<0||value>1))throw DataError("E_CELL_TYPE","cell boolean scalar must be zero or one");
  return result;
}
Value read(Handle *cell,SourceLocation location){return checked(heap(location).read(readHandle(cell)),location);}
int64_t readScalar(Handle *cell,int64_t tag,SourceLocation location){
  auto result=read(cell,location);auto expected=tag==0?Value::Integer:tag==1?Value::Boolean:tag==2?Value::Floating:Value::Object;
  if(expected==Value::Object||result.tag!=expected)throw DataError("E_CELL_TYPE","cell payload scalar kind differs from its checked type");return result.scalar;
}
Handle *readHeap(Handle *cell,SourceLocation location){auto result=read(cell,location);if(result.tag!=Value::Object)throw DataError("E_CELL_TYPE","cell payload is not a checked heap value");return makeHandle(result);}
}
#ifdef NEX_ASYNC_TASKS
namespace nexrt {
void configureManagedCellHeap(CellHeapLimits limits){
  hostOperation({},[&]{pollHostOperation(0);(void)managedReferenceContext(create,&limits,destroy,true);pollHostOperation(0);});
}
CellHeapStats managedCellHeapStats(){return hostOperation({},[]{return heap({}).stats();});}
CellCollection collectManagedCells(){return hostOperation({},[]{return heap({}).collect();});}
TaskOwnerExecution managedTaskOwnerExecution(){
  return {[](const Value &value,void *context){(void)static_cast<CellHeap*>(context)->read(value);},
    [](void *context){(void)static_cast<CellHeap*>(context)->collect();},&heap({})};
}
}
#endif
extern "C" {
void nex_cell_request_enter(int64_t line){nexrt::hostOperation({line},[&]{if(!nexrt::inRequestScope())throw nexrt::DataError("E_CELL_CONTEXT","request entry requires a live RequestScope");nex_poll(line);});}
void nex_cell_request_enter_at(int64_t line,const nexrt::NativeSite *site){nexrt::hostOperation({line,site},[&]{if(!nexrt::inRequestScope())throw nexrt::DataError("E_CELL_CONTEXT","request entry requires a live RequestScope");nex_poll(line);});}
void nex_cell_context_limits(int64_t cells,int64_t nodes,int64_t edges,int64_t line){nexrt::hostOperation({line},[&]{configure(cells,nodes,edges,{line});});}
void nex_cell_context_limits_at(int64_t cells,int64_t nodes,int64_t edges,int64_t line,const nexrt::NativeSite *site){nexrt::hostOperation({line,site},[&]{configure(cells,nodes,edges,{line,site});});}
nexrt::Handle *nex_cell_new_i64(int64_t value,int64_t tag,int64_t line){return nexrt::hostValue({line},[&]{return checked(heap({line}).create(scalar(value,tag)),{line});});}
nexrt::Handle *nex_cell_new_i64_at(int64_t value,int64_t tag,int64_t line,const nexrt::NativeSite *site){return nexrt::hostValue({line,site},[&]{return checked(heap({line,site}).create(scalar(value,tag)),{line,site});});}
nexrt::Handle *nex_cell_new_heap(nexrt::Handle *value,int64_t line){return nexrt::hostValue({line},[&]{return checked(heap({line}).create(nexrt::readHandle(value)),{line});});}
nexrt::Handle *nex_cell_new_heap_at(nexrt::Handle *value,int64_t line,const nexrt::NativeSite *site){return nexrt::hostValue({line,site},[&]{return checked(heap({line,site}).create(nexrt::readHandle(value)),{line,site});});}
int64_t nex_cell_read_i64(nexrt::Handle *cell,int64_t tag,int64_t line){return nexrt::hostOperation({line},[&]{return readScalar(cell,tag,{line});});}
int64_t nex_cell_read_i64_at(nexrt::Handle *cell,int64_t tag,int64_t line,const nexrt::NativeSite *site){return nexrt::hostOperation({line,site},[&]{return readScalar(cell,tag,{line,site});});}
nexrt::Handle *nex_cell_read_heap(nexrt::Handle *cell,int64_t line){return nexrt::hostOperation({line},[&]{return readHeap(cell,{line});});}
nexrt::Handle *nex_cell_read_heap_at(nexrt::Handle *cell,int64_t line,const nexrt::NativeSite *site){return nexrt::hostOperation({line,site},[&]{return readHeap(cell,{line,site});});}
void nex_cell_write_i64(nexrt::Handle *cell,int64_t value,int64_t tag,int64_t line){nexrt::hostOperation({line},[&]{heap({line}).write(nexrt::readHandle(cell),scalar(value,tag));nexrt::pollHostOperation(line);});}
void nex_cell_write_i64_at(nexrt::Handle *cell,int64_t value,int64_t tag,int64_t line,const nexrt::NativeSite *site){nexrt::hostOperation({line,site},[&]{heap({line,site}).write(nexrt::readHandle(cell),scalar(value,tag));nexrt::pollHostOperation(line);});}
void nex_cell_write_heap(nexrt::Handle *cell,nexrt::Handle *value,int64_t line){nexrt::hostOperation({line},[&]{heap({line}).write(nexrt::readHandle(cell),nexrt::readHandle(value));nexrt::pollHostOperation(line);});}
void nex_cell_write_heap_at(nexrt::Handle *cell,nexrt::Handle *value,int64_t line,const nexrt::NativeSite *site){nexrt::hostOperation({line,site},[&]{heap({line,site}).write(nexrt::readHandle(cell),nexrt::readHandle(value));nexrt::pollHostOperation(line);});}
void nex_cell_collect(int64_t line){nexrt::hostOperation({line},[&]{heap({line}).collect();nexrt::pollHostOperation(line);});}
void nex_cell_collect_at(int64_t line,const nexrt::NativeSite *site){nexrt::hostOperation({line,site},[&]{heap({line,site}).collect();nexrt::pollHostOperation(line);});}
}
