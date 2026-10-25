#pragma once
#include "nex_files.h"
#include "nex_task_external.h"
#include <limits>
#include <mutex>
#include <optional>
#include <utility>

#ifndef _WIN32
namespace nexrt {
namespace task_file_stream_detail {
inline bool ordinary(const std::string &code){
  return code=="CAPABILITY"||code=="NOT_FOUND"||code=="PERMISSION"||code=="VALIDATION"||
    code=="LIMIT"||code=="E_RANGE"||code=="E_FILE"||code=="E_UTF8"||
    code=="E_RESOURCE_CLOSED"||code=="E_RESOURCE_LIMIT";
}
inline std::vector<uint8_t> scalar(int64_t value){
  if(value<0)throw DataError("E_TASK_VALUE","file stream returned a negative scalar");
  std::vector<uint8_t> bytes(8);
  for(unsigned i=0;i<8;++i)bytes[i]=uint8_t(uint64_t(value)>>(8*i));
  return bytes;
}
inline int64_t scalar(const std::vector<uint8_t> &bytes){
  if(bytes.size()!=8||(bytes[7]&128))throw DataError("E_TASK_VALUE","invalid file stream scalar reply");
  uint64_t value=0;for(unsigned i=0;i<8;++i)value|=uint64_t(bytes[i])<<(8*i);
  return int64_t(value);
}
}

// Trusted-host foundation only; language023 still rejects file-bearing tasks.
// The pool carries raw bytes/scalars. Only the coordinator constructs Values.
class PreparedTaskFileStream {
  enum class Action {Read,Write,Seek,Size,Flush};
  struct Payload {
    const size_t size;
    const std::unique_ptr<uint8_t[]> bytes;
    explicit Payload(std::span<const uint8_t> input):size(input.size()),bytes(std::make_unique<uint8_t[]>(size)){
      std::copy(input.begin(),input.end(),bytes.get());
    }
    std::span<const uint8_t> view()const{return {bytes.get(),size};}
  };
  struct State {
    FileStreamLease lease;
    const Action action;
    const int64_t argument;
    std::shared_ptr<const Payload> payload;
    const size_t reservation,maximumReply;
    std::mutex mutex;
    bool started=false,completed=false,admitted=false;
    State(FileStreamLease lease,Action action,int64_t argument,std::shared_ptr<const Payload> payload,size_t reservation,size_t maximumReply)
      :lease(std::move(lease)),action(action),argument(argument),payload(std::move(payload)),reservation(reservation),maximumReply(maximumReply){}
  };
  std::shared_ptr<State> state;
  explicit PreparedTaskFileStream(std::shared_ptr<State> state):state(std::move(state)){}
  class Operation final:public TaskExternalOperation {
    std::shared_ptr<State> state;
  public:
    explicit Operation(std::shared_ptr<State> state):state(std::move(state)){}
    TaskExternalResult run(const TaskExternalControl &control)override{
      {std::lock_guard lock(state->mutex);if(std::exchange(state->started,true))throw DataError("E_TASK_STATE","file stream operation already started");}
      control.checkpoint();TaskExternalResult raw;
      auto poll=[&]{control.checkpoint();state->lease.check();};
      try{
        state->lease.check();
        switch(state->action){
          case Action::Read:raw.bytes=state->lease.read(state->argument,poll);break;
          case Action::Write:raw.bytes=task_file_stream_detail::scalar(state->lease.write(state->payload->view(),poll));break;
          case Action::Seek:raw.bytes=task_file_stream_detail::scalar(state->lease.seek(state->argument,poll));break;
          case Action::Size:raw.bytes=task_file_stream_detail::scalar(state->lease.size(poll));break;
          case Action::Flush:state->lease.flush(poll);break;
        }
        state->lease.check();
      }catch(const DataError &error){
        if(!task_file_stream_detail::ordinary(error.code))throw;
        raw.bytes={};raw.errorCode=error.code;raw.errorMessage=error.what();
      }
      control.checkpoint();{std::lock_guard lock(state->mutex);state->completed=true;}return raw;
    }
  };
public:
  static PreparedTaskFileStream read(const FileResource &file,int64_t maximum,const ResourceRegionAuthority &actor={}){
    auto lease=file.leaseInRegion(actor);lease.checkRead(maximum);
    return PreparedTaskFileStream(std::make_shared<State>(std::move(lease),Action::Read,maximum,nullptr,size_t(maximum),size_t(maximum)));
  }
  static PreparedTaskFileStream write(const FileResource &file,std::span<const uint8_t> input,const ResourceRegionAuthority &actor={}){
    auto lease=file.leaseInRegion(actor);lease.checkWrite(input.size());auto payload=std::make_shared<const Payload>(input);
    return PreparedTaskFileStream(std::make_shared<State>(std::move(lease),Action::Write,0,std::move(payload),input.size()+8,8));
  }
  static PreparedTaskFileStream seek(const FileResource &file,int64_t offset,const ResourceRegionAuthority &actor={}){
    auto lease=file.leaseInRegion(actor);lease.checkSeek(offset);
    return PreparedTaskFileStream(std::make_shared<State>(std::move(lease),Action::Seek,offset,nullptr,8,8));
  }
  static PreparedTaskFileStream size(const FileResource &file,const ResourceRegionAuthority &actor={}){
    return PreparedTaskFileStream(std::make_shared<State>(file.leaseInRegion(actor),Action::Size,0,nullptr,8,8));
  }
  static PreparedTaskFileStream flush(const FileResource &file,const ResourceRegionAuthority &actor={}){
    auto lease=file.leaseInRegion(actor);lease.checkWrite(0);
    return PreparedTaskFileStream(std::make_shared<State>(std::move(lease),Action::Flush,0,nullptr,0,0));
  }
  size_t reservation()const noexcept{return state?state->reservation:0;}
  std::shared_ptr<TaskExternalOperation> operation()const{
    if(!state)throw DataError("E_TASK_STATE","file stream request was moved");return std::make_shared<Operation>(state);
  }
  Value admit(TaskExternalResult raw,const std::function<void()> &poll={})const{
    auto retained=state;if(!retained)throw DataError("E_TASK_STATE","file stream request was moved");
    validateTaskExternalResult(raw,retained->reservation,retained->maximumReply);auto callback=poll;
    {std::lock_guard lock(retained->mutex);if(!retained->completed||std::exchange(retained->admitted,true))throw DataError("E_TASK_STATE","file stream result is absent or already admitted");}
    if(!raw.errorCode.empty()&&(!raw.bytes.empty()||!task_file_stream_detail::ordinary(raw.errorCode)))
      throw DataError("E_TASK_VALUE","unexpected file stream diagnostic");
    if(callback)callback();
    try{
      retained->lease.check();Value value;
      if(!raw.errorCode.empty())value=failure(std::move(raw.errorCode),std::move(raw.errorMessage));
      else if(retained->action==Action::Read)value=success(Value(bytes(ByteBuffer::copy(raw.bytes))));
      else if(retained->action==Action::Flush){
        if(!raw.bytes.empty())throw DataError("E_TASK_VALUE","flush reply cannot contain bytes");
        value=success(Value(1,true));
      }else{
        auto count=task_file_stream_detail::scalar(raw.bytes);
        if((retained->action==Action::Write&&uint64_t(count)>retained->payload->size)||
           (retained->action==Action::Seek&&count!=retained->argument))throw DataError("E_TASK_VALUE","file stream scalar violates its request");
        value=success(Value(count));
      }
      retained->lease.check();if(callback)callback();retained->lease.check();return value;
    }catch(const DataError &error){
      if(error.code!="E_RESOURCE_CLOSED")throw;
      if(callback)callback();
      try{retained->lease.check();}catch(const DataError &revoked){if(revoked.code!="E_RESOURCE_CLOSED")throw;}
      return failure(error.code,error.what());
    }
  }
};

// A newly opened owner uses a one-shot typed side channel, never a fabricated
// source file ID in raw bytes. Destruction/discard closes unpublished owners.
class PreparedTaskFileOpen {
  struct State {
    FileOpenLease lease;
    ResourceRegionAuthority region;
    std::mutex mutex;
    std::optional<FileResource> file;
    bool started=false,completed=false,admitted=false,discarded=false;
    std::shared_ptr<ResourceExecutor> cleanup;
    explicit State(FileOpenLease lease,ResourceRegionAuthority region,std::shared_ptr<ResourceExecutor> cleanup)
      :lease(std::move(lease)),region(std::move(region)),cleanup(std::move(cleanup)){}
  };
  std::shared_ptr<State> state;
  class Operation final:public TaskExternalOperation {
    std::shared_ptr<State> state;
  public:
    explicit Operation(std::shared_ptr<State> state):state(std::move(state)){}
    TaskExternalResult run(const TaskExternalControl &control)override{
      {std::lock_guard lock(state->mutex);
        if(std::exchange(state->started,true))throw DataError("E_TASK_STATE","file open operation already started");
        if(state->discarded)throw DataError("E_CANCELLED","file open result was discarded");
      }
      control.checkpoint();TaskExternalResult raw;std::optional<FileResource> file;
      auto poll=[&]{control.checkpoint();state->lease.check();};
      try{state->lease.check();file=state->lease.openInRegion(state->region,poll,state->cleanup);poll();}
      catch(const DataError &error){
        if(!task_file_stream_detail::ordinary(error.code))throw;
        raw.errorCode=error.code;raw.errorMessage=error.what();file.reset();
      }
      control.checkpoint();
      {std::lock_guard lock(state->mutex);state->completed=true;
        if(!state->discarded){state->file=std::move(file);file.reset();}
      }
      return raw;
    }
  };
public:
  explicit PreparedTaskFileOpen(FileOpenLease lease,ResourceRegionAuthority region={},std::shared_ptr<ResourceExecutor> cleanup={}){lease.check();if(region)region.check();state=std::make_shared<State>(std::move(lease),std::move(region),std::move(cleanup));}
  PreparedTaskFileOpen(const PreparedTaskFileOpen&)=delete;
  PreparedTaskFileOpen &operator=(const PreparedTaskFileOpen&)=delete;
  PreparedTaskFileOpen(PreparedTaskFileOpen&&)=default;
  PreparedTaskFileOpen &operator=(PreparedTaskFileOpen &&other)noexcept{
    if(this!=&other){discard();state=std::move(other.state);}return *this;
  }
  ~PreparedTaskFileOpen(){discard();}
  size_t reservation()const noexcept{return state?state->lease.retainedPathBytes():0;}
  std::shared_ptr<TaskExternalOperation> operation()const{
    if(!state)throw DataError("E_TASK_STATE","file open request was moved");return std::make_shared<Operation>(state);
  }
  void discard()const noexcept{
    if(!state)return;std::optional<FileResource> retired;
    {std::lock_guard lock(state->mutex);state->discarded=true;retired=std::move(state->file);state->file.reset();}
  }
  FileResource admit(TaskExternalResult raw,const std::function<void()> &poll={})const{
    auto retained=state;if(!retained)throw DataError("E_TASK_STATE","file open request was moved");
    validateTaskExternalResult(raw,reservation(),0);auto callback=poll;
    std::optional<FileResource> file;
    {std::lock_guard lock(retained->mutex);
      if(!retained->completed||retained->discarded||std::exchange(retained->admitted,true))throw DataError("E_TASK_STATE","file open result is absent or already admitted");
      file=std::move(retained->file);retained->file.reset();
    }
    if(!raw.bytes.empty()||raw.errorCode.empty()!=bool(file)||(!raw.errorCode.empty()&&!task_file_stream_detail::ordinary(raw.errorCode)))
      throw DataError("E_TASK_VALUE","file open wakeup differs from its typed outcome");
    if(callback)callback();retained->lease.check();if(retained->region)retained->region.check();
    if(!raw.errorCode.empty())throw DataError(raw.errorCode,raw.errorMessage);
    if(!file->isOpen())throw DataError("E_RESOURCE_SCOPE","newly opened file has been revoked");
    if(callback)callback();retained->lease.check();if(retained->region)retained->region.check();return std::move(*file);
  }
};
}
#endif
