#pragma once
#include "nex/language.h"
#include "nex/change_store.h"
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
// Explicit same-store migration. Preflight opens the existing graph read-only;
// only apply may publish a checked target with a guarded HEAD transition.
struct GraphMigrationPlan {
  std::filesystem::path directory;
  SourceLanguage target=currentSourceLanguage;
  std::string originRevision,originLanguage,originSourceHash,expectedHead;
  std::string identityNamespace;
  std::string targetRevision,targetSourceHash;
  llvm::json::Value sources=nullptr;
  bool originVerified=false,candidateUsed=false;
};
GraphMigrationPlan preflightGraphMigration(const std::filesystem::path &directory,
    const std::string &originRevision,const std::string &expectedHead,
    SourceLanguage target=currentSourceLanguage,const llvm::json::Object *reviewedCandidate=nullptr);
llvm::json::Object applyGraphMigration(const GraphMigrationPlan &,
    const ChangeInfo &change={"migrate","versioned source recheck","","",""});
}
