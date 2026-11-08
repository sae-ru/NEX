#include "nex/project_capture.h"
#include "llvm/Support/Error.h"
#include <filesystem>
#include <iostream>

// Explicit C++ integration driver. No private-language switch is added to CLI.
int main(int argc,char **argv){try{
 using namespace nex;using Object=llvm::json::Object;
 if(argc!=2)throw Error("E_OPTION","private project probe requires one request file");
 auto parsed=llvm::json::parse(readFile(argv[1]));if(!parsed||!parsed->getAsObject())throw Error("E_OPTION","invalid project probe request");
 auto &o=*parsed->getAsObject();auto text=[&](const char *key,const std::string &fallback=""){return o.getString(key).value_or(fallback).str();};
 auto sourceLanguage=o.getBoolean("public_api").value_or(false)?currentSourceLanguage:SourceLanguage::TaskStreams024;
 if(auto retained=o.getString("source_language")){
  if(*retained=="0.23")sourceLanguage=SourceLanguage::TaskWrites023;
  else if(*retained=="0.24")sourceLanguage=SourceLanguage::TaskStreams024;
  else if(*retained=="0.26")sourceLanguage=SourceLanguage::ExceptionHandlers026;
  else if(*retained=="0.27")sourceLanguage=SourceLanguage::TypedErrors027;
  else if(*retained=="0.28")sourceLanguage=SourceLanguage::Contracts028;
  else throw Error("E_LANGUAGE_VERSION","project probe accepts explicit retained023/024/026/027 or candidate028");
 }
 const auto action=text("action","plan"),root=text("root"),manifest=text("manifest",(std::filesystem::path(root)/"nex.build.json").string());
 llvm::json::Value output=nullptr;
 if(action=="capture"){
  std::set<std::string> configurations,debug;
  if(auto rows=o.getArray("configurations"))for(const auto &value:*rows){auto name=value.getAsString();if(!name)throw Error("E_OPTION","invalid configuration");configurations.insert(name->str());}
  if(configurations.empty())configurations.insert(text("configuration","debug"));
  if(o.getBoolean("task_debug").value_or(false))debug=configurations;
  output=captureProject(root,manifest,readFile(manifest),text("component","app"),configurations,{},debug,sourceLanguage);
 }else if(action=="restore"||action=="validate"||action=="verify"){
  auto value=llvm::json::parse(readFile(text("capture")));if(!value)throw Error("E_JSON",llvm::toString(value.takeError()));
  validateProjectCaptureData(*value,sourceLanguage);
  if(action=="restore"){
   auto restored=materializeProjectCapture(*value,text("directory"),sourceLanguage);validateProjectCapturePlans(*value,text("directory"),sourceLanguage);
   output=Object{{"ok",true},{"root",restored},{"language",programLanguage(sourceLanguage)}};
  }else {
   if(action=="verify")validateProjectCapturePlans(*value,text("directory"),sourceLanguage);
   output=Object{{"ok",true},{"language",programLanguage(sourceLanguage)}};
  }
 }else{
  ProjectBuildOptions options;options.kind=action;options.component=text("component","app");options.configuration=text("configuration","debug");
  options.compilerVersion=NEX_VERSION;options.compilerBuild=NEX_BUILD_ID;options.sourceLanguage=sourceLanguage;
  options.directory=text("directory");options.compiler=text("compiler");options.adapter=text("adapter","nex-dap");
  options.taskDebug=o.getBoolean("task_debug").value_or(false);options.package.directory=text("package_directory");options.package.compiler=options.compiler;
  options.package.notices=text("notices");
  options.profiling.output=text("profile_output");options.profiling.directory=root;
  if(auto env=o.getObject("environment"))for(const auto &[key,value]:*env){auto item=value.getAsString();if(!item)throw Error("E_OPTION","invalid profile environment");options.profiling.environment[key.str()]=item->str();}
  output=buildProject(root,manifest,readFile(manifest),options);
 }
 std::cout<<json(output)<<'\n';return 0;
 }catch(const nex::Error &e){std::cout<<nex::json(llvm::json::Object{{"ok",false},{"code",e.code},{"message",e.what()}})<<'\n';return 1;}
 catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 2;}
}
