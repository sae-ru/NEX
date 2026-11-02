#pragma once
#include "resolver.hpp"
#include <curl/curl.h>
#include <openssl/ssl.h>
#include <charconv>
#ifndef _WIN32
#include <fcntl.h>
#include <unistd.h>
#endif

namespace nex_http {
using Clock=std::chrono::steady_clock;
struct Header {std::string name;std::vector<uint8_t> value;};
struct Request {
 std::string authority,method,url;std::vector<Header> headers;std::vector<uint8_t> body;
 int64_t replyLimit=262144,timeout=1000,redirectLimit=0;std::string protocol="auto";
};
struct Response {int64_t status=0;std::vector<Header> headers;std::vector<uint8_t> body;std::string protocol,url;};
struct Rule {std::string name,domain;bool subdomains=false;std::vector<std::string> schemes,methods;std::vector<unsigned> ports;bool crossOriginRedirects=false;};
struct Config {std::string servers,ca;std::vector<Rule> rules;};
struct CurlLibrary {
 CurlLibrary(){if(curl_global_init(CURL_GLOBAL_DEFAULT)!=CURLE_OK)throw std::bad_alloc();auto *v=curl_version_info(CURLVERSION_NOW);if(!v||v->version_num!=0x081700||!(v->features&CURL_VERSION_HTTP2)||!v->ssl_version||!std::string_view(v->ssl_version).starts_with("OpenSSL/")){curl_global_cleanup();throw nexrt::DataError("E_HTTP","HTTP dependency does not match the pinned curl/OpenSSL/HTTP2 build");}}
 ~CurlLibrary(){curl_global_cleanup();}
};
struct Context {
 nex_dns::Library dns;CurlLibrary curl;
 std::atomic<size_t> opened{0},closed{0},live{0},maximumLive{0};
 std::atomic<size_t> socketsOpened{0},socketsClosed{0},socketsLive{0},maximumSocketsLive{0};
};
inline std::string lower(std::string text){for(auto &c:text)if(c>='A'&&c<='Z')c=char(c-'A'+'a');return text;}
inline bool token(unsigned char c){return (c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')||std::string_view("!#$%&'*+-.^_`|~").find(char(c))!=std::string_view::npos;}
inline bool sensitive(std::string_view name){auto s=lower(std::string(name));return s=="authorization"||s=="cookie"||s=="origin"||s=="referer";}
inline void validate(const Request &r){
 if(r.authority.empty()||r.authority.size()>64||r.method.empty()||r.method.size()>32||r.url.size()<8||r.url.size()>8192)throw nexrt::DataError("VALIDATION","invalid HTTP authority, method or URL length");
 for(unsigned char c:r.method)if(!token(c))throw nexrt::DataError("VALIDATION","invalid HTTP method");
 if(lower(r.method)=="connect")throw nexrt::DataError("VALIDATION","CONNECT tunneling is not a request operation");
 for(unsigned char c:r.url)if(c<33||c>126)throw nexrt::DataError("VALIDATION","HTTP URLs require percent-encoded ASCII");
 if(r.replyLimit<1||r.replyLimit>524288||r.body.size()>524288||r.timeout<1||r.timeout>30000||r.redirectLimit<0||r.redirectLimit>8||(r.protocol!="auto"&&r.protocol!="1.1"&&r.protocol!="2")||r.headers.size()>64)throw nexrt::DataError("VALIDATION","invalid HTTP bounds or protocol");
 if(r.method=="HEAD"&&!r.body.empty())throw nexrt::DataError("VALIDATION","HEAD requires an empty body");
 size_t total=0;for(const auto &h:r.headers){
  if(h.name.empty()||h.name.size()>128||h.value.size()>8192)throw nexrt::DataError("VALIDATION","HTTP header exceeds field limit");
  for(unsigned char c:h.name)if(!token(c))throw nexrt::DataError("VALIDATION","invalid HTTP header name");
  auto name=lower(h.name);for(auto blocked:{"host","connection","proxy-connection","proxy-authorization","content-length","transfer-encoding","upgrade","te","trailer","expect"})if(name==blocked)throw nexrt::DataError("VALIDATION","transport-owned HTTP header");
  for(auto c:h.value)if((c<32&&c!=9)||c==127)throw nexrt::DataError("VALIDATION","control byte in HTTP header");
  total+=h.name.size()+h.value.size()+4;if(total>65536)throw nexrt::DataError("VALIDATION","request headers exceed64KiB");
 }
 if(r.body.size()+size_t(r.replyLimit)+r.url.size()+r.authority.size()+r.method.size()+total+65536+8192>1044480)throw nexrt::DataError("VALIDATION","HTTP copied request/reply budget exceeds1020KiB");
}
struct URL {
 CURLU *handle=nullptr;std::string text,scheme,host;unsigned port=0;bool numeric=false;
 static std::string get(CURLU *h,CURLUPart part,unsigned flags=0,bool optional=false){char *value=nullptr;auto status=curl_url_get(h,part,&value,flags);if(status==CURLUE_OUT_OF_MEMORY)throw std::bad_alloc();if(status!=CURLUE_OK){if(optional)return {};throw nexrt::DataError("VALIDATION","HTTP URL component is missing or malformed");}std::unique_ptr<char,decltype(&curl_free)> owned(value,curl_free);return std::string(value);}
 explicit URL(const std::string &input,const URL *base=nullptr){
  handle=base?curl_url_dup(base->handle):curl_url();if(!handle)throw std::bad_alloc();
  try{
   auto status=curl_url_set(handle,CURLUPART_URL,input.c_str(),CURLU_DISALLOW_USER);if(status==CURLUE_OUT_OF_MEMORY)throw std::bad_alloc();if(status!=CURLUE_OK)throw nexrt::DataError("VALIDATION","invalid HTTP URL");
   scheme=lower(get(handle,CURLUPART_SCHEME));if(scheme!="http"&&scheme!="https")throw nexrt::DataError("CAPABILITY","only HTTP and HTTPS URLs are permitted");
   if(!get(handle,CURLUPART_ZONEID,0,true).empty())throw nexrt::DataError("VALIDATION","scoped IPv6 HTTP URLs are unavailable");
   host=lower(get(handle,CURLUPART_HOST));if(host.size()>1&&host.front()=='['&&host.back()==']')host=host.substr(1,host.size()-2);
   in_addr v4{};in6_addr v6{};char address[INET6_ADDRSTRLEN]{};
   if(nexrt::socket_platform::parseAddress(AF_INET,host.c_str(),&v4)==1){if(v4.s_addr==0||((ntohl(v4.s_addr)&0xf0000000U)==0xe0000000U)||v4.s_addr==INADDR_BROADCAST)throw nexrt::DataError("VALIDATION","invalid HTTP target address");if(!ares_inet_ntop(AF_INET,&v4,address,sizeof(address)))throw nexrt::DataError("VALIDATION","invalid IPv4 address");host=address;numeric=true;}
   else if(nexrt::socket_platform::parseAddress(AF_INET6,host.c_str(),&v6)==1){if(IN6_IS_ADDR_UNSPECIFIED(&v6)||IN6_IS_ADDR_MULTICAST(&v6))throw nexrt::DataError("VALIDATION","invalid HTTP target address");if(!ares_inet_ntop(AF_INET6,&v6,address,sizeof(address)))throw nexrt::DataError("VALIDATION","invalid IPv6 address");host=address;numeric=true;}
   else host=nex_dns::hostname(host);
   auto hostname=numeric&&host.find(':')!=std::string::npos?"["+host+"]":host;
   if(curl_url_set(handle,CURLUPART_SCHEME,scheme.c_str(),0)!=CURLUE_OK||curl_url_set(handle,CURLUPART_HOST,hostname.c_str(),0)!=CURLUE_OK||curl_url_set(handle,CURLUPART_FRAGMENT,nullptr,0)!=CURLUE_OK)throw nexrt::DataError("VALIDATION","URL canonicalization failed");
   auto value=get(handle,CURLUPART_PORT,CURLU_DEFAULT_PORT);auto parsed=std::from_chars(value.data(),value.data()+value.size(),port);if(parsed.ec!=std::errc{}||parsed.ptr!=value.data()+value.size()||port<1||port>65535)throw nexrt::DataError("VALIDATION","invalid HTTP port");
   text=get(handle,CURLUPART_URL);if(text.size()>8192)throw nexrt::DataError("VALIDATION","canonical HTTP URL exceeds8192 bytes");
  }catch(...){curl_url_cleanup(handle);handle=nullptr;throw;}
 }
 ~URL(){if(handle)curl_url_cleanup(handle);}
 URL(const URL&)=delete;URL &operator=(const URL&)=delete;
 bool sameOrigin(const URL &other)const{return scheme==other.scheme&&host==other.host&&port==other.port;}
};
inline const Rule &authorize(const Config &config,const Request &request,const URL &url){
 for(const auto &rule:config.rules)if(rule.name==request.authority){
  bool domain=rule.domain=="*"||rule.domain==url.host||(rule.subdomains&&!url.numeric&&url.host.size()>rule.domain.size()+1&&url.host.ends_with("."+rule.domain));
  if(domain&&std::find(rule.schemes.begin(),rule.schemes.end(),url.scheme)!=rule.schemes.end()&&std::find(rule.ports.begin(),rule.ports.end(),url.port)!=rule.ports.end()&&std::find(rule.methods.begin(),rule.methods.end(),request.method)!=rule.methods.end())return rule;
  throw nexrt::DataError("CAPABILITY","HTTP URL or method is outside the selected authority");
 }
 throw nexrt::DataError("CAPABILITY","HTTP authority is unavailable");
}
enum class Failure {None,Limit,Memory,Protocol,Address,DNS};
struct Frame {
 Context &owner;Response response;size_t replyLimit,headerBytes=0;unsigned port;
 const std::vector<std::string> &addresses;std::array<curl_socket_t,16> sockets;Failure failure=Failure::None;
 Frame(Context &owner,size_t limit,unsigned port,const std::vector<std::string> &addresses):owner(owner),replyLimit(limit),port(port),addresses(addresses){sockets.fill(CURL_SOCKET_BAD);}
 void close(curl_socket_t fd)noexcept{for(auto &value:sockets)if(value==fd){value=CURL_SOCKET_BAD;nexrt::socket_platform::close(fd);owner.socketsClosed.fetch_add(1);owner.socketsLive.fetch_sub(1);return;}failure=Failure::Protocol;}
 ~Frame(){for(auto fd:sockets)if(fd!=CURL_SOCKET_BAD)close(fd);}
};
inline curl_socket_t openSocket(void *opaque,curlsocktype purpose,struct curl_sockaddr *address)noexcept{
 auto &f=*static_cast<Frame*>(opaque);int socketType=address->socktype;
#ifdef SOCK_CLOEXEC
 socketType&=~SOCK_CLOEXEC;
#endif
 if(purpose!=CURLSOCKTYPE_IPCXN||socketType!=SOCK_STREAM){f.failure=Failure::Address;return CURL_SOCKET_BAD;}
 char text[INET6_ADDRSTRLEN]{};unsigned port=0;const void *raw=nullptr;
 if(address->family==AF_INET&&address->addrlen>=sizeof(sockaddr_in)){auto &a=*reinterpret_cast<const sockaddr_in*>(&address->addr);raw=&a.sin_addr;port=ntohs(a.sin_port);}
 else if(address->family==AF_INET6&&address->addrlen>=sizeof(sockaddr_in6)){auto &a=*reinterpret_cast<const sockaddr_in6*>(&address->addr);if(a.sin6_scope_id){f.failure=Failure::Address;return CURL_SOCKET_BAD;}raw=&a.sin6_addr;port=ntohs(a.sin6_port);}
 if(!raw||port!=f.port||!ares_inet_ntop(address->family,raw,text,sizeof(text))||std::find(f.addresses.begin(),f.addresses.end(),text)==f.addresses.end()){f.failure=Failure::Address;return CURL_SOCKET_BAD;}
 auto slot=std::find(f.sockets.begin(),f.sockets.end(),CURL_SOCKET_BAD);if(slot==f.sockets.end()){f.failure=Failure::Limit;return CURL_SOCKET_BAD;}
#ifdef _WIN32
 auto fd=::WSASocketW(address->family,address->socktype,address->protocol,nullptr,0,WSA_FLAG_OVERLAPPED|WSA_FLAG_NO_HANDLE_INHERIT);if(fd==INVALID_SOCKET)return CURL_SOCKET_BAD;
#else
 auto fd=::socket(address->family,address->socktype,address->protocol);if(fd<0)return CURL_SOCKET_BAD;
 if(::fcntl(fd,F_SETFD,FD_CLOEXEC)<0){::close(fd);return CURL_SOCKET_BAD;}
#endif
#ifdef SO_NOSIGPIPE
 int enabled=1;if(setsockopt(fd,SOL_SOCKET,SO_NOSIGPIPE,&enabled,sizeof(enabled))!=0){::close(fd);return CURL_SOCKET_BAD;}
#endif
 *slot=fd;f.owner.socketsOpened.fetch_add(1);auto live=f.owner.socketsLive.fetch_add(1)+1,maximum=f.owner.maximumSocketsLive.load();while(live>maximum&&!f.owner.maximumSocketsLive.compare_exchange_weak(maximum,live)){}return fd;
}
inline int closeSocket(void *opaque,curl_socket_t fd)noexcept{static_cast<Frame*>(opaque)->close(fd);return 0;}
inline int refuseResolver(void *,void *,void *opaque)noexcept{static_cast<Frame*>(opaque)->failure=Failure::DNS;return 1;}
inline size_t body(char *data,size_t size,size_t count,void *opaque)noexcept{
 auto &f=*static_cast<Frame*>(opaque);if(size&&count>SIZE_MAX/size){f.failure=Failure::Limit;return 0;}auto length=size*count;
 if(length>f.replyLimit-f.response.body.size()){f.failure=Failure::Limit;return 0;}
 try{auto *p=reinterpret_cast<uint8_t*>(data);f.response.body.insert(f.response.body.end(),p,p+length);return length;}catch(const std::bad_alloc&){f.failure=Failure::Memory;}catch(...){f.failure=Failure::Protocol;}return 0;
}
inline size_t headers(char *data,size_t size,size_t count,void *opaque)noexcept{
 auto &f=*static_cast<Frame*>(opaque);if(size&&count>SIZE_MAX/size){f.failure=Failure::Limit;return 0;}auto length=size*count;
 if(length>65536-f.headerBytes){f.failure=Failure::Limit;return 0;}f.headerBytes+=length;
 try{
  std::string_view line(data,length);if(!line.ends_with("\r\n")){f.failure=Failure::Protocol;return 0;}line.remove_suffix(2);if(line.empty())return length;
  if(line.starts_with("HTTP/")){f.response.headers.clear();return length;}
  auto colon=line.find(':');if(colon==std::string_view::npos||!colon||colon>128){f.failure=Failure::Protocol;return 0;}
  auto name=line.substr(0,colon);for(unsigned char c:name)if(!token(c)){f.failure=Failure::Protocol;return 0;}
  auto value=line.substr(colon+1);while(!value.empty()&&(value.front()==' '||value.front()=='\t'))value.remove_prefix(1);while(!value.empty()&&(value.back()==' '||value.back()=='\t'))value.remove_suffix(1);
  for(unsigned char c:value)if((c<32&&c!=9)||c==127){f.failure=Failure::Protocol;return 0;}
  if(f.response.headers.size()==64){f.failure=Failure::Limit;return 0;}f.response.headers.push_back({lower(std::string(name)),{value.begin(),value.end()}});return length;
 }catch(const std::bad_alloc&){f.failure=Failure::Memory;}catch(...){f.failure=Failure::Protocol;}return 0;
}
inline CURLcode sslContext(CURL *,void *context,void *)noexcept{auto *ctx=static_cast<SSL_CTX*>(context);SSL_CTX_set_verify_depth(ctx,8);SSL_CTX_set_max_cert_list(ctx,65536);SSL_CTX_set_keylog_callback(ctx,nullptr);return CURLE_OK;}
inline void checked(CURLcode status){if(status==CURLE_OUT_OF_MEMORY)throw std::bad_alloc();if(status!=CURLE_OK)throw nexrt::DataError("E_HTTP",std::string("HTTP option configuration failed: ")+curl_easy_strerror(status));}
struct Transfer {
 Frame frame;CURL *easy=nullptr;CURLM *multi=nullptr;curl_slist *requestHeaders=nullptr,*resolved=nullptr;bool attached=false;
 Transfer(Context &owner,size_t limit,unsigned port,const std::vector<std::string> &addresses):frame(owner,limit,port,addresses){easy=curl_easy_init();if(!easy)throw std::bad_alloc();multi=curl_multi_init();if(!multi){curl_easy_cleanup(easy);easy=nullptr;throw std::bad_alloc();}}
 ~Transfer(){if(attached)curl_multi_remove_handle(multi,easy);if(easy)curl_easy_cleanup(easy);if(multi)curl_multi_cleanup(multi);curl_slist_free_all(requestHeaders);curl_slist_free_all(resolved);}
 void append(curl_slist *&list,const std::string &text){auto *next=curl_slist_append(list,text.c_str());if(!next)throw std::bad_alloc();list=next;}
};
inline void configure(Transfer &t,const Config &config,const Request &request,const URL &url,const std::vector<std::string> &addresses,int64_t totalReplyLimit){
 auto *c=t.easy;
  checked(curl_easy_setopt(c,CURLOPT_URL,url.text.c_str()));checked(curl_easy_setopt(c,CURLOPT_PROTOCOLS_STR,"http,https"));checked(curl_easy_setopt(c,CURLOPT_REDIR_PROTOCOLS_STR,"http,https"));checked(curl_easy_setopt(c,CURLOPT_FOLLOWLOCATION,0L));checked(curl_easy_setopt(c,CURLOPT_PROXY,""));/* NETRC parser is absent in the pinned build; its removed option is unavailable. */
  checked(curl_easy_setopt(c,CURLOPT_NOSIGNAL,1L));checked(curl_easy_setopt(c,CURLOPT_FRESH_CONNECT,1L));checked(curl_easy_setopt(c,CURLOPT_FORBID_REUSE,1L));checked(curl_easy_setopt(c,CURLOPT_HTTP09_ALLOWED,0L));checked(curl_easy_setopt(c,CURLOPT_MAXFILESIZE_LARGE,curl_off_t(totalReplyLimit)));checked(curl_easy_setopt(c,CURLOPT_HTTP_CONTENT_DECODING,0L));
  checked(curl_easy_setopt(c,CURLOPT_SSL_VERIFYPEER,1L));checked(curl_easy_setopt(c,CURLOPT_SSL_VERIFYHOST,2L));checked(curl_easy_setopt(c,CURLOPT_SSLVERSION,long(CURL_SSLVERSION_TLSv1_2)));checked(curl_easy_setopt(c,CURLOPT_SSL_CTX_FUNCTION,sslContext));
  curl_blob ca{const_cast<char*>(config.ca.data()),config.ca.size(),CURL_BLOB_NOCOPY};if(url.scheme=="https"){if(config.ca.empty())throw nexrt::DataError("CAPABILITY","HTTPS authority has no pinned CA bundle");checked(curl_easy_setopt(c,CURLOPT_CAINFO_BLOB,&ca));}
  checked(curl_easy_setopt(c,CURLOPT_HTTP_VERSION,long(request.protocol=="1.1"?CURL_HTTP_VERSION_1_1:request.protocol=="2"?CURL_HTTP_VERSION_2_PRIOR_KNOWLEDGE:CURL_HTTP_VERSION_2TLS)));
  checked(curl_easy_setopt(c,CURLOPT_OPENSOCKETFUNCTION,openSocket));checked(curl_easy_setopt(c,CURLOPT_OPENSOCKETDATA,&t.frame));checked(curl_easy_setopt(c,CURLOPT_CLOSESOCKETFUNCTION,closeSocket));checked(curl_easy_setopt(c,CURLOPT_CLOSESOCKETDATA,&t.frame));checked(curl_easy_setopt(c,CURLOPT_RESOLVER_START_FUNCTION,refuseResolver));checked(curl_easy_setopt(c,CURLOPT_RESOLVER_START_DATA,&t.frame));
  checked(curl_easy_setopt(c,CURLOPT_WRITEFUNCTION,body));checked(curl_easy_setopt(c,CURLOPT_WRITEDATA,&t.frame));checked(curl_easy_setopt(c,CURLOPT_HEADERFUNCTION,headers));checked(curl_easy_setopt(c,CURLOPT_HEADERDATA,&t.frame));
  {std::string entry=(url.host.find(':')==std::string::npos?url.host:"["+url.host+"]")+":"+std::to_string(url.port)+":";for(size_t i=0;i<addresses.size();++i){if(i)entry+=",";entry+=addresses[i].find(':')==std::string::npos?addresses[i]:"["+addresses[i]+"]";}t.append(t.resolved,entry);checked(curl_easy_setopt(c,CURLOPT_RESOLVE,t.resolved));}
  bool contentType=false;for(const auto &h:request.headers){if(lower(h.name)=="content-type")contentType=true;t.append(t.requestHeaders,h.name+(h.value.empty()?";":": "+std::string(h.value.begin(),h.value.end())));}
  if(!contentType)t.append(t.requestHeaders,"Content-Type:");checked(curl_easy_setopt(c,CURLOPT_HTTPHEADER,t.requestHeaders));
  if(request.method=="HEAD")checked(curl_easy_setopt(c,CURLOPT_NOBODY,1L));
  else if(!request.body.empty()||request.method=="POST"||request.method=="PUT"||request.method=="PATCH"){checked(curl_easy_setopt(c,CURLOPT_POSTFIELDS,request.body.empty()?"":reinterpret_cast<const char*>(request.body.data())));checked(curl_easy_setopt(c,CURLOPT_POSTFIELDSIZE_LARGE,curl_off_t(request.body.size())));}
  checked(curl_easy_setopt(c,CURLOPT_CUSTOMREQUEST,request.method.c_str()));
  if(curl_multi_setopt(t.multi,CURLMOPT_MAX_TOTAL_CONNECTIONS,2L)!=CURLM_OK||curl_multi_setopt(t.multi,CURLMOPT_MAX_HOST_CONNECTIONS,2L)!=CURLM_OK||curl_multi_add_handle(t.multi,c)!=CURLM_OK)throw nexrt::DataError("E_HTTP","HTTP transfer initialization failed");t.attached=true;
}
inline Response hop(Context &owner,const Config &config,const Request &request,const URL &url,Clock::time_point deadline,const std::function<void()> &pollParent){
 pollParent();auto remaining=std::chrono::duration_cast<std::chrono::milliseconds>(deadline-Clock::now()).count();if(remaining<1)throw nexrt::DataError("E_HTTP_TIMEOUT","HTTP deadline expired");
 std::vector<std::string> addresses;if(url.numeric)addresses.push_back(url.host);else{try{addresses=nex_dns::lookup(owner,url.host,64,unsigned(remaining),config.servers.c_str(),pollParent);}catch(const nexrt::DataError &e){if(e.code=="E_DNS_TIMEOUT")throw nexrt::DataError("E_HTTP_TIMEOUT","HTTP deadline expired during DNS");throw;}}
 Response result;
 {
  Transfer t(owner,size_t(request.replyLimit),url.port,addresses);auto *c=t.easy;
  configure(t,config,request,url,addresses,request.replyLimit);
  int running=0;
  for(;;){pollParent();if(Clock::now()>=deadline)throw nexrt::DataError("E_HTTP_TIMEOUT","HTTP deadline expired");auto status=curl_multi_perform(t.multi,&running);if(status!=CURLM_OK)throw nexrt::DataError("E_HTTP","HTTP transfer event processing failed");if(!running)break;remaining=std::chrono::duration_cast<std::chrono::milliseconds>(deadline-Clock::now()).count();if(curl_multi_poll(t.multi,nullptr,0,int(std::max<int64_t>(0,std::min<int64_t>(20,remaining))),nullptr)!=CURLM_OK)throw nexrt::DataError("E_HTTP","HTTP socket polling failed");}
  pollParent();if(Clock::now()>=deadline)throw nexrt::DataError("E_HTTP_TIMEOUT","HTTP deadline expired");
  if(t.frame.failure==Failure::Memory)throw std::bad_alloc();if(t.frame.failure==Failure::Limit)throw nexrt::DataError("E_HTTP_LIMIT","HTTP response or socket bound exceeded");if(t.frame.failure==Failure::Address)throw nexrt::DataError("CAPABILITY","HTTP transport attempted an unapproved socket address");if(t.frame.failure==Failure::DNS)throw nexrt::DataError("CAPABILITY","HTTP transport attempted a fallback DNS lookup");if(t.frame.failure!=Failure::None)throw nexrt::DataError("E_HTTP","invalid HTTP response");
  int messages=0;auto *message=curl_multi_info_read(t.multi,&messages);if(!message||message->msg!=CURLMSG_DONE)throw nexrt::DataError("E_HTTP","HTTP completion is missing");auto code=message->data.result;
  if(code==CURLE_OUT_OF_MEMORY)throw std::bad_alloc();if(code==CURLE_FILESIZE_EXCEEDED)throw nexrt::DataError("E_HTTP_LIMIT","HTTP response exceeds its byte limit");
  if(code==CURLE_PEER_FAILED_VERIFICATION||code==CURLE_SSL_CONNECT_ERROR||code==CURLE_SSL_CACERT_BADFILE||code==CURLE_SSL_CERTPROBLEM||code==CURLE_SSL_ISSUER_ERROR)throw nexrt::DataError("E_TLS",curl_easy_strerror(code));if(code!=CURLE_OK)throw nexrt::DataError("E_HTTP",curl_easy_strerror(code));
  long status=0,version=0;checked(curl_easy_getinfo(c,CURLINFO_RESPONSE_CODE,&status));checked(curl_easy_getinfo(c,CURLINFO_HTTP_VERSION,&version));if(status<100||status>999)throw nexrt::DataError("E_HTTP","invalid HTTP status");
  t.frame.response.status=status;t.frame.response.protocol=version==CURL_HTTP_VERSION_2_0?"2":version==CURL_HTTP_VERSION_1_1?"1.1":version==CURL_HTTP_VERSION_1_0?"1.0":"unknown";t.frame.response.url=url.text;result=std::move(t.frame.response);
 }
 return result;
}
inline Response execute(Context &owner,const Config &config,Request request,const std::function<void()> &pollParent){
 pollParent();validate(request);auto deadline=Clock::now()+std::chrono::milliseconds(request.timeout);auto url=std::make_unique<URL>(request.url);
 for(int64_t redirect=0;;++redirect){const auto &rule=authorize(config,request,*url);if(url->scheme=="https"&&config.ca.empty())throw nexrt::DataError("CAPABILITY","HTTPS authority requires pinned CA trust");auto response=hop(owner,config,request,*url,deadline,pollParent);
  bool changed=response.status==301||response.status==302||response.status==303||response.status==307||response.status==308;const Header *location=nullptr;for(const auto &h:response.headers)if(h.name=="location"){if(location)throw nexrt::DataError("E_HTTP","multiple HTTP redirect locations");location=&h;}
  if(!changed||!location||request.redirectLimit==0)return response;if(redirect==request.redirectLimit)throw nexrt::DataError("E_HTTP_REDIRECT","HTTP redirect bound exceeded");
  std::string target(location->value.begin(),location->value.end());for(unsigned char c:target)if(c<33||c>126)throw nexrt::DataError("E_HTTP","redirect URL requires percent-encoded ASCII");auto next=std::make_unique<URL>(target,url.get());
  if(url->scheme=="https"&&next->scheme!="https")throw nexrt::DataError("CAPABILITY","HTTPS redirect downgrade is unavailable");
  bool cross=!url->sameOrigin(*next);if(cross&&!rule.crossOriginRedirects)throw nexrt::DataError("CAPABILITY","cross-origin redirect is outside the selected policy");
  if(cross)request.headers.erase(std::remove_if(request.headers.begin(),request.headers.end(),[](const auto &h){return sensitive(h.name);}),request.headers.end());
  if((response.status==303&&request.method!="HEAD")||((response.status==301||response.status==302)&&request.method=="POST")){request.method="GET";request.body.clear();request.headers.erase(std::remove_if(request.headers.begin(),request.headers.end(),[](const auto &h){auto name=lower(h.name);return name=="content-type"||name=="content-encoding";}),request.headers.end());}
  authorize(config,request,*next);url=std::move(next);
 }
}
}
