#pragma once
#include "nex/web.h"
namespace nex {
// Private checked-source staging, with ephemeral source maps. Public019 uses
// emitTypeScript and real checked revision/operation identities instead.
WebModule emitTaskTypeScript(const Program &,const std::map<std::string,std::string> &entries);
void writeTaskTypeScriptModule(const WebModule &,const std::string &directory);
}
