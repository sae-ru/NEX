#include "nex/language.h"
#include "nex/web.h"
#include "nex_source_error.h"
#include <filesystem>
#include <iostream>
using namespace nex;
int main(int argc,char **argv){try{
  if(argc<3)throw std::runtime_error("expected mode source [output]");
  auto file=std::filesystem::absolute(argv[2]);std::string mode=argv[1];bool project=mode.starts_with("project-");
  auto p=project?loadVersionedProgram(file.string(),file.parent_path().string(),SourceLanguage::TypedErrors027)
      :parseVersioned(readFile(file.string()),file.string(),SourceLanguage::TypedErrors027);
  if(!project)check(p);
  std::string entry;
  for(const auto &f:p.functions)if(f.name=="main"||f.localName=="main"){entry=f.name;break;}
  if(entry.empty())throw Error("E_ENTRY","missing main");
  if(mode=="reference"||mode=="project-reference"){
    try{auto result=evaluate(p,entry);std::cout<<json(llvm::json::Object{{"kind","return"},{"value",std::move(result.value)},{"output",result.output}})<<'\n';}
    catch(const SourceException &e){llvm::json::Value key=e.payload?llvm::json::Value(e.payload->typeKey):llvm::json::Value(nullptr);
      std::cout<<json(llvm::json::Object{{"kind","exception"},{"code",e.code},{"message",e.message},{"file",e.span.file},{"line",int64_t(e.span.line)},{"column",int64_t(e.span.column)},{"payload_type_key",std::move(key)},{"output",e.output}})<<'\n';}
    catch(const Error &e){std::cout<<json(llvm::json::Object{{"kind","trap"},{"code",e.code},{"line",int64_t(e.span.line)},{"column",int64_t(e.span.column)},{"output",e.output}})<<'\n';}
    return 0;
  }
  if((mode=="typescript"||mode=="project-typescript")&&argc==4){writeWebModule(emitTypeScript(p,{{"main",entry}}),argv[3]);return 0;}
  throw std::runtime_error("unknown mode");
}catch(const Error &e){std::cerr<<e.code<<": "<<e.what()<<'\n';return 1;}
catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 1;}}
