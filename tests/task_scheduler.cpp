#include "nex_tasks.h"
#include <barrier>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <map>
#include <mutex>
#include <set>
#include <thread>

extern "C" nexrt::Handle *nex_string_new(const char*,int64_t,int64_t);
namespace {
using nexrt::TaskBody;using nexrt::TaskGroup;using nexrt::Value;
std::mutex allocationMutex,threadMutex;
std::map<const void*,int> allocations;
std::set<std::thread::id> workerThreads;
std::atomic<int> running{0},maximumRunning{0},destructors{0},phase{0},resumes{0};
size_t cases=0;
thread_local bool failHandle=false;
std::unique_ptr<std::barrier<>> rendezvous;
TaskGroup::Channel pipe;
TaskGroup::Ticket childTicket,cycleA,cycleB;
void require(bool value,const char *message){if(!value){std::fprintf(stderr,"task scheduler: %s\n",message);std::abort();}}
template<class F> void expect(const char *code,F action){
  bool caught=false;try{action();}catch(const nexrt::Trap &e){if(e.code!=code)std::fprintf(stderr,"expected%s got%s:%s\n",code,e.code.c_str(),e.what());require(e.code==code,"wrong checked error");caught=true;}require(caught,"expected checked error");
}
void clean(){
  require(!nexrt::inRequestScope(),"request context survived");require(running==0,"task survived group");require(nexrt::liveObjects==0,"managed value survived group");
  {std::lock_guard lock(allocationMutex);require(allocations.empty(),"owned allocation survived group");}
  {std::lock_guard lock(threadMutex);workerThreads.clear();}
  pipe={};childTicket={};cycleA={};cycleB={};phase=0;resumes=0;maximumRunning=0;destructors=0;++cases;nex_runtime_finish();
}
void advancePhase(int value){auto previous=phase.load();while(previous<value&&!phase.compare_exchange_weak(previous,value)){};}
void waitPhase(int target){
  auto deadline=std::chrono::steady_clock::now()+std::chrono::seconds(3);
  while(phase.load()<target){require(std::chrono::steady_clock::now()<deadline,"fixture synchronization timed out");std::this_thread::yield();}
}
struct Active {
  Active(){int value=++running,previous=maximumRunning.load();while(previous<value&&!maximumRunning.compare_exchange_weak(previous,value)){}std::lock_guard lock(threadMutex);workerThreads.insert(std::this_thread::get_id());}
  ~Active(){--running;++destructors;}
};
TaskBody overlap(TaskGroup &,Value input,Value captures){
  Active active;rendezvous->arrive_and_wait();
  auto *temporary=nex_string_new("temporary",9,10);(void)temporary;
  co_return Value(input.scalar+captures.scalar);
}
TaskBody increment(TaskGroup &group,Value input,Value){co_await group.yield();co_return Value(input.scalar+1);}
TaskBody checkpoint(TaskGroup &,Value input,Value){co_return input;}
TaskBody deepSpawn(TaskGroup &group,Value input,Value){
  if(input.scalar==0)co_return Value(0);
  auto child=group.spawn(deepSpawn,Value(input.scalar-1));auto event=co_await group.await(child);co_return event.value;
}
TaskBody nestedPool(TaskGroup &,Value,Value){TaskGroup other(1);co_return Value();}
TaskBody nested(TaskGroup &group,Value,Value){
  Active active;auto left=group.spawn(increment,Value(20));auto right=group.spawn(increment,Value(20));
  auto a=co_await group.await(left);auto b=co_await group.await(right);co_return Value(a.value.scalar+b.value.scalar);
}
TaskBody producer(TaskGroup &group,Value count,Value){
  Active active;
  for(int64_t i=0;i<count.scalar;++i){auto sent=co_await group.send(pipe,Value(i));require(sent.present,"channel rejected open send");}
  group.close(pipe);co_return count;
}
TaskBody consumer(TaskGroup &group,Value,Value){
  Active active;int64_t count=0,total=0;
  for(;;){auto received=co_await group.receive(pipe);if(!received.present)break;require(received.value.scalar==count,"channel FIFO order changed");total+=received.value.scalar;++count;}
  co_return Value(total);
}
TaskBody sendClosed(TaskGroup &group,Value,Value){auto sent=co_await group.send(pipe,Value(99));co_return Value(sent.present, true);}
TaskBody blockedSender(TaskGroup &group,Value,Value){
  Active active;require((co_await group.send(pipe,Value(1))).present,"first send failed");advancePhase(2);
  (void)co_await group.send(pipe,Value(2));co_return Value(2);
}
TaskBody blockedReceiver(TaskGroup &group,Value,Value){Active active;advancePhase(1);auto event=co_await group.receive(pipe);co_return event.present?event.value:Value(-1);}
TaskBody descendant(TaskGroup &group,Value,Value){Active active;childTicket=group.spawn(blockedReceiver);advancePhase(3);auto result=co_await group.await(childTicket);co_return result.value;}
TaskBody yielding(TaskGroup &group,Value,Value){Active active;for(;;){++resumes;co_await group.yield();}co_return Value();}
TaskBody ownedAcrossSuspend(TaskGroup &group,Value,Value){
  Active active;Value kept=nexrt::readHandle(nex_string_new("A\xf0\x9f\xa7\xa0",5,21));
  (void)nex_string_new("unkept",6,21);co_await group.yield();
  require(kept.object->text=="A\xf0\x9f\xa7\xa0","retained value lost across suspension");co_return kept;
}
TaskBody ordinaryFailure(TaskGroup &group,Value,Value){Active active;co_await group.yield();throw nexrt::Trap("E_ITEM","ordinary task failure",22);co_return Value();}
TaskBody resourceFailure(TaskGroup &group,Value,Value){Active active;co_await group.yield();throw nexrt::Trap("E_LIMIT","task-local resource failure",23);co_return Value();}
TaskBody invalidOutput(TaskGroup &,Value,Value){co_return Value(nexrt::diagnosticFile(9));}
TaskBody memoryFailure(TaskGroup &group,Value,Value){
  Active active;(void)nex_string_new("before",6,24);co_await group.yield();
  (void)nex_string_new("owned",5,24);failHandle=true;(void)nex_string_new("fail",4,24);co_return Value();
}
TaskBody cycle(TaskGroup &group,Value input,Value){while(!phase.load())co_await group.yield();auto event=co_await group.await(input.scalar?cycleA:cycleB);co_return event.value;}
TaskBody ignoredSuspend(TaskGroup &,Value,Value){Active active;co_await std::suspend_always{};co_return Value();}
const char *zero="0000000000000000000000000000000000000000000000000000000000000000";
const char *one="1111111111111111111111111111111111111111111111111111111111111111";
const nexrt::NativeFunctionSite function{zero,zero,zero};const nexrt::NativeSite site{&function,one,"task_failure",1,2};
TaskBody locatedFailure(TaskGroup &group,Value,Value){co_await group.yield();nexrt::runtimeFail("E_LOCATED","located task failure",nexrt::SourceLocation{25,&site});co_return Value();}
void run(){
  expect("E_TASK_SCOPE",[]{TaskGroup group;});clean();
  {nexrt::RequestScope request;expect("E_RANGE",[]{TaskGroup group(0);});expect("E_RANGE",[]{TaskGroup group(1,0);});expect("E_RANGE",[]{TaskGroup group(1,static_cast<size_t>(-1));});}clean();
  {nexrt::RequestScope request;TaskGroup group(4);rendezvous=std::make_unique<std::barrier<>>(4);std::vector<TaskGroup::Ticket> tasks;
   for(int64_t i=0;i<4;++i)tasks.push_back(group.spawn(overlap,Value(i),Value(40)));
   for(int64_t i=0;i<4;++i)require(group.join(tasks[size_t(i)]).scalar==i+40,"parallel result changed");group.finish();require(maximumRunning==4&&workerThreads.size()==4,"four workers did not overlap");}clean();
  for(size_t workers:{size_t(1),size_t(2),size_t(16)}){
    {nexrt::RequestScope request;TaskGroup group(workers);auto task=group.spawn(nested);require(group.join(task).scalar==42,"nested await deadlocked or changed result");group.finish();}clean();
  }
  for(size_t workers:{size_t(1),size_t(4),size_t(16)})for(size_t capacity:{size_t(0),size_t(1),size_t(17)}){
    {nexrt::RequestScope request(100000,5000);TaskGroup group(workers);pipe=group.channel(capacity);auto writer=group.spawn(producer,Value(1000));auto reader=group.spawn(consumer);
     require(group.join(reader).scalar==499500,"bounded channel result changed");require(group.join(writer).scalar==1000,"producer result changed");require(!group.join(group.spawn(sendClosed)).scalar,"closed channel accepted a send");require(!group.close(pipe),"channel close was not idempotent");group.finish();expect("E_TASK_SCOPE",[&]{(void)group.receive(pipe);});}clean();
  }
  {nexrt::RequestScope request;TaskGroup group(1);pipe=group.channel(1);auto sender=group.spawn(blockedSender);group.join(group.spawn(checkpoint));require(group.cancel(sender),"blocked sender did not cancel");expect("E_CANCELLED",[&]{(void)group.join(sender);});group.close(pipe);auto reader=group.spawn(blockedReceiver);require(group.join(reader).scalar==1,"canceled send escaped or removed previous buffered value");auto eof=group.spawn(blockedReceiver);require(group.join(eof).scalar==-1,"canceled send left a queued value");group.finish();}clean();
  {nexrt::RequestScope request;TaskGroup group(1);pipe=group.channel(0);auto reader=group.spawn(blockedReceiver);group.join(group.spawn(checkpoint));group.cancel(reader);expect("E_CANCELLED",[&]{(void)group.join(reader);});auto writer=group.spawn(producer,Value(1));auto next=group.spawn(consumer);require(group.join(next).scalar==0,"canceled receive stole next message");group.join(writer);group.finish();}clean();
  {nexrt::RequestScope request;TaskGroup group(2);pipe=group.channel(0);auto parent=group.spawn(descendant);waitPhase(3);group.cancel(parent);expect("E_CANCELLED",[&]{group.join(parent);});expect("E_CANCELLED",[&]{group.join(childTicket);});require(group.join(group.spawn(increment,Value(49))).scalar==50,"parent cancellation reached unrelated task");group.finish();}clean();
  {nexrt::RequestScope request(32,5000);TaskGroup group(1);auto task=group.spawn(yielding);expect("E_LIMIT",[&]{group.join(task);});expect("E_LIMIT",[&]{group.finish();});}clean();
  {nexrt::RequestScope request(100000,25);TaskGroup group(1);pipe=group.channel(0);auto task=group.spawn(blockedReceiver);expect("E_TIMEOUT",[&]{group.join(task);});expect("E_TIMEOUT",[&]{group.finish();});}clean();
  {nexrt::RequestScope request;auto coordinator=std::this_thread::get_id();std::atomic<bool> wrongThread{false};request.setCancellation([&]{if(std::this_thread::get_id()!=coordinator)wrongThread=true;return resumes.load()>20;});
   {TaskGroup group(2);auto task=group.spawn(yielding);expect("E_CANCELLED",[&]{group.join(task);});}require(!wrongThread,"worker ran coordinator cancellation callback");}clean();
  {nexrt::RequestScope request;TaskGroup group(2);auto value=group.join(group.spawn(ownedAcrossSuspend));require(value.object->text=="A\xf0\x9f\xa7\xa0","owned task result changed");group.finish();}clean();
  {nexrt::RequestScope request;TaskGroup group(2);group.spawn(ordinaryFailure);group.spawn(resourceFailure);expect("E_LIMIT",[&]{group.finish();});}clean();
  {nexrt::RequestScope request;TaskGroup group(1);auto task=group.spawn(ordinaryFailure);expect("E_ITEM",[&]{group.join(task);});group.finish();}clean();
  {nexrt::RequestScope request;TaskGroup group(1);group.spawn(ordinaryFailure);expect("E_ITEM",[&]{group.finish();});}clean();
  {nexrt::RequestScope request;TaskGroup group(1);auto task=group.spawn(memoryFailure);expect("E_MEMORY",[&]{group.join(task);});group.finish();}clean();
  {nexrt::RequestScope request;TaskGroup group(1);expect("E_TASK_VALUE",[&]{group.spawn(increment,Value(nexrt::diagnosticFile(8)));});auto task=group.spawn(invalidOutput);expect("E_TASK_VALUE",[&]{group.join(task);});group.finish();}clean();
  {nexrt::RequestScope request;TaskGroup group(1,2);auto a=group.spawn(increment),b=group.spawn(increment);expect("E_LIMIT",[&]{group.spawn(increment);});group.join(a);group.join(b);expect("E_RANGE",[&]{group.channel(65537);});group.channel(65536);expect("E_LIMIT",[&]{group.channel(1);});group.finish();}clean();
  {nexrt::RequestScope request;TaskGroup a(1),b(1);auto task=a.spawn(increment);auto channel=a.channel(1);expect("E_TASK_SCOPE",[&]{b.join(task);});expect("E_TASK_SCOPE",[&]{b.close(channel);});a.join(task);a.finish();b.finish();}clean();
  TaskGroup::Ticket expired;
  {nexrt::RequestScope request;{TaskGroup group(1);pipe=group.channel(0);expired=group.spawn(blockedReceiver);group.join(group.spawn(checkpoint));}require(destructors==1,"suspended frame cleanup did not run");TaskGroup next(1);expect("E_TASK_SCOPE",[&]{next.join(expired);});next.finish();}clean();
  {nexrt::RequestScope request;TaskGroup group(1);cycleA=group.spawn(cycle,Value(0));cycleB=group.spawn(cycle,Value(1));phase=1;expect("E_TASK_CYCLE",[&]{group.join(cycleA);});expect("E_TASK_CYCLE",[&]{group.join(cycleB);});group.finish();}clean();
  {nexrt::RequestScope request;TaskGroup group(1);auto task=group.spawn(ignoredSuspend);expect("E_TASK_STATE",[&]{group.join(task);});group.finish();}clean();
  {nexrt::RequestScope request;TaskGroup group(1);auto task=group.spawn(locatedFailure);bool caught=false;try{group.join(task);}catch(const nexrt::LocatedTrap &e){require(e.code=="E_LOCATED"&&e.line==25&&!e.source.empty(),"rich task error source lost");caught=true;}require(caught,"located task trap was not preserved");group.finish();}clean();
  for(size_t workers:{size_t(1),size_t(4),size_t(16)}){
    {nexrt::RequestScope request(100000,5000);TaskGroup group(workers);std::vector<TaskGroup::Ticket> tasks;
     for(int64_t i=0;i<2000;++i)tasks.push_back(group.spawn(increment,Value(i)));
     for(int64_t i=0;i<2000;++i)require(group.join(tasks[size_t(i)]).scalar==i+1,"large runnable queue lost a task");group.finish();}clean();
  }
  {nexrt::RequestScope request;TaskGroup group(4);auto task=group.spawn(deepSpawn,Value(300));expect("E_LIMIT",[&]{group.join(task);});group.finish();}clean();
  {nexrt::RequestScope request;TaskGroup group(1);auto task=group.spawn(nestedPool);expect("E_TASK_SCOPE",[&]{group.join(task);});group.finish();}clean();
}
}
extern "C" void nex_profile_enter(const char*,const char*,int64_t,const char*){}
extern "C" void nex_profile_leave(){}
extern "C" void nex_profile_unwind(){}
extern "C" void nex_profile_allocation(const void *pointer,size_t,int pool){
  if(pool==0&&failHandle){failHandle=false;throw std::bad_alloc();}
  std::lock_guard lock(allocationMutex);require(!allocations.contains(pointer),"duplicate tracked allocation");allocations.emplace(pointer,pool);
}
extern "C" void nex_profile_free(const void *pointer){std::lock_guard lock(allocationMutex);require(allocations.erase(pointer)==1,"untracked allocation released");}
int main(){run();std::printf("{\"ok\":true,\"cases\":%zu,\"source_async\":false}\n",cases);}
