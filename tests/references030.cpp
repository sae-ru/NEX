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
  if(mode=="build"){
    BuildOptions options;options.entry=selected;options.profile=argc>4?argv[4]:"debug";
    auto built=build(p,output.string(),options);
    std::cout<<json(llvm::json::Object{{"ok",true},{"artifact",built.executable},{"key",built.key},{"library_abi",built.libraryABI},{"language",programLanguage(p)},{"revision",rev}},false)<<'\n';return 0;
  }
  if(mode=="mlir") {writeFile(output.string(),emitMLIR(p,selected));return 0;}
  if(mode=="wasm") {writeFile(output.string(),emitWasmMLIR(p,selected,false));return 0;}
  throw Error("E_OPTION","unknown source030 probe mode");
}catch(const Error &e){std::cerr<<e.code<<": "<<e.message<<'\n';return 1;}
catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 2;}}
