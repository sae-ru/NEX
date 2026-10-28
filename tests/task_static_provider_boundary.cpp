#include "nex/backend.h"
#include "nex/incremental.h"
#include <filesystem>
#include <functional>
#include <iostream>
using namespace nex;
namespace {
unsigned checks=0,rejections=0;
void require(bool value,const char *message){++checks;if(!value)throw std::runtime_error(message);}
void rejected(const std::function<void()> &body,const std::string &expected){
 try{body();}catch(const Error &error){require(error.code==expected,("unexpected boundary diagnostic: "+error.code+" "+error.what()).c_str());++rejections;return;}
 throw std::runtime_error("invalid task provider boundary accepted");
}
}
int main(){std::filesystem::path root;try{
 auto program=parse("module boundary;pub fn compute(x:i64)->i64 !{task}{task_yield();return x+1;}fn main()->i64 !{task}{return compute(41);}","boundary.nex");check(program);
 auto plan=planNative(program,"main",{},true);std::map<std::string,std::string> contracts;
 for(const auto &unit:plan.units){auto value=llvm::json::parse(unit.contract);value->getAsObject()->erase("unit");contracts[unit.identity]=hash(json(*value,false));}
 const auto name=program.function("compute").name;
 NativeTaskProviderInfo info;info.enabled=true;info.codeOnly=true;info.language="0.20";info.component="leaf";info.cohort=std::string(64,'a');info.definitions={name};info.exports[name]=nativeTaskExportInterface(program,name,contracts.at(name));
 auto valid=nativeTaskProviderJSON(info);auto parsed=parseNativeTaskProvider(llvm::json::Value(llvm::json::Object(valid)));require(parsed.definitions==info.definitions&&parsed.exports.at(name).signature==info.exports.at(name).signature,"valid static source interface changed");
 auto bad=[&](const std::function<void(llvm::json::Object&)> &change){auto value=llvm::json::Object(valid);change(value);rejected([&]{(void)parseNativeTaskProvider(llvm::json::Value(std::move(value)));},"E_TASK_PROVIDER");};
 bad([](auto &v){v["unknown"]=1;});bad([](auto &v){v.erase("cohort");});bad([](auto &v){v["mode"]="dynamic";});
 bad([](auto &v){v["descriptor_abi"]=3;});bad([](auto &v){v["descriptor_size"]=80;});bad([](auto &v){v["abi_offset"]=32;});
 bad([](auto &v){v["compiler_build"]="foreign";});bad([](auto &v){v["language"]="0.18";});bad([](auto &v){v["cohort"]="bad";});
 bad([](auto &v){v["component"]="";});bad([](auto &v){v["code_only"]=0;});bad([](auto &v){v["task_file_reads"]=0;});
 bad([&](auto &v){v["definitions"]=llvm::json::Array{name,name};});
 auto exportBad=[&](const std::string &key,llvm::json::Value value){bad([&](auto &v){(*v.getObject("exports")->getObject(name))[key]=std::move(value);});};
 exportBad("unknown",1);exportBad("accessor","wrong");exportBad("signature","bad");exportBad("contract","bad");
 for(int64_t bits:{0,32,5,9,13,17})exportBad("requirements",bits);
 // Canonical fs declaration bits are accepted only with020/server/task/read;
 // the image bit must agree with the component read requirement.
 auto fs=info;fs.exports[name].requirements=15;require(parseNativeTaskProvider(llvm::json::Value(nativeTaskProviderJSON(fs))).exports.at(name).requirements==15,"valid raw task/fs bits rejected");
 fs.language="0.19";rejected([&]{(void)parseNativeTaskProvider(llvm::json::Value(nativeTaskProviderJSON(fs)));},"E_TASK_PROVIDER");
 // The pure helper ABI is synchronous, but a callable must never escape it
 // into a task cohort and fail later when task_spawn needs a descriptor.
 for(const auto &source:std::vector<std::string>{
   "module b;pub fn make()->(fn()->i64){return fn()->i64{return 42;};}",
   "module b;pub fn make(f:fn()->i64)->i64{return f();}",
   "module b;pub struct Box{items:list<fn()->i64>;}pub fn make()->result<Box>{return ok(Box([fn()->i64{return 42;}]));}"
 }){
   auto boundary=parse(source,"callable-boundary.nex");check(boundary);
   BuildOptions mode;mode.entry="make";mode.libraryEntry=true;mode.codeOnlyLibrary=true;mode.projectLibraryABI=true;mode.staticTaskABI=true;mode.taskComponent="leaf";
   rejected([&]{validateNativeBuildEntry(boundary,mode);},"E_TASK_PROVIDER");
   // Historical synchronous libraries keep their existing callback ABI.
   mode.staticTaskABI=false;mode.taskComponent.clear();validateNativeBuildEntry(boundary,mode);++checks;
 }
 root=createTemporaryDirectory("nex-task-provider-boundary");auto archive=root/"leaf.a",record=root/"task-provider.json";writeFile(archive.string(),"!<arch>\n");
 BuildOptions options;options.staticTaskABI=true;options.projectLibraryABI=true;options.taskComponent="app";options.taskImportedFunctions={name};
 // Every negative below must finish before even reading this missing toolchain.
 // No compiler/linker executable is involved in this probe.
 options.toolchain=(root/"MUST_NOT_READ_TOOLCHAIN.json").string();
 NativeLibraryInput input{archive.string(),hash(readFile(archive.string())),info.cohort,{{name,contracts.at(name)}},false,record.string(),{}};
 auto preflight=[&](const NativeTaskProviderInfo &value,const std::string &expected){writeFile(record.string(),json(nativeTaskProviderJSON(value))+"\n");input.taskProviderDigest=hash(readFile(record.string()));options.libraries={input};rejected([&]{(void)build(program,(root/"artifacts").string(),options);},expected);require(!std::filesystem::exists(root/"artifacts"),"failed preflight published native artifacts");};
 options.taskDebug=true;validateNativeBuildEntry(program,options);++checks;preflight(info,"E_TASK_PROVIDER");options.taskDebug=false;
 auto changed=info;changed.exports[name].signature=std::string(64,'b');preflight(changed,"E_TASK_PROVIDER");
 changed=info;changed.exports.clear();preflight(changed,"E_TASK_PROVIDER");
 changed=info;changed.cohort=std::string(64,'b');preflight(changed,"E_TASK_PROVIDER");
 changed=info;changed.codeOnly=false;preflight(changed,"E_TASK_PROVIDER");
 changed=info;changed.component="app";preflight(changed,"E_TASK_PROVIDER");
 changed=info;changed.definitions={"missing::definition"};changed.exports.clear();preflight(changed,"E_TASK_PROVIDER");
 writeFile(record.string(),"{}\n");input.taskProviderDigest=std::string(64,'0');options.libraries={input};rejected([&]{(void)build(program,(root/"artifacts").string(),options);},"E_PROJECT_INPUT_CHANGED");
 input.taskProviderPath.clear();options.libraries={input};rejected([&]{(void)build(program,(root/"artifacts").string(),options);},"E_TASK_PROVIDER");
 std::filesystem::remove_all(root);root.clear();
 std::cout<<json(llvm::json::Object{{"ok",true},{"checks",checks},{"rejections",rejections},{"execution_abi",3},{"descriptor_layout_unchanged",true},{"native_tools_executed",false},{"runtime_execution_claim",false}})<<'\n';return 0;
 }catch(const std::exception &error){if(!root.empty())std::filesystem::remove_all(root);std::cerr<<error.what()<<'\n';return 1;}}
