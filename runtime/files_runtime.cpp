#include "nex_host.h"
#include "nex_files.h"
using nexrt::Handle;
namespace {
void prepare(){if(!nexrt::inRequestScope())nexrt::registerRuntimeCleanup(nexrt::resetFileEnvironment);}
}
extern "C" {
Handle *nex_file_read_text(Handle *path,int64_t line){
  return nexrt::hostValue(line,[&]{prepare();return nexrt::fileReadText(nexrt::readHandle(path).object->text,
    !nexrt::inRequestScope(),[&]{nexrt::pollHostOperation(line);});});
}
Handle *nex_file_write_text(Handle *path,Handle *text,int64_t line){
  return nexrt::hostValue(line,[&]{prepare();return nexrt::fileWriteText(nexrt::readHandle(path).object->text,
    nexrt::readHandle(text).object->text,!nexrt::inRequestScope(),[&]{nexrt::pollHostOperation(line);});});
}
}
