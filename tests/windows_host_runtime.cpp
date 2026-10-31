#include "nex/task_process_windows.h"
#include "third_party/json.hpp"
#include <future>
#include <iostream>
#include <winioctl.h>
using J=nlohmann::json;
namespace fs=std::filesystem;
using nexrt::host_windows::Handle;
void require(bool condition,const char *message){if(!condition)throw std::runtime_error(message);}
std::string bytes(const fs::path &path){auto value=path.u8string();return {reinterpret_cast<const char*>(value.data()),value.size()};}
fs::path executable(){std::vector<wchar_t> path(32768);auto count=GetModuleFileNameW(nullptr,path.data(),DWORD(path.size()));require(count&&count<path.size(),"own executable path");return std::wstring(path.data(),count);}
int main(int argc,char **argv){
  try{
    if(argc>1&&std::string(argv[1])=="--echo"){
      J out={{"argument",argc>2?argv[2]:""},{"environment",nexrt::platform::environment("NEX_JOB_UNICODE").value_or("")},{"cwd",bytes(fs::current_path())}};
      std::cout<<out.dump()<<std::endl;return 42;
    }
    if(argc>2&&std::string(argv[1])=="--hold"){
      Handle file(CreateFileW(nexrt::platform::wide(argv[2]).c_str(),GENERIC_READ|GENERIC_WRITE,0,nullptr,CREATE_NEW,0,nullptr));
      require(file.value!=INVALID_HANDLE_VALUE,"descendant canary file");Sleep(30000);return 0;
    }
    if(argc>2&&(std::string(argv[1])=="--spawn"||std::string(argv[1])=="--orphan")){
      auto own=executable();auto command=nex::windows_process::quote(own.native())+L" --hold "+nex::windows_process::quote(nexrt::platform::wide(argv[2]));
      STARTUPINFOW start{};start.cb=sizeof(start);PROCESS_INFORMATION process{};
      require(CreateProcessW(own.c_str(),command.data(),nullptr,nullptr,FALSE,CREATE_NO_WINDOW,nullptr,nullptr,&start,&process),"create descendant");
      Handle thread(process.hThread),child(process.hProcess);
      for(unsigned i=0;i<300&&GetFileAttributesW(nexrt::platform::wide(argv[2]).c_str())==INVALID_FILE_ATTRIBUTES;++i)Sleep(10);
      DWORD code=0;require(GetExitCodeProcess(child.value,&code)&&code==STILL_ACTIVE,"descendant is alive");
      require(GetFileAttributesW(nexrt::platform::wide(argv[2]).c_str())!=INVALID_FILE_ATTRIBUTES,"descendant owns canary");
      std::cout<<"ready"<<std::endl;if(std::string(argv[1])=="--spawn")Sleep(30000);return 42;
    }
    if(argc>1&&std::string(argv[1])=="--flood"){std::cout<<std::string(9*1024*1024,'x');return 0;}
    require(argc==2,"provide a dedicated artifact base directory");
    auto base=fs::absolute(nexrt::platform::wide(argv[1])).lexically_normal();fs::create_directories(base);base=fs::canonical(base);
    auto model=bytes(base/L"host-XXXXXX");require(::mkdtemp(model.data()),"private test directory");auto root=fs::path(nexrt::platform::wide(model));
    auto identity=nexrt::host_windows::identity(root);require(identity&&identity->directory,"test directory identity");
    unsigned passed=0,failed=0;
    auto test=[&](const char *name,auto body){try{body();++passed;std::cout<<"PASS "<<name<<std::endl;}catch(const std::exception &error){++failed;std::cerr<<"FAIL "<<name<<": "<<error.what()<<std::endl;}};
    test("private directory ACL",[&]{require(nexrt::host_windows::isPrivateDirectory(root),"directory must have protected current-user ACL");});
    test("host bytes and real reparse rejection",[&]{
      auto path=root/L"данные 🧠";std::string data("A\0Я",4);{std::ofstream file(path,std::ios::binary);file.write(data.data(),data.size());}
      require(nexrt::host_windows::readRegular(path,64)==data,"raw host bytes differ");
      auto link=root/L"link";require(CreateSymbolicLinkW(link.c_str(),path.c_str(),SYMBOLIC_LINK_FLAG_ALLOW_UNPRIVILEGED_CREATE),"actual test symbolic link");
      bool rejected=false;try{(void)nexrt::host_windows::readRegular(link,64);}catch(const nexrt::DataError&){rejected=true;}require(rejected,"host reader followed reparse point");
    });
    test("native sparse read beyond4GiB without cursor mutation",[&]{
      auto path=root/L"sparse";constexpr int64_t offset=0x100000020LL;std::array<unsigned char,7> data{0,1,255,65,0,90,42};
      {Handle file(CreateFileW(path.c_str(),GENERIC_READ|GENERIC_WRITE,7,nullptr,CREATE_NEW,0,nullptr));require(file.value!=INVALID_HANDLE_VALUE,"sparse file creation");
       DWORD count=0;require(DeviceIoControl(file.value,FSCTL_SET_SPARSE,nullptr,0,nullptr,0,&count,nullptr),"NTFS sparse support");
       LARGE_INTEGER position{};position.QuadPart=offset;require(SetFilePointerEx(file.value,position,nullptr,FILE_BEGIN),"large seek");
       require(WriteFile(file.value,data.data(),DWORD(data.size()),&count,nullptr)&&count==data.size(),"sparse write");}
      int fd=nexrt::host_windows::openRegularDescriptor(path,O_RDONLY);require(fd>=0,"open sparse descriptor");
      struct Close{int fd;~Close(){::_close(fd);}} close{fd};std::array<unsigned char,7> observed{};
      require(nexrt::host_windows::fileSize(fd)==offset+int64_t(data.size()),"64-bit size differs");
      require(nexrt::host_windows::readAt(fd,observed.data(),observed.size(),offset)==int64_t(data.size())&&observed==data,"positioned read differs");
      require(::_lseeki64(fd,0,SEEK_CUR)==0,"positioned read changed original cursor");
    });
    auto own=bytes(executable());auto directory=bytes(root);
    auto run=[&](std::vector<std::string> args,const char *label,unsigned timeout=10){return nex::windows_process::run(args,directory,{{"NEX_JOB_UNICODE","λ Я 🧠"}},timeout,bytes(root/label));};
    test("job Unicode argument/environment/cwd and exit42",[&]{
      std::string argument="Я 🧠 quotes \" and trailing\\";auto value=run({own,"--echo",argument},"echo");
      require(value.process.code==42&&!value.timedOut&&!value.outputLimit,"job exit status");auto observed=J::parse(value.process.output);
      require(observed["argument"]==argument&&observed["environment"]=="λ Я 🧠"&&fs::equivalent(nexrt::platform::wide(observed["cwd"].get<std::string>()),root),"job transport differs");
    });
    test("job closes all repeated process handles",[&]{
      DWORD before=0,after=0;require(GetProcessHandleCount(GetCurrentProcess(),&before),"handle baseline");
      for(unsigned i=0;i<8;++i)require(run({own,"--echo","repeat"},"repeat").process.code==42,"repeated job failed");
      require(GetProcessHandleCount(GetCurrentProcess(),&after)&&after==before,"native process handles leaked");
    });
    test("timeout physically retires descendant file handle",[&]{auto marker=root/L"timeout-held";
      auto value=run({own,"--spawn",bytes(marker)},"timeout",5);require(value.timedOut&&value.process.output.find("ready")!=std::string::npos,"timeout fixture did not run");
      require(DeleteFileW(marker.c_str()),"descendant retained a file handle after job timeout");
    });
    test("root exit retires orphan descendant",[&]{auto marker=root/L"orphan-held";
      auto value=run({own,"--orphan",bytes(marker)},"orphan");require(value.process.code==42&&!value.timedOut&&value.process.output.find("ready")!=std::string::npos,"orphan fixture did not run");
      require(DeleteFileW(marker.c_str()),"orphan retained a file handle after root exit");
    });
    test("output cap retains bounded bytes",[&]{auto value=run({own,"--flood"},"flood");require(value.outputLimit&&value.process.output.size()==8*1024*1024&&fs::file_size(root/L"flood/stdout")==8*1024*1024,"output cap differs");});
    if(!failed){require(root.parent_path()==base&&fs::canonical(root)==root&&nexrt::host_windows::identity(root)==identity,"cleanup target identity changed");fs::remove_all(root);}
    std::cout<<"RESULT passed="<<passed<<" failed="<<failed<<std::endl;return failed?1:0;
  }catch(const std::exception &error){std::cerr<<error.what()<<std::endl;return 1;}
}
