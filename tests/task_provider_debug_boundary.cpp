#include "nex/backend.h"
#include "nex/incremental.h"
#include "nex/task_ir.h"
#include <filesystem>
#include <functional>
#include <iostream>
using namespace nex;
namespace {
unsigned checks=0,rejections=0;
void require(bool yes,const char *message){++checks;if(!yes)throw std::runtime_error(message);}
void rejects(const std::function<void()> &body,const std::string &code="E_TASK_PROVIDER"){
 try{body();}catch(const Error &error){require(error.code==code,(error.code+": "+error.what()).c_str());++rejections;return;}
 throw std::runtime_error("invalid debugger provider boundary accepted");
}
}
int main(){std::filesystem::path temporary;try{
 auto p=parse("module boundary;pub fn work(x:i64)->i64!{task}{let retained:i64=x+1;task_yield();return retained;}fn main()->i64!{task}{return work(41);}","boundary.nex");check(p);
 auto name=p.function("work").name;const auto &function=p.function(name);auto plan=planNative(p,"main",{},true);std::map<std::string,std::string> contracts;
 for(const auto &u:plan.units){auto value=llvm::json::parse(u.contract);value->getAsObject()->erase("unit");contracts[u.identity]=hash(json(*value,false));}
 const std::string digest(64,'a'),file="/checked/leaf.nex";
 NativeTaskDebugCatalog catalog;catalog.mode=NativeTaskLinkageMode::Static;
 catalog.registries.push_back({"leaf",nativeTaskDebugRegistryAccessor("leaf"),{},{{name,hash(json(canonical(function),false)),hash(p.definition(function)),hash(p.source),file,contracts.at(name),taskDebugFunctionMetadata(p,function,file)}}});
 NativeTaskDebugSourceUnion sources;sources.mode=catalog.mode;
 NativeTaskDebugSourceComponent source;source.component="leaf";source.entry=name;source.language=programLanguage(p);source.revision=revision(p);source.sourceHash=hash(json(sourceBundle(p),false));source.bundleFile="debugger/components/leaf/source-bundle.json";source.bundleHash=hash(json(sourceBundle(p))+"\n");
 source.definitions.push_back({name,hash(json(canonical(function),false)),hash(p.definition(function)),hash(p.source),file,contracts.at(name),function.span.line,true});sources.components.push_back(source);
 auto info=nativeTaskDebugInfo(catalog,sources);require(info.registries[0].codeCount==1,"retained debugger range lost");
 auto original=nativeTaskDebugCatalogJSON(catalog);require(original.size()==7&&parseNativeTaskDebugCatalog(llvm::json::Value(llvm::json::Object(original))).registries.size()==1,"catalog7 roundtrip failed");
 auto bad=[&](const std::function<void(llvm::json::Object&)> &f){auto value=llvm::json::Object(original);f(value);rejects([&]{(void)parseNativeTaskDebugCatalog(llvm::json::Value(std::move(value)));});};
 bad([](auto &o){o["unknown"]=1;});bad([](auto &o){o.erase("catalog_abi");});bad([](auto &o){o["catalog_abi"]=1;});bad([](auto &o){o["registry_abi"]=2;});bad([](auto &o){o["mode"]="dlopen";});bad([](auto &o){o["owner_image"]="leaf";});
 auto code=[](auto &o)->llvm::json::Object&{return *(*(*o.getArray("registries"))[0].getAsObject()->getArray("codes"))[0].getAsObject();};
 bad([&](auto &o){code(o)["contract"]="bad";});bad([&](auto &o){code(o).getObject("task_debug")->operator[]("slot_count")=-1;});bad([&](auto &o){code(o).getObject("task_debug")->operator[]("extra")=0;});
 bad([&](auto &o){auto &points=*code(o).getObject("task_debug")->getArray("points");points[0].getAsObject()->operator[]("kind")=6;});
 bad([&](auto &o){auto &points=*code(o).getObject("task_debug")->getArray("points");points[0].getAsObject()->operator[]("visible")=llvm::json::Array{99999};});
 bad([&](auto &o){auto &codes=*(*o.getArray("registries"))[0].getAsObject()->getArray("codes");codes.push_back(llvm::json::Object(*codes[0].getAsObject()));});
 auto sourceJSON=nativeTaskDebugSourceUnionJSON(sources);require(sourceJSON.size()==5,"sourceunion5 shape changed");
 auto badSource=[&](const std::function<void(llvm::json::Object&)> &f){auto object=llvm::json::Object(sourceJSON);f(object);rejects([&]{(void)parseNativeTaskDebugSourceUnion(llvm::json::Value(std::move(object)));});};
 badSource([](auto &o){o.erase("components");});badSource([](auto &o){(*o.getArray("components"))[0].getAsObject()->operator[]("bundle_file")="../source-bundle.json";});badSource([](auto &o){(*o.getArray("components"))[0].getAsObject()->operator[]("bundle_hash")="bad";});
 auto mismatch=sources;mismatch.components[0].definitions[0].retained=false;rejects([&]{(void)nativeTaskDebugInfo(catalog,mismatch);});
 // Pure-only component facts carry no invented retained frame/code.
 auto empty=catalog;empty.registries[0].codes.clear();auto pure=sources;pure.components[0].definitions[0].retained=false;require(nativeTaskDebugInfo(empty,pure).registries[0].codeCount==0,"zero retained range was rejected");
 NativeTaskProviderInfo provider;provider.enabled=true;provider.codeOnly=true;provider.component="leaf";provider.language="0.20";provider.cohort=digest;provider.definitions={name};provider.exports[name]=nativeTaskExportInterface(p,name,contracts.at(name));provider.debugging=info;
 auto record=nativeTaskProviderJSON(provider);require(record.size()==14&&record.getString("schema")=="nex.native-task-provider/4","static debugger provider4 shape differs");require(parseNativeTaskProvider(llvm::json::Value(llvm::json::Object(record))).debugging->catalogHash==info.catalogHash,"debugger pins lost");
 auto badProvider=[&](const std::function<void(llvm::json::Object&)> &f){auto value=llvm::json::Object(record);f(value);rejects([&]{(void)parseNativeTaskProvider(llvm::json::Value(std::move(value)));});};
 badProvider([](auto &o){o.erase("debugging");});badProvider([](auto &o){o["profiling"]=llvm::json::Object{};});badProvider([](auto &o){(*o.getObject("debugging"))["registry_abi"]=2;});badProvider([](auto &o){(*o.getObject("debugging"))["catalog_file"]="../bad";});badProvider([](auto &o){auto &row=*(*o.getObject("debugging")->getArray("registries"))[0].getAsObject();row["code_count"]=2;});
 provider.mode=NativeTaskLinkageMode::SharedFixed;provider.artifact=NativeTaskArtifactKind::PicStage;provider.definitionOwners[name]="leaf";provider.componentFileReads["leaf"]=false;require(nativeTaskProviderJSON(provider).size()==19,"shared debugger provider4 shape differs");(void)parseNativeTaskProvider(llvm::json::Value(nativeTaskProviderJSON(provider)));++checks;
 auto item=[](const char *kind,const std::string &path){return llvm::json::Object{{"kind",kind},{"path",path}};};
 llvm::json::Array inputs{item("abi","library-abi.json"),item("task_provider","task-provider.json"),item("debug_catalog","task-debug-catalog.json"),item("debug_sources","task-debug-sources.json"),item("debug_source_bundle","debugger/components/leaf/source-bundle.json"),item("debug_source_projection","debugger/source-cache/"+digest+"/source.nex"),item("debug_manifest","debug.json"),item("debug_formatter","debugger/lldb_nex.py"),item("debug_adapter","debugger/nex_dap.py")};
 llvm::json::Object completion{{"completion_schema","nex.native-completion/7"},{"completion_mode","static-application"},{"completion_inputs",llvm::json::Array(inputs)}};require(nativeCompletionInputs(completion).size()==9,"debugger7 completion rejected");
 auto broken=llvm::json::Object(completion);broken.getArray("completion_inputs")->pop_back();rejects([&]{(void)nativeCompletionInputs(broken);},"E_CORE_BUILD");broken=llvm::json::Object(completion);(*broken.getArray("completion_inputs"))[5]=item("debug_source_projection","../bad");rejects([&]{(void)nativeCompletionInputs(broken);},"E_CORE_BUILD");
 auto darwin=llvm::json::Object(completion);darwin["compiler_target"]="arm64-apple-macosx13.0";
 rejects([&]{(void)nativeCompletionInputs(darwin);},"E_CORE_BUILD");
 for(const auto &path:{"debug-symbols.complete","app.dSYM/Contents/Info.plist","app.dSYM/Contents/Resources/DWARF/app"})darwin.getArray("completion_inputs")->push_back(item("root_symbols",path));
 require(nativeCompletionInputs(darwin).size()==12,"Darwin root debug symbols were not retained");
 broken=llvm::json::Object(darwin);broken.getArray("completion_inputs")->pop_back();rejects([&]{(void)nativeCompletionInputs(broken);},"E_CORE_BUILD");
 broken=llvm::json::Object(darwin);(*broken.getArray("completion_inputs"))[11]=item("root_symbols","../app");rejects([&]{(void)nativeCompletionInputs(broken);},"E_CORE_BUILD");
 broken=llvm::json::Object(darwin);broken["completion_mode"]="static-archive";rejects([&]{(void)nativeCompletionInputs(broken);},"E_CORE_BUILD");
 temporary=createTemporaryDirectory("nex-task-debug-boundary");auto archive=temporary/"leaf.a",sidecar=temporary/"task-provider.json";writeFile(archive.string(),"!<arch>\n");
 BuildOptions options;options.projectLibraryABI=true;options.staticTaskABI=true;options.taskComponent="app";options.toolchain=(temporary/"MUST_NOT_READ_TOOLCHAIN.json").string();options.taskDebug=true;validateNativeBuildEntry(p,options);++checks;
 provider.mode=NativeTaskLinkageMode::Static;provider.artifact=NativeTaskArtifactKind::CodeArchive;provider.definitionOwners.clear();provider.componentFileReads.clear();
 auto preflight=[&](bool debugger,bool profile){provider.debugging=debugger?std::optional(info):std::nullopt;provider.profiling.reset();if(profile){NativeTaskProfileCatalog c;c.mode=NativeTaskLinkageMode::Static;c.registries.push_back({"leaf",nativeTaskProfileRegistryAccessor("leaf"),{},{{name,digest,digest,digest,file,contracts.at(name),1}}});provider.profiling=nativeTaskProfileInfo(c);}writeFile(sidecar.string(),json(nativeTaskProviderJSON(provider)));options.libraries={{archive.string(),hash(readFile(archive.string())),digest,{{name,contracts.at(name)}},false,sidecar.string(),hash(readFile(sidecar.string()))}};rejects([&]{(void)build(p,(temporary/"artifacts").string(),options);});require(!std::filesystem::exists(temporary/"artifacts"),"invalid preflight created cache");};
 preflight(false,false);preflight(false,true);options.taskDebug=false;preflight(true,false);
 std::filesystem::remove_all(temporary);temporary.clear();
 std::cout<<json(llvm::json::Object{{"ok",true},{"checks",checks},{"rejections",rejections},{"catalog_abi",2},{"registry_abi",1},{"execution_abi",3},{"native_tools_executed",false}})<<'\n';return 0;
 }catch(const std::exception &e){if(!temporary.empty())std::filesystem::remove_all(temporary);std::cerr<<e.what()<<'\n';return 1;}}
