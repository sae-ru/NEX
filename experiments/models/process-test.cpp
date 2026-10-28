#define NEX_MODEL_SIGNATURE "0000000000000000000000000000000000000000000000000000000000000000"
#include NEX_MODEL_TEST_MODULE
#include <atomic>
#include <iostream>
static unsigned polls=0;
static nex_ffi_status poll(nex_ffi_call){
 ++polls;if(!std::getenv("NEX_TEST_CANCEL"))return NEX_FFI_OK;
 if(std::getenv("NEX_TEST_HELD"))return polls>=4?NEX_FFI_LIMIT:NEX_FFI_OK;
 auto path=std::getenv("NEX_TEST_PID");return path&&std::filesystem::exists(path)?NEX_FFI_LIMIT:NEX_FFI_OK;
}
static int descriptors(){int n=0;for(int fd=0;fd<1024;++fd)if(fcntl(fd,F_GETFD)>=0)++n;return n;}
int main(){
 const auto before=descriptors();const auto cwd=std::filesystem::current_path();nex_ffi_api_v1 api{};api.poll=poll;bool held=std::getenv("NEX_TEST_HELD");std::atomic<bool>acquired=false,release=false;std::thread holder;
 if(held){holder=std::thread([&]{std::lock_guard lock(modelMutex);acquired=true;while(!release.load())std::this_thread::sleep_for(std::chrono::milliseconds(1));});while(!acquired.load())std::this_thread::sleep_for(std::chrono::milliseconds(1));}
 std::string result;bool correct=true;
 try{auto values=dispatch({std::vector<uint8_t>(24)},0,&api,1);correct=values==std::vector<std::vector<uint8_t>>{std::vector<uint8_t>(24)};result="OK";}
 catch(const Failure&e){result=e.code;}catch(const HostStatus&e){result="HOST:"+std::to_string(e.value);}catch(const std::exception&e){result="CPP_EXCEPTION";}
 if(held){release=true;holder.join();}if(!correct)return 2;if(descriptors()!=before||std::filesystem::current_path()!=cwd)return 3;std::cout<<result<<'\n';return 0;
}
