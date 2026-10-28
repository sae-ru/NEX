#include "nex_task_foreign.h"
#include "nex_host.h"
#include <iostream>
#include <thread>
#include <atomic>
#include <fstream>

using namespace nexrt;
static std::string read(const char *path){std::ifstream input(path);return {std::istreambuf_iterator<char>(input),{}};}
template<class F> static void expect(const char *code,F action){
  try{action();}catch(const DataError &error){if(error.code==code)return;throw;}
  throw DataError("E_TEST",std::string("expected ")+code);
}
int main(int argc,char **argv)try{
  if(argc!=3)throw DataError("E_OPTION","expected operator catalogue and checked add binding");
  auto libraries=loadForeignLibraries(argv[1]);auto binding=read(argv[2]);
  size_t checks=0;
  {
    RequestScope request;
    auto scope=std::make_unique<ForeignScope>(libraries);
    auto captured=captureForeignScope();std::optional<TaskExternalResult> ready;
    // Construction and IO happen on a task-resume worker. Its transient
    // request is deliberately gone before the next task continuation runs.
    auto work=[&]{
      std::exception_ptr failure;
      std::thread worker([&]{try{
        RequestScope transient;
        PreparedTaskForeignCall call(captured,binding,std::vector<Value>{Value(41)});
        auto raw=call.operation()->run(TaskExternalControl{});
        auto value=call.admit(std::move(raw));
        if(value.tag!=Value::Integer||value.scalar!=42)throw DataError("E_TEST","worker typed result differs");
      }catch(...){failure=std::current_exception();}});
      worker.join();if(failure)std::rethrow_exception(failure);captured.check();++checks;
    };
    work();work();
    {
      ResourceRegion unrelated;unrelated.close();size_t acquired=0;
      PreparedTaskForeignCall pure(captured,binding,std::vector<Value>{Value(41)},{},{},{},[&]{++acquired;return unrelated.authority();});
      auto raw=pure.operation()->run(TaskExternalControl{});
      if(pure.admit(std::move(raw)).scalar!=42||acquired!=0)throw DataError("E_TEST","copied-data call acquired unrelated logical authority");++checks;
    }
    PreparedTaskForeignCall late(captured,binding,std::vector<Value>{Value(41)});
    ready=late.operation()->run(TaskExternalControl{});
    scope.reset();
    expect("E_FFI_SCOPE",[&]{(void)late.admit(std::move(*ready));});++checks;
    expect("E_FFI_SCOPE",[&]{(void)PreparedTaskForeignCall(captured,binding,std::vector<Value>{Value(41)});});++checks;
  }
  {
    auto request=std::make_unique<RequestScope>();
    ForeignScope scope(libraries);auto captured=captureForeignScope();
    PreparedTaskForeignCall late(captured,binding,std::vector<Value>{Value(41)});
    auto raw=late.operation()->run(TaskExternalControl{});
    request.reset();
    expect("E_RESOURCE_SCOPE",[&]{(void)late.admit(std::move(raw));});++checks;
    std::exception_ptr failure;
    std::thread worker([&]{try{
      RequestScope unrelated;
      expect("E_RESOURCE_SCOPE",[&]{(void)captured.bind(binding);});
    }catch(...){failure=std::current_exception();}});
    worker.join();if(failure)std::rethrow_exception(failure);++checks;
  }
  {
    ForeignScope scope(libraries);auto captured=captureForeignScope();
    PreparedTaskForeignCall late(captured,binding,std::vector<Value>{Value(41)});
    auto raw=late.operation()->run(TaskExternalControl{});libraries->revoke();
    // Captured lexical state can still be live; the module grant cannot.
    expect("E_RESOURCE_SCOPE",[&]{(void)late.operation()->run(TaskExternalControl{});});++checks;
    // Successful old bytes also require the physical module authorization at
    // admission, rather than merely an active lexical context.
    expect("E_RESOURCE_SCOPE",[&]{(void)late.admit(std::move(raw));});++checks;
  }
  std::cout<<"CAPTURED SOURCE FFI CONTEXT "<<checks<<" CASES PASSED\n";return 0;
}catch(const DataError &error){std::cerr<<error.code<<": "<<error.what()<<'\n';return 1;}
catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 2;}
