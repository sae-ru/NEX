#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "nex/task_process.h"
#include "llvm/Support/Program.h"
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <thread>
#ifdef _WIN32
#include "nex/task_process_windows.h"
#endif
#if defined(__APPLE__) || defined(__linux__)
#include <cerrno>
#include <fcntl.h>
#include <signal.h>
#include <spawn.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>
#ifdef __APPLE__
#include <crt_externs.h>
#else
extern char **environ;
#endif
#if defined(__linux__)
#if !defined(__GLIBC__)
#define NEX_TASK_FORK_SPAWN 1
#elif !__GLIBC_PREREQ(2,29) || defined(NEX_TASK_PROCESS_TEST_FORK)
#define NEX_TASK_FORK_SPAWN 1
#endif
#endif
#endif
namespace nex {
#if defined(__APPLE__) || defined(__linux__)
namespace {
constexpr uint64_t outputCap=8*1024*1024;
std::atomic_flag active=ATOMIC_FLAG_INIT;
volatile sig_atomic_t supervisedGroup=0,interruptedSignal=0;
void interrupt(int signal){if(!interruptedSignal)interruptedSignal=signal;auto group=supervisedGroup;if(group>0)::kill(-group,SIGKILL);}
uint64_t size(const std::filesystem::path &path){struct stat info{};return ::stat(path.c_str(),&info)==0?uint64_t(info.st_size):0;}
std::string prefix(const std::filesystem::path &path){
  std::ifstream input(path,std::ios::binary);if(!input)throw Error("E_TASK_PROCESS","cannot read task process output");
  std::string text(std::min(size(path),outputCap),'\0');input.read(text.data(),text.size());text.resize(input.gcount());return text;
}
struct Guard {
  posix_spawn_file_actions_t files{};posix_spawnattr_t attributes{};
  sigset_t blocked{},oldMask{};struct sigaction oldInt{},oldTerm{};
  bool fileReady=false,attributeReady=false,maskReady=false,intReady=false,termReady=false;pid_t child=0;
  int spawnRead=-1,spawnWrite=-1;
  Guard(){
    if(active.test_and_set())throw Error("E_TASK_PROCESS","task process supervisor is already active");
  }
  ~Guard(){
    if(maskReady)::sigprocmask(SIG_BLOCK,&blocked,nullptr);
    if(child>0){::kill(-child,SIGKILL);while(::waitpid(child,nullptr,0)<0&&errno==EINTR){}}
    supervisedGroup=0;
    if(intReady)::sigaction(SIGINT,&oldInt,nullptr);if(termReady)::sigaction(SIGTERM,&oldTerm,nullptr);
    if(maskReady)::sigprocmask(SIG_SETMASK,&oldMask,nullptr);
    if(spawnRead>=0)::close(spawnRead);if(spawnWrite>=0)::close(spawnWrite);
    if(fileReady)::posix_spawn_file_actions_destroy(&files);if(attributeReady)::posix_spawnattr_destroy(&attributes);active.clear();
  }
  void check(int code,const char *operation){if(code)throw Error("E_TASK_PROCESS",std::string(operation)+": "+std::strerror(code));}
};
#ifdef NEX_TASK_FORK_SPAWN
// glibc before2.29 has no spawn chdir action. Never change the parent's cwd:
// prepare all storage before fork and use only async-signal-safe child calls.
pid_t spawnWithDirectory(Guard &guard,const char *executable,const char *directory,
  const char *out,const char *err,char *const *args,char *const *environment){
  int pipes[2];if(::pipe2(pipes,O_CLOEXEC)!=0)guard.check(errno,"task spawn status pipe");
  guard.spawnRead=pipes[0];guard.spawnWrite=pipes[1];
  for(auto *fd:{&guard.spawnRead,&guard.spawnWrite})if(*fd<3){
    int replacement=::fcntl(*fd,F_DUPFD_CLOEXEC,3);if(replacement<0)guard.check(errno,"task spawn status descriptor");
    ::close(*fd);*fd=replacement;
  }
  struct sigaction defaults{};defaults.sa_handler=SIG_DFL;::sigemptyset(&defaults.sa_mask);
  auto child=::fork();if(child<0)guard.check(errno,"task spawn");
  if(child==0){
    ::close(guard.spawnRead);
    auto fail=[&](){
      int code=errno;const char *data=reinterpret_cast<const char*>(&code);size_t left=sizeof(code);
      while(left){auto count=::write(guard.spawnWrite,data,left);if(count<0&&errno==EINTR)continue;if(count<=0)break;data+=count;left-=size_t(count);}
      ::_exit(127);
    };
    if(::setpgid(0,0)!=0)fail();
    if(::chdir(directory)!=0)fail();
    auto redirect=[&](const char *path,int destination,int flags){
      int fd=::open(path,flags,0600);if(fd<0)fail();
      if(fd!=destination){if(::dup2(fd,destination)<0)fail();::close(fd);}
    };
    redirect("/dev/null",0,O_RDONLY);redirect(out,1,O_WRONLY|O_CREAT|O_TRUNC);redirect(err,2,O_WRONLY|O_CREAT|O_TRUNC);
    if(::sigaction(SIGINT,&defaults,nullptr)!=0||::sigaction(SIGTERM,&defaults,nullptr)!=0)fail();
    if(::sigprocmask(SIG_SETMASK,&guard.oldMask,nullptr)!=0)fail();
    ::execve(executable,args,environment);fail();
  }
  guard.child=child;supervisedGroup=child;
  ::close(guard.spawnWrite);guard.spawnWrite=-1;
  int code=0;size_t received=0;
  while(received<sizeof(code)){
    auto count=::read(guard.spawnRead,reinterpret_cast<char*>(&code)+received,sizeof(code)-received);
    if(count<0&&errno==EINTR)continue;if(count<0)guard.check(errno,"task spawn status");if(count==0)break;received+=size_t(count);
  }
  ::close(guard.spawnRead);guard.spawnRead=-1;
  if(received&&received!=sizeof(code))throw Error("E_TASK_PROCESS","incomplete task spawn status");
  if(received)guard.check(code,"task spawn");
  return child;
}
#endif
}
#endif
TaskProcessResult runTaskProcess(const std::vector<std::string> &arguments,const std::string &directory,
  const std::map<std::string,std::string> &overrides,unsigned seconds,const std::string &logs){
#if defined(__APPLE__) || defined(__linux__)
  if(arguments.empty()||seconds==0)throw Error("E_TASK_PROCESS","task command and positive timeout required");
  for(const auto &argument:arguments)if(argument.find('\0')!=std::string::npos)throw Error("E_TASK_PROCESS","NUL is not valid in task process arguments");
  auto executable=llvm::sys::findProgramByName(arguments[0]);if(!executable)throw Error("E_TOOL","cannot find task compiler executable");
  std::filesystem::create_directories(logs);auto out=std::filesystem::path(logs)/"stdout",err=std::filesystem::path(logs)/"stderr";
  std::map<std::string,std::string> environment;
#ifdef __APPLE__
  auto inherited=*_NSGetEnviron();
#else
  auto inherited=::environ;
#endif
  for(auto entry=inherited;*entry;++entry){std::string text=*entry;auto equals=text.find('=');if(equals!=std::string::npos)environment[text.substr(0,equals)]=text.substr(equals+1);}
  for(const auto &[key,value]:overrides){if(key.empty()||key.find('=')!=std::string::npos||key.find('\0')!=std::string::npos||value.find('\0')!=std::string::npos)throw Error("E_TASK_PROCESS","invalid task environment override");environment[key]=value;}
  std::vector<std::string> entries;for(const auto &[key,value]:environment)entries.push_back(key+"="+value);
  std::vector<char*> args,env;for(const auto &arg:arguments)args.push_back(const_cast<char*>(arg.c_str()));args.push_back(nullptr);for(auto &entry:entries)env.push_back(entry.data());env.push_back(nullptr);
  Guard guard;
#ifndef NEX_TASK_FORK_SPAWN
  guard.check(::posix_spawn_file_actions_init(&guard.files),"spawn file actions");guard.fileReady=true;
  guard.check(::posix_spawnattr_init(&guard.attributes),"spawn attributes");guard.attributeReady=true;
  guard.check(::posix_spawn_file_actions_addchdir_np(&guard.files,directory.c_str()),"task working directory");
  guard.check(::posix_spawn_file_actions_addopen(&guard.files,0,"/dev/null",O_RDONLY,0),"task stdin");
  guard.check(::posix_spawn_file_actions_addopen(&guard.files,1,out.c_str(),O_WRONLY|O_CREAT|O_TRUNC,0600),"task stdout");
  guard.check(::posix_spawn_file_actions_addopen(&guard.files,2,err.c_str(),O_WRONLY|O_CREAT|O_TRUNC,0600),"task stderr");
#endif
  sigemptyset(&guard.blocked);sigaddset(&guard.blocked,SIGINT);sigaddset(&guard.blocked,SIGTERM);
  if(::sigprocmask(SIG_BLOCK,&guard.blocked,&guard.oldMask)!=0)throw Error("E_TASK_PROCESS","cannot block task setup signals");guard.maskReady=true;
#ifndef NEX_TASK_FORK_SPAWN
  guard.check(::posix_spawnattr_setpgroup(&guard.attributes,0),"task process group");
  guard.check(::posix_spawnattr_setsigmask(&guard.attributes,&guard.oldMask),"task signal mask");
  guard.check(::posix_spawnattr_setsigdefault(&guard.attributes,&guard.blocked),"task signal defaults");
  guard.check(::posix_spawnattr_setflags(&guard.attributes,POSIX_SPAWN_SETPGROUP|POSIX_SPAWN_SETSIGMASK|POSIX_SPAWN_SETSIGDEF),"task spawn flags");
#endif
  struct sigaction handler{};handler.sa_handler=interrupt;handler.sa_mask=guard.blocked;
  if(::sigaction(SIGINT,&handler,&guard.oldInt)!=0)throw Error("E_TASK_PROCESS","cannot install task interrupt handler");guard.intReady=true;
  if(::sigaction(SIGTERM,&handler,&guard.oldTerm)!=0)throw Error("E_TASK_PROCESS","cannot install task termination handler");guard.termReady=true;
  interruptedSignal=0;pid_t child=0;
#ifdef NEX_TASK_FORK_SPAWN
  auto outPath=out.string(),errPath=err.string();
  child=spawnWithDirectory(guard,executable->c_str(),directory.c_str(),outPath.c_str(),errPath.c_str(),args.data(),env.data());
#else
  guard.check(::posix_spawn(&child,executable->c_str(),&guard.files,&guard.attributes,args.data(),env.data()),"task spawn");
#endif
  guard.child=child;supervisedGroup=child;
  ::sigprocmask(SIG_SETMASK,&guard.oldMask,nullptr);
  auto deadline=std::chrono::steady_clock::now()+std::chrono::seconds(seconds);TaskProcessResult result{};
  for(;;){
    siginfo_t info{};
    if(::waitid(P_PID,guard.child,&info,WEXITED|WNOHANG|WNOWAIT)!=0){if(errno==EINTR)continue;throw Error("E_TASK_PROCESS","cannot observe task child");}
    if(info.si_pid==guard.child)break;
    if(std::chrono::steady_clock::now()>=deadline){result.timedOut=true;break;}
    if(size(out)>outputCap||size(err)>outputCap){result.outputLimit=true;break;}
    if(interruptedSignal)break;
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
  }
  // WNOWAIT keeps the leader PID reserved until its whole group is stopped;
  // the group ID cannot be recycled between observation and cleanup.
  ::sigprocmask(SIG_BLOCK,&guard.blocked,nullptr);::kill(-guard.child,SIGKILL);int status=0;
  while(::waitpid(guard.child,&status,0)<0){if(errno==EINTR)continue;throw Error("E_TASK_PROCESS","cannot reap task child");}
  guard.child=0;supervisedGroup=0;result.interrupted=interruptedSignal;
  result.process={WIFEXITED(status)?WEXITSTATUS(status):128+(WIFSIGNALED(status)?WTERMSIG(status):0),prefix(out),prefix(err)};
  result.outputLimit=result.outputLimit||size(out)>outputCap||size(err)>outputCap;
  for(const auto &path:{out,err})if(size(path)>outputCap)std::filesystem::resize_file(path,outputCap);
  return result;
#elif defined(_WIN32)
  return windows_process::run(arguments,directory,overrides,seconds,logs);
#else
  (void)arguments;(void)directory;(void)overrides;(void)seconds;(void)logs;
  throw Error("E_TASK_PLATFORM","task process supervision is not configured on this host");
#endif
}
}
