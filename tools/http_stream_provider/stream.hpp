#pragma once
#include "transport.hpp"
#include <mutex>
#include <thread>

namespace nex_http_stream {
using namespace nex_http;
struct Chunk {std::vector<uint8_t> bytes;bool done=false;};
class Stream {
 Context &owner;const Config &config;Request request;const int64_t totalLimit;
 Clock::time_point deadline;std::unique_ptr<URL> url;std::vector<std::string> addresses;
 std::unique_ptr<Transfer> transfer;std::vector<uint8_t> pending;size_t offset=0;int64_t received=0;
 bool paused=false,complete=false,headersReady=false;long currentStatus=0;std::mutex mutex;
 static size_t write(char *data,size_t size,size_t count,void *opaque)noexcept{
  auto &s=*static_cast<Stream*>(opaque);auto &frame=s.transfer->frame;
  if(size&&count>SIZE_MAX/size){frame.failure=Failure::Limit;return 0;}auto length=size*count;
  if(!length)return 0;
  if(!s.pending.empty()){s.paused=true;return CURL_WRITEFUNC_PAUSE;}
  if(length>CURL_MAX_WRITE_SIZE||length>uint64_t(s.totalLimit-s.received)){frame.failure=Failure::Limit;return 0;}
  try{s.pending.assign(reinterpret_cast<uint8_t*>(data),reinterpret_cast<uint8_t*>(data)+length);s.offset=0;s.received+=int64_t(length);return length;}
  catch(const std::bad_alloc&){frame.failure=Failure::Memory;}catch(...){frame.failure=Failure::Protocol;}return 0;
 }
 static size_t header(char *data,size_t size,size_t count,void *opaque)noexcept{
  auto &s=*static_cast<Stream*>(opaque);auto accepted=nex_http::headers(data,size,count,&s.transfer->frame);if(size&&count>SIZE_MAX/size)return 0;auto length=size*count;if(accepted!=length)return accepted;
  std::string_view text(data,length);
  if(text.starts_with("HTTP/")){
   auto space=text.find(' ');s.currentStatus=0;s.headersReady=false;
   if(space!=std::string_view::npos&&space+4<=text.size()){auto first=text.data()+space+1;auto parsed=std::from_chars(first,first+3,s.currentStatus);if(parsed.ec!=std::errc{})s.currentStatus=0;}
  }else if(text=="\r\n"&&s.currentStatus>=200)s.headersReady=true;
  return accepted;
 }
 void check(const std::function<void()> &poll){poll();if(Clock::now()>=deadline)throw nexrt::DataError("E_HTTP_TIMEOUT","HTTP stream deadline expired");}
 void failure(){
  auto value=transfer->frame.failure;
  if(value==Failure::Memory)throw std::bad_alloc();
  if(value==Failure::Limit)throw nexrt::DataError("E_HTTP_LIMIT","HTTP stream response bound exceeded");
  if(value!=Failure::None)throw nexrt::DataError("E_HTTP","HTTP stream transfer failed");
 }
 void advance(const std::function<void()> &poll){
  check(poll);int running=0;auto status=curl_multi_perform(transfer->multi,&running);
  if(status!=CURLM_OK)throw nexrt::DataError("E_HTTP","HTTP stream event processing failed");failure();check(poll);
  if(!running){
   int count=0;auto *message=curl_multi_info_read(transfer->multi,&count);
   if(!message||message->msg!=CURLMSG_DONE)throw nexrt::DataError("E_HTTP","HTTP stream completion is missing");auto code=message->data.result;
   if(code==CURLE_OUT_OF_MEMORY)throw std::bad_alloc();if(code==CURLE_FILESIZE_EXCEEDED)throw nexrt::DataError("E_HTTP_LIMIT","HTTP stream exceeds its total limit");
   if(code==CURLE_PEER_FAILED_VERIFICATION||code==CURLE_SSL_CONNECT_ERROR||code==CURLE_SSL_CACERT_BADFILE||code==CURLE_SSL_CERTPROBLEM||code==CURLE_SSL_ISSUER_ERROR)throw nexrt::DataError("E_TLS",curl_easy_strerror(code));
   if(code!=CURLE_OK)throw nexrt::DataError("E_HTTP",curl_easy_strerror(code));complete=true;
  }
 }
 void wait(const std::function<void()> &poll){
  check(poll);auto remaining=std::chrono::duration_cast<std::chrono::milliseconds>(deadline-Clock::now()).count();
  if(curl_multi_poll(transfer->multi,nullptr,0,int(std::max<int64_t>(0,std::min<int64_t>(20,remaining))),nullptr)!=CURLM_OK)throw nexrt::DataError("E_HTTP","HTTP stream socket polling failed");
 }
 void start(const std::function<void()> &poll){
  check(poll);addresses.clear();
  if(url->numeric)addresses.push_back(url->host);
  else{auto remaining=std::chrono::duration_cast<std::chrono::milliseconds>(deadline-Clock::now()).count();try{addresses=nex_dns::lookup(owner,url->host,64,unsigned(std::max<int64_t>(1,remaining)),config.servers.c_str(),poll);}catch(const nexrt::DataError &error){if(error.code=="E_DNS_TIMEOUT")throw nexrt::DataError("E_HTTP_TIMEOUT","HTTP stream deadline expired during DNS");throw;}}
  transfer=std::make_unique<Transfer>(owner,0,url->port,addresses);configure(*transfer,config,request,*url,addresses,totalLimit);
  checked(curl_easy_setopt(transfer->easy,CURLOPT_WRITEFUNCTION,write));checked(curl_easy_setopt(transfer->easy,CURLOPT_WRITEDATA,this));
  checked(curl_easy_setopt(transfer->easy,CURLOPT_HEADERFUNCTION,header));checked(curl_easy_setopt(transfer->easy,CURLOPT_HEADERDATA,this));
  checked(curl_easy_setopt(transfer->easy,CURLOPT_BUFFERSIZE,long(CURL_MAX_WRITE_SIZE)));
  while(!headersReady&&!complete){advance(poll);if(!headersReady&&!complete)wait(poll);}
  if(!headersReady)throw nexrt::DataError("E_HTTP","HTTP response headers are missing");
  long status=0,version=0;checked(curl_easy_getinfo(transfer->easy,CURLINFO_RESPONSE_CODE,&status));checked(curl_easy_getinfo(transfer->easy,CURLINFO_HTTP_VERSION,&version));metadata.status=status;
  metadata.headers=transfer->frame.response.headers;metadata.protocol=version==CURL_HTTP_VERSION_2_0?"2":version==CURL_HTTP_VERSION_1_1?"1.1":version==CURL_HTTP_VERSION_1_0?"1.0":"unknown";metadata.url=url->text;
 }
 void releaseTransfer()noexcept{transfer.reset();pending.clear();offset=0;paused=false;}
public:
 Response metadata;
 Stream(Context &owner,const Config &config,Request value,int64_t totalLimit,const std::function<void()> &poll):owner(owner),config(config),request(std::move(value)),totalLimit(totalLimit),deadline(Clock::now()){
  validate(request);if(totalLimit<1||totalLimit>1073741824)throw nexrt::DataError("VALIDATION","HTTP stream total limit must be1..1073741824 bytes");deadline=Clock::now()+std::chrono::milliseconds(request.timeout);url=std::make_unique<URL>(request.url);
  for(int64_t redirect=0;;++redirect){
   const auto &rule=authorize(config,request,*url);start(poll);
   bool changed=metadata.status==301||metadata.status==302||metadata.status==303||metadata.status==307||metadata.status==308;const Header *location=nullptr;
   for(const auto &item:metadata.headers)if(item.name=="location"){if(location)throw nexrt::DataError("E_HTTP","multiple redirect locations");location=&item;}
   if(!changed||!location||request.redirectLimit==0)break;
   if(redirect==request.redirectLimit)throw nexrt::DataError("E_HTTP_REDIRECT","HTTP redirect bound exceeded");
   std::string target(location->value.begin(),location->value.end());for(unsigned char ch:target)if(ch<33||ch>126)throw nexrt::DataError("E_HTTP","redirect URL requires ASCII");auto next=std::make_unique<URL>(target,url.get());
   if(url->scheme=="https"&&next->scheme!="https")throw nexrt::DataError("CAPABILITY","HTTPS redirect downgrade is unavailable");auto cross=!url->sameOrigin(*next);if(cross&&!rule.crossOriginRedirects)throw nexrt::DataError("CAPABILITY","cross-origin redirect is outside policy");
   if(cross)request.headers.erase(std::remove_if(request.headers.begin(),request.headers.end(),[](const auto &h){return sensitive(h.name);}),request.headers.end());
   if((metadata.status==303&&request.method!="HEAD")||((metadata.status==301||metadata.status==302)&&request.method=="POST")){request.method="GET";request.body.clear();request.headers.erase(std::remove_if(request.headers.begin(),request.headers.end(),[](const auto &h){auto name=lower(h.name);return name=="content-type"||name=="content-encoding";}),request.headers.end());}
   authorize(config,request,*next);releaseTransfer();complete=false;headersReady=false;currentStatus=0;received=0;url=std::move(next);
  }
 }
 ~Stream()noexcept{releaseTransfer();}
 size_t retainedBytes()const noexcept{auto size=request.body.size()+request.url.size()+request.authority.size()+request.method.size()+65536+8192+CURL_MAX_WRITE_SIZE+sizeof(Stream);for(const auto &h:request.headers)size+=h.name.size()+h.value.size()+sizeof(Header);return size;}
 Chunk read(size_t maximum,const std::function<void()> &poll){
  if(maximum<1||maximum>65536)throw nexrt::DataError("VALIDATION","HTTP stream read size must be1..65536 bytes");std::unique_lock lock(mutex,std::defer_lock);
  while(!lock.try_lock()){poll();std::this_thread::sleep_for(std::chrono::milliseconds(1));}
  try{
   poll();if(!transfer){if(complete)return {{},true};throw nexrt::DataError("E_HTTP_STREAM_CLOSED","HTTP stream is closed");}check(poll);
   while(pending.empty()&&!complete){
    if(paused){paused=false;checked(curl_easy_pause(transfer->easy,CURLPAUSE_CONT));failure();}
    if(pending.empty()&&!complete){advance(poll);if(pending.empty()&&!complete)wait(poll);}
   }
   auto available=pending.size()-offset;auto count=std::min(maximum,available);Chunk result;result.bytes.assign(pending.begin()+offset,pending.begin()+offset+count);offset+=count;
   if(offset==pending.size()){pending.clear();offset=0;}result.done=complete&&pending.empty();if(result.done)releaseTransfer();check(poll);return result;
  }catch(...){releaseTransfer();complete=false;throw;}
 }
 void close()noexcept{releaseTransfer();complete=false;}
};
}
