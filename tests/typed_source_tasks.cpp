#include "nex/backend.h"
#include "nex/task_native.h"
#include "nex/task_frontend.h"
#include "nex/task_reference.h"
#include "nex/task_lifetime.h"
#include "nex/web.h"
#include "nex_source_error.h"
#include "nex_task_protocol.h"
#include "nex_foreign.h"
#include "nex_files.h"
#include "nex_host.h"
#include <filesystem>
#include <iostream>
using namespace nex;
static_assert(int(TaskInstruction::RethrowPendingSource)==18&&int(TaskInstruction::RaiseTyped)==19&&int(TaskInstruction::SourceBind)==21);
int main(int argc,char **argv){try{
  if(argc<3)throw std::runtime_error("expected ast/ir/check/typescript/emit source [output triple layout optimized]");
  auto path=std::filesystem::absolute(argv[2]);auto p=parseVersioned(readFile(path.string()),path.string(),SourceLanguage::TypedErrors027);check(p);
  std::string entry="main";for(const auto &f:p.functions)if(f.localName=="main"||f.name=="main"){entry=f.name;break;}
  std::string mode=argv[1];if(mode=="check"){analyzeTaskLifetimes(p,entry);return 0;}
  if(mode=="signatures"){
    llvm::json::Object signatures;for(const auto &f:p.functions)if(f.foreign)signatures[f.foreign->symbol]=foreignSignature(p,f);
    std::cout<<json(std::move(signatures))<<'\n';return 0;
  }
  if(mode=="lifetime"){
    const auto r=analyzeTaskLifetimes(p,entry);
    std::cout<<json(llvm::json::Object{{"steps",r.steps},{"widenings",r.widenings},{"dynamic",r.dynamic},{"exceptional_edges",r.exceptionalEdges}})<<'\n';return 0;
  }
  if(mode=="ast"||mode=="ir"){
    const auto baseline=nexrt::liveObjects.load();llvm::json::Object result;std::shared_ptr<nexrt::ForeignLibraries> libraries;
    {
      nexrt::RequestScope request(1000000,30000);nexrt::FileScope files(true);std::unique_ptr<nexrt::ForeignScope> foreign;
      if(const auto *catalog=std::getenv("NEX_TYPED_HOST_CATALOG");catalog&&*catalog){libraries=nexrt::loadForeignLibraries(catalog);foreign=std::make_unique<nexrt::ForeignScope>(libraries);}
      try{auto value=mode=="ast"?evaluateTaskReference(p,entry):evaluateTaskIRReference(p,entry);
        if(value.external.pending||value.external.reservedBytes)throw Error("E_TEST","reference retained external work");
        result=llvm::json::Object{{"kind","return"},{"value",p.function(entry).result==Type::Unit?llvm::json::Value(nullptr):llvm::json::Value(value.value.scalar)},{"output",value.output}};
      }catch(const SourceException &e){result=llvm::json::Object{{"kind","exception"},{"code",e.code},{"message",e.message},{"line",int64_t(e.span.line)},{"column",int64_t(e.span.column)},{"output",e.output},{"typed",bool(e.payload)}};}
      catch(const Error &e){result=llvm::json::Object{{"kind","trap"},{"code",e.code}};}
    }
    if(nexrt::liveObjects.load()!=baseline||(libraries&&libraries->resourceBytesUsed()))throw Error("E_TEST","reference retained managed values or physical resource capacity");
    std::cout<<json(std::move(result))<<'\n';return 0;
  }
  if(mode=="typescript"&&argc==4){writeWebModule(emitTypeScript(p,{{"main",entry}}),argv[3]);return 0;}
  if(mode=="emit"&&argc==7){auto out=std::filesystem::absolute(argv[3]);std::filesystem::create_directories(out);
    auto module=emitTypedErrorTasksDevelopmentNative(p,entry,std::string(argv[6])=="true");
    if(module.descriptorABI!=nexrt::taskCodeTypedAuthorityDevelopmentABI)throw Error("E_TEST","typed tasks aliased a published/legacy ABI");
    writeFile((out/"program.mlir").string(),module.mlir);
    writeFile((out/"program.ll").string(),lowerMLIRToLLVM(module.mlir,path.string(),argv[4],argv[5]));
    writeFile((out/"descriptor.json").string(),json(llvm::json::Object{{"abi",module.descriptorABI},{"symbol",module.descriptorSymbol}}));return 0;
  }
  throw std::runtime_error("invalid mode/argument count");
}catch(const Error &e){std::cerr<<e.code<<": "<<e.what()<<" at "<<e.span.line<<'\n';}
catch(const std::exception &e){std::cerr<<e.what()<<'\n';}return 1;}
