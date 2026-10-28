#include "nex/backend.h"
#include "nex/task_frontend.h"
#include "nex_task_protocol.h"
#include <functional>
#include <iostream>
#include <stdexcept>

using namespace nex;
namespace {
size_t checks=0;
void require(bool condition){++checks;if(!condition)throw std::runtime_error("source provider contract failed");}
void rejected(const std::function<void()> &action){
  try{action();}catch(const Error &error){require(error.code=="E_TASK_PROVIDER");return;}
  throw std::runtime_error("incompatible source provider accepted");
}
}
int main(){try{
  auto program=parseVersioned(R"(module provider;
pub fn next(value:i64)->i64{return value+1;}
pub fn fail()->i64 !{throw}{throw("USER","message");}
pub fn delayed()->i64 !{task,throw}{task_yield();return fail();}
)","provider.nex",SourceLanguage::SourceExceptions025);
  check(program);
  NativeTaskProviderInfo info;info.enabled=true;info.codeOnly=true;
  info.language="0.25";info.component="leaf";info.cohort=std::string(64,'a');
  for(auto name:{"next","fail","delayed"}){
    const auto &function=program.function(name);info.definitions.insert(function.name);
    info.exports[function.name]=nativeTaskExportInterface(program,function.name,std::string(64,'b'));
  }
  require(info.exports.at(program.function("next").name).requirements==0);
  require(info.exports.at(program.function("fail").name).requirements==nexrt::taskCodeDeclaredThrow);
  require(info.exports.at(program.function("delayed").name).requirements==(nexrt::taskCodeDeclaredTask|nexrt::taskCodeDeclaredThrow));
  auto record=nativeTaskProviderJSON(info);
  auto parsed=parseNativeTaskProvider(llvm::json::Value(llvm::json::Object(record)));
  require(record.size()==15&&record.getString("schema")=="nex.native-task-provider/11");
  require(record.getInteger("descriptor_abi")==nexrt::taskCodeSourceExceptionABI&&parsed.exports.size()==3);
  auto bad=[&](const std::function<void(llvm::json::Object&)> &edit){
    auto copy=llvm::json::Object(record);edit(copy);
    rejected([&]{(void)parseNativeTaskProvider(llvm::json::Value(std::move(copy)));});
  };
  bad([](auto &o){o["schema"]="nex.native-task-provider/8";});
  bad([](auto &o){o["descriptor_abi"]=nexrt::taskCodeStreamABI;});
  bad([](auto &o){o["descriptor_abi"]=nexrt::taskCodeExceptionHostPrototypeABI;});
  bad([](auto &o){o["language"]="0.24";});
  bad([](auto &o){o["descriptor_size"]=96;});
  bad([](auto &o){o["abi_offset"]=48;});
  bad([](auto &o){o["component"]="invalid-component";});
  bad([](auto &o){o.erase("task_file_streams");});
  for(auto bits:{int64_t(32),int64_t(64),int64_t(128),int64_t(8192),int64_t(-1)})
    bad([&](auto &o){(*o.getObject("exports")->getObject(program.function("fail").name))["requirements"]=nexrt::taskCodeDeclaredThrow|bits;});
  info.mode=NativeTaskLinkageMode::SharedFixed;info.artifact=NativeTaskArtifactKind::PicStage;
  for(const auto &name:info.definitions)info.definitionOwners[name]="leaf";
  info.componentFileReads["leaf"]=false;info.componentFileWrites["leaf"]=false;info.componentFileStreams["leaf"]=false;
  record=nativeTaskProviderJSON(info);parsed=parseNativeTaskProvider(llvm::json::Value(llvm::json::Object(record)));
  require(record.size()==22&&parsed.mode==NativeTaskLinkageMode::SharedFixed&&parsed.exports.size()==3);
  bad([](auto &o){(*o.getObject("definition_owners"))["provider::fail"]="other";});
  bad([](auto &o){(*o.getObject("component_file_streams"))["leaf"]=true;});
  NativeTaskApplicationStage stage;stage.enabled=true;stage.entry="main";
  stage.descriptorAccessor=nativeSymbol(stage.entry)+"__task_code_address";stage.executionABI=nexrt::taskCodeSourceExceptionABI;
  auto application=nativeTaskApplicationStageJSON(stage);
  require(application.getAsObject()->getString("schema")=="nex.native-task-application/4");
  require(parseNativeTaskApplicationStage(application).executionABI==nexrt::taskCodeSourceExceptionABI);
  auto old=llvm::json::Object(*application.getAsObject());old["schema"]="nex.native-task-application/3";
  rejected([&]{(void)parseNativeTaskApplicationStage(llvm::json::Value(std::move(old)));});
  static_assert(nexrt::taskProviderRequirementsMask==31&&nexrt::taskWriteProviderRequirementsMask==799&&nexrt::taskStreamProviderRequirementsMask==3871&&nexrt::taskSourceExceptionProviderRequirementsMask==7967);
  std::cout<<"{\"ok\":true,\"checks\":"<<checks<<",\"source_provider_mask\":7967,\"retained_masks\":[31,799,3871]}\n";
  return 0;
}catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 1;}}
