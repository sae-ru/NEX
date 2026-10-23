#include "nex/profiling.h"
#include "nex/task_limits.h"
#include "third_party/json.hpp"
#include <algorithm>
#include <limits>
#include <map>
#include <set>

namespace nex {
void validateTaskProfileCatalogOwnership(const NativeTaskProviderInfo &provider,
                                        const NativeTaskProfileCatalog &catalog,
                                        const std::map<std::string,std::set<std::string>> &definitions){
  auto fail=[](){throw Error("E_PROFILE","profile catalog differs from its physical definition owner");};
  const bool shared=provider.mode==NativeTaskLinkageMode::SharedFixed;
  const auto artifact=shared?provider.artifact:provider.codeOnly?NativeTaskArtifactKind::CodeArchive:NativeTaskArtifactKind::Application;
  const bool stage=artifact==NativeTaskArtifactKind::CodeArchive||artifact==NativeTaskArtifactKind::PicStage;
  const auto owner=stage?std::string{}:provider.component;
  if(!provider.enabled||!provider.profiling||catalog.mode!=provider.mode||catalog.artifact!=artifact||catalog.ownerImage!=owner||
     definitions.empty()||!definitions.contains(provider.component)||definitions.at(provider.component).empty())fail();
  auto computed=provider;computed.profiling=nativeTaskProfileInfo(catalog);
  if(*nativeTaskProviderJSON(computed).get("profiling")!=*nativeTaskProviderJSON(provider).get("profiling"))fail();
  if(catalog.registries.size()!=definitions.size())fail();
  std::set<std::string> all;
  for(const auto &registry:catalog.registries){
    auto expected=definitions.find(registry.component);if(expected==definitions.end()||expected->second.empty()||registry.ownerImage!=owner)fail();
    std::set<std::string> names;for(const auto &site:registry.sites){if(!names.insert(site.name).second||!all.insert(site.name).second)fail();
      if(shared){auto found=provider.definitionOwners.find(site.name);if(found==provider.definitionOwners.end()||found->second!=registry.component)fail();}}
    if(names!=expected->second)fail();
  }
  if(shared){if(all!=provider.definitions)fail();}
  else if(definitions.at(provider.component)!=provider.definitions||(stage&&definitions.size()!=1))fail();
}
namespace {
using Object=llvm::json::Object;using Array=llvm::json::Array;using Value=llvm::json::Value;
[[noreturn]] void invalid(const std::string &message){throw Error("E_PROFILE","invalid task profile: "+message);}
const Object &object(const Value &value){auto result=value.getAsObject();if(!result)invalid("expected object");return *result;}
const Array &array(const Object &value,const char *key,size_t maximum){auto result=value.getArray(key);if(!result||result->size()>maximum)invalid(std::string("missing/oversized array: ")+key);return *result;}
uint64_t number(const Object &value,const char *key){auto item=value.get(key);auto result=item?item->getAsUINT64():std::nullopt;if(!result||*result>uint64_t(INT64_MAX))invalid(std::string("missing/noninteger counter: ")+key);return *result;}
bool boolean(const Object &value,const char *key){auto result=value.getBoolean(key);if(!result)invalid(std::string("missing boolean: ")+key);return *result;}
std::string text(const Object &value,const char *key,size_t maximum=8192){auto result=value.getString(key);if(!result||result->empty()||result->size()>maximum||result->contains('\0'))invalid(std::string("missing/invalid text: ")+key);return result->str();}
void fields(const Object &value,std::initializer_list<const char*> allowed){std::set<std::string> names;for(auto key:allowed)names.insert(key);for(const auto &[key,item]:value)if(!names.contains(key.str()))invalid("unknown field: "+key.str());}
uint64_t sum(uint64_t a,uint64_t b){if(b>UINT64_MAX-a)invalid("counter overflow");return a+b;}
void digest(const Object &value,const char *key){auto result=text(value,key,64);if(result.size()!=64||!std::all_of(result.begin(),result.end(),[](char c){return (c>='0'&&c<='9')||(c>='a'&&c<='f');}))invalid(std::string("invalid digest: ")+key);}
void timing(const Object &value,bool maximum){
  auto inclusive=number(value,"inclusive_cpu_ns"),self=number(value,"self_cpu_ns");
  auto active=number(value,"active_elapsed_ns"),own=number(value,"self_active_elapsed_ns"),life=number(value,"lifetime_ns");
  if(self>inclusive||own>active)invalid("self time exceeds inclusive time");
  if(maximum&&number(value,"max_lifetime_ns")>life)invalid("maximum lifetime exceeds accumulated lifetime");
  (void)boolean(value,"cpu_available");(void)boolean(value,"elapsed_available");(void)boolean(value,"lifetime_available");
}
}
Value parseTaskProfileRuntimeReport(const std::string &source){
  if(source.size()>64*1024*1024)invalid("report exceeds64MiB");
  // LLVM's object representation coalesces duplicate keys. Check the original
  // text as well, so a second identity/reference cannot replace the first one.
  using JSON=nlohmann::ordered_json;
  std::vector<std::set<std::string>> names;size_t nodes=0;
  auto callback=[&](int depth,JSON::parse_event_t event,JSON &value){
    if(depth>16||++nodes>16000000)invalid("JSON depth/node limit");
    if(event==JSON::parse_event_t::object_start)names.emplace_back();
    if(event==JSON::parse_event_t::key&&!names.back().insert(value.get<std::string>()).second)invalid("duplicate JSON key");
    if(event==JSON::parse_event_t::object_end)names.pop_back();
    return true;
  };
  try{(void)JSON::parse(source,callback);}catch(const Error&){throw;}catch(const JSON::exception&){invalid("malformed JSON");}
  auto parsed=llvm::json::parse(source);if(!parsed){llvm::consumeError(parsed.takeError());invalid("malformed JSON");}return std::move(*parsed);
}
void validateTaskProfileRuntimeReport(const Object &report,const Object &expected,const nexrt::TaskExecutionLimits &effective,const NativeTaskProfileCatalog *catalog){
  const bool provider=expected.getString("schema")=="nex.profile-build/2";
  Object base(report);if(provider)base.erase("catalog");
  fields(base,{"schema","kind","tracy","build","clock","duration_ns","origin_wall_ns","task_execution","completeness","incomplete","dropped_events","dropped_functions","dropped_frames","dropped_allocations","untracked_frees","dropped_tasks","dropped_invocations","dropped_guards","suppressed_hooks","invalid_transitions","clock_failures","counter_overflows","serialization_overflows","limits","collector_memory","functions","tasks","invocations","segments","memory","traceEvents"});
  if(report.getString("schema")!=(provider?"nex.profile-runtime/3":"nex.profile-runtime/2"))invalid("schema");
  auto identity=report.getObject("build");if(!identity)invalid("missing build identity");
  Object baseIdentity(*identity);if(provider)baseIdentity.erase("task_profile_catalog");
  fields(baseIdentity,{"schema","toolchain","language","revision","build_key","compiler_build","source_hash","entry","task_limits"});
  for(const auto *key:{"schema","toolchain","language","revision","build_key","compiler_build","source_hash","entry"}){
    auto selected=expected.getString(key);if(!selected||identity->getString(key)!=selected)invalid(std::string("build identity mismatch: ")+key);
  }
  digest(*identity,"revision");digest(*identity,"build_key");digest(*identity,"compiler_build");digest(*identity,"source_hash");
  auto configured=expected.get("task_limits"),actual=identity->get("task_limits");
  if(!configured||!actual||json(*configured,false)!=json(*actual,false))invalid("configured task limits differ");
  auto limits=report.getObject("task_execution");if(!limits)invalid("missing task execution limits");
  fields(*limits,{"configured","effective","executor_workers"});
  auto rawConfigured=limits->get("configured"),rawEffective=limits->get("effective");
  if(!rawConfigured||json(*rawConfigured,false)!=json(*configured,false)||!rawEffective||json(*rawEffective,false)!=json(taskLimitsJSON(effective),false))invalid("effective task limits differ");
  if(number(*limits,"executor_workers")!=effective.workers)invalid("actual executor count differs");
  if(boolean(report,"tracy"))invalid("task Tracy report is unsupported");
  if(report.getString("kind")!="native_tasks"||report.getString("clock")!="steady_wall_and_thread_cpu_nanoseconds")invalid("kind/clock");
  (void)number(report,"duration_ns");(void)number(report,"origin_wall_ns");
  const auto &functions=array(report,"functions",16384);
  if(provider){
    if(!catalog||!expected.getString("task_profile_catalog")||identity->getString("task_profile_catalog")!=expected.getString("task_profile_catalog")||
       expected.getString("task_profile_catalog")!=nativeTaskProfileInfo(*catalog).catalogHash)invalid("provider catalog identity differs");
    digest(*identity,"task_profile_catalog");
    auto ranges=report.getObject("catalog");if(!ranges||ranges->size()!=2||ranges->getString("schema")!="nex.task-profile-runtime-catalog/1")invalid("missing provider runtime catalog");
    const auto &registries=array(*ranges,"registries",128);if(registries.size()!=catalog->registries.size()||registries.empty())invalid("provider registry union differs");
    size_t first=0;std::set<std::string> components;
    for(size_t index=0;index<registries.size();++index){const auto &row=object(registries[index]);const auto &checked=catalog->registries[index];
      fields(row,{"component","first_site","site_count"});
      if(text(row,"component",64)!=checked.component||!components.insert(checked.component).second||number(row,"first_site")!=first||number(row,"site_count")!=checked.sites.size()||checked.sites.empty()||checked.sites.size()>functions.size()-first)invalid("provider registry range/order differs");
      for(const auto &site:checked.sites){const auto &measured=object(functions[first++]);
        if(measured.getString("name")!=site.name||measured.getString("file")!=site.debugPath||measured.getString("content_hash")!=site.functionHash||measured.getInteger("line")!=site.line)invalid("provider site union differs");
      }
    }
    if(first!=functions.size())invalid("provider catalog does not exhaust function sites");
  }
  const auto &tasks=array(report,"tasks",65536);
  const auto &invocations=array(report,"invocations",65536);
  const auto &segments=array(report,"segments",1000000);
  std::set<std::string> sites;
  for(const auto &item:functions){const auto &f=object(item);fields(f,{"name","file","content_hash","line","calls","completed","aborted","inclusive_cpu_ns","self_cpu_ns","active_elapsed_ns","self_active_elapsed_ns","lifetime_ns","max_lifetime_ns","cpu_available","elapsed_available","lifetime_available","allocations","allocated_shallow_bytes"});if(!sites.insert(text(f,"name")).second)invalid("duplicate function site");text(f,"file");digest(f,"content_hash");if(number(f,"line")==0)invalid("invalid source line");
    auto calls=number(f,"calls"),finished=sum(number(f,"completed"),number(f,"aborted"));if(finished>calls)invalid("finished calls exceed calls");timing(f,true);(void)number(f,"allocations");(void)number(f,"allocated_shallow_bytes");}
  std::map<uint64_t,const Object*> taskIndex,invocationIndex;
  for(const auto &item:tasks){const auto &t=object(item);fields(t,{"id","spawning_invocation_id","spawn_origin_omitted","created_wall_ns","terminal_wall_ns","resumes","migrations","last_thread_id","source_cpu_ns","source_elapsed_ns","active_invocations","started","cancelled_before_start","terminal","outcome","ready_ns","blocked_future_ns","blocked_send_ns","blocked_receive_ns","blocked_scope_ns","blocked_external_ns","drain_ns","executor_cpu_ns","executor_elapsed_ns","executor_cpu_available","scheduler_elapsed_available"});auto id=number(t,"id");if(!id||!taskIndex.emplace(id,&t).second)invalid("duplicate/zero task ID");
    auto created=number(t,"created_wall_ns"),terminal=number(t,"terminal_wall_ns");
    if(boolean(t,"terminal")&&terminal<created)invalid("task lifetime regressed");
    auto started=boolean(t,"started"),cancelled=boolean(t,"cancelled_before_start");if(cancelled&&started)invalid("started task cancelled before start");
    if(boolean(t,"terminal")&&number(t,"active_invocations")!=0)invalid("terminal task has active invocations");
    auto outcome=text(t,"outcome",16);if(outcome!="completed"&&outcome!="aborted"&&outcome!="cancelled")invalid("invalid task outcome");
    if(number(t,"migrations")>number(t,"resumes"))invalid("migrations exceed resumes");
    (void)number(t,"last_thread_id");(void)number(t,"source_cpu_ns");(void)number(t,"source_elapsed_ns");(void)number(t,"spawning_invocation_id");
    for(const auto *key:{"ready_ns","blocked_future_ns","blocked_send_ns","blocked_receive_ns","blocked_scope_ns","blocked_external_ns","drain_ns","executor_cpu_ns","executor_elapsed_ns"})(void)number(t,key);
    (void)boolean(t,"executor_cpu_available");(void)boolean(t,"scheduler_elapsed_available");
    if(boolean(t,"spawn_origin_omitted")&&number(t,"spawning_invocation_id"))invalid("omitted spawn has an origin");}
  const auto *completeness=report.getObject("completeness");if(!completeness)invalid("missing completeness");
  fields(*completeness,{"aggregates","timeline","memory","cpu","elapsed","lifetime"});
  bool aggregates=boolean(*completeness,"aggregates"),timeline=boolean(*completeness,"timeline");
  bool memory=boolean(*completeness,"memory"),cpu=boolean(*completeness,"cpu"),elapsed=boolean(*completeness,"elapsed"),lifetime=boolean(*completeness,"lifetime");
  if(boolean(report,"incomplete")==bool(aggregates&&timeline&&memory&&cpu&&elapsed&&lifetime))invalid("incomplete contradicts completeness");
  for(const auto &item:invocations){const auto &v=object(item);fields(v,{"id","task_id","parent_id","parent_omitted","site","outcome","start_wall_ns","end_wall_ns","inclusive_cpu_ns","self_cpu_ns","active_elapsed_ns","self_active_elapsed_ns","lifetime_ns","cpu_available","elapsed_available","lifetime_available"});auto id=number(v,"id"),task=number(v,"task_id"),parent=number(v,"parent_id");
    if(!id||!invocationIndex.emplace(id,&v).second||!taskIndex.contains(task))invalid("duplicate/foreign invocation ID");
    if(number(v,"site")>=functions.size()||parent>=id)invalid("invalid invocation site/parent");
    if(boolean(v,"parent_omitted")&&(parent||timeline))invalid("invalid omitted invocation parent");
    auto outcome=text(v,"outcome",16);if(outcome!="active"&&outcome!="completed"&&outcome!="aborted")invalid("invalid invocation outcome");
    auto start=number(v,"start_wall_ns"),end=number(v,"end_wall_ns");if(outcome!="active"&&end<start)invalid("invocation lifetime regressed");
    if(outcome!="active"&&boolean(v,"lifetime_available")&&end-start!=number(v,"lifetime_ns"))invalid("invocation lifetime mismatch");timing(v,false);
    if((cpu&&!boolean(v,"cpu_available"))||(elapsed&&!boolean(v,"elapsed_available"))||(lifetime&&!boolean(v,"lifetime_available")))invalid("invocation availability contradicts completeness");
  }
  for(const auto &[id,v]:invocationIndex){auto parent=number(*v,"parent_id");if(parent){auto found=invocationIndex.find(parent);if(found==invocationIndex.end())invalid("missing parent invocation");else if(number(*found->second,"task_id")!=number(*v,"task_id"))invalid("cross-task call parent");}}
  for(const auto &[id,t]:taskIndex){auto spawning=number(*t,"spawning_invocation_id");if(spawning&&!invocationIndex.contains(spawning))invalid("missing spawning invocation");if(timeline&&boolean(*t,"spawn_origin_omitted"))invalid("complete timeline has omitted spawn");}
  for(const auto &item:segments){const auto &s=object(item);fields(s,{"task_id","invocation_id","thread_id","start_wall_ns","elapsed_ns","cpu_ns","elapsed_available","cpu_available"});auto task=number(s,"task_id"),invocation=number(s,"invocation_id");if(!taskIndex.contains(task)||!invocation||!number(s,"thread_id"))invalid("invalid segment owner/thread");
    auto found=invocationIndex.find(invocation);if(found==invocationIndex.end())invalid("missing segment invocation");else if(number(*found->second,"task_id")!=task)invalid("cross-task segment owner");
    auto start=number(s,"start_wall_ns"),elapsedNs=number(s,"elapsed_ns");(void)sum(start,elapsedNs);(void)number(s,"cpu_ns");(void)boolean(s,"elapsed_available");(void)boolean(s,"cpu_available");
    if((cpu&&!boolean(s,"cpu_available"))||(elapsed&&!boolean(s,"elapsed_available")))invalid("segment availability contradicts completeness");}
  for(const auto *key:{"dropped_functions","dropped_frames","dropped_allocations","untracked_frees","dropped_events"})(void)number(report,key);
  bool aggregateDrop=false;
  for(const auto *key:{"dropped_tasks","dropped_invocations","dropped_guards","suppressed_hooks","invalid_transitions","counter_overflows","dropped_functions","dropped_frames"})aggregateDrop|=number(report,key)!=0;
  auto clocks=number(report,"clock_failures"),serialization=number(report,"serialization_overflows");
  if(aggregates&&aggregateDrop)invalid("aggregate completeness contradicts drops");
  if(timeline&&(aggregateDrop||number(report,"dropped_events")||serialization))invalid("timeline completeness contradicts drops");
  if(memory&&(number(report,"dropped_allocations")||number(report,"untracked_frees")))invalid("memory completeness contradicts drops");
  if(clocks&&cpu&&elapsed&&lifetime)invalid("clock failure has no unavailable clock");
  for(const auto &item:functions){const auto &f=object(item);if((cpu&&!boolean(f,"cpu_available"))||(elapsed&&!boolean(f,"elapsed_available"))||(lifetime&&!boolean(f,"lifetime_available")))invalid("function availability contradicts completeness");}
  if(aggregates){for(const auto &item:functions){const auto &f=object(item);if(number(f,"calls")!=sum(number(f,"completed"),number(f,"aborted")))invalid("complete function has unfinished calls");}for(const auto &[id,t]:taskIndex)if(!boolean(*t,"terminal"))invalid("complete task is not terminal");}
  if(aggregates&&timeline){
    std::vector<uint64_t> calls(functions.size()),completed(functions.size()),aborted(functions.size());
    for(const auto &[id,v]:invocationIndex){auto site=number(*v,"site");++calls[site];auto outcome=text(*v,"outcome",16);if(outcome=="completed")++completed[site];else if(outcome=="aborted")++aborted[site];else invalid("complete timeline contains active invocation");}
    for(size_t site=0;site<functions.size();++site){const auto &f=object(functions[site]);if(calls[site]!=number(f,"calls")||completed[site]!=number(f,"completed")||aborted[site]!=number(f,"aborted"))invalid("timeline call totals differ from aggregates");}
    for(const auto *key:{"inclusive_cpu_ns","self_cpu_ns","active_elapsed_ns","self_active_elapsed_ns","lifetime_ns"}){
      std::vector<uint64_t> totals(functions.size());for(const auto &[id,v]:invocationIndex){auto site=number(*v,"site");totals[site]=sum(totals[site],number(*v,key));}
      for(size_t site=0;site<functions.size();++site)if(totals[site]!=number(object(functions[site]),key))invalid("timeline time totals differ from aggregates");
    }

  }
  std::set<std::string> pools;for(const auto &item:array(report,"memory",2)){const auto &p=object(item);fields(p,{"pool","allocations","frees","live","peak_live","live_shallow_bytes","peak_shallow_bytes"});auto name=text(p,"pool",64);if((name!="NEX handles"&&name!="NEX objects (shallow)")||!pools.insert(name).second)invalid("invalid memory pool");
    auto allocations=number(p,"allocations"),frees=number(p,"frees"),live=number(p,"live"),peak=number(p,"peak_live");
    if(frees>allocations||live>allocations-frees||peak<live||number(p,"peak_shallow_bytes")<number(p,"live_shallow_bytes"))invalid("inconsistent memory pool");}
  if(pools.size()!=2)invalid("missing managed memory pool");
  auto caps=report.getObject("limits");if(!caps)invalid("missing recording limits");
  fields(*caps,{"events","sites","tasks","active_invocations","guards_per_thread","live_allocations","report_bytes"});
  for(const auto &[key,maximum]:std::map<std::string,uint64_t>{{"events",1000000},{"sites",16384},{"tasks",65536},{"active_invocations",65536},{"guards_per_thread",4096},{"live_allocations",1000000},{"report_bytes",67108864}}){auto n=number(*caps,key.c_str());if(n>maximum||(key!="events"&&!n))invalid("invalid recording limit: "+key);}
  if(functions.size()>number(*caps,"sites")||tasks.size()>number(*caps,"tasks"))invalid("records exceed configured collector limits");
  auto storage=report.getObject("collector_memory");if(!storage||storage->size()>16)invalid("missing/oversized collector memory description");
  for(const auto &[key,value]:*storage){if(key.str().size()>64||!value.getAsUINT64()||*value.getAsUINT64()>uint64_t(INT64_MAX))invalid("invalid collector storage counter");}
  // The reader constructs no timeline from arbitrary embedded trace payloads.
  if(auto trace=report.get("traceEvents");trace&&(!trace->getAsArray()||trace->getAsArray()->size()>1000000||json(*trace,false).size()>32*1024*1024))invalid("oversized visual trace");
}
std::string serializeTaskProfileReport(Object &report,size_t runtimeBytes,size_t maximumBytes){
  if(maximumBytes>64*1024*1024)invalid("public report bound exceeds64MiB");
  report["report_serialization"]=Object{{"maximum_bytes",int64_t(maximumBytes)},
    {"runtime_bytes",int64_t(runtimeBytes)},{"timeline_omitted",false}};
  auto serialized=json(Value(Object(report)),false);
  if(serialized.size()+1>maximumBytes){
    // Graph/path annotations have their own byte cost. Keep exact aggregates;
    // omit the entire optional tree so no dangling references survive the cut.
    auto invocations=report.getArray("invocations"),segments=report.getArray("segments"),tasks=report.getArray("tasks");
    if(!invocations||!segments||!tasks||!report.getObject("completeness"))invalid("cannot bound missing task arrays/completeness");
    auto omitted=invocations->size()+segments->size();
    (*report.getObject("report_serialization"))["timeline_omitted"]=true;
    (*report.getObject("report_serialization"))["omitted_records"]=int64_t(omitted);
    auto dropped=number(report,"dropped_events");
    report["runtime_dropped_events"]=int64_t(dropped);
    report["dropped_events"]=int64_t(std::min(uint64_t(INT64_MAX),dropped+uint64_t(omitted)));
    report["invocations"]=Array{};report["segments"]=Array{};report.erase("traceEvents");
    for(auto &task:*report.getArray("tasks")){auto &t=*task.getAsObject();if(number(t,"spawning_invocation_id")){
      t["spawning_invocation_id"]=0;t["spawn_origin_omitted"]=true;}}
    (*report.getObject("completeness"))["timeline"]=false;report["incomplete"]=true;
    serialized=json(Value(Object(report)),false);
  }
  if(serialized.size()+1>maximumBytes)invalid("required aggregates exceed public report bound");
  return serialized;
}
Array taskProfileBudgetIncomplete(const Object &report,const Object &budget){
  Array failures;auto completeness=report.getObject("completeness");
  auto clean=[&](const char *key){return completeness&&completeness->getBoolean(key).value_or(false);};
  if(budget.get("max_calls")&&!clean("aggregates"))failures.push_back("task_profile:incomplete_aggregates");
  if(budget.get("max_duration_ns")&&!clean("elapsed"))failures.push_back("task_profile:elapsed_unavailable");
  if((budget.get("max_peak_handles")||budget.get("max_peak_objects"))&&!clean("memory"))failures.push_back("task_profile:incomplete_memory");
  return failures;
}
}
