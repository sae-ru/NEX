#include "nex_tasks.h"
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <functional>
#include <iostream>
#include <mutex>
#include <thread>
using namespace nexrt;
using namespace std::chrono_literals;
namespace {
void require(bool value,const char *message){if(!value){std::cerr<<"retirement check: "<<message<<"\n";throw std::runtime_error(message);}}
thread_local bool helperAwaitSuspend=false,insideCloseApi=false;
template<class F>void rejected(const char *code,F action){
  try{action();}catch(const Trap &e){require(e.code==code,"unexpected task retirement error");return;}
  throw std::runtime_error(std::string("missing ")+code);
}
struct Gate {
  std::mutex mutex;std::condition_variable changed;bool entered=false,released=false;
  void enter(){std::unique_lock lock(mutex);entered=true;changed.notify_all();changed.wait(lock,[&]{return released;});}
  bool reached(){std::lock_guard lock(mutex);return entered;}
  void open(){{std::lock_guard lock(mutex);released=true;}changed.notify_all();}
};
struct State {
  TaskGroup *group=nullptr;
  TaskGroup::Channel channel,second;
  TaskGroup::Ticket other;
  std::atomic<int> destroyed{0},queried{0};
  std::atomic<bool> afterScope{false},quotaHeld{false},nestedCancelled{false};
  std::atomic<bool> foreignHelperCleanup{false},finalizerInCloseApi{false};
  std::shared_ptr<Gate> gate;
  std::function<void()> hook;
  int mode=0;
  bool query=true;
};
// A host-owned managed allocation with an observable real destructor. It has
// no external/file/task authority and does not relax source snapshot guards.
struct AuditedData final:Data {
  std::shared_ptr<State> state;
  explicit AuditedData(std::shared_ptr<State> state):Data(Data::Record),state(std::move(state)){values.emplace_back(int64_t(42));}
  ~AuditedData(){
    state->finalizerInCloseApi=insideCloseApi;
    if(helperAwaitSuspend){state->foreignHelperCleanup=true;if(state->gate)state->gate->open();}
    if(state->gate)state->gate->enter();
    if(state->query){(void)state->group->externalStats();++state->queried;}
    if(state->hook)state->hook();
    ++state->destroyed;
  }
};
Value audited(const std::shared_ptr<State> &state){return Value(std::make_shared<AuditedData>(state));}
TaskBody sendTask(TaskGroup &group,std::shared_ptr<State> state){
  auto result=co_await group.send(state->channel,audited(state));co_return Value(result.present,true);
}
TaskBody sendFactory(TaskGroup &group,Value,Value,const void *p){return sendTask(group,*static_cast<const std::shared_ptr<State>*>(p));}
TaskBody secondSend(TaskGroup &group,std::shared_ptr<State> state){
  (void)co_await group.send(state->second,audited(state));co_return Value(int64_t(42));
}
TaskBody secondFactory(TaskGroup &group,Value,Value,const void *p){return secondSend(group,*static_cast<const std::shared_ptr<State>*>(p));}
TaskBody receiveTask(TaskGroup &group,std::shared_ptr<State> state){auto event=co_await group.receive(state->channel);co_return event.value;}
TaskBody receiveFactory(TaskGroup &group,Value,Value,const void *p){return receiveTask(group,*static_cast<const std::shared_ptr<State>*>(p));}
TaskBody returnTask(TaskGroup &,std::shared_ptr<State> state){co_return audited(state);}
TaskBody returnFactory(TaskGroup &group,Value,Value,const void *p){return returnTask(group,*static_cast<const std::shared_ptr<State>*>(p));}
TaskBody failTask(TaskGroup &,Value,Value){throw Trap("E_ITEM","controlled child failure",0);co_return Value();}
TaskBody pendingParent(TaskGroup &group,std::shared_ptr<State> state){
  auto sender=group.spawnWithContext(sendFactory,&state);co_await group.yield();
  require(state->destroyed==0,"pending send was not retained");
  if(state->mode==0){require(group.cancel(sender),"sender was not cancelled");}
  else group.close(state->channel);
  if(state->mode==0){bool caught=false;try{co_await group.await(sender);}catch(const Trap &e){require(e.code=="E_CANCELLED","wrong pending-send error");caught=true;}require(caught,"cancelled sender returned normally");}
  else require(!(co_await group.await(sender)).value.scalar,"closed pending send reported success");
  require(state->destroyed==1&&state->queried==1,"pending root cleanup did not precede completion");co_return Value(int64_t(42));
}
TaskBody pendingFactory(TaskGroup &group,Value,Value,const void *p){return pendingParent(group,*static_cast<const std::shared_ptr<State>*>(p));}
TaskBody cancelledEvent(TaskGroup &group,std::shared_ptr<State> state){
  auto receiver=group.spawnWithContext(receiveFactory,&state);co_await group.yield();
  require((co_await group.send(state->channel,audited(state))).present,"rendezvous did not create a delivered event");
  require(state->destroyed==0,"delivered event vanished before cancellation");require(group.cancel(receiver),"queued receiver cancellation failed");
  bool caught=false;try{co_await group.await(receiver);}catch(const Trap &e){require(e.code=="E_CANCELLED","wrong delivered-event failure");caught=true;}
  require(caught&&state->destroyed==1&&state->queried==1,"cancelled delivered event survived task completion");co_return Value(int64_t(42));
}
TaskBody eventFactory(TaskGroup &group,Value,Value,const void *p){return cancelledEvent(group,*static_cast<const std::shared_ptr<State>*>(p));}
TaskBody scopedResults(TaskGroup &group,std::shared_ptr<State> state){
  auto scope=group.openScope(1);auto child=group.spawnWithContext(returnFactory,&state);
  Value kept;
  if(state->mode==1)kept=(co_await group.await(child)).value;
  co_await group.leaveScope(scope);
  if(state->mode==1){require(state->destroyed==0&&kept.object,"scope revoked an independently retained passive alias");kept={};}
  require(state->destroyed==1&&state->queried==1,"scoped result cleanup did not precede publication");state->afterScope=true;co_return Value(int64_t(42));
}
TaskBody scopedResultFactory(TaskGroup &group,Value,Value,const void *p){return scopedResults(group,*static_cast<const std::shared_ptr<State>*>(p));}
TaskBody bufferedScope(TaskGroup &group,std::shared_ptr<State> state){
  auto scope=group.openScope(1);auto channel=group.channel(2);
  require((co_await group.send(channel,audited(state))).present,"buffered value send failed");
  co_await group.leaveScope(scope);
  require(state->destroyed==1&&state->queried==1,"buffer cleanup outlived scope publication");
  state->afterScope=true;
  if(state->mode==1)(void)group.channel(65536); // Retired buffer slots must now be available.
  co_return Value(int64_t(42));
}
TaskBody bufferFactory(TaskGroup &group,Value,Value,const void *p){return bufferedScope(group,*static_cast<const std::shared_ptr<State>*>(p));}
TaskBody quotaHelper(TaskGroup &group,std::shared_ptr<State> state){
  while(!state->gate->reached())co_await group.yield();
  bool held=false;try{(void)group.channel(65536);}catch(const Trap &e){held=e.code=="E_LIMIT";}
  state->quotaHeld=held&&!state->afterScope.load()&&state->destroyed==0;state->gate->open();co_return Value(int64_t(2));
}
TaskBody quotaFactory(TaskGroup &group,Value,Value,const void *p){return quotaHelper(group,*static_cast<const std::shared_ptr<State>*>(p));}
TaskBody failedResult(TaskGroup &group,std::shared_ptr<State> state){
  (void)group.openScope(1);group.spawn(failTask);co_return audited(state);
}
TaskBody failedFactory(TaskGroup &group,Value,Value,const void *p){return failedResult(group,*static_cast<const std::shared_ptr<State>*>(p));}
TaskBody reentrantParent(TaskGroup &group,std::shared_ptr<State> state){
  auto first=group.spawnWithContext(sendFactory,&state);state->other=group.spawnWithContext(secondFactory,&state);
  co_await group.yield();
  group.close(state->channel);
  require(state->nestedCancelled&&state->destroyed==2&&state->queried==2,"nested destructor callback did not retire both pending roots");
  require(!(co_await group.await(first)).value.scalar,"first closed sender succeeded");
  bool caught=false;try{co_await group.await(state->other);}catch(const Trap &e){caught=e.code=="E_CANCELLED";}
  require(caught,"reentrant cancellation was lost");co_return Value(int64_t(42));
}
TaskBody reentrantFactory(TaskGroup &group,Value,Value,const void *p){return reentrantParent(group,*static_cast<const std::shared_ptr<State>*>(p));}
TaskBody manyValues(TaskGroup &group,std::shared_ptr<State> state){
  auto scope=group.openScope(4);state->channel=group.channel(0);
  for(size_t i=0;i<64;++i)group.spawnWithContext(sendFactory,&state);
  co_await group.yield();group.close(state->channel);co_await group.leaveScope(scope);
  require(state->destroyed==64&&state->queried==64,"multiworker channel cleanup lost or duplicated roots");co_return Value(int64_t(42));
}
TaskBody manyFactory(TaskGroup &group,Value,Value,const void *p){return manyValues(group,*static_cast<const std::shared_ptr<State>*>(p));}
TaskBody deepScopes(TaskGroup &group,std::shared_ptr<State> state){
  for(size_t i=0;i<256;++i)(void)group.openScope(1);
  require(group.resourceAuthority().depth()==256,"logical native scope depth changed");
  group.spawnWithContext(returnFactory,&state);co_return Value(int64_t(42));
}
TaskBody deepFactory(TaskGroup &group,Value,Value,const void *p){return deepScopes(group,*static_cast<const std::shared_ptr<State>*>(p));}
TaskBody rootBuffer(TaskGroup &group,std::shared_ptr<State> state){
  (void)co_await group.send(state->channel,audited(state));co_return Value(int64_t(42));
}
TaskBody rootBufferFactory(TaskGroup &group,Value,Value,const void *p){return rootBuffer(group,*static_cast<const std::shared_ptr<State>*>(p));}
struct Pair {
  std::shared_ptr<State> first=std::make_shared<State>(),second=std::make_shared<State>();
  std::atomic<bool> helperStarted{false},helperEntered{false},helperReturned{false},closeReturned{false};
};
template<class F>bool eventually(F predicate){
  auto until=std::chrono::steady_clock::now()+5s;
  while(!predicate()){if(std::chrono::steady_clock::now()>=until)return false;std::this_thread::sleep_for(1ms);}return true;
}
struct MarkedYield {
  TaskGroup::Awaiter inner;Pair *pair;
  bool await_ready()const noexcept{return false;}
  bool await_suspend(TaskBody::Handle handle){
    struct Reset {bool previous=helperAwaitSuspend;~Reset(){helperAwaitSuspend=previous;}}reset;
    helperAwaitSuspend=true;pair->helperEntered=true;return inner.await_suspend(handle);
  }
  TaskEvent await_resume(){return inner.await_resume();}
};
TaskBody twoBuffers(TaskGroup &group,std::shared_ptr<Pair> pair){
  while(!pair->helperStarted.load())co_await group.yield();
  auto scope=group.openScope(1);auto first=group.channel(1),second=group.channel(1);
  (void)co_await group.send(first,audited(pair->first));(void)co_await group.send(second,audited(pair->second));
  co_await group.leaveScope(scope);co_return Value(int64_t(42));
}
TaskBody twoBufferFactory(TaskGroup &group,Value,Value,const void *p){return twoBuffers(group,*static_cast<const std::shared_ptr<Pair>*>(p));}
TaskBody isolatedHelper(TaskGroup &group,std::shared_ptr<Pair> pair){
  pair->helperStarted=true;
  require(eventually([&]{return pair->first->gate->reached();}),"foreign cleanup owner did not enter its first finalizer");
  co_await MarkedYield{group.yield(),pair.get()};pair->helperReturned=true;pair->second->gate->open();co_return Value(int64_t(2));
}
TaskBody isolatedHelperFactory(TaskGroup &group,Value,Value,const void *p){return isolatedHelper(group,*static_cast<const std::shared_ptr<Pair>*>(p));}
TaskBody closePair(TaskGroup &group,std::shared_ptr<Pair> pair){
  auto scope=group.openScope(1);auto channel=group.channel(0);pair->first->channel=pair->second->channel=channel;
  auto first=group.spawnWithContext(sendFactory,&pair->first),second=group.spawnWithContext(sendFactory,&pair->second);
  co_await group.yield();
  insideCloseApi=true;group.close(channel);insideCloseApi=false;pair->closeReturned=true;
  require(!(co_await group.await(first)).value.scalar&&!(co_await group.await(second)).value.scalar,"closed pair send succeeded");
  co_await group.leaveScope(scope);co_return Value(int64_t(42));
}
TaskBody closePairFactory(TaskGroup &group,Value,Value,const void *p){return closePair(group,*static_cast<const std::shared_ptr<Pair>*>(p));}
std::shared_ptr<Pair> pairFor(TaskGroup &group){
  auto pair=std::make_shared<Pair>();pair->first->group=pair->second->group=&group;
  pair->first->gate=std::make_shared<Gate>();pair->second->gate=std::make_shared<Gate>();return pair;
}
std::shared_ptr<State> stateFor(TaskGroup &group){auto state=std::make_shared<State>();state->group=&group;return state;}
void success(TaskGroup &group,TaskGroup::ContextFactory factory,const std::shared_ptr<State> &state){
  auto ticket=group.spawnWithContext(factory,&state);require(group.join(ticket).scalar==42,"retirement changed task result");group.finish();
}
}
int main(int argc,char **argv){try{
 size_t cases=0;std::string selection=argc>1?argv[1]:"";
 auto run=[&](const char *name,auto action){if(!selection.empty()&&selection!=name)return;auto before=liveObjects.load();action();require(liveObjects.load()==before,"retirement leaked managed values");++cases;std::cout<<"PASS "<<name<<std::endl;};
 run("cancel_pending",[]{RequestScope request(1000000,5000);TaskGroup group(1);auto state=stateFor(group);state->channel=group.channel(0);success(group,pendingFactory,state);});
 run("close_pending",[]{RequestScope request(1000000,5000);TaskGroup group(1);auto state=stateFor(group);state->mode=1;state->channel=group.channel(0);success(group,pendingFactory,state);});
 run("cancel_delivered_event",[]{RequestScope request(1000000,5000);TaskGroup group(1);auto state=stateFor(group);state->channel=group.channel(0);success(group,eventFactory,state);});
 run("scoped_result",[]{RequestScope request(1000000,5000);TaskGroup group(1);auto state=stateFor(group);success(group,scopedResultFactory,state);});
 run("scoped_passive_alias",[]{RequestScope request(1000000,5000);TaskGroup group(1);auto state=stateFor(group);state->mode=1;success(group,scopedResultFactory,state);});
 run("scoped_buffer",[]{RequestScope request(1000000,5000);TaskGroup group(1);auto state=stateFor(group);success(group,bufferFactory,state);});
 run("buffer_quota_fence",[]{
   RequestScope request(10000000,5000);TaskGroup group(2);auto state=stateFor(group);state->mode=1;state->gate=std::make_shared<Gate>();
   auto owner=group.spawnWithContext(bufferFactory,&state),helper=group.spawnWithContext(quotaFactory,&state);
   require(group.join(owner).scalar==42&&group.join(helper).scalar==2,"buffer quota helper changed result");group.finish();
   require(state->quotaHeld&&state->afterScope&&state->destroyed==1,"buffer allocation quota recycled before physical cleanup");
 });
 run("failed_owner_result",[]{
   RequestScope request(1000000,5000);TaskGroup group(1);auto state=stateFor(group);auto owner=group.spawnWithContext(failedFactory,&state);
   rejected("E_ITEM",[&]{group.join(owner);});require(state->destroyed==1&&state->queried==1,"failed owner published before discarded result cleanup");group.finish();
 });
 run("nested_reentrant_cleanup",[]{
   RequestScope request(1000000,5000);TaskGroup group(1);auto state=stateFor(group);state->channel=group.channel(0);state->second=group.channel(0);
   state->hook=[raw=state.get(),&group]{if(!raw->nestedCancelled.exchange(true))require(group.cancel(raw->other),"nested cancellation failed");};
   success(group,reentrantFactory,state);
 });
 run("multiworker_bounded_roots",[]{RequestScope request(10000000,5000);TaskGroup group(4,128);auto state=stateFor(group);success(group,manyFactory,state);});
 run("deep_scope_retirement",[]{
   RequestScope request(10000000,5000);TaskGroup group(1);group.enableResourceRegions();auto state=stateFor(group);success(group,deepFactory,state);
   require(state->destroyed==1&&state->queried==1,"256 nested scopes did not retire their owned result");
 });
 run("api_guard_ignores_foreign_cleanup",[]{
   RequestScope request(10000000,5000);TaskGroup group(2);auto pair=pairFor(group);std::atomic<bool> observed=false;
   std::jthread monitor([&]{
     observed=eventually([&]{return pair->helperEntered.load();});pair->first->gate->open();
     if(!observed)pair->second->gate->open();
   });
   auto owner=group.spawnWithContext(twoBufferFactory,&pair),helper=group.spawnWithContext(isolatedHelperFactory,&pair);
   require(group.join(owner).scalar==42&&group.join(helper).scalar==2,"isolated API helper changed result");monitor.join();group.finish();
   require(observed&&pair->helperReturned&&!pair->second->foreignHelperCleanup,"helper source API stole an unrelated finalizer");
   require(pair->first->destroyed==1&&pair->second->destroyed==1,"foreign finalizer isolation lost cleanup");
 });
 run("api_guard_waits_stolen_completion",[]{
   RequestScope request(10000000,5000);TaskGroup group(2);auto pair=pairFor(group);std::atomic<bool> observed=false,premature=false;
   std::jthread monitor([&]{
     observed=eventually([&]{return pair->first->gate->reached()&&pair->second->gate->reached();});
     if(observed){
       bool firstOwn=pair->first->finalizerInCloseApi.load(),secondOwn=pair->second->finalizerInCloseApi.load();
       observed=firstOwn!=secondOwn;
       auto own=firstOwn?pair->first:pair->second,stolen=firstOwn?pair->second:pair->first;
       own->gate->open();observed=observed.load()&&eventually([&]{return own->destroyed.load()==1;});
       std::this_thread::sleep_for(25ms);premature=pair->closeReturned.load()||stolen->destroyed.load()!=0;
     }
     pair->first->gate->open();pair->second->gate->open();
   });
   auto owner=group.spawnWithContext(closePairFactory,&pair);require(group.join(owner).scalar==42,"stolen completion changed owner result");
   monitor.join();group.finish();require(observed&&!premature&&pair->closeReturned,"API returned before its stolen finalizer physically settled");
 });
 run("root_buffer_shutdown",[]{
   RequestScope request(1000000,5000);TaskGroup group(1);auto state=stateFor(group);state->channel=group.channel(1);
   auto ticket=group.spawnWithContext(rootBufferFactory,&state);require(group.join(ticket).scalar==42&&state->destroyed==0,"buffer lost its owner before shutdown");
   group.finish();require(state->destroyed==1&&state->queried==1,"root shutdown retained buffered allocation");
 });
 run("root_results_remain_joinable",[]{
   RequestScope request(1000000,5000);std::shared_ptr<State> state;
   {TaskGroup group(1);state=stateFor(group);state->query=false;auto ticket=group.spawnWithContext(returnFactory,&state);
    {auto first=group.join(ticket),second=group.join(ticket);require(first.object==second.object&&state->destroyed==0,"root result lost alias identity");}
    group.finish();require(state->destroyed==0&&group.join(ticket).object,"finish discarded a still-joinable root result");}
   require(state->destroyed==1,"group lifetime did not release retained root result");
 });
 require(cases>0,"unknown retirement scenario");std::cout<<"TASK VALUE RETIREMENT CASES "<<cases<<"\n";return 0;
}catch(const std::exception &e){std::cerr<<e.what()<<"\n";return 1;}}
