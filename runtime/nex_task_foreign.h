#pragma once
#include "nex_foreign.h"
#include "nex_ffi_types.h"
#include "nex_task_external.h"
#include <mutex>
#include <optional>
#include <utility>

namespace nexrt {
// Private source adapter. Copied results use the generic byte ticket. Resource
// results use a one-shot typed host side channel; the generic ticket carries
// only its empty wakeup. Source Values and C tokens stay on their own threads.
class PreparedTaskForeignCall {
  struct State {
    CapturedForeignScope scope;
    ForeignFunction function;
    foreign_detail::TaskCodec codec;
    std::vector<uint8_t> arguments;
    ResourceRegionAuthority region;
    ResourceAccess values;
    std::shared_ptr<ResourceExecutor> cleanup;
    std::shared_ptr<void> transport;
    std::optional<foreign_detail::TaskForeignSnapshot> ownedArguments,ownedResult;
    std::mutex mutex;
    const bool owned;
    bool started=false,completed=false,admitted=false;
    State(CapturedForeignScope scope,ForeignFunction function,foreign_detail::TaskCodec codec,
          std::vector<uint8_t> arguments,bool owned)
      :scope(std::move(scope)),function(std::move(function)),codec(std::move(codec)),arguments(std::move(arguments)),owned(owned){}
  };
  std::shared_ptr<State> state;
  class Operation final:public TaskExternalOperation {
    std::shared_ptr<State> state;
  public:
    explicit Operation(std::shared_ptr<State> value):state(std::move(value)){}
    TaskExternalResult run(const TaskExternalControl &control)override{
      auto poll=[&]{state->scope.check();control.checkpoint();state->scope.check();};
      poll();TaskExternalResult raw;
      if(state->owned){
        {std::lock_guard lock(state->mutex);if(std::exchange(state->started,true))throw DataError("E_TASK_STATE","owned foreign operation already started");}
        foreign_detail::TaskForeignSnapshot output;
        {
          auto arguments=state->codec.restoreArguments(*state->ownedArguments,state->region,poll);
          auto result=state->function.invokeInRegion(arguments,state->values,state->region,state->cleanup,poll,state->scope.callLimits());
          output=state->codec.snapshotResult(result,state->region,poll);
        }
        // The C invocation and its local leases/tokens have physically ended.
        // Cancellation may still discard this result; admission never renews it.
        poll();std::lock_guard lock(state->mutex);state->ownedResult=std::move(output);state->completed=true;return raw;
      }
      {
        // The worker reconstructs its own owned values and fresh C call/type/
        // resource tokens. None of these values leave this physical call.
        auto arguments=state->codec.decodeArguments(state->arguments,poll);
        auto result=state->function.invoke(arguments,poll,state->scope.callLimits());
        raw.bytes=state->codec.encodeResult(result,poll);
      }
      poll();return raw;
    }
  };
public:
  PreparedTaskForeignCall(const CapturedForeignScope &scope,const std::string &binding,
      std::span<const Value> arguments,const std::function<void()> &poll={},
      ResourceRegionAuthority region={},std::shared_ptr<ResourceExecutor> cleanup={}){
    std::vector<Value> retained(arguments.begin(),arguments.end());
    // Reject unsupported types and hidden values before loading native code.
    auto signature=scope.signature(binding);const bool owned=signature.hasResources();
    std::shared_ptr<void> transport;
    if(owned){
      if(!region||!cleanup)throw DataError("E_RESOURCE_SCOPE","task resource calls require explicit owner and cleanup executor");
      region.check();transport=scope.reserveTransport();
    }
    foreign_detail::TaskCodec codec(signature,owned);
    std::vector<uint8_t> snapshot;
    std::optional<foreign_detail::TaskForeignSnapshot> ownerSnapshot;
    if(owned)ownerSnapshot=codec.snapshotArguments(retained,region,poll);
    else snapshot=codec.encodeArguments(retained,poll);
    auto function=scope.bind(binding,poll);
    state=std::make_shared<State>(scope,std::move(function),std::move(codec),std::move(snapshot),owned);
    if(owned){state->ownedArguments=std::move(ownerSnapshot);state->region=std::move(region);state->values=scope.valueAccess();state->cleanup=std::move(cleanup);state->transport=std::move(transport);}
    scope.check();
  }
  // Bounded retained input, exact signature and two codec schemas, and output.
  // This is a transport reservation, not a total native/vendor-memory bound.
  static constexpr size_t reservation=4*1048576;
  std::shared_ptr<TaskExternalOperation> operation()const{return std::make_shared<Operation>(state);}
  Value admit(TaskExternalResult raw,const std::function<void()> &poll={})const{
    validateTaskExternalResult(raw,reservation,foreign_detail::TaskCodec::byteLimit);
    state->scope.check();
    if(!state->function.isOpen())throw DataError("E_RESOURCE_SCOPE","task foreign module authorization has ended");
    if(!raw.errorCode.empty())throw DataError(raw.errorCode,raw.errorMessage);
    if(state->owned){
      if(!raw.bytes.empty())throw DataError("E_TASK_VALUE","owned foreign wakeup cannot contain copied payload");
      std::shared_ptr<void> retiredReservation;
      foreign_detail::TaskForeignSnapshot snapshot;
      std::optional<foreign_detail::TaskForeignSnapshot> retiredInput;
      {std::lock_guard lock(state->mutex);
        if(!state->completed||!state->ownedResult||std::exchange(state->admitted,true))throw DataError("E_TASK_STATE","owned foreign result is absent or already admitted");
        snapshot=std::move(*state->ownedResult);state->ownedResult.reset();
        retiredInput=std::exchange(state->ownedArguments,std::nullopt);
        retiredReservation=std::move(state->transport);
      }
      state->region.check();auto result=state->codec.restoreResult(snapshot,state->region,poll);state->scope.check();
      if(!state->function.isOpen())throw DataError("E_RESOURCE_SCOPE","task foreign module authorization has ended");return result;
    }
    auto result=state->codec.decodeResult(raw.bytes,poll);state->scope.check();
    if(!state->function.isOpen())throw DataError("E_RESOURCE_SCOPE","task foreign module authorization has ended");return result;
  }
};
}
