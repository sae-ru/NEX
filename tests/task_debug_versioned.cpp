#include "nex/backend.h"
#include "nex/task_frontend.h"
#include "nex/task_ir.h"
#include <filesystem>
#include <iostream>

// This builder consumes an archived, SDK-produced language019 bundle.  It never
// rewrites its language or source and does not widen public CLI selection.
int main(int argc,char **argv){try{
  if(argc!=3)throw nex::Error("E_OPTION","versioned task debug probe requires genuine019 fixture and output directory");
  auto parsed=llvm::json::parse(nex::readFile(argv[1]));auto fixture=parsed?parsed->getAsObject():nullptr;
  auto sdk=fixture?fixture->getObject("sdk"):nullptr;
  if(!fixture||fixture->getString("schema")!="nex.language-019-migration-fixture/1"||fixture->getString("language")!="0.19"||
     !sdk||sdk->getString("toolchain")!="0.108.0"||sdk->getBoolean("acceptance_ok")!=true)
    throw nex::Error("E_OPTION","requires genuine accepted SDK115019 fixture");
  auto rows=fixture->getArray("revisions");if(!rows||rows->empty())throw nex::Error("E_OPTION","fixture omitted retained revisions");
  auto row=rows->back().getAsObject();auto bundle=row?row->get("bundle"):nullptr;auto expected=row?row->getString("revision"):std::nullopt;
  if(!bundle||!expected||row->getString("language")!="0.19")throw nex::Error("E_OPTION","fixture omitted genuine019 bundle/revision");
  auto root=std::filesystem::absolute(argv[2]);std::filesystem::create_directories(root);
  auto before=nex::json(*bundle,false);auto program=nex::loadVersionedBundle(*bundle,root.string(),"0.19");
  if(nex::revision(program)!=expected||std::string(nex::programLanguage(program))!="0.19"||nex::json(nex::sourceBundle(program),false)!=before)
    throw nex::Error("E_REVISION","genuine019 source or checked revision changed");
  nex::BuildOptions options;options.profile="debug";options.taskDebug=true;options.taskLimits.timeoutMs=60000;options.taskLimits.workers=2;
  auto built=nex::build(program,(root/"build").string(),options);
  auto manifestPath=std::filesystem::path(built.executable).parent_path()/"debug.json";
  auto manifestValue=llvm::json::parse(nex::readFile(manifestPath.string()));auto manifest=manifestValue?manifestValue->getAsObject():nullptr;
  if(!manifest||manifest->getString("schema")!="nex.debug/2"||manifest->getString("language")!="0.19"||manifest->getString("revision")!=expected)
    throw nex::Error("E_DEBUG_METADATA","debug manifest lost genuine019 provenance");
  auto functions=manifest->getArray("functions");if(!functions)throw nex::Error("E_DEBUG_METADATA","missing function metadata");
  unsigned checked=0;
  for(const auto &value:*functions){auto f=value.getAsObject();auto metadata=f?f->getObject("task_debug"):nullptr;auto name=f?f->getString("name"):std::nullopt;
    if(!metadata||!name)throw nex::Error("E_DEBUG_METADATA","missing task debug function");
    auto file=metadata->getString("file");if(!file)throw nex::Error("E_DEBUG_METADATA","missing frozen source identity");
    auto actual=nex::taskDebugFunctionMetadata(program,program.function(name->str()),file->str());auto emitted=*metadata;emitted.erase("site_id");
    if(nex::json(llvm::json::Value(std::move(actual)),false)!=nex::json(llvm::json::Value(std::move(emitted)),false))
      throw nex::Error("E_DEBUG_METADATA","genuine019 logical visibility failed checked source rederivation");
    ++checked;
  }
  if(!checked||nex::revision(program)!=expected||std::string(nex::programLanguage(program))!="0.19")throw nex::Error("E_REVISION","debug build altered019 identity");
  std::cout<<nex::json(llvm::json::Object{{"ok",true},{"schema","nex.private-task-debug-versioned/1"},{"language","0.19"},
    {"genuine019",true},{"source_unchanged",true},{"revision",nex::revision(program)},{"checked_functions",checked},
    {"executable",built.executable},{"debug_manifest",manifestPath.string()},{"metadata",(manifestPath.parent_path()/"build.json").string()},
    {"mlir",built.mlir},{"llvm",built.llvm},{"cached",built.cached},{"live_debugger_claim",false}})<<'\n';return 0;
}catch(const nex::Error &error){std::cout<<nex::json(llvm::json::Object{{"ok",false},{"code",error.code},{"message",error.what()}})<<'\n';return 1;}
catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 2;}}
