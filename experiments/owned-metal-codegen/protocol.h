#pragma once
#include <cerrno>
#include <cstdint>
#include <cstring>
#include <functional>
#include <stdexcept>
#include <string>
#include <vector>
#include <sys/socket.h>
#include <unistd.h>

namespace owned_metal_map {
constexpr uint32_t magic=0x3143474e,version=1,maximum=1048576+128,maximumElements=262144;
enum Operation:uint32_t {Open=1,Upload=2,Generated=3,Download=4,Free=5,Close=6};
enum Status:uint32_t {Success=0,Failure=1,Unsettled=2,Progress=3};
struct Error:std::runtime_error {
 std::string code;
 Error(std::string code,std::string message):std::runtime_error(std::move(message)),code(std::move(code)){}
};
using Bytes=std::vector<uint8_t>;
struct Data {
 Bytes bytes;size_t offset=0;
 Data()=default;explicit Data(Bytes data):bytes(std::move(data)){}
 void u32(uint32_t n){for(unsigned i=0;i<4;++i)bytes.push_back(uint8_t(n>>(8*i)));}
 void u64(uint64_t n){for(unsigned i=0;i<8;++i)bytes.push_back(uint8_t(n>>(8*i)));}
 void blob(const Bytes &value){if(value.size()>maximum)throw Error("E_DEVICE_PROTOCOL","payload too large");u32(uint32_t(value.size()));bytes.insert(bytes.end(),value.begin(),value.end());}
 void text(const std::string &value){blob(Bytes(value.begin(),value.end()));}
 uint32_t get32(){if(bytes.size()-offset<4)throw Error("E_DEVICE_PROTOCOL","truncated u32");uint32_t n=0;for(unsigned i=0;i<4;++i)n|=uint32_t(bytes[offset++])<<(8*i);return n;}
 uint64_t get64(){if(bytes.size()-offset<8)throw Error("E_DEVICE_PROTOCOL","truncated u64");uint64_t n=0;for(unsigned i=0;i<8;++i)n|=uint64_t(bytes[offset++])<<(8*i);return n;}
 Bytes getBlob(){auto n=get32();if(n>maximum||bytes.size()-offset<n)throw Error("E_DEVICE_PROTOCOL","invalid byte payload");Bytes result(bytes.begin()+offset,bytes.begin()+offset+n);offset+=n;return result;}
 std::string getText(){auto value=getBlob();return {value.begin(),value.end()};}
 void done()const{if(offset!=bytes.size())throw Error("E_DEVICE_PROTOCOL","trailing payload data");}
};
struct Frame {uint64_t sequence;uint32_t operation,status;Bytes payload;};
using Poll=std::function<void()>;
inline bool readExact(int fd,void *buffer,size_t size,const Poll &poll={}){
 auto *p=static_cast<uint8_t*>(buffer);bool first=true;
 while(size){
  if(poll)poll();auto n=::recv(fd,p,size,0);
  if(n<0&&errno==EINTR)continue;
  if(n==0&&first)return false;
  if(n<=0)throw Error("E_DEVICE_PROTOCOL","worker stream ended before physical acknowledgement");
  first=false;p+=n;size-=size_t(n);
 }
 return true;
}
inline void writeExact(int fd,const void *buffer,size_t size,const Poll &poll={}){
 auto *p=static_cast<const uint8_t*>(buffer);
 while(size){
  if(poll)poll();
#ifdef MSG_NOSIGNAL
  auto n=::send(fd,p,size,MSG_NOSIGNAL);
#else
  auto n=::send(fd,p,size,0);
#endif
  if(n<0&&errno==EINTR)continue;
  if(n<=0)throw Error("E_DEVICE_PROTOCOL","worker stream write failed");p+=n;size-=size_t(n);
 }
}
inline void send(int fd,const Frame &f,const Poll &poll={}){
 if(f.payload.size()>maximum)throw Error("E_DEVICE_PROTOCOL","frame exceeds bounded transport");
 Data h;h.u32(magic);h.u32(version);h.u64(f.sequence);h.u32(f.operation);h.u32(f.status);h.u32(uint32_t(f.payload.size()));
 writeExact(fd,h.bytes.data(),h.bytes.size(),poll);if(!f.payload.empty())writeExact(fd,f.payload.data(),f.payload.size(),poll);
}
inline bool receive(int fd,Frame &f,const Poll &poll={}){
 Bytes header(28);if(!readExact(fd,header.data(),header.size(),poll))return false;Data h(std::move(header));
 if(h.get32()!=magic||h.get32()!=version)throw Error("E_DEVICE_PROTOCOL","invalid worker protocol identity");
 f.sequence=h.get64();f.operation=h.get32();f.status=h.get32();auto size=h.get32();h.done();
 if(size>maximum||f.status>Progress)throw Error("E_DEVICE_PROTOCOL","invalid bounded frame size or status");
 f.payload.resize(size);if(size&&!readExact(fd,f.payload.data(),size,poll))throw Error("E_DEVICE_PROTOCOL","missing frame payload");return true;
}
inline Bytes failure(const Error &e){Data d;d.text(e.code.substr(0,128));auto message=std::string(e.what()).substr(0,2048);for(char &c:message)if(uint8_t(c)<32||uint8_t(c)>126)c='?';d.text(message);return std::move(d.bytes);}
}
