// Owned Metal host adapter; resource/transport structure follows owned-opencl.
#include "nex_ffi_module.h"
#include "protocol.h"
#include "signatures.h"
#include "generated_kernel.h"
#include "third_party/json.hpp"
#include <atomic>
#include <array>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <dlfcn.h>
#include <fcntl.h>
#include <filesystem>
#include <fstream>
#include <mutex>
#include <spawn.h>
#include <poll.h>
#include <thread>
#include <sys/wait.h>
extern char **environ;
using namespace owned_metal_map;
using JSON=nlohmann::json;
struct HostStatus {nex_ffi_status value;};
#define TRACE(...) do{if(std::getenv("NEX_OWNED_METAL_MAP_TRACE")){try{trace(__VA_ARGS__);}catch(...){}}}while(false)
static std::mutex traceMutex;
static std::atomic<uint64_t> identities{1};
static void trace(const JSON &value)noexcept{try{if(auto p=std::getenv("NEX_OWNED_METAL_MAP_TRACE")){std::lock_guard lock(traceMutex);auto row=value;row["steady_ns"]=std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now().time_since_epoch()).count();std::ofstream output(p,std::ios::app);output<<row.dump()<<'\n';}}catch(...) {}}
static void checked(nex_ffi_status value){if(value!=NEX_FFI_OK)throw HostStatus{value};}
static std::string workerPath(){Dl_info info{};if(!dladdr(reinterpret_cast<const void*>(&workerPath),&info)||!info.dli_fname)throw Error("E_DEVICE_ABI","module cannot resolve its pinned snapshot");return (std::filesystem::path(info.dli_fname).parent_path()/"worker").string();}

struct BoundedLog {
 static constexpr size_t part=32736;
 std::array<char,part> first{},last{};size_t head=0,tail=0,next=0;uint64_t total=0;
 void append(const char *data,size_t size)noexcept{
  total=size>UINT64_MAX-total?UINT64_MAX:total+size;
  auto prefix=std::min(size,part-head);std::memcpy(first.data()+head,data,prefix);head+=prefix;data+=prefix;size-=prefix;if(!size)return;
  if(size>=part){std::memcpy(last.data(),data+size-part,part);next=0;tail=part;return;}
  auto count=std::min(size,part-next);std::memcpy(last.data()+next,data,count);if(size>count)std::memcpy(last.data(),data+count,size-count);
  next=(next+size)%part;tail=std::min(part,tail+size);
 }
 static void writeAll(int fd,const char *data,size_t size)noexcept{
  while(size){auto n=::write(fd,data,size);if(n<0&&errno==EINTR)continue;if(n<=0)return;data+=n;size-=size_t(n);}
 }
 void flush(int fd)const noexcept{
  writeAll(fd,first.data(),head);auto dropped=total-head-tail;
  if(dropped){char marker[64];auto n=std::snprintf(marker,sizeof(marker),"\nNEXGPU_LOG_DROPPED %llu\n",static_cast<unsigned long long>(dropped));if(n>0&&size_t(n)<sizeof(marker))writeAll(fd,marker,size_t(n));}
  auto start=tail==part?next:0,count=std::min(tail,part-start);writeAll(fd,last.data()+start,count);if(tail>count)writeAll(fd,last.data(),tail-count);
 }
};

class Session {
 std::mutex mutex;int stream=-1;pid_t pid=-1;uint64_t sequence=0,nextBuffer=1;
 bool drained=false,failed=false;std::string directory;
 std::atomic<uint32_t> queued{0};
 BoundedLog log;std::thread logReader;std::atomic<bool> logStop{false};
 void startLog(int input,int output){
  logReader=std::thread([this,input,output]{
   struct Close{int a,b;~Close(){::close(a);::close(b);}} close{input,output};char buffer[4096];unsigned finalReads=0;
   for(;;){bool stop=logStop.load();if(stop&&finalReads>=16)break;pollfd p{input,POLLIN,0};auto ready=::poll(&p,1,20);
    if(ready<0&&errno==EINTR)continue;if(ready<0||(!ready&&stop))break;if(!ready)continue;
    if(!(p.revents&(POLLIN|POLLHUP)))break;
    auto n=::read(input,buffer,sizeof(buffer));if(n<0&&errno==EINTR)continue;if(n<=0)break;log.append(buffer,size_t(n));if(stop)++finalReads;
   }
   log.flush(output);
  });
 }
 void stopLog()noexcept{logStop=true;if(logReader.joinable())logReader.join();}
 // Unknown vendor settlement is never converted to a completed resource fence.
 [[noreturn]] void retainUnsettled()noexcept{
  TRACE(JSON{{"event","unsettled"},{"session",identity},{"physical_completion_verified",false}});
  std::fputs("NEX E_DEVICE_UNSETTLED: physical GPU completion is unproven; resource capacity remains retained\n",stderr);
  for(;;)std::this_thread::sleep_for(std::chrono::seconds(1));
 }
 void wait(const Poll &poll={}){
  if(pid<0)return;int status=0;
  for(;;){if(poll)poll();auto n=waitpid(pid,&status,WNOHANG);if(n==pid)break;if(n<0&&errno==EINTR)continue;if(n<0)retainUnsettled();std::this_thread::sleep_for(std::chrono::milliseconds(2));}
  auto reaped=pid;pid=-1;
  TRACE(JSON{{"event","worker_exited"},{"session",identity},{"worker_pid",reaped},{"wait_status",status},{"exit_code",WIFEXITED(status)?WEXITSTATUS(status):-1},{"signal",WIFSIGNALED(status)?WTERMSIG(status):0}});
  // These exits are emitted by the pinned worker only after explicit queue
  // drainage and object release, including a failed protocol's EOF cleanup.
  if(!WIFEXITED(status)||(WEXITSTATUS(status)!=0&&WEXITSTATUS(status)!=20))retainUnsettled();
  drained=true;
 }
 void failedDrain(const Poll &poll={}){
  if(drained)return;
  failed=true;if(stream>=0){::close(stream);stream=-1;}wait(poll);if(!drained&&pid>=0)retainUnsettled();stopLog();
  TRACE(JSON{{"event","failed_session_drained"},{"session",identity},{"physical_completion_verified",drained}});
 }
 Data callLocked(uint32_t operation,Data input,const Poll &poll){
  if(failed||drained||stream<0)throw Error("E_DEVICE_LOST","persistent GPU session is no longer available");
  const auto id=++sequence;Frame response{};bool progressed=false;
  struct QueuedGuard{std::atomic<uint32_t> &value;~QueuedGuard(){value=0;}} queuedGuard{queued};
  try{
   send(stream,Frame{id,operation,Success,std::move(input.bytes)},poll);
   for(;;){
    if(!receive(stream,response,poll)||response.sequence!=id||response.operation!=operation)throw Error("E_DEVICE_PROTOCOL","worker acknowledgement does not match the admitted command");
    if(response.status!=Progress)break;
    Data progress(std::move(response.payload));if(operation!=Generated||progressed||progress.get32()!=1)throw Error("E_DEVICE_PROTOCOL","invalid GPU progress acknowledgement");auto state=progress.get32(),gate=progress.get32();progress.done();if(state<2||state>4||gate>1)throw Error("E_DEVICE_PROTOCOL","invalid queued physical event status");progressed=true;
    TRACE(JSON{{"event","kernel_queued"},{"session",identity},{"sequence",id},{"physical_enqueue_verified",true},{"execution_status",state},{"completion_pending",state!=4},{"controlled_shared_event",gate==1}});
    queued=1;
   }
  }catch(...){failedDrain(poll);throw;}
  if(response.status==Unsettled){failedDrain(poll);throw Error("E_DEVICE_UNSETTLED","worker could not confirm physical completion");}
  if(response.status==Failure){
   std::string code,message;
   try{Data error(std::move(response.payload));code=error.getText();message=error.getText();error.done();if(code.empty()||code.size()>128||message.size()>2048)throw Error("E_DEVICE_PROTOCOL","worker error bounds differ");}
   catch(...){failedDrain(poll);throw;}
   if(code=="E_DEVICE_PROTOCOL"||code=="E_DEVICE_ABI"||code=="E_DEVICE_BUFFER")failedDrain(poll);
   throw Error(code,message);
  }
  return Data(std::move(response.payload));
 }
public:
 // Only the synchronous Success decoder calls this while holding mutex.
 void acceptBuffer(uint64_t id){if(id!=nextBuffer)throw Error("E_DEVICE_PROTOCOL","worker buffer identity is not the next unique allocation");++nextBuffer;}
 const uint64_t identity=identities.fetch_add(1);
 std::string name;uint64_t registryID=0;
 uint32_t busy()const noexcept{return queued.load();}
 bool available(const nex_ffi_api_v1 *api,nex_ffi_call call){
  std::unique_lock lock(mutex,std::defer_lock);while(!lock.try_lock()){checked(api->poll(call));std::this_thread::sleep_for(std::chrono::milliseconds(1));}
  checked(api->poll(call));return !failed&&!drained&&stream>=0&&pid>=0;
 }
 ~Session()noexcept{
  try{
   std::unique_lock lock(mutex);
   if(pid>=0){
    if(!failed){try{Data empty;auto result=callLocked(Close,std::move(empty),{});if(result.get32()!=0)throw Error("E_DEVICE_PROTOCOL","nonempty session close acknowledgement");result.done();}catch(...){failedDrain();}}
    if(stream>=0){::close(stream);stream=-1;}wait();
   }
   if(stream>=0)::close(stream);stopLog();
   TRACE(JSON{{"event","session_destroyed"},{"session",identity},{"physical_completion_verified",drained||pid<0}});
   if(!directory.empty()){
    if(std::getenv("NEX_OWNED_METAL_MAP_TRACE")){try{std::ifstream f(std::filesystem::path(directory)/"vendor.log",std::ios::binary);std::string raw(65536,'\0');f.read(raw.data(),raw.size());raw.resize(size_t(f.gcount()));std::string hex;hex.reserve(raw.size()*2);for(unsigned char c:raw){hex+="0123456789abcdef"[c>>4];hex+="0123456789abcdef"[c&15];}TRACE(JSON{{"event","worker_diagnostics"},{"session",identity},{"bytes",raw.size()},{"received_bytes",log.total},{"bounded_capture",true},{"hex",hex}});}catch(...){}}
    std::error_code ec;std::filesystem::remove_all(directory,ec);
   }
  }catch(...){if(pid>=0&&!drained)retainUnsettled();stopLog();}
 }
 template<class Decode>auto call(uint32_t operation,Data input,Decode decode,const nex_ffi_api_v1 *api=nullptr,nex_ffi_call token=0){
  std::unique_lock lock(mutex,std::defer_lock);
  while(!lock.try_lock()){if(api)checked(api->poll(token));std::this_thread::sleep_for(std::chrono::milliseconds(1));}
  if(api)checked(api->poll(token));
  // Once admitted, cancellation becomes sticky in the host call but never
  // aborts transport or discards the buffer ID needed by unpublished cleanup.
  Poll observe;if(api)observe=[=]{(void)api->poll(token);};
  // Worker Failure responses retain their checked error semantics. A Success
  // payload must be fully decoded and validated before another command can
  // enter, or before a failed factory returns any physical capacity.
  auto response=callLocked(operation,std::move(input),observe);
  try{return decode(response);}catch(...){failedDrain(observe);throw;}
 }
 void start(uint32_t ordinal,const nex_ffi_api_v1 *api,nex_ffi_call call){
  std::string pattern=(std::filesystem::temp_directory_path()/"nex-owned-metal-XXXXXX").string();auto created=mkdtemp(pattern.data());if(!created)throw Error("E_DEVICE_PROCESS","private worker directory creation failed");directory=created;
  int sockets[2]={-1,-1};if(socketpair(AF_UNIX,SOCK_STREAM,0,sockets))throw Error("E_DEVICE_PROCESS","private worker socket creation failed");
  struct FDs{int a,b,log=-1,reader=-1,writer=-1;~FDs(){for(auto fd:{a,b,log,reader,writer})if(fd>=0)::close(fd);}} fds{sockets[0],sockets[1]};
  fcntl(fds.a,F_SETFD,FD_CLOEXEC);int elevated=fcntl(fds.b,F_DUPFD_CLOEXEC,10);if(elevated<0)throw Error("E_DEVICE_PROCESS","private protocol descriptor duplication failed");::close(fds.b);fds.b=elevated;
#ifdef SO_NOSIGPIPE
  int enabled=1;if(setsockopt(fds.a,SOL_SOCKET,SO_NOSIGPIPE,&enabled,sizeof(enabled)))throw Error("E_DEVICE_PROCESS","private socket signal policy failed");
#endif
  fds.log=::open((std::filesystem::path(directory)/"vendor.log").c_str(),O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0600);if(fds.log<0)throw Error("E_DEVICE_PROCESS","private worker log creation failed");
  int logs[2];
#ifdef __linux__
  if(pipe2(logs,O_CLOEXEC))throw Error("E_DEVICE_PROCESS","private worker log pipe failed");
#else
  if(pipe(logs))throw Error("E_DEVICE_PROCESS","private worker log pipe failed");
#endif
  fds.reader=logs[0];fds.writer=logs[1];
  if(fcntl(fds.reader,F_SETFD,FD_CLOEXEC)||fcntl(fds.writer,F_SETFD,FD_CLOEXEC))throw Error("E_DEVICE_PROCESS","private log descriptor policy failed");
  startLog(fds.reader,fds.log);fds.reader=-1;fds.log=-1;
  posix_spawn_file_actions_t actions;if(posix_spawn_file_actions_init(&actions))throw Error("E_DEVICE_PROCESS","spawn actions initialization failed");
  struct Actions{posix_spawn_file_actions_t *p;~Actions(){posix_spawn_file_actions_destroy(p);}} guard{&actions};
  auto add=[&](int code){if(code)throw Error("E_DEVICE_PROCESS","private worker spawn action failed");};
  add(posix_spawn_file_actions_adddup2(&actions,fds.writer,1));add(posix_spawn_file_actions_adddup2(&actions,fds.writer,2));
  if(fds.writer>2)add(posix_spawn_file_actions_addclose(&actions,fds.writer));if(fds.a>2)add(posix_spawn_file_actions_addclose(&actions,fds.a));
  add(posix_spawn_file_actions_addopen(&actions,0,"/dev/null",O_RDONLY,0));add(posix_spawn_file_actions_adddup2(&actions,fds.b,3));add(posix_spawn_file_actions_addclose(&actions,fds.b));
  posix_spawnattr_t attributes;add(posix_spawnattr_init(&attributes));struct Attributes{posix_spawnattr_t *p;~Attributes(){posix_spawnattr_destroy(p);}} attributesGuard{&attributes};
#ifdef POSIX_SPAWN_CLOEXEC_DEFAULT
  add(posix_spawnattr_setflags(&attributes,POSIX_SPAWN_CLOEXEC_DEFAULT));
#endif
  auto worker=workerPath();char *argv[]={worker.data(),nullptr};pid_t child=-1;auto status=posix_spawn(&child,worker.c_str(),&actions,&attributes,argv,environ);
  if(status)throw Error("E_DEVICE_PROCESS","pinned worker spawn failed: "+std::to_string(status));
  ::close(fds.b);fds.b=-1;::close(fds.writer);fds.writer=-1;
  pid=child;stream=fds.a;fds.a=-1;Data input;input.u32(ordinal);this->call(Open,std::move(input),[&](Data &response){
   auto receivedName=response.getText();auto receivedRegistryID=response.get64();auto limit=response.get32();auto arguments=response.get32();auto shader=response.getText();response.done();
   if(receivedName.empty()||receivedName.size()>4096||!receivedRegistryID||limit!=maximumElements||arguments!=GENERATED_ARGUMENTS||shader!=GENERATED_SHADER_SHA256)throw Error("E_DEVICE_ABI","physical GPU identity, kernel or limits differ");
   name=std::move(receivedName);registryID=receivedRegistryID;
  },api,call);
  TRACE(JSON{{"event","session_created"},{"session",identity},{"worker_pid",pid},{"device",name},{"backend","Metal"},{"registryID",registryID},{"ordinal",ordinal},{"persistent",true},{"cpu_fallback",false}});
 }
 void release(uint64_t id)noexcept{
  try{std::unique_lock lock(mutex);uint32_t live=0;bool wholeSession=drained;
   if(!drained){try{Data input;input.u64(id);auto result=callLocked(Free,std::move(input),{});live=result.get32();result.done();}catch(...){failedDrain();wholeSession=true;}}
   TRACE(JSON{{"event","buffer_released"},{"session",identity},{"buffer",id},{"worker_live_buffers",live},{"via_session_drain",wholeSession},{"physical_completion_verified",true}});
  }
  catch(...){retainUnsettled();}
 }
};
struct Buffer {
 Session *session=nullptr;uint64_t id=0,bytes=0,kernelNs=0;uint32_t dtype=0;
 ~Buffer()noexcept{if(id&&session)session->release(id);}
};
struct ReadCursor {
 Buffer *buffer=nullptr;uint64_t offset=0;std::mutex mutex;const uint64_t identity=identities.fetch_add(1);
 ~ReadCursor()noexcept{if(buffer)TRACE(JSON{{"event","read_cursor_destroyed"},{"session",buffer->session->identity},{"cursor",identity},{"buffer",buffer->id},{"offset",offset}});}
};
static void destroyCursor(void *p)noexcept{delete static_cast<ReadCursor*>(p);}
static void destroySession(void *p)noexcept{delete static_cast<Session*>(p);}
static void destroyBuffer(void *p)noexcept{delete static_cast<Buffer*>(p);}
struct Creation {
 enum Kind{SessionOpen,BufferUpload,BufferGenerated,ReaderOpen}kind;
 Session *session=nullptr;Buffer *a=nullptr;uint32_t ordinal=0,dtype=0,lanes=0,steps=0;Bytes data;std::string code,message;
 std::vector<Buffer*> columns;
};
static nex_ffi_status creationError(Creation &in,const char *code,const char *message)noexcept{
 try{in.code=code;in.message=message;return NEX_FFI_INTERNAL;}catch(...){return NEX_FFI_LIMIT;}
}
static nex_ffi_status factory(const nex_ffi_api_v1 *api,nex_ffi_call call,void *user,void **out)noexcept{
 auto &in=*static_cast<Creation*>(user);
 try{
  if(in.kind==Creation::SessionOpen){auto value=std::make_unique<Session>();auto pointer=value.get();*out=value.release();pointer->start(in.ordinal,api,call);}
  else if(in.kind==Creation::ReaderOpen){
   auto value=std::make_unique<ReadCursor>();value->buffer=in.a;
   TRACE(JSON{{"event","read_cursor_created"},{"session",in.a->session->identity},{"cursor",value->identity},{"buffer",in.a->id}});
   *out=value.release();
  }
  else{
   auto value=std::make_unique<Buffer>();auto pointer=value.get();pointer->session=in.session;pointer->dtype=in.dtype;*out=value.release();Data payload;
   if(in.kind==Creation::BufferUpload){payload.u32(in.dtype);payload.blob(in.data);in.session->call(Upload,std::move(payload),[&](Data &result){auto id=result.get64(),bytes=result.get64();result.done();if(!id||bytes!=in.data.size())throw Error("E_DEVICE_PROTOCOL","upload acknowledgement differs");in.session->acceptBuffer(id);pointer->id=id;pointer->bytes=bytes;},api,call);}
   else{
    payload.u32(uint32_t(in.columns.size()));for(auto column:in.columns)payload.u64(column->id);payload.u32(in.lanes);payload.u32(in.steps);
    const uint64_t expectedBytes=uint64_t(in.lanes)*8;
    in.session->call(Generated,std::move(payload),[&](Data &result){
     auto id=result.get64(),bytes=result.get64(),kernelNs=result.get64();auto executed=result.get32(),handlers=result.get32();result.done();
     if(!id||bytes!=expectedBytes||kernelNs>uint64_t(INT64_MAX)||executed!=4||handlers!=1)throw Error("E_DEVICE_PROTOCOL","physical kernel acknowledgement differs");
     in.session->acceptBuffer(id);pointer->id=id;pointer->bytes=bytes;pointer->kernelNs=kernelNs;
     TRACE(JSON{{"event","kernel_completed"},{"session",in.session->identity},{"buffer",id},{"elements",in.lanes},
      {"operation","generated_map"},{"dtype",in.dtype},{"columns",in.columns.size()},{"steps",in.steps},{"kernel_sha256",GENERATED_SHADER_SHA256},{"kernel_ns",kernelNs},
      {"Metal_command_buffer_status",executed},{"completion_handlers",handlers},{"physical_completion_verified",true},{"cpu_fallback",false}});
    },api,call);
   }
   TRACE(JSON{{"event","buffer_created"},{"session",in.session->identity},{"buffer",pointer->id},{"bytes",pointer->bytes},{"dtype",pointer->dtype}});
  }
  return api->poll(call);
 }catch(const HostStatus &e){return e.value;}
 catch(const Error &e){return creationError(in,e.code.c_str(),e.what());}
 catch(const std::exception &e){return creationError(in,"E_DEVICE_HOST",e.what());}
 catch(...){return creationError(in,"E_DEVICE_HOST","unexpected trusted provider failure");}
}
static int64_t integer(const nex_ffi_api_v1 *api,nex_ffi_call c,nex_ffi_ref r){int64_t v=0;checked(api->get_i64(c,r,&v));return v;}
static void *borrow(const nex_ffi_api_v1 *api,nex_ffi_call c,nex_ffi_ref r,uint64_t argument){nex_ffi_type t=0;checked(api->argument_type(c,argument,&t));void *p=nullptr;checked(api->resource_borrow(c,r,t,&p));return p;}
static nex_ffi_status failure(const nex_ffi_api_v1 *api,nex_ffi_call call,nex_ffi_ref *out,const std::string &code,const std::string &text){auto message=text.substr(0,2048);return api->make_failure(call,reinterpret_cast<const uint8_t*>(code.data()),code.size(),reinterpret_cast<const uint8_t*>(message.data()),message.size(),out);}
static nex_ffi_status construct(const nex_ffi_api_v1 *api,nex_ffi_call call,Creation &input,uint64_t capacity,nex_ffi_ref parent,nex_ffi_ref *out){
 nex_ffi_type type=0;checked(api->result_type(call,&type));checked(api->type_child(call,type,0,0,&type));nex_ffi_ref value=0;
 auto status=input.kind==Creation::SessionOpen?api->resource_create(call,type,capacity,factory,destroySession,&input,&value):api->resource_create_with_parents(call,type,capacity,&parent,1,factory,input.kind==Creation::ReaderOpen?destroyCursor:destroyBuffer,&input,&value);
 if(status!=NEX_FFI_OK){if(status==NEX_FFI_HOST_TRAP)return status;if(!input.code.empty())return failure(api,call,out,input.code,input.message);if(status==NEX_FFI_LIMIT)return failure(api,call,out,"E_COMPUTE_LIMIT","declared owned device capacity is exhausted");return status;}
 return api->make_success(call,value,out);
}
static nex_ffi_status callback(const nex_ffi_api_v1 *api,nex_ffi_call call,const nex_ffi_ref *args,uint64_t count,nex_ffi_ref *out,void *user)noexcept{
 try{
  if(api->struct_size<NEX_FFI_V1_RESOURCE_PARENTS_SIZE)return NEX_FFI_ARGUMENT;checked(api->poll(call));auto op=uint64_t(user);
  if(op==1){if(count!=1)return NEX_FFI_ARGUMENT;auto ordinal=integer(api,call,args[0]);if(ordinal<0||ordinal>63)return failure(api,call,out,"E_COMPUTE_DEVICE","GPU index must be0..63");Creation in{Creation::SessionOpen};in.ordinal=uint32_t(ordinal);return construct(api,call,in,maximumElements+sizeof(Session),0,out);}
  if(op==2){if(count!=3)return NEX_FFI_ARGUMENT;auto *session=static_cast<Session*>(borrow(api,call,args[0],0));auto dtype=integer(api,call,args[1]);if(dtype!=1)return failure(api,call,out,"E_GPU_INPUT","generated input uses immutable byte columns");uint64_t size=0;checked(api->byte_size(call,args[2],&size));auto width=dtype==3?4u:1u;if(!size||size>uint64_t(maximumElements)*width||size>1044480||size%width)return failure(api,call,out,"E_COMPUTE_SIZE","buffer byte count exceeds exact dtype bounds");Creation in{Creation::BufferUpload};in.session=session;in.dtype=uint32_t(dtype);in.data.resize(size);uint64_t copied=0;checked(api->copy_bytes(call,args[2],0,in.data.data(),size,&copied));if(copied!=size)return NEX_FFI_INTERNAL;return construct(api,call,in,size+sizeof(Buffer),args[0],out);}
  if(op==3){
   if(count!=4)return NEX_FFI_ARGUMENT;
   auto *session=static_cast<Session*>(borrow(api,call,args[0],0));
   auto lanes=integer(api,call,args[2]),steps=integer(api,call,args[3]);
   if(lanes<1||lanes>32768||steps<1||steps>65536||uint64_t(lanes)*uint64_t(steps)>16777216)
    return failure(api,call,out,"E_GPU_INPUT","generated kernel geometry exceeds declared bounds");
   uint64_t length=0;checked(api->child_count(call,args[1],&length));
   if(length!=GENERATED_ARGUMENTS||length>8)return failure(api,call,out,"E_GPU_INPUT","column count differs from selected scalar function");
   nex_ffi_type listType=0,elementType=0;checked(api->argument_type(call,1,&listType));checked(api->type_child(call,listType,0,0,&elementType));
   Creation in{Creation::BufferGenerated};in.session=session;in.dtype=1;in.lanes=uint32_t(lanes);in.steps=uint32_t(steps);
   for(uint64_t i=0;i<length;++i){nex_ffi_ref child=0;checked(api->child(call,args[1],i,&child));void *pointer=nullptr;checked(api->resource_borrow(call,child,elementType,&pointer));
    auto *column=static_cast<Buffer*>(pointer);
    if(column->session!=session)return failure(api,call,out,"E_GPU_INPUT","column belongs to another physical session");
    if(column->dtype!=1||column->bytes!=uint64_t(lanes)*8)return failure(api,call,out,"E_GPU_INPUT","column bytes do not match selected scalar function");
    in.columns.push_back(column);
   }
   return construct(api,call,in,uint64_t(lanes)*8+sizeof(Buffer),args[0],out);
  }
  if(op==4){
   if(count!=1)return NEX_FFI_ARGUMENT;auto *buffer=static_cast<Buffer*>(borrow(api,call,args[0],0));
   if(!buffer->session->available(api,call))return failure(api,call,out,"E_DEVICE_LOST","persistent GPU session is no longer available");
   Creation in{Creation::ReaderOpen};in.a=buffer;return construct(api,call,in,sizeof(ReadCursor),args[0],out);
  }
  if(op==8){
   if(count!=1)return NEX_FFI_ARGUMENT;auto *cursor=static_cast<ReadCursor*>(borrow(api,call,args[0],0));
   std::unique_lock lock(cursor->mutex,std::defer_lock);while(!lock.try_lock()){checked(api->poll(call));std::this_thread::sleep_for(std::chrono::milliseconds(1));}
   checked(api->poll(call));auto *buffer=cursor->buffer;
   if(cursor->offset>buffer->bytes)return NEX_FFI_INTERNAL;
   const auto expected=std::min<uint64_t>(262144,buffer->bytes-cursor->offset);
   Data request;request.u64(buffer->id);request.u64(cursor->offset);request.u32(uint32_t(expected));
   auto bytes=buffer->session->call(Download,std::move(request),[&](Data &result){auto data=result.getBlob();result.done();
    if(data.size()!=expected)throw Error("E_DEVICE_PROTOCOL","download chunk byte count differs");return data;},api,call);
   nex_ffi_ref value=0;checked(api->make_bytes(call,bytes.data(),bytes.size(),&value));auto status=api->make_success(call,value,out);
   if(status==NEX_FFI_OK){cursor->offset+=bytes.size();TRACE(JSON{{"event","read_cursor_chunk"},{"session",buffer->session->identity},
     {"cursor",cursor->identity},{"buffer",buffer->id},{"bytes",bytes.size()},{"offset",cursor->offset}});}
   return status;
  }
  if(op==5){if(count!=1)return NEX_FFI_ARGUMENT;auto *session=static_cast<Session*>(borrow(api,call,args[0],0));return api->make_string(call,reinterpret_cast<const uint8_t*>(session->name.data()),session->name.size(),out);}
  if(op==6){if(count!=1)return NEX_FFI_ARGUMENT;auto *buffer=static_cast<Buffer*>(borrow(api,call,args[0],0));if(buffer->kernelNs>uint64_t(INT64_MAX))return NEX_FFI_RANGE;return api->make_i64(call,int64_t(buffer->kernelNs),out);}
  if(op==7){if(count!=1)return NEX_FFI_ARGUMENT;auto *session=static_cast<Session*>(borrow(api,call,args[0],0));auto busy=session->busy();if(busy)TRACE(JSON{{"event","kernel_busy_observed"},{"session",session->identity}});return api->make_i64(call,busy,out);}
  return NEX_FFI_ARGUMENT;
 }catch(const HostStatus &e){return e.value;}catch(const Error &e){return failure(api,call,out,e.code,e.what());}catch(...){return NEX_FFI_INTERNAL;}
}
static const nex_ffi_export_v1 exports[]={
 {sizeof(nex_ffi_export_v1),0,"open",PIN_OPEN,callback,(void*)1},
 {sizeof(nex_ffi_export_v1),0,"upload",PIN_UPLOAD,callback,(void*)2},
 {sizeof(nex_ffi_export_v1),0,"map",PIN_MAP,callback,(void*)3},
 {sizeof(nex_ffi_export_v1),0,"download",PIN_DOWNLOAD,callback,(void*)4},
 {sizeof(nex_ffi_export_v1),0,"name",PIN_NAME,callback,(void*)5},
 {sizeof(nex_ffi_export_v1),0,"kernel_ns",PIN_KERNEL_NS,callback,(void*)6},
 {sizeof(nex_ffi_export_v1),0,"busy",PIN_BUSY,callback,(void*)7},
 {sizeof(nex_ffi_export_v1),0,"read_next",PIN_READ_NEXT,callback,(void*)8}
};
extern "C" const nex_ffi_module_v1 *nex_ffi_module_entry(uint32_t abi,uint32_t size){static const nex_ffi_module_v1 m{NEX_FFI_MODULE_ABI_V1,sizeof(nex_ffi_module_v1),sizeof(exports)/sizeof(exports[0]),sizeof(nex_ffi_export_v1),exports};return abi==1&&size>=NEX_FFI_V1_RESOURCE_PARENTS_SIZE?&m:nullptr;}
