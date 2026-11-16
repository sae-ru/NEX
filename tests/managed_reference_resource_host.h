#pragma once
#include "managed_reference_request_host.h"
#include "nex_files.h"
#include "nex_foreign.h"
#include "host_file_observers.h"
#include <fcntl.h>
#include <iostream>

inline size_t managedResourceFiles(){
#ifdef _WIN32
  return nex_test::files().size();
#else
  size_t count=0;for(int fd=0;fd<4096;++fd)if(::fcntl(fd,F_GETFD)>=0)++count;return count;
#endif
}
inline int runManagedReferenceResources(void *entry,bool request,const char *root,const char *catalogue,const char *report){
  const auto baseline=nexrt::liveObjects.load();const auto descriptors=managedResourceFiles();int status;
  uint64_t remaining=0;
  {
    nexrt::TextFiles files(root,true);nexrt::FileScope fileScope(files);
    auto libraries=std::string(catalogue)=="-"?nullptr:nexrt::loadForeignLibraries(catalogue);
    std::unique_ptr<nexrt::ForeignScope> foreign;
    if(libraries)foreign=std::make_unique<nexrt::ForeignScope>(libraries);
    if(request)status=runManagedRequests(reinterpret_cast<ManagedRequestEntry>(entry),2,2,{},report);
    else status=reinterpret_cast<int(*)(int,const char *const*)>(entry)(0,nullptr);
    if(libraries)remaining=libraries->resourceBytesUsed();
  }
  if(remaining||nexrt::liveObjects.load()!=baseline||managedResourceFiles()!=descriptors)
    throw std::runtime_error("native cell/resource execution did not retire its values, files or external capacity");
  std::cerr<<"NEX_REFERENCE_RESOURCES {\"live_delta\":0,\"file_delta\":0,\"external_bytes\":0}\n";
  return status;
}
