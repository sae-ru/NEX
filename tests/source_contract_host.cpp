#include "host_test.h"
#include "nex_host.h"
#include "nex_value.h"
#include "nex_task_frame.h"
#ifndef _WIN32
#include <dlfcn.h>
#endif
#include <iostream>
int main(int argc,char **argv){
  try{
    if(argc<3||std::string(argv[1])!="run")throw std::runtime_error("expected run library [workers]");
    const auto baseline=nexrt::liveObjects.load();
    void *library=dlopen(argv[2],RTLD_NOW|RTLD_LOCAL);if(!library)throw std::runtime_error(dlerror());
    auto entry=reinterpret_cast<int(*)(int,const char *const*)>(dlsym(library,"main"));if(!entry)throw std::runtime_error(dlerror());
    const char *arguments[]={"nex-contract-host","--nex-task-workers",argc>3?argv[3]:"1"};
    auto status=entry(3,arguments);
    if(nexrt::liveObjects.load()!=baseline)throw std::runtime_error("contract exit retained native managed values");
    dlclose(library);return status;
  }catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 1;}
}
