#include "nex_host.h"
#include "nex_files.h"
#include "nex_file_abi.h"
using nexrt::Handle;
namespace {
void prepare(){if(!nexrt::inRequestScope())nexrt::registerRuntimeCleanup(nexrt::resetFileEnvironment);}
template<class F> nexrt::Value outcome(F operation){
  try{return nexrt::success(operation());}
  catch(const nexrt::DataError &error){return nexrt::failure(error.code,error.what());}
}
Handle *openFile(Handle *path,nexrt::FileMode mode,int64_t line){
  return nexrt::hostValue(line,[&]{prepare();return outcome([&]{
    auto value=nexrt::readHandle(path);
    if(!value.object||value.object->kind!=nexrt::Data::String)throw nexrt::DataError("E_RUNTIME","file path must be a string value");
    return nexrt::Value(nexrt::fileValue(nexrt::fileOpen(value.object->text,mode,
      !nexrt::inRequestScope(),[&]{nexrt::pollHostOperation(line);})));
  });});
}
}
extern "C" {
Handle *nex_file_open_read(Handle *path,int64_t line){return openFile(path,nexrt::FileMode::Read,line);}
Handle *nex_file_open_write(Handle *path,int64_t line){return openFile(path,nexrt::FileMode::WriteTruncate,line);}
Handle *nex_file_open_append(Handle *path,int64_t line){return openFile(path,nexrt::FileMode::Append,line);}
Handle *nex_file_read(Handle *file,int64_t maximum,int64_t line){
  return nexrt::hostValue(line,[&]{return outcome([&]{
    auto resource=nexrt::fileResource(nexrt::readHandle(file).object);
    return nexrt::Value(nexrt::bytes(resource.read(maximum,[&]{nexrt::pollHostOperation(line);})));
  });});
}
Handle *nex_file_write(Handle *file,Handle *bytes,int64_t line){
  return nexrt::hostValue(line,[&]{return outcome([&]{
    auto resource=nexrt::fileResource(nexrt::readHandle(file).object);
    auto content=nexrt::byteBuffer(nexrt::readHandle(bytes).object);
    return nexrt::Value(resource.write(content,[&]{nexrt::pollHostOperation(line);}));
  });});
}
Handle *nex_file_seek(Handle *file,int64_t offset,int64_t line){
  return nexrt::hostValue(line,[&]{return outcome([&]{
    auto resource=nexrt::fileResource(nexrt::readHandle(file).object);
    return nexrt::Value(resource.seek(offset,[&]{nexrt::pollHostOperation(line);}));
  });});
}
Handle *nex_file_size(Handle *file,int64_t line){
  return nexrt::hostValue(line,[&]{return outcome([&]{
    auto resource=nexrt::fileResource(nexrt::readHandle(file).object);
    return nexrt::Value(resource.size([&]{nexrt::pollHostOperation(line);}));
  });});
}
Handle *nex_file_flush(Handle *file,int64_t line){
  return nexrt::hostValue(line,[&]{return outcome([&]{
    auto resource=nexrt::fileResource(nexrt::readHandle(file).object);
    resource.flush([&]{nexrt::pollHostOperation(line);});return nexrt::Value(1,true);
  });});
}
int64_t nex_file_close(Handle *file,int64_t line){
  return nexrt::hostOperation(line,[&]{auto resource=nexrt::fileResource(nexrt::readHandle(file).object);nexrt::pollHostOperation(line);return int64_t(resource.close());});
}
int64_t nex_file_is_open(Handle *file,int64_t line){
  return nexrt::hostOperation(line,[&]{auto resource=nexrt::fileResource(nexrt::readHandle(file).object);nexrt::pollHostOperation(line);return int64_t(resource.isOpen());});
}
Handle *nex_file_read_text(Handle *path,int64_t line){
  return nexrt::hostValue(line,[&]{prepare();return nexrt::fileReadText(nexrt::readHandle(path).object->text,
    !nexrt::inRequestScope(),[&]{nexrt::pollHostOperation(line);});});
}
Handle *nex_file_write_text(Handle *path,Handle *text,int64_t line){
  return nexrt::hostValue(line,[&]{prepare();return nexrt::fileWriteText(nexrt::readHandle(path).object->text,
    nexrt::readHandle(text).object->text,!nexrt::inRequestScope(),[&]{nexrt::pollHostOperation(line);});});
}
Handle *nex_file_read_bytes(Handle *path,int64_t line){
  return nexrt::hostValue(line,[&]{prepare();return nexrt::fileReadBytes(nexrt::readHandle(path).object->text,
    !nexrt::inRequestScope(),[&]{nexrt::pollHostOperation(line);});});
}
Handle *nex_file_write_bytes(Handle *path,Handle *bytes,int64_t line){
  return nexrt::hostValue(line,[&]{prepare();return nexrt::fileWriteBytes(nexrt::readHandle(path).object->text,
    nexrt::byteBuffer(nexrt::readHandle(bytes).object),!nexrt::inRequestScope(),[&]{nexrt::pollHostOperation(line);});});
}
}
