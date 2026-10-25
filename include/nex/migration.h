#pragma once
#include "nex/language.h"
#include <filesystem>

namespace nex {
// Shared by ordinary CLI migration and explicit internal semantic-version
// tests. Neither origin nor target preflight opens a writable graph Store.
// Private023 origins are admitted only for an explicitly selected023 target;
// ordinary public022 migration does not acquire future-language enablement.
bool versionedMigrationLanguage(const std::string &,SourceLanguage target=currentSourceLanguage);
void validateMigrationLanguage(const std::string &,SourceLanguage target=currentSourceLanguage);
bool verifyMigrationOrigin(const llvm::json::Value &bundle,const std::filesystem::path &root,
    const std::string &language,const std::string &revision,SourceLanguage target=currentSourceLanguage);
Program preflightMigrationTarget(const llvm::json::Value &bundle,const std::filesystem::path &root,
    SourceLanguage target=currentSourceLanguage);
}
