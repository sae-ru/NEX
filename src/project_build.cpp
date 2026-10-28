#include "nex/project_build.h"
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
  const bool execution=options.kind=="run"||options.kind=="debug"||options.kind=="profile",buildTest=options.kind=="build-test",testing=options.kind=="test"||buildTest;
  if(options.kind!="plan"&&options.kind!="build"&&options.kind!="package"&&!execution&&!testing)fail("project kind must be plan, build, package, run, test, build-test, debug or profile","E_OPTION");
  if(buildTest&&options.selectedTest.empty())fail("build-test requires --symbol NAME","E_OPTION");
  if(options.kind=="debug"&&options.adapter!="lldb"&&options.adapter!="dap"&&options.adapter!="nex-dap")fail("debug adapter must be lldb, dap or nex-dap","E_OPTION");
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
  auto selectedComponent=options.component;
  if(execution){
    if(selectedComponent.empty()){
      for(const auto &[name,c]:components)if(c.kind=="executable"||c.kind=="server"||c.kind=="web"){
        if(!selectedComponent.empty())fail("project action requires --component when multiple applications exist","E_OPTION");selectedComponent=name;
      }
    }
    if(selectedComponent.empty())fail("project action requires an executable, server or web application","E_PROJECT_CAPABILITY");
    const auto &kind=components.at(selectedComponent).kind;
    if(kind!="executable"&&kind!="server"&&kind!="web")fail("project action requires an executable, server or web application","E_PROJECT_CAPABILITY");
    if((options.kind=="debug"||options.kind=="profile")&&kind!="executable")fail("project debug/profile currently requires a native executable; server workloads and browser debugging remain pending","E_PROJECT_CAPABILITY");
    if(options.kind=="profile"&&configuration.profile!="profile")fail("project profile requires a configuration whose profile is profile","E_OPTION");
    if(options.kind=="run"&&options.machine&&(kind=="server"||kind=="web")&&!options.explicitTimeout)fail("captured server/web run requires an explicit --timeout; use an interactive run for a long-lived process","E_OPTION");
    if(kind=="web"&&!options.foreign.empty())fail("a web preview receives no native foreign catalogue","E_OPTION");
  }
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
    auto program=loadProgram((root/c.entry).string(),root.string(),!options.archivedSources,options.sourceOverlays);llvm::json::Array sources;
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
      validateNativeBuildEntry(program,native);
      if(options.kind=="package"&&(c.kind=="executable"||c.kind=="server")){
        if(!imageABI.isMacOSX()&&!imageABI.isOSLinux())fail("project native packages currently require macOS or Linux targets","E_PROJECT_CAPABILITY");
        for(const auto &unit:planNative(program,native.entry).units)if(program.function(unit.identity).foreign)
          fail("project source-foreign package projection remains pending; package an explicitly reviewed source entry with its operator catalogue","E_PROJECT_CAPABILITY");
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
    std::function<void(const std::string&)> gather=[&](const auto &name){if(!walked.insert(name).second)return;for(const auto &[dep,link]:components.at(name).dependencies){if(link=="static"||link=="dynamic")binaries.insert(dep);gather(dep);}};gather(item.name);
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
  for(const auto &[file,text]:capturedSources)if(options.sourceOverlays.contains(file)?options.sourceOverlays.at(file)!=text:readFile(file)!=text)fail("captured source changed while planning: "+file,"E_PROJECT_INPUT_CHANGED");
  Object plan{{"schema","nex.project-plan/1"},{"ok",true},{"language",languageVersion},{"compiler",Object{{"version",options.compilerVersion},{"build",options.compilerBuild}}},
    {"root",root.string()},{"manifest",manifest},{"manifest_hash",hash(source)},{"architecture_hash",hash(json(*parsed,false))},{"source_project_manifest_hash",hash(sourceManifest)},
    {"configuration",Object{{"name",configuration.name},{"profile",configuration.profile},{"target",configuration.target},{"toolchain",configuration.toolchain.empty()?llvm::json::Value(nullptr):llvm::json::Value(configuration.toolchain)}}},
    {"selected_component",selectedComponent.empty()?llvm::json::Value(nullptr):llvm::json::Value(selectedComponent)},{"components",std::move(descriptions)},
    {"source_checked",true},{"graph_store_opened",false},{"external_tools_invoked",false},{"target_execution_verified",false},{"artifact_dependencies_inspected",false}};
  auto serialized=json(llvm::json::Value(Object(plan)),false);if(serialized.size()>8*1048576)fail("project plan exceeds8MiB","E_PROJECT_LIMIT");
  auto planHash=hash(serialized);plan["plan_hash"]=planHash;
  if(!options.expectedPlanHash.empty()&&planHash!=options.expectedPlanHash)fail("project test inputs changed after preflight","E_PROJECT_INPUT_CHANGED");
  if(options.kind=="plan")return plan;
  auto cache=fs::absolute(options.directory.empty()?(root/".nex/build").string():options.directory);
  if(options.kind=="debug")cache=nativeDebugBuildDirectory(cache.string());
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
        auto module=emitTypeScript(program,{{"entry",test.function}});auto key=hash(module.source+readFile(resourceFile("web/nex-runtime.ts"))+NEX_BUILD_ID);
        auto child=runTypeScriptTest(module,(cache/key/"typescript").string(),options.timeout);
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
        auto module=emitTypeScript(program,{{"entry",test.function}});auto key=hash(module.source+readFile(resourceFile("web/nex-runtime.ts"))+NEX_BUILD_ID);
        auto child=runTypeScriptTest(module,(cache/key/"typescript").string(),options.timeout);
        row["typescript_observation"]=Object{{"exit_code",child.code},{"stdout",child.output},{"stderr",child.errors}};
        ok&=child.code==0&&child.output==expected;
      }
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
    if(c.kind=="web"){webResults.emplace(item.name,buildWebApp(item.program,cache.string(),configuration.profile));continue;}
    auto expected=item.description.getAsObject()->getObject("native_toolchain")->getString("hash")->str();
    if(inspectNativeToolchain(item.options).hash!=expected)fail("native toolchain changed after project planning","E_PROJECT_INPUT_CHANGED");
    std::set<std::string> binaries,walked;
    std::function<void(const std::string&)> gather=[&](const auto &name){if(!walked.insert(name).second)return;for(const auto &[dep,link]:components.at(name).dependencies){if(link=="static"||link=="dynamic")binaries.insert(dep);gather(dep);}};gather(item.name);
    for(auto name=order.rbegin();name!=order.rend();++name)if(binaries.contains(*name)){
      const auto &dependency=nativeResults.at(*name);
      item.options.libraries.push_back({dependency.executable,hash(readFile(dependency.executable)),dependency.libraryABI,dependency.functionContracts});
    }
    nativeResults[item.name]=build(item.program,cache.string(),item.options);
  }
  std::map<std::string,std::vector<std::string>> staticFrontiers,dynamicImages;
  std::set<std::string> imageStages;
  for(const auto &item:prepared) {
    const auto &c=components.at(item.name);if(c.kind=="source"||c.kind=="web")continue;
    if(!item.options.deferredLink&&!(c.kind=="static_library"&&dynamicClosure.at(item.name)))continue;
    imageStages.insert(item.name);std::set<std::string> statics,dynamics,seen,seenDynamic;
    std::function<void(const std::string&)> nested=[&](const auto &name){if(!seenDynamic.insert(name).second)return;for(const auto &[dep,link]:components.at(name).dependencies){if(link=="dynamic")dynamics.insert(dep);nested(dep);}};
    std::function<void(const std::string&)> frontier=[&](const auto &name){if(!seen.insert(name).second)return;for(const auto &[dep,link]:components.at(name).dependencies){if(link=="dynamic"){dynamics.insert(dep);nested(dep);}else{if(link=="static")statics.insert(dep);frontier(dep);}}};frontier(item.name);
    for(auto n=order.rbegin();n!=order.rend();++n)if(statics.contains(*n))staticFrontiers[item.name].push_back(*n);
    for(const auto &n:order)if(dynamics.contains(n))dynamicImages[item.name].push_back(n);
    imageStages.insert(statics.begin(),statics.end());
  }
  std::vector<NativeImageInput> imageInputs;
  for(const auto &item:prepared)if(imageStages.contains(item.name))imageInputs.push_back({item.name,components.at(item.name).kind,&item.program,item.options,nativeResults.at(item.name),staticFrontiers[item.name],dynamicImages[item.name]});
  NativeImageResults images;if(!imageInputs.empty())images=buildNativeImages(cache.string(),imageInputs);
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
    llvm::json::Value observation=nullptr;
    verifyGrant();
    if(kind=="web"){
      observation=previewWebApp(webResults.at(selectedComponent).getAsObject()->getString("directory")->str(),options.arguments,options.timeout,options.machine);
    }else{
      const auto &built=images.images.contains(selectedComponent)?images.images.at(selectedComponent):nativeResults.at(selectedComponent);
      requireNativeHost(built);auto arguments=runtimeArguments(kind);
      if(options.kind=="profile"){
        llvm::json::Array nodes;
        for(const auto &function:item.program.functions)nodes.push_back(Object{{"name",function.name},{"hash",hash(json(canonical(function),false))},{"file",function.unit},{"id",nullptr}});
        auto profiling=options.profiling;profiling.arguments=arguments;profiling.directory=root.string();
        observation=profileNative(item.program,built,Object{{"nodes",std::move(nodes)}},profiling);
      }else if(options.kind=="debug"){
        observation=nativeDebugSession(item.program,built,root.string(),options.compiler,options.adapter,arguments);
        if(!options.machine&&options.adapter=="lldb"){
          std::vector<std::string> command{"lldb",built.executable};
          for(const auto &value:*observation.getAsObject()->getObject("launch")->getArray("initCommands")){command.push_back("-o");command.push_back(value.getAsString()->str());}
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
    verifyGrant();auto code=observation.getAsObject()->getInteger("exit_code").value_or(0);
    return Object{{"schema","nex.project-session/1"},{"ok",code==0},{"exit_code",code},{"action",options.kind},{"component",selectedComponent},
      {"plan_hash",planHash},{"plan",std::move(plan)},{"artifacts",std::move(artifacts)},{"native_runtime_image",std::move(images.runtime)},
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
          auto package=options.package;package.directory=(stage/"apps"/item.name).string();
          auto result=packageNativeArtifact(item.program,built,package);auto data=result.getAsObject();
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
      auto result=Object{{"schema","nex.project-package/1"},{"ok",true},{"plan_hash",planHash},{"compiler_version",options.compilerVersion},{"compiler_build",options.compilerBuild},{"language",languageVersion},
        {"configuration",configuration.name},{"profile",configuration.profile},{"components",std::move(packaged)},{"files",std::move(inventory)},{"graph_store_opened",false},{"application_execution",false},{"target_execution_verified",false},{"native_dependencies_inspected",nativeInspected}};
      writeFile((stage/"project.json").string(),json(llvm::json::Value(Object(result)))+"\n");
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
  return Object{{"schema","nex.project-build-result/1"},{"ok",true},{"plan_hash",planHash},{"plan",std::move(plan)},{"artifacts",std::move(artifacts)},
    {"native_runtime_image",std::move(images.runtime)},{"graph_store_opened",false},{"external_tools_invoked",true},{"target_execution_verified",false},{"artifact_dependencies_inspected",false}};
}
}
