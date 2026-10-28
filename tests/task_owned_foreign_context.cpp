#include "nex_task_foreign.h"
#include "nex_host.h"
#include "third_party/json.hpp"
#include <fstream>
#include <iostream>
#include <thread>

using namespace nexrt;
using J=nlohmann::ordered_json;
static std::string read(const char *path){std::ifstream input(path);return {std::istreambuf_iterator<char>(input),{}};}
template<class F> static void expect(const char *code,F action){
  try{action();}catch(const DataError &error){if(error.code==code)return;throw;}
  throw DataError("E_TEST",std::string("expected ")+code);
}
static TaskExternalResult run(PreparedTaskForeignCall &call){
  std::exception_ptr failure;TaskExternalResult result;
  std::thread worker([&]{try{
    RequestScope unrelatedWorkerRequest;
    result=call.operation()->run(TaskExternalControl{});
  }catch(...){failure=std::current_exception();}});
  worker.join();if(failure)std::rethrow_exception(failure);return result;
}
struct HostObject {~HostObject()noexcept=default;};
int main(int argc,char **argv)try{
  if(argc!=3)throw DataError("E_OPTION","expected catalogue and source-checked bindings");
  auto bindings=J::parse(read(argv[2]));const auto create=bindings.at("create").dump(),inspect=bindings.at("read").dump();
  size_t checks=0;
  {
    auto libraries=loadForeignLibraries(argv[1]);RequestScope request;ForeignScope scope(libraries);auto captured=captureForeignScope();
    auto cleanup=std::make_shared<ResourceExecutor>();ResourceRegion root;auto ownerRegion=root.child();auto sibling=root.child();auto region=ownerRegion.authority();
    size_t acquired=0;
    PreparedTaskForeignCall factory(captured,create,std::vector<Value>{Value(42)},{},{},cleanup,[&]{++acquired;return ownerRegion.authority();});
    auto raw=run(factory);if(!raw.bytes.empty()||acquired!=1)throw DataError("E_TEST","owned wakeup carried a payload or authority was not captured once");++checks;
    Value owner;
    std::exception_ptr failure;
    std::thread worker([&]{try{RequestScope differentResumeRequest;owner=factory.admit(std::move(raw));}catch(...){failure=std::current_exception();}});
    worker.join();if(failure)std::rethrow_exception(failure);
    if(libraries->resourceBytesUsed()!=8||!externalResource(owner.object).isOpen())throw DataError("E_TEST","worker TLS revoked the caller's owner");++checks;
    expect("E_TASK_STATE",[&]{(void)factory.admit(TaskExternalResult{});});++checks;
    expect("E_TASK_STATE",[&]{(void)run(factory);});++checks;
    PreparedTaskForeignCall reader(captured,inspect,std::vector<Value>{owner},{},region,cleanup);
    if(reader.admit(run(reader)).scalar!=42)throw DataError("E_TEST","owned caller authority was not retained across workers");++checks;
    foreign_detail::TaskCodec codec(captured.signature(create),true);
    auto snapshot=codec.snapshotResult(owner,region);
    if(snapshot.owners.size()!=1||codec.restoreResult(snapshot,region).object->kind!=Data::External)throw DataError("E_TEST","genuine owner table differs");++checks;
    auto descendant=ownerRegion.child();
    if(externalResource(codec.restoreResult(snapshot,descendant.authority()).object).identity()!=externalResource(owner.object).identity())throw DataError("E_TEST","ancestor borrow lost its owner identity");++checks;
    expect("E_RESOURCE_SCOPE",[&]{(void)codec.restoreResult(snapshot,sibling.authority());});++checks;
    ResourceRegion foreign;
    expect("E_RESOURCE_SCOPE",[&]{(void)codec.restoreResult(snapshot,foreign.authority());});++checks;
    auto changed=snapshot;changed.bytes={'"','1','"'};
    expect("E_FFI_TYPE",[&]{(void)codec.restoreResult(changed,region);});++checks;
    changed=snapshot;changed.owners.clear();expect("E_FFI_TYPE",[&]{(void)codec.restoreResult(changed,region);});++checks;
    changed=snapshot;changed.owners.push_back(changed.owners[0]);expect("E_FFI_TYPE",[&]{(void)codec.restoreResult(changed,region);});++checks;
    ResourceByteBudget bytes(16);const auto &original=externalResource(owner.object);
    auto pin=std::make_shared<int>(1);
    ExternalResourceType<HostObject> other(original.typeName(),std::string(64,'f'));
    auto different=ExternalResource::makeInRegion(captured.valueAccess(),region,other,std::span<const ResourceByteBudget>(&bytes,1),1,pin,cleanup,[](const ResourcePermit &permit){permit.check();return std::make_unique<HostObject>();});
    changed=snapshot;changed.owners[0]=different;expect("E_FFI_TYPE",[&]{(void)codec.restoreResult(changed,region);});++checks;
    // Matching metadata still cannot authorize a payload registered by a
    // different image/class. The real C borrow enforces registration identity.
    ExternalResourceType<HostObject> matching(original.typeName(),original.typeHash());
    auto fake=ExternalResource::makeInRegion(captured.valueAccess(),region,matching,std::span<const ResourceByteBudget>(&bytes,1),1,pin,cleanup,[](const ResourcePermit &permit){permit.check();return std::make_unique<HostObject>();});
    PreparedTaskForeignCall spoof(captured,inspect,std::vector<Value>{Value(externalValue(fake))},{},region,cleanup);
    expect("E_FFI",[&]{(void)run(spoof);});++checks;
  }
  for(unsigned mode=0;mode<3;++mode){
    auto libraries=loadForeignLibraries(argv[1]);auto request=std::make_unique<RequestScope>();auto scope=std::make_unique<ForeignScope>(libraries);auto captured=captureForeignScope();
    auto cleanup=std::make_shared<ResourceExecutor>();ResourceRegion region;
    PreparedTaskForeignCall late(captured,create,std::vector<Value>{Value(42)},{},region.authority(),cleanup);
    auto raw=run(late);
    if(mode==0){scope.reset();expect("E_FFI_SCOPE",[&]{(void)late.admit(std::move(raw));});}
    if(mode==1){request.reset();expect("E_RESOURCE_SCOPE",[&]{(void)late.admit(std::move(raw));});}
    if(mode==2){libraries->revoke();expect("E_RESOURCE_SCOPE",[&]{(void)late.admit(std::move(raw));});}
    ++checks;
  }
  {
    auto libraries=loadForeignLibraries(argv[1]);ForeignScope scope(libraries);auto captured=captureForeignScope();
    auto cleanup=std::make_shared<ResourceExecutor>();ResourceRegion region;
    PreparedTaskForeignCall late(captured,create,std::vector<Value>{Value(42)},{},region.authority(),cleanup);auto raw=run(late);
    auto retirement=region.beginClose();retirement.requestClose();
    expect("E_RESOURCE_SCOPE",[&]{(void)late.admit(std::move(raw));});++checks;
    size_t acquired=0;
    expect("E_RESOURCE_SCOPE",[&]{PreparedTaskForeignCall denied(captured,create,std::vector<Value>{Value(42)},{},{},cleanup,[&]{++acquired;return region.authority();});});
    if(acquired!=1)throw DataError("E_TEST","owned request skipped logical authority acquisition");++checks;
  }
  {
    auto libraries=loadForeignLibraries(argv[1]);ForeignScope scope(libraries);auto captured=captureForeignScope();
    auto cleanup=std::make_shared<ResourceExecutor>();ResourceRegion region;
    auto first=std::make_unique<PreparedTaskForeignCall>(captured,create,std::vector<Value>{Value(1)},std::function<void()>{},region.authority(),cleanup);
    PreparedTaskForeignCall second(captured,create,std::vector<Value>{Value(2)},{},region.authority(),cleanup);
    expect("E_RESOURCE_LIMIT",[&]{PreparedTaskForeignCall third(captured,create,std::vector<Value>{Value(3)},{},region.authority(),cleanup);});++checks;
    first.reset();PreparedTaskForeignCall third(captured,create,std::vector<Value>{Value(3)},{},region.authority(),cleanup);++checks;
  }
  std::cout<<"OWNED SOURCE FFI CONTEXT "<<checks<<" CASES PASSED\n";return 0;
}catch(const DataError &error){std::cerr<<error.code<<": "<<error.what()<<'\n';return 1;}
catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 2;}
