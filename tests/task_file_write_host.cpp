#include "nex_task_file_write.h"
#include "nex_host.h"
#include "nex_tasks.h"
#include <atomic>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <future>
#include <iostream>
#include <thread>
#include <unistd.h>

namespace fs=std::filesystem;
using namespace nexrt;
using namespace std::chrono_literals;
namespace {
size_t cases=0;
void require(bool value,const char *message){if(!value)throw std::runtime_error(message);}
template<class F>void rejects(const std::string &code,F operation){
  try{operation();}catch(const DataError &error){
    if(error.code!=code)throw std::runtime_error("expected "+code+", got "+error.code);
    return;
  }
  throw std::runtime_error("expected "+code);
}
template<class F>void scenario(const char *name,F operation){operation();++cases;std::cout<<"PASS "<<name<<'\n';}
struct Directory {
  fs::path path;
  Directory(){auto pattern=(fs::temp_directory_path()/"nex-write-host-XXXXXX").string();auto p=::mkdtemp(pattern.data());require(p,"mkdtemp failed");path=p;}
  ~Directory(){std::error_code ignored;fs::remove_all(path,ignored);}
};
void write(const fs::path &path,const std::string &bytes){std::ofstream f(path,std::ios::binary);f.write(bytes.data(),bytes.size());require(bool(f),"fixture write failed");}
std::string read(const fs::path &path){std::ifstream f(path,std::ios::binary);require(bool(f),"fixture read failed");return {std::istreambuf_iterator<char>(f),{}};}
std::span<const uint8_t> raw(const std::string &s){return {reinterpret_cast<const uint8_t*>(s.data()),s.size()};}
bool temporaryExists(const fs::path &root){for(const auto &e:fs::directory_iterator(root))if(e.path().filename().string().starts_with(".nex-write-"))return true;return false;}
void noTemporary(const fs::path &root){require(!temporaryExists(root),"unpublished temporary leaked");}
void waitReady(TaskExternalPool &pool,const TaskExternalTicket &ticket){
  auto limit=std::chrono::steady_clock::now()+5s;
  while(!pool.ready(ticket)&&std::chrono::steady_clock::now()<limit)std::this_thread::yield();
  require(pool.ready(ticket),"external write did not physically settle");
}
Value execute(const PreparedTaskFileWrite &prepared){
  TaskExternalPool pool;auto ticket=pool.submit(1,prepared.operation(),prepared.reservation());
  waitReady(pool,ticket);auto result=prepared.admit(pool.take(ticket));
  require(pool.stats().tickets==0&&pool.stats().reservedBytes==0,"transport credits leaked");return result;
}
void successValue(const Value &value){require(value.object&&value.object->kind==Data::Success&&unwrap(value).tag==Value::Boolean&&unwrap(value).scalar==1,"write did not admit result<bool>");}
void failureValue(const Value &value,const std::string &code){require(value.object&&value.object->kind==Data::Failure&&value.object->text==code,"ordinary write error was not a typed result");}
struct Gate {
  std::promise<void> entered,release;
  std::shared_future<void> released=release.get_future().share();
  std::future<void> began=entered.get_future();
  std::function<bool()> condition;
  std::atomic<bool> blocked{false},destroyed{false};
  explicit Gate(std::function<bool()> condition):condition(std::move(condition)){}
};
struct Release {
  std::shared_ptr<Gate> gate;
  bool done=false;
  void now(){if(!done){gate->release.set_value();done=true;}}
  ~Release(){now();}
};
struct GatedOperation final:TaskExternalOperation {
  std::shared_ptr<TaskExternalOperation> operation;std::shared_ptr<Gate> gate;
  GatedOperation(std::shared_ptr<TaskExternalOperation> operation,std::shared_ptr<Gate> gate):operation(std::move(operation)),gate(std::move(gate)){}
  ~GatedOperation(){gate->destroyed=true;}
  TaskExternalResult run(const TaskExternalControl &control)override{
    FileScope denied(false);
    return operation->run(TaskExternalControl([&]{
      control.checkpoint();
      if(!gate->blocked.load()&&gate->condition()){
        gate->blocked=true;gate->entered.set_value();gate->released.wait();
      }
      control.checkpoint();
    }));
  }
};
struct TaskState {
  FileWriteGrant grant;std::string bytes;std::shared_ptr<Gate> gate;
  std::promise<void> progress;std::atomic<bool> admitted{false};
};
std::shared_ptr<TaskState> factoryState;
TaskBody writeTask(TaskGroup &group,std::shared_ptr<TaskState> state){
  co_await group.yield();
  PreparedTaskFileWrite prepared(state->grant,"task",raw(state->bytes));
  auto ticket=group.submitExternal(std::make_shared<GatedOperation>(prepared.operation(),state->gate),prepared.reservation());
  auto result=co_await group.awaitExternal(ticket);
  successValue(prepared.admit(std::move(result)));state->admitted=true;
  co_return Value(int64_t(42));
}
TaskBody progressTask(TaskGroup &,std::shared_ptr<TaskState> state){state->progress.set_value();co_return Value(int64_t(0));}
TaskBody writeFactory(TaskGroup &group,Value,Value){return writeTask(group,factoryState);}
TaskBody progressFactory(TaskGroup &group,Value,Value){return progressTask(group,factoryState);}
void tests(){
  Directory directory;auto root=directory.path/"root",other=directory.path/"other";fs::create_directory(root);fs::create_directory(other);
  TextFiles writable(root.string(),true),readonly(root.string(),false);const auto initialObjects=liveObjects.load();
  const std::string old="old complete value",next(200000,'x');
  scenario("owned_binary_snapshot_and_exact_reservation",[&]{
    FileScope scope(writable);auto grant=captureFileWriteGrant(false);std::string input("A\0\xff",3);
    PreparedTaskFileWrite prepared(grant,"bytes",raw(input));require(prepared.reservation()==8,"snapshot charged wrong payload/path bytes");
    input.assign(1000000,'z');successValue(execute(prepared));require(read(root/"bytes")==std::string("A\0\xff",3),"worker used mutable caller storage");
  });
  scenario("text_unicode_nul_bom",[&]{
    FileScope scope(writable);std::string text="\xef\xbb\xbf\xd0\xaf";text+='\0';text+="\xf0\x9f\x98\x80";
    successValue(execute(PreparedTaskFileWrite(captureFileWriteGrant(false),"text",raw(text),true)));require(read(root/"text")==text,"text encoding changed");
  });
  scenario("empty_and_maximum_payload",[&]{
    FileScope scope(writable);auto grant=captureFileWriteGrant(false);std::string empty,maximum(TextFiles::byteLimit,'m');
    successValue(execute(PreparedTaskFileWrite(grant,"empty",raw(empty))));require(fs::file_size(root/"empty")==0,"empty file was not published");
    successValue(execute(PreparedTaskFileWrite(grant,"maximum",raw(maximum))));require(read(root/"maximum")==maximum,"maximum file changed");
  });
  scenario("preparation_rejects_oversize_and_invalid_text_before_mutation",[&]{
    FileScope scope(writable);auto grant=captureFileWriteGrant(false);write(root/"protected",old);std::string tooLarge(TextFiles::byteLimit+1,'z'),bad("\xed\xa0\x80",3);
    rejects("LIMIT",[&]{(void)PreparedTaskFileWrite(grant,"protected",raw(tooLarge));});
    rejects("E_UTF8",[&]{(void)PreparedTaskFileWrite(grant,"protected",raw(bad),true);});require(read(root/"protected")==old,"invalid preparation modified destination");noTemporary(root);
  });
  scenario("paths_and_maximum_retained_path",[&]{
    FileScope scope(writable);auto grant=captureFileWriteGrant(false);
    for(const auto &path:std::vector<std::string>{"../escape","/absolute","a//b","a/./b","a/../b",std::string("a\0b",3)})rejects("VALIDATION",[&]{(void)grant.lease(path);});
    rejects("E_UTF8",[&]{(void)grant.lease(std::string("\xff",1));});std::string path;
    for(int i=0;i<17;++i){if(i)path+='/';path.append(240,'p');}
    PreparedTaskFileWrite boundary(grant,path,{});require(boundary.reservation()==4096,"maximum path reservation is not exact");
    rejects("VALIDATION",[&]{(void)grant.lease(path+"x");});
  });
  scenario("readonly_and_missing_grants_are_lazy_and_cannot_escalate",[&]{
    {FileScope scope(readonly);auto grant=captureFileWriteGrant(false);rejects("CAPABILITY",[&]{(void)grant.lease("bytes");});require(captureFileReadGrant(false).lease("bytes").read().size()==3,"read authority changed");}
    FileScope denied(false);auto grant=captureFileWriteGrant(false);rejects("CAPABILITY",[&]{grant.check();});rejects("CAPABILITY",[]{(void)FileWriteGrant().lease("x");});
    rejects("E_RESOURCE_CLOSED",[]{FileWriteLease().write({});});
  });
  scenario("leaf_symlink_does_not_write_target",[&]{
    write(other/"outside",old);fs::create_symlink(other/"outside",root/"link");FileScope scope(writable);
    failureValue(execute(PreparedTaskFileWrite(captureFileWriteGrant(false),"link",raw(next))),"VALIDATION");require(read(other/"outside")==old,"symlink target was overwritten");noTemporary(root);
  });
  scenario("parent_symlink_and_directory_are_rejected",[&]{
    fs::create_directory_symlink(other,root/"linked");fs::create_directory(root/"directory");FileScope scope(writable);auto grant=captureFileWriteGrant(false);
    failureValue(execute(PreparedTaskFileWrite(grant,"linked/outside",raw(next))),"VALIDATION");
    failureValue(execute(PreparedTaskFileWrite(grant,"directory",raw(next))),"VALIDATION");require(read(other/"outside")==old,"parent symlink escaped root");
  });
  scenario("missing_parent_is_ordinary_result",[&]{FileScope scope(writable);failureValue(execute(PreparedTaskFileWrite(captureFileWriteGrant(false),"absent/child",raw(next))),"NOT_FOUND");noTemporary(root);});
  scenario("captured_root_and_no_worker_TLS_discovery",[&]{
    FileScope scope(writable);auto grant=captureFileWriteGrant(false);PreparedTaskFileWrite prepared(grant,"captured",raw(next));
    auto value=std::async(std::launch::async,[&]{TextFiles wrong(other.string(),true);FileScope scope(wrong);return prepared.operation()->run(TaskExternalControl{});}).get();
    successValue(prepared.admit(std::move(value)));require(read(root/"captured")==next&&!fs::exists(other/"captured"),"worker redirected captured authority");
  });
  scenario("request_revocation_prevents_a_new_write",[&]{
    FileScope scope(writable);FileWriteGrant grant;{RequestScope request;grant=captureFileWriteGrant(false);grant.check();}
    rejects("E_RESOURCE_SCOPE",[&]{(void)grant.lease("revoked");});require(!fs::exists(root/"revoked"),"revoked grant published a file");
  });
  scenario("scope_revocation_during_write_keeps_old_destination_and_physical_credit",[&]{
    auto scope=std::make_unique<FileScope>(writable);auto grant=captureFileWriteGrant(false);write(root/"revoked",old);
    PreparedTaskFileWrite prepared(grant,"revoked",raw(next));auto gate=std::make_shared<Gate>([&]{return temporaryExists(root);});Release release{gate};
    TaskExternalPool pool;auto ticket=pool.submit(1,std::make_shared<GatedOperation>(prepared.operation(),gate),prepared.reservation());
    require(gate->began.wait_for(5s)==std::future_status::ready,"write did not enter temporary stage");scope.reset();
    require(!pool.ready(ticket)&&pool.stats().reservedBytes==prepared.reservation(),"revocation returned credits before physical completion");
    release.now();waitReady(pool,ticket);require(gate->destroyed,"adapter outlived physical publication");rejects("E_RESOURCE_SCOPE",[&]{(void)pool.take(ticket);});
    require(read(root/"revoked")==old,"revoked precommit write changed destination");noTemporary(root);
  });
  scenario("cancellation_before_commit_is_atomic_and_drained",[&]{
    FileScope scope(writable);write(root/"cancel",old);PreparedTaskFileWrite prepared(captureFileWriteGrant(false),"cancel",raw(next));
    auto gate=std::make_shared<Gate>([&]{return temporaryExists(root);});Release release{gate};TaskExternalPool pool;
    auto ticket=pool.submit(1,std::make_shared<GatedOperation>(prepared.operation(),gate),prepared.reservation());
    require(gate->began.wait_for(5s)==std::future_status::ready,"cancel fixture did not enter write");pool.cancel(ticket);
    require(!pool.ready(ticket)&&pool.stats().reservedBytes==prepared.reservation(),"cancel pretended physical completion");release.now();waitReady(pool,ticket);
    rejects("E_CANCELLED",[&]{(void)pool.take(ticket);});require(pool.stats().tickets==0&&pool.stats().reservedBytes==0,"cancelled ticket leaked");require(read(root/"cancel")==old,"cancelled precommit destination was partial");noTemporary(root);
  });
  scenario("deadline_before_commit_keeps_old_destination",[&]{
    FileScope scope(writable);write(root/"deadline",old);PreparedTaskFileWrite prepared(captureFileWriteGrant(false),"deadline",raw(next));TaskExternalPool pool;
    auto ticket=pool.submit(1,prepared.operation(),prepared.reservation(),TaskExternalControl([&]{if(temporaryExists(root))throw DataError("E_TIMEOUT","controlled deadline");}));
    waitReady(pool,ticket);rejects("E_TIMEOUT",[&]{(void)pool.take(ticket);});require(read(root/"deadline")==old,"deadline published a partial value");noTemporary(root);
  });
  scenario("cancelled_new_file_remains_absent",[&]{
    FileScope scope(writable);PreparedTaskFileWrite prepared(captureFileWriteGrant(false),"unpublished",raw(next));
    auto gate=std::make_shared<Gate>([&]{return temporaryExists(root);});Release release{gate};TaskExternalPool pool;
    auto ticket=pool.submit(1,std::make_shared<GatedOperation>(prepared.operation(),gate),prepared.reservation());
    require(gate->began.wait_for(5s)==std::future_status::ready,"new-file write did not enter temporary stage");pool.cancel(ticket);release.now();waitReady(pool,ticket);
    rejects("E_CANCELLED",[&]{(void)pool.take(ticket);});require(!fs::exists(root/"unpublished"),"cancelled new file was published");noTemporary(root);
  });
  scenario("concurrent_replacements_never_expose_partial_files",[&]{
    FileScope scope(writable);auto grant=captureFileWriteGrant(false);std::string a(TextFiles::byteLimit,'a'),b(TextFiles::byteLimit,'b');write(root/"race",old);
    PreparedTaskFileWrite first(grant,"race",raw(a)),second(grant,"race",raw(b));auto gate1=std::make_shared<Gate>([]{return true;}),gate2=std::make_shared<Gate>([]{return true;});
    Release release1{gate1},release2{gate2};TaskExternalPool pool;
    auto one=pool.submit(1,std::make_shared<GatedOperation>(first.operation(),gate1),first.reservation());
    auto two=pool.submit(2,std::make_shared<GatedOperation>(second.operation(),gate2),second.reservation());
    require(gate1->began.wait_for(5s)==std::future_status::ready&&gate2->began.wait_for(5s)==std::future_status::ready,"both IO workers did not run");
    require(pool.stats().running==2,"writes were not independently admitted");release1.now();release2.now();
    auto until=std::chrono::steady_clock::now()+5s;
    do{auto value=read(root/"race");require(value==old||value==a||value==b,"concurrent read saw a partial replacement");require(std::chrono::steady_clock::now()<until,"concurrent writes stalled");}while(!pool.ready(one)||!pool.ready(two));
    successValue(first.admit(pool.take(one)));successValue(second.admit(pool.take(two)));auto value=read(root/"race");require(value==a||value==b,"last rename did not publish a complete value");noTemporary(root);
  });
  scenario("postcommit_cancel_suppresses_result_without_claiming_rollback",[&]{
    FileScope scope(writable);write(root/"committed",old);PreparedTaskFileWrite prepared(captureFileWriteGrant(false),"committed",raw(next));
    auto gate=std::make_shared<Gate>([&]{return !temporaryExists(root)&&read(root/"committed")==next;});Release release{gate};TaskExternalPool pool;
    auto ticket=pool.submit(1,std::make_shared<GatedOperation>(prepared.operation(),gate),prepared.reservation());require(gate->began.wait_for(5s)==std::future_status::ready,"postcommit checkpoint not reached");
    pool.cancel(ticket);require(!pool.ready(ticket),"postcommit cancellation skipped physical retirement");release.now();waitReady(pool,ticket);rejects("E_CANCELLED",[&]{(void)pool.take(ticket);});require(read(root/"committed")==next,"postcommit cancellation rolled back completed side effect");noTemporary(root);
  });
  scenario("revocation_after_physical_completion_blocks_value_admission",[&]{
    auto scope=std::make_unique<FileScope>(writable);PreparedTaskFileWrite prepared(captureFileWriteGrant(false),"late",raw(next));TaskExternalPool pool;
    auto ticket=pool.submit(1,prepared.operation(),prepared.reservation());waitReady(pool,ticket);auto result=pool.take(ticket);scope.reset();
    rejects("E_RESOURCE_SCOPE",[&]{(void)prepared.admit(std::move(result));});require(read(root/"late")==next,"late revocation pretended rollback");
  });
  scenario("raw_result_protocol_rejects_payload_and_unknown_error",[&]{
    FileScope scope(writable);PreparedTaskFileWrite prepared(captureFileWriteGrant(false),"protocol",{});TaskExternalResult data;data.bytes.push_back(1);
    rejects("E_LIMIT",[&]{(void)prepared.admit(std::move(data));});TaskExternalResult unknown;unknown.errorCode="UNEXPECTED";
    rejects("E_TASK_VALUE",[&]{(void)prepared.admit(std::move(unknown));});require(!fs::exists(root/"protocol"),"admission wrote a file");
  });
  scenario("read_and_write_leases_share_real_resource_quota",[&]{
    FileScope scope(writable);auto readGrant=captureFileReadGrant(false);auto writeGrant=captureFileWriteGrant(false);
    std::vector<FileReadLease> reads;std::vector<FileWriteLease> writes;
    for(int i=0;i<32;++i){reads.push_back(readGrant.lease("bytes"));writes.push_back(writeGrant.lease("quota"));}
    rejects("E_RESOURCE_LIMIT",[&]{(void)writeGrant.lease("quota");});reads.clear();writes.clear();successValue(execute(PreparedTaskFileWrite(writeGrant,"quota",raw(old))));
  });
  for(bool cancel:{false,true})scenario(cancel?"one_CPU_task_cancel_waits_physical_write":"one_CPU_task_progresses_during_physical_write",[&]{
    FileScope scope(writable);RequestScope request;auto state=std::make_shared<TaskState>();state->grant=captureFileWriteGrant(false);state->bytes=next;
    write(root/"task",old);state->gate=std::make_shared<Gate>([&]{return temporaryExists(root);});Release release{state->gate};factoryState=state;TaskGroup group(1);
    auto progress=state->progress.get_future();auto writer=group.spawn(writeFactory),sibling=group.spawn(progressFactory);
    require(state->gate->began.wait_for(5s)==std::future_status::ready,"task write never reached worker");require(progress.wait_for(5s)==std::future_status::ready,"write blocked the only CPU worker");
    if(cancel)request.cancel();require(!state->gate->destroyed&&group.externalStats().tickets==1,"task returned physical credits while write blocked");release.now();
    if(cancel){bool stopped=false;try{(void)group.join(writer);}catch(const Trap &error){stopped=error.code=="E_CANCELLED";}require(stopped&&!state->admitted,"cancelled task resumed source");try{group.finish();}catch(const Trap &error){require(error.code=="E_CANCELLED","wrong task drain failure");}require(read(root/"task")==old,"cancelled task changed destination");}
    else{require(group.join(writer).scalar==42&&state->admitted,"task write result changed");(void)group.join(sibling);group.finish();require(read(root/"task")==next,"task write was not committed");}
    require(state->gate->destroyed&&group.externalStats().tickets==0&&group.externalStats().reservedBytes==0,"task completion escaped physical cleanup");factoryState.reset();noTemporary(root);
  });
  scenario("captured_root_descriptor_survives_path_replacement",[&]{
    FileScope scope(writable);auto grant=captureFileWriteGrant(false);fs::rename(root,directory.path/"pinned");fs::create_directory(root);
    successValue(execute(PreparedTaskFileWrite(grant,"pinned",raw(old))));require(read(directory.path/"pinned/pinned")==old&&!fs::exists(root/"pinned"),"path replacement redirected root descriptor");
  });
  require(liveObjects.load()==initialObjects,"host write tests leaked source values");
}
}
int main(){try{tests();std::cout<<"{\"ok\":true,\"host_write_cases\":"<<cases<<",\"public_source_writes\":false}\n";return 0;}catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 1;}}
