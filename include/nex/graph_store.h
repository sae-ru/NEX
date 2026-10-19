#pragma once
#include "nex/language.h"
struct sqlite3;
namespace nex {
// Additive schema-3 extension: old compilers can continue reading/writing their
// own tables. New readers backfill declaration metadata for an old revision.
void initializeGraphIdentities(sqlite3 *db);
void saveGraphDeclarations(sqlite3 *db,const Program &program);
bool graphDeclarationsReady(sqlite3 *db,const Program &program);
llvm::json::Value graphDeclarations(sqlite3 *db,const Program &program,
    const std::string &kind="",const std::string &symbol="",unsigned offset=0,unsigned limit=100);
llvm::json::Value graphIdentities(sqlite3 *db,const Program &program,
    const std::string &kind="all",const std::string &symbol="",unsigned offset=0,unsigned limit=100);
// Caller owns an IMMEDIATE transaction and has checked its expected HEAD.
llvm::json::Value reconcileGraphIdentities(sqlite3 *db,const Program &program,const llvm::json::Value &manifest);
llvm::json::Value resolveGraphIdentity(sqlite3 *db,const Program &program,
    const std::string &origin,const std::string &sourceRevision,const std::string &id);
std::string graphIdentityNamespace(sqlite3 *db);
}
