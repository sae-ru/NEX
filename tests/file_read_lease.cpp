#include "nex_files.h"
#include "nex_host.h"
#include "nex_task_file_read.h"
#include <atomic>
#include <filesystem>
#include <fstream>
#include <future>
#include <iostream>
#include <thread>
#include <unistd.h>

namespace fs=std::filesystem;
using namespace nexrt;
namespace {
size_t cases=0;
void require(bool value,const char *message){if(!value)throw std::runtime_error(message);}
template<class F>void rejects(const std::string &code,F function){
  try{function();}catch(const DataError &error){require(error.code==code,"unexpected file lease error");++cases;return;}
  throw std::runtime_error("expected file lease failure");
}
void write(const fs::path &path,const std::string &bytes){std::ofstream file(path,std::ios::binary);file.write(bytes.data(),bytes.size());require(bool(file),"cannot write fixture");}
struct Directory {
  fs::path path;
  Directory(){std::string pattern=(fs::temp_directory_path()/"nex-read-lease-XXXXXX").string();auto value=::mkdtemp(pattern.data());require(value,"mkdtemp failed");path=value;}
  ~Directory(){std::error_code ignored;fs::remove_all(path,ignored);}
};
void tests(){
  Directory temporary;auto root=temporary.path/"root",other=temporary.path/"other";fs::create_directory(root);fs::create_directory(other);
  const std::string bytes("A\0\xff",3);write(root/"data",bytes);write(other/"data","wrong grant");
  auto before=liveObjects.load();TextFiles capability(root.string(),false);
  {
    FileScope scope(capability);auto lease=captureFileReadLease("data");
    require(lease.identity()!=0,"lease has no identity");
    // A worker's unrelated TLS grant cannot replace the captured coordinator.
    auto future=std::async(std::launch::async,[lease,other](){
      TextFiles wrong(other.string(),false);FileScope scope(wrong);
      return lease.read();
    });
    auto result=future.get();require(std::string(result.begin(),result.end())==bytes,"worker consulted its ambient grant");++cases;
    auto denied=std::async(std::launch::async,[lease](){FileScope scope(false);rejects("CAPABILITY",[]{(void)captureFileReadLease("data",false);});return lease.read();});
    result=denied.get();require(std::string(result.begin(),result.end())==bytes,"explicit lease was lost on a worker");++cases;
    fs::rename(root,temporary.path/"pinned");fs::create_directory(root);write(root/"data","replaced root");
    auto pinned=captureFileReadLease("data").read();require(std::string(pinned.begin(),pinned.end())==bytes,"root pathname replacement redirected a lease");++cases;
    rejects("VALIDATION",[]{(void)captureFileReadLease("../escape");});
    rejects("VALIDATION",[]{(void)captureFileReadLease("/absolute");});
    rejects("E_UTF8",[]{(void)captureFileReadLease(std::string("\xff",1));});
    auto absent=captureFileReadLease("missing");rejects("NOT_FOUND",[&]{(void)absent.read();});
    fs::create_symlink(other/"data",temporary.path/"pinned/link");
    auto link=captureFileReadLease("link");rejects("VALIDATION",[&]{(void)link.read();});
    write(temporary.path/"pinned/large",std::string(TextFiles::byteLimit+1,'x'));
    auto large=captureFileReadLease("large");rejects("LIMIT",[&]{(void)large.read();});
  }
  {
    auto scope=std::make_unique<FileScope>(capability);auto lease=captureFileReadLease("data");
    std::promise<void> entered,release;auto ready=entered.get_future(),go=release.get_future();
    auto worker=std::async(std::launch::async,[lease,&entered,&go](){
      unsigned polls=0;
      try{(void)lease.read([&]{if(++polls==2){entered.set_value();go.wait();}});return std::string("unexpected success");}
      catch(const DataError &error){return error.code;}
    });
    ready.wait();scope.reset();rejects("E_RESOURCE_SCOPE",[&]{lease.check();});
    require(worker.wait_for(std::chrono::milliseconds(0))==std::future_status::timeout,"logical revoke pretended physical completion");
    release.set_value();require(worker.get()=="E_RESOURCE_SCOPE","in-flight read ignored grant revocation");++cases;
  }
  {
    FileScope scope(capability);FileReadLease requestLease;
    {RequestScope request;requestLease=captureFileReadLease("data");(void)requestLease.read();}
    rejects("E_RESOURCE_SCOPE",[&]{requestLease.check();});
    (void)captureFileReadLease("data").read();++cases;
  }
  {
    FileScope scope(capability);std::vector<FileReadLease> held;
    for(size_t i=0;i<64;++i)held.push_back(captureFileReadLease("data"));
    rejects("E_RESOURCE_LIMIT",[]{(void)captureFileReadLease("data");});
    held.clear();(void)captureFileReadLease("data").read();++cases;
  }
  {
    FileScope scope(capability);
    PreparedTaskFileRead binary("data",false),text("data",true);
    auto result=std::async(std::launch::async,[operation=binary.operation()](){FileScope deny(false);return operation->run(TaskExternalControl{});}).get();
    require(result.bytes.capacity()<=TextFiles::byteLimit,"raw physical capacity exceeded its reservation");
    auto value=binary.admit(std::move(result));auto actual=byteBuffer(unwrap(value).object).view();
    require(std::string(actual.begin(),actual.end())==bytes,"coordinator binary admission changed bytes");++cases;
    auto invalid=text.admit(text.operation()->run(TaskExternalControl{}));
    require(invalid.object->kind==Data::Failure&&invalid.object->text=="E_UTF8","text admission accepted invalid UTF-8");++cases;
    PreparedTaskFileRead missing("missing",false);
    auto rawMissing=std::async(std::launch::async,[operation=missing.operation()](){return operation->run(TaskExternalControl{});}).get();
    require(rawMissing.errorCode=="NOT_FOUND"&&rawMissing.bytes.empty(),"ordinary file error did not use raw transport");
    auto failed=missing.admit(std::move(rawMissing));
    require(failed.object->kind==Data::Failure&&failed.object->text=="NOT_FOUND","ordinary file error was raised instead of returned");++cases;
    TaskExternalResult limit;limit.errorCode="E_TIMEOUT";limit.errorMessage="root expired";
    rejects("E_TIMEOUT",[&]{(void)binary.admit(std::move(limit));});
  }
  {
    auto scope=std::make_unique<FileScope>(capability);PreparedTaskFileRead read("data",false);
    auto result=read.operation()->run(TaskExternalControl{});scope.reset();
    rejects("E_RESOURCE_SCOPE",[&]{(void)read.admit(std::move(result));});
  }
  rejects("E_RESOURCE_CLOSED",[]{(void)FileReadLease().read();});
  require(liveObjects.load()==before,"raw worker lease created/leaked managed source values");++cases;
}
}
int main(){try{tests();std::cout<<"{\"ok\":true,\"cases\":"<<cases<<",\"worker_reads_explicit_physical_lease\":true,\"lexical_revoke\":true,\"request_revoke\":true,\"logical_cancel_is_not_physical_completion\":true,\"public_async_io\":false}\n";return 0;}catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 1;}}
