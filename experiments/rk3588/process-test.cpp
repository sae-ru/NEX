// NEX-owned CPU-only transport regression: production broker, controlled child.
#include "npu-common.h"
#include "npu-broker.inc"
#include <iostream>
#include <sys/resource.h>
static int polls=0;
static nex_ffi_status poll(nex_ffi_call){++polls;return std::getenv("NEX_TEST_CANCEL")&&polls>=3?NEX_FFI_LIMIT:NEX_FFI_OK;}
int main(){
 rlimit core{0,0};setrlimit(RLIMIT_CORE,&core);
 nex_ffi_api_v1 api{};api.poll=poll;
 try {
  auto value=isolatedNPU(std::vector<uint8_t>{1,2,3,4},4,&api,1);
  if(value!=std::vector<uint8_t>{1,2,3,4})return 2;
  std::cout<<"OK\n";
 }catch(const HostStatus &e){std::cout<<"HOST:"<<e.value<<"\n";}
 catch(const Failure &e){std::cout<<e.code<<"\n";}
}
