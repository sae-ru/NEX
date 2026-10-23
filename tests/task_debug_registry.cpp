#include "nex_task_application.h"
#include "nex_task_debug.h"
#include <array>
#include <atomic>
#include <chrono>
#include <future>
#include <iostream>
#include <mutex>
#include <thread>
#include <vector>
using namespace nexrt;
namespace {
std::atomic<size_t> checks{0},stops{0};std::atomic<bool> bad{false};std::mutex observations;
std::atomic<TaskGroup*> markerGroup{nullptr};
std::array<uint64_t,8> taskIds{},activationIds{};std::array<size_t,8> visits{};
uint64_t load(const uint64_t &v){return std::atomic_ref<uint64_t>(const_cast<uint64_t&>(v)).load(std::memory_order_acquire);}
void require(bool value,const char *text){++checks;if(!value)throw std::runtime_error(text);}
constexpr char digest[]="0000000000000000000000000000000000000000000000000000000000000000";
TaskCodeDescriptor mainCode,childCode,trapCode,parkCode;
int64_t kinds[]={3,0},parameter[]={0},childKinds[]={0};
const TaskDebugBinding mainBindings[]={{1,"retained","str",0,0},{2,"result","i64",1,0}};
const TaskDebugBinding childBindings[]={{1,"input","i64",0,0}};
const int64_t mainVisible[]={0,0,0,1},childVisible[]={0};
const TaskDebugPoint mainPoints[]={
 {digest,0,1,1,0,1,0,0,0},{digest,0,2,1,1,2,1,0,1},{digest,1,3,1,2,3,4,1,1},
 {digest,1,4,1,3,4,3,2,1},{digest,2,5,1,4,5,1,2,2}};
const TaskDebugPoint childPoints[]={{digest,0,6,1,5,6,0,0,1},{digest,1,7,1,6,7,4,0,1}};
const TaskDebugPoint simplePoints[]={{digest,0,8,1,7,8,0,0,0},{digest,1,9,1,8,9,4,0,0}};
TaskDebugCodeSite metadata[4];
TaskDebugCodeRegistry registries[3];
int64_t childStep(void *pointer){auto &frame=*static_cast<NativeTaskFrame*>(pointer);if(frame.pc==0){nex_task_debug_checkpoint(pointer,0);frame.pc=1;return 1;}nex_task_debug_checkpoint(pointer,1);nex_task_frame_return_i64(pointer,frame.read(0,0).scalar+2,0);return 0;}
int64_t mainStep(void *pointer){auto &frame=*static_cast<NativeTaskFrame*>(pointer);
 if(frame.pc==0){nex_task_debug_checkpoint(pointer,0);frame.write(0,Value(string(std::string("retained\0🧠",13))),3);nex_task_debug_checkpoint(pointer,1);frame.pc=1;return 1;}
 if(frame.pc==1){nex_task_debug_checkpoint(pointer,2);auto args=makeHandle(Value(std::make_shared<Data>(Data::List)));readHandle(args).object->values.push_back(Value(40));nex_task_debug_checkpoint(pointer,3);nex_task_frame_call_at(pointer,&childCode,nullptr,args,1,4,nullptr);nex_release(args);frame.pc=2;return 2;}
 nex_task_debug_checkpoint(pointer,4);require(frame.read(1,0).scalar==42,"child result differs");nex_task_frame_return_i64(pointer,42,0);return 0;
}
int64_t trapStep(void *pointer){nex_task_debug_checkpoint(pointer,0);(void)makeHandle(Value(string("trap-owned")));throw Trap("E_ITEM","controlled debug trap",8);}
int64_t unusedStep(void *pointer){nex_task_frame_return_i64(pointer,0,0);return 0;}
void setup(){
 mainCode={mainStep,kinds,nullptr,nullptr,nullptr,taskCodeABI,2,0,0,0,taskCodeDeclaredTask};
 childCode={childStep,childKinds,parameter,nullptr,nullptr,taskCodeABI,1,1,0,0,taskCodeDeclaredTask};
 trapCode={trapStep,nullptr,nullptr,nullptr,nullptr,taskCodeABI,0,0,0,0,taskCodeDeclaredTask};
 parkCode={unusedStep,kinds,nullptr,nullptr,nullptr,taskCodeABI,2,0,0,0,taskCodeDeclaredTask};
 metadata[0]={&mainCode,"main","probe.nex",digest,digest,mainPoints,mainBindings,mainVisible,5,2,4,2};
 metadata[1]={&childCode,"child","probe.nex",digest,digest,childPoints,childBindings,childVisible,2,1,1,1};
 metadata[2]={&trapCode,"trap","probe.nex",digest,digest,simplePoints,nullptr,nullptr,2,0,0,0};
 metadata[3]={&parkCode,"park","probe.nex",digest,digest,simplePoints,nullptr,nullptr,2,0,0,2};
 registries[0]={1,metadata,1,"app"};registries[1]={1,metadata+1,3,"leaf"};registries[2]={1,nullptr,0,"pure"};
}
void clean(){require(!inRequestScope()&&liveObjects==0,"debug catalog retained source ownership");nex_runtime_finish();}
TaskDebugTaskRecord *tasks(){return reinterpret_cast<TaskDebugTaskRecord*>(load(nex_task_debug_catalog_v2.base.tasks_address));}
TaskDebugFrameRecord *frames(){return reinterpret_cast<TaskDebugFrameRecord*>(load(nex_task_debug_catalog_v2.base.frames_address));}
void terminal(){for(size_t i=0;i<load(nex_task_debug_catalog_v2.base.task_count);++i){auto &task=tasks()[i];require(load(task.state)==uint64_t(TaskDebugState::Terminal),"task terminal was not published");require(load(task.frame_count)==0,"terminal task retained frame addresses");}require(!load(nex_task_debug_catalog_v2.base.live_frames),"debug frame pool did not retire");}
struct Gate {std::promise<void> entered,release;std::shared_future<void> released=release.get_future().share();std::atomic<bool> retired{false};bool memory=false;};
struct Held final:TaskExternalOperation {std::shared_ptr<Gate> gate;explicit Held(std::shared_ptr<Gate> gate):gate(std::move(gate)){}TaskExternalResult run(const TaskExternalControl &)override{gate->entered.set_value();gate->released.wait();gate->retired=true;if(gate->memory)throw std::bad_alloc();return {};}};
std::weak_ptr<Data> parkedValue;
TaskBody park(TaskGroup &group,std::shared_ptr<Gate> gate){
 std::vector<NativeTaskFrame> stack;stack.emplace_back(parkCode,std::vector<Value>{},Value{});TaskDebugStackRegistration registration(&stack);stack.back().debugActivation=TaskDebugFrame(3);
 auto data=string("only source owns parked payload");parkedValue=data;stack.back().write(0,Value(std::move(data)),3);nex_task_debug_checkpoint(&stack.back(),0);
 auto ticket=group.submitExternal(std::make_shared<Held>(gate),32);(void)co_await group.awaitExternal(ticket);
 nex_task_debug_checkpoint(&stack.back(),1);co_return Value(7);
}
TaskBody parkFactory(TaskGroup &group,Value,Value,const void *context){return park(group,*static_cast<const std::shared_ptr<Gate>*>(context));}
bool waitFor(auto predicate){const auto until=std::chrono::steady_clock::now()+std::chrono::seconds(3);while(!predicate()){if(std::chrono::steady_clock::now()>=until)return false;std::this_thread::yield();}return true;}
void physical(bool cancel,bool fatal){
 auto first=load(nex_task_debug_catalog_v2.base.task_count);
 {RequestScope request;TaskGroup group(2);auto gate=std::make_shared<Gate>();gate->memory=fatal;auto entered=gate->entered.get_future();markerGroup=&group;auto ticket=group.spawnWithContext(parkFactory,&gate);
  require(entered.wait_for(std::chrono::seconds(3))==std::future_status::ready,"physical operation did not start");
  auto &task=tasks()[first];require(waitFor([&]{return !(load(task.source_sequence)&1)&&(load(task.flags)&taskDebugParked);}),"accepted external park was not stable");
  require(load(task.wait_kind)==uint64_t(TaskDebugWait::External),"external park used another wait kind");auto slot=load(task.top_frame_slot);auto id=load(task.top_frame_id);auto &frame=frames()[slot];
  require(load(frame.id)==id&&load(frame.task_id)==load(task.id),"parked frame identity mismatched");auto *native=reinterpret_cast<NativeTaskFrame*>(load(frame.frame_address));require(native&&native->read(0,3).object->text=="only source owns parked payload","stable park lost retained source slot");
  if(cancel){group.cancel();require(waitFor([&]{return load(task.state)==uint64_t(TaskDebugState::Draining);}),"cancel did not enter physical drain");require(!gate->retired,"logical cancel skipped physical fence");require(waitFor([&]{return parkedValue.expired();}),"non-owning debugger kept cancelled source payload");require(load(task.source_sequence)&1,"destroyed source frame stayed readable");}
  gate->release.set_value();bool selected=false;
  try{auto result=group.join(ticket);require(!cancel&&result.scalar==7,"cancelled task resumed source");}catch(const Trap &error){selected=error.code==(fatal?"E_MEMORY":"E_CANCELLED");}
  if(cancel||fatal)require(selected,"fatal/cancel result changed by debugger");try{group.finish();}catch(const Trap &error){require(error.code==(fatal?"E_MEMORY":"E_CANCELLED"),"finish changed physical fatal priority");}
  require(gate->retired&&group.externalStats().tickets==0,"debugger changed physical retirement");markerGroup=nullptr;
 }clean();terminal();
}
void transfer(){
 auto task=taskDebugCreateTask();TaskDebugFrame activation;uint64_t id=0;
 std::thread first([&]{taskDebugKernelState(task,TaskDebugState::Running);TaskDebugTurn turn(task);activation=TaskDebugFrame(3);id=activation.activation();int token=0;TaskDebugFrameView view{&activation,&token,0,0};taskDebugPublish(std::span(&view,1),true);});first.join();
 std::thread second([&]{taskDebugKernelState(task,TaskDebugState::Running);TaskDebugTurn turn(task);require(activation.activation()==id,"activation changed across real worker transfer");int token=0;TaskDebugFrame moved=std::move(activation);TaskDebugFrameView view{&moved,&token,1,0};taskDebugPublish(std::span(&view,1),true);});second.join();taskDebugKernelState(task,TaskDebugState::Terminal);
 // Manual module-only activations have no registered stack owner; clear chain
 // for the probe terminal contract by publishing an empty accepted park first.
 {TaskDebugTurn turn(task);taskDebugPublish({},false);}taskDebugKernelState(task,TaskDebugState::Terminal);
}
void concurrentPublication(){
 auto a=taskDebugCreateTask(),b=taskDebugCreateTask();std::atomic<bool> stop{false};std::atomic<size_t> reads{0},ready{0};std::promise<void> release;auto released=release.get_future().share();
 std::thread reader([&]{while(!stop){for(auto task:{a,b}){auto &t=tasks()[task.slot];auto seq=load(t.source_sequence);if(seq&1)continue;auto slot=load(t.top_frame_slot),id=load(t.top_frame_id),count=load(t.frame_count);if(!count||slot>=maximumTaskDebugFrames)continue;auto &f=frames()[slot];auto fid=load(f.id),owner=load(f.task_id),fs=load(f.sequence),pointer=load(f.frame_address);if(load(t.source_sequence)==seq){if(fid!=id||owner!=task.id||(fs&1)||!pointer)bad=true;++reads;}}}});
 auto work=[&](TaskDebugTask task){taskDebugKernelState(task,TaskDebugState::Running);TaskDebugTurn turn(task);{TaskDebugFrame activation(3);int opaque=42;TaskDebugFrameView parked{&activation,&opaque,0,0};taskDebugPublish(std::span(&parked,1),false);++ready;released.wait();for(size_t i=0;i<300;++i){TaskDebugFrameView view{&activation,&opaque,uint64_t(i%2),0};taskDebugPublish(std::span(&view,1),true);std::this_thread::yield();}}taskDebugPublish({},false);taskDebugKernelState(task,TaskDebugState::Terminal);};
 std::thread first(work,a),second(work,b);const bool observed=waitFor([&]{return ready==2&&reads>0;});release.set_value();first.join();second.join();stop=true;reader.join();require(observed&&reads>0,"concurrent atomic publication reader saw no stable records");require(!bad,"concurrent catalog words were torn");
}
void failClosed(){
 const auto before=load(nex_task_debug_catalog_v2.base.invalid_transitions);const auto beforeStops=stops.load();
 auto task=taskDebugCreateTask();{TaskDebugTurn turn(task);TaskDebugFrame activation(3);TaskDebugFrameView null{&activation,nullptr,0,0};taskDebugPublish(std::span(&null,1),true);}
 require(stops==beforeStops&&(load(tasks()[task.slot].flags)&taskDebugUnavailable),"null source frame was published as usable");taskDebugKernelState(task,TaskDebugState::Terminal);
 auto maximum=taskDebugCreateTask();std::atomic_ref<uint64_t>(tasks()[maximum.slot].source_sequence).store(UINT64_MAX-1,std::memory_order_release);
 {TaskDebugTurn turn(maximum);TaskDebugFrame activation(3);int opaque=0;TaskDebugFrameView view{&activation,&opaque,0,0};taskDebugPublish(std::span(&view,1),true);}
 require(load(tasks()[maximum.slot].source_sequence)==UINT64_MAX&&(load(tasks()[maximum.slot].flags)&taskDebugUnavailable)&&stops==beforeStops,"sequence overflow wrapped to a usable old publication");taskDebugKernelState(maximum,TaskDebugState::Terminal);require(load(nex_task_debug_catalog_v2.base.invalid_transitions)>before,"invalid debug metadata was silent");
}
void tests(){setup();
 require(executeTaskApplication(mainCode,{1000000,5000,2},{})==42,"dormant debugger changed source result");clean();require(!taskDebugEnabled()&&!stops&&!load(nex_task_debug_catalog_v2.base.magic),"dormant debug hooks initialized a catalog");
 {auto broken=metadata[0];broken.points=nullptr;bool rejected=false;try{nex_task_debug_prepare(&broken,1);}catch(const Trap &error){rejected=error.code=="E_DEBUG_INIT";}require(rejected&&!taskDebugEnabled(),"invalid preallocation metadata was accepted");}
 const TaskDebugCodeRegistry *batch[]={registries+2,registries+1,registries};
 auto reject=[&](const TaskDebugCodeRegistry *const *rows,int64_t count){bool rejected=false;try{nex_task_debug_prepare_registries(rows,count);}catch(const Trap &e){rejected=e.code=="E_DEBUG_INIT";}require(rejected&&!taskDebugEnabled(),"invalid original registry was accepted/published");};
 reject(nullptr,1);reject(batch,0);reject(batch,129);
 auto brokenRegistry=registries[0];brokenRegistry.abi=2;const TaskDebugCodeRegistry *one[]={&brokenRegistry};reject(one,1);
 brokenRegistry=registries[0];brokenRegistry.component="invalid-component";reject(one,1);
 brokenRegistry=registries[0];brokenRegistry.count=0;reject(one,1);
 brokenRegistry=registries[0];brokenRegistry.count=1;brokenRegistry.codes=nullptr;reject(one,1);
 brokenRegistry=registries[0];brokenRegistry.component="other";const TaskDebugCodeRegistry *overlap[]={registries,&brokenRegistry};reject(overlap,2);
 const TaskDebugCodeRegistry *duplicate[]={registries,registries};reject(duplicate,2);
 const TaskDebugCodeRegistry *empty[]={registries+2};reject(empty,1);
 auto copiedCode=metadata[0];auto duplicateName=metadata[1];duplicateName.name="main";TaskDebugCodeRegistry duplicateFunction{1,&duplicateName,1,"other"};const TaskDebugCodeRegistry *duplicateNames[]={registries,&duplicateFunction};reject(duplicateNames,2);
 nex_task_debug_prepare_registries(batch,3);require(taskDebugEnabled(),"debugger was not prepared");require(load(nex_task_debug_catalog_v2.base.magic)==taskDebugProviderCatalogMagic&&load(nex_task_debug_catalog_v2.base.abi)==2&&load(nex_task_debug_catalog_v2.base.header_size)==200,"catalog header differs from contract");
 require(!load(nex_task_debug_catalog_v1.magic),"provider registry overwrote legacy catalog");
 require(load(nex_task_debug_catalog_v2.registry_count)==3&&load(nex_task_debug_catalog_v2.registry_record_size)==24&&load(nex_task_debug_catalog_v2.code_ref_record_size)==16,"provider ref layout differs");
 auto *refs=reinterpret_cast<const TaskDebugCodeRef*>(load(nex_task_debug_catalog_v2.base.codes_address));auto *registryRefs=reinterpret_cast<const TaskDebugRegistryRef*>(load(nex_task_debug_catalog_v2.registries_address));
 require(registryRefs[0].registry_address==reinterpret_cast<uintptr_t>(registries)&&registryRefs[0].first_code==0&&registryRefs[1].first_code==1&&registryRefs[2].first_code==4&&!registryRefs[2].code_count,"registry ordering/pure zero range differs");
 for(size_t i=0;i<4;++i){require(refs[i].site_address==reinterpret_cast<uintptr_t>(metadata+i),"original site pointer was copied/retagged");require(taskDebugCodeIndex(metadata[i].code)==i,"original descriptor lookup differs");}
 nex_task_debug_prepare_registries(batch,3);const TaskDebugCodeRegistry *sorted[]={registries,registries+1,registries+2};nex_task_debug_prepare_registries(sorted,3);++checks;
 bool changed=false;TaskDebugCodeRegistry equivalent=registries[0];const TaskDebugCodeRegistry *different[]={&equivalent,registries+1,registries+2};try{nex_task_debug_prepare_registries(different,3);}catch(const Trap &e){changed=e.code=="E_DEBUG_INIT";}require(changed,"changed original registry identity was accepted");
 changed=false;try{nex_task_debug_prepare(&copiedCode,1);}catch(const Trap &e){changed=e.code=="E_DEBUG_INIT";}require(changed,"legacy prepare replaced active provider catalog");
 require(executeTaskApplication(mainCode,{1000000,5000,2},{})==42,"debug checkpoints changed result");clean();terminal();
 require(visits[0]==5&&visits[1]==2,"resume checkpoints/source visits differ");require(taskIds[0]&&taskIds[0]==taskIds[1],"logical direct child changed task identity");require(activationIds[0]&&activationIds[1]&&activationIds[0]!=activationIds[1],"logical child activation missing");
 bool trapped=false;try{executeTaskApplication(trapCode,{1000000,5000,2},{});}catch(const Trap &error){trapped=error.code=="E_ITEM";}require(trapped,"debugging masked source trap");clean();terminal();
 physical(false,false);physical(true,false);physical(true,true);transfer();concurrentPublication();
 require(!bad,"marker observed torn or misattributed source state");require(!load(nex_task_debug_catalog_v2.base.invalid_transitions),"valid runtime reported invalid debug transitions");require(!load(nex_task_debug_catalog_v2.base.dropped_frames)&&!load(nex_task_debug_catalog_v2.base.dropped_tasks),"small runtime dropped catalog metadata");failClosed();
}
}
extern "C" void nex_task_debug_stop_marker(const TaskDebugStop *stop)noexcept{
 ++stops;
 if(auto *group=markerGroup.load()){(void)group->externalStats();auto auxiliary=taskDebugCreateTask();taskDebugKernelState(auxiliary,TaskDebugState::Terminal);}
 if(!stop||stop->catalog_address!=reinterpret_cast<uintptr_t>(&nex_task_debug_catalog_v2.base)||stop->task_slot>=maximumTaskDebugTasks||stop->frame_slot>=maximumTaskDebugFrames){bad=true;return;}
 auto &task=tasks()[stop->task_slot];auto &frame=frames()[stop->frame_slot];const auto sequence=load(task.source_sequence);auto code=load(frame.code_index);
 if(sequence!=stop->source_sequence||(sequence&1)||load(task.id)!=stop->task_id||load(frame.id)!=stop->frame_id||load(frame.task_id)!=stop->task_id||load(frame.point_index)!=stop->point_index||!(load(task.flags)&taskDebugAtCheckpoint)||code>=4){bad=true;return;}
 // Real driver frames are inspected only while the owning source is stopped
 // in this marker. Module transfer cases intentionally use an opaque address.
 if(code<3){auto *native=reinterpret_cast<NativeTaskFrame*>(load(frame.frame_address));if(!native||!native->debugActivation||native->debugActivation.activation()!=stop->frame_id){bad=true;return;}}
 {std::lock_guard lock(observations);++visits[code];if(!activationIds[code])activationIds[code]=stop->frame_id;else if(code<2&&activationIds[code]!=stop->frame_id)bad=true;if(!taskIds[code])taskIds[code]=stop->task_id;}
 if(load(task.source_sequence)!=sequence)bad=true;
}
int main(){try{tests();std::cout<<"{\"ok\":true,\"checks\":"<<checks<<",\"markers\":"<<stops<<",\"catalog_abi\":2,\"execution_abi\":3,\"nonowning\":true}\n";return 0;}catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 1;}}
