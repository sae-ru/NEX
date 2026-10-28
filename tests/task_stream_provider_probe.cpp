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
 auto p=parseVersioned("module stream;pub server fn save(f:file)->file !{task,fs}{task_yield();return f;}","stream.nex",SourceLanguage::TaskStreams024);check(p);
 auto name=p.function("save").name;NativeTaskProviderInfo info;info.enabled=true;info.codeOnly=true;info.language="0.24";info.component="leaf";info.cohort=std::string(64,'a');info.definitions={name};info.taskFileStreams=true;
 auto value=nativeTaskExportInterface(p,name,std::string(64,'b'));value.requirements|=nexrt::taskCodeImageFileStream;info.exports[name]=value;
 size_t checks=0;auto valid=[&](const llvm::json::Object &record,size_t size){auto parsed=parseNativeTaskProvider(llvm::json::Value(llvm::json::Object(record)));require(record.size()==size&&parsed.taskFileStreams&&parsed.language=="0.24","stream provider shape differs");++checks;};
 auto record=nativeTaskProviderJSON(info);valid(record,15);
 auto bad=[&](const std::function<void(llvm::json::Object&)> &f){auto copy=llvm::json::Object(record);f(copy);reject([&]{(void)parseNativeTaskProvider(llvm::json::Value(std::move(copy)));});++checks;};
 bad([](auto &o){o["schema"]="nex.native-task-provider/5";});bad([](auto &o){o["descriptor_abi"]=nexrt::taskCodeWriteABI;});bad([](auto &o){o["language"]="0.23";});
 bad([](auto &o){o.erase("task_file_streams");});bad([](auto &o){o["task_file_streams"]=1;});bad([](auto &o){o["task_file_streams"]=false;});
 for(auto bits:{int64_t(32),int64_t(64),int64_t(128),int64_t(4096),int64_t(-1)})bad([&](auto &o){(*o.getObject("exports")->getObject(name))["requirements"]=value.requirements|bits;});
 bad([&](auto &o){(*o.getObject("exports")->getObject(name))["requirements"]=value.requirements&~nexrt::taskCodeFileStream;});
 info.mode=NativeTaskLinkageMode::SharedFixed;info.artifact=NativeTaskArtifactKind::PicStage;info.definitionOwners[name]="leaf";info.componentFileReads["leaf"]=false;info.componentFileWrites["leaf"]=false;info.componentFileStreams["leaf"]=true;
 record=nativeTaskProviderJSON(info);valid(record,22);
 bad([](auto &o){o.erase("component_file_streams");});bad([](auto &o){(*o.getObject("component_file_streams"))["leaf"]=false;});bad([](auto &o){(*o.getObject("component_file_streams"))["other"]=true;});
 info.language="0.23";reject([&]{(void)nativeTaskProviderJSON(info);});++checks;
 NativeTaskApplicationStage stage;stage.enabled=true;stage.entry="main";stage.descriptorAccessor=nativeSymbol("main")+"__task_code_address";stage.fileStreams=true;stage.executionABI=nexrt::taskCodeStreamABI;
 auto application=nativeTaskApplicationStageJSON(stage);require(application.getAsObject()->size()==8&&parseNativeTaskApplicationStage(application).fileStreams,"stream root requirements lost");++checks;
 for(auto abi:{nexrt::taskCodeABI,nexrt::taskCodeWriteABI}){auto old=llvm::json::Object(*application.getAsObject());old["execution_abi"]=abi;reject([&]{(void)parseNativeTaskApplicationStage(llvm::json::Value(std::move(old)));});++checks;}
 stage.executionABI=nexrt::taskCodeWriteABI;reject([&]{(void)nativeTaskApplicationStageJSON(stage);});++checks;
 std::cout<<"{\"ok\":true,\"stream_boundary_checks\":"<<checks<<",\"retained_ABI3_ABI4_masks\":[31,799],\"stream_mask\":3871}\n";
 static_assert(nexrt::taskProviderRequirementsMask==31&&nexrt::taskWriteProviderRequirementsMask==799&&nexrt::taskStreamProviderRequirementsMask==3871);
}
}
int main(int argc,char **argv){try{
 if(argc==2&&std::string(argv[1])=="boundary"){boundaries();return 0;}
 if(argc!=3)throw Error("E_OPTION","write provider probe requires REQUEST OUTPUT");
 auto request=llvm::json::parse(readFile(argv[1]));if(!request||!request->getAsObject())throw Error("E_OPTION","invalid request");auto &o=*request->getAsObject();
 auto mode=o.getString("mode").value_or("static"),profile=o.getString("profile").value_or("debug");bool debug=o.getBoolean("task_debug").value_or(false);
 auto bundle=o.get("bundle");if(!bundle)throw Error("E_OPTION","missing bundle");auto p=loadVersionedBundle(*bundle,std::filesystem::absolute(argv[1]).parent_path().string(),"0.24");
 std::filesystem::path root=std::filesystem::absolute(argv[2]);std::filesystem::create_directories(root);
 BuildOptions leaf;leaf.entry=o.getString("entry").value_or("save").str();leaf.profile=profile.str();leaf.libraryEntry=true;leaf.codeOnlyLibrary=true;leaf.projectLibraryABI=true;leaf.taskComponent="leaf";leaf.taskDebug=debug;
 leaf.taskLinkageMode=mode=="shared"?NativeTaskLinkageMode::SharedFixed:NativeTaskLinkageMode::Static;leaf.positionIndependent=mode=="shared";
 auto library=build(p,(root/"leaf").string(),leaf);BuildOptions app=leaf;app.entry="main";app.libraryEntry=false;app.codeOnlyLibrary=false;app.taskComponent="app";
 app.taskImportedFunctions=library.taskProvider.definitions;app.libraries={{library.executable,hash(readFile(library.executable)),library.libraryABI,library.functionContracts,false,library.taskProviderFile,library.taskProviderDigest}};
 if(mode=="shared"){app.deferredLink=true;app.functionsOnly=true;}
 auto executable=build(p,(root/"app").string(),app);llvm::json::Value runtime=nullptr;
 if(mode=="shared"){
  auto images=buildNativeImages((root/"images").string(),{{"leaf","shared_library",&p,leaf,library,{},{}},{"app","executable",&p,app,executable,{}, {"leaf"}}});
  library=images.images.at("leaf");executable=images.images.at("app");runtime=std::move(images.runtime);
 }
 nexrt::TaskExecutionLimits limits;limits.workers=1;std::string referenceError;int64_t referenceValue=0;std::string referenceOutput;try{auto reference=evaluateTaskReference(p,"main",{},limits.steps,{},&limits);referenceValue=reference.value.scalar;referenceOutput=reference.output;}catch(const Error &error){referenceError=error.code;}
 std::cout<<json(llvm::json::Object{{"ok",true},{"mode",mode},{"profile",profile},{"task_debug",debug},{"language",programLanguage(p)},{"executable",executable.executable},{"provider_executable",library.executable},{"root_mlir",executable.mlir},{"provider",nativeTaskProviderJSON(library.taskProvider)},{"application",nativeTaskProviderJSON(executable.taskProvider)},{"runtime",std::move(runtime)},{"reference_value",referenceValue},{"reference_stdout",referenceOutput},{"reference_error",referenceError},{"revision",revision(p)}})<<'\n';return 0;
 }catch(const Error &e){std::cout<<json(llvm::json::Object{{"ok",false},{"code",e.code},{"message",e.what()}})<<'\n';return 1;}
 catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 2;}}
