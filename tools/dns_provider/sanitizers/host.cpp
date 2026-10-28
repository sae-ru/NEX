#include "nex_task_foreign.h"
#include "nex_host.h"
#include "third_party/json.hpp"
#include <openssl/evp.h>
#include <array>
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <thread>
#include <fcntl.h>
#include <unistd.h>
using namespace nexrt;using J=nlohmann::ordered_json;namespace fs=std::filesystem;
namespace {
void require(bool value,const std::string &why){if(!value)throw DataError("E_TEST",why);}
std::string read(const fs::path &path){std::ifstream file(path,std::ios::binary);require(bool(file),"missing input");return {std::istreambuf_iterator<char>(file),{}};}
void write(const fs::path &path){std::ofstream file(path);file<<"release";require(bool(file),"gate write failed");}
std::string digest(std::string_view text){std::array<unsigned char,32> bytes{};unsigned count=0;auto *ctx=EVP_MD_CTX_new();require(ctx,"digest allocation");bool ok=EVP_DigestInit_ex2(ctx,EVP_sha256(),nullptr)==1&&EVP_DigestUpdate(ctx,text.data(),text.size())==1&&EVP_DigestFinal_ex(ctx,bytes.data(),&count)==1&&count==32;EVP_MD_CTX_free(ctx);require(ok,"digest failed");std::string result;for(auto b:bytes){result+="0123456789abcdef"[b>>4];result+="0123456789abcdef"[b&15];}return result;}
int descriptors(){int count=0;for(int fd=0;fd<1024;++fd)if(::fcntl(fd,F_GETFD)>=0)++count;return count;}
template<class P>void waitFor(P ready){auto end=std::chrono::steady_clock::now()+std::chrono::seconds(12);while(!ready()){require(std::chrono::steady_clock::now()<end,"test observation timeout");std::this_thread::sleep_for(std::chrono::milliseconds(1));}}
template<class F>void error(const char *code,F action,const char *message=nullptr){try{action();}catch(const DataError &e){require(e.code==code,std::string("expected ")+code+", got "+e.code);if(message)require(e.what()==std::string(message),"original host error message changed");return;}throw DataError("E_TEST",std::string("expected failure ")+code);}
void expectAddresses(const Value &value){require(isSuccess(value),"ordinary DNS error instead of success");auto result=unwrap(value);require(result.object&&result.object->values.size()==2,"address count");std::array<std::string,2> expected{"127.0.0.42","2001:db8::42"};for(size_t i=0;i<2;++i)require(result.object->values[i].object&&result.object->values[i].object->text==expected[i],"canonical address result differs");}
void ordinary(const Value &value,const char *code){require(!isSuccess(value)&&value.object&&value.object->text==code,std::string("ordinary failure differs: ")+code);}
struct Calls {
 CapturedForeignScope scope;std::string lookup,statistics;TaskExternalPool pool;uint64_t id=0;fs::path gates;std::string run;
 Calls(CapturedForeignScope scope,std::string lookup,std::string statistics,fs::path gates,std::string run):scope(std::move(scope)),lookup(std::move(lookup)),statistics(std::move(statistics)),gates(std::move(gates)),run(std::move(run)){for(auto &c:this->run)if(c>='A'&&c<='Z')c=char(c-'A'+'a');}
 PreparedTaskForeignCall prepare(const std::string &name,const std::string &authority="public",int64_t limit=64,int64_t timeout=3000){std::vector<Value> args{Value(string(authority)),Value(string(name)),Value(limit),Value(timeout)};PreparedTaskForeignCall prepared(scope,lookup,args);args.clear();return prepared;}
 TaskExternalTicket submit(const PreparedTaskForeignCall &call,TaskExternalControl control=TaskExternalControl{}){return pool.submit(++id,call.operation(),call.reservation,std::move(control));}
 Value take(const PreparedTaskForeignCall &call,const TaskExternalTicket &ticket){waitFor([&]{return pool.ready(ticket);});return call.admit(pool.take(ticket));}
 Value invoke(const std::string &name,const std::string &authority="public",int64_t limit=64,int64_t timeout=3000){auto call=prepare(name,authority,limit,timeout);auto ticket=submit(call);return take(call,ticket);}
 std::array<int64_t,4> stats(){auto fn=scope.bind(statistics);auto value=fn.invoke({});require(value.object&&value.object->values.size()==4,"statistics layout");std::array<int64_t,4> result{};for(size_t i=0;i<4;++i)result[i]=value.object->values[i].scalar;return result;}
 std::string label(const char *name){return std::string("held-")+name+"-"+run+".example.test";}
 void gate(const std::string &name){waitFor([&]{return fs::is_regular_file(gates/(digest(name)+".ready"));});}
 void release(const std::string &name){write(gates/(digest(name)+".release"));}
 void settled(){auto s=stats();require(s[0]==s[1]&&s[2]==0,"channel not physically retired before admission");auto k=pool.stats();require(k.tickets==0&&k.reservedBytes==0&&k.running==0&&k.queued==0,"IO reservation remains");}
};
}
int main(int argc,char **argv)try{
 require(argc==5,"expected project, gates, run identity, mode");fs::path project=argv[1];auto config=J::parse(read(project/"host-input.json"));auto libraries=loadForeignLibraries((project/"two-context-foreign.json").string());J checks=J::array();
 {
  RequestScope request(100000000,120000);ForeignScope lexical(libraries);Calls calls(captureForeignScope(),config.at("lookup").dump(),config.at("statistics").dump(),argv[2],argv[3]);calls.stats();
  auto run=[&](const char *name,auto action){auto fds=descriptors();auto objects=liveObjects.load();action();calls.settled();require(liveObjects.load()==objects,"managed value owner leaked");require(descriptors()==fds,"native descriptor leaked");checks.push_back(name);std::cerr<<"NEX_DNS_HOST_CHECK "<<name<<'\n';};
  const auto mode=std::string(argv[4]);
  if(mode=="capacity"){
   run("owned_capacity_cancel_and_reuse",[&]{auto name=calls.label("capacity");auto held=calls.prepare(name,"public",64,10000);auto ticket=calls.submit(held);calls.gate(name);ordinary(calls.invoke("service.example.test"),"E_DNS_BUSY");calls.pool.cancel(ticket);waitFor([&]{return calls.pool.ready(ticket);});error("E_CANCELLED",[&]{(void)calls.pool.take(ticket);});expectAddresses(calls.invoke("service.example.test"));auto s=calls.stats();require(s[0]==2&&s[1]==2&&s[3]==1,"capacity did not cover physical lifetime");});
  }else{
   run("canonical_A_AAAA_C_tokens_and_input_snapshot",[&]{std::string name="service.example.test";auto call=calls.prepare(name);name="outside.test";auto ticket=calls.submit(call);expectAddresses(calls.take(call,ticket));});
   run("duplicate_answers",[&]{expectAddresses(calls.invoke("duplicate.example.test"));});
   run("actual_TCP_fallback",[&]{expectAddresses(calls.invoke("tcp.example.test"));});
   run("forged_source_and_transaction",[&]{expectAddresses(calls.invoke("spoof.example.test"));});
   if(mode=="full"){
    run("ungranted_domain_before_channel",[&]{auto before=calls.stats()[0];ordinary(calls.invoke("service.example.test","unknown"),"CAPABILITY");ordinary(calls.invoke("evil-example.test"),"CAPABILITY");require(calls.stats()[0]==before,"denied hostname queried");});
    run("invalid_requests_before_channel",[&]{auto before=calls.stats()[0];ordinary(calls.invoke("bad..example.test"),"VALIDATION");ordinary(calls.invoke("service.example.test","public",0),"VALIDATION");ordinary(calls.invoke("service.example.test","public",64,0),"VALIDATION");require(calls.stats()[0]==before,"invalid request queried");});
    run("NXDOMAIN_and_bounded_answer_failure",[&]{ordinary(calls.invoke("missing.example.test"),"E_DNS");ordinary(calls.invoke("many.example.test","public",2),"E_DNS_LIMIT");});
    run("ordinary_timeout_then_success",[&]{ordinary(calls.invoke(calls.label("own-timeout"),"public",64,60),"E_DNS_TIMEOUT");expectAddresses(calls.invoke("service.example.test"));});
    run("IO_progress_and_coordinator_work",[&]{auto name=calls.label("progress");auto call=calls.prepare(name,"public",64,10000);auto ticket=calls.submit(call);calls.gate(name);uint64_t total=0;for(unsigned i=0;i<10000;++i)total+=i;require(total==49995000,"coordinator calculation");expectAddresses(calls.invoke("service.example.test"));calls.release(name);expectAddresses(calls.take(call,ticket));require(calls.stats()[3]>=2,"IO did not overlap");});
    run("inflight_pool_cancellation",[&]{auto name=calls.label("cancel");auto call=calls.prepare(name,"public",64,10000);auto ticket=calls.submit(call);calls.gate(name);calls.pool.cancel(ticket);waitFor([&]{return calls.pool.ready(ticket);});error("E_CANCELLED",[&]{(void)calls.pool.take(ticket);});});
    run("original_parent_deadline",[&]{auto name=calls.label("deadline");std::atomic<bool> expired=false;auto call=calls.prepare(name,"public",64,10000);auto ticket=calls.submit(call,TaskExternalControl([&]{if(expired.load())throw DataError("E_TIMEOUT","original-owner-deadline");}));calls.gate(name);expired=true;waitFor([&]{return calls.pool.ready(ticket);});error("E_TIMEOUT",[&]{(void)calls.pool.take(ticket);},"original-owner-deadline");});
    run("queued_cancel_opens_no_channel",[&]{TaskExternalPool one({1,64,8*1048576,1048576});auto name=calls.label("queued");auto call=calls.prepare(name,"public",64,10000);auto first=one.submit(1,call.operation(),call.reservation);calls.gate(name);auto before=calls.stats()[0];auto queued=calls.prepare("service.example.test");auto second=one.submit(2,queued.operation(),queued.reservation);one.cancel(second);one.cancel(first);waitFor([&]{return one.ready(first)&&one.ready(second);});error("E_CANCELLED",[&]{(void)one.take(first);});error("E_CANCELLED",[&]{(void)one.take(second);});require(calls.stats()[0]==before,"queued cancellation queried");});
    run("scope_revocation_and_late_admission",[&]{auto nested=std::make_unique<ForeignScope>(libraries);auto captured=captureForeignScope();auto name=calls.label("scope-revocation");std::vector<Value> args{Value(string("public")),Value(string(name)),Value(64),Value(10000)};PreparedTaskForeignCall held(captured,calls.lookup,args);auto ticket=calls.submit(held);calls.gate(name);std::vector<Value> doneArgs{Value(string("public")),Value(string("service.example.test")),Value(64),Value(3000)};PreparedTaskForeignCall late(captured,calls.lookup,doneArgs);auto done=calls.submit(late);waitFor([&]{return calls.pool.ready(done);});auto raw=calls.pool.take(done);nested.reset();waitFor([&]{return calls.pool.ready(ticket);});try{(void)calls.pool.take(ticket);throw DataError("E_TEST","revoked IO succeeded");}catch(const DataError &e){require(e.code=="E_RESOURCE_SCOPE"||e.code=="E_FFI_SCOPE","wrong revocation error");}error("E_FFI_SCOPE",[&]{(void)late.admit(std::move(raw));});});
    run("abandoned_pool_drains_physical_call",[&]{auto name=calls.label("abandoned");auto call=calls.prepare(name,"public",64,10000);{TaskExternalPool abandoned;auto ticket=abandoned.submit(1,call.operation(),call.reservation);calls.gate(name);}});
    {auto name=calls.label("module-revocation");auto call=calls.prepare(name,"public",64,10000);auto ticket=calls.submit(call);calls.gate(name);libraries->revoke();waitFor([&]{return calls.pool.ready(ticket);});error("E_RESOURCE_SCOPE",[&]{(void)calls.pool.take(ticket);});checks.push_back("module_grant_revocation_during_IO");}
   }
  }
 }
 libraries.reset();require(liveObjects.load()==0,"managed value survives host request");
 std::cout<<J{{"schema","nex.dns-typed-host-sanitizers/1"},{"ok",true},{"checks",checks},{"actual_C_API",true},{"actual_copied_task_FFI_bridge",true},{"actual_loaded_pinned_module",true},{"compiler_or_generated_NEX_IR_instrumented",false}}.dump()<<'\n';return 0;
}catch(const DataError &error){std::cerr<<error.code<<": "<<error.what()<<'\n';return 1;}catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 2;}
