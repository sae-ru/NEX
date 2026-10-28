#include "nex/task_typescript.h"
#include "nex/task_frontend.h"
#include <filesystem>
#include <iostream>
int main(int argc,char **argv)try{
  using namespace nex;
  if(argc!=4)throw Error("E_OPTION","expected source, output directory and entry");
  auto source=std::filesystem::absolute(argv[1]),directory=std::filesystem::absolute(argv[2]);
  if(std::filesystem::exists(directory))throw Error("E_OPTION","private output directory must be new");
  auto p=loadTaskPrototype(source.string(),source.parent_path().string());
  auto module=emitTaskTypeScript(p,{{"entry",argv[3]}});
  std::filesystem::create_directories(directory);writeTaskTypeScriptModule(module,directory.string());
  std::cout<<json(llvm::json::Object{{"ok",true},{"public_source_tasks",false},{"schema","nex.private-typescript-task-map/1"},{"directory",directory.string()}})<<'\n';return 0;
}catch(const nex::Error &e){std::cout<<nex::json(llvm::json::Object{{"ok",false},{"code",e.code},{"message",e.what()},{"line",int64_t(e.span.line)}})<<'\n';return 1;}
catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 2;}
