#include "nex/backend.h"
#include "nex/task_frontend.h"
#include <filesystem>
#include <iostream>

int main(int argc,char **argv){try{
  if(argc!=3)throw nex::Error("E_OPTION","private task debug build requires SOURCE OUTPUT_DIRECTORY");
  auto source=std::filesystem::absolute(argv[1]);
  auto program=nex::loadProgram(source.string(),source.parent_path().string(),false);
  if(!nex::usesTaskEffects(program,"main"))throw nex::Error("E_OPTION","private task debug build requires a task entry");
  nex::BuildOptions options;options.profile="debug";options.taskDebug=true;
  options.taskLimits.timeoutMs=60000;options.taskLimits.workers=2;
  auto built=nex::build(program,std::filesystem::absolute(argv[2]).string(),options);
  std::cout<<nex::json(llvm::json::Object{{"ok",true},{"schema","nex.private-task-debug-build/1"},
    {"executable",built.executable},{"debug_manifest",(std::filesystem::path(built.executable).parent_path()/"debug.json").string()},
    {"metadata",(std::filesystem::path(built.executable).parent_path()/"build.json").string()},
    {"mlir",built.mlir},{"llvm",built.llvm},{"build_key",built.key},{"revision",nex::revision(program)},
    {"language",nex::programLanguage(program)},{"cached",built.cached}})<<'\n';return 0;
}catch(const nex::Error &error){std::cout<<nex::json(llvm::json::Object{{"ok",false},{"code",error.code},{"message",error.what()}})<<'\n';return 1;}
catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 2;}}
