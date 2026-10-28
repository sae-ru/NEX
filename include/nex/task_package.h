#pragma once
#include "nex/language.h"
namespace nex {
llvm::json::Value captureTaskPackageNotices(const std::string &file,const std::string &projectRoot);
std::string taskPackageNoticesHash(const llvm::json::Value &snapshot);
llvm::json::Value describeTaskPackageNotices(const llvm::json::Value &snapshot);
void saveTaskPackageNotices(const llvm::json::Value &snapshot,const std::string &directory);
void verifyTaskPackageNotices(const llvm::json::Value &snapshot,const std::string &directory);
}
