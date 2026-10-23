#include "nex/profiling.h"
#include "nex/task_limits.h"
#include <iostream>
#include <functional>

namespace {
using namespace nex;using Object=llvm::json::Object;using Array=llvm::json::Array;using Value=llvm::json::Value;
unsigned cases=0;
void require(bool value){if(!value)throw std::runtime_error("profile report assertion failed");}
Object identity(){return Object{{"schema","nex.profile-build/1"},{"toolchain","0.114.0"},{"language","0.20"},{"revision",std::string(64,'a')},{"build_key",std::string(64,'b')},{"compiler_build",std::string(64,'c')},{"source_hash",std::string(64,'d')},{"entry","measured::main"},{"task_limits",taskLimitsJSON({})}};}
Object timing(bool maximum){Object value{{"inclusive_cpu_ns",10},{"self_cpu_ns",10},{"active_elapsed_ns",20},{"self_active_elapsed_ns",20},{"lifetime_ns",30},{"cpu_available",true},{"elapsed_available",true},{"lifetime_available",true}};if(maximum)value["max_lifetime_ns"]=30;return value;}
Value valid(){
  auto function=timing(true);function["name"]="measured::main";function["file"]="/source/main.nex";function["content_hash"]=std::string(64,'e');function["line"]=1;function["calls"]=1;function["completed"]=1;function["aborted"]=0;function["allocations"]=0;function["allocated_shallow_bytes"]=0;
  auto invocation=timing(false);invocation["id"]=1;invocation["task_id"]=1;invocation["parent_id"]=0;invocation["parent_omitted"]=false;invocation["site"]=0;invocation["outcome"]="completed";invocation["start_wall_ns"]=100;invocation["end_wall_ns"]=130;
  Object task{{"id",1},{"spawning_invocation_id",0},{"spawn_origin_omitted",false},{"created_wall_ns",90},{"terminal_wall_ns",140},{"resumes",2},{"migrations",1},{"last_thread_id",2},{"source_cpu_ns",10},{"source_elapsed_ns",20},{"active_invocations",0},{"started",true},{"cancelled_before_start",false},{"terminal",true},{"outcome","completed"},{"executor_cpu_available",true},{"scheduler_elapsed_available",true}};
  for(auto key:{"ready_ns","blocked_future_ns","blocked_send_ns","blocked_receive_ns","blocked_scope_ns","blocked_external_ns","drain_ns","executor_cpu_ns","executor_elapsed_ns"})task[key]=0;
  Array pools;for(auto name:{"NEX handles","NEX objects (shallow)"})pools.push_back(Object{{"pool",name},{"allocations",0},{"frees",0},{"live",0},{"peak_live",0},{"live_shallow_bytes",0},{"peak_shallow_bytes",0}});
  Value result=Object{{"schema","nex.profile-runtime/2"},{"kind","native_tasks"},{"tracy",false},{"build",identity()},
    {"clock","steady_wall_and_thread_cpu_nanoseconds"},{"duration_ns",50},{"origin_wall_ns",90},
    {"task_execution",Object{{"configured",taskLimitsJSON({})},{"effective",taskLimitsJSON({})},{"executor_workers",16}}},
    {"completeness",Object{{"aggregates",true},{"timeline",true},{"memory",true},{"cpu",true},{"elapsed",true},{"lifetime",true}}},{"incomplete",false},
    {"functions",Array{std::move(function)}},{"tasks",Array{std::move(task)}},{"invocations",Array{std::move(invocation)}},
    {"segments",Array{Object{{"task_id",1},{"invocation_id",1},{"thread_id",2},{"start_wall_ns",100},{"elapsed_ns",20},{"cpu_ns",10},{"elapsed_available",true},{"cpu_available",true}}}},
    {"memory",std::move(pools)},{"collector_memory",Object{}},
    {"limits",Object{{"events",100000},{"sites",16384},{"tasks",4096},{"active_invocations",65536},{"guards_per_thread",4096},{"live_allocations",1000000},{"report_bytes",67108864}}}};
  for(auto key:{"dropped_events","dropped_functions","dropped_frames","dropped_allocations","untracked_frees","dropped_tasks","dropped_invocations","dropped_guards","suppressed_hooks","invalid_transitions","clock_failures","counter_overflows","serialization_overflows"})(*result.getAsObject())[key]=0;
  return result;
}
void check(Value value){validateTaskProfileRuntimeReport(*value.getAsObject(),identity(),{});++cases;}
void reject(const std::function<void(Object&)> &mutate){auto value=valid();mutate(*value.getAsObject());try{validateTaskProfileRuntimeReport(*value.getAsObject(),identity(),{});}catch(const Error &e){require(e.code=="E_PROFILE");++cases;return;}throw std::runtime_error("malformed report accepted");}
Object &first(Object &o,const char *key){return *o.getArray(key)->front().getAsObject();}
}
int main(){try{
  check(parseTaskProfileRuntimeReport(json(valid())));
  for(auto key:{"toolchain","language","revision","build_key","compiler_build","source_hash","entry"})reject([&](auto &o){(*o.getObject("build"))[key]="foreign";});
  reject([](auto &o){(*o.getObject("task_execution"))["executor_workers"]=1;});
  reject([](auto &o){(*o.getObject("task_execution")->getObject("effective"))["steps"]=2;});
  reject([](auto &o){o["kind"]="synchronous";});reject([](auto &o){o["clock"]="wall_as_cpu";});reject([](auto &o){o["tracy"]=true;});
  reject([](auto &o){first(o,"functions")["calls"]=-1;});reject([](auto &o){first(o,"functions")["calls"]=1.5;});
  reject([](auto &o){first(o,"functions")["completed"]=2;});reject([](auto &o){first(o,"functions")["self_cpu_ns"]=11;});
  reject([](auto &o){first(o,"functions")["content_hash"]="bad";});
  reject([](auto &o){o.getArray("tasks")->push_back(o.getArray("tasks")->front());});
  reject([](auto &o){first(o,"invocations")["task_id"]=2;});reject([](auto &o){first(o,"invocations")["site"]=1;});
  reject([](auto &o){first(o,"invocations")["parent_id"]=1;});reject([](auto &o){first(o,"invocations")["end_wall_ns"]=99;});
  reject([](auto &o){first(o,"segments")["invocation_id"]=2;});reject([](auto &o){first(o,"tasks")["spawning_invocation_id"]=99;});
  reject([](auto &o){first(o,"tasks")["active_invocations"]=1;});reject([](auto &o){first(o,"tasks")["cancelled_before_start"]=true;});
  reject([](auto &o){o["dropped_events"]=1;});reject([](auto &o){o["dropped_invocations"]=1;});
  reject([](auto &o){o["incomplete"]=true;});reject([](auto &o){first(o,"functions")["cpu_available"]=false;});
  reject([](auto &o){first(o,"memory")["peak_live"]=-1;});reject([](auto &o){(*o.getObject("limits"))["events"]=1000001;});
  reject([](auto &o){o["unknown_payload"]="unbounded report extension";});
  reject([](auto &o){o.getArray("invocations")->push_back(o.getArray("invocations")->front());});
  reject([](auto &o){first(o,"functions")["calls"]=2;first(o,"functions")["completed"]=2;});
  reject([](auto &o){first(o,"functions")["calls"]=uint64_t(INT64_MAX)+1;});
  reject([](auto &o){first(o,"functions")["max_lifetime_ns"]=31;});
  reject([](auto &o){first(o,"functions")["cpu_available"]=1;});
  reject([](auto &o){first(o,"tasks")["spawn_origin_omitted"]=true;});
  reject([](auto &o){first(o,"invocations")["parent_omitted"]=true;});
  reject([](auto &o){o["dropped_allocations"]=1;});
  reject([](auto &o){o["clock_failures"]=1;});
  reject([](auto &o){o["serialization_overflows"]=1;});
  reject([](auto &o){(*o.getObject("limits"))["sites"]=0;});
  reject([](auto &o){o["incomplete"]=true;(*o.getObject("completeness"))["timeline"]=false;o["dropped_events"]=1;first(o,"invocations")["id"]=2;first(o,"invocations")["parent_id"]=1;first(o,"segments")["invocation_id"]=2;});
  auto truncated=valid();auto &t=*truncated.getAsObject();t["incomplete"]=true;(*t.getObject("completeness"))["timeline"]=false;t["dropped_events"]=2;t["invocations"]=Array{};t["segments"]=Array{};check(truncated);
  require(taskProfileBudgetIncomplete(t,Object{{"max_calls",Object{{"measured::main","1"}}}}).empty());++cases;
  (*t.getObject("completeness"))["aggregates"]=false;t["dropped_invocations"]=1;check(truncated);require(!taskProfileBudgetIncomplete(t,Object{{"max_calls",Object{{"measured::main","1"}}}}).empty());++cases;
  require(taskProfileBudgetIncomplete(t,Object{{"max_peak_handles","100"}}).empty());++cases;
  auto unavailable=valid();auto &u=*unavailable.getAsObject();u["incomplete"]=true;(*u.getObject("completeness"))["elapsed"]=false;first(u,"functions")["elapsed_available"]=false;first(u,"invocations")["elapsed_available"]=false;first(u,"segments")["elapsed_available"]=false;check(unavailable);require(!taskProfileBudgetIncomplete(u,Object{{"max_duration_ns","100"}}).empty());++cases;
  auto memoryIncomplete=valid();auto &m=*memoryIncomplete.getAsObject();m["incomplete"]=true;(*m.getObject("completeness"))["memory"]=false;m["dropped_allocations"]=1;check(memoryIncomplete);require(!taskProfileBudgetIncomplete(m,Object{{"max_peak_objects","100"}}).empty());require(taskProfileBudgetIncomplete(m,Object{{"max_calls",Object{{"measured::main","1"}}}}).empty());++cases;
  auto cpuUnavailable=valid();auto &c=*cpuUnavailable.getAsObject();c["incomplete"]=true;(*c.getObject("completeness"))["cpu"]=false;first(c,"functions")["cpu_available"]=false;first(c,"invocations")["cpu_available"]=false;first(c,"segments")["cpu_available"]=false;check(cpuUnavailable);require(taskProfileBudgetIncomplete(c,Object{{"max_calls",Object{{"measured::main","1"}}}}).empty());++cases;
  auto bounded=valid();auto &b=*bounded.getAsObject();auto repeated=b.getArray("segments")->front();for(unsigned i=0;i<100;++i)b.getArray("segments")->push_back(repeated);
  auto child=*b.getArray("tasks")->front().getAsObject();child["id"]=2;child["spawning_invocation_id"]=1;child["started"]=false;child["cancelled_before_start"]=true;child["outcome"]="cancelled";b.getArray("tasks")->push_back(std::move(child));
  auto encoded=serializeTaskProfileReport(b,1000,6000);require(encoded.size()+1<=6000);require(b.getArray("invocations")->empty()&&b.getArray("segments")->empty());require(b.getObject("completeness")->getBoolean("aggregates")==true&&b.getObject("completeness")->getBoolean("timeline")==false);require(first(b,"functions").getInteger("calls")==1);require(b.getArray("tasks")->back().getAsObject()->getInteger("spawning_invocation_id")==0&&b.getArray("tasks")->back().getAsObject()->getBoolean("spawn_origin_omitted")==true);require(taskProfileBudgetIncomplete(b,Object{{"max_calls",Object{{"measured::main","1"}}}}).empty());++cases;
  auto tiny=valid();bool overlarge=false;try{serializeTaskProfileReport(*tiny.getAsObject(),100,10);}catch(const Error &e){overlarge=e.code=="E_PROFILE";}require(overlarge);++cases;
  auto original=json(valid());auto duplicate="{\"schema\":\"foreign\","+original.substr(1);bool refused=false;try{parseTaskProfileRuntimeReport(duplicate);}catch(const Error &e){refused=e.code=="E_PROFILE";}require(refused);++cases;
  std::cout<<"{\"ok\":true,\"cases\":"<<cases<<"}\n";return 0;
}catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 1;}}
