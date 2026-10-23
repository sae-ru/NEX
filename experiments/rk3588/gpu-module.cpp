#ifndef _GNU_SOURCE
#define _GNU_SOURCE 1
#endif
// Experimental trusted RK3588 OpenCL adapter. No NEX/runtime C++ objects cross its ABI.
#define CL_TARGET_OPENCL_VERSION 120
#include <CL/cl.h>
#include "nex_ffi_module.h"
#include "third_party/json.hpp"
#include <array>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <filesystem>
#include <fstream>
#include <mutex>
#include <stdexcept>
#include <string>
#include <vector>
#include <unistd.h>

using JSON=nlohmann::json;
struct Failure:std::runtime_error {
  std::string code;
  Failure(std::string code,std::string text):std::runtime_error(std::move(text)),code(std::move(code)){}
};
struct Library {
  void *value=nullptr;
  explicit Library(const char *path,int flags=RTLD_NOW|RTLD_LOCAL){value=dlopen(path,flags);if(!value)throw Failure("E_DEVICE_UNAVAILABLE",dlerror());}
  ~Library(){if(value)dlclose(value);}
  template<class T>T symbol(const char *name){dlerror();auto p=dlsym(value,name);auto e=dlerror();if(e||!p)throw Failure("E_DEVICE_ABI",e?e:name);return reinterpret_cast<T>(p);}
  Library(const Library&)=delete;
};
void trace(const JSON &entry){
  if(auto path=std::getenv("NEX_RK_GPU_TRACE_FILE")){
    std::ofstream output(path,std::ios::app);if(!output)throw Failure("E_TRACE","cannot append private accelerator trace");
    output<<entry.dump()<<'\n';if(!output)throw Failure("E_TRACE","cannot write private accelerator trace");
  }
}
nex_ffi_status error(const nex_ffi_api_v1 *a,nex_ffi_call call,nex_ffi_ref *out,const std::string &code,const std::string &message){
  auto text=message.substr(0,2048);
  return a->make_failure(call,reinterpret_cast<const uint8_t*>(code.data()),code.size(),reinterpret_cast<const uint8_t*>(text.data()),text.size(),out);
}
#define FFI(expression) do {auto status=(expression);if(status)return status;}while(0)
std::mutex acceleratorMutex; // Explicit serialized adapter; no source concurrency claim.

#include <cerrno>
#include <csignal>
#include <fcntl.h>
#include <spawn.h>
#include <sys/wait.h>
#include <thread>
extern char **environ;
struct HostStatus {nex_ffi_status value;};
struct PrivateJob {
 std::filesystem::path root;pid_t pid=-1;int status=0;
 PrivateJob(){auto pattern=(std::filesystem::temp_directory_path()/"nex-rk-gpu-XXXXXX").string();std::vector<char> text(pattern.begin(),pattern.end());text.push_back(0);auto p=mkdtemp(text.data());if(!p)throw Failure("E_HOST_IO","cannot create private GPU job");root=p;}
 void reap()noexcept{if(pid>0){kill(pid,SIGKILL);while(waitpid(pid,&status,0)<0&&errno==EINTR){}pid=-1;}}
 ~PrivateJob(){reap();std::error_code ec;std::filesystem::remove_all(root,ec);}
};
static std::vector<uint8_t> isolatedGPU(std::vector<uint8_t>&x,std::vector<uint8_t>&y,const nex_ffi_api_v1*,nex_ffi_call);
static std::vector<uint8_t> isolatedGPU(std::vector<uint8_t>&x,std::vector<uint8_t>&y,const nex_ffi_api_v1 *api,nex_ffi_call call){
 PrivateJob job;auto input=job.root/"input",output=job.root/"output",log=job.root/"vendor-log";
 auto put32=[](std::ostream &s,uint32_t n){for(int i=0;i<4;++i)s.put(char(uint8_t(n>>(8*i))));};
 {std::ofstream f(input,std::ios::binary);put32(f,x.size());f.write(reinterpret_cast<const char*>(x.data()),x.size());f.write(reinterpret_cast<const char*>(y.data()),y.size());if(!f)throw Failure("E_HOST_IO","cannot write GPU request");}
 Dl_info image{};if(!dladdr(reinterpret_cast<void*>(&isolatedGPU),&image)||!image.dli_fname)throw Failure("E_CONFIGURATION","cannot locate pinned GPU worker");
 auto worker=std::filesystem::path(image.dli_fname).parent_path()/"gpu-worker";
 if(!std::filesystem::is_regular_file(worker))throw Failure("E_CONFIGURATION","pinned GPU worker missing");
 int in=open(input.c_str(),O_RDONLY|O_CLOEXEC);int out=open(output.c_str(),O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0600);int err=open(log.c_str(),O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0600);
 if(in<0||out<0||err<0){if(in>=0)close(in);if(out>=0)close(out);if(err>=0)close(err);throw Failure("E_HOST_IO","cannot create GPU transport");}
 posix_spawn_file_actions_t actions;int setup=posix_spawn_file_actions_init(&actions);bool initialized=setup==0;
 if(!setup)setup=posix_spawn_file_actions_adddup2(&actions,in,0);
 if(!setup)setup=posix_spawn_file_actions_adddup2(&actions,out,1);
 if(!setup)setup=posix_spawn_file_actions_adddup2(&actions,err,2);
 if(!setup)setup=posix_spawn_file_actions_addclosefrom_np(&actions,3);
 const char *loader="/lib/ld-linux-aarch64.so.1";auto path=worker.string();char *args[]={const_cast<char*>(loader),path.data(),nullptr};
 int spawned=setup?setup:posix_spawn(&job.pid,loader,&actions,nullptr,args,environ);
 if(initialized)posix_spawn_file_actions_destroy(&actions);close(in);close(out);close(err);
 if(spawned){job.pid=-1;throw Failure("E_HOST_PROCESS","GPU worker spawn:"+std::to_string(spawned));}
 auto start=std::chrono::steady_clock::now();
 while(true){
  auto result=waitpid(job.pid,&job.status,WNOHANG);
  if(result==job.pid){job.pid=-1;break;}
  if(result<0&&errno!=EINTR){if(errno==ECHILD)job.pid=-1;throw Failure("E_HOST_PROCESS","GPU worker wait failed");}
  auto polled=api->poll(call);if(polled)throw HostStatus{polled};
  if(std::chrono::steady_clock::now()-start>std::chrono::seconds(60))throw Failure("E_DEVICE_TIMEOUT","GPU worker process timeout");
  std::this_thread::sleep_for(std::chrono::milliseconds(2));
 }
 std::ifstream diagnostics(log,std::ios::binary);std::string raw(4096,'\0');diagnostics.read(raw.data(),raw.size());raw.resize(diagnostics.gcount());
 if(!raw.empty()){static constexpr char digits[]="0123456789abcdef";std::string hex;for(unsigned char c:raw){hex+=digits[c>>4];hex+=digits[c&15];}trace(JSON{{"backend","worker-log"},{"vendor_stderr_hex",hex},{"captured_bytes",raw.size()},{"scope","private child; parent stdout unchanged"}});}
 if(!WIFEXITED(job.status)||WEXITSTATUS(job.status)!=0)throw Failure("E_DEVICE_PROCESS","GPU worker terminated; see private vendor log trace");
 auto bytes=std::filesystem::file_size(output);if(bytes<8||bytes>65544)throw Failure("E_PROTOCOL","GPU worker result size invalid");
 std::ifstream f(output,std::ios::binary);auto get32=[&](){uint32_t n=0;for(int i=0;i<4;++i){int c=f.get();if(c==std::char_traits<char>::eof())throw Failure("E_PROTOCOL","truncated GPU worker header");n|=uint32_t(uint8_t(c))<<(8*i);}return n;};
 uint32_t status=get32(),size=get32();if(bytes!=uint64_t(size)+8||size>65536||status>1)throw Failure("E_PROTOCOL","GPU worker frame invalid");
 std::vector<uint8_t>data(size);f.read(reinterpret_cast<char*>(data.data()),data.size());if(!f)throw Failure("E_PROTOCOL","truncated GPU worker result");
 if(status){auto value=JSON::parse(data.begin(),data.end());throw Failure(value.at("code").get<std::string>(),value.at("message").get<std::string>());}
 if(data.size()!=x.size())throw Failure("E_PROTOCOL","wrong GPU worker payload size");return data;
}
extern "C" nex_ffi_status gpu_affine(const nex_ffi_api_v1 *a,nex_ffi_call call,const nex_ffi_ref *args,uint64_t count,nex_ffi_ref *out,void*){
  try{
    if(count!=2)return NEX_FFI_ARGUMENT;FFI(a->poll(call));uint64_t n=0,m=0;FFI(a->byte_size(call,args[0],&n));FFI(a->byte_size(call,args[1],&m));
    if(n!=m||!n||n>65536)return error(a,call,out,"E_INPUT_SIZE","GPU inputs require equal nonzero byte lengths <=65536");
    std::vector<uint8_t> x(n),y(n);uint64_t copied=0;FFI(a->copy_bytes(call,args[0],0,x.data(),n,&copied));if(copied!=n)return NEX_FFI_INTERNAL;
    FFI(a->copy_bytes(call,args[1],0,y.data(),n,&copied));if(copied!=n)return NEX_FFI_INTERNAL;
    for(size_t i=0;i<n;++i)if(x[i]>60||y[i]>30)return error(a,call,out,"E_INPUT_RANGE","bounded affine input exceeds a<=60,b<=30");
    std::vector<uint8_t> result;{std::lock_guard lock(acceleratorMutex);result=isolatedGPU(x,y,a,call);}FFI(a->poll(call));
    nex_ffi_ref value=0;FFI(a->make_bytes(call,result.data(),result.size(),&value));return a->make_success(call,value,out);
  }catch(const HostStatus &e){return e.value;}catch(const Failure &e){return error(a,call,out,e.code,e.what());}catch(const std::exception &e){return error(a,call,out,"E_ACCELERATOR",e.what());}catch(...){return NEX_FFI_INTERNAL;}
}
NEX_FFI_MODULE_EXPORT const nex_ffi_module_v1 *nex_ffi_module_entry(uint32_t abi,uint32_t size){
static const nex_ffi_export_v1 exports[]={{sizeof(nex_ffi_export_v1),0,"gpu_affine",NEX_GPU_SIGNATURE,gpu_affine,nullptr}};
static const nex_ffi_module_v1 module={NEX_FFI_MODULE_ABI_V1,sizeof(nex_ffi_module_v1),1,sizeof(nex_ffi_export_v1),exports};
return abi==NEX_FFI_ABI_V1&&size>=sizeof(nex_ffi_api_v1)?&module:nullptr;}
