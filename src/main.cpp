#include "nex/backend.h"
#include "nex/native_toolchain.h"
#include "nex/project.h"
#include "nex/web.h"
#include "nex/api.h"
#include "nex/profiling.h"
#include "nex/verification.h"
#include "nex/tasks.h"
#include "nex/debugging.h"
#include "nex/packaging.h"
#include "llvm/Support/FileSystem.h"
#include "llvm/Support/Program.h"
#include "llvm/Support/Error.h"
#include "llvm/Support/RandomNumberGenerator.h"
#include "llvm/Support/SHA256.h"
#include "nex_auth.h"
#include "nex_json.h"
#include "llvm/Config/llvm-config.h"
#include "llvm/TargetParser/Host.h"
#include <filesystem>
#include <iostream>
#include <algorithm>
#include <functional>

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
  const std::set<std::string> flagNames={"--json","--interpreter-only","--library","--dpkg-notices"};
  const std::set<std::string> valueNames={"--profile","--target","--toolchain","--toolchains","--entry","--kind","--revision","--steps","--patch","--symbol","--output","--directory","--user","--auth","--events","--timeout","--scenario","--contracts","--solver-timeout","--resource-limit","--build-directory","--candidates","--task-hash","--manifest","--expression","--operation","--site","--offset","--limit","--notices"};
  for(int i=2;i<argc;++i){
    std::string a=argv[i];if(a=="--"){while(++i<argc)o.extra.push_back(argv[i]);break;}
    if(a=="-o")a="--output";
    if(flagNames.contains(a))o.flags.insert(a);
    else if(valueNames.contains(a)){if(i+1==argc)throw Error("E_OPTION","missing value for "+a);o.values[a]=argv[++i];}
    else if(a.starts_with("-"))throw Error("E_OPTION","unknown option "+a);
    else o.positional.push_back(a);
  }
  if(o.positional.size()>1)throw Error("E_OPTION","expected at most one source file or directory");return o;
}
void print(llvm::json::Value value){std::cout<<json(value)<<'\n';}
llvm::json::Value parseJSON(const std::string &text) {
  auto value=llvm::json::parse(text);if(!value)throw Error("E_JSON",llvm::toString(value.takeError()));return std::move(*value);
}
std::string required(const llvm::json::Object &object,const std::string &key){auto v=object.getString(key);if(!v)throw Error("E_JSON","missing string '"+key+"'");return v->str();}
std::string defaultSource(const fs::path &root){
  if(fs::exists(root/"nex.json")){auto value=parseJSON(readFile((root/"nex.json").string()));auto obj=value.getAsObject();if(!obj)throw Error("E_MANIFEST","manifest must be an object");return (root/required(*obj,"entry")).string();}
  return (root/"main.nex").string();
}
llvm::json::Value graphSources(const llvm::json::Object &object){
  if(auto bundle=object.get("bundle"))return *bundle;
  auto source=required(object,"source");
  return llvm::json::Object{{"schema","nex.sources/1"},{"entry","main.nex"},{"files",llvm::json::Object{{"main.nex",source}}}};
}
Program load(const Options &o,const fs::path &root,Store &store,bool saved=false) {
  auto rev=o.get("--revision",saved?"HEAD":"");
  if(rev.empty()){
    auto path=fs::absolute(o.positional.empty()?defaultSource(root):o.positional[0]).string();
    auto p=loadProgram(path,root.string(),o.command!="lock");store.save(p);return p;
  }
  auto selected=rev=="HEAD"?store.headRevision():rev;
  if(store.revisionLanguage(selected)!=languageVersion)throw Error("E_LANGUAGE_VERSION","stored revision uses another language version; run nex migrate or export its source and check it");
  auto p=loadBundle(store.bundle(selected),root.string());
  if(revision(p)!=selected)throw Error("E_REVISION","stored source does not match its semantic revision");return p;
}
int run(const Options &o) {
  if((o.values.contains("--notices")||o.has("--dpkg-notices"))&&o.command!="package")throw Error("E_OPTION","--notices and --dpkg-notices are for native package");
  if(o.command=="package"){
    if(o.get("--directory").empty())throw Error("E_OPTION","package requires --directory NEW_DIRECTORY");
    if(o.get("--target")=="web"||o.has("--interpreter-only")||o.has("--library")||o.values.contains("--output")||o.values.contains("--kind")||!o.extra.empty())
      throw Error("E_OPTION","package builds a native executable/server; use --directory for its output");
    auto output=fs::absolute(o.get("--directory")).lexically_normal();
    if(fs::exists(output)||fs::is_symlink(output))throw Error("E_EXISTS","package requires a new output directory");
  }
  if(o.values.contains("--toolchains")&&o.command!="task")throw Error("E_OPTION","--toolchains FILE is for task check/run/replay");
  if(o.values.contains("--toolchain")){
    const std::set<std::string> nativeCommands={"build","package","run","test","debug","profile","emit"};
    if(o.get("--toolchain").empty()||!nativeCommands.contains(o.command)||o.get("--target")=="web"||o.has("--interpreter-only")||(o.command=="emit"&&o.get("--kind")!="llvm"))
      throw Error("E_OPTION","--toolchain FILE selects a native build/package/run/test/debug/profile or emit --kind llvm");
  }
  if(o.command=="help"||o.command=="--help"||o.command=="-h") {
    std::cout<<"NEX "<<NEX_VERSION<<" (language "<<languageVersion<<")\n"
      "  nex init [directory]\n  nex describe [--json]\n  nex guide --kind prompt|language|grammar|protocol|web|server|api|debug|build|profile|verify|task|expression|operation|linux|match|function|files [--json]\n  nex doctor\n  nex toolchain FILE [--json]\n"
      "  nex check|eval|build|run|test|emit [file] [--json]\n  nex package [file] --directory NEW [--target server] [--notices FILE] [--dpkg-notices] [--json]\n  nex profile [file] [--events COUNT] [--timeout SECONDS] [--scenario TEXT] [-o REPORT.json] [--json]\n  nex contract [file] --symbol NAME [-o CONTRACT.json]\n  nex verify [file] --contracts FILE [--symbol NAME] [--solver-timeout MS] [--resource-limit COUNT] [--timeout SECONDS] [--json]\n"
      "  nex graph|history [--json]\n  nex context --symbol NAME | --operation ID | --site KEY\n  nex operations --symbol NAME [--offset N] [--limit N] [--json]\n"
      "  nex apply --patch FILE\n  nex export --revision HEAD -o FILE\n"
      "  nex import FILE\n  nex migrate [GRAPH.json] [--revision HASH]\n  nex lock [file]\n  nex export --directory PATH\n  nex web [file] --directory PATH\n  nex api [file] [--directory PATH]\n  nex token --user USER --auth FILE\n  nex debug [file] [--kind lldb|dap|nex-dap] [--json] -- [lldb options]\n"
      "  nex inspect [FRAME.json] --manifest DEBUG.json --expression TEXT [--kind plan|demand|value] [--steps COUNT] [--json]\n"
      "  nex task SOURCE --kind init [-o TASK.json]\n  nex task TASK.json --kind check|run|history [--task-hash HASH] [--revision HASH | --candidates FILE]\n  nex task RECEIPT.json --kind replay [--directory NEW_RUN] [--toolchains CATALOG.json]\n  nex contract --kind intent --contracts FILE\n"
      "Options: --profile debug|profile|release --entry NAME --target native|TRIPLE|web|server --toolchain FILE\n"
      "         --kind mlir|llvm|typescript --revision HASH --steps COUNT --interpreter-only --library --build-directory PATH\n";return 0;
  }
  if(o.command=="describe"){print(describe());return 0;}
  if(o.command=="toolchain"){
    if(o.positional.empty())throw Error("E_OPTION","toolchain requires a configuration file");
    BuildOptions options;options.toolchain=o.positional[0];auto snapshot=inspectNativeToolchain(options);
    print(llvm::json::Object{{"schema","nex.toolchain-report/1"},{"ok",true},{"hash",snapshot.hash},{"target",snapshot.target},{"host_compatible",snapshot.hostCompatible},{"manifest",std::move(snapshot.manifest)},{"inputs",std::move(snapshot.inputs)}});return 0;
  }
  if(o.command=="inspect"){
    auto path=o.get("--manifest"),expression=o.get("--expression");if(path.empty()||expression.empty())throw Error("E_OPTION","inspect requires --manifest FILE and --expression TEXT");
    auto kind=o.get("--kind","value");if(kind!="plan"&&kind!="value"&&kind!="demand")throw Error("E_OPTION","inspect kind must be plan, demand or value");std::string frame;
    if(!o.positional.empty()){auto file=o.positional[0];if(!fs::is_regular_file(file)||fs::file_size(file)>1048576)throw Error("E_DEBUG_LIMIT","frame file exceeds 1 MiB or is missing");frame=readFile(file);}
    else {char buffer[4096];while(std::cin.read(buffer,sizeof(buffer))||std::cin.gcount()){if(frame.size()+std::cin.gcount()>1048576)throw Error("E_DEBUG_LIMIT","stdin frame exceeds 1 MiB");frame.append(buffer,std::cin.gcount());}}
    uint64_t steps=100000;auto raw=o.get("--steps");if(!raw.empty()){steps=0;for(char c:raw){if(c<'0'||c>'9'||steps>(1000000-unsigned(c-'0'))/10)throw Error("E_OPTION","expression step limit must be 1..1000000");steps=steps*10+unsigned(c-'0');}if(!steps||steps>1000000)throw Error("E_OPTION","expression step limit must be 1..1000000");}
    std::cout<<json(inspectExpression(path,parseDebugFrame(frame),expression,kind=="plan",steps,kind=="demand"),false)<<'\n';return 0;
  }
  if(o.command=="contract"&&o.get("--kind")=="intent"){
    auto path=o.get("--contracts");if(path.empty()||!fs::is_regular_file(path)||fs::file_size(path)>1048576)throw Error("E_OPTION","intent requires a bounded --contracts JSON file");
    auto value=parseJSON(readFile(path));print(llvm::json::Object{{"schema","nex.verification-intent/1"},{"intent_hash",verificationIntentHash(value)}});return 0;
  }
  if(o.command=="task"){
    if(o.positional.empty())throw Error("E_OPTION","task requires a source, task or receipt path");auto path=fs::absolute(o.positional[0]);auto root=projectRoot(path.parent_path());
    TaskOptions options{root.string(),o.compiler,o.get("--revision"),o.get("--directory"),o.get("--task-hash"),{}, {}};
    if(o.values.contains("--toolchains")){
      auto file=fs::absolute(o.get("--toolchains"));if(!fs::is_regular_file(file)||fs::file_size(file)>65536)throw Error("E_OPTION","toolchain catalog requires a JSON file of at most 64 KiB");
      auto map=parseJSON(readFile(file.string()));auto catalog=map.getAsObject();if(!catalog||catalog->empty()||catalog->size()>16)throw Error("E_OPTION","toolchain catalog must map 1..16 IDs to trusted configuration paths");
      for(const auto &[id,v]:*catalog){auto name=id.str();auto path=v.getAsString();if(name.empty()||name.size()>64||!std::all_of(name.begin(),name.end(),[](unsigned char c){return (c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')||c=='_'||c=='-';})||!path||path->empty()||path->size()>8192||path->contains('\0'))throw Error("E_OPTION","invalid toolchain catalog ID/path");
        fs::path manifest(path->str());if(manifest.is_relative())manifest=file.parent_path()/manifest;options.toolchains[name]=manifest.lexically_normal().string();}
    }
    if(!o.get("--candidates").empty()){auto file=o.get("--candidates");if(!fs::is_regular_file(file)||fs::file_size(file)>1048576)throw Error("E_OPTION","candidate map requires a bounded JSON file");auto map=parseJSON(readFile(file));auto object=map.getAsObject();if(!object||object->size()>8)throw Error("E_OPTION","candidate file must map program IDs to archived revisions");for(const auto &[id,v]:*object){auto revision=v.getAsString();if(!revision)throw Error("E_OPTION","candidate revision must be a string");options.candidates[id.str()]=revision->str();}}
    auto kind=o.get("--kind","check");
    if(kind=="init"){
      auto p=loadProgram(path.string(),root.string());Store store(root/".nex");store.save(p,"",false);auto result=taskTemplate(p,p.entryUnit);auto output=o.get("--output");
      if(output.empty())print(std::move(result));else {if(fs::exists(output))throw Error("E_EXISTS","task init requires a new output file");writeFile(output,json(result)+"\n");print(llvm::json::Object{{"ok",true},{"output",fs::absolute(output).string()},{"task_hash",hash(json(result,false))}});}return 0;
    }
    if(kind=="replay"){auto result=replayTask(path.string(),options);auto object=result.getAsObject();auto code=object->getInteger("signal");auto success=object->getBoolean("ok").value_or(false);print(std::move(result));return code?128+int(*code):success?0:1;}
    if(!fs::is_regular_file(path)||fs::file_size(path)>1048576)throw Error("E_TASK","missing or oversized task JSON");auto task=parseJSON(readFile(path));
    if(kind=="history"){auto object=task.getAsObject();if(!object)throw Error("E_TASK","task must be an object");Store store(root/".nex");print(store.taskHistory(required(*object,"id")));return 0;}
    if(kind!="check"&&kind!="run")throw Error("E_OPTION","task kind must be init, check, run, replay or history");
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
    const std::map<std::string,std::string> files={{"prompt","llm/SYSTEM_PROMPT.md"},{"language","docs/language.md"},{"grammar","docs/grammar.ebnf"},{"protocol","docs/protocol.md"},{"web","docs/web.md"},{"server","docs/server.md"},{"api","docs/api.md"},{"debug","docs/debugging.md"},{"build","docs/incremental.md"},{"profile","docs/profiling.md"},{"verify","docs/verification.md"},{"task","docs/tasks.md"},{"expression","docs/expressions.md"},{"operation","docs/operations.md"},{"linux","docs/linux.md"},{"match","docs/matching.md"},{"function","docs/functions.md"},{"files","docs/files.md"},{"bytes","docs/bytes.md"},{"resources","docs/resources.md"},{"ffi","docs/ffi-design.md"}};
    auto kind=o.get("--kind","prompt");if(!files.contains(kind))throw Error("E_OPTION","guide kind must be prompt, language, grammar, protocol, web, server, api, debug, build, profile, verify, task, expression, operation, linux, match, function, files, bytes, resources or ffi");
    auto text=readFile(resourceFile(files.at(kind)));
    if(o.has("--json"))print(llvm::json::Object{{"schema","nex.guide/1"},{"language",languageVersion},{"kind",kind},{"hash",hash(text)},{"text",text}});else std::cout<<text;return 0;
  }
  if(o.command=="doctor") {
    auto runtime=resourceFile("runtime/runtime.cpp");auto native=configureNative({});
    print(llvm::json::Object{{"schema","nex.doctor/1"},{"version",NEX_VERSION},{"language",languageVersion},{"llvm",LLVM_VERSION_STRING},{"host",llvm::sys::getDefaultTargetTriple()},{"native_compiler",native.compiler},{"native_archiver",native.archiver},{"native_debug_packager",native.debugPackager},{"native_linker",native.linker},{"sdk_manifest",native.sdkManifest},{"native_sqlite_include",native.sqliteInclude},{"native_sqlite_library",native.sqliteLibrary},{"native_openssl_include",native.opensslInclude},{"native_openssl_ssl",native.opensslSSL},{"native_openssl_crypto",native.opensslCrypto},{"runtime",runtime},{"runtime_available",fs::exists(runtime)},{"verifier","Z3"},{"verifier_version",verifierVersion()}});return 0;
  }
  if(o.command=="init") {
    fs::path root=fs::absolute(o.positional.empty()?".":o.positional[0]);
    if(fs::exists(root/"nex.json")||fs::exists(root/"src/main.nex"))throw Error("E_EXISTS","project already exists; refusing to overwrite");
    writeFile((root/"nex.json").string(),json(llvm::json::Object{{"schema","nex.project/1"},{"language",languageVersion},{"entry","src/main.nex"}})+"\n");
    writeFile((root/"src/main.nex").string(),
      "module app;\n\nfn sum(n: i64) -> i64 {\n  var total: i64 = 0;\n  var i: i64 = 1;\n  while i <= n {\n    total = total + i;\n    i = i + 1;\n  }\n  return total;\n}\n\nfn main() -> i64 !{io} {\n  print(sum(10));\n  return 0;\n}\n\ntest fn sum_test() -> unit {\n  assert(sum(10) == 55);\n  assert(sum(0) == 0);\n}\n");
    print(llvm::json::Object{{"ok",true},{"directory",root.string()}});return 0;
  }
  const std::set<std::string> commands={"check","eval","build","package","run","test","emit","graph","operations","context","history","apply","import","export","debug","migrate","lock","web","api","profile","contract","verify","ffi"};
  if(!commands.contains(o.command))throw Error("E_COMMAND","unknown command '"+o.command+"'");
  if(o.has("--library")&&o.command!="build"&&o.command!="emit")throw Error("E_OPTION","--library is supported by native build/emit");
  if(o.has("--library")&&o.get("--target")=="web")throw Error("E_OPTION","--library is a native archive target; use emit --kind typescript for a web module");
  const std::set<std::string> sourceCommands={"check","eval","build","package","run","test","emit","debug","lock","web","api","profile","contract","verify","ffi"};
  auto root=projectRoot(sourceCommands.contains(o.command)&&!o.positional.empty()?fs::absolute(o.positional[0]).parent_path():fs::current_path());Store store(root/".nex");
  if(o.command=="history"){print(store.history());return 0;}
  if(o.command=="migrate"){
    auto previous=store.headRevision();std::string original;llvm::json::Value bundle=nullptr;
    if(o.positional.empty()){original=o.get("--revision","HEAD");if(original=="HEAD")original=previous;bundle=store.bundle(original);}
    else{
      auto value=parseJSON(readFile(o.positional[0]));auto obj=value.getAsObject();
      if(!obj||(required(*obj,"schema")!="nex.graph/1"&&required(*obj,"schema")!="nex.graph/2"))throw Error("E_SCHEMA","expected an exported NEX graph");
      bundle=graphSources(*obj);original=required(*obj,"revision");
    }
    auto p=loadBundle(bundle,root.string());auto rev=store.save(p,previous.empty()?"EMPTY":previous);
    print(llvm::json::Object{{"schema","nex.migration/1"},{"ok",true},{"declared_original_revision",original},{"revision",rev},{"language",languageVersion},{"materialized",false}});return 0;
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
    auto rev=store.save(p);print(llvm::json::Object{{"ok",true},{"revision",rev}});return 0;
  }
  if(o.command=="apply") {
    auto patchFile=o.get("--patch");if(patchFile.empty())throw Error("E_OPTION","apply requires --patch FILE");
    auto value=parseJSON(readFile(patchFile));auto obj=value.getAsObject();if(!obj)throw Error("E_JSON","patch must be an object");
    auto expected=required(*obj,"expected_revision");if(expected.empty())throw Error("E_JSON","expected_revision cannot be empty");
    auto replacements=obj->getArray("replacements");if(!replacements||replacements->empty())throw Error("E_JSON","replacements must be a nonempty array");
    auto selected=store.headRevision();
    if(store.revisionLanguage(selected)!=languageVersion)throw Error("E_LANGUAGE_VERSION","run nex migrate before applying patches to an older graph");
    auto p=loadBundle(store.bundle(selected),root.string());
    if(revision(p)!=selected)throw Error("E_REVISION","stored source snapshot is corrupt");
    struct Replacement{size_t begin,end;std::string source;};
    std::map<std::string,std::vector<Replacement>> edits;std::set<std::string> names;
    for(const auto &item:*replacements){
      auto entry=item.getAsObject();if(!entry)throw Error("E_JSON","replacement must be an object");
      auto name=required(*entry,"name"),source=required(*entry,"source");
      const Endpoint *endpoint=nullptr;for(const auto &candidate:p.endpoints)if(candidate.name==name||(candidate.owner==p.module&&candidate.localName==name))endpoint=&candidate;
      auto symbol=endpoint?endpoint->name:p.function(name).name;
      if(!names.insert(symbol).second)throw Error("E_JSON","duplicate replacement");
      auto fragment=parse("module fragment;\n"+source,"<patch>");
      if(endpoint){
        if(fragment.endpoints.size()!=1||fragment.endpoints[0].name!=endpoint->localName||!fragment.functions.empty()||!fragment.structures.empty()||!fragment.imports.empty())throw Error("E_PATCH","replacement must define exactly the named local endpoint");
        edits[endpoint->unit].push_back({endpoint->span.begin,endpoint->span.end,source});
      }else{
        const auto &f=p.function(name);
        if(!f.templateName.empty())throw Error("E_PATCH_SPECIALIZATION","replace the source template '"+f.templateName+"'; specializations are derived",f.span);
        if(f.closure)throw Error("E_PATCH_CLOSURE","replace the source owner '"+f.closureOwner+"'; closures are derived",f.span);
        if(fragment.functions.size()!=1||fragment.functions[0].name!=f.localName||!fragment.structures.empty()||!fragment.imports.empty()||!fragment.endpoints.empty())throw Error("E_PATCH","replacement must define exactly the named local function");
        edits[f.unit].push_back({f.span.begin,f.span.end,source});
      }
    }
    auto bundle=sourceBundle(p);auto files=bundle.getAsObject()->getObject("files");
    for(auto &[key,changes]:edits){
      std::sort(changes.begin(),changes.end(),[](const auto &a,const auto &b){return a.begin>b.begin;});
      auto source=p.units.at(key).source;for(const auto &e:changes)source.replace(e.begin,e.end-e.begin,e.source);(*files)[key]=source;
    }
    auto candidate=loadBundle(bundle,root.string());auto rev=store.save(candidate,expected);
    print(llvm::json::Object{{"schema","nex.patch-result/1"},{"ok",true},{"revision",rev},{"materialized",false},{"next","build --revision HEAD; export to materialize the source snapshot"}});return 0;
  }
  bool saved=o.command=="graph"||o.command=="context"||o.command=="operations";auto p=load(o,root,store,saved);
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
    for(const auto &endpoint:p.endpoints)if(endpoint.name==name||(endpoint.owner==p.module&&endpoint.localName==name)){
      const auto &handler=p.function(endpoint.target);auto descriptor=describeAPI(p);llvm::json::Value contract=nullptr;
      for(const auto &item:*descriptor.getAsObject()->getArray("endpoints"))if(item.getAsObject()->getString("name")==endpoint.name)contract=item;
      llvm::json::Array structures;std::set<std::string> seen;
      std::function<void(const Type&)> include=[&](const Type &t){if(t.element)include(*t.element);if(t.kind==Type::Function)for(const auto &argument:t.arguments)include(argument);if(t.kind==Type::Record&&seen.insert(t.name).second){const auto &s=p.structure(t.name);structures.push_back(llvm::json::Object{{"name",s.name},{"source",p.definition(s)},{"file",s.unit}});for(const auto &argument:s.typeArguments)include(argument);for(auto field:s.members())include(field->type);}};
      for(const auto &param:handler.params)include(param.type);include(handler.result);
      llvm::json::Array imports;for(const auto &dependency:p.units.at(endpoint.unit).imports)imports.push_back(llvm::json::Object{{"alias",dependency.alias},{"file",dependency.target},{"module",p.units.at(dependency.target).module}});
      print(llvm::json::Object{{"schema","nex.context/2"},{"kind","endpoint"},{"language",languageVersion},{"revision",revision(p)},{"symbol",endpoint.name},{"local_name",endpoint.localName},{"module",endpoint.owner},{"file",endpoint.unit},{"source",p.definition(endpoint)},{"definition",canonical(endpoint)},{"contract",std::move(contract)},{"imports",std::move(imports)},{"handler",llvm::json::Object{{"name",handler.name},{"source",p.definition(handler)},{"file",handler.unit}}},{"structures",std::move(structures)}});return 0;
    }
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
    print(llvm::json::Object{{"schema","nex.context/2"},{"language",languageVersion},{"revision",revision(p)},{"symbol",f.name},{"local_name",f.localName},{"module",f.owner},{"file",f.unit},{"native_symbol",nativeSymbol(f.name)},{"source",p.definition(f)},{"type_parameters",std::move(parameters)},{"type_bounds",canonicalBounds(f.typeParameters,f.typeBounds)},{"template",f.templateName},{"type_arguments",std::move(arguments)},{"editable",f.templateName.empty()&&!f.closure},{"closure_owner",f.closureOwner},{"captures",std::move(captures)},{"imports",std::move(imports)},{"callees",std::move(callees)},{"callers",std::move(callers)},{"structures",std::move(structures)}});return 0;
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
  if(o.command=="eval") {
    uint64_t limit=1000000;
    if(!o.get("--steps").empty()){try{size_t used;auto raw=o.get("--steps");limit=std::stoull(raw,&used);if(used!=raw.size()||raw.starts_with("-"))throw std::invalid_argument("steps");}catch(...){throw Error("E_OPTION","--steps requires a nonnegative integer");}}
    Evaluation result;
    try{result=evaluate(p,o.get("--entry","main"),limit);}catch(Error &error){
      if(!error.operationSite.empty()){auto mapped=store.operations(p,"",error.operationSite,0,1);error.operationId=(*mapped.getAsObject()->getArray("nodes"))[0].getAsObject()->getString("id")->str();}throw;
    }
    if(o.has("--json"))print(llvm::json::Object{{"ok",true},{"value",result.value},{"stdout",result.output},{"steps",int64_t(result.steps)}});else std::cout<<result.output;return 0;
  }
  if(o.command=="emit"&&o.get("--kind")=="typescript"){
    auto module=emitTypeScript(p,{{"entry",o.get("--entry","main")}});auto directory=o.get("--directory"),output=o.get("--output");
    if(!directory.empty()){writeWebModule(module,directory);print(llvm::json::Object{{"ok",true},{"directory",fs::absolute(directory).string()},{"revision",revision(p)}});}
    else if(output.empty())std::cout<<module.source;else writeFile(output,module.source);return 0;
  }
  if(o.get("--target")=="server"&&o.command=="test")throw Error("E_OPTION","use native test for server functions; --target server builds the HTTP entry");
  if(o.get("--target")=="server"&&o.command=="run"&&o.has("--json"))throw Error("E_OPTION","server is long-running; use build --json or run without --json");
  BuildOptions buildOptions{o.get("--profile",o.command=="package"?"release":"debug"),o.get("--target"),o.get("--entry",o.get("--target")=="server"?"handle":"main"),false,o.has("--library"),o.get("--toolchain")};
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
    profiling={o.get("--output"),o.get("--scenario"),count("--events",100000,0,1000000),count("--timeout",30,1,3600)};
    buildOptions.profile="profile";
  }
  auto directory=fs::absolute(o.get("--build-directory",(root/".nex/build").string())).string();
  if(o.command=="test") {
    int count=0;llvm::json::Array tests;
    auto selected=o.get("--symbol");if(!selected.empty()){const auto &f=p.function(selected);if(!f.test)throw Error("E_TEST","--symbol must select a test function");selected=f.name;}
    for(const auto &f:p.functions)if(f.test&&(selected.empty()||selected==f.name)){
      bool web=o.get("--target")=="web";
      if(web&&f.realm=="server"){tests.push_back(llvm::json::Object{{"name",f.name},{"skipped",true},{"reason","server test excluded from web target"}});continue;}
      auto expected=evaluate(p,f.name);bool native=!o.has("--interpreter-only");
      if(native){
        ProcessResult actual;
        if(web){
          auto module=emitTypeScript(p,{{"entry",f.name}});auto key=hash(module.source+readFile(resourceFile("web/nex-runtime.ts"))+NEX_BUILD_ID);
          auto folder=fs::path(directory)/key/"typescript";writeWebModule(module,folder.string());
          writeFile((folder/"package.json").string(),"{\"type\":\"module\"}\n");
          writeFile((folder/"test.ts").string(),"import { entry } from './program.ts';\nentry();\n");
          const char *node=std::getenv("NEX_NODE");actual=capture({node?node:"node","--experimental-strip-types","--no-warnings",(folder/"test.ts").string()});
        }else{auto opts=buildOptions;opts.entry=f.name;opts.testEntry=true;auto result=build(p,directory,opts);requireNativeHost(result);actual=capture({result.executable});}
        if(actual.code!=0||actual.output!=expected.output)throw Error("E_DIFFERENTIAL",std::string(web?"TypeScript":"native")+" test disagrees with interpreter: "+f.name+"\n"+actual.errors,f.span);}
      ++count;tests.push_back(llvm::json::Object{{"name",f.name},{"ok",true},{"native",native&&!web},{"web",native&&web}});
    }
    if(!count)throw Error("E_TEST","no tests found");
    if(o.has("--json"))print(llvm::json::Object{{"ok",true},{"tests",std::move(tests)}});else std::cout<<count<<" tests passed ("<<(o.has("--interpreter-only")?"interpreter":o.get("--target")=="web"?"interpreter + TypeScript":"interpreter + native")<<")\n";return 0;
  }
  if(o.command=="emit"&&o.get("--kind","mlir")=="mlir"){
    auto text=emitMLIR(p,buildOptions.entry,false,buildOptions.libraryEntry||buildOptions.target=="server");auto output=o.get("--output");if(output.empty())std::cout<<text;else writeFile(output,text);return 0;
  }
  if(o.command=="emit"&&o.get("--kind")!="llvm")throw Error("E_OPTION","--kind must be mlir, llvm or typescript");
  auto result=build(p,directory,buildOptions);
  if(o.command=="package"){
    print(packageApplication(p,result,{o.get("--directory"),o.get("--notices"),o.compiler,o.has("--dpkg-notices")}));return 0;
  }
  if(o.command=="run"||o.command=="debug"||o.command=="profile")requireNativeHost(result);
  if(o.command=="profile"){
    auto report=profileNative(p,result,store.graph(p),profiling);auto object=report.getAsObject();auto code=int(*object->getInteger("exit_code"));
    if(o.has("--json"))print(std::move(report));else std::cout<<"Profile: "<<object->getString("output")->str()<<" (exit "<<code<<")\n";return code;
  }
  if(o.command=="emit") {auto text=readFile(result.llvm);auto output=o.get("--output");if(output.empty())std::cout<<text;else writeFile(output,text);return 0;}
  if(o.command=="run") {
    if(!o.has("--json")){std::vector<std::string> arguments{result.executable};arguments.insert(arguments.end(),o.extra.begin(),o.extra.end());return execute(arguments);}
    auto child=capture({result.executable});print(llvm::json::Object{{"ok",child.code==0},{"exit_code",child.code},{"stdout",child.output},{"stderr",child.errors},{"build_key",result.key}});return child.code;
  }
  if(o.command=="debug") {
    auto kind=o.get("--kind","lldb");if(kind!="lldb"&&kind!="dap"&&kind!="nex-dap")throw Error("E_OPTION","debug kind must be lldb, dap or nex-dap");
    auto folder=fs::path(result.executable).parent_path();auto manifest=(folder/"debug.json").string();
    std::vector<std::string> init={"command script import "+json((folder/"debugger/lldb_nex.py").string(),false),"nex-load-debug "+json(manifest,false)+" --compiler "+json(o.compiler,false)};
    if(o.has("--json")||kind=="dap"||kind=="nex-dap"){
      llvm::json::Array commands;for(const auto &command:init)commands.push_back(command);
      auto backend=std::getenv("NEX_LLDB_DAP");std::string dap=backend?backend:"lldb-dap";auto found=llvm::sys::findProgramByName(dap);bool available=bool(found);if(found)dap=*found;
#ifdef __APPLE__
      if(!available&&!backend){auto result=capture({"xcrun","--find","lldb-dap"});if(result.code==0){dap=llvm::StringRef(result.output).trim().str();available=!dap.empty();}}
#endif
      llvm::json::Array adapterCommand{std::getenv("NEX_PYTHON")?std::getenv("NEX_PYTHON"):"python3",(folder/"debugger/nex_dap.py").string(),"--backend",dap};
      llvm::json::Object launch{{"type",kind=="nex-dap"?"nex":"lldb-dap"},{"request","launch"},{"name","NEX"},{"program",result.executable},{"cwd",root.string()},{"stopOnEntry",false},{"initCommands",std::move(commands)}};
      auto debugManifest=llvm::json::parse(readFile(manifest));
      if(!debugManifest||!debugManifest->getAsObject())throw Error("E_DEBUG","invalid build debug manifest");
      if(auto mappings=debugManifest->getAsObject()->getArray("source_map"))launch["sourceMap"]=llvm::json::Array(*mappings);
      auto nexLaunch=launch;nexLaunch["type"]="nex";
      llvm::json::Object session{{"schema","nex.debug-session/1"},{"ok",true},{"revision",revision(p)},{"build_key",result.key},{"manifest",manifest},{"adapter",kind=="nex-dap"?"nex-dap":"lldb-dap"},{"launch",std::move(launch)},
        {"nex_adapter",llvm::json::Object{{"schema","nex.dap-adapter/1"},{"available",available},{"command",llvm::json::Array(adapterCommand)},{"launch",std::move(nexLaunch)}}}};
      if(kind=="nex-dap")session["adapter_command"]=std::move(adapterCommand);print(std::move(session));return 0;
    }
    std::vector<std::string> args={"lldb",result.executable};for(const auto &command:init){args.push_back("-o");args.push_back(command);}args.insert(args.end(),o.extra.begin(),o.extra.end());return execute(args);
  }
  auto output=o.get("--output");if(!output.empty()){copyFile(result.executable,output,true);if(!buildOptions.libraryEntry)fs::permissions(output,fs::perms::owner_exec|fs::perms::group_exec|fs::perms::others_exec,fs::perm_options::add);}
  auto notices=result.notices;
  if(!output.empty()&&!notices.empty()){notices=fs::absolute(output).string()+".THIRD_PARTY_NOTICES.txt";copyFile(result.notices,notices,true);}
  if(o.has("--json"))print(llvm::json::Object{{"ok",true},{"executable",output.empty()?result.executable:fs::absolute(output).string()},{"kind",buildOptions.target=="server"?"http_server":buildOptions.libraryEntry?"static_library":"executable"},{"cached",result.cached},{"target",result.target},{"compiler_target",result.compilerTarget},{"host_compatible",result.hostCompatible},{"revision",revision(p)},{"build_key",result.key},{"mlir",result.mlir},{"llvm",result.llvm},{"notices",notices},{"metadata",(fs::path(result.executable).parent_path()/"build.json").string()},{"debug_manifest",(fs::path(result.executable).parent_path()/"debug.json").string()},{"compilation",result.compilation},{"compiled_modules",result.compiledModules},{"reused_modules",result.reusedModules},{ "compiled_functions",result.compiledFunctions},{"reused_functions",result.reusedFunctions}});
  else std::cout<<(result.cached?"Cached ":"Built ")<<(output.empty()?result.executable:output)<<'\n';return 0;
}
}
int main(int argc,char **argv) {
  bool machine=false;for(int i=1;i<argc;++i)if(std::string(argv[i])=="--json")machine=true;
  try{return run(options(argc,argv));}
  catch(const nex::Error &e){
    if(machine){llvm::json::Object diagnostic{{"schema","nex.diagnostic/1"},{"ok",false},{"code",e.code},{"message",e.what()},{"line",int64_t(e.span.line)},{"column",int64_t(e.span.column)},{"file",e.span.file},{"stdout",e.output}};if(!e.operationSite.empty()){diagnostic["operation_site"]=e.operationSite;diagnostic["revision"]=e.operationRevision;diagnostic["source_hash"]=e.operationSource;}if(!e.operationId.empty())diagnostic["operation_id"]=e.operationId;print(std::move(diagnostic));}
    else {std::cout<<e.output;std::cerr<<(e.span.file.empty()?"":e.span.file+":")<<e.code<<":"<<e.span.line<<":"<<e.span.column<<": "<<e.what()<<'\n';}return 1;
  }catch(const std::exception &e){if(machine)print(llvm::json::Object{{"ok",false},{"code","E_INTERNAL"},{"message",e.what()}});else std::cerr<<"E_INTERNAL: "<<e.what()<<'\n';return 1;}
}
