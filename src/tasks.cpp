#include "nex/tasks.h"
#include "nex/task_process.h"
#include "nex/verification.h"
#include "nex/native_toolchain.h"
#include "llvm/Support/Error.h"
#include "llvm/TargetParser/Host.h"
#include <algorithm>
#include <chrono>
#include <filesystem>
#include <functional>
#include <random>
#include <thread>

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
struct Prepared {JSON task=nullptr;std::string taskHash,id;std::map<std::string,Candidate> programs;std::map<std::string,JSON> contracts;Object linkage;std::map<std::string,NativeToolchainSnapshot> toolchains;std::map<std::string,std::string> checkTools;};
bool supported(const Prepared &p,const Object &c){
  auto kind=text(c,"kind"),target=text(c,"target");
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
Object toolchainValues(const Prepared &p){Object result;for(const auto &[id,s]:p.toolchains)result[id]=Object{{"hash",s.hash},{"target",s.target},{"host_compatible",s.hostCompatible}};return result;}
std::set<std::string> reach(const Program &p,const std::set<std::string> &roots){std::set<std::string> found;std::function<void(const std::string&)> visit=[&](const auto &name){if(found.insert(name).second){const auto &f=p.function(name);if(!f.templateName.empty())visit(f.templateName);for(const auto &d:f.dependencies)visit(d);}};for(const auto &r:roots)visit(r);return found;}
std::set<std::string> types(const Program &p,const std::set<std::string> &functions){std::set<std::string> found;std::function<void(Type)> visit=[&](auto t){if(t.element)visit(*t.element);if(t.kind==Type::Function)for(const auto &argument:t.arguments)visit(argument);if(t.kind==Type::Record&&found.insert(t.name).second){const auto &s=p.structure(t.name);if(!s.templateName.empty())visit(Type::record(s.templateName));for(const auto &argument:s.typeArguments)visit(argument);for(auto field:s.members())visit(field->type);}};std::function<void(E)> expr=[&](E e){if(e){visit(e->type);for(auto a:e->args)expr(a);}};std::function<void(const std::vector<S>&)> block=[&](const auto &b){for(auto s:b){visit(s->type);expr(s->expr);childBlocks(s,block);}};for(const auto &name:functions){const auto &f=p.function(name);visit(f.result);for(const auto &v:f.params)visit(v.type);for(const auto &capture:f.captures)visit(capture.type);block(f.body);}return found;}
uint64_t decimal(const JSON &v){auto s=v.getAsString();if(!s||s->empty()||s->size()>20||(s->size()>1&&(*s)[0]=='0'))invalid("budget must be a canonical unsigned decimal string");uint64_t n=0;for(char c:*s){if(c<'0'||c>'9'||n>(UINT64_MAX-unsigned(c-'0'))/10)invalid("budget exceeds uint64");n=n*10+unsigned(c-'0');}return n;}
void validateShape(const JSON &task){
  const auto &t=object(task);fields(t,{"schema","language","id","title","goal","programs","requirements","checks"});
  if(text(t,"schema")!="nex.task/1"||text(t,"language")!=languageVersion)invalid("unsupported task schema/language");identifier(t,"id");text(t,"title");text(t,"goal");
  std::set<std::string> programs,checks,requirements;
  for(const auto &value:array(t,"programs",1,8)){const auto &p=object(value);fields(p,{"id","entry","baseline_revision"});if(!programs.insert(identifier(p,"id")).second)invalid("duplicate program");pathName(text(p,"entry"));if(p.get("baseline_revision"))digest(p,"baseline_revision");}
  for(const auto &value:array(t,"checks")){
    const auto &c=object(value);auto kind=text(c,"kind");std::set<std::string> names={"id","kind","program","target","timeout_seconds"};
    auto add=[&](std::initializer_list<const char*> keys){for(auto k:keys)names.insert(k);};
    if(kind=="test")add({"tests"});else if(kind=="build")add({"entry","profile","mode"});else if(kind=="run")add({"entry","profile","expect"});else if(kind=="verify")add({"contracts","intent_hash","solver_timeout_ms","resource_limit"});else if(kind=="effects")add({"symbols","allowed_effects","allowed_realms"});else if(kind=="profile")add({"entry","scenario","budget","hardware"});else if(kind=="api"){}else invalid("unknown check kind: "+kind);
    if(kind=="build"||kind=="test"||kind=="run"||kind=="profile")add({"toolchain","toolchain_hash"});
    fields(c,names);if(!checks.insert(identifier(c,"id")).second)invalid("duplicate check");if(!programs.contains(text(c,"program")))invalid("unknown check program");text(c,"target");number(c,"timeout_seconds",60);
    if(bool(c.get("toolchain"))!=bool(c.get("toolchain_hash")))invalid("toolchain and toolchain_hash must be supplied together");
    if(c.get("toolchain")){identifier(c,"toolchain");digest(c,"toolchain_hash");if(text(c,"target")=="web"||(kind!="build"&&text(c,"target")!="native"))invalid("toolchain requires a native check target");}
    if(kind=="test"){std::set<std::string> seen;for(const auto &v:array(c,"tests")){const auto &pin=object(v);fields(pin,{"symbol","content_hash"});if(!seen.insert(text(pin,"symbol")).second)invalid("duplicate test");digest(pin,"content_hash");}}
    if(kind=="build"||kind=="run"){auto profile=optional(c,"profile","debug");if(profile!="debug"&&profile!="release"&&profile!="profile")invalid("unknown build profile");if(kind=="build"){auto mode=optional(c,"mode","application");if(mode!="application"&&mode!="library"&&mode!="module")invalid("unknown build mode");}if(c.get("entry"))text(c,"entry");}
    if(kind=="run"){auto e=c.getObject("expect");if(!e)invalid("run requires expect");fields(*e,{"stdout","exit_code","runtime_code"});text(*e,"stdout",true,true);number(*e,"exit_code",999,0,255);if(!e->get("exit_code"))invalid("run requires exit_code");if(e->get("runtime_code"))text(*e,"runtime_code");}
    if(kind=="verify"){pathName(text(c,"contracts"));digest(c,"intent_hash");number(c,"solver_timeout_ms",2000,1,60000);number(c,"resource_limit",1000000,1,100000000);}
    if(kind=="effects"){strings(c,"symbols");for(const auto &s:strings(c,"allowed_effects",0))if(s!="io"&&s!="db"&&s!="fs"&&s!="ffi")invalid("unknown effect");if(c.get("allowed_realms"))for(const auto &s:strings(c,"allowed_realms"))if(s!="shared"&&s!="client"&&s!="server")invalid("unknown realm");}
    if(kind=="profile"){text(c,"entry");text(c,"scenario");auto b=c.getObject("budget");if(!b||b->empty())invalid("profile requires nonempty budget");fields(*b,{"max_duration_ns","max_peak_handles","max_peak_objects","max_calls"});for(const auto &[k,v]:*b){if(k=="max_calls"){const auto &calls=object(v);if(calls.empty()||calls.size()>64)invalid("invalid call budget");for(const auto &[name,count]:calls){if(name.str().empty())invalid("empty call symbol");decimal(count);}}else decimal(v);}if(c.get("hardware")){const auto &h=object(*c.get("hardware"));fields(h,{"cpu","target"});text(h,"cpu");text(h,"target");}if(b->get("max_duration_ns")&&!c.get("hardware"))invalid("duration budget requires explicit hardware cpu/target");}
  }
  std::set<std::string> used;
  for(const auto &v:array(t,"requirements",1,32)){const auto &r=object(v);fields(r,{"id","text","bindings","targets","checks"});if(!requirements.insert(identifier(r,"id")).second)invalid("duplicate requirement");text(r,"text");strings(r,"targets");for(const auto &id:strings(r,"checks")){if(!checks.contains(id))invalid("requirement refers to unknown check");used.insert(id);}for(const auto &b:array(r,"bindings")){const auto &binding=object(b);fields(binding,{"program","kind","symbol"});if(!programs.contains(text(binding,"program")))invalid("binding refers to unknown program");auto kind=text(binding,"kind");if(kind!="function"&&kind!="structure"&&kind!="endpoint")invalid("unknown binding kind");text(binding,"symbol");}}
  if(used!=checks)invalid("every check must be linked to a requirement");
}
Prepared prepare(const JSON &task,const TaskOptions &options,const fs::path &frozen={}){
  if(json(task).size()+1>1048576)invalid("formatted task snapshot exceeds 1 MiB");
  validateShape(task);Prepared result;result.task=task;result.taskHash=hash(json(task,false));const auto &t=object(task);result.id=text(t,"id");
  if(!options.expectedHash.empty()&&options.expectedHash!=result.taskHash)throw Error("E_TASK_INTENT","task definition differs from --task-hash");
  if(!options.revision.empty()&&array(t,"programs").size()!=1)invalid("--revision requires a single program; use --candidates for multiple programs");
  Store store(fs::path(options.root)/".nex");std::map<std::string,std::string> shared;
  for(const auto &value:array(t,"programs")){
    const auto &p=object(value);auto id=text(p,"id"),entry=text(p,"entry"),selected=options.revision;
    if(options.candidates.contains(id))selected=options.candidates.at(id);
    JSON bundle=nullptr;Program program;
    if(!frozen.empty()){bundle=readJSON(frozen/("inputs/programs/"+id+".json"),16*1048576);program=loadBundle(bundle,options.root);}
    else if(!selected.empty()){bundle=store.bundle(selected);program=loadBundle(bundle,options.root);if(selected!="HEAD"&&revision(program)!=selected)throw Error("E_REVISION","candidate snapshot does not match its revision");}
    else {program=loadProgram(inside(options.root,entry).string(),options.root);bundle=sourceBundle(program);}
    if(program.entryUnit!=entry)invalid("candidate entry differs from task program: "+id);
    if(json(bundle).size()+1>16*1048576)invalid("program source snapshot exceeds 16 MiB");
    for(const auto &[_,unit]:program.units){auto found=shared.find(unit.module);if(found!=shared.end()&&found->second!=unit.source)throw Error("E_TASK_SNAPSHOT","programs contain conflicting sources for module "+unit.module);shared[unit.module]=unit.source;}
    auto rev=store.save(program,"",false);auto graph=store.graph(program);auto sourceHash=hash(json(bundle,false));
    result.programs.emplace(id,Candidate{std::move(program),std::move(bundle),std::move(graph),rev,sourceHash});
  }
  for(const auto &[id,_]:options.candidates)if(!result.programs.contains(id))invalid("candidate map contains unknown program: "+id);
  std::map<std::string,std::set<std::string>> covered,structures;std::map<std::string,const Object*> checks;
  for(const auto &value:array(t,"checks")){
    const auto &c=object(value);auto id=text(c,"id"),kind=text(c,"kind");checks[id]=&c;const auto &p=result.programs.at(text(c,"program")).program;std::set<std::string> roots;
    if(c.get("toolchain")){
      auto name=text(c,"toolchain");auto selected=options.toolchains.find(name);
      if(selected==options.toolchains.end())throw Error("E_TASK_TOOLCHAIN","missing trusted toolchain '"+name+"'; supply --toolchains CATALOG.json");
      BuildOptions native;native.target=text(c,"target");native.toolchain=selected->second;configureNative(native);
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
    else if(kind=="build"&&text(c,"target")=="web"&&optional(c,"mode","application")=="application"){
      for(const auto &f:p.functions)if(f.owner==p.module&&(f.localName=="initial"||f.localName=="update"||f.localName=="view"||f.localName=="title"||f.localName=="route"||f.localName=="commands"))function(f.name);
    }else function(optional(c,"entry",p.module+"::"+(text(c,"target")=="server"?"handle":"main")));
    covered[id]=reach(p,roots);structures[id]=types(p,covered[id]);
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
  }return files;
}
Object fileIndex(const fs::path &root){Object files;uint64_t bytes=0;for(const auto &e:fs::recursive_directory_iterator(root)){if(e.is_symlink())throw Error("E_TASK_INTEGRITY","symlink in saved artifact");if(!e.is_regular_file())continue;bytes+=e.file_size();if(bytes>256*1048576||files.size()>=8192)invalid("artifact size/count limit exceeded");auto data=readFile(e.path().string());files[e.path().lexically_relative(root).generic_string()]=Object{{"hash",hash(data)},{"bytes",int64_t(data.size())}};}return files;}
void saveInputs(const Prepared &p,const fs::path &directory,const TaskOptions &options){
  writeFile((directory/"inputs/task.json").string(),json(p.task)+"\n");
  for(const auto &[id,candidate]:p.programs)writeFile((directory/("inputs/programs/"+id+".json")).string(),json(candidate.bundle)+"\n");
  for(const auto &[id,contract]:p.contracts)writeFile((directory/("inputs/contracts/"+id+".json")).string(),json(contract)+"\n");
  for(const auto &[id,snapshot]:p.toolchains){writeFile((directory/"inputs/toolchains"/id/"config.json").string(),json(snapshot.manifest)+"\n");writeFile((directory/"inputs/toolchains"/id/"identity.json").string(),json(snapshot.inputs)+"\n");}
  for(const auto &[name,data]:resources())writeFile((directory/"inputs/resources"/name).string(),data);
  auto files=fileIndex(directory/"inputs");Object indexed;uint64_t bytes=0;for(auto &[name,v]:files){bytes+=*object(v).getInteger("bytes");indexed["inputs/"+name.str()]=std::move(v);}if(bytes>128*1048576)invalid("task input snapshot exceeds 128 MiB");
  atomic(directory/"inputs/manifest.json",Object{{"schema","nex.task-inputs/1"},{"task_hash",p.taskHash},{"compiler_build",NEX_BUILD_ID},{"compiler_hash",hash(readFile(options.compiler))},{"files",std::move(indexed)}});
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
  auto actual=fileIndex(directory/"inputs");if(actual.size()!=files.size()+1)throw Error("E_TASK_INTEGRITY","unindexed task inputs");
  for(const auto &[name,_]:actual)if(name!="manifest.json"&&!files.get("inputs/"+name.str()))throw Error("E_TASK_INTEGRITY","unindexed task input");
  return manifest;
}
JSON summary(const Prepared &p){Array programs,checks;for(const auto &[id,c]:p.programs)programs.push_back(Object{{"id",id},{"revision",c.revision},{"source_hash",c.sourceHash}});bool ready=true;for(const auto &v:array(object(p.task),"checks")){const auto &c=object(v);bool available=supported(p,c);if(text(c,"kind")=="test")for(const auto &test:array(c,"tests")){auto realm=p.programs.at(text(c,"program")).program.function(text(object(test),"symbol")).realm;if((text(c,"target")=="web"&&realm=="server")||(text(c,"target")=="native"&&realm=="client"))available=false;}ready&=available;checks.push_back(Object{{"id",text(c,"id")},{"status",available?"ready":"unsupported"}});}return Object{{"schema","nex.task-check/1"},{"ok",ready},{"task",p.id},{"task_hash",p.taskHash},{"programs",std::move(programs)},{"toolchains",toolchainValues(p)},{"checks",std::move(checks)},{"bindings",Object(p.linkage)},{"linkage","static reachability, not measured coverage or proof of natural-language requirements"}};}
std::string nonce(){return std::to_string(std::random_device{}())+"-"+std::to_string(std::random_device{}());}
struct Runner {
  Prepared &p;TaskOptions options;fs::path directory;Object report;bool interrupted=false;
  void verifyToolchain(const std::string &id){
    auto selected=p.checkTools.find(id);if(selected==p.checkTools.end())return;
    BuildOptions native;native.toolchain=inside(directory,"inputs/toolchains/"+selected->second+"/config.json").string();
    auto current=inspectNativeToolchain(native);const auto &expected=p.toolchains.at(selected->second);
    if(current.hash!=expected.hash||json(current.manifest,false)!=json(expected.manifest,false))throw Error("E_TASK_TOOLCHAIN","captured toolchain inputs changed during execution: "+selected->second);
  }
  JSON command(const std::string &id,const std::string &program,const std::vector<std::string> &args,unsigned timeout,const std::string &label){
    const auto &candidate=p.programs.at(program);auto workspace=directory/"workspaces"/program;
    std::vector<std::string> command{options.compiler};command.insert(command.end(),args.begin(),args.end());
    if(p.checkTools.contains(id)&&!args.empty()&&(args[0]=="build"||args[0]=="test"||args[0]=="run"||args[0]=="profile"))command.insert(command.end(),{"--toolchain",(directory/"inputs/toolchains"/p.checkTools.at(id)/"config.json").string()});
    command.insert(command.end(),{"--revision",candidate.revision,"--build-directory",(fs::path(options.root)/".nex/build").string(),"--json"});
    auto relative="logs/"+id+"/"+label;auto process=runTaskProcess(command,workspace.string(),{{"NEX_RESOURCE_DIR",(directory/"inputs/resources").string()},{"NEX_TRACY","0"}},timeout,(directory/relative).string());
    Object result{{"command",Array{}},{"exit_code",process.process.code},{"stdout",relative+"/stdout"},{"stderr",relative+"/stderr"},{"timed_out",process.timedOut},{"output_limit",process.outputLimit},{"interrupted",process.interrupted}};
    for(const auto &arg:command)result.getArray("command")->push_back(arg);
    if(process.interrupted){interrupted=true;report["signal"]=process.interrupted;}
    JSON response=nullptr;if(!process.outputLimit){auto parsed=llvm::json::parse(process.process.output);if(parsed)response=std::move(*parsed);else llvm::consumeError(parsed.takeError());}
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
    if(!supported(p,c)){row["status"]="unsupported";row["reason"]="target is not configured on this host";return row;}
    auto started=std::chrono::steady_clock::now();auto timeout=number(c,"timeout_seconds",60);auto artifact=directory/"artifacts"/id;fs::create_directories(artifact);
    auto invoke=[&](std::vector<std::string> args,const std::string &label){verifyToolchain(id);auto elapsed=std::chrono::duration_cast<std::chrono::seconds>(std::chrono::steady_clock::now()-started).count();if(elapsed>=timeout)throw Error("E_TASK_TIMEOUT","check exhausted its process timeout");auto value=command(id,program,args,timeout-unsigned(elapsed),label);verifyToolchain(id);if(!ok(value))throw Error(interrupted?"E_TASK_INTERRUPTED":object(value).getBoolean("timed_out").value_or(false)?"E_TASK_TIMEOUT":"E_TASK_OUTPUT","check process exceeded its execution/output limit");return value;};
    auto successful=[&](const JSON &v){return object(v).getInteger("exit_code")==0&&object(v).get("response")&&ok(*object(v).get("response"));};
    auto response=[&](const JSON &v)->const Object&{auto result=object(v).get("response");if(!result||!result->getAsObject())throw Error("E_TASK_PROCESS","compiler did not produce a JSON response");return object(*result);};
    auto entry=optional(c,"entry",source.module+"::"+(target=="server"?"handle":"main"));
    bool passed=false;
    if(kind=="test"){
      passed=true;Array results;unsigned index=0;for(const auto &v:array(c,"tests")){auto name=text(object(v),"symbol");const auto &f=source.function(name);if((target=="web"&&f.realm=="server")||(target=="native"&&f.realm=="client")){row["status"]="unsupported";row["reason"]="selected test realm is unavailable on the requested target";return row;}
        auto value=invoke({"test","--symbol",name,"--target",target},"test-"+std::to_string(index++));bool found=false;if(successful(value)){auto tests=response(value).getArray("tests");if(tests)for(const auto &r:*tests)if(object(r).getString("name")==name&&ok(r)&&!object(r).getBoolean("skipped").value_or(false))found=true;}passed&=found;results.push_back(Object{{"symbol",name},{"ok",found},{"receipt",text(object(value),"receipt")}});if(interrupted)break;}
      row["tests"]=std::move(results);
    }else if(kind=="effects"){
      auto allowed=strings(c,"allowed_effects",0);auto realms=c.get("allowed_realms")?strings(c,"allowed_realms"):std::vector<std::string>{"shared","client","server"};std::set<std::string> roots;for(const auto &s:strings(c,"symbols"))roots.insert(s);Array violations;
      for(const auto &name:reach(source,roots)){const auto &f=source.function(name);for(const auto &e:f.effects)if(std::find(allowed.begin(),allowed.end(),e)==allowed.end())violations.push_back(Object{{"symbol",name},{"effect",e}});if(std::find(realms.begin(),realms.end(),f.realm)==realms.end())violations.push_back(Object{{"symbol",name},{"realm",f.realm}});}passed=violations.empty();row["violations"]=std::move(violations);
    }else if(kind=="verify"){
      auto input=directory/("inputs/contracts/"+id+".json");auto value=invoke({"verify","--contracts",input.string(),"--directory",(artifact/"proof").string(),"--solver-timeout",std::to_string(number(c,"solver_timeout_ms",2000,1,60000)),"--resource-limit",std::to_string(number(c,"resource_limit",1000000,1,100000000)),"--timeout",std::to_string(std::min(timeout,300u))},"verify");passed=successful(value);row["receipt"]=text(object(value),"receipt");
    }else if(kind=="run"){
      auto reference=invoke({"eval","--entry",entry},"reference");auto native=invoke({"run","--entry",entry,"--profile",optional(c,"profile","debug")},"native");const auto &expected=*c.getObject("expect");const auto &r=response(reference);const auto &n=response(native);auto exit=number(expected,"exit_code",0,0,255);bool referenceMatch=false;
      if(auto error=expected.getString("runtime_code"))referenceMatch=r.getString("code")==error&&n.getString("stderr")&&n.getString("stderr")->starts_with(error->str()+":");
      else if(ok(*object(reference).get("response"))){auto value=r.get("value");int code=0;if(value&&!value->getAsNull()){auto v=value->getAsInteger();if(!v)invalid("run entry must return unit or i64");code=int(uint64_t(*v)&255);}referenceMatch=unsigned(code)==exit;}
      passed=referenceMatch&&r.getString("stdout")==expected.getString("stdout")&&n.getString("stdout")==expected.getString("stdout")&&n.getInteger("exit_code")==exit;
      row["reference"]=text(object(reference),"receipt");row["native"]=text(object(native),"receipt");
    }else if(kind=="profile"){
      if(auto hardware=c.getObject("hardware"))if(text(*hardware,"cpu")!=llvm::sys::getHostCPUName()||text(*hardware,"target")!=llvm::sys::getDefaultTargetTriple()){row["status"]="unsupported";row["reason"]="profile hardware differs from the approved measurement target";return row;}
      auto value=invoke({"profile","--entry",entry,"--events","0","--scenario",text(c,"scenario"),"--timeout",std::to_string(timeout),"--output",(artifact/"profile.json").string()},"profile");passed=successful(value);row["receipt"]=text(object(value),"receipt");
      if(passed){auto full=readJSON(artifact/"profile.json",64*1048576);const auto &r=object(full),&budget=*c.getObject("budget");Array failures;
        for(const auto &key:{"dropped_functions","dropped_frames","dropped_allocations","untracked_frees"})if(r.getInteger(key).value_or(1)!=0)failures.push_back(key);
        auto exceeds=[&](const std::string &key,int64_t observed){if(auto max=budget.get(key))if(observed<0||uint64_t(observed)>decimal(*max))failures.push_back(key);};exceeds("max_duration_ns",r.getInteger("duration_ns").value_or(-1));
        auto pools=r.getArray("memory");for(const auto &[name,key]:std::map<std::string,std::string>{{"NEX handles","max_peak_handles"},{"NEX objects (shallow)","max_peak_objects"}}){int64_t peak=-1;if(pools)for(const auto &pool:*pools)if(object(pool).getString("pool")==name)peak=object(pool).getInteger("peak_live").value_or(-1);exceeds(key,peak);}
        if(auto calls=budget.getObject("max_calls"))for(const auto &[name,max]:*calls){bool found=false;for(const auto &v:array(r,"functions",0,16384))if(object(v).getString("name")==name.str()){found=true;auto n=object(v).getInteger("calls");if(!n||*n<0||uint64_t(*n)>decimal(max))failures.push_back(name.str());}if(!found)failures.push_back(name.str()+":unobserved");}
        passed=failures.empty();row["budget_failures"]=std::move(failures);
      }
    }else if(kind=="api"){
      auto value=invoke({"api","--directory",(artifact/"generated").string()},"api");passed=successful(value);row["receipt"]=text(object(value),"receipt");
    }else if(kind=="build"){
      auto mode=optional(c,"mode","application");if(target=="web"&&mode=="library")invalid("web libraries use mode module");if(target!="web"&&mode=="module")invalid("module output requires target web");
      std::vector<std::string> args;
      if(mode=="module")args={"emit","--kind","typescript","--entry",entry,"--directory",(artifact/"module").string()};
      else {args={"build","--target",target,"--profile",optional(c,"profile","debug")};if(target!="web"){args.insert(args.end(),{"--entry",entry});if(mode=="library")args.push_back("--library");}}
      auto value=invoke(args,"build");passed=successful(value);row["receipt"]=text(object(value),"receipt");
      if(passed&&mode!="module"){const auto &r=response(value);if(target=="web")copyArtifact(text(r,"dist"),artifact/"dist");else {auto exe=fs::path(text(r,"executable"));copyArtifact(exe,artifact/exe.filename());auto notices=r.getString("notices").value_or("").str();if(!notices.empty())copyArtifact(notices,artifact/"THIRD_PARTY_NOTICES.txt");for(auto k:{"metadata","compilation","debug_manifest"})if(auto path=r.getString(k))if(fs::is_regular_file(path->str()))copyArtifact(path->str(),artifact/(std::string(k)+".json"));}}
    }
    row["status"]=passed?"passed":"failed";row["artifacts"]=fileIndex(artifact);return row;
  }
  void checkpoint(Store &store){auto output=directory/"receipt.json";atomic(output,report);store.recordTask(text(report,"run_id"),p.id,p.taskHash,text(report,"status"),output.string(),hash(readFile(output.string())));}
  JSON run(const std::string &replayOf=""){
    Store store(fs::path(options.root)/".nex");auto inputs=readFile((directory/"inputs/manifest.json").string());report=Object{{"schema","nex.task-receipt/1"},{"run_id","run-"+nonce()},{"task",p.id},{"task_hash",p.taskHash},{"language",languageVersion},{"toolchain",NEX_VERSION},{"compiler_build",NEX_BUILD_ID},{"input_hash",hash(inputs)},{"status","running"},{"ok",false},{"checks",Array{}},{"bindings",Object(p.linkage)},{"programs",*object(summary(p)).get("programs")},{"replay_of",replayOf},{"toolchains",toolchainValues(p)},{"hardware",Object{{"cpu",llvm::sys::getHostCPUName().str()},{"target",llvm::sys::getDefaultTargetTriple()}}}};
    for(const auto &[id,candidate]:p.programs){auto workspace=directory/"workspaces"/id;writeFile((workspace/"nex.json").string(),json(Object{{"schema","nex.project/1"},{"language",languageVersion},{"entry",candidate.program.entryUnit}})+"\n");Store local(workspace/".nex");local.save(loadBundle(candidate.bundle,workspace.string()));}
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
fs::path runDirectory(const TaskOptions &options){auto directory=options.directory.empty()?fs::path(options.root)/".nex/tasks/runs"/("run-"+nonce()):fs::absolute(options.directory);fs::create_directories(directory.parent_path());if(!fs::create_directory(directory))throw Error("E_EXISTS","task run requires a new directory");return directory;}
}
JSON checkTask(const JSON &task,const TaskOptions &options){return summary(prepare(task,options));}
JSON runTask(const JSON &task,const TaskOptions &options){auto p=prepare(task,options);auto directory=runDirectory(options);saveInputs(p,directory,options);Runner runner{p,options,directory,{}};return runner.run();}
JSON replayTask(const std::string &receipt,const TaskOptions &options){
  auto path=fs::absolute(receipt);auto old=path.parent_path();auto saved=readJSON(path,32*1048576);const auto &r=object(saved);if(text(r,"schema")!="nex.task-receipt/1")invalid("expected a task receipt");auto manifest=verifyInputs(old,options,digest(r,"input_hash"));auto task=readJSON(old/"inputs/task.json");if(hash(json(task,false))!=text(object(manifest),"task_hash")||text(r,"task_hash")!=text(object(manifest),"task_hash"))throw Error("E_TASK_INTEGRITY","task identity differs from inputs");
  if(!options.revision.empty()||!options.candidates.empty())invalid("replay uses captured candidates");auto p=prepare(task,options,old);auto directory=runDirectory(options);
  for(const auto &[name,_]:object(*object(manifest).get("files"))){auto destination=directory/name.str();fs::create_directories(destination.parent_path());copyFile(inside(old,name.str()).string(),destination.string());}
  atomic(directory/"inputs/manifest.json",manifest);Runner runner{p,options,directory,{}};return runner.run(path.string());
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
