#include "host_test.h"
#include "nex_task_file_stream.h"
#include "nex_host.h"
#include "nex_tasks.h"
#include <atomic>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <future>
#include <iostream>
#ifndef _WIN32
#include <spawn.h>
#endif
#ifndef _WIN32
#include <sys/resource.h>
#endif
#include <sys/stat.h>
#ifndef _WIN32
#include <sys/wait.h>
#endif
#include <thread>
#include <unistd.h>

#ifndef _WIN32
extern char **environ;
#endif
namespace fs=std::filesystem;
using namespace nexrt;
using namespace std::chrono_literals;
namespace {
size_t cases=0;fs::path self;
void require(bool value,const char *message){if(!value)throw std::runtime_error(message);}
template<class F>void rejects(const std::string &code,F function){
  try{function();}catch(const DataError &error){if(error.code==code)return;throw std::runtime_error("expected "+code+", got "+error.code);}
  throw std::runtime_error("expected "+code);
}
template<class F>void scenario(const char *name,F function){function();++cases;std::cout<<"PASS "<<name<<'\n';}
struct Directory {
  fs::path path;
  Directory(){auto pattern=(fs::temp_directory_path()/"nex-stream-host-XXXXXX").string();auto value=::mkdtemp(pattern.data());require(value,"mkdtemp failed");path=value;}
  ~Directory(){std::error_code ignored;fs::remove_all(path,ignored);}
};
void write(const fs::path &p,const std::string &value){std::ofstream f(p,std::ios::binary);f.write(value.data(),value.size());require(bool(f),"fixture write failed");}
std::string read(const fs::path &p){std::ifstream f(p,std::ios::binary);require(bool(f),"fixture read failed");return {std::istreambuf_iterator<char>(f),{}};}
std::span<const uint8_t> raw(const std::string &s){return {reinterpret_cast<const uint8_t*>(s.data()),s.size()};}
std::string content(const Value &v){auto view=byteBuffer(unwrap(v).object).view();return {view.begin(),view.end()};}
void failure(const Value &v,const std::string &code){require(v.object&&v.object->kind==Data::Failure&&v.object->text==code,"wrong typed stream error");}
void ready(TaskExternalPool &pool,const TaskExternalTicket &ticket){
  const auto end=std::chrono::steady_clock::now()+5s;
  while(!pool.ready(ticket)&&std::chrono::steady_clock::now()<end)std::this_thread::yield();
  require(pool.ready(ticket),"physical file operation did not retire");
}
struct NoAmbient final:TaskExternalOperation {
  std::shared_ptr<TaskExternalOperation> operation;
  explicit NoAmbient(std::shared_ptr<TaskExternalOperation> operation):operation(std::move(operation)){}
  TaskExternalResult run(const TaskExternalControl &control)override{FileScope denied(false);return operation->run(control);}
};
TaskExternalResult executeRaw(const std::shared_ptr<TaskExternalOperation> &operation,size_t reservation){
  TaskExternalPool pool;auto ticket=pool.submit(1,std::make_shared<NoAmbient>(operation),reservation);ready(pool,ticket);auto result=pool.take(ticket);
  require(pool.stats().tickets==0&&pool.stats().reservedBytes==0,"transport credits leaked");return result;
}
Value execute(const PreparedTaskFileStream &prepared){return prepared.admit(executeRaw(prepared.operation(),prepared.reservation()));}
FileResource execute(const PreparedTaskFileOpen &prepared){return prepared.admit(executeRaw(prepared.operation(),prepared.reservation()));}
struct Gate {
  std::promise<void> entered,release;
  std::future<void> began=entered.get_future();
  std::shared_future<void> released=release.get_future().share();
  std::atomic<bool> destroyed{false};
};
struct Release {
  std::shared_ptr<Gate> gate;bool done=false;
  void now(){if(!done){gate->release.set_value();done=true;}}
  ~Release(){now();}
};
struct Gated final:TaskExternalOperation {
  std::shared_ptr<TaskExternalOperation> operation;std::shared_ptr<Gate> gate;bool after;
  Gated(std::shared_ptr<TaskExternalOperation> operation,std::shared_ptr<Gate> gate,bool after=false)
    :operation(std::move(operation)),gate(std::move(gate)),after(after){}
  ~Gated(){gate->destroyed=true;}
  void pause(){gate->entered.set_value();gate->released.wait();}
  TaskExternalResult run(const TaskExternalControl &control)override{
    FileScope denied(false);if(!after)pause();auto result=operation->run(control);if(after)pause();return result;
  }
};
struct TaskState {FileResource file;std::shared_ptr<Gate> gate;std::promise<void> progress;std::atomic<bool> admitted{false};};
std::shared_ptr<TaskState> factoryState;
TaskBody streamTask(TaskGroup &group,std::shared_ptr<TaskState> state){
  co_await group.yield();auto prepared=PreparedTaskFileStream::read(state->file,4);
  auto ticket=group.submitExternal(std::make_shared<Gated>(prepared.operation(),state->gate),prepared.reservation());
  auto result=co_await group.awaitExternal(ticket);require(content(prepared.admit(std::move(result)))=="abcd","task read changed bytes");state->admitted=true;
  co_return Value(int64_t(42));
}
TaskBody progressTask(TaskGroup &,std::shared_ptr<TaskState> state){state->progress.set_value();co_return Value(int64_t(0));}
TaskBody makeStreamTask(TaskGroup &group,Value,Value){return streamTask(group,factoryState);}
TaskBody makeProgressTask(TaskGroup &group,Value,Value){return progressTask(group,factoryState);}

#ifndef _WIN32
void partialChild(const fs::path &root){
  rlimit limit{1024,1024};require(::setrlimit(RLIMIT_FSIZE,&limit)==0,"cannot set child-only file limit");
  TextFiles capability(root.string(),true);FileScope scope(capability);auto file=fileOpen("partial",FileMode::WriteTruncate,false);
  std::string input(2048,'p');auto value=execute(PreparedTaskFileStream::write(file,raw(input)));
  require(unwrap(value).scalar==1024&&fs::file_size(root/"partial")==1024,"stream write fabricated a complete count");
}
#endif
void tests(){
  Directory directory;auto root=directory.path/"root";fs::create_directory(root);write(root/"input","abcdef");
  TextFiles capability(root.string(),true);const auto initial=liveObjects.load();
  scenario("open_on_worker_uses_captured_root_without_TLS",[&]{
    FileScope scope(capability);PreparedTaskFileOpen prepared(captureFileReadGrant(false).openRead("input"));
    require(prepared.reservation()==5,"open path reservation is wrong");auto file=execute(prepared);require(file.isOpen(),"open did not deliver a genuine file");
    require(content(execute(PreparedTaskFileStream::read(file,3)))=="abc","read ignored captured file");
    require(file.close()&&!file.close(),"aliases did not share close");
  });
  scenario("streamed_file_exceeds_whole_file_limit",[&]{
    std::string input(TextFiles::byteLimit*2+17,'x');input[TextFiles::byteLimit-1]='\0';input[TextFiles::byteLimit]='\xff';write(root/"large",input);
    FileScope scope(capability);PreparedTaskFileOpen open(captureFileReadGrant(false).openRead("large"));auto file=execute(open);std::string result;
    for(;;){auto part=content(execute(PreparedTaskFileStream::read(file,TextFiles::byteLimit)));if(part.empty())break;result+=part;}
    require(result==input&&unwrap(execute(PreparedTaskFileStream::size(file))).scalar==int64_t(input.size()),"streaming imposed the whole-file bound or changed bytes");
  });
  scenario("shared_cursor_aliases_and_absolute_seek",[&]{
    FileScope scope(capability);auto file=fileOpen("input",FileMode::Read,false),alias=file;
    require(content(execute(PreparedTaskFileStream::read(file,2)))=="ab","first cursor read failed");
    require(content(execute(PreparedTaskFileStream::read(alias,2)))=="cd","alias did not share cursor");
    require(unwrap(execute(PreparedTaskFileStream::seek(file,1))).scalar==1,"seek changed position");
    require(content(execute(PreparedTaskFileStream::read(alias,100)))=="bcdef","seek/read disagreement");
    require(content(execute(PreparedTaskFileStream::read(file,1))).empty(),"EOF changed");
    require(content(execute(PreparedTaskFileStream::read(file,0))).empty(),"zero-byte read changed");
  });
  scenario("concurrent_reads_share_one_serialized_cursor",[&]{
    FileScope scope(capability);auto file=fileOpen("input",FileMode::Read,false);auto a=PreparedTaskFileStream::read(file,3),b=PreparedTaskFileStream::read(file,3);
    TaskExternalPool pool;auto first=pool.submit(1,a.operation(),a.reservation()),second=pool.submit(2,b.operation(),b.reservation());ready(pool,first);ready(pool,second);
    auto x=content(a.admit(pool.take(first))),y=content(b.admit(pool.take(second)));
    require((x=="abc"&&y=="def")||(x=="def"&&y=="abc"),"concurrent cursor duplicated or skipped bytes");
  });
  scenario("write_snapshots_visible_input_and_flushes",[&]{
    FileScope scope(capability);auto file=fileOpen("snapshot",FileMode::WriteTruncate,false);std::string backing(TextFiles::byteLimit+19,'x');backing.replace(117,3,std::string("A\0\xff",3));
    auto prepared=PreparedTaskFileStream::write(file,raw(backing).subspan(117,3));require(prepared.reservation()==11,"tiny view retained or charged a large backing allocation");
    backing.assign(backing.size(),'z');require(unwrap(execute(prepared)).scalar==3,"write count changed");
    auto flushed=unwrap(execute(PreparedTaskFileStream::flush(file)));require(flushed.tag==Value::Boolean&&flushed.scalar==1,"flush did not return true");
    require(read(root/"snapshot")==std::string("A\0\xff",3),"write read mutable caller backing");
  });
  scenario("append_uses_kernel_end_even_after_seek",[&]{
    write(root/"append","old");FileScope scope(capability);PreparedTaskFileOpen open(captureFileWriteGrant(false).openWrite("append",FileMode::Append));auto file=execute(open);
    require(unwrap(execute(PreparedTaskFileStream::seek(file,0))).scalar==0,"append seek failed");
    require(unwrap(execute(PreparedTaskFileStream::write(file,raw("new")))).scalar==3&&read(root/"append")=="oldnew","append overwrote the file");
  });
#ifndef _WIN32
  scenario("actual_partial_write_count_in_separate_child",[&]{
    auto executable=self.string(),path=root.string();char *args[]={executable.data(),const_cast<char*>("--partial-root"),path.data(),nullptr};pid_t child=0;
    require(::posix_spawn(&child,executable.c_str(),nullptr,nullptr,args,environ)==0,"cannot spawn partial-write child");int status=0;
    while(::waitpid(child,&status,0)<0)require(errno==EINTR,"cannot wait for partial-write child");
    require(WIFEXITED(status)&&WEXITSTATUS(status)==0,"partial-write child failed");
  });
#endif
  scenario("modes_ranges_and_existing_error_priority",[&]{
    FileScope scope(capability);auto input=fileOpen("input",FileMode::Read,false),output=fileOpen("mode",FileMode::WriteTruncate,false);std::string oversized(TextFiles::byteLimit+1,'x');
    rejects("CAPABILITY",[&]{(void)PreparedTaskFileStream::write(input,raw(oversized));});
    rejects("CAPABILITY",[&]{(void)PreparedTaskFileStream::read(output,-1);});
    rejects("CAPABILITY",[&]{(void)PreparedTaskFileStream::flush(input);});
    rejects("E_RANGE",[&]{(void)PreparedTaskFileStream::read(input,-1);});
    rejects("LIMIT",[&]{(void)PreparedTaskFileStream::read(input,TextFiles::byteLimit+1);});
    rejects("LIMIT",[&]{(void)PreparedTaskFileStream::write(output,raw(oversized));});
    rejects("E_RANGE",[&]{(void)PreparedTaskFileStream::seek(input,-1);});
    require(unwrap(execute(PreparedTaskFileStream::write(output,{}))).scalar==0,"empty write failed");
  });
  scenario("read_only_grant_cannot_open_a_writer",[&]{
    TextFiles readonly(root.string(),false);FileScope scope(readonly);auto readGrant=captureFileReadGrant(false);auto writeGrant=captureFileWriteGrant(false);
    rejects("CAPABILITY",[&]{(void)writeGrant.openWrite("denied");});require(!fs::exists(root/"denied"),"read-only capture created a file");
    PreparedTaskFileOpen prepared(readGrant.openRead("input"));auto file=execute(prepared);require(file.isOpen(),"read-only grant lost reads");
  });
  scenario("invalid_paths_and_nonregular_files_do_not_open",[&]{
    fs::create_directory(root/"directory");fs::create_symlink("input",root/"symlink");nex_test::NonRegular nonregular(root/"fifo");FileScope scope(capability);auto grant=captureFileReadGrant(false);
    for(const auto &path:{"../escape","/absolute","a/../input"})rejects("VALIDATION",[&]{(void)grant.openRead(path);});
    rejects("E_UTF8",[&]{(void)grant.openRead(std::string("\xff",1));});
    for(const auto &path:{"directory","symlink","fifo"}){PreparedTaskFileOpen prepared(grant.openRead(path));rejects("VALIDATION",[&]{(void)execute(prepared);});}
    PreparedTaskFileOpen missing(grant.openRead("absent"));rejects("NOT_FOUND",[&]{(void)execute(missing);});
    rejects("VALIDATION",[&]{(void)captureFileWriteGrant(false).openWrite("bad-mode",FileMode::Read);});
  });
  scenario("preparation_does_not_create_or_truncate",[&]{
    write(root/"unchanged","old");FileScope scope(capability);auto grant=captureFileWriteGrant(false);
    {PreparedTaskFileOpen a(grant.openWrite("unchanged")),b(grant.openWrite("not-created"));require(read(root/"unchanged")=="old"&&!fs::exists(root/"not-created"),"preparation performed IO");}
    require(read(root/"unchanged")=="old"&&!fs::exists(root/"not-created"),"discard performed IO");
  });
  scenario("prepared_open_is_one_shot_and_has_no_raw_file_id",[&]{
    FileScope scope(capability);PreparedTaskFileOpen prepared(captureFileReadGrant(false).openRead("input"));rejects("E_TASK_STATE",[&]{(void)prepared.admit({});});
    auto result=executeRaw(prepared.operation(),prepared.reservation());require(result.bytes.empty(),"file authority escaped in copied bytes");auto file=prepared.admit(std::move(result));
    rejects("E_TASK_STATE",[&]{(void)prepared.admit({});});rejects("E_TASK_STATE",[&]{(void)executeRaw(prepared.operation(),prepared.reservation());});
    auto moved=std::move(prepared);rejects("E_TASK_STATE",[&]{(void)prepared.operation();});
    moved.discard();require(file.isOpen(),"discard revoked an admitted owner");
    auto deleting=std::make_unique<PreparedTaskFileOpen>(captureFileReadGrant(false).openRead("input"));auto raw=executeRaw(deleting->operation(),deleting->reservation());
    std::function<void()> poll;poll=[&]{deleting.reset();poll={};};auto delivered=deleting->admit(std::move(raw),poll);
    require(delivered.isOpen(),"coordinator cleanup invalidated its admitted file");
  });
  scenario("unpublished_open_retains_real_quota_until_discard",[&]{
    FileScope scope(capability);std::vector<FileResource> held;for(unsigned i=0;i<63;++i)held.push_back(fileOpen("input",FileMode::Read,false));
    PreparedTaskFileOpen prepared(captureFileReadGrant(false).openRead("input"));auto result=executeRaw(prepared.operation(),prepared.reservation());
    rejects("E_RESOURCE_LIMIT",[&]{(void)fileOpen("input",FileMode::Read,false);});prepared.discard();auto file=fileOpen("input",FileMode::Read,false);require(file.isOpen(),"discard leaked physical open quota");
    rejects("E_TASK_STATE",[&]{(void)prepared.admit(std::move(result));});
  });
  scenario("closed_file_pins_quota_until_actual_worker_retirement",[&]{
    auto domain=capability.resourceScope(1);auto file=capability.openIn(domain,"input",FileMode::Read);auto prepared=std::make_unique<PreparedTaskFileStream>(PreparedTaskFileStream::read(file,4));
    TaskExternalPool pool;auto gate=std::make_shared<Gate>();Release release{gate};auto ticket=pool.submit(1,std::make_shared<Gated>(prepared->operation(),gate),prepared->reservation());
    require(gate->began.wait_for(5s)==std::future_status::ready,"stream did not enter worker");require(file.close()&&domain.used()==1,"logical close released an active descriptor");prepared.reset();
    rejects("E_RESOURCE_LIMIT",[&]{(void)capability.openIn(domain,"input",FileMode::Read);});require(!pool.ready(ticket),"blocked worker was reported retired");release.now();ready(pool,ticket);
    require(pool.take(ticket).errorCode=="E_RESOURCE_CLOSED"&&domain.used()==0&&gate->destroyed,"file quota returned before operation destruction");
  });
  scenario("close_after_IO_suppresses_data_with_typed_closed_result",[&]{
    FileScope scope(capability);auto file=fileOpen("input",FileMode::Read,false);auto prepared=PreparedTaskFileStream::read(file,6);auto result=executeRaw(prepared.operation(),prepared.reservation());
    file.close();failure(prepared.admit(std::move(result)),"E_RESOURCE_CLOSED");
  });
  scenario("request_scope_revocation_prevents_open_admission",[&]{
    auto scope=std::make_unique<FileScope>(capability);PreparedTaskFileOpen prepared(captureFileReadGrant(false).openRead("input"));auto result=executeRaw(prepared.operation(),prepared.reservation());scope.reset();
    rejects("E_RESOURCE_SCOPE",[&]{(void)prepared.admit(std::move(result));});
  });
  for(bool after:{false,true})scenario(after?"postopen_cancel_discards_owner_without_rollback":"preopen_cancel_preserves_old_file",[&]{
    write(root/"cancel-open","old");FileScope scope(capability);auto prepared=std::make_unique<PreparedTaskFileOpen>(captureFileWriteGrant(false).openWrite("cancel-open"));TaskExternalPool pool;auto gate=std::make_shared<Gate>();Release release{gate};
    auto reservation=prepared->reservation();auto ticket=pool.submit(1,std::make_shared<Gated>(prepared->operation(),gate,after),reservation);
    require(gate->began.wait_for(5s)==std::future_status::ready,"open gate did not begin");pool.cancel(ticket);prepared.reset();
    require(!pool.ready(ticket)&&pool.stats().reservedBytes==reservation,"cancel skipped physical drain");release.now();ready(pool,ticket);rejects("E_CANCELLED",[&]{(void)pool.take(ticket);});
    require(read(root/"cancel-open")== (after?"":"old"),"open cancellation fabricated rollback or mutated before admission");
  });
  scenario("postwrite_cancel_keeps_bytes_and_withholds_result",[&]{
    FileScope scope(capability);auto file=fileOpen("cancel-write",FileMode::WriteTruncate,false);auto prepared=PreparedTaskFileStream::write(file,raw("committed"));TaskExternalPool pool;auto gate=std::make_shared<Gate>();Release release{gate};
    auto ticket=pool.submit(1,std::make_shared<Gated>(prepared.operation(),gate,true),prepared.reservation());require(gate->began.wait_for(5s)==std::future_status::ready,"write gate did not begin");
    pool.cancel(ticket);require(!pool.ready(ticket)&&read(root/"cancel-write")=="committed","write effects were hidden or drain skipped");release.now();ready(pool,ticket);rejects("E_CANCELLED",[&]{(void)pool.take(ticket);});
  });
  scenario("stream_reply_bounds_and_scalar_contracts_are_checked",[&]{
    FileScope scope(capability);auto output=fileOpen("protocol",FileMode::WriteTruncate,false);
    {std::string bytes(261,'x');auto p=PreparedTaskFileStream::write(output,raw(bytes));auto r=executeRaw(p.operation(),p.reservation());
      require(r.bytes==std::vector<uint8_t>({5,1,0,0,0,0,0,0}),"scalar reply is not canonical little endian");require(unwrap(p.admit(std::move(r))).scalar==261,"scalar count did not decode");}
    {auto p=PreparedTaskFileStream::write(output,raw("x"));auto r=executeRaw(p.operation(),p.reservation());r.bytes={2,0,0,0,0,0,0,0};rejects("E_TASK_VALUE",[&]{(void)p.admit(std::move(r));});}
    {auto p=PreparedTaskFileStream::size(output);auto r=executeRaw(p.operation(),p.reservation());r.bytes.resize(7);rejects("E_TASK_VALUE",[&]{(void)p.admit(std::move(r));});}
    {auto p=PreparedTaskFileStream::seek(output,0);auto r=executeRaw(p.operation(),p.reservation());r.bytes={1,0,0,0,0,0,0,0};rejects("E_TASK_VALUE",[&]{(void)p.admit(std::move(r));});}
    {auto p=PreparedTaskFileStream::size(output);auto r=executeRaw(p.operation(),p.reservation());r.bytes[7]=128;rejects("E_TASK_VALUE",[&]{(void)p.admit(std::move(r));});}
    {auto p=PreparedTaskFileStream::flush(output);auto r=executeRaw(p.operation(),p.reservation());r.bytes.push_back(1);output.close();rejects("E_LIMIT",[&]{(void)p.admit(std::move(r));});}
  });
  scenario("stream_one_shot_and_unknown_error_rejection",[&]{
    FileScope scope(capability);auto file=fileOpen("input",FileMode::Read,false);auto p=PreparedTaskFileStream::read(file,1);rejects("E_TASK_STATE",[&]{(void)p.admit({});});
    auto r=executeRaw(p.operation(),p.reservation());require(content(p.admit(std::move(r)))=="a","single read failed");rejects("E_TASK_STATE",[&]{(void)p.admit({});});
    auto q=PreparedTaskFileStream::read(file,1);r=executeRaw(q.operation(),q.reservation());r.bytes.clear();r.errorCode="UNKNOWN";rejects("E_TASK_VALUE",[&]{(void)q.admit(std::move(r));});
    auto deleting=std::make_unique<PreparedTaskFileStream>(PreparedTaskFileStream::read(file,1));r=executeRaw(deleting->operation(),deleting->reservation());
    std::function<void()> poll;poll=[&]{deleting.reset();poll={};};require(content(deleting->admit(std::move(r),poll))=="c","coordinator cleanup invalidated its stream result");
  });
  scenario("open_wakeup_cannot_fabricate_file_authority",[&]{
    FileScope scope(capability);PreparedTaskFileOpen p(captureFileReadGrant(false).openRead("absent"));auto r=executeRaw(p.operation(),p.reservation());r.errorCode.clear();r.errorMessage.clear();
    rejects("E_TASK_VALUE",[&]{(void)p.admit(std::move(r));});
    PreparedTaskFileOpen q(captureFileReadGrant(false).openRead("input"));r=executeRaw(q.operation(),q.reservation());r.bytes.push_back(1);rejects("E_LIMIT",[&]{(void)q.admit(std::move(r));});
  });
  scenario("transport_backpressure_retains_exact_payload_credits",[&]{
    FileScope scope(capability);auto file=fileOpen("input",FileMode::Read,false);auto p=PreparedTaskFileStream::read(file,4);TaskExternalPool pool({1,1,4,4});auto gate=std::make_shared<Gate>();Release release{gate};
    auto ticket=pool.submit(1,std::make_shared<Gated>(p.operation(),gate),p.reservation());require(gate->began.wait_for(5s)==std::future_status::ready,"credit gate did not begin");
    rejects("E_LIMIT",[&]{(void)pool.submit(2,p.operation(),p.reservation());});require(pool.stats().tickets==1&&pool.stats().reservedBytes==4,"backpressure lost reserved bytes");release.now();ready(pool,ticket);
    require(content(p.admit(pool.take(ticket)))=="abcd"&&pool.stats().tickets==0&&pool.stats().reservedBytes==0,"credits did not settle");
  });
  scenario("captured_root_survives_pathname_replacement",[&]{
    auto original=directory.path/"pin-root",retained=directory.path/"retained-root";fs::create_directory(original);write(original/"input","original");TextFiles pinned(original.string(),true);FileScope scope(pinned);
    auto grant=captureFileReadGrant(false);auto opening=grant.openRead("input");fs::rename(original,retained);fs::create_directory(original);write(original/"input","replacement");PreparedTaskFileOpen prepared(std::move(opening));auto file=execute(prepared);
    require(content(execute(PreparedTaskFileStream::read(file,100)))=="original","worker rediscovered the root pathname");
  });
  scenario("post_IO_deadlines_retain_fatal_priority_and_retire_unpublished_files",[&]{
    FileScope scope(capability);
    {
      auto file=fileOpen("deadline-write",FileMode::WriteTruncate,false);auto p=PreparedTaskFileStream::write(file,raw("written"));TaskExternalPool pool;
      auto ticket=pool.submit(1,p.operation(),p.reservation(),TaskExternalControl([&]{if(fs::file_size(root/"deadline-write"))throw DataError("E_TIMEOUT","controlled post-write deadline");}));
      ready(pool,ticket);pool.cancel(ticket);rejects("E_TIMEOUT",[&]{(void)pool.take(ticket);});require(read(root/"deadline-write")=="written","deadline fabricated write rollback");file.close();
    }
    write(root/"deadline-open","old");PreparedTaskFileOpen p(captureFileWriteGrant(false).openWrite("deadline-open"));TaskExternalPool pool;
    auto ticket=pool.submit(1,p.operation(),p.reservation(),TaskExternalControl([&]{if(!fs::file_size(root/"deadline-open"))throw DataError("E_TIMEOUT","controlled post-open deadline");}));
    ready(pool,ticket);pool.cancel(ticket);rejects("E_TIMEOUT",[&]{(void)pool.take(ticket);});require(read(root/"deadline-open").empty(),"deadline fabricated truncate rollback");
    std::vector<FileResource> held;for(unsigned i=0;i<64;++i)held.push_back(fileOpen("input",FileMode::Read,false));
    rejects("E_RESOURCE_LIMIT",[&]{(void)fileOpen("input",FileMode::Read,false);});
  });
  for(bool cancel:{false,true})scenario(cancel?"one_CPU_task_cancel_waits_stream_retirement":"one_CPU_task_progresses_during_stream_IO",[&]{
    FileScope scope(capability);RequestScope request;auto domain=capability.resourceScope(1);auto state=std::make_shared<TaskState>();state->file=capability.openIn(domain,"input",FileMode::Read);state->gate=std::make_shared<Gate>();factoryState=state;
    TaskGroup group(1);Release release{state->gate};auto progress=state->progress.get_future();auto reader=group.spawn(makeStreamTask),sibling=group.spawn(makeProgressTask);
    require(state->gate->began.wait_for(5s)==std::future_status::ready&&progress.wait_for(5s)==std::future_status::ready,"stream IO blocked the only CPU worker");
    if(cancel){state->file.close();request.cancel();}require(!state->gate->destroyed&&group.externalStats().tickets==1,"task completed before physical IO");release.now();
    if(cancel){bool stopped=false;try{(void)group.join(reader);}catch(const Trap &error){stopped=error.code=="E_CANCELLED";}require(stopped&&!state->admitted,"cancelled source resumed");try{group.finish();}catch(const Trap &error){require(error.code=="E_CANCELLED","wrong task drain error");}}
    else{require(group.join(reader).scalar==42&&state->admitted,"stream task result failed");(void)group.join(sibling);group.finish();state->file.close();}
    require(group.externalStats().tickets==0&&group.externalStats().reservedBytes==0&&domain.used()==0,"task stream leaked a ticket, lease or file quota");factoryState.reset();
  });
  require(liveObjects.load()==initial,"stream test leaked source values");
}
}
int main(int argc,char **argv){
  try{self=fs::absolute(argv[0]);
#ifndef _WIN32
if(argc==3&&std::string(argv[1])=="--partial-root"){partialChild(argv[2]);return 0;}
#else
(void)argc;
#endif
tests();std::cout<<"{\"ok\":true,\"host_stream_cases\":"<<cases<<",\"public_source_support\":false,\"maximum_chunk_bytes\":1048576,\"one_shot_typed_open\":true,\"physical_drain\":true}\n";return 0;}
  catch(const std::exception &error){std::cerr<<error.what()<<'\n';std::cout<<"{\"ok\":false,\"host_stream_cases\":"<<cases<<"}\n";return 1;}
}
