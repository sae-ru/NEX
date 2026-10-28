#include "nex_task_frame.h"
#include "nex_profile.h"
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sys/wait.h>
#include <unistd.h>
using namespace nexrt;
extern "C" const char *nex_profile_build_info(){return "{\"schema\":\"nex.profile-build/2\",\"task_profile_catalog\":\"registry-probe\"}";}
namespace {
unsigned checks=0;
void require(bool yes,const char *text){++checks;if(!yes)throw std::runtime_error(text);}
const TaskProfileCodeSite leafSites[]={{"leaf","registry.nex","leaf-hash",1},{"pure","registry.nex","pure-hash",2}};
const TaskProfileCodeSite rootSites[]={{"main","registry.nex","root-hash",3}};
const TaskProfileCodeSite expandedRootSites[]={{"main","registry.nex","root-hash",3},{"extra","registry.nex","extra-hash",4}};
const TaskProfileCodeRegistry leaf{1,leafSites,2,"leaf"},root{1,rootSites,1,"root"};
void helper(){nex_profile_enter("pure","registry.nex",2,"pure-hash");auto h=makeHandle(Value(string("owned🧠")));nex_release(h);nex_profile_leave();}
int64_t step(void *pointer){auto &frame=*static_cast<NativeTaskFrame*>(pointer);if(!frame.pc){frame.pc=1;return 1;}helper();frame.completed=true;frame.result=Value(int64_t(42));return 0;}
TaskBody body(TaskGroup &group,Value,Value,const void *context){return executeTaskFrame(group,NativeTaskFrame(*static_cast<const TaskCodeDescriptor*>(context),{},Value(int64_t(0))));}
void reject(const TaskProfileCodeRegistry *const *input,int64_t count){bool rejected=false;try{nex_task_profile_prepare_registries(input,count);}catch(const Trap &e){rejected=e.code=="E_PROFILE_INIT";}require(rejected,"invalid registry accepted");require(!taskProfileCollector(),"invalid preparation published a collector");}
void child(const std::string &mode){
 if(mode=="tracy"){::setenv("NEX_TRACY","1",1);bool rejected=false;const TaskProfileCodeRegistry *rows[]={&root};try{nex_task_profile_prepare_registries(rows,1);}catch(const Trap &e){rejected=e.code=="E_TASK_PROFILE";}require(rejected&&!taskProfileCollector(),"Tracy initialized before rejection");return;}
 if(mode=="invalid"){TaskProfileCodeRegistry bad=root;const TaskProfileCodeRegistry *rows[]={&bad,&leaf};bad.abi=2;reject(rows,2);bad=root;bad.count=0;reject(rows,2);bad=root;bad.count=16385;reject(rows,2);bad=root;bad.component="bad-name";reject(rows,2);bad=root;bad.component="leaf";reject(rows,2);bad=root;bad.sites=leafSites;reject(rows,2);bad=root;reject(rows,0);reject(nullptr,1);return;}
 if(mode=="duplicate"){const TaskProfileCodeSite duplicate[]={{"main","other.nex","different",1}};const TaskProfileCodeRegistry other{1,duplicate,1,"other"};const TaskProfileCodeRegistry *rows[]={&root,&other};reject(rows,2);return;}
 const TaskProfileCodeRegistry *rows[]={&root,&leaf};nex_task_profile_prepare_registries(rows,2);
 require(bool(taskProfileCollector())==(mode!="dormant"),"dormant preparation allocated collector");
 if(mode=="dormant"){helper();return;}
 require(taskProfileSiteIndex(&leafSites[0])==0&&taskProfileSiteIndex(&leafSites[1])==1&&taskProfileSiteIndex(&rootSites[0])==2,"range to dense identity mismatch");
 TaskProfileCodeSite foreign{"foreign","other","hash",1};require(!taskProfileSiteIndex(&foreign),"foreign site accepted");
 const TaskProfileCodeRegistry *again[]={&leaf,&root};nex_task_profile_prepare_registries(again,2);
 TaskProfileCodeRegistry changed=root;changed.sites=expandedRootSites;changed.count=2;const TaskProfileCodeRegistry *other[]={&changed,&leaf};bool mismatch=false;try{nex_task_profile_prepare_registries(other,2);}catch(const Trap &e){mismatch=e.code=="E_PROFILE_INIT";}require(mismatch,"changed registry replaced live collector");
 TaskCodeDescriptor descriptor{};descriptor.step=step;descriptor.profileSite=&rootSites[0];descriptor.abi=taskCodeABI;descriptor.resultKind=0;descriptor.requirements=taskCodeDeclaredTask;
 auto invalid=descriptor;invalid.profileSite=&foreign;bool foreignRejected=false;try{NativeTaskFrame frame(invalid,{},Value(int64_t(0)));}catch(const DataError &e){foreignRejected=e.code=="E_TASK_STATE";}require(foreignRejected,"foreign descriptor profile site accepted");
 {RequestScope request;TaskGroup group(2);auto ticket=group.spawnWithContext(body,&descriptor);require(group.join(ticket).scalar==42,"profile altered source result");group.finish();}
 auto *collector=taskProfileCollector();auto retirement=collector->task();
 {TaskProfileTurnScope active(retirement);auto before=collector->snapshot().tasks.back().resumes;
  {TaskProfileRetirementScope nested(retirement);require(currentTaskProfileTask()==retirement.id(),"retirement replaced the active executor");}
  require(collector->snapshot().tasks.back().resumes==before,"nested retirement counted a source resume");}
 collector->terminal(retirement,TaskProfileTaskOutcome::Completed);auto before=collector->snapshot().tasks.back();
 {TaskProfileRetirementScope detached(retirement);require(!currentTaskProfileTask(),"retirement reactivated a completed source task");auto value=makeHandle(Value(string("late result cleanup")));nex_release(value);}
 auto after=collector->snapshot().tasks.back();require(after.terminal&&after.terminalWallNs==before.terminalWallNs&&after.resumes==before.resumes&&after.activeInvocations==0,"late retirement changed source completion");require(after.executorElapsedNs>=before.executorElapsedNs&&after.executorCpuNs>=before.executorCpuNs,"retirement executor accounting regressed");
 auto snapshot=collector->snapshot();require(snapshot.functions.size()==3,"site footprint mismatch");require(snapshot.functions[0].calls==0&&snapshot.functions[1].calls==1&&snapshot.functions[2].calls==1,"helper/activation counted incorrectly");require(snapshot.functions[2].completed==1,"root activation did not complete");for(const auto &task:snapshot.tasks)require(task.terminal&&task.activeInvocations==0,"profile task did not retire");require(!snapshot.drops.incomplete,"multi-range measurement incomplete");require(liveObjects.load()==0,"retained source object leak");nex_runtime_finish();
}
}
int main(int argc,char **argv){try{if(argc>1){child(argv[1]);return 0;}char path[]="/tmp/nex-task-registry-XXXXXX";require(::mkdtemp(path),"mkdtemp failed");auto report=std::filesystem::path(path)/"runtime.json";
 for(const auto *mode:{"invalid","duplicate","tracy","dormant","profile"}){auto pid=::fork();require(pid>=0,"fork failed");if(!pid){::unsetenv("NEX_TRACY");::unsetenv("NEX_PROFILE_OUTPUT");if(std::string(mode)=="profile"||std::string(mode)=="duplicate")::setenv("NEX_PROFILE_OUTPUT",report.c_str(),1);::execl(argv[0],argv[0],mode,nullptr);::_exit(127);}int status=0;require(::waitpid(pid,&status,0)==pid&&WIFEXITED(status)&&WEXITSTATUS(status)==0,"registry child failed");}
 std::ifstream input(report);std::string json{std::istreambuf_iterator<char>(input),{}};require(json.find("nex.profile-runtime/3")!=std::string::npos,"provider raw3 absent");require(json.find("\"catalog\":{\"schema\":\"nex.task-profile-runtime-catalog/1\"")!=std::string::npos,"raw range catalog absent");require(json.find("\"incomplete\":false")!=std::string::npos,"valid registry report incomplete");for(const auto *key:{"registry_record_capacity","registry_record_capacity_bytes","registry_component_text_capacity_bytes","metadata_record_capacity_bytes","metadata_text_capacity_bytes","site_lookup_capacity_bytes"})require(json.find(std::string("\"")+key+"\":")!=std::string::npos,"provider backing capacity gauge absent");std::filesystem::remove_all(path);std::cout<<"task profile registry PASS "<<checks<<" parent checks +isolated children\n";return 0;
 }catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 1;}}
