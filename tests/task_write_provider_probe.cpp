#include "nex/backend.h"
#include "nex/native_images.h"
#include "nex/task_reference.h"
#include "nex_task_protocol.h"
#include <filesystem>
#include <functional>
#include <iostream>
using namespace nex;
namespace {
void require(bool value,const char *message){if(!value)throw std::runtime_error(message);}
void reject(const std::function<void()> &body){try{body();}catch(const Error &e){require(e.code=="E_TASK_PROVIDER","wrong provider error");return;}throw std::runtime_error("invalid write provider accepted");}
void boundaries(){
 auto p=parseVersioned("module w;pub server fn save()->result<bool> !{task,fs}{return file_write_text(\"output\",\"complete\");}","write.nex",SourceLanguage::TaskWrites023);check(p);
 auto name=p.function("save").name;NativeTaskProviderInfo info;info.enabled=true;info.codeOnly=true;info.language="0.23";info.component="leaf";info.cohort=std::string(64,'a');info.definitions={name};info.taskFileReads=true;info.taskFileWrites=true;
 auto value=nativeTaskExportInterface(p,name,std::string(64,'b'));value.requirements|=nexrt::taskCodeImageFileRead|nexrt::taskCodeImageFileWrite;info.exports[name]=value;
 auto record=nativeTaskProviderJSON(info);require(record.size()==14&&record.getString("schema")=="nex.native-task-provider/5","wrong write provider shape");require(parseNativeTaskProvider(llvm::json::Value(llvm::json::Object(record))).taskFileWrites,"write requirement lost");
 auto bad=[&](const std::function<void(llvm::json::Object&)> &f){auto copy=llvm::json::Object(record);f(copy);reject([&]{(void)parseNativeTaskProvider(llvm::json::Value(std::move(copy)));});};
 bad([](auto &o){o["schema"]="nex.native-task-provider/1";});bad([](auto &o){o["descriptor_abi"]=nexrt::taskCodeABI;});bad([](auto &o){o["language"]="0.22";});bad([](auto &o){o.erase("task_file_writes");});bad([](auto &o){o["task_file_writes"]=1;});bad([](auto &o){o["task_file_writes"]=false;});
 for(auto bits:{int64_t(31),int64_t(543),int64_t(1023),int64_t(-1)})bad([&](auto &o){(*o.getObject("exports")->getObject(name))["requirements"]=bits;});
 info.mode=NativeTaskLinkageMode::SharedFixed;info.artifact=NativeTaskArtifactKind::PicStage;info.definitionOwners[name]="leaf";info.componentFileReads["leaf"]=true;info.componentFileWrites["leaf"]=true;
 record=nativeTaskProviderJSON(info);require(record.size()==20&&parseNativeTaskProvider(llvm::json::Value(llvm::json::Object(record))).componentFileWrites.at("leaf"),"shared component writes lost");
 bad([](auto &o){o.erase("component_file_writes");});bad([](auto &o){(*o.getObject("component_file_writes"))["leaf"]=false;});bad([](auto &o){(*o.getObject("component_file_writes"))["other"]=true;});
 info.language="0.22";reject([&]{(void)nativeTaskProviderJSON(info);});
 NativeTaskApplicationStage stage;stage.enabled=true;stage.entry="main";stage.descriptorAccessor=nativeSymbol("main")+"__task_code_address";stage.fileWrites=true;stage.executionABI=nexrt::taskCodeWriteABI;
 auto application=nativeTaskApplicationStageJSON(stage);require(application.getAsObject()->size()==7&&parseNativeTaskApplicationStage(application).fileWrites,"root stage writes lost");
 auto old=llvm::json::Object(*application.getAsObject());old["execution_abi"]=nexrt::taskCodeABI;reject([&]{(void)parseNativeTaskApplicationStage(llvm::json::Value(std::move(old)));});
 stage.executionABI=nexrt::taskCodeABI;reject([&]{(void)nativeTaskApplicationStageJSON(stage);});stage.fileWrites=false;require(nativeTaskApplicationStageJSON(stage).getAsObject()->size()==4,"retained stage shape changed");
 static_assert(nexrt::taskProviderRequirementsMask==31&&nexrt::taskWriteProviderRequirementsMask==799);
}
}
int main(int argc,char **argv){try{
 if(argc==2&&std::string(argv[1])=="boundary"){boundaries();std::cout<<"{\"ok\":true,\"retained_ABI3_mask31\":true,\"write_ABI4_mask799\":true}\n";return 0;}
 if(argc!=3)throw Error("E_OPTION","write provider probe requires REQUEST OUTPUT");
 auto request=llvm::json::parse(readFile(argv[1]));if(!request||!request->getAsObject())throw Error("E_OPTION","invalid request");auto &o=*request->getAsObject();
 auto mode=o.getString("mode").value_or("static"),profile=o.getString("profile").value_or("debug");bool debug=o.getBoolean("task_debug").value_or(false);
 auto bundle=o.get("bundle");if(!bundle)throw Error("E_OPTION","missing bundle");auto p=loadVersionedBundle(*bundle,std::filesystem::absolute(argv[1]).parent_path().string(),"0.23");
 std::filesystem::path root=std::filesystem::absolute(argv[2]);std::filesystem::create_directories(root);
 BuildOptions leaf;leaf.entry="save";leaf.profile=profile.str();leaf.libraryEntry=true;leaf.codeOnlyLibrary=true;leaf.projectLibraryABI=true;leaf.taskComponent="leaf";leaf.taskDebug=debug;
 leaf.taskLinkageMode=mode=="shared"?NativeTaskLinkageMode::SharedFixed:NativeTaskLinkageMode::Static;leaf.positionIndependent=mode=="shared";
 auto library=build(p,(root/"leaf").string(),leaf);BuildOptions app=leaf;app.entry="main";app.libraryEntry=false;app.codeOnlyLibrary=false;app.taskComponent="app";
 app.taskImportedFunctions=library.taskProvider.definitions;app.libraries={{library.executable,hash(readFile(library.executable)),library.libraryABI,library.functionContracts,false,library.taskProviderFile,library.taskProviderDigest}};
 if(mode=="shared"){app.deferredLink=true;app.functionsOnly=true;}
 auto executable=build(p,(root/"app").string(),app);llvm::json::Value runtime=nullptr;
 if(mode=="shared"){
  auto images=buildNativeImages((root/"images").string(),{{"leaf","shared_library",&p,leaf,library,{},{}},{"app","executable",&p,app,executable,{}, {"leaf"}}});
  library=images.images.at("leaf");executable=images.images.at("app");runtime=std::move(images.runtime);
 }
 nexrt::TaskExecutionLimits limits;limits.workers=1;auto reference=evaluateTaskReference(p,"main",{},limits.steps,{},&limits);
 std::cout<<json(llvm::json::Object{{"ok",true},{"mode",mode},{"profile",profile},{"task_debug",debug},{"language",programLanguage(p)},{"executable",executable.executable},{"provider",nativeTaskProviderJSON(library.taskProvider)},{"application",nativeTaskProviderJSON(executable.taskProvider)},{"runtime",std::move(runtime)},{"reference_value",reference.value.scalar},{"reference_stdout",reference.output}})<<'\n';return 0;
 }catch(const Error &e){std::cout<<json(llvm::json::Object{{"ok",false},{"code",e.code},{"message",e.what()}})<<'\n';return 1;}
 catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 2;}}
