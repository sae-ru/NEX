#include "nex/migration.h"
#include "nex/backend.h"
#include "nex/task_frontend.h"
#include "nex/task_limits.h"
#include "nex/discovery.h"
#include "nex/wasm.h"
#include "nex/frontend_diagnostics.h"
#include "nex/editor.h"
#include "nex/native_diagnostics.h"
#include "nex/native_toolchain.h"
#include "nex/project.h"
#include "nex/project_build.h"
#include "nex/graph_snapshot.h"
#include "nex/web.h"
#include "nex/api.h"
#include "nex/profiling.h"
#include "nex/verification.h"
#include "nex/tasks.h"
#include "nex/task_package.h"
#include "nex/foreign_catalogue.h"
#include "nex/debugging.h"
#include "nex/debug_session.h"
#include "nex/core_dump.h"
#include "nex/packaging.h"
#include "llvm/Support/FileSystem.h"
#include "llvm/Support/Program.h"
#include "llvm/Support/Error.h"
#include "llvm/Support/RandomNumberGenerator.h"
#include "llvm/Support/SHA256.h"
#include "nex_auth.h"
#include "nex_json.h"
#include "nex_foreign.h"
#include "llvm/Config/llvm-config.h"
#include "llvm/TargetParser/Host.h"
#include <filesystem>
#include <iostream>
#include <algorithm>
#include <functional>
#include <array>
#include <cerrno>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

namespace fs=std::filesystem;
namespace {
using namespace nex;
struct Options {
  std::string command,compiler;std::map<std::string,std::string> values;std::set<std::string> flags;
  std::vector<std::string> positional,extra;
  bool has(const std::string &name)const{return flags.contains(name);}
  std::string get(const std::string &name,const std::string &fallback="")const{auto i=values.find(name);return i==values.end()?fallback:i->second;}
};
Options options(int argc,char **argv) {
  Options o;o.command=argc>1?argv[1]:"help";o.compiler=llvm::sys::fs::getMainExecutable(argv[0],reinterpret_cast<void*>(&options));
  const std::set<std::string> flagNames={"--json","--interpreter-only","--library","--dpkg-notices","--task-debug"};
  const std::set<std::string> valueNames={"--workload","--adapter","--profile-output","--component","--configuration","--profile","--target","--toolchain","--toolchains","--entry","--kind","--revision","--steps","--task-steps","--task-timeout-ms","--task-workers","--patch","--symbol","--output","--directory","--user","--auth","--events","--timeout","--scenario","--contracts","--solver-timeout","--resource-limit","--build-directory","--candidates","--task-hash","--manifest","--expression","--operation","--site","--offset","--limit","--notices","--foreign","--entity","--origin","--node","--from-revision","--expected-revision","--log","--note","--actor","--query","--field","--depth","--direction","--edge-offset","--edge-limit"};
  for(int i=2;i<argc;++i){
    std::string a=argv[i];if(a=="--"){while(++i<argc)o.extra.push_back(argv[i]);break;}
    if(a=="-o")a="--output";
    if(flagNames.contains(a)){if(a=="--task-debug"&&o.command!="project")throw Error("E_OPTION","--task-debug requires project plan/build/package");o.flags.insert(a);}
    else if(a=="--overlay"){if(o.command!="analyze"||i+1==argc)throw Error("E_OPTION","--overlay requires analyze and a JSON file");o.values[a]=argv[++i];}
    else if(a=="--details"){if(o.command!="analyze")throw Error("E_OPTION","--details requires analyze");o.flags.insert(a);}
    else if(a=="--references"){if(o.command!="analyze")throw Error("E_OPTION","--references requires analyze");o.flags.insert(a);}
    else if(a=="--capsule"||a=="--export"){if(o.command!="core"||i+1==argc)throw Error("E_OPTION","--capsule/--export require core and a directory");o.values[a]=argv[++i];}
    else if(a=="--thread"||a=="--frame"){if(o.command!="core"||i+1==argc)throw Error("E_OPTION","--thread/--frame require core and an index");o.values[a]=argv[++i];}
    else if(valueNames.contains(a)){if(i+1==argc)throw Error("E_OPTION","missing value for "+a);if(a.starts_with("--task-")&&o.values.contains(a))throw Error("E_OPTION","duplicate option "+a);o.values[a]=argv[++i];}
    else if(a.starts_with("-"))throw Error("E_OPTION","unknown option "+a);
    else o.positional.push_back(a);
  }
  if(o.positional.size()>1)throw Error("E_OPTION","expected at most one source file or directory");return o;
}
void print(llvm::json::Value value){std::cout<<json(value)<<'\n';}
llvm::json::Value parseJSON(const std::string &text) {
  auto value=llvm::json::parse(text);if(!value)throw Error("E_JSON",llvm::toString(value.takeError()));return std::move(*value);
}
std::string readBoundedText(const std::string &path,size_t limit,const std::string &label,const std::string &code){
  struct File{int fd;~File(){if(fd>=0)::close(fd);}} file{::open(path.c_str(),O_RDONLY|O_NONBLOCK|O_NOFOLLOW|O_CLOEXEC)};
  struct stat info{};
  if(file.fd<0||::fstat(file.fd,&info)||!S_ISREG(info.st_mode)||info.st_size<0||uint64_t(info.st_size)>limit)throw Error(code,label+" requires a regular non-symlink file of at most "+std::to_string(limit)+" bytes");
  std::string text;std::array<char,65536> buffer{};
  for(;;){auto count=::read(file.fd,buffer.data(),buffer.size());if(count<0){if(errno==EINTR)continue;throw Error("E_FILE","cannot read "+label);}if(!count)break;if(size_t(count)>limit-text.size())throw Error(code,label+" exceeds "+std::to_string(limit)+" bytes");text.append(buffer.data(),size_t(count));}
  try{nexrt::unicodeOffsets(text,false);}catch(const nexrt::DataError&){throw Error("E_JSON",label+" must be valid UTF-8");}
  return text;
}
llvm::json::Value readPatch(const std::string &path){
  auto text=readBoundedText(path,4*1048576,"patch","E_PATCH_LIMIT");
  unsigned depth=0;bool quoted=false,escape=false;
  for(char c:text){
    if(quoted){if(escape)escape=false;else if(c=='\\')escape=true;else if(c=='"')quoted=false;continue;}
    if(c=='"')quoted=true;else if(c=='{'||c=='['){if(++depth>64)throw Error("E_PATCH_LIMIT","patch JSON exceeds depth 64");}
    else if((c=='}'||c==']')&&depth)--depth;
  }
  return parseJSON(text);
}
llvm::json::Value readIdentityManifest(const std::string &path){return parseJSON(readBoundedText(path,4*1048576,"identity manifest","E_IDENTITY_LIMIT"));}
std::string required(const llvm::json::Object &object,const std::string &key){auto v=object.getString(key);if(!v)throw Error("E_JSON","missing string '"+key+"'");return v->str();}
std::shared_ptr<nexrt::ForeignLibraries> foreignLibraries(const std::string &path){
  try{return nexrt::loadForeignLibraries(path);}
  catch(const nexrt::DataError &error){throw Error(error.code,error.what());}
}
std::string defaultSource(const fs::path &root){
  if(fs::exists(root/"nex.json")){auto value=parseJSON(readFile((root/"nex.json").string()));auto obj=value.getAsObject();if(!obj)throw Error("E_MANIFEST","manifest must be an object");return (root/required(*obj,"entry")).string();}
  return (root/"main.nex").string();
}
llvm::json::Value graphSources(const llvm::json::Object &object){
  if(auto bundle=object.get("bundle"))return *bundle;
  auto source=required(object,"source");
  return llvm::json::Object{{"schema","nex.sources/1"},{"entry","main.nex"},{"files",llvm::json::Object{{"main.nex",source}}}};
}
ChangeInfo changeInfo(const Options &o,const std::string &action,const std::string &request=""){return {action,o.command,o.get("--actor"),o.get("--note"),request};}
Program load(const Options &o,const fs::path &root,Store &store,bool saved=false) {
  auto rev=o.get("--revision",saved?"HEAD":"");
  if(rev.empty()){
    const auto previous=store.headRevision();
    if(!previous.empty()&&store.revisionLanguage(previous)!=languageVersion)
      throw Error("E_LANGUAGE_VERSION","graph HEAD uses another language version; run nex migrate explicitly");
    auto path=fs::absolute(o.positional.empty()?defaultSource(root):o.positional[0]).string();
    auto p=loadProgram(path,root.string(),o.command!="lock");store.save(p,"",true,changeInfo(o,"synchronize"));return p;
  }
  auto selected=rev=="HEAD"?store.headRevision():rev;
  if(store.revisionLanguage(selected)!=languageVersion)throw Error("E_LANGUAGE_VERSION","stored revision uses another language version; run nex migrate or export its source and check it");
  auto p=loadBundle(store.bundle(selected),root.string());
  if(revision(p)!=selected)throw Error("E_REVISION","stored source does not match its semantic revision");return p;
}
void migrate(const Options &o,const fs::path &root){
  std::unique_ptr<Store> archive;
  if(fs::exists(root/".nex/graph.db"))archive=std::make_unique<Store>(root/".nex",StoreOpenMode::ReadOnly);
  auto previous=archive?archive->headRevision():std::string{};
  auto expected=o.get("--expected-revision",previous.empty()?"EMPTY":previous);
  if(expected.empty())throw Error("E_OPTION","migration requires a nonempty expected revision");
  if(previous!=(expected=="EMPTY"?"":expected))throw Error("E_CONFLICT","graph HEAD changed; read context and retry");
  std::string original,originLanguage;llvm::json::Value bundle=nullptr;bool verified=false;
  if(o.positional.empty()){
    if(!archive)throw Error("E_REVISION","migration requires an existing archived revision or graph JSON");
    original=o.get("--revision","HEAD");if(original=="HEAD")original=previous;
    originLanguage=archive->revisionLanguage(original);validateMigrationLanguage(originLanguage);
    bundle=archive->bundle(original);verified=verifyMigrationOrigin(bundle,root,originLanguage,original);
  }else{
    auto value=parseJSON(readFile(o.positional[0]));auto object=value.getAsObject();
    if(!object||(required(*object,"schema")!="nex.graph/1"&&required(*object,"schema")!="nex.graph/2"))throw Error("E_SCHEMA","expected an exported NEX graph");
    original=required(*object,"revision");originLanguage=required(*object,"language");validateMigrationLanguage(originLanguage);
    bundle=graphSources(*object);
    if(archive&&archive->containsRevision(original)){
      if(archive->revisionLanguage(original)!=originLanguage)throw Error("E_REVISION","graph origin language differs from the retained revision");
      verified=verifyMigrationOrigin(archive->bundle(original),root,originLanguage,original);
    }else verified=verifyMigrationOrigin(bundle,root,originLanguage,original);
  }
  // No writable Store, schema upgrade or destination creation before both the
  // origin integrity check and complete current-language target preflight.
  auto program=preflightMigrationTarget(bundle,root);auto sourceHash=hash(json(bundle,false));
  archive.reset();
  Store store(root/".nex");auto selected=store.save(program,expected,true,changeInfo(o,"migrate",sourceHash));
  print(llvm::json::Object{{"schema","nex.migration/1"},{"ok",true},{"declared_original_revision",original},
    {"origin_language",originLanguage},{"origin_verified",verified},{"previous_revision",previous},
    {"revision",selected},{"language",programLanguage(program)},{"source_hash",sourceHash},
    {"changed",previous!=selected},{"materialized",false}});
}
int run(const Options &o) {
  nexrt::TaskExecutionLimits taskLimits;bool taskLimitsSpecified=false;
  for(const auto &[flag,maximum]:std::vector<std::pair<std::string,uint64_t>>{{"--task-steps",nexrt::maximumTaskExecutionSteps},{"--task-timeout-ms",nexrt::maximumTaskExecutionTimeoutMs},{"--task-workers",nexrt::maximumTaskExecutionWorkers}}){
    if(!o.values.contains(flag))continue;
    if(o.command!="eval"&&o.command!="build"&&o.command!="run"&&o.command!="test"&&o.command!="package"&&o.command!="profile"&&o.command!="debug")
      throw Error("E_OPTION","task limits require eval/build/run/test/package/profile/debug; project limits belong in configuration.task_limits");
    auto value=nexrt::parseTaskLimitDecimal(o.get(flag),maximum);
    if(!value)throw Error("E_OPTION","invalid positive decimal value for "+flag);
    taskLimitsSpecified=true;if(flag=="--task-steps")taskLimits.steps=*value;
    else if(flag=="--task-timeout-ms")taskLimits.timeoutMs=*value;else taskLimits.workers=unsigned(*value);
  }
  if(taskLimitsSpecified&&o.command=="build"&&(o.get("--target")=="web"||o.get("--target")=="wasm"))
    throw Error("E_OPTION","task limits require a native task application build");
  if(o.values.contains("--steps")&&(o.command=="run"||o.command=="test"||o.command=="build"||o.command=="package"||o.command=="profile"||o.command=="debug"))
    throw Error("E_OPTION","--steps is an interpreter option; use --task-steps for task applications");
  if(o.command=="eval"&&taskLimitsSpecified&&o.values.contains("--steps"))
    throw Error("E_OPTION","use either --steps or --task-steps for task evaluation");
  if(o.command=="project"){
    const auto kind=o.get("--kind","plan");const bool packaging=kind=="package",execution=kind=="run"||kind=="test"||kind=="profile"||kind=="debug";
    for(const auto &[key,value]:o.values){(void)value;
      bool allowed=((kind=="plan"||kind=="profile")&&key=="--workload")||key=="--kind"||key=="--component"||key=="--configuration"||key=="--build-directory"||key=="--output"||
        (packaging&&(key=="--directory"||key=="--notices"))||((execution||packaging||kind=="plan")&&key=="--foreign")||
        ((kind=="run"||kind=="test"||kind=="profile")&&key=="--timeout")||((kind=="test"||kind=="build-test")&&key=="--symbol")||
        (kind=="debug"&&key=="--adapter")||(kind=="profile"&&(key=="--profile-output"||key=="--events"||key=="--scenario"));
      if(!allowed)throw Error("E_OPTION","unsupported project option: "+key);
    }
    for(const auto &flag:o.flags)if(flag!="--json"&&!(packaging&&flag=="--dpkg-notices")&&
      !(flag=="--task-debug"&&(kind=="plan"||kind=="build"||packaging)))throw Error("E_OPTION","unsupported project flag: "+flag);
    if(!o.extra.empty()&&kind!="run"&&kind!="profile"&&kind!="debug")throw Error("E_OPTION","application arguments require project run/profile/debug");
    auto selected=fs::absolute(o.positional.empty()?projectRoot(fs::current_path())/"nex.build.json":fs::path(o.positional[0]));
    if(fs::is_directory(selected))selected/="nex.build.json";
    auto source=readBoundedText(selected.string(),262144,"project build manifest","E_PROJECT_LIMIT");
    try{nexrt::validateJSONText(source);}catch(const nexrt::DataError &e){throw Error("E_PROJECT_BUILD",e.what());}
    ProjectBuildOptions project{o.get("--kind","plan"),o.get("--component"),o.get("--configuration"),o.get("--build-directory"),NEX_VERSION,NEX_BUILD_ID};
    project.taskDebug=o.has("--task-debug");
    project.package.directory=o.get("--directory");project.package.notices=o.get("--notices");project.package.compiler=o.compiler;project.package.dpkgNotices=o.has("--dpkg-notices");
    auto count=[&](const std::string &key,unsigned fallback,unsigned minimum,unsigned maximum){
      auto raw=o.get(key);if(!o.values.contains(key))return fallback;if(raw.empty())throw Error("E_OPTION",key+" requires a nonempty integer");uint64_t n=0;
      for(char c:raw){if(c<'0'||c>'9'||n>(maximum-unsigned(c-'0'))/10)throw Error("E_OPTION",key+" is outside its supported integer range");n=n*10+unsigned(c-'0');}
      if(n<minimum||n>maximum)throw Error("E_OPTION",key+" is outside its supported integer range");return unsigned(n);
    };
    project.compiler=o.compiler;project.machine=o.has("--json");project.adapter=o.get("--adapter","lldb");project.arguments=o.extra;
    project.foreign=o.get("--foreign");if(packaging)project.package.foreign=project.foreign;
    project.selectedTest=o.get("--symbol");project.timeout=count("--timeout",30,1,3600);project.explicitTimeout=o.values.contains("--timeout");
    if(o.values.contains("--workload")&&o.get("--workload").empty())throw Error("E_OPTION","--workload requires a nonempty project file");
    project.workload=o.get("--workload");
    project.profiling={o.get("--profile-output"),o.get("--scenario"),count("--events",100000,0,1000000),project.timeout,{}};
    auto result=buildProject(selected.parent_path().string(),selected.string(),source,project);
    auto code=int(result.getAsObject()->getInteger("exit_code").value_or(0));
    if(o.values.contains("--output"))writeFile(o.get("--output"),json(result)+"\n");
    if(project.machine||(kind!="run"&&(kind!="debug"||project.adapter!="lldb")))print(std::move(result));return code;
  }
  if(o.values.contains("--workload"))throw Error("E_OPTION","--workload requires project plan/profile");
  if(o.values.contains("--adapter")||o.values.contains("--profile-output"))throw Error("E_OPTION","--adapter/--profile-output require project");
  if((o.values.contains("--component")||o.values.contains("--configuration"))&&!(o.command=="task"&&o.get("--kind")=="init"&&!o.get("--component").empty()))throw Error("E_OPTION","--component/--configuration require project or project task init");
  if(o.command=="analyze"){
    if(!o.extra.empty())throw Error("E_OPTION","analyze does not execute program arguments");
    for(const auto &[key,_]:o.values)if(key!="--overlay")throw Error("E_OPTION","unsupported analyze option: "+key);
    for(const auto &flag:o.flags)if(flag!="--json"&&flag!="--references"&&flag!="--details")throw Error("E_OPTION","unsupported analyze flag: "+flag);
    auto root=projectRoot(o.positional.empty()?fs::current_path():fs::absolute(o.positional[0]).parent_path());
    auto entry=fs::absolute(o.positional.empty()?defaultSource(root):o.positional[0]).string();
    llvm::json::Value overlay=nullptr;
    if(o.values.contains("--overlay")){
      auto text=readBoundedText(o.get("--overlay"),16*1048576,"editor overlay","E_OVERLAY");
      unsigned depth=0;bool quoted=false,escape=false;
      for(char c:text){if(quoted){if(escape)escape=false;else if(c=='\\')escape=true;else if(c=='"')quoted=false;}
        else if(c=='"')quoted=true;else if(c=='{'||c=='['){if(++depth>8)throw Error("E_OVERLAY","editor overlay exceeds JSON depth 8");}
        else if((c=='}'||c==']')&&depth)--depth;}
      overlay=parseJSON(text);
    }
    if(o.has("--references")&&o.has("--details"))throw Error("E_OPTION","choose --references for analysis/2 or --details for analysis/3");
    auto result=editorAnalysis(entry,root.string(),overlay,o.has("--references"),o.has("--details"));
    result.getAsObject()->insert({"compiler",llvm::json::Object{{"version",NEX_VERSION},{"build",NEX_BUILD_ID}}});
    print(std::move(result));return 0;
  }
  if(o.command=="lsp"){
    if(!o.values.empty()||!o.flags.empty()||!o.positional.empty()||!o.extra.empty())throw Error("E_OPTION","lsp uses standard input/output without CLI options");
    auto python=llvm::sys::findProgramByName(std::getenv("NEX_PYTHON")?std::getenv("NEX_PYTHON"):"python3");
    if(!python)throw Error("E_LSP","Python3 is required for nex lsp");
    auto helper=resourceFile("editor/lsp/server.py");std::vector<llvm::StringRef> args{*python,helper,"--compiler",o.compiler};
    return llvm::sys::ExecuteAndWait(*python,args);
  }
  if(o.command=="core"){
    const std::set<std::string> allowed={"--manifest","--expression","--timeout","--thread","--frame","--capsule","--export"};
    for(const auto &[key,value]:o.values){(void)value;if(!allowed.contains(key))throw Error("E_OPTION","unsupported core option: "+key);}
    for(const auto &flag:o.flags)if(flag!="--json")throw Error("E_OPTION","unsupported core flag: "+flag);
    bool capsule=o.values.contains("--capsule"),exporting=o.values.contains("--export");
    if(!o.extra.empty()||(capsule?(!o.positional.empty()||o.values.contains("--manifest")||exporting||o.get("--capsule").empty()):(o.positional.size()!=1||o.get("--manifest").empty()))||(exporting&&o.get("--export").empty()))throw Error("E_OPTION","core requires CORE_FILE --manifest DEBUG.json [--export NEW_DIRECTORY], or --capsule DIRECTORY");
    auto number=[&](const char *key,int fallback,unsigned maximum){if(!o.values.contains(key))return fallback;auto value=o.get(key);unsigned result=0;if(value.empty())throw Error("E_OPTION","empty core range");for(char c:value){if(c<'0'||c>'9'||result>(maximum-unsigned(c-'0'))/10)throw Error("E_OPTION","invalid core range");result=result*10+unsigned(c-'0');}if(result>maximum)throw Error("E_OPTION","invalid core range");return int(result);};
    CoreOptions core;core.core=capsule?"":o.positional[0];core.manifest=o.get("--manifest");core.compiler=o.compiler;core.expression=o.get("--expression");core.thread=number("--thread",-1,63);core.frame=number("--frame",-1,63);core.timeout=unsigned(number("--timeout",60,300));
    if(capsule)print(inspectCoreCapsule(o.get("--capsule"),core));
    else if(exporting)print(exportCoreCapsule(o.get("--export"),core));
    else print(inspectCore(core));return 0;
  }
  bool graphQuery=o.command=="search"||o.command=="subgraph";GraphQueryOptions queryOptions;
  for(const auto &key:{"--query","--field","--depth","--direction","--edge-offset","--edge-limit"})
    if(!graphQuery&&o.values.contains(key)&&!(o.command=="describe"&&std::string(key)=="--field"))
      throw Error("E_OPTION",std::string(key)+(std::string(key)=="--field"?" requires search or describe":" requires search or subgraph"));
  if(graphQuery){
    std::set<std::string> allowed={"--revision","--entity","--offset","--limit","--output"};
    if(o.command=="search"){allowed.insert("--query");allowed.insert("--field");}
    else for(const auto &key:{"--symbol","--direction","--depth","--edge-offset","--edge-limit"})allowed.insert(key);
    if(!o.positional.empty()||!o.extra.empty())throw Error("E_OPTION","graph queries read saved revisions, without physical source or execution arguments");
    for(const auto &[key,value]:o.values){(void)value;if(!allowed.contains(key))throw Error("E_OPTION","unsupported graph query option: "+key);}
    for(const auto &flag:o.flags)if(flag!="--json")throw Error("E_OPTION","unsupported graph query flag: "+flag);
    auto count=[&](const std::string &key,unsigned fallback,unsigned maximum){if(!o.values.contains(key))return fallback;auto text=o.get(key);uint64_t value=0;if(text.empty())throw Error("E_OPTION","empty graph query range: "+key);for(char c:text){if(c<'0'||c>'9'||value>(maximum-unsigned(c-'0'))/10)throw Error("E_OPTION","invalid graph query range: "+key);value=value*10+unsigned(c-'0');}return unsigned(value);};
    queryOptions.query=o.get("--query");queryOptions.entity=o.get("--entity",o.command=="search"?"all":"function");queryOptions.field=o.get("--field","any");queryOptions.symbol=o.get("--symbol");queryOptions.direction=o.get("--direction","dependencies");
    queryOptions.depth=count("--depth",1,8);queryOptions.offset=count("--offset",0,10000000);queryOptions.limit=count("--limit",100,1000);queryOptions.edgeOffset=count("--edge-offset",0,10000000);queryOptions.edgeLimit=count("--edge-limit",100,1000);
    if(o.values.contains("--revision")){auto selected=o.get("--revision");if(selected!="HEAD"&&(selected.size()!=64||selected.find_first_not_of("0123456789abcdef")!=std::string::npos))throw Error("E_OPTION","graph queries require --revision HEAD or a lowercase 64-character digest");}
    validateGraphQuery(queryOptions,o.command=="subgraph");
  }
  if(o.values.contains("--note")||o.values.contains("--actor")){
    const std::set<std::string> supported={"check","apply","import","migrate","restore"};
    if(!supported.contains(o.command))throw Error("E_OPTION","--note and --actor annotate check/apply/import/migrate/restore");
    validateChangeInfo(changeInfo(o,"save"));
  }
  if(o.command=="changes"||o.command=="restore"){
    std::set<std::string> allowed=o.command=="changes"?std::set<std::string>{"--offset","--limit","--output"}:std::set<std::string>{"--revision","--expected-revision","--note","--actor"};
    if(!o.positional.empty()||!o.extra.empty())throw Error("E_OPTION","changes/restore select the current project store, without source files or execution arguments");
    for(const auto &[key,value]:o.values){(void)value;if(!allowed.contains(key))throw Error("E_OPTION","unsupported option for "+o.command+": "+key);}
    for(const auto &flag:o.flags)if(flag!="--json")throw Error("E_OPTION","unsupported flag for "+o.command+": "+flag);
    if(o.command=="restore"){
      auto target=o.get("--revision"),expected=o.get("--expected-revision");
      auto digest=[](const std::string &v){return v.size()==64&&v.find_first_not_of("0123456789abcdef")==std::string::npos;};
      if(!digest(target)||(!digest(expected)&&expected!="EMPTY"))throw Error("E_OPTION","restore requires --revision HASH and --expected-revision HEAD_HASH|EMPTY");
    }
  }
  if(o.values.contains("--entity")&&o.command!="context"&&o.command!="declarations"&&o.command!="identities"&&!graphQuery)throw Error("E_OPTION","--entity selects graph declarations/identities or typed context");
  for(const auto &name:{"--origin","--node","--from-revision","--expected-revision"})if(o.values.contains(name)&&o.command!="identities"&&!((o.command=="restore"||o.command=="migrate")&&std::string(name)=="--expected-revision"))throw Error("E_OPTION",std::string(name)+" is for graph identities or guarded restore/migrate");
  if(o.command=="identities"){
    auto kind=o.get("--kind","export");if(kind!="export"&&kind!="reconcile"&&kind!="resolve")throw Error("E_OPTION","identities kind must be export, reconcile or resolve");
    if(kind!="export"&&!o.positional.empty())throw Error("E_OPTION","identity mutation/lookup selects an archived graph, without source-file synchronization");
    if(kind=="reconcile"&&(o.get("--expected-revision").empty()||o.get("--manifest").empty()))throw Error("E_OPTION","reconcile requires --manifest FILE and --expected-revision HEAD_HASH");
    if(kind=="resolve"&&(o.get("--origin").empty()||o.get("--node").empty()||o.get("--from-revision").empty()))throw Error("E_OPTION","resolve requires --origin NAMESPACE --from-revision SOURCE_HASH --node ID");
    if(kind!="export")for(const auto &name:{"--entity","--symbol","--offset","--limit"})if(o.values.contains(name))throw Error("E_OPTION","identity reconciliation/lookup uses complete references, without export filters");
    for(const auto &name:{"--origin","--node","--from-revision"})if(kind!="resolve"&&o.values.contains(name))throw Error("E_OPTION",std::string(name)+" requires identities --kind resolve");
    for(const auto &name:{"--manifest","--expected-revision"})if(kind!="reconcile"&&o.values.contains(name))throw Error("E_OPTION",std::string(name)+" requires identities --kind reconcile");
  }
  if(o.command=="context"&&o.values.contains("--entity")&&(o.values.contains("--operation")||o.values.contains("--site")))throw Error("E_OPTION","--entity requires declaration context with --symbol");
  if((o.values.contains("--notices")||o.has("--dpkg-notices"))&&o.command!="package")throw Error("E_OPTION","--notices and --dpkg-notices are for native package");
  if(o.command=="package"){
    if(o.get("--directory").empty())throw Error("E_OPTION","package requires --directory NEW_DIRECTORY");
    if(o.get("--target")=="web"||o.get("--target")=="wasm"||o.has("--interpreter-only")||o.has("--library")||o.values.contains("--output")||o.values.contains("--kind")||!o.extra.empty())
      throw Error("E_OPTION","package builds a native executable/server; use --directory for its output");
    auto output=fs::absolute(o.get("--directory")).lexically_normal();
    if(fs::exists(output)||fs::is_symlink(output))throw Error("E_EXISTS","package requires a new output directory");
  }
  if(o.get("--target")=="wasm"&&(o.command!="build"||o.has("--library")||o.has("--interpreter-only")||
     o.values.contains("--toolchain")||o.values.contains("--directory")||o.values.contains("--kind")||!o.extra.empty()))
    throw Error("E_OPTION","scalar Wasm uses build --target wasm --entry NAME, with optional --profile debug|release and -o NEW_DIRECTORY");
  if(o.values.contains("--foreign")&&o.command!="eval"&&o.command!="run"&&o.command!="test"&&o.command!="debug"&&o.command!="profile"&&o.command!="task"&&o.command!="package")throw Error("E_OPTION","--foreign FILE is for eval/run/test/debug/profile/package or reviewed task execution");
  if(o.values.contains("--toolchains")&&o.command!="task")throw Error("E_OPTION","--toolchains FILE is for task check/run/replay");
  if(o.values.contains("--toolchain")){
    const std::set<std::string> nativeCommands={"build","package","run","test","debug","profile","emit"};
    if(o.get("--toolchain").empty()||!nativeCommands.contains(o.command)||o.get("--target")=="web"||o.has("--interpreter-only")||(o.command=="emit"&&o.get("--kind")!="llvm"))
      throw Error("E_OPTION","--toolchain FILE selects a native build/package/run/test/debug/profile or emit --kind llvm");
  }
  if(o.command=="snapshot"||o.command=="recover"){
    const std::set<std::string> allowed={"--directory","--timeout"};
    for(const auto &[key,value]:o.values){(void)value;if(!allowed.contains(key))throw Error("E_OPTION","unsupported snapshot/recovery option: "+key);}
    for(const auto &flag:o.flags)if(flag!="--json")throw Error("E_OPTION","unsupported snapshot/recovery flag: "+flag);
    if(!o.extra.empty()||o.get("--directory").empty()||(o.command=="snapshot"&&!o.positional.empty())||(o.command=="recover"&&o.positional.empty()))throw Error("E_OPTION","snapshot needs --directory NEW; recover needs SNAPSHOT --directory NEW_PROJECT");
    unsigned seconds=60;if(o.values.contains("--timeout")){auto text=o.get("--timeout");seconds=0;if(text.empty())throw Error("E_OPTION","snapshot timeout must be 1..3600 seconds");for(char c:text){if(c<'0'||c>'9'||seconds>(3600-unsigned(c-'0'))/10)throw Error("E_OPTION","invalid snapshot timeout");seconds=seconds*10+unsigned(c-'0');}if(!seconds)throw Error("E_OPTION","snapshot timeout must be 1..3600 seconds");}
    auto result=o.command=="snapshot"?createGraphSnapshot(projectRoot(fs::current_path()).string(),o.get("--directory"),seconds):recoverGraphSnapshot(o.positional[0],o.get("--directory"),seconds);
    print(std::move(result));return 0;
  }
  if(o.command=="help"||o.command=="--help"||o.command=="-h") {
    std::cout<<"NEX "<<NEX_VERSION<<" (language "<<languageVersion<<")\n"
      "  nex init [directory]\n  nex project [directory|nex.build.json] [--kind plan|build|package|run|test|build-test|debug|profile] [--component NAME] [--configuration NAME] [--workload FILE] [--foreign HOST.json] [--task-debug (plan/build/package)] [--json]\n  nex describe [--kind full|index | --field PATH] [--json]\n  nex analyze [file] [--overlay FILE] [--references|--details] [--json]\n  nex lsp\n  nex guide --kind dns|tcp|model|compute|task-provider-debug|task-provider-profile|task-shared-providers|task-providers|task-debug|task-file-reads|task-external|task-limits|tasks-runtime|browser-worker|project|project-task|server-workload|server-debug|task-workload|prompt|lsp|language|grammar|protocol|web|server|api|debug|build|profile|verify|task|expression|operation|graph|linux|match|function|files|bytes|resources|ffi|history|snapshot|compatibility|frontend|query|string-debug|trait|editor [--json]\n  nex doctor\n  nex toolchain FILE [--json]\n"
      "  Task hosts: --task-steps N --task-timeout-ms N --task-workers N (see guide)\n  nex check|eval|build|run|test|emit [file] [--json]\n  nex package [file] --directory NEW [--target server] [--notices FILE] [--dpkg-notices] [--json]\n  nex profile [file] [--events COUNT] [--timeout SECONDS] [--scenario TEXT] [-o REPORT.json] [--json]\n  nex contract [file] --symbol NAME [-o CONTRACT.json]\n  nex verify [file] --contracts FILE [--symbol NAME] [--solver-timeout MS] [--resource-limit COUNT] [--timeout SECONDS] [--json]\n"
      "  nex ffi [file] --symbol NAME [--json]\n  nex foreign HOST.json [--json]\n  nex snapshot --directory NEW [--timeout SECONDS] [--json]\n  nex recover SNAPSHOT --directory NEW_PROJECT [--timeout SECONDS] [--json]\n  nex graph|history [--json]\n  nex search --query TEXT [--entity KIND] [--field symbol|source|any] [--revision HASH] [--json]\n  nex subgraph --symbol NAME [--entity KIND] [--direction dependencies|dependents|both] [--depth N] [--json]\n  nex context --symbol NAME | --operation ID | --site KEY\n  nex operations --symbol NAME [--offset N] [--limit N] [--json]\n"
      "  nex declarations [file] [--entity module|type|trait|impl] [--symbol NAME] [--offset N] [--limit N]\n  nex context --entity module|type|trait|impl|function|endpoint --symbol NAME\n"
      "  nex identities [file] [--entity all|module|type|trait|impl|function|endpoint|operation] [--symbol NAME] [-o PAGE.json]\n  nex identities --kind reconcile --manifest PAGE.json --expected-revision HEAD_HASH [--revision HASH]\n  nex identities --kind resolve --origin NAMESPACE --from-revision SOURCE_HASH --node ID [--revision HASH]\n"
      "  nex changes [--offset N] [--limit N] [-o PAGE.json]\n  nex restore --revision HASH --expected-revision HEAD_HASH [--note TEXT] [--actor LABEL]\n  nex apply --patch FILE\n  nex export --revision HEAD -o FILE\n"
      "  nex import FILE\n  nex migrate [GRAPH.json] [--revision HASH]\n  nex lock [file]\n  nex export --directory PATH\n  nex web [file] --directory PATH\n  nex api [file] [--directory PATH]\n  nex token --user USER --auth FILE\n  nex debug [file] [--kind lldb|dap|nex-dap] [--json] -- [lldb options]\n"
      "  nex core CORE_FILE --manifest DEBUG.json [--export NEW_DIRECTORY] [--expression TEXT] [--thread INDEX] [--frame INDEX] [--json]\n  nex core --capsule DIRECTORY [--expression TEXT] [--thread INDEX] [--frame INDEX] [--json]\n"
      "  nex diagnose [file] --manifest DEBUG.json --log STDERR.log [--revision HASH] [--json]\n"
      "  nex inspect [FRAME.json] --manifest DEBUG.json --expression TEXT [--kind plan|demand|value] [--steps COUNT] [--json]\n"
      "  nex task SOURCE --kind init [-o TASK.json]\n  nex task NOTICES.json --kind notices\n  nex task TASK.json --kind check|run|history [--task-hash HASH] [--revision HASH | --candidates FILE]\n  nex task RECEIPT.json --kind replay [--directory NEW_RUN] [--toolchains CATALOG.json]\n  nex contract --kind intent --contracts FILE\n"
      "Options: --profile debug|profile|release --entry NAME --target native|TRIPLE|web|server|wasm --toolchain FILE\n"
      "         --foreign HOST.json (eval/run/test/debug/profile/task check/run/replay)\n         --kind mlir|llvm|typescript --revision HASH --steps COUNT --interpreter-only --library --build-directory PATH\n";return 0;
  }
  if(o.command=="describe"){
    if(!o.positional.empty()||!o.extra.empty())throw Error("E_OPTION","describe does not take source files or execution arguments");
    for(const auto &[key,value]:o.values){(void)value;if(key!="--kind"&&key!="--field")throw Error("E_OPTION","unsupported describe option: "+key);}
    for(const auto &flag:o.flags)if(flag!="--json")throw Error("E_OPTION","unsupported describe flag: "+flag);
    const bool field=o.values.contains("--field");auto kind=o.get("--kind",field?"field":"full");
    if(field&&kind!="field")throw Error("E_OPTION","describe --field requires the field kind");
    print(discover(kind,o.get("--field"),NEX_VERSION,NEX_BUILD_ID));return 0;
  }
  if(o.command=="toolchain"){
    if(o.positional.empty())throw Error("E_OPTION","toolchain requires a configuration file");
    BuildOptions options;options.toolchain=o.positional[0];auto snapshot=inspectNativeToolchain(options);
    print(llvm::json::Object{{"schema","nex.toolchain-report/1"},{"ok",true},{"hash",snapshot.hash},{"target",snapshot.target},{"host_compatible",snapshot.hostCompatible},{"manifest",std::move(snapshot.manifest)},{"inputs",std::move(snapshot.inputs)}});return 0;
  }
  if(o.command=="inspect"||o.command=="inspect-private-task"){
    auto path=o.get("--manifest"),expression=o.get("--expression");if(path.empty()||expression.empty())throw Error("E_OPTION","inspect requires --manifest FILE and --expression TEXT");
    auto kind=o.get("--kind","value");if(kind!="plan"&&kind!="value"&&kind!="demand")throw Error("E_OPTION","inspect kind must be plan, demand or value");std::string frame;
    if(!o.positional.empty()){auto file=o.positional[0];if(!fs::is_regular_file(file)||fs::file_size(file)>1048576)throw Error("E_DEBUG_LIMIT","frame file exceeds 1 MiB or is missing");frame=readFile(file);}
    else {char buffer[4096];while(std::cin.read(buffer,sizeof(buffer))||std::cin.gcount()){if(frame.size()+std::cin.gcount()>1048576)throw Error("E_DEBUG_LIMIT","stdin frame exceeds 1 MiB");frame.append(buffer,std::cin.gcount());}}
    uint64_t steps=100000;auto raw=o.get("--steps");if(!raw.empty()){steps=0;for(char c:raw){if(c<'0'||c>'9'||steps>(1000000-unsigned(c-'0'))/10)throw Error("E_OPTION","expression step limit must be 1..1000000");steps=steps*10+unsigned(c-'0');}if(!steps||steps>1000000)throw Error("E_OPTION","expression step limit must be 1..1000000");}
    std::cout<<json(o.command=="inspect-private-task"?inspectSourceExceptionTaskExpressionPrototype(path,parseDebugFrame(frame),expression,kind=="plan",steps,kind=="demand"):inspectExpression(path,parseDebugFrame(frame),expression,kind=="plan",steps,kind=="demand"),false)<<'\n';return 0;
  }
  if(o.command=="contract"&&o.get("--kind")=="intent"){
    auto path=o.get("--contracts");if(path.empty()||!fs::is_regular_file(path)||fs::file_size(path)>1048576)throw Error("E_OPTION","intent requires a bounded --contracts JSON file");
    auto value=parseJSON(readFile(path));print(llvm::json::Object{{"schema","nex.verification-intent/1"},{"intent_hash",verificationIntentHash(value)}});return 0;
  }
  if(o.command=="foreign"){if(o.positional.empty())throw Error("E_OPTION","foreign requires a trusted host catalogue path");print(describeForeignCatalogue(inspectForeignCatalogue(o.positional[0])));return 0;}
  if(o.command=="task"){
    if(o.positional.empty())throw Error("E_OPTION","task requires a source, task or receipt path");auto path=fs::absolute(o.positional[0]);auto kind=o.get("--kind","check");
    // A receipt can live below an unrelated project's directory. Replaying it
    // must never discover or modify that ancestor's graph/history/build cache.
    auto root=kind=="replay"?path.parent_path():projectRoot(path.parent_path());
    TaskOptions options{root.string(),o.compiler,o.get("--revision"),o.get("--directory"),o.get("--task-hash"),{}, {},o.get("--foreign")};
    if(o.values.contains("--toolchains")){
      auto file=fs::absolute(o.get("--toolchains"));if(!fs::is_regular_file(file)||fs::file_size(file)>65536)throw Error("E_OPTION","toolchain catalog requires a JSON file of at most 64 KiB");
      auto map=parseJSON(readFile(file.string()));auto catalog=map.getAsObject();if(!catalog||catalog->empty()||catalog->size()>16)throw Error("E_OPTION","toolchain catalog must map 1..16 IDs to trusted configuration paths");
      for(const auto &[id,v]:*catalog){auto name=id.str();auto path=v.getAsString();if(name.empty()||name.size()>64||!std::all_of(name.begin(),name.end(),[](unsigned char c){return (c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')||c=='_'||c=='-';})||!path||path->empty()||path->size()>8192||path->contains('\0'))throw Error("E_OPTION","invalid toolchain catalog ID/path");
        fs::path manifest(path->str());if(manifest.is_relative())manifest=file.parent_path()/manifest;options.toolchains[name]=manifest.lexically_normal().string();}
    }
    if(!o.get("--candidates").empty()){auto file=o.get("--candidates");if(!fs::is_regular_file(file)||fs::file_size(file)>1048576)throw Error("E_OPTION","candidate map requires a bounded JSON file");auto map=parseJSON(readFile(file));auto object=map.getAsObject();if(!object||object->size()>8)throw Error("E_OPTION","candidate file must map program IDs to archived revisions");for(const auto &[id,v]:*object){auto revision=v.getAsString();if(!revision)throw Error("E_OPTION","candidate revision must be a string");options.candidates[id.str()]=revision->str();}}
    if(o.values.contains("--foreign")&&(options.foreign.empty()||(kind!="check"&&kind!="run"&&kind!="replay")))throw Error("E_OPTION","task --foreign requires a nonempty catalogue for check/run/replay");
    if(kind=="notices"){print(describeTaskPackageNotices(captureTaskPackageNotices(path.string(),root.string())));return 0;}
    if(kind=="init"){
      if(!o.get("--component").empty()){
        auto task=projectTaskTemplate(root.string(),path.string(),o.get("--component"),o.get("--configuration"));auto output=o.get("--output");
        if(output.empty())print(std::move(task));else{if(fs::exists(output))throw Error("E_EXISTS","task init requires a new output file");writeFile(output,json(task)+"\n");print(llvm::json::Object{{"ok",true},{"output",fs::absolute(output).string()},{"task_hash",hash(json(task,false))}});}return 0;
      }
      auto p=loadProgram(path.string(),root.string());Store store(root/".nex");store.save(p,"",false);auto result=taskTemplate(p,p.entryUnit);auto output=o.get("--output");
      if(output.empty())print(std::move(result));else {if(fs::exists(output))throw Error("E_EXISTS","task init requires a new output file");writeFile(output,json(result)+"\n");print(llvm::json::Object{{"ok",true},{"output",fs::absolute(output).string()},{"task_hash",hash(json(result,false))}});}return 0;
    }
    if(kind=="replay"){auto result=replayTask(path.string(),options);auto object=result.getAsObject();auto code=object->getInteger("signal");auto success=object->getBoolean("ok").value_or(false);print(std::move(result));return code?128+int(*code):success?0:1;}
    if(!fs::is_regular_file(path)||fs::file_size(path)>1048576)throw Error("E_TASK","missing or oversized task JSON");auto task=parseJSON(readFile(path));
    if(kind=="history"){auto object=task.getAsObject();if(!object)throw Error("E_TASK","task must be an object");Store store(root/".nex");print(store.taskHistory(required(*object,"id")));return 0;}
    if(kind!="check"&&kind!="run")throw Error("E_OPTION","task kind must be init, notices, check, run, replay or history");
    auto result=kind=="run"?runTask(task,options):checkTask(task,options);auto object=result.getAsObject();auto code=object->getInteger("signal");auto success=object->getBoolean("ok").value_or(false);print(std::move(result));return code?128+int(*code):success?0:1;
  }
  if(o.command=="token"){
    auto user=o.get("--user"),file=o.get("--auth");if(user.empty()||user.size()>256||user.find('\0')!=std::string::npos||file.empty())throw Error("E_OPTION","token requires --user USER and --auth FILE");
    try{nexrt::unicodeOffsets(user,false);}catch(const nexrt::DataError &){throw Error("E_AUTH","user identifier must be valid UTF-8");}
    llvm::json::Value value=llvm::json::Object{{"schema","nex.auth/1"},{"tokens",llvm::json::Array{}}};
    if(fs::exists(file)){
      auto decoded=nexrt::decodeJSON(readFile(file),nexrt::authenticationSchema);
      if(!nexrt::isSuccess(decoded))throw Error("E_AUTH","invalid authentication file");value=parseJSON(nexrt::representation(nexrt::unwrap(decoded)));
      if(value.getAsObject()->getString("schema")!="nex.auth/1")throw Error("E_AUTH","unsupported authentication file version");
    }
    auto entries=value.getAsObject()->getArray("tokens");if(entries->size()>=1024)throw Error("E_AUTH","authentication token limit reached");
    std::set<std::string> hashes;
    for(const auto &entry:*entries){
      auto object=entry.getAsObject();auto owner=object->getString("user")->str(),digest=object->getString("sha256")->str();
      if(owner.empty()||owner.size()>256||owner.find('\0')!=std::string::npos||digest.size()!=64||!std::all_of(digest.begin(),digest.end(),[](char c){return (c>='0'&&c<='9')||(c>='a'&&c<='f');})||!hashes.insert(digest).second)throw Error("E_AUTH","invalid or duplicate authentication entry");
    }
    std::array<uint8_t,32> random;if(auto error=llvm::getRandomBytes(random.data(),random.size()))throw Error("E_AUTH","secure token generation failed: "+error.message());
    auto hex=[](const auto &bytes){std::string out;for(auto byte:bytes){out+="0123456789abcdef"[byte>>4];out+="0123456789abcdef"[byte&15];}return out;};
    auto token="nex_"+hex(random);auto digest=llvm::SHA256::hash(llvm::ArrayRef<uint8_t>(reinterpret_cast<const uint8_t*>(token.data()),token.size()));
    entries->push_back(llvm::json::Object{{"user",user},{"sha256",hex(digest)}});
    auto output=fs::absolute(file);auto temporary=output;temporary+=".tmp."+hex(random).substr(0,16);
    writeFile(temporary.string(),json(value)+"\n");fs::permissions(temporary,fs::perms::owner_read|fs::perms::owner_write,fs::perm_options::replace);fs::rename(temporary,output);
    print(llvm::json::Object{{"ok",true},{"user",user},{"token",token},{"auth",output.string()}});return 0;
  }
  if(o.command=="guide") {
    const std::map<std::string,std::string> files={{"exception-module-debug","docs/source-exception-module-debug.md"},{"exception-module-profile","docs/source-exception-module-profile.md"},{"exception-module-http","docs/source-exception-module-http.md"},{"exception-instances","docs/source-exception-instances.md"},{"exception-frontiers","docs/source-exception-frontiers.md"},{"exception-modules","docs/source-exception-modules.md"},{"exception-http","docs/source-exception-http.md"},{"exception-host","docs/source-exception-host.md"},{"exception-task-watch","docs/source-exception-task-watch.md"},{"exception-task-lldb","docs/source-exception-task-lldb.md"},{"exception-task-debug","docs/source-exception-task-debug.md"},{"exception-task-control-profile","docs/source-exception-task-control-profile.md"},{"exception-native-tasks","docs/source-exception-native-tasks.md"},{"exception-task-ir","docs/source-exception-task-ir.md"},{"exception-lifetimes","docs/source-exception-lifetimes.md"},{"exception-tasks-prototype","docs/source-exception-tasks-prototype.md"},{"exception-prototype","docs/source-exceptions-prototype.md"},{"http-stream","docs/http-streams.md"},{"http-client","docs/http-client.md"},{"dns","docs/dns-provider.md"},{"tcp","docs/tcp-provider.md"},{"task-network-host","docs/task-network-transport.md"},{"task-file-streams","docs/task-file-streams.md"},{"task-file-stream-host","docs/task-file-stream-host.md"},{"task-write-providers","docs/task-write-providers.md"},{"task-write-migration","docs/task-write-migration.md"},{"task-file-writes","docs/task-file-writes-prototype.md"},{"task-file-write-host","docs/task-file-writes-host.md"},{"device","docs/device.md"},{"task-foreign-source","docs/task-foreign-prototype.md"},{"task-value-retirement","docs/task-value-retirement.md"},{"resource-regions","docs/resource-regions.md"},{"resource-executor","docs/resource-executor.md"},{"source-resources","docs/source-resources.md"},{"model","docs/models.md"},{"compute","docs/compute.md"},{"task-provider-debug","docs/task-provider-debugging.md"},{"task-provider-profile","docs/task-provider-profiling.md"},{"task-shared-providers","docs/task-shared-providers.md"},{"task-providers","docs/task-providers.md"},{"task-debug","docs/task-debugging.md"},{"task-file-reads","docs/task-file-reads.md"},{"task-external","docs/task-external.md"},{"task-limits","docs/task-limits.md"},{"task-migration","docs/task-migration.md"},{"task-lifetime","docs/task-lifetimes.md"},{"tasks-runtime","docs/tasks-runtime-design.md"},{"browser-worker","docs/browser-workers.md"},{"result","docs/error-propagation.md"},{"discovery","docs/discovery.md"},{"bootstrap","llm/BOOTSTRAP.md"},{"quality","docs/quality.md"},{"concurrency","docs/concurrency-design.md"},{"task-workload","docs/task-workloads.md"},{"server-workload","docs/server-workload.md"}, {"server-debug","docs/server-debugging.md"},{"project-task","docs/project-tasks.md"},{"project","docs/project-build.md"},{"lsp","docs/lsp.md"},{"windows","docs/windows.md"},{"wasm","docs/wasm.md"},{"core","docs/core-debugging.md"},{"prompt","llm/SYSTEM_PROMPT.md"},{"language","docs/language.md"},{"grammar","docs/grammar.ebnf"},{"protocol","docs/protocol.md"},{"web","docs/web.md"},{"server","docs/server.md"},{"api","docs/api.md"},{"debug","docs/debugging.md"},{"build","docs/incremental.md"},{"profile","docs/profiling.md"},{"verify","docs/verification.md"},{"task","docs/tasks.md"},{"expression","docs/expressions.md"},{"operation","docs/operations.md"},{"graph","docs/graph.md"},{"linux","docs/linux.md"},{"match","docs/matching.md"},{"function","docs/functions.md"},{"files","docs/files.md"},{"bytes","docs/bytes.md"},{"resources","docs/resources.md"},{"ffi","docs/ffi-design.md"},{"diagnostic","docs/native-diagnostics.md"},{"history","docs/history.md"},{"snapshot","docs/snapshots.md"},{"compatibility","docs/compatibility.md"},{"frontend","docs/frontend-diagnostics.md"},{"query","docs/queries.md"},{"string-debug","docs/string-debug.md"},{"trait","docs/traits.md"},{"editor","docs/editor.md"}};
    auto kind=o.get("--kind","prompt");
    if(!files.contains(kind))throw Error("E_OPTION","guide kind must be exception-prototype, http-stream, http-client, dns, tcp, task-network-host, task-file-streams, task-write-migration, task-file-writes, task-file-write-host, task-foreign-source, task-value-retirement, resource-regions, resource-executor, task-provider-debug, task-provider-profile, task-shared-providers, task-providers, task-debug, task-file-reads, task-external, task-limits, task-migration, task-lifetime, tasks-runtime, browser-worker, result, discovery, bootstrap, quality, concurrency, server-debug, task-workload, server-workload, project-task, prompt, language, grammar, protocol, web, server, api, debug, build, profile, verify, task, expression, operation, graph, linux, match, function, files, bytes, resources, ffi, diagnostic, history, snapshot, compatibility, frontend, query, string-debug, trait, editor, lsp, core, windows, project or wasm");
    auto text=readFile(resourceFile(files.at(kind)));
    if(o.has("--json"))print(llvm::json::Object{{"schema","nex.guide/1"},{"language",languageVersion},{"kind",kind},{"hash",hash(text)},{"text",text}});else std::cout<<text;return 0;
  }
  if(o.command=="doctor") {
    auto runtime=resourceFile("runtime/runtime.cpp");auto native=configureNative({});
    print(llvm::json::Object{{"schema","nex.doctor/1"},{"version",NEX_VERSION},{"language",languageVersion},{"llvm",LLVM_VERSION_STRING},{"host",llvm::sys::getDefaultTargetTriple()},{"cpu",llvm::sys::getHostCPUName().str()},{"native_compiler",native.compiler},{"wasm_linker",native.wasmLinker},{"native_archiver",native.archiver},{"native_debug_packager",native.debugPackager},{"native_linker",native.linker},{"sdk_manifest",native.sdkManifest},{"native_sqlite_include",native.sqliteInclude},{"native_sqlite_library",native.sqliteLibrary},{"native_openssl_include",native.opensslInclude},{"native_openssl_ssl",native.opensslSSL},{"native_openssl_crypto",native.opensslCrypto},{"runtime",runtime},{"runtime_available",fs::exists(runtime)},{"verifier","Z3"},{"verifier_version",verifierVersion()}});return 0;
  }
  if(o.command=="init") {
    fs::path root=fs::absolute(o.positional.empty()?".":o.positional[0]);
    if(fs::exists(root/"nex.json")||fs::exists(root/"src/main.nex"))throw Error("E_EXISTS","project already exists; refusing to overwrite");
    writeFile((root/"nex.json").string(),json(llvm::json::Object{{"schema","nex.project/1"},{"language",languageVersion},{"entry","src/main.nex"}})+"\n");
    writeFile((root/"src/main.nex").string(),
      "module app;\n\nfn sum(n: i64) -> i64 {\n  var total: i64 = 0;\n  var i: i64 = 1;\n  while i <= n {\n    total = total + i;\n    i = i + 1;\n  }\n  return total;\n}\n\nfn main() -> i64 !{io} {\n  print(sum(10));\n  return 0;\n}\n\ntest fn sum_test() -> unit {\n  assert(sum(10) == 55);\n  assert(sum(0) == 0);\n}\n");
    print(llvm::json::Object{{"ok",true},{"directory",root.string()}});return 0;
  }
  const std::set<std::string> commands={"check","eval","build","package","run","test","emit","graph","declarations","identities","operations","context","history","changes","restore","apply","import","export","debug","migrate","lock","web","api","profile","contract","verify","ffi","diagnose","search","subgraph"};
  if(!commands.contains(o.command))throw Error("E_COMMAND","unknown command '"+o.command+"'");
  if(o.has("--library")&&o.command!="build"&&o.command!="emit")throw Error("E_OPTION","--library is supported by native build/emit");
  if(o.has("--library")&&o.get("--target")=="web")throw Error("E_OPTION","--library is a native archive target; use emit --kind typescript for a web module");
  if(o.command=="debug"){
    auto kind=o.get("--kind","lldb");
    if(kind!="lldb"&&kind!="dap"&&kind!="nex-dap")throw Error("E_OPTION","debug kind must be lldb, dap or nex-dap");
    if(o.has("--library"))throw Error("E_OPTION","debug launches a native application or HTTP server; select a library frame within its application");
  }
  const std::set<std::string> sourceCommands={"check","eval","build","package","run","test","emit","debug","lock","web","api","profile","contract","verify","ffi","diagnose","declarations","identities"};
  auto root=projectRoot(sourceCommands.contains(o.command)&&!o.positional.empty()?fs::absolute(o.positional[0]).parent_path():fs::current_path());
  bool physical=sourceCommands.contains(o.command)&&o.get("--revision").empty()&&
    ((o.command!="declarations"&&o.command!="identities")||!o.positional.empty());
  if(physical)validateProjectMetadata(root.string());
  if(o.command=="migrate"){migrate(o,root);return 0;}
  if(physical&&fs::is_regular_file(root/".nex/graph.db")){
    Store retained(root/".nex",StoreOpenMode::ReadOnly);const auto previous=retained.headRevision();
    if(!previous.empty()&&retained.revisionLanguage(previous)!=languageVersion)
      throw Error("E_LANGUAGE_VERSION","graph HEAD uses another language version; run nex migrate explicitly");
  }
  Store store(root/".nex");
  if(o.command=="history"){print(store.history());return 0;}
  if(o.command=="changes"){
    auto count=[&](const std::string &key,unsigned fallback,unsigned maximum){if(!o.values.contains(key))return fallback;auto text=o.get(key);uint64_t value=0;if(text.empty())throw Error("E_OPTION","empty page option");for(char c:text){if(c<'0'||c>'9'||value>(maximum-unsigned(c-'0'))/10)throw Error("E_OPTION","invalid page option "+key);value=value*10+unsigned(c-'0');}return unsigned(value);};
    auto result=store.changes(count("--offset",0,10000000),count("--limit",100,1000));auto output=o.get("--output");
    if(output.empty())print(std::move(result));else{auto selected=result.getAsObject()->getString("head")->str();writeFile(output,json(result)+"\n");print(llvm::json::Object{{"ok",true},{"output",fs::absolute(output).string()},{"head",selected}});}return 0;
  }
  if(o.command=="restore"){
    auto target=o.get("--revision"),expected=o.get("--expected-revision"),previous=store.headRevision();
    if(previous!=(expected=="EMPTY"?"":expected))throw Error("E_CONFLICT","graph HEAD changed; read context and retry");
    if(store.revisionLanguage(target)!=languageVersion)throw Error("E_LANGUAGE_VERSION","restore requires a current-language revision; migrate older source explicitly");
    auto archived=store.bundle(target);auto candidate=loadBundle(archived,root.string());if(revision(candidate)!=target)throw Error("E_REVISION","stored source does not match the selected restore revision");
    auto request=llvm::json::Object{{"revision",target},{"expected_revision",expected}};
    auto rev=store.save(candidate,expected,true,changeInfo(o,"restore",hash(json(std::move(request),false))));
    print(llvm::json::Object{{"schema","nex.restore/1"},{"ok",true},{"previous_revision",previous},{"revision",rev},{"source_hash",hash(json(archived,false))},{"changed",previous!=rev},{"materialized",false}});return 0;
  }
  if(o.command=="export") {
    auto selected=o.get("--revision","HEAD");if(selected=="HEAD")selected=store.headRevision();
    auto bundle=store.bundle(selected);auto directory=o.get("--directory");
    if(!directory.empty()){
      llvm::json::Value lock=nullptr;auto language=store.revisionLanguage(selected);
      if(language==languageVersion){auto p=loadBundle(bundle,root.string());if(revision(p)!=selected)throw Error("E_REVISION","stored source snapshot is corrupt");lock=dependencyLock(p);}
      exportProject(bundle,directory,language);
      if(!lock.getAsNull())writeFile((fs::path(directory)/"nex.lock.json").string(),json(lock)+"\n");
      print(llvm::json::Object{{"ok",true},{"directory",fs::absolute(directory).string()},{"revision",selected}});return 0;
    }
    auto obj=bundle.getAsObject();auto files=obj?obj->getObject("files"):nullptr;
    if(!files||files->size()!=1)throw Error("E_EXPORT","multi-module projects require export --directory PATH");
    auto source=store.source(selected);auto output=o.get("--output");
    if(output.empty())std::cout<<source;else {writeFile(output,source);print(llvm::json::Object{{"ok",true},{"output",output}});}return 0;
  }
  if(o.command=="import") {
    if(o.positional.empty())throw Error("E_OPTION","import requires a graph JSON file");
    auto value=parseJSON(readFile(o.positional[0]));auto obj=value.getAsObject();
    if(!obj||(required(*obj,"schema")!="nex.graph/1"&&required(*obj,"schema")!="nex.graph/2"))throw Error("E_SCHEMA","expected an exported NEX graph");
    if(required(*obj,"language")!=languageVersion)throw Error("E_LANGUAGE_VERSION","graph uses another language version; use nex migrate GRAPH.json to recheck its source");
    if(required(*obj,"schema")!="nex.graph/2"||!obj->get("bundle"))throw Error("E_SCHEMA","current graphs require nex.graph/2 and a source bundle");
    auto p=loadBundle(*obj->get("bundle"),root.string());
    if(required(*obj,"source")!=p.source)throw Error("E_BUNDLE","root source and source bundle disagree");
    if(revision(p)!=required(*obj,"revision"))throw Error("E_REVISION","graph revision does not match checked source");
    auto rev=store.save(p,"",true,changeInfo(o,"import",hash(json(value,false))));print(llvm::json::Object{{"ok",true},{"revision",rev}});return 0;
  }
  if(o.command=="apply") {
    auto patchFile=o.get("--patch");if(patchFile.empty())throw Error("E_OPTION","apply requires --patch FILE");
    auto value=readPatch(patchFile);auto obj=value.getAsObject();if(!obj)throw Error("E_JSON","patch must be an object");
    auto fields=[](const llvm::json::Object &object,const std::set<std::string> &allowed){for(const auto &[key,value]:object){(void)value;if(!allowed.contains(key.str()))throw Error("E_JSON","unknown patch field '"+key.str()+"'");}};
    fields(*obj,{"expected_revision","expected_source_hash","replacements"});
    auto expected=required(*obj,"expected_revision");if(expected.size()!=64||expected.find_first_not_of("0123456789abcdef")!=std::string::npos)throw Error("E_JSON","expected_revision must be a lowercase 64-character digest");
    auto replacements=obj->getArray("replacements");if(!replacements||replacements->empty())throw Error("E_JSON","replacements must be a nonempty array");
    if(replacements->size()>1000)throw Error("E_PATCH_LIMIT","patch exceeds 1000 replacements");
    std::string expectedSource;if(auto value=obj->get("expected_source_hash")){auto digest=value->getAsString();if(!digest||digest->size()!=64||digest->find_first_not_of("0123456789abcdef")!=llvm::StringRef::npos)throw Error("E_JSON","expected_source_hash must be a lowercase 64-character digest");expectedSource=digest->str();}

    auto selected=store.headRevision();
    if(selected!=expected)throw Error("E_CONFLICT","graph HEAD changed; read context and retry");
    if(store.revisionLanguage(selected)!=languageVersion)throw Error("E_LANGUAGE_VERSION","run nex migrate before applying patches to an older graph");
    auto p=loadBundle(store.bundle(selected),root.string());
    if(revision(p)!=selected)throw Error("E_REVISION","stored source snapshot is corrupt");
    auto selectedSource=hash(json(sourceBundle(p),false));if(!expectedSource.empty()&&expectedSource!=selectedSource)throw Error("E_SOURCE_CONFLICT","exact archived source changed; request operation context for the selected revision");
    struct Replacement{size_t begin,end;std::string source;};
    std::map<std::string,std::vector<Replacement>> edits;std::set<std::string> names;
    for(const auto &item:*replacements){
      auto entry=item.getAsObject();if(!entry)throw Error("E_JSON","replacement must be an object");
      bool operation=entry->get("operation_id")||entry->getString("kind")=="operation";
      if(operation){
        fields(*entry,{"operation_id","source","kind"});
        if(auto kind=entry->get("kind");kind&&kind->getAsString()!="operation")throw Error("E_JSON","operation replacement kind must be operation");
        auto id=required(*entry,"operation_id"),source=required(*entry,"source");
        if(id.size()!=32||id.find_first_not_of("0123456789abcdef")!=std::string::npos)throw Error("E_JSON","operation_id must be a lowercase local 32-character ID");
        if(expectedSource.empty())throw Error("E_PATCH_SOURCE","operation replacement requires expected_source_hash from exact archived context");
        if(!names.insert("operation:"+id).second)throw Error("E_JSON","duplicate operation replacement");
        auto context=store.operations(p,"",id,0,1,true);const auto &node=*(*context.getAsObject()->getArray("nodes"))[0].getAsObject();
        const auto &function=p.function(node.getString("function")->str());
        if(!function.templateName.empty())throw Error("E_PATCH_SPECIALIZATION","replace source operations of template '"+function.templateName+"'; specializations are derived",function.span);
        if(function.traitSignature)throw Error("E_PATCH_TRAIT","replace the source trait declaration",function.span);
        if(function.closure)throw Error("E_PATCH_CLOSURE","replace source operations of owner '"+function.closureOwner+"'; closures are derived",function.span);
        auto range=node.getObject("source_range");if(!range||range->getBoolean("editable")!=true)throw Error("E_PATCH_TARGET","selected operation has no editable source interval");
        auto kind=range->getString("kind");std::string fragment;
        try{
          if(kind=="expression"){fragment="(\n"+source+"\n)";parseExpression(fragment,"<operation-patch>",100000);}
          else if(kind=="statement"){parseStatement(source,"<operation-patch>",100000);fragment="\n"+source+"\n";}
          else if(kind=="pattern"){parsePattern(source,"<operation-patch>",100000);fragment="\n"+source+"\n";}
          else throw Error("E_PATCH_TARGET","operation source kind is not replaceable");
        }catch(const Error &error){if(error.code=="E_DEBUG_LIMIT"){Error translated("E_PATCH_LIMIT","operation fragment exceeds 100000 tokens",error.span);translated.frontend=error.frontend;throw translated;}throw;}
        edits[function.unit].push_back({size_t(*range->getInteger("byte_begin")),size_t(*range->getInteger("byte_end")),std::move(fragment)});
        continue;
      }
      fields(*entry,{"name","source","kind"});
      auto name=required(*entry,"name"),source=required(*entry,"source");
      std::string requestedKind;if(auto value=entry->get("kind")){auto label=value->getAsString();if(!label||(label!="function"&&label!="endpoint"&&label!="type"&&label!="trait"&&label!="impl"))throw Error("E_JSON","replacement kind must be function, endpoint, type, trait or impl");requestedKind=label->str();}
      const Trait *trait=nullptr;for(const auto &candidate:p.traits)if(candidate.name==name||(candidate.owner==p.module&&candidate.localName==name))trait=&candidate;
      const Implementation *implementation=nullptr;for(const auto &candidate:p.implementations)if(candidate.name==name||(candidate.owner==p.module&&candidate.localName==name))implementation=&candidate;
      const Endpoint *endpoint=nullptr;for(const auto &candidate:p.endpoints)if(candidate.name==name||(candidate.owner==p.module&&candidate.localName==name))endpoint=&candidate;
      const Structure *type=!endpoint&&p.hasStructure(name)?&p.structure(name):nullptr;
      const Function *function=!trait&&!implementation&&!endpoint&&!type?&p.function(name):nullptr;
      auto kind=trait?"trait":implementation?"impl":endpoint?"endpoint":type?"type":"function";
      if(!requestedKind.empty()&&requestedKind!=kind)throw Error("E_PATCH_TARGET","replacement kind differs from the checked declaration");
      auto symbol=trait?trait->name:implementation?implementation->name:endpoint?endpoint->name:type?type->name:function->name;
      if(!names.insert(symbol).second)throw Error("E_JSON","duplicate replacement");
      if(type&&!type->templateName.empty())throw Error("E_PATCH_SPECIALIZATION","replace the source template '"+type->templateName+"'; specializations are derived",type->span);
      if(function&&function->traitSignature)throw Error("E_PATCH_TRAIT","replace source trait '"+function->traitOwner+"'",function->span);
      auto fragment=parse("module fragment;\n"+source,"<patch>");
      if(fragment.functions.size()+fragment.structures.size()+fragment.endpoints.size()+fragment.traits.size()+fragment.implementations.size()!=1||!fragment.imports.empty())throw Error("E_PATCH","replacement must define exactly one existing declaration");
      if(trait){if(fragment.traits.size()!=1||fragment.traits[0].name!=trait->localName)throw Error("E_PATCH","replacement must define the named source trait");edits[trait->unit].push_back({trait->span.begin,trait->span.end,source+"\n"});}
      else if(implementation){if(fragment.implementations.size()!=1||fragment.implementations[0].name!=implementation->localName)throw Error("E_PATCH","replacement must define the named source implementation");edits[implementation->unit].push_back({implementation->span.begin,implementation->span.end,source+"\n"});}
      else if(endpoint){
        if(fragment.endpoints.size()!=1||fragment.endpoints[0].name!=endpoint->localName||!fragment.functions.empty()||!fragment.structures.empty()||!fragment.imports.empty())throw Error("E_PATCH","replacement must define exactly the named local endpoint");
        edits[endpoint->unit].push_back({endpoint->span.begin,endpoint->span.end,source+"\n"});
      }else if(type){
        if(fragment.structures.size()!=1||fragment.structures[0].name!=type->localName||!fragment.functions.empty()||!fragment.endpoints.empty()||!fragment.imports.empty())throw Error("E_PATCH","replacement must define exactly the named local structure, enum or resource");
        edits[type->unit].push_back({type->span.begin,type->span.end,source+"\n"});
      }else{
        const auto &f=*function;
        if(!f.templateName.empty())throw Error("E_PATCH_SPECIALIZATION","replace the source template '"+f.templateName+"'; specializations are derived",f.span);
        if(f.closure)throw Error("E_PATCH_CLOSURE","replace the source owner '"+f.closureOwner+"'; closures are derived",f.span);
        if(fragment.functions.size()!=1||fragment.functions[0].name!=f.localName||!fragment.structures.empty()||!fragment.imports.empty()||!fragment.endpoints.empty())throw Error("E_PATCH","replacement must define exactly the named local function");
        edits[f.unit].push_back({f.span.begin,f.span.end,source+"\n"});
      }
    }
    auto bundle=sourceBundle(p);auto files=bundle.getAsObject()->getObject("files");
    for(auto &[key,changes]:edits){
      std::sort(changes.begin(),changes.end(),[](const auto &a,const auto &b){return a.begin>b.begin;});
      auto source=p.units.at(key).source;size_t previous=source.size();
      for(const auto &e:changes){if(e.begin>e.end||e.end>source.size()||e.end>previous)throw Error("E_PATCH_OVERLAP","replacement intervals overlap or exceed the source snapshot");previous=e.begin;}
      for(const auto &e:changes)source.replace(e.begin,e.end-e.begin,e.source);(*files)[key]=source;
    }
    auto candidate=loadBundle(bundle,root.string());auto rev=store.save(candidate,expected,true,changeInfo(o,"apply",hash(json(value,false))));
    print(llvm::json::Object{{"schema","nex.patch-result/1"},{"ok",true},{"revision",rev},{"materialized",false},{"next","build --revision HEAD; export to materialize the source snapshot"}});return 0;
  }
  bool saved=graphQuery||o.command=="graph"||o.command=="context"||o.command=="operations"||((o.command=="declarations"||o.command=="identities")&&o.positional.empty());auto p=load(o,root,store,saved);
  if(graphQuery){
    auto result=o.command=="search"?store.search(p,queryOptions):store.subgraph(p,queryOptions);auto output=o.get("--output");
    if(output.empty())print(std::move(result));else{auto object=result.getAsObject();auto selected=object->getString("revision")->str(),queryHash=object->getString("query_hash")->str();writeFile(output,json(result)+"\n");print(llvm::json::Object{{"ok",true},{"output",fs::absolute(output).string()},{"revision",selected},{"query_hash",queryHash}});}return 0;
  }
  if(o.command=="declarations"||o.command=="identities"){
    auto count=[&](const std::string &option,unsigned fallback,unsigned maximum){auto text=o.get(option);if(text.empty())return fallback;uint64_t value=0;for(char c:text){if(c<'0'||c>'9'||value>(maximum-unsigned(c-'0'))/10)throw Error("E_OPTION","invalid range for "+option);value=value*10+unsigned(c-'0');}return unsigned(value);};
    auto kind=o.get("--kind","export");llvm::json::Value result=nullptr;
    if(o.command=="declarations"||kind=="export"){
      auto offset=count("--offset",0,10000000),limit=count("--limit",100,1000);if(!limit)throw Error("E_OPTION","graph page limit must be 1..1000");
      if(o.command=="declarations"){auto entity=o.get("--entity");if(!entity.empty()&&entity!="module"&&entity!="type"&&entity!="trait"&&entity!="impl")throw Error("E_OPTION","declarations entity must be module or type");result=store.declarations(p,entity,o.get("--symbol"),offset,limit);}
      else result=store.identities(p,o.get("--entity","all"),o.get("--symbol"),offset,limit);
    }else if(kind=="reconcile"){
      result=store.reconcileIdentities(p,readIdentityManifest(o.get("--manifest")),o.get("--expected-revision"));
    }else result=store.resolveIdentity(p,o.get("--origin"),o.get("--from-revision"),o.get("--node"));
    auto output=o.get("--output");if(output.empty())print(std::move(result));else {writeFile(output,json(result)+"\n");print(llvm::json::Object{{"ok",true},{"output",fs::absolute(output).string()},{"revision",revision(p)}});}return 0;
  }
  if(o.command=="contract"){
    if(o.get("--symbol").empty())throw Error("E_OPTION","contract requires --symbol NAME");
    auto value=contractTemplate(p,o.get("--symbol"));auto output=o.get("--output");
    if(output.empty())print(std::move(value));else {writeFile(output,json(value)+"\n");print(llvm::json::Object{{"ok",true},{"output",fs::absolute(output).string()},{"revision",revision(p)}});}return 0;
  }
  if(o.command=="verify"){
    auto file=o.get("--contracts");if(file.empty())throw Error("E_OPTION","verify requires --contracts FILE");
    if(!fs::is_regular_file(file))throw Error("E_FILE","contract file does not exist: "+file);
    if(fs::file_size(file)>1048576)throw Error("E_CONTRACT","contract file exceeds 1 MiB");
    if(!o.get("--target").empty()||!o.get("--profile").empty())throw Error("E_OPTION","verification checks source semantics, without a target/profile selection");
    auto number=[&](const std::string &key,unsigned fallback,unsigned minimum,unsigned maximum){auto text=o.get(key);if(text.empty())return fallback;uint64_t value=0;for(char c:text){if(c<'0'||c>'9'||value>(maximum-unsigned(c-'0'))/10)throw Error("E_OPTION","invalid range for "+key);value=value*10+unsigned(c-'0');}if(value<minimum||value>maximum)throw Error("E_OPTION","invalid range for "+key);return unsigned(value);};
    VerificationOptions options{o.get("--symbol"),o.get("--directory",(root/".nex/verify").string()),number("--solver-timeout",2000,1,60000),number("--resource-limit",1000000,1,100000000),number("--timeout",30,1,300)};
    auto result=verifyContracts(p,parseJSON(readFile(file)),store.graph(p),options);auto ok=*result.getAsObject()->getBoolean("ok");
    if(o.has("--json"))print(std::move(result));else std::cout<<(ok?"Proven: ":"Not proven: ")<<result.getAsObject()->getString("output")->str()<<'\n';return ok?0:1;
  }
  if(o.command=="lock"){
    auto output=o.get("--output",(root/"nex.lock.json").string());auto lock=dependencyLock(p);
    if(fs::is_regular_file(output)){
      auto old=parseJSON(readFile(output));auto previous=old.getAsObject();
      if(previous&&previous->getString("schema")=="nex.lock/1"&&previous->getString("language")==languageVersion){
        auto entries=previous->getObject("dependencies");auto current=lock.getAsObject()->getObject("dependencies");
        if(entries)for(const auto &[key,value]:*entries)if(!current->get(key))(*current)[key]=value;
      }
    }
    writeFile(output,json(lock)+"\n");print(llvm::json::Object{{"ok",true},{"output",fs::absolute(output).string()},{"lock",std::move(lock)}});return 0;
  }
  if(o.command=="graph"){auto text=json(store.graph(p))+"\n";auto output=o.get("--output");if(output.empty())std::cout<<text;else writeFile(output,text);return 0;}
  if(o.command=="operations"||(o.command=="context"&&(!o.get("--operation").empty()||!o.get("--site").empty()))){
    auto selector=o.get("--operation",o.get("--site")),symbol=o.get("--symbol");
    if(!o.get("--operation").empty()&&!o.get("--site").empty())throw Error("E_OPTION","select one operation ID or site");
    if(selector.empty()&&symbol.empty())throw Error("E_OPTION","operations requires --symbol NAME, --operation ID or --site KEY");
    auto number=[&](const std::string &option,unsigned fallback,unsigned maximum){auto text=o.get(option);if(text.empty())return fallback;uint64_t n=0;for(char c:text){if(c<'0'||c>'9'||n>(maximum-unsigned(c-'0'))/10)throw Error("E_OPTION","invalid range for "+option);n=n*10+unsigned(c-'0');}if(n>maximum)throw Error("E_OPTION","invalid range for "+option);return unsigned(n);};
    auto offset=number("--offset",0,10000000),limit=number("--limit",100,1000);if(!limit)throw Error("E_OPTION","operation page limit must be 1..1000");
    print(store.operations(p,symbol,selector,offset,limit,o.command=="context"));return 0;
  }
  if(o.command=="context") {
    auto name=o.get("--symbol");if(name.empty())throw Error("E_OPTION","context requires --symbol NAME");
    auto entity=o.get("--entity");
    if(entity=="module"||entity=="type"||entity=="trait"||entity=="impl"){
      auto value=store.declarations(p,entity,name,0,1);auto object=value.getAsObject();auto nodes=object->getArray("nodes");if(nodes->empty())throw Error("E_IDENTITY_SYMBOL","declaration is not in the selected graph");
      print(llvm::json::Object{{"schema","nex.declaration-context/1"},{"language",languageVersion},{"revision",revision(p)},{"namespace",object->getString("namespace")->str()},{"node",(*nodes)[0]}});return 0;
    }
    if(!entity.empty()&&entity!="function"&&entity!="endpoint")throw Error("E_OPTION","context entity must be module, type, function or endpoint");
    for(const auto &endpoint:p.endpoints)if(entity!="function"&&(endpoint.name==name||(endpoint.owner==p.module&&endpoint.localName==name))){
      const auto &handler=p.function(endpoint.target);auto descriptor=describeAPI(p);llvm::json::Value contract=nullptr;
      for(const auto &item:*descriptor.getAsObject()->getArray("endpoints"))if(item.getAsObject()->getString("name")==endpoint.name)contract=item;
      llvm::json::Array structures;std::set<std::string> seen;
      std::function<void(const Type&)> include=[&](const Type &t){if(t.element)include(*t.element);if(t.kind==Type::Function)for(const auto &argument:t.arguments)include(argument);if(t.kind==Type::Record&&seen.insert(t.name).second){const auto &s=p.structure(t.name);structures.push_back(llvm::json::Object{{"name",s.name},{"source",p.definition(s)},{"file",s.unit}});for(const auto &argument:s.typeArguments)include(argument);for(auto field:s.members())include(field->type);}};
      for(const auto &param:handler.params)include(param.type);include(handler.result);
      llvm::json::Array imports;for(const auto &dependency:p.units.at(endpoint.unit).imports)imports.push_back(llvm::json::Object{{"alias",dependency.alias},{"file",dependency.target},{"module",p.units.at(dependency.target).module}});
      print(llvm::json::Object{{"schema","nex.context/2"},{"kind","endpoint"},{"language",languageVersion},{"revision",revision(p)},{"symbol",endpoint.name},{"local_name",endpoint.localName},{"module",endpoint.owner},{"file",endpoint.unit},{"source",p.definition(endpoint)},{"definition",canonical(endpoint)},{"contract",std::move(contract)},{"imports",std::move(imports)},{"handler",llvm::json::Object{{"name",handler.name},{"source",p.definition(handler)},{"file",handler.unit}}},{"structures",std::move(structures)}});return 0;
    }
    if(entity=="endpoint")throw Error("E_IDENTITY_SYMBOL","endpoint is not in the selected graph");
    const auto &f=p.function(name);llvm::json::Array callees,callers;
    for(const auto &d:f.dependencies){const auto &fn=p.function(d);callees.push_back(llvm::json::Object{{"name",fn.name},{"source",p.definition(fn)},{"module",fn.owner},{"file",fn.unit}});}
    for(const auto &fn:p.functions)if(fn.dependencies.contains(f.name))callers.push_back(fn.name);
    for(const auto &endpoint:p.endpoints)if(endpoint.target==f.name)callers.push_back(endpoint.name);
    std::set<std::string> needed;
    std::function<void(const Type&)> visitType=[&](const Type &t){if(t.element)visitType(*t.element);if(t.kind==Type::Function)for(const auto &argument:t.arguments)visitType(argument);if(t.kind==Type::Record&&needed.insert(t.name).second){const auto &s=p.structure(t.name);for(const auto &argument:s.typeArguments)visitType(argument);for(auto field:s.members())visitType(field->type);}};
    std::function<void(E)> visitExpr=[&](E e){if(e){visitType(e->type);for(auto a:e->args)visitExpr(a);}};
    std::function<void(const std::vector<S>&)> visitBlock=[&](const auto &body){for(auto s:body){visitType(s->type);visitExpr(s->expr);childBlocks(s,visitBlock);}};
    auto visitFunction=[&](const Function &fn){visitType(fn.result);for(const auto &param:fn.params)visitType(param.type);for(const auto &capture:fn.captures)visitType(capture.type);visitBlock(fn.body);};
    visitFunction(f);for(const auto &dependency:f.dependencies)visitFunction(p.function(dependency));
    llvm::json::Array structures;for(const auto &s:p.structures)if(needed.contains(s.name))structures.push_back(llvm::json::Object{{"name",s.name},{"source",p.definition(s)},{"module",s.owner},{"file",s.unit},{"definition",canonical(s)}});
    llvm::json::Array imports;for(const auto &dependency:p.units.at(f.unit).imports)imports.push_back(llvm::json::Object{{"alias",dependency.alias},{"module",p.units.at(dependency.target).module},{"file",dependency.target}});
    llvm::json::Array parameters,arguments;for(const auto &parameter:f.typeParameters)parameters.push_back(parameter);for(const auto &argument:f.typeArguments)arguments.push_back(typeName(argument));
    llvm::json::Array captures;for(const auto &capture:f.captures)captures.push_back(llvm::json::Object{{"name",capture.name},{"type",typeName(capture.type)}});
    print(llvm::json::Object{{"schema","nex.context/2"},{"language",languageVersion},{"revision",revision(p)},{"symbol",f.name},{"local_name",f.localName},{"module",f.owner},{"file",f.unit},{"native_symbol",nativeSymbol(f.name)},{"source",p.definition(f)},{"type_parameters",std::move(parameters)},{"type_bounds",canonicalBounds(f.typeParameters,f.typeBounds)},{"template",f.templateName},{"type_arguments",std::move(arguments)},{"editable",f.templateName.empty()&&!f.closure&&!f.traitSignature},{"closure_owner",f.closureOwner},{"captures",std::move(captures)},{"foreign",f.foreign?llvm::json::Value(llvm::json::Object{{"library",f.foreign->library},{"export",f.foreign->symbol},{"manifest_sha256",f.foreign->manifest}}):llvm::json::Value(nullptr)},{"imports",std::move(imports)},{"callees",std::move(callees)},{"callers",std::move(callers)},{"structures",std::move(structures)}});return 0;
  }
  if(o.command=="diagnose"){
    if(o.get("--manifest").empty()||o.get("--log").empty())throw Error("E_OPTION","diagnose requires --manifest and --log");
    auto manifest=parseNativeManifest(readBoundedText(o.get("--manifest"),64*1048576,"native manifest","E_DIAGNOSTIC_LIMIT"));
    auto log=readBoundedText(o.get("--log"),4*1048576,"native diagnostic log","E_DIAGNOSTIC_LIMIT");
    print(nativeDiagnostics(p,manifest,store,log));return 0;
  }
  if(o.command=="ffi"){auto symbol=o.get("--symbol");if(symbol.empty())throw Error("E_OPTION","ffi requires --symbol for a concrete named function");print(foreignSignature(p,p.function(symbol)));return 0;}
  if(o.command=="check"){if(o.has("--json"))print(llvm::json::Object{{"ok",true},{"revision",revision(p)},{"functions",int64_t(p.functions.size())}});else std::cout<<"Checked "<<p.functions.size()<<" functions; revision "<<revision(p)<<'\n';return 0;}
  if(o.command=="api"){auto directory=o.get("--directory");print(directory.empty()?describeAPI(p):generateAPI(p,directory));return 0;}
  if(o.command=="web"){
    auto directory=o.get("--directory",o.get("--output"));if(directory.empty())throw Error("E_OPTION","web generation requires --directory PATH");
    print(generateWebApp(p,directory));return 0;
  }
  if(o.command=="build"&&o.get("--target")=="web"){
    auto output=o.get("--output");
    if(!output.empty()&&fs::exists(output)&&(!fs::is_directory(output)||!fs::is_empty(output)))throw Error("E_EXISTS","web build output requires a new or empty directory");
    auto result=buildWebApp(p,o.get("--build-directory",(root/".nex/build").string()),o.get("--profile","debug"));
    if(!output.empty()){
      auto dist=result.getAsObject()->getString("dist")->str();fs::create_directories(output);
      fs::copy(dist,output,fs::copy_options::recursive|fs::copy_options::overwrite_existing);(*result.getAsObject())["dist"]=fs::absolute(output).string();
    }
    if(o.has("--json"))print(std::move(result));else std::cout<<"Web assets: "<<result.getAsObject()->getString("dist")->str()<<'\n';return 0;
  }
  if(o.command=="build"&&o.get("--target")=="wasm"){
    auto result=buildWasm(p,o.get("--build-directory",(root/".nex/build").string()),
                          o.get("--entry","main"),o.get("--profile","debug"),o.get("--output"));
    if(o.has("--json"))print(std::move(result));else std::cout<<"Wasm module: "<<result.getAsObject()->getString("module")->str()<<'\n';return 0;
  }
  if(o.command=="eval") {
    std::shared_ptr<nexrt::ForeignLibraries> libraries;
    std::unique_ptr<nexrt::ForeignScope> foreign;
    if(!o.get("--foreign").empty()){libraries=foreignLibraries(o.get("--foreign"));foreign=std::make_unique<nexrt::ForeignScope>(libraries);}
    uint64_t limit=1000000;
    if(!o.get("--steps").empty()){try{size_t used;auto raw=o.get("--steps");limit=std::stoull(raw,&used);if(used!=raw.size()||raw.starts_with("-"))throw std::invalid_argument("steps");}catch(...){throw Error("E_OPTION","--steps requires a nonnegative integer");}}
    auto entry=o.get("--entry","main");bool taskEntry=usesTaskEffects(p,entry);
    if(taskLimitsSpecified&&!taskEntry)throw Error("E_OPTION","task limits require an entry with the task effect");
    if(taskLimitsSpecified)limit=taskLimits.steps;
    Evaluation result;
    try{result=evaluate(p,entry,limit,taskLimitsSpecified?&taskLimits:nullptr);}catch(Error &error){
      if(!error.operationSite.empty()){auto mapped=store.operations(p,"",error.operationSite,0,1);error.operationId=(*mapped.getAsObject()->getArray("nodes"))[0].getAsObject()->getString("id")->str();}throw;
    }
    foreign.reset();
    const auto foreignCapacity=libraries?libraries->resourceBytesUsed():0;
    const bool hadForeign=bool(libraries);libraries.reset();
    if(o.has("--json")){
      llvm::json::Object response{{"ok",true},{"value",result.value},{"stdout",result.output},{"steps",int64_t(result.steps)}};
      if(hadForeign)response["foreign_resource_bytes_after_scope"]=int64_t(foreignCapacity);
      if(taskEntry){auto configured=taskLimits;configured.steps=limit;response["task_execution"]=taskExecutionJSON(configured,configured,"reference");}
      print(std::move(response));
    }else std::cout<<result.output;return 0;
  }
  if(o.command=="emit"&&o.get("--kind")=="typescript"){
    auto module=emitTypeScript(p,{{"entry",o.get("--entry","main")}});auto directory=o.get("--directory"),output=o.get("--output");
    if(!directory.empty()){writeWebModule(module,directory);print(llvm::json::Object{{"ok",true},{"directory",fs::absolute(directory).string()},{"revision",revision(p)}});}
    else if(output.empty())std::cout<<module.source;else writeFile(output,module.source);return 0;
  }
  if(o.get("--target")=="server"&&o.command=="test")throw Error("E_OPTION","use native test for server functions; --target server builds the HTTP entry");
  if(o.get("--target")=="server"&&o.command=="run"&&o.has("--json"))throw Error("E_OPTION","server is long-running; use build --json or run without --json");
  std::vector<std::string> foreignArguments;if(!o.get("--foreign").empty()){foreignArguments={o.get("--target")=="server"?"--foreign":"--nex-foreign",fs::absolute(o.get("--foreign")).string()};}
  auto executionArguments=[&](const std::string &executable){std::vector<std::string> result{executable};result.insert(result.end(),foreignArguments.begin(),foreignArguments.end());return result;};
  BuildOptions buildOptions{o.get("--profile",o.command=="package"?"release":"debug"),o.get("--target"),o.get("--entry",o.get("--target")=="server"?"handle":"main"),false,o.has("--library"),o.get("--toolchain")};
  buildOptions.taskLimits=taskLimits;buildOptions.taskLimitsSpecified=taskLimitsSpecified;
  if(o.command=="debug"&&taskLimitsSpecified&&!usesTaskEffects(p,buildOptions.entry))throw Error("E_OPTION","task limits require an entry with the task effect",p.function(buildOptions.entry).span);
  auto supervisorTimeout=[&](const nexrt::TaskExecutionLimits &limits){
    if(o.values.contains("--timeout")){
      auto value=nexrt::parseTaskLimitDecimal(o.get("--timeout"),3600);if(!value)throw Error("E_OPTION","--timeout requires 1..3600 seconds");return unsigned(*value);
    }
    return std::max(30u,unsigned((limits.timeoutMs+999)/1000+5));
  };
  if((o.command=="run"||o.command=="test"||o.command=="debug"||o.command=="profile")&&o.get("--target")!="web"&&!o.has("--interpreter-only"))requireNativeHost(buildOptions);
  ProfileOptions profiling;
  if(o.command=="profile"){
    if(buildOptions.libraryEntry||!o.extra.empty()||!o.get("--kind").empty()||buildOptions.target=="web"||buildOptions.target=="server")throw Error("E_OPTION","profile runs a host-native application; use a profile build with Tracy for a server/library");
    if(o.get("--profile","profile")!="profile")throw Error("E_OPTION","profile requires the instrumented profile build mode");
    auto count=[&](const std::string &key,unsigned fallback,unsigned minimum,unsigned maximum){
      auto text=o.get(key);if(text.empty())return fallback;uint64_t number=0;
      for(char c:text){if(c<'0'||c>'9'||number>(maximum-unsigned(c-'0'))/10)throw Error("E_OPTION",key+" is outside its supported integer range");number=number*10+unsigned(c-'0');}
      if(number<minimum||number>maximum)throw Error("E_OPTION",key+" is outside its supported integer range");return unsigned(number);
    };
    profiling={o.get("--output"),o.get("--scenario"),count("--events",100000,0,1000000),count("--timeout",30,1,3600),foreignArguments};
    if(usesTaskEffects(p,buildOptions.entry))profiling.timeout=supervisorTimeout(taskLimits);
    buildOptions.profile="profile";
  }
  if(o.command=="debug"&&usesTaskEffects(p,buildOptions.entry)){
    if(buildOptions.profile!="debug"||buildOptions.target=="server"||buildOptions.libraryEntry||!o.get("--foreign").empty())throw Error("E_TASK_DEBUG","task debug requires a standalone native debug executable; server/provider/profile task debugging is pending",p.function(buildOptions.entry).span);
    if(o.get("--kind","lldb")=="dap")throw Error("E_TASK_DEBUG","logical source task debugging requires lldb or nex-dap; raw DAP is pending",p.function(buildOptions.entry).span);
    buildOptions.taskDebug=true;
  }
  auto directory=fs::absolute(o.get("--build-directory",(root/".nex/build").string())).string();
  if(o.command=="debug")directory=nativeDebugBuildDirectory(directory);
  if(o.command=="test") {
    std::unique_ptr<nexrt::ForeignScope> foreign;if(!o.get("--foreign").empty())foreign=std::make_unique<nexrt::ForeignScope>(foreignLibraries(o.get("--foreign")));
    int count=0;llvm::json::Array tests;
    auto selected=o.get("--symbol");if(!selected.empty()){const auto &f=p.function(selected);if(!f.test)throw Error("E_TEST","--symbol must select a test function");selected=f.name;}
    if(taskLimitsSpecified)for(const auto &f:p.functions)if(f.test&&(selected.empty()||selected==f.name)&&!usesTaskEffects(p,f.name))
      throw Error("E_OPTION","select a task test with --symbol when specifying task limits",f.span);
    for(const auto &f:p.functions)if(f.test&&(selected.empty()||selected==f.name)){
      bool web=o.get("--target")=="web";
      if(web&&f.realm=="server"){tests.push_back(llvm::json::Object{{"name",f.name},{"skipped",true},{"reason","server test excluded from web target"}});continue;}
      bool taskTest=usesTaskEffects(p,f.name);
      if(taskLimitsSpecified&&!taskTest)throw Error("E_OPTION","select a task test with --symbol when specifying task limits",f.span);
      auto expected=evaluate(p,f.name,taskLimits.steps,taskTest?&taskLimits:nullptr);bool native=!o.has("--interpreter-only");
      if(native){
        ProcessResult actual;
        if(web){
          auto module=emitTypeScript(p,{{"entry",f.name}});auto runtimeInputs=readFile(resourceFile("web/nex-runtime.ts"))+readFile(resourceFile("web/nex-bytes.ts"));
          if(module.asynchronous)runtimeInputs+=readFile(resourceFile("web/nex-task-runtime.ts"));
          auto key=hash(module.source+runtimeInputs+NEX_BUILD_ID);
          actual=runTypeScriptTest(module,(fs::path(directory)/key/"typescript").string(),supervisorTimeout(taskLimits),taskTest?&taskLimits:nullptr);
        }else{auto opts=buildOptions;opts.entry=f.name;opts.testEntry=true;auto result=build(p,directory,opts);requireNativeHost(result);actual=capture(executionArguments(result.executable),taskTest?supervisorTimeout(taskLimits):30);}
        if(actual.code!=0||actual.output!=expected.output)throw Error("E_DIFFERENTIAL",std::string(web?"TypeScript":"native")+" test disagrees with interpreter: "+f.name+"\n"+actual.errors,f.span);}
      ++count;llvm::json::Object observed{{"name",f.name},{"ok",true},{"native",native&&!web},{"web",native&&web}};
      if(taskTest)observed["task_execution"]=taskExecutionJSON(taskLimits,taskLimits,native?(web?"typescript":"native"):"reference",native?supervisorTimeout(taskLimits):0);
      tests.push_back(std::move(observed));
    }
    if(!count)throw Error("E_TEST","no tests found");
    if(o.has("--json"))print(llvm::json::Object{{"ok",true},{"tests",std::move(tests)}});else std::cout<<count<<" tests passed ("<<(o.has("--interpreter-only")?"interpreter":o.get("--target")=="web"?"interpreter + TypeScript":"interpreter + native")<<")\n";return 0;
  }
  if(o.command=="emit"&&o.get("--kind","mlir")=="mlir"){
    auto text=emitMLIR(p,buildOptions.entry,false,buildOptions.libraryEntry||buildOptions.target=="server");auto output=o.get("--output");if(output.empty())std::cout<<text;else writeFile(output,text);return 0;
  }
  if(o.command=="emit"&&o.get("--kind")!="llvm")throw Error("E_OPTION","--kind must be mlir, llvm or typescript");
  if(o.command=="package"){
    print(packageApplication(p,buildOptions,directory,root.string(),store,
      {o.get("--directory"),o.get("--notices"),o.compiler,o.has("--dpkg-notices"),o.get("--foreign")}));return 0;
  }
  auto result=build(p,directory,buildOptions);
  if(o.command=="run"||o.command=="debug"||o.command=="profile")requireNativeHost(result);
  if(o.command=="profile"){
    auto report=profileNative(p,result,store.graph(p),profiling);auto object=report.getAsObject();auto code=int(*object->getInteger("exit_code"));
    if(o.has("--json"))print(std::move(report));else std::cout<<"Profile: "<<object->getString("output")->str()<<" (exit "<<code<<")\n";return code;
  }
  if(o.command=="emit") {auto text=readFile(result.llvm);auto output=o.get("--output");if(output.empty())std::cout<<text;else writeFile(output,text);return 0;}
  if(o.command=="run") {
    if(!o.has("--json")){std::vector<std::string> arguments=executionArguments(result.executable);arguments.insert(arguments.end(),o.extra.begin(),o.extra.end());return execute(arguments);}
    auto arguments=executionArguments(result.executable);arguments.insert(arguments.end(),o.extra.begin(),o.extra.end());
    bool taskEntry=usesTaskEffects(p,buildOptions.entry);auto effective=taskEntry?taskEffectiveLimits(taskLimits,arguments):taskLimits;
    auto timeout=taskEntry?supervisorTimeout(effective):30u;auto child=capture(arguments,timeout);
    auto manifest=parseJSON(readFile((fs::path(result.executable).parent_path()/"debug.json").string()));
    llvm::json::Object observed{{"ok",child.code==0},{"exit_code",child.code},{"stdout",child.output},{"stderr",child.errors},{"build_key",result.key},{"native_diagnostics",nativeDiagnostics(p,manifest,store,child.errors)}};
    if(taskEntry)observed["task_execution"]=taskExecutionJSON(taskLimits,effective,"native",timeout);
    print(std::move(observed));return child.code;
  }
  if(o.command=="debug") {
    auto kind=o.get("--kind","lldb");if(kind!="lldb"&&kind!="dap"&&kind!="nex-dap")throw Error("E_OPTION","debug kind must be lldb, dap or nex-dap");
    auto session=nativeDebugSession(p,result,root.string(),o.compiler,kind,foreignArguments);
    if(o.has("--json")||kind!="lldb"){print(std::move(session));return 0;}
    std::vector<std::string> args={"lldb",result.executable};
    for(const auto &command:nativeLLDBCommands(session)){args.push_back("-o");args.push_back(command);}
    args.insert(args.end(),o.extra.begin(),o.extra.end());return execute(args);
  }
  auto output=o.get("--output");if(!output.empty()){copyFile(result.executable,output,true);if(!buildOptions.libraryEntry)fs::permissions(output,fs::perms::owner_exec|fs::perms::group_exec|fs::perms::others_exec,fs::perm_options::add);}
  auto notices=result.notices;
  if(!output.empty()&&!notices.empty()){notices=fs::absolute(output).string()+".THIRD_PARTY_NOTICES.txt";copyFile(result.notices,notices,true);}
  if(o.has("--json")){llvm::json::Object observed{{"ok",true},{"executable",output.empty()?result.executable:fs::absolute(output).string()},{"kind",buildOptions.target=="server"?"http_server":buildOptions.libraryEntry?"static_library":"executable"},{"cached",result.cached},{"target",result.target},{"compiler_target",result.compilerTarget},{"host_compatible",result.hostCompatible},{"revision",revision(p)},{"build_key",result.key},{"mlir",result.mlir},{"llvm",result.llvm},{"notices",notices},{"metadata",(fs::path(result.executable).parent_path()/"build.json").string()},{"debug_manifest",(fs::path(result.executable).parent_path()/"debug.json").string()},{"compilation",result.compilation},{"compiled_modules",result.compiledModules},{"reused_modules",result.reusedModules},{ "compiled_functions",result.compiledFunctions},{"reused_functions",result.reusedFunctions}};if(usesTaskEffects(p,buildOptions.entry))observed["task_limits"]=taskLimitsJSON(taskLimits);print(std::move(observed));}
  else std::cout<<(result.cached?"Cached ":"Built ")<<(output.empty()?result.executable:output)<<'\n';return 0;
}
}
int main(int argc,char **argv) {
  bool machine=false;for(int i=1;i<argc;++i)if(std::string(argv[i])=="--json")machine=true;
  try{return run(options(argc,argv));}
  catch(const nex::Error &e){
    if(machine)print(nex::diagnosticJSON(e,NEX_VERSION,NEX_BUILD_ID));
    else {std::cout<<e.output;std::cerr<<(e.span.file.empty()?"":e.span.file+":")<<e.code<<":"<<e.span.line<<":"<<e.span.column<<": "<<e.what()<<'\n';}return 1;
  }catch(const std::exception &e){if(machine)print(nex::diagnosticJSON(nex::Error("E_INTERNAL",e.what()),NEX_VERSION,NEX_BUILD_ID));else std::cerr<<"E_INTERNAL: "<<e.what()<<'\n';return 1;}
}
