#include "nex/packaging.h"
#include "nex/foreign_catalogue.h"
#include "nex/native_toolchain.h"
#include "nex/native_images.h"
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
  const char *python=std::getenv("NEX_PYTHON");
  auto bytes=readFile(built.executable);
  auto metadata=llvm::json::parse(readFile((fs::path(built.executable).parent_path()/"build.json").string()));
  if(!metadata){llvm::consumeError(metadata.takeError());throw Error("E_PACKAGE","invalid native build metadata");}
  auto info=metadata->getAsObject();
  if(!info||info->getString("key")!=built.key)throw Error("E_PACKAGE","native build metadata does not match its artifact");
  if(info->getString("compiler_build")!=NEX_BUILD_ID||info->getString("revision")!=revision(candidate)||
     (info->getString("kind")!="executable"&&info->getString("kind")!="http_server"))
    throw Error("E_PACKAGE","packaging requires its matching checked native application artifact");
  auto buildFolder=fs::path(built.executable).parent_path();std::string complete=built.key;
  for(const auto &file:{fs::path(built.executable),buildFolder/"program.mlir",buildFolder/"program.ll",buildFolder/"compilation.json",buildFolder/"build.json",buildFolder/"source-bundle.json"})complete+=hash(readFile(file.string()));
  for(const auto &name:nativeCompletionInputs(*info))complete+=hash(readFile((buildFolder/name).string()));
  if(readFile((buildFolder/"complete").string())!=hash(complete)+"\n")throw Error("E_PACKAGE","native artifact completion differs before packaging");
  llvm::json::Array owned;
  if(info->getString("completion_schema")=="nex.native-completion/3"){
    auto link=llvm::json::parse(readFile((buildFolder/"image-inputs.json").string()));
    auto inventory=link&&link->getAsObject()?link->getAsObject()->getArray("images"):nullptr;
    if(!inventory||inventory->empty()||inventory->size()>129)throw Error("E_PACKAGE","invalid compiler-owned native image inventory");
    std::set<std::string> expected,seen;
    for(const auto &entry:*info->getArray("completion_inputs"))if(entry.getAsObject()->getString("kind")=="owned_image")expected.insert(entry.getAsObject()->getString("path")->str());
    for(const auto &entry:*inventory){
      auto record=entry.getAsObject();if(!record)throw Error("E_PACKAGE","invalid compiler-owned image record");
      auto path=record->getString("path"),digest=record->getString("sha256"),key=record->getString("key"),abi=record->getString("abi"),kind=record->getString("kind"),uuid=record->getString("uuid");
      if(!path||!digest||!key||!abi||!kind||!uuid)throw Error("E_PACKAGE","missing compiler-owned image identity");
      auto relative=(fs::path("images")/fs::path(path->str()).filename()).generic_string();
      if(fs::path(path->str())!=buildFolder/relative||!expected.contains(relative)||!seen.insert(relative).second||
         sha256(readFile(path->str()))!=*digest||nativeImageUUID(path->str())!=*uuid||*abi!=built.libraryABI)
        throw Error("E_PACKAGE","compiler-owned native image bytes/UUID/path differ");
      owned.push_back(llvm::json::Object{{"path",path->str()},{"sha256",digest->str()},{"key",key->str()},{"abi",abi->str()},{"kind",kind->str()},{"uuid",uuid->str()}});
    }
    if(seen!=expected)throw Error("E_PACKAGE","compiler-owned image inventory is incomplete");
  }
  writeFile(request.string(),json(llvm::json::Object{{"schema","nex.application-request/1"},
    {"binary",built.executable},{"binary_sha256",sha256(bytes)},{"owned_images",std::move(owned)},
    {"runtime_notices",built.notices},{"runtime_notices_sha256",sha256(readFile(built.notices))},{"sdk_root",fs::path(options.compiler).parent_path().parent_path().string()},
    {"toolchain",NEX_VERSION},{"language",languageVersion},{"revision",revision(candidate)},
    {"foreign_directory",foreignDirectory},
    {"foreign_files",std::move(foreignFiles)},{"foreign_projection",std::move(projection)},
    {"build_key",built.key},{"target",built.target},{"compiler_target",built.compilerTarget},
    {"compiler_build",info->getString("compiler_build").value_or("")},
    {"profile",info->getString("profile").value_or("")},{"kind",info->getString("kind").value_or("")},
    {"host_compatible",built.hostCompatible}})+"\n");
  std::vector<std::string> command={python?python:"python3",resourceFile("tools/app_bundle.py"),
    "--request",request.string(),"--output",output.string()};
  if(!options.notices.empty())command.insert(command.end(),{"--notices",fs::absolute(options.notices).string()});
  if(options.dpkgNotices)command.push_back("--dpkg-notices");
  auto parsed=checkedTool(command,request);
  auto object=parsed.getAsObject();
  if(!object||object->getString("schema")!="nex.package/1"||object->getBoolean("ok")!=true||object->getString("build_key")!=built.key)
    throw Error("E_PACKAGE","package report does not match the selected native build");
  return parsed;
}

}
llvm::json::Value packageApplication(const Program &program,BuildOptions buildOptions,
    const std::string &buildDirectory,const std::string &root,Store &store,
    const PackageOptions &options) {
  namespace fs=std::filesystem;
  if(llvm::Triple(configureNative(buildOptions).target).isOSWindows())throw Error("E_TARGET","Windows application packages are not configured; build the explicit GNU/UCRT core artifact");
  auto output=fs::absolute(options.directory).lexically_normal();
  if(fs::exists(output)||fs::is_symlink(output))throw Error("E_EXISTS","package requires a new output directory");
  auto folder=fs::path(createTemporaryDirectory("nex-package")),request=folder/"request.json";
  const char *python=std::getenv("NEX_PYTHON");
  auto candidate=program;llvm::json::Value projection=nullptr;llvm::json::Object foreignFiles;
  std::set<std::string> reachable;std::function<void(const Function&)> visit=[&](const Function &function){
    if(reachable.insert(function.name).second)for(const auto &name:function.dependencies)visit(program.function(name));
  };visit(program.function(buildOptions.entry));
  std::vector<const Function*> bindings;llvm::json::Object selection;
  std::map<std::string,std::set<std::string>> exports;
  for(const auto &name:reachable){const auto &function=program.function(name);if(function.foreign){bindings.push_back(&function);exports[function.foreign->library].insert(function.foreign->symbol);}}
  if(!bindings.empty()){
    if(options.foreign.empty())throw Error("E_FFI_PACKAGE","packaging external calls requires an explicit --foreign HOST.json operator catalogue");
    // The host inspector and native dependency tools describe this execution
    // host. Cross-target module preparation needs a separate target SDK path.
    requireNativeHost(buildOptions);
    for(const auto &[library,names]:exports){llvm::json::Array values;for(const auto &name:names)values.push_back(name);selection[library]=std::move(values);}
    auto selected=folder/"selection.json";writeFile(selected.string(),json(llvm::json::Value(std::move(selection)))+"\n");
    auto prepared=folder/"prepared";
    std::vector<std::string> command={python?python:"python3",resourceFile("tools/foreign_bundle.py"),
      "--nex",options.compiler,"--foreign",fs::absolute(options.foreign).string(),
      "--sdk-root",fs::path(options.compiler).parent_path().parent_path().string(),
      "--selection",selected.string(),"--output",prepared.string()};
    if(!options.notices.empty())command.insert(command.end(),{"--notices",fs::absolute(options.notices).string()});
    if(options.dpkgNotices)command.push_back("--dpkg-notices");
    auto preparedReport=checkedTool(command,request);auto report=preparedReport.getAsObject();
    auto libraries=report?report->getObject("libraries"):nullptr;
    if(!report||report->getString("schema")!="nex.foreign-package/1"||report->getBoolean("assembly_passed")!=true||!libraries)
      throw Error("E_PACKAGE","invalid foreign preparation report; inputs retained at "+folder.string());
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
    auto derived=loadBundle(bundle,root);check(derived);
    if(revision(derived)!=revision(candidate))throw Error("E_PACKAGE","packaged projection changed semantics outside reachable manifest pins");
    auto snapshot=inspectForeignCatalogue((prepared/"host.json").string());
    for(const auto *function:bindings){
      try{checkForeignBinding(snapshot,derived,derived.function(function->name));}
      catch(const Error &error){throw Error("E_FFI_PACKAGE",error.what(),error.span);}
    }
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
    projection=llvm::json::Object{{"schema","nex.foreign-projection/1"},{"source_revision",revision(program)},
      {"packaged_revision",revision(derived)},{"source_hash",hash(json(sourceBundle(program),false))},
      {"packaged_source_hash",hash(json(sourceBundle(derived),false))},{"changes",std::move(changes)},
      {"catalogue_hash",snapshot.hash},{"preparation",std::move(preparedReport)}};
    store.save(program,"",false);store.save(derived,"",false);candidate=std::move(derived);
    buildOptions.foreignCatalogue="../foreign/host.json";
  }else if(!options.foreign.empty())throw Error("E_FFI_PACKAGE","selected native entry has no reachable external calls");
  auto built=build(candidate,buildDirectory,buildOptions);
  auto parsed=packageCapturedArtifact(candidate,built,options,request,
      projection.getAsObject()?(folder/"foreign").string():"",std::move(projection),std::move(foreignFiles));
  fs::remove_all(folder);return parsed;
}
llvm::json::Value packageNativeArtifact(const Program &program,const BuildResult &built,const PackageOptions &options){
  namespace fs=std::filesystem;
  if(built.foreignCalls||!options.foreign.empty())throw Error("E_PROJECT_CAPABILITY","project packaging of source foreign calls requires project-wide pin projection, which remains pending");
  auto output=fs::absolute(options.directory).lexically_normal();
  if(fs::exists(output)||fs::is_symlink(output))throw Error("E_EXISTS","package requires a new output directory");
  auto folder=fs::path(createTemporaryDirectory("nex-project-application-package"));
  auto result=packageCapturedArtifact(program,built,options,folder/"request.json","",nullptr,{});
  fs::remove_all(folder);return result;
}

}
