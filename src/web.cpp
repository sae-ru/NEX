#include "nex/web.h"
#include "nex/backend.h"
#include "nex/task_process.h"
#include "nex_task_limits.h"
#include "llvm/Support/Error.h"
#include <filesystem>
#include <cstdlib>

namespace nex {
namespace {
// Node's ESM file URLs reject literal backslashes in POSIX paths. Vite also
// normalizes them as separators. Keep the generated project at its real path,
// but execute identical files from an owned temporary directory when needed.
class ToolDirectory {
  std::filesystem::path original,temporary;
public:
  explicit ToolDirectory(const std::filesystem::path &directory):original(std::filesystem::absolute(directory)){
    namespace fs=std::filesystem;
    if(fs::weakly_canonical(original).string().find('\\')==std::string::npos)return;
    auto base=fs::canonical(fs::temp_directory_path());
    if(base.string().find('\\')!=std::string::npos)base=fs::canonical("/tmp");
    temporary=createTemporaryDirectory("nex-web",base.string());
  }
  ToolDirectory(const ToolDirectory&)=delete;
  ToolDirectory& operator=(const ToolDirectory&)=delete;
  ~ToolDirectory(){if(!temporary.empty()){std::error_code ignored;std::filesystem::remove_all(temporary,ignored);}}
  const std::filesystem::path &path()const{return temporary.empty()?original:temporary;}
  bool relocated()const{return !temporary.empty();}
  void retain(const std::string &name){
    if(!relocated())return;
    namespace fs=std::filesystem;
    fs::remove_all(original/name);
    std::error_code error;fs::rename(temporary/name,original/name,error);
    if(error){fs::copy(temporary/name,original/name,fs::copy_options::recursive|fs::copy_options::copy_symlinks);}
  }
};
void requireFunction(const Function &f,const std::vector<Type> &params,const Type &result){
  if(f.effects.contains("task"))throw Error("E_TASK_UNIMPLEMENTED","the synchronous web application/worker adapter cannot invoke task functions",f.span);
  bool valid=!f.test&&f.realm!="server"&&f.effects.empty()&&f.result==result&&f.params.size()==params.size();
  if(valid)for(size_t i=0;i<params.size();++i)if(f.params[i].type!=params[i])valid=false;
  if(!valid)throw Error("E_WEB_SIGNATURE","invalid web application contract for "+f.name+"; see docs/web.md",f.span);
}
void requireStructure(const Program &p,const std::string &name,const std::vector<std::pair<std::string,Type>> &fields){
  if(!p.hasStructure(name))throw Error("E_WEB_SIGNATURE","web application requires type "+name);
  const auto &s=p.structure(name);bool valid=s.fields.size()==fields.size();
  if(valid)for(size_t i=0;i<fields.size();++i)if(s.fields[i].name!=fields[i].first||s.fields[i].type!=fields[i].second)valid=false;
  if(!valid)throw Error("E_WEB_SIGNATURE","incompatible web library type "+name,s.span);
}
struct Project {std::map<std::string,std::string> files;llvm::json::Value metadata;};
Project prepare(const Program &p){
  auto attribute=Type::record("std::web::Attribute"),binding=Type::record("std::web::Binding"),event=Type::record("std::web::Event"),view=Type::record("std::web::View");
  requireStructure(p,attribute.name,{{"name",Type::Str},{"value",Type::Str}});
  requireStructure(p,binding.name,{{"event",Type::Str},{"action",Type::Str}});
  requireStructure(p,event.name,{{"name",Type::Str},{"value",Type::Str},{"path",Type::Str}});
  requireStructure(p,view.name,{{"tag",Type::Str},{"text",Type::Str},{"attributes",Type::list(attribute)},{"events",Type::list(binding)},{"children",Type::list(view)}});
  const auto &initial=p.function("initial"),&update=p.function("update"),&render=p.function("view"),&title=p.function("title");
  if(initial.result==Type::Unit)throw Error("E_WEB_SIGNATURE","initial() must return application state",initial.span);
  auto state=initial.result;
  requireFunction(initial,{},state);requireFunction(update,{state,event},state);requireFunction(render,{state},view);requireFunction(title,{},Type::Str);
  std::map<std::string,std::string> entries={{"initial",initial.name},{"update",update.name},{"view",render.name},{"title",title.name}};
  const Function *commands=nullptr,*workerCompute=nullptr,*workerCommands=nullptr;
  for(const auto &f:p.functions)if(f.owner==p.module){
    if(f.localName=="commands")commands=&f;
    if(f.localName=="worker_compute")workerCompute=&f;
    if(f.localName=="worker_commands")workerCommands=&f;
  }
  // A new nominal command type opts into this host contract. Old applications
  // may already use either name for an ordinary helper; keep those valid.
  bool workerContract=workerCommands&&workerCommands->result.kind==Type::List&&workerCommands->result.element->kind==Type::Record&&p.structure(workerCommands->result.element->name).templateName=="std::worker::Command";
  if(!workerContract){workerCompute=nullptr;workerCommands=nullptr;}
  else if(!workerCompute)throw Error("E_WEB_SIGNATURE","typed worker_commands requires worker_compute");
  llvm::json::Value workerInput=nullptr,workerOutput=nullptr;
  if(workerCompute){
    if(workerCompute->params.size()!=1)throw Error("E_WEB_SIGNATURE","worker_compute requires one wire input",workerCompute->span);
    const auto &input=workerCompute->params[0].type;
    requireFunction(*workerCompute,{input},workerCompute->result);
    try{workerInput=wireSchema(p,input);workerOutput=wireSchema(p,workerCompute->result);}
    catch(const Error &e){throw Error("E_WEB_SIGNATURE",std::string("worker_compute requires wire input/output: ")+e.what(),workerCompute->span);}
    if(workerCommands->result.kind!=Type::List||workerCommands->result.element->kind!=Type::Record)throw Error("E_WEB_SIGNATURE","worker_commands must return list<worker::Command<Input>>",workerCommands->span);
    auto command=*workerCommands->result.element;const auto &s=p.structure(command.name);
    if(s.templateName!="std::worker::Command"||s.typeArguments!=std::vector<Type>{input})throw Error("E_WEB_SIGNATURE","worker command input must match worker_compute",workerCommands->span);
    requireStructure(p,command.name,{{"kind",Type::Str},{"id",Type::Str},{"input",Type::result(input)},{"action",Type::Str},{"timeout_ms",Type::I64}});
    requireFunction(*workerCommands,{state,state,event},Type::list(command));entries["worker_commands"]=workerCommands->name;
  }
  if(commands){
    auto command=Type::record("std::net::Command");
    requireStructure(p,command.name,{{"kind",Type::Str},{"id",Type::Str},{"method",Type::Str},{"path",Type::Str},{"body",Type::Str},{"token",Type::Str},{"action",Type::Str},{"timeout_ms",Type::I64}});
    requireStructure(p,"std::net::Response",{{"id",Type::Str},{"status",Type::I64},{"body",Type::result(Type::Str)}});
    requireFunction(*commands,{state,state,event},Type::list(command));entries["commands"]=commands->name;
  }
  auto module=emitTypeScript(p,entries);
  if(module.asynchronous)throw Error("E_TASK_UNIMPLEMENTED","the synchronous web application adapter cannot retain reachable task callables");
  // Names used by the renderer are explicit aliases; the source retains qualified nominal identities.
  module.source+="\nexport type State = ReturnType<typeof "+nativeSymbol(initial.name)+">;\nexport type View = ReturnType<typeof "+nativeSymbol(render.name)+">;\nexport type Event = Parameters<typeof "+nativeSymbol(update.name)+">[1];\n";
  module.source+="export function makeEvent(name: string, value: string, path: string): Event {\n  return nex.record<Event>('std::web::Event', [['name', nex.string(name)], ['value', nex.string(value)], ['path', nex.string(path)]]);\n}\n";
  if(commands)module.source+="export type Command = ReturnType<typeof "+nativeSymbol(commands->name)+">[number];\n";
  else module.source+="export type Command = nex.RecordValue & { readonly kind: string; readonly id: string; readonly method: string; readonly path: string; readonly body: string; readonly token: string; readonly action: string; readonly timeout_ms: bigint };\nexport function commands(_before: State, _after: State, _event: Event): ReadonlyArray<Command> { return nex.list<Command>([]); }\n";
  module.source+="export function makeResponseEvent(action: string, id: string, status: number, body: string, code: string, message: string, path: string): Event {\n  const payload = (content: nex.Result<string>) => nex.record('std::net::Response', [['id', nex.string(id)], ['status', nex.checked(BigInt(status))], ['body', content]]);\n  let encoded: string;\n  try { encoded = nex.encodeJSON(payload(code ? nex.err<string>(nex.string(code), nex.string(message)) : nex.ok(nex.string(body)))); }\n  catch (error) {\n    if (!(error instanceof nex.NexError) || error.code !== 'E_JSON') throw error;\n    encoded = nex.encodeJSON(payload(nex.err<string>('E_LIMIT', 'Response envelope exceeds wire limits')));\n  }\n  return makeEvent(action, encoded, path);\n}\n";
  std::map<std::string,std::string> files;
  module.source+="\nexport const workerEnabled = "+std::string(workerCompute?"true":"false")+";\n";
  if(workerCompute){
    module.source+="export type WorkerCommand = ReturnType<typeof "+nativeSymbol(workerCommands->name)+">[number];\n";
    auto worker=emitTypeScript(p,{{"compute",workerCompute->name}});
    if(worker.asynchronous)throw Error("E_TASK_UNIMPLEMENTED","the synchronous browser worker adapter cannot retain reachable task callables",workerCompute->span);
    files["src/worker-program.ts"]=worker.source;
    files["nex-worker-map.json"]=json(worker.mapping)+"\n";
    files["src/worker-contract.ts"]="import type { Schema } from './nex-runtime.ts';\nexport const inputSchema: Schema = "+json(workerInput,false)+";\nexport const outputSchema: Schema = "+json(workerOutput,false)+";\n";
    files["src/workers.ts"]=readFile(resourceFile("web/workers.ts"));
    files["src/worker-entry.ts"]=readFile(resourceFile("web/worker-entry.ts"));
  }else{
    module.source+="export type WorkerCommand = nex.RecordValue & { readonly kind: string; readonly id: string; readonly input: nex.Result<nex.Value>; readonly action: string; readonly timeout_ms: bigint };\nexport function worker_commands(_before: State, _after: State, _event: Event): ReadonlyArray<WorkerCommand> { return []; }\n";
    files["src/workers.ts"]="import type { WorkerCommand } from './program.ts';\nexport class WorkerRunner { constructor(_deliver: (action: string, id: string, body: string, code: string, message: string) => void) {} validate(_commands: ReadonlyArray<WorkerCommand>): void {} run(_commands: ReadonlyArray<WorkerCommand>): void {} close(): void {} }\n";
  }
  if(workerCompute)module.source+="import { outputSchema as workerOutputSchema } from './worker-contract.ts';\n";
  module.source+="export function makeWorkerResponseEvent(action: string, id: string, body: string, code: string, message: string, path: string): Event {\n  const value: nex.Result<nex.Value> = "+std::string(workerCompute?"code ? nex.err(code, message) : nex.decodeJSON<nex.Value>(body, workerOutputSchema)":"nex.err('E_WORKER', 'No worker handler configured')")+";\n";
  // Wire input is already checked by the runner. Encode the response envelope
  // without parsing numeric wire strings into JavaScript Number values.
  module.source+="  let encoded: string;\n  try { encoded = nex.encodeJSON(nex.record('std::worker::Response', [['id', id], ['value', value]])); }\n  catch (error) {\n    if (!(error instanceof nex.NexError) || error.code !== 'E_JSON') throw error;\n    encoded = nex.encodeJSON(nex.record('std::worker::Response', [['id', id], ['value', nex.err('E_LIMIT', 'Worker response envelope exceeds wire limits')]]));\n  }\n  return makeEvent(action, encoded, path);\n}\n";
  files["src/program.ts"]=module.source;
  files["src/nex-runtime.ts"]=readFile(resourceFile("web/nex-runtime.ts"));
  files["src/nex-bytes.ts"]=readFile(resourceFile("web/nex-bytes.ts"));
  files["nex-map.json"]=json(module.mapping)+"\n";
  const std::vector<std::string> rootFiles={"package.json","package-lock.json","tsconfig.json","vite.config.js","playwright.config.js","index.html"};
  for(const auto &file:rootFiles)files[file]=readFile(resourceFile("web/"+file));
  for(const auto &file:{"app.tsx","renderer.tsx","net.ts","urls.ts","app.css","vite-env.d.ts"})files["src/"+std::string(file)]=readFile(resourceFile("web/"+std::string(file)));
  files["tests/smoke.spec.js"]=readFile(resourceFile("web/smoke.spec.js"));
  files["public/THIRD_PARTY_NOTICES.txt"]=readFile(resourceFile("web/THIRD_PARTY_NOTICES.txt"));
  files["README.md"]="# Generated NEX web application\n\nEdit NEX sources and regenerate this directory.\n\nRun `npm ci --ignore-scripts`, `npm run build`, then `npm run preview`.\nThe `dist` directory contains the client application; configure SPA route fallback to index.html.\nNo NEX compiler or model is needed to serve/run the result.\n\nOptional pure commands(before, after, event) describes bounded same-origin /api/ requests and cancellation using std/net.nex. Responses return as typed JSON in ordinary web events. Configure credentials at runtime; no token is bundled by NEX. Serve this dist with the native HTTP server's --static option for a same-origin API. See the installed web/server guides for contracts and limits.\n";
  llvm::json::Object hashes;for(const auto &[name,text]:files)hashes[name]=hash(text);
  llvm::json::Value fileHashes=std::move(hashes);auto key=hash(json(fileHashes,false));
  llvm::json::Value metadata=llvm::json::Object{{"schema","nex.web/1"},{"language",programLanguage(p)},{"revision",revision(p)},{"key",key},{"files",std::move(fileHashes)}};
  return {std::move(files),std::move(metadata)};
}
void materialize(const Project &project,const std::filesystem::path &directory){
  for(const auto &[name,text]:project.files)writeFile((directory/name).string(),text);
  writeFile((directory/"nex-web.json").string(),json(project.metadata)+"\n");
}
llvm::json::Value distHashes(const std::filesystem::path &directory){
  llvm::json::Object result;
  if(!std::filesystem::is_regular_file(directory/"index.html"))return nullptr;
  for(const auto &file:std::filesystem::recursive_directory_iterator(directory))if(file.is_regular_file())result[file.path().lexically_relative(directory).generic_string()]=hash(readFile(file.path().string()));
  return result;
}
}
ProcessResult runTypeScriptTest(const WebModule &module,const std::string &directory,unsigned timeout,const nexrt::TaskExecutionLimits *limits){
  namespace fs=std::filesystem;
  if(limits&&!nexrt::validTaskExecutionLimits(*limits))throw Error("E_OPTION","invalid TypeScript task execution limits");
  std::string taskOptions;
  if(limits)taskOptions=", {steps: "+std::to_string(limits->steps)+", timeoutMs: "+std::to_string(limits->timeoutMs)+", workers: "+std::to_string(limits->workers)+"}";
  auto folder=fs::absolute(directory);writeWebModule(module,folder.string());
  writeFile((folder/"package.json").string(),"{\"type\":\"module\"}\n");
  writeFile((folder/"test.ts").string(),module.asynchronous?
    "import { entry } from './program.ts';\nimport * as task from './nex-task-runtime.ts';\nawait task.run(task.call(() => entry())"+taskOptions+");\n":
    "import { entry } from './program.ts';\nentry();\n");
  ToolDirectory runner(folder);
  if(runner.relocated())for(const auto *name:{"program.ts","nex-runtime.ts","nex-bytes.ts","nex-map.json","package.json","test.ts"})
    fs::copy_file(folder/name,runner.path()/name);
  if(runner.relocated()&&module.asynchronous)fs::copy_file(folder/"nex-task-runtime.ts",runner.path()/"nex-task-runtime.ts");
  const char *node=std::getenv("NEX_NODE");
  return capture({node?node:"node","--experimental-strip-types","--no-warnings",(runner.path()/"test.ts").string()},timeout);
}
llvm::json::Value previewWebApp(const std::string &directory,const std::vector<std::string> &arguments,unsigned timeout,bool machine){
  namespace fs=std::filesystem;
  if(!fs::is_regular_file(fs::path(directory)/"dist/index.html"))throw Error("E_WEB_TOOL","preview requires a completed web distribution");
  ToolDirectory runner(directory);
  if(runner.relocated())fs::copy(directory,runner.path(),fs::copy_options::recursive|fs::copy_options::copy_symlinks);
  const char *npm=std::getenv("NEX_NPM");
  std::vector<std::string> command{npm?npm:"npm","--prefix",runner.path().string(),"run","preview","--","--host","127.0.0.1"};
  command.insert(command.end(),arguments.begin(),arguments.end());
  if(!machine){auto code=execute(command);return llvm::json::Object{{"exit_code",code},{"ok",code==0}};}
  auto logs=createTemporaryDirectory("nex-web-preview");
  try{
    auto child=runTaskProcess(command,runner.path().string(),{},timeout,logs);fs::remove_all(logs);
    auto code=child.timedOut?124:child.outputLimit?125:child.process.code;
    return llvm::json::Object{{"ok",code==0},{"exit_code",code},{"stdout",child.process.output},{"stderr",child.process.errors},
      {"timed_out",child.timedOut},{"output_limit",child.outputLimit},{"interrupted",child.interrupted}};
  }catch(...){fs::remove_all(logs);throw;}
}
llvm::json::Value inspectWebApp(const Program &p){return prepare(p).metadata;}
llvm::json::Value generateWebApp(const Program &p,const std::string &directory){
  namespace fs=std::filesystem;
  auto project=prepare(p);fs::path output=fs::absolute(directory);
  if(fs::exists(output)&&(!fs::is_directory(output)||!fs::is_empty(output)))throw Error("E_EXISTS","web generation requires a new or empty directory");
  materialize(project,output);(*project.metadata.getAsObject())["directory"]=output.string();return std::move(project.metadata);
}
llvm::json::Value buildWebApp(const Program &p,const std::string &directory,const std::string &profile){
  namespace fs=std::filesystem;
  if(profile!="debug"&&profile!="profile"&&profile!="release")throw Error("E_OPTION","profile must be debug, profile or release");
  auto project=prepare(p);
  const char *nodeOverride=std::getenv("NEX_NODE"),*npmOverride=std::getenv("NEX_NPM"),*cacheOverride=std::getenv("NEX_NPM_CACHE");
  std::string node=nodeOverride?nodeOverride:"node",npm=npmOverride?npmOverride:"npm";
  auto nodeVersion=capture({node,"--version"}),npmVersion=capture({npm,"--version"});
  if(nodeVersion.code||npmVersion.code)throw Error("E_WEB_TOOL","cannot identify Node.js/npm");
  auto key=hash(project.metadata.getAsObject()->getString("key")->str()+profile+nodeVersion.output+npmVersion.output);
  auto folder=fs::absolute(fs::path(directory)/key/"web"),dist=folder/"dist",marker=folder/"complete-web.json";
  bool cached=false;
  if(fs::is_regular_file(marker)){
    auto parsed=llvm::json::parse(readFile(marker.string()));
    if(parsed&&parsed->getAsObject()&&parsed->getAsObject()->getString("key")==key&&parsed->getAsObject()->get("dist")){
      auto actual=distHashes(dist);cached=!actual.getAsNull()&&actual==*parsed->getAsObject()->get("dist");
    }else if(!parsed)llvm::consumeError(parsed.takeError());
  }
  if(!cached){
    materialize(project,folder);
    ToolDirectory runner(folder);
    if(runner.relocated())materialize(project,runner.path());
    auto cache=cacheOverride?std::string(cacheOverride):(fs::absolute(directory)/"npm-cache").string();
    auto install=capture({npm,"--prefix",runner.path().string(),"ci","--ignore-scripts","--no-audit","--no-fund","--cache",cache},180);
    if(install.code)throw Error("E_WEB_TOOL","npm ci failed:\n"+install.output+install.errors);
    std::vector<std::string> command={npm,"--prefix",runner.path().string(),"run","build"};
    if(profile=="debug")command.insert(command.end(),{"--","--minify","false"});
    auto built=capture(command,180);if(built.code)throw Error("E_WEB_TOOL","TypeScript/Vite build failed:\n"+built.output+built.errors);
    runner.retain("dist");runner.retain("node_modules");
    auto hashes=distHashes(dist);if(hashes.getAsNull())throw Error("E_WEB_TOOL","Vite did not produce dist/index.html");
    writeFile(marker.string(),json(llvm::json::Object{{"key",key},{"dist",std::move(hashes)}})+"\n");
  }
  return llvm::json::Object{{"schema","nex.web-build/1"},{"ok",true},{"directory",folder.string()},{"dist",dist.string()},{"revision",revision(p)},{"build_key",key},{"profile",profile},{"cached",cached},{"node",nodeVersion.output},{"npm",npmVersion.output}};
}
}
