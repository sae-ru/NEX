#include "host_test.h"
#include "nex_ffi_host.h"
#include "nex_host.h"
#include "nex_files.h"
#include "nex_json.h"
#include <bit>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <set>
#include <thread>
#include <mutex>
#include <fcntl.h>
#include <unistd.h>
using namespace nexrt;
extern "C" nex_ffi_status nex_test_c_values(const nex_ffi_api_v1*,nex_ffi_call,const nex_ffi_ref*,uint64_t,nex_ffi_ref*,void*);
extern "C" nex_ffi_status nex_test_c_forward(const nex_ffi_api_v1*,nex_ffi_call,const nex_ffi_ref*,uint64_t,nex_ffi_ref*,void*);
namespace {
const auto *api=nex_ffi_get_api(NEX_FFI_ABI_V1,sizeof(nex_ffi_api_v1));
void require(bool value,const char *message){if(!value)throw std::runtime_error(message);}
void ok(nex_ffi_status status){require(status==NEX_FFI_OK,"C API status failed");}
template<class F> void error(const char *code,F body){try{body();}catch(const DataError &e){require(e.code==code,"wrong DataError");return;}throw std::runtime_error("missing DataError");}
using Body=std::function<nex_ffi_status(nex_ffi_call,const nex_ffi_ref*,uint64_t,nex_ffi_ref*)>;
Value call(Body body,std::vector<Value> args={},std::function<void()> poll={},ForeignCallLimits limits={}){
  auto bridge=[](const nex_ffi_api_v1*,nex_ffi_call c,const nex_ffi_ref *a,uint64_t n,nex_ffi_ref *o,void *p)->nex_ffi_status{return (*static_cast<Body*>(p))(c,a,n,o);};
  return invokeForeign(bridge,args,&body,std::move(poll),limits);
}
int descriptors(){
#ifdef _WIN32
return int(nex_test::files().size());
#else
int n=0;for(int fd=0;fd<1024;++fd)if(::fcntl(fd,F_GETFD)>=0)++n;return n;
#endif
}
struct Directory {
  std::filesystem::path root;
  Directory(){auto p=(std::filesystem::temp_directory_path()/"nex-ffi-XXXXXX").string();require(::mkdtemp(p.data()),"mkdtemp failed");root=p;std::ofstream(root/"input")<<"data";}
  ~Directory(){std::error_code e;std::filesystem::remove_all(root,e);}
};
std::string copiedLabel(nex_ffi_call c,nex_ffi_ref r,uint64_t i){uint64_t size=0,written=0;ok(api->label_size(c,r,i,&size));std::string text(size,'\0');ok(api->copy_label(c,r,i,0,reinterpret_cast<uint8_t*>(text.data()),size,&written));require(written==size,"short label");return text;}
}
int main(){try{
 unsigned count=0;auto run=[&](const char *name,auto body){
    auto before=descriptors();body();require(liveObjects==0,"managed value leak");require(descriptors()==before,"file descriptor leak");
    ++count;std::cout<<"PASS "<<name<<std::endl;
  };
 run("C ABI negotiation and immutable table prefix",[]{
  require(api&&api->abi_version==1&&api->struct_size==sizeof(*api),"bad API table");
  require(nex_ffi_get_api(1,8)==api&&nex_ffi_get_api(1,0)==api,"prefix negotiation failed");
  require(!nex_ffi_get_api(0,0)&&!nex_ffi_get_api(2,0)&&!nex_ffi_get_api(1,UINT32_MAX),"unsupported ABI accepted");
 });
 run("separately compiled C producer copies all scalar and binary kinds",[]{
  std::vector<uint8_t> storage{0,255,128,1};std::string text=std::string("Я\0",3)+"🧠";
  std::vector<Value> args{Value(41),Value::floating(-0.0),Value(1,true),Value(string(text)),Value(bytes(ByteBuffer::copy(storage)))};
  unsigned polls=0;auto result=unwrap(invokeForeign(nex_test_c_values,args,nullptr,[&]{++polls;}));auto &v=result.object->values;
  require(v.size()==5&&v[0].scalar==42&&v[1].tag==Value::Floating&&std::bit_cast<uint64_t>(v[1].floating())==0&&v[2].tag==Value::Boolean&&!v[2].scalar,"C scalar semantics differ");
  require(v[3].object->text==text+"!"&&byteBuffer(v[4].object).toVector()==std::vector<uint8_t>({1,128,255,0})&&polls==3,"C copied data differs");
 });
 run("stale scopes and reference IDs never alias a later call",[]{
  nex_ffi_call oldCall=0;nex_ffi_ref oldRef=0;
  call([&](auto c,auto a,auto,auto o){oldCall=c;oldRef=a[0];*o=a[0];return NEX_FFI_OK;},{Value(42)});
  uint32_t untouched=99;require(api->kind(oldCall,oldRef,&untouched)==NEX_FFI_SCOPE&&untouched==99,"expired scope accepted");
  call([&](auto c,auto a,auto,auto o){require(c!=oldCall&&a[0]!=oldRef,"token reuse");int64_t v=91;require(api->get_i64(c,oldRef,&v)==NEX_FFI_REF&&v==91,"old reference accepted");*o=a[0];return NEX_FFI_OK;},{Value(7)});
 });
 run("nested calls enforce reference ownership",[]{
  auto v=call([&](auto outer,auto args,auto,auto out){
   auto nested=call([&](auto c,auto a,auto,auto o){int64_t value=0;require(api->get_i64(c,args[0],&value)==NEX_FFI_REF,"cross-call reference accepted");ok(api->get_i64(outer,args[0],&value));require(value==42,"outer scope lost");*o=a[0];return NEX_FFI_OK;},{Value(9)});
   require(nested.scalar==9,"nested result differs");*out=args[0];return NEX_FFI_OK;
  },{Value(42)});require(v.scalar==42,"outer result differs");
 });
 run("wrong-thread access leaves output and owner state intact",[]{
  call([](auto c,auto a,auto,auto o){nex_ffi_ref value=77;nex_ffi_status status=0;std::thread t([&]{status=api->make_i64(c,1,&value);});t.join();require(status==NEX_FFI_THREAD&&value==77,"cross-thread mutation accepted");*o=a[0];return NEX_FFI_OK;},{Value(42)});
 });
 run("parallel independent C calls have disjoint tokens",[]{
  std::mutex mutex;std::set<uint64_t> tokens;std::atomic<bool> failed=false;std::vector<std::thread> threads;
  for(unsigned i=0;i<8;++i)threads.emplace_back([&]{try{for(unsigned j=0;j<50;++j)call([&](auto c,auto a,auto,auto o){std::lock_guard lock(mutex);if(!tokens.insert(c).second||!tokens.insert(a[0]).second)failed=true;*o=a[0];return NEX_FFI_OK;},{Value(42)});}catch(...){failed=true;}});
  for(auto &t:threads)t.join();require(!failed&&tokens.size()==800,"parallel registry failed");
 });
 run("invalid values and pointers return statuses without output writes",[]{
  call([](auto c,auto a,auto,auto o){nex_ffi_ref r=77;uint8_t bad[]={0xc0};
   require(api->make_string(c,bad,1,&r)==NEX_FFI_UTF8&&r==77,"invalid UTF-8 imported");
   require(api->make_string(c,nullptr,1,&r)==NEX_FFI_ARGUMENT&&r==77,"null input accepted");
   require(api->make_bool(c,2,&r)==NEX_FFI_RANGE&&r==77,"boolean normalized silently");
   require(api->make_f64(c,std::numeric_limits<double>::infinity(),&r)==NEX_FFI_RANGE&&r==77,"infinity imported");
   require(api->make_f64(c,std::numeric_limits<double>::quiet_NaN(),&r)==NEX_FFI_RANGE&&r==77,"NaN imported");
   require(api->get_i64(c,a[0],nullptr)==NEX_FFI_ARGUMENT,"null output accepted");uint64_t size=99;
   require(api->byte_size(c,a[0],&size)==NEX_FFI_TYPE&&size==99,"scalar treated as bytes");
   *o=a[0];return NEX_FFI_OK;
  },{Value(42)});
 });
 run("UTF-8 byte copies preserve source and validate unsigned ranges",[]{
  call([](auto c,auto a,auto,auto o){uint8_t data[16]={};uint64_t written=99;
   ok(api->copy_bytes(c,a[0],1,data,1,&written));require(written==1&&data[0]==0xaf,"C byte offset became a scalar offset");
   require(api->copy_bytes(c,a[0],UINT64_MAX,data,1,&written)==NEX_FFI_BOUNDS&&written==1,"overflowed offset accepted");
   ok(api->copy_bytes(c,a[0],2,nullptr,0,&written));require(written==0,"zero-byte copy failed");
   *o=a[0];return NEX_FFI_OK;
  },{Value(string("Я"))});
 });
 run("C buffers are copied before subsequent mutation",[]{
  auto value=call([](auto c,auto,auto,auto o){uint8_t data[]={0,255,128};nex_ffi_ref r=0;ok(api->make_bytes(c,data,3,&r));data[0]=42;*o=r;return NEX_FFI_OK;});
  require(byteBuffer(value.object).toVector()==std::vector<uint8_t>({0,255,128}),"import retained mutable C memory");
 });
 run("record enum result metadata is copied and closures stay opaque",[]{
  auto record=std::make_shared<Data>(Data::Record),tag=std::make_shared<Data>(Data::Enum),closure=std::make_shared<Data>(Data::Closure);
  tag->text="model::Some";tag->values={Value(42)};record->names={"tag"};record->values={Value(tag)};
  call([](auto c,auto a,auto,auto o){uint64_t n=0;nex_ffi_ref tag=0,message=0;uint32_t k=0;
   ok(api->child_count(c,a[0],&n));require(n==1&&copiedLabel(c,a[0],0)=="tag","record metadata lost");
   ok(api->child(c,a[0],0,&tag));require(copiedLabel(c,tag,0)=="model::Some","enum identity lost");
   require(copiedLabel(c,a[1],0)=="E_USER","failure code lost");ok(api->child(c,a[1],0,&message));ok(api->kind(c,message,&k));require(k==NEX_FFI_STRING,"failure message is not a string");
   ok(api->kind(c,a[2],&k));require(k==NEX_FFI_FUNCTION&&api->child_count(c,a[2],&n)==NEX_FFI_TYPE,"closure internals exposed");
   *o=a[0];return NEX_FFI_OK;
  },{Value(record),failure("E_USER",std::string("a\0b",3)),Value(closure)});
 });
 run("reference release consumes tokens and retain preserves aliases",[]{
  auto v=call([](auto c,auto a,auto,auto o){nex_ffi_ref keep=0;ok(api->retain(c,a[0],&keep));ok(api->release(c,a[0]));require(api->release(c,a[0])==NEX_FFI_REF,"double release accepted");*o=keep;return NEX_FFI_OK;},{Value(string("kept"))});require(v.object->text=="kept","retain lost owner");
 });
 run("C failure builders preserve UTF-8 code and embedded NUL message",[]{
  auto v=call([](auto c,auto,auto,auto o){const uint8_t code[]={'E','_','C'},message[]={0xd0,0xaf,0,0xf0,0x9f,0xa7,0xa0};return api->make_failure(c,code,sizeof(code),message,sizeof(message),o);});
  require(!isSuccess(v)&&v.object->text=="E_C"&&v.object->values[0].object->text==std::string("Я\0",3)+"🧠","C failure builder changed data");
 });
 run("arguments are retained before entry poll releases caller storage",[]{
  std::vector<Value> args{Value(string("snapshot"))};auto value=invokeForeign(nex_test_c_forward,args,nullptr,[&]{args.clear();});require(value.object->text=="snapshot","entry poll released input");
 });
 run("forwarded files retain identity and obey original grant revocation",[]{
  Directory d;Value forwarded;uint64_t identity=0;
  {TextFiles files(d.root.string(),false);Value file(fileValue(files.open("input",FileMode::Read)));identity=fileIdentity(file.object);
   forwarded=call([&](auto c,auto a,auto,auto o){uint64_t found=0;ok(api->file_identity(c,a[0],&found));require(found==identity,"file identity changed");return api->retain(c,a[0],o);},{file});
   require(equal(file,forwarded)&&fileResource(forwarded.object).isOpen(),"forwarded owner lost");error("E_JSON",[&]{encodeJSON(forwarded);});}
  require(fileIdentity(forwarded.object)==identity&&!fileResource(forwarded.object).isOpen(),"FFI bypassed grant revocation");
 });
 run("failed C callbacks release the last file owner",[]{
  Directory d;TextFiles files(d.root.string(),false);std::vector<Value> args{Value(fileValue(files.open("input",FileMode::Read)))};auto before=descriptors();
  Body body=[](auto,auto,auto,auto){return NEX_FFI_RANGE;};auto bridge=[](const nex_ffi_api_v1*,auto c,auto a,auto n,auto o,void *p)->nex_ffi_status{return (*static_cast<Body*>(p))(c,a,n,o);};
  error("E_FFI",[&]{invokeForeign(bridge,args,&body,[&]{args.clear();});});require(descriptors()==before-1,"failed callback retained file");
 });
 run("forwarding diagnostic file IDs never grants IO authority",[]{
  std::vector<Value> args{Value(diagnosticFile(17))};auto v=invokeForeign(nex_test_c_forward,args);require(fileIdentity(v.object)==17,"diagnostic identity changed");error("E_RUNTIME",[&]{fileResource(v.object);});error("E_JSON",[&]{encodeJSON(v);});
 });
 run("host trap is sticky and retains the original native line",[]{
  unsigned polls=0;bool trapped=false;
  try{call([](auto c,auto a,auto,auto o){require(api->poll(c)==NEX_FFI_HOST_TRAP,"poll did not report trap");int64_t v=99;require(api->get_i64(c,a[0],&v)==NEX_FFI_HOST_TRAP&&v==99,"trap was ignored");*o=a[0];return NEX_FFI_OK;},{Value(42)},[&]{if(++polls==2)throw Trap("E_CANCELLED","cancelled",47);});}
  catch(const Trap &t){trapped=t.code=="E_CANCELLED"&&t.line==47;}require(trapped&&polls==2,"host trap was translated or swallowed");
 });
 run("host value errors take precedence over transport error mapping",[]{
  unsigned polls=0;error("E_UTF8",[&]{call([](auto c,auto a,auto,auto o){require(api->poll(c)==NEX_FFI_HOST_TRAP,"host UTF8 mapped to transport status");*o=a[0];return NEX_FFI_OK;},{Value(42)},[&]{if(++polls==2)throw DataError("E_UTF8","host failure");});});
 });
 run("entry cancellation prevents C entry and exit polling remains mandatory",[]{
  bool entered=false;error("E_BUDGET",[&]{call([&](auto,auto,auto,auto){entered=true;return NEX_FFI_OK;},{},[]{throw DataError("E_BUDGET","entry");});});require(!entered,"cancelled callback entered");
  unsigned polls=0;error("E_DEADLINE",[&]{call([](auto,auto a,auto,auto o){*o=a[0];return NEX_FFI_OK;},{Value(42)},[&]{if(++polls==2)throw DataError("E_DEADLINE","exit");});});
 });
 run("recursive polling fails without recursively invoking the host",[]{
  nex_ffi_call active=0;unsigned polls=0;
  call([&](auto c,auto a,auto,auto o){active=c;ok(api->poll(c));active=0;*o=a[0];return NEX_FFI_OK;},{Value(42)},[&]{++polls;if(active)require(api->poll(active)==NEX_FFI_REENTRANT,"recursive poll entered host");});require(polls==3,"wrong host poll count");
 });
 run("reference quotas do not recycle consumed identities",[]{
  call([](auto c,auto a,auto,auto o){nex_ffi_ref first=0,extra=77;ok(api->retain(c,a[0],&first));require(api->make_i64(c,1,&extra)==NEX_FFI_LIMIT&&extra==77,"reference quota bypass");ok(api->release(c,first));ok(api->retain(c,a[0],o));require(*o!=first,"released identity reused");return NEX_FFI_OK;},{Value(42)},{},{2,1048576,65536});
 });
 run("copy and operation budgets apply to actual work",[]{
  call([](auto c,auto a,auto,auto o){uint8_t bytes[2];uint64_t n=0;ok(api->copy_bytes(c,a[0],0,bytes,2,&n));n=77;require(api->copy_bytes(c,a[0],0,bytes,1,&n)==NEX_FFI_LIMIT&&n==77,"copy budget bypass");*o=a[0];return NEX_FFI_OK;},{Value(string("ab"))},{},{4096,2,65536});
  call([](auto c,auto a,auto,auto o){int64_t v=0;ok(api->get_i64(c,a[0],&v));require(api->get_i64(c,a[0],&v)==NEX_FFI_LIMIT,"operation budget bypass");*o=a[0];return NEX_FFI_OK;},{Value(42)},{},{4096,1048576,1});
 });
 run("constructed aggregate nesting is bounded and failure is atomic",[]{
  call([](auto c,auto a,auto,auto o){nex_ffi_ref current=a[0];for(unsigned i=0;i<128;++i){nex_ffi_ref next=0;ok(api->make_success(c,current,&next));if(current!=a[0])ok(api->release(c,current));current=next;}nex_ffi_ref next=77;require(api->make_success(c,current,&next)==NEX_FFI_LIMIT&&next==77,"unbounded aggregate nesting");*o=current;return NEX_FFI_OK;},{Value(42)});
 });
 run("invalid callback outputs and exceptions cannot escape as C++ ABI",[]{
  error("E_FFI",[]{call([](auto,auto,auto,auto){return NEX_FFI_OK;});});
  error("E_FFI",[]{call([](auto,auto,auto,auto o){*o=UINT64_MAX;return NEX_FFI_OK;});});
  error("E_FFI",[]{call([](auto c,auto a,auto,auto o){ok(api->release(c,a[0]));*o=a[0];return NEX_FFI_OK;},{Value(42)});});
  error("E_FFI_EXCEPTION",[]{call([](auto,auto,auto,auto)->nex_ffi_status{throw std::runtime_error("foreign");});});
  error("E_FFI_CONFIG",[]{invokeForeign(nullptr,{});});error("E_FFI_CONFIG",[]{call([](auto,auto,auto,auto){return NEX_FFI_OK;},{},{},{0,1,1});});
  error("E_FFI_LIMIT",[]{std::vector<Value> args(4097,Value(1));invokeForeign(nex_test_c_forward,args);});
 });
 run("callback target destruction can safely reenter the registry",[]{
  bool destroyed=false;struct Reenter{bool &done;explicit Reenter(bool &done):done(done){}~Reenter(){auto v=invokeForeign(nex_test_c_forward,std::vector<Value>{Value(7)});done=v.scalar==7;}};
  auto v=call([](auto,auto a,auto,auto o){*o=a[0];return NEX_FFI_OK;},{Value(42)},[target=std::make_shared<Reenter>(destroyed)]{});
  require(v.scalar==42&&destroyed,"callback destruction retained target or deadlocked");
 });
 std::cout<<count<<" cases passed\n";return 0;
}catch(const std::exception &e){std::cerr<<"FAIL "<<e.what()<<'\n';return 1;}}
