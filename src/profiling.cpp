#include "nex/profiling.h"
#include "llvm/TargetParser/Host.h"
#include "llvm/Support/FileSystem.h"
#include "llvm/Support/raw_ostream.h"
#include <chrono>
#include <filesystem>
#include <thread>
#include <random>
#include <algorithm>

namespace nex {
llvm::json::Value profileNative(const Program &p,const BuildResult &built,llvm::json::Value graph,const ProfileOptions &options){
  auto directory=std::filesystem::path(createTemporaryDirectory("nex-profile")),raw=directory/"runtime.json";
  try{
    // env is launched directly, with no shell expansion. Override a parent's
    // Tracy setting: local reports never start a profiler listener implicitly.
    auto started=std::chrono::system_clock::now();
    std::vector<std::string> arguments{"env","NEX_TRACY=0","NEX_PROFILE_OUTPUT="+raw.string(),"NEX_PROFILE_EVENTS="+std::to_string(options.events),built.executable};arguments.insert(arguments.end(),options.arguments.begin(),options.arguments.end());auto process=capture(arguments,options.timeout);
    if(!std::filesystem::is_regular_file(raw)||std::filesystem::file_size(raw)>256*1024*1024)throw Error("E_PROFILE","profile runtime did not produce a bounded report; process stderr: "+process.errors);
    auto parsed=llvm::json::parse(readFile(raw.string()));
    if(!parsed)throw Error("E_PROFILE","profile runtime produced invalid JSON");
    auto report=parsed->getAsObject();auto functions=report?report->getArray("functions"):nullptr;
    if(!report||report->getString("schema")!="nex.profile-runtime/1"||!functions)throw Error("E_PROFILE","incompatible profile runtime report");
    auto identity=report->getObject("build");
    if(!identity||identity->getString("revision")!=revision(p)||identity->getString("build_key")!=built.key)throw Error("E_PROFILE","measured build identity does not match the selected revision");
    auto nodes=graph.getAsObject()->getArray("nodes");
    std::map<std::string,const llvm::json::Object*> nodeIndex;
    for(const auto &node:*nodes)nodeIndex.emplace(node.getAsObject()->getString("name")->str(),node.getAsObject());
    auto manifest=llvm::json::parse(readFile((std::filesystem::path(built.executable).parent_path()/"debug.json").string()));
    if(!manifest||!manifest->getAsObject())throw Error("E_PROFILE","invalid profile debug manifest");
    std::map<std::string,std::string> sourcePaths;
    if(auto sources=manifest->getAsObject()->getArray("sources"))for(const auto &source:*sources){
      if(auto value=source.getAsObject())if(auto anchor=value->getString("debug_path"))
        if(auto projection=value->getString("projection"))sourcePaths[anchor->str()]=projection->str();
    }
    for(auto &value:*functions){
      auto function=value.getAsObject();bool matched=false;
      auto name=function?function->getString("name"):std::nullopt;
      if(name&&nodeIndex.contains(name->str())){const auto &node=*nodeIndex.at(name->str());
        if(function->getString("content_hash")==node.getString("hash")){
          (*function)["node_id"]=node.getString("id")->str();(*function)["source_file"]=node.getString("file")->str();matched=true;
        }
      }
      if(!matched)throw Error("E_PROFILE","measured function does not match the selected graph revision");
      if(auto file=function->getString("file");file&&sourcePaths.contains(file->str())){
        auto anchor=file->str();(*function)["debug_path"]=anchor;(*function)["file"]=sourcePaths.at(anchor);
      }
    }
    auto sinceEpoch=std::chrono::duration_cast<std::chrono::milliseconds>(started.time_since_epoch()).count();
    (*report)["schema"]="nex.profile/1";(*report)["ok"]=process.code==0;(*report)["exit_code"]=process.code;
    (*report)["stdout"]=process.output;(*report)["stderr"]=process.errors;(*report)["revision"]=revision(p);(*report)["build_key"]=built.key;
    (*report)["toolchain"]=NEX_VERSION;(*report)["language"]=languageVersion;(*report)["profile"]="profile";
    (*report)["started_unix_ms"]=int64_t(sinceEpoch);(*report)["scenario"]=options.scenario;
    (*report)["hardware"]=llvm::json::Object{{"target",llvm::sys::getDefaultTargetTriple()},{"cpu",llvm::sys::getHostCPUName().str()},{"hardware_threads",std::thread::hardware_concurrency()}};
    (*report)["limits"]=llvm::json::Object{{"events",options.events},{"functions",16384},{"stack_frames_per_thread",4096},{"live_allocations",1000000},{"timeout_seconds",options.timeout}};
    (*report)["measurement"]=llvm::json::Object{{"time","instrumented elapsed wall time, including instrumentation"},{"memory","managed handle/object shallow sizes; excludes dynamic buffers, shared_ptr control blocks and allocator overhead"},{"coverage","reachable native NEX functions and managed runtime allocations"}};
    auto output=options.output;
    if(output.empty()){
      auto folder=std::filesystem::path(built.executable).parent_path()/"profiles";std::filesystem::create_directories(folder);
      int fd;auto path=folder/("run-"+std::to_string(std::random_device{}())+"-"+std::to_string(std::random_device{}())+".json");
      if(auto ec=llvm::sys::fs::openFileForWrite(path.string(),fd,llvm::sys::fs::CD_CreateNew))throw Error("E_FILE",ec.message());
      llvm::raw_fd_ostream stream(fd,true);stream.close();output=path.string();
    }
    output=std::filesystem::absolute(output).string();(*report)["output"]=output;
    writeFile(output,json(*parsed)+"\n");std::filesystem::remove_all(directory);
    // Keep the agent response bounded. The saved report retains all measured
    // functions and timeline events; its path is the detailed result.
    report->erase("traceEvents");
    auto summary=std::move(*report->getArray("functions"));
    std::sort(summary.begin(),summary.end(),[](const auto &a,const auto &b){return *a.getAsObject()->getInteger("self_ns")>*b.getAsObject()->getInteger("self_ns");});
    (*report)["total_functions"]=summary.size();
    while(summary.size()>100)summary.pop_back();
    (*report)["functions"]=std::move(summary);
    (*report)["schema"]="nex.profile-session/1";return std::move(*parsed);
  }catch(...){std::filesystem::remove_all(directory);throw;}
}
}
