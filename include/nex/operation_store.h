#pragma once
#include "nex/operations.h"
struct sqlite3;
namespace nex {
void saveOperationGraph(sqlite3 *db,const Program &p,const Function &f,const std::string &function,const std::string &revision,const std::string &basis);
llvm::json::Value storedOperations(sqlite3 *db,const Program &p,const std::string &symbol,const std::string &selector,unsigned offset,unsigned limit,bool context=false);
}
