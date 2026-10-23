#include "npu-common.h"
// Optional vendor SDK headers are provided privately by the operator, not vendored.
#include "rknn_api.h"
#include "rknn_matmul_api.h"
#include <fcntl.h>
#include <iostream>
#include <cerrno>
#include <sys/resource.h>
static_assert(sizeof(rknn_matmul_info)==64);
static_assert(sizeof(rknn_tensor_mem)==40);
static void check(int code,const char *where){if(code)throw Failure("E_DEVICE",std::string(where)+":"+std::to_string(code));}
class Matmul {
 Library library{"/usr/lib/librknnrt.so"};
 decltype(&rknn_matmul_create) create=library.symbol<decltype(create)>("rknn_matmul_create");
 decltype(&rknn_matmul_destroy) destroy=library.symbol<decltype(destroy)>("rknn_matmul_destroy");
 decltype(&rknn_matmul_set_core_mask) core=library.symbol<decltype(core)>("rknn_matmul_set_core_mask");
 decltype(&rknn_create_mem) alloc=library.symbol<decltype(alloc)>("rknn_create_mem");
 decltype(&rknn_destroy_mem) freeMem=library.symbol<decltype(freeMem)>("rknn_destroy_mem");
 decltype(&rknn_matmul_set_io_mem) bind=library.symbol<decltype(bind)>("rknn_matmul_set_io_mem");
 decltype(&rknn_matmul_run) execute=library.symbol<decltype(execute)>("rknn_matmul_run");
 rknn_matmul_ctx ctx=0;std::array<rknn_tensor_mem*,3> mem{};int cleanupError=0;
 void cleanup()noexcept {
  for(auto &p:mem)if(p){auto rc=freeMem(ctx,p);if(rc&&!cleanupError)cleanupError=rc;p=nullptr;}
  if(ctx){auto rc=destroy(ctx);if(rc&&!cleanupError)cleanupError=rc;ctx=0;}
 }
 public:
 ~Matmul(){cleanup();}
 std::vector<uint8_t> run(const std::vector<uint8_t> &payload) {
  if(payload.size()<12)throw Failure("E_PROTOCOL","missing matmul shape");
  std::array<uint32_t,3> shape{};
  for(int i=0;i<3;++i)for(int j=0;j<4;++j)shape[i]|=uint32_t(payload[i*4+j])<<(8*j);
  auto [m,k,n]=shape;
  if(m<1||m>32||k<32||k>128||k%32||n<32||n>128||n%32)throw Failure("E_SHAPE","invalid bounded matmul shape");
  if(payload.size()!=12+uint64_t(m)*k+uint64_t(k)*n)throw Failure("E_PROTOCOL","matmul frame shape mismatch");
  rknn_matmul_info info{};rknn_matmul_io_attr io{};
  info.M=m;info.K=k;info.N=n;info.type=RKNN_INT8_MM_INT8_TO_INT32;
  info.B_layout=RKNN_MM_LAYOUT_NORM;info.AC_layout=RKNN_MM_LAYOUT_NORM;
  check(create(&ctx,&info,&io),"create");check(core(ctx,RKNN_NPU_CORE_0),"core");
  std::array<rknn_matmul_tensor_attr*,3> attrs{&io.A,&io.B,&io.C};
  std::array<uint32_t,3> lengths{m*k,k*n,m*n*4};
  std::array<rknn_tensor_type,3> types{RKNN_TENSOR_INT8,RKNN_TENSOR_INT8,RKNN_TENSOR_INT32};
  for(size_t i=0;i<3;++i) {
   auto &attr=*attrs[i];
   uint32_t rows=i==1?k:m,cols=i==0?k:n;
   if(attr.n_dims!=2||attr.dims[0]!=rows||attr.dims[1]!=cols||attr.type!=types[i]||attr.size!=lengths[i])throw Failure("E_DEVICE_ABI","unexpected normal-layout tensor contract");
   mem[i]=alloc(ctx,attr.size);
   if(!mem[i]||!mem[i]->virt_addr||mem[i]->size<attr.size)throw Failure("E_DEVICE_MEMORY","allocation failed");
  }
  std::memcpy(mem[0]->virt_addr,payload.data()+12,lengths[0]);
  std::memcpy(mem[1]->virt_addr,payload.data()+12+lengths[0],lengths[1]);
  // Never CPU-initialize C here: writing this cached DMA mapping caused stale
  // zero/sentinel outputs on RK3588 runtime2.3/2.5. Upstream leaves C untouched.
  for(size_t i=0;i<3;++i)check(bind(ctx,mem[i],attrs[i]),"bind");
  auto start=std::chrono::steady_clock::now();check(execute(ctx),"run");
  const auto elapsed=std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now()-start).count();
  bool device=false;
  for(const auto &entry:std::filesystem::directory_iterator("/proc/self/fd")) {
   std::error_code ec;auto target=std::filesystem::read_symlink(entry.path(),ec);
   if(ec||target.string().find("/dev/dri/")!=0)continue;
   auto driver=std::filesystem::canonical(std::filesystem::path("/sys/class/drm")/target.filename()/"device/driver",ec);
   if(!ec&&driver.filename()=="RKNPU")device=true;
  }
  if(!device)throw Failure("E_DEVICE_UNAVAILABLE","actual RKNPU device fd required");
  const auto *c=static_cast<const int32_t*>(mem[2]->virt_addr);std::vector<uint8_t> result;
  for(uint32_t i=0;i<m*n;++i)for(int j=0;j<4;++j)result.push_back(uint8_t(uint32_t(c[i])>>(8*j)));
  cleanup();check(cleanupError,"cleanup");
  trace(JSON{{"backend","npu"},{"provider","RKNN"},{"device_driver","RKNPU"},{"m",m},{"k",k},{"n",n},{"elements",m*n},{"cpu_fallback_allowed",false},{"rknpu_fd_open",device},{"cleanup_verified",true},{"host_call_ns",elapsed}});
  return result;
 }
};
static void writeAll(int fd,const void *data,size_t count) {
 auto p=static_cast<const uint8_t*>(data);
 while(count){auto n=write(fd,p,count);if(n<0&&errno==EINTR)continue;if(n<=0)throw std::runtime_error("worker result write");p+=n;count-=n;}
}
static void put32(int fd,uint32_t n){uint8_t b[4];for(int i=0;i<4;++i)b[i]=uint8_t(n>>(8*i));writeAll(fd,b,4);}
int main() {
 int protocol=fcntl(STDOUT_FILENO,F_DUPFD_CLOEXEC,3);if(protocol<0)return 3;
 if(dup2(STDERR_FILENO,STDOUT_FILENO)<0)return 3;
 rlimit files{2097152,2097152};if(setrlimit(RLIMIT_FSIZE,&files))return 3;
 rlimit coreLimit{0,0};setrlimit(RLIMIT_CORE,&coreLimit);
 try {
  uint8_t header[4];std::cin.read(reinterpret_cast<char*>(header),4);if(!std::cin)throw Failure("E_PROTOCOL","missing worker header");
  uint32_t size=0;for(int i=0;i<4;++i)size|=uint32_t(header[i])<<(8*i);
  if(size<12||size>20492)throw Failure("E_PROTOCOL","invalid worker input size");
  std::vector<uint8_t> input(size);std::cin.read(reinterpret_cast<char*>(input.data()),size);
  if(!std::cin||std::cin.peek()!=std::char_traits<char>::eof())throw Failure("E_PROTOCOL","invalid worker input frame");
  std::vector<uint8_t> result;{Matmul device;result=device.run(input);}
  put32(protocol,0);put32(protocol,result.size());writeAll(protocol,result.data(),result.size());close(protocol);return 0;
 }catch(const std::exception &e) {
  std::string message=e.what();for(auto &c:message)if(static_cast<unsigned char>(c)<32||static_cast<unsigned char>(c)>126)c='?';message=message.substr(0,2048);
  const auto *specific=dynamic_cast<const Failure*>(&e);std::string code=specific?specific->code:"E_ACCELERATOR";
  try{auto text=JSON{{"code",code},{"message",message}}.dump();put32(protocol,1);put32(protocol,text.size());writeAll(protocol,text.data(),text.size());close(protocol);return 0;}catch(...){return 3;}
 }
}
