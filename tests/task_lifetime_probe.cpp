#include "nex/task_frontend.h"
#include "nex/task_lifetime.h"
#include <filesystem>
#include <iostream>

int main(int argc,char **argv)try{
  using namespace nex;
  if(argc<2||argc>4)throw Error("E_OPTION","expected source, optional entry and optional analysis budget");
  auto path=std::filesystem::absolute(argv[1]);
  auto p=loadTaskPrototype(path.string(),path.parent_path().string());
  uint64_t budget=262144;
  if(argc>=4){
    std::string text=argv[3];
    if(text.empty()||text.size()>7||text.find_first_not_of("0123456789")!=std::string::npos)
      throw Error("E_OPTION","analysis budget requires a decimal integer");
    budget=std::stoull(text);
  }
  auto r=analyzeTaskLifetimes(p,argc>=3?argv[2]:"",budget);
  std::cout<<json(llvm::json::Object{{"ok",true},{"schema","nex.private-task-lifetime/1"},
    {"public_source_tasks",false},{"fully_static",false},{"mandatory_runtime_guards",true},
    {"functions",int64_t(r.functions)},{"regions",int64_t(r.regions)},
    {"transfers",int64_t(r.transfers)},{"proved",int64_t(r.proved)},{"dynamic",int64_t(r.dynamic)},
    {"opaque_calls",int64_t(r.opaqueCalls)},{"widenings",int64_t(r.widenings)},{"steps",int64_t(r.steps)}})<<'\n';
  return 0;
}catch(const nex::Error &error){
  std::cout<<nex::json(llvm::json::Object{{"ok",false},{"code",error.code},{"message",error.what()},
    {"file",error.span.file},{"line",int64_t(error.span.line)},{"column",int64_t(error.span.column)}})<<'\n';return 1;
}catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 2;}
