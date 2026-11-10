#include "nex_host.h"
#include "nex_files.h"
#include "nex_file_abi.h"
using nexrt::Handle;
namespace {
void prepare(){if(!nexrt::inRequestScope())nexrt::registerRuntimeCleanup(nexrt::resetFileEnvironment);}
template<class F> nexrt::Value outcome(F operation){
  try{return nexrt::success(operation());}
  catch(const nexrt::DataError &error){return nexrt::failure(error.code,error.message);}
}
Handle *openFile(Handle *path,nexrt::FileMode mode,nexrt::SourceLocation line){
  return nexrt::hostValue(line,[&]{prepare();return outcome([&]{
    auto value=nexrt::readHandle(path);
    if(!value.object||value.object->kind!=nexrt::Data::String)throw nexrt::DataError("E_RUNTIME","file path must be a string value");
    return nexrt::Value(nexrt::fileValue(nexrt::fileOpen(value.object->text,mode,
      !nexrt::inRequestScope(),[&]{nexrt::pollHostOperation(line);})));
  });});
}
}
extern "C" {
static Handle * impl_nex_file_open_read(Handle *path,nexrt::SourceLocation line){
  return nexrt::hostOperation(line,[&]() -> Handle * {return openFile(path,nexrt::FileMode::Read,line);});
}
Handle * nex_file_open_read(Handle *path,int64_t line){return impl_nex_file_open_read(path, line);}
Handle * nex_file_open_read_at(Handle *path,int64_t line, const nexrt::NativeSite *nex_site){return impl_nex_file_open_read(path, nexrt::SourceLocation{line,nex_site});}
static Handle * impl_nex_file_open_write(Handle *path,nexrt::SourceLocation line){
  return nexrt::hostOperation(line,[&]() -> Handle * {return openFile(path,nexrt::FileMode::WriteTruncate,line);});
}
Handle * nex_file_open_write(Handle *path,int64_t line){return impl_nex_file_open_write(path, line);}
Handle * nex_file_open_write_at(Handle *path,int64_t line, const nexrt::NativeSite *nex_site){return impl_nex_file_open_write(path, nexrt::SourceLocation{line,nex_site});}
static Handle * impl_nex_file_open_append(Handle *path,nexrt::SourceLocation line){
  return nexrt::hostOperation(line,[&]() -> Handle * {return openFile(path,nexrt::FileMode::Append,line);});
}
Handle * nex_file_open_append(Handle *path,int64_t line){return impl_nex_file_open_append(path, line);}
Handle * nex_file_open_append_at(Handle *path,int64_t line, const nexrt::NativeSite *nex_site){return impl_nex_file_open_append(path, nexrt::SourceLocation{line,nex_site});}
static Handle * impl_nex_file_read(Handle *file,int64_t maximum,nexrt::SourceLocation line){
  return nexrt::hostOperation(line,[&]() -> Handle * {
  return nexrt::hostValue(line,[&]{return outcome([&]{
    auto resource=nexrt::fileResource(nexrt::readHandle(file).object);
    return nexrt::Value(nexrt::bytes(resource.read(maximum,[&]{nexrt::pollHostOperation(line);})));
  });});
});
}
Handle * nex_file_read(Handle *file,int64_t maximum,int64_t line){return impl_nex_file_read(file, maximum, line);}
Handle * nex_file_read_at(Handle *file,int64_t maximum,int64_t line, const nexrt::NativeSite *nex_site){return impl_nex_file_read(file, maximum, nexrt::SourceLocation{line,nex_site});}
static Handle * impl_nex_file_write(Handle *file,Handle *bytes,nexrt::SourceLocation line){
  return nexrt::hostOperation(line,[&]() -> Handle * {
  return nexrt::hostValue(line,[&]{return outcome([&]{
    auto resource=nexrt::fileResource(nexrt::readHandle(file).object);
    auto content=nexrt::byteBuffer(nexrt::readHandle(bytes).object);
    return nexrt::Value(resource.write(content,[&]{nexrt::pollHostOperation(line);}));
  });});
});
}
Handle * nex_file_write(Handle *file,Handle *bytes,int64_t line){return impl_nex_file_write(file, bytes, line);}
Handle * nex_file_write_at(Handle *file,Handle *bytes,int64_t line, const nexrt::NativeSite *nex_site){return impl_nex_file_write(file, bytes, nexrt::SourceLocation{line,nex_site});}
static Handle * impl_nex_file_seek(Handle *file,int64_t offset,nexrt::SourceLocation line){
  return nexrt::hostOperation(line,[&]() -> Handle * {
  return nexrt::hostValue(line,[&]{return outcome([&]{
    auto resource=nexrt::fileResource(nexrt::readHandle(file).object);
    return nexrt::Value(resource.seek(offset,[&]{nexrt::pollHostOperation(line);}));
  });});
});
}
Handle * nex_file_seek(Handle *file,int64_t offset,int64_t line){return impl_nex_file_seek(file, offset, line);}
Handle * nex_file_seek_at(Handle *file,int64_t offset,int64_t line, const nexrt::NativeSite *nex_site){return impl_nex_file_seek(file, offset, nexrt::SourceLocation{line,nex_site});}
static Handle * impl_nex_file_size(Handle *file,nexrt::SourceLocation line){
  return nexrt::hostOperation(line,[&]() -> Handle * {
  return nexrt::hostValue(line,[&]{return outcome([&]{
    auto resource=nexrt::fileResource(nexrt::readHandle(file).object);
    return nexrt::Value(resource.size([&]{nexrt::pollHostOperation(line);}));
  });});
});
}
Handle * nex_file_size(Handle *file,int64_t line){return impl_nex_file_size(file, line);}
Handle * nex_file_size_at(Handle *file,int64_t line, const nexrt::NativeSite *nex_site){return impl_nex_file_size(file, nexrt::SourceLocation{line,nex_site});}
static Handle * impl_nex_file_flush(Handle *file,nexrt::SourceLocation line){
  return nexrt::hostOperation(line,[&]() -> Handle * {
  return nexrt::hostValue(line,[&]{return outcome([&]{
    auto resource=nexrt::fileResource(nexrt::readHandle(file).object);
    resource.flush([&]{nexrt::pollHostOperation(line);});return nexrt::Value(1,true);
  });});
});
}
Handle * nex_file_flush(Handle *file,int64_t line){return impl_nex_file_flush(file, line);}
Handle * nex_file_flush_at(Handle *file,int64_t line, const nexrt::NativeSite *nex_site){return impl_nex_file_flush(file, nexrt::SourceLocation{line,nex_site});}
static int64_t impl_nex_file_close(Handle *file,nexrt::SourceLocation line){
  return nexrt::hostOperation(line,[&]() -> int64_t {
  return nexrt::hostOperation(line,[&]{auto resource=nexrt::fileResource(nexrt::readHandle(file).object);nexrt::pollHostOperation(line);return int64_t(resource.close());});
});
}
int64_t nex_file_close(Handle *file,int64_t line){return impl_nex_file_close(file, line);}
int64_t nex_file_close_at(Handle *file,int64_t line, const nexrt::NativeSite *nex_site){return impl_nex_file_close(file, nexrt::SourceLocation{line,nex_site});}
static int64_t impl_nex_file_is_open(Handle *file,nexrt::SourceLocation line){
  return nexrt::hostOperation(line,[&]() -> int64_t {
  return nexrt::hostOperation(line,[&]{auto resource=nexrt::fileResource(nexrt::readHandle(file).object);nexrt::pollHostOperation(line);return int64_t(resource.isOpen());});
});
}
int64_t nex_file_is_open(Handle *file,int64_t line){return impl_nex_file_is_open(file, line);}
int64_t nex_file_is_open_at(Handle *file,int64_t line, const nexrt::NativeSite *nex_site){return impl_nex_file_is_open(file, nexrt::SourceLocation{line,nex_site});}
static Handle * impl_nex_file_read_text(Handle *path,nexrt::SourceLocation line){
  return nexrt::hostOperation(line,[&]() -> Handle * {
  return nexrt::hostValue(line,[&]{prepare();return nexrt::fileReadText(nexrt::readHandle(path).object->text,
    !nexrt::inRequestScope(),[&]{nexrt::pollHostOperation(line);});});
});
}
Handle * nex_file_read_text(Handle *path,int64_t line){return impl_nex_file_read_text(path, line);}
Handle * nex_file_read_text_at(Handle *path,int64_t line, const nexrt::NativeSite *nex_site){return impl_nex_file_read_text(path, nexrt::SourceLocation{line,nex_site});}
static Handle * impl_nex_file_write_text(Handle *path,Handle *text,nexrt::SourceLocation line){
  return nexrt::hostOperation(line,[&]() -> Handle * {
  return nexrt::hostValue(line,[&]{prepare();return nexrt::fileWriteText(nexrt::readHandle(path).object->text,
    nexrt::readHandle(text).object->text,!nexrt::inRequestScope(),[&]{nexrt::pollHostOperation(line);});});
});
}
Handle * nex_file_write_text(Handle *path,Handle *text,int64_t line){return impl_nex_file_write_text(path, text, line);}
Handle * nex_file_write_text_at(Handle *path,Handle *text,int64_t line, const nexrt::NativeSite *nex_site){return impl_nex_file_write_text(path, text, nexrt::SourceLocation{line,nex_site});}
static Handle * impl_nex_file_read_bytes(Handle *path,nexrt::SourceLocation line){
  return nexrt::hostOperation(line,[&]() -> Handle * {
  return nexrt::hostValue(line,[&]{prepare();return nexrt::fileReadBytes(nexrt::readHandle(path).object->text,
    !nexrt::inRequestScope(),[&]{nexrt::pollHostOperation(line);});});
});
}
Handle * nex_file_read_bytes(Handle *path,int64_t line){return impl_nex_file_read_bytes(path, line);}
Handle * nex_file_read_bytes_at(Handle *path,int64_t line, const nexrt::NativeSite *nex_site){return impl_nex_file_read_bytes(path, nexrt::SourceLocation{line,nex_site});}
static Handle * impl_nex_file_write_bytes(Handle *path,Handle *bytes,nexrt::SourceLocation line){
  return nexrt::hostOperation(line,[&]() -> Handle * {
  return nexrt::hostValue(line,[&]{prepare();return nexrt::fileWriteBytes(nexrt::readHandle(path).object->text,
    nexrt::byteBuffer(nexrt::readHandle(bytes).object),!nexrt::inRequestScope(),[&]{nexrt::pollHostOperation(line);});});
});
}
Handle * nex_file_write_bytes(Handle *path,Handle *bytes,int64_t line){return impl_nex_file_write_bytes(path, bytes, line);}
Handle * nex_file_write_bytes_at(Handle *path,Handle *bytes,int64_t line, const nexrt::NativeSite *nex_site){return impl_nex_file_write_bytes(path, bytes, nexrt::SourceLocation{line,nex_site});}
}
