#pragma once
#include "nex/web.h"
namespace nex {
// Private checked-source staging only. Public emit/build/archive guards remain.
WebModule emitTaskTypeScript(const Program &,const std::map<std::string,std::string> &entries);
void writeTaskTypeScriptModule(const WebModule &,const std::string &directory);
}
