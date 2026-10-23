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
 PrivateJob(){auto pattern=(std::filesystem::temp_directory_path()/"nex-model-XXXXXX").string();std::vector<char> text(pattern.begin(),pattern.end());text.push_back(0);auto p=mkdtemp(text.data());if(!p)throw Failure("E_HOST_IO","cannot create private Model job");root=p;}
 void reap()noexcept{if(pid>0){kill(pid,SIGKILL);while(waitpid(pid,&status,0)<0&&errno==EINTR){}pid=-1;}}
 ~PrivateJob(){reap();std::error_code ec;std::filesystem::remove_all(root,ec);}
};
static std::vector<uint8_t> isolatedModel(const std::vector<std::vector<uint8_t>>&x,uint32_t device,const nex_ffi_api_v1*,nex_ffi_call);
static std::vector<uint8_t> isolatedModel(const std::vector<std::vector<uint8_t>>&x,uint32_t device,const nex_ffi_api_v1 *api,nex_ffi_call call){
 PrivateJob job;auto input=job.root/"input",output=job.root/"output",log=job.root/"vendor-log";
 auto put32=[](std::ostream &s,uint32_t n){for(int i=0;i<4;++i)s.put(char(uint8_t(n>>(8*i))));};
 {std::ofstream f(input,std::ios::binary);put32(f,1);put32(f,device);put32(f,x.size());for(const auto&v:x){put32(f,v.size());f.write(reinterpret_cast<const char*>(v.data()),v.size());}if(!f)throw Failure("E_HOST_IO","cannot write Model request");}
 Dl_info image{};if(!dladdr(reinterpret_cast<void*>(&isolatedModel),&image)||!image.dli_fname)throw Failure("E_MODEL_CONFIGURATION","cannot locate pinned Model worker");
 auto worker=std::filesystem::absolute(std::filesystem::path(image.dli_fname).parent_path()/"model-worker");
 if(!std::filesystem::is_regular_file(worker))throw Failure("E_MODEL_CONFIGURATION","pinned Model worker missing");
 int in=open(input.c_str(),O_RDONLY|O_CLOEXEC);int out=open(output.c_str(),O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0600);int err=open(log.c_str(),O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0600);
 if(in<0||out<0||err<0){if(in>=0)close(in);if(out>=0)close(out);if(err>=0)close(err);throw Failure("E_HOST_IO","cannot create Model transport");}
 posix_spawn_file_actions_t actions;int setup=posix_spawn_file_actions_init(&actions);bool initialized=setup==0;
 if(!setup)setup=posix_spawn_file_actions_adddup2(&actions,in,0);
 if(!setup)setup=posix_spawn_file_actions_adddup2(&actions,out,1);
 if(!setup)setup=posix_spawn_file_actions_adddup2(&actions,err,2);
 if(!setup)setup=posix_spawn_file_actions_addchdir_np(&actions,job.root.c_str());
 if(!setup)setup=posix_spawn_file_actions_addclosefrom_np(&actions,3);
 const char *loader="/lib/ld-linux-aarch64.so.1";auto path=worker.string();char *args[]={const_cast<char*>(loader),path.data(),nullptr};
 int spawned=setup?setup:posix_spawn(&job.pid,loader,&actions,nullptr,args,environ);
 if(initialized)posix_spawn_file_actions_destroy(&actions);close(in);close(out);close(err);
 if(spawned){job.pid=-1;throw Failure("E_HOST_PROCESS","Model worker spawn:"+std::to_string(spawned));}
 auto start=std::chrono::steady_clock::now();
 while(true){
  auto result=waitpid(job.pid,&job.status,WNOHANG);
  if(result==job.pid){job.pid=-1;break;}
  if(result<0&&errno!=EINTR){if(errno==ECHILD)job.pid=-1;throw Failure("E_HOST_PROCESS","Model worker wait failed");}
  auto polled=api->poll(call);if(polled)throw HostStatus{polled};
  if(std::chrono::steady_clock::now()-start>std::chrono::seconds(60))throw Failure("E_MODEL_TIMEOUT","Model worker process timeout");
  std::this_thread::sleep_for(std::chrono::milliseconds(2));
 }
 std::ifstream diagnostics(log,std::ios::binary);std::string raw(4096,'\0');diagnostics.read(raw.data(),raw.size());raw.resize(diagnostics.gcount());
 if(!raw.empty()){static constexpr char digits[]="0123456789abcdef";std::string hex;for(unsigned char c:raw){hex+=digits[c>>4];hex+=digits[c&15];}trace(JSON{{"backend","worker-log"},{"vendor_stderr_hex",hex},{"captured_bytes",raw.size()},{"scope","private child; parent stdout unchanged"}});}
 if(!WIFEXITED(job.status)||WEXITSTATUS(job.status)!=0)throw Failure("E_MODEL_PROCESS","Model worker terminated; see private vendor log trace");
 auto bytes=std::filesystem::file_size(output);if(bytes<8||bytes>1048584)throw Failure("E_MODEL_PROTOCOL","Model worker result size invalid");
 std::ifstream f(output,std::ios::binary);auto get32=[&](){uint32_t n=0;for(int i=0;i<4;++i){int c=f.get();if(c==std::char_traits<char>::eof())throw Failure("E_MODEL_PROTOCOL","truncated Model worker header");n|=uint32_t(uint8_t(c))<<(8*i);}return n;};
 uint32_t status=get32(),size=get32();if(bytes!=uint64_t(size)+8||size>1048576||status>1)throw Failure("E_MODEL_PROTOCOL","Model worker frame invalid");
 std::vector<uint8_t>data(size);f.read(reinterpret_cast<char*>(data.data()),data.size());if(!f)throw Failure("E_MODEL_PROTOCOL","truncated Model worker result");
 if(status){
  if(data.size()>8192)throw Failure("E_MODEL_PROTOCOL","oversized model error frame");JSON value;
  try{value=JSON::parse(data.begin(),data.end());}catch(const JSON::exception&){throw Failure("E_MODEL_PROTOCOL","malformed model error JSON");}
  if(!value.is_object()||value.size()!=2||!value.contains("code")||!value.contains("message")||!value["code"].is_string()||!value["message"].is_string())throw Failure("E_MODEL_PROTOCOL","invalid model error fields");
  auto code=value["code"].get<std::string>(),message=value["message"].get<std::string>();
  if(code.empty()||code.size()>128||message.size()>2048)throw Failure("E_MODEL_PROTOCOL","model error text exceeds its bound");throw Failure(code,message);
 }
 return data;
}
