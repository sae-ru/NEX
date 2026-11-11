#include "nex/cli.h"
#include <algorithm>
#include <sstream>

namespace nex {
const std::map<std::string,std::string> &cliGuides(){
  static const std::map<std::string,std::string> files={
    {"format","docs/formatting.md"},
    {"stdlib","docs/stdlib.md"},
    {"quick","llm/QUICK_REFERENCE.md"},
    {"source-contract","docs/source-contracts.md"},
    {"source-contract-migration","docs/source-contract-migration.md"},
    {"typed-web-delivery","docs/typed-web-delivery.md"},
    {"typed-error-provider","docs/typed-error-providers.md"},
    {"typed-exception","docs/typed-exceptions-design.md"},
    {"exception-provider","docs/source-exception-providers.md"},
    {"exception","docs/exceptions.md"},
    {"exception-module-debug","docs/source-exception-module-debug.md"},
    {"exception-module-profile","docs/source-exception-module-profile.md"},
    {"exception-module-http","docs/source-exception-module-http.md"},
    {"exception-instances","docs/source-exception-instances.md"},
    {"exception-frontiers","docs/source-exception-frontiers.md"},
    {"exception-modules","docs/source-exception-modules.md"},
    {"exception-http","docs/source-exception-http.md"},
    {"exception-host","docs/source-exception-host.md"},
    {"exception-task-watch","docs/source-exception-task-watch.md"},
    {"exception-task-lldb","docs/source-exception-task-lldb.md"},
    {"exception-task-debug","docs/source-exception-task-debug.md"},
    {"exception-task-control-profile","docs/source-exception-task-control-profile.md"},
    {"exception-native-tasks","docs/source-exception-native-tasks.md"},
    {"exception-task-ir","docs/source-exception-task-ir.md"},
    {"exception-lifetimes","docs/source-exception-lifetimes.md"},
    {"exception-tasks-prototype","docs/source-exception-tasks-prototype.md"},
    {"exception-prototype","docs/source-exceptions-prototype.md"},
    {"http-stream","docs/http-streams.md"},
    {"http-client","docs/http-client.md"},
    {"dns","docs/dns-provider.md"},
    {"tcp","docs/tcp-provider.md"},
    {"task-network-host","docs/task-network-transport.md"},
    {"task-file-streams","docs/task-file-streams.md"},
    {"task-file-stream-host","docs/task-file-stream-host.md"},
    {"task-write-providers","docs/task-write-providers.md"},
    {"task-write-migration","docs/task-write-migration.md"},
    {"task-file-writes","docs/task-file-writes-prototype.md"},
    {"task-file-write-host","docs/task-file-writes-host.md"},
    {"device","docs/device.md"},
    {"task-foreign-source","docs/task-foreign-prototype.md"},
    {"task-value-retirement","docs/task-value-retirement.md"},
    {"resource-regions","docs/resource-regions.md"},
    {"resource-executor","docs/resource-executor.md"},
    {"source-resources","docs/source-resources.md"},
    {"model","docs/models.md"},
    {"gpu","docs/gpu-codegen.md"},
    {"compute","docs/compute.md"},
    {"task-provider-debug","docs/task-provider-debugging.md"},
    {"task-provider-profile","docs/task-provider-profiling.md"},
    {"task-shared-providers","docs/task-shared-providers.md"},
    {"task-providers","docs/task-providers.md"},
    {"task-debug","docs/task-debugging.md"},
    {"task-file-reads","docs/task-file-reads.md"},
    {"task-external","docs/task-external.md"},
    {"task-limits","docs/task-limits.md"},
    {"task-migration","docs/task-migration.md"},
    {"task-lifetime","docs/task-lifetimes.md"},
    {"tasks-runtime","docs/tasks-runtime-design.md"},
    {"browser-worker","docs/browser-workers.md"},
    {"result","docs/error-propagation.md"},
    {"discovery","docs/discovery.md"},
    {"bootstrap","llm/BOOTSTRAP.md"},
    {"quality","docs/quality.md"},
    {"cost","experiments/quality/llm_cost.md"},
    {"concurrency","docs/concurrency-design.md"},
    {"task-workload","docs/task-workloads.md"},
    {"server-workload","docs/server-workload.md"},
    {"server-debug","docs/server-debugging.md"},
    {"project-task","docs/project-tasks.md"},
    {"project","docs/project-build.md"},
    {"lsp","docs/lsp.md"},
    {"windows","docs/windows.md"},
    {"wasm","docs/wasm.md"},
    {"core","docs/core-debugging.md"},
    {"prompt","llm/SYSTEM_PROMPT.md"},
    {"language","docs/language.md"},
    {"grammar","docs/grammar.ebnf"},
    {"protocol","docs/protocol.md"},
    {"web","docs/web.md"},
    {"server","docs/server.md"},
    {"api","docs/api.md"},
    {"debug","docs/debugging.md"},
    {"build","docs/incremental.md"},
    {"native-entry-abi","docs/native-entry-abi.md"},
    {"profile","docs/profiling.md"},
    {"verify","docs/verification.md"},
    {"runtime-contract","docs/runtime-contracts.md"},
    {"task","docs/tasks.md"},
    {"expression","docs/expressions.md"},
    {"operation","docs/operations.md"},
    {"graph","docs/graph.md"},
    {"linux","docs/linux.md"},
    {"match","docs/matching.md"},
    {"function","docs/functions.md"},
    {"files","docs/files.md"},
    {"bytes","docs/bytes.md"},
    {"resources","docs/resources.md"},
    {"ffi","docs/ffi-design.md"},
    {"diagnostic","docs/native-diagnostics.md"},
    {"history","docs/history.md"},
    {"snapshot","docs/snapshots.md"},
    {"compatibility","docs/compatibility.md"},
    {"frontend","docs/frontend-diagnostics.md"},
    {"query","docs/queries.md"},
    {"string-debug","docs/string-debug.md"},
    {"trait","docs/traits.md"},
    {"editor","docs/editor.md"},
    {"cli","docs/cli.md"},
    {"list-build","docs/list-construction.md"},
    {"text-construction","docs/text-construction.md"},
    {"bench","docs/bench.md"},
    {"fixes","docs/fixes.md"},
    {"bytes-construction","docs/bytes-construction.md"},
  };return files;
}
const std::vector<CliOption> &cliOptions(){
  static const auto options=[] {
    std::vector<CliOption> v;
    auto add=[&](const char *name,const char *value,const char *description){
      CliOption o;o.name=name;o.metavar=value;o.description=description;v.push_back(std::move(o));
    };
    add("--help","","Show bounded command help without opening a project.");
    add("--quiet","","Suppress routine NEX success status; retain results, errors and JSON.");
    add("--json","","Use the command's machine-readable JSON protocol.");
    add("--interpreter-only","","Use reference execution instead of native compilation.");
    add("--library","","Build/emit a native library entry.");
    add("--dpkg-notices","","Include selected system package notices when packaging.");
    add("--task-debug","","Prepare task debugging for project plan/build/package.");
    add("--check","","Check formatting without writing; exit 1 if it differs.");
    add("--write","","Replace the explicitly selected source with formatted bytes.");
    add("--details","","Request analysis/3 identifier details.");
    add("--references","","Request analysis/2 symbol references.");
    add("--workload","FILE","Project profile/plan workload contract.");
    add("--adapter","NAME","Project debugger adapter.");
    add("--profile-output","FILE","Project profiling report destination.");
    add("--component","NAME","Select a project component.");
    add("--configuration","NAME","Select a project build configuration.");
    add("--profile","NAME","Native optimization/debug profile.");
    add("--target","TARGET","Native target/triple or a supported adapter target.");
    add("--toolchain","FILE","Explicit native toolchain configuration.");
    add("--toolchains","FILE","Task replay toolchain catalogue.");
    add("--entry","NAME","Select an executable/emitted entry function.");
    add("--kind","KIND","Select the command's operation or output kind.");
    add("--revision","HASH|HEAD","Select retained graph source instead of physical files.");
    add("--steps","COUNT","Reference evaluation or expression step budget.");
    add("--task-steps","COUNT","Native/reference task step ceiling.");
    add("--task-timeout-ms","MS","Task wall deadline ceiling.");
    add("--task-workers","COUNT","Task executor worker ceiling.");
    add("--patch","FILE","Reviewed, revision-guarded graph patch.");
    add("--symbol","NAME","Select a source symbol for this operation.");
    add("--output","PATH","Command-specific output destination; see its guide.");
    add("--directory","PATH","Command-specific output/project directory.");
    add("--user","USER","Token principal identifier.");
    add("--auth","FILE","Operator-selected authentication configuration.");
    add("--events","COUNT","Profiling event limit.");
    add("--timeout","SECONDS","Command-specific wall timeout.");
    add("--apply","","Apply the unique compiler-checked fix.");
    add("--repetitions","COUNT","Measured benchmark repetitions.");
    add("--warmup","COUNT","Unmeasured benchmark warmup runs.");
    add("--baseline","FILE","Earlier nex.bench/1 report for comparison.");
    add("--scenario","TEXT","Profiling scenario label.");
    add("--contracts","FILE","Explicit verification/runtime/intent contracts.");
    add("--solver-timeout","MS","Bounded proof solver timeout.");
    add("--resource-limit","COUNT","Bounded proof solver resource limit.");
    add("--build-directory","PATH","Native/project build directory.");
    add("--candidates","FILE","Task comparison's reviewed revision map.");
    add("--task-hash","HASH","Select an archived task identity.");
    add("--manifest","FILE","Matching command-specific manifest.");
    add("--expression","TEXT","Checked, bounded debugger expression.");
    add("--operation","ID","Select an archived local operation ID.");
    add("--site","KEY","Select a matching compiled operation site.");
    add("--offset","COUNT","Result page offset.");
    add("--limit","COUNT","Result page size, bounded by the command.");
    add("--notices","FILE","Explicit native dependency notice inventory.");
    add("--foreign","FILE","Operator-prepared foreign library catalogue.");
    add("--entity","KIND","Select a declaration/graph entity kind.");
    add("--origin","NAMESPACE","Original graph namespace for identity resolution.");
    add("--node","ID","Original local graph node identity.");
    add("--from-revision","HASH","Original revision for identity resolution.");
    add("--expected-revision","HASH|EMPTY","Guard graph mutation against the observed HEAD.");
    add("--log","FILE","Captured native diagnostic log.");
    add("--note","TEXT","Change-history annotation.");
    add("--actor","LABEL","Change-history actor annotation.");
    add("--query","TEXT","Graph search query.");
    add("--field","PATH","Capability field or graph search field.");
    add("--depth","COUNT","Graph traversal depth.");
    add("--direction","NAME","Graph traversal edge direction.");
    add("--edge-offset","COUNT","Graph edge page offset.");
    add("--edge-limit","COUNT","Graph edge page size.");
    add("--input-layout","LAYOUT","GPU batch input organization.");
    add("--list-capacity","COUNT","Explicit CUDA list capacity.");
    add("--byte-capacity","COUNT","Explicit CUDA byte capacity.");
    add("--text-capacity","COUNT","Enable CUDA text with an explicit byte capacity.");
    add("--candidate","FILE","Reviewed migration candidate with origin guards.");
    add("--overlay","FILE","Editor source overlay JSON.");
    add("--capsule","DIRECTORY","Inspect a retained portable core capsule.");
    add("--export","DIRECTORY","Export a core capsule to a new directory.");
    add("--thread","INDEX","Core thread index.");
    add("--frame","INDEX","Core frame index.");
    for(auto &o:v){
      if(o.name=="--help")o.aliases={"-h"};
      if(o.name=="--output")o.aliases={"-o"};
      if(o.name=="--check"||o.name=="--write"){o.restrictedCommands={"fmt"};o.unique=true;o.restrictionMessage=o.name+" requires fmt and may occur only once";}
      if(o.name=="--task-debug"){o.restrictedCommands={"project"};o.restrictionMessage="--task-debug requires project plan/build/package";}
      if(o.name=="--candidate"){o.restrictedCommands={"migrate"};o.unique=true;o.restrictionMessage="--candidate requires migrate and one reviewed candidate file";}
      if(o.name=="--overlay"){o.restrictedCommands={"analyze"};o.restrictionMessage="--overlay requires analyze and a JSON file";}
      if(o.name=="--details"||o.name=="--references"){o.restrictedCommands={"analyze"};o.restrictionMessage=o.name+" requires analyze";}
      if(o.name=="--capsule"||o.name=="--export"){o.restrictedCommands={"core"};o.restrictionMessage="--capsule/--export require core and a directory";}
      if(o.name=="--thread"||o.name=="--frame"){o.restrictedCommands={"core"};o.restrictionMessage="--thread/--frame require core and an index";}
      if(o.name=="--apply"){o.restrictedCommands={"fix"};o.unique=true;o.restrictionMessage="--apply requires fix";}
      if(o.name=="--repetitions"||o.name=="--warmup"||o.name=="--baseline"){o.restrictedCommands={"bench"};o.restrictionMessage=o.name+" requires bench";}
    }
    return v;
  }();return options;
}
const CliOption *cliOption(const std::string &name){
  for(const auto &option:cliOptions())
    if(option.name==name||std::find(option.aliases.begin(),option.aliases.end(),name)!=option.aliases.end())return &option;
  return nullptr;
}
const std::vector<CliCommand> &cliCommands(){
  static const auto commands=[] {
    std::vector<CliCommand> v;
    auto add=[&](const char *name,const char *arguments,const char *description,const char *guide,const std::string &options){
      CliCommand c;c.name=name;c.arguments=arguments;c.description=description;c.guide=guide;
      c.options={"--help","--quiet"};if(c.name!="lsp")c.options.push_back("--json");
      std::istringstream stream(options);std::string option;while(stream>>option)c.options.push_back(option);
      v.push_back(std::move(c));
    };
    const std::string native="--revision --profile --entry --target --toolchain --build-directory --task-steps --task-timeout-ms --task-workers";
    add("help","[COMMAND]","Show the command index or one bounded command contract.","cli","");
    add("completion","--kind SHELL","Print a shell completion script without installing it.","cli","--kind");
    add("complete","-- WORDS...","Query completion candidates; the last word is the current prefix.","cli","");
    add("init","[DIRECTORY]","Create a new current-language project without overwriting files.","bootstrap","");
    add("project","[DIRECTORY|nex.build.json]","Plan/build/package/run/test/debug/profile project components.","project","--kind --component --configuration --build-directory --output --workload --foreign --adapter --profile-output --events --timeout --scenario --symbol --directory --notices --dpkg-notices --task-debug");
    add("describe","[--kind full|index | --field PATH]","Discover the selected compiled capability descriptor.","discovery","--kind --field");
    add("analyze","[FILE]","Read-only editor analysis with optional overlays/references.","editor","--overlay --references --details");
    add("fmt","FILE|DIRECTORY [--check|--write]","Format current syntax, retaining comments and graph history.","format","--check --write");
    add("lsp","","Run the installed language server on standard input/output.","lsp","");
    add("guide","[--kind KIND]","Read one selected source/SDK guide.","discovery","--kind");
    add("doctor","","Report the selected host/compiler/runtime configuration.","build","");
    add("explain","[CODE | --kind index]","Read bounded compiled diagnostic advice or its index.","diagnostic","--kind");
    add("cost","LEDGER.json","Summarize recorded model trial costs offline.","cost","--output");
    add("toolchain","FILE","Inspect a native toolchain configuration.","build","");
    add("check","[FILE]","Check current source and synchronize the semantic graph.","language","--revision --note --actor");
    add("eval","[FILE]","Evaluate with the reference engine; preserve source stdout.","language","--revision --entry --steps --task-steps --task-timeout-ms --task-workers --foreign");
    add("build","[FILE]","Build a native application/library or a supported adapter target.","build",native+" --output --directory --library");
    add("run","[FILE] [-- PROGRAM_ARGS...]","Compile and run a native program.","build",native+" --foreign");
    add("test","[FILE]","Run checked source tests.","language",native+" --foreign --interpreter-only --symbol");
    add("emit","[FILE]","Emit checked MLIR/LLVM/TypeScript/Metal/CUDA source.","gpu",native+" --kind --output --directory --library --input-layout --list-capacity --byte-capacity --text-capacity");
    add("package","[FILE] --directory NEW","Build/package a native application with its notices.","build",native+" --directory --notices --dpkg-notices --foreign");
    add("profile","[FILE]","Profile actual native work with a bounded event budget.","profile",native+" --foreign --events --timeout --scenario --output");
    add("bench","[FILE]","Measure repeated native runtime of one checked program.","bench",native+" --kind --repetitions --warmup --baseline --output");
    add("fix","[FILE]","Apply or preview one compiler-checked diagnostic fix.","fixes","--apply");
    add("debug","[FILE] [-- DEBUGGER_ARGS...]","Launch native LLDB/DAP debugging with matching source metadata.","debug",native+" --kind --foreign");
    add("contract","[FILE]","Generate proof/runtime/intent contracts as explicitly selected.","verify","--kind --revision --symbol --output --contracts --directory");
    add("verify","[FILE] --contracts FILE","Check explicitly supplied bounded proof contracts.","verify","--revision --contracts --symbol --solver-timeout --resource-limit --timeout --output");
    add("ffi","[FILE] --symbol NAME","Describe the selected checked foreign signature.","ffi","--revision --symbol");
    add("foreign","FILE","Inspect an operator-selected foreign catalogue.","ffi","");
    add("snapshot","--directory NEW","Save retained graph history to a new snapshot.","snapshot","--directory --timeout");
    add("recover","SNAPSHOT --directory NEW","Recover retained graph history to a new project.","snapshot","--directory --timeout");
    add("graph","","Read the semantic graph projection.","graph","--revision");
    add("history","","Read stored revision history.","history","");
    add("search","--query TEXT","Search retained graph declarations.","query","--query --entity --field --revision --offset --limit --output");
    add("subgraph","--symbol NAME","Read bounded graph dependencies/dependents.","query","--symbol --entity --direction --depth --revision --offset --limit --edge-offset --edge-limit --output");
    add("context","--symbol NAME | --operation ID | --site KEY","Read bounded archived context.","graph","--symbol --operation --site --entity --revision --offset --limit");
    add("operations","--symbol NAME","Read operation identities/source ranges for one function.","operation","--symbol --revision --offset --limit");
    add("declarations","[FILE]","Read module/type/trait/implementation declarations.","graph","--entity --symbol --revision --offset --limit");
    add("identities","[FILE]","Read/reconcile/resolve retained graph local identities.","graph","--kind --entity --symbol --output --manifest --expected-revision --revision --origin --from-revision --node");
    add("changes","","Read graph change history.","history","--offset --limit --output");
    add("restore","--revision HASH --expected-revision HASH|EMPTY","Restore a revision under an explicit HEAD guard.","history","--revision --expected-revision --note --actor");
    add("apply","--patch FILE","Apply a reviewed graph patch with revision/source guards.","protocol","--patch --note --actor");
    add("export","[--revision HASH|HEAD]","Export archived graph JSON or materialize source.","graph","--revision --output --directory");
    add("import","FILE","Import an integrity-checked archived graph.","graph","--note --actor");
    add("migrate","[GRAPH.json]","Plan/apply an explicit history-preserving language migration.","source-contract-migration","--kind --revision --candidate --expected-revision --note --actor");
    add("lock","[FILE]","Explicitly update reviewed dependency source pins.","build","--output");
    add("web","[FILE] --directory PATH","Generate the browser adapter from checked reachable code.","web","--revision --directory --output");
    add("api","[FILE]","Describe or generate checked HTTP API code.","api","--revision --directory");
    add("token","--user USER --auth FILE","Create a token using operator-selected authentication data.","server","--user --auth");
    add("core","[CORE_FILE]","Inspect a matching native core or retained capsule.","core","--manifest --capsule --export --expression --thread --frame --timeout");
    add("diagnose","[FILE] --manifest FILE --log FILE","Attribute captured native diagnostics to retained source.","diagnostic","--revision --manifest --log");
    add("inspect","[FRAME.json] --manifest FILE --expression TEXT","Inspect a retained debugger frame without target evaluation.","expression","--manifest --expression --kind --steps");
    add("inspect-private-task","FRAME.json","Inspect an explicitly selected private task experiment.","exception-task-watch","--manifest --expression --kind --steps");
    add("task","FILE","Initialize/check/run/replay or inspect a bounded task contract.","task","--kind --task-hash --revision --candidates --directory --toolchains --foreign --output --component --configuration");
    for(auto &c:v){
      for(const auto &name:c.options){
        if(!cliOption(name))throw Error("E_INTERNAL","CLI catalogue references unknown option "+name);
        if(name=="--profile")c.choices[name]={"debug","profile","release"};
        if(name=="--target")c.choices[name]={"native","server","wasm","web"};
        if(name=="--input-layout")c.choices[name]={"rows","columns"};
        if(name=="--direction")c.choices[name]={"dependencies","dependents","both"};
        if(name=="--entity")c.choices[name]={"all","module","type","trait","impl","function","endpoint","operation"};
      }
      if(c.name=="help")for(const auto &entry:v)if(entry.name!="inspect-private-task"&&entry.name!="complete")c.choices["positional"].push_back(entry.name);
      if(c.name=="guide")for(const auto &[name,path]:cliGuides()){(void)path;c.choices["--kind"].push_back(name);}
      if(c.name=="describe")c.choices["--kind"]={"full","index"};
      if(c.name=="explain")c.choices["--kind"]={"index"};
      if(c.name=="completion")c.choices["--kind"]={"bash","zsh","fish","powershell"};
      if(c.name=="emit")c.choices["--kind"]={"mlir","llvm","typescript","metal","cuda","opencl"};
      if(c.name=="debug")c.choices["--kind"]={"lldb","dap","nex-dap"};
      if(c.name=="project")c.choices["--kind"]={"plan","build","package","run","test","build-test","debug","profile"};
      if(c.name=="migrate")c.choices["--kind"]={"plan","apply"};
      if(c.name=="contract")c.choices["--kind"]={"runtime","intent"};
      if(c.name=="task")c.choices["--kind"]={"init","notices","check","run","history","replay"};
      if(c.name=="inspect"||c.name=="inspect-private-task")c.choices["--kind"]={"plan","demand","value"};
      if(c.name=="identities")c.choices["--kind"]={"reconcile","resolve"};
      if(c.name=="search")c.choices["--field"]={"symbol","source","any"};
      if(c.name=="declarations")c.choices["--entity"]={"module","type","trait","impl"};
      if(c.name=="context")c.choices["--entity"]={"module","type","trait","impl","function","endpoint"};
      if(c.name=="search")c.choices["--entity"]={"all","module","type","trait","impl","function","endpoint"};
      if(c.name=="subgraph")c.choices["--entity"]={"module","type","trait","impl","function","endpoint"};
      if(c.name=="profile"){
        c.choices["--profile"]={"profile"};c.choices["--target"]={"native"};
      }
      if(c.name=="run"||c.name=="package"||c.name=="debug")c.choices["--target"]={"native","server"};
      if(c.name=="test"){
        c.options.erase(std::remove(c.options.begin(),c.options.end(),"--entry"),c.options.end());
        c.choices["--target"]={"native","web"};
      }
      c.quietStatus=c.name=="check"||c.name=="init"||c.name=="lock"||c.name=="build"||c.name=="package";
      c.applicationArguments=c.name=="run"||c.name=="debug"||c.name=="project";
      c.hidden=c.name=="inspect-private-task"||c.name=="complete";
    }
    return v;
  }();return commands;
}
const CliCommand *cliCommand(const std::string &name){
  for(const auto &command:cliCommands())if(command.name==name)return &command;return nullptr;
}
}
