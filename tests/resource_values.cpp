#include "nex_file_abi.h"
#include "nex_files.h"
#include "nex_json.h"
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <mutex>
#include <thread>
#include <fcntl.h>
#include <unistd.h>

using namespace nexrt;
namespace fs=std::filesystem;
namespace {
std::mutex profileMutex;
std::map<const void*,std::pair<size_t,int>> allocations;
bool profileError=false;
void require(bool value,const std::string &message){if(!value)throw std::runtime_error(message);}
template<class F> void error(const std::string &expected,F operation){
  try{operation();}catch(const DataError &e){require(e.code==expected,"expected "+expected+", got "+e.code);return;}
  throw std::runtime_error("expected "+expected);
}
void code(const Value &value,const std::string &expected){require(!isSuccess(value)&&value.object->text==expected,"unexpected result: "+printable(value));}
Value checked(Handle *handle){auto value=readHandle(handle);require(isSuccess(value),printable(value));return unwrap(value);}
ByteBuffer binary(std::string_view text){return ByteBuffer::copy({reinterpret_cast<const uint8_t*>(text.data()),text.size()});}
std::string text(const ByteBuffer &bytes){auto v=bytes.view();return v.empty()?std::string():std::string(reinterpret_cast<const char*>(v.data()),v.size());}
int descriptors(){int n=0;for(int fd=0;fd<1024;++fd)if(::fcntl(fd,F_GETFD)>=0)++n;return n;}
void raw(const fs::path &path,const std::string &text){std::ofstream out(path,std::ios::binary);out.write(text.data(),text.size());require(bool(out),"fixture write failed");}
struct Fixture {
  fs::path root;
  Fixture(){auto p=(fs::temp_directory_path()/"nex-resource-values-XXXXXX").string();require(::mkdtemp(p.data()),"mkdtemp failed");root=fs::canonical(p);}
  ~Fixture(){std::error_code e;fs::remove_all(root,e);}
};
Handle *path(const char *name){return makeHandle(Value(string(name)));}
Handle *opened(Handle *name){auto result=nex_file_open_read(name,10);auto file=makeHandle(checked(result));nex_release(result);return file;}
}
extern "C" {
void nex_profile_enter(const char*,const char*,int64_t,const char*){}
void nex_profile_leave(){}
void nex_profile_unwind(){}
void nex_profile_allocation(const void *p,size_t size,int pool){std::lock_guard guard(profileMutex);if(!allocations.emplace(p,std::pair{size,pool}).second)profileError=true;}
void nex_profile_free(const void *p){std::lock_guard guard(profileMutex);if(allocations.erase(p)!=1)profileError=true;}
}
int main(){try{
  unsigned cases=0;auto run=[&](const char *name,const auto &body){
    auto before=descriptors();body();require(descriptors()==before,"FD leak after "+std::string(name));
    require(liveObjects==0,"managed object leak after "+std::string(name));
    require(!profileError&&allocations.empty(),"profile ownership mismatch after "+std::string(name));
    ++cases;std::cout<<"PASS "<<name<<std::endl;
  };
  run("owned file subtype preserves base layout and profile size",[]{
    static_assert(Data::Bytes==7&&Data::File==8);Fixture f;raw(f.root/"input","text");TextFiles files(f.root.string(),false);auto before=descriptors();
    auto value=fileValue(files.open("input",FileMode::Read));require(value->kind==Data::File,"wrong kind");
    require(allocations.at(value.get())==std::pair{sizeof(FileData),1},"wrong subtype allocation size");
    require(fileResource(value).isOpen()&&descriptors()==before+1,"file payload missing");
    error("E_RUNTIME",[]{(void)std::make_shared<Data>(Data::File);});
    error("E_RUNTIME",[&]{(void)std::make_shared<Data>(*value);});
    error("E_RUNTIME",[]{fileResource(string("wrong"));});error("E_RUNTIME",[]{fileResource({});});
    value.reset();require(descriptors()==before,"last value did not close descriptor");
  });
  run("separate managed wrappers alias one resource identity",[]{
    Fixture f;raw(f.root/"input","text");TextFiles files(f.root.string(),false);
    Value a(fileValue(files.open("input",FileMode::Read))),b(fileValue(fileResource(a.object))),c(fileValue(files.open("input",FileMode::Read)));
    require(a.object!=b.object&&equal(a,b)&&!equal(a,c)&&!equal(a,Value(string("text"))),"file equality became structural");
    require(fileResource(b.object).close()&&!fileResource(a.object).close()&&!fileResource(a.object).isOpen(),"managed aliases have separate close state");
    require(printable(a)=="<file>"&&representation(a)=="\"<file>\"","opaque display exposes host data");
  });
  run("aggregate result and closure captures retain file owner",[]{
    Fixture f;raw(f.root/"input","data");TextFiles files(f.root.string(),false);auto before=descriptors();
    Value file(fileValue(files.open("input",FileMode::Read)));auto list=std::make_shared<Data>(Data::List);list->values={file};
    auto record=std::make_shared<Data>(Data::Record);record->names={"items"};record->values={Value(list)};
    auto closure=std::make_shared<Data>(Data::Closure);closure->values={success(Value(record))};file={};list.reset();record.reset();
    auto retained=unwrap(closure->values[0]).object->values[0].object->values[0];require(text(fileResource(retained.object).read(10))=="data","capture lost resource");
    closure.reset();require(descriptors()==before+1,"borrowed managed value did not retain owner");retained={};require(descriptors()==before,"aggregate release leaked file");
  });
  run("file values are rejected at every JSON nesting boundary",[]{
    Fixture f;raw(f.root/"input","data");TextFiles files(f.root.string(),false);Value file(fileValue(files.open("input",FileMode::Read)));
    for(auto kind:{Data::List,Data::Record,Data::Enum}){auto data=std::make_shared<Data>(kind);data->values={file};data->names={"resource"};data->text="model::Some";error("E_JSON",[&]{encodeJSON(Value(data));});}
    error("E_JSON",[&]{encodeJSON(file);});error("E_JSON",[&]{encodeJSON(success(file));});
    require(fileResource(file.object).isOpen(),"failed JSON consumed resource");
  });
  run("joined domains bind independent quotas and revoke from either side",[]{
    ResourceDomain request(1),first,second;auto a=request.combine(first),b=request.combine(second);
    auto value=a.make<int>([](const auto &){return std::make_unique<int>(42);});int factories=0;
    error("E_RESOURCE_LIMIT",[&]{b.make<int>([&](const auto &){++factories;return std::make_unique<int>(7);});});
    require(!factories&&request.used()==1&&first.used()==1&&!second.used(),"joint quota bypass");
    first.revoke();require(!value.isOpen()&&!request.used(),"capability revocation failed");
    auto other=b.make<int>([](const auto &){return std::make_unique<int>(7);});request.revoke();require(!other.isOpen(),"request revocation failed");
  });
  run("diagnostic file identities cannot authorize native IO",[]{
    Value a(diagnosticFile(17)),b(diagnosticFile(17)),c(diagnosticFile(18));require(equal(a,b)&&!equal(a,c),"diagnostic identity equality differs");
    error("E_RUNTIME",[&]{fileResource(a.object);});error("E_JSON",[&]{encodeJSON(a);});
    RequestScope request;auto file=makeHandle(a);code(readHandle(nex_file_read(file,1,9)),"E_RUNTIME");
    bool trapped=false;try{nex_file_is_open(file,9);}catch(const Trap &t){trapped=t.code=="E_RUNTIME"&&t.line==9;}require(trapped,"diagnostic file granted status authority");
  });
  run("native streaming ABI read write append seek flush and close",[]{
    Fixture f;TextFiles files(f.root.string(),true);FileScope grant(files);RequestScope request;
    auto name=path("output"),write=makeHandle(checked(nex_file_open_write(name,10)));
    auto data=makeHandle(Value(bytes(binary(std::string("A\0",2)+"Я🧠"))));
    require(checked(nex_file_write(write,data,11)).scalar==8&&checked(nex_file_size(write,12)).scalar==8,"write/size ABI differs");
    require(checked(nex_file_seek(write,1,13)).scalar==1&&checked(nex_file_flush(write,14)).scalar==1,"seek/flush ABI differs");
    require(nex_file_close(write,15)==1&&nex_file_close(write,16)==0&&!nex_file_is_open(write,17),"close ABI differs");
    auto append=makeHandle(checked(nex_file_open_append(name,18)));auto extra=makeHandle(Value(bytes(binary("!"))));
    require(checked(nex_file_write(append,extra,19)).scalar==1,"append ABI differs");
    auto read=opened(name);require(text(byteBuffer(checked(nex_file_read(read,100,20)).object))==std::string("A\0",2)+"Я🧠!","read ABI differs");
    require(byteBuffer(checked(nex_file_read(read,1,21)).object).length()==0,"EOF ABI differs");
    require(checked(nex_file_seek(read,2,22)).scalar==2&&text(byteBuffer(checked(nex_file_read(read,100,23)).object))=="Я🧠!","shared seek differs");
  });
  run("native stream errors are recoverable results",[]{
    Fixture f;raw(f.root/"input","data");TextFiles files(f.root.string(),false);FileScope grant(files);RequestScope request;
    auto name=path("input"),file=opened(name),empty=makeHandle(Value(bytes({})));
    code(readHandle(nex_file_open_write(name,31)),"CAPABILITY");code(readHandle(nex_file_open_read(path("missing"),32)),"NOT_FOUND");
    code(readHandle(nex_file_write(file,empty,33)),"CAPABILITY");code(readHandle(nex_file_flush(file,34)),"CAPABILITY");
    code(readHandle(nex_file_read(file,-1,35)),"E_RANGE");code(readHandle(nex_file_read(file,TextFiles::byteLimit+1,36)),"LIMIT");
    code(readHandle(nex_file_seek(file,-1,37)),"E_RANGE");nex_file_close(file,38);code(readHandle(nex_file_read(file,0,39)),"E_RESOURCE_CLOSED");
  });
  run("HTTP request ABI denies implicit environment grants",[]{
    Fixture f;raw(f.root/"input","data");::setenv("NEX_FILES_ROOT",f.root.c_str(),1);
    {RequestScope request;code(readHandle(nex_file_open_read(path("input"),41)),"CAPABILITY");}
    ::unsetenv("NEX_FILES_ROOT");resetFileEnvironment();
  });
  run("request exit revokes escaped values while host grant survives",[]{
    Fixture f;raw(f.root/"input","data");TextFiles files(f.root.string(),false);FileScope grant(files);Value escaped;
    {RequestScope request;escaped=checked(nex_file_open_read(path("input"),45));require(fileResource(escaped.object).isOpen(),"request open failed");}
    error("E_RESOURCE_SCOPE",[&]{fileResource(escaped.object).read(0);});
    require(text(fileOpen("input",FileMode::Read,false).read(10))=="data","request exit revoked independent host grant");
  });
  run("cross-thread cancellation revokes escaped file before request exit",[]{
    Fixture f;raw(f.root/"input","data");TextFiles files(f.root.string(),false);FileScope grant(files);RequestScope request;
    auto file=opened(path("input"));auto escaped=readHandle(file);auto before=descriptors();
    std::thread cancel([&]{request.cancel();});cancel.join();require(!fileResource(escaped.object).isOpen()&&descriptors()==before-1,"cancel did not revoke physical file");
    bool trapped=false;try{nex_file_is_open(file,51);}catch(const Trap &t){trapped=t.code=="E_CANCELLED"&&t.line==51;}require(trapped,"cancel trap lost source line");
  });
  run("post-read cancellation releases operation lease",[]{
    Fixture f;raw(f.root/"input","data");TextFiles files(f.root.string(),false);FileScope grant(files);RequestScope request;
    auto file=opened(path("input"));auto before=descriptors();unsigned polls=0;request.setCancellation([&]{return ++polls==2;});
    bool trapped=false;try{nex_file_read(file,4,61);}catch(const Trap &t){trapped=t.code=="E_CANCELLED"&&t.line==61;}
    require(trapped&&polls==2&&!fileResource(readHandle(file).object).isOpen()&&descriptors()==before-1,"post-read lease leaked");
  });
  run("budget trap revokes file values without early descriptor reuse",[]{
    Fixture f;raw(f.root/"input","data");TextFiles files(f.root.string(),false);FileScope grant(files);RequestScope request(3);
    auto file=opened(path("input"));auto before=descriptors();bool trapped=false;
    try{nex_file_read(file,1,71);}catch(const Trap &t){trapped=t.code=="E_LIMIT"&&t.line==71;}
    require(trapped&&!fileResource(readHandle(file).object).isOpen()&&descriptors()==before-1,"budget trap retained authority or lease");
  });
  run("canceled native open unwinds pending reservation and descriptor",[]{
    Fixture f;raw(f.root/"input","data");TextFiles files(f.root.string(),false);FileScope grant(files);auto before=descriptors();bool trapped=false;
    try{RequestScope request;unsigned polls=0;request.setCancellation([&]{return ++polls==3;});nex_file_open_read(path("input"),81);}
    catch(const Trap &t){trapped=t.code=="E_CANCELLED"&&t.line==81;}
    require(trapped&&descriptors()==before,"canceled open leaked descriptor");require(files.open("input",FileMode::Read).isOpen(),"cancel poisoned root capability");
  });
  run("deadline trap revokes an already-bound host file",[]{
    Fixture f;raw(f.root/"input","data");TextFiles files(f.root.string(),false);auto capability=files.resourceScope();RequestScope request(1000000,0);
    auto value=fileValue(files.openIn(request.bindResources(capability),"input",FileMode::Read));auto file=makeHandle(Value(value));auto before=descriptors();bool trapped=false;
    try{nex_file_size(file,85);}catch(const Trap &t){trapped=t.code=="E_TIMEOUT"&&t.line==85;}
    require(trapped&&!fileResource(value).isOpen()&&descriptors()==before-1,"deadline left an external resource live");
  });
  run("one request quota spans multiple explicit capabilities",[]{
    Fixture a,b;raw(a.root/"input","a");raw(b.root/"input","b");TextFiles first(a.root.string(),false),second(b.root.string(),false);FileScope grant(first);RequestScope request;
    for(int i=0;i<32;++i)opened(path("input"));
    {FileScope another(second);for(int i=0;i<32;++i)opened(path("input"));code(readHandle(nex_file_open_read(path("input"),91)),"E_RESOURCE_LIMIT");}
    require(checked(nex_file_size(opened(path("input")),92)).scalar==1,"revoked second scope failed to return request quota");
  });
  run("native byte argument remains owned while cancellation callback drops handles",[]{
    Fixture f;TextFiles files(f.root.string(),true);FileScope grant(files);RequestScope request;
    auto file=makeHandle(checked(nex_file_open_write(path("output"),101))),data=makeHandle(Value(bytes(binary(std::string(150000,'x')))));
    bool dropped=false;request.setCancellation([&]{if(!dropped){dropped=true;nex_release(data);}return false;});
    require(checked(nex_file_write(file,data,102)).scalar==150000,"callback dropped in-flight bytes");
    require(dropped&&checked(nex_file_size(file,103)).scalar==150000,"native byte callback state differs");
  });
  run("scalar file ABI retains handles before polling",[]{
    Fixture f;raw(f.root/"input","data");TextFiles files(f.root.string(),false);FileScope grant(files);RequestScope request;
    auto file=opened(path("input"));auto before=descriptors();bool dropped=false;
    request.setCancellation([&]{if(!dropped){dropped=true;nex_release(file);}return false;});
    require(nex_file_close(file,105)==1&&dropped&&descriptors()==before-1,"scalar close used released handle");
    request.setCancellation({});auto other=opened(path("input"));before=descriptors();dropped=false;
    request.setCancellation([&]{if(!dropped){dropped=true;nex_release(other);request.setCancellation({});}return false;});
    require(nex_file_is_open(other,106)==1&&dropped&&descriptors()==before-1,"scalar query used released handle/callback");
  });
  run("poll callback can end its own native request scope",[]{
    Fixture f;raw(f.root/"input","data");TextFiles files(f.root.string(),false);FileScope grant(files);
    auto request=std::make_unique<RequestScope>();auto file=opened(path("input"));auto before=descriptors();bool trapped=false;
    request->setCancellation([&]{request.reset();return false;});
    try{nex_file_read(file,1,107);}catch(const Trap &t){trapped=t.code=="E_CANCELLED"&&t.line==107;}
    require(trapped&&!request&&!inRequestScope()&&descriptors()==before-1,"ended scope retained callback/handles/descriptor");
    require(fileOpen("input",FileMode::Read,false).isOpen(),"ended request poisoned explicit host grant");
  });
  run("parallel native requests keep thread-local bindings independent",[]{
    Fixture f;raw(f.root/"input","data");TextFiles files(f.root.string(),false);std::atomic<bool> failed=false;
    auto work=[&]{try{FileScope grant(files);for(int i=0;i<30;++i){RequestScope request;auto file=opened(path("input"));if(text(byteBuffer(checked(nex_file_read(file,4,111)).object))!="data")failed=true;if(i%2)request.cancel();}}catch(...){failed=true;}};
    std::thread a(work),b(work);a.join();b.join();require(!failed,"thread-local request binding crossed threads");
  });
  run("native cleanup revokes escaped environment values before finish",[]{
    Fixture f;raw(f.root/"input","data");::setenv("NEX_FILES_ROOT",f.root.c_str(),1);auto name=path("input"),result=nex_file_open_read(name,121);auto escaped=checked(result);
    nex_release(result);nex_release(name);cleanupRuntimeResources();require(!fileResource(escaped.object).isOpen(),"cleanup retained environment capability");
    error("E_RESOURCE_SCOPE",[&]{fileResource(escaped.object).read(0);});escaped={};nex_runtime_finish();::unsetenv("NEX_FILES_ROOT");
  });
  std::cout<<"managed file resources: "<<cases<<" cases passed\n";return 0;
}catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 1;}}
