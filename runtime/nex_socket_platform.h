#pragma once
#include "nex_error.h"
#include <algorithm>
#include <climits>
#include <cstddef>
#include <cstdint>
#ifdef _WIN32
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <winsock2.h>
#include <ws2tcpip.h>
#else
#include <arpa/inet.h>
#include <cerrno>
#include <poll.h>
#include <sys/socket.h>
#include <unistd.h>
#endif

namespace nexrt::socket_platform {
#ifdef _WIN32
using Handle=SOCKET;
using Length=int;
inline constexpr Handle invalid=INVALID_SOCKET;
inline int error()noexcept{return WSAGetLastError();}
inline bool interrupted(int code)noexcept{return code==WSAEINTR;}
inline bool blocked(int code)noexcept{return code==WSAEWOULDBLOCK;}
inline bool connecting(int code)noexcept{return blocked(code)||code==WSAEINPROGRESS||code==WSAEALREADY||interrupted(code);}
inline constexpr int brokenPipe=WSAECONNRESET;
inline constexpr int writeEOF=SD_SEND;
inline void close(Handle socket)noexcept{::closesocket(socket);}
// Keep one matched initialization in every retained grant. Exchange/operation
// ownership keeps it alive until all physical IO and its sockets have retired.
struct Library {
  Library(){
    WSADATA data{};int status=::WSAStartup(MAKEWORD(2,2),&data);
    if(status)throw DataError("E_NETWORK","Winsock initialization: "+std::to_string(status));
    if(data.wVersion!=MAKEWORD(2,2)){::WSACleanup();throw DataError("E_NETWORK","Winsock2.2 is unavailable");}
  }
  ~Library(){::WSACleanup();}
  Library(const Library&)=delete;Library&operator=(const Library&)=delete;
};
#else
using Handle=int;
using Length=socklen_t;
inline constexpr Handle invalid=-1;
inline int error()noexcept{return errno;}
inline bool interrupted(int code)noexcept{return code==EINTR;}
inline bool blocked(int code)noexcept{return code==EAGAIN||code==EWOULDBLOCK;}
inline bool connecting(int code)noexcept{return blocked(code)||code==EINPROGRESS||code==EALREADY||interrupted(code);}
inline constexpr int brokenPipe=EPIPE;
inline constexpr int writeEOF=SHUT_WR;
inline void close(Handle socket)noexcept{::close(socket);}
struct Library {};
#endif
inline int setOption(Handle socket,int level,int name,const void *value,Length length)noexcept{
#ifdef _WIN32
  return ::setsockopt(socket,level,name,static_cast<const char*>(value),length);
#else
  return ::setsockopt(socket,level,name,value,length);
#endif
}
inline int getOption(Handle socket,int level,int name,void *value,Length *length)noexcept{
#ifdef _WIN32
  return ::getsockopt(socket,level,name,static_cast<char*>(value),length);
#else
  return ::getsockopt(socket,level,name,value,length);
#endif
}
inline int parseAddress(int family,const char *text,void *address)noexcept{
#ifdef _WIN32
  return ::InetPtonA(family,text,address);
#else
  return ::inet_pton(family,text,address);
#endif
}
inline auto send(Handle socket,const uint8_t *data,size_t size,int flags)noexcept{
#ifdef _WIN32
  return ::send(socket,reinterpret_cast<const char*>(data),int(std::min<size_t>(size,INT_MAX)),flags);
#else
  return ::send(socket,data,size,flags);
#endif
}
inline auto receive(Handle socket,uint8_t *data,size_t size,int flags)noexcept{
#ifdef _WIN32
  return ::recv(socket,reinterpret_cast<char*>(data),int(std::min<size_t>(size,INT_MAX)),flags);
#else
  return ::recv(socket,data,size,flags);
#endif
}
struct Wait {int ready=0,error=0;};
inline Wait wait(Handle socket,bool writing,int milliseconds)noexcept{
#ifdef _WIN32
  fd_set interested,failed;FD_ZERO(&interested);FD_ZERO(&failed);
  FD_SET(socket,&interested);FD_SET(socket,&failed);
  timeval timeout{milliseconds/1000,(milliseconds%1000)*1000};
  // A failed nonblocking connect is reported in exceptfds on Winsock.
  int ready=::select(0,writing?nullptr:&interested,writing?&interested:nullptr,&failed,&timeout);
  return {ready,ready==SOCKET_ERROR?error():0};
#else
  pollfd descriptor{socket,short(writing?POLLOUT:POLLIN),0};
  int ready=::poll(&descriptor,1,milliseconds);int code=ready<0?error():0;
  if(descriptor.revents&POLLNVAL)return {-1,EBADF};
  return {ready,code};
#endif
}
}
