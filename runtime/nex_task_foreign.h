#pragma once
#include "nex_foreign.h"
#include "nex_ffi_types.h"
#include "nex_task_external.h"

namespace nexrt {
// Private source prototype: copied capability-free data only. External owners
// need a separate authenticated owned-result channel and remain rejected here.
class PreparedTaskForeignCall {
  struct State {
    CapturedForeignScope scope;
    ForeignFunction function;
    foreign_detail::TaskCodec codec;
    std::vector<uint8_t> arguments;
    State(CapturedForeignScope scope,ForeignFunction function,foreign_detail::TaskCodec codec,
          std::vector<uint8_t> arguments)
      :scope(std::move(scope)),function(std::move(function)),codec(std::move(codec)),arguments(std::move(arguments)){}
  };
  std::shared_ptr<const State> state;
  class Operation final:public TaskExternalOperation {
    std::shared_ptr<const State> state;
  public:
    explicit Operation(std::shared_ptr<const State> value):state(std::move(value)){}
    TaskExternalResult run(const TaskExternalControl &control)override{
      auto poll=[&]{state->scope.check();control.checkpoint();state->scope.check();};
      poll();TaskExternalResult raw;
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
      std::span<const Value> arguments,const std::function<void()> &poll={}){
    std::vector<Value> retained(arguments.begin(),arguments.end());
    // Reject unsupported types and hidden values before loading native code.
    foreign_detail::TaskCodec codec(scope.signature(binding));
    auto snapshot=codec.encodeArguments(retained,poll);
    auto function=scope.bind(binding,poll);
    state=std::make_shared<State>(scope,std::move(function),std::move(codec),std::move(snapshot));
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
    auto result=state->codec.decodeResult(raw.bytes,poll);state->scope.check();
    if(!state->function.isOpen())throw DataError("E_RESOURCE_SCOPE","task foreign module authorization has ended");return result;
  }
};
}
