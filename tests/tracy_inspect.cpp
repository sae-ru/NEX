// Optional acceptance helper: link against the matching upstream TracyServer.
#include "TracyFileRead.hpp"
#include "TracyWorker.hpp"
#include <chrono>
#include <iostream>
#include <memory>
#include <thread>
int main(int argc,char **argv){
  if(argc!=2)return 2;std::unique_ptr<tracy::FileRead> file(tracy::FileRead::Open(argv[1]));if(!file)return 3;
  tracy::Worker worker(*file);while(!worker.AreSourceLocationZonesReady())std::this_thread::sleep_for(std::chrono::milliseconds(10));
  if(worker.GetFailureType()!=tracy::Worker::Failure::None)return 4;
  std::cout<<"{\"pools\":[";bool comma=false;
  for(const auto &[name,data]:worker.GetMemNameMap()){
    if(!name)continue;if(comma)std::cout<<',';comma=true;
    std::cout<<"{\"name\":\""<<worker.GetString(name)<<"\",\"allocations\":"<<data->data.size()<<",\"frees\":"<<data->frees.size()<<",\"active\":"<<data->active.size()<<",\"usage\":"<<data->usage<<'}';
  }
  std::cout<<"],\"application_info\":[";comma=false;for(const auto &info:worker.GetAppInfo()){if(comma)std::cout<<',';comma=true;std::cout<<worker.GetString(info);}
  std::cout<<"]}\n";
}
