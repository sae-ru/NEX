#include "nex_host.h"
#include "nex_io.h"
#include <cassert>
#include <exception>
#include <iostream>
#include <mutex>
#include <thread>
#include <vector>
extern "C" nexrt::Handle *nex_7_storage_6_mutate(nexrt::Handle*);

void request(const char *path,const std::string &principal,int64_t mode,const char *trap=nullptr,bool commit=true){
  bool caught=false;
  try {
    nexrt::Database db(path,principal,true);nexrt::StorageScope capability(db);nexrt::RequestScope scope(30,10000);
    auto argument=nexrt::makeHandle(nexrt::Value(nexrt::string(std::to_string(mode))));
    auto returned=nex_7_storage_6_mutate(argument);
    assert(trap==nullptr);assert(nexrt::isSuccess(nexrt::readHandle(returned)));
    nex_release(returned);nex_release(argument);scope.poll();
    auto result=db.commit();assert(nexrt::isSuccess(result)==commit);
  }catch(const nexrt::Trap &error){assert(trap&&error.code==trap);caught=true;}
  assert(caught==(trap!=nullptr));
}
int64_t count(const char *path,const std::string &principal){
  nexrt::Database db(path,principal,false);auto value=db.get("counter");assert(nexrt::isSuccess(value));
  auto text=nexrt::unwrap(value).object->text;return std::stoll(text.substr(1,text.size()-2));
}
int main(int argc,char **argv){
  assert(argc==2);nexrt::Database::initialize(argv[1]);
  request(argv[1],"alice",0);assert(count(argv[1],"alice")==1);
  request(argv[1],"alice",1,"E_ASSERT");assert(count(argv[1],"alice")==1);
  request(argv[1],"alice",2,nullptr,false);assert(count(argv[1],"alice")==1);
  request(argv[1],"alice",3,"E_LIMIT");assert(count(argv[1],"alice")==1);
  request(argv[1],"bob",0);assert(count(argv[1],"bob")==1);
  {
    nexrt::Database db(argv[1],"alice",false);assert(!nexrt::isSuccess(db.put("counter","bad")));assert(!nexrt::isSuccess(db.commit()));
  }
  assert(count(argv[1],"alice")==1);
  std::vector<std::thread> workers;
  std::mutex errorsMutex;
  std::vector<std::exception_ptr> errors;
  for(int i=0;i<8;++i)workers.emplace_back([&]{
    try{for(int n=0;n<12;++n)request(argv[1],"alice",0);}
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
  assert(count(argv[1],"alice")==97);assert(count(argv[1],"bob")==1);
  nex_runtime_finish();
}
