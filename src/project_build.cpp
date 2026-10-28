#include "nex/project_build.h"
#include "nex/task_ir.h"
#include "nex/task_provider_debug.h"
#include "nex/task_limits.h"
#include "nex/task_frontend.h"
#include "nex/server_workload.h"
#include "nex/backend.h"
#include "nex/incremental.h"
#include "nex/native_toolchain.h"
#include "nex/native_images.h"
#include "nex/debug_session.h"
#include "nex/native_diagnostics.h"
#include "nex/foreign_catalogue.h"
#include "nex/task_process.h"
#include "llvm/TargetParser/Triple.h"
#include "nex/web.h"
#include "llvm/Support/Error.h"
#include "llvm/Support/SHA256.h"
#include "llvm/ADT/StringExtras.h"
#include <cstdio>
#include <cstdlib>
#include <fcntl.h>
#include <unistd.h>
#ifdef __linux__
#include <sys/syscall.h>
#include <linux/fs.h>
#endif
#include <algorithm>
#include <filesystem>
#include <functional>

namespace nex {
struct ProjectPackageProjection {
  std::function<void()> verify;
  std::map<std::string,std::string> sourceHashes,toolchains;
  std::map<std::string,ForeignPackageArtifact> applications;
  llvm::json::Value report=nullptr;
};
namespace {
namespace fs=std::filesystem;
using Object=llvm::json::Object;
struct Component {
  std::string name,kind,root,entry,function;
  fs::path physicalRoot;
  std::map<std::string,std::string> dependencies;
  std::vector<std::string> exports;
};
struct Configuration {std::string name,profile,target,toolchain;nexrt::TaskExecutionLimits taskLimits;bool taskLimitsSpecified=false;};
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
llvm::json::Value runCaptured(const std::vector<std::string> &arguments,const fs::path &root,unsigned seconds){
  auto logs=createTemporaryDirectory("nex-project-run");
  try{
    auto child=runTaskProcess(arguments,root.string(),{},seconds,logs);fs::remove_all(logs);
    auto code=child.timedOut?124:child.outputLimit?125:child.process.code;
    return Object{{"ok",code==0},{"exit_code",code},{"stdout",child.process.output},{"stderr",child.process.errors},
      {"timed_out",child.timedOut},{"output_limit",child.outputLimit},{"interrupted",child.interrupted}};
  }catch(...){fs::remove_all(logs);throw;}
}
int runInteractive(const std::vector<std::string> &arguments,const fs::path &root){
  struct Directory {fs::path old=fs::current_path();~Directory(){std::error_code ignored;fs::current_path(old,ignored);}} directory;
  fs::current_path(root);return execute(arguments);
}
void boundTestResult(Object &row,const fs::path &cache){
  if(json(llvm::json::Value(Object(row)),false).size()<=32768)return;
  fs::create_directories(cache);auto model=(cache/"test-result-XXXXXX").string();
  if(!::mkdtemp(model.data()))fail("cannot retain detailed project test result","E_PROJECT_BUILD");
  row["report"]=(fs::path(model)/"result.json").string();row["response_truncated"]=true;
  writeFile((fs::path(model)/"result.json").string(),json(llvm::json::Value(Object(row)))+"\n");
  auto summarize=[](const llvm::json::Value &value){
    Object summary;auto original=value.getAsObject();if(!original)return llvm::json::Value(std::move(summary));
    for(auto key:{"exit_code","timed_out","output_limit","interrupted"})if(auto v=original->get(key))summary[key]=*v;
    for(auto key:{"stdout","stderr"})if(auto text=original->getString(key)){
      auto count=std::min(text->size(),size_t(4096));
      while(count&&count<text->size()&&(static_cast<unsigned char>((*text)[count])&0xc0)==0x80)--count;
      summary[key]=text->take_front(count).str();summary[std::string(key)+"_bytes"]=int64_t(text->size());
    }
    return llvm::json::Value(std::move(summary));
  };
  row["observation"]=summarize(*row.get("observation"));
  if(auto value=row.get("typescript_observation"))row["typescript_observation"]=summarize(*value);
  row.erase("artifact");
  if(json(llvm::json::Value(Object(row)),false).size()>32768)row.erase("reference_error");
  if(json(llvm::json::Value(Object(row)),false).size()>32768)fail("project test summary exceeds32KiB; detailed report retained","E_PROJECT_LIMIT");
}
}

llvm::json::Value buildProject(const std::string &directory,const std::string &manifest,
                              const std::string &source,const ProjectBuildOptions &options) {
  const bool withWorkload=!options.workload.empty();
  if(withWorkload&&options.kind!="plan"&&options.kind!="profile")fail("--workload requires project plan or profile","E_OPTION");
  const bool execution=options.kind=="run"||options.kind=="debug"||options.kind=="profile",buildTest=options.kind=="build-test",testing=options.kind=="test"||buildTest;
  if(options.kind!="plan"&&options.kind!="build"&&options.kind!="package"&&!execution&&!testing)fail("project kind must be plan, build, package, run, test, build-test, debug or profile","E_OPTION");
  if(options.taskDebug&&options.kind!="plan"&&options.kind!="build"&&options.kind!="package")fail("--task-debug applies only to project plan/build/package","E_OPTION");
  if(buildTest&&options.selectedTest.empty())fail("build-test requires --symbol NAME","E_OPTION");
  if(options.kind=="debug"&&options.adapter!="lldb"&&options.adapter!="dap"&&options.adapter!="nex-dap")fail("debug adapter must be lldb, dap or nex-dap","E_OPTION");
  if(options.kind=="debug")validateNativeDebugArguments(options.arguments);
  if(options.kind=="run"&&!options.machine&&options.explicitTimeout)fail("supervised project run --timeout requires --json","E_OPTION");
  fs::path packageOutput;
  if(options.kind=="package"){
    if(options.package.directory.empty())fail("project package requires --directory NEW_DIRECTORY","E_OPTION");
    packageOutput=fs::absolute(options.package.directory).lexically_normal();std::error_code error;
    if(fs::exists(fs::symlink_status(packageOutput,error)))fail("project package destination already exists","E_EXISTS");
    auto parent=fs::canonical(packageOutput.parent_path(),error);
    if(error||!fs::is_directory(parent))fail("project package destination requires an existing parent directory","E_PROJECT_PACKAGE");
    packageOutput=parent/packageOutput.filename();
  }
  auto parsed=llvm::json::parse(source);if(!parsed)throw Error("E_JSON",llvm::toString(parsed.takeError()));
  auto top=parsed->getAsObject();if(!top)fail("project build manifest must be an object");
  keys(*top,{"schema","components","configurations","default_configuration"});
  if(text(*top,"schema","",true)!="nex.project-build/1")fail("expected nex.project-build/1");
  auto root=fs::canonical(directory);
  if(!fs::is_regular_file(root/"nex.json"))fail("project builds require nex.json beside the build description");
  validateProjectMetadata(root.string(),options.sourceLanguage);
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
    if(c.kind!="source"&&c.kind!="executable"&&c.kind!="static_library"&&c.kind!="shared_library"&&c.kind!="server"&&c.kind!="web")
      fail("unsupported component kind: "+c.kind+"; accelerator components are pending","E_PROJECT_CAPABILITY");
    c.physicalRoot=path(root,c.root,true);auto entry=path(root,c.entry,false);
    if(!c.entry.ends_with(".nex")||!inside(entry,c.physicalRoot))fail("component entry must be a .nex file inside its root: "+c.name);
    if(c.kind=="source"||c.kind=="web") {
      if(o->get("entry_function"))fail("source/web components do not select entry_function: "+c.name);
    } else c.function=text(*o,"entry_function",c.kind=="server"?"handle":"main",(c.kind=="static_library"||c.kind=="shared_library"));
    if(auto value=o->get("exports")){
      auto names=value->getAsArray();if((c.kind!="static_library"&&c.kind!="shared_library")||!names||names->size()>128)fail("exports requires a native library and at most128 concrete functions");
      std::set<std::string> unique;
      for(const auto &name:*names){auto s=name.getAsString();if(!s||s->empty()||s->size()>4096||s->find('\0')!=llvm::StringRef::npos||!unique.insert(s->str()).second)fail("invalid or duplicate library export");c.exports.push_back(s->str());}
    }
    if(auto deps=o->get("dependencies")) {
      auto mapping=deps->getAsObject();if(!mapping||mapping->size()>128)fail("dependencies must be an object of at most128 components");
      for(const auto &[dep,link]:*mapping) {
        if(!identifier(dep.str()))fail("invalid dependency component name");
        auto linkage=link.getAsString();if(linkage!="source"&&linkage!="static"&&linkage!="dynamic")fail("component dependencies require source, static or dynamic linkage","E_PROJECT_CAPABILITY");
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
      if(found->second.kind!="source"&&found->second.kind!="static_library"&&found->second.kind!="shared_library")fail("only source/native library components can be dependencies: "+name);
      if(link=="static"&&(found->second.kind!="static_library"||first->second.kind=="web"||first->second.kind=="source"))fail("static linkage requires a native consumer and static_library dependency","E_PROJECT_CAPABILITY");
      if(link=="dynamic"&&(found->second.kind!="shared_library"||first->second.kind=="web"||first->second.kind=="source"))fail("dynamic linkage requires a native consumer and shared_library dependency","E_PROJECT_CAPABILITY");
    }
  }
  std::map<std::string,Configuration> configurations;
  for(const auto &[name,value]:settings) {
    if(!identifier(name.str()))fail("invalid configuration name");auto o=value.getAsObject();if(!o)fail("configuration must be an object");
    keys(*o,{"profile","target","toolchain","task_limits"});Configuration c;c.name=name.str();c.profile=text(*o,"profile","debug");c.target=text(*o,"target","native");
    if(c.profile!="debug"&&c.profile!="profile"&&c.profile!="release")fail("configuration profile must be debug, profile or release");
    if(c.target=="web"||c.target=="server"||c.target=="wasm")fail("configuration target selects a native CPU ABI; component kind selects web/server");
    if(o->get("toolchain"))c.toolchain=path(root,text(*o,"toolchain"),false).string();
    if(auto limits=o->get("task_limits")){c.taskLimits=parseTaskLimitsJSON(*limits,"E_PROJECT_BUILD");c.taskLimitsSpecified=true;}
    configurations.emplace(c.name,std::move(c));
  }
  auto defaultConfiguration=text(*top,"default_configuration","",true);
  if(!configurations.contains(defaultConfiguration))fail("unknown default configuration: "+defaultConfiguration);
  auto selectedConfiguration=options.configuration.empty()?defaultConfiguration:options.configuration;
  if(!configurations.contains(selectedConfiguration))fail("unknown configuration: "+selectedConfiguration);
  if(!options.component.empty()&&!components.contains(options.component))fail("unknown component: "+options.component);
  const auto &configuration=configurations.at(selectedConfiguration);
  if(options.taskDebug&&(configuration.profile!="debug"||!options.foreign.empty()||withWorkload))fail("--task-debug requires a native task application, debug profile and no HTTP/foreign workload","E_TASK_DEBUG");
  auto selectedComponent=options.component;
  if(execution||withWorkload){
    if(selectedComponent.empty()){
      for(const auto &[name,c]:components)if(c.kind=="executable"||c.kind=="server"||c.kind=="web"){
        if(!selectedComponent.empty())fail("project action requires --component when multiple applications exist","E_OPTION");selectedComponent=name;
      }
    }
    if(selectedComponent.empty())fail("project action requires an executable, server or web application","E_PROJECT_CAPABILITY");
    const auto &kind=components.at(selectedComponent).kind;
    if(kind!="executable"&&kind!="server"&&kind!="web")fail("project action requires an executable, server or web application","E_PROJECT_CAPABILITY");
    if(options.kind=="debug"&&!options.foreign.empty()){
      auto arguments=options.arguments;arguments.insert(arguments.begin(),{kind=="server"?"--foreign":"--nex-foreign",fs::absolute(options.foreign).string()});validateNativeDebugArguments(arguments);
    }
    if((options.kind=="debug"||options.kind=="profile")&&kind!="executable"&&!(options.kind=="debug"&&kind=="server")&&!(options.kind=="profile"&&kind=="server"&&withWorkload))fail("project debug requires a native executable/server; profile requires an executable or server with --workload; browser debugging remains pending","E_PROJECT_CAPABILITY");
    if(withWorkload&&(kind!="server"||configuration.profile!="profile"))fail("--workload requires a server component and a profile configuration","E_OPTION");
    if(options.kind=="profile"&&configuration.profile!="profile")fail("project profile requires a configuration whose profile is profile","E_OPTION");
    if(options.kind=="run"&&options.machine&&(kind=="server"||kind=="web")&&!options.explicitTimeout)fail("captured server/web run requires an explicit --timeout; use an interactive run for a long-lived process","E_OPTION");
    if(kind=="web"&&!options.foreign.empty())fail("a web preview receives no native foreign catalogue","E_OPTION");
  }
  std::optional<ServerWorkload> workload;
  if(withWorkload){workload=inspectServerWorkload(root.string(),options.workload);if(options.kind=="profile")validateServerWorkloadAuthority(*workload,options.arguments,options.profiling.environment);}
  std::vector<std::string> order;std::map<std::string,int> state;
  std::function<void(const std::string&)> visit=[&](const auto &name) {
    if(state[name]==2)return;if(state[name]==1)fail("component dependency cycle at "+name,"E_PROJECT_CYCLE");state[name]=1;
    for(const auto &[dep,link]:components.at(name).dependencies){(void)link;visit(dep);}state[name]=2;order.push_back(name);
  };
  for(const auto &[name,c]:components){(void)c;visit(name);} // Validate even unselected architecture edges.
  std::set<std::string> selected;
  std::function<void(const std::string&)> select=[&](const auto &name){if(!selected.insert(name).second)return;for(const auto &[dep,link]:components.at(name).dependencies){(void)link;select(dep);}};
  if(selectedComponent.empty())for(const auto &[name,c]:components){(void)c;select(name);}else select(selectedComponent);
  std::string declaredTestKind;
  if(!options.testFunction.empty()){
    if(options.component.empty()||(options.kind!="plan"&&options.kind!="build"))fail("invalid internal project test selection","E_INTERNAL");
    auto &component=components.at(options.component);declaredTestKind=component.kind;
    component.kind="executable";component.function=options.testFunction;component.exports.clear();
  }
  if(options.kind=="package"&&std::none_of(selected.begin(),selected.end(),[&](const auto &name){const auto &kind=components.at(name).kind;return kind=="executable"||kind=="server"||kind=="web";}))
    fail("project package selection requires an executable, server or web application","E_PROJECT_CAPABILITY");
  if(options.kind=="package"&&std::none_of(selected.begin(),selected.end(),[&](const auto &name){const auto &kind=components.at(name).kind;return kind=="executable"||kind=="server";})&&
     (!options.package.notices.empty()||options.package.dpkgNotices))fail("native notice options require a selected native application","E_OPTION");
  bool sharedSelected=false;
  for(const auto &name:selected)sharedSelected|=components.at(name).kind=="shared_library";
  std::map<std::string,bool> dynamicClosure;
  std::function<bool(const std::string&)> dynamic=[&](const auto &name){
    auto old=dynamicClosure.find(name);if(old!=dynamicClosure.end())return old->second;
    bool value=false;for(const auto &[dep,link]:components.at(name).dependencies)value|=link=="dynamic"||dynamic(dep);
    return dynamicClosure[name]=value;
  };
  for(const auto &name:selected)dynamic(name);
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
  for(const auto &name:selected)for(const auto &[dep,link]:components.at(name).dependencies)if(link=="static"||link=="dynamic")binaryProviders.insert(dep);
  for(const auto &name:order) {
    if(!selected.contains(name))continue;const auto &c=components.at(name);
    auto program=loadVersionedProgram((root/c.entry).string(),root.string(),options.sourceLanguage,!options.archivedSources,options.sourceOverlays);llvm::json::Array sources;
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
    BuildOptions native;native.profile=configuration.profile;native.entry=c.function;native.libraryEntry=c.kind=="static_library"||c.kind=="shared_library";native.toolchain=configuration.toolchain;
    if(!options.testFunction.empty()&&name==options.component){
      const auto &f=program.function(options.testFunction);
      if(!f.test||owner(program.units.at(f.unit).path)!=name)fail("test entry must be a test owned by the selected component","E_TEST");
      native.testEntry=true;
    }
    if(!native.entry.empty()&&usesTaskEffects(program,native.entry)){
      native.taskLimits=configuration.taskLimits;native.taskLimitsSpecified=configuration.taskLimitsSpecified;
      if((options.kind=="debug"||options.taskDebug)&&(c.kind=="executable"||c.kind=="server")){
        if(configuration.profile!="debug"||c.kind!="executable"||!options.foreign.empty())fail("task debug requires a native debug task application without HTTP or foreign code","E_TASK_DEBUG");
        if(options.adapter=="dap")fail("logical source task debugging requires lldb or nex-dap; raw DAP is pending","E_TASK_DEBUG");
        native.taskDebug=true;
      }
    }
    native.libraryExports=c.exports;native.projectLibraryABI=c.kind!="source"&&c.kind!="web";
    native.codeOnlyLibrary=binaryProviders.contains(name)||c.kind=="shared_library"||(c.kind=="static_library"&&dynamicClosure.at(name));
    native.positionIndependent=sharedSelected;
    native.deferredLink=c.kind=="shared_library"||((c.kind=="executable"||c.kind=="server")&&dynamicClosure.at(name));
    native.functionsOnly=native.deferredLink&&c.kind=="executable";
    native.target=c.kind=="server"?"server":configuration.target;
    llvm::json::Value toolchain=nullptr,web=nullptr;
    if(c.kind=="web")web=inspectWebApp(program);
    else if(c.kind!="source") {
      auto abiOptions=native;abiOptions.target=configuration.target;auto declared=configureNative(abiOptions);auto actual=configureNative(native);
      llvm::Triple imageABI(actual.target);if(sharedSelected&&!imageABI.isMacOSX()&&!imageABI.isOSLinux())fail("shared project images currently require macOS or Linux targets","E_PROJECT_CAPABILITY");
      if(declared.target!=actual.target)fail("server target requires a matching explicit toolchain for this configuration","E_TARGET");
      auto captured=inspectNativeToolchain(native);toolchain=Object{{"hash",captured.hash},{"target",captured.target},{"host_compatible",captured.hostCompatible}};
      if(execution&&name==selectedComponent&&!captured.hostCompatible)fail("project execution requires the compiler host ABI","E_TARGET");
      // Native task imports need the complete checked ownership/export plan.
      // Entry validation below still precedes tools, cache creation and plan
      // publication, after every selected source closure is available.
      if(options.kind=="package"&&(c.kind=="executable"||c.kind=="server")){
        if(!imageABI.isMacOSX()&&!imageABI.isOSLinux())fail("project native packages currently require macOS or Linux targets","E_PROJECT_CAPABILITY");
        if(options.packageProjection&&options.packageProjection->applications.contains(name))native.foreignCatalogue="../foreign/host.json";
      }
      if((c.kind=="static_library"||c.kind=="shared_library")&&owner(program.units.at(program.function(c.function).unit).path)!=name)fail("library entry must be owned by "+name,"E_PROJECT_EXPORT");
      for(const auto &entry:c.exports){const auto &f=program.function(entry);if(!f.exported||owner(program.units.at(f.unit).path)!=name)fail("library exports must be public concrete functions owned by "+name,"E_PROJECT_EXPORT");}
    }
    Object dependencies;for(const auto &[dep,link]:c.dependencies)dependencies[dep]=link;
    llvm::json::Array exports;for(const auto &entry:c.exports)exports.push_back(program.function(entry).name);
    auto description=llvm::json::Value(Object{{"name",name},{"kind",c.kind},{"root",c.root},{"entry",c.entry},{"entry_function",c.function.empty()?llvm::json::Value(nullptr):llvm::json::Value(program.function(c.function).name)},{"exports",std::move(exports)},{"code_only_library",native.codeOnlyLibrary},{"position_independent",native.positionIndependent},{"shared_runtime_image",native.deferredLink},
      {"dependencies",std::move(dependencies)},{"revision",revision(program)},{"source_bundle_hash",hash(json(sourceBundle(program),false))},{"sources",std::move(sources)},
      {"native_toolchain",std::move(toolchain)},{"web_projection",std::move(web)}});
    if(native.testEntry){(*description.getAsObject())["test_entry"]=true;(*description.getAsObject())["declared_kind"]=declaredTestKind;}
    prepared.push_back({name,std::move(program),std::move(native),std::move(description)});
  }
  // Bind each binary edge before invoking tools. Every ordinary concrete
  // definition in a binary-owned component must actually exist in its archive.
  // New generic specializations are explicitly instantiated in the consumer.
  std::map<std::string,Prepared*> byName;for(auto &item:prepared)byName[item.name]=&item;
  std::map<std::string,std::set<std::string>> binaryClosures;
  for(const auto &item:prepared){
    std::set<std::string> walked;
    std::function<void(const std::string&)> gather=[&](const auto &name){if(!walked.insert(name).second)return;for(const auto &[dep,link]:components.at(name).dependencies){if(link=="static"||link=="dynamic")binaryClosures[item.name].insert(dep);gather(dep);}};
    gather(item.name);
  }
  auto taskEntries=[&](const Prepared &item){
    if(item.options.entry.empty())return false;
    if(usesTaskEffects(item.program,item.options.entry))return true;
    return std::any_of(item.options.libraryExports.begin(),item.options.libraryExports.end(),[&](const auto &name){return usesTaskEffects(item.program,name);});
  };
  std::set<std::string> taskABI;
  for(const auto &item:prepared)if(taskEntries(item)&&
      (components.at(item.name).kind=="static_library"||components.at(item.name).kind=="shared_library"||!binaryClosures[item.name].empty()||(options.taskDebug&&components.at(item.name).kind=="executable")))taskABI.insert(item.name);
  // A task archive and its pure dependencies/consumers use one compatible
  // runtime cohort. Source-only task applications retain their existing path.
  for(bool changed=true;changed;){
    changed=false;
    for(const auto &item:prepared){
      const auto &c=components.at(item.name);if(c.kind=="source"||c.kind=="web")continue;
      bool connected=taskABI.contains(item.name);
      for(const auto &dependency:binaryClosures[item.name])connected|=taskABI.contains(dependency);
      if(!connected)continue;
      changed|=taskABI.insert(item.name).second;
      std::set<std::string> walked;
      std::function<void(const std::string&)> include=[&](const auto &name){if(!walked.insert(name).second)return;const auto &component=components.at(name);if(component.kind!="source"&&component.kind!="web")changed|=taskABI.insert(name).second;for(const auto &[dep,link]:component.dependencies){(void)link;include(dep);}};
      include(item.name);
    }
  }
  std::set<std::string> sharedTaskABI;
  for(const auto &item:prepared)if(taskABI.contains(item.name)&&
      (components.at(item.name).kind=="shared_library"||dynamicClosure.at(item.name)))sharedTaskABI.insert(item.name);
  // One reusable PIC mode for every connected task cohort. Independent roots
  // may share these stages; final ownership is checked per load closure below.
  for(bool changed=true;changed;){
    changed=false;
    for(const auto &item:prepared)if(taskABI.contains(item.name)){
      bool connected=sharedTaskABI.contains(item.name);
      for(const auto &dependency:binaryClosures[item.name])connected|=sharedTaskABI.contains(dependency);
      if(!connected)continue;
      changed|=sharedTaskABI.insert(item.name).second;
      for(const auto &dependency:binaryClosures[item.name])if(taskABI.contains(dependency))changed|=sharedTaskABI.insert(dependency).second;
    }
  }
  if(options.taskDebug){bool application=false;for(const auto &item:prepared){const auto &c=components.at(item.name);if(c.kind=="executable"){application=true;if(item.options.entry.empty()||!usesTaskEffects(item.program,item.options.entry))fail("--task-debug requires actual task application roots","E_TASK_DEBUG");}else if(c.kind=="server"||c.kind=="web")fail("--task-debug supports native task applications without HTTP or browser adapters","E_TASK_DEBUG");}if(!application)fail("--task-debug requires a selected native task application","E_TASK_DEBUG");}
  for(auto &item:prepared)if(taskABI.contains(item.name)){
    const auto &c=components.at(item.name);
    if((c.kind!="executable"&&c.kind!="static_library"&&c.kind!="shared_library")||
       !options.foreign.empty())
      fail("task binary providers require fixed native applications without HTTP or foreign code","E_TASK_PROVIDER");
    if((options.kind=="debug"||options.taskDebug||item.options.taskDebug)&&configuration.profile!="debug")fail("task provider debugging requires a debug profile","E_TASK_DEBUG");
    if(c.kind=="executable"&&!usesTaskEffects(item.program,item.options.entry))
      fail("a pure application cannot consume a task-provider cohort; no implicit task executor is created","E_TASK_PROVIDER");
    const bool shared=sharedTaskABI.contains(item.name);
    item.options.staticTaskABI=!shared;item.options.taskComponent=item.name;
    item.options.taskLinkageMode=shared?NativeTaskLinkageMode::SharedFixed:NativeTaskLinkageMode::Static;
    if(options.kind=="debug"||options.taskDebug)item.options.taskDebug=true;
    if(shared){
      item.options.positionIndependent=true;
      if(c.kind=="executable"){item.options.deferredLink=true;item.options.functionsOnly=true;}
    }
    auto &description=*item.description.getAsObject();description["position_independent"]=item.options.positionIndependent;description["shared_runtime_image"]=item.options.deferredLink;
    if(c.kind=="static_library"||c.kind=="shared_library"){
      item.options.codeOnlyLibrary=true;
      item.options.taskLimits={};item.options.taskLimitsSpecified=false;
    }
  }
  // A physical component has one stage/cohort in a selected architecture.
  // Unrelated processes may use different cohorts, but no binary dependency
  // can cross them or silently acquire a second runtime/ABI incarnation.
  for(const auto &item:prepared)if(components.at(item.name).kind!="source"&&components.at(item.name).kind!="web")
    for(const auto &dependency:binaryClosures[item.name])if(effectiveNativeTaskLinkage(item.options)!=effectiveNativeTaskLinkage(byName.at(dependency)->options))
      fail("connected native components require one task linkage mode: "+item.name+" -> "+dependency,"E_TASK_PROVIDER");
  std::map<std::string,std::vector<std::string>> staticFrontiers,dynamicImages;
  std::set<std::string> imageStages;
  for(const auto &item:prepared) {
    const auto &c=components.at(item.name);if(c.kind=="source"||c.kind=="web")continue;
    if(!item.options.deferredLink&&!(c.kind=="static_library"&&dynamicClosure.at(item.name))&&effectiveNativeTaskLinkage(item.options)!=NativeTaskLinkageMode::SharedFixed)continue;
    imageStages.insert(item.name);std::set<std::string> statics,dynamics,seen,seenDynamic;
    std::function<void(const std::string&)> nested=[&](const auto &name){if(!seenDynamic.insert(name).second)return;for(const auto &[dep,link]:components.at(name).dependencies){if(link=="dynamic")dynamics.insert(dep);nested(dep);}};
    std::function<void(const std::string&)> frontier=[&](const auto &name){if(!seen.insert(name).second)return;for(const auto &[dep,link]:components.at(name).dependencies){if(link=="dynamic"){dynamics.insert(dep);nested(dep);}else{if(link=="static")statics.insert(dep);frontier(dep);}}};frontier(item.name);
    for(auto n=order.rbegin();n!=order.rend();++n)if(statics.contains(*n))staticFrontiers[item.name].push_back(*n);
    for(const auto &n:order)if(dynamics.contains(n))dynamicImages[item.name].push_back(n);
    imageStages.insert(statics.begin(),statics.end());
  }
  std::map<std::string,std::map<std::string,std::string>> contracts;
  for(auto &item:prepared)if(components.at(item.name).kind!="source"&&components.at(item.name).kind!="web"){
    for(const auto &unit:planNative(item.program,item.options.entry,item.options.libraryExports,true).units){
      auto parsed=llvm::json::parse(unit.contract);if(!parsed)fail("invalid native contract","E_INTERNAL");parsed->getAsObject()->erase("unit");
      contracts[item.name][unit.identity]=hash(json(*parsed,false));
    }
  }
  std::map<std::string,std::map<std::string,std::string>> taskDefinitions;
  for(auto &item:prepared){
    const auto &c=components.at(item.name);if(c.kind=="source"||c.kind=="web")continue;
    const auto &binaries=binaryClosures[item.name];
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
          if(effectiveNativeTaskLinkage(item.options)!=NativeTaskLinkageMode::None&&usesTaskEffects(item.program,function))
            fail("static task dependency "+owned+" does not export concrete task definition "+function+"; add the specialization to exports","E_PROJECT_EXPORT");
          instantiate|=!f.templateName.empty();
          if(!instantiate)fail("binary dependency "+owned+" does not export the concrete closure containing "+function+"; add it to exports","E_PROJECT_EXPORT");
          instantiated.insert(function);
        }else{
          if(provider->second!=contract)fail("binary dependency function/type context differs: "+function,"E_PROJECT_ABI");
          if(effectiveNativeTaskLinkage(item.options)!=NativeTaskLinkageMode::None)item.options.taskImportedFunctions.insert(function);
          instantiate=false;
        }
      }
      for(const auto &callee:f.dependencies)validate(callee,instantiate);
    };
    validate(item.program.function(item.options.entry).name,false);
    for(const auto &entry:item.options.libraryExports)validate(item.program.function(entry).name,false);
    llvm::json::Array instances;for(const auto &name:instantiated)instances.push_back(name);(*item.description.getAsObject())["consumer_instantiations"]=std::move(instances);
    if(effectiveNativeTaskLinkage(item.options)!=NativeTaskLinkageMode::None){
      // Machine closure ownership also includes checked package/std helpers.
      // Such a helper has no physical component owner, but its actual archive
      // definition must still be imported rather than emitted a second time.
      std::map<std::string,std::pair<std::string,std::string>> supplied;
      for(const auto &dependency:binaries)for(const auto &[name,contract]:taskDefinitions.at(dependency)){
        if(!supplied.emplace(name,std::pair{dependency,contract}).second)
          fail("static task providers contain duplicate machine definition: "+name,"E_TASK_PROVIDER");
      }
      for(const auto &[name,contract]:contracts.at(item.name))if(auto provider=supplied.find(name);provider!=supplied.end()){
        if(provider->second.second!=contract)fail("binary dependency helper/type context differs: "+name,"E_PROJECT_ABI");
        if(!instantiated.contains(name))item.options.taskImportedFunctions.insert(name);
      }
      // A reachable provider helper has a physical definition, but only its
      // selected public task roots have descriptor accessors. Check actual
      // local-to-imported calls; internal calls in an imported body stay local
      // to that provider and do not require another public export.
      for(const auto &[name,contract]:contracts.at(item.name))if(!item.options.taskImportedFunctions.contains(name)){
        (void)contract;
        for(const auto &callee:item.program.function(name).dependencies){
          if(!item.options.taskImportedFunctions.contains(callee)||(!supportsSourceExceptionTasks(item.program)&&!item.program.function(callee).effects.contains("task")))continue;
          auto found=supplied.find(callee);if(found==supplied.end())fail("task import has no actual provider definition: "+callee,"E_TASK_PROVIDER");
          const auto &provider=*byName.at(found->second.first);
          auto selected=provider.options.libraryExports;selected.push_back(provider.options.entry);
          if(std::none_of(selected.begin(),selected.end(),[&](const auto &entry){return provider.program.function(entry).name==callee;}))
            fail("static task dependency "+provider.name+" does not select concrete task export "+callee+"; add it to exports","E_PROJECT_EXPORT");
        }
      }
      llvm::json::Array definitions,imports;Object exports;
      for(const auto &[name,contract]:contracts.at(item.name)){
        const auto &function=item.program.function(name);
        if(item.options.taskImportedFunctions.contains(name)){
          auto provider=supplied.find(name);if(provider==supplied.end())fail("task import has no actual provider definition: "+name,"E_TASK_PROVIDER");
          imports.push_back(Object{{"function",name},{"provider",provider->second.first},{"contract",contract},{"calling_mode",supportsSourceExceptionTasks(item.program)?"task-code/6":function.effects.contains("task")?(supportsTaskFileStreams(item.program)?"task-code/5":supportsTaskFileWrites(item.program)?"task-code/4":"task-code/3"):"sync/1"}});
        }else{definitions.push_back(Object{{"function",name},{"contract",contract}});taskDefinitions[item.name][name]=contract;}
      }
      if(c.kind=="static_library"||c.kind=="shared_library"){
        auto entries=item.options.libraryExports;entries.push_back(item.options.entry);
        for(const auto &entry:entries){const auto &function=item.program.function(entry);if(!supportsSourceExceptionTasks(item.program)&&!function.effects.contains("task"))continue;
          auto value=nativeTaskExportInterface(item.program,function.name,contracts.at(item.name).at(function.name));
          exports[function.name]=Object{{"contract",value.contract},{"signature",value.signature},{"accessor",value.accessor},{"requirements",value.requirements}};
        }
      }
      auto &description=*item.description.getAsObject();description["code_only_library"]=item.options.codeOnlyLibrary;
      description["task_linkage"]=Object{{"schema",supportsSourceExceptionTasks(item.program)?"nex.project-static-task-linkage/4":supportsTaskFileStreams(item.program)?"nex.project-static-task-linkage/3":supportsTaskFileWrites(item.program)?"nex.project-static-task-linkage/2":"nex.project-static-task-linkage/1"},{"component",item.name},{"execution_abi",supportsSourceExceptionTasks(item.program)?6:supportsTaskFileStreams(item.program)?5:supportsTaskFileWrites(item.program)?4:3},
        {"definitions",std::move(definitions)},{"imports",std::move(imports)},{"exports",std::move(exports)}};
      if(supportsTaskFileWrites(item.program)&&!supportsTaskFileStreams(item.program)){std::set<std::string> selected;for(const auto &[name,contract]:contracts.at(item.name)){(void)contract;selected.insert(name);}(*description.getObject("task_linkage"))["task_file_writes"]=nativeTaskFileWrites(item.program,selected);}
      if(supportsTaskFileStreams(item.program)){
        std::set<std::string> selected;for(const auto &[name,contract]:contracts.at(item.name)){(void)contract;selected.insert(name);}
        auto requirements=nativeTaskFileRequirements(item.program,selected);auto &linkage=*description.getObject("task_linkage");
        linkage["task_file_reads"]=requirements.reads;linkage["task_file_writes"]=requirements.writes;linkage["task_file_streams"]=requirements.streams;
      }
    }
  }
  for(auto &item:prepared)if(effectiveNativeTaskLinkage(item.options)==NativeTaskLinkageMode::SharedFixed||(effectiveNativeTaskLinkage(item.options)!=NativeTaskLinkageMode::None&&(configuration.profile=="profile"||item.options.taskDebug))){
    const bool shared=effectiveNativeTaskLinkage(item.options)==NativeTaskLinkageMode::SharedFixed;
    auto &linkage=*item.description.getAsObject()->getObject("task_linkage");
    linkage["schema"]=supportsSourceExceptionTasks(item.program)?(item.options.taskDebug?"nex.project-task-linkage/13":configuration.profile=="profile"?"nex.project-task-linkage/12":"nex.project-task-linkage/11"):supportsTaskFileStreams(item.program)?(item.options.taskDebug?"nex.project-task-linkage/10":configuration.profile=="profile"?"nex.project-task-linkage/9":"nex.project-task-linkage/8"):supportsTaskFileWrites(item.program)?(item.options.taskDebug?"nex.project-task-linkage/7":configuration.profile=="profile"?"nex.project-task-linkage/6":"nex.project-task-linkage/5"):(item.options.taskDebug?"nex.project-task-linkage/4":configuration.profile=="profile"?"nex.project-task-linkage/3":"nex.project-task-linkage/2");linkage["mode"]=shared?"shared-fixed":"static";linkage["load_closure"]=nullptr;
    if(item.options.taskDebug){llvm::json::Array sites;bool retained=supportsSourceExceptionTasks(item.program)||usesTaskEffects(item.program,item.options.entry);for(const auto &entry:item.options.libraryExports)retained|=usesTaskEffects(item.program,entry);
      for(const auto &[name,contract]:taskDefinitions.at(item.name)){const auto &function=item.program.function(name);auto unit=item.program.units.find(function.unit);auto source=unit==item.program.units.end()?item.program.source:unit->second.source;
        sites.push_back(Object{{"name",name},{"function_hash",hash(json(canonical(function),false))},{"function_source_hash",hash(item.program.definition(function))},{"source_unit_hash",hash(source)},{"contract",contract},{"line",int64_t(function.span.line)},{"retained",retained},{"task_debug",retained?llvm::json::Value(taskDebugFunctionMetadata(item.program,function,function.unit)):llvm::json::Value(nullptr)}});
      }
      linkage["debugging"]=Object{{"schema","nex.project-task-debug/1"},{"registry_abi",1},{"catalog_abi",2},{"definitions",std::move(sites)}};
    }
    if(configuration.profile=="profile"){llvm::json::Array sites;for(const auto &[name,contract]:taskDefinitions.at(item.name)){const auto &function=item.program.function(name);auto unit=item.program.units.find(function.unit);auto source=unit==item.program.units.end()?item.program.source:unit->second.source;
      sites.push_back(Object{{"name",name},{"function_hash",hash(json(canonical(function),false))},{"function_source_hash",hash(item.program.definition(function))},{"source_unit_hash",hash(source)},{"contract",contract},{"line",int64_t(function.span.line)}});}
      linkage["profiling"]=Object{{"schema","nex.project-task-profile/1"},{"registry_abi",1},{"sites",std::move(sites)}};
    }
    const auto &kind=components.at(item.name).kind;if(kind!="executable"&&kind!="shared_library")continue;
    std::set<std::string> loaded(dynamicImages[item.name].begin(),dynamicImages[item.name].end());loaded.insert(item.name);
    std::map<std::string,std::string> owners;llvm::json::Array images;
    for(const auto &name:order)if(loaded.contains(name)){
      llvm::json::Array definitions,statics,dynamics;
      auto add=[&](const std::string &component){for(const auto &[function,contract]:taskDefinitions.at(component)){
        auto [old,inserted]=owners.emplace(function,name);
        if(!inserted)fail("task load closure "+item.name+" contains duplicate machine definition "+function+" in "+old->second+" and "+name,"E_TASK_PROVIDER");
        definitions.push_back(Object{{"function",function},{"source_component",component},{"contract",contract}});
      }};
      add(name);
      if(shared)for(const auto &component:staticFrontiers[name]){add(component);statics.push_back(component);}
      else for(const auto &component:order)if(binaryClosures[name].contains(component)){add(component);statics.push_back(component);}
      for(const auto &component:dynamicImages[name])dynamics.push_back(component);
      images.push_back(Object{{"component",name},{"kind",components.at(name).kind=="executable"?"application":"shared-image"},
        {"definitions",std::move(definitions)},{"static_components",std::move(statics)},{"dynamic_components",std::move(dynamics)}});
    }
    linkage["load_closure"]=Object{{"root",item.name},{"images",std::move(images)}};
  }
  for(auto &item:prepared)if(components.at(item.name).kind!="source"&&components.at(item.name).kind!="web")validateNativeBuildEntry(item.program,item.options);
  for(const auto &item:prepared)descriptions.push_back(item.description);
  if(options.packageProjection){
    options.packageProjection->verify();
    if(prepared.size()!=options.packageProjection->sourceHashes.size())fail("project projection component set changed","E_PROJECT_INPUT_CHANGED");
    for(const auto &item:prepared){
      if(hash(json(sourceBundle(item.program),false))!=options.packageProjection->sourceHashes.at(item.name))fail("project projection source differs: "+item.name,"E_PROJECT_INPUT_CHANGED");
      auto expected=options.packageProjection->toolchains.find(item.name);
      if(expected!=options.packageProjection->toolchains.end()&&item.description.getAsObject()->getObject("native_toolchain")->getString("hash")!=expected->second)
        fail("project projection toolchain differs: "+item.name,"E_PROJECT_INPUT_CHANGED");
    }
  }
  std::map<std::string,ForeignSelection> applicationForeign;
  ForeignSelection selectedForeign;
  std::set<std::tuple<std::string,size_t,size_t>> physicalBindings;
  for(const auto &item:prepared){
    const auto &kind=components.at(item.name).kind;if(kind!="executable"&&kind!="server")continue;
    for(const auto &unit:planNative(item.program,item.options.entry).units){
      const auto &function=item.program.function(unit.identity);if(!function.foreign)continue;
      const auto &binding=*function.foreign;
      applicationForeign[item.name][binding.library].insert(binding.symbol);selectedForeign[binding.library].insert(binding.symbol);
      physicalBindings.emplace(item.program.units.at(function.unit).path,binding.manifestSpan.begin,binding.manifestSpan.end);
    }
  }
  std::optional<ForeignCatalogueSnapshot> packageForeign;
  // A private test-entry plan is compared with its actual build. It must not
  // acquire deployment-only catalogue annotations; the parent still checks
  // every selected test's exact reachable grants before any execution/tool.
  if(!options.packageProjection&&(options.kind=="package"||(options.kind=="plan"&&options.testFunction.empty()))&&!options.foreign.empty()){
    if(selectedForeign.empty())fail("selected native applications have no reachable external calls","E_FFI_PACKAGE");
    packageForeign=inspectForeignCatalogue(options.foreign);
    for(const auto &item:prepared)if(applicationForeign.contains(item.name)){
      if(options.kind=="package")requireNativeHost(item.options);
      for(const auto &unit:planNative(item.program,item.options.entry).units)checkForeignBinding(*packageForeign,item.program,item.program.function(unit.identity));
    }
  }
  if(options.kind=="package"&&!selectedForeign.empty()&&!packageForeign&&!options.packageProjection)
    fail("project packaging external calls requires an explicit --foreign HOST.json operator catalogue","E_FFI_PACKAGE");
  if(readFile((root/"nex.json").string())!=sourceManifest||
     (fs::is_regular_file(root/"nex.lock.json")?std::optional<std::string>(readFile((root/"nex.lock.json").string())):std::nullopt)!=sourceLock)
    fail("project metadata or dependency lock changed while planning","E_PROJECT_INPUT_CHANGED");
  for(const auto &[file,text]:capturedSources)if(options.sourceOverlays.contains(file)?options.sourceOverlays.at(file)!=text:readFile(file)!=text)fail("captured source changed while planning: "+file,"E_PROJECT_INPUT_CHANGED");
  Object plan{{"schema","nex.project-plan/1"},{"ok",true},{"language",programLanguage(options.sourceLanguage)},{"compiler",Object{{"version",options.compilerVersion},{"build",options.compilerBuild}}},
    {"root",root.string()},{"manifest",manifest},{"manifest_hash",hash(source)},{"architecture_hash",hash(json(*parsed,false))},{"source_project_manifest_hash",hash(sourceManifest)},
    {"configuration",Object{{"name",configuration.name},{"profile",configuration.profile},{"target",configuration.target},{"toolchain",configuration.toolchain.empty()?llvm::json::Value(nullptr):llvm::json::Value(configuration.toolchain)}}},
    {"selected_component",selectedComponent.empty()?llvm::json::Value(nullptr):llvm::json::Value(selectedComponent)},{"components",std::move(descriptions)},
    {"source_checked",true},{"graph_store_opened",false},{"external_tools_invoked",false},{"target_execution_verified",false},{"artifact_dependencies_inspected",false}};
  if(configuration.taskLimitsSpecified)(*plan.getObject("configuration"))["task_limits"]=taskLimitsJSON(configuration.taskLimits);
  if(packageForeign){
    Object applications;for(const auto &[name,selection]:applicationForeign){Object libraries;for(const auto &[library,exports]:selection){llvm::json::Array values;for(const auto &value:exports)values.push_back(value);libraries[library]=std::move(values);}applications[name]=std::move(libraries);}
    plan["foreign_packaging"]=Object{{"schema","nex.project-foreign-plan/1"},{"catalogue_hash",packageForeign->hash},{"applications",std::move(applications)},
      {"module_initialization",false},{"pin_projection",false},{"native_dependencies_inspected",false}};
  }
  if(options.packageProjection)plan["foreign_projection"]=options.packageProjection->report;
  if(workload){verifyServerWorkloadInputs(*workload);auto details=Object(workload->plan);details["definition_file"]=workload->selection;details["runner_sha256"]=workload->helperSha256;plan["server_workload"]=std::move(details);}
  auto serialized=json(llvm::json::Value(Object(plan)),false);if(serialized.size()>8*1048576)fail("project plan exceeds8MiB","E_PROJECT_LIMIT");
  auto planHash=hash(serialized);plan["plan_hash"]=planHash;
  if(!options.expectedPlanHash.empty()&&planHash!=options.expectedPlanHash)fail("project test inputs changed after preflight","E_PROJECT_INPUT_CHANGED");
  if(options.kind=="plan")return plan;
  if(options.kind=="package"&&packageForeign){
    // Validate the original locked project first, then compile one consistent
    // source projection. All apps sharing a binary provider use the same new
    // literal pins; each deployed catalogue retains only that app's exports.
    auto context=std::make_shared<ProjectPackageProjection>();
    std::map<std::string,std::string> aliases;std::map<std::string,std::optional<std::string>> metadata;
    auto alias=[&](const fs::path &input){auto logical=fs::absolute(input).lexically_normal().string();aliases[logical]=fs::weakly_canonical(input).string();};
    auto captureMetadata=[&](const fs::path &input){alias(input);metadata[input.string()]=fs::is_regular_file(input)?std::optional<std::string>(readFile(input.string())):std::nullopt;};
    alias(directory);captureMetadata(root/"nex.json");captureMetadata(root/"nex.lock.json");captureMetadata(manifest);
    captureMetadata(fs::absolute(options.foreign));
    auto rootMetadata=llvm::json::parse(sourceManifest);auto packageRoots=rootMetadata->getAsObject()->getObject("libraries");
    for(const auto &[name,c]:components){(void)name;alias(root/c.root);alias(root/c.entry);}
    for(const auto &item:prepared)for(const auto &[key,unit]:item.program.units){
      if(!key.starts_with("@"))alias(root/key);
      else{
        auto standard=key.starts_with("@std/");auto split=key.find('/',5);auto name=standard?"std":key.substr(5,split-5);
        if(packageRoots&&packageRoots->getString(name)){
          auto base=root/packageRoots->getString(name)->str();alias(base);captureMetadata(base/"nex.json");alias(base/key.substr(standard?5:split+1));
        }else alias(unit.path);
      }
    }
    for(const auto &item:prepared)if(auto value=item.description.getAsObject()->getObject("native_toolchain")){
      context->toolchains[item.name]=value->getString("hash")->str();
      if(!item.options.toolchain.empty())captureMetadata(item.options.toolchain);
    }
    std::map<std::string,std::string> helpers;
    for(const auto &name:{"tools/foreign_bundle.py","tools/app_bundle.py","tools/sdk_bundle.py"})helpers[name]=hash(readFile(resourceFile(name)));
    if(!options.package.notices.empty()){
      auto notice=fs::absolute(options.package.notices);captureMetadata(notice);
      auto parsedNotices=llvm::json::parse(readFile(notice.string()));
      if(parsedNotices){if(auto value=parsedNotices->getAsObject())if(auto components=value->getArray("components"))for(const auto &component:*components)
        if(auto record=component.getAsObject())if(auto files=record->getArray("license_files"))for(const auto &file:*files)
          if(auto value=file.getAsString())captureMetadata(notice.parent_path()/value->str());
      }else llvm::consumeError(parsedNotices.takeError());
    }
    auto originalSources=capturedSources;auto catalogue=options.foreign,catalogueHash=packageForeign->hash;
    context->verify=[aliases=std::move(aliases),metadata=std::move(metadata),helpers=std::move(helpers),originalSources=std::move(originalSources),catalogue,catalogueHash](){
      for(const auto &[logical,physical]:aliases)if(fs::weakly_canonical(logical).string()!=physical)fail("project package input alias changed: "+logical,"E_PROJECT_INPUT_CHANGED");
      for(const auto &[path,bytes]:metadata)if((fs::is_regular_file(path)?std::optional<std::string>(readFile(path)):std::nullopt)!=bytes)fail("project package metadata changed: "+path,"E_PROJECT_INPUT_CHANGED");
      for(const auto &[path,bytes]:originalSources)if(readFile(path)!=bytes)fail("project package source changed: "+path,"E_PROJECT_INPUT_CHANGED");
      for(const auto &[name,digest]:helpers)if(hash(readFile(resourceFile(name)))!=digest)fail("project package helper changed: "+name,"E_PROJECT_INPUT_CHANGED");
      if(inspectForeignCatalogue(catalogue).hash!=catalogueHash)fail("project package operator catalogue changed","E_PROJECT_INPUT_CHANGED");
    };
    context->verify();auto temporary=fs::path(createTemporaryDirectory("nex-project-foreign"));
    auto package=options.package;package.foreign=options.foreign;
    auto unionPackage=prepareForeignPackage(package,selectedForeign,temporary.string());context->verify();
    auto projected=options;projected.archivedSources=true;projected.expectedPlanHash.clear();projected.sourceOverlays=capturedSources;
    Object projections;
    for(const auto &item:prepared){
      std::set<std::string> bindings;
      for(const auto &function:item.program.functions)if(function.foreign&&physicalBindings.contains({item.program.units.at(function.unit).path,function.foreign->manifestSpan.begin,function.foreign->manifestSpan.end}))bindings.insert(function.name);
      auto projection=projectForeignProgram(item.program,bindings,unionPackage,root.string());
      context->sourceHashes[item.name]=hash(json(sourceBundle(projection.program),false));
      for(const auto &[key,unit]:projection.program.units){
        auto physical=item.program.units.at(key).path;auto &previous=projected.sourceOverlays.at(physical);
        if(previous!=capturedSources.at(physical)&&previous!=unit.source)fail("inconsistent physical pin projection","E_FFI_PACKAGE");previous=unit.source;
      }
      auto report=Object(*projection.report.getAsObject());report["scope"]="project";report["source_plan_hash"]=planHash;
      Object identity;for(const auto *key:{"source_revision","packaged_revision","source_hash","packaged_source_hash","changes"})identity[key]=*report.get(key);
      projections[item.name]=std::move(identity);
      if(applicationForeign.contains(item.name)){
        auto subset=selectForeignPackage(unionPackage,applicationForeign.at(item.name),(temporary/"applications"/item.name).string());
        report["catalogue_hash"]=subset.snapshot.hash;report["preparation"]=std::move(subset.report);
        context->applications.emplace(item.name,ForeignPackageArtifact{subset.directory,std::move(report),std::move(subset.files)});
      }
    }
    context->report=Object{{"schema","nex.project-foreign-projection/1"},{"source_plan_hash",planHash},{"source_catalogue_hash",catalogueHash},
      {"components",std::move(projections)},{"preparation",unionPackage.report},{"source_files_modified",false},{"graph_store_opened",false},{"module_initialization",false}};
    projected.packageProjection=context;projected.foreign.clear();projected.package.foreign.clear();context->verify();
    auto result=buildProject(directory,manifest,source,projected);context->verify();fs::remove_all(temporary);return result;
  }
  auto cache=fs::absolute(options.directory.empty()?(root/".nex/build").string():options.directory);
  // Resolve a caller-selected root alias before producing closed profile
  // inputs. Individual completed files still reject internal symlinks.
  if(std::any_of(prepared.begin(),prepared.end(),[&](const auto &item){return effectiveNativeTaskLinkage(item.options)!=NativeTaskLinkageMode::None&&(configuration.profile=="profile"||item.options.taskDebug);}))
    cache=fs::weakly_canonical(cache);
  if(options.kind=="debug"||options.taskDebug)cache=nativeDebugBuildDirectory(cache.string());
  std::optional<ForeignCatalogueSnapshot> foreign;
  if(!options.foreign.empty())foreign=inspectForeignCatalogue(options.foreign);
  auto grant=[&](const Program &program,const std::string &entry){
    for(const auto &unit:planNative(program,entry).units)if(program.function(unit.identity).foreign){
      if(!foreign)fail("project execution of foreign code requires an explicit --foreign catalogue","E_FOREIGN_CATALOGUE");
      checkForeignBinding(*foreign,program,program.function(unit.identity));
    }
  };
  auto verifyGrant=[&](){if(foreign&&inspectForeignCatalogue(options.foreign).hash!=foreign->hash)fail("foreign catalogue changed after project planning","E_PROJECT_INPUT_CHANGED");};
  auto runtimeArguments=[&](const std::string &kind){
    std::vector<std::string> arguments;
    if(foreign)arguments={kind=="server"?"--foreign":"--nex-foreign",fs::absolute(options.foreign).string()};
    arguments.insert(arguments.end(),options.arguments.begin(),options.arguments.end());return arguments;
  };
  if(execution&&components.at(selectedComponent).kind!="web")grant(byName.at(selectedComponent)->program,byName.at(selectedComponent)->options.entry);
  if(testing){
    struct Test {Prepared *item;std::string function;bool web;std::string planHash;};std::vector<Test> tests;
    for(auto &item:prepared)for(const auto &f:item.program.functions)if(f.test&&owner(item.program.units.at(f.unit).path)==item.name){
      if(options.selectedTest.empty()||options.selectedTest==f.name||options.selectedTest==f.localName)tests.push_back({&item,f.name,f.realm=="client"||(components.at(item.name).kind=="web"&&f.realm!="server"),{}});
    }
    if(tests.empty())fail("no owned tests found in the selected project components","E_TEST");
    if(tests.size()>256)fail("selected project test count exceeds256","E_PROJECT_LIMIT");
    if(!options.selectedTest.empty()&&tests.size()!=1)fail("ambiguous project test symbol; select its qualified name","E_TEST");
    // Preflight every selected test and its binary dependency contracts before
    // invoking any compiler, test process or extension initialization.
    for(auto &test:tests){
      if(test.web){emitTypeScript(test.item->program,{{"entry",test.function}});continue;}
      const auto &function=test.item->program.function(test.function);
      if(function.realm=="shared"&&function.effects.empty())emitTypeScript(test.item->program,{{"entry",test.function}});
      auto check=options;check.kind="plan";check.component=test.item->name;check.testFunction=test.function;
      auto planned=buildProject(directory,manifest,source,check);
      test.planHash=planned.getAsObject()->getString("plan_hash")->str();
      for(const auto &component:*planned.getAsObject()->getArray("components"))if(component.getAsObject()->getString("name")==test.item->name){
        if(!component.getAsObject()->getObject("native_toolchain")->getBoolean("host_compatible").value_or(false))fail("project tests require the compiler host ABI","E_TARGET");
      }
      if(!buildTest)grant(test.item->program,test.function);
    }
    if(buildTest){
      const auto &test=tests.front();if(test.web)fail("build-test currently produces native test executables","E_PROJECT_CAPABILITY");
      auto buildOptions=options;buildOptions.kind="build";buildOptions.component=test.item->name;buildOptions.testFunction=test.function;buildOptions.expectedPlanHash=test.planHash;
      auto built=buildProject(directory,manifest,source,buildOptions);
      return Object{{"schema","nex.project-test-build/1"},{"ok",true},{"name",test.function},{"component",test.item->name},
        {"revision",revision(test.item->program)},{"source_bundle_hash",hash(json(sourceBundle(test.item->program),false))},
        {"content_hash",hash(json(canonical(test.item->program.function(test.function)),false))},{"build",std::move(built)},
        {"test_execution",false},{"graph_store_opened",false}};
    }
    llvm::json::Array results;bool success=true;
    for(const auto &test:tests){
      const auto &program=test.item->program;const auto &function=program.function(test.function);
      const bool typescriptReference=!test.web&&function.realm=="shared"&&function.effects.empty();
      Object row{{"component",test.item->name},{"name",test.function},{"realm",function.realm},{"native",!test.web},{"typescript",test.web||typescriptReference},{"reference",false}};
      bool referenceOK=true;std::string expected;
      if(function.effects.empty()){
        row["reference"]=true;
        try{expected=evaluate(program,test.function).output;}
        catch(const Error &error){referenceOK=false;row["reference_error"]=Object{{"code",error.code},{"message",std::string(error.what())}};}
      }else row["reference_skip_reason"]="effectful test executes once in its selected backend";
      verifyGrant();llvm::json::Value observation=nullptr;
      if(test.web){
        auto module=emitTypeScript(program,{{"entry",test.function}});auto key=hash(module.source+readFile(resourceFile("web/nex-runtime.ts"))+readFile(resourceFile("web/nex-bytes.ts"))+(module.asynchronous?readFile(resourceFile("web/nex-task-runtime.ts")):std::string())+NEX_BUILD_ID);
        auto child=runTypeScriptTest(module,(cache/key/"typescript").string(),options.timeout,module.asynchronous?&configuration.taskLimits:nullptr);
        observation=Object{{"exit_code",child.code},{"stdout",child.output},{"stderr",child.errors}};
      }else{
        auto buildOptions=options;buildOptions.kind="build";buildOptions.component=test.item->name;buildOptions.testFunction=test.function;buildOptions.expectedPlanHash=test.planHash;
        auto built=buildProject(directory,manifest,source,buildOptions);const Object *artifact=nullptr;
        for(const auto &value:*built.getAsObject()->getArray("artifacts"))if(value.getAsObject()->getString("component")==test.item->name)artifact=value.getAsObject();
        if(!artifact)fail("project test build has no executable","E_INTERNAL");
        row["artifact"]=Object(*artifact);row["plan_hash"]=built.getAsObject()->getString("plan_hash")->str();
        std::vector<std::string> arguments{artifact->getString("artifact")->str()};
        if(foreign)arguments.insert(arguments.end(),{"--nex-foreign",fs::absolute(options.foreign).string()});
        verifyGrant();observation=runCaptured(arguments,root,options.timeout);
        auto debug=parseNativeManifest(readFile(artifact->getString("debug_manifest")->str()));
        (*observation.getAsObject())["native_diagnostics"]=nativeDiagnostics(program,debug,observation.getAsObject()->getString("stderr")->str());
      }
      verifyGrant();auto &observed=*observation.getAsObject();
      bool ok=observed.getInteger("exit_code")==0&&referenceOK&&(!function.effects.empty()||observed.getString("stdout")==expected);
      if(typescriptReference){
        auto module=emitTypeScript(program,{{"entry",test.function}});auto key=hash(module.source+readFile(resourceFile("web/nex-runtime.ts"))+readFile(resourceFile("web/nex-bytes.ts"))+(module.asynchronous?readFile(resourceFile("web/nex-task-runtime.ts")):std::string())+NEX_BUILD_ID);
        auto child=runTypeScriptTest(module,(cache/key/"typescript").string(),options.timeout);
        row["typescript_observation"]=Object{{"exit_code",child.code},{"stdout",child.output},{"stderr",child.errors}};
        ok&=child.code==0&&child.output==expected;
      }
      if(usesTaskEffects(program,test.function))row["task_execution"]=taskExecutionJSON(configuration.taskLimits,configuration.taskLimits,test.web?"typescript":"native",options.timeout);
      row["ok"]=ok;row["observation"]=std::move(observation);success&=ok;boundTestResult(row,cache);results.push_back(std::move(row));
    }
    return Object{{"schema","nex.project-test/1"},{"ok",success},{"exit_code",success?0:1},{"plan_hash",planHash},{"configuration",configuration.name},
      {"tests",std::move(results)},{"graph_store_opened",false},{"test_execution",true},{"effectful_reference_replay",false}};
  }
  llvm::json::Array artifacts;
  std::map<std::string,BuildResult> nativeResults;
  std::map<std::string,llvm::json::Value> webResults;
  for(auto &item:prepared) {
    const auto &c=components.at(item.name);if(c.kind=="source")continue;
    if(options.packageProjection)options.packageProjection->verify();
    if(c.kind=="web"){webResults.emplace(item.name,buildWebApp(item.program,cache.string(),configuration.profile));continue;}
    auto expected=item.description.getAsObject()->getObject("native_toolchain")->getString("hash")->str();
    if(inspectNativeToolchain(item.options).hash!=expected)fail("native toolchain changed after project planning","E_PROJECT_INPUT_CHANGED");
    std::set<std::string> binaries,walked;
    std::function<void(const std::string&)> gather=[&](const auto &name){if(!walked.insert(name).second)return;for(const auto &[dep,link]:components.at(name).dependencies){if(link=="static"||link=="dynamic")binaries.insert(dep);gather(dep);}};gather(item.name);
    for(auto name=order.rbegin();name!=order.rend();++name)if(binaries.contains(*name)){
      const auto &dependency=nativeResults.at(*name);
      NativeLibraryInput library{dependency.executable,hash(readFile(dependency.executable)),dependency.libraryABI,dependency.functionContracts,dependency.parallelCalls,{},{}};
      if(effectiveNativeTaskLinkage(item.options)!=NativeTaskLinkageMode::None){
        if(dependency.taskProviderFile.empty()||dependency.taskProviderDigest.empty()||dependency.taskProvider.component!=*name)
          fail("static task dependency omitted its checked provider record: "+*name,"E_TASK_PROVIDER");
        library.taskProviderPath=dependency.taskProviderFile;library.taskProviderDigest=dependency.taskProviderDigest;
      }
      item.options.libraries.push_back(std::move(library));
    }
    nativeResults[item.name]=build(item.program,cache.string(),item.options);
    if(options.packageProjection)options.packageProjection->verify();
  }
  std::vector<NativeImageInput> imageInputs;
  for(const auto &item:prepared)if(imageStages.contains(item.name))imageInputs.push_back({item.name,components.at(item.name).kind,&item.program,item.options,nativeResults.at(item.name),staticFrontiers[item.name],dynamicImages[item.name]});
  if(options.packageProjection)options.packageProjection->verify();
  NativeImageResults images;llvm::json::Array runtimeImages;std::map<std::string,llvm::json::Value> runtimeByComponent;
  std::map<NativeTaskLinkageMode,std::vector<NativeImageInput>> imageCohorts;
  for(auto &input:imageInputs)imageCohorts[effectiveNativeTaskLinkage(input.options)].push_back(std::move(input));
  for(const auto &[mode,cohort]:imageCohorts){(void)mode;auto linked=buildNativeImages(cache.string(),cohort);
    runtimeImages.push_back(llvm::json::Value(linked.runtime));
    for(auto &[name,built]:linked.images){runtimeByComponent.emplace(name,llvm::json::Value(linked.runtime));if(!images.images.emplace(name,std::move(built)).second)fail("native image belongs to multiple runtime cohorts","E_INTERNAL");}
  }
  if(runtimeImages.size()==1)images.runtime=llvm::json::Value(runtimeImages.front());
  if(options.packageProjection)options.packageProjection->verify();
  for(const auto &item:prepared){
    const auto &c=components.at(item.name);if(c.kind=="source")continue;
    if(c.kind=="web"){artifacts.push_back(Object{{"component",item.name},{"kind","web"},{"result",llvm::json::Value(webResults.at(item.name))}});continue;}
    const auto &built=images.images.contains(item.name)?images.images.at(item.name):nativeResults.at(item.name);
    artifacts.push_back(Object{{"component",item.name},{"kind",c.kind},{"artifact",built.executable},{"cached",built.cached},{"build_key",built.key},
      {"target",built.target},{"compiler_target",built.compilerTarget},{"host_compatible",built.hostCompatible},{"metadata",(fs::path(built.executable).parent_path()/"build.json").string()},
      {"debug_manifest",(fs::path(built.executable).parent_path()/"debug.json").string()},{"notices",built.notices},{"compilation",built.compilation}});
  }
  if(execution){
    auto &item=*byName.at(selectedComponent);const auto &kind=components.at(selectedComponent).kind;
    llvm::json::Value observation=nullptr;std::optional<nexrt::TaskExecutionLimits> effectiveTaskLimits;
    verifyGrant();
    if(kind=="web"){
      observation=previewWebApp(webResults.at(selectedComponent).getAsObject()->getString("directory")->str(),options.arguments,options.timeout,options.machine);
    }else{
      const auto &built=images.images.contains(selectedComponent)?images.images.at(selectedComponent):nativeResults.at(selectedComponent);
      requireNativeHost(built);auto arguments=runtimeArguments(kind);
      if(kind=="executable"&&usesTaskEffects(item.program,item.options.entry)){
        auto argv=arguments;argv.insert(argv.begin(),built.executable);effectiveTaskLimits=taskEffectiveLimits(configuration.taskLimits,argv);
      }
      if(options.kind=="profile"){
        llvm::json::Array nodes;
        for(const auto &function:item.program.functions)nodes.push_back(Object{{"name",function.name},{"hash",hash(json(canonical(function),false))},{"file",function.unit},{"id",nullptr}});
        auto profiling=options.profiling;profiling.arguments=arguments;profiling.directory=root.string();
        TaskProfileSourceUnion profileSources;
        if(effectiveNativeTaskLinkage(item.options)!=NativeTaskLinkageMode::None){
          for(const auto &source:prepared)if(taskDefinitions.contains(source.name))
            profileSources.emplace(source.name,TaskProfileComponentSource{source.program,taskDefinitions.at(source.name)});
          profiling.taskProviderSources=&profileSources;
        }
        if(effectiveTaskLimits&&!options.explicitTimeout)
          profiling.timeout=std::max(30u,unsigned((effectiveTaskLimits->timeoutMs+999)/1000+5));
        std::unique_ptr<ServerWorkloadRun> workloadRun;
        if(workload){workloadRun=std::make_unique<ServerWorkloadRun>(*workload);profiling.launcher=workloadRun->launcher();profiling.additionalEvidence=[&](){return workloadRun->evidence();};}
        observation=profileNative(item.program,built,Object{{"nodes",std::move(nodes)}},profiling);
        if(workload)verifyServerWorkloadInputs(*workload);
      }else if(options.kind=="debug"){
        observation=nativeDebugSession(item.program,built,root.string(),options.compiler,options.adapter,arguments);
        if(!options.machine&&options.adapter=="lldb"){
          std::vector<std::string> command{"lldb",built.executable};
          for(const auto &value:nativeLLDBCommands(observation)){command.push_back("-o");command.push_back(value);}
          auto code=runInteractive(command,root);(*observation.getAsObject())["exit_code"]=code;(*observation.getAsObject())["ok"]=code==0;
        }
      }else{
        arguments.insert(arguments.begin(),built.executable);
        if(options.machine){
          observation=runCaptured(arguments,root,options.timeout);
          auto debug=parseNativeManifest(readFile((fs::path(built.executable).parent_path()/"debug.json").string()));
          (*observation.getAsObject())["native_diagnostics"]=nativeDiagnostics(item.program,debug,observation.getAsObject()->getString("stderr")->str());
        }else{auto code=runInteractive(arguments,root);observation=Object{{"ok",code==0},{"exit_code",code}};}
      }
    }
    if(effectiveTaskLimits&&options.kind!="profile")(*observation.getAsObject())["task_execution"]=taskExecutionJSON(configuration.taskLimits,*effectiveTaskLimits,"native",options.kind=="debug"?0:options.machine?options.timeout:0);
    verifyGrant();auto code=observation.getAsObject()->getInteger("exit_code").value_or(0);
    return Object{{"schema","nex.project-session/1"},{"ok",code==0},{"exit_code",code},{"action",options.kind},{"component",selectedComponent},
      {"plan_hash",planHash},{"plan",std::move(plan)},{"artifacts",std::move(artifacts)},{"native_runtime_image",runtimeByComponent.contains(selectedComponent)?llvm::json::Value(runtimeByComponent.at(selectedComponent)):llvm::json::Value(nullptr)},
      {"observation",std::move(observation)},{"graph_store_opened",false},{"browser_ui_execution_verified",false}};
  }
  if(options.kind=="package"){
    // Publish the whole architecture only after every selected application and
    // browser distribution has been captured successfully.
    auto model=(packageOutput.parent_path()/".nex-project-package-XXXXXX").string();
    auto created=::mkdtemp(model.data());if(!created)fail("cannot create sibling project package staging directory","E_PROJECT_PACKAGE");
    auto stage=fs::path(created);
    try{
      llvm::json::Array packaged;bool nativeInspected=false;
      for(const auto &item:prepared){
        const auto &c=components.at(item.name);
        if(c.kind=="web"){
          const auto &web=*webResults.at(item.name).getAsObject();auto dist=web.getString("dist");
          if(!dist)fail("web build has no completed distribution","E_PROJECT_PACKAGE");
          auto destination=stage/"web"/item.name;fs::create_directories(destination);
          for(const auto &entry:fs::recursive_directory_iterator(dist->str())){
            auto relative=entry.path().lexically_relative(dist->str());
            if(entry.is_symlink()||(!entry.is_directory()&&!entry.is_regular_file()))fail("unsupported web distribution input","E_PROJECT_PACKAGE");
            if(entry.is_directory())fs::create_directories(destination/relative);
            else{fs::create_directories((destination/relative).parent_path());copyFile(entry.path().string(),(destination/relative).string(),false);}
          }
          if(!fs::is_regular_file(destination/"index.html")||!fs::is_regular_file(destination/"THIRD_PARTY_NOTICES.txt"))fail("web distribution lacks its entry/notices","E_PROJECT_PACKAGE");
          packaged.push_back(Object{{"component",item.name},{"kind","web"},{"directory","web/"+item.name},{"entry","web/"+item.name+"/index.html"},{"revision",revision(item.program)}});
        }else if(c.kind=="executable"||c.kind=="server"){
          const auto &built=images.images.contains(item.name)?images.images.at(item.name):nativeResults.at(item.name);
          auto package=options.package;package.directory=(stage/"apps"/item.name).string();package.publishedDirectory=(packageOutput/"apps"/item.name).string();
          const ForeignPackageArtifact *foreign=nullptr;
          if(options.packageProjection){options.packageProjection->verify();auto found=options.packageProjection->applications.find(item.name);if(found!=options.packageProjection->applications.end())foreign=&found->second;}
          auto result=packageNativeArtifact(item.program,built,package,foreign);auto data=result.getAsObject();
          if(options.packageProjection)options.packageProjection->verify();
          packaged.push_back(Object{{"component",item.name},{"kind",c.kind},{"directory","apps/"+item.name},{"entry","apps/"+item.name+"/bin/app"},{"manifest","apps/"+item.name+"/application.json"},{"revision",revision(item.program)},{"build_key",data->getString("build_key")->str()}});
          nativeInspected=true;
        }
      }
      Object inventory;uint64_t total=0;
      for(const auto &entry:fs::recursive_directory_iterator(stage)){
        if(entry.is_directory()&&!entry.is_symlink())continue;
        auto relative=entry.path().lexically_relative(stage).generic_string();
        if(inventory.size()>=16384||(!entry.is_regular_file()&&!entry.is_symlink()))fail("project package inventory limit/type exceeded","E_PROJECT_LIMIT");
        if(entry.is_symlink()){
          auto resolved=fs::canonical(entry.path());if(!inside(resolved,stage)||!fs::is_regular_file(resolved))fail("escaping/non-file project package symlink","E_PROJECT_PACKAGE");
          inventory[relative]=Object{{"symlink",fs::read_symlink(entry.path()).generic_string()}};continue;
        }
        auto size=entry.file_size();if(size>512ULL*1048576||size>4ULL*1024*1024*1024-total)fail("project package byte limit exceeded","E_PROJECT_LIMIT");total+=size;
        auto bytes=readFile(entry.path().string());
        auto sha=llvm::toHex(llvm::SHA256::hash(llvm::arrayRefFromStringRef(bytes)),true);
        inventory[relative]=Object{{"bytes",int64_t(bytes.size())},{"sha256",sha},{"executable",(entry.status().permissions()&fs::perms::owner_exec)!=fs::perms::none}};
      }
      auto result=Object{{"schema","nex.project-package/1"},{"ok",true},{"plan_hash",planHash},{"compiler_version",options.compilerVersion},{"compiler_build",options.compilerBuild},{"language",programLanguage(options.sourceLanguage)},
        {"configuration",configuration.name},{"profile",configuration.profile},{"components",std::move(packaged)},{"files",std::move(inventory)},{"graph_store_opened",false},{"application_execution",false},{"target_execution_verified",false},{"native_dependencies_inspected",nativeInspected}};
      if(options.packageProjection)result["foreign_projection"]=options.packageProjection->report;
      writeFile((stage/"project.json").string(),json(llvm::json::Value(Object(result)))+"\n");
      if(options.packageProjection)options.packageProjection->verify();
#ifdef __APPLE__
      int published=::renameatx_np(AT_FDCWD,stage.c_str(),AT_FDCWD,packageOutput.c_str(),RENAME_EXCL);
#elif defined(__linux__) && defined(SYS_renameat2)
      int published=int(::syscall(SYS_renameat2,AT_FDCWD,stage.c_str(),AT_FDCWD,packageOutput.c_str(),RENAME_NOREPLACE));
#else
      int published=-1;
#endif
      if(published!=0)fail("cannot publish project package without replacing an existing destination","E_PROJECT_PACKAGE");
      result["directory"]=packageOutput.string();result["manifest"]=(packageOutput/"project.json").string();return result;
    }catch(const std::exception &error){throw Error("E_PROJECT_PACKAGE",std::string(error.what())+"; partial project package retained at "+stage.string());}
  }
  Object buildResult{{"schema","nex.project-build-result/1"},{"ok",true},{"plan_hash",planHash},{"plan",std::move(plan)},{"artifacts",std::move(artifacts)},
    {"native_runtime_image",std::move(images.runtime)},{"graph_store_opened",false},{"external_tools_invoked",true},{"target_execution_verified",false},{"artifact_dependencies_inspected",false}};
  if(options.taskDebug){llvm::json::Object sessions;for(const auto &item:prepared)if(components.at(item.name).kind=="executable"){const auto &built=images.images.contains(item.name)?images.images.at(item.name):nativeResults.at(item.name);auto session=nativeDebugSession(item.program,built,root.string(),options.compiler,"nex-dap",{});if(item.name==options.component)buildResult["observation"]=llvm::json::Value(session);sessions[item.name]=std::move(session);}buildResult["debug_sessions"]=std::move(sessions);}
  if(runtimeImages.size()>1)buildResult["native_runtime_images"]=std::move(runtimeImages);
  return buildResult;
}
}
