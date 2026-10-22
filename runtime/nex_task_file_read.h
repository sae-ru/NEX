#pragma once
#include "nex_files.h"
#include "nex_task_external.h"

#ifndef _WIN32
namespace nexrt {
// Experimental trusted-host adapter. It does not enable a source operation or
// supply a grant: capture must run on the explicitly authorized coordinator.
class PreparedTaskFileRead {
  FileReadLease lease;
  bool text;
  class Operation final:public TaskExternalOperation {
    FileReadLease lease;
  public:
    explicit Operation(FileReadLease lease):lease(std::move(lease)){}
    TaskExternalResult run(const TaskExternalControl &control)override {
      control.checkpoint();TaskExternalResult result;
      try{result.bytes=lease.read([&]{control.checkpoint();});}
      catch(const DataError &error){
        // Ordinary filesystem failures travel as raw diagnostics. Cancellation,
        // resource revocation and execution limits retain their fatal priority.
        if(error.code!="NOT_FOUND"&&error.code!="PERMISSION"&&error.code!="VALIDATION"&&error.code!="LIMIT"&&error.code!="E_FILE")throw;
        result.errorCode=error.code;result.errorMessage=error.what();
      }
      control.checkpoint();return result;
    }
  };
public:
  PreparedTaskFileRead(const FileReadGrant &grant,const std::string &relative,bool text)
    :lease(grant.lease(relative)),text(text){}
  // Compatibility for private host probes only. Resumable source adapters must
  // use the explicit coordinator-captured grant overload above.
  PreparedTaskFileRead(const std::string &relative,bool text,bool environmentAllowed=true)
    :lease(captureFileReadLease(relative,environmentAllowed)),text(text){}
  // Charge the maximum result and bounded retained path, including a view's
  // entire owned payload rather than trusting a small slice length.
  static constexpr size_t reservation=TextFiles::byteLimit+TextFiles::pathLimit;
  std::shared_ptr<TaskExternalOperation> operation()const{return std::make_shared<Operation>(lease);}
  Value admit(TaskExternalResult result)const {
    // Revocation can win after the last worker poll or before mailbox delivery.
    // This check and all source Value construction belong to the coordinator.
    lease.check();
    if(result.errorCode=="E_LIMIT"||result.errorCode=="E_MEMORY"||result.errorCode=="E_TIMEOUT"||result.errorCode=="E_CANCELLED")
      throw DataError(result.errorCode,result.errorMessage);
    if(!result.errorCode.empty())return failure(std::move(result.errorCode),std::move(result.errorMessage));
    if(result.bytes.size()>TextFiles::byteLimit)throw DataError("E_TASK_VALUE","external read returned an oversized payload");
    try{
      if(text)return success(Value(string(std::string(result.bytes.begin(),result.bytes.end()))));
      // Published source storage owns only its actual bytes. The worker's
      // maximum-size read reservation need not follow a tiny source value.
      return success(Value(bytes(ByteBuffer::copy(result.bytes))));
    }catch(const DataError &error){
      if(error.code!="E_UTF8")throw;
      return failure(error.code,error.what());
    }
  }
};
}
#endif
