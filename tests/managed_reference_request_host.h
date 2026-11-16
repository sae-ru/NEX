#pragma once
#include "nex_host.h"
#include "nex_cell_host.h"
#include "nex_cells.h"
#include <fstream>
#include <string>
#include <stdexcept>
using ManagedRequestEntry=int64_t(*)(nexrt::Handle **);
inline int runManagedRequests(ManagedRequestEntry entry,unsigned requests,unsigned calls,nexrt::CellHeapLimits limits,const std::string &report,uint64_t budget=4000000,unsigned cancelAt=0,uint64_t timeoutMs=10000){
  const auto baseline=nexrt::liveObjects.load();int64_t status=0;std::ofstream output(report);
  if(!output)throw std::runtime_error("cannot write request report");
  output<<"[";bool first=true;
  for(unsigned request=0;request<requests;++request){
    unsigned completed=0;bool failed=false;int64_t result=0;std::string code;
    {
      nexrt::RequestScope scope(budget,timeoutMs);unsigned polls=0;
      if(cancelAt)scope.setCancellation([&]{return ++polls==cancelAt;});
      try{
        nex_cell_context_limits(int64_t(limits.maximumCells),int64_t(limits.maximumNodes),int64_t(limits.maximumEdges),0);
        for(unsigned call=0;call<calls;++call){
          nexrt::Handle *error=nullptr;result=entry(&error);++completed;
          if(error){auto packet=nexrt::readSourceErrorHandle(error);nexrt::printNativeSourceException(packet);packet.payload.reset();nex_release(error);failed=true;code="E_SOURCE_EXCEPTION";status=70;break;}
          status=result;
        }
      }catch(const nexrt::Trap &error){
        const auto *located=dynamic_cast<const nexrt::LocatedTrap*>(&error);
        nexrt::printNativeTrapText(error.code,nexrt::trapMessage(error),error.line,located?located->source:std::string());failed=true;code=error.code;status=70;
      }
    }
    if(nexrt::liveObjects.load()!=baseline)throw std::runtime_error("request left live values after teardown");
    if(!first)output<<",";first=false;
    output<<"{\"request\":"<<request<<",\"calls\":"<<completed<<",\"failed\":"<<(failed?"true":"false")<<",\"code\":"<<nexrt::quoted(code)<<",\"result\":"<<result<<",\"live_delta\":0}";
  }
  output<<"]\n";output.close();nex_runtime_finish();return int(status);
}
