#include "nex_socket_platform.h"
#include "nex_task_network.h"
#include <algorithm>
#include <array>
#include <chrono>
#include <condition_variable>
#include <exception>
#include <iostream>
#include <mutex>
#include <thread>

using namespace nexrt;
namespace sockets=nexrt::socket_platform;
using namespace std::chrono_literals;
namespace {
size_t checks=0;
void require(bool value,const char *message){if(!value)throw std::runtime_error(message);++checks;}
template<class F> void rejected(const char *code,F run){
  try{run();throw std::runtime_error(std::string("accepted ")+code);}
  catch(const DataError &error){require(error.code==code,(std::string("unexpected ")+error.code+" expected "+code).c_str());}
}
template<class F> void until(F condition){
  const auto end=std::chrono::steady_clock::now()+3s;
  while(!condition()){if(std::chrono::steady_clock::now()>end)throw std::runtime_error("test condition timed out");std::this_thread::sleep_for(1ms);}
}
struct FD {sockets::Handle value=sockets::invalid;explicit FD(sockets::Handle value):value(value){}~FD(){if(value!=sockets::invalid)sockets::close(value);}FD(const FD&)=delete;};
class Server {
  FD listener;std::jthread thread;std::exception_ptr error;std::mutex mutex;std::condition_variable changed;bool released=false;
public:
  enum Mode {Echo,Hold,Overflow,Reset};
  const int family;uint16_t port=0;std::atomic<bool> accepted{false};std::vector<uint8_t> received;
  explicit Server(Mode mode=Echo,int family=AF_INET,size_t extra=0):listener(::socket(family,SOCK_STREAM,0)),family(family){
    if(listener.value==sockets::invalid)throw std::runtime_error("server socket failed");
    int one=1;sockets::setOption(listener.value,SOL_SOCKET,SO_REUSEADDR,&one,sizeof(one));
    if(family==AF_INET){
      sockaddr_in address{};address.sin_family=AF_INET;address.sin_addr.s_addr=htonl(INADDR_LOOPBACK);
      if(::bind(listener.value,reinterpret_cast<sockaddr*>(&address),sizeof(address)))throw std::runtime_error("server bind failed");
      sockets::Length length=sizeof(address);require(::getsockname(listener.value,reinterpret_cast<sockaddr*>(&address),&length)==0,"server address");port=ntohs(address.sin_port);
    }else{
      sockaddr_in6 address{};address.sin6_family=AF_INET6;address.sin6_addr=in6addr_loopback;
      if(::bind(listener.value,reinterpret_cast<sockaddr*>(&address),sizeof(address)))throw std::runtime_error("IPv6 server bind failed");
      sockets::Length length=sizeof(address);require(::getsockname(listener.value,reinterpret_cast<sockaddr*>(&address),&length)==0,"IPv6 server address");port=ntohs(address.sin6_port);
    }
    require(::listen(listener.value,4)==0,"server listen");
    thread=std::jthread([this,mode,extra]{try{
      if(sockets::wait(listener.value,false,3000).ready!=1)throw std::runtime_error("server accept timed out");
      FD client(::accept(listener.value,nullptr,nullptr));if(client.value==sockets::invalid)throw std::runtime_error("server accept failed");accepted=true;
      if(mode==Reset){linger immediate{1,0};sockets::setOption(client.value,SOL_SOCKET,SO_LINGER,&immediate,sizeof(immediate));return;}
#ifdef _WIN32
      DWORD timeout=2000;
#else
      timeval timeout{2,0};
#endif
      sockets::setOption(client.value,SOL_SOCKET,SO_RCVTIMEO,&timeout,sizeof(timeout));sockets::setOption(client.value,SOL_SOCKET,SO_SNDTIMEO,&timeout,sizeof(timeout));
      for(;;){uint8_t block[4096];auto n=sockets::receive(client.value,block,sizeof(block),0);if(!n)break;if(n<0)throw std::runtime_error("server read failed");received.insert(received.end(),block,block+n);}
      if(mode==Hold){std::unique_lock lock(mutex);changed.wait_for(lock,3s,[this]{return released;});return;}
      std::vector<uint8_t> reply=received;if(mode==Overflow)reply.resize(reply.size()+extra,99);
      size_t sent=0;while(sent<reply.size()){
        int flags=0;
#ifdef MSG_NOSIGNAL
        flags=MSG_NOSIGNAL;
#endif
#ifdef SO_NOSIGPIPE
        int enabled=1;sockets::setOption(client.value,SOL_SOCKET,SO_NOSIGPIPE,&enabled,sizeof(enabled));
#endif
        auto n=sockets::send(client.value,reply.data()+sent,std::min<size_t>(127,reply.size()-sent),flags);
        if(n<1)throw std::runtime_error("server reply failed");sent+=size_t(n);
      }
    }catch(...){error=std::current_exception();}});
  }
  void release(){std::lock_guard lock(mutex);released=true;changed.notify_all();}
  void join(){release();if(thread.joinable())thread.join();if(error)std::rethrow_exception(error);}
  ~Server(){release();if(thread.joinable())thread.join();}
  TaskTcpEndpoint endpoint(std::string name="echo")const{return {std::move(name),family==AF_INET?"127.0.0.1":"::1",port};}
};
TaskNetworkGrant grantFor(ResourceDomain &scope,const Server &server){auto endpoint=server.endpoint();return TaskNetworkGrant(scope.access(),std::span(&endpoint,1));}
TaskExternalResult finish(TaskExternalPool &pool,const TaskExternalTicket &ticket){until([&]{return pool.ready(ticket);});return pool.take(ticket);}
void boundaries(){
  std::vector<uint8_t> bytes{1,0,255};TaskNetworkGrant absent;
  rejected("CAPABILITY",[&]{PreparedTaskTcpExchange p(absent,"echo",bytes,8);});
  ResourceDomain scope;TaskTcpEndpoint valid{"echo","127.0.0.1",1};TaskNetworkGrant grant(scope.access(),std::span(&valid,1));
  rejected("CAPABILITY",[&]{PreparedTaskTcpExchange p(grant,"other",bytes,8);});
  for(auto bad:std::vector<TaskTcpEndpoint>{{"","127.0.0.1",1},{"echo","localhost",1},{"echo","127.0.0.1",0},{"echo",std::string("127.0.0.1\0hidden",16),1}})
    rejected("E_RANGE",[&]{TaskNetworkGrant badGrant(scope.access(),std::span(&bad,1));});
  TaskTcpEndpoint twice[]{valid,valid};rejected("E_RANGE",[&]{TaskNetworkGrant g(scope.access(),twice);});
  for(auto limit:{size_t(0),PreparedTaskTcpExchange::maximumReply+1})rejected("E_RANGE",[&]{PreparedTaskTcpExchange p(grant,"echo",bytes,limit);});
  for(auto timeout:{0u,PreparedTaskTcpExchange::maximumTimeoutMs+1})rejected("E_RANGE",[&]{PreparedTaskTcpExchange p(grant,"echo",bytes,8,timeout);});
  std::vector<uint8_t> large(PreparedTaskTcpExchange::maximumInput+1);rejected("E_RANGE",[&]{PreparedTaskTcpExchange p(grant,"echo",large,8);});
  require(grant.stats().opened==0,"validation opened a socket");scope.revoke();rejected("E_RESOURCE_SCOPE",[&]{PreparedTaskTcpExchange p(grant,"echo",bytes,8);});
}
void echo(int family){
  ResourceDomain scope;Server server(Server::Echo,family);auto grant=grantFor(scope,server);
  std::vector<uint8_t> input(65537);for(size_t i=0;i<input.size();++i)input[i]=uint8_t(i);auto expected=input;
  PreparedTaskTcpExchange prepared(grant,"echo",input,input.size());input.assign(input.size(),42);
  TaskExternalPool pool;auto ticket=pool.submit(1,prepared.operation(),prepared.reservation());
  auto raw=finish(pool,ticket);require(grant.stats().live==0&&grant.stats().opened==grant.stats().closed,"socket survived physical publication");
  auto reply=prepared.admit(std::move(raw));require(reply.bytes==expected,(std::string("TCP snapshot or exact-limit reply changed: ")+reply.errorCode+" "+reply.errorMessage+"; received "+std::to_string(reply.bytes.size())+" of "+std::to_string(expected.size())+" bytes").c_str());server.join();require(server.received==expected,"request snapshot changed");pool.drain();require(pool.stats().reservedBytes==0,"echo quota leaked");
}
void ordinaryError(){
  uint16_t port=0;
  {FD unused(::socket(AF_INET,SOCK_STREAM,0));require(unused.value!=sockets::invalid,"unused socket");sockaddr_in address{};address.sin_family=AF_INET;address.sin_addr.s_addr=htonl(INADDR_LOOPBACK);
   require(::bind(unused.value,reinterpret_cast<sockaddr*>(&address),sizeof(address))==0,"unused bind");sockets::Length length=sizeof(address);require(::getsockname(unused.value,reinterpret_cast<sockaddr*>(&address),&length)==0,"unused address");port=ntohs(address.sin_port);}
  ResourceDomain scope;TaskTcpEndpoint endpoint{"closed","127.0.0.1",port};TaskNetworkGrant grant(scope.access(),std::span(&endpoint,1));
  // Windows reports a refused loopback connect after about2s; use the normal
  // transport deadline. Held-peer/queue cases test deadlines independently.
  PreparedTaskTcpExchange p(grant,"closed",{},8);TaskExternalPool pool;auto ticket=pool.submit(1,p.operation(),p.reservation());auto raw=p.admit(finish(pool,ticket));require(raw.errorCode=="E_NETWORK"&&raw.bytes.empty(),"connection refusal not an ordinary error");require(grant.stats().live==0,"refused socket leaked");
}
void overflow(){
  ResourceDomain scope;Server server(Server::Overflow,AF_INET,1);auto grant=grantFor(scope,server);std::vector<uint8_t> input{1,2,3};
  PreparedTaskTcpExchange p(grant,"echo",input,3);TaskExternalPool pool;auto ticket=pool.submit(1,p.operation(),p.reservation());until([&]{return pool.ready(ticket);});rejected("E_LIMIT",[&]{pool.take(ticket);});server.join();require(grant.stats().live==0,"overflow socket leaked");
}
void interrupted(bool revoke,bool parentDeadline,bool ownDeadline=false){
  ResourceDomain scope;Server server(Server::Hold);auto grant=grantFor(scope,server);std::vector<uint8_t> input{9};
  PreparedTaskTcpExchange p(grant,"echo",input,8,ownDeadline?300:5000);std::atomic<bool> timeout{false};
  TaskExternalPool pool;auto ticket=pool.submit(1,p.operation(),p.reservation(),TaskExternalControl([&]{if(timeout)throw DataError("E_TIMEOUT","parent request expired");}));until([&]{return server.accepted.load();});
  if(revoke)scope.revoke();else if(parentDeadline)timeout=true;else if(!ownDeadline)pool.cancel(ticket);
  until([&]{return pool.ready(ticket);});rejected(revoke?"E_RESOURCE_SCOPE":(parentDeadline||ownDeadline)?"E_TIMEOUT":"E_CANCELLED",[&]{pool.take(ticket);});
  require(grant.stats().live==0&&grant.stats().opened==grant.stats().closed,"interrupted socket survived completion");server.join();pool.drain();require(pool.stats().reservedBytes==0,"interrupt quota leaked");
}
void lateAdmission(){
  ResourceDomain scope;Server server;auto grant=grantFor(scope,server);std::vector<uint8_t> input{5};PreparedTaskTcpExchange p(grant,"echo",input,8);
  TaskExternalPool pool;auto ticket=pool.submit(1,p.operation(),p.reservation());auto raw=finish(pool,ticket);server.join();scope.revoke();rejected("E_RESOURCE_SCOPE",[&]{p.admit(std::move(raw));});
}
struct Gate final:TaskExternalOperation {
  std::atomic<bool> &entered,&release;Gate(std::atomic<bool> &e,std::atomic<bool> &r):entered(e),release(r){}
  TaskExternalResult run(const TaskExternalControl &control)override{entered=true;until([&]{return release.load();});control.checkpoint();return {};}
};
void queued(){
  ResourceDomain scope;TaskTcpEndpoint endpoint{"unused","127.0.0.1",1};TaskNetworkGrant grant(scope.access(),std::span(&endpoint,1));std::atomic<bool> entered{false},release{false};
  PreparedTaskTcpExchange p(grant,"unused",{},8,10);TaskExternalPool pool({1,2,16384,1024});auto blocker=pool.submit(1,std::make_shared<Gate>(entered,release),0);until([&]{return entered.load();});auto ticket=pool.submit(2,p.operation(),p.reservation());std::this_thread::sleep_for(30ms);release=true;finish(pool,blocker);until([&]{return pool.ready(ticket);});rejected("E_TIMEOUT",[&]{pool.take(ticket);});require(grant.stats().opened==0,"expired queued request opened a socket");
}
void concurrent(){
  ResourceDomain scope;Server a(Server::Hold),b(Server::Hold);TaskTcpEndpoint endpoints[]{a.endpoint("a"),b.endpoint("b")};TaskNetworkGrant grant(scope.access(),endpoints);
  PreparedTaskTcpExchange first(grant,"a",{},8),second(grant,"b",{},8);TaskExternalPool pool({2,2,16384,1024});auto ta=pool.submit(1,first.operation(),first.reservation());auto tb=pool.submit(2,second.operation(),second.reservation());until([&]{return a.accepted.load()&&b.accepted.load();});require(grant.stats().live==2&&pool.stats().running==2,"network requests serialized on coordinator");pool.cancel(ta);pool.cancel(tb);until([&]{return pool.ready(ta)&&pool.ready(tb);});rejected("E_CANCELLED",[&]{pool.take(ta);});rejected("E_CANCELLED",[&]{pool.take(tb);});a.join();b.join();require(grant.stats().live==0,"concurrent sockets leaked");
}
void queuedCancellationAndReservation(){
  ResourceDomain scope;TaskTcpEndpoint endpoint{"unused","127.0.0.1",1};TaskNetworkGrant grant(scope.access(),std::span(&endpoint,1));
  std::vector<uint8_t> input(4096,7);PreparedTaskTcpExchange p(grant,"unused",input,8);
  TaskExternalPool small({1,1,1024,1024});rejected("E_LIMIT",[&]{small.submit(1,p.operation(),p.reservation());});require(grant.stats().opened==0,"rejected reservation opened a socket");
  std::atomic<bool> entered{false},release{false};TaskExternalPool pool({1,2,16384,1024});auto blocker=pool.submit(1,std::make_shared<Gate>(entered,release),0);until([&]{return entered.load();});auto ticket=pool.submit(2,p.operation(),p.reservation());pool.cancel(ticket);
  require(pool.stats().tickets==2&&pool.stats().reservedBytes==p.reservation(),"queued cancellation released quota before physical retirement");release=true;finish(pool,blocker);until([&]{return pool.ready(ticket);});rejected("E_CANCELLED",[&]{pool.take(ticket);});require(grant.stats().opened==0,"cancelled queued request connected");pool.drain();require(pool.stats().reservedBytes==0,"queued reservation survived drain");
}
void resetAndAbandonedPool(){
  {
    ResourceDomain scope;Server server(Server::Reset);auto grant=grantFor(scope,server);std::vector<uint8_t> input(1048576,42);PreparedTaskTcpExchange p(grant,"echo",input,8);TaskExternalPool pool;auto ticket=pool.submit(1,p.operation(),p.reservation());auto raw=p.admit(finish(pool,ticket));require(raw.errorCode=="E_NETWORK","peer reset did not report a network failure");server.join();require(grant.stats().live==0,"reset socket leaked");
  }
  {
    ResourceDomain scope;Server server(Server::Hold);auto grant=grantFor(scope,server);PreparedTaskTcpExchange p(grant,"echo",{},8);
    {TaskExternalPool pool;pool.submit(1,p.operation(),p.reservation());until([&]{return server.accepted.load();});}
    require(grant.stats().live==0&&grant.stats().opened==grant.stats().closed,"pool destruction did not close actual network IO");server.join();
  }
}
void rejectedAdmission(){
  ResourceDomain scope;TaskTcpEndpoint endpoint{"unused","127.0.0.1",1};TaskNetworkGrant grant(scope.access(),std::span(&endpoint,1));PreparedTaskTcpExchange p(grant,"unused",{},8);
  TaskExternalResult oversized;oversized.bytes.reserve(32);rejected("E_LIMIT",[&]{p.admit(std::move(oversized));});
  TaskExternalResult forged;forged.errorCode="E_CANCELLED";rejected("E_TASK_VALUE",[&]{p.admit(std::move(forged));});
  TaskExternalResult mixed;mixed.errorCode="E_NETWORK";mixed.bytes.push_back(1);rejected("E_TASK_VALUE",[&]{p.admit(std::move(mixed));});
  rejected("E_CANCELLED",[&]{p.admit({},TaskExternalControl([]{throw DataError("E_CANCELLED","parent cancelled before admission");}));});
  scope.revoke();TaskExternalResult fatal;fatal.errorCode="E_TIMEOUT";rejected("E_TIMEOUT",[&]{p.admit(std::move(fatal));});require(grant.stats().opened==0,"admission validation opened a socket");
}
void retainedGrant(){
  ResourceDomain scope;Server server;auto endpoint=server.endpoint();
  auto prepared=[&]{TaskNetworkGrant original(scope.access(),std::span(&endpoint,1));return PreparedTaskTcpExchange(original,"echo",std::array<uint8_t,3>{1,0,255},3);}();
  TaskExternalPool pool;auto ticket=pool.submit(1,prepared.operation(),prepared.reservation());
  require(prepared.admit(finish(pool,ticket)).bytes==std::vector<uint8_t>({1,0,255}),"exchange lost its retained grant");server.join();
}
void winsockOwnership(){
#ifdef _WIN32
  auto bare=::socket(AF_INET,SOCK_STREAM,0);
  require(bare==INVALID_SOCKET&&::WSAGetLastError()==WSANOTINITIALISED,"unexpected ambient Winsock initialization");
  ResourceDomain scope;TaskTcpEndpoint endpoint{"unused","127.0.0.1",1};
  auto prepared=std::make_unique<PreparedTaskTcpExchange>([&]{TaskNetworkGrant original(scope.access(),std::span(&endpoint,1));return PreparedTaskTcpExchange(original,"unused",{},8);}());
  auto retained=::socket(AF_INET,SOCK_STREAM,0);require(retained!=INVALID_SOCKET,"exchange did not retain Winsock");::closesocket(retained);
  prepared.reset();bare=::socket(AF_INET,SOCK_STREAM,0);
  require(bare==INVALID_SOCKET&&::WSAGetLastError()==WSANOTINITIALISED,"grant leaked its Winsock initialization");
#endif
}
}
int main(int argc,const char *const*argv){try{
  std::vector<std::string> selected;
  for(int i=1;i<argc;++i){if(std::string(argv[i])!="--case"||i+1>=argc)throw std::runtime_error("expected --case NAME");selected.push_back(argv[++i]);}
  std::vector<std::string> ran;
  auto run=[&](const char *name,auto test){if(selected.empty()||std::find(selected.begin(),selected.end(),name)!=selected.end()){try{test();}catch(const std::exception &error){throw std::runtime_error(std::string(name)+": "+error.what());}ran.emplace_back(name);}};
  {[[maybe_unused]] sockets::Library testSockets;
   run("boundaries",boundaries);run("ipv4",[]{echo(AF_INET);});run("ipv6",[]{echo(AF_INET6);});
   run("refusal",ordinaryError);run("overflow",overflow);run("cancel",[]{interrupted(false,false);});
   run("revoke",[]{interrupted(true,false);});run("parent-deadline",[]{interrupted(false,true);});
   run("own-deadline",[]{interrupted(false,false,true);});run("late-admission",lateAdmission);
   run("queued-deadline",queued);run("concurrent",concurrent);run("queued-cancel",queuedCancellationAndReservation);
   run("reset-and-abandoned",resetAndAbandonedPool);run("rejected-admission",rejectedAdmission);run("retained-grant",retainedGrant);
  }
  run("winsock-ownership",winsockOwnership);
  for(const auto &name:selected)if(std::find(ran.begin(),ran.end(),name)==ran.end())throw std::runtime_error("unknown case "+name);
  std::cout<<"{\"schema\":\"nex.task-tcp-kernel/1\",\"ok\":true,\"checks\":"<<checks<<",\"actual_IPv4_IPv6\":"<<((std::find(ran.begin(),ran.end(),"ipv4")!=ran.end()&&std::find(ran.begin(),ran.end(),"ipv6")!=ran.end())?"true":"false")<<",\"full_suite\":"<<(selected.empty()?"true":"false")<<",\"cases\":"<<ran.size()<<",\"source_language_enabled\":false}\n";
}catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 1;}}
