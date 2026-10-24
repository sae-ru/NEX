#include "nex_foreign.h"
#include "nex_host.h"
#include "nex_ffi_types.h"
#include "third_party/json.hpp"
#include <openssl/evp.h>
#include <array>
#include <atomic>
#include <barrier>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <thread>
#include <fcntl.h>
#include <unistd.h>
using namespace nexrt;
namespace fs=std::filesystem;
using J=nlohmann::ordered_json;
namespace {
std::mutex allocationMutex;
std::map<const void*,std::pair<size_t,int>> allocations;
bool allocationError=false;
}
extern "C" {
void nex_profile_enter(const char*,const char*,int64_t,const char*){}
void nex_profile_leave(){}
void nex_profile_unwind(){}
void nex_profile_allocation(const void *p,size_t bytes,int pool){std::lock_guard lock(allocationMutex);if(!allocations.emplace(p,std::pair{bytes,pool}).second)allocationError=true;}
void nex_profile_free(const void *p){std::lock_guard lock(allocationMutex);if(allocations.erase(p)!=1)allocationError=true;}
}
namespace {
void require(bool condition,const char *message){if(!condition)throw std::runtime_error(message);}
template<class F> void error(const char *code,F body){try{body();}catch(const DataError &e){if(e.code!=code)throw std::runtime_error(std::string("expected ")+code+", got "+e.code+": "+e.what());return;}throw std::runtime_error(std::string("missing error ")+code);}
std::string read(const fs::path &p){std::ifstream in(p,std::ios::binary);return {std::istreambuf_iterator<char>(in),{}};}
void write(const fs::path &p,const std::string &text){std::ofstream out(p,std::ios::binary);out<<text;require(bool(out),"fixture write failed");}
std::string sha(std::string_view text){std::unique_ptr<EVP_MD_CTX,decltype(&EVP_MD_CTX_free)> c(EVP_MD_CTX_new(),EVP_MD_CTX_free);std::array<unsigned char,32> bytes{};unsigned count=0;require(c&&EVP_DigestInit_ex2(c.get(),EVP_sha256(),nullptr)==1&&EVP_DigestUpdate(c.get(),text.data(),text.size())==1&&EVP_DigestFinal_ex(c.get(),bytes.data(),&count)==1&&count==32,"fixture SHA256 failed");std::string result;for(auto b:bytes){result+="0123456789abcdef"[b>>4];result+="0123456789abcdef"[b&15];}return result;}
int descriptors(){int n=0;for(int fd=0;fd<1024;++fd)if(::fcntl(fd,F_GETFD)>=0)++n;return n;}
Value call(const ForeignFunction &f,std::vector<Value> args,std::function<void()> poll={},ForeignCallLimits limits={}){return f.invoke(args,std::move(poll),limits);}
struct Fixture {
  fs::path root,marker;J signatures;std::map<std::string,std::string> pins;
  Fixture(const fs::path &a,const fs::path &b,const J &s):signatures(s){
    auto pattern=(fs::temp_directory_path()/"nex-typed-resource-XXXXXX").string();require(::mkdtemp(pattern.data()),"mkdtemp failed");root=fs::canonical(pattern);marker=root/"events";
    for(auto [name,module]:{std::pair{"a",a},std::pair{"b",b}}){auto dir=root/name;fs::create_directory(dir);fs::copy_file(module,dir/"module");write(dir/"NOTICE","NEX typed resource module test fixture\n");J exports=J::object();for(auto it=signatures.begin();it!=signatures.end();++it)exports[it.key()]=foreignSignatureDigest(ForeignSignature(it.value().dump()));
      J manifest={{"schema","nex.foreign-bundle/1"},{"platform",foreignPlatform()},{"entry","module"},{"files",J::array({J{{"path","module"},{"sha256",sha(read(dir/"module"))}},J{{"path","NOTICE"},{"sha256",sha(read(dir/"NOTICE"))}}})},{"exports",exports},{"notices",J::array({"NOTICE"})}};
      auto text=manifest.dump();write(dir/"manifest.json",text);pins[name]=sha(text);
    }
    require(setenv("NEX_TYPED_RESOURCE_MARKER",marker.c_str(),1)==0,"setenv failed");
  }
  ~Fixture(){unsetenv("NEX_TYPED_RESOURCE_MARKER");std::error_code e;fs::remove_all(root,e);}
  ForeignLibraryGrant grant(const std::string &name="a")const{std::set<std::string> exports;for(auto it=signatures.begin();it!=signatures.end();++it)exports.insert(it.key());return {(root/name).string(),pins.at(name),std::move(exports)};}
  std::shared_ptr<ForeignLibraries> libraries(size_t limit=64,uint64_t bytes=64*1048576,size_t modules=64,bool both=false)const{std::map<std::string,ForeignLibraryGrant> grants{{"a",grant()}};if(both)grants["b"]=grant("b");return std::make_shared<ForeignLibraries>(std::move(grants),modules,limit,bytes);}
  ForeignFunction function(const ForeignLibraries &libs,const std::string &name,const std::string &library="a")const{return libs.bind(library,name,ForeignSignature(signatures.at(name).dump()),pins.at(library));}
  std::string binding(const std::string &name)const{return J{{"schema","nex.foreign-binding/1"},{"library","a"},{"export",name},{"manifest_sha256",pins.at("a")},{"signature",signatures.at(name)}}.dump();}
  Value scoped(const std::string &name,std::vector<Value> args,std::function<void()> poll={})const{return invokeScopedForeign(binding(name),args,std::move(poll));}
  std::string events()const{return read(marker);}
  size_t count(char event)const{auto s=events();return std::count(s.begin(),s.end(),event);}
};
}
int main(int argc,char **argv){try{
  require(argc==4,"usage: typed_resource_ffi MODULE_A MODULE_B SIGNATURES");auto a=fs::canonical(argv[1]),b=fs::canonical(argv[2]);auto signatures=J::parse(read(argv[3]));unsigned cases=0;
  auto run=[&](const char *name,auto body){auto before=descriptors();body();require(liveObjects==0&&!allocationError&&allocations.empty(),"managed values/profile allocations leaked");require(descriptors()==before,"file descriptors leaked");++cases;std::cout<<"PASS "<<name<<std::endl;};
  run("resource metadata is bounded nominal identity rather than a native layout",[&]{
    auto good=signatures.at("forward");ForeignSignature valid(good.dump());require(valid.hasResources(),"resource signature not detected");
    for(int mode=0;mode<7;++mode){auto doc=good;
      if(mode==0)doc["types"][0]["identity"]=std::string(63,'a');
      if(mode==1)doc["types"][0]["identity"]=std::string(64,'A');
      if(mode==2)doc["types"][0]["name"]="fixture:::Session";
      if(mode==3)doc["types"][0]["name"]="fixture::";
      if(mode==4)doc["types"][0]["name"]=std::string(129,'x');
      if(mode==5){doc["types"].push_back(doc["types"][0]);doc["types"][1]["identity"]=std::string(64,'b');doc["parameters"].push_back(1);}
      if(mode==6){doc["types"].push_back(J{{"kind","record"},{"name","fixture::Session"},{"fields",J::array()}});doc["parameters"].push_back(1);}
      error("E_FFI_SIGNATURE",[&]{ForeignSignature bad(doc.dump());});
    }
  });
  run("append-only resource C slots preserve both previous table prefixes",[]{const auto *api=nex_ffi_get_api(1,NEX_FFI_V1_RESOURCE_SIZE);require(api&&api->struct_size==sizeof(*api)&&NEX_FFI_V1_TRANSPORT_SIZE<NEX_FFI_V1_TYPED_SIZE&&NEX_FFI_V1_TYPED_SIZE<NEX_FFI_V1_RESOURCE_SIZE,"prefix sizes differ");require(nex_ffi_get_api(1,NEX_FFI_V1_TYPED_SIZE)==api&&nex_ffi_get_api(1,NEX_FFI_V1_TRANSPORT_SIZE)==api,"old prefix negotiation failed");});
  run("one module quota is independent of value ownership and alias identity",[&]{Fixture f(a,b,signatures);auto libs=f.libraries(1,8,1);auto create=f.function(*libs,"create"),read=f.function(*libs,"read"),forward=f.function(*libs,"forward");auto r=call(create,{Value(42)});auto alias=call(forward,{r});require(externalResource(r.object).identity()==externalResource(alias.object).identity()&&call(read,{r}).scalar==42&&libs->resourceBytesUsed()==8,"owned roundtrip failed");require(externalResource(alias.object).close()&&!externalResource(r.object).isOpen()&&libs->resourceBytesUsed()==0&&f.count('X')==1,"alias close did not settle exactly once");});
  run("capacity and reference admission reject before entering the producer factory",[&]{
    for(int mode=0;mode<3;++mode){Fixture f(a,b,signatures);auto libs=f.libraries(1,mode==0?7:8);auto create=f.function(*libs,"create");ForeignCallLimits limits;if(mode==1)limits.references=1;if(mode==2)limits.copiedBytes=sizeof(ExternalData)-1;error("E_FFI",[&]{call(create,{Value(42)},{},limits);});require(f.count('F')==0&&libs->resourceBytesUsed()==0,"rejected constructor called factory or reserved capacity");}
  });
  run("result-reachable construction works through an immutable result container",[&]{Fixture f(a,b,signatures);auto libs=f.libraries();auto result=call(f.function(*libs,"result_create"),{Value(42)});auto r=unwrap(result);require(call(f.function(*libs,"read"),{r}).scalar==42,"nested output resource constructor failed");});
  run("input-only metadata never grants construction",[&]{Fixture f(a,b,signatures);auto libs=f.libraries();auto r=call(f.function(*libs,"create"),{Value(42)});auto before=f.count('F');require(call(f.function(*libs,"input_constructor"),{r}).scalar==NEX_FFI_TYPE&&f.count('F')==before,"input type granted a constructor");});
  run("resource factory and destructor must belong to the actual pinned module",[&]{Fixture f(a,b,signatures);auto libs=f.libraries();error("E_FFI",[&]{call(f.function(*libs,"bad_callback"),{Value(42)});});require(!f.count('F')&&!f.count('X')&&libs->resourceBytesUsed()==0,"unowned callback reached factory");});
  run("written pointers transfer immediately and factory errors roll back physical quotas",[&]{Fixture f(a,b,signatures);auto libs=f.libraries(1,8);auto create=f.function(*libs,"create");for(int n=0;n<3;++n){error("E_FFI",[&]{call(create,{Value(-1)});});require(libs->resourceBytesUsed()==0&&f.count('F')==size_t(n+1)&&f.count('X')==size_t(n+1),"failed factory did not destroy transferred object");}error("E_FFI",[&]{call(create,{Value(-2)});});require(f.count('N')==1&&libs->resourceBytesUsed()==0,"null success retained capacity");auto r=call(create,{Value(42)});require(call(f.function(*libs,"read"),{r}).scalar==42,"quota not reusable after constructor failure");});
  run("a module may forward another image owner but cannot cast its private payload",[&]{Fixture f(a,b,signatures);auto libs=f.libraries(64,64*1048576,2,true);auto r=call(f.function(*libs,"create"),{Value(42)});auto forwarded=call(f.function(*libs,"forward","b"),{r});require(externalResource(forwarded.object).identity()==externalResource(r.object).identity(),"cross-image opaque forward failed");error("E_FFI",[&]{call(f.function(*libs,"read","b"),{r});});require(call(f.function(*libs,"read"),{r}).scalar==42,"origin rejection damaged original owner");});
  run("ordinary records and conflicting resource semantic identities are rejected",[&]{Fixture f(a,b,signatures);auto libs=f.libraries();auto forward=f.function(*libs,"forward");auto record=std::make_shared<Data>(Data::Record);record->text="fixture::Session";error("E_FFI_TYPE",[&]{call(forward,{Value(record)});});ResourceDomain domain;ResourceByteBudget bytes(8);ExternalResourceType<int> type("fixture::Session",std::string(64,'b'));auto owner=ExternalResource::make(domain,type,std::span(&bytes,1),4,std::make_shared<int>(0),[](const ResourcePermit &){return std::make_unique<int>(42);});error("E_FFI_TYPE",[&]{call(forward,{Value(externalValue(owner))});});});
  run("closing and releasing a C reference retains its borrowed native object until return",[&]{Fixture f(a,b,signatures);auto libs=f.libraries(1,8);auto r=call(f.function(*libs,"create"),{Value(42)});require(call(f.function(*libs,"close_borrow"),{r}).scalar==42&&!externalResource(r.object).isOpen()&&f.count('X')==1&&libs->resourceBytesUsed()==0,"in-flight close destroyed borrowed memory or leaked it");require(call(f.function(*libs,"status"),{r}).scalar==NEX_FFI_RESOURCE_CLOSED,"closed resource status differs");});
  run("C type and value tokens expire and new resource entry points enforce thread ownership",[&]{Fixture f(a,b,signatures);auto libs=f.libraries();auto r=call(f.function(*libs,"create"),{Value(42)});auto tokens=f.function(*libs,"tokens");require(call(tokens,{r}).scalar==42&&call(tokens,{r}).scalar==42,"stale tokens aliased a new call");require(call(f.function(*libs,"wrong_thread"),{r}).scalar==NEX_FFI_THREAD,"wrong thread accessed resource payload");});
  run("ForeignScope exit retires only its created owners despite a shared catalogue",[&]{Fixture f(a,b,signatures);auto libs=f.libraries();Value outer,inner;{ForeignScope scope(libs);outer=f.scoped("create",{Value(42)});{ForeignScope nested(libs);auto forwarded=f.scoped("forward",{outer});inner=f.scoped("create",{Value(7)});require(externalResource(forwarded.object).isOpen(),"nested forwarding lost owner");}require(!externalResource(inner.object).isOpen()&&externalResource(outer.object).isOpen()&&f.scoped("read",{outer}).scalar==42,"nested scope revocation escaped owner domain");}require(!externalResource(outer.object).isOpen()&&f.count('X')==2&&libs->resourceBytesUsed()==0,"scope resource escaped lexical authority");});
  run("a globally prebound factory still joins the current actual RequestScope",[&]{Fixture f(a,b,signatures);auto libs=f.libraries();auto create=f.function(*libs,"create");Value r;{RequestScope request;r=call(create,{Value(42)});require(externalResource(r.object).isOpen(),"request owner closed during call");}require(!externalResource(r.object).isOpen()&&create.isOpen()&&libs->resourceBytesUsed()==0,"request resource escaped or revoked global factory");auto next=call(create,{Value(7)});require(externalResource(next.object).isOpen(),"request revocation disabled later root calls");});
  run("destroying a lexical scope during factory polling revokes the retained State",[&]{Fixture f(a,b,signatures);auto libs=f.libraries();auto scope=std::make_unique<ForeignScope>(libs);error("E_FFI_SCOPE",[&]{f.scoped("create",{Value(-3)},[&]{if(f.count('F'))scope.reset();});});require(!scope&&f.count('F')==1&&f.count('X')==1&&libs->resourceBytesUsed()==0,"retained scope extended resource creation");});
  run("ignored factory poll failure remains sticky and destroys an already transferred object",[&]{Fixture f(a,b,signatures);auto libs=f.libraries(1,8);auto create=f.function(*libs,"create");error("E_TEST_STOP",[&]{call(create,{Value(-3)},[&]{if(f.count('F'))throw DataError("E_TEST_STOP","factory cancellation");});});require(f.count('X')==1&&libs->resourceBytesUsed()==0,"factory trap leaked native object or capacity");auto r=call(create,{Value(42)});require(externalResource(r.object).isOpen(),"factory trap leaked quota");});
  run("concurrent alias close preserves the physical pointer and byte charge through settlement",[&]{Fixture f(a,b,signatures);auto libs=f.libraries(1,8);auto r=call(f.function(*libs,"create"),{Value(42)});bool closed=false;auto v=call(f.function(*libs,"hold_poll"),{r},[&]{if(!closed&&f.count('B')){std::thread t([&]{externalResource(r.object).close();});t.join();closed=true;require(libs->resourceBytesUsed()==8&&f.count('X')==0,"physical charge released while native pointer in flight");}});require(v.scalar==42&&closed&&libs->resourceBytesUsed()==0&&f.events().find("BPX")!=std::string::npos,"borrowed operation did not settle before destruction");});
  run("catalogue revocation retains borrowed payload then unloads real code after its destructor",[&]{Fixture f(a,b,signatures);auto libs=f.libraries(1,8);auto r=call(f.function(*libs,"create"),{Value(42)});auto hold=f.function(*libs,"hold_poll");bool revoked=false;error("E_RESOURCE_SCOPE",[&]{call(hold,{r},[&]{if(!revoked&&f.count('B')){libs.reset();revoked=true;require(f.count('X')==0&&f.count('D')==0,"revocation destroyed in-flight payload/code");}});});require(revoked&&!hold.isOpen()&&!externalResource(r.object).isOpen()&&f.events().ends_with("BPXD"),"actual destructor/unload ordering differs");});
  run("request cancellation holds admitted work until settlement and forbids result admission",[&]{Fixture f(a,b,signatures);auto libs=f.libraries(1,8);auto create=f.function(*libs,"create"),hold=f.function(*libs,"hold_poll");Value r;{RequestScope request;r=call(create,{Value(42)});bool canceled=false;error("E_RESOURCE_SCOPE",[&]{call(hold,{r},[&]{if(!canceled&&f.count('B')){request.cancel();canceled=true;require(libs->resourceBytesUsed()==8&&f.count('X')==0,"request cancellation released physical capacity too early");}});});require(canceled&&!externalResource(r.object).isOpen()&&libs->resourceBytesUsed()==0,"request did not settle borrowed work");}require(create.isOpen(),"request cancellation revoked global module owner");});
  run("parallel calls share the actual image registry with bounded independent call tokens",[&]{Fixture f(a,b,signatures);auto libs=f.libraries(64,512);auto create=f.function(*libs,"create"),reader=f.function(*libs,"read");std::barrier start(8);std::atomic<bool> failed=false;std::vector<std::thread> threads;for(int i=0;i<8;++i)threads.emplace_back([&,i]{try{start.arrive_and_wait();for(int j=0;j<8;++j){auto r=call(create,{Value(i*8+j)});require(call(reader,{r}).scalar==i*8+j,"parallel payload differs");externalResource(r.object).close();}}catch(...){failed=true;}});for(auto &t:threads)t.join();require(!failed&&f.count('F')==64&&f.count('X')==64&&libs->resourceBytesUsed()==0,"concurrent resource operations leaked or crossed identities");});
  run("operator resource limits are explicit strict metadata and never execute native code",[&]{Fixture f(a,b,signatures);J names=J::array();for(auto it=signatures.begin();it!=signatures.end();++it)names.push_back(it.key());J host={{"schema","nex.foreign-host/1"},{"module_limit",1},{"resource_limit",3},{"resource_bytes",24},{"libraries",J{{"a",J{{"directory","a"},{"manifest_sha256",f.pins.at("a")},{"exports",names}}}}}};auto p=f.root/"host.json";write(p,host.dump());auto libs=loadForeignLibraries(p.string());require(libs->resourceLimit()==3&&libs->resourceBytesLimit()==24&&libs->moduleLimit()==1,"operator resource limits lost");for(auto key:{"resource_limit","resource_bytes"})for(auto value:{J(0),J(-1),J(1.5),J("8"),J(uint64_t(1)<<40)}){auto bad=host;bad[key]=value;write(p,bad.dump());error("E_FFI_GRANT",[&]{loadForeignLibraries(p.string());});}require(f.events().empty(),"configuration reading initialized module");});
  std::cout<<"typed external resource C boundary: "<<cases<<" cases passed\n";return 0;
}catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 1;}}
