#pragma once
#include "nex/language.h"

namespace nex {
// Private source integration entry points. Public language0.18 parsing, stored
// revisions and emitted programs must not accidentally acquire task semantics.
Program parseTaskPrototype(std::string source,std::string path,
    bool editorNames=false,bool editorDetails=false);
Program loadTaskPrototype(const std::string &entry,const std::string &root,
    const std::map<std::string,std::string> &overlays={});
const std::set<std::string> &taskBuiltins();
bool isPublicTaskLanguage(const Program &program);
bool supportsTaskFileReads(const Program &program);
// Explicit private023 integration; public022 and historical execution stay intact.
bool supportsTaskFileWrites(const Program &program);
// Explicit private024 source integration; ordinary CLI stays023.
bool supportsTaskFileStreams(const Program &program);
bool taskFileWriteOperation(const std::string &operation);
// Private022 source prototype; current public language021 remains unchanged.
bool supportsTaskForeignCalls(const Program &program);
bool containsTaskAuthority(const Program &program,const Type &type);
bool usesTaskEffects(const Program &program,const std::string &entry);
void rejectUnloweredTasks(const Program &program,const char *operation);
void rejectUnarchivedTasks(const Program &program,const char *operation);
}
