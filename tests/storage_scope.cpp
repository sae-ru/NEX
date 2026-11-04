#include "nex_host.h"
#include "nex_io.h"
#include <atomic>
#include <barrier>
#include <cassert>
#include <exception>
#include <future>
#include <iostream>
#include <memory>
#include <mutex>
#include <thread>
#include <vector>
extern "C" nexrt::Handle *nex_7_storage_6_mutate(nexrt::Handle*);

std::unique_ptr<nexrt::Database> admit(const char *path,const std::string &principal,bool allowBusy){
  try{return std::make_unique<nexrt::Database>(path,principal,true);}
  catch(const nexrt::DataError &error){
    // Only eager transaction admission may be rejected. Never turn an error
    // after the source mutation or an uncertain commit into a retry/success.
    if(allowBusy&&error.code=="STORE_BUSY")return nullptr;
    throw;
  }
}
bool request(const char *path,const std::string &principal,int64_t mode,const char *trap=nullptr,bool commit=true,bool allowBusy=false){
  bool caught=false;
  try {
    auto db=admit(path,principal,allowBusy);if(!db)return false;
    nexrt::StorageScope capability(*db);nexrt::RequestScope scope(30,10000);
    auto argument=nexrt::makeHandle(nexrt::Value(nexrt::string(std::to_string(mode))));
    auto returned=nex_7_storage_6_mutate(argument);
    assert(trap==nullptr);assert(nexrt::isSuccess(nexrt::readHandle(returned)));
    nex_release(returned);nex_release(argument);scope.poll();
    auto result=db->commit();assert(nexrt::isSuccess(result)==commit);
  }catch(const nexrt::Trap &error){assert(trap&&error.code==trap);caught=true;}
  assert(caught==(trap!=nullptr));
  return true;
}
int64_t count(const char *path,const std::string &principal){
  nexrt::Database db(path,principal,false);auto value=db.get("counter");assert(nexrt::isSuccess(value));
  auto text=nexrt::unwrap(value).object->text;return std::stoll(text.substr(1,text.size()-2));
}
int main(int argc,char **argv){
  assert(argc==2);nexrt::Database::initialize(argv[1]);
  try{admit(":memory:","alice",true);assert(false);}
  catch(const nexrt::DataError &error){assert(error.code=="VALIDATION");}
  request(argv[1],"alice",0);assert(count(argv[1],"alice")==1);
  request(argv[1],"alice",1,"E_ASSERT");assert(count(argv[1],"alice")==1);
  request(argv[1],"alice",2,nullptr,false);assert(count(argv[1],"alice")==1);
  request(argv[1],"alice",3,"E_LIMIT");assert(count(argv[1],"alice")==1);
  request(argv[1],"bob",0);assert(count(argv[1],"bob")==1);
  {
    nexrt::Database db(argv[1],"alice",false);assert(!nexrt::isSuccess(db.put("counter","bad")));assert(!nexrt::isSuccess(db.commit()));
  }
  assert(count(argv[1],"alice")==1);
  {
    nexrt::Database held(argv[1],"alice",true);
    auto conflict=std::async(std::launch::async,[&]{return request(argv[1],"alice",0,nullptr,true,true);});
    assert(conflict.wait_for(std::chrono::seconds(3))==std::future_status::ready);
    assert(!conflict.get());held.rollback();
  }
  assert(count(argv[1],"alice")==1);
  std::vector<std::thread> workers;
  std::barrier start(8);
  std::atomic<unsigned> committed{0},busy{0};
  std::mutex errorsMutex;
  std::vector<std::exception_ptr> errors;
  for(int i=0;i<8;++i)workers.emplace_back([&]{
    start.arrive_and_wait();
    try{for(int n=0;n<12;++n){
      if(request(argv[1],"alice",0,nullptr,true,true))++committed;else ++busy;
    }}
    catch(...){std::lock_guard lock(errorsMutex);errors.push_back(std::current_exception());}
  });
  for(auto &worker:workers)worker.join();
  if(!errors.empty()){
    for(const auto &error:errors){
      try{std::rethrow_exception(error);}
      catch(const nexrt::DataError &value){std::cerr<<"worker database error ["<<value.code<<"]: "<<value.what()<<'\n';}
      catch(const std::exception &value){std::cerr<<"worker exception: "<<value.what()<<'\n';}
      catch(...){std::cerr<<"unknown worker exception\n";}
    }
    nex_runtime_finish();return 1;
  }
  assert(committed>0&&committed+busy==96);
  assert(count(argv[1],"alice")==1+committed);assert(count(argv[1],"bob")==1);
  // No writer lease survives a rejected/admitted request. A subsequent strict
  // request must commit once, independently of the contended admission order.
  request(argv[1],"alice",0);
  const auto alice=count(argv[1],"alice"),bob=count(argv[1],"bob");
  assert(alice==2+committed&&bob==1);
  nex_runtime_finish();
  assert(nexrt::liveObjects==0);
  std::cout<<"{\"schema\":\"nex.storage-contention/1\",\"ok\":true,\"attempts\":96,\"committed\":"<<committed
    <<",\"busy_admissions\":"<<busy<<",\"forced_busy_admission\":true,\"automatic_retries\":false,\"final_alice\":"<<alice
    <<",\"final_bob\":"<<bob<<",\"managed_values\":0}\n";
}
