#pragma once
#include "nex_files.h"
#include "nex_task_external.h"

#ifndef _WIN32
namespace nexrt {
// Private trusted-host bridge. Source task writes remain unsupported until the
// frontend, independent interpreter, native continuations and migration agree.
class PreparedTaskFileWrite {
  struct Payload {
    const size_t length;
    const std::unique_ptr<uint8_t[]> storage;
    explicit Payload(std::span<const uint8_t> input)
      :length(input.size()),storage(std::make_unique<uint8_t[]>(length)){
      std::copy(input.begin(),input.end(),storage.get());
    }
    std::span<const uint8_t> view()const{return {storage.get(),length};}
  };
  FileWriteLease lease;
  std::shared_ptr<const Payload> payload;
  class Operation final:public TaskExternalOperation {
    FileWriteLease lease;
    std::shared_ptr<const Payload> payload;
  public:
    Operation(FileWriteLease lease,std::shared_ptr<const Payload> payload)
      :lease(std::move(lease)),payload(std::move(payload)){}
    TaskExternalResult run(const TaskExternalControl &control)override {
      control.checkpoint();TaskExternalResult result;
      try{lease.write(payload->view(),[&]{control.checkpoint();});}
      catch(const DataError &error){
        if(!ordinaryError(error.code))throw;
        result.errorCode=error.code;result.errorMessage=error.what();
      }
      // Cancellation/revocation may win after rename. The file is already
      // committed then; suppressing source admission does not roll it back.
      control.checkpoint();return result;
    }
  };
public:
  static bool ordinaryError(const std::string &code){
    return code=="CAPABILITY"||code=="NOT_FOUND"||code=="PERMISSION"||
      code=="VALIDATION"||code=="LIMIT"||code=="E_FILE"||code=="E_UTF8";
  }
  PreparedTaskFileWrite(const FileWriteGrant &grant,const std::string &relative,
      std::span<const uint8_t> input,bool text=false):lease(grant.lease(relative)){
    if(input.size()>TextFiles::byteLimit)
      throw DataError("LIMIT","file value exceeds byte limit");
    if(text)unicodeOffsets(std::string(input.begin(),input.end()),false);
    // Copy only the visible bytes. A tiny source slice must not retain its
    // potentially much larger immutable backing allocation on the IO worker.
    payload=std::make_shared<const Payload>(input);
  }
  size_t reservation()const noexcept{return lease.retainedPathBytes()+payload->length;}
  std::shared_ptr<TaskExternalOperation> operation()const{
    return std::make_shared<Operation>(lease,payload);
  }
  Value admit(TaskExternalResult result)const{
    validateTaskExternalResult(result,reservation(),0);
    if(result.errorCode=="E_CANCELLED")throw DataError(result.errorCode,result.errorMessage);
    lease.check();
    if(!result.errorCode.empty()){
      if(!ordinaryError(result.errorCode))throw DataError("E_TASK_VALUE","unexpected file write diagnostic");
      auto value=failure(std::move(result.errorCode),std::move(result.errorMessage));lease.check();return value;
    }
    auto value=success(Value(1,true));lease.check();return value;
  }
};
}
#endif
