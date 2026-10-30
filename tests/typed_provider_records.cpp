#include "nex/backend.h"
#include "nex/task_frontend.h"
#include "nex_task_protocol.h"
#include <functional>
#include <iostream>
#include <stdexcept>
using namespace nex;
namespace {
unsigned checks=0;
void require(bool v){++checks;if(!v)throw std::runtime_error("typed provider protocol check failed");}
void rejected(const llvm::json::Object &record,const std::function<void(llvm::json::Object&)> &edit){
 auto copy=llvm::json::Object(record);edit(copy);
 try{(void)parseNativeTaskProvider(llvm::json::Value(std::move(copy)));}
 catch(const Error &e){require(e.code=="E_TASK_PROVIDER");return;}
 throw std::runtime_error("incompatible typed provider accepted");
}
}
int main(){try{
 llvm::json::Array records;
 for(auto language:{SourceLanguage::SourceExceptions025,SourceLanguage::ExceptionHandlers026,SourceLanguage::TypedErrors027}){
  const bool typed=language==SourceLanguage::TypedErrors027;
  auto p=parseVersioned(std::string("module provider;\npub struct Problem<T>{value:T;}\npub fn fail()->i64 !{throw}{")+
      (typed?"throw(Problem<i64>(42));":"throw(\"CODE\",\"legacy\");")+
      "}pub fn delayed()->i64 !{task,throw}{task_yield();return fail();}","provider.nex",language);check(p);
  NativeTaskProviderInfo info;info.enabled=true;info.codeOnly=true;info.component="leaf";info.cohort=std::string(64,'a');info.language=programLanguage(p);
  for(auto name:{"fail","delayed"}){const auto &f=p.function(name);info.definitions.insert(f.name);info.exports[f.name]=nativeTaskExportInterface(p,f.name,std::string(64,'b'));}
  for(bool shared:{false,true}){
   if(shared){info.mode=NativeTaskLinkageMode::SharedFixed;info.artifact=NativeTaskArtifactKind::PicStage;
    for(const auto &name:info.definitions)info.definitionOwners[name]="leaf";
    info.componentFileReads["leaf"]=false;info.componentFileWrites["leaf"]=false;info.componentFileStreams["leaf"]=false;}
   auto record=nativeTaskProviderJSON(info);auto parsed=parseNativeTaskProvider(llvm::json::Value(llvm::json::Object(record)));
   require(record.getString("schema")== (typed?"nex.native-task-provider/14":"nex.native-task-provider/11"));
   require(record.getInteger("descriptor_abi")== (typed?nexrt::taskCodeTypedSourceExceptionABI:nexrt::taskCodeSourceExceptionABI));
   require(parsed.language==programLanguage(p)&&parsed.exports.size()==2&&parsed.mode==info.mode);records.push_back(llvm::json::Object(record));
   rejected(record,[](auto &r){r["schema"]="nex.native-task-provider/17";});
   rejected(record,[&](auto &r){r["descriptor_abi"]=typed?nexrt::taskCodeSourceExceptionABI:nexrt::taskCodeTypedSourceExceptionABI;});
   rejected(record,[](auto &r){r["descriptor_abi"]=nexrt::taskCodeTypedAuthorityDevelopmentABI;});
   rejected(record,[&](auto &r){r["language"]=typed?"0.26":"0.27";});
   rejected(record,[](auto &r){r["descriptor_size"]=96;});
   rejected(record,[](auto &r){r["abi_offset"]=48;});
   rejected(record,[](auto &r){r.erase("task_file_streams");});
   rejected(record,[](auto &r){r["payload"]=42;});
   rejected(record,[&](auto &r){(*r.getObject("exports")->getObject(p.function("fail").name))["requirements"]=nexrt::taskCodeDeclaredThrow|nexrt::taskCodeDeclaredFfi;});
   if(typed)rejected(record,[](auto &r){r["schema"]="nex.native-task-provider/11";});
   NativeTaskProfileInfo profile;profile.catalogFile="task-profile-catalog.json";profile.catalogHash=std::string(64,'c');
   profile.registries.push_back({"leaf",nativeTaskProfileRegistryAccessor("leaf"),std::string(64,'d'),2,10});
   info.profiling=profile;record=nativeTaskProviderJSON(info);parsed=parseNativeTaskProvider(llvm::json::Value(llvm::json::Object(record)));
   require(record.getString("schema")==(typed?"nex.native-task-provider/15":"nex.native-task-provider/12"));require(bool(parsed.profiling));records.push_back(llvm::json::Object(record));
   info.profiling.reset();NativeTaskDebugInfo debug;debug.catalogFile="task-debug-catalog.json";debug.sourceUnionFile="task-debug-sources.json";
   debug.catalogHash=std::string(64,'c');debug.sourceUnionHash=std::string(64,'e');
   debug.registries.push_back({"leaf",nativeTaskDebugRegistryAccessor("leaf"),std::string(64,'d'),2});
   info.debugging=debug;record=nativeTaskProviderJSON(info);parsed=parseNativeTaskProvider(llvm::json::Value(llvm::json::Object(record)));
   require(record.getString("schema")==(typed?"nex.native-task-provider/16":"nex.native-task-provider/13"));require(bool(parsed.debugging));records.push_back(llvm::json::Object(record));info.debugging.reset();
  }
 }
 NativeTaskApplicationStage stage;stage.enabled=true;stage.entry="main";stage.descriptorAccessor=nativeSymbol(stage.entry)+"__task_code_address";stage.executionABI=nexrt::taskCodeTypedSourceExceptionABI;
 auto application=nativeTaskApplicationStageJSON(stage);require(application.getAsObject()->getString("schema")=="nex.native-task-application/5");
 require(parseNativeTaskApplicationStage(application).executionABI==nexrt::taskCodeTypedSourceExceptionABI);
 for(auto schema:{"nex.native-task-application/4","nex.native-task-application/3"}){
  auto old=llvm::json::Object(*application.getAsObject());old["schema"]=schema;bool failed=false;
  try{(void)parseNativeTaskApplicationStage(llvm::json::Value(std::move(old)));}catch(const Error &e){failed=e.code=="E_TASK_PROVIDER";}require(failed);
 }
 std::cout<<json(llvm::json::Object{{"ok",true},{"checks",checks},{"records",std::move(records)},{"application",std::move(application)}})<<'\n';
 return 0;
}catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 1;}}
