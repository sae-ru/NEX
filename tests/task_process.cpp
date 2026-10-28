#include "nex/task_process.h"
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <functional>
#include <iostream>
#include <signal.h>
#include <sys/stat.h>
#include <unistd.h>

namespace {
namespace fs=std::filesystem;
void require(bool condition,const char *message){if(!condition)throw std::runtime_error(message);}
void rejects(const std::function<void()> &body){
  try{body();}catch(const nex::Error &error){require(error.code=="E_TASK_PROCESS","unexpected supervisor diagnostic");return;}
  throw std::runtime_error("expected task launch failure");
}
struct Temporary {
  fs::path path;
  Temporary(){auto name=(fs::temp_directory_path()/"nex-process-XXXXXX").string();require(::mkdtemp(name.data())!=nullptr,"temporary directory");path=name;}
  ~Temporary(){std::error_code ignored;fs::remove_all(path,ignored);}
};
struct SavedStdio {
  int saved[3];
  SavedStdio(){for(int i=0;i<3;++i){saved[i]=::dup(i);require(saved[i]>=3,"save stdio");}for(int i=0;i<3;++i)::close(i);}
  ~SavedStdio(){for(int i=0;i<3;++i){::dup2(saved[i],i);::close(saved[i]);}}
};
}
int main(int argc,char **argv)try{
  if(argc>1){
    std::string mode=argv[1];
    if(mode=="inspect"){
      char byte;require(::read(0,&byte,1)==0,"child stdin must be EOF");
      const char *value=std::getenv("NEX_PROCESS_PROBE_VALUE");
      std::cout<<fs::current_path().string()<<'\n'<<(value?value:"missing")<<'\n'<<argv[2]<<'\n';std::cerr<<"child stderr\n";return 0;
    }
    if(mode=="exit127")return 127;
    if(mode=="sleep"){std::cout<<::getpid()<<' '<<::getpgrp()<<std::endl;for(;;)::pause();}
    if(mode=="flood"){std::cout<<std::string(9*1024*1024,'x');return 0;}
    throw std::runtime_error("unknown child mode");
  }
  Temporary temporary;auto work=temporary.path/"cwd space λ";fs::create_directory(work);work=fs::canonical(work);
  auto self=fs::canonical(argv[0]).string();auto original=fs::current_path();unsigned cases=0,sequence=0;
  auto run=[&](std::vector<std::string> args,unsigned timeout=5,const fs::path &cwd=fs::path{}){
    return nex::runTaskProcess(args,(cwd.empty()?work:cwd).string(),{{"NEX_PROCESS_PROBE_VALUE","literal value"}},timeout,(temporary.path/("logs-"+std::to_string(sequence++))).string());
  };
  const std::string literal="$(not-a-command) `literal` ; * \" λ";
  auto result=run({self,"inspect",literal});
  require(result.process.code==0&&result.process.output==work.string()+"\nliteral value\n"+literal+"\n"&&result.process.errors=="child stderr\n","cwd/argv/environment/output");
  require(fs::current_path()==original&&!result.timedOut&&!result.outputLimit&&!result.interrupted,"parent cwd/status");++cases;
  result=run({self,"exit127"});require(result.process.code==127&&!result.timedOut,"real exit127 is not a launch failure");++cases;
  rejects([&]{run({self,"inspect",literal},5,temporary.path/"missing");});
  auto invalid=temporary.path/"invalid executable";{std::ofstream file(invalid);file<<"not an executable\n";}require(::chmod(invalid.c_str(),0700)==0,"invalid executable mode");
  rejects([&]{run({invalid.string()});});
  require(fs::current_path()==original,"failed launch changed parent cwd");++cases;
  {SavedStdio saved;result=run({self,"inspect",literal});}
  require(result.process.code==0&&result.process.output==work.string()+"\nliteral value\n"+literal+"\n","closed parent stdio");++cases;
  result=run({self,"sleep"},1);
  require(result.timedOut&&!result.interrupted&&result.process.code==128+SIGKILL,"timeout must kill the child group");
  auto separator=result.process.output.find(' ');require(separator!=std::string::npos,"child process group report");
  auto pid=std::stol(result.process.output.substr(0,separator)),group=std::stol(result.process.output.substr(separator+1));
  require(pid==group&&group!=::getpgrp(),"child must own a distinct process group");++cases;
  result=run({self,"flood"});require(result.outputLimit&&result.process.output.size()==8*1024*1024,"bounded output retention");++cases;
  result=run({self,"inspect",literal});require(result.process.code==0,"supervisor must recover after failures and limits");++cases;
  std::cout<<"task process cases: "<<cases<<'\n';return 0;
}catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 1;}
