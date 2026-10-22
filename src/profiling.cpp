#include "nex/profiling.h"
#include "nex/task_process.h"
#include "llvm/TargetParser/Host.h"
#include "llvm/Support/FileSystem.h"
#include "llvm/Support/raw_ostream.h"
#include <chrono>
#include <filesystem>
#include <thread>
#include <random>
#include <algorithm>
#include <exception>

namespace nex {
namespace {
bool cleanupProfileDirectory(const std::filesystem::path &directory)noexcept{
  // A forcibly stopped FFI image can leave its snapshot directories sealed0500.
  // Restore access only to owned directories; do not follow symbolic links.
  try{
    namespace fs=std::filesystem;std::error_code ec;
    auto status=fs::symlink_status(directory,ec);if(ec==std::errc::no_such_file_or_directory)return true;
    if(ec||!fs::is_directory(status))return false;
    fs::permissions(directory,fs::perms::owner_all,fs::perm_options::add|fs::perm_options::nofollow,ec);if(ec)return false;
    for(fs::recursive_directory_iterator it(directory,ec),end;!ec&&it!=end;it.increment(ec)){
      auto item=it->symlink_status(ec);if(ec)return false;
      if(fs::is_directory(item))fs::permissions(it->path(),fs::perms::owner_all,fs::perm_options::add|fs::perm_options::nofollow,ec);
      if(ec)return false;
    }
    if(ec)return false;fs::remove_all(directory,ec);return !ec;
  }catch(...){return false;}
}
}
llvm::json::Value profileNative(const Program &p,const BuildResult &built,llvm::json::Value graph,const ProfileOptions &options){
  auto metadata=llvm::json::parse(readFile((std::filesystem::path(built.executable).parent_path()/"build.json").string()));
  if(metadata&&metadata->getAsObject())if(auto requirements=metadata->getAsObject()->getObject("runtime_requirements");requirements&&requirements->getBoolean("tasks").value_or(false))
    throw Error("E_TASK_UNIMPLEMENTED","source task profile attribution is not implemented");
  auto directory=std::filesystem::path(createTemporaryDirectory("nex-profile")),raw=directory/"runtime.json";
  try{
    auto nativeTemporary=directory/"native-tmp";std::filesystem::create_directory(nativeTemporary);
    // env is launched directly, with no shell expansion. Override a parent's
    // Tracy setting: local reports never start a profiler listener implicitly.
    auto started=std::chrono::system_clock::now();
    std::vector<std::string> arguments{"env","NEX_TRACY=0","NEX_PROFILE_OUTPUT="+raw.string(),"NEX_PROFILE_EVENTS="+std::to_string(options.events),"TMPDIR="+nativeTemporary.string()};arguments.insert(arguments.end(),options.launcher.begin(),options.launcher.end());arguments.push_back(built.executable);arguments.insert(arguments.end(),options.arguments.begin(),options.arguments.end());
    ProcessResult process;
    {
      auto workingDirectory=options.directory.empty()?std::filesystem::current_path().string():options.directory;
      auto child=runTaskProcess(arguments,workingDirectory,options.environment,options.timeout,(directory/"logs").string());
      if(child.interrupted&&options.interrupted)options.interrupted(child.interrupted);
      if(child.interrupted)throw Error("E_PROFILE_INTERRUPTED","profile process interrupted by signal "+std::to_string(child.interrupted));
      if(child.timedOut)throw Error("E_PROFILE_TIMEOUT","profile process exhausted its timeout");
      if(child.outputLimit)throw Error("E_PROFILE_OUTPUT","profile process exhausted its output limit");
      process=std::move(child.process);if(child.timedOut)process.code=124;else if(child.outputLimit)process.code=125;
    }
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
          auto id=node.getString("id");(*function)["node_id"]=id?llvm::json::Value(id->str()):llvm::json::Value(nullptr);
          if(!id)(*function)["identity_scope"]="captured_project";
          (*function)["source_file"]=node.getString("file")->str();matched=true;
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
    if(options.additionalEvidence)(*report)["workload"]=options.additionalEvidence();
    auto output=options.output;
    if(output.empty()){
      auto folder=std::filesystem::path(built.executable).parent_path()/"profiles";std::filesystem::create_directories(folder);
      int fd;auto path=folder/("run-"+std::to_string(std::random_device{}())+"-"+std::to_string(std::random_device{}())+".json");
      if(auto ec=llvm::sys::fs::openFileForWrite(path.string(),fd,llvm::sys::fs::CD_CreateNew))throw Error("E_FILE",ec.message());
      llvm::raw_fd_ostream stream(fd,true);stream.close();output=path.string();
    }
    output=std::filesystem::absolute(output).string();(*report)["output"]=output;
    writeFile(output,json(*parsed)+"\n");if(!cleanupProfileDirectory(directory))throw Error("E_PROFILE_CLEANUP","cannot clean owned profile temporary files");
    // Keep the agent response bounded. The saved report retains all measured
    // functions and timeline events; its path is the detailed result.
    report->erase("traceEvents");
    auto summary=std::move(*report->getArray("functions"));
    std::sort(summary.begin(),summary.end(),[](const auto &a,const auto &b){return *a.getAsObject()->getInteger("self_ns")>*b.getAsObject()->getInteger("self_ns");});
    (*report)["total_functions"]=summary.size();
    while(summary.size()>100)summary.pop_back();
    (*report)["functions"]=std::move(summary);
    (*report)["schema"]="nex.profile-session/1";return std::move(*parsed);
  }catch(...){auto original=std::current_exception();if(!cleanupProfileDirectory(directory))throw Error("E_PROFILE_CLEANUP","cannot clean owned profile temporary files after failure");std::rethrow_exception(original);}
}
}
