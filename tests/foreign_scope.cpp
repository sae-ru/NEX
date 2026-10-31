#include "host_test.h"
#include "nex_foreign.h"
#include "nex_foreign_abi.h"
#include "nex_host.h"
#include "nex_files.h"
#include "third_party/json.hpp"
#include <openssl/evp.h>
#include <atomic>
#include <barrier>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <thread>
#ifndef _WIN32
#include <sys/wait.h>
#endif
#include <fcntl.h>
#include <unistd.h>
using namespace nexrt;namespace fs=std::filesystem;using J=nlohmann::ordered_json;
namespace {
void require(bool condition,const char *message){if(!condition)throw std::runtime_error(message);}
template<class F> void error(const char *code,F body){try{body();}catch(const DataError &e){if(e.code!=code)throw std::runtime_error(std::string("expected ")+code+", got "+e.code+": "+e.what());return;}throw std::runtime_error(std::string("missing error ")+code);}
template<class F> void trap(const char *code,int64_t line,F body){try{body();}catch(const Trap &e){require(e.code==code&&e.line==line,"native trap code/line differs");return;}throw std::runtime_error("missing native trap");}
std::string read(const fs::path &path){std::ifstream in(path,std::ios::binary);return {std::istreambuf_iterator<char>(in),{}};}
void write(const fs::path &path,std::string_view text){std::ofstream out(path,std::ios::binary);out.write(text.data(),text.size());require(bool(out),"fixture write failed");}
std::string sha(std::string_view text){unsigned char bytes[32];unsigned size=0;auto *ctx=EVP_MD_CTX_new();require(ctx,"digest allocation");require(EVP_DigestInit_ex2(ctx,EVP_sha256(),nullptr)==1&&EVP_DigestUpdate(ctx,text.data(),text.size())==1&&EVP_DigestFinal_ex(ctx,bytes,&size)==1&&size==32,"test digest failed");EVP_MD_CTX_free(ctx);std::string result;for(auto b:bytes){result+="0123456789abcdef"[b>>4];result+="0123456789abcdef"[b&15];}return result;}
const char *valuesContract=R"({"parameters":[0,1,2,3,4,5,6,10],"result":11,"schema":"nex.foreign-signature/1","types":[{"kind":"i64"},{"kind":"bool"},{"kind":"f64"},{"kind":"str"},{"kind":"bytes"},{"kind":"file"},{"kind":"function","name":"host::callback"},{"fields":[{"name":"value","type":0}],"kind":"record","name":"host::Packet"},{"kind":"enum","name":"host::Maybe","variants":[{"fields":[],"name":"None"},{"fields":[{"name":"value","type":7}],"name":"Some"}]},{"item":8,"kind":"result"},{"item":9,"kind":"list"},{"fields":[{"name":"number","type":0},{"name":"flag","type":1},{"name":"real","type":2},{"name":"text","type":3},{"name":"data","type":4},{"name":"file","type":5},{"name":"callback","type":6},{"name":"nested","type":10}],"kind":"record","name":"host::Bundle"}]})";
J signature(const std::string &name){if(name=="values")return J::parse(valuesContract);return J{{"schema","nex.foreign-signature/1"},{"parameters",name=="unit"?J::array():J::array({0})},{"result",0},{"types",J::array({J{{"kind",name=="unit"?"unit":"i64"}}})}};}
int descriptors(){
#ifdef _WIN32
return int(nex_test::files().size());
#else
int n=0;for(int fd=0;fd<1024;++fd)if(::fcntl(fd,F_GETFD)>=0)++n;return n;
#endif
}
struct Fixture {
  fs::path root,bundle,marker,config;J grants;std::string pin;
  Fixture(const fs::path &module){auto pattern=(fs::temp_directory_path()/"nex-foreign-scope-XXXXXX").string();require(::mkdtemp(pattern.data()),"mkdtemp failed");root=fs::canonical(pattern);bundle=root/"bundle";marker=root/"marker";config=root/"host.json";fs::create_directory(bundle);fs::copy_file(module,bundle/"module");write(bundle/"NOTICE","NEX test module\n");write(root/"input","file data");J exports=J::object();for(auto name:{"echo","unit","values","wrong"})exports[name]=foreignSignatureDigest(ForeignSignature(signature(name).dump()));
    auto manifest=J{{"schema","nex.foreign-bundle/1"},{"platform",foreignPlatform()},{"entry","module"},{"files",J::array({J{{"path","module"},{"sha256",sha(read(bundle/"module"))}},J{{"path","NOTICE"},{"sha256",sha(read(bundle/"NOTICE"))}}})},{"exports",exports},{"notices",J::array({"NOTICE"})}};write(bundle/"manifest.json",manifest.dump());pin=sha(read(bundle/"manifest.json"));grants=J{{"schema","nex.foreign-host/1"},{"module_limit",64},{"libraries",J{{"test",J{{"directory","bundle"},{"manifest_sha256",pin},{"exports",J::array({"echo","unit","values","wrong"})}}}}}};save();require(::setenv("NEX_FOREIGN_TEST_MARKER",marker.c_str(),1)==0,"setenv failed");
  }
  ~Fixture(){::unsetenv("NEX_FOREIGN_TEST_MARKER");::unsetenv("NEX_FOREIGN_CONFIG");std::error_code ec;fs::remove_all(root,ec);}
  void save(){write(config,grants.dump());}
  std::shared_ptr<ForeignLibraries> libraries(){return loadForeignLibraries(config.string());}
  std::string binding(const std::string &name="echo")const{return J{{"schema","nex.foreign-binding/1"},{"library","test"},{"export",name},{"manifest_sha256",pin},{"signature",signature(name)}}.dump();}
  std::string events()const{return read(marker);}
};
Value invoke(const std::string &binding,std::function<void()> poll={}){std::vector<Value> args{Value(42)};return invokeScopedForeign(binding,args,std::move(poll));}
Handle *pack(std::vector<Value> values){auto data=std::make_shared<Data>(Data::List);data->values=std::move(values);return makeHandle(Value(std::move(data)));}
Value native(const std::string &binding,Handle *args,int64_t line=55){auto box=nex_foreign_invoke(binding.data(),int64_t(binding.size()),args,line);auto value=readHandle(box).object->values.at(0);nex_release(box);return value;}
}
int main(int argc,char **argv){try{
  if(argc==4&&std::string(argv[1])=="--fatal"){
    auto libraries=loadForeignLibraries(argv[2]);ForeignScope scope(libraries);auto description=read(argv[3]);auto args=pack({Value(42)});require(native(description,args).scalar==42,"fatal setup failed");nex_release(args);runtimeFail("E_TEST_STOP","fatal cleanup",77);
  }
  require(argc==2,"usage: foreign_scope MODULE");auto module=fs::canonical(argv[1]);unsigned cases=0;
  auto run=[&](const char *name,auto body){
    auto before=descriptors();body();require(liveObjects==0,"managed value leak");require(descriptors()==before,"file descriptor leak");
    ++cases;std::cout<<"PASS "<<name<<std::endl;
  };
  run("host configuration is explicit relative and non-executing",[&]{Fixture f(module);auto libs=f.libraries();require(f.events().empty(),"reading host config executed native code");ForeignScope scope(libs);require(invoke(f.binding()).scalar==42,"configured call differs");});
  run("relative grants follow the actual configuration parent through symlinks",[&]{Fixture f(module);auto actual=f.root/"actual";fs::create_directories(actual/"inner");fs::rename(f.bundle,actual/"bundle");write(actual/"host.json",f.grants.dump());fs::create_directory_symlink(actual/"inner",f.root/"link");f.grants["libraries"]=J::object();f.save();ForeignScope scope(loadForeignLibraries((f.root/"link/../host.json").string()));require(invoke(f.binding()).scalar==42,"configuration path was normalized before symlink resolution");});
  run("absent and shadowing scopes do not gain environment authority",[&]{Fixture f(module);::setenv("NEX_FOREIGN_CONFIG",f.config.c_str(),1);error("E_FFI_GRANT",[&]{invoke(f.binding());});{ForeignScope outer(f.libraries());{ForeignScope deny(std::make_shared<ForeignLibraries>(std::map<std::string,ForeignLibraryGrant>{}));error("E_FFI_GRANT",[&]{invoke(f.binding());});require(f.events().empty(),"denied inner context fell back");}require(invoke(f.binding()).scalar==42,"outer context not restored");}error("E_FFI_GRANT",[&]{invoke(f.binding());});});
  run("non-LIFO destruction cannot restore an ended scope",[&]{Fixture f(module);auto outer=std::make_unique<ForeignScope>(f.libraries());auto inner=std::make_unique<ForeignScope>(f.libraries());outer.reset();require(invoke(f.binding()).scalar==42,"live inner context lost");inner.reset();error("E_FFI_GRANT",[&]{invoke(f.binding());});});
  run("scope nesting is bounded and ended contexts are pruned without calls",[&]{Fixture f(module);auto libs=f.libraries();for(int i=0;i<5000;++i){ForeignScope scope(libs);}std::vector<std::unique_ptr<ForeignScope>> nested;for(int i=0;i<64;++i)nested.push_back(std::make_unique<ForeignScope>(libs));error("E_FFI_LIMIT",[&]{ForeignScope excessive(libs);});nested.clear();ForeignScope fresh(libs);require(f.events().empty(),"context management initialized native code");});
  run("host JSON rejects unknown duplicate malformed and excessive fields",[&]{for(int mode=0;mode<8;++mode){Fixture f(module);if(mode==0)f.grants["extra"]=true;if(mode==1)f.grants["module_limit"]=0;if(mode==2)f.grants["module_limit"]=-1;if(mode==3)f.grants["module_limit"]=1.5;if(mode==4)f.grants["libraries"]["test"]["exports"]=J::array({"echo","echo"});if(mode==5)f.grants["libraries"]["test"]["manifest_sha256"]="bad";if(mode==6)f.grants["libraries"]["test"]["directory"]=std::string("x\0y",3);f.save();if(mode==7)write(f.config,"{\"schema\":0,\"schema\":1}");error("E_FFI_GRANT",[&]{f.libraries();});require(f.events().empty(),"invalid config executed code");}});
  run("configuration files must be bounded regular files without final symlinks",[&]{Fixture f(module);auto link=f.root/"link";fs::create_symlink(f.config,link);error("E_FFI_IO",[&]{loadForeignLibraries(link.string());});error("E_FFI_IO",[&]{loadForeignLibraries(f.root.string());});error("E_FFI_IO",[&]{loadForeignLibraries((f.root/"absent").string());});int fd=::open(f.config.c_str(),O_WRONLY);require(fd>=0&&::ftruncate(fd,1048577)==0,"large fixture failed");::close(fd);error("E_FFI_LIMIT",[&]{f.libraries();});});
  run("invalid binding metadata is rejected before native initialization",[&]{Fixture f(module);ForeignScope scope(f.libraries());for(int mode=0;mode<5;++mode){auto b=J::parse(f.binding());if(mode==0)b["schema"]="wrong";if(mode==1)b["extra"]=true;if(mode==2)b["export"]="bad-name";if(mode==3)b["manifest_sha256"]="bad";if(mode==4)b["signature"]["types"][0]["kind"]="unknown";error(mode==4?"E_FFI_SIGNATURE":"E_FFI_BINDING",[&]{invoke(b.dump());});}require(f.events().empty(),"bad binding initialized code");});
  run("metadata and argument bounds apply before allocation or polling",[&]{Fixture f(module);ForeignScope scope(f.libraries());bool polled=false;std::vector<Value> args(4097);error("E_FFI_LIMIT",[&]{invokeScopedForeign(f.binding(),args,[&]{polled=true;});});error("E_FFI_LIMIT",[&]{invoke(std::string(1048577,' '),[&]{polled=true;});});require(!polled&&f.events().empty(),"excessive input reached poll or C");});
  run("bounded metadata cache permits warm entries after exhaustion",[&]{Fixture f(module);ForeignScopeLimits limits;limits.bindings=2;ForeignScope scope(f.libraries(),limits);auto b=f.binding();require(invoke(b).scalar==42&&invoke(" "+b).scalar==42,"metadata cache failed");error("E_FFI_LIMIT",[&]{invoke("  "+b);});require(invoke(b).scalar==42,"warm binding lost after exhaustion");});
  run("metadata byte and call budgets are enforced",[&]{Fixture f(module);ForeignScopeLimits limits;limits.metadataBytes=f.binding().size()-1;{ForeignScope scope(f.libraries(),limits);error("E_FFI_LIMIT",[&]{invoke(f.binding());});}require(f.events().empty(),"metadata budget checked after init");limits.metadataBytes=1048576;limits.call.references=1;{ForeignScope scope(f.libraries(),limits);require(invoke(f.binding()).scalar==42,"minimal scalar reference budget failed");}limits.call.references=0;error("E_FFI_LIMIT",[&]{ForeignScope scope(f.libraries(),limits);});});
  run("call snapshots survive destruction of caller values metadata and poll",[&]{Fixture f(module);ForeignScope scope(f.libraries());auto b=f.binding();std::vector<Value> args{Value(42)};std::function<void()> poll;poll=[&]{b.clear();args.clear();poll={};};require(invokeScopedForeign(b,args,poll).scalar==42,"caller storage leaked into invocation");});
  run("destroying the selected scope in a poll prevents initialization",[&]{Fixture f(module);auto scope=std::make_unique<ForeignScope>(f.libraries());error("E_FFI_SCOPE",[&]{invoke(f.binding(),[&]{scope.reset();});});require(f.events().empty(),"ended scope initialized module");});
  run("scope destruction inside C keeps code mapped until unwind",[&]{Fixture f(module);auto scope=std::make_unique<ForeignScope>(f.libraries());bool ended=false;error("E_FFI_SCOPE",[&]{invoke(f.binding(),[&]{if(f.events().find('C')!=std::string::npos){scope.reset();ended=true;require(f.events().find('D')==std::string::npos,"executing C code was unloaded");}});});require(ended&&f.events()=="IGCD","scope unwind failed final cleanup");});
  run("request authority is captured before the first user poll",[&]{Fixture f(module);ForeignScope scope(f.libraries());auto request=std::make_unique<RequestScope>();error("E_RESOURCE_SCOPE",[&]{invoke(f.binding(),[&]{request.reset();});});require(f.events().empty(),"destroyed request gained process authority");});
  run("cached metadata rebinds to each real request scope",[&]{Fixture f(module);ForeignScope scope(f.libraries());for(int i=0;i<2;++i){RequestScope request;require(invoke(f.binding()).scalar==42,"request call failed");request.cancel();error("E_RESOURCE_SCOPE",[&]{invoke(f.binding());});}require(f.events()=="IGCDIGCD","request close/rebind did not release images");});
  run("native scalar and unit results use internal owned result boxes",[&]{Fixture f(module);ForeignScope scope(f.libraries());RequestScope request;auto a=pack({Value(42)});require(native(f.binding(),a).scalar==42,"native scalar bridge differs");nex_release(a);a=pack({});(void)native(f.binding("unit"),a);nex_release(a);});
  run("native bridge validates pack pointers and preserves source diagnostics",[&]{Fixture f(module);ForeignScope scope(f.libraries());RequestScope request;auto a=pack({Value(42)});trap("E_FFI_TYPE",91,[&]{auto h=nex_foreign_invoke(f.binding().data(),f.binding().size(),nullptr,91);nex_release(h);});trap("E_FFI_BINDING",92,[&]{auto h=nex_foreign_invoke(nullptr,1,a,92);nex_release(h);});trap("E_FFI_TYPE",93,[&]{native(f.binding("wrong"),a,93);});auto s=makeHandle(Value(string("wrong pack")));trap("E_FFI_TYPE",94,[&]{native(f.binding(),s,94);});nex_release(s);nex_release(a);});
  run("native cancellation is sticky when C ignores the poll status",[&]{Fixture f(module);ForeignScope scope(f.libraries());RequestScope request;request.setCancellation([&]{return f.events().find('C')!=std::string::npos;});auto a=pack({Value(42)});trap("E_CANCELLED",55,[&]{native(f.binding(),a);});nex_release(a);require(f.events()=="IGCD","cancelled request leaked image");});
  run("native bridge retains every value kind and checked nominal nesting",[&]{Fixture f(module);ForeignScope scope(f.libraries());RequestScope request;TextFiles files(f.root.string(),false);auto file=files.open("input",FileMode::Read);auto callback=std::make_shared<Data>(Data::Closure);callback->text="host::callback";auto record=std::make_shared<Data>(Data::Record);record->text="host::Packet";record->names={"value"};record->values={Value(7)};auto e=std::make_shared<Data>(Data::Enum);e->text="host::Maybe::Some";e->ordinal=1;e->names={"value"};e->values={Value(record)};auto list=std::make_shared<Data>(Data::List);list->values={success(Value(e))};std::vector<uint8_t> bytes{0,255,128,1};std::vector<Value> values{Value(42),Value(1,true),Value::floating(1.25),Value(string(std::string("Я\0🧠",7))),Value(nexrt::bytes(ByteBuffer::copy(bytes))),Value(fileValue(file)),Value(callback),Value(list)};auto a=pack(values);auto result=native(f.binding("values"),a);nex_release(a);require(result.object->text=="host::Bundle"&&result.object->names.size()==8&&result.object->values.size()==8,"native nominal layout differs");for(size_t i=0;i<values.size();++i)require(equal(result.object->values[i],values[i]),"native field payload or owner differs");require(fileResource(result.object->values[5].object).identity()==file.identity()&&result.object->values[6].object==callback,"native borrowed authority changed");});
  run("host poll may re-enter a cached scoped call",[&]{Fixture f(module);ForeignScope scope(f.libraries());require(invoke(f.binding()).scalar==42,"warm call failed");bool nested=false;require(invoke(f.binding(),[&]{if(!nested){nested=true;require(invoke(f.binding()).scalar==42,"nested scoped call failed");}}).scalar==42&&nested,"reentrant poll did not finish");});
  run("independent thread contexts share one image and keep their own grants",[&]{Fixture f(module);std::vector<std::shared_ptr<ForeignLibraries>> catalogues;for(int i=0;i<8;++i)catalogues.push_back(f.libraries());std::barrier start(8);std::atomic<bool> failed=false;std::vector<std::thread> threads;for(int i=0;i<8;++i)threads.emplace_back([&,i]{try{ForeignScope scope(catalogues[i]);start.arrive_and_wait();for(int j=0;j<16;++j)require(invoke(f.binding()).scalar==42,"thread result differs");}catch(...){failed=true;}});for(auto &t:threads)t.join();require(!failed,"independent context call failed");auto events=f.events();require(std::count(events.begin(),events.end(),'I')==1&&std::count(events.begin(),events.end(),'G')==1&&std::count(events.begin(),events.end(),'C')==128,"global image sharing differs");error("E_FFI_GRANT",[&]{invoke(f.binding());});});
  run("native finish performs terminal context and module cleanup",[&]{Fixture f(module);auto libs=f.libraries();ForeignScope scope(libs);auto a=pack({Value(42)});require(native(f.binding(),a).scalar==42,"finish setup failed");nex_release(a);nex_runtime_finish();require(f.events()=="IGCD","native finish retained module image");error("E_FFI_GRANT",[&]{invoke(f.binding());});error("E_RESOURCE_SCOPE",[&]{libs->bind("test","echo",ForeignSignature(signature("echo").dump()),f.pin);});});
  run("native terminal cleanup revokes module owners before process failure",[&]{Fixture f(module);auto bindingPath=(f.root/"binding.json").string();write(bindingPath,f.binding());
#ifdef _WIN32
    auto own=fs::absolute(argv[0]).wstring();auto command=L"\""+own+L"\" --fatal \""+f.config.wstring()+L"\" \""+nexrt::platform::wide(bindingPath)+L"\"";
    STARTUPINFOW start{};start.cb=sizeof(start);PROCESS_INFORMATION process{};
    require(CreateProcessW(own.c_str(),command.data(),nullptr,nullptr,FALSE,CREATE_NO_WINDOW,nullptr,nullptr,&start,&process),"CreateProcess fatal fixture failed");
    nexrt::host_windows::Handle child(process.hProcess),thread(process.hThread);DWORD code=0;
    require(WaitForSingleObject(child.value,30000)==WAIT_OBJECT_0&&GetExitCodeProcess(child.value,&code)&&code==70,"fatal host exit differs");
#else
    pid_t child=::fork();require(child>=0,"fork failed");if(!child){::execl(argv[0],argv[0],"--fatal",f.config.c_str(),bindingPath.c_str(),static_cast<char*>(nullptr));::_exit(127);}int status=0;require(::waitpid(child,&status,0)==child&&WIFEXITED(status)&&WEXITSTATUS(status)==70,"fatal host exit differs");
#endif
    require(f.events()=="IGCD","fatal native exit did not finalize module");});
  std::cout<<"foreign invocation contexts: "<<cases<<" cases passed\n";return 0;
}catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 1;}}
