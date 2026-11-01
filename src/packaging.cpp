#include "nex/packaging.h"
#include "nex/foreign_catalogue.h"
#include "nex/native_toolchain.h"
#include "nex/native_images.h"
#include "nex/profiling.h"
#include "nex/task_provider_debug.h"
#include "nex/debug_session.h"
#include "llvm/ADT/StringExtras.h"
#include "llvm/Support/FileSystem.h"
#include "llvm/Support/SHA256.h"
#include "llvm/TargetParser/Triple.h"
#include <cstdlib>
#include <filesystem>
#include <algorithm>

namespace nex {
namespace {
std::string sha256(const std::string &bytes){
  auto digest=llvm::SHA256::hash(llvm::ArrayRef<uint8_t>(reinterpret_cast<const uint8_t*>(bytes.data()),bytes.size()));
  return llvm::toHex(digest,true);
}
llvm::json::Value checkedTool(const std::vector<std::string> &command,const std::filesystem::path &request){
  auto result=capture(command,300);
  if(result.code!=0)throw Error("E_PACKAGE","application packaging failed; inputs retained at "+request.parent_path().string()+"\n"+result.errors);
  auto parsed=llvm::json::parse(result.output);
  if(!parsed){llvm::consumeError(parsed.takeError());throw Error("E_PACKAGE","invalid package report; inputs retained at "+request.parent_path().string());}
  return std::move(*parsed);
}
llvm::json::Value packageCapturedArtifact(const Program &candidate,const BuildResult &built,
    const PackageOptions &options,const std::filesystem::path &request,
    const std::string &foreignDirectory,llvm::json::Value projection,llvm::json::Object foreignFiles){
  namespace fs=std::filesystem;auto output=fs::absolute(options.directory).lexically_normal();

  auto bytes=readFile(built.executable);
  auto metadata=llvm::json::parse(readFile((fs::path(built.executable).parent_path()/"build.json").string()));
  if(!metadata){llvm::consumeError(metadata.takeError());throw Error("E_PACKAGE","invalid native build metadata");}
  auto info=metadata->getAsObject();
  if(!info||info->getString("key")!=built.key)throw Error("E_PACKAGE","native build metadata does not match its artifact");
  if(info->getString("compiler_build")!=NEX_BUILD_ID||info->getString("revision")!=revision(candidate)||
     (info->getString("kind")!="executable"&&info->getString("kind")!="http_server"))
    throw Error("E_PACKAGE","packaging requires its matching checked native application artifact");
  if(!foreignDirectory.empty()&&info->getString("foreign_catalogue")!="../foreign/host.json")
    throw Error("E_FFI_PACKAGE","foreign package artifact lacks its executable-relative catalogue default");
  auto buildFolder=fs::path(built.executable).parent_path();
  const bool windows=llvm::Triple(built.target).isOSWindows();auto imagesFolder=windows?buildFolder:buildFolder/"images";std::string complete=built.key;
  for(const auto &file:{fs::path(built.executable),buildFolder/"program.mlir",buildFolder/"program.ll",buildFolder/"compilation.json",buildFolder/"build.json",buildFolder/"source-bundle.json"})complete+=hash(readFile(file.string()));
  for(const auto &name:nativeCompletionInputs(*info))complete+=hash(readFile((buildFolder/name).string()));
  if(readFile((buildFolder/"complete").string())!=hash(complete)+"\n")throw Error("E_PACKAGE","native artifact completion differs before packaging");
  llvm::json::Array owned,taskFiles;
  std::set<fs::path> ownedImagePaths;
  const bool debug=info->getString("completion_schema")=="nex.native-completion/7";
  const bool profiled=info->getString("completion_schema")=="nex.native-completion/6";
  const bool sharedTasks=info->getString("completion_schema")=="nex.native-completion/5"||((profiled||debug)&&info->getString("completion_mode")=="shared-application");
  auto physical=[&](const fs::path &path){
    if(!path.is_absolute()||path.lexically_normal()!=path)throw Error("E_PACKAGE","invalid owned native input path");
    fs::path current;for(const auto &part:path){current/=part;if(fs::is_symlink(current))throw Error("E_PACKAGE","symlink in owned native input path");}
    if(!fs::is_regular_file(path))throw Error("E_PACKAGE","owned native input is not a regular file");
  };
  auto taskFile=[&](const std::string &kind,const fs::path &path,const NativeTaskProviderInfo *provider){
    physical(path);auto data=readFile(path.string());
    llvm::json::Object record{{"kind",kind},{"path",path.string()},{"hash",hash(data)},{"sha256",sha256(data)},{"bytes",int64_t(data.size())},
      {"component",nullptr},{"image",nullptr},{"image_key",nullptr},{"image_sha256",nullptr},{"image_uuid",nullptr}};
    if(provider){const bool application=kind=="application_provider"||kind=="application_profile_catalog";
      if(!application&&!provider->image)throw Error("E_PACKAGE","task provider has no physical image");
      auto suffix=kind=="owned_profile_catalog"?std::string(".task-profile-catalog.json"):std::string(".task-provider.json");
      auto image=application?fs::path(built.executable):imagesFolder/path.filename().string().substr(0,path.filename().string().size()-suffix.size());
      record["component"]=provider->component;record["image"]=image.string();
      record["image_key"]=application?built.key:provider->image->key;record["image_sha256"]=sha256(readFile(image.string()));record["image_uuid"]=nativeImageUUID(image.string());}
    taskFiles.push_back(std::move(record));
  };
  if(info->getString("completion_schema")=="nex.native-completion/3"||sharedTasks){
    auto link=llvm::json::parse(readFile((buildFolder/"image-inputs.json").string()));
    auto inventory=link&&link->getAsObject()?link->getAsObject()->getArray("images"):nullptr;
    if(!inventory||inventory->empty()||inventory->size()>129||(sharedTasks&&(link->getAsObject()->getString("schema")!=(debug?"nex.native-image-inputs/4":profiled?"nex.native-image-inputs/3":"nex.native-image-inputs/2")||link->getAsObject()->size()!=(debug?6:profiled?5:4))))throw Error("E_PACKAGE","invalid compiler-owned native image inventory");
    std::set<std::string> expected,seen;std::map<std::string,const llvm::json::Object*> imageRecords;size_t runtimes=0;
    for(const auto &entry:*info->getArray("completion_inputs"))if(entry.getAsObject()->getString("kind")=="owned_image")expected.insert(entry.getAsObject()->getString("path")->str());
    for(const auto &entry:*inventory){
      auto record=entry.getAsObject();if(!record)throw Error("E_PACKAGE","invalid compiler-owned image record");
      auto path=record->getString("path"),digest=record->getString("sha256"),key=record->getString("key"),abi=record->getString("abi"),kind=record->getString("kind"),uuid=record->getString("uuid");
      if(!path||!digest||!key||!abi||!kind||!uuid)throw Error("E_PACKAGE","missing compiler-owned image identity");
      auto relative=(windows?fs::path(path->str()).filename():fs::path("images")/fs::path(path->str()).filename()).generic_string();if(sharedTasks)physical(path->str());
      if(fs::path(path->str())!=buildFolder/relative||!expected.contains(relative)||!seen.insert(relative).second||
         (sharedTasks&&record->getString("hash")!=hash(readFile(path->str())))||sha256(readFile(path->str()))!=*digest||nativeImageUUID(path->str())!=*uuid||*abi!=built.libraryABI)
        throw Error("E_PACKAGE","compiler-owned native image bytes/UUID/path differ");
      imageRecords.emplace(relative,record);runtimes+=*kind=="runtime";
      ownedImagePaths.insert(fs::path(path->str()).lexically_normal());
      owned.push_back(llvm::json::Object{{"path",path->str()},{"sha256",digest->str()},{"key",key->str()},{"abi",abi->str()},{"kind",kind->str()},{"uuid",uuid->str()}});
    }
    if(seen!=expected||(sharedTasks&&runtimes!=1))throw Error("E_PACKAGE","compiler-owned image inventory is incomplete");
    if(sharedTasks&&!profiled&&!debug){
      auto ownPath=buildFolder/"task-provider.json";auto ownBytes=readFile(ownPath.string());auto ownJSON=llvm::json::parse(ownBytes);
      if(!ownJSON)throw Error("E_PACKAGE","invalid task application provider");auto own=parseNativeTaskProvider(*ownJSON);
      auto seed=link->getAsObject()->getObject("inputs");
      if(own.mode!=NativeTaskLinkageMode::SharedFixed||own.artifact!=NativeTaskArtifactKind::Application||!own.image||
         own.image->key!=built.key||own.image->digest!=hash(bytes)||own.image->sha256!=sha256(bytes)||own.image->uuid!=nativeImageUUID(built.executable)||
         !seed||seed->getString("runtime_key")!=own.image->runtimeKey||seed->getString("runtime_hash")!=own.image->runtimeDigest||
         info->getString("task_provider_hash")!=hash(ownBytes)||built.taskProviderDigest!=hash(ownBytes))throw Error("E_PACKAGE","task application provider identity differs");
      taskFile("application_provider",ownPath,&own);
      auto providers=link->getAsObject()->getArray("task_providers");if(!providers||providers->size()>128)throw Error("E_PACKAGE","invalid owned task provider inventory");
      std::set<std::string> providerNames,expectedProviders;
      for(const auto &entry:*info->getArray("completion_inputs"))if(entry.getAsObject()->getString("kind")=="owned_task_provider")expectedProviders.insert(entry.getAsObject()->getString("path")->str());
      for(const auto &entry:*providers){auto row=entry.getAsObject();auto image=row?row->getString("image"):std::nullopt;auto path=row?row->getString("path"):std::nullopt;auto pin=row?row->getString("hash"):std::nullopt;auto component=row?row->getString("component"):std::nullopt;
        if(!row||row->size()!=4||!image||!path||!pin||!component||path->str()!=image->str()+".task-provider.json"||!expectedProviders.contains(path->str())||!providerNames.insert(path->str()).second||!imageRecords.contains(image->str()))throw Error("E_PACKAGE","invalid owned task provider fields/path");
        const auto &physicalImage=*imageRecords.at(image->str());auto data=readFile((buildFolder/path->str()).string());auto parsed=llvm::json::parse(data);if(!parsed||hash(data)!=*pin)throw Error("E_PACKAGE","owned task provider pin differs");auto provider=parseNativeTaskProvider(*parsed);
        if(provider.mode!=NativeTaskLinkageMode::SharedFixed||provider.artifact!=NativeTaskArtifactKind::SharedImage||provider.component!=*component||!provider.image||physicalImage.getString("kind")!="library"||
           physicalImage.getString("key")!=provider.image->key||physicalImage.getString("hash")!=provider.image->digest||physicalImage.getString("sha256")!=provider.image->sha256||physicalImage.getString("uuid")!=provider.image->uuid||
           provider.image->runtimeKey!=own.image->runtimeKey||provider.image->runtimeDigest!=own.image->runtimeDigest)throw Error("E_PACKAGE","owned task provider image differs");
        taskFile("owned_provider",buildFolder/path->str(),&provider);
      }
      if(providerNames!=expectedProviders||providers->size()+1!=inventory->size())throw Error("E_PACKAGE","owned task provider closure is incomplete");
      taskFile("image_inputs",buildFolder/"image-inputs.json",nullptr);taskFile("build",buildFolder/"build.json",nullptr);taskFile("complete",buildFolder/"complete",nullptr);
    }
  }
  if(profiled){
    (void)inspectTaskProfileBuildInputs(built);
    auto parseProvider=[&](const fs::path &path){auto parsed=llvm::json::parse(readFile(path.string()));if(!parsed)throw Error("E_PACKAGE","invalid profile provider");return parseNativeTaskProvider(*parsed);};
    auto own=parseProvider(buildFolder/"task-provider.json");if(!own.profiling)throw Error("E_PACKAGE","profile application omitted catalog");
    taskFile("application_provider",buildFolder/"task-provider.json",&own);taskFile("application_profile_catalog",buildFolder/"task-profile-catalog.json",&own);
    if(sharedTasks){auto parsed=llvm::json::parse(readFile((buildFolder/"image-inputs.json").string()));const auto &link=*parsed->getAsObject();
      for(const auto &value:*link.getArray("task_providers")){const auto &row=*value.getAsObject();auto path=buildFolder/row.getString("path")->str();auto provider=parseProvider(path);taskFile("owned_provider",path,&provider);
        auto image=row.getString("image")->str();taskFile("owned_profile_catalog",buildFolder/(image+".task-profile-catalog.json"),&provider);}
      taskFile("image_inputs",buildFolder/"image-inputs.json",nullptr);
    }
    taskFile("build",buildFolder/"build.json",nullptr);taskFile("complete",buildFolder/"complete",nullptr);
  }
  if(debug){
    (void)inspectNativeTaskDebugBuildInputs(built);
    std::map<std::string,std::string> imageComponents;imageComponents[built.executable]=built.taskProvider.component;
    if(sharedTasks){auto input=llvm::json::parse(readFile((buildFolder/"image-inputs.json").string()));for(const auto &value:*input->getAsObject()->getArray("task_providers")){const auto &row=*value.getAsObject();imageComponents[(buildFolder/row.getString("image")->str()).string()]=row.getString("component")->str();}}
    auto add=[&](const std::string &kind,const std::string &relative){auto path=buildFolder/relative;physical(path);auto data=readFile(path.string());std::string image;
      if(kind=="base_binary"||kind=="task_provider"||kind=="debug_catalog"||kind=="debug_sources")image=built.executable;
      if(kind=="owned_image")image=path.string();
      for(const auto &suffix:{std::string(".task-provider.json"),std::string(".task-debug-catalog.json"),std::string(".task-debug-sources.json")})if(kind.starts_with("owned_")&&relative.ends_with(suffix))image=(buildFolder/relative.substr(0,relative.size()-suffix.size())).string();
      llvm::json::Object row{{"kind",kind},{"relative",relative},{"path",path.string()},{"hash",hash(data)},{"sha256",sha256(data)},{"bytes",int64_t(data.size())},{"component",nullptr},{"image",nullptr},{"image_key",nullptr},{"image_sha256",nullptr},{"image_uuid",nullptr}};
      if(!image.empty()){row["image"]=image;row["component"]=imageComponents.contains(image)?llvm::json::Value(imageComponents.at(image)):llvm::json::Value(nullptr);row["image_key"]=image==built.executable?built.key:fs::path(image).stem().string().substr(fs::path(image).stem().string().size()-64);row["image_sha256"]=sha256(readFile(image));row["image_uuid"]=nativeImageUUID(image);}
      taskFiles.push_back(std::move(row));};
    for(const auto &[kind,name]:std::vector<std::pair<std::string,std::string>>{{"base_binary",fs::path(built.executable).filename().string()},{"base_mlir","program.mlir"},{"base_llvm","program.ll"},{"base_compilation","compilation.json"},{"base_build","build.json"},{"base_source_bundle","source-bundle.json"}})add(kind,name);
    for(const auto &value:*info->getArray("completion_inputs")){const auto &row=*value.getAsObject();add(row.getString("kind")->str(),row.getString("path")->str());}add("complete","complete");
  }
  llvm::json::Object packageRequest{{"schema",debug?"nex.application-request/4":profiled?"nex.application-request/3":sharedTasks?"nex.application-request/2":"nex.application-request/1"},
    {"binary",built.executable},{"binary_sha256",sha256(bytes)},{"owned_images",std::move(owned)},
    {"runtime_notices",built.notices},{"runtime_notices_sha256",sha256(readFile(built.notices))},{"sdk_root",fs::path(options.compiler).parent_path().parent_path().string()},
    {"toolchain",NEX_VERSION},{"language",programLanguage(candidate)},{"revision",revision(candidate)},
    {"foreign_directory",foreignDirectory},
    {"foreign_files",std::move(foreignFiles)},{"foreign_projection",std::move(projection)},
    {"build_key",built.key},{"target",built.target},{"compiler_target",built.compilerTarget},
    {"compiler_build",info->getString("compiler_build").value_or("")},
    {"profile",info->getString("profile").value_or("")},{"kind",info->getString("kind").value_or("")},
    {"host_compatible",built.hostCompatible}};
  if(auto inputs=info->getArray("static_link_inputs")){
    for(const auto &value:*inputs){const auto *input=value.getAsObject();auto path=input?input->getString("path"):std::nullopt;auto digest=input?input->getString("sha256"):std::nullopt;auto size=input?input->getInteger("bytes"):std::nullopt;
      if(!path||!digest||!size||*size<0||*size>256LL*1048576)throw Error("E_PACKAGE","invalid completed static link input");
      physical(path->str());auto data=readFile(path->str());if(int64_t(data.size())!=*size||sha256(data)!=*digest)throw Error("E_PACKAGE","static link input changed after compilation");
    }
    packageRequest["static_link_inputs"]=llvm::json::Array(*inputs);
  }
  if(sharedTasks||profiled||debug)packageRequest["task_inputs"]=llvm::json::Object{{"schema",debug?"nex.application-task-inputs/3":profiled?"nex.application-task-inputs/2":"nex.application-task-inputs/1"},{"files",std::move(taskFiles)}};
  writeFile(request.string(),json(llvm::json::Value(std::move(packageRequest)))+"\n");
  std::vector<std::string> command={pythonProgram(),"-X","utf8",resourceFile("tools/app_bundle.py"),
    "--request",request.string(),"--output",output.string()};
  if(!options.notices.empty())command.insert(command.end(),{"--notices",fs::absolute(options.notices).string()});
  if(options.dpkgNotices)command.push_back("--dpkg-notices");
  auto parsed=checkedTool(command,request);
  auto object=parsed.getAsObject();
  if(!object||object->getString("schema")!="nex.package/1"||object->getBoolean("ok")!=true||object->getString("build_key")!=built.key)
    throw Error("E_PACKAGE","package report does not match the selected native build");
  if(debug){
    auto reportValue=llvm::json::parse(readFile((output/"application.json").string()));auto report=reportValue?reportValue->getAsObject():nullptr;auto provenance=report?report->getObject("task_debug_provenance"):nullptr;auto rows=provenance?provenance->getArray("files"):nullptr;if(!rows)throw Error("E_PACKAGE","debug package omitted raw provenance");
    std::map<std::string,std::string> imageOutputs;
    for(const auto &value:*rows){const auto &row=*value.getAsObject();if(auto image=row.getString("output_image")){auto original=row.getString("input_image_key");if(!original)throw Error("E_PACKAGE","debug package image key missing");auto relative=row.getString("relative")->str();std::string input;
        if(relative==fs::path(built.executable).filename().string()||relative=="task-provider.json"||relative=="task-debug-catalog.json"||relative=="task-debug-sources.json")input=built.executable;
        else{auto owner=(buildFolder/relative).string();for(const auto &suffix:{std::string(".task-provider.json"),std::string(".task-debug-catalog.json"),std::string(".task-debug-sources.json")})if(owner.ends_with(suffix))owner.resize(owner.size()-suffix.size());if(ownedImagePaths.contains(fs::path(owner).lexically_normal()))input=std::move(owner);}
        if(input.empty())throw Error("E_PACKAGE","unexpected debug package image association");auto target=output/image->str();if(sha256(readFile(target.string()))!=row.getString("output_image_sha256"))throw Error("E_PACKAGE","debug package loaded output image changed");auto [old,inserted]=imageOutputs.emplace(input,target.string());if(!inserted&&old->second!=target.string())throw Error("E_PACKAGE","debug package image mapping differs");
      }}
    auto raw=output/"debugger/retained-build";auto finalOutput=options.publishedDirectory.empty()?output:fs::absolute(options.publishedDirectory).lexically_normal();auto relocated=relocateNativeTaskDebugSession(candidate,built,raw.string(),output.string(),finalOutput.string(),options.compiler,imageOutputs);
    for(const auto &[key,value]:relocated){auto relative=fs::path(value.getAsString()->str()).lexically_relative(finalOutput).generic_string();(*report)[key]=relative;(*object)[key]=(output/relative).string();}
    auto files=report->getObject("files");for(const auto &name:{"debug-relocated.json","debug-session.json","debug-relocation.json"}){auto file=raw/name;(*files)[file.lexically_relative(output).generic_string()]=llvm::json::Object{{"sha256",sha256(readFile(file.string()))},{"bytes",int64_t(fs::file_size(file))},{"executable",false}};}
    writeFile((output/"application.json").string(),json(llvm::json::Object(*report))+"\n");(*object)["files"]=int64_t(files->size());
  }
  return parsed;
}

}
ForeignPackagePreparation prepareForeignPackage(const PackageOptions &options,
  const ForeignSelection &selection,const std::string &workingDirectory){
  namespace fs=std::filesystem;auto folder=fs::path(workingDirectory),request=folder/"request.json";
  fs::create_directories(folder);
  if(selection.empty())throw Error("E_FFI_PACKAGE","foreign preparation requires selected exports");
  llvm::json::Object selectionObject;for(const auto &[name,exports]:selection){llvm::json::Array values;for(const auto &value:exports)values.push_back(value);selectionObject[name]=std::move(values);}
    auto selected=folder/"selection.json";writeFile(selected.string(),json(llvm::json::Value(std::move(selectionObject)))+"\n");
    auto prepared=folder/"prepared";
    std::vector<std::string> command={pythonProgram(),"-X","utf8",resourceFile("tools/foreign_bundle.py"),
      "--nex",options.compiler,"--foreign",fs::absolute(options.foreign).string(),
      "--sdk-root",fs::path(options.compiler).parent_path().parent_path().string(),
      "--selection",selected.string(),"--output",prepared.string()};
    if(!options.notices.empty())command.insert(command.end(),{"--notices",fs::absolute(options.notices).string()});
    if(options.dpkgNotices)command.push_back("--dpkg-notices");
    auto preparedReport=checkedTool(command,request);auto report=preparedReport.getAsObject();
    auto libraries=report?report->getObject("libraries"):nullptr;
    if(!report||report->getString("schema")!="nex.foreign-package/1"||report->getBoolean("assembly_passed")!=true||!libraries)
      throw Error("E_PACKAGE","invalid foreign preparation report; inputs retained at "+folder.string());
  llvm::json::Object foreignFiles;
    auto snapshot=inspectForeignCatalogue((prepared/"host.json").string());
    if(report->getString("notices_root")=="catalogue"){
      size_t bytes=0;for(const auto &[name,data]:snapshot.files){(void)name;bytes+=data.size();}
      for(const auto &[name,value]:*libraries){
        (void)name;auto library=value.getAsObject();auto components=library?library->getArray("components"):nullptr;
        if(!components)throw Error("E_PACKAGE","foreign preparation has no component notices");
        for(const auto &componentValue:*components){auto component=componentValue.getAsObject();auto notices=component?component->getArray("license_files"):nullptr;
          if(!notices)throw Error("E_PACKAGE","foreign component has no notice inventory");
          for(const auto &noticeValue:*notices){auto notice=noticeValue.getAsObject();auto path=notice?notice->getString("path"):std::nullopt;auto digest=notice?notice->getString("sha256"):std::nullopt;
            if(!path||!digest||!path->starts_with("licenses/")||path->contains('\0')||path->contains('\\')||path->contains(':'))throw Error("E_PACKAGE","invalid captured notice path");
            auto source=prepared;for(const auto &part:fs::path(path->str())){
              if(part.empty()||part=="."||part==".."||part.is_absolute())throw Error("E_PACKAGE","invalid captured notice path");source/=part;
              if(fs::is_symlink(source))throw Error("E_PACKAGE","symlink in captured notice input");
            }
            if(auto existing=snapshot.files.find(path->str());existing!=snapshot.files.end()){
              if(sha256(existing->second)!=*digest)throw Error("E_PACKAGE","conflicting captured component notice hashes");continue;
            }
            if(!fs::is_regular_file(source)||fs::file_size(source)>64*1048576||fs::file_size(source)>128*1048576-bytes||snapshot.files.size()>=8190)
              throw Error("E_PACKAGE","foreign capture exceeds package input limits");
            auto data=readFile(source.string());
            if(data.size()>64*1048576||data.size()>128*1048576-bytes)throw Error("E_PACKAGE","foreign capture exceeds package input limits");
            if(sha256(data)!=*digest)throw Error("E_PACKAGE","foreign component notice changed after preparation");
            bytes+=data.size();snapshot.files.emplace(path->str(),std::move(data));
          }
        }
      }
    }
    auto foreign=folder/"foreign";saveForeignCatalogue(snapshot,foreign);
    writeFile((foreign/"foreign-package.json").string(),json(preparedReport)+"\n");
    for(const auto &entry:fs::recursive_directory_iterator(foreign)){
      if(entry.is_symlink())throw Error("E_PACKAGE","symlink in prepared foreign input");
      if(entry.is_regular_file())foreignFiles[fs::relative(entry.path(),foreign).generic_string()]=sha256(readFile(entry.path().string()));
    }
  return {foreign.string(),std::move(snapshot),std::move(preparedReport),std::move(foreignFiles)};
}
ForeignProgramProjection projectForeignProgram(const Program &program,
  const std::set<std::string> &functions,const ForeignPackagePreparation &prepared,const std::string &root){
  auto candidate=program;std::vector<const Function*> bindings;
  for(const auto &name:functions){const auto &f=program.function(name);if(!f.foreign)throw Error("E_FFI_PACKAGE","projection requires an external binding: "+name);bindings.push_back(&f);}
  const auto *libraries=prepared.report.getAsObject()->getObject("libraries");
    struct Edit{size_t begin,end;std::string replacement;};std::map<std::string,std::vector<Edit>> edits;
    auto bundle=sourceBundle(program);auto files=bundle.getAsObject()->getObject("files");
    llvm::json::Array changes;
    for(const auto *function:bindings){
      const auto &binding=*function->foreign;auto library=libraries->getObject(binding.library);
      auto pin=library?library->getString("manifest_sha256"):std::nullopt;
      if(!pin||library->getString("source_manifest_sha256")!=binding.manifest)
        throw Error("E_FFI_PACKAGE","source external pin differs from the operator-selected original bundle: "+function->name,function->span);
      const auto &span=binding.manifestSpan;const auto &source=program.units.at(function->unit).source;
      if(span.begin<function->span.begin||span.end>function->span.end||span.begin>=span.end||span.end>source.size())
        throw Error("E_PACKAGE","external source pin has no valid token location",function->span);
      edits[function->unit].push_back({span.begin,span.end,json(pin->str(),false)});
      for(auto &expected:candidate.functions)if(expected.name==function->name)expected.foreign->manifest=pin->str();
      changes.push_back(llvm::json::Object{{"function",function->name},{"library",binding.library},{"export",binding.symbol},
        {"source_manifest_sha256",binding.manifest},{"manifest_sha256",pin->str()}});
    }
    for(auto &[unit,values]:edits){
      std::sort(values.begin(),values.end(),[](const auto &a,const auto &b){return a.begin>b.begin;});
      auto source=program.units.at(unit).source;size_t previous=source.size();
      for(const auto &edit:values){if(edit.end>previous)throw Error("E_PACKAGE","overlapping external pin projection");source.replace(edit.begin,edit.end-edit.begin,edit.replacement);previous=edit.begin;}(*files)[unit]=source;
    }
    auto derived=loadVersionedBundle(bundle,root,programLanguage(program));check(derived);
    if(revision(derived)!=revision(candidate))throw Error("E_PACKAGE","packaged projection changed semantics outside reachable manifest pins");
    for(const auto *function:bindings){
      try{checkForeignBinding(prepared.snapshot,derived,derived.function(function->name));}
      catch(const Error &error){throw Error("E_FFI_PACKAGE",error.what(),error.span);}
    }
  auto report=llvm::json::Object{{"schema","nex.foreign-projection/1"},{"source_revision",revision(program)},
      {"packaged_revision",revision(derived)},{"source_hash",hash(json(sourceBundle(program),false))},
      {"packaged_source_hash",hash(json(sourceBundle(derived),false))},{"changes",std::move(changes)},
      {"catalogue_hash",prepared.snapshot.hash},{"preparation",prepared.report}};
  return {std::move(derived),std::move(report)};
}
ForeignPackagePreparation selectForeignPackage(const ForeignPackagePreparation &prepared,
    const ForeignSelection &selection,const std::string &directory){
  if(selection.empty())throw Error("E_FFI_PACKAGE","application foreign selection is empty");
  ForeignCatalogueSnapshot subset;subset.platform=prepared.snapshot.platform;
  auto manifest=llvm::json::Object(*prepared.snapshot.manifest.getAsObject());
  llvm::json::Object grants,libraries;std::set<std::string> retained;
  auto copy=[&](const std::string &name){
    auto found=prepared.snapshot.files.find(name);
    if(found==prepared.snapshot.files.end())throw Error("E_FFI_PACKAGE","selected foreign package input is missing: "+name);
    retained.insert(name);
  };
  for(const auto &[name,exports]:selection){
    auto original=prepared.snapshot.grants.find(name);
    if(original==prepared.snapshot.grants.end()||exports.empty()||
       !std::includes(original->second.exports.begin(),original->second.exports.end(),exports.begin(),exports.end()))
      throw Error("E_FFI_PACKAGE","application foreign selection exceeds prepared authority: "+name);
    auto grant=original->second;grant.exports=exports;subset.grants.emplace(name,grant);
    llvm::json::Array names;for(const auto &value:exports)names.push_back(value);
    auto record=llvm::json::Object(*prepared.snapshot.manifest.getAsObject()->getObject("libraries")->getObject(name));
    record["exports"]=llvm::json::Array(names);grants[name]=std::move(record);
    auto library=llvm::json::Object(*prepared.report.getAsObject()->getObject("libraries")->getObject(name));
    library["exports"]=std::move(names);
    for(const auto &value:*library.getArray("components"))for(const auto &notice:*value.getAsObject()->getArray("license_files"))
      copy(notice.getAsObject()->getString("path")->str());
    libraries[name]=std::move(library);
    auto prefix="bundles/"+grant.pin+"/";
    for(const auto &[path,data]:prepared.snapshot.files){(void)data;if(path.starts_with(prefix))copy(path);}
  }
  manifest["libraries"]=std::move(grants);subset.manifest=std::move(manifest);
  subset.identity=llvm::json::Object{{"schema","nex.foreign-catalogue/1"},{"platform",subset.platform},{"catalogue",subset.manifest}};
  subset.hash=hash(json(subset.identity,false));
  for(const auto &name:retained)subset.files.emplace(name,prepared.snapshot.files.at(name));
  auto report=llvm::json::Object(*prepared.report.getAsObject());report["libraries"]=std::move(libraries);report["catalogue_hash"]=subset.hash;
  saveForeignCatalogue(subset,directory);writeFile((std::filesystem::path(directory)/"foreign-package.json").string(),json(llvm::json::Value(llvm::json::Object(report)))+"\n");
  llvm::json::Object files;
  for(const auto &entry:std::filesystem::recursive_directory_iterator(directory))if(entry.is_regular_file())
    files[entry.path().lexically_relative(directory).generic_string()]=sha256(readFile(entry.path().string()));
  if(inspectForeignCatalogue((std::filesystem::path(directory)/"host.json").string()).hash!=subset.hash)
    throw Error("E_FFI_PACKAGE","application foreign subset differs after capture");
  return {directory,std::move(subset),std::move(report),std::move(files)};
}
llvm::json::Value packageApplication(const Program &program,BuildOptions buildOptions,
    const std::string &buildDirectory,const std::string &root,Store &store,
    const PackageOptions &options) {
  namespace fs=std::filesystem;

  auto output=fs::absolute(options.directory).lexically_normal();
  if(fs::exists(output)||fs::is_symlink(output))throw Error("E_EXISTS","package requires a new output directory");
  auto folder=fs::path(createTemporaryDirectory("nex-package")),request=folder/"request.json";
  auto candidate=program;llvm::json::Value projection=nullptr;llvm::json::Object foreignFiles;
  std::set<std::string> reachable;std::function<void(const Function&)> visit=[&](const Function &function){
    if(reachable.insert(function.name).second)for(const auto &name:function.dependencies)visit(program.function(name));
  };visit(program.function(buildOptions.entry));
  std::vector<const Function*> bindings;
  std::map<std::string,std::set<std::string>> exports;
  for(const auto &name:reachable){const auto &function=program.function(name);if(function.foreign){bindings.push_back(&function);exports[function.foreign->library].insert(function.foreign->symbol);}}
  if(!bindings.empty()){
    if(options.foreign.empty())throw Error("E_FFI_PACKAGE","packaging external calls requires an explicit --foreign HOST.json operator catalogue");
    // The host inspector and native dependency tools describe this execution
    // host. Cross-target module preparation needs a separate target SDK path.
    requireNativeHost(buildOptions);
    auto prepared=prepareForeignPackage(options,exports,folder.string());
    std::set<std::string> selectedFunctions;for(const auto *f:bindings)selectedFunctions.insert(f->name);
    auto projected=projectForeignProgram(program,selectedFunctions,prepared,root);auto derived=std::move(projected.program);
    projection=std::move(projected.report);foreignFiles=std::move(prepared.files);
    store.save(program,"",false);store.save(derived,"",false);candidate=std::move(derived);
    buildOptions.foreignCatalogue="../foreign/host.json";
  }else if(!options.foreign.empty())throw Error("E_FFI_PACKAGE","selected native entry has no reachable external calls");
  auto built=build(candidate,buildDirectory,buildOptions);
  auto parsed=packageCapturedArtifact(candidate,built,options,request,
      projection.getAsObject()?(folder/"foreign").string():"",std::move(projection),std::move(foreignFiles));
  fs::remove_all(folder);return parsed;
}
llvm::json::Value packageNativeArtifact(const Program &program,const BuildResult &built,const PackageOptions &options,const ForeignPackageArtifact *foreign){
  namespace fs=std::filesystem;
  if(built.foreignCalls!=bool(foreign))throw Error("E_FFI_PACKAGE","checked native foreign requirements differ from the captured application grant");
  auto output=fs::absolute(options.directory).lexically_normal();
  if(fs::exists(output)||fs::is_symlink(output))throw Error("E_EXISTS","package requires a new output directory");
  auto folder=fs::path(createTemporaryDirectory("nex-project-application-package"));
  auto result=packageCapturedArtifact(program,built,options,folder/"request.json",foreign?foreign->directory:"",
    foreign?foreign->projection:llvm::json::Value(nullptr),foreign?llvm::json::Object(foreign->files):llvm::json::Object{});
  fs::remove_all(folder);return result;
}

}
