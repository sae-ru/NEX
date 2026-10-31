#include "nex/profiling.h"
#include "nex/task_process.h"
#include "nex/task_limits.h"
#include "nex/native_toolchain.h"
#include "nex/incremental.h"
#include "nex/native_images.h"
#include "llvm/Support/SHA256.h"
#include "llvm/ADT/StringExtras.h"
#include "llvm/TargetParser/Host.h"
#include "llvm/Support/FileSystem.h"
#include "llvm/Support/raw_ostream.h"
#include <chrono>
#include <filesystem>
#include <thread>
#include <random>
#include <algorithm>
#include <exception>
#include <set>

namespace nex {

namespace {
struct ProviderProfileBuild {
  NativeTaskProfileCatalog catalog;
  llvm::json::Object provenance;
  std::map<std::string,std::string> pins;
};
ProviderProfileBuild providerProfileBuild(const BuildResult &built,const llvm::json::Object &metadata){
  namespace fs=std::filesystem;using Object=llvm::json::Object;using JSON=llvm::json::Value;
  ProviderProfileBuild result;const auto folder=fs::path(built.executable).parent_path();
  auto fail=[](const std::string &message){throw Error("E_PROFILE","invalid measured provider build: "+message);};
  auto read=[&](const fs::path &path){if(path.lexically_normal()!=path||!path.is_absolute())fail("invalid input path");fs::path current;for(const auto &part:path){current/=part;if(fs::is_symlink(current))fail("symlink input");}if(!fs::is_regular_file(path)||fs::file_size(path)>512ULL*1048576)fail("missing/oversized input");auto bytes=readFile(path.string());result.pins[fs::path(path).make_preferred().string()]=hash(bytes);return bytes;};
  auto object=[&](const fs::path &path){auto parsed=llvm::json::parse(read(path));if(!parsed||!parsed->getAsObject())fail("invalid JSON input");return Object(*parsed->getAsObject());};
  auto text=[&](const Object &value,const char *key){auto item=value.getString(key);if(!item)fail(std::string("missing ")+key);return item->str();};
  auto sha=[](const std::string &bytes){return llvm::toHex(llvm::SHA256::hash(llvm::arrayRefFromStringRef(bytes)),true);};
  if(metadata.getString("completion_schema")!="nex.native-completion/6")fail("profile providers require completion6");
  std::string completion=built.key;
  for(const auto &path:{fs::path(built.executable),folder/"program.mlir",folder/"program.ll",folder/"compilation.json",folder/"build.json",folder/"source-bundle.json"})completion+=hash(read(path));
  for(const auto &name:nativeCompletionInputs(metadata))completion+=hash(read(folder/name));
  if(read(folder/"complete")!=hash(completion)+"\n")fail("completion differs");(void)read(folder/"debug.json");
  auto providerJSON=object(folder/"task-provider.json");auto provider=parseNativeTaskProvider(JSON(Object(providerJSON)));
  if(!provider.profiling||metadata.getString("task_provider_hash")!=result.pins.at((folder/"task-provider.json").string())||!metadata.get("task_provider")||*metadata.get("task_provider")!=JSON(Object(providerJSON)))fail("application provider pin differs");
  auto own=parseNativeTaskProfileCatalog(JSON(object(folder/"task-profile-catalog.json")));
  auto abi=object(folder/"library-abi.json");auto libraries=abi.getArray("static_libraries");
  if(!libraries||libraries->size()>128||abi.getString("abi")!=provider.cohort)fail("static archive inventory differs");
  for(size_t index=0;index<libraries->size();++index){auto row=(*libraries)[index].getAsObject();if(!row)fail("invalid static archive row");
    auto prefix="libraries/"+std::to_string(index);auto archive=(folder/(prefix+".a")).make_preferred(),sidecar=(folder/(prefix+".task-provider.json")).make_preferred(),catalog=(folder/(prefix+".task-profile-catalog.json")).make_preferred();
    if(fs::path(text(*row,"path"))!=archive||fs::path(text(*row,"task_provider_path"))!=sidecar||fs::path(text(*row,"task_profile_catalog_path"))!=catalog||
       !result.pins.contains(archive.string())||!result.pins.contains(sidecar.string())||!result.pins.contains(catalog.string())||
       text(*row,"hash")!=result.pins.at(archive.string())||text(*row,"task_provider_hash")!=result.pins.at(sidecar.string())||text(*row,"task_profile_catalog_hash")!=result.pins.at(catalog.string()))fail("static archive/profile raw pins differ");
    auto recorded=row->get("task_provider");if(!recorded||*recorded!=JSON(object(sidecar)))fail("static provider inventory differs");
  }
  std::map<std::string,std::set<std::string>> definitions;
  if(provider.mode==NativeTaskLinkageMode::SharedFixed){for(const auto &[name,component]:provider.definitionOwners)definitions[component].insert(name);}
  else{
    definitions.emplace(provider.component,provider.definitions);
    auto expected=own;expected.registries.clear();
    for(const auto &registry:own.registries)if(registry.component==provider.component)expected.registries.push_back(registry);
    for(const auto &name:nativeCompletionInputs(metadata))if(name.starts_with("libraries/")&&name.ends_with(".task-provider.json")){
      auto stage=parseNativeTaskProvider(JSON(object(folder/name)));
      if(stage.mode!=NativeTaskLinkageMode::Static||!stage.codeOnly||stage.cohort!=provider.cohort||stage.language!=provider.language||
         !definitions.emplace(stage.component,stage.definitions).second)fail("static profile stage owner differs");
      auto catalogName=name.substr(0,name.size()-std::string(".task-provider.json").size())+".task-profile-catalog.json";
      auto catalog=parseNativeTaskProfileCatalog(JSON(object(folder/catalogName)));
      validateTaskProfileCatalogOwnership(stage,catalog,{{stage.component,stage.definitions}});
      for(auto registry:catalog.registries){registry.ownerImage=provider.component;expected.registries.push_back(std::move(registry));}
    }
    if(definitions.size()!=libraries->size()+1)fail("static archive owner cardinality differs");
    std::sort(expected.registries.begin(),expected.registries.end(),[](const auto &a,const auto &b){return a.component<b.component;});
    if(json(nativeTaskProfileCatalogJSON(expected),false)!=json(nativeTaskProfileCatalogJSON(own),false))fail("static final catalog differs from captured stages");
  }
  validateTaskProfileCatalogOwnership(provider,own,definitions);
  if(own.artifact!=NativeTaskArtifactKind::Application)fail("application catalog differs");
  result.catalog=own;llvm::json::Array images;
  auto application=read(built.executable);
  images.push_back(Object{{"component",provider.component},{"kind","application"},{"key",built.key},{"hash",hash(application)},{"sha256",sha(application)},{"uuid",nativeImageUUID(built.executable)},
    {"provider_hash",result.pins.at((folder/"task-provider.json").string())},{"catalog_hash",nativeTaskProfileInfo(own).catalogHash}});
  const bool shared=provider.mode==NativeTaskLinkageMode::SharedFixed;
  if(shared){
    auto input=object(folder/"image-inputs.json");auto inventory=input.getArray("images"),providers=input.getArray("task_providers"),catalogs=input.getArray("task_profile_catalogs");
    if(input.size()!=5||input.getString("schema")!="nex.native-image-inputs/3"||!inventory||inventory->empty()||inventory->size()>129||!providers||!catalogs||providers->size()!=catalogs->size()||providers->size()+1!=inventory->size())fail("image/catalog closure differs");
    std::map<std::string,const Object*> providerRows,catalogRows;
    for(const auto &row:*providers){auto value=row.getAsObject();if(!value||value->size()!=4||!providerRows.emplace(text(*value,"image"),value).second)fail("duplicate provider pin");}
    for(const auto &row:*catalogs){auto value=row.getAsObject();if(!value||value->size()!=5||!catalogRows.emplace(text(*value,"image"),value).second)fail("duplicate catalog pin");}
    size_t runtimeCount=0;std::set<std::string> seen;
    for(const auto &value:*inventory){auto row=value.getAsObject();if(!row)fail("invalid image row");auto path=fs::path(text(*row,"path"));auto relative=(path.extension()==".dll"?"":"images/")+path.filename().string();
      if(path!=folder/relative||!seen.insert(relative).second)fail("image path differs");auto bytes=read(path);auto kind=text(*row,"kind");
      if(hash(bytes)!=text(*row,"hash")||sha(bytes)!=text(*row,"sha256")||nativeImageUUID(path.string())!=text(*row,"uuid"))fail("physical image differs");
      if(kind=="runtime"){if(!provider.image||provider.image->runtimeKey!=text(*row,"key")||provider.image->runtimeDigest!=hash(bytes))fail("runtime image pin differs");++runtimeCount;images.push_back(Object{{"component","runtime"},{"kind","runtime"},{"key",text(*row,"key")},{"hash",hash(bytes)},{"sha256",sha(bytes)},{"uuid",text(*row,"uuid")},{"provider_hash",nullptr},{"catalog_hash",nullptr}});continue;}
      if(kind!="library"||!providerRows.contains(relative)||!catalogRows.contains(relative))fail("missing code-image catalog/provider");
      const auto &pin=*providerRows.at(relative),&catalogPin=*catalogRows.at(relative);auto providerPath=text(pin,"path"),catalogPath=text(catalogPin,"path");
      if(providerPath!=relative+".task-provider.json"||catalogPath!=relative+".task-profile-catalog.json")fail("image companion path differs");
      auto info=parseNativeTaskProvider(JSON(object(folder/providerPath)));auto catalog=parseNativeTaskProfileCatalog(JSON(object(folder/catalogPath)));
      std::map<std::string,std::set<std::string>> imageDefinitions;for(const auto &[name,component]:info.definitionOwners)imageDefinitions[component].insert(name);
      validateTaskProfileCatalogOwnership(info,catalog,imageDefinitions);
      if(result.pins.at((folder/providerPath).make_preferred().string())!=text(pin,"hash")||result.pins.at((folder/catalogPath).make_preferred().string())!=text(catalogPin,"hash")||!info.profiling||!info.image||
         nativeTaskProfileInfo(catalog).catalogHash!=info.profiling->catalogHash||info.profiling->catalogHash!=text(catalogPin,"catalog_hash")||info.component!=text(pin,"component")||info.component!=text(catalogPin,"component")||catalog.ownerImage!=info.component||
         info.image->key!=text(*row,"key")||info.image->digest!=hash(bytes)||info.image->sha256!=sha(bytes)||info.image->uuid!=text(*row,"uuid")||!provider.image||info.image->runtimeKey!=provider.image->runtimeKey||info.image->runtimeDigest!=provider.image->runtimeDigest)fail("image profile identity differs");
      for(const auto &registry:catalog.registries)result.catalog.registries.push_back(registry);
      images.push_back(Object{{"component",info.component},{"kind","shared-image"},{"key",info.image->key},{"hash",hash(bytes)},{"sha256",sha(bytes)},{"uuid",info.image->uuid},{"provider_hash",text(pin,"hash")},{"catalog_hash",info.profiling->catalogHash}});
    }
    if(runtimeCount!=1)fail("runtime closure differs");
    if(!provider.image||provider.image->key!=built.key||provider.image->digest!=hash(application)||provider.image->sha256!=sha(application)||provider.image->uuid!=nativeImageUUID(built.executable))fail("application image pin differs");
  }
  std::sort(result.catalog.registries.begin(),result.catalog.registries.end(),[](const auto &a,const auto &b){return a.component<b.component;});
  const auto semantic=nativeTaskProfileInfo(result.catalog).catalogHash;
  if(metadata.getString("task_profile_catalog")!=semantic)fail("root registry union differs");
  result.provenance=Object{{"schema","nex.task-provider-profile/1"},{"runtime_linkage",shared?"shared":"embedded"},{"catalog_hash",semantic},{"catalog",nativeTaskProfileCatalogJSON(result.catalog)},{"images",std::move(images)}};
  return result;
}
void verifyProfilePins(const std::map<std::string,std::string> &pins){for(const auto &[path,digest]:pins)if(hash(readFile(path))!=digest)throw Error("E_PROFILE","measured provider input changed during execution: "+path);}
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
llvm::json::Object inspectTaskProfileBuildInputs(const BuildResult &built){
  auto parsed=llvm::json::parse(readFile((std::filesystem::path(built.executable).parent_path()/"build.json").string()));
  if(!parsed||!parsed->getAsObject())throw Error("E_PROFILE","invalid provider profile build metadata");
  auto checked=providerProfileBuild(built,*parsed->getAsObject());llvm::json::Object pins;
  for(const auto &[path,digest]:checked.pins)pins[path]=digest;
  return llvm::json::Object{{"provenance",std::move(checked.provenance)},{"pins",std::move(pins)}};
}
llvm::json::Object validateTaskProfileSourceUnion(const NativeTaskProfileCatalog &catalog,const TaskProfileSourceUnion &sources){
  llvm::json::Object result;
  for(const auto &registry:catalog.registries){
    auto checked=sources.find(registry.component);if(checked==sources.end())throw Error("E_PROFILE","provider catalog has no checked source component: "+registry.component);
    const auto &component=checked->second;const auto &program=component.program;std::set<std::string> found;
    for(const auto &site:registry.sites){
      if(!found.insert(site.name).second||result.get(site.name)||!component.definitions.contains(site.name))throw Error("E_PROFILE","provider catalog definition ownership differs: "+site.name);
      const auto &function=program.function(site.name);auto unit=program.units.find(function.unit);
      const auto &source=unit==program.units.end()?program.source:unit->second.source;
      const auto &module=unit==program.units.end()?program.module:unit->second.module;
      auto anchor=hash(json(llvm::json::Array{"nex.native-source-anchor/2",module},false));
      auto path=std::filesystem::path(site.debugPath);
      auto plan=planNative(program,site.name,{},true);std::string contract;
      for(const auto &entry:plan.units)if(entry.identity==site.name){auto parsed=llvm::json::parse(entry.contract);if(!parsed||!parsed->getAsObject())throw Error("E_PROFILE","invalid checked native profile contract");parsed->getAsObject()->erase("unit");contract=hash(json(*parsed,false));break;}
      if(site.functionHash!=hash(json(canonical(function),false))||site.functionSourceHash!=hash(program.definition(function))||site.sourceUnitHash!=hash(source)||
         site.line!=int64_t(function.span.line)||site.contract!=component.definitions.at(site.name)||site.contract!=contract||
         !path.is_absolute()||path.lexically_normal()!=path||path.filename()!="source.nex"||path.parent_path().filename()!=anchor||path.parent_path().parent_path().filename()!="source-anchors")
        throw Error("E_PROFILE","provider profile source/site contract differs: "+site.name);
      result[site.name]=llvm::json::Object{{"component",registry.component},{"owner_image",registry.ownerImage},{"source_file",function.unit},
        {"source_unit_hash",site.sourceUnitHash},{"function_source_hash",site.functionSourceHash},{"contract",site.contract},{"source_revision",revision(program)},
        {"projection",(path.parent_path().parent_path().parent_path()/"source-cache"/hash(json(llvm::json::Object{{"schema","nex.native-source/2"},{"module",module},{"source",source}},false))/"source.nex").string()}};
    }
    if(found.size()!=component.definitions.size())throw Error("E_PROFILE","provider catalog omits checked definitions: "+registry.component);
  }
  return result;
}
llvm::json::Value profileNative(const Program &p,const BuildResult &built,llvm::json::Value graph,const ProfileOptions &options){
  auto metadata=llvm::json::parse(readFile((std::filesystem::path(built.executable).parent_path()/"build.json").string()));
  auto buildMetadata=metadata?metadata->getAsObject():nullptr;
  if(!buildMetadata)throw Error("E_PROFILE","invalid measured build metadata");
  auto requirements=buildMetadata->getObject("runtime_requirements");
  bool tasks=requirements&&requirements->getBoolean("tasks").value_or(false);
  const auto providerMetadata=buildMetadata->getObject("task_provider");
  const bool providers=tasks&&providerMetadata&&providerMetadata->getObject("profiling");
  std::optional<ProviderProfileBuild> providerBuild;llvm::json::Object providerSites;
  std::optional<nexrt::TaskExecutionLimits> configured,effective;
  llvm::json::Object expectedIdentity;
  if(tasks){
#if !defined(__APPLE__) && !defined(__linux__) && !defined(_WIN32)
    throw Error("E_TASK_PROFILE","task profiling requires a macOS/Linux/Windows host executable");
#endif
    if(buildMetadata->getString("profile")!="profile"||buildMetadata->getString("final_kind")!="executable"||
       buildMetadata->getString("revision")!=revision(p)||buildMetadata->getString("key")!=built.key||
       buildMetadata->getString("compiler_build")!=NEX_BUILD_ID)
      throw Error("E_PROFILE","task profile build metadata does not match the selected executable");
    requireNativeHost(built);
    auto limits=buildMetadata->get("task_limits");if(!limits)throw Error("E_PROFILE","task profile build omitted its limits");
    configured=parseTaskLimitsJSON(*limits,"E_PROFILE");auto arguments=options.arguments;arguments.insert(arguments.begin(),built.executable);
    effective=taskEffectiveLimits(*configured,arguments);
    auto entry=buildMetadata->getString("entry");if(!entry)throw Error("E_PROFILE","task profile build omitted its entry");
    expectedIdentity=llvm::json::Object{{"schema","nex.profile-build/1"},{"toolchain",NEX_VERSION},{"language",programLanguage(p)},
      {"revision",revision(p)},{"build_key",built.key},{"compiler_build",NEX_BUILD_ID},{"source_hash",hash(json(sourceBundle(p),false))},
      {"entry",p.function(entry->str()).name},{"task_limits",taskLimitsJSON(*configured)}};
    if(providers){
      if(!options.taskProviderSources)throw Error("E_PROFILE","provider profiling requires its checked component source union");
      providerBuild=providerProfileBuild(built,*buildMetadata);providerSites=validateTaskProfileSourceUnion(providerBuild->catalog,*options.taskProviderSources);
      for(const auto &[name,value]:providerSites){(void)name;auto row=value.getAsObject();auto path=row->getString("projection")->str();auto data=readFile(path);if(hash(data)!=row->getString("source_unit_hash"))throw Error("E_PROFILE","profile source projection differs");providerBuild->pins[path]=hash(data);}
      expectedIdentity["schema"]="nex.profile-build/2";expectedIdentity["task_profile_catalog"]=nativeTaskProfileInfo(providerBuild->catalog).catalogHash;
    }
  }
  auto directory=std::filesystem::path(createTemporaryDirectory("nex-profile")),raw=directory/"runtime.json";
  try{
    auto nativeTemporary=directory/"native-tmp";std::filesystem::create_directory(nativeTemporary);
    // Pass an explicit child environment through the native supervisor.
    // Local reports never start a profiler listener implicitly.
    auto started=std::chrono::system_clock::now();
    auto childEnvironment=options.environment;
    childEnvironment["NEX_TRACY"]="0";childEnvironment["NEX_PROFILE_OUTPUT"]=raw.string();
    childEnvironment["NEX_PROFILE_EVENTS"]=std::to_string(options.events);childEnvironment["TMPDIR"]=nativeTemporary.string();
#ifdef _WIN32
    childEnvironment["TEMP"]=nativeTemporary.string();childEnvironment["TMP"]=nativeTemporary.string();
#endif
    auto arguments=options.launcher;arguments.push_back(built.executable);arguments.insert(arguments.end(),options.arguments.begin(),options.arguments.end());
    ProcessResult process;
    {
      auto workingDirectory=options.directory.empty()?std::filesystem::current_path().string():options.directory;
      auto child=runTaskProcess(arguments,workingDirectory,childEnvironment,options.timeout,(directory/"logs").string());
      if(child.interrupted&&options.interrupted)options.interrupted(child.interrupted);
      if(child.interrupted)throw Error("E_PROFILE_INTERRUPTED","profile process interrupted by signal "+std::to_string(child.interrupted));
      if(child.timedOut)throw Error("E_PROFILE_TIMEOUT","profile process exhausted its timeout");
      if(child.outputLimit)throw Error("E_PROFILE_OUTPUT","profile process exhausted its output limit");
      process=std::move(child.process);if(child.timedOut)process.code=124;else if(child.outputLimit)process.code=125;
    }
    if(providerBuild)verifyProfilePins(providerBuild->pins);
    if(!std::filesystem::is_regular_file(raw)||std::filesystem::file_size(raw)>(tasks?64u:256u)*1024*1024)throw Error("E_PROFILE","profile runtime did not produce a bounded report; process stderr: "+process.errors);
    llvm::json::Value parsed=nullptr;
    if(tasks)parsed=parseTaskProfileRuntimeReport(readFile(raw.string()));
    else{auto value=llvm::json::parse(readFile(raw.string()));if(!value)throw Error("E_PROFILE","profile runtime produced invalid JSON");parsed=std::move(*value);}
    auto report=parsed.getAsObject();auto functions=report?report->getArray("functions"):nullptr;
    if(!report||report->getString("schema")!=(providers?"nex.profile-runtime/3":tasks?"nex.profile-runtime/2":"nex.profile-runtime/1")||!functions)throw Error("E_PROFILE","incompatible profile runtime report");
    if(tasks)validateTaskProfileRuntimeReport(*report,expectedIdentity,*effective,providerBuild?&providerBuild->catalog:nullptr);
    auto identity=report->getObject("build");
    if(!identity||identity->getString("revision")!=revision(p)||identity->getString("build_key")!=built.key)throw Error("E_PROFILE","measured build identity does not match the selected revision");
    auto nodes=graph.getAsObject()->getArray("nodes");
    std::map<std::string,const llvm::json::Object*> nodeIndex;
    for(const auto &node:*nodes)nodeIndex.emplace(node.getAsObject()->getString("name")->str(),node.getAsObject());
    auto manifest=llvm::json::parse(readFile((std::filesystem::path(built.executable).parent_path()/"debug.json").string()));
    if(!manifest||!manifest->getAsObject())throw Error("E_PROFILE","invalid profile debug manifest");
    if(tasks){auto &m=*manifest->getAsObject();
      if(m.getString("revision")!=revision(p)||m.getString("build_key")!=built.key||m.getString("compiler_build")!=NEX_BUILD_ID||
         m.getString("source_hash")!=hash(json(sourceBundle(p),false))||m.getString("language")!=programLanguage(p))
        throw Error("E_PROFILE","task profile source manifest differs from the selected build");
    }
    std::map<std::string,std::string> sourcePaths,sourceHashes;
    if(auto sources=manifest->getAsObject()->getArray("sources"))for(const auto &source:*sources){
      if(auto value=source.getAsObject())if(auto anchor=value->getString("debug_path"))
        if(auto projection=value->getString("projection")){sourcePaths[anchor->str()]=projection->str();if(auto digest=value->getString("hash"))sourceHashes[anchor->str()]=digest->str();}
    }
    for(auto &value:*functions){
      auto function=value.getAsObject();bool matched=false;
      auto name=function?function->getString("name"):std::nullopt;
      auto selectedName=name?name->str():std::string{};
      if(name&&nodeIndex.contains(selectedName)){const auto &node=*nodeIndex.at(selectedName);
        if(function->getString("content_hash")==node.getString("hash")){
          auto id=node.getString("id");(*function)["node_id"]=id?llvm::json::Value(id->str()):llvm::json::Value(nullptr);
          if(!id)(*function)["identity_scope"]="captured_project";
          (*function)["source_file"]=node.getString("file")->str();matched=true;
        }
      }
      if(providers){
        auto checked=providerSites.getObject(selectedName);if(!checked)throw Error("E_PROFILE","measured provider function has no checked source owner");
        if(!matched){(*function)["node_id"]=nullptr;(*function)["identity_scope"]="captured_project_component";matched=true;}
        (*function)["provider_component"]=checked->getString("component")->str();(*function)["owner_image"]=checked->getString("owner_image")->str();
        (*function)["source_file"]=checked->getString("source_file")->str();(*function)["source_revision"]=checked->getString("source_revision")->str();
        (*function)["debug_path"]=function->getString("file")->str();(*function)["file"]=checked->getString("projection")->str();
      }
      if(!matched)throw Error("E_PROFILE","measured function does not match the selected graph revision");
      if(tasks&&!providers){const auto &selected=p.function(selectedName);auto file=function->getString("file");
        auto source=p.units.contains(selected.unit)?p.units.at(selected.unit).source:p.source;
        if(!file||!sourceHashes.contains(file->str())||sourceHashes.at(file->str())!=hash(source)||function->getInteger("line")!=int64_t(selected.span.line))
          throw Error("E_PROFILE","task profile site source/line differs from the selected function");
      }
      if(auto file=function->getString("file");file&&sourcePaths.contains(file->str())){
        auto anchor=file->str();(*function)["debug_path"]=anchor;(*function)["file"]=sourcePaths.at(anchor);
      }
    }
    auto sinceEpoch=std::chrono::duration_cast<std::chrono::milliseconds>(started.time_since_epoch()).count();
    (*report)["schema"]=providers?"nex.profile/3":tasks?"nex.profile/2":"nex.profile/1";(*report)["ok"]=process.code==0;(*report)["exit_code"]=process.code;
    if(providerBuild)(*report)["task_provider_profile"]=llvm::json::Object(providerBuild->provenance);
    (*report)["stdout"]=process.output;(*report)["stderr"]=process.errors;(*report)["revision"]=revision(p);(*report)["build_key"]=built.key;
    (*report)["toolchain"]=NEX_VERSION;(*report)["language"]=programLanguage(p);(*report)["profile"]="profile";
    (*report)["started_unix_ms"]=int64_t(sinceEpoch);(*report)["scenario"]=options.scenario;
    (*report)["hardware"]=llvm::json::Object{{"target",llvm::sys::getDefaultTargetTriple()},{"cpu",llvm::sys::getHostCPUName().str()},{"hardware_threads",std::thread::hardware_concurrency()}};
    if(tasks){(*report)["task_execution"]=taskExecutionJSON(*configured,*effective,"native",options.timeout);
      (*report->getObject("limits"))["timeout_seconds"]=options.timeout;
      (*report)["measurement"]=llvm::json::Object{{"time","source thread CPU and active elapsed segments; overlapping logical invocation lifetime; process duration is wall time"},
        {"scheduler","ready queue, blocked reason and physical drain wall intervals; executor CPU includes driver/cleanup overhead"},
        {"memory","allocation-site managed handle/object shallow sizes; excludes Value aliases, dynamic backing, coroutine/scheduler backing and total RAM"},
        {"coverage","reachable native task frames and ordinary helpers; no IO worker CPU or disk service measurement"}};
    }else{
    (*report)["limits"]=llvm::json::Object{{"events",options.events},{"functions",16384},{"stack_frames_per_thread",4096},{"live_allocations",1000000},{"timeout_seconds",options.timeout}};
    (*report)["measurement"]=llvm::json::Object{{"time","instrumented elapsed wall time, including instrumentation"},{"memory","managed handle/object shallow sizes; excludes dynamic buffers, shared_ptr control blocks and allocator overhead"},{"coverage","reachable native NEX functions and managed runtime allocations"}};
    }
    if(options.additionalEvidence)(*report)["workload"]=options.additionalEvidence();
    auto output=options.output;
    if(output.empty()){
      auto folder=std::filesystem::path(built.executable).parent_path()/"profiles";std::filesystem::create_directories(folder);
      int fd;auto path=folder/("run-"+std::to_string(std::random_device{}())+"-"+std::to_string(std::random_device{}())+".json");
      if(auto ec=llvm::sys::fs::openFileForWrite(path.string(),fd,llvm::sys::fs::CD_CreateNew))throw Error("E_FILE",ec.message());
      llvm::raw_fd_ostream stream(fd,true);stream.close();output=path.string();
    }
    output=std::filesystem::absolute(output).string();(*report)["output"]=output;
    std::string serialized;
    if(tasks)serialized=serializeTaskProfileReport(*report,std::filesystem::file_size(raw));
    else serialized=json(parsed);
    writeFile(output,serialized+"\n");if(!cleanupProfileDirectory(directory))throw Error("E_PROFILE_CLEANUP","cannot clean owned profile temporary files");
    // Keep the agent response bounded. The saved report retains all measured
    // functions and timeline events; its path is the detailed result.
    report->erase("traceEvents");
    if(providers){auto &provenance=*report->getObject("task_provider_profile");provenance["total_registries"]=providerBuild->catalog.registries.size();size_t sites=0;for(const auto &registry:providerBuild->catalog.registries)sites+=registry.sites.size();provenance["total_sites"]=sites;provenance.erase("catalog");}
    if(tasks){for(auto key:{"tasks","invocations","segments"}){auto entries=report->getArray(key);(*report)[std::string("total_")+key]=entries?entries->size():0;report->erase(key);}(*report)["function_sort_key"]="self_cpu_ns";}
    auto summary=std::move(*report->getArray("functions"));
    std::sort(summary.begin(),summary.end(),[&](const auto &a,const auto &b){auto key=tasks?"self_cpu_ns":"self_ns";return *a.getAsObject()->getInteger(key)>*b.getAsObject()->getInteger(key);});
    (*report)["total_functions"]=summary.size();
    while(summary.size()>100)summary.pop_back();
    (*report)["functions"]=std::move(summary);
    (*report)["schema"]=providers?"nex.profile-session/3":tasks?"nex.profile-session/2":"nex.profile-session/1";return parsed;
  }catch(...){auto original=std::current_exception();if(!cleanupProfileDirectory(directory))throw Error("E_PROFILE_CLEANUP","cannot clean owned profile temporary files after failure");std::rethrow_exception(original);}
}
}
