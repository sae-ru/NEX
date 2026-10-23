// CPU-only regression of the real GPU broker and cancellable serialized lease.
#define NEX_GPU_SIGNATURE "0000000000000000000000000000000000000000000000000000000000000000"
#include "gpu-module.cpp"
#include <future>
#include <iostream>
#include <sys/resource.h>
static std::atomic<int> polls{0};
static nex_ffi_status poll(nex_ffi_call){return std::getenv("NEX_TEST_CANCEL")&&++polls>=4?NEX_FFI_LIMIT:NEX_FFI_OK;}
static std::string attempt(const nex_ffi_api_v1 *api){
 try{std::vector<uint8_t>x{1,2,3,4},y{5,6,7,8};auto r=checkedGPU(x,y,255,api,1);if(r!=x)return "BAD";return "OK";}
 catch(const HostStatus &e){return "HOST:"+std::to_string(e.value);}
 catch(const Failure &e){return e.code;}
}
int main(){
 rlimit core{0,0};setrlimit(RLIMIT_CORE,&core);nex_ffi_api_v1 api{};api.poll=poll;
 if(std::getenv("NEX_TEST_HELD_LEASE")){
  std::unique_lock held(acceleratorMutex);
  auto result=std::async(std::launch::async,[&]{return attempt(&api);});
  if(result.wait_for(std::chrono::seconds(1))!=std::future_status::ready){held.unlock();result.wait();return 2;}
  auto text=result.get();if(text!="HOST:9"||polls<4)return 2;std::cout<<text<<"\n";return 0;
 }
 std::cout<<attempt(&api)<<"\n";
}
