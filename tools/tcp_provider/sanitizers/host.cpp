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
void require(bool b,const std::string &why){if(!b)throw DataError("E_TEST",why);}
std::string read(const fs::path &p){std::ifstream f(p,std::ios::binary);require(bool(f),"missing test input");return {std::istreambuf_iterator<char>(f),{}};}
std::string digest(std::string_view s){
 std::array<unsigned char,32> bytes{};unsigned n=0;auto *ctx=EVP_MD_CTX_new();require(ctx,"digest allocation");
 bool ok=EVP_DigestInit_ex2(ctx,EVP_sha256(),nullptr)==1&&EVP_DigestUpdate(ctx,s.data(),s.size())==1&&EVP_DigestFinal_ex(ctx,bytes.data(),&n)==1&&n==32;EVP_MD_CTX_free(ctx);require(ok,"digest failed");
 std::string result;for(auto b:bytes){result+="0123456789abcdef"[b>>4];result+="0123456789abcdef"[b&15];}return result;
}
int descriptors(){int n=0;for(int fd=0;fd<1024;++fd)if(::fcntl(fd,F_GETFD)>=0)++n;return n;}
template<class P>void waitFor(P ready){auto end=std::chrono::steady_clock::now()+std::chrono::seconds(12);while(!ready()){require(std::chrono::steady_clock::now()<end,"test observation timeout");std::this_thread::sleep_for(std::chrono::milliseconds(1));}}
template<class F>void error(const char *code,F action,const char *message=nullptr){try{action();}catch(const DataError &e){require(e.code==code,std::string("expected ")+code+", got "+e.code);if(message)require(e.what()==std::string(message),"original host error message changed");return;}throw DataError("E_TEST",std::string("expected failure ")+code);}
std::vector<uint8_t> bytesOf(std::string_view text){return {text.begin(),text.end()};}
void success(const Value &value,const std::vector<uint8_t> &expected){require(isSuccess(value),"ordinary TCP error instead of success");auto result=unwrap(value);require(byteBuffer(result.object).toVector()==expected,"copied binary TCP result differs");}
void ordinary(const Value &v,const char *code){require(!isSuccess(v)&&v.object&&v.object->text==code,std::string("ordinary failure differs: ")+code);}
struct Calls {
 CapturedForeignScope scope;std::string exchange,statistics;TaskExternalPool pool;uint64_t id=0;fs::path gates;std::string run;
 Calls(CapturedForeignScope scope,std::string exchange,std::string statistics,fs::path gates,std::string run)
  :scope(std::move(scope)),exchange(std::move(exchange)),statistics(std::move(statistics)),gates(std::move(gates)),run(std::move(run)){}
 PreparedTaskForeignCall prepare(const std::string &endpoint,std::span<const uint8_t> body,size_t reply=64,unsigned timeout=3000){
  std::vector<Value> arguments{Value(string(endpoint)),Value(bytes(ByteBuffer::copy(body))),Value(int64_t(reply)),Value(int64_t(timeout))};
  PreparedTaskForeignCall prepared(scope,exchange,arguments);arguments.clear();return prepared;
 }
 TaskExternalTicket submit(const PreparedTaskForeignCall &call,TaskExternalControl control=TaskExternalControl{}){return pool.submit(++id,call.operation(),call.reservation,std::move(control));}
 Value take(const PreparedTaskForeignCall &call,const TaskExternalTicket &ticket){waitFor([&]{return pool.ready(ticket);});return call.admit(pool.take(ticket));}
 Value invoke(const std::string &endpoint,std::span<const uint8_t> input,size_t reply=64,unsigned timeout=3000){auto p=prepare(endpoint,input,reply,timeout);auto t=submit(p);return take(p,t);}
 std::array<int64_t,4> stats(){auto fn=scope.bind(statistics);auto result=fn.invoke({});require(result.object&&result.object->values.size()==4,"statistics layout");std::array<int64_t,4> s{};for(size_t i=0;i<4;++i)s[i]=result.object->values[i].scalar;return s;}
 std::string label(const char *caseName){return run+"-"+caseName;}
 void gate(const std::string &label){waitFor([&]{return fs::is_regular_file(gates/(digest(label)+".ready"));});}
 void settled(){auto s=stats();require(s[0]==s[1]&&s[2]==0,"socket not physically retired before admission");auto k=pool.stats();require(k.tickets==0&&k.reservedBytes==0&&k.running==0&&k.queued==0,"IO reservation remains");}
};
}
int main(int argc,char **argv)try{
 require(argc==5,"expected project, gate directory, run identity and capacity mode");fs::path project=argv[1];auto config=J::parse(read(project/"host-input.json"));auto libraries=loadForeignLibraries((project/"two-context-foreign.json").string());J checks=J::array();
 {
  RequestScope request(100000000,120000);ForeignScope lexical(libraries);auto scope=captureForeignScope();Calls calls(scope,config.at("exchange").dump(),config.at("statistics").dump(),argv[2],argv[3]);calls.stats();
  auto run=[&](const char *name,auto action){auto fds=descriptors();auto objects=liveObjects.load();action();calls.settled();require(liveObjects.load()==objects,"managed value owner leaked");require(descriptors()==fds,"native descriptor leaked");checks.push_back(name);std::cerr<<"NEX_TCP_HOST_CHECK "<<name<<'\n';};
  if(std::string(argv[4])=="capacity"){
   run("owned_capacity_cancel_and_reuse",[&]{
    auto label=calls.label("capacity");auto input=bytesOf(label);auto held=calls.prepare("held",input,64,10000);auto h=calls.submit(held);calls.gate(label);
    ordinary(calls.invoke("echo",bytesOf("must-not-connect")),"E_NETWORK_BUSY");calls.pool.cancel(h);waitFor([&]{return calls.pool.ready(h);});error("E_CANCELLED",[&]{(void)calls.pool.take(h);});success(calls.invoke("echo",bytesOf("after")),bytesOf("after"));auto s=calls.stats();require(s[0]==2&&s[1]==2&&s[3]==1,"provider capacity did not cover physical lifetime");
   });
  }else{
   run("binary_C_tokens_and_input_snapshot",[&]{std::vector<uint8_t> input{0,255,128,208,175,240,159,167,160};auto expected=input;auto p=calls.prepare("echo",input);std::fill(input.begin(),input.end(),7);auto t=calls.submit(p);success(calls.take(p,t),expected);});
   run("IPv6_UTF8_bytes",[&]{auto input=bytesOf("Я🧠");success(calls.invoke("ipv6",input),input);});
   run("copied_bytes_quota_exact_boundary",[&]{std::vector<uint8_t> input(522240);for(size_t i=0;i<input.size();++i)input[i]=uint8_t(i);success(calls.invoke("echo",input,input.size(),10000),input);});
   run("ungranted_endpoint_before_socket",[&]{auto before=calls.stats()[0];ordinary(calls.invoke("not-granted",bytesOf("x")),"CAPABILITY");require(calls.stats()[0]==before,"denied endpoint connected");});
   run("invalid_limits_before_socket",[&]{auto before=calls.stats()[0];ordinary(calls.invoke("echo",bytesOf("x"),0),"VALIDATION");ordinary(calls.invoke("echo",bytesOf("x"),64,0),"VALIDATION");require(calls.stats()[0]==before,"invalid request connected");});
   run("peer_overflow",[&]{ordinary(calls.invoke("overflow",bytesOf("abc"),3),"E_NETWORK_LIMIT");});
   run("actual_abortive_reset",[&]{ordinary(calls.invoke("reset",bytesOf("request")),"E_NETWORK");});
   run("ordinary_timeout_then_success",[&]{ordinary(calls.invoke("held",bytesOf(calls.label("own-timeout")),64,60),"E_NETWORK_TIMEOUT");success(calls.invoke("echo",bytesOf("after-timeout")),bytesOf("after-timeout"));});
   run("IO_progress_and_coordinator_work",[&]{auto label=calls.label("progress");auto input=bytesOf(label);auto p=calls.prepare("held",input,64,10000);auto t=calls.submit(p);calls.gate(label);uint64_t total=0;for(unsigned i=0;i<10000;++i)total+=i;require(total==49995000,"coordinator calculation");success(calls.invoke("release",input),bytesOf("released"));success(calls.take(p,t),input);require(calls.stats()[3]>=2,"IO did not overlap");});
   run("inflight_pool_cancellation",[&]{auto label=calls.label("cancel");auto p=calls.prepare("held",bytesOf(label),64,10000);auto t=calls.submit(p);calls.gate(label);calls.pool.cancel(t);waitFor([&]{return calls.pool.ready(t);});error("E_CANCELLED",[&]{(void)calls.pool.take(t);});});
   run("original_parent_deadline",[&]{auto label=calls.label("deadline");std::atomic<bool> expired=false;auto p=calls.prepare("held",bytesOf(label),64,10000);auto t=calls.submit(p,TaskExternalControl([&]{if(expired.load())throw DataError("E_TIMEOUT","original-owner-deadline");}));calls.gate(label);expired=true;waitFor([&]{return calls.pool.ready(t);});error("E_TIMEOUT",[&]{(void)calls.pool.take(t);},"original-owner-deadline");});
   run("queued_cancel_opens_no_socket",[&]{TaskExternalPool one({1,64,8*1048576,1048576});auto label=calls.label("queued");auto p=calls.prepare("held",bytesOf(label),64,10000);auto first=one.submit(1,p.operation(),p.reservation);calls.gate(label);auto before=calls.stats()[0];auto q=calls.prepare("echo",bytesOf("queued-not-sent"));auto second=one.submit(2,q.operation(),q.reservation);one.cancel(second);one.cancel(first);waitFor([&]{return one.ready(first)&&one.ready(second);});error("E_CANCELLED",[&]{(void)one.take(first);});error("E_CANCELLED",[&]{(void)one.take(second);});require(calls.stats()[0]==before,"queued cancellation connected");});
   run("scope_revocation_during_actual_IO",[&]{auto nested=std::make_unique<ForeignScope>(libraries);auto captured=captureForeignScope();auto label=calls.label("scope-revocation");std::vector<Value> args{Value(string("held")),Value(bytes(ByteBuffer::copy(bytesOf(label)))),Value(64),Value(10000)};PreparedTaskForeignCall p(captured,calls.exchange,args);auto t=calls.submit(p);calls.gate(label);
    // This completed call uses the outer authority. Prepare the equivalent
    // copied call under the nested context so late admission checks that exact
    // ended lexical owner, independently of physical module revocation timing.
    std::vector<Value> doneArgs{Value(string("echo")),Value(bytes(ByteBuffer::copy(bytesOf("late-admission")))),Value(64),Value(3000)};
    PreparedTaskForeignCall late(captured,calls.exchange,doneArgs);auto done=calls.submit(late);waitFor([&]{return calls.pool.ready(done);});auto raw=calls.pool.take(done);
    nested.reset();waitFor([&]{return calls.pool.ready(t);});
    // Scope destruction revokes both logical context and physical domain.
    // Whichever check observes this concurrent event first remains fatal.
    try{(void)calls.pool.take(t);throw DataError("E_TEST","revoked IO succeeded");}
    catch(const DataError &e){require(e.code=="E_RESOURCE_SCOPE"||e.code=="E_FFI_SCOPE","wrong in-flight revocation error");}
    error("E_FFI_SCOPE",[&]{(void)late.admit(std::move(raw));});});
   run("abandoned_pool_drains_physical_call",[&]{auto label=calls.label("abandoned");auto p=calls.prepare("held",bytesOf(label),64,10000);{TaskExternalPool abandoned;auto t=abandoned.submit(1,p.operation(),p.reservation);calls.gate(label);} });
   // Revocation intentionally retires the catalogue and its held descriptors;
   // it is checked after the per-case stable-descriptor invariants above.
   {auto label=calls.label("module-revocation");auto p=calls.prepare("held",bytesOf(label),64,10000);auto t=calls.submit(p);calls.gate(label);libraries->revoke();waitFor([&]{return calls.pool.ready(t);});error("E_RESOURCE_SCOPE",[&]{(void)calls.pool.take(t);});checks.push_back("module_grant_revocation_during_IO");}
  }
 }
 libraries.reset();require(liveObjects.load()==0,"managed value survives completed host request");
 std::cout<<J{{"schema","nex.tcp-typed-host-sanitizers/1"},{"ok",true},{"checks",checks},{"actual_C_API",true},{"actual_copied_task_FFI_bridge",true},{"actual_loaded_pinned_module",true},{"compiler_or_generated_NEX_IR_instrumented",false}}.dump()<<'\n';return 0;
}catch(const DataError &e){std::cerr<<e.code<<": "<<e.what()<<'\n';return 1;}catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 2;}
