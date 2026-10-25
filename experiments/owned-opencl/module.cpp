#include "nex_ffi_module.h"
#include "protocol.h"
#include "signatures.h"
#include "third_party/json.hpp"
#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <dlfcn.h>
#include <fcntl.h>
#include <filesystem>
#include <fstream>
#include <mutex>
#include <spawn.h>
#include <thread>
#include <sys/wait.h>
extern char **environ;
using namespace owned_gpu;
using JSON=nlohmann::json;
struct HostStatus {nex_ffi_status value;};
#define TRACE(...) do{if(std::getenv("NEX_OWNED_OPENCL_TRACE")){try{trace(__VA_ARGS__);}catch(...){}}}while(false)
static std::mutex traceMutex;
static std::atomic<uint64_t> identities{1};
static void trace(const JSON &value)noexcept{try{if(auto p=std::getenv("NEX_OWNED_OPENCL_TRACE")){std::lock_guard lock(traceMutex);auto row=value;row["steady_ns"]=std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now().time_since_epoch()).count();std::ofstream output(p,std::ios::app);output<<row.dump()<<'\n';}}catch(...) {}}
static void checked(nex_ffi_status value){if(value!=NEX_FFI_OK)throw HostStatus{value};}
static std::string workerPath(){Dl_info info{};if(!dladdr(reinterpret_cast<const void*>(&workerPath),&info)||!info.dli_fname)throw Error("E_DEVICE_ABI","module cannot resolve its pinned snapshot");return (std::filesystem::path(info.dli_fname).parent_path()/"worker").string();}

class Session {
 std::mutex mutex;int stream=-1;pid_t pid=-1;uint64_t sequence=0,nextBuffer=1;
 bool drained=false,failed=false;std::string directory;
 std::atomic<uint32_t> queued{0};
 // Unknown vendor settlement is never converted to a completed resource fence.
 [[noreturn]] void retainUnsettled()noexcept{
  TRACE(JSON{{"event","unsettled"},{"session",identity},{"physical_completion_verified",false}});
  std::fputs("NEX E_DEVICE_UNSETTLED: physical GPU completion is unproven; resource capacity remains retained\n",stderr);
  for(;;)std::this_thread::sleep_for(std::chrono::seconds(1));
 }
 void wait(const Poll &poll={}){
  if(pid<0)return;int status=0;
  for(;;){if(poll)poll();auto n=waitpid(pid,&status,WNOHANG);if(n==pid)break;if(n<0&&errno==EINTR)continue;if(n<0)retainUnsettled();std::this_thread::sleep_for(std::chrono::milliseconds(2));}
  pid=-1;
  // These exits are emitted by the pinned worker only after explicit queue
  // drainage and object release, including a failed protocol's EOF cleanup.
  if(!WIFEXITED(status)||(WEXITSTATUS(status)!=0&&WEXITSTATUS(status)!=20))retainUnsettled();
  drained=true;
 }
 void failedDrain(const Poll &poll={}){
  if(drained)return;
  failed=true;if(stream>=0){::close(stream);stream=-1;}wait(poll);if(!drained&&pid>=0)retainUnsettled();
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
    Data progress(std::move(response.payload));if(operation!=Affine||progressed||progress.get32()!=1)throw Error("E_DEVICE_PROTOCOL","invalid GPU progress acknowledgement");auto state=progress.get32(),gate=progress.get32();progress.done();if(state>3||gate>1)throw Error("E_DEVICE_PROTOCOL","invalid queued physical event status");progressed=true;
    TRACE(JSON{{"event","kernel_queued"},{"session",identity},{"sequence",id},{"physical_enqueue_verified",true},{"execution_status",state},{"completion_pending",state!=0},{"controlled_user_event",gate==1}});
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
 std::string name;uint64_t type=0;
 uint32_t busy()const noexcept{return queued.load();}
 ~Session()noexcept{
  try{
   std::unique_lock lock(mutex);
   if(pid>=0){
    if(!failed){try{Data empty;auto result=callLocked(Close,std::move(empty),{});if(result.get32()!=0)throw Error("E_DEVICE_PROTOCOL","nonempty session close acknowledgement");result.done();}catch(...){failedDrain();}}
    if(stream>=0){::close(stream);stream=-1;}wait();
   }
   if(stream>=0)::close(stream);
   TRACE(JSON{{"event","session_destroyed"},{"session",identity},{"physical_completion_verified",drained||pid<0}});
   if(!directory.empty()){
    if(std::getenv("NEX_OWNED_OPENCL_TRACE")){try{std::ifstream f(std::filesystem::path(directory)/"vendor.log",std::ios::binary);std::string raw(65536,'\0');f.read(raw.data(),raw.size());raw.resize(size_t(f.gcount()));std::string hex;hex.reserve(raw.size()*2);for(unsigned char c:raw){hex+="0123456789abcdef"[c>>4];hex+="0123456789abcdef"[c&15];}TRACE(JSON{{"event","worker_diagnostics"},{"session",identity},{"bytes",raw.size()},{"hex",hex}});}catch(...){}}
    std::error_code ec;std::filesystem::remove_all(directory,ec);
   }
  }catch(...){if(pid>=0&&!drained)retainUnsettled();}
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
  std::string pattern=(std::filesystem::temp_directory_path()/"nex-owned-opencl-XXXXXX").string();auto created=mkdtemp(pattern.data());if(!created)throw Error("E_DEVICE_PROCESS","private worker directory creation failed");directory=created;
  int sockets[2]={-1,-1};if(socketpair(AF_UNIX,SOCK_STREAM,0,sockets))throw Error("E_DEVICE_PROCESS","private worker socket creation failed");
  struct FDs{int a,b,log=-1;~FDs(){if(a>=0)::close(a);if(b>=0)::close(b);if(log>=0)::close(log);}} fds{sockets[0],sockets[1]};
  fcntl(fds.a,F_SETFD,FD_CLOEXEC);int elevated=fcntl(fds.b,F_DUPFD_CLOEXEC,10);if(elevated<0)throw Error("E_DEVICE_PROCESS","private protocol descriptor duplication failed");::close(fds.b);fds.b=elevated;
#ifdef SO_NOSIGPIPE
  int enabled=1;if(setsockopt(fds.a,SOL_SOCKET,SO_NOSIGPIPE,&enabled,sizeof(enabled)))throw Error("E_DEVICE_PROCESS","private socket signal policy failed");
#endif
  fds.log=::open((std::filesystem::path(directory)/"vendor.log").c_str(),O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0600);if(fds.log<0)throw Error("E_DEVICE_PROCESS","private worker log creation failed");
  posix_spawn_file_actions_t actions;if(posix_spawn_file_actions_init(&actions))throw Error("E_DEVICE_PROCESS","spawn actions initialization failed");
  struct Actions{posix_spawn_file_actions_t *p;~Actions(){posix_spawn_file_actions_destroy(p);}} guard{&actions};
  auto add=[&](int code){if(code)throw Error("E_DEVICE_PROCESS","private worker spawn action failed");};
  add(posix_spawn_file_actions_adddup2(&actions,fds.log,1));add(posix_spawn_file_actions_adddup2(&actions,fds.log,2));
  if(fds.log>2)add(posix_spawn_file_actions_addclose(&actions,fds.log));if(fds.a>2)add(posix_spawn_file_actions_addclose(&actions,fds.a));
  add(posix_spawn_file_actions_addopen(&actions,0,"/dev/null",O_RDONLY,0));add(posix_spawn_file_actions_adddup2(&actions,fds.b,3));add(posix_spawn_file_actions_addclose(&actions,fds.b));
  auto worker=workerPath();char *argv[]={worker.data(),nullptr};pid_t child=-1;auto status=posix_spawn(&child,worker.c_str(),&actions,nullptr,argv,environ);
  if(status)throw Error("E_DEVICE_PROCESS","pinned worker spawn failed: "+std::to_string(status));
  ::close(fds.b);fds.b=-1;::close(fds.log);fds.log=-1;
  pid=child;stream=fds.a;fds.a=-1;Data input;input.u32(ordinal);this->call(Open,std::move(input),[&](Data &response){
   auto receivedName=response.getText();auto receivedType=response.get64();auto limit=response.get32();response.done();
   if(receivedName.empty()||receivedName.size()>4096||!(receivedType&4)||receivedType&2||limit!=maximumElements)throw Error("E_DEVICE_ABI","physical GPU identity or limits differ");
   name=std::move(receivedName);type=receivedType;
  },api,call);
  TRACE(JSON{{"event","session_created"},{"session",identity},{"worker_pid",pid},{"device",name},{"device_type",type},{"ordinal",ordinal},{"persistent",true},{"cpu_fallback",false}});
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
static void destroySession(void *p)noexcept{delete static_cast<Session*>(p);}
static void destroyBuffer(void *p)noexcept{delete static_cast<Buffer*>(p);}
struct Creation {
 enum Kind{SessionOpen,BufferUpload,BufferAffine}kind;
 Session *session=nullptr;Buffer *a=nullptr,*b=nullptr;uint32_t ordinal=0,dtype=0,scale=0;Bytes data;std::string code,message;
};
static nex_ffi_status creationError(Creation &in,const char *code,const char *message)noexcept{
 try{in.code=code;in.message=message;return NEX_FFI_INTERNAL;}catch(...){return NEX_FFI_LIMIT;}
}
static nex_ffi_status factory(const nex_ffi_api_v1 *api,nex_ffi_call call,void *user,void **out)noexcept{
 auto &in=*static_cast<Creation*>(user);
 try{
  if(in.kind==Creation::SessionOpen){auto value=std::make_unique<Session>();auto pointer=value.get();*out=value.release();pointer->start(in.ordinal,api,call);}
  else{
   auto value=std::make_unique<Buffer>();auto pointer=value.get();pointer->session=in.session;pointer->dtype=in.dtype;*out=value.release();Data payload;
   if(in.kind==Creation::BufferUpload){payload.u32(in.dtype);payload.blob(in.data);in.session->call(Upload,std::move(payload),[&](Data &result){auto id=result.get64(),bytes=result.get64();result.done();if(!id||bytes!=in.data.size())throw Error("E_DEVICE_PROTOCOL","upload acknowledgement differs");in.session->acceptBuffer(id);pointer->id=id;pointer->bytes=bytes;},api,call);}
   else{payload.u64(in.a->id);payload.u64(in.b->id);payload.u32(in.scale);in.session->call(Affine,std::move(payload),[&](Data &result){auto id=result.get64(),bytes=result.get64(),kernelNs=result.get64();auto executed=result.get32(),command=result.get32();result.done();if(!id||bytes!=in.a->bytes||kernelNs>uint64_t(INT64_MAX)||executed!=0||command!=0x11f0)throw Error("E_DEVICE_PROTOCOL","physical kernel acknowledgement differs");in.session->acceptBuffer(id);pointer->id=id;pointer->bytes=bytes;pointer->kernelNs=kernelNs;TRACE(JSON{{"event","kernel_completed"},{"session",in.session->identity},{"buffer",id},{"elements",bytes},{"scale",in.scale},{"kernel_ns",kernelNs},{"command_type",command},{"physical_completion_verified",true},{"cpu_fallback",false}});},api,call);}
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
 auto status=input.kind==Creation::SessionOpen?api->resource_create(call,type,capacity,factory,destroySession,&input,&value):api->resource_create_with_parents(call,type,capacity,&parent,1,factory,destroyBuffer,&input,&value);
 if(status!=NEX_FFI_OK){if(status==NEX_FFI_HOST_TRAP)return status;if(!input.code.empty())return failure(api,call,out,input.code,input.message);if(status==NEX_FFI_LIMIT)return failure(api,call,out,"E_COMPUTE_LIMIT","declared owned device capacity is exhausted");return status;}
 return api->make_success(call,value,out);
}
static nex_ffi_status callback(const nex_ffi_api_v1 *api,nex_ffi_call call,const nex_ffi_ref *args,uint64_t count,nex_ffi_ref *out,void *user)noexcept{
 try{
  if(api->struct_size<NEX_FFI_V1_RESOURCE_PARENTS_SIZE)return NEX_FFI_ARGUMENT;checked(api->poll(call));auto op=uint64_t(user);
  if(op==1){if(count!=1)return NEX_FFI_ARGUMENT;auto ordinal=integer(api,call,args[0]);if(ordinal<0||ordinal>63)return failure(api,call,out,"E_COMPUTE_DEVICE","GPU index must be0..63");Creation in{Creation::SessionOpen};in.ordinal=uint32_t(ordinal);return construct(api,call,in,maximumElements+sizeof(Session),0,out);}
  if(op==2){if(count!=3)return NEX_FFI_ARGUMENT;auto *session=static_cast<Session*>(borrow(api,call,args[0],0));auto dtype=integer(api,call,args[1]);if(dtype<1||dtype>3)return failure(api,call,out,"E_COMPUTE_DTYPE","unsupported immutable buffer dtype");uint64_t size=0;checked(api->byte_size(call,args[2],&size));auto width=dtype==3?4u:1u;if(!size||size>uint64_t(maximumElements)*width||size>1044480||size%width)return failure(api,call,out,"E_COMPUTE_SIZE","buffer byte count exceeds exact dtype bounds");Creation in{Creation::BufferUpload};in.session=session;in.dtype=uint32_t(dtype);in.data.resize(size);uint64_t copied=0;checked(api->copy_bytes(call,args[2],0,in.data.data(),size,&copied));if(copied!=size)return NEX_FFI_INTERNAL;return construct(api,call,in,size+sizeof(Buffer),args[0],out);}
  if(op==3){if(count!=5)return NEX_FFI_ARGUMENT;auto *session=static_cast<Session*>(borrow(api,call,args[0],0));auto *a=static_cast<Buffer*>(borrow(api,call,args[1],1)),*b=static_cast<Buffer*>(borrow(api,call,args[2],2));auto mode=integer(api,call,args[3]),scale=integer(api,call,args[4]);if(mode==3)return failure(api,call,out,"E_COMPUTE_UNSUPPORTED","owned OpenCL provider has no matmul kernel");if((mode!=1&&mode!=2)||scale<0||scale>255||(mode==1&&scale!=1))return failure(api,call,out,"E_COMPUTE_RANGE","invalid exact affine operation");if(a->session!=session||b->session!=session)return failure(api,call,out,"E_COMPUTE_DEVICE","buffer belongs to another physical session");if(a->dtype!=1||b->dtype!=1||a->bytes!=b->bytes||a->bytes>maximumElements)return failure(api,call,out,"E_COMPUTE_SIZE","input buffer dtype or bytes disagree");Creation in{Creation::BufferAffine};in.session=session;in.a=a;in.b=b;in.dtype=1;in.scale=uint32_t(scale);return construct(api,call,in,a->bytes+sizeof(Buffer),args[0],out);}
  if(op==4){if(count!=1)return NEX_FFI_ARGUMENT;auto *buffer=static_cast<Buffer*>(borrow(api,call,args[0],0));Data request;request.u64(buffer->id);auto bytes=buffer->session->call(Download,std::move(request),[&](Data &result){auto data=result.getBlob();result.done();if(data.size()!=buffer->bytes)throw Error("E_DEVICE_PROTOCOL","download byte count differs");return data;},api,call);nex_ffi_ref value=0;checked(api->make_bytes(call,bytes.data(),bytes.size(),&value));return api->make_success(call,value,out);}
  if(op==5){if(count!=1)return NEX_FFI_ARGUMENT;auto *session=static_cast<Session*>(borrow(api,call,args[0],0));return api->make_string(call,reinterpret_cast<const uint8_t*>(session->name.data()),session->name.size(),out);}
  if(op==6){if(count!=1)return NEX_FFI_ARGUMENT;auto *buffer=static_cast<Buffer*>(borrow(api,call,args[0],0));if(buffer->kernelNs>uint64_t(INT64_MAX))return NEX_FFI_RANGE;return api->make_i64(call,int64_t(buffer->kernelNs),out);}
  if(op==7){if(count!=1)return NEX_FFI_ARGUMENT;auto *session=static_cast<Session*>(borrow(api,call,args[0],0));auto busy=session->busy();if(busy)TRACE(JSON{{"event","kernel_busy_observed"},{"session",session->identity}});return api->make_i64(call,busy,out);}
  return NEX_FFI_ARGUMENT;
 }catch(const HostStatus &e){return e.value;}catch(const Error &e){return failure(api,call,out,e.code,e.what());}catch(...){return NEX_FFI_INTERNAL;}
}
static const nex_ffi_export_v1 exports[]={
 {sizeof(nex_ffi_export_v1),0,"open",PIN_OPEN,callback,(void*)1},
 {sizeof(nex_ffi_export_v1),0,"upload",PIN_UPLOAD,callback,(void*)2},
 {sizeof(nex_ffi_export_v1),0,"dispatch",PIN_DISPATCH,callback,(void*)3},
 {sizeof(nex_ffi_export_v1),0,"download",PIN_DOWNLOAD,callback,(void*)4},
 {sizeof(nex_ffi_export_v1),0,"name",PIN_NAME,callback,(void*)5},
 {sizeof(nex_ffi_export_v1),0,"kernel_ns",PIN_KERNEL_NS,callback,(void*)6},
 {sizeof(nex_ffi_export_v1),0,"busy",PIN_BUSY,callback,(void*)7}
};
extern "C" const nex_ffi_module_v1 *nex_ffi_module_entry(uint32_t abi,uint32_t size){static const nex_ffi_module_v1 m{NEX_FFI_MODULE_ABI_V1,sizeof(nex_ffi_module_v1),sizeof(exports)/sizeof(exports[0]),sizeof(nex_ffi_export_v1),exports};return abi==1&&size>=NEX_FFI_V1_RESOURCE_PARENTS_SIZE?&m:nullptr;}
