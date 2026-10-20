#include "nex/project_build.h"
#include "nex/backend.h"
#include "nex/incremental.h"
#include "nex/native_toolchain.h"
#include "nex/web.h"
#include "llvm/Support/Error.h"
#include <algorithm>
#include <filesystem>
#include <functional>

namespace nex {
namespace {
namespace fs=std::filesystem;
using Object=llvm::json::Object;
struct Component {
  std::string name,kind,root,entry,function;
  fs::path physicalRoot;
  std::map<std::string,std::string> dependencies;
  std::vector<std::string> exports;
};
struct Configuration {std::string name,profile,target,toolchain;};
struct Prepared {std::string name;Program program;BuildOptions options;llvm::json::Value description;};
[[noreturn]] void fail(const std::string &message,const std::string &code="E_PROJECT_BUILD") {throw Error(code,message);}
void keys(const Object &o,const std::set<std::string> &allowed) {
  for(const auto &[k,v]:o){(void)v;if(!allowed.contains(k.str()))fail("unknown project build field: "+k.str());}
}
std::string text(const Object &o,const std::string &key,const std::string &fallback="",bool required=false) {
  auto v=o.get(key);if(!v){if(required)fail("missing project build field: "+key);return fallback;}
  auto s=v->getAsString();if(!s||s->empty()||s->size()>4096||s->find('\0')!=llvm::StringRef::npos)fail("invalid project build string: "+key);
  return s->str();
}
bool identifier(const std::string &s) {
  auto alpha=[](char c){return (c>='a'&&c<='z')||(c>='A'&&c<='Z')||c=='_';};
  return !s.empty()&&s.size()<=64&&alpha(s.front())&&std::all_of(s.begin(),s.end(),[&](char c){return alpha(c)||(c>='0'&&c<='9');});
}
bool inside(const fs::path &path,const fs::path &base) {
  auto rel=path.lexically_relative(base);if(rel.empty())return path==base;
  return !rel.is_absolute()&&std::none_of(rel.begin(),rel.end(),[](const auto &p){return p=="..";});
}
fs::path path(const fs::path &base,const std::string &value,bool directory) {
  fs::path relative(value);
  if(value.find_first_of("\\:")!=std::string::npos||relative.is_absolute()||relative.generic_string()!=relative.lexically_normal().generic_string()||
     std::any_of(relative.begin(),relative.end(),[](const auto &p){return p==".."||p==".git"||p==".nex";}))fail("project build paths must be normalized relative paths: "+value);
  auto p=fs::weakly_canonical(base/relative);
  if(!inside(p,base))fail("project build path escapes project root: "+value);
  if(directory?!fs::is_directory(p):!fs::is_regular_file(p))fail("missing project build input: "+value);
  return p;
}
const Object &object(const Object &o,const std::string &key) {
  auto p=o.getObject(key);if(!p)fail("project build field must be an object: "+key);return *p;
}
}

llvm::json::Value buildProject(const std::string &directory,const std::string &manifest,
                              const std::string &source,const ProjectBuildOptions &options) {
  if(options.kind!="plan"&&options.kind!="build")fail("project kind must be plan or build","E_OPTION");
  auto parsed=llvm::json::parse(source);if(!parsed)throw Error("E_JSON",llvm::toString(parsed.takeError()));
  auto top=parsed->getAsObject();if(!top)fail("project build manifest must be an object");
  keys(*top,{"schema","components","configurations","default_configuration"});
  if(text(*top,"schema","",true)!="nex.project-build/1")fail("expected nex.project-build/1");
  auto root=fs::canonical(directory);
  if(!fs::is_regular_file(root/"nex.json"))fail("project builds require nex.json beside the build description");
  validateProjectMetadata(root.string());
  auto sourceManifest=readFile((root/"nex.json").string());
  auto sourceLock=fs::is_regular_file(root/"nex.lock.json")?std::optional<std::string>(readFile((root/"nex.lock.json").string())):std::nullopt;
  const auto &definitions=object(*top,"components"),&settings=object(*top,"configurations");
  if(definitions.empty()||definitions.size()>128||settings.empty()||settings.size()>32)fail("project builds require 1..128 components and 1..32 configurations");
  std::map<std::string,Component> components;
  for(const auto &[name,value]:definitions) {
    if(!identifier(name.str()))fail("invalid component name: "+name.str());
    auto o=value.getAsObject();if(!o)fail("component must be an object: "+name.str());
    keys(*o,{"kind","root","entry","entry_function","dependencies","exports"});
    Component c;c.name=name.str();c.kind=text(*o,"kind","",true);c.root=text(*o,"root","",true);c.entry=text(*o,"entry","",true);
    if(c.kind!="source"&&c.kind!="executable"&&c.kind!="static_library"&&c.kind!="server"&&c.kind!="web")
      fail("unsupported component kind: "+c.kind+"; shared-library output and accelerator components are pending","E_PROJECT_CAPABILITY");
    c.physicalRoot=path(root,c.root,true);auto entry=path(root,c.entry,false);
    if(!c.entry.ends_with(".nex")||!inside(entry,c.physicalRoot))fail("component entry must be a .nex file inside its root: "+c.name);
    if(c.kind=="source"||c.kind=="web") {
      if(o->get("entry_function"))fail("source/web components do not select entry_function: "+c.name);
    } else c.function=text(*o,"entry_function",c.kind=="server"?"handle":"main",c.kind=="static_library");
    if(auto value=o->get("exports")){
      auto names=value->getAsArray();if(c.kind!="static_library"||!names||names->size()>128)fail("exports requires a static_library and at most128 concrete functions");
      std::set<std::string> unique;
      for(const auto &name:*names){auto s=name.getAsString();if(!s||s->empty()||s->size()>4096||s->find('\0')!=llvm::StringRef::npos||!unique.insert(s->str()).second)fail("invalid or duplicate library export");c.exports.push_back(s->str());}
    }
    if(auto deps=o->get("dependencies")) {
      auto mapping=deps->getAsObject();if(!mapping||mapping->size()>128)fail("dependencies must be an object of at most128 components");
      for(const auto &[dep,link]:*mapping) {
        if(!identifier(dep.str()))fail("invalid dependency component name");
        auto linkage=link.getAsString();if(linkage!="source"&&linkage!="static")fail("component dependencies require source or static linkage; DLL consumption is pending","E_PROJECT_CAPABILITY");
        c.dependencies[dep.str()]=linkage->str();
      }
    }
    components.emplace(c.name,std::move(c));
  }
  for(auto first=components.begin();first!=components.end();++first) {
    for(auto second=std::next(first);second!=components.end();++second)
      if(inside(first->second.physicalRoot,second->second.physicalRoot)||inside(second->second.physicalRoot,first->second.physicalRoot))
        fail("component roots overlap: "+first->first+" and "+second->first);
    for(const auto &[name,link]:first->second.dependencies) {
      (void)link;auto found=components.find(name);if(found==components.end())fail("unknown dependency component: "+name);
      if(found->second.kind!="source"&&found->second.kind!="static_library")fail("only source/static_library components can be source dependencies: "+name);
      if(link=="static"&&(found->second.kind!="static_library"||first->second.kind=="web"||first->second.kind=="source"))fail("static linkage requires a native consumer and static_library dependency","E_PROJECT_CAPABILITY");
    }
  }
  std::map<std::string,Configuration> configurations;
  for(const auto &[name,value]:settings) {
    if(!identifier(name.str()))fail("invalid configuration name");auto o=value.getAsObject();if(!o)fail("configuration must be an object");
    keys(*o,{"profile","target","toolchain"});Configuration c;c.name=name.str();c.profile=text(*o,"profile","debug");c.target=text(*o,"target","native");
    if(c.profile!="debug"&&c.profile!="profile"&&c.profile!="release")fail("configuration profile must be debug, profile or release");
    if(c.target=="web"||c.target=="server"||c.target=="wasm")fail("configuration target selects a native CPU ABI; component kind selects web/server");
    if(o->get("toolchain"))c.toolchain=path(root,text(*o,"toolchain"),false).string();
    configurations.emplace(c.name,std::move(c));
  }
  auto defaultConfiguration=text(*top,"default_configuration","",true);
  if(!configurations.contains(defaultConfiguration))fail("unknown default configuration: "+defaultConfiguration);
  auto selectedConfiguration=options.configuration.empty()?defaultConfiguration:options.configuration;
  if(!configurations.contains(selectedConfiguration))fail("unknown configuration: "+selectedConfiguration);
  if(!options.component.empty()&&!components.contains(options.component))fail("unknown component: "+options.component);
  const auto &configuration=configurations.at(selectedConfiguration);
  std::vector<std::string> order;std::map<std::string,int> state;
  std::function<void(const std::string&)> visit=[&](const auto &name) {
    if(state[name]==2)return;if(state[name]==1)fail("component dependency cycle at "+name,"E_PROJECT_CYCLE");state[name]=1;
    for(const auto &[dep,link]:components.at(name).dependencies){(void)link;visit(dep);}state[name]=2;order.push_back(name);
  };
  for(const auto &[name,c]:components){(void)c;visit(name);} // Validate even unselected architecture edges.
  std::set<std::string> selected;
  std::function<void(const std::string&)> select=[&](const auto &name){if(!selected.insert(name).second)return;for(const auto &[dep,link]:components.at(name).dependencies){(void)link;select(dep);}};
  if(options.component.empty())for(const auto &[name,c]:components){(void)c;select(name);}else select(options.component);
  auto owner=[&](const fs::path &file)->std::string {
    auto physical=fs::weakly_canonical(file);for(const auto &[name,c]:components)if(inside(physical,c.physicalRoot))return name;
    return {};
  };
  auto unitOwner=[&](const std::string &key,const auto &unit){
    auto name=owner(unit.path);
    if(name.empty()&&!key.starts_with("@"))fail("project source is outside all component roots: "+unit.path,"E_PROJECT_BOUNDARY");
    return name;
  };
  std::map<std::string,std::string> capturedSources;
  std::vector<Prepared> prepared;llvm::json::Array descriptions;size_t sourceBytes=0;
  std::set<std::string> binaryProviders;
  for(const auto &name:selected)for(const auto &[dep,link]:components.at(name).dependencies)if(link=="static")binaryProviders.insert(dep);
  for(const auto &name:order) {
    if(!selected.contains(name))continue;const auto &c=components.at(name);
    auto program=loadProgram((root/c.entry).string(),root.string());llvm::json::Array sources;
    for(const auto &[key,unit]:program.units) {
      sourceBytes+=unit.source.size();if(sourceBytes>64*1048576)fail("selected component source closures exceed64MiB","E_PROJECT_LIMIT");
      auto [captured,inserted]=capturedSources.emplace(unit.path,unit.source);
      if(!inserted&&captured->second!=unit.source)fail("source changed between selected component closures: "+unit.path,"E_PROJECT_INPUT_CHANGED");
      auto from=unitOwner(key,unit);llvm::json::Array imports;
      for(const auto &dependency:unit.imports) {
        auto to=unitOwner(dependency.target,program.units.at(dependency.target));
        if(!from.empty()&&!to.empty()&&from!=to&&!components.at(from).dependencies.contains(to))
          throw Error("E_PROJECT_BOUNDARY","undeclared source dependency "+from+" -> "+to,dependency.span);
        if(from.empty()&&!to.empty())throw Error("E_PROJECT_BOUNDARY","configured libraries cannot import project components",dependency.span);
        imports.push_back(Object{{"target",dependency.target},{"component",to.empty()?llvm::json::Value(nullptr):llvm::json::Value(to)}});
      }
      sources.push_back(Object{{"path",key},{"module",unit.module},{"component",from.empty()?llvm::json::Value(nullptr):llvm::json::Value(from)},{"source_hash",hash(unit.source)},{"imports",std::move(imports)}});
    }
    BuildOptions native;native.profile=configuration.profile;native.entry=c.function;native.libraryEntry=c.kind=="static_library";native.toolchain=configuration.toolchain;
    native.libraryExports=c.exports;native.projectLibraryABI=c.kind!="source"&&c.kind!="web";
    native.codeOnlyLibrary=binaryProviders.contains(name);
    native.target=c.kind=="server"?"server":configuration.target;
    llvm::json::Value toolchain=nullptr,web=nullptr;
    if(c.kind=="web")web=inspectWebApp(program);
    else if(c.kind!="source") {
      auto abiOptions=native;abiOptions.target=configuration.target;auto declared=configureNative(abiOptions);auto actual=configureNative(native);
      if(declared.target!=actual.target)fail("server target requires a matching explicit toolchain for this configuration","E_TARGET");
      auto captured=inspectNativeToolchain(native);toolchain=Object{{"hash",captured.hash},{"target",captured.target},{"host_compatible",captured.hostCompatible}};
      validateNativeBuildEntry(program,native);
      if(c.kind=="static_library"&&owner(program.units.at(program.function(c.function).unit).path)!=name)fail("library entry must be owned by "+name,"E_PROJECT_EXPORT");
      for(const auto &entry:c.exports){const auto &f=program.function(entry);if(!f.exported||owner(program.units.at(f.unit).path)!=name)fail("library exports must be public concrete functions owned by "+name,"E_PROJECT_EXPORT");}
    }
    Object dependencies;for(const auto &[dep,link]:c.dependencies)dependencies[dep]=link;
    llvm::json::Array exports;for(const auto &entry:c.exports)exports.push_back(program.function(entry).name);
    auto description=llvm::json::Value(Object{{"name",name},{"kind",c.kind},{"root",c.root},{"entry",c.entry},{"entry_function",c.function.empty()?llvm::json::Value(nullptr):llvm::json::Value(program.function(c.function).name)},{"exports",std::move(exports)},{"code_only_library",native.codeOnlyLibrary},
      {"dependencies",std::move(dependencies)},{"revision",revision(program)},{"source_bundle_hash",hash(json(sourceBundle(program),false))},{"sources",std::move(sources)},
      {"native_toolchain",std::move(toolchain)},{"web_projection",std::move(web)}});
    prepared.push_back({name,std::move(program),std::move(native),std::move(description)});
  }
  // Bind each binary edge before invoking tools. Every ordinary concrete
  // definition in a binary-owned component must actually exist in its archive.
  // New generic specializations are explicitly instantiated in the consumer.
  std::map<std::string,Prepared*> byName;for(auto &item:prepared)byName[item.name]=&item;
  std::map<std::string,std::map<std::string,std::string>> contracts;
  for(auto &item:prepared)if(components.at(item.name).kind!="source"&&components.at(item.name).kind!="web"){
    for(const auto &unit:planNative(item.program,item.options.entry,item.options.libraryExports,true).units){
      auto parsed=llvm::json::parse(unit.contract);if(!parsed)fail("invalid native contract","E_INTERNAL");parsed->getAsObject()->erase("unit");
      contracts[item.name][unit.identity]=hash(json(*parsed,false));
    }
  }
  for(auto &item:prepared){
    const auto &c=components.at(item.name);if(c.kind=="source"||c.kind=="web")continue;
    std::set<std::string> binaries,walked;
    std::function<void(const std::string&)> gather=[&](const auto &name){if(!walked.insert(name).second)return;for(const auto &[dep,link]:components.at(name).dependencies){if(link=="static")binaries.insert(dep);gather(dep);}};gather(item.name);
    std::map<std::string,fs::path> moduleOrigins;
    auto origins=[&](const Program &p){for(const auto &[key,u]:p.units){(void)key;auto physical=fs::weakly_canonical(u.path);auto [found,inserted]=moduleOrigins.emplace(u.module,physical);if(!inserted&&found->second!=physical)fail("linked module identity resolves to different files: "+u.module,"E_PROJECT_ABI");}};
    origins(item.program);for(const auto &name:binaries)origins(byName.at(name)->program);
    std::set<std::pair<std::string,bool>> visited;std::set<std::string> instantiated;
    std::function<void(const std::string&,bool)> validate=[&](const auto &function,bool instantiate){
      if(!visited.insert({function,instantiate}).second)return;
      const auto &contract=contracts[item.name].at(function);
      const auto &f=item.program.function(function);auto owned=owner(item.program.units.at(f.unit).path);
      if(binaries.contains(owned)){
        auto provider=contracts.at(owned).find(function);
        if(provider==contracts.at(owned).end()){
          instantiate|=!f.templateName.empty();
          if(!instantiate)fail("binary dependency "+owned+" does not export the concrete closure containing "+function+"; add it to exports","E_PROJECT_EXPORT");
          instantiated.insert(function);
        }else{
          if(provider->second!=contract)fail("binary dependency function/type context differs: "+function,"E_PROJECT_ABI");
          instantiate=false;
        }
      }
      for(const auto &callee:f.dependencies)validate(callee,instantiate);
    };
    validate(item.program.function(item.options.entry).name,false);
    for(const auto &entry:item.options.libraryExports)validate(item.program.function(entry).name,false);
    llvm::json::Array instances;for(const auto &name:instantiated)instances.push_back(name);(*item.description.getAsObject())["consumer_instantiations"]=std::move(instances);
  }
  for(const auto &item:prepared)descriptions.push_back(item.description);
  if(readFile((root/"nex.json").string())!=sourceManifest||
     (fs::is_regular_file(root/"nex.lock.json")?std::optional<std::string>(readFile((root/"nex.lock.json").string())):std::nullopt)!=sourceLock)
    fail("project metadata or dependency lock changed while planning","E_PROJECT_INPUT_CHANGED");
  for(const auto &[file,text]:capturedSources)if(readFile(file)!=text)fail("captured source changed while planning: "+file,"E_PROJECT_INPUT_CHANGED");
  Object plan{{"schema","nex.project-plan/1"},{"ok",true},{"language",languageVersion},{"compiler",Object{{"version",options.compilerVersion},{"build",options.compilerBuild}}},
    {"root",root.string()},{"manifest",manifest},{"manifest_hash",hash(source)},{"source_project_manifest_hash",hash(sourceManifest)},
    {"configuration",Object{{"name",configuration.name},{"profile",configuration.profile},{"target",configuration.target},{"toolchain",configuration.toolchain.empty()?llvm::json::Value(nullptr):llvm::json::Value(configuration.toolchain)}}},
    {"selected_component",options.component.empty()?llvm::json::Value(nullptr):llvm::json::Value(options.component)},{"components",std::move(descriptions)},
    {"source_checked",true},{"graph_store_opened",false},{"external_tools_invoked",false},{"target_execution_verified",false},{"artifact_dependencies_inspected",false}};
  auto serialized=json(llvm::json::Value(Object(plan)),false);if(serialized.size()>8*1048576)fail("project plan exceeds8MiB","E_PROJECT_LIMIT");
  auto planHash=hash(serialized);plan["plan_hash"]=planHash;
  if(options.kind=="plan")return plan;
  auto cache=fs::absolute(options.directory.empty()?(root/".nex/build").string():options.directory);
  llvm::json::Array artifacts;
  std::map<std::string,BuildResult> nativeResults;
  // All selected source closures, import edges and entry contracts were checked
  // above. Build consumes those captured Programs, not subsequently edited files.
  for(auto &item:prepared) {
    const auto &c=components.at(item.name);if(c.kind=="source")continue;
    if(c.kind=="web") {
      auto result=buildWebApp(item.program,cache.string(),configuration.profile);
      artifacts.push_back(Object{{"component",item.name},{"kind","web"},{"result",std::move(result)}});
    } else {
      auto expected=item.description.getAsObject()->getObject("native_toolchain")->getString("hash")->str();
      if(inspectNativeToolchain(item.options).hash!=expected)fail("native toolchain changed after project planning","E_PROJECT_INPUT_CHANGED");
      std::set<std::string> binaries,walked;
      std::function<void(const std::string&)> gather=[&](const auto &name){if(!walked.insert(name).second)return;for(const auto &[dep,link]:components.at(name).dependencies){if(link=="static")binaries.insert(dep);gather(dep);}};gather(item.name);
      // A caller archive precedes its dependency archives for one-pass linkers.
      for(auto name=order.rbegin();name!=order.rend();++name)if(binaries.contains(*name)){
        const auto &dependency=nativeResults.at(*name);
        item.options.libraries.push_back({dependency.executable,hash(readFile(dependency.executable)),dependency.libraryABI,dependency.functionContracts});
      }
      auto built=build(item.program,cache.string(),item.options);
      nativeResults[item.name]=built;
      artifacts.push_back(Object{{"component",item.name},{"kind",c.kind},{"artifact",built.executable},{"cached",built.cached},{"build_key",built.key},
        {"target",built.target},{"compiler_target",built.compilerTarget},{"host_compatible",built.hostCompatible},{"metadata",(fs::path(built.executable).parent_path()/"build.json").string()},
        {"debug_manifest",(fs::path(built.executable).parent_path()/"debug.json").string()},{"notices",built.notices},{"compilation",built.compilation}});
    }
  }
  return Object{{"schema","nex.project-build-result/1"},{"ok",true},{"plan_hash",planHash},{"plan",std::move(plan)},{"artifacts",std::move(artifacts)},
    {"graph_store_opened",false},{"external_tools_invoked",true},{"target_execution_verified",false},{"artifact_dependencies_inspected",false}};
}
}
