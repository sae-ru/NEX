#include "nex/project_capture.h"
#include "nex/native_toolchain.h"
#include "nex_task_protocol.h"
#include "llvm/Support/Error.h"
#include <algorithm>
#include <filesystem>
#include <functional>

namespace nex {
namespace {
namespace fs=std::filesystem;
using JSON=llvm::json::Value;using Object=llvm::json::Object;using Array=llvm::json::Array;
[[noreturn]] void fail(const std::string &message){throw Error("E_PROJECT_CAPTURE",message);}
const Object &object(const JSON &value){auto p=value.getAsObject();if(!p)fail("capture requires an object");return *p;}
std::string text(const Object &o,const std::string &name){auto s=o.getString(name);if(!s||s->empty()||s->size()>32768||s->contains('\0'))fail("invalid capture string: "+name);return s->str();}
JSON parse(const std::string &source){auto value=llvm::json::parse(source);if(!value)throw Error("E_JSON",llvm::toString(value.takeError()));return std::move(*value);}
bool inside(const fs::path &path,const fs::path &root){auto relative=path.lexically_relative(root);return !relative.is_absolute()&&std::none_of(relative.begin(),relative.end(),[](auto p){return p=="..";});}
std::string name(const std::string &value){
  fs::path p(value);if(value.empty()||value.size()>32768||!llvm::json::isUTF8(value)||value.find('\0')!=std::string::npos||p.is_absolute()||p.generic_string()!=p.lexically_normal().generic_string())fail("invalid captured relative path");
  for(const auto &part:p)if(part==".."||part=="."||part.empty())fail("escaping captured path");
  if(*p.begin()!="fs")fail("captured paths must stay in fs/");return value;
}
std::string mapped(const fs::path &physical){
  auto p=physical.lexically_normal();if(!p.is_absolute())fail("capture input is not absolute");
  // lexically_normal preserves a directory separator for component roots
  // such as root/".". The serialized namespace uses component names, never
  // an empty terminal component. This normalizes trusted physical inputs;
  // name() still rejects dot/parent/empty components in untrusted captures.
  auto relative=p.relative_path();
  if(!relative.empty()&&relative.filename().empty())relative=relative.parent_path();
  return name(relative.empty()?std::string("fs"):(fs::path("fs")/relative).generic_string());
}
std::string read(const fs::path &p,uint64_t maximum){if(!fs::is_regular_file(p)||fs::file_size(p)>maximum)fail("missing/oversized capture input: "+p.string());return readFile(p.string());}
void taskLinkage(const JSON &value,const std::string &component,SourceLanguage language){
  const auto &o=object(value);
  const auto schema=o.getString("schema");
  const bool typed=schema=="nex.project-static-task-linkage/5"||schema=="nex.project-task-linkage/14"||schema=="nex.project-task-linkage/15"||schema=="nex.project-task-linkage/16";
  const bool exceptions=typed||schema=="nex.project-static-task-linkage/4"||schema=="nex.project-task-linkage/11"||schema=="nex.project-task-linkage/12"||schema=="nex.project-task-linkage/13";
  const bool streams=exceptions||schema=="nex.project-static-task-linkage/3"||schema=="nex.project-task-linkage/8"||schema=="nex.project-task-linkage/9"||schema=="nex.project-task-linkage/10";
  const bool writes=streams||schema=="nex.project-static-task-linkage/2"||schema=="nex.project-task-linkage/5"||schema=="nex.project-task-linkage/6"||schema=="nex.project-task-linkage/7";
  const bool debug=schema=="nex.project-task-linkage/16"||schema=="nex.project-task-linkage/13"||schema=="nex.project-task-linkage/4"||schema=="nex.project-task-linkage/7"||schema=="nex.project-task-linkage/10";
  const bool profiled=schema=="nex.project-task-linkage/15"||schema=="nex.project-task-linkage/12"||schema=="nex.project-task-linkage/3"||schema=="nex.project-task-linkage/6"||schema=="nex.project-task-linkage/9";
  const bool shared=debug||profiled||schema=="nex.project-task-linkage/14"||schema=="nex.project-task-linkage/11"||schema=="nex.project-task-linkage/2"||schema=="nex.project-task-linkage/5"||schema=="nex.project-task-linkage/8";
  if(typed!=(language==SourceLanguage::TypedErrors027)||exceptions!=(isPublicSourceExceptionLanguage(language))||streams!=(language==SourceLanguage::TaskStreams024||isPublicSourceExceptionLanguage(language))||writes!=(language==SourceLanguage::TaskWrites023||language==SourceLanguage::TaskStreams024||isPublicSourceExceptionLanguage(language)))fail("captured task linkage language/ABI differs");
  for(const auto &[key,_]:o)if(key!="schema"&&key!="component"&&key!="execution_abi"&&(!writes||key!="task_file_writes")&&(!streams||(key!="task_file_reads"&&key!="task_file_streams"))&&key!="definitions"&&key!="imports"&&key!="exports"&&(!profiled||key!="profiling")&&(!debug||key!="debugging")&&(!shared||(key!="mode"&&key!="load_closure")))fail("unknown captured task linkage field");
  auto definitions=o.getArray("definitions"),imports=o.getArray("imports");auto exports=o.getObject("exports");
  const size_t extra=streams?3:writes?1:0;
  if((shared?(o.size()!=((profiled||debug)?9:8)+extra||(o.getString("mode")!="shared-fixed"&&(!(profiled||debug)||o.getString("mode")!="static"))||!o.get("load_closure")):(o.size()!=6+extra||schema!=(typed?"nex.project-static-task-linkage/5":exceptions?"nex.project-static-task-linkage/4":streams?"nex.project-static-task-linkage/3":writes?"nex.project-static-task-linkage/2":"nex.project-static-task-linkage/1")))||o.getString("component")!=component||o.getInteger("execution_abi")!=(typed?7:exceptions?6:streams?5:writes?4:3)||(writes&&!o.getBoolean("task_file_writes"))||(streams&&(!o.getBoolean("task_file_reads")||!o.getBoolean("task_file_streams")))||
     !definitions||definitions->empty()||definitions->size()>65536||!imports||imports->size()>65536||!exports||exports->size()>129)fail("invalid captured static task linkage");
  auto digest=[](const Object &row,const char *key){auto value=row.getString(key);if(!value||value->size()!=64||!std::all_of(value->begin(),value->end(),[](char c){return (c>='0'&&c<='9')||(c>='a'&&c<='f');}))fail("invalid captured task contract digest");};
  std::set<std::string> defined,imported;
  for(const auto &value:*definitions){const auto &row=object(value);if(row.size()!=2||!defined.insert(text(row,"function")).second)fail("invalid/duplicate captured task definition");digest(row,"contract");}
  for(const auto &value:*imports){const auto &row=object(value);auto function=text(row,"function"),provider=text(row,"provider");
    auto mode=row.getString("calling_mode");
    if(row.size()!=4||!imported.insert(function).second||defined.contains(function)||provider==component||
       (mode!=(typed?"task-code/7":exceptions?"task-code/6":streams?"task-code/5":writes?"task-code/4":"task-code/3")&&(exceptions||mode!="sync/1")))fail("invalid captured task import");
    digest(row,"contract");
  }
  for(const auto &[name,value]:*exports){const auto &row=object(value);auto requirements=row.getInteger("requirements");
    if(!defined.contains(name.str())||row.size()!=4||!requirements||(!exceptions&&!(*requirements&nexrt::taskCodeDeclaredTask))||(*requirements&~(exceptions?nexrt::taskSourceExceptionProviderRequirementsMask:streams?nexrt::taskStreamProviderRequirementsMask:writes?nexrt::taskWriteProviderRequirementsMask:nexrt::taskProviderRequirementsMask)))fail("invalid captured task export");
    digest(row,"contract");digest(row,"signature");text(row,"accessor");
  }
  if(profiled){auto profile=o.getObject("profiling");auto sites=profile?profile->getArray("sites"):nullptr;
    if(!profile||profile->size()!=3||profile->getString("schema")!="nex.project-task-profile/1"||profile->getInteger("registry_abi")!=1||!sites||sites->size()!=defined.size())fail("invalid captured profile source sites");
    std::set<std::string> names;for(const auto &value:*sites){const auto &row=object(value);auto function=text(row,"name");auto line=row.getInteger("line");
      if(row.size()!=6||!defined.contains(function)||!names.insert(function).second||!line||*line<1)fail("invalid captured profile source definition");
      for(const auto *key:{"function_hash","function_source_hash","source_unit_hash","contract"})digest(row,key);
      const auto &definition=*std::find_if(definitions->begin(),definitions->end(),[&](const auto &value){return value.getAsObject()->getString("function")==function;});
      if(row.getString("contract")!=definition.getAsObject()->getString("contract"))fail("captured profile contract differs");
    }
  }
  if(debug){auto metadata=o.getObject("debugging");auto rows=metadata?metadata->getArray("definitions"):nullptr;
    if(!metadata||metadata->size()!=4||metadata->getString("schema")!="nex.project-task-debug/1"||metadata->getInteger("registry_abi")!=1||metadata->getInteger("catalog_abi")!=2||!rows||rows->size()!=defined.size())fail("invalid captured logical debug source definitions");
    std::set<std::string> names;for(const auto &value:*rows){const auto &row=object(value);auto name=text(row,"name");auto retained=row.getBoolean("retained");if(row.size()!=8||!defined.contains(name)||!names.insert(name).second||!row.getInteger("line")||*row.getInteger("line")<1||!retained||!row.get("task_debug")||(*retained?!row.getObject("task_debug"):!row.get("task_debug")->getAsNull()))fail("invalid captured logical debug source definition");for(const auto *key:{"function_hash","function_source_hash","source_unit_hash","contract"})digest(row,key);
      for(const auto &entry:*definitions)if(entry.getAsObject()->getString("function")==name&&entry.getAsObject()->getString("contract")!=row.getString("contract"))fail("captured debug source contract differs");
    }
  }
  if(shared&&!o.get("load_closure")->getAsNull()){
    const auto &closure=object(*o.get("load_closure"));auto images=closure.getArray("images");
    if(closure.size()!=2||closure.getString("root")!=component||!images||images->empty()||images->size()>129)fail("invalid captured task load closure");
    std::set<std::string> seenImages,functions;
    for(const auto &value:*images){const auto &image=object(value);auto name=text(image,"component");auto kind=image.getString("kind");
      auto definitions=image.getArray("definitions"),statics=image.getArray("static_components"),dynamics=image.getArray("dynamic_components");
      if(image.size()!=5||!seenImages.insert(name).second||(kind!="application"&&kind!="shared-image")||!definitions||definitions->empty()||definitions->size()>65536||!statics||statics->size()>128||!dynamics||dynamics->size()>128)fail("invalid captured task image owner");
      for(const auto &definition:*definitions){const auto &row=object(definition);if(row.size()!=3||!functions.insert(text(row,"function")).second||functions.size()>65536)fail("duplicate captured task image definition");text(row,"source_component");digest(row,"contract");}
      for(const auto *list:{statics,dynamics}){std::set<std::string> seen;for(const auto &entry:*list){auto dependency=entry.getAsString();if(!dependency||dependency->empty()||dependency->size()>64||!seen.insert(dependency->str()).second||*dependency==name||(list==dynamics&&!seenImages.contains(dependency->str())))fail("invalid captured task image dependency");}}
    }
    if(images->back().getAsObject()->getString("component")!=component)fail("captured task load root is not last");
  }
}
struct Shape {const Object *files,*links,*expectations,*toolchains;std::vector<std::string> directories;std::string root,manifest;};
Shape shape(const JSON &capture,SourceLanguage language){
  const auto &c=object(capture);
  for(const auto &[key,_]:c)if(key!="schema"&&key!="language"&&key!="project_root"&&key!="manifest"&&key!="component"&&key!="architecture_hash"&&key!="original_project_manifest_hash"&&key!="files"&&key!="links"&&key!="directories"&&key!="expectations"&&key!="toolchains"&&key!="function_owners")fail("unknown project capture field");
  if(c.getString("schema")!="nex.project-capture/1"||c.getString("language")!=programLanguage(language))fail("unsupported project capture");
  Shape s;s.files=c.getObject("files");s.links=c.getObject("links");s.expectations=c.getObject("expectations");s.toolchains=c.getObject("toolchains");
  auto directories=c.getArray("directories");if(!s.files||s.files->empty()||s.files->size()>8192||!s.links||s.links->size()>8192||!directories||directories->size()>8192||!s.expectations||s.expectations->empty()||s.expectations->size()>32||!s.toolchains||s.toolchains->size()>32||!c.getObject("function_owners"))fail("invalid capture inventories");
  s.root=name(text(c,"project_root"));s.manifest=text(c,"manifest");if(fs::path(s.manifest).filename()!=s.manifest||s.manifest=="."||s.manifest=="..")fail("capture manifest must be a root filename");
  uint64_t bytes=0;
  for(const auto &[key,value]:*s.files){name(key.str());auto data=value.getAsString();if(!data||!llvm::json::isUTF8(*data)||data->contains('\0'))fail("capture files must be UTF-8 text without NUL");bytes+=data->size();if(bytes>64*1048576)fail("capture source bytes exceed64MiB");}
  for(const auto &[key,value]:*s.links){name(key.str());auto target=value.getAsString();if(!target)fail("capture link target requires text");name(target->str());}
  std::set<std::string> unique;for(const auto &v:*directories){auto p=v.getAsString();if(!p||!unique.insert(name(p->str())).second)fail("invalid/duplicate capture directory");s.directories.push_back(p->str());}
  if(!s.files->get(s.root+"/nex.json")||!s.files->get(s.root+"/"+s.manifest))fail("capture lacks project metadata");
  auto project=parse(s.files->getString(s.root+"/nex.json")->str());
  if(auto libraries=object(project).getObject("libraries"))for(const auto &[alias,value]:*libraries){(void)alias;auto p=value.getAsString();if(!p)fail("invalid captured library root");name((fs::path(s.root)/p->str()).lexically_normal().generic_string());}
  auto architecture=parse(s.files->getString(s.root+"/"+s.manifest)->str());auto configurations=object(architecture).getObject("configurations");
  if(!configurations||c.getString("architecture_hash")!=hash(json(architecture,false)))fail("captured architecture hash differs");
  auto selected=text(c,"component");
  for(const auto &[configuration,value]:*s.expectations){
    auto entries=value.getAsArray();auto native=s.toolchains->getObject(configuration);auto config=configurations->getObject(configuration);
    if(!entries||entries->empty()||entries->size()>128||!native||!config||!native->getString("hash")||!native->getString("target")||!native->getBoolean("host_compatible")||!native->getBoolean("explicit")||!native->getObject("manifest")||!native->getObject("identity"))fail("invalid captured configuration");
    if(bool(config->get("toolchain"))!=*native->getBoolean("explicit"))fail("captured configuration trust mode differs");
    if(*native->getBoolean("explicit")){auto file=name(text(*native,"file"));auto data=s.files->getString(file);if(!data||parse(data->str())!=*native->get("manifest"))fail("captured toolchain data differs");}
    bool found=false;std::set<std::string> names;
    for(const auto &entry:*entries){const auto &e=object(entry);auto id=text(e,"name");if(!names.insert(id).second)fail("duplicate captured component");found|=id==selected;
      for(auto field:{"kind","entry","revision","source_bundle_hash"})text(e,field);
      auto function=e.get("entry_function");if(!function||(!function->getAsNull()&&!function->getAsString()))fail("invalid captured entry function");
      if(auto fingerprint=e.getString("native_toolchain_hash");fingerprint&&fingerprint!=native->getString("hash"))fail("component toolchain differs from its configuration");
      if(auto linkage=e.get("task_linkage"))taskLinkage(*linkage,id,language);
    }
    if(!found)fail("capture lacks its selected component");
  }
  if(s.toolchains->size()!=s.expectations->size())fail("unselected captured toolchain");
  for(const auto &[key,value]:*c.getObject("function_owners")){if(key.str().size()>8192||(!value.getAsNull()&&!value.getAsString()))fail("invalid captured function owner");}
  return s;
}
}

JSON captureProject(const std::string &directory,const std::string &manifest,const std::string &source,const std::string &component,const std::set<std::string> &configurations,const std::map<std::string,std::string> &overlays,const std::set<std::string> &debugConfigurations,SourceLanguage language){
  if(configurations.empty()||configurations.size()>32)fail("capture requires1..32 configurations");
  auto root=fs::canonical(directory);fs::path manifestName=fs::path(manifest).filename();
  if(fs::canonical(manifest).parent_path()!=root)fail("task architecture manifest must be beside nex.json");
  ProjectBuildOptions preflight;preflight.kind="plan";preflight.component=component;preflight.configuration=*configurations.begin();preflight.compilerVersion=NEX_VERSION;preflight.compilerBuild=NEX_BUILD_ID;
  preflight.sourceLanguage=language;preflight.taskDebug=debugConfigurations.contains(preflight.configuration);preflight.sourceOverlays=overlays;preflight.archivedSources=!overlays.empty();
  buildProject(root.string(),manifest,source,preflight);
  auto architecture=parse(source),project=parse(read(root/"nex.json",1048576));
  const auto &definitions=*object(architecture).getObject("components"),&settings=*object(architecture).getObject("configurations");
  Object files,links,expectations,tools,owners,derivedLock;std::set<std::string> directories;
  std::map<std::string,fs::path> componentRoots,packages;
  std::map<std::string,std::string> observed;
  auto put=[&](const fs::path &physical,const std::string &data,bool placeholder=false){
    auto key=mapped(physical);
    if(auto previous=files.getString(key)){if(!placeholder&&*previous!=data)fail("inconsistent physical source capture: "+physical.string());return;}
    files[key]=data;
  };
  auto alias=[&](const fs::path &logical,const fs::path &physical){auto a=mapped(logical),b=mapped(physical);if(a==b)return;
    if(auto old=links.getString(a);old&&*old!=b)fail("conflicting captured source alias");links[a]=b;
  };
  for(const auto &[key,value]:definitions){
    const auto &c=object(value);auto physical=fs::canonical(root/text(c,"root"));componentRoots[key.str()]=physical;directories.insert(mapped(physical));
    alias(root/text(c,"root"),physical);auto entry=root/text(c,"entry");auto actual=fs::canonical(entry);alias(entry,actual);put(actual,"",true);
  }
  if(auto libs=object(project).getObject("libraries"))for(const auto &[key,value]:*libs)packages[key.str()]=fs::canonical(root/value.getAsString()->str());
  packages.try_emplace("std",fs::canonical(fs::path(resourceFile("runtime/runtime.cpp")).parent_path().parent_path()/"lib"));
  for(const auto &[key,value]:settings){(void)key;const auto &c=object(value);if(auto p=c.getString("toolchain")){auto logical=root/p->str(),actual=fs::canonical(logical);alias(logical,actual);put(actual,"{}\n",true);}}
  auto originalProject=read(root/"nex.json",1048576);auto originalLock=fs::is_regular_file(root/"nex.lock.json")?std::optional<std::string>(read(root/"nex.lock.json",4*1048576)):std::nullopt;
  Object usedLibraries;
  bool sourcesCaptured=false;
  for(const auto &configuration:configurations){
    ProjectBuildOptions options;options.kind="plan";options.component=component;options.configuration=configuration;options.compilerVersion=NEX_VERSION;options.compilerBuild=NEX_BUILD_ID;
    options.sourceLanguage=language;options.taskDebug=debugConfigurations.contains(configuration);options.sourceOverlays=overlays;options.archivedSources=!overlays.empty();
    auto plan=buildProject(root.string(),manifest,source,options);const auto &p=object(plan);Array descriptions;
    for(const auto &value:*p.getArray("components")){
      const auto &c=object(value);auto cName=text(c,"name"),entry=text(c,"entry");auto program=loadVersionedProgram((root/entry).string(),root.string(),language,overlays.empty(),overlays);
      if(c.getString("revision")!=revision(program)||c.getString("source_bundle_hash")!=hash(json(sourceBundle(program),false)))fail("component changed while capturing: "+cName);
      Object descriptor{{"name",cName},{"kind",text(c,"kind")},{"entry",entry},{"entry_function",*c.get("entry_function")},{"revision",revision(program)},{"source_bundle_hash",hash(json(sourceBundle(program),false))}};
      if(auto native=c.getObject("native_toolchain"))descriptor["native_toolchain_hash"]=text(*native,"hash");
      if(auto linkage=c.get("task_linkage"))descriptor["task_linkage"]=*linkage;
      descriptions.push_back(std::move(descriptor));
      if(sourcesCaptured)continue;
      auto lock=dependencyLock(program);for(const auto &[key,value]:*object(lock).getObject("dependencies"))derivedLock[key]=value;
      for(const auto &[key,unit]:program.units){
        auto physical=fs::weakly_canonical(unit.path);auto [found,inserted]=observed.emplace(physical.string(),unit.source);if(!inserted&&found->second!=unit.source)fail("source changed between component captures");
        // Replace only synthetic global-validation placeholders with real source.
        files[mapped(physical)]=unit.source;
        if(!key.starts_with("@"))alias(root/key,physical);
        else{
          std::string library,suffix;
          if(key.starts_with("@std/")){library="std";suffix=key.substr(5);}else{auto slash=key.find('/',5);library=key.substr(5,slash-5);suffix=key.substr(slash+1);}
          const auto &base=packages.at(library);directories.insert(mapped(base));alias(base/suffix,physical);
          usedLibraries[library]=(fs::path(mapped(base)).lexically_relative(mapped(root))).generic_string();
          if(fs::is_regular_file(base/"nex.json")){auto actual=fs::canonical(base/"nex.json");files[mapped(actual)]=read(actual,1048576);alias(base/"nex.json",actual);}
        }
      }
      if(cName==component)for(const auto &function:program.functions){
        auto physical=fs::weakly_canonical(program.units.at(function.unit).path);std::string owner;
        for(const auto &[name,base]:componentRoots)if(inside(physical,base)){owner=name;break;}
        JSON value=owner.empty()?JSON(nullptr):JSON(owner);
        if(auto old=owners.get(function.name);old&&*old!=value)fail("function has inconsistent component ownership");owners[function.name]=std::move(value);
      }
    }
    sourcesCaptured=true;expectations[configuration]=std::move(descriptions);
    const auto &configurationObject=object(*settings.get(configuration));BuildOptions native;native.target=configurationObject.getString("target").value_or("native").str();
    auto selected=configurationObject.getString("toolchain");if(selected)native.toolchain=fs::canonical(root/selected->str()).string();
    auto snapshot=inspectNativeToolchain(native);
    tools[configuration]=Object{{"hash",snapshot.hash},{"target",snapshot.target},{"host_compatible",snapshot.hostCompatible},{"manifest",snapshot.manifest},{"identity",snapshot.inputs},
      {"explicit",bool(selected)},{"file",selected?JSON(mapped(fs::canonical(root/selected->str()))):JSON(nullptr)}};
    if(selected)files[mapped(fs::canonical(root/selected->str()))]=json(snapshot.manifest)+"\n";
  }
  auto normalizedProject=object(project);normalizedProject["libraries"]=std::move(usedLibraries);
  files[mapped(root/"nex.json")]=json(JSON(std::move(normalizedProject)))+"\n";files[mapped(root/manifestName)]=source;
  if(!overlays.empty())files[mapped(root/"nex.lock.json")]=json(Object{{"schema","nex.lock/1"},{"language",programLanguage(language)},{"dependencies",std::move(derivedLock)}})+"\n";
  else if(originalLock)files[mapped(root/"nex.lock.json")]=*originalLock;
  if(read(root/"nex.json",1048576)!=originalProject||read(root/manifestName,262144)!=source||
     (fs::is_regular_file(root/"nex.lock.json")?std::optional<std::string>(read(root/"nex.lock.json",4*1048576)):std::nullopt)!=originalLock)fail("project metadata changed during capture");
  for(const auto &[path,data]:observed)if(overlays.contains(path)?overlays.at(path)!=data:readFile(path)!=data)fail("source changed during capture");
  Array dirs;for(const auto &p:directories)dirs.push_back(p);
  JSON result=Object{{"schema","nex.project-capture/1"},{"language",programLanguage(language)},{"project_root",mapped(root)},{"manifest",manifestName.generic_string()},
    {"component",component},{"architecture_hash",hash(json(architecture,false))},{"original_project_manifest_hash",hash(originalProject)},
    {"files",std::move(files)},{"links",std::move(links)},{"directories",std::move(dirs)},{"expectations",std::move(expectations)},{"toolchains",std::move(tools)},{"function_owners",std::move(owners)}};
  shape(result,language);if(json(result).size()+1>64*1048576)fail("serialized project capture exceeds64MiB");return result;
}

std::string materializeProjectCapture(const JSON &capture,const std::string &directory,SourceLanguage language){
  auto s=shape(capture,language);fs::path base=fs::absolute(directory);
  if(fs::exists(base)||!fs::create_directories(base))fail("project capture needs a new container");fs::permissions(base,fs::perms::owner_all,fs::perm_options::replace);base=fs::canonical(base);
  for(const auto &path:s.directories)fs::create_directories(base/path);
  for(const auto &[path,value]:*s.files){auto output=base/path.str();fs::create_directories(output.parent_path());writeFile(output.string(),value.getAsString()->str());}
  std::vector<std::pair<std::string,std::string>> links;for(const auto &[path,target]:*s.links)links.emplace_back(path.str(),target.getAsString()->str());
  std::sort(links.begin(),links.end(),[](const auto &a,const auto &b){auto depth=[](const auto &v){return std::count(v.begin(),v.end(),'/');};return std::make_pair(depth(a.first),a.first)<std::make_pair(depth(b.first),b.first);});
  for(const auto &[path,target]:links){
    auto output=base/path,actual=fs::canonical(base/target);if(!inside(actual,base))fail("capture link target escapes container");
    if(fs::exists(output)){if(fs::canonical(output)!=actual)fail("capture link collides with a different input");continue;}
    fs::create_directories(output.parent_path());auto parent=fs::canonical(output.parent_path());if(!inside(parent,base))fail("capture link parent escapes container");
    fs::create_symlink(actual.lexically_relative(parent),output);
  }
  verifyProjectCapture(capture,base.string(),language);return (base/s.root).string();
}
void verifyProjectCapture(const JSON &capture,const std::string &directory,SourceLanguage language){
  auto s=shape(capture,language);auto base=fs::canonical(directory);
  for(const auto &path:s.directories){auto expected=base/path,actual=fs::canonical(expected);if(actual!=expected||!fs::is_directory(actual))fail("captured directory changed");}
  for(const auto &[path,value]:*s.files){auto expected=base/path.str(),actual=fs::canonical(expected);if(actual!=expected||read(actual,64*1048576)!=value.getAsString()->str())fail("captured project input changed: "+path.str());}
  for(const auto &[path,target]:*s.links){auto a=fs::canonical(base/path.str()),b=fs::canonical(base/target.getAsString()->str());if(!inside(a,base)||a!=b)fail("captured alias changed");}
}
void validateProjectCaptureData(const JSON &capture,SourceLanguage language){shape(capture,language);}
void validateProjectCapturePlans(const JSON &capture,const std::string &directory,SourceLanguage language){
  auto s=shape(capture,language);verifyProjectCapture(capture,directory,language);auto base=fs::canonical(directory),root=fs::canonical(base/s.root);
  for(const auto &[configuration,expected]:*s.expectations){
    const auto &record=*s.toolchains->getObject(configuration);BuildOptions native;native.target=text(record,"target");
    if(record.getBoolean("explicit").value_or(false))native.toolchain=(base/text(record,"file")).string();
    auto toolchain=inspectNativeToolchain(native);
    if(toolchain.hash!=text(record,"hash")||toolchain.manifest!=*record.get("manifest")||toolchain.inputs!=*record.get("identity"))throw Error("E_TASK_TOOLCHAIN","captured/current project toolchain data differs");
    ProjectBuildOptions options;options.kind="plan";options.component=text(object(capture),"component");options.configuration=configuration.str();options.compilerVersion=NEX_VERSION;options.compilerBuild=NEX_BUILD_ID;options.sourceLanguage=language;
    for(const auto &entry:*expected.getAsArray())if(auto linkage=entry.getAsObject()->getObject("task_linkage"))options.taskDebug|=linkage->getString("schema")=="nex.project-task-linkage/4"||linkage->getString("schema")=="nex.project-task-linkage/7"||linkage->getString("schema")=="nex.project-task-linkage/10"||linkage->getString("schema")=="nex.project-task-linkage/13";
    auto plan=buildProject(root.string(),(root/s.manifest).string(),readFile((root/s.manifest).string()),options);
    auto actual=object(plan).getArray("components"),entries=expected.getAsArray();if(!actual||!entries||actual->size()!=entries->size())fail("captured component selection changed");
    for(size_t i=0;i<entries->size();++i){
      const auto &a=object((*actual)[i]),&e=object((*entries)[i]);
      for(auto field:{"name","kind","entry","entry_function","revision","source_bundle_hash"})if(!a.get(field)||!e.get(field)||*a.get(field)!=*e.get(field))fail("captured component/source identity changed");
      auto actualLinkage=a.get("task_linkage"),expectedLinkage=e.get("task_linkage");
      if(bool(actualLinkage)!=bool(expectedLinkage)||(actualLinkage&&*actualLinkage!=*expectedLinkage))fail("captured task provider ownership/contracts changed");
      if(auto fingerprint=e.getString("native_toolchain_hash")){auto native=a.getObject("native_toolchain");if(!native||native->getString("hash")!=fingerprint)throw Error("E_TASK_TOOLCHAIN","captured project toolchain fingerprint changed");}
      auto program=loadVersionedProgram((root/text(a,"entry")).string(),root.string(),language);
      for(const auto &[key,unit]:program.units){(void)key;auto actual=fs::canonical(unit.path);if(!inside(actual,base))fail("project source fell back outside the captured namespace");auto saved=s.files->getString(actual.lexically_relative(base).generic_string());if(!saved||*saved!=unit.source)fail("project source is not indexed in the capture");}
    }
  }
}
}
