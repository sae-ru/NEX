#pragma once
#ifdef _WIN32
#include "nex_platform.h"
#include <winternl.h>
#include <set>
#include <vector>
#include <algorithm>
#include <cstddef>
namespace nex_test {
inline std::set<uintptr_t> files(){
  struct Entry {HANDLE handle;ULONG_PTR handles,pointers;ULONG access,type,attributes,reserved;};
  struct Snapshot {ULONG_PTR count,reserved;Entry entries[1];};
  static_assert(sizeof(Entry)==40);
  using Query=NTSTATUS(NTAPI*)(HANDLE,int,void*,ULONG,ULONG*);
  auto query=reinterpret_cast<Query>(GetProcAddress(GetModuleHandleW(L"ntdll.dll"),"NtQueryInformationProcess"));
  if(!query)throw std::runtime_error("cannot inspect own Windows handles");
  std::vector<unsigned char> data(16384);ULONG bytes=0;NTSTATUS status;
  while((status=query(GetCurrentProcess(),51,data.data(),ULONG(data.size()),&bytes))<0){
    if(status!=NTSTATUS(0xc0000004)||data.size()>=16*1024*1024)throw std::runtime_error("own handle snapshot failed");
    data.resize(std::max<size_t>(data.size()*2,bytes));
  }
  auto snapshot=reinterpret_cast<const Snapshot*>(data.data());
  if(snapshot->count>(data.size()-offsetof(Snapshot,entries))/sizeof(Entry))throw std::runtime_error("invalid Windows handle snapshot");
  std::set<uintptr_t> result;
  for(size_t i=0;i<snapshot->count;++i){auto h=snapshot->entries[i].handle;auto kind=GetFileType(h);
    if(kind==FILE_TYPE_DISK||kind==FILE_TYPE_PIPE||kind==FILE_TYPE_CHAR)result.insert(reinterpret_cast<uintptr_t>(h));}
  return result;
}
}
#endif
