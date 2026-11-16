#include "nex/managed_references.h"
#include "nex/backend.h"
#include "nex/web.h"
#include "nex/metal.h"
#include "nex/cuda.h"
#include "nex/opencl.h"
#include "nex_value.h"
#include <filesystem>
#include <iostream>

using namespace nex;
namespace fs=std::filesystem;
namespace {
Program load(const fs::path &path){
  llvm::json::Value bundle=nullptr;
  if(path.extension()==".json"){
    auto parsed=llvm::json::parse(readFile(path.string()));if(!parsed)throw Error("E_BUNDLE","invalid sources JSON");bundle=std::move(*parsed);
  }else bundle=llvm::json::Object{{"schema","nex.sources/1"},{"entry","main.nex"},{"files",llvm::json::Object{{"main.nex",readFile(path.string())}}}};
  return loadVersionedBundle(bundle,path.parent_path().string(),"0.30");
}
std::string entry(const Program &p){return p.function("main").name;}
}
int main(int argc,char **argv){try{
  if(argc<3)throw Error("E_OPTION","expected mode input [output [profile]]");
  auto path=fs::absolute(argv[2]);auto p=load(path);const std::string mode=argv[1];
  const auto selected=entry(p),rev=revision(p);
  if(mode=="reference"){
    const auto before=nexrt::liveObjects.load();llvm::json::Object result;
    try{auto value=evaluate(p,selected,4000000);result=llvm::json::Object{{"kind","return"},{"value",std::move(value.value)},{"output",value.output}};}
    catch(const Error &e){result=llvm::json::Object{{"kind","trap"},{"code",e.code},{"message",e.message},{"output",e.output},{"file",e.span.file},{"line",int64_t(e.span.line)}};}
    catch(const SourceException &e){result=llvm::json::Object{{"kind","trap"},{"code","E_SOURCE_EXCEPTION"},{"message",e.code+": "+e.message},{"output",e.output},{"file",e.span.file},{"line",int64_t(e.span.line)}};}
    result["live_delta"]=nexrt::liveObjects.load()-before;result["language"]=programLanguage(p);result["revision"]=rev;
    std::cout<<json(std::move(result),false)<<'\n';return 0;
  }
  if(mode=="inspect"){
    auto bundle=sourceBundle(p);auto reread=loadVersionedBundle(bundle,path.parent_path().string(),"0.30");
    if(revision(reread)!=rev)throw Error("E_TEST","source030 bundle changed its revision");
    std::cout<<json(llvm::json::Object{{"ok",true},{"language",programLanguage(p)},{"revision",rev},{"source_hash",hash(json(bundle,false))},{"sources",std::move(bundle)},{"references",usesManagedReferences(p,{selected})},{"task_language",p.taskPrototype}},false)<<'\n';return 0;
  }
  if(argc<4)throw Error("E_OPTION","output is required");auto output=fs::absolute(argv[3]);
  if(mode=="typescript"){
    writeWebModule(emitTypeScriptDelivery(p,{{"main",selected}}),output.string());return 0;
  }
  if(mode=="entry-test"){
    auto result=runTypeScriptTest(emitTypeScriptDelivery(p,{{"entry",selected}}),output.string());
    std::cout<<json(llvm::json::Object{{"ok",result.code==0},{"code",result.code},{"stdout",result.output},{"stderr",result.errors}},false)<<'\n';return result.code?1:0;
  }
  if(mode=="scalar-devices"){
    auto metal=emitMetal(p,selected);auto opencl=emitOpenCL(p,selected);
    auto cuda=emitCuda(p,selected,"rows");
    if(metal.resultType!="i64"||opencl.resultType!="i64"||cuda.resultType!="i64"||metal.parameterTypes!=std::vector<std::string>{"i64"}||opencl.parameterTypes!=metal.parameterTypes||cuda.parameterTypes!=metal.parameterTypes)throw Error("E_TEST","inherited030 scalar device contract changed");
    writeFile((output/"program.metal").string(),metal.source);writeFile((output/"program.cu").string(),cuda.source);writeFile((output/"program.cl").string(),opencl.source);
    writeFile((output/"program-wasm.mlir").string(),emitWasmMLIR(p,selected,false));
    std::cout<<json(llvm::json::Object{{"ok",true},{"language",programLanguage(p)},{"revision",rev},{"metal",hash(metal.source)},{"cuda",hash(cuda.source)},{"opencl",hash(opencl.source)}},false)<<'\n';return 0;
  }
  if(mode=="build"||mode=="library"||mode=="library-app"||mode=="library-embedded"||mode=="server"||mode=="server-library"){
    BuildOptions options;options.entry=selected;options.profile=argc>4?argv[4]:"debug";
    if(mode=="server"||mode=="server-library"){
      options.entry=p.function("handle").name;options.target="server";
      if(mode=="server-library"){options.positionIndependent=true;options.projectLibraryABI=true;}
    }
    if(mode=="library"||mode=="library-embedded"){
      if(argc!=6)throw Error("E_OPTION","library mode requires an export specification JSON");
      auto spec=llvm::json::parse(argv[5]);if(!spec||!spec->getAsObject())throw Error("E_OPTION","invalid library export specification");
      auto object=spec->getAsObject();auto named=object->getString("entry");auto exports=object->getArray("exports");
      if(!named||!exports)throw Error("E_OPTION","library specification needs entry/exports");
      options.entry=p.function(named->str()).name;options.libraryEntry=true;options.codeOnlyLibrary=mode=="library";options.positionIndependent=true;options.projectLibraryABI=true;
      for(const auto &value:*exports){auto name=value.getAsString();if(!name)throw Error("E_OPTION","export must name a source function");options.libraryExports.push_back(p.function(name->str()).name);}
    }
    if(mode=="library-app"||mode=="server-library"){
      if(argc!=6)throw Error("E_OPTION","library-app requires a dependency specification JSON");
      auto spec=llvm::json::parse(argv[5]);if(!spec||!spec->getAsObject())throw Error("E_OPTION","invalid dependency specification");
      auto object=spec->getAsObject();auto named=object->getString("entry");auto libraries=object->getArray("libraries");
      if(!named||!libraries)throw Error("E_OPTION","dependency specification needs entry/libraries");
      options.entry=p.function(named->str()).name;options.positionIndependent=true;options.projectLibraryABI=true;
      for(const auto &value:*libraries){
        auto library=value.getAsObject();if(!library)throw Error("E_OPTION","invalid library");
        auto path=library->getString("artifact"),digest=library->getString("artifact_hash"),abi=library->getString("library_abi");
        auto contracts=library->getObject("function_contracts");if(!path||!digest||!abi||!contracts)throw Error("E_OPTION","incomplete library");
        NativeLibraryInput input;input.path=path->str();input.digest=digest->str();input.abi=abi->str();
        for(const auto &field:*contracts){auto text=field.second.getAsString();if(!text)throw Error("E_OPTION","invalid function contract");input.contracts[field.first.str()]=text->str();}
        options.libraries.push_back(std::move(input));
      }
    }
    auto built=build(p,output.string(),options);
    llvm::json::Value abi=nullptr;if(!built.nativeEntryABI.empty()){auto parsed=llvm::json::parse(built.nativeEntryABI);if(!parsed)throw Error("E_TEST","invalid native entry ABI");abi=std::move(*parsed);}
    llvm::json::Object contracts;for(const auto &[name,digest]:built.functionContracts)contracts[name]=digest;
    std::cout<<json(llvm::json::Object{{"ok",true},{"artifact",built.executable},{"artifact_hash",hash(readFile(built.executable))},{"function_contracts",std::move(contracts)},{"key",built.key},{"cached",built.cached},{"native_entry_abi",std::move(abi)},{"library_abi",built.libraryABI},{"language",programLanguage(p)},{"revision",rev}},false)<<'\n';return 0;
  }
  if(mode=="mlir") {writeFile(output.string(),emitMLIR(p,selected));return 0;}
  if(mode=="wasm") {writeFile(output.string(),emitWasmMLIR(p,selected,false));return 0;}
  throw Error("E_OPTION","unknown source030 probe mode");
}catch(const Error &e){std::cerr<<e.code<<": "<<e.message<<'\n';return 1;}
catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 2;}}
