#pragma once
#include "nex/language.h"
#include <filesystem>

namespace nex {
// Shared by ordinary CLI migration and explicit internal semantic-version
// tests. Neither origin nor target preflight opens a writable graph Store.
// Public024 rechecks retained018..023 origins under their own parser before
// checking a new024 target. Neither a metadata edit nor ordinary load migrates.
bool versionedMigrationLanguage(const std::string &,SourceLanguage target=currentSourceLanguage);
void validateMigrationLanguage(const std::string &,SourceLanguage target=currentSourceLanguage);
bool verifyMigrationOrigin(const llvm::json::Value &bundle,const std::filesystem::path &root,
    const std::string &language,const std::string &revision,SourceLanguage target=currentSourceLanguage);
Program preflightMigrationTarget(const llvm::json::Value &bundle,const std::filesystem::path &root,
    SourceLanguage target=currentSourceLanguage);
}
