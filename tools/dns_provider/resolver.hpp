#pragma once
#include "nex_error.h"
#include <ares.h>
#include <arpa/inet.h>
#include <poll.h>
#include <algorithm>
#include <array>
#include <atomic>
#include <cerrno>
#include <chrono>
#include <functional>
#include <memory>
#include <string>
#include <vector>

namespace nex_dns {
struct Library {
  Library(){if(ares_library_init(ARES_LIB_INIT_ALL)!=ARES_SUCCESS)throw std::bad_alloc();}
  ~Library(){ares_library_cleanup();}
};
struct Socket {ares_socket_t fd=ARES_SOCKET_BAD;short events=0;};
struct Frame {
  std::array<Socket,16> sockets{};
  bool overflow=false,done=false;
  int status=ARES_ECANCELLED;
  ares_addrinfo *answer=nullptr;
  ~Frame(){if(answer)ares_freeaddrinfo(answer);}
};
void socketState(void *data,ares_socket_t fd,int readable,int writable)noexcept{
  auto &frame=*static_cast<Frame*>(data);Socket *slot=nullptr;
  for(auto &s:frame.sockets)if(s.fd==fd){slot=&s;break;}
  if(!readable&&!writable){if(slot)*slot=Socket{};return;}
  if(!slot)for(auto &s:frame.sockets)if(s.fd==ARES_SOCKET_BAD){slot=&s;break;}
  if(!slot){frame.overflow=true;return;}
  slot->fd=fd;slot->events=short((readable?POLLIN:0)|(writable?POLLOUT:0));
}
void answered(void *data,int status,int,ares_addrinfo *answer)noexcept{
  auto &frame=*static_cast<Frame*>(data);frame.status=status;frame.answer=answer;frame.done=true;
}
template<class Owner> struct Channel {
  ares_channel_t *value=nullptr;
  Owner &owner;
  explicit Channel(Owner &owner):owner(owner){}
  void opened(){owner.opened.fetch_add(1);auto live=owner.live.fetch_add(1)+1,maximum=owner.maximumLive.load();while(live>maximum&&!owner.maximumLive.compare_exchange_weak(maximum,live)){};}
  ~Channel(){if(value){ares_destroy(value);owner.closed.fetch_add(1);owner.live.fetch_sub(1);}}
};
std::string hostname(std::string value){
  if(!value.empty()&&value.back()=='.')value.pop_back();
  if(value.empty()||value.size()>253)throw nexrt::DataError("VALIDATION","invalid DNS hostname length");
  size_t label=0;char previous=0;
  for(char &c:value){
    if(c>='A'&&c<='Z')c=char(c-'A'+'a');
    if(c=='.'){if(!label||previous=='-')throw nexrt::DataError("VALIDATION","invalid DNS label");label=0;}
    else{if(!((c>='a'&&c<='z')||(c>='0'&&c<='9')||c=='-')||(!label&&c=='-')||++label>63)throw nexrt::DataError("VALIDATION","DNS names require valid ASCII or IDNA A-labels");}
    previous=c;
  }
  if(!label||previous=='-')throw nexrt::DataError("VALIDATION","invalid final DNS label");
  return value;
}
template<class Owner> std::vector<std::string> lookup(Owner &owner,const std::string &name,size_t limit,unsigned timeout,const char *servers,const std::function<void()> &pollParent){
  using Clock=std::chrono::steady_clock;
  auto deadline=Clock::now()+std::chrono::milliseconds(timeout);pollParent();
  Frame frame;Channel channel(owner);ares_options options{};char lookups[]="b",resolvconf[]="/dev/null";
  options.flags=ARES_FLAG_NOSEARCH|ARES_FLAG_NOALIASES;options.lookups=lookups;options.resolvconf_path=resolvconf;
  options.timeout=int(timeout);options.tries=1;options.qcache_max_ttl=0;options.sock_state_cb=socketState;options.sock_state_cb_data=&frame;
  auto status=ares_init_options(&channel.value,&options,ARES_OPT_FLAGS|ARES_OPT_LOOKUPS|ARES_OPT_RESOLVCONF|ARES_OPT_TIMEOUTMS|ARES_OPT_TRIES|ARES_OPT_QUERY_CACHE|ARES_OPT_SOCK_STATE_CB);
  if(status!=ARES_SUCCESS){channel.value=nullptr;if(status==ARES_ENOMEM)throw std::bad_alloc();throw nexrt::DataError("E_DNS","DNS channel initialization failed");}
  channel.opened();status=ares_set_servers_csv(channel.value,servers);
  if(status!=ARES_SUCCESS){if(status==ARES_ENOMEM)throw std::bad_alloc();throw nexrt::DataError("E_DNS","compiled DNS server policy is invalid");}
  ares_addrinfo_hints hints{};hints.ai_family=AF_UNSPEC;hints.ai_socktype=SOCK_STREAM;hints.ai_flags=ARES_AI_NOSORT;
  auto absolute=name+".";ares_getaddrinfo(channel.value,absolute.c_str(),nullptr,&hints,answered,&frame);
  while(!frame.done){
    pollParent();
    if(Clock::now()>=deadline)throw nexrt::DataError("E_DNS_TIMEOUT","DNS lookup deadline expired");
    if(frame.overflow)throw nexrt::DataError("E_DNS_LIMIT","DNS socket event inventory is full");
    std::array<pollfd,16> descriptors{};size_t count=0;
    for(const auto &s:frame.sockets)if(s.fd!=ARES_SOCKET_BAD)descriptors[count++]={s.fd,s.events,0};
    auto remaining=std::chrono::duration_cast<std::chrono::milliseconds>(deadline-Clock::now()).count();
    int wait=int(std::min<int64_t>(20,std::max<int64_t>(0,remaining)));
    int ready=::poll(descriptors.data(),nfds_t(count),wait);
    if(ready<0){if(errno==EINTR)continue;throw nexrt::DataError("E_DNS","DNS socket polling failed");}
    pollParent();std::array<ares_fd_events_t,16> events{};size_t active=0;
    for(size_t i=0;i<count;++i)if(descriptors[i].revents){
      unsigned flags=0;auto observed=descriptors[i].revents;
      if(observed&(POLLIN|POLLERR|POLLHUP|POLLNVAL))flags|=ARES_FD_EVENT_READ;
      if(observed&POLLOUT)flags|=ARES_FD_EVENT_WRITE;
      events[active++]={descriptors[i].fd,flags};
    }
    status=ares_process_fds(channel.value,events.data(),active,ARES_PROCESS_FLAG_NONE);
    if(status==ARES_ENOMEM)throw std::bad_alloc();
    if(status!=ARES_SUCCESS)throw nexrt::DataError("E_DNS","DNS event processing failed");
  }
  pollParent();
  if(Clock::now()>=deadline)throw nexrt::DataError("E_DNS_TIMEOUT","DNS lookup deadline expired");
  if(frame.status==ARES_ENOMEM)throw std::bad_alloc();
  if(frame.status==ARES_ETIMEOUT)throw nexrt::DataError("E_DNS_TIMEOUT","DNS server timed out");
  if(frame.status!=ARES_SUCCESS)throw nexrt::DataError("E_DNS",ares_strerror(frame.status));
  std::vector<std::string> result;size_t visited=0;
  if(frame.answer)for(auto *node=frame.answer->nodes;node;node=node->ai_next){
    if(++visited>512)throw nexrt::DataError("E_DNS_LIMIT","DNS address inventory exceeds512 records");
    if(!node->ai_addr)throw nexrt::DataError("E_DNS","resolver returned a missing IP address");
    char address[INET6_ADDRSTRLEN]{};const void *raw=nullptr;
    if(node->ai_family==AF_INET&&node->ai_addrlen>=sizeof(sockaddr_in))raw=&reinterpret_cast<const sockaddr_in*>(node->ai_addr)->sin_addr;
    else if(node->ai_family==AF_INET6&&node->ai_addrlen>=sizeof(sockaddr_in6))raw=&reinterpret_cast<const sockaddr_in6*>(node->ai_addr)->sin6_addr;
    if(!raw||!inet_ntop(node->ai_family,raw,address,sizeof(address)))throw nexrt::DataError("E_DNS","resolver returned an invalid IP address");
    if(std::find(result.begin(),result.end(),address)==result.end()){
      if(result.size()==limit)throw nexrt::DataError("E_DNS_LIMIT","DNS answer count exceeds the declared limit");
      result.emplace_back(address);
    }
  }
  if(result.empty())throw nexrt::DataError("E_DNS","DNS lookup returned no addresses");
  std::sort(result.begin(),result.end());pollParent();return result;
}
}
