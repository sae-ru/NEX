#include "nex_files.h"
#include <atomic>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <thread>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

namespace fs=std::filesystem;
namespace {
void require(bool value,const std::string &message){if(!value)throw std::runtime_error(message);}
void successful(const nexrt::Value &value){require(nexrt::isSuccess(value),nexrt::printable(value));}
std::string text(const nexrt::Value &value){successful(value);return nexrt::unwrap(value).object->text;}
void code(const nexrt::Value &value,const std::string &expected){require(!nexrt::isSuccess(value)&&value.object->text==expected,"expected "+expected+", got "+nexrt::printable(value));}
void raw(const fs::path &path,const std::string &value){std::ofstream stream(path,std::ios::binary);stream.write(value.data(),value.size());require(bool(stream),"fixture write failed");}
int descriptors(){int count=0;for(int fd=0;fd<512;++fd)if(::fcntl(fd,F_GETFD)>=0)++count;return count;}
void noTemporary(const fs::path &root){for(const auto &entry:fs::recursive_directory_iterator(root))require(!entry.path().filename().string().starts_with(".nex-write-"),"orphan temporary file");}
struct Fixture {
  fs::path directory;
  Fixture(){auto pattern=(fs::temp_directory_path()/"nex-files-XXXXXX").string();auto *p=::mkdtemp(pattern.data());require(p,"cannot create fixture");directory=fs::canonical(p);}
  ~Fixture(){std::error_code error;fs::remove_all(directory,error);}
};
}
int main(){
  try{
    Fixture fixture;auto root=fixture.directory/"root",outside=fixture.directory/"outside";
    fs::create_directories(root/"nested");fs::create_directories(outside);
    raw(outside/"private.txt","outside remains unchanged");
    nexrt::TextFiles files(root.string(),true),readonly(root.string(),false);
    unsigned cases=0;
    auto run=[&](const char *name,const auto &call){call();++cases;std::cout<<"PASS "<<name<<'\n';};
    run("Unicode and embedded NUL",[&]{
      auto value=std::string("A\0",2)+"Я🧠\n";successful(files.write("nested/Я🧠.txt",value));
      require(text(files.read("nested/Я🧠.txt"))==value,"Unicode roundtrip differs");
    });
    run("read-only capability",[&]{code(readonly.write("denied","text"),"CAPABILITY");require(!fs::exists(root/"denied"),"denied write created a file");});
    run("missing file and parent",[&]{code(files.read("missing"),"NOT_FOUND");code(files.write("missing/file","x"),"NOT_FOUND");});
    run("path rejection",[&]{
      for(const auto &name:std::vector<std::string>{"","../outside/private.txt","/absolute","nested//file","nested/./file","nested/../file","nested/",std::string("zero\0file",9),std::string(4097,'a')}){
        code(files.read(name),"VALIDATION");code(files.write(name,"x"),"VALIDATION");
      }
    });
    run("symlinked leaf and parent",[&]{
      fs::create_symlink(outside/"private.txt",root/"link");fs::create_directory_symlink(outside,root/"linked-directory");
      code(files.read("link"),"VALIDATION");code(files.write("link","overwritten"),"VALIDATION");
      code(files.read("linked-directory/private.txt"),"VALIDATION");code(files.write("linked-directory/private.txt","overwritten"),"VALIDATION");
      require(text(nexrt::TextFiles(outside.string(),false).read("private.txt"))=="outside remains unchanged","outside file changed");
    });
    run("invalid UTF-8",[&]{
      auto invalid=std::string("\xc3\x28",2);raw(root/"invalid",invalid);code(files.read("invalid"),"E_UTF8");
      code(files.write("new-invalid",invalid),"E_UTF8");require(!fs::exists(root/"new-invalid"),"invalid write created a file");
    });
    run("exact byte limit and oversized files",[&]{
      std::string maximum(nexrt::TextFiles::textLimit,'x');successful(files.write("maximum",maximum));require(text(files.read("maximum"))==maximum,"exact limit failed");
      maximum+='x';code(files.write("too-large",maximum),"LIMIT");raw(root/"too-large",maximum);code(files.read("too-large"),"LIMIT");
    });
    run("non-regular files do not block",[&]{
      require(::mkfifo((root/"fifo").c_str(),0600)==0,"cannot create FIFO");
      code(files.read("fifo"),"VALIDATION");code(files.write("fifo","x"),"VALIDATION");code(files.read("nested"),"VALIDATION");
      code(nexrt::TextFiles("/dev",false).read("null"),"VALIDATION");
    });
    run("private replacement mode",[&]{
      auto old=::umask(077);auto result=files.write("mode","value");::umask(old);successful(result);
      struct stat info{};require(::stat((root/"mode").c_str(),&info)==0 && (info.st_mode&0777)==0600,"new file mode is not private");
    });
    run("cancellation before commit preserves destination",[&]{
      successful(files.write("original","preserved"));auto baseline=descriptors();
      for(unsigned stop:{2,3,6}){
        unsigned polls=0;bool cancelled=false;
        try{files.write("original",std::string(150000,'y'),[&]{if(++polls==stop)throw std::runtime_error("cancelled");});}
        catch(const std::runtime_error &error){require(std::string(error.what())=="cancelled","unexpected cancellation error");cancelled=true;}
        require(cancelled,"cancellation was not observed");require(text(files.read("original"))=="preserved","cancelled write changed destination");
        noTemporary(root);require(descriptors()==baseline,"cancelled write leaked descriptors");
      }
      unsigned polls=0;bool cancelled=false;
      try{files.read("maximum",[&]{if(++polls==2)throw std::runtime_error("cancelled");});}catch(const std::runtime_error &){cancelled=true;}
      require(cancelled && descriptors()==baseline,"cancelled read leaked descriptors");
    });
    run("concurrent writes are complete replacements",[&]{
      std::string first(200000,'a'),second(200000,'b');successful(files.write("concurrent",first));std::atomic<bool> failed=false;
      auto writer=[&](const std::string &value){for(unsigned i=0;i<8;++i)if(!nexrt::isSuccess(files.write("concurrent",value)))failed=true;};
      std::thread a(writer,std::cref(first)),b(writer,std::cref(second));
      for(unsigned i=0;i<30;++i){auto value=text(files.read("concurrent"));if(value!=first && value!=second)failed=true;}
      a.join();b.join();require(!failed,"concurrent reader observed a partial file");noTemporary(root);
    });
    run("repeated success and failure close descriptors",[&]{
      auto baseline=descriptors();
      for(unsigned i=0;i<60;++i){code(files.read("missing"),"NOT_FOUND");code(files.read("link"),"VALIDATION");successful(files.write("repeat","x"));require(text(files.read("repeat"))=="x","repeat differs");}
      require(descriptors()==baseline,"filesystem operations leaked descriptors");
    });
    run("opened root remains pinned after rename",[&]{
      auto moved=fixture.directory/"moved";fs::rename(root,moved);fs::create_directory(root);raw(root/"original","wrong root");
      require(text(files.read("original"))=="preserved","root followed a replaced pathname");successful(files.write("pinned","correct root"));
      require(fs::exists(moved/"pinned") && !fs::exists(root/"pinned"),"write escaped opened root");
    });
    std::cout<<"filesystem adapter: "<<cases<<" cases passed\n";return 0;
  }catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 1;}
}
