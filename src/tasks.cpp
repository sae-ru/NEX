#include "nex/tasks.h"
#include "nex/task_process.h"
#include "nex/verification.h"
#include "nex/native_toolchain.h"
#include "nex/foreign_catalogue.h"
#include "nex/project_capture.h"
#include "nex/task_package.h"
#include "nex/task_workload.h"
#include "nex/graph_snapshot.h"
#include "nex/native_diagnostics.h"
#include "llvm/Support/Error.h"
#include "llvm/TargetParser/Host.h"
#include <algorithm>
#include <chrono>
#include <filesystem>
#include <functional>
#include <random>
#include <thread>
#include <cerrno>
#include <cstdlib>
#include <sys/stat.h>
#include <unistd.h>

namespace nex {
namespace {
namespace fs=std::filesystem;
using JSON=llvm::json::Value;using Object=llvm::json::Object;using Array=llvm::json::Array;
[[noreturn]] void invalid(const std::string &message){throw Error("E_TASK",message);}
const Object &object(const JSON &v){auto o=v.getAsObject();if(!o)invalid("expected an object");return *o;}
std::string text(const Object &o,const std::string &key,bool empty=false,bool nul=false){auto v=o.getString(key);if(!v||(!empty&&v->empty())||v->size()>8192||(!nul&&v->contains('\0')))invalid("invalid string: "+key);return v->str();}
std::string optional(const Object &o,const std::string &key,const std::string &fallback=""){return o.get(key)?text(o,key):fallback;}
void fields(const Object &o,std::set<std::string> names){for(const auto &[name,_]:o)if(!names.contains(name.str()))invalid("unknown field: "+name.str());}
const Array &array(const Object &o,const std::string &key,size_t min=1,size_t max=64){auto v=o.getArray(key);if(!v||v->size()<min||v->size()>max)invalid("invalid array size: "+key);return *v;}
std::vector<std::string> strings(const Object &o,const std::string &key,size_t min=1){std::vector<std::string> result;std::set<std::string> seen;for(const auto &v:array(o,key,min)){auto s=v.getAsString();if(!s||s->empty()||s->size()>256||s->contains('\0')||!seen.insert(s->str()).second)invalid("invalid/duplicate string in "+key);result.push_back(s->str());}return result;}
std::string identifier(const Object &o,const std::string &key){auto s=text(o,key);if(s.size()>64||!std::all_of(s.begin(),s.end(),[](unsigned char c){return (c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')||c=='_'||c=='-';}))invalid("invalid task identifier: "+key);return s;}
std::string digest(const Object &o,const std::string &key){auto s=text(o,key);if(s.size()!=64||!std::all_of(s.begin(),s.end(),[](char c){return (c>='0'&&c<='9')||(c>='a'&&c<='f');}))invalid("expected a lowercase content hash: "+key);return s;}
unsigned number(const Object &o,const std::string &key,unsigned fallback,unsigned min=1,unsigned max=3600){if(!o.get(key))return fallback;auto n=o.getInteger(key);if(!n||*n<min||*n>max)invalid("integer outside supported range: "+key);return unsigned(*n);}
std::string pathName(const std::string &s){fs::path p(s);if(p.empty()||p.is_absolute()||s.find('\\')!=std::string::npos||s.find('\0')!=std::string::npos)invalid("expected a normalized relative path");for(const auto &c:p)if(c==".."||c=="."||c.empty())invalid("unsafe relative path");if(p.generic_string()!=s)invalid("path must be normalized");return s;}
fs::path inside(const fs::path &root,const std::string &name){auto path=root;for(const auto &part:fs::path(pathName(name))){path/=part;if(fs::is_symlink(path))throw Error("E_TASK_INTEGRITY","symlink in task input/artifact path");}return path;}
JSON parse(const std::string &s){auto v=llvm::json::parse(s);if(!v)throw Error("E_JSON",llvm::toString(v.takeError()));return std::move(*v);}
JSON readJSON(const fs::path &path,uint64_t max=1048576){if(!fs::is_regular_file(path)||fs::file_size(path)>max)invalid("missing or oversized JSON: "+path.string());return parse(readFile(path.string()));}
std::string content(const Function &f){return hash(json(canonical(f),false));}
void atomic(const fs::path &path,const JSON &value){auto temporary=path;temporary+=".tmp";writeFile(temporary.string(),json(value)+"\n");fs::rename(temporary,path);}
void atomic(const fs::path &path,const Object &value){atomic(path,JSON(Object(value)));}
bool ok(const JSON &v){auto o=v.getAsObject();return o&&o->getBoolean("ok").value_or(false);}
struct Candidate {Program program;JSON bundle,graph;std::string revision,sourceHash;};
struct Prepared {JSON task=nullptr;std::string taskHash,id;std::map<std::string,Candidate> programs;std::map<std::string,JSON> contracts,projects,packageNotices;std::map<std::string,ServerWorkload> workloads;Object linkage;std::map<std::string,NativeToolchainSnapshot> toolchains;std::map<std::string,std::string> checkTools;std::optional<ForeignCatalogueSnapshot> foreign;std::set<std::string> foreignChecks;};
const Object &projectComponent(const JSON &capture,const std::string &configuration){
  const auto &c=object(capture);auto entries=c.getObject("expectations")->getArray(configuration);if(!entries)throw Error("E_TASK_PROJECT","unknown captured project configuration");
  for(const auto &v:*entries)if(object(v).getString("name")==c.getString("component"))return object(v);
  throw Error("E_TASK_PROJECT","captured project has no selected component");
}
bool projectTestNative(const JSON &capture,const Function &f,const std::string &configuration){
  const auto &c=object(capture);auto owner=c.getObject("function_owners")->getString(f.name);if(!owner)throw Error("E_TASK_PROJECT","test has no selected project component owner: "+f.name);
  for(const auto &v:*c.getObject("expectations")->getArray(configuration))if(object(v).getString("name")==owner)return f.realm!="client"&&(object(v).getString("kind")!="web"||f.realm=="server");
  throw Error("E_TASK_PROJECT","test owner is outside the selected architecture");
}
bool supported(const Prepared &p,const Object &c){
  auto kind=text(c,"kind"),target=text(c,"target");
  if(auto project=p.projects.find(text(c,"program"));project!=p.projects.end()){
    auto configuration=text(c,"configuration");const auto &component=projectComponent(project->second,configuration),&native=*object(project->second).getObject("toolchains")->getObject(configuration);
    auto componentKind=text(component,"kind");
    if(kind=="package")return componentKind=="web"?target=="web":
      (componentKind=="executable"||componentKind=="server")&&native.getBoolean("host_compatible").value_or(false)&&target==(componentKind=="server"?"server":"native");
    if(kind=="build")return componentKind=="web"?target=="web":componentKind=="server"?target=="server":componentKind!="source"&&(target=="native"||target==text(native,"target"));
    if(kind=="test"){
      for(const auto &value:array(c,"tests")){
        const auto &f=p.programs.at(text(c,"program")).program.function(text(object(value),"symbol"));auto nativeTest=projectTestNative(project->second,f,configuration);
        if(nativeTest&&!native.getBoolean("host_compatible").value_or(false))return false;
        if(target=="native"?!nativeTest:target=="web"?nativeTest&&(f.realm!="shared"||!f.effects.empty()):true)return false;
      }return true;
    }
    if(kind=="profile"&&c.get("workload"))return target=="server"&&componentKind=="server"&&native.getBoolean("host_compatible").value_or(false);
    if(kind=="run"||kind=="profile")return target=="native"&&componentKind=="executable"&&native.getBoolean("host_compatible").value_or(false);
    return target=="source";
  }
  if(kind=="build"){
    if(target=="web")return true;
    if(c.get("toolchain"))return true; // configureNative validated this selector.
    BuildOptions options;options.target=target;try{configureNative(options);return true;}catch(const Error &e){if(e.code=="E_TARGET")return false;throw;}
  }
  if(c.get("toolchain")&&!p.toolchains.at(text(c,"toolchain")).hostCompatible)return false;
  if(kind=="test")return target=="native"||target=="web";
  if(kind=="run"||kind=="profile")return target=="native";
  return target=="source";
}
Object foreignValues(const Prepared &p){return p.foreign?Object{{"hash",p.foreign->hash},{"platform",p.foreign->platform}}:Object{};}
Object toolchainValues(const Prepared &p){Object result;for(const auto &[id,s]:p.toolchains)result[id]=Object{{"hash",s.hash},{"target",s.target},{"host_compatible",s.hostCompatible}};return result;}
std::set<std::string> reach(const Program &p,const std::set<std::string> &roots){std::set<std::string> found;std::function<void(const std::string&)> visit=[&](const auto &name){if(found.insert(name).second){const auto &f=p.function(name);if(!f.templateName.empty())visit(f.templateName);for(const auto &d:f.dependencies)visit(d);}};for(const auto &r:roots)visit(r);return found;}
std::set<std::string> types(const Program &p,const std::set<std::string> &functions){std::set<std::string> found;std::function<void(Type)> visit=[&](auto t){if(t.element)visit(*t.element);if(t.kind==Type::Function)for(const auto &argument:t.arguments)visit(argument);if(t.kind==Type::Record&&found.insert(t.name).second){const auto &s=p.structure(t.name);if(!s.templateName.empty())visit(Type::record(s.templateName));for(const auto &argument:s.typeArguments)visit(argument);for(auto field:s.members())visit(field->type);}};std::function<void(E)> expr=[&](E e){if(e){visit(e->type);for(auto a:e->args)expr(a);}};std::function<void(const std::vector<S>&)> block=[&](const auto &b){for(auto s:b){visit(s->type);expr(s->expr);childBlocks(s,block);}};for(const auto &name:functions){const auto &f=p.function(name);visit(f.result);for(const auto &v:f.params)visit(v.type);for(const auto &capture:f.captures)visit(capture.type);block(f.body);}return found;}
uint64_t decimal(const JSON &v){auto s=v.getAsString();if(!s||s->empty()||s->size()>20||(s->size()>1&&(*s)[0]=='0'))invalid("budget must be a canonical unsigned decimal string");uint64_t n=0;for(char c:*s){if(c<'0'||c>'9'||n>(UINT64_MAX-unsigned(c-'0'))/10)invalid("budget exceeds uint64");n=n*10+unsigned(c-'0');}return n;}
void validateShape(const JSON &task){
  const auto &t=object(task);fields(t,{"schema","language","id","title","goal","programs","requirements","checks"});
  if(text(t,"schema")!="nex.task/1"||text(t,"language")!=languageVersion)invalid("unsupported task schema/language");identifier(t,"id");text(t,"title");text(t,"goal");
  std::set<std::string> programs,checks,requirements,projectPrograms;
  for(const auto &value:array(t,"programs",1,8)){const auto &p=object(value);fields(p,{"id","entry","baseline_revision","project"});auto id=identifier(p,"id");if(!programs.insert(id).second)invalid("duplicate program");pathName(text(p,"entry"));if(p.get("baseline_revision"))digest(p,"baseline_revision");
    if(auto value=p.get("project")){const auto &project=object(*value);fields(project,{"manifest","component","architecture_hash"});auto manifest=pathName(text(project,"manifest"));if(fs::path(manifest).filename()!=manifest)invalid("project task architecture must be beside nex.json");identifier(project,"component");digest(project,"architecture_hash");projectPrograms.insert(id);}
  }
  for(const auto &value:array(t,"checks")){
    const auto &c=object(value);auto kind=text(c,"kind");bool project=projectPrograms.contains(text(c,"program"));std::set<std::string> names={"id","kind","program","target","timeout_seconds"};
    auto add=[&](std::initializer_list<const char*> keys){for(auto k:keys)names.insert(k);};
    if(kind=="test")add({"tests"});else if(kind=="build")add({"entry","profile","mode"});else if(kind=="run")add({"entry","profile","expect"});else if(kind=="verify")add({"contracts","intent_hash","solver_timeout_ms","resource_limit"});else if(kind=="effects")add({"symbols","allowed_effects","allowed_realms"});else if(kind=="profile")add({"entry","scenario","budget","hardware"});else if(kind=="package"){if(!project)invalid("package checks require a declared project architecture");}else if(kind=="api"){}else invalid("unknown check kind: "+kind);
    if(project)add({"configuration"});
    if(project&&kind=="profile")add({"workload","workload_hash","server_workers"});
    if(kind=="package")add({"notices","notices_hash"});
    if(project||kind=="build"||kind=="test"||kind=="run"||kind=="profile")add({"toolchain","toolchain_hash"});
    if(kind=="test"||kind=="run"||kind=="profile")add({"foreign_hash"});
    fields(c,names);if(!checks.insert(identifier(c,"id")).second)invalid("duplicate check");if(!programs.contains(text(c,"program")))invalid("unknown check program");text(c,"target");number(c,"timeout_seconds",60);
    if(bool(c.get("toolchain"))!=bool(c.get("toolchain_hash")))invalid("toolchain and toolchain_hash must be supplied together");
    if(project){identifier(c,"configuration");if(c.get("profile"))invalid("project checks select a configuration, without overriding its profile");}
    if(kind=="package"){if(bool(c.get("notices"))!=bool(c.get("notices_hash")))invalid("package notices and notices_hash must be supplied together");if(c.get("notices")){pathName(text(c,"notices"));digest(c,"notices_hash");}}
    if(c.get("toolchain")){identifier(c,"toolchain");digest(c,"toolchain_hash");if(!project&&(text(c,"target")=="web"||(kind!="build"&&text(c,"target")!="native")))invalid("toolchain requires a native check target");}
    if(bool(c.get("workload"))!=bool(c.get("workload_hash")))invalid("workload and workload_hash must be supplied together");
    if(c.get("workload")){if(!project||kind!="profile"||text(c,"target")!="server")invalid("workload requires a project server profile check");pathName(text(c,"workload"));digest(c,"workload_hash");number(c,"server_workers",8,1,64);}
    else if(c.get("server_workers")||(project&&kind=="profile"&&text(c,"target")=="server"))invalid("server profile requires a pinned workload");
    if(c.get("foreign_hash")){digest(c,"foreign_hash");if(text(c,"target")!="native"&&!(project&&kind=="profile"&&c.get("workload")&&text(c,"target")=="server"))invalid("foreign_hash requires native execution or a server workload");}
    if(kind=="test"){std::set<std::string> seen;for(const auto &v:array(c,"tests")){const auto &pin=object(v);fields(pin,{"symbol","content_hash"});if(!seen.insert(text(pin,"symbol")).second)invalid("duplicate test");digest(pin,"content_hash");}}
    if(kind=="build"||kind=="run"){auto profile=optional(c,"profile","debug");if(profile!="debug"&&profile!="release"&&profile!="profile")invalid("unknown build profile");if(kind=="build"){auto mode=optional(c,"mode","application");if(mode!="application"&&mode!="library"&&mode!="module")invalid("unknown build mode");}if(c.get("entry"))text(c,"entry");}
    if(kind=="run"){auto e=c.getObject("expect");if(!e)invalid("run requires expect");fields(*e,{"stdout","exit_code","runtime_code"});text(*e,"stdout",true,true);number(*e,"exit_code",999,0,255);if(!e->get("exit_code"))invalid("run requires exit_code");if(e->get("runtime_code"))text(*e,"runtime_code");}
    if(kind=="verify"){pathName(text(c,"contracts"));digest(c,"intent_hash");number(c,"solver_timeout_ms",2000,1,60000);number(c,"resource_limit",1000000,1,100000000);}
    if(kind=="effects"){strings(c,"symbols");for(const auto &s:strings(c,"allowed_effects",0))if(s!="io"&&s!="db"&&s!="fs"&&s!="ffi")invalid("unknown effect");if(c.get("allowed_realms"))for(const auto &s:strings(c,"allowed_realms"))if(s!="shared"&&s!="client"&&s!="server")invalid("unknown realm");}
    if(kind=="profile"){text(c,"entry");text(c,"scenario");auto b=c.getObject("budget");if(!b||b->empty())invalid("profile requires nonempty budget");fields(*b,{"max_duration_ns","max_peak_handles","max_peak_objects","max_calls","max_p95_latency_ns","max_p99_latency_ns","min_requests_per_second"});for(const auto &[k,v]:*b){if(k=="max_calls"){const auto &calls=object(v);if(calls.empty()||calls.size()>64)invalid("invalid call budget");for(const auto &[name,count]:calls){if(name.str().empty())invalid("empty call symbol");decimal(count);}}else decimal(v);}if(c.get("hardware")){const auto &h=object(*c.get("hardware"));fields(h,{"cpu","target"});text(h,"cpu");text(h,"target");}bool performance=b->get("max_duration_ns");for(auto key:{"max_p95_latency_ns","max_p99_latency_ns","min_requests_per_second"})if(b->get(key)){if(!c.get("workload"))invalid("request budgets require a server workload");performance=true;}if(performance&&!c.get("hardware"))invalid("timing/rate budget requires explicit hardware cpu/target");}
  }
  std::set<std::string> used;
  for(const auto &v:array(t,"requirements",1,32)){const auto &r=object(v);fields(r,{"id","text","bindings","targets","checks"});if(!requirements.insert(identifier(r,"id")).second)invalid("duplicate requirement");text(r,"text");strings(r,"targets");for(const auto &id:strings(r,"checks")){if(!checks.contains(id))invalid("requirement refers to unknown check");used.insert(id);}for(const auto &b:array(r,"bindings")){const auto &binding=object(b);fields(binding,{"program","kind","symbol"});if(!programs.contains(text(binding,"program")))invalid("binding refers to unknown program");auto kind=text(binding,"kind");if(kind!="function"&&kind!="structure"&&kind!="endpoint")invalid("unknown binding kind");text(binding,"symbol");}}
  if(used!=checks)invalid("every check must be linked to a requirement");
}
std::map<std::string,std::string> projectOverlays(const JSON &bundle,const fs::path &root){
  auto metadata=readJSON(root/"nex.json");auto libraries=object(metadata).getObject("libraries");std::map<std::string,std::string> result;
  for(const auto &[key,value]:*object(bundle).getObject("files")){
    fs::path base=root;std::string relative=key.str();
    if(relative.starts_with("@")){
      std::string alias;
      if(relative.starts_with("@std/")){alias="std";relative=relative.substr(5);}
      else{auto slash=relative.find('/',5);alias=relative.substr(5,slash-5);relative=relative.substr(slash+1);}
      auto selected=libraries?libraries->getString(alias):std::nullopt;
      if(selected)base=fs::weakly_canonical(root/selected->str());
      else if(alias=="std")base=fs::weakly_canonical(fs::path(resourceFile("runtime/runtime.cpp")).parent_path().parent_path()/"lib");
      else throw Error("E_TASK_PROJECT","archived candidate needs its configured library alias: "+alias);
    }
    auto physical=fs::weakly_canonical(base/relative);auto from=physical.lexically_relative(fs::weakly_canonical(base));
    if(from.is_absolute()||std::any_of(from.begin(),from.end(),[](const auto &p){return p=="..";}))throw Error("E_TASK_PROJECT","archived source escapes its configured root");
    auto source=value.getAsString()->str();auto [found,inserted]=result.emplace(physical.string(),source);if(!inserted&&found->second!=source)throw Error("E_TASK_PROJECT","archived source aliases disagree");
  }return result;
}
Prepared prepare(const JSON &task,const TaskOptions &options,const fs::path &frozen={}){
  if(json(task).size()+1>1048576)invalid("formatted task snapshot exceeds 1 MiB");
  validateShape(task);Prepared result;result.task=task;result.taskHash=hash(json(task,false));const auto &t=object(task);result.id=text(t,"id");
  if(!options.expectedHash.empty()&&options.expectedHash!=result.taskHash)throw Error("E_TASK_INTENT","task definition differs from --task-hash");
  if(!options.revision.empty()&&array(t,"programs").size()!=1)invalid("--revision requires a single program; use --candidates for multiple programs");
  if(frozen.empty())for(const auto &value:array(t,"programs")){
    auto id=text(object(value),"id"),selected=options.revision;if(options.candidates.contains(id))selected=options.candidates.at(id);
    if(selected.empty()){validateProjectMetadata(options.root);break;}
  }
  Store store(fs::path(options.root)/".nex");std::map<std::string,std::string> shared;
  for(const auto &value:array(t,"programs")){
    const auto &p=object(value);auto id=text(p,"id"),entry=text(p,"entry"),selected=options.revision;
    if(options.candidates.contains(id))selected=options.candidates.at(id);
    JSON bundle=nullptr;Program program;
    if(!frozen.empty()){bundle=readJSON(frozen/("inputs/programs/"+id+".json"),16*1048576);program=loadBundle(bundle,options.root);}
    else if(!selected.empty()){
      if(p.get("project")&&store.revisionLanguage(selected=="HEAD"?store.headRevision():selected)!=languageVersion)throw Error("E_LANGUAGE_VERSION","project candidate requires an explicit language migration");
      bundle=store.bundle(selected);program=loadBundle(bundle,options.root);if(selected!="HEAD"&&revision(program)!=selected)throw Error("E_REVISION","candidate snapshot does not match its revision");
    }
    else {program=loadProgram(inside(options.root,entry).string(),options.root);bundle=sourceBundle(program);}
    if(program.entryUnit!=entry)invalid("candidate entry differs from task program: "+id);
    if(json(bundle).size()+1>16*1048576)invalid("program source snapshot exceeds 16 MiB");
    for(const auto &[_,unit]:program.units){auto found=shared.find(unit.module);if(found!=shared.end()&&found->second!=unit.source)throw Error("E_TASK_SNAPSHOT","programs contain conflicting sources for module "+unit.module);shared[unit.module]=unit.source;}
    auto rev=store.save(program,"",false);auto graph=store.graph(program);auto sourceHash=hash(json(bundle,false));
    result.programs.emplace(id,Candidate{std::move(program),std::move(bundle),std::move(graph),rev,sourceHash});
    if(auto project=p.getObject("project")){
      std::set<std::string> configurations;for(const auto &value:array(t,"checks"))if(object(value).getString("program")==id)configurations.insert(text(object(value),"configuration"));
      JSON captured=nullptr;
      if(!frozen.empty())captured=readJSON(frozen/"inputs/projects"/(id+".json"),64*1048576);
      else{
        auto manifest=inside(options.root,text(*project,"manifest"));auto source=readFile(manifest.string());auto architecture=parse(source);
        if(hash(json(architecture,false))!=digest(*project,"architecture_hash"))throw Error("E_TASK_PROJECT","reviewed project architecture changed");
        auto overlays=selected.empty()?std::map<std::string,std::string>{}:projectOverlays(result.programs.at(id).bundle,options.root);
        captured=captureProject(options.root,manifest.string(),source,text(*project,"component"),configurations,overlays);
      }
      validateProjectCaptureData(captured);const auto &capture=object(captured);
      if(capture.getString("schema")!="nex.project-capture/1"||capture.getString("component")!=project->getString("component")||capture.getString("architecture_hash")!=project->getString("architecture_hash")||capture.getString("manifest")!=project->getString("manifest"))throw Error("E_TASK_PROJECT","captured architecture identity differs from the task");
      for(const auto &configuration:configurations)if(projectComponent(captured,configuration).getString("source_bundle_hash")!=result.programs.at(id).sourceHash)throw Error("E_TASK_PROJECT","architecture sources disagree with the selected graph candidate");
      result.projects.insert_or_assign(id,std::move(captured));
    }
  }
  for(const auto &[id,_]:options.candidates)if(!result.programs.contains(id))invalid("candidate map contains unknown program: "+id);
  std::map<std::string,std::set<std::string>> covered,structures;std::map<std::string,const Object*> checks;
  for(const auto &value:array(t,"checks")){
    const auto &c=object(value);auto id=text(c,"id"),kind=text(c,"kind");checks[id]=&c;const auto &p=result.programs.at(text(c,"program")).program;std::set<std::string> roots;
    if(c.get("workload")){
      auto base=frozen/"inputs/workloads"/id;
      auto workload=frozen.empty()?inspectServerWorkload(options.root,inside(options.root,text(c,"workload")).string()):inspectServerWorkload(base.string(),"workload.json");
      if(workload.sha256!=digest(c,"workload_hash"))throw Error("E_TASK_WORKLOAD","reviewed workload definition changed: "+id);
      result.workloads.emplace(id,std::move(workload));
    }
    if(kind=="package"&&c.get("notices")){
      auto base=frozen/"inputs/package-notices"/id;
      auto snapshot=frozen.empty()?captureTaskPackageNotices(inside(options.root,text(c,"notices")).string(),options.root):readJSON(base/"snapshot.json",16*1048576);
      if(taskPackageNoticesHash(snapshot)!=digest(c,"notices_hash"))throw Error("E_TASK_NOTICES","reviewed package notice inputs changed: "+id);
      if(!frozen.empty())verifyTaskPackageNotices(snapshot,base.string());result.packageNotices.emplace(id,std::move(snapshot));
    }
    if(c.get("toolchain")){
      auto name=text(c,"toolchain");auto selected=options.toolchains.find(name);
      if(selected==options.toolchains.end())throw Error("E_TASK_TOOLCHAIN","missing trusted toolchain '"+name+"'; supply --toolchains CATALOG.json");
      BuildOptions native;native.target=result.projects.contains(text(c,"program"))?text(*object(result.projects.at(text(c,"program"))).getObject("toolchains")->getObject(text(c,"configuration")),"target"):text(c,"target");native.toolchain=selected->second;configureNative(native);
      if(!result.toolchains.contains(name)){
        auto snapshot=inspectNativeToolchain(native);
        if(!frozen.empty()){
          auto base=frozen/"inputs/toolchains"/name;
          if(json(readJSON(base/"config.json"),false)!=json(snapshot.manifest,false)||json(readJSON(base/"identity.json",4*1048576),false)!=json(snapshot.inputs,false))throw Error("E_TASK_TOOLCHAIN","trusted current toolchain differs from captured inputs: "+name);
        }
        result.toolchains.emplace(name,std::move(snapshot));
      }
      if(result.toolchains.at(name).hash!=digest(c,"toolchain_hash"))throw Error("E_TASK_TOOLCHAIN","reviewed toolchain fingerprint changed: "+name);
      result.checkTools[id]=name;
    }
    if(auto project=result.projects.find(text(c,"program"));project!=result.projects.end()){
      auto configuration=text(c,"configuration");const auto &component=projectComponent(project->second,configuration),&native=*object(project->second).getObject("toolchains")->getObject(configuration);
      if(native.getBoolean("explicit").value_or(false)&&!c.get("toolchain"))throw Error("E_TASK_TOOLCHAIN","project configuration requires a reviewed current --toolchains entry: "+configuration);
        if(c.get("toolchain")){
          const auto &current=result.toolchains.at(text(c,"toolchain"));
          if(current.hash!=text(native,"hash")||current.manifest!=*native.get("manifest")||current.inputs!=*native.get("identity"))throw Error("E_TASK_TOOLCHAIN","trusted toolchain differs from the project configuration");
        }
      if(c.get("entry")&&c.getString("entry")!=component.getString("entry_function"))throw Error("E_TASK_PROJECT","check entry must match the declared component entry");
      if(kind=="build"){
        auto mode=optional(c,"mode","application"),componentKind=text(component,"kind");
        if(mode=="module"||((componentKind=="static_library"||componentKind=="shared_library")!=(mode=="library")))throw Error("E_TASK_PROJECT","build mode must match the declared component artifact kind");
      }
      if(kind=="profile"){
        if(c.get("workload")&&component.getString("kind")!="server")throw Error("E_TASK_WORKLOAD","workload profile requires a server component");
        const auto &files=*object(project->second).getObject("files");auto build=parse(files.getString(text(object(project->second),"project_root")+"/"+text(object(project->second),"manifest"))->str());
        if(object(build).getObject("configurations")->getObject(configuration)->getString("profile")!="profile")throw Error("E_TASK_PROJECT","profile check requires a profile configuration");
      }
    }
    auto function=[&](const std::string &name)->const Function&{const auto &f=p.function(name);if(name!=f.name)invalid("task bindings require qualified function names: "+name);roots.insert(f.name);return f;};
    if(kind=="test")for(const auto &v:array(c,"tests")){const auto &pin=object(v);const auto &f=function(text(pin,"symbol"));if(!f.test)invalid("selected function is not a test");if(content(f)!=text(pin,"content_hash"))throw Error("E_TASK_TEST_CHANGED","reviewed test body changed: "+f.name);}
    else if(kind=="verify"){
      auto contract=readJSON(frozen.empty()?inside(options.root,text(c,"contracts")):frozen/("inputs/contracts/"+id+".json"));
      if(verificationIntentHash(contract)!=text(c,"intent_hash"))throw Error("E_TASK_INTENT","formal acceptance property changed: "+id);
      auto &o=*contract.getAsObject();o["expected_revision"]=revision(p);o["source_hash"]=hash(json(sourceBundle(p),false));
      for(auto &v:*o.getArray("functions")){auto &spec=*v.getAsObject();spec["content_hash"]=content(function(text(spec,"symbol")));}
      if(json(contract).size()+1>1048576)invalid("derived formal contract exceeds 1 MiB");
      result.contracts.emplace(id,std::move(contract));
    }else if(kind=="effects")for(const auto &name:strings(c,"symbols"))function(name);
    else if(kind=="api")for(const auto &e:p.endpoints)function(e.target);
    else if((kind=="package"||kind=="build")&&text(c,"target")=="web"&&optional(c,"mode","application")=="application"){
      for(const auto &f:p.functions)if(f.owner==p.module&&(f.localName=="initial"||f.localName=="update"||f.localName=="view"||f.localName=="title"||f.localName=="route"||f.localName=="commands"))function(f.name);
    }else{
      auto fallback=p.module+"::"+(text(c,"target")=="server"?"handle":"main");
      if(auto project=result.projects.find(text(c,"program"));project!=result.projects.end())if(auto entry=projectComponent(project->second,text(c,"configuration")).getString("entry_function"))fallback=entry->str();
      function(optional(c,"entry",fallback));
    }
    covered[id]=reach(p,roots);structures[id]=types(p,covered[id]);
    bool executes=kind=="run"||kind=="profile"||(kind=="test"&&text(c,"target")=="native");
    bool external=false;for(const auto &name:covered[id])external|=p.function(name).foreign.has_value();
    if(executes&&external&&!c.get("foreign_hash"))throw Error("E_TASK_FOREIGN","external execution check must pin foreign_hash: "+id);
    if(c.get("foreign_hash")){
      if(options.foreign.empty())throw Error("E_TASK_FOREIGN","supply a current trusted --foreign HOST.json for check: "+id);
      if(!result.foreign)result.foreign=inspectForeignCatalogue(options.foreign);
      if(result.foreign->hash!=digest(c,"foreign_hash"))throw Error("E_TASK_FOREIGN","operator catalogue differs from reviewed foreign_hash: "+id);
      for(const auto &name:covered[id])checkForeignBinding(*result.foreign,p,p.function(name));
      result.foreignChecks.insert(id);
    }
  }
  if(!options.foreign.empty()&&!result.foreign)throw Error("E_TASK_FOREIGN","no task execution check pins the supplied operator catalogue");
  if(result.foreign&&!frozen.empty())verifyForeignCatalogue(*result.foreign,frozen/"inputs/foreign");
  for(const auto &[id,capture]:result.projects){
    auto temporary=fs::path(createTemporaryDirectory("nex-task-project"));
    try{
      auto container=temporary/"capture";auto root=materializeProjectCapture(capture,container.string());validateProjectCapturePlans(capture,container.string());
      for(const auto &value:array(t,"checks")){
        const auto &check=object(value);if(check.getString("program")!=id||check.getString("kind")!="test")continue;
        auto entries=object(capture).getObject("expectations")->getArray(text(check,"configuration"));
        for(const auto &pin:array(check,"tests")){
          auto symbol=text(object(pin),"symbol");auto owner=object(capture).getObject("function_owners")->getString(symbol);if(!owner)throw Error("E_TASK_PROJECT","selected test has no component owner");
          for(const auto &component:*entries)if(object(component).getString("name")==owner){
            auto program=loadProgram((fs::path(root)/text(object(component),"entry")).string(),root);
            if(content(program.function(symbol))!=text(object(pin),"content_hash"))throw Error("E_TASK_TEST_CHANGED","reviewed test context differs in its owning component: "+symbol);
          }
        }
      }
      fs::remove_all(temporary);
    }
    catch(...){std::error_code ignored;fs::remove_all(temporary,ignored);throw;}
  }
  for(const auto &value:array(t,"requirements")){
    const auto &r=object(value);auto linked=strings(r,"checks");std::set<std::string> targets;for(const auto &id:linked)targets.insert(text(*checks.at(id),"target"));for(const auto &target:strings(r,"targets"))if(!targets.contains(target))invalid("requirement target has no linked check: "+target);
    Array bindings;
    for(const auto &v:array(r,"bindings")){
      const auto &b=object(v);auto program=text(b,"program"),kind=text(b,"kind"),symbol=text(b,"symbol");const auto &candidate=result.programs.at(program);const auto &p=candidate.program;std::string source,file,hashValue;bool touched=false;Array related;
      if(kind=="function"){const auto &f=p.function(symbol);if(f.name!=symbol)invalid("qualified binding required");source=p.definition(f);file=f.unit;hashValue=content(f);}
      else if(kind=="structure"){const auto &s=p.structure(symbol);if(s.name!=symbol)invalid("qualified binding required");source=p.definition(s);file=s.unit;hashValue=hash(json(canonical(s),false));}
      else {const Endpoint *found=nullptr;for(const auto &e:p.endpoints)if(e.name==symbol)found=&e;if(!found)invalid("endpoint binding not found: "+symbol);source=p.definition(*found);file=found->unit;hashValue=hash(json(canonical(*found),false));}
      for(const auto &id:linked){const auto &c=*checks.at(id);if(text(c,"program")!=program)continue;bool hit=kind=="function"?covered[id].contains(symbol):kind=="structure"?structures[id].contains(symbol):text(c,"kind")=="api";
        if(kind=="endpoint")for(const auto &e:p.endpoints)if(e.name==symbol&&covered[id].contains(e.target))hit=true;
        if(hit){touched=true;related.push_back(id);}}
      if(!touched)invalid("binding is not statically reached by its linked checks: "+symbol);
      Object binding{{"program",program},{"kind",kind},{"symbol",symbol},{"file",file},{"content_hash",hashValue},{"checks",std::move(related)}};
      for(const auto &node:*object(candidate.graph).getArray("nodes"))if(object(node).getString("name")==symbol)binding["node_id"]=text(object(node),"id");
      bindings.push_back(std::move(binding));
    }
    result.linkage[text(r,"id")]=std::move(bindings);
  }
  return result;
}
// Executable resources are copied from the compiler's selected trusted root.
// Replay never selects C++/JS/Python resources from arbitrary receipt paths.
std::map<std::string,std::string> resources(){
  auto root=fs::path(resourceFile("runtime/runtime.cpp")).parent_path().parent_path();std::map<std::string,std::string> files;uint64_t bytes=0;
  for(const auto &directory:{"runtime","lib","web","debug"}){
    for(fs::recursive_directory_iterator i(root/directory),end;i!=end;++i){
      auto name=i->path().filename().string();if(i->is_symlink())throw Error("E_TASK_INTEGRITY","symlink in compiler resource tree");
      if(i->is_directory()&&(name=="node_modules"||name==".nex"||name=="dist"||name=="generated"||name=="__pycache__"||name=="test-results"||name=="playwright-report")){i.disable_recursion_pending();continue;}
      if(!i->is_regular_file())continue;bytes+=i->file_size();if(bytes>64*1048576||files.size()>=4096)invalid("compiler resource snapshot limit exceeded");
      auto key=i->path().lexically_relative(root).generic_string();files.emplace(key,readFile(i->path().string()));
    }
  }
  for(const auto &name:{"tools/app_bundle.py","tools/sdk_bundle.py","tools/server_workload.py"}){
    auto path=root/name;if(fs::is_symlink(path)||!fs::is_regular_file(path))throw Error("E_TASK_RESOURCE","missing trusted package resource");
    auto data=readFile(path.string());bytes+=data.size();if(bytes>64*1048576||files.size()>=4096)invalid("compiler resource snapshot limit exceeded");files.emplace(name,std::move(data));
  }
  return files;
}
Object fileIndex(const fs::path &root,size_t maximumFiles=8192,const fs::path &linkRoot={}){
  Object files;uint64_t bytes=0;
  for(const auto &e:fs::recursive_directory_iterator(root)){
    if(e.is_symlink()){
      if(linkRoot.empty())throw Error("E_TASK_INTEGRITY","symlink in saved artifact");
      auto target=fs::read_symlink(e.path()),resolved=fs::canonical(e.path()),relative=resolved.lexically_relative(fs::canonical(linkRoot));
      if(target.is_absolute()||relative.is_absolute()||std::any_of(relative.begin(),relative.end(),[](const auto &part){return part=="..";})||!fs::is_regular_file(resolved))throw Error("E_TASK_INTEGRITY","package symlink escapes its saved package");
      auto value=target.generic_string();bytes+=value.size();if(bytes>256*1048576||files.size()>=maximumFiles)invalid("artifact size/count limit exceeded");
      files[e.path().lexically_relative(root).generic_string()]=Object{{"symlink",value},{"hash",hash(value)},{"bytes",int64_t(value.size())}};continue;
    }
    if(!e.is_regular_file())continue;bytes+=e.file_size();if(bytes>256*1048576||files.size()>=maximumFiles)invalid("artifact size/count limit exceeded");
    auto data=readFile(e.path().string());files[e.path().lexically_relative(root).generic_string()]=Object{{"hash",hash(data)},{"bytes",int64_t(data.size())}};
  }return files;
}
void saveInputs(const Prepared &p,const fs::path &directory,const TaskOptions &options){
  writeFile((directory/"inputs/task.json").string(),json(p.task)+"\n");
  for(const auto &[id,candidate]:p.programs)writeFile((directory/("inputs/programs/"+id+".json")).string(),json(candidate.bundle)+"\n");
  for(const auto &[id,workload]:p.workloads)writeFile((directory/"inputs/workloads"/id/"workload.json").string(),workload.source);
  for(const auto &[id,capture]:p.projects)writeFile((directory/"inputs/projects"/(id+".json")).string(),json(capture)+"\n");
  for(const auto &[id,notices]:p.packageNotices)saveTaskPackageNotices(notices,(directory/"inputs/package-notices"/id).string());
  for(const auto &[id,contract]:p.contracts)writeFile((directory/("inputs/contracts/"+id+".json")).string(),json(contract)+"\n");
  for(const auto &[id,snapshot]:p.toolchains){writeFile((directory/"inputs/toolchains"/id/"config.json").string(),json(snapshot.manifest)+"\n");writeFile((directory/"inputs/toolchains"/id/"identity.json").string(),json(snapshot.inputs)+"\n");}
  if(p.foreign)saveForeignCatalogue(*p.foreign,directory/"inputs/foreign");
  for(const auto &[name,data]:resources())writeFile((directory/"inputs/resources"/name).string(),data);
  auto files=fileIndex(directory/"inputs");Object indexed;uint64_t bytes=0;for(auto &[name,v]:files){bytes+=*object(v).getInteger("bytes");indexed["inputs/"+name.str()]=std::move(v);}if(bytes>128*1048576)invalid("task input snapshot exceeds 128 MiB");
  JSON manifest=Object{{"schema","nex.task-inputs/1"},{"task_hash",p.taskHash},{"compiler_build",NEX_BUILD_ID},{"compiler_hash",hash(readFile(options.compiler))},{"files",std::move(indexed)}};
  if(json(manifest).size()+1>4*1048576)invalid("task input index exceeds 4 MiB");
  atomic(directory/"inputs/manifest.json",manifest);
}
JSON verifyInputs(const fs::path &directory,const TaskOptions &options,const std::string &expected){
  auto manifest=readJSON(inside(directory,"inputs/manifest.json"),4*1048576);const auto &m=object(manifest);
  if(hash(readFile((directory/"inputs/manifest.json").string()))!=expected)throw Error("E_TASK_INTEGRITY","input manifest hash differs");
  fields(m,{"schema","task_hash","compiler_build","compiler_hash","files"});if(text(m,"schema")!="nex.task-inputs/1"||text(m,"compiler_build")!=NEX_BUILD_ID||text(m,"compiler_hash")!=hash(readFile(options.compiler)))throw Error("E_TASK_COMPILER","replay requires the captured compiler binary/build");
  auto indexed=m.get("files");if(!indexed)invalid("input manifest lacks files");const auto &files=object(*indexed);if(files.empty()||files.size()>8192)invalid("invalid input manifest size");uint64_t bytes=0;std::map<std::string,std::string> savedResources;
  for(const auto &[key,v]:files){auto name=pathName(key.str());if(!name.starts_with("inputs/")||name=="inputs/manifest.json")invalid("input manifest path is outside inputs");auto path=inside(directory,name);const auto &entry=object(v);fields(entry,{"hash","bytes"});auto size=entry.getInteger("bytes");if(!size||*size<0||*size>64*1048576||!fs::is_regular_file(path)||fs::file_size(path)!=uint64_t(*size))throw Error("E_TASK_INTEGRITY","input size differs: "+name);bytes+=*size;if(bytes>128*1048576)invalid("input snapshot exceeds limit");auto data=readFile(path.string());if(hash(data)!=digest(entry,"hash"))throw Error("E_TASK_INTEGRITY","input content differs: "+name);if(name.starts_with("inputs/resources/"))savedResources[name.substr(17)]=std::move(data);}
  if(savedResources!=resources())throw Error("E_TASK_RESOURCE","saved executable resources differ from the compiler's trusted resources");
  // Reject extra input files too, rather than allowing an unindexed header to
  // participate in a later compilation. The manifest itself is the only extra.
  auto actual=fileIndex(directory/"inputs",8193);if(actual.size()!=files.size()+1)throw Error("E_TASK_INTEGRITY","unindexed task inputs");
  for(const auto &[name,_]:actual)if(name!="manifest.json"&&!files.get("inputs/"+name.str()))throw Error("E_TASK_INTEGRITY","unindexed task input");
  return manifest;
}
Object workloadValues(const Prepared &p){Object result;for(const auto &[id,w]:p.workloads)result[id]=Object{{"definition_sha256",w.sha256},{"runner_sha256",w.helperSha256},{"planned_requests",w.plan.getInteger("total_requests").value()},{"runtime_state","fresh synthetic credential and database per check"}};return result;}
JSON summary(const Prepared &p){Array programs,checks;for(const auto &[id,c]:p.programs)programs.push_back(Object{{"id",id},{"revision",c.revision},{"source_hash",c.sourceHash}});bool ready=true;for(const auto &v:array(object(p.task),"checks")){const auto &c=object(v);bool available=supported(p,c);if(text(c,"kind")=="test")for(const auto &test:array(c,"tests")){auto realm=p.programs.at(text(c,"program")).program.function(text(object(test),"symbol")).realm;if((text(c,"target")=="web"&&realm=="server")||(text(c,"target")=="native"&&realm=="client"))available=false;}ready&=available;checks.push_back(Object{{"id",text(c,"id")},{"status",available?"ready":"unsupported"}});}return Object{{"schema","nex.task-check/1"},{"ok",ready},{"task",p.id},{"task_hash",p.taskHash},{"programs",std::move(programs)},{"toolchains",toolchainValues(p)},{"foreign_catalogue",foreignValues(p)},{"checks",std::move(checks)},{"bindings",Object(p.linkage)},{"workloads",workloadValues(p)},{"linkage","static reachability, not measured coverage or proof of natural-language requirements"}};}
std::string nonce(){return std::to_string(std::random_device{}())+"-"+std::to_string(std::random_device{}());}
class ForeignTemporary {
  fs::path path;dev_t device=0;ino_t inode=0;
  bool cleanup()noexcept{
    try{
      if(path.empty())return true;
      struct stat current{};
      if(::lstat(path.c_str(),&current)){if(errno==ENOENT){path.clear();return true;}return false;}
      // A native callback must not redirect parent cleanup to another object.
      if(current.st_dev!=device||current.st_ino!=inode||!S_ISDIR(current.st_mode))return false;
      std::error_code ec;fs::permissions(path,fs::perms::owner_all,fs::perm_options::add|fs::perm_options::nofollow,ec);if(ec)return false;
      for(fs::recursive_directory_iterator it(path,ec),end;!ec&&it!=end;it.increment(ec)){
        auto status=it->symlink_status(ec);if(ec)return false;
        if(fs::is_directory(status))fs::permissions(it->path(),fs::perms::owner_all,fs::perm_options::add|fs::perm_options::nofollow,ec);
      }
      if(ec)return false;fs::remove_all(path,ec);if(ec)return false;path.clear();return true;
    }catch(...){return false;}
  }
public:
  ForeignTemporary(){
    std::error_code ec;auto root=fs::temp_directory_path(ec);
    if(ec)throw Error("E_TASK_TEMP","native temporary root is unavailable");
    root=fs::absolute(root,ec);if(ec)throw Error("E_TASK_TEMP","native temporary root is unavailable");
    auto pattern=(root/"nex-task-XXXXXX").string();
    if(!::mkdtemp(pattern.data()))throw Error("E_TASK_TEMP","cannot create a fresh native temporary directory");
    path=pattern;
    struct stat created{};
    if(::lstat(path.c_str(),&created)||!S_ISDIR(created.st_mode)||::chmod(path.c_str(),0700)){fs::remove(path,ec);throw Error("E_TASK_TEMP","cannot protect native temporary directory");}
    device=created.st_dev;inode=created.st_ino;
  }
  ~ForeignTemporary(){cleanup();}
  const fs::path &directory()const{return path;}
  void finish(){if(!cleanup())throw Error("E_TASK_CLEANUP","cannot clean owned native temporary files");}
};
struct Runner {
  Prepared &p;TaskOptions options;fs::path directory;Object report;bool interrupted=false;
  fs::path workspace(const std::string &program){
    auto root=directory/"workspaces"/program;auto found=p.projects.find(program);return found==p.projects.end()?root:root/text(object(found->second),"project_root");
  }
  void verifyProject(const std::string &program){auto found=p.projects.find(program);if(found!=p.projects.end())validateProjectCapturePlans(found->second,(directory/"workspaces"/program).string());}
  void verifyNotices(const std::string &id){auto found=p.packageNotices.find(id);if(found!=p.packageNotices.end())verifyTaskPackageNotices(found->second,(directory/"inputs/package-notices"/id).string());}
  ServerWorkload checkedWorkload(const std::string &id){
    const auto &expected=p.workloads.at(id);auto selected=inspectServerWorkload((directory/"inputs/workloads"/id).string(),"workload.json");
    if(selected.source!=expected.source||selected.sha256!=expected.sha256||selected.helperSource!=expected.helperSource||selected.helperSha256!=expected.helperSha256)
      throw Error("E_TASK_INTEGRITY","captured workload or trusted runner changed: "+id);return selected;
  }
  void verifyWorkload(const std::string &id){if(p.workloads.contains(id))(void)checkedWorkload(id);}
  void verifyForeign(const std::string &id){if(p.foreignChecks.contains(id))verifyForeignCatalogue(*p.foreign,directory/"inputs/foreign");}
  void verifyToolchain(const std::string &id){
    auto selected=p.checkTools.find(id);if(selected==p.checkTools.end())return;
    BuildOptions native;native.toolchain=inside(directory,"inputs/toolchains/"+selected->second+"/config.json").string();
    auto current=inspectNativeToolchain(native);const auto &expected=p.toolchains.at(selected->second);
    if(current.hash!=expected.hash||json(current.manifest,false)!=json(expected.manifest,false))throw Error("E_TASK_TOOLCHAIN","captured toolchain inputs changed during execution: "+selected->second);
  }
  JSON command(const std::string &id,const std::string &program,const std::vector<std::string> &args,unsigned timeout,const std::string &label,const std::string &selectedRevision=""){
    const auto &candidate=p.programs.at(program);bool project=!args.empty()&&args[0]=="project";
    std::vector<std::string> command{options.compiler};command.insert(command.end(),args.begin(),args.end());
    if(p.checkTools.contains(id)&&!args.empty()&&(args[0]=="build"||args[0]=="test"||args[0]=="run"||args[0]=="profile"))command.insert(command.end(),{"--toolchain",(directory/"inputs/toolchains"/p.checkTools.at(id)/"config.json").string()});
    bool projectExec=false;if(project)for(size_t i=1;i+1<args.size();++i)if(args[i]=="--kind")projectExec=args[i+1]=="test"||args[i+1]=="run"||args[i+1]=="profile";
    if(p.foreignChecks.contains(id)&&!args.empty()&&(projectExec||args[0]=="eval"||args[0]=="run"||args[0]=="test"||args[0]=="profile"))command.insert(command.end(),{"--foreign",(directory/"inputs/foreign/host.json").string()});
    if(!project)command.insert(command.end(),{"--revision",selectedRevision.empty()?candidate.revision:selectedRevision});
    command.insert(command.end(),{"--build-directory",(fs::path(options.root)/".nex/build").string(),"--json"});
    return observeCommand(id,program,command,timeout,label,true);
  }
  JSON observeCommand(const std::string &id,const std::string &program,const std::vector<std::string> &command,unsigned timeout,const std::string &label,bool structured,const Program *native=nullptr,const std::string &manifest=""){
    std::map<std::string,std::string> environment{{"NEX_RESOURCE_DIR",(directory/"inputs/resources").string()},{"NEX_TRACY","0"},{"PYTHONDONTWRITEBYTECODE","1"}};
    std::unique_ptr<ForeignTemporary> temporary;
    if(p.foreignChecks.contains(id)){temporary=std::make_unique<ForeignTemporary>();environment["TMPDIR"]=temporary->directory().string();}
    auto relative="logs/"+id+"/"+label;auto began=std::chrono::steady_clock::now();
    auto process=runTaskProcess(command,workspace(program).string(),environment,timeout,(directory/relative).string());
    auto elapsed=std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now()-began).count();
    if(process.interrupted){interrupted=true;report["signal"]=process.interrupted;}
    // runTaskProcess has reaped the owned group, including uncooperative C.
    if(temporary)temporary->finish();
    Object result{{"command",Array{}},{"exit_code",process.process.code},{"stdout",relative+"/stdout"},{"stderr",relative+"/stderr"},{"timed_out",process.timedOut},{"output_limit",process.outputLimit},{"interrupted",process.interrupted},{"timeout_seconds",timeout},{"elapsed_ns",int64_t(elapsed)}};
    for(const auto &arg:command)result.getArray("command")->push_back(arg);
    JSON response=nullptr;
    if(!structured){
      response=Object{{"ok",process.process.code==0},{"exit_code",process.process.code},{"stdout",process.process.output},{"stderr",process.process.errors}};
      if(native)(*response.getAsObject())["native_diagnostics"]=nativeDiagnostics(*native,parseNativeManifest(readFile(manifest)),process.process.errors);
    }
    else if(!process.outputLimit){auto parsed=llvm::json::parse(process.process.output);if(parsed)response=std::move(*parsed);else llvm::consumeError(parsed.takeError());}
    auto file="artifacts/"+id+"/commands/"+label+".json";result["response"]=response;atomic(directory/file,result);
    return Object{{"ok",!process.timedOut&&!process.outputLimit&&!process.interrupted},{"exit_code",process.process.code},{"receipt",file},{"response",std::move(response)},{"timed_out",process.timedOut},{"output_limit",process.outputLimit}};
  }
  void copyArtifact(const fs::path &source,const fs::path &destination){
    if(fs::is_symlink(source))throw Error("E_TASK_INTEGRITY","refusing a symlink artifact");
    if(fs::is_directory(source)){fs::create_directories(destination);for(const auto &e:fs::directory_iterator(source))copyArtifact(e.path(),destination/e.path().filename());}
    else if(fs::is_regular_file(source)){fs::create_directories(destination.parent_path());copyFile(source.string(),destination.string(),true);}
    else throw Error("E_TASK_ARTIFACT","missing output artifact: "+source.string());
  }
  JSON check(const Object &c){
    auto id=text(c,"id"),kind=text(c,"kind"),program=text(c,"program"),target=text(c,"target");const auto &candidate=p.programs.at(program);const auto &source=candidate.program;
    Object row{{"id",id},{"kind",kind},{"program",program},{"target",target},{"status","failed"}};
    if(p.checkTools.contains(id)){const auto &snapshot=p.toolchains.at(p.checkTools.at(id));row["toolchain"]=p.checkTools.at(id);row["toolchain_hash"]=snapshot.hash;row["native_target"]=snapshot.target;row["host_compatible"]=snapshot.hostCompatible;}
    if(p.foreignChecks.contains(id))row["foreign_hash"]=p.foreign->hash;
    if(!supported(p,c)){row["status"]="unsupported";row["reason"]="target is not configured on this host";return row;}
    auto started=std::chrono::steady_clock::now();auto timeout=number(c,"timeout_seconds",60);auto artifact=directory/"artifacts"/id;fs::create_directories(artifact);
    auto remaining=[&](){auto elapsed=std::chrono::duration_cast<std::chrono::seconds>(std::chrono::steady_clock::now()-started).count();if(elapsed>=timeout)throw Error("E_TASK_TIMEOUT","check exhausted its process timeout");return timeout-unsigned(elapsed);};
    auto invoke=[&](std::vector<std::string> args,const std::string &label,const std::string &revision=""){verifyToolchain(id);verifyForeign(id);verifyProject(program);verifyNotices(id);verifyWorkload(id);auto value=command(id,program,args,remaining(),label,revision);verifyToolchain(id);verifyForeign(id);verifyProject(program);verifyNotices(id);verifyWorkload(id);if(!ok(value))throw Error(interrupted?"E_TASK_INTERRUPTED":object(value).getBoolean("timed_out").value_or(false)?"E_TASK_TIMEOUT":"E_TASK_OUTPUT","check process exceeded its execution/output limit");return value;};
    auto successful=[&](const JSON &v){return object(v).getInteger("exit_code")==0&&object(v).get("response")&&ok(*object(v).get("response"));};
    auto response=[&](const JSON &v)->const Object&{auto result=object(v).get("response");if(!result||!result->getAsObject())throw Error("E_TASK_PROCESS","compiler did not produce a JSON response");return object(*result);};
    bool project=p.projects.contains(program);
    auto fallback=source.module+"::"+(target=="server"?"handle":"main");
    if(project)if(auto entry=projectComponent(p.projects.at(program),text(c,"configuration")).getString("entry_function"))fallback=entry->str();
    auto entry=optional(c,"entry",fallback);
    auto projectArguments=[&](const std::string &kind){return std::vector<std::string>{"project",text(object(p.projects.at(program)),"manifest"),"--kind",kind,"--component",text(object(p.projects.at(program)),"component"),"--configuration",text(c,"configuration")};};
    auto builtArtifact=[&](const Object &build,const std::string &component)->const Object&{for(const auto &value:array(build,"artifacts",0,128))if(object(value).getString("component")==component)return object(value);throw Error("E_TASK_ARTIFACT","project build did not produce its requested artifact");};
    auto executeNative=[&](const Object &built,const Program &scope,const std::string &label){
      std::vector<std::string> arguments{text(built,"artifact")};if(p.foreignChecks.contains(id))arguments.insert(arguments.end(),{"--nex-foreign",(directory/"inputs/foreign/host.json").string()});
      verifyToolchain(id);verifyForeign(id);verifyProject(program);
      auto value=observeCommand(id,program,arguments,remaining(),label,false,&scope,text(built,"debug_manifest"));
      verifyToolchain(id);verifyForeign(id);verifyProject(program);
      if(!ok(value))throw Error(interrupted?"E_TASK_INTERRUPTED":object(value).getBoolean("timed_out").value_or(false)?"E_TASK_TIMEOUT":"E_TASK_OUTPUT","native process exceeded its execution/output limit");return value;
    };
    if(project){row["component"]=text(object(p.projects.at(program)),"component");row["configuration"]=text(c,"configuration");row["architecture_hash"]=text(object(p.projects.at(program)),"architecture_hash");}
    bool passed=false;
    if(kind=="test"){
      if(project){
        passed=true;Array results;unsigned index=0;
        for(const auto &pin:array(c,"tests")){
          auto name=text(object(pin),"symbol"),label="test-"+std::to_string(index++);const auto &f=source.function(name);bool native=projectTestNative(p.projects.at(program),f,text(c,"configuration"));
          if(!native){auto args=projectArguments("test");args.insert(args.end(),{"--symbol",name,"--timeout",std::to_string(timeout)});auto value=invoke(args,label);bool found=false;
            if(successful(value))if(auto tests=response(value).getArray("tests"))for(const auto &entry:*tests)found|=object(entry).getString("name")==name&&ok(entry)&&object(entry).getBoolean("typescript").value_or(false);
            passed&=found;results.push_back(Object{{"symbol",name},{"ok",found},{"receipt",text(object(value),"receipt")}});continue;
          }
          auto args=projectArguments("build-test");args.insert(args.end(),{"--symbol",name});auto compiled=invoke(args,label+"-build");
          if(!successful(compiled)){passed=false;results.push_back(Object{{"symbol",name},{"ok",false},{"receipt",text(object(compiled),"receipt")}});continue;}
          const auto &test=response(compiled);if(test.getString("content_hash")!=object(pin).getString("content_hash"))throw Error("E_TASK_TEST_CHANGED","built test differs from the approved body");
          auto owner=text(test,"component");std::string sourceEntry;
          for(const auto &entry:*object(p.projects.at(program)).getObject("expectations")->getArray(text(c,"configuration")))if(object(entry).getString("name")==owner)sourceEntry=text(object(entry),"entry");
          auto scope=loadProgram((workspace(program)/sourceEntry).string(),workspace(program).string());
          if(revision(scope)!=test.getString("revision")||hash(json(sourceBundle(scope),false))!=test.getString("source_bundle_hash"))throw Error("E_TASK_PROJECT","test scope changed after compilation");
          Store local(workspace(program)/".nex");auto selected=local.save(scope,"",false);
          Object observed{{"symbol",name},{"build",text(object(compiled),"receipt")}};bool reference=true;
          if(f.effects.empty()){
            auto ref=f.realm=="shared"?invoke({"test","--symbol",name,"--target","web"},label+"-reference-typescript",selected):invoke({"eval","--entry",name},label+"-reference",selected);
            reference=successful(ref);observed["reference"]=text(object(ref),"receipt");
          }else observed["reference_skip_reason"]="effectful project test executes once in its native backend";
          const auto &built=builtArtifact(*test.getObject("build"),owner);auto actual=executeNative(built,scope,label+"-native");
          bool found=successful(actual)&&reference&&(!f.effects.empty()||response(actual).getString("stdout")=="");
          observed["native"]=text(object(actual),"receipt");observed["ok"]=found;passed&=found;results.push_back(std::move(observed));if(interrupted)break;
        }row["tests"]=std::move(results);
      }else{
      passed=true;Array results;unsigned index=0;for(const auto &v:array(c,"tests")){auto name=text(object(v),"symbol");const auto &f=source.function(name);if((target=="web"&&f.realm=="server")||(target=="native"&&f.realm=="client")){row["status"]="unsupported";row["reason"]="selected test realm is unavailable on the requested target";return row;}
        auto args=project?projectArguments("test"):std::vector<std::string>{"test","--target",target};args.insert(args.end(),{"--symbol",name});if(project)args.insert(args.end(),{"--timeout",std::to_string(timeout)});
        auto value=invoke(args,"test-"+std::to_string(index++));bool found=false;if(successful(value)){auto tests=response(value).getArray("tests");if(tests)for(const auto &r:*tests)if(object(r).getString("name")==name&&ok(r)&&!object(r).getBoolean("skipped").value_or(false)&&(!project||object(r).getBoolean(target=="web"?"typescript":"native").value_or(false)))found=true;}passed&=found;results.push_back(Object{{"symbol",name},{"ok",found},{"receipt",text(object(value),"receipt")}});if(interrupted)break;}
      row["tests"]=std::move(results);
      }
    }else if(kind=="effects"){
      auto allowed=strings(c,"allowed_effects",0);auto realms=c.get("allowed_realms")?strings(c,"allowed_realms"):std::vector<std::string>{"shared","client","server"};std::set<std::string> roots;for(const auto &s:strings(c,"symbols"))roots.insert(s);Array violations;
      for(const auto &name:reach(source,roots)){const auto &f=source.function(name);for(const auto &e:f.effects)if(std::find(allowed.begin(),allowed.end(),e)==allowed.end())violations.push_back(Object{{"symbol",name},{"effect",e}});if(std::find(realms.begin(),realms.end(),f.realm)==realms.end())violations.push_back(Object{{"symbol",name},{"realm",f.realm}});}passed=violations.empty();row["violations"]=std::move(violations);
    }else if(kind=="verify"){
      auto input=directory/("inputs/contracts/"+id+".json");auto value=invoke({"verify","--contracts",input.string(),"--directory",(artifact/"proof").string(),"--solver-timeout",std::to_string(number(c,"solver_timeout_ms",2000,1,60000)),"--resource-limit",std::to_string(number(c,"resource_limit",1000000,1,100000000)),"--timeout",std::to_string(std::min(timeout,300u))},"verify");passed=successful(value);row["receipt"]=text(object(value),"receipt");
    }else if(kind=="run"){
      bool compareReference=!project||source.function(entry).effects.empty();JSON reference=nullptr;
      if(compareReference)reference=invoke({"eval","--entry",entry},"reference");
      JSON native=nullptr;
      if(project){
        auto compiled=invoke(projectArguments("build"),"native-build");if(!successful(compiled))throw Error("E_TASK_BUILD","project application build failed; inspect its command receipt");
        row["build"]=text(object(compiled),"receipt");const auto &built=builtArtifact(response(compiled),text(object(p.projects.at(program)),"component"));native=executeNative(built,source,"native");
      }else native=invoke({"run","--entry",entry,"--profile",optional(c,"profile","debug")},"native");
      const auto &expected=*c.getObject("expect");const auto &n=response(native);auto exit=number(expected,"exit_code",0,0,255);bool referenceMatch=!compareReference;
      if(compareReference){
        const auto &r=response(reference);
        if(auto error=expected.getString("runtime_code"))referenceMatch=r.getString("code")==error&&n.getString("stderr")&&n.getString("stderr")->starts_with(error->str()+":");
        else if(ok(*object(reference).get("response"))){auto value=r.get("value");int code=0;if(value&&!value->getAsNull()){auto v=value->getAsInteger();if(!v)invalid("run entry must return unit or i64");code=int(uint64_t(*v)&255);}referenceMatch=unsigned(code)==exit;}
        referenceMatch&=r.getString("stdout")==expected.getString("stdout");row["reference"]=text(object(reference),"receipt");
      }else row["reference_skip_reason"]="effectful project entry executes once in its native backend";
      bool errorMatch=true;
      if(project&&expected.getString("runtime_code")){
        errorMatch=false;if(auto diagnostics=n.getObject("native_diagnostics"))if(auto entries=diagnostics->getArray("diagnostics"))for(const auto &entry:*entries){auto e=entry.getAsObject();if(e&&e->getString("status")=="mapped")if(auto raw=e->getObject("report"))errorMatch|=raw->getString("code")==expected.getString("runtime_code");}
      }
      passed=referenceMatch&&errorMatch&&n.getString("stdout")==expected.getString("stdout")&&n.getInteger("exit_code")==exit;row["native"]=text(object(native),"receipt");
    }else if(kind=="profile"){
      if(auto hardware=c.getObject("hardware"))if(text(*hardware,"cpu")!=llvm::sys::getHostCPUName()||text(*hardware,"target")!=llvm::sys::getDefaultTargetTriple()){row["status"]="unsupported";row["reason"]="profile hardware differs from the approved measurement target";return row;}
      if(project){
        auto compiled=invoke(projectArguments("build"),"profile-build");if(!successful(compiled))throw Error("E_TASK_BUILD","project profile build failed; inspect its command receipt");
        const auto &a=builtArtifact(response(compiled),text(object(p.projects.at(program)),"component"));BuildResult built;
        built.executable=text(a,"artifact");built.key=text(a,"build_key");built.target=text(a,"target");built.compilerTarget=text(a,"compiler_target");built.hostCompatible=a.getBoolean("host_compatible").value_or(false);requireNativeHost(built);
        Array nodes;for(const auto &f:source.functions)nodes.push_back(Object{{"name",f.name},{"hash",content(f)},{"file",f.unit},{"id",nullptr}});
        ProfileOptions profiling;profiling.output=(artifact/"profile.json").string();profiling.scenario=text(c,"scenario");profiling.events=0;profiling.timeout=remaining();profiling.directory=workspace(program).string();
        profiling.interrupted=[&](int signal){interrupted=true;report["signal"]=signal;};
        std::unique_ptr<ForeignTemporary> temporary,serverState;
        std::unique_ptr<ServerWorkloadRun> workloadRun;
        if(p.workloads.contains(id)){
          auto workload=checkedWorkload(id);serverState=std::make_unique<ForeignTemporary>();
          auto state=createTaskWorkloadState(workload,serverState->directory().string(),number(c,"server_workers",8,1,64));
          profiling.arguments=std::move(state.arguments);profiling.environment=std::move(state.environment);row["workload_runtime"]=std::move(state.description);
          workloadRun=std::make_unique<ServerWorkloadRun>(workload);profiling.launcher=workloadRun->launcher();
          profiling.additionalEvidence=[&](){return workloadRun->evidence();};row["workload_hash"]=workload.sha256;
        }
        if(p.foreignChecks.contains(id)){
          profiling.arguments.insert(profiling.arguments.end(),{p.workloads.contains(id)?"--foreign":"--nex-foreign",(directory/"inputs/foreign/host.json").string()});
          temporary=std::make_unique<ForeignTemporary>();profiling.environment["TMPDIR"]=temporary->directory().string();
        }
        auto finish=[&](){if(serverState)serverState->finish();if(temporary)temporary->finish();};
        verifyToolchain(id);verifyForeign(id);verifyProject(program);verifyWorkload(id);JSON measured=nullptr;
        try{measured=profileNative(source,built,Object{{"nodes",std::move(nodes)}},profiling);finish();}
        catch(const Error &error){finish();if(error.code=="E_PROFILE_TIMEOUT")throw Error("E_TASK_TIMEOUT",error.what());if(error.code=="E_PROFILE_OUTPUT")throw Error("E_TASK_OUTPUT",error.what());if(error.code=="E_PROFILE_INTERRUPTED")throw Error("E_TASK_INTERRUPTED",error.what());throw;}
        catch(...){finish();throw;}
        verifyToolchain(id);verifyForeign(id);verifyProject(program);verifyWorkload(id);passed=ok(measured);
        auto receipt="artifacts/"+id+"/commands/profile.json";Array command;
        for(const auto &argument:profiling.launcher)command.push_back(argument);command.push_back(built.executable);for(const auto &argument:profiling.arguments)command.push_back(argument);
        atomic(directory/receipt,Object{{"command",std::move(command)},{"instrumented",true},{"build_key",built.key},{"revision",revision(source)},{"response",std::move(measured)}});
        row["receipt"]=receipt;row["build"]=text(object(compiled),"receipt");
      }else{
        auto value=invoke({"profile","--entry",entry,"--events","0","--scenario",text(c,"scenario"),"--timeout",std::to_string(timeout),"--output",(artifact/"profile.json").string()},"profile");passed=successful(value);row["receipt"]=text(object(value),"receipt");
      }
      if(passed){auto full=readJSON(artifact/"profile.json",64*1048576);const auto &r=object(full),&budget=*c.getObject("budget");Array failures;
        for(const auto &key:{"dropped_functions","dropped_frames","dropped_allocations","untracked_frees"})if(r.getInteger(key).value_or(1)!=0)failures.push_back(key);
        auto exceeds=[&](const std::string &key,int64_t observed){if(auto max=budget.get(key))if(observed<0||uint64_t(observed)>decimal(*max))failures.push_back(key);};exceeds("max_duration_ns",r.getInteger("duration_ns").value_or(-1));
        auto pools=r.getArray("memory");for(const auto &[name,key]:std::map<std::string,std::string>{{"NEX handles","max_peak_handles"},{"NEX objects (shallow)","max_peak_objects"}}){int64_t peak=-1;if(pools)for(const auto &pool:*pools)if(object(pool).getString("pool")==name)peak=object(pool).getInteger("peak_live").value_or(-1);exceeds(key,peak);}
        if(auto calls=budget.getObject("max_calls"))for(const auto &[name,max]:*calls){bool found=false;for(const auto &v:array(r,"functions",0,16384))if(object(v).getString("name")==name.str()){found=true;auto n=object(v).getInteger("calls");if(!n||*n<0||uint64_t(*n)>decimal(max))failures.push_back(name.str());}if(!found)failures.push_back(name.str()+":unobserved");}
        if(p.workloads.contains(id))for(auto &failure:taskWorkloadBudgetFailures(r,budget))failures.push_back(std::move(failure));
        passed=failures.empty();row["budget_failures"]=std::move(failures);
      }
    }else if(kind=="api"){
      auto value=invoke({"api","--directory",(artifact/"generated").string()},"api");passed=successful(value);row["receipt"]=text(object(value),"receipt");
    }else if(kind=="package"){
      auto destination=artifact/"package";auto args=projectArguments("package");args.insert(args.end(),{"--directory",destination.string()});
      if(p.packageNotices.contains(id)){args.insert(args.end(),{"--notices",(directory/"inputs/package-notices"/id/"notices.json").string()});row["notices_hash"]=taskPackageNoticesHash(p.packageNotices.at(id));}
      auto value=invoke(args,"package");passed=successful(value);row["receipt"]=text(object(value),"receipt");
      if(passed){
        const auto &r=response(value);if(r.getString("schema")!="nex.project-package/1"||r.getBoolean("application_execution").value_or(true))throw Error("E_TASK_ARTIFACT","invalid project package response");
        row["package"]=destination.lexically_relative(directory).generic_string();row["components"]=*r.get("components");row["application_execution"]=false;
      }
    }else if(kind=="build"){
      auto mode=optional(c,"mode","application");if(target=="web"&&mode=="library")invalid("web libraries use mode module");if(target!="web"&&mode=="module")invalid("module output requires target web");
      std::vector<std::string> args;
      if(project)args=projectArguments("build");
      else if(mode=="module")args={"emit","--kind","typescript","--entry",entry,"--directory",(artifact/"module").string()};
      else {args={"build","--target",target,"--profile",optional(c,"profile","debug")};if(target!="web"){args.insert(args.end(),{"--entry",entry});if(mode=="library")args.push_back("--library");}}
      auto value=invoke(args,"build");passed=successful(value);row["receipt"]=text(object(value),"receipt");
      if(passed&&project){
        Array outputs;
        for(const auto &item:array(response(value),"artifacts",0,128)){
          const auto &a=object(item);auto name=text(a,"component"),kind=text(a,"kind");auto destination=artifact/"components"/name;
          if(kind=="web")copyArtifact(text(*a.getObject("result"),"dist"),destination/"dist");
          else{
            auto executable=fs::path(text(a,"artifact"));copyArtifact(executable,destination/executable.filename());
            if(fs::is_directory(executable.parent_path()/"images"))copyArtifact(executable.parent_path()/"images",destination/"images");
            for(auto key:{"metadata","compilation","debug_manifest","notices"})if(auto file=a.getString(key);file&&!file->empty())copyArtifact(file->str(),destination/(std::string(key)+(std::string(key)=="notices"?".txt":".json")));
          }
          outputs.push_back(Object{{"component",name},{"kind",kind},{"directory",destination.lexically_relative(directory).generic_string()}});
        }row["components"]=std::move(outputs);
      }else if(passed&&mode!="module"){const auto &r=response(value);if(target=="web")copyArtifact(text(r,"dist"),artifact/"dist");else {auto exe=fs::path(text(r,"executable"));copyArtifact(exe,artifact/exe.filename());auto notices=r.getString("notices").value_or("").str();if(!notices.empty())copyArtifact(notices,artifact/"THIRD_PARTY_NOTICES.txt");for(auto k:{"metadata","compilation","debug_manifest"})if(auto path=r.getString(k))if(fs::is_regular_file(path->str()))copyArtifact(path->str(),artifact/(std::string(k)+".json"));}}
    }
    row["status"]=passed?"passed":"failed";row["artifacts"]=fileIndex(artifact,8192,kind=="package"?artifact/"package":fs::path{});return row;
  }
  void checkpoint(Store &store){auto output=directory/"receipt.json";atomic(output,report);store.recordTask(text(report,"run_id"),p.id,p.taskHash,text(report,"status"),output.string(),hash(readFile(output.string())));}
  JSON run(const std::string &replayOf=""){
    Store store(fs::path(options.root)/".nex");auto inputs=readFile((directory/"inputs/manifest.json").string());report=Object{{"schema","nex.task-receipt/1"},{"run_id","run-"+nonce()},{"task",p.id},{"task_hash",p.taskHash},{"language",languageVersion},{"toolchain",NEX_VERSION},{"compiler_build",NEX_BUILD_ID},{"input_hash",hash(inputs)},{"status","running"},{"ok",false},{"checks",Array{}},{"bindings",Object(p.linkage)},{"programs",*object(summary(p)).get("programs")},{"replay_of",replayOf},{"toolchains",toolchainValues(p)},{"foreign_catalogue",foreignValues(p)},{"workloads",workloadValues(p)},{"hardware",Object{{"cpu",llvm::sys::getHostCPUName().str()},{"target",llvm::sys::getDefaultTargetTriple()}}}};
    for(const auto &[id,candidate]:p.programs){
      if(auto project=p.projects.find(id);project!=p.projects.end()){materializeProjectCapture(project->second,(directory/"workspaces"/id).string());verifyProject(id);}
      else writeFile((workspace(id)/"nex.json").string(),json(Object{{"schema","nex.project/1"},{"language",languageVersion},{"entry",candidate.program.entryUnit}})+"\n");
      Store local(workspace(id)/".nex");local.save(loadBundle(candidate.bundle,workspace(id).string()));
    }
    checkpoint(store);
    for(const auto &v:array(object(p.task),"checks")){
      const auto &c=object(v);Object row{{"id",text(c,"id")},{"status",interrupted?"skipped":"running"}};report.getArray("checks")->push_back(std::move(row));checkpoint(store);
      if(!interrupted)try{report.getArray("checks")->back()=check(c);}catch(const Error &e){report.getArray("checks")->back()=Object{{"id",text(c,"id")},{"status",interrupted?"interrupted":"failed"},{"code",e.code},{"message",std::string(e.what())}};}catch(const std::exception &e){report.getArray("checks")->back()=Object{{"id",text(c,"id")},{"status","failed"},{"code","E_TASK_CHECK"},{"message",std::string(e.what())}};}
      checkpoint(store);
    }
    std::map<std::string,std::string> statuses;bool passed=true;for(const auto &v:*report.getArray("checks")){auto status=text(object(v),"status");statuses[text(object(v),"id")]=status;passed&=status=="passed";}
    Array requirements;for(const auto &v:array(object(p.task),"requirements")){const auto &r=object(v);bool accepted=true;Array results;for(const auto &id:strings(r,"checks")){accepted&=statuses[id]=="passed";results.push_back(Object{{"id",id},{"status",statuses[id]}});}requirements.push_back(Object{{"id",text(r,"id")},{"status",accepted?"passed":"not_satisfied"},{"checks",std::move(results)}});}
    report["requirements"]=std::move(requirements);report["status"]=interrupted?"interrupted":passed?"passed":"not_satisfied";report["ok"]=passed;checkpoint(store);
    auto value=report;value["schema"]="nex.task-session/1";value["output"]=(directory/"receipt.json").string();value.erase("bindings");
    for(auto &check:*value.getArray("checks")){auto &row=*check.getAsObject();row.erase("artifacts");if(auto tests=row.getArray("tests")){row["test_count"]=tests->size();row.erase("tests");}}
    for(auto &requirement:*value.getArray("requirements"))requirement.getAsObject()->erase("checks");return value;
  }
};
fs::path runDirectory(const TaskOptions &options){auto directory=options.directory.empty()?fs::path(options.root)/".nex/tasks/runs"/("run-"+nonce()):fs::absolute(options.directory);fs::create_directories(directory.parent_path());if(!fs::create_directory(directory))throw Error("E_EXISTS","task run requires a new directory");fs::permissions(directory,fs::perms::owner_all,fs::perm_options::replace);return directory;}
struct ReplayPreflight {
  fs::path directory=createTemporaryDirectory("nex-task-replay-preflight");
  ~ReplayPreflight(){std::error_code error;fs::remove_all(directory,error);}
};
}
JSON checkTask(const JSON &task,const TaskOptions &options){return summary(prepare(task,options));}
JSON runTask(const JSON &task,const TaskOptions &options){auto p=prepare(task,options);auto directory=runDirectory(options);saveInputs(p,directory,options);Runner runner{p,options,directory,{}};return runner.run();}
JSON replayTask(const std::string &receipt,const TaskOptions &options){
  auto path=fs::absolute(receipt);auto old=path.parent_path();auto saved=readJSON(path,32*1048576);const auto &r=object(saved);if(text(r,"schema")!="nex.task-receipt/1")invalid("expected a task receipt");auto manifest=verifyInputs(old,options,digest(r,"input_hash"));auto task=readJSON(old/"inputs/task.json");if(hash(json(task,false))!=text(object(manifest),"task_hash")||text(r,"task_hash")!=text(object(manifest),"task_hash"))throw Error("E_TASK_INTEGRITY","task identity differs from inputs");
  if(!options.revision.empty()||!options.candidates.empty())invalid("replay uses captured candidates");
  // Preflight may assign local graph identities. Keep that graph private, then
  // preserve its complete rows/IDs in the exclusively created output run.
  // Neither an ancestor project nor the saved receipt needs a writable graph.
  ReplayPreflight temporary;auto preparation=options;preparation.root=temporary.directory.string();auto p=prepare(task,preparation,old);
  auto directory=runDirectory(options);auto execution=options;execution.root=(directory/"state").string();fs::create_directory(execution.root);
  createGraphSnapshot(temporary.directory.string(),(fs::path(execution.root)/".nex").string());
  writeFile((fs::path(execution.root)/"nex.json").string(),json(Object{{"schema","nex.project/1"},{"language",languageVersion},{"entry","main.nex"}})+"\n");
  writeFile((fs::path(execution.root)/"task.json").string(),json(task)+"\n");
  for(const auto &[name,_]:object(*object(manifest).get("files"))){auto destination=directory/name.str();fs::create_directories(destination.parent_path());copyFile(inside(old,name.str()).string(),destination.string());}
  atomic(directory/"inputs/manifest.json",manifest);Runner runner{p,execution,directory,{}};return runner.run(path.string());
}
JSON projectTaskTemplate(const std::string &directory,const std::string &manifest,const std::string &component,const std::string &configuration){
  auto root=fs::canonical(directory);auto source=readFile(manifest);auto architecture=parse(source);
  auto selected=configuration.empty()?text(object(architecture),"default_configuration"):configuration;
  auto capture=captureProject(root.string(),manifest,source,component,{selected});const auto &description=projectComponent(capture,selected);
  auto program=loadProgram((root/text(description,"entry")).string(),root.string());const auto &native=*object(capture).getObject("toolchains")->getObject(selected);
  Array checks,requirements;
  auto add=[&](Object check,const std::vector<std::string> &symbols){
    auto id=text(check,"id"),target=text(check,"target");check["program"]="app";check["configuration"]=selected;
    if(native.getBoolean("explicit").value_or(false)){check["toolchain"]="project";check["toolchain_hash"]=text(native,"hash");}
    checks.push_back(std::move(check));Array bindings;for(const auto &symbol:symbols)bindings.push_back(Object{{"program","app"},{"kind","function"},{"symbol",symbol}});
    requirements.push_back(Object{{"id",id},{"text","Review this scaffold requirement and its acceptance criteria"},{"bindings",std::move(bindings)},{"targets",Array{target}},{"checks",Array{id}}});
  };
  unsigned index=0;for(const auto &f:program.functions)if(f.test&&object(capture).getObject("function_owners")->getString(f.name)){
    auto id="test-"+std::to_string(index++);add(Object{{"id",id},{"kind","test"},{"target",projectTestNative(capture,f,selected)?"native":"web"},{"tests",Array{Object{{"symbol",f.name},{"content_hash",content(f)}}}}},{f.name});
  }
  auto kind=text(description,"kind");
  if(kind=="web"){
    std::vector<std::string> entries;for(const auto &name:{"initial","update","view","title"})entries.push_back(program.function(name).name);
    add(Object{{"id","build-web"},{"kind","build"},{"target","web"}},entries);
  }else if(kind!="source"){
    auto entry=text(description,"entry_function");add(Object{{"id","build-native"},{"kind","build"},{"target",kind=="server"?"server":"native"},{"mode",kind=="static_library"||kind=="shared_library"?"library":"application"},{"entry",entry}},{entry});
  }
  if(checks.empty())invalid("project task scaffold needs an artifact entry or owned tests");
  JSON task=Object{{"schema","nex.task/1"},{"language",languageVersion},{"id","task-001"},{"title","Review and name this project task"},{"goal","Replace this scaffold with required behavior, edge cases and acceptance criteria"},
    {"programs",Array{Object{{"id","app"},{"entry",program.entryUnit},{"baseline_revision",revision(program)},
      {"project",Object{{"manifest",fs::path(manifest).filename().string()},{"component",component},{"architecture_hash",text(object(capture),"architecture_hash")}}}}}},
    {"requirements",std::move(requirements)},{"checks",std::move(checks)}};
  validateShape(task);return task;
}
JSON taskTemplate(const Program &p,const std::string &entry){
  Array checks,requirements;auto add=[&](Object c,const std::vector<std::string> &symbols){auto id=text(c,"id"),target=text(c,"target");c["program"]="app";checks.push_back(std::move(c));Array bindings;for(const auto &symbol:symbols)bindings.push_back(Object{{"program","app"},{"kind","function"},{"symbol",symbol}});requirements.push_back(Object{{"id",id},{"text","Review this scaffold requirement and its acceptance checks"},{"bindings",std::move(bindings)},{"targets",Array{target}},{"checks",Array{id}}});};
  unsigned index=0;for(const auto &f:p.functions)if(f.test){auto id="test-"+std::to_string(index++);add(Object{{"id",id},{"kind","test"},{"target",f.realm=="client"?"web":"native"},{"tests",Array{Object{{"symbol",f.name},{"content_hash",content(f)}}}}},{f.name});}
  const Function *main=nullptr,*web=nullptr,*server=nullptr;for(const auto &f:p.functions)if(f.owner==p.module&&!f.test){if(f.localName=="main"&&f.params.empty()&&(f.result==Type::I64||f.result==Type::Unit)&&f.realm!="client")main=&f;if(f.localName=="initial")web=&f;if(f.localName=="handle"&&f.realm=="server")server=&f;}
  if(web)add(Object{{"id","build-web"},{"kind","build"},{"target","web"},{"mode","application"},{"profile","release"}},{web->name});
  else if(server)add(Object{{"id","build-server"},{"kind","build"},{"target","server"},{"entry",server->name},{"profile","release"}},{server->name});
  else if(main)add(Object{{"id","build-native"},{"kind","build"},{"target","native"},{"entry",main->name},{"profile","release"}},{main->name});
  else for(const auto &f:p.functions)if(!f.test){add(Object{{"id","build-library"},{"kind","build"},{"target",f.realm=="client"?"web":"native"},{"entry",f.name},{"mode",f.realm=="client"?"module":"library"}},{f.name});break;}
  if(checks.empty())invalid("a task scaffold needs at least one function/test");JSON task=Object{{"schema","nex.task/1"},{"language",languageVersion},{"id","task-001"},{"title","Review and name this task"},{"goal","Replace this scaffold with the required behavior, edge cases and acceptance criteria"},{"programs",Array{Object{{"id","app"},{"entry",pathName(entry)},{"baseline_revision",revision(p)}}}},{"requirements",std::move(requirements)},{"checks",std::move(checks)}};validateShape(task);return task;
}
}
