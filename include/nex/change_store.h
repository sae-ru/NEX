#pragma once
#include "llvm/Support/JSON.h"
#include <string>
struct sqlite3;
namespace nex {
struct ChangeInfo {
  std::string action="save",command,actor,note,requestHash;
};
void validateChangeInfo(const ChangeInfo &info);
void initializeChanges(sqlite3 *db);
void recordHeadChange(sqlite3 *db,const std::string &before,const std::string &after,
                      const std::string &sourceHash,const ChangeInfo &info);
llvm::json::Value graphChanges(sqlite3 *db,unsigned offset,unsigned limit);
}
