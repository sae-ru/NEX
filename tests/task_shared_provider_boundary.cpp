#include "nex/backend.h"
#include "nex/incremental.h"
#include <filesystem>
#include <functional>
#include <iostream>
using namespace nex;
namespace {
unsigned checks=0,rejections=0;
void require(bool yes,const char *message){++checks;if(!yes)throw std::runtime_error(message);}
void rejects(const std::function<void()> &f,const std::string &code="E_TASK_PROVIDER"){
  try{f();}catch(const Error &e){require(e.code==code,(e.code+": "+e.what()).c_str());++rejections;return;}throw std::runtime_error("invalid shared task boundary accepted");
}
}
int main(){std::filesystem::path directory;try{
 auto p=parse("module boundary;pub fn compute(x:i64)->i64!{task}{task_yield();return x+1;}fn main()->i64!{task}{return compute(41);}","boundary.nex");check(p);
 auto name=p.function("compute").name;auto plan=planNative(p,"main",{},true);std::map<std::string,std::string> contracts;
 for(const auto &u:plan.units){auto v=llvm::json::parse(u.contract);v->getAsObject()->erase("unit");contracts[u.identity]=hash(json(*v,false));}
 NativeTaskProviderInfo stage;stage.enabled=true;stage.codeOnly=true;stage.component="leaf";stage.language="0.20";stage.cohort=std::string(64,'a');stage.definitions={name};stage.exports[name]=nativeTaskExportInterface(p,name,contracts.at(name));
 // Unchanged schema1 remains a distinct explicitly static record.
 require(parseNativeTaskProvider(llvm::json::Value(nativeTaskProviderJSON(stage))).mode==NativeTaskLinkageMode::Static,"static record mode changed");
 stage.mode=NativeTaskLinkageMode::SharedFixed;stage.artifact=NativeTaskArtifactKind::PicStage;stage.definitionOwners[name]="leaf";stage.componentFileReads["leaf"]=false;
 auto original=nativeTaskProviderJSON(stage);require(original.size()==18,"provider2 shape is not exact18");
 auto read=parseNativeTaskProvider(llvm::json::Value(llvm::json::Object(original)));require(read.ownerImage.empty()&&!read.image&&read.mode==NativeTaskLinkageMode::SharedFixed,"PIC stage invented final owner");
 auto bad=[&](const std::function<void(llvm::json::Object&)> &f){auto v=llvm::json::Object(original);f(v);rejects([&]{(void)parseNativeTaskProvider(llvm::json::Value(std::move(v)));});};
 bad([](auto &v){v["extra"]=1;});bad([](auto &v){v.erase("image");});bad([](auto &v){v["mode"]="static";});bad([](auto &v){v["artifact_kind"]="plugin";});
 bad([](auto &v){v["descriptor_abi"]=3;});bad([](auto &v){v["descriptor_size"]=96;});bad([](auto &v){v["abi_offset"]=48;});bad([](auto &v){v["compiler_build"]="foreign";});
 bad([](auto &v){v["owner_image"]="app";});bad([](auto &v){v["code_only"]=false;});bad([](auto &v){v["image"]=llvm::json::Object{};});
 bad([](auto &v){v["definition_owners"]=llvm::json::Object{};});bad([&](auto &v){(*v.getObject("definition_owners"))[name]="other";});
 bad([](auto &v){(*v.getObject("component_file_reads"))["leaf"]=1;});bad([](auto &v){(*v.getObject("component_file_reads"))["leaf"]=true;});
 for(int64_t flags:{33,65,129,97,225})bad([&](auto &v){(*v.getObject("exports")->getObject(name))["requirements"]=flags;});
 auto mixed=stage;mixed.artifact=NativeTaskArtifactKind::SharedImage;mixed.ownerImage="leaf";mixed.image=NativeTaskImageIdentity{std::string(64,'b'),std::string(64,'c'),std::string(64,'d'),std::string(32,'e'),std::string(64,'f'),std::string(64,'0')};
 mixed.definitions.insert("mid::read");mixed.definitionOwners["mid::read"]="mid";mixed.componentFileReads["mid"]=true;mixed.taskFileReads=true;
 auto other=stage.exports.at(name);other.accessor=nativeSymbol("mid::read")+"__task_code_address";other.requirements=31;mixed.exports["mid::read"]=other;
 auto merged=parseNativeTaskProvider(llvm::json::Value(nativeTaskProviderJSON(mixed)));require(merged.exports.at(name).requirements==1&&merged.exports.at("mid::read").requirements==31,"aggregate normalized component descriptor flags");
 auto broken=mixed;broken.componentFileReads["leaf"]=true;rejects([&]{(void)parseNativeTaskProvider(llvm::json::Value(nativeTaskProviderJSON(broken)));});
 broken=mixed;broken.image->uuid="not-an-image-id";rejects([&]{(void)parseNativeTaskProvider(llvm::json::Value(nativeTaskProviderJSON(broken)));});
 broken=mixed;broken.ownerImage="wrong";rejects([&]{(void)parseNativeTaskProvider(llvm::json::Value(nativeTaskProviderJSON(broken)));});
 broken=mixed;broken.image.reset();rejects([&]{(void)parseNativeTaskProvider(llvm::json::Value(nativeTaskProviderJSON(broken)));});
 mixed.artifact=NativeTaskArtifactKind::Application;mixed.codeOnly=false;require(parseNativeTaskProvider(llvm::json::Value(nativeTaskProviderJSON(mixed))).definitions==mixed.definitions,"executable lost actual NEX ownership");
 NativeTaskApplicationStage app{true,p.function("main").name,nativeSymbol(p.function("main").name)+"__task_code_address",{123,456,2},false};
 auto application=nativeTaskApplicationStageJSON(app);require(parseNativeTaskApplicationStage(application).configured==app.configured,"root limits lost in stage contract");require(!parseNativeTaskApplicationStage(nullptr).enabled,"null root contract enabled");
 for(const auto &key:{"steps","timeout_ms","workers"}){auto v=llvm::json::Object(*application.getAsObject());(*v.getObject("configured"))[key]=0;rejects([&]{(void)parseNativeTaskApplicationStage(llvm::json::Value(std::move(v)));});}
 auto v=llvm::json::Object(*application.getAsObject());v["descriptor_accessor"]="wrong";rejects([&]{(void)parseNativeTaskApplicationStage(llvm::json::Value(std::move(v)));});
 BuildOptions options;options.taskLinkageMode=NativeTaskLinkageMode::SharedFixed;options.positionIndependent=true;options.deferredLink=true;options.functionsOnly=true;options.projectLibraryABI=true;options.taskComponent="app";
 validateNativeBuildEntry(p,options);++checks;auto changed=options;changed.staticTaskABI=true;rejects([&]{validateNativeBuildEntry(p,changed);});
 changed=options;changed.taskLinkageMode=static_cast<NativeTaskLinkageMode>(99);rejects([&]{validateNativeBuildEntry(p,changed);});
 changed=options;changed.positionIndependent=false;rejects([&]{validateNativeBuildEntry(p,changed);});changed=options;changed.functionsOnly=false;rejects([&]{validateNativeBuildEntry(p,changed);});
 changed=options;changed.profile="profile";validateNativeBuildEntry(p,changed);++checks;changed=options;changed.taskDebug=true;validateNativeBuildEntry(p,changed);++checks;changed=options;changed.target="server";rejects([&]{validateNativeBuildEntry(p,changed);});
 // Schema5 structure, order and paired pins are independent of file contents.
 auto entry=[](const std::string &kind,const std::string &path){return llvm::json::Object{{"kind",kind},{"path",path}};};
 auto image="images/libnex_leaf_"+std::string(64,'a')+".so";
 llvm::json::Array files{entry("abi","library-abi.json"),entry("task_provider","task-provider.json"),entry("link_inputs","image-inputs.json"),entry("objects","objects.a"),entry("static_library","libraries/0.a"),entry("static_task_provider","libraries/0.task-provider.json"),entry("owned_image",image),entry("owned_task_provider",image+".task-provider.json")};
 llvm::json::Object completion{{"completion_schema","nex.native-completion/5"},{"completion_inputs",llvm::json::Array(files)}};require(nativeCompletionInputs(completion).size()==8,"valid task image completion rejected");
 auto malformed=[&](const std::function<void(llvm::json::Array&)> &f){auto a=llvm::json::Array(files);f(a);auto m=llvm::json::Object(completion);m["completion_inputs"]=std::move(a);rejects([&]{(void)nativeCompletionInputs(m);},"E_CORE_BUILD");};
 malformed([](auto &a){a.erase(a.begin()+5);});malformed([](auto &a){a[5]=llvm::json::Object{{"kind","static_task_provider"},{"path","libraries/1.task-provider.json"}};});
 malformed([](auto &a){a[7]=llvm::json::Object{{"kind","owned_task_provider"},{"path","images/missing.so.task-provider.json"}};});malformed([](auto &a){a.push_back(llvm::json::Object{{"kind","owned_image"},{"path","../escape"}});});
 directory=createTemporaryDirectory("nex-shared-provider-boundary");auto archive=directory/"leaf.a",record=directory/"task-provider.json";writeFile(archive.string(),"!<arch>\n");options.taskImportedFunctions={name};options.toolchain=(directory/"MUST_NOT_READ_TOOLCHAIN.json").string();
 auto preflight=[&](const NativeTaskProviderInfo &info){writeFile(record.string(),json(nativeTaskProviderJSON(info))+"\n");options.libraries={{archive.string(),hash(readFile(archive.string())),stage.cohort,{{name,contracts.at(name)}},false,record.string(),hash(readFile(record.string()))}};rejects([&]{(void)build(p,(directory/"artifacts").string(),options);});require(!std::filesystem::exists(directory/"artifacts"),"failed preflight created cache");};
 auto wrongMode=stage;wrongMode.mode=NativeTaskLinkageMode::Static;preflight(wrongMode);preflight(mixed);auto wrong=stage;wrong.exports[name].signature=std::string(64,'b');preflight(wrong);
 // Profile and ordinary task-provider cohorts reject mixing before tools/cache.
 options.profile="profile";preflight(stage);options.profile="debug";options.taskDebug=true;preflight(stage);options.taskDebug=false;
 NativeTaskProfileCatalog catalog;catalog.mode=NativeTaskLinkageMode::SharedFixed;catalog.artifact=NativeTaskArtifactKind::PicStage;
 catalog.registries.push_back({"leaf",nativeTaskProfileRegistryAccessor("leaf"),"",{{name,hash(json(canonical(p.function(name)),false)),hash(p.definition(p.function(name))),hash(p.source),"/verified/boundary.nex",contracts.at(name),1}}});
 auto profiled=stage;profiled.profiling=nativeTaskProfileInfo(catalog);preflight(profiled);
 require(!std::filesystem::exists(directory/"task-profile-catalog.json"),"mode mismatch read a profile catalog");
 std::filesystem::remove_all(directory);directory.clear();
 std::cout<<json(llvm::json::Object{{"ok",true},{"checks",checks},{"rejections",rejections},{"execution_abi",3},{"descriptor_bytes",88},{"native_tools_executed",false},{"source_runtime_execution_claim",false}})<<'\n';return 0;
 }catch(const std::exception &e){if(!directory.empty())std::filesystem::remove_all(directory);std::cerr<<e.what()<<'\n';return 1;}}
