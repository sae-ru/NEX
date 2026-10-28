#include "nex/backend.h"
#include "nex/incremental.h"
#include <filesystem>
#include <iostream>
#include <functional>
using namespace nex;
namespace {
unsigned checks=0,rejections=0;
void require(bool value,const char *text){++checks;if(!value)throw std::runtime_error(text);}
void rejects(std::function<void()> action,const std::string &code="E_TASK_PROVIDER"){try{action();}catch(const Error &e){require(e.code==code,e.what());++rejections;return;}throw std::runtime_error("malformed profile boundary accepted");}
}
int main(){std::filesystem::path temporary;try{
 const auto digest=std::string(64,'a');NativeTaskProfileCatalog catalog;catalog.mode=NativeTaskLinkageMode::Static;
 catalog.registries.push_back({"leaf",nativeTaskProfileRegistryAccessor("leaf"),{},{{"leaf::work",digest,digest,digest,"/source/leaf.nex",digest,1}}});
 auto info=nativeTaskProfileInfo(catalog);require(info.registries.size()==1&&info.registries[0].siteCount==1,"catalog site footprint lost");
 auto original=nativeTaskProfileCatalogJSON(catalog);require(original.size()==6&&parseNativeTaskProfileCatalog(llvm::json::Value(llvm::json::Object(original))).registries.size()==1,"catalog roundtrip failed");
 auto badCatalog=[&](std::function<void(llvm::json::Object&)> change){auto object=llvm::json::Object(original);change(object);rejects([&]{(void)parseNativeTaskProfileCatalog(llvm::json::Value(std::move(object)));});};
 badCatalog([](auto &o){o["extra"]=0;});badCatalog([](auto &o){o.erase("owner_image");});badCatalog([](auto &o){o["registry_abi"]=2;});badCatalog([](auto &o){o["mode"]="runtime-load";});badCatalog([](auto &o){o["artifact_kind"]="plugin";});
 badCatalog([](auto &o){(*o.getArray("registries"))[0].getAsObject()->operator[]("accessor")="wrong";});
 badCatalog([](auto &o){auto &registry=*(*o.getArray("registries"))[0].getAsObject();registry["component"]="bad-name";});
 badCatalog([](auto &o){auto &site=*(*(*o.getArray("registries"))[0].getAsObject()->getArray("sites"))[0].getAsObject();site["function_hash"]="wrong";});
 badCatalog([](auto &o){auto &sites=*(*o.getArray("registries"))[0].getAsObject()->getArray("sites");sites.push_back(llvm::json::Object(*sites[0].getAsObject()));});
 NativeTaskProviderInfo provider;provider.enabled=true;provider.codeOnly=true;provider.component="leaf";provider.language="0.20";provider.cohort=digest;provider.definitions={"leaf::work"};provider.profiling=info;
 auto object=nativeTaskProviderJSON(provider);require(object.size()==14&&object.getString("schema")=="nex.native-task-provider/3","static3 shape wrong");require(parseNativeTaskProvider(llvm::json::Value(llvm::json::Object(object))).profiling->catalogHash==info.catalogHash,"provider catalog pin lost");
 auto badProvider=[&](std::function<void(llvm::json::Object&)> change){auto bad=llvm::json::Object(object);change(bad);rejects([&]{(void)parseNativeTaskProvider(llvm::json::Value(std::move(bad)));});};
 badProvider([](auto &o){o.erase("profiling");});badProvider([](auto &o){(*o.getObject("profiling"))["extra"]=1;});badProvider([](auto &o){(*o.getObject("profiling"))["registry_abi"]=2;});badProvider([](auto &o){(*o.getObject("profiling"))["catalog_file"]="../escape";});badProvider([](auto &o){(*o.getObject("profiling"))["catalog_hash"]="invalid";});
 badProvider([](auto &o){auto &r=*(*o.getObject("profiling")->getArray("registries"))[0].getAsObject();r["site_count"]=0;});badProvider([](auto &o){auto &r=*(*o.getObject("profiling")->getArray("registries"))[0].getAsObject();r["site_count"]=2;});badProvider([](auto &o){auto &r=*(*o.getObject("profiling")->getArray("registries"))[0].getAsObject();r["component"]="other";r["accessor"]=nativeTaskProfileRegistryAccessor("other");});badProvider([](auto &o){auto &r=*(*o.getObject("profiling")->getArray("registries"))[0].getAsObject();r["text_bytes"]=0;});badProvider([](auto &o){auto &r=*(*o.getObject("profiling")->getArray("registries"))[0].getAsObject();r["text_bytes"]=16777217;});
 provider.mode=NativeTaskLinkageMode::SharedFixed;provider.artifact=NativeTaskArtifactKind::PicStage;provider.definitionOwners["leaf::work"]="leaf";provider.componentFileReads["leaf"]=false;require(nativeTaskProviderJSON(provider).size()==19,"shared3 shape wrong");(void)parseNativeTaskProvider(llvm::json::Value(nativeTaskProviderJSON(provider)));++checks;
 auto row=[](const std::string &kind,const std::string &path){return llvm::json::Object{{"kind",kind},{"path",path}};};llvm::json::Array inputs{row("abi","library-abi.json"),row("task_provider","task-provider.json"),row("profile_catalog","task-profile-catalog.json"),row("static_library","libraries/0.a"),row("static_task_provider","libraries/0.task-provider.json"),row("static_profile_catalog","libraries/0.task-profile-catalog.json")};
 llvm::json::Object completion{{"completion_schema","nex.native-completion/6"},{"completion_mode","static-application"},{"completion_inputs",llvm::json::Array(inputs)}};require(nativeCompletionInputs(completion).size()==6,"static6 completion rejected");
 auto badCompletion=[&](std::function<void(llvm::json::Object&)> change){auto bad=llvm::json::Object(completion);change(bad);rejects([&]{(void)nativeCompletionInputs(bad);},"E_CORE_BUILD");};badCompletion([](auto &o){o.erase("completion_mode");});badCompletion([](auto &o){o["completion_mode"]="shared-application";});badCompletion([](auto &o){o.getArray("completion_inputs")->pop_back();});
 auto p=parse("module profile_boundary;pub fn answer()->i64!{task}{task_yield();return 42;}fn main()->i64!{task}{return answer();}","profile.nex");check(p);
 temporary=createTemporaryDirectory("nex-provider-profile-boundary");auto archive=temporary/"leaf.a",record=temporary/"task-provider.json",profile=temporary/"task-profile-catalog.json";writeFile(archive.string(),"!<arch>\n");
 provider.mode=NativeTaskLinkageMode::Static;provider.artifact=NativeTaskArtifactKind::CodeArchive;provider.definitionOwners.clear();provider.componentFileReads.clear();provider.profiling->catalogHash=std::string(64,'b');writeFile(record.string(),json(nativeTaskProviderJSON(provider)));writeFile(profile.string(),json(llvm::json::Value(llvm::json::Object(original))));
 BuildOptions options;options.profile="profile";options.projectLibraryABI=true;options.staticTaskABI=true;options.taskComponent="app";options.toolchain=(temporary/"MUST_NOT_READ_TOOLCHAIN.json").string();options.libraries={{archive.string(),hash(readFile(archive.string())),digest,{{"leaf::work",digest}},false,record.string(),hash(readFile(record.string()))}};
 rejects([&]{(void)build(p,(temporary/"artifacts").string(),options);});require(!std::filesystem::exists(temporary/"artifacts"),"bad profile pin created cache before validation");std::filesystem::remove_all(temporary);temporary.clear();
 std::cout<<json(llvm::json::Object{{"ok",true},{"checks",checks},{"rejections",rejections},{"execution_abi",3},{"registry_abi",1},{"tools_executed",false}})<<'\n';return 0;
 }catch(const std::exception &e){if(!temporary.empty())std::filesystem::remove_all(temporary);std::cerr<<e.what()<<'\n';return 1;}}
