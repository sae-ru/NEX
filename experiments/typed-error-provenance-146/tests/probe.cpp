#include "nex/language.h"
#include "nex/task_lifetime.h"
#include "nex/task_reference.h"
#include <filesystem>
#include <iostream>
namespace nex {extern bool draft146SkipLifetime;}
using namespace nex;
int main(int argc,char **argv){try{
  if(argc!=2&&argc!=3)throw Error("E_OPTION","expected source file [ast|ir]");
  draft146SkipLifetime=argc==3;
  auto file=std::filesystem::absolute(argv[1]);auto p=parseVersioned(readFile(file.string()),file.string(),SourceLanguage::TypedErrors027);check(p);
  if(argc==3){
    const auto before=nexrt::liveObjects.load();llvm::json::Object result;
    {
      try{auto value=std::string(argv[2])=="ir"?evaluateTaskIRReference(p,"main"):evaluateTaskReference(p,"main");
        if(value.external.pending||value.external.reservedBytes)throw Error("E_TEST","draft reference retained external work");
        result=llvm::json::Object{{"kind","return"},{"value",p.function("main").result==Type::Unit?llvm::json::Value(nullptr):llvm::json::Value(value.value.scalar)},{"output",value.output}};
      }catch(const SourceException &e){result=llvm::json::Object{{"kind","exception"},{"code",e.code},{"message",e.message},{"output",e.output},{"typed",bool(e.payload)}};}
      catch(const Error &e){result=llvm::json::Object{{"kind","trap"},{"code",e.code},{"message",std::string(e.what())},{"line",int64_t(e.span.line)}};}
    }
    if(nexrt::liveObjects.load()!=before)throw Error("E_TEST","draft reference retained a managed value");
    std::cout<<json(std::move(result))<<'\n';return 0;
  }
  auto r=analyzeTaskLifetimes(p,"main");
  std::cout<<json(llvm::json::Object{{"ok",true},{"scope","isolated146 static provenance only"},{"public027_enabled",false},{"authority_execution_enabled",false},{"regions",int64_t(r.regions)},{"transfers",int64_t(r.transfers)},{"proved",int64_t(r.proved)},{"dynamic",int64_t(r.dynamic)},{"widenings",int64_t(r.widenings)},{"exceptional_edges",int64_t(r.exceptionalEdges)},{"steps",int64_t(r.steps)}})<<'\n';return 0;
}catch(const Error &e){std::cout<<json(llvm::json::Object{{"ok",false},{"code",e.code},{"message",std::string(e.what())},{"line",int64_t(e.span.line)}})<<'\n';return 1;}
catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 2;}}
