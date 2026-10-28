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
Value aggregate(Data::Kind kind,std::vector<Value> values){auto data=std::make_shared<Data>(kind);data->values=std::move(values);return Value(std::move(data));}
Value octets(const std::vector<uint8_t> &value){return Value(bytes(ByteBuffer::copy(value)));}
void ordinary(const Value &value,const char *code){require(!isSuccess(value)&&value.object&&value.object->text==code,std::string("ordinary failure differs: ")+code);}
void expectResponse(const Value &value,int64_t status=200,const std::vector<uint8_t> &body={52,50},const std::string &protocol=""){
 require(isSuccess(value),"ordinary HTTP error instead of success: "+representation(value));auto response=unwrap(value);require(response.object&&response.object->kind==Data::Record&&response.object->text=="std::http_client::Response"&&response.object->values.size()==5,"response layout");const auto &fields=response.object->values;require(fields[0].scalar==status,"HTTP status differs");require(byteBuffer(fields[2].object).toVector()==body,"binary HTTP body differs");if(!protocol.empty())require(fields[3].object&&fields[3].object->text==protocol,"HTTP protocol differs");
}
struct Calls {
 CapturedForeignScope scope;std::string send,statistics;TaskExternalPool pool;uint64_t id=0;fs::path gates;std::string run;J config,type;
 Calls(CapturedForeignScope scope,const J &config,fs::path gates,std::string run):scope(std::move(scope)),send(config.at("send").dump()),statistics(config.at("statistics").dump()),gates(std::move(gates)),run(std::move(run)),config(config),type(config.at("send").at("signature").at("types").at(0)){}
 Value request(const std::string &path="/ok",const std::string &transport="http",int64_t timeout=3000,int64_t limit=262144){
  auto data=std::make_shared<Data>(Data::Record);data->text=type.at("name");for(const auto &field:type.at("fields"))data->names.push_back(field.at("name"));
  data->values={Value(string(transport=="ipv6"?"ip6":transport=="ipv4"?"ip4":"backend")),Value(string("GET")),Value(string(config.at(transport).get<std::string>()+path)),aggregate(Data::List,{}),octets({}),Value(limit),Value(timeout),Value(int64_t(0)),Value(string("auto"))};return Value(std::move(data));
 }
 PreparedTaskForeignCall prepare(Value request){std::array<Value,1> args{std::move(request)};return PreparedTaskForeignCall(scope,send,args);}
 TaskExternalTicket submit(const PreparedTaskForeignCall &call,TaskExternalControl control=TaskExternalControl{}){return pool.submit(++id,call.operation(),call.reservation,std::move(control));}
 Value take(const PreparedTaskForeignCall &call,const TaskExternalTicket &ticket){waitFor([&]{return pool.ready(ticket);});return call.admit(pool.take(ticket));}
 Value invoke(Value request){auto call=prepare(std::move(request));auto ticket=submit(call);return take(call,ticket);}
 std::array<int64_t,8> stats(){auto fn=scope.bind(statistics);auto value=fn.invoke({});require(value.object&&value.object->values.size()==8,"statistics layout");std::array<int64_t,8> result{};for(size_t i=0;i<8;++i)result[i]=value.object->values[i].scalar;return result;}
 std::string label(const char *name){return std::string("/held-")+name+"-"+run;}
 void gate(const std::string &path){waitFor([&]{return fs::is_regular_file(gates/(digest(path)+".ready"));});}
 void release(const std::string &path){write(gates/(digest(path)+".release"));}
 void settled(){auto s=stats();require(s[0]==s[1]&&s[2]==0&&s[4]==s[5]&&s[6]==0,"HTTP/DNS not physically retired before admission");auto k=pool.stats();require(k.tickets==0&&k.reservedBytes==0&&k.running==0&&k.queued==0,"IO reservation remains");}
};
}
int main(int argc,char **argv)try{
 require(argc==5,"expected project, gates, run identity, mode");fs::path project=argv[1];auto config=J::parse(read(project/"host-input.json"));auto libraries=loadForeignLibraries((project/"two-context-foreign.json").string());J checks=J::array();
 {
  RequestScope request(100000000,120000);ForeignScope lexical(libraries);Calls calls(captureForeignScope(),config,argv[2],argv[3]);calls.stats();
  auto run=[&](const std::string &name,auto action){auto fds=descriptors();auto objects=liveObjects.load();action();calls.settled();require(liveObjects.load()==objects,"managed value owner leaked");require(descriptors()==fds,"native descriptor leaked");checks.push_back(name);std::cerr<<"NEX_HTTP_HOST_CHECK "<<name<<'\n';};
  if(std::string(argv[4])=="capacity"){
   run("owned_capacity_cancel_and_reuse",[&]{auto name=calls.label("capacity");auto held=calls.prepare(calls.request(name,"http",10000));auto ticket=calls.submit(held);calls.gate(name);ordinary(calls.invoke(calls.request()),"E_HTTP_BUSY");calls.pool.cancel(ticket);waitFor([&]{return calls.pool.ready(ticket);});error("E_CANCELLED",[&]{(void)calls.pool.take(ticket);});expectResponse(calls.invoke(calls.request()));require(calls.stats()[3]==1,"capacity did not cover physical lifetime");});
  }else{
   run("HTTP_typed_C_tokens_and_input_snapshot",[&]{auto input=calls.request();auto call=calls.prepare(input);input.object->values[2]=Value(string("http://outside.test/"));input.object->values[4]=octets({0,255});auto ticket=calls.submit(call);expectResponse(calls.take(call,ticket),200,{52,50},"1.1");});
   run("HTTPS_HTTP2_and_repeated_headers",[&]{auto result=calls.invoke(calls.request("/ok","https"));expectResponse(result,200,{52,50},"2");auto response=unwrap(result);size_t cookies=0;for(const auto &header:response.object->values[1].object->values)if(header.object->values[0].object->text=="set-cookie")++cookies;require(cookies==2,"repeated HTTP2 headers lost");});
   run("HTTPS_forced_HTTP1",[&]{auto input=calls.request("/ok","https");input.object->values[8]=Value(string("1.1"));expectResponse(calls.invoke(input),200,{52,50},"1.1");});
   run("TLS_hostname_rejection",[&]{auto input=calls.request("/ok","https");auto url=input.object->values[2].object->text;auto pos=url.find("api.example.test");require(pos!=std::string::npos,"owned TLS hostname missing");url.replace(pos,16,"other.example.test");input.object->values[2]=Value(string(url));ordinary(calls.invoke(input),"E_TLS");});
   run("binary_POST_snapshot",[&]{std::vector<uint8_t> body{0,255,128,208,175,240,159,167,160};auto input=calls.request("/echo");input.object->values[1]=Value(string("POST"));input.object->values[4]=octets(body);auto call=calls.prepare(input);input.object->values[4]=octets({99});auto ticket=calls.submit(call);expectResponse(calls.take(call,ticket),200,body);});
   run("numeric_IPv4_IPv6_without_DNS",[&]{auto count=calls.stats()[0];expectResponse(calls.invoke(calls.request("/ok","ipv4")));expectResponse(calls.invoke(calls.request("/ok","ipv6")));require(calls.stats()[0]==count,"literal IP triggered DNS");});
   run("invalid_bounds_before_DNS",[&]{auto count=calls.stats()[0];ordinary(calls.invoke(calls.request("/ok","http",INT64_MAX)),"VALIDATION");ordinary(calls.invoke(calls.request("/ok","http",1000,0)),"VALIDATION");require(calls.stats()[0]==count,"invalid request queried");});
   run("ungranted_domain_before_DNS",[&]{auto count=calls.stats()[0];auto input=calls.request();input.object->values[0]=Value(string("unknown"));ordinary(calls.invoke(input),"CAPABILITY");input=calls.request();input.object->values[2]=Value(string("http://evil-example.test:80/"));ordinary(calls.invoke(input),"CAPABILITY");require(calls.stats()[0]==count,"ungranted domain queried");});
   run("response_bounds_and_opaque_bytes",[&]{ordinary(calls.invoke(calls.request("/many","http",3000,8)),"E_HTTP_LIMIT");ordinary(calls.invoke(calls.request("/too-many-headers")),"E_HTTP_LIMIT");expectResponse(calls.invoke(calls.request("/invalid-UTF8")),200,{255,128,0});});
   run("own_HTTP_TLS_timeout_then_reuse",[&]{ordinary(calls.invoke(calls.request(calls.label("own"),"http",60)),"E_HTTP_TIMEOUT");ordinary(calls.invoke(calls.request("/","stall",60)),"E_HTTP_TIMEOUT");expectResponse(calls.invoke(calls.request()));});
   for(const auto &transport:std::array<std::string,2>{"http","https"}){
    run(transport+"_IO_progress_and_coordinator_work",[&]{auto name=calls.label((transport+"-progress").c_str());auto call=calls.prepare(calls.request(name,transport,10000));auto ticket=calls.submit(call);calls.gate(name);uint64_t total=0;for(unsigned i=0;i<10000;++i)total+=i;require(total==49995000,"coordinator work");expectResponse(calls.invoke(calls.request()));calls.release(name);expectResponse(calls.take(call,ticket));require(calls.stats()[7]>=2,"IO did not overlap");});
    run(transport+"_inflight_pool_cancellation",[&]{auto name=calls.label((transport+"-cancel").c_str());auto call=calls.prepare(calls.request(name,transport,10000));auto ticket=calls.submit(call);calls.gate(name);calls.pool.cancel(ticket);waitFor([&]{return calls.pool.ready(ticket);});error("E_CANCELLED",[&]{(void)calls.pool.take(ticket);});});
    run(transport+"_original_parent_deadline",[&]{auto name=calls.label((transport+"-deadline").c_str());std::atomic<bool> expired=false;auto call=calls.prepare(calls.request(name,transport,10000));auto ticket=calls.submit(call,TaskExternalControl([&]{if(expired.load())throw DataError("E_TIMEOUT","original-owner-deadline");}));calls.gate(name);expired=true;waitFor([&]{return calls.pool.ready(ticket);});error("E_TIMEOUT",[&]{(void)calls.pool.take(ticket);},"original-owner-deadline");});
   }
   run("queued_cancel_opens_no_channel_or_socket",[&]{TaskExternalPool one({1,64,8*1048576,1048576});auto name=calls.label("queued");auto call=calls.prepare(calls.request(name,"http",10000));auto first=one.submit(1,call.operation(),call.reservation);calls.gate(name);auto before=calls.stats();auto queued=calls.prepare(calls.request());auto second=one.submit(2,queued.operation(),queued.reservation);one.cancel(second);one.cancel(first);waitFor([&]{return one.ready(first)&&one.ready(second);});error("E_CANCELLED",[&]{(void)one.take(first);});error("E_CANCELLED",[&]{(void)one.take(second);});auto after=calls.stats();require(after[0]==before[0]&&after[4]==before[4],"queued cancellation opened IO");});
   run("scope_revocation_and_late_admission",[&]{auto nested=std::make_unique<ForeignScope>(libraries);auto captured=captureForeignScope();auto name=calls.label("scope-revocation");std::array<Value,1> args{calls.request(name,"https",10000)};PreparedTaskForeignCall held(captured,calls.send,args);auto ticket=calls.submit(held);calls.gate(name);args[0]=calls.request();PreparedTaskForeignCall late(captured,calls.send,args);auto done=calls.submit(late);waitFor([&]{return calls.pool.ready(done);});auto raw=calls.pool.take(done);nested.reset();waitFor([&]{return calls.pool.ready(ticket);});try{(void)calls.pool.take(ticket);throw DataError("E_TEST","revoked IO succeeded");}catch(const DataError &e){require(e.code=="E_RESOURCE_SCOPE"||e.code=="E_FFI_SCOPE","wrong revocation error");}error("E_FFI_SCOPE",[&]{(void)late.admit(std::move(raw));});});
   run("abandoned_pool_drains_physical_call",[&]{auto name=calls.label("abandoned");auto call=calls.prepare(calls.request(name,"https",10000));{TaskExternalPool abandoned;auto ticket=abandoned.submit(1,call.operation(),call.reservation);calls.gate(name);}});
   {auto name=calls.label("module-revocation");auto call=calls.prepare(calls.request(name,"https",10000));auto ticket=calls.submit(call);calls.gate(name);libraries->revoke();waitFor([&]{return calls.pool.ready(ticket);});error("E_RESOURCE_SCOPE",[&]{(void)calls.pool.take(ticket);});auto s=calls.pool.stats();require(s.tickets==0&&s.reservedBytes==0&&s.running==0&&s.queued==0,"revoked module retains IO reservation");checks.push_back("module_grant_revocation_during_IO");}
  }
 }
 libraries.reset();require(liveObjects.load()==0,"managed value survives host request");
 std::cout<<J{{"schema","nex.http-typed-host-sanitizers/1"},{"ok",true},{"checks",checks},{"actual_C_API",true},{"actual_copied_task_FFI_bridge",true},{"actual_loaded_pinned_module",true},{"compiler_or_generated_NEX_IR_instrumented",false},{"OpenSSL_instrumented",false}}.dump()<<'\n';return 0;
}catch(const DataError &error){std::cerr<<error.code<<": "<<error.what()<<'\n';return 1;}catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 2;}
