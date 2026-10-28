#pragma once
#include "nex_task_file_stream.h"

#ifndef _WIN32
namespace nexrt {
// Coordinator-only bridge for explicit private024 source continuations.
// The physical operation retains only the prepared raw/typed host payload.
class PreparedSourceTaskFile {
  std::shared_ptr<PreparedTaskFileOpen> opened;
  std::shared_ptr<PreparedTaskFileStream> stream;
  std::optional<Value> immediate;
  ResourceRegionAuthority region;
public:
  PreparedSourceTaskFile(const std::string &operation,std::span<const Value> args,
      const FileReadGrant &reads,const FileWriteGrant &writes,
      const ResourceRegionAuthority &actor,const std::shared_ptr<ResourceExecutor> &cleanup):region(actor){
    actor.check();
    auto arity=[&](size_t count){if(args.size()!=count)throw DataError("E_TASK_STATE","source file argument count differs");};
    auto integer=[&](size_t at){if(args[at].tag!=Value::Integer)throw DataError("E_TASK_STATE","source file argument is not i64");return args[at].scalar;};
    if(operation=="file_open_read"||operation=="file_open_write"||operation=="file_open_append"){
      arity(1);
      if(args[0].tag!=Value::Object||!args[0].object||args[0].object->kind!=Data::String)
        throw DataError("E_TASK_STATE","source file path is not str");
      auto lease=operation=="file_open_read"?reads.openRead(args[0].object->text):
          writes.openWrite(args[0].object->text,operation=="file_open_append"?FileMode::Append:FileMode::WriteTruncate);
      if(!cleanup)throw DataError("E_RESOURCE_EXECUTOR","source file open has no owning cleanup executor");
      opened=std::make_shared<PreparedTaskFileOpen>(std::move(lease),actor,cleanup);return;
    }
    const bool two=operation=="file_read"||operation=="file_write"||operation=="file_seek";
    arity(two?2:1);
    if(args[0].tag!=Value::Object||!args[0].object||args[0].object->kind!=Data::File)
      throw DataError("E_TASK_STATE","source stream operand is not file");
    const auto &file=fileResource(args[0].object);file.checkRegion(actor);
    if(operation=="file_close"){immediate=Value(file.close(),true);return;}
    if(operation=="file_is_open"){immediate=Value(file.isOpen(),true);return;}
    if(operation=="file_read")stream=std::make_shared<PreparedTaskFileStream>(PreparedTaskFileStream::read(file,integer(1),actor));
    else if(operation=="file_write"){
      if(args[1].tag!=Value::Object||!args[1].object||args[1].object->kind!=Data::Bytes)
        throw DataError("E_TASK_STATE","source file write argument is not bytes");
      stream=std::make_shared<PreparedTaskFileStream>(PreparedTaskFileStream::write(file,byteBuffer(args[1].object).view(),actor));
    }else if(operation=="file_seek")stream=std::make_shared<PreparedTaskFileStream>(PreparedTaskFileStream::seek(file,integer(1),actor));
    else if(operation=="file_size")stream=std::make_shared<PreparedTaskFileStream>(PreparedTaskFileStream::size(file,actor));
    else if(operation=="file_flush")stream=std::make_shared<PreparedTaskFileStream>(PreparedTaskFileStream::flush(file,actor));
    else throw DataError("E_TASK_STATE","unknown source file operation");
  }
  bool external()const noexcept{return !immediate.has_value();}
  size_t reservation()const noexcept{return opened?opened->reservation():stream?stream->reservation():0;}
  std::shared_ptr<TaskExternalOperation> operation()const{
    if(opened)return opened->operation();if(stream)return stream->operation();
    throw DataError("E_TASK_STATE","immediate file operation has no worker");
  }
  Value admit(TaskExternalResult raw={},const std::function<void()> &poll={})const{
    auto open=opened;auto work=stream;auto value=immediate;auto checkpoint=poll;auto actor=region;
    if(value){if(checkpoint)checkpoint();actor.check();return std::move(*value);}
    if(work)return work->admit(std::move(raw),checkpoint);
    if(!open)throw DataError("E_TASK_STATE","source file operation has no outcome");
    try{return success(Value(fileValue(open->admit(std::move(raw),checkpoint))));}
    catch(const DataError &error){if(!task_file_stream_detail::ordinary(error.code))throw;return failure(error.code,error.what());}
  }
};
}
#endif
