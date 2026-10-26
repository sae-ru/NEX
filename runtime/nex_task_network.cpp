#include "nex_task_network.h"

#ifndef _WIN32
#include <algorithm>
#include <arpa/inet.h>
#include <cerrno>
#include <cstring>
#include <fcntl.h>
#include <poll.h>
#include <sys/socket.h>
#include <unistd.h>

namespace nexrt {
namespace task_network_detail {
using Clock=std::chrono::steady_clock;
struct Endpoint {std::string name;sockaddr_storage address{};socklen_t length=0;};
struct Ledger {
  std::atomic<size_t> opened{0},closed{0},live{0},maximumLive{0};
};
struct Grant {ResourceAccess authority;std::vector<Endpoint> endpoints;std::shared_ptr<Ledger> ledger=std::make_shared<Ledger>();};
struct Exchange {
  std::shared_ptr<const Grant> grant;Endpoint endpoint;std::vector<uint8_t> input;
  size_t replyLimit=0,reservation=0;Clock::time_point deadline;
};
[[noreturn]] void networkError(const char *operation,int error){
  throw DataError("E_NETWORK",std::string(operation)+": "+std::strerror(error));
}
class Socket {
  int descriptor=-1;std::shared_ptr<Ledger> ledger;
public:
  Socket(int family,std::shared_ptr<Ledger> counters):ledger(std::move(counters)){
    int type=SOCK_STREAM;
#ifdef SOCK_CLOEXEC
    type|=SOCK_CLOEXEC;
#endif
#ifdef SOCK_NONBLOCK
    type|=SOCK_NONBLOCK;
#endif
    descriptor=::socket(family,type,0);
    if(descriptor<0)networkError("socket",errno);
    try{
      auto flags=::fcntl(descriptor,F_GETFD);if(flags<0||::fcntl(descriptor,F_SETFD,flags|FD_CLOEXEC)<0)networkError("socket close-on-exec",errno);
      flags=::fcntl(descriptor,F_GETFL);if(flags<0||::fcntl(descriptor,F_SETFL,flags|O_NONBLOCK)<0)networkError("socket nonblocking",errno);
#ifdef SO_NOSIGPIPE
      int enabled=1;if(::setsockopt(descriptor,SOL_SOCKET,SO_NOSIGPIPE,&enabled,sizeof(enabled)))networkError("socket no-sigpipe",errno);
#endif
    }catch(...){::close(descriptor);descriptor=-1;throw;}
    ledger->opened.fetch_add(1);auto count=ledger->live.fetch_add(1)+1;
    auto maximum=ledger->maximumLive.load();while(maximum<count&&!ledger->maximumLive.compare_exchange_weak(maximum,count)){}
  }
  ~Socket(){if(descriptor>=0){::close(descriptor);ledger->closed.fetch_add(1);ledger->live.fetch_sub(1);}}
  Socket(const Socket&)=delete;Socket &operator=(const Socket&)=delete;
  int get()const noexcept{return descriptor;}
};
bool validName(const std::string &name){
  return !name.empty()&&name.size()<=64&&std::all_of(name.begin(),name.end(),[](unsigned char c){return (c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')||c=='_'||c=='-'||c=='.';});
}
void checkpoint(const Exchange &work,const TaskExternalControl &control){
  control.checkpoint();work.grant->authority.check();
  if(Clock::now()>=work.deadline)throw DataError("E_TIMEOUT","TCP exchange deadline exceeded");
}
void wait(int socket,short events,const Exchange &work,const TaskExternalControl &control){
  for(;;){
    checkpoint(work,control);pollfd fd{socket,events,0};
    const auto left=std::chrono::ceil<std::chrono::milliseconds>(work.deadline-Clock::now()).count();
    const int interval=int(std::clamp<int64_t>(left,1,10));
    const auto ready=::poll(&fd,1,interval);const int error=errno;checkpoint(work,control);
    if(ready<0){if(error==EINTR)continue;networkError("socket poll",error);}
    if(fd.revents&POLLNVAL)networkError("socket poll",EBADF);
    if(ready&&(fd.revents&(events|POLLERR|POLLHUP)))return;
  }
}
class Operation final:public TaskExternalOperation {
  std::shared_ptr<const Exchange> work;
public:
  explicit Operation(std::shared_ptr<const Exchange> work):work(std::move(work)){}
  TaskExternalResult run(const TaskExternalControl &control)override{
    checkpoint(*work,control);
    TaskExternalResult result;
    try{
      const auto *address=reinterpret_cast<const sockaddr*>(&work->endpoint.address);
      Socket socket(address->sa_family,work->grant->ledger);checkpoint(*work,control);
      auto connected=::connect(socket.get(),address,work->endpoint.length);
      if(connected<0){
        int error=errno;
        if(error!=EINPROGRESS&&error!=EALREADY&&error!=EINTR&&error!=EWOULDBLOCK)networkError("socket connect",error);
        for(;;){
          wait(socket.get(),POLLOUT,*work,control);socklen_t length=sizeof(error);
          if(::getsockopt(socket.get(),SOL_SOCKET,SO_ERROR,&error,&length))networkError("socket connect status",errno);
          if(!error)break;
          if(error!=EINPROGRESS&&error!=EALREADY)networkError("socket connect",error);
        }
      }
      size_t sent=0;
      while(sent<work->input.size()){
        checkpoint(*work,control);int flags=0;
#ifdef MSG_NOSIGNAL
        flags|=MSG_NOSIGNAL;
#endif
        const auto count=::send(socket.get(),work->input.data()+sent,work->input.size()-sent,flags);
        if(count>0){sent+=size_t(count);continue;}
        const int error=count<0?errno:EPIPE;if(error==EINTR)continue;
        if(error==EAGAIN||error==EWOULDBLOCK){wait(socket.get(),POLLOUT,*work,control);continue;}
        networkError("socket send",error);
      }
      checkpoint(*work,control);
      if(::shutdown(socket.get(),SHUT_WR))networkError("socket write EOF",errno);
      result.bytes.resize(work->replyLimit);
      if(result.bytes.capacity()>work->replyLimit)throw DataError("E_LIMIT","TCP reply allocation exceeds reservation");
      size_t received=0;uint8_t excess=0;
      for(;;){
        checkpoint(*work,control);const bool full=received==work->replyLimit;
        const auto count=::recv(socket.get(),full?&excess:result.bytes.data()+received,full?1:work->replyLimit-received,0);
        if(!count){result.bytes.resize(received);break;}
        if(count>0){if(full)throw DataError("E_LIMIT","TCP reply exceeds its declared limit");received+=size_t(count);continue;}
        const int error=errno;if(error==EINTR)continue;
        if(error==EAGAIN||error==EWOULDBLOCK){wait(socket.get(),POLLIN,*work,control);continue;}
        networkError("socket receive",error);
      }
      // The local socket closes before pool publication, on every exit path.
    }catch(const DataError &error){
      if(error.code!="E_NETWORK")throw;
      std::vector<uint8_t>{}.swap(result.bytes);result.errorCode=error.code;result.errorMessage=error.what();
    }
    checkpoint(*work,control);return result;
  }
};
}
TaskNetworkGrant::TaskNetworkGrant(ResourceAccess authority,std::span<const TaskTcpEndpoint> endpoints){
  authority.check();
  if(endpoints.empty()||endpoints.size()>16)throw DataError("E_RANGE","network grant requires1..16 exact endpoints");
  auto prepared=std::make_shared<task_network_detail::Grant>();prepared->authority=std::move(authority);
  for(const auto &input:endpoints){
    if(!task_network_detail::validName(input.name)||!input.port||input.address.empty()||input.address.size()>INET6_ADDRSTRLEN||input.address.find('\0')!=std::string::npos)
      throw DataError("E_RANGE","network endpoint requires a name, numeric address and port1..65535");
    if(std::any_of(prepared->endpoints.begin(),prepared->endpoints.end(),[&](const auto &e){return e.name==input.name;}))throw DataError("E_RANGE","duplicate network endpoint name");
    task_network_detail::Endpoint endpoint;endpoint.name=input.name;
    sockaddr_in v4{};v4.sin_family=AF_INET;v4.sin_port=htons(input.port);
    sockaddr_in6 v6{};v6.sin6_family=AF_INET6;v6.sin6_port=htons(input.port);
    if(::inet_pton(AF_INET,input.address.c_str(),&v4.sin_addr)==1){std::memcpy(&endpoint.address,&v4,sizeof(v4));endpoint.length=sizeof(v4);}
    else if(::inet_pton(AF_INET6,input.address.c_str(),&v6.sin6_addr)==1){std::memcpy(&endpoint.address,&v6,sizeof(v6));endpoint.length=sizeof(v6);}
    else throw DataError("E_RANGE","network endpoint address must be an exact IPv4 or IPv6 literal");
    prepared->endpoints.push_back(std::move(endpoint));
  }
  prepared->authority.check();grant=std::move(prepared);
}
void TaskNetworkGrant::check()const{if(!grant)throw DataError("CAPABILITY","network grant is unavailable");grant->authority.check();}
TaskNetworkStats TaskNetworkGrant::stats()const noexcept{
  if(!grant)return {};const auto &l=*grant->ledger;return {l.opened.load(),l.closed.load(),l.live.load(),l.maximumLive.load()};
}
PreparedTaskTcpExchange::PreparedTaskTcpExchange(const TaskNetworkGrant &grant,const std::string &endpoint,std::span<const uint8_t> input,size_t replyLimit,unsigned timeoutMs){
  grant.check();
  if(input.size()>maximumInput||!replyLimit||replyLimit>maximumReply||!timeoutMs||timeoutMs>maximumTimeoutMs)throw DataError("E_RANGE","TCP exchange exceeds input/reply/deadline limits");
  const auto &endpoints=grant.grant->endpoints;
  auto selected=std::find_if(endpoints.begin(),endpoints.end(),[&](const auto &e){return e.name==endpoint;});
  if(selected==endpoints.end())throw DataError("CAPABILITY","network endpoint is not granted");
  auto prepared=std::make_shared<task_network_detail::Exchange>();prepared->grant=grant.grant;prepared->endpoint=*selected;
  prepared->deadline=task_network_detail::Clock::now()+std::chrono::milliseconds(timeoutMs);
  prepared->input.assign(input.begin(),input.end());prepared->replyLimit=replyLimit;
  // Include actual retained input capacity and the bounded complete grant table,
  // not just a slice length. This is a payload budget, not total process RAM.
  size_t metadata=sizeof(task_network_detail::Grant)+sizeof(task_network_detail::Ledger)+
      grant.grant->endpoints.capacity()*sizeof(task_network_detail::Endpoint);
  for(const auto &entry:grant.grant->endpoints)metadata+=entry.name.capacity();
  prepared->reservation=prepared->input.capacity()+replyLimit+sizeof(*prepared)+prepared->endpoint.name.capacity()+metadata;
  grant.check();exchange=std::move(prepared);
}
size_t PreparedTaskTcpExchange::reservation()const noexcept{return exchange->reservation;}
std::shared_ptr<TaskExternalOperation> PreparedTaskTcpExchange::operation()const{return std::make_shared<task_network_detail::Operation>(exchange);}
TaskExternalResult PreparedTaskTcpExchange::admit(TaskExternalResult result,const TaskExternalControl &control)const{
  validateTaskExternalResult(result,reservation(),exchange->replyLimit);task_network_detail::checkpoint(*exchange,control);
  if(result.bytes.size()>exchange->replyLimit||(!result.errorCode.empty()&&result.errorCode!="E_NETWORK")||(!result.errorCode.empty()&&!result.bytes.empty()))throw DataError("E_TASK_VALUE","invalid TCP exchange outcome");
  return result;
}
}
#endif
